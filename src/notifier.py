import os
import requests


def send_telegram(message: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram bilgileri eksik, bildirim atlandı.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=10)


def notify_clip_uploaded(title: str, video_id: str, clip_num: int, total: int):
    message = (
        f"✅ <b>Klip {clip_num}/{total} yüklendi</b>\n"
        f"📌 {title}\n"
        f"▶️ https://youtube.com/shorts/{video_id}"
    )
    send_telegram(message)


def notify_error(error: str):
    message = f"❌ <b>Hata oluştu</b>\n<code>{error[:300]}</code>"
    send_telegram(message)


def notify_no_clips():
    send_telegram("ℹ️ Yeni yayın işlendi ama ilgi çekici klip bulunamadı.")
