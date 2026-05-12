import os
import json
import tempfile
from datetime import datetime


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


def upload_to_tiktok(clip: dict, schedule_at: datetime = None) -> str:
    """TikTok'a klip yükler. schedule_at verilirse zamanlanmış yayın yapar."""
    if not os.environ.get("TIKTOK_COOKIES"):
        return ""

    cookies_path = None
    try:
        from tiktok_uploader.upload import upload_video

        cookies_path = _get_cookies_file()

        title = clip.get("caption") or clip.get("title", "")
        title = title[:150]

        if schedule_at:
            print(f"  📱 TikTok zamanlanıyor ({schedule_at.strftime('%d/%m %H:%M')} UTC): {clip['title'][:40]}")
        else:
            print(f"  📱 TikTok'a yükleniyor: {clip['title'][:50]}")

        kwargs = dict(
            filename=clip["file_path"],
            description=title,
            cookies=cookies_path,
            headless=True,
        )
        if schedule_at:
            kwargs["schedule"] = schedule_at

        import threading
        result_holder = [None, None]  # [result, error]

        def _run():
            try:
                result_holder[0] = upload_video(**kwargs)
            except Exception as e:
                result_holder[1] = e

        t = threading.Thread(target=_run)
        t.start()
        t.join()

        if result_holder[1]:
            raise result_holder[1]

        result = result_holder[0]

        # tiktok-uploader bazen URL, bazen video ID döner
        tiktok_url = ""
        if isinstance(result, str) and result.startswith("http"):
            tiktok_url = result
        elif isinstance(result, str) and result:
            tiktok_url = f"https://www.tiktok.com/@feronline/video/{result}"

        print(f"  ✅ TikTok yüklendi{': ' + tiktok_url if tiktok_url else ''}")
        return tiktok_url or "uploaded"

    except Exception as e:
        print(f"  ⚠️ TikTok yükleme hatası: {e}")
        return ""
    finally:
        if cookies_path:
            try:
                os.unlink(cookies_path)
            except Exception:
                pass
