# src/mediatool/image/pipelines/blur_script_interactive.py
from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional, Iterable
from PIL import Image, ImageFilter

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}

def blur_folder(
    input_folder: str | Path,
    radius: int = 78,
    output_folder: Optional[str | Path] = None,
    progress: Optional[Callable[[int, int, str | None], None]] = None,
    files: Optional[Iterable[str | Path]] = None,   # <-- NEW
):
    in_path = Path(input_folder).expanduser().resolve()
    if not in_path.exists():
        raise ValueError(f"Path not found: {in_path}")

    out_path = Path(output_folder).expanduser().resolve() if output_folder else in_path if in_path.is_dir() else in_path.parent
    if in_path.is_dir() and output_folder is None:
        out_path = in_path.parent / f"{in_path.name}_blurred"
    out_path.mkdir(parents=True, exist_ok=True)

    if files:
        file_list = [Path(p) for p in files]
    else:
        base = in_path if in_path.is_dir() else in_path.parent
        file_list = [p for p in base.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]

    total = len(file_list)
    if progress:
        progress(0, total, "start")

    processed = failed = 0
    for i, src in enumerate(file_list, start=1):
        if progress:
            progress(i - 1, total, src.name)
        try:
            with Image.open(src) as im:
                blurred = im.filter(ImageFilter.GaussianBlur(radius=radius))
                dst = out_path / src.name
                if dst.suffix.lower() in {".jpg", ".jpeg"} and blurred.mode in ("RGBA", "LA", "P"):
                    blurred = blurred.convert("RGB")
                blurred.save(dst)
            processed += 1
        except Exception as e:
            print(f"[quick-blur] failed {src}: {e}")
            failed += 1

    if progress:
        progress(total, total, "done")

    return {
        "input": str(in_path),
        "output": str(out_path),
        "total": total,
        "processed": processed,
        "failed": failed,
        "radius": radius,
    }
