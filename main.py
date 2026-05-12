import os
import re
import sys
import subprocess
import shutil
import json
from datetime import datetime, timezone, timedelta

from src.kick_monitor import check_new_vod, save_last_processed_id
from src.transcriber import extract_audio, transcribe, segments_to_text
from src.clip_detector import detect_clips
from src.audio_analyzer import detect_spikes, spikes_to_text, spikes_to_clips
from src.video_processor import process_clips
from src.youtube_uploader import upload_clip, upload_all_clips, PUBLISH_INTERVAL_HOURS, MAX_UPLOADS_PER_RUN
from src.notifier import notify_clip_uploaded, notify_error, notify_no_clips
from src.performance_tracker import (log_upload, get_performance_context, should_skip_category,
                                      get_pending_tiktok_uploads, mark_tiktok_uploaded)
from src.drive_sheets import (log_to_sheets, ensure_sheet_headers,
                               get_pending_clips, update_clip_status)
from src.github_storage import upload_clip as gh_upload, download_clip as gh_download, delete_clip as gh_delete
from src.tiktok_uploader import upload_to_tiktok

WORK_DIR = "workspace"
_GA = bool(os.environ.get("GITHUB_ACTIONS"))


def notice(msg: str):
    prefix = "::notice::" if _GA else ""
    print(f"{prefix}{msg}", flush=True)


def download_vod(vod: dict) -> str:
    os.makedirs(WORK_DIR, exist_ok=True)
    output_path = os.path.join(WORK_DIR, "stream.mp4")

    vod_url = (
        vod.get("source")
        or vod.get("playback_url")
        or f"https://kick.com/video/{vod.get('uuid') or vod.get('id')}"
    )

    print(f"⬇️  İndiriliyor: {vod_url}")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
        "--quiet", "--no-warnings",
        "-o", output_path,
        vod_url
    ]
    subprocess.run(cmd, check=True)
    print("✅ İndirme tamamlandı.")
    return output_path


def cleanup():
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)
        print("Geçici dosyalar temizlendi.")


def _save_clips_to_storage_and_sheets(clips: list[dict], stream_title: str, category: str, sheet_id: str):
    """Her klip için GitHub'a yükle + Sheets'e 'Bekliyor' olarak kaydet."""
    for clip in clips:
        file_link = ""
        try:
            safe = (clip["title"][:50].replace("/", "-").replace("\\", "-")
                    + f"_{clip.get('start_seconds', 0):.0f}.mp4")
            file_link = gh_upload(clip["file_path"], safe)
        except Exception as e:
            notice(f"  ⚠️ GitHub yükleme hatası: {e}")

        if sheet_id:
            try:
                log_to_sheets(sheet_id, {
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "stream_title": stream_title,
                    "category": category,
                    "title": clip["title"],
                    "duration": f"{clip.get('end_seconds', 0) - clip.get('start_seconds', 0):.0f}",
                    "score": clip.get("score", ""),
                    "status": "Bekliyor",
                    "publish_at": "",
                    "youtube_link": "",
                    "tiktok_link": "",
                    "drive_link": file_link,
                    "description": clip.get("caption", clip.get("description", "")),
                })
                notice(f"  📝 Kaydedildi: {clip['title'][:50]}")
            except Exception as e:
                notice(f"  ⚠️ Sheets kayıt hatası: {e}")


def _upload_pending_from_sheets(sheet_id: str):
    """Sheets'teki 'Bekliyor' klipleri GitHub'dan indirip YouTube'a yükle."""
    from googleapiclient.errors import HttpError

    pending = get_pending_clips(sheet_id)
    if not pending:
        notice("📭 Sheetste bekleyen klip yok.")
        return

    notice(f"📤 Sheetste {len(pending)} bekleyen klip var, YouTube kotası varsa yükleniyor...")
    os.makedirs(os.path.join(WORK_DIR, "clips"), exist_ok=True)

    now = datetime.now(timezone.utc)
    publish_time = now + timedelta(hours=1)
    uploaded = 0

    for idx, info in enumerate(pending[:MAX_UPLOADS_PER_RUN]):
        file_link = info.get("drive_link", "")
        if not file_link:
            notice(f"  ⚠️ Dosya linki yok, atlanıyor: {info['title'][:40]}")
            continue

        filename = file_link.split("/")[-1]
        local_path = os.path.join(WORK_DIR, "clips", filename)

        if not os.path.exists(local_path):
            try:
                notice(f"  ⬇️  GitHub'dan indiriliyor: {info['title'][:40]}")
                gh_download(file_link, local_path)
            except Exception as e:
                notice(f"  ⚠️ GitHub indirme hatası: {e}")
                continue

        clip = {
            "title": info["title"],
            "file_path": local_path,
            "caption": info.get("description", ""),
        }

        try:
            video_id = upload_clip(clip, publish_at=publish_time)
        except HttpError as e:
            reason = ""
            try:
                details = json.loads(e.content)
                reason = details.get("error", {}).get("errors", [{}])[0].get("reason", "")
            except Exception:
                pass
            if reason == "uploadLimitExceeded":
                notice("⚠️ YouTube günlük kotası doldu, bu run'da daha fazla yüklenemiyor.")
                break
            raise

        youtube_link = f"https://youtube.com/shorts/{video_id}"
        publish_at_str = publish_time.strftime("%Y-%m-%d %H:%M UTC")

        tiktok_url = ""
        if os.environ.get("TIKTOK_COOKIES"):
            try:
                tiktok_url = upload_to_tiktok(clip, schedule_at=publish_time) or ""
                if tiktok_url:
                    mark_tiktok_uploaded(video_id)
            except Exception as e:
                notice(f"  ⚠️ TikTok yükleme hatası: {e}")

        try:
            update_clip_status(sheet_id, info["row_index"], youtube_link, publish_at_str, tiktok_url)
        except Exception as e:
            notice(f"  ⚠️ Sheets güncelleme hatası: {e}")

        notify_clip_uploaded(info["title"], video_id, idx + 1, len(pending), tiktok_url=tiktok_url)
        log_upload(video_id, info["title"], info.get("category", "Genel"), file_path=local_path)
        notice(f"  ✅ [{idx + 1}/{len(pending)}] Yüklendi: {info['title'][:50]}")

        # YouTube'a yüklendi, GitHub asset'i temizle
        try:
            gh_delete(file_link)
        except Exception:
            pass

        publish_time += timedelta(hours=PUBLISH_INTERVAL_HOURS)
        uploaded += 1

    notice(f"✅ Bu run'da {uploaded} klip YouTube'a yüklendi.")


