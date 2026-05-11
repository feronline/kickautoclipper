import requests
import os
import json

KICK_CHANNEL = "feronline"
LAST_VOD_FILE = "last_vod_id.txt"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def get_latest_vod():
    url = f"https://kick.com/api/v2/channels/{KICK_CHANNEL}/videos"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        videos = data.get("data", [])
        if not videos:
            print("Kick'te hiç yayın tekrarı bulunamadı.")
            return None
        return videos[0]
    except Exception as e:
        print(f"Kick API hatası: {e}")
        return None


def get_last_processed_id():
    if not os.path.exists(LAST_VOD_FILE):
        return None
    with open(LAST_VOD_FILE, "r") as f:
        content = f.read().strip()
        return content if content else None


def save_last_processed_id(vod_id):
    with open(LAST_VOD_FILE, "w") as f:
        f.write(str(vod_id))


def check_new_vod():
    vod = get_latest_vod()
    if not vod:
        return None

    vod_id = str(vod.get("id") or vod.get("uuid"))
    last_id = get_last_processed_id()

    if vod_id == last_id:
        print(f"Yeni yayın yok. Son işlenen: {vod_id}")
        return None

    print(f"Yeni yayın bulundu: {vod.get('title')} (ID: {vod_id})")
    return vod
