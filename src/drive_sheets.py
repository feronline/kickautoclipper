import os
import json
from datetime import datetime, timezone
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

SHEET_HEADERS = [
    "Tarih", "Yayın", "Kategori", "Klip Adı", "Süre (sn)",
    "Puan", "Yükleme Durumu", "Yayın Zamanı",
    "YouTube Linki", "TikTok Linki", "Drive Linki", "Açıklama"
]


def _get_creds():
    key_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not key_json:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON secret eksik")
    info = json.loads(key_json)
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def ensure_sheet_headers(sheet_id: str):
    creds = _get_creds()
    svc = build("sheets", "v4", credentials=creds)
    sheet = svc.spreadsheets()

    result = sheet.values().get(spreadsheetId=sheet_id, range="A1:K1").execute()
    if not result.get("values"):
        sheet.values().update(
            spreadsheetId=sheet_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": [SHEET_HEADERS]}
        ).execute()
        print("📊 Google Sheets başlık satırı oluşturuldu.")


def upload_to_drive(file_path: str, filename: str) -> tuple[str, str]:
    """Returns (webViewLink, file_id)"""
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    creds = _get_creds()
    svc = build("drive", "v3", credentials=creds)

    metadata = {"name": filename}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
    file = svc.files().create(
        body=metadata,
        media_body=media,
        fields="id, webViewLink"
    ).execute()

    link = file.get("webViewLink", "")
    file_id = file.get("id", "")
    print(f"  ☁️  Drive'a yüklendi: {filename}")
    return link, file_id


def download_from_drive(file_id: str, dest_path: str):
    creds = _get_creds()
    svc = build("drive", "v3", credentials=creds)
    request = svc.files().get_media(fileId=file_id)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with io.FileIO(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    print(f"  ⬇️  Drive'dan indirildi: {os.path.basename(dest_path)}")


def log_to_sheets(sheet_id: str, row: dict):
    creds = _get_creds()
    svc = build("sheets", "v4", credentials=creds)

    values = [[
        row.get("date", ""),
        row.get("stream_title", ""),
        row.get("category", ""),
        row.get("title", ""),
        row.get("duration", ""),
        row.get("score", ""),
        row.get("status", ""),
        row.get("publish_at", ""),
        row.get("youtube_link", ""),
        row.get("tiktok_link", ""),
        row.get("drive_link", ""),
        row.get("description", ""),
    ]]

    svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": values}
    ).execute()
