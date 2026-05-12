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
    # Öldürme / çatışma
    "öldür", "vurdu", "vurdum", "vuramadım", "vur", "headshot", "ace", "clutch",
    "öldü", "düştü", "düşürdüm", "aldım", "aldı", "bitti", "kaçtım", "kaçtı",
    # Konum / takım çağrısı
    "orada", "orda", "burda", "burada", "arkada", "sağda", "solda", "geliyor",
    "gel", "geldim", "gelin", "bekle", "bekleyin", "dur", "durun",
    # Maç terimleri
    "round", "kazandık", "kaybettik", "plant", "defuse", "ult", "flash", "smoke",
    "entry", "retake", "peek", "hold", "push", "rush", "eco", "pistol",
    # Ani tepki / bağırma (argo tamam, ağır küfür yok)
    "lan", "ulan", "ya", "abi", "oha", "of", "yok artık", "ne oluyor",
    "neden", "nasıl", "imkansız", "inanamıyorum",
    # Gülme
    "haha", "hehe", "ahaha", "güldüm", "güldük", "öldüm",
]

# Bu kelimeleri içeren klipler tamamen atlanır
PROFANITY_FILTER = [
    "ananı", "anana", "ananızı", "amına", "amınakoyim", "amına koyim",
    "orospu", "orospu çocuğu", "orospunun", "siktir", "hassiktir",
    "sik", "yarram", "götveren", "ibne",
]


def _has_profanity(segments: list[dict], start: float, end: float) -> bool:
    """Klip aralığındaki transkriptte ağır küfür var mı?"""
    for seg in segments:
        if seg["end"] < start or seg["start"] > end:
            continue
        text = seg["text"].lower()
        if any(p in text for p in PROFANITY_FILTER):
            return True
    return False


def _has_action_keyword(clip: dict, extra_keywords: list = None) -> bool:
    title = clip.get("title", "").lower()
    desc = clip.get("description", "").lower()
    caption = clip.get("caption", "").lower()
    text = title + " " + desc + " " + caption
    all_keywords = ACTION_KEYWORDS + (extra_keywords or [])
    return any(k in text for k in all_keywords)


def filter_by_spikes(clips: list[dict], spikes: list[dict], category: str, extra_keywords: list = None) -> list[dict]:
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
        has_keyword = _has_action_keyword(clip, extra_keywords)

        if has_spike or has_keyword:
            filtered.append(clip)
        else:
            print(f"  ⚡ Spike/keyword yok, elendi: {clip['title'][:50]}")

    print(f"Aksiyon filtresi: {len(clips)} → {len(filtered)} klip kaldı")
    return filtered


def detect_clips(transcript_text: str, stream_title: str, category: str = "Genel", audio_spikes_text: str = "", performance_context: str = "", spikes: list = None, segments: list = None) -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    category_instruction = get_category_instruction(category)

    prompt = f"""Sen Türk bir Kick yayıncısının (feronline) klip editörüsün.
Yayın: '{stream_title}' | Kategori: {category}

{category_instruction}

Transkriptten ilgi çekici anları bul, en iyi 10'unu döndür.
Eğer ses analizi verisi varsa oradaki yüksek enerjili anları da değerlendir — konuşma olmasa bile oyun sesi spike'ları ilgi çekici olabilir.
Eğer gerçekten iyi an yoksa clips için boş liste döndür: []

🎤 GÜLMEYİ ÖNCE AL — EN YÜKSEK ÖNCELİK:
Yayıncının yüksek sesle güldüğü, "haha", "ahahaha", "öldüm", "güldüm" dediği anlar
aksiyon anlarından bile daha değerlidir. Bu anları mutlaka listeye al, 9-10 puan ver.

ÖNEMLİ — Oyun kategorilerinde (Valorant, FPS, aksiyon oyunları):
Sadece konuşma olan, arka planda oyun aksiyonu/sesi olmayan anları ALMA.
O anın yakınında ses spike'ı yoksa max 4 puan ver.

🚫 KÜFÜR YASAĞI — KLİP ALMA:
"ananı", "amına", "orospu", "siktir" ve benzer ağır küfürlerin geçtiği anları ASLA klipleme.
Hafif argo (lan, ulan, ya, of) olan anlar kliplenebilir.

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
- MUTLAKA her caption şu şekilde bitsin (sıra değişmesin):
  kick.com/feronline

  #feronline #kick #shorts
- Bunlara ek kategoriye uygun 2-3 hashtag daha ekle, toplam max 8

--- KEYWORDS KURALI ---
Bu yayının kategori ve başlığına bakarak, bu yayında "ilgi çekici an" sayılabilecek
10-20 Türkçe anahtar kelime üret. Bunlar transkriptte geçince clipin değerini artırır.
Örnek: kategori "Just Chatting", başlık "şarkı söylüyoruz" → ["şarkı", "söyle", "yanlış", "gitar", "nota", "beste", "söyledim", "tutturamadım"]

--- DİĞER KURALLAR ---
- Her klip 20-60 saniye arası
- Klipler çakışmasın
- Score 1-10, sadece >= {MIN_SCORE} olanları döndür

SADECE JSON döndür (başka hiçbir şey yazma):
{{
  "keywords": ["kelime1", "kelime2", "..."],
  "clips": [
    {{
      "title": "başlık #Shorts",
      "start_seconds": 120,
      "end_seconds": 175,
      "description": "kısa açıklama",
      "caption": "2-3 satır samimi açıklama\\n\\nkick.com/feronline\\n\\n#feronline #kick #shorts",
      "tags": ["feronline", "kick", "shorts"],
      "score": 8
    }}
  ]
}}

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

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠️ JSON parse hatası: {e}")
        return []

    # Yeni format: {"keywords": [...], "clips": [...]}
    # Eski format fallback: direkt liste
    if isinstance(parsed, dict):
        clips = parsed.get("clips", [])
        dynamic_keywords = [k.lower() for k in parsed.get("keywords", [])]
        if dynamic_keywords:
            print(f"  🔑 Claude {len(dynamic_keywords)} keyword üretti: {', '.join(dynamic_keywords[:8])}...")
    else:
        clips = parsed
        dynamic_keywords = []

    if not clips:
        print(f"Claude bu yayında klip almaya değer an bulmadı. Pass geçiliyor.")
        return []

    # Sırala, min score filtrele, max 12 al
    clips = [c for c in clips if c.get("score", 0) >= MIN_SCORE]
    clips.sort(key=lambda x: x.get("score", 0), reverse=True)
    clips = clips[:12]

    # 60 sn limitini zorla
    for clip in clips:
        if clip["end_seconds"] - clip["start_seconds"] > 60:
            clip["end_seconds"] = clip["start_seconds"] + 60

    print(f"Claude {len(clips)} klip seçti (kategori: {category}):")
    for i, c in enumerate(clips):
        print(f"  {i+1}. [{c.get('score','?')}/10] {c['title'][:55]}")

    # Transkript küfür filtresi
    if segments:
        before = len(clips)
        clips = [c for c in clips if not _has_profanity(segments, c["start_seconds"], c["end_seconds"])]
        removed = before - len(clips)
        if removed:
            print(f"  🚫 {removed} küfürlü klip elendi")

    # Oyun kategorilerinde spike olmayan klipler elenir (statik + dinamik keywordler)
    if spikes:
        clips = filter_by_spikes(clips, spikes, category, extra_keywords=dynamic_keywords)

    return clips
