from pathlib import Path
from PIL import Image
from mediatool.utils.logging import get_logger

log = get_logger(__name__)
ALLOWED = {".png", ".jpg", ".jpeg"}

def _convert_one(src: Path, quality=90, png_lossless=True) -> bool:
    ext = src.suffix.lower()
    dst = src.with_suffix(".webp")
    try:
        with Image.open(src) as im:
            params = {}
            if im.info.get("exif"):
                params["exif"] = im.info["exif"]
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
            if ext == ".png" and png_lossless:
                params["lossless"] = True
            else:
                params["quality"] = int(quality)
                params["method"] = 6
            if dst.exists():
                dst.unlink()
            im.save(dst, "WEBP", **params)
        if dst.exists() and dst.stat().st_size > 0:
            src.unlink()
            log.info("OK %s → %s", src.name, dst.name)
            return True
    except Exception as e:
        log.error("ERR %s → %s", src.name, e)
    if dst.exists():
        dst.unlink(missing_ok=True)
    return False

def convert_folder_to_webp(folder: str | Path, recursive=True, quality=90, png_lossless=True):
    root = Path(folder)
    paths = root.rglob("*") if recursive else root.glob("*")
    total = ok = 0
    for p in paths:
        if p.is_file() and p.suffix.lower() in ALLOWED:
            total += 1
            if _convert_one(p, quality, png_lossless):
                ok += 1
    return ok, total
