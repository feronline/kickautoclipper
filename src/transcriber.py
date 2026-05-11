import whisper
import subprocess
import os


def extract_audio(video_path: str) -> str:
    audio_path = video_path.rsplit(".", 1)[0] + ".mp3"
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        audio_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"Ses çıkarıldı: {audio_path}")
    return audio_path


def transcribe(audio_path: str) -> list[dict]:
    print("Whisper ile transkript oluşturuluyor...")
    model = whisper.load_model("tiny")
    result = model.transcribe(audio_path, language="tr", verbose=False, word_timestamps=True)

    segments = []
    for seg in result["segments"]:
        words = [
            {"word": w["word"], "start": w["start"], "end": w["end"]}
            for w in seg.get("words", [])
        ]
        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
            "words": words
        })

    print(f"Transkript tamamlandı: {len(segments)} segment")
    return segments


def segments_to_text(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        m = int(seg["start"] // 60)
        s = int(seg["start"] % 60)
        lines.append(f"[{m:02d}:{s:02d}] {seg['text']}")
    return "\n".join(lines)


def generate_tiktok_ass(segments: list[dict], output_path: str, width=1080, height=1920):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,85,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,1,2,20,20,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def ts(sec: float) -> str:
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    events = []
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            m = int(seg["start"] // 60)
            s = int(seg["start"] % 60)
            events.append(
                f"Dialogue: 0,{ts(seg['start'])},{ts(seg['end'])},Default,,0,0,0,,{seg['text']}"
            )
            continue

        group_size = 4
        for i in range(0, len(words), group_size):
            group = words[i:i + group_size]
            start = group[0]["start"]
            end = group[-1]["end"]
            parts = []
            for w in group:
                dur_cs = max(1, int((w["end"] - w["start"]) * 100))
                parts.append(f"{{\\k{dur_cs}}}{w['word'].strip()}")
            text = " ".join(parts)
            events.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
