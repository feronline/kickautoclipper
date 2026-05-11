import os
import time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# YouTube günlük kotası 10.000 birim, her yükleme ~1600 birim → max 6/gün
# 10 video için quota artırımı gerekebilir (Google Cloud Console'dan istenebilir)
UPLOAD_DELAY_SECONDS = 60


def get_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_clip(clip: dict, youtube=None) -> str:
    if youtube is None:
        youtube = get_youtube_client()

    title = clip["title"]
    if "#Shorts" not in title and "#shorts" not in title:
        title = title[:90] + " #Shorts"
    title = title[:100]  # YouTube max 100 karakter

    body = {
        "snippet": {
            "title": title,
            "description": clip.get("caption") or (
                clip.get("description", "") +
                "\n\n#Shorts #feronline #kick #gaming #clips"
            ),
            "tags": clip.get("tags", []) + ["feronline", "kick", "shorts", "gaming", "clips"],
            "categoryId": "20",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    media = MediaFileUpload(clip["file_path"], mimetype="video/mp4", resumable=True)

    print(f"YouTube Shorts'a yükleniyor: {title}")
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Yükleme: %{int(status.progress() * 100)}")

    video_id = response["id"]
    print(f"  Yüklendi: https://youtube.com/shorts/{video_id}")
    return video_id


def upload_all_clips(clips: list[dict]) -> list[str]:
    youtube = get_youtube_client()
    video_ids = []

    for i, clip in enumerate(clips):
        video_id = upload_clip(clip, youtube)
        video_ids.append(video_id)

        if i < len(clips) - 1:
            print(f"  Sonraki yükleme için {UPLOAD_DELAY_SECONDS} saniye bekleniyor...")
            time.sleep(UPLOAD_DELAY_SECONDS)

    return video_ids
