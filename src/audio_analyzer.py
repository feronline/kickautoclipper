import subprocess
import numpy as np


def get_rms_per_second(audio_path: str) -> tuple[np.ndarray, np.ndarray]:
    """FFmpeg ile ses dosyasından ham PCM alır, saniye saniye RMS hesaplar."""
    # 4kHz mono PCM çıkar — memory verimli
    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-ar", "4000", "-ac", "1", "-f", "f32le", "-"
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        return np.array([]), np.array([])

    samples = np.frombuffer(result.stdout, dtype=np.float32)
    sr = 4000

    # Saniye saniye RMS hesapla
    n_seconds = len(samples) // sr
    if n_seconds == 0:
        return np.array([]), np.array([])

    samples = samples[:n_seconds * sr].reshape(n_seconds, sr)
    rms = np.sqrt(np.mean(samples ** 2, axis=1))
    times = np.arange(n_seconds, dtype=float)
    return times, rms


def detect_spikes(audio_path: str, min_gap: float = 30.0) -> list[dict]:
    """
    Ses enerjisi spike'larını tespit eder.
    Konuşma olmasa bile patlama, öldürme sesi gibi anlarda çalışır.
    """
    times, rms = get_rms_per_second(audio_path)
    if len(rms) == 0:
        print("Ses analizi: veri alınamadı.")
        return []

    # Normalleştir
    mean = np.mean(rms)
    std = np.std(rms)
    if std == 0:
        return []

    # Ortalamanın 2 standart sapma üzerindeki anlar = spike
    threshold = mean + 2.0 * std
    spike_times = times[rms > threshold]

    if len(spike_times) == 0:
        print("Ses analizi: belirgin spike bulunamadı.")
        return []

    # Yakın spike'ları grupla → her grup bir klip adayı
    groups = []
    current = [spike_times[0]]
    for t in spike_times[1:]:
        if t - current[-1] < min_gap:
            current.append(t)
        else:
            groups.append(current)
            current = [t]
    groups.append(current)

    total_duration = float(times[-1])
    clips = []
    for group in groups:
        center = float(np.mean(group))
        start = max(0.0, center - 25.0)
        end = min(total_duration, center + 25.0)

        # Bu bölgenin ortalama enerjisine göre skor ver
        region_mask = (times >= start) & (times <= end)
        region_rms = np.mean(rms[region_mask]) if region_mask.any() else mean
        intensity = (region_rms - mean) / (std + 1e-8)
        score = int(np.clip(5 + intensity, 5, 9))

        clips.append({
            "start_seconds": start,
            "end_seconds": end,
            "source": "audio",
            "score": score,
        })

    print(f"Ses analizi: {len(clips)} potansiyel an tespit edildi.")
    return clips


def spikes_to_clips(spikes: list[dict], category: str = "Genel") -> list[dict]:
    """Ses spike'larından direkt klip üret (Claude bulamazsa fallback)."""
    category_tag = category.lower().replace(" ", "")
    clips = []
    for i, s in enumerate(spikes[:10]):
        clips.append({
            **s,
            "title": f"🎮 Heyecanlı an #{i+1} #Shorts",
            "description": f"{category} yayınından ilgi çekici an",
            "caption": f"Yayında dikkat çeken bir an 🎮🔥\n\n#feronline #kick #shorts #{category_tag}",
            "tags": ["feronline", "kick", "shorts", category_tag, "gaming"],
        })
    return clips


LAUGH_TOKENS = [
    "haha", "hehe", "ahaha", "ahahah", "hahah", "heheheh",
    "güldüm", "güldük", "gülüyorum", "çok güldüm", "öldüm gülerek",
    "öldüm", "bitiyorum", "bitim", "kahkaha",
]


def detect_laughs(segments: list[dict]) -> list[dict]:
    """Transkriptten gülme anlarını yüksek öncelikli klip adayı olarak döndürür."""
    laughs = []
    for seg in segments:
        text = seg["text"].lower()
        if any(tok in text for tok in LAUGH_TOKENS):
            laughs.append({
                "start_seconds": max(0.0, seg["start"] - 10.0),
                "end_seconds": seg["end"] + 10.0,
                "source": "laugh",
                "score": 10,
                "text": seg["text"].strip(),
            })
    # Üst üste binen gülmeleri birleştir
    merged = []
    for l in sorted(laughs, key=lambda x: x["start_seconds"]):
        if merged and l["start_seconds"] < merged[-1]["end_seconds"]:
            merged[-1]["end_seconds"] = max(merged[-1]["end_seconds"], l["end_seconds"])
        else:
            merged.append(l)
    if merged:
        print(f"😂 {len(merged)} gülme anı tespit edildi.")
    return merged


def laughs_to_text(laughs: list[dict]) -> str:
    if not laughs:
        return ""
    lines = ["[😂 Gülme anları (EN YÜKSEK ÖNCELİK — mutlaka kliplensin):]"]
    for i, l in enumerate(laughs):
        m_s = int(l["start_seconds"] // 60)
        s_s = int(l["start_seconds"] % 60)
        m_e = int(l["end_seconds"] // 60)
        s_e = int(l["end_seconds"] % 60)
        text_preview = l.get("text", "")[:60]
        lines.append(f"  {i+1}. {m_s:02d}:{s_s:02d}-{m_e:02d}:{s_e:02d} → \"{text_preview}\"")
    return "\n".join(lines)


def spikes_to_text(spikes: list[dict]) -> str:
    """Claude'a geçirmek için spike'ları metin formatına çevir."""
    if not spikes:
        return ""
    lines = ["[Ses analizi ile tespit edilen yüksek enerjili anlar:]"]
    for i, s in enumerate(spikes):
        m_start = int(s["start_seconds"] // 60)
        s_start = int(s["start_seconds"] % 60)
        m_end = int(s["end_seconds"] // 60)
        s_end = int(s["end_seconds"] % 60)
        lines.append(f"  {i+1}. {m_start:02d}:{s_start:02d} - {m_end:02d}:{s_end:02d} (enerji skoru: {s['score']}/9)")
    return "\n".join(lines)
