import os
import sys
import subprocess
import shutil

from src.kick_monitor import check_new_vod, save_last_processed_id
from src.transcriber import extract_audio, transcribe, segments_to_text
from src.clip_detector import detect_clips
from src.audio_analyzer import detect_spikes, spikes_to_text, spikes_to_clips
from src.video_processor import process_clips
from src.youtube_uploader import upload_all_clips
from src.notifier import notify_clip_uploaded, notify_error, notify_no_clips
from src.performance_tracker import log_upload, get_performance_context
from src.upload_queue import add_to_queue, pop_batch, queue_size
from src.youtube_uploader import MAX_UPLOADS_PER_RUN
from src.drive_sheets import upload_to_drive, log_to_sheets, ensure_sheet_headers

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


def _upload_batch(clips: list[dict]):
    from src.youtube_uploader import upload_all_clips
    def on_uploaded(title, video_id, num, total):
        notify_clip_uploaded(title, video_id, num, total)
        log_upload(video_id, title, clips[num-1].get("category", "Genel"))
    upload_all_clips(clips, on_uploaded=on_uploaded)


def cleanup():
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)
        print("Geçici dosyalar temizlendi.")


def main():
    notice("🚀 Kick → YouTube Otomasyonu başlatıldı")

    # Önce kuyrukta bekleyen klip var mı bak
    qs = queue_size()
    if qs > 0:
        notice(f"📋 Kuyrukta {qs} klip var, önce onları yükle...")
        batch = pop_batch(MAX_UPLOADS_PER_RUN)
        _upload_batch(batch)
        notice(f"✅ Kuyruk yüklemesi tamamlandı")
        return

    notice("🔍 Yeni VOD kontrol ediliyor...")
    vod = check_new_vod()
    if not vod:
        notice("⏭️ Yeni VOD yok. İşlem yok.")
        return

    vod_id = str(vod.get("id") or vod.get("uuid"))
    stream_title = vod.get("_title") or vod.get("title") or "Kick Yayın Tekrarı"
    category = vod.get("_category", "Genel")
    notice(f"✅ Yeni VOD bulundu: {stream_title} ({category})")

    try:
        notice("⬇️ VOD indiriliyor...")
        video_path = download_vod(vod)
        notice("✅ İndirme tamamlandı")

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
        clips = detect_clips(transcript_text, stream_title, category, audio_spikes_text, performance_context, spikes=spikes)

        if not clips:
            notice("⚠️ Claude klip bulamadı → ses spike fallback devreye giriyor...")
            clips = spikes_to_clips(spikes, category)

        if not clips:
            notice("❌ Hiç klip bulunamadı. İşlem tamamlandı.")
            save_last_processed_id(vod_id)
            notify_no_clips()
            return

        notice(f"✅ {len(clips)} klip seçildi → videolar işleniyor...")
        clips_dir = os.path.join(WORK_DIR, "clips")
        processed_clips = process_clips(video_path, clips, segments, clips_dir)
        notice(f"✅ {len(processed_clips)} video işlendi")

        to_upload = processed_clips[:MAX_UPLOADS_PER_RUN]
        to_queue = processed_clips[MAX_UPLOADS_PER_RUN:]

        if to_queue:
            add_to_queue([{**c, "category": category} for c in to_queue])
            notice(f"📋 {len(to_queue)} klip kuyruğa eklendi (sonraki run'da yüklenecek)")

        sheet_id = os.environ.get("GOOGLE_SHEET_ID", "")
        if sheet_id:
            ensure_sheet_headers(sheet_id)

        notice(f"📤 {len(to_upload)} klip YouTube'a yükleniyor...")

        publish_times = {}

        def on_uploaded(title, video_id, num, total):
            from datetime import datetime, timezone, timedelta
            notify_clip_uploaded(title, video_id, num, total)
            notice(f"  ✅ [{num}/{total}] Yüklendi: {title[:50]}")
            source = next((c.get("source", "transcript") for c in processed_clips if c["title"] == title), "transcript")
            log_upload(video_id, title, category, source)

            clip = next((c for c in processed_clips if c["title"] == title), {})
            publish_at = publish_times.get(title, "")

            drive_link = ""
            if os.environ.get("GOOGLE_DRIVE_FOLDER_ID") or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
                try:
                    safe_name = title[:50].replace("/", "-").replace("\\", "-") + f"_{video_id}.mp4"
                    drive_link = upload_to_drive(clip.get("file_path", ""), safe_name)
                except Exception as e:
                    print(f"  ⚠️ Drive yükleme hatası: {e}")

            if sheet_id:
                try:
                    log_to_sheets(sheet_id, {
                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                        "stream_title": stream_title,
                        "category": category,
                        "title": title,
                        "duration": f"{clip.get('end_seconds', 0) - clip.get('start_seconds', 0):.0f}",
                        "score": clip.get("score", ""),
                        "status": "Yüklendi ✅",
                        "publish_at": publish_at,
                        "youtube_link": f"https://youtube.com/shorts/{video_id}",
                        "drive_link": drive_link,
                        "description": clip.get("caption", clip.get("description", "")),
                    })
                except Exception as e:
                    print(f"  ⚠️ Sheets kayıt hatası: {e}")

        from src.youtube_uploader import PUBLISH_INTERVAL_HOURS
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        for i, clip in enumerate(to_upload):
            t = now + timedelta(hours=1) + timedelta(hours=PUBLISH_INTERVAL_HOURS * i)
            publish_times[clip["title"]] = t.strftime("%Y-%m-%d %H:%M UTC")

        video_ids = upload_all_clips(to_upload, on_uploaded=on_uploaded)

        save_last_processed_id(vod_id)
        notice(f"🎉 Tamamlandı! {len(video_ids)} Shorts yüklendi.")

    except Exception as e:
        notice(f"❌ HATA: {e}")
        notify_error(str(e))
        raise
    finally:
        cleanup()


if __name__ == "__main__":
    main()
