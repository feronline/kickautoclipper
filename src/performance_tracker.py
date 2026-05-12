import json
import os
from datetime import datetime, timezone

UPLOADS_FILE = "uploads.json"
PERFORMANCE_FILE = "performance.json"


def log_upload(video_id: str, title: str, category: str, clip_source: str = "transcript"):
    """Yüklenen klibi uploads.json'a kaydet."""
    uploads = _read_json(UPLOADS_FILE, [])
    uploads.append({
        "video_id": video_id,
        "title": title,
        "category": category,
        "source": clip_source,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "views": 0,
        "likes": 0,
    })
    _write_json(UPLOADS_FILE, uploads)


def fetch_and_update_stats(youtube):
    """YouTube'dan tüm kliplerin istatistiklerini çek, güncelle."""
    uploads = _read_json(UPLOADS_FILE, [])
    if not uploads:
        print("Takip edilecek video yok.")
        return

    video_ids = [u["video_id"] for u in uploads]

    # YouTube API max 50 ID per request
    all_stats = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        response = youtube.videos().list(
            part="statistics",
            id=",".join(batch)
        ).execute()
        for item in response.get("items", []):
            vid = item["id"]
            stats = item.get("statistics", {})
            all_stats[vid] = {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
            }

    # Güncelle
    for upload in uploads:
        vid = upload["video_id"]
        if vid in all_stats:
            upload["views"] = all_stats[vid]["views"]
            upload["likes"] = all_stats[vid]["likes"]

    _write_json(UPLOADS_FILE, uploads)

    # Kategori bazlı özet oluştur
    _build_performance_summary(uploads)
    print(f"{len(uploads)} video istatistiği güncellendi.")


def _build_performance_summary(uploads: list):
    """Kategori ve içerik tipine göre performans özeti oluştur."""
    if not uploads:
        return

    from collections import defaultdict
    by_category = defaultdict(list)
    by_source = defaultdict(list)

    for u in uploads:
        if u["views"] > 0:
            by_category[u.get("category", "Genel")].append(u["views"])
            by_source[u.get("source", "transcript")].append(u["views"])

    summary = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_videos": len(uploads),
        "total_views": sum(u["views"] for u in uploads),
        "by_category": {
            cat: {
                "avg_views": int(sum(views) / len(views)),
                "count": len(views),
            }
            for cat, views in by_category.items()
        },
        "by_source": {
            src: {
                "avg_views": int(sum(views) / len(views)),
                "count": len(views),
            }
            for src, views in by_source.items()
        },
        "top_clips": sorted(uploads, key=lambda x: x["views"], reverse=True)[:5],
    }

    _write_json(PERFORMANCE_FILE, summary)


def get_performance_context() -> str:
    """Claude'a geçirilecek performans özetini oluştur."""
    summary = _read_json(PERFORMANCE_FILE, {})
    if not summary or summary.get("total_videos", 0) == 0:
        return ""

    lines = [f"\n[Geçmiş klip performansı — {summary['total_videos']} video, toplam {summary['total_views']:,} görüntüleme]"]

    by_cat = summary.get("by_category", {})
    if by_cat:
        lines.append("Kategori bazlı ortalama görüntüleme:")
        for cat, data in sorted(by_cat.items(), key=lambda x: x[1]["avg_views"], reverse=True):
            lines.append(f"  - {cat}: {data['avg_views']:,} görüntüleme ({data['count']} video)")

    by_src = summary.get("by_source", {})
    if by_src:
        lines.append("Klip tipi bazlı ortalama görüntüleme:")
        for src, data in by_src.items():
            src_name = "Konuşma bazlı" if src == "transcript" else "Ses spike bazlı"
            lines.append(f"  - {src_name}: {data['avg_views']:,} görüntüleme")

    top = summary.get("top_clips", [])
    if top:
        lines.append("En iyi klipler:")
        for clip in top[:3]:
            lines.append(f"  - '{clip['title'][:50]}' → {clip['views']:,} görüntüleme")

    return "\n".join(lines)


def _read_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return default


def _write_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
