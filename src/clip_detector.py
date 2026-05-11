import anthropic
import json
import os

MIN_SCORE = 5  # Bu puanın altındaki klipler atlanır


CATEGORY_INSTRUCTIONS = {
    "valorant": (
        "Bu bir Valorant yayını. Şunlara bak: ace, clutch, multi-kill, inanılmaz atış, "
        "düşmana güzel kapan, maç kazanma anı, sinirlenme veya kutlama. "
        "Caption'lar Valorant terimleri içersin (clutch, ace, ranked, radiant vb.)."
    ),
    "just chatting": (
        "Bu bir Just Chatting yayını. Şunlara bak: çok güldüğü anlar, ilginç hikayeler, "
        "beklenmedik tepkiler, izleyiciyle komik diyaloglar, yüksek sesle güldüğü yerler. "
        "Caption'lar sohbet ve eğlence odaklı olsun."
    ),
    "minecraft": (
        "Bu bir Minecraft yayını. Şunlara bak: büyük yapılar, ölüm anları, güzel buluşlar, "
        "komik olaylar, büyük başarılar. Caption'lar Minecraft temalı olsun."
    ),
}

DEFAULT_INSTRUCTION = (
    "Güçlü/heyecanlı oyun anları, komik tepkiler, beklenmedik olaylar ve "
    "izleyicinin arkadaşına göndereceği anları bul."
)


def get_category_instruction(category: str) -> str:
    key = category.lower().strip()
    for k, v in CATEGORY_INSTRUCTIONS.items():
        if k in key:
            return v
    return DEFAULT_INSTRUCTION


def detect_clips(transcript_text: str, stream_title: str, category: str = "Genel") -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    category_instruction = get_category_instruction(category)

    prompt = f"""Sen bir oyun yayını editörüsün. Aşağıda '{stream_title}' adlı Kick yayınının transkripti var.
Yayın kategorisi: {category}

{category_instruction}

Transkriptten viral olabilecek TÜM ilgi çekici anları bul — kaç tane olursa olsun.
Sonra onları viral potansiyeline göre en iyiden en kötüye sırala ve EN İYİ 10'unu döndür.

Eğer yayında hiç ilgi çekici an yoksa veya transkript çok boşsa BOŞ LİSTE döndür: []

Kurallar:
- Her klip MAXIMUM 60 saniye (tercihen 30-60 sn arası), minimum 20 saniye
- Klipler birbiriyle çakışmasın
- Score 1-10 arası: 7 ve üzeri gerçekten iyi, 5-6 orta, 5 altı atla
- Sadece score >= {MIN_SCORE} olan klipler döndür

Caption için: {category} kategorisine uygun, Türkçe, enerjik, emoji'li yaz.
- Açıklama max 400 karakter olsun (YouTube 5000 ama kısa daha iyi)
- En fazla 10 hashtag ekle, ilk 3'ü en önemli olsun (YouTube başlığın üzerinde gösterir)
- Başlık max 60 karakter (# dahil)

SADECE JSON döndür, başka hiçbir şey yazma. Format:
[
  {{
    "title": "YouTube Shorts başlığı (Türkçe, max 60 karakter) #Shorts",
    "start_seconds": 120,
    "end_seconds": 175,
    "description": "Klibin kısa açıklaması",
    "caption": "3-4 satır açıklama, emoji ve hashtagler (#feronline #kick #{category.lower().replace(' ', '')} #shorts)",
    "tags": ["feronline", "kick", "shorts"],
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

    if not clips:
        print(f"Claude bu yayında klip almaya değer an bulmadı. Pass geçiliyor.")
        return []

    # Sırala, min score filtrele, max 10 al
    clips = [c for c in clips if c.get("score", 0) >= MIN_SCORE]
    clips.sort(key=lambda x: x.get("score", 0), reverse=True)
    clips = clips[:10]

    # 60 sn limitini zorla
    for clip in clips:
        if clip["end_seconds"] - clip["start_seconds"] > 60:
            clip["end_seconds"] = clip["start_seconds"] + 60

    print(f"Claude {len(clips)} klip seçti (kategori: {category}):")
    for i, c in enumerate(clips):
        print(f"  {i+1}. [{c.get('score','?')}/10] {c['title'][:55]}")

    return clips
