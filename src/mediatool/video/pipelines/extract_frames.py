import subprocess
from pathlib import Path
from mediatool.utils.config import FFMPEG_BIN
from mediatool.utils.logging import get_logger
from mediatool.utils.paths import ensure_dir

log = get_logger(__name__)

def extract_frames(input_path: str | Path, fps=1, out_dir: str | Path | None = None):
    inp = Path(input_path)
    out_dir = ensure_dir(out_dir or (inp.parent / f"{inp.stem}_frames"))
    pattern = out_dir / "frame_%06d.png"
    cmd = [FFMPEG_BIN, "-y", "-i", str(inp), "-vf", f"fps={fps}", str(pattern)]
    log.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    return out_dir
