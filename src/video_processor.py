import subprocess
import os
import shutil


def cut_clip(video_path: str, start: float, end: float, output_path: str):
    duration = end - start
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(start), "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264", "-c:a", "aac", "-preset", "fast",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def convert_to_vertical_cam_game(input_path: str, output_path: str):
    """
    Kamera üstte (%40), oyun ekranı altta (%60).
    Kamera kaynağı: sağ alt 1/4 x 1/4 (16'ya bölündüğünde sağ alt hücre).
    Oyun: tam 16:9 frame. Her iki bölüm bulanık arka plan + zoom ile doldurulur.
    """
    cam_h = 768   # 1920 * 0.40
    game_h = 1152  # 1920 * 0.60

    filter_complex = (
        # Girişi 3'e böl: kamera için, oyun bg için, oyun fg için
        "[0:v]split=3[inp_cam][inp_game_bg][inp_game_fg];"

        # Kamera: sağ-alt 1/4 x 1/4, bg ve fg için 2'ye böl
        "[inp_cam]crop=iw/4:ih/4:iw*3/4:ih*3/4,split=2[cam_bg_src][cam_fg_src];"

        # Kamera arka plan (blur ile 1080x{cam_h} doldur)
        f"[cam_bg_src]scale=1080:{cam_h}:force_original_aspect_ratio=increase,"
        f"crop=1080:{cam_h},boxblur=20:5[cam_bg];"

        # Kamera ön plan (%5 zoom, 1080 genişlik)
        "[cam_fg_src]scale=1134:-2,crop=1080:ih:(iw-1080)/2:0[cam_fg];"

        # Kamera bölümü birleştir
        f"[cam_bg][cam_fg]overlay=(W-w)/2:(H-h)/2[cam_section];"

        # Oyun arka plan (%5 zoom + blur ile 1080x{game_h} doldur)
        f"[inp_game_bg]scale=1134:-2,crop=1080:ih:(iw-1080)/2:0,"
        f"scale=1080:{game_h}:force_original_aspect_ratio=increase,"
        f"crop=1080:{game_h},boxblur=20:5[game_bg];"

        # Oyun ön plan (%5 zoom, yüksekliğe sığdır)
        f"[inp_game_fg]scale=1134:-2,crop=1080:ih:(iw-1080)/2:0,"
        f"scale=-2:{game_h}[game_fg];"

        # Oyun bölümü birleştir
        f"[game_bg][game_fg]overlay=(W-w)/2:(H-h)/2[game_section];"

        # Kamera üstte, oyun altta
        "[cam_section][game_section]vstack=inputs=2"
    )

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"Dikey dönüşüm hatası: {result.stderr.decode()[-300:]}")
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

        print(f"[{i+1}/10] Dikey formata çevriliyor (kamera üst, oyun alt)...")
        convert_to_vertical_cam_game(raw_path, vertical_path)
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
