import anthropic
import json
import os

MIN_SCORE = 3  # Bu puanın altındaki klipler atlanır


CATEGORY_INSTRUCTIONS = {
    "valorant": (
        "Bu bir Valorant yayını.\n"
        "KESİNLİKLE SADECE şu tür anları al: ace, clutch, multi-kill, güzel atış, "
        "düşmana kapan, round kazanma, sinirlenme veya kutlama — BUNLARIN HEPSINDE "
        "arka planda silah sesi / yetenek sesi / aksiyon OLMAK ZORUNDA.\n"
        "YASAK: sadece konuşma olan, oyun aksiyonu olmayan anlar. "
        "Yayıncı konuşurken arka planda sessizlik varsa o anı ALMA. "
        "Ses analizi verisindeki spike'lar bu kategori için çok önemli — "
        "spike olmayan bir ana 7+ puan verme.\n"
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


def detect_clips(transcript_text: str, stream_title: str, category: str = "Genel", audio_spikes_text: str = "", performance_context: str = "") -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    category_instruction = get_category_instruction(category)

    prompt = f"""Sen Türk bir Kick yayıncısının (feronline) klip editörüsün.
Yayın: '{stream_title}' | Kategori: {category}

{category_instruction}

Transkriptten ilgi çekici anları bul, en iyi 10'unu döndür.
Eğer ses analizi verisi varsa oradaki yüksek enerjili anları da değerlendir — konuşma olmasa bile oyun sesi spike'ları ilgi çekici olabilir.
Eğer gerçekten iyi an yoksa boş liste döndür: []

ÖNEMLİ — Oyun kategorilerinde (Valorant, FPS, aksiyon oyunları):
Sadece konuşma olan, arka planda oyun aksiyonu/sesi olmayan anları ALMA.
O anın yakınında ses spike'ı yoksa max 4 puan ver.

--- BAŞLIK KURALLARI (ÇOK ÖNEMLİ) ---
- Başlık SAMİMİ ve DOĞAL olsun, sanki bir arkadaşın klip attığında yazacağı gibi
- ASLA şu klişe ifadeleri kullanma: "çıldırdı", "patladı", "aniden", "inanılmaz", "kaçırma", "sadece burada", "böyle sahneler"
- Transkriptte geçen gerçek bir sözü veya anı yansıt
- Sade, kısa, merak uyandıran yaz — max 55 karakter (#Shorts hariç)
- Türkçe internet dilinde, doğal konuşma tarzında

Kötü başlık örnekleri (YAPMA):
❌ "Yayıncı Aniden Patladı 💢"
❌ "Bu Anı Kaçırma! 😱"
❌ "Çıldırdı! 😂🔥"

İyi başlık örnekleri (BÖYLE YAP):
✅ "neden böyle bir şey yaparsın ki"
✅ "o an sessizlik"
✅ "2 saatlik uğraş 10 saniyede gitti"

--- CAPTION KURALLARI ---
- 2-3 satır, samimi ve kısa
- Abartılı "viral olacak!" tarzı yazma
- Transkriptten emin olmadığın kelimeleri caption'a yazma
- Max 300 karakter
- Sonuna max 8 hashtag: #feronline #kick #shorts ve kategoriye uygun 2-3 tane daha

--- DİĞER KURALLAR ---
- Her klip 20-60 saniye arası
- Klipler çakışmasın
- Score 1-10, sadece >= {MIN_SCORE} olanları döndür

SADECE JSON döndür:
[
  {{
    "title": "başlık #Shorts",
    "start_seconds": 120,
    "end_seconds": 175,
    "description": "kısa açıklama",
    "caption": "2-3 satır samimi açıklama\\n\\n#feronline #kick #shorts",
    "tags": ["feronline", "kick", "shorts"],
    "score": 8
  }}
]

Transkript:
{transcript_text[:12000]}

{audio_spikes_text}

{performance_context}
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
    clips = clips[:12]  # En iyi 12, yükleme 2 güne yayılır

    # 60 sn limitini zorla
    for clip in clips:
        if clip["end_seconds"] - clip["start_seconds"] > 60:
            clip["end_seconds"] = clip["start_seconds"] + 60

    print(f"Claude {len(clips)} klip seçti (kategori: {category}):")
    for i, c in enumerate(clips):
        print(f"  {i+1}. [{c.get('score','?')}/10] {c['title'][:55]}")

    return clips
