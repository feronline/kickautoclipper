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

WORK_DIR = "workspace"


def download_vod(vod: dict) -> str:
    os.makedirs(WORK_DIR, exist_ok=True)
    output_path = os.path.join(WORK_DIR, "stream.mp4")

    vod_url = (
        vod.get("source")
        or vod.get("playback_url")
        or f"https://kick.com/video/{vod.get('uuid') or vod.get('id')}"
    )

    print(f"İndiriliyor: {vod_url}")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
        "--quiet", "--progress",
        "--progress-template", "[download] %(progress._percent_str)s %(progress._speed_str)s ETA %(progress._eta_str)s",
        "-o", output_path,
        vod_url
    ]
    subprocess.run(cmd, check=True)
    return output_path


def cleanup():
    if os.path.exists(WORK_DIR):
        shutil.rmtree(WORK_DIR)
        print("Geçici dosyalar temizlendi.")


def main():
    print("=== Kick → YouTube Otomasyonu Başlatıldı ===")

    vod = check_new_vod()
    if not vod:
        print("İşlem yok. Çıkılıyor.")
        return

    vod_id = str(vod.get("id") or vod.get("uuid"))
    stream_title = vod.get("_title") or vod.get("title") or "Kick Yayın Tekrarı"
    category = vod.get("_category", "Genel")

    try:
        video_path = download_vod(vod)

        audio_path = extract_audio(video_path)
        segments = transcribe(audio_path)

        transcript_text = segments_to_text(segments)
        spikes = detect_spikes(audio_path)
        audio_spikes_text = spikes_to_text(spikes)

        os.remove(audio_path)

        performance_context = get_performance_context()
        clips = detect_clips(transcript_text, stream_title, category, audio_spikes_text, performance_context)

        if not clips:
            print("Claude klip bulamadı, ses spike fallback'e geçiliyor...")
            clips = spikes_to_clips(spikes, category)

        if not clips:
            print("Hiç klip bulunamadı. İşlem tamamlandı.")
            save_last_processed_id(vod_id)
            notify_no_clips()
            return

        clips_dir = os.path.join(WORK_DIR, "clips")
        processed_clips = process_clips(video_path, clips, segments, clips_dir)

        def on_uploaded(title, video_id, num, total):
            notify_clip_uploaded(title, video_id, num, total)
            source = next((c.get("source", "transcript") for c in processed_clips if c["title"] == title), "transcript")
            log_upload(video_id, title, category, source)

        video_ids = upload_all_clips(processed_clips, on_uploaded=on_uploaded)

        save_last_processed_id(vod_id)
        print(f"\n=== Tamamlandı! {len(video_ids)} Shorts yüklendi. ===")

    except Exception as e:
        print(f"HATA: {e}")
        notify_error(str(e))
        raise
    finally:
        cleanup()


if __name__ == "__main__":
    main()
