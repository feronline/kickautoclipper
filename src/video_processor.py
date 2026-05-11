import subprocess
import os
import shutil


def cut_clip(video_path: str, start: float, end: float, output_path: str):
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def convert_to_vertical_with_zoom(input_path: str, output_path: str):
    """16:9 yatay videoyu 9:16 dikeye çevir: bulanık arka plan + %5 zoom ön plan."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex",
        (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=25:5[bg];"
            "[0:v]scale=1134:-2,crop=1080:ih:(iw-1080)/2:0,setsar=1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        ),
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print("Dikey dönüşüm hatası, orijinal devam ediyor.")
        shutil.copy(input_path, output_path)


def burn_ass_subtitles(input_path: str, ass_path: str, output_path: str):
    ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print("Altyazı yakma hatası, altyazısız devam ediliyor.")
        shutil.copy(input_path, output_path)


def filter_segments_for_clip(segments: list[dict], start: float, end: float) -> list[dict]:
    result = []
    for seg in segments:
        if seg["start"] >= start and seg["end"] <= end:
            offset_seg = {**seg, "start": seg["start"] - start, "end": seg["end"] - start}
            if "words" in seg:
                offset_seg["words"] = [
                    {**w, "start": w["start"] - start, "end": w["end"] - start}
                    for w in seg["words"]
                ]
            result.append(offset_seg)
    return result


def process_clips(video_path: str, clips: list[dict], segments: list[dict], output_dir: str) -> list[dict]:
    from src.transcriber import generate_tiktok_ass
    os.makedirs(output_dir, exist_ok=True)
    processed = []

    for i, clip in enumerate(clips):
        start = clip["start_seconds"]
        end = clip["end_seconds"]
        label = f"clip_{i+1}"

        raw_path = os.path.join(output_dir, f"{label}_raw.mp4")
        vertical_path = os.path.join(output_dir, f"{label}_vertical.mp4")
        ass_path = os.path.join(output_dir, f"{label}.ass")
        final_path = os.path.join(output_dir, f"{label}_final.mp4")

        print(f"[{i+1}/10] Kesiliyor: {start:.0f}s - {end:.0f}s")
        cut_clip(video_path, start, end, raw_path)

        print(f"[{i+1}/10] Dikey formata çevriliyor + zoom...")
        convert_to_vertical_with_zoom(raw_path, vertical_path)
        os.remove(raw_path)

        clip_segments = filter_segments_for_clip(segments, start, end)
        if clip_segments:
            print(f"[{i+1}/10] TikTok altyazı ekleniyor...")
            generate_tiktok_ass(clip_segments, ass_path)
            burn_ass_subtitles(vertical_path, ass_path, final_path)
        else:
            shutil.copy(vertical_path, final_path)

        os.remove(vertical_path)

        processed.append({**clip, "file_path": final_path})
        print(f"[{i+1}/10] Hazır: {final_path}")

    return processed
