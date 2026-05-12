from src.youtube_uploader import get_youtube_client
from src.performance_tracker import fetch_and_update_stats, get_performance_context
from src.notifier import send_telegram
import json, os

def main():
    print("=== Haftalık Performans Takibi ===")
    youtube = get_youtube_client()
    fetch_and_update_stats(youtube)

    summary = {}
    if os.path.exists("performance.json"):
        with open("performance.json", encoding="utf-8") as f:
            summary = json.load(f)

    total = summary.get("total_videos", 0)
    views = summary.get("total_views", 0)

    msg = (
        f"📊 <b>Haftalık Rapor</b>\n"
        f"🎬 Toplam video: {total}\n"
        f"👁 Toplam görüntüleme: {views:,}\n"
    )

    top = summary.get("top_clips", [])
    if top:
        msg += "\n🏆 <b>En iyi klipler:</b>\n"
        for clip in top[:3]:
            msg += f"  • {clip['title'][:45]} → {clip['views']:,} görüntüleme\n"

    send_telegram(msg)
    print("Tamamlandı.")

if __name__ == "__main__":
    main()
