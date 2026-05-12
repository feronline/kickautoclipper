import anthropic
import json
import os

MIN_SCORE = 3  # Bu puanın altındaki klipler atlanır

# Bu kategorilerde spike zorunlu — saf konuşma klipler elenir
GAME_CATEGORIES = ["valorant", "fps", "cs2", "csgo", "fortnite", "apex", "overwatch",
                   "minecraft", "pubg", "warzone", "league", "dota", "gaming"]


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


def is_game_category(category: str) -> bool:
    key = category.lower()
    return any(g in key for g in GAME_CATEGORIES)


ACTION_KEYWORDS = [
    "öldür", "vurdu", "vurdum", "headshot", "ace", "clutch", "kaçtım", "kaçtı",
    "aldım", "aldı", "bitti", "öldü", "düştü", "düşürdüm", "round", "kazandık",
    "kaybettik", "plant", "defuse", "ult", "flash", "smoke", "entry", "retake",
    "peek", "hold", "push", "rush", "eco", "full buy", "pistol",
]


def _has_action_keyword(clip: dict) -> bool:
    title = clip.get("title", "").lower()
    desc = clip.get("description", "").lower()
    caption = clip.get("caption", "").lower()
    text = title + " " + desc + " " + caption
    return any(k in text for k in ACTION_KEYWORDS)


def filter_by_spikes(clips: list[dict], spikes: list[dict], category: str) -> list[dict]:
    """Oyun kategorilerinde: spike'ı VEYA aksiyon kelimesi olmayan klipler elenir."""
    if not is_game_category(category):
        return clips

    filtered = []
    for clip in clips:
        cs = clip["start_seconds"]
        ce = clip["end_seconds"]
        has_spike = spikes and any(
            not (s["end_seconds"] < cs or s["start_seconds"] > ce)
            for s in spikes
        )
        has_keyword = _has_action_keyword(clip)

        if has_spike or has_keyword:
            filtered.append(clip)
        else:
            print(f"  ⚡ Spike/keyword yok, elendi: {clip['title'][:50]}")

    print(f"Aksiyon filtresi: {len(clips)} → {len(filtered)} klip kaldı")
    return filtered


def detect_clips(transcript_text: str, stream_title: str, category: str = "Genel", audio_spikes_text: str = "", performance_context: str = "", spikes: list = None) -> list[dict]:
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
- Başlık MUTLAKA transkriptten gerçek bir söz veya tepki olsun
- Transkriptte alıntılanabilecek bir şey yoksa o klip için başlık UYDURMA, o klibe düşük puan ver
- SAMİMİ ve DOĞAL: sanki o an telefona ekran kaydı atarken yazacağın şey
- ASLA şunları yazma: "çıldırdı", "patladı", "aniden", "inanılmaz", "kaçırma", "yüksek enerji", "gergin an", "maç içi", "heyecanlı an", "dikkat çekici"
- max 55 karakter (#Shorts hariç)
- Türkçe internet dilinde, küçük harf, doğal

Kötü başlık örnekleri (YAPMA):
❌ "Yayıncı Aniden Patladı 💢"
❌ "yüksek enerji an - maç içi"
❌ "sessiz ama gergin"
❌ "dikkat çekici bir an"
❌ "Çıldırdı! 😂🔥"

İyi başlık örnekleri (BÖYLE YAP):
✅ "ya bu nasıl headshot ya"
✅ "3e karşı 1 kaldım bi de kazandım"
✅ "reyna niye ult atmıyor anlamıyorum"
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

    # Oyun kategorilerinde spike olmayan klipler elenir
    if spikes:
        clips = filter_by_spikes(clips, spikes, category)

    return clips
