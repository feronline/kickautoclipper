import os
import json
import tempfile


def _get_cookies_file() -> str:
    """TIKTOK_COOKIES secret'ından geçici cookies.txt dosyası oluşturur."""
    cookies_json = os.environ.get("TIKTOK_COOKIES", "")
    if not cookies_json:
        raise EnvironmentError("TIKTOK_COOKIES secret eksik")

    # JSON array formatında cookies bekleniyor (EditThisCookie/Get cookies.txt LOCALLY)
    cookies = json.loads(cookies_json)

    # Netscape cookie format (tiktok-uploader'ın beklediği format)
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c.get("domain", ".tiktok.com")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        expiry = str(int(c.get("expirationDate", 0)))
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tmp.write("\n".join(lines))
    tmp.close()
    return tmp.name


def upload_to_tiktok(clip: dict) -> bool:
    """TikTok'a klip yükler. Başarılıysa True döner."""
    if not os.environ.get("TIKTOK_COOKIES"):
        return False

    try:
        from tiktok_uploader.upload import upload_video

        cookies_path = _get_cookies_file()

        title = clip.get("caption") or clip.get("title", "")
        # TikTok başlık max 2200 karakter ama pratikte 150 ideal
        title = title[:150]

        print(f"  TikTok'a yükleniyor: {clip['title'][:50]}")
        upload_video(
            filename=clip["file_path"],
            description=title,
            cookies=cookies_path,
            headless=True,
        )
        print(f"  ✅ TikTok yüklendi")
        return True

    except Exception as e:
        print(f"  ⚠️ TikTok yükleme hatası: {e}")
        return False
    finally:
        try:
            os.unlink(cookies_path)
        except Exception:
            pass
