import subprocess
import os


def extract_audio(video_path: str) -> str:
    audio_path = video_path.rsplit(".", 1)[0] + ".mp3"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        audio_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"✅ Ses çıkarıldı.")
    return audio_path


def transcribe(audio_path: str) -> list[dict]:
    return _transcribe_whisper(audio_path)


def _transcribe_whisper(audio_path: str) -> list[dict]:
    from faster_whisper import WhisperModel
    import logging
    print("🎙️  Transkript oluşturuluyor (faster-whisper large-v3)...")
    logging.getLogger("faster_whisper").setLevel(logging.ERROR)
    model = WhisperModel("large-v3", device="cpu", compute_type="int8")
    result_segments, _ = model.transcribe(
        audio_path,
        language="tr",
        word_timestamps=True,
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        condition_on_previous_text=False,
        temperature=0.0,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    segments = []
    for seg in result_segments:
        text = seg.text.strip()
        if not text or len(text) < 3:
            continue
        if seg.no_speech_prob > 0.6:
            continue
        words = [
            {"word": w.word, "start": w.start, "end": w.end}
            for w in (seg.words or [])
        ]
        segments.append({"start": seg.start, "end": seg.end, "text": text, "words": words})

    print(f"✅ Transkript tamamlandı (Whisper): {len(segments)} segment")
    return segments


def segments_to_text(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        m = int(seg["start"] // 60)
        s = int(seg["start"] % 60)
        lines.append(f"[{m:02d}:{s:02d}] {seg['text']}")
    return "\n".join(lines)


def generate_tiktok_ass(segments: list[dict], output_path: str, width=1080, height=1920):
    # Düz TikTok tarzı: beyaz yazı + siyah kontur, animasyon yok
    # Sadece kelime söylenirken görünür (word-level timing)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,7,0,2,40,40,320,1

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
            continue

        group_size = 3
        for i in range(0, len(words), group_size):
            group = words[i:i + group_size]
            start = group[0]["start"]
            end = group[-1]["end"]
            if end - start < 0.15:
                end = start + 0.15
            text = " ".join(w["word"].strip().upper() for w in group)
            events.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
