import argparse
import os
import sys
import subprocess
import shutil
import logging
from pathlib import Path
import cv2
import numpy as np
import easyocr
from tqdm import tqdm

def check_ffmpeg():
    """Verify that FFmpeg is installed and accessible."""
    if shutil.which("ffmpeg") is None:
        print("Error: FFmpeg is not installed or not in the system PATH. Please install FFmpeg to continue.")
        sys.exit(1)

def detect_watermark(frame, keyword):
    """
    Scans the provided frame for the given keyword (case-insensitive) using EasyOCR.
    Returns the padded bounding box [x, y, w, h] if found, otherwise None.
    padding = 15 pixels
    """
    reader = easyocr.Reader(['en'], gpu=False) # Or allow GPU if available
    results = reader.readtext(frame)
    keyword_lower = keyword.lower()
    
    for bbox, text, conf in results:
        if keyword_lower in text.lower():
            # bbox is a list of 4 points: [top-left, top-right, bottom-right, bottom-left]
            x_coords = [p[0] for p in bbox]
            y_coords = [p[1] for p in bbox]
            x_min = int(min(x_coords))
            x_max = int(max(x_coords))
            y_min = int(min(y_coords))
            y_max = int(max(y_coords))
            
            # Apply base 15px padding, plus extra padding on the left to catch the logo
            pad = 15
            text_h = y_max - y_min
            left_pad = pad + int(text_h * 1.5)  # Estimate logo width based on text height
            
            frame_h, frame_w = frame.shape[:2]
            final_x = max(0, x_min - left_pad)
            final_y = max(0, y_min - pad)
            final_w = min(frame_w - final_x, (x_max - x_min) + left_pad + pad)
            final_h = min(frame_h - final_y, text_h + 2 * pad)
            
            return [final_x, final_y, final_w, final_h]
            
    return None

def generate_mask(frame_shape, bbox, padding=15):
    """
    Generates a solid black mask of the same shape as the video frame, 
    with a white rectangle covering the bounding box.
    Returns the generated mask.
    """
    mask = np.zeros(frame_shape[:2], dtype=np.uint8)
    x, y, w, h = bbox
    cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
    return mask

def remove_watermark_ffmpeg(input_path, bbox, output_path):
    """
    Uses FFmpeg to apply a 'delogo' filter. The delogo filter suppresses
    a watermark by performing simple interpolation from surrounding pixels,
    creating a content-aware fill that looks much more natural than boxblur.
    """
    x, y, w, h = bbox
    # Ensure w and h are at least 1, and don't go out of bounds
    filter_chain = f"delogo=x={x}:y={y}:w={w}:h={h}:show=0"
    
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", filter_chain,
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise Exception(f"FFmpeg failed with error: {result.stderr}")

def process_video(input_path, keyword, output_path, temp_dir):
    """
    Processes a single video: extracts frames sequentially until the watermark is found,
    detects the watermark, generates a mask, and completely removes it using ffmpeg.
    """
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise ValueError("Could not open the video file.")
    
    bbox = None
    frame_count = 0
    max_frames_to_check = 3000  # Check up to ~100 seconds at 30fps
    
    print(f"Scanning {input_path.name} for watermark '{keyword}'...")
    while frame_count < max_frames_to_check:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Optional: scan every Nth frame to speed things up
        if frame_count % 30 == 0:
            bbox = detect_watermark(frame, keyword)
            if bbox:
                print(f"  -> Watermark found at frame {frame_count}")
                break
                
        frame_count += 1
        
    cap.release()
    
    if not bbox:
        return False, "Watermark keyword not detected within the scanned frames."
        
    mask = generate_mask(frame.shape, bbox)
    mask_path = temp_dir / "mask.png"
    cv2.imwrite(str(mask_path), mask)
    
    remove_watermark_ffmpeg(input_path, bbox, output_path)
    return True, "Successfully processed."

def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="Watermark Remover CLI")
    parser.add_argument("--input", required=True, help="Input video file or folder containing videos")
    parser.add_argument("--keyword", required=True, help="Watermark text to search for")
    parser.add_argument("--output", required=True, help="Destination folder for cleaned videos")
    
    args = parser.parse_args()
    check_ffmpeg()
    
    input_path = Path(args.input)
    output_dir = Path(args.output)
    keyword = args.keyword
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = output_dir / "run.log"
    logging.basicConfig(filename=log_file, level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    
    temp_dir = output_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    videos = []
    if input_path.is_file():
        if input_path.suffix.lower() in [".mp4", ".mov", ".mkv"]:
            videos.append(input_path)
        else:
            print("Unsupported file format. Please provide .mp4, .mov, or .mkv files.")
            sys.exit(1)
    elif input_path.is_dir():
        for ext in [".mp4", ".mov", ".mkv"]:
            videos.extend(input_path.rglob(f"*{ext}"))
            videos.extend(input_path.rglob(f"*{ext.upper()}"))
    else:
        print(f"Error: {input_path} does not exist.")
        sys.exit(1)
        
    # Remove duplicates because rglob could match both depending on filesystem
    videos = list(set(videos))
    
    if not videos:
        print("No videos found to process.")
        sys.exit(0)
    
    success_count = 0
    skip_count = 0
    fail_count = 0
        
    print(f"Found {len(videos)} video(s) to process.")
    for video in tqdm(videos, desc="Processing videos"):
        out_video_path = output_dir / video.name
        
        try:
            success, message = process_video(video, keyword, out_video_path, temp_dir)
            if success:
                logging.info(f"SUCCESS: {video.name} - {message}")
                success_count += 1
            else:
                logging.warning(f"SKIP: {video.name} - {message}")
                skip_count += 1
        except Exception as e:
            logging.error(f"FAILURE: {video.name} - {str(e)}")
            fail_count += 1
            
    print(f"\nProcessing complete.")
    print(f"Success: {success_count}, Skipped: {skip_count}, Failed: {fail_count}")
    print(f"Logs saved to {log_file}")

if __name__ == "__main__":
    main()
