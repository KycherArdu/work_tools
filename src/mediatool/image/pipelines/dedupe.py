# src/mediatool/image/pipelines/dedupe.py
import os
import shutil
from PIL import Image
import imagehash
from collections import defaultdict
from typing import Callable, Iterable

IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp")


def _iter_images(root: str) -> list[str]:
    files: list[str] = []
    for dirpath, _, fnames in os.walk(root):
        for f in fnames:
            if os.path.splitext(f)[1].lower() in IMG_EXTS:
                files.append(os.path.join(dirpath, f))
    return files


def _avg_hash(path: str):
    try:
        with Image.open(path) as im:
            return imagehash.average_hash(im)
    except Exception as e:
        # Skip unreadable files
        print(f"[dedupe] hash error: {path} -> {e}")
        return None


def copy_images_and_deduplicate(
    source_folder: str,
    output_folder: str | None = None,
    progress: Callable[[int, int, str | None], None] | None = None,
):
    """
    Copy all images under `source_folder` into `ALL_MERGED` (or custom `output_folder`)
    and remove duplicates by perceptual average hash.

    Returns a dict summary.
    """
    src = os.path.abspath(source_folder)
    out = output_folder or os.path.join(src, "ALL_MERGED")
    os.makedirs(out, exist_ok=True)

    files = _iter_images(src)
    total = len(files)
    if progress:
        progress(0, total, "start")

    seen: dict[str, str] = {}
    copied = 0
    skipped = 0
    removed = 0  # (kept for compatibility—here we skip before copy)

    for i, source_path in enumerate(files, start=1):
        if progress:
            progress(i - 1, total, os.path.basename(source_path))

        h = _avg_hash(source_path)
        if h is None:
            continue
        key = str(h)

        if key in seen:
            skipped += 1
            continue  # duplicate -> don't copy
        else:
            # unique -> copy to output_folder (avoid name collisions)
            base = os.path.basename(source_path)
            name, ext = os.path.splitext(base)
            dest_path = os.path.join(out, base)
            counter = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(out, f"{name}_{counter}{ext}")
                counter += 1
            shutil.copy2(source_path, dest_path)
            seen[key] = dest_path
            copied += 1

    if progress:
        progress(total, total, "done")

    return {
        "source": src,
        "output": out,
        "total_scanned": total,
        "copied_unique": copied,
        "skipped_duplicates": skipped,
        "removed_after_copy": removed,  # always 0 in this fast path
    }
