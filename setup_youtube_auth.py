"""
Bu script'i BİR KERE lokalda çalıştır.
YouTube refresh token'ını alır, GitHub secret olarak eklersin.

Kullanım:
  python setup_youtube_auth.py
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

client_id = input("YouTube Client ID: ").strip()
client_secret = input("YouTube Client Secret: ").strip()

CLIENT_CONFIG = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
    }
}

flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)

print("\nTarayıcı açılıyor... Açılmazsa aşağıdaki URL'yi manuel aç:\n")

try:
    creds = flow.run_local_server(port=8080, open_browser=True)
except Exception:
    creds = flow.run_console()

print("\n=== GitHub Secrets olarak şunları ekle ===")
print(f"YOUTUBE_CLIENT_ID     = {client_id}")
print(f"YOUTUBE_CLIENT_SECRET = {client_secret}")
print(f"YOUTUBE_REFRESH_TOKEN = {creds.refresh_token}")
