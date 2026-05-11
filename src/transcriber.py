import whisper
import subprocess
import os


def extract_audio(video_path: str) -> str:
    audio_path = video_path.rsplit(".", 1)[0] + ".mp3"
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-b:a", "64k",
        audio_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"Ses çıkarıldı: {audio_path}")
    return audio_path


def transcribe(audio_path: str) -> list[dict]:
    print("Whisper ile transkript oluşturuluyor (base model)...")
    model = whisper.load_model("base")
    result = model.transcribe(audio_path, language="tr", verbose=False)

    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip()
        })

    print(f"Transkript tamamlandı: {len(segments)} segment")
    return segments


def segments_to_text(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        minutes = int(seg["start"] // 60)
        seconds = int(seg["start"] % 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {seg['text']}")
    return "\n".join(lines)


def segments_to_srt(segments: list[dict], output_path: str):
    def fmt(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{fmt(seg['start'])} --> {fmt(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")
