import subprocess
import os


def cut_clip(video_path: str, start: float, end: float, output_path: str):
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def filter_segments_for_clip(segments: list[dict], start: float, end: float) -> list[dict]:
    return [
        {**seg, "start": seg["start"] - start, "end": seg["end"] - start}
        for seg in segments
        if seg["start"] >= start and seg["end"] <= end
    ]


def burn_subtitles(video_path: str, srt_path: str, output_path: str):
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"subtitles='{srt_escaped}':force_style='FontSize=18,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Bold=1'",
        "-c:a", "copy",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print("Altyazı yakma başarısız, altyazısız devam ediliyor.")
        import shutil
        shutil.copy(video_path, output_path)


def process_clips(video_path: str, clips: list[dict], segments: list[dict], output_dir: str) -> list[dict]:
    from src.transcriber import segments_to_srt
    os.makedirs(output_dir, exist_ok=True)
    processed = []

    for i, clip in enumerate(clips):
        start = clip["start_seconds"]
        end = clip["end_seconds"]
        safe_title = f"clip_{i+1}"

        raw_path = os.path.join(output_dir, f"{safe_title}_raw.mp4")
        srt_path = os.path.join(output_dir, f"{safe_title}.srt")
        final_path = os.path.join(output_dir, f"{safe_title}_final.mp4")

        print(f"Klip {i+1} kesiliyor: {start}s - {end}s")
        cut_clip(video_path, start, end, raw_path)

        clip_segments = filter_segments_for_clip(segments, start, end)
        if clip_segments:
            segments_to_srt(clip_segments, srt_path)
            print(f"Altyazı yakılıyor: klip {i+1}")
            burn_subtitles(raw_path, srt_path, final_path)
        else:
            import shutil
            shutil.copy(raw_path, final_path)

        os.remove(raw_path)

        processed.append({
            **clip,
            "file_path": final_path
        })

    return processed
