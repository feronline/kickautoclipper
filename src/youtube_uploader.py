import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


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


def upload_clip(clip: dict) -> str:
    youtube = get_youtube_client()

    body = {
        "snippet": {
            "title": clip["title"],
            "description": clip.get("description", "") + "\n\n#feronline #kick #gaming",
            "tags": clip.get("tags", []) + ["feronline", "kick", "gaming", "clips"],
            "categoryId": "20",
        },
        "status": {
            "privacyStatus": "public",
        }
    }

    media = MediaFileUpload(
        clip["file_path"],
        mimetype="video/mp4",
        resumable=True
    )

    print(f"YouTube'a yükleniyor: {clip['title']}")
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Yükleme: %{int(status.progress() * 100)}")

    video_id = response["id"]
    print(f"Yüklendi: https://youtube.com/watch?v={video_id}")
    return video_id