def main():
    notice("🚀 Kick → YouTube Otomasyonu başlatıldı")

    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
    if sheet_id:
        try:
            ensure_sheet_headers(sheet_id)
        except Exception as e:
            notice(f"⚠️ Sheets başlık kontrolü hatası: {e}")

    # TikTok'a yüklenmemiş klipler var mı?
    if os.environ.get("TIKTOK_COOKIES"):
        pending_tiktok = get_pending_tiktok_uploads()
        if pending_tiktok:
            notice(f"📱 TikTok'a yüklenmemiş {len(pending_tiktok)} klip var, yükleniyor...")
            for clip in pending_tiktok:
                if os.path.exists(clip.get("file_path", "")):
                    ok = upload_to_tiktok(clip)
                    if ok:
                        mark_tiktok_uploaded(clip["video_id"])
                else:
                    mark_tiktok_uploaded(clip["video_id"])

    notice("🔍 Yeni VOD kontrol ediliyor...")
    vod = check_new_vod()

    if vod:
        vod_id = str(vod.get("id") or vod.get("uuid"))
        stream_title = vod.get("_title") or vod.get("title") or "Kick Yayın Tekrarı"
        category = vod.get("_category", "Genel")
        notice(f"✅ Yeni VOD bulundu: {stream_title} ({category})")

        if should_skip_category(category):
            notice(f"⏭️ '{category}' düşük performanslı kategori, atlanıyor.")
            save_last_processed_id(vod_id)
        else:
            try:
                notice("⬇️ VOD indiriliyor...")
                video_path = download_vod(vod)

                notice("🎤 Ses çıkarılıyor ve transkript oluşturuluyor...")
                audio_path = extract_audio(video_path)
                segments = transcribe(audio_path)
                notice(f"✅ Transkript hazır: {len(segments)} segment")

                transcript_text = segments_to_text(segments)
                spikes = detect_spikes(audio_path)
                audio_spikes_text = spikes_to_text(spikes)
                os.remove(audio_path)

                notice("🎯 Claude klipler arıyor...")
                performance_context = get_performance_context()
                clips = detect_clips(
                    transcript_text, stream_title, category,
                    audio_spikes_text, performance_context, spikes=spikes
                )

                if not clips:
                    notice("⚠️ Claude klip bulamadı → ses spike fallback devreye giriyor...")
                    clips = spikes_to_clips(spikes, category)

                if not clips:
                    notice("❌ Hiç klip bulunamadı.")
                    save_last_processed_id(vod_id)
                    notify_no_clips()
                else:
                    notice(f"✅ {len(clips)} klip seçildi → videolar işleniyor...")
                    clips_dir = os.path.join(WORK_DIR, "clips")
                    processed_clips = process_clips(video_path, clips, segments, clips_dir)
                    notice(f"✅ {len(processed_clips)} video işlendi")

                    notice("☁️ GitHub'a yükleniyor ve Sheets'e kaydediliyor...")
                    _save_clips_to_storage_and_sheets(processed_clips, stream_title, category, sheet_id)
                    save_last_processed_id(vod_id)

            except Exception as e:
                notice(f"❌ HATA: {e}")
                notify_error(str(e))
                raise
    else:
        notice("⏭️ Yeni VOD yok.")

    # Her run'da: Sheets'teki bekleyenleri YouTube kotası varsa yükle
    if sheet_id:
        try:
            _upload_pending_from_sheets(sheet_id)
        except Exception as e:
            notice(f"❌ Yükleme hatası: {e}")
            notify_error(str(e))
            raise

    notice("🎉 Tamamlandı!")
    cleanup()


if __name__ == "__main__":
    main()
