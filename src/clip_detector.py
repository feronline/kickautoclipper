import anthropic
import json
import os


def detect_clips(transcript_text: str, stream_title: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""Sen bir oyun yayını editörüsün. Aşağıda '{stream_title}' adlı Kick yayınının transkripti var.

Bu transkriptten en ilgi çekici, komik, heyecanlı veya viral olabilecek 3-5 anı tespit et.
Her an için YouTube klibi oluşturulacak.

Şunlara dikkat et:
- Güçlü/heyecanlı oyun anları
- Komik tepkiler veya sözler
- Beklenmedik olaylar
- İzleyicinin "bunu arkadaşıma gönderirim" diyeceği anlar
- Her klip 1-4 dakika uzunluğunda olmalı

SADECE JSON döndür, başka hiçbir şey yazma. Format:
[
  {{
    "title": "YouTube başlığı (Türkçe, dikkat çekici, max 70 karakter)",
    "start_seconds": 120,
    "end_seconds": 240,
    "description": "Klibin kısa açıklaması",
    "tags": ["tag1", "tag2", "tag3"]
  }}
]

Transkript:
{transcript_text[:15000]}
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    raw = raw.strip("```json").strip("```").strip()

    clips = json.loads(raw)
    print(f"Claude {len(clips)} ilgi çekici an tespit etti.")
    return clips
