import anthropic
import json
import os


def detect_clips(transcript_text: str, stream_title: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""Sen bir oyun yayını editörüsün. Aşağıda '{stream_title}' adlı Kick yayınının transkripti var.

Bu transkriptten viral olabilecek TÜM ilgi çekici anları bul — kaç tane olursa olsun, hepsini listele.
Sonra onları viral potansiyeline göre en iyiden en kötüye sırala.
En iyi 10 tanesini döndür.

Her an için şunlara bak:
- Güçlü/heyecanlı oyun anları
- Komik tepkiler veya sözler
- Beklenmedik olaylar
- İzleyicinin "bunu arkadaşıma gönderirim" diyeceği anlar
- Duygusal veya çok konuşulan anlar

Kural:
- Her klip MAXIMUM 60 saniye (tercihen 30-60 sn arası)
- Minimum 20 saniye
- Klipler birbiriyle çakışmasın

Her klibin sonuna "score" alanı ekle (1-10 arası viral potansiyeli puanı).
SADECE JSON döndür, başka hiçbir şey yazma. Format:
[
  {{
    "title": "YouTube Shorts başlığı (Türkçe, dikkat çekici, max 60 karakter) #Shorts",
    "start_seconds": 120,
    "end_seconds": 175,
    "description": "Klibin kısa açıklaması",
    "caption": "YouTube Shorts açıklaması — 3-4 satır, Türkçe, enerjik, emoji kullan, sonuna ilgili hashtagler ekle (#feronline #kick #gaming #shorts vb.)",
    "tags": ["tag1", "tag2", "gaming", "shorts"],
    "score": 9
  }}
]

Transkript:
{transcript_text[:15000]}
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip().strip("```json").strip("```").strip()
    clips = json.loads(raw)

    # Score'a göre sırala, en iyi 10'u al
    clips.sort(key=lambda x: x.get("score", 0), reverse=True)
    clips = clips[:10]

    # 60 saniyelik limiti zorla
    for clip in clips:
        if clip["end_seconds"] - clip["start_seconds"] > 60:
            clip["end_seconds"] = clip["start_seconds"] + 60

    print(f"Claude {len(clips)} klip seçti (en iyi 10).")
    for i, c in enumerate(clips):
        print(f"  {i+1}. [{c.get('score', '?')}/10] {c['title'][:50]}")

    return clips
