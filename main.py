import os
import sys
import subprocess
import shutil

from src.kick_monitor import check_new_vod, save_last_processed_id
from src.transcriber import extract_audio, transcribe, segments_to_text
from src.clip_detector import detect_clips
from src.video_processor import process_clips
from src.youtube_uploader import upload_all_clips

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
    stream_title = vod.get("title", "Kick Yayın Tekrarı")

    try:
        video_path = download_vod(vod)

        audio_path = extract_audio(video_path)
        segments = transcribe(audio_path)
        os.remove(audio_path)

        transcript_text = segments_to_text(segments)

        clips = detect_clips(transcript_text, stream_title)

        clips_dir = os.path.join(WORK_DIR, "clips")
        processed_clips = process_clips(video_path, clips, segments, clips_dir)

        video_ids = upload_all_clips(processed_clips)

        save_last_processed_id(vod_id)
        print(f"\n=== Tamamlandı! {len(video_ids)} Shorts yüklendi. ===")

    except Exception as e:
        print(f"HATA: {e}")
        raise
    finally:
        cleanup()


if __name__ == "__main__":
    main()
