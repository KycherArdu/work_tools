import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)

FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")
