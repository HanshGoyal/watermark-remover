# Watermark Remover

A Python CLI tool that automatically detects and removes a static text watermark from videos.

## Requirements

- Python 3.8+
- [FFmpeg](https://ffmpeg.org/download.html) must be installed and available in your system's PATH.

## Installation

1. Clone or download this repository.
2. Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the tool using the following arguments:
- `--input`: A single video file or a folder containing multiple videos (.mp4, .mov, .mkv).
- `--keyword`: The watermark text to search for (case-insensitive).
- `--output`: Your desired destination folder for cleaned videos.

### Example Single File
```bash
python watermark_remover.py --input ./video.mp4 --keyword "Pictory" --output ./clean
```

### Example Folder (Batch Processing)
```bash
python watermark_remover.py --input ./videos --keyword "Logo Name" --output ./clean
```

## Output Logs
When processing multiple files, the tool will create a `run.log` inside the `--output` folder. This log will list which videos were successfully cleaned, skipped, or failed.
