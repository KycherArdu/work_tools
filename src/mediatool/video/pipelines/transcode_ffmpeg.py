import subprocess
from pathlib import Path
from mediatool.utils.config import FFMPEG_BIN
from mediatool.utils.logging import get_logger

log = get_logger(__name__)

def transcode_h264(input_path: str | Path, out_dir: str | Path | None = None, crf=20, preset="medium"):
    inp = Path(input_path)
    out_dir = Path(out_dir) if out_dir else inp.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (inp.stem + "_h264.mp4")

    cmd = [
        FFMPEG_BIN, "-y", "-i", str(inp),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-c:a", "aac", "-b:a", "192k",
        str(out)
    ]
    log.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    return out
