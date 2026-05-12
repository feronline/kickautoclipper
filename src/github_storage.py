import os
import re
import requests

_QUEUE_TAG = "clip-queue"


def _headers():
    token = os.environ.get("GITHUB_TOKEN", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _repo():
    return os.environ.get("GITHUB_REPOSITORY", "")


def _safe_name(name: str) -> str:
    name = re.sub(r"[^\w\-.]", "_", name)
    return name[:100]


def _get_or_create_release() -> dict:
    repo = _repo()
    h = _headers()
    r = requests.get(f"https://api.github.com/repos/{repo}/releases/tags/{_QUEUE_TAG}", headers=h, timeout=15)
    if r.ok:
        return r.json()
    r = requests.post(
        f"https://api.github.com/repos/{repo}/releases",
        headers=h,
        json={
            "tag_name": _QUEUE_TAG,
            "name": "Clip Queue",
            "body": "Otomatik klip kuyruğu — silmeyin",
            "draft": False,
            "prerelease": True,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def upload_clip(file_path: str, filename: str) -> str:
    """Klip dosyasını GitHub Release asset olarak yükler. Download URL döner."""
    release = _get_or_create_release()
    repo = _repo()
    safe = _safe_name(filename)

    # Aynı isimde asset varsa sil
    assets = requests.get(
        f"https://api.github.com/repos/{repo}/releases/{release['id']}/assets",
        headers=_headers(), timeout=15
    ).json()
    for asset in (assets if isinstance(assets, list) else []):
        if asset["name"] == safe:
            requests.delete(
                f"https://api.github.com/repos/{repo}/releases/assets/{asset['id']}",
                headers=_headers(), timeout=15
            )

    upload_headers = {**_headers(), "Content-Type": "video/mp4"}
    upload_url = f"https://uploads.github.com/repos/{repo}/releases/{release['id']}/assets?name={safe}"

    with open(file_path, "rb") as f:
        r = requests.post(upload_url, headers=upload_headers, data=f, timeout=600)
    r.raise_for_status()

    url = r.json()["browser_download_url"]
    print(f"  📦 GitHub'a yüklendi: {safe}")
    return url


def download_clip(download_url: str, dest_path: str):
    """GitHub Release asset'i indirir."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    h = {**_headers(), "Accept": "application/octet-stream"}
    r = requests.get(download_url, headers=h, stream=True, timeout=600)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    print(f"  ⬇️  GitHub'dan indirildi: {os.path.basename(dest_path)}")


def delete_clip(download_url: str):
    """YouTube'a yüklenen asset'i Release'dan temizler."""
    repo = _repo()
    h = _headers()
    try:
        release = _get_or_create_release()
        assets = requests.get(
            f"https://api.github.com/repos/{repo}/releases/{release['id']}/assets",
            headers=h, timeout=15
        ).json()
        for asset in (assets if isinstance(assets, list) else []):
            if asset["browser_download_url"] == download_url:
                requests.delete(
                    f"https://api.github.com/repos/{repo}/releases/assets/{asset['id']}",
                    headers=h, timeout=15
                )
                return
    except Exception as e:
        print(f"  ⚠️ GitHub asset silme hatası: {e}")
