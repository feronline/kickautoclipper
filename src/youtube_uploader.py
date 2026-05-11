import os
import time
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Her video bu kadar arayla yayına girer (saat)
PUBLISH_INTERVAL_HOURS = 3


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


def upload_clip(clip: dict, youtube=None, publish_at: datetime = None) -> str:
    if youtube is None:
        youtube = get_youtube_client()

    title = clip["title"]
    if "#Shorts" not in title and "#shorts" not in title:
        title = title[:90] + " #Shorts"
    title = title[:100]

    if publish_at:
        privacy = "private"
        publish_at_str = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"  Zamanlanmış yayın: {publish_at.strftime('%d/%m %H:%M')} UTC")
    else:
        privacy = "public"
        publish_at_str = None

    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at_str:
        status["publishAt"] = publish_at_str

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
        "status": status,
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


def upload_all_clips(clips: list[dict], on_uploaded=None) -> list[str]:
    youtube = get_youtube_client()
    video_ids = []
    total = len(clips)

    now = datetime.now(timezone.utc)
    publish_time = now + timedelta(hours=1)

    for i, clip in enumerate(clips):
        video_id = upload_clip(clip, youtube, publish_at=publish_time)
        video_ids.append(video_id)

        if on_uploaded:
            on_uploaded(clip["title"], video_id, i + 1, total)

        publish_time += timedelta(hours=PUBLISH_INTERVAL_HOURS)

    print(f"\nToplam {len(video_ids)} video yüklendi.")
    print(f"İlk video: 1 saat sonra | Son video: ~{1 + len(video_ids)*3} saat sonra")
    return video_ids
