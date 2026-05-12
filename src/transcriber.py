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
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        return _transcribe_assemblyai(audio_path)
    return _transcribe_whisper(audio_path)


def _transcribe_assemblyai(audio_path: str) -> list[dict]:
    import requests
    import time
    print("🎙️  Transkript oluşturuluyor (AssemblyAI)...")

    api_key = os.environ["ASSEMBLYAI_API_KEY"]
    headers = {"authorization": api_key}
    base = "https://api.assemblyai.com/v2"

    # Dosyayı yükle
    print("  AssemblyAI: ses dosyası yükleniyor...")
    with open(audio_path, "rb") as f:
        upload = requests.post(f"{base}/upload", headers=headers, data=f, timeout=300)
    upload.raise_for_status()
    audio_url = upload.json()["upload_url"]

    # Transkripsiyon başlat
    payload = {
        "audio_url": audio_url,
        "language_code": "tr",
        "speech_models": ["universal-2"],
    }
    resp = requests.post(f"{base}/transcript", headers={**headers, "content-type": "application/json"},
                         json=payload, timeout=30)
    if not resp.ok:
        print(f"  AssemblyAI hata: {resp.text[:300]}", flush=True)
    resp.raise_for_status()
    transcript_id = resp.json()["id"]
    print(f"  AssemblyAI: transkripsiyon başlatıldı (ID: {transcript_id})")

    # Tamamlanmasını bekle
    while True:
        r = requests.get(f"{base}/transcript/{transcript_id}", headers=headers, timeout=30)
        r.raise_for_status()
        result = r.json()
        status = result["status"]
        if status == "completed":
            break
        elif status == "error":
            print(f"⚠️ AssemblyAI hatası: {result.get('error')}, Whisper'a geçiliyor...")
            return _transcribe_whisper(audio_path)
        print(f"  AssemblyAI: {status}...")
        time.sleep(5)

    # words → segments
    words_raw = result.get("words") or []
    segments, chunk, chunk_start = [], [], None
    for w in words_raw:
        if chunk_start is None:
            chunk_start = w["start"] / 1000
        chunk.append({"word": w["text"], "start": w["start"] / 1000, "end": w["end"] / 1000})
        if len(chunk) >= 8:
            segments.append({
                "start": chunk_start,
                "end": chunk[-1]["end"],
                "text": " ".join(c["word"] for c in chunk),
                "words": chunk,
            })
            chunk, chunk_start = [], None
    if chunk:
        segments.append({
            "start": chunk_start,
            "end": chunk[-1]["end"],
            "text": " ".join(c["word"] for c in chunk),
            "words": chunk,
        })

    print(f"✅ Transkript tamamlandı (AssemblyAI): {len(segments)} segment")
    return segments


def _transcribe_whisper(audio_path: str) -> list[dict]:
    from faster_whisper import WhisperModel
    import logging
    print("🎙️  Transkript oluşturuluyor (faster-whisper medium)...")
    logging.getLogger("faster_whisper").setLevel(logging.ERROR)
    model = WhisperModel("medium", device="cpu", compute_type="int8")
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
    # Impact font, kalın outline, sarı karaoke highlight (SecondaryColour = aktif kelime rengi)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,98,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,6,3,2,20,20,300,1

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
            events.append(
                f"Dialogue: 0,{ts(seg['start'])},{ts(seg['end'])},Default,,0,0,0,,{seg['text'].upper()}"
            )
            continue

        group_size = 3  # 3 kelime → daha büyük ve okunabilir
        for i in range(0, len(words), group_size):
            group = words[i:i + group_size]
            start = group[0]["start"]
            end = group[-1]["end"]
            parts = []
            for w in group:
                dur_cs = max(1, int((w["end"] - w["start"]) * 100))
                # \kf = smooth fill (sarıdan beyaza geçiş)
                parts.append(f"{{\\kf{dur_cs}}}{w['word'].strip().upper()}")
            text = " ".join(parts)
            events.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
