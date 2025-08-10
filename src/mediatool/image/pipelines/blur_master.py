# src/mediatool/image/pipelines/blur_master.py

import os
import cv2
import numpy as np
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Optional Stage 1 (photo copy) ---
try:
    from SelectIMG import PhotoCopier   # your local helper (optional)
except Exception:
    PhotoCopier = None

# TensorFlow is only needed for some NudeNet builds; make it optional
try:
    import tensorflow as tf
except Exception:
    tf = None

# Pillow (for optimization + watermark)
from PIL import Image, ImageFilter  # noqa: F401  (ImageFilter reserved for future use)
try:
    RESAMPLE = Image.Resampling.LANCZOS  # Pillow >= 9.1
except Exception:
    RESAMPLE = Image.LANCZOS


# ======================= DEFAULTS / CONSTANTS =======================

WATERMARK_SETS = {
    "MIDNIGHT": {
        "port": r"E:\The Midnight Black Studios\watermark_midNight_port.png",
        "land": r"E:\The Midnight Black Studios\watermark_midNight_land.png",
    },
    "BLACK_MIR": {
        "port": r"E:\BLACK_MIRACLE\Black_Miracle_WM_port.png",
        "land": r"E:\BLACK_MIRACLE\Black_Miracle_WM_land.png",
    },
    "JINX": {
        "port": r"E:\Jinx_Universe\WATERMARK_JINX.png",
        "land": r"E:\Jinx_Universe\WATERMARK_JINX_land.png",
    },
    "JinXGirl": {
        "port": r"E:\XXX-Ai\DevianArt\WATERMARK\port_jingirl.png",
        "land": r"E:\XXX-Ai\DevianArt\WATERMARK\land_jingirl.png",
    },
}

NUDENET_CLASSES = [
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "ANUS_COVERED",
]

_BLUR_KERNEL_SIZE = 151   # odd number
_PADDING = 60
_CIRCLE_RADIUS_SCALE = 1.0

_nudectl = None  # cached NudeDetector instance


# ======================= TF / NudeNet helpers =======================

def _init_tf():
    if tf is None:
        return
    try:
        gpus = tf.config.list_physical_devices("GPU")
        if gpus:
            tf.config.experimental.set_memory_growth(gpus[0], True)
            print("✅ Using GPU for TensorFlow.")
        else:
            print("⚠️ GPU not found for TensorFlow. Using CPU.")
    except Exception as e:
        print(f"TensorFlow initialization error: {e}")


def _get_nude_detector():
    """Lazy-create NudeNet detector when first needed."""
    global _nudectl
    if _nudectl is None:
        from nudenet import NudeDetector  # import lazily to speed module import
        print("Initializing NudeNet detector (this may take a moment)...")
        _nudectl = NudeDetector()
        print("✅ NudeNet detector ready.")
    return _nudectl


# ======================= STAGE 2: CENSORING =======================

def _has_any(detections, wanted):
    for d in detections:
        if d.get("class") in wanted:
            return True
    return False


def _censor_one(args):
    (filename, in_dir, out_dir, classes, padding, blur_kernel, circle_scale) = args

    nude = _get_nude_detector()
    src = os.path.join(in_dir, filename)
    dst = os.path.join(out_dir, filename)

    try:
        det = nude.detect(src)
        img = cv2.imread(src)
        if img is None:
            return f"Skip {filename}: cannot read."

        if _has_any(det, classes):
            for r in det:
                if r["class"] in classes:
                    x, y, w, h = r["box"]
                    x = max(x - padding, 0)
                    y = max(y - padding, 0)
                    w = min(w + 2 * padding, img.shape[1] - x)
                    h = min(h + 2 * padding, img.shape[0] - y)

                    roi = img[y:y+h, x:x+w]
                    if roi.size == 0:
                        continue

                    mask = np.zeros(roi.shape[:2], dtype=np.uint8)
                    center = (w // 2, h // 2)
                    radius = int(min(w, h) / 2 * circle_scale)
                    cv2.circle(mask, center, radius, 255, -1)

                    blurred = cv2.GaussianBlur(roi, (blur_kernel, blur_kernel), 0)
                    img[y:y+h, x:x+w] = np.where(mask[:, :, None] == 255, blurred, roi)

        cv2.imwrite(dst, img)
        return None
    except Exception as e:
        return f"Error {filename}: {e}"


def _run_censoring(in_dir, out_dir, classes, padding, blur_kernel, circle_scale):
    os.makedirs(out_dir, exist_ok=True)
    files = [f for f in os.listdir(in_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    tasks = [
        (fn, in_dir, out_dir, classes, padding, blur_kernel, circle_scale) for fn in files
    ]
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as ex:
        futures = [ex.submit(_censor_one, t) for t in tasks]
        for fut in tqdm(as_completed(futures), total=len(files), desc="🖼️  Censoring images", unit="image"):
            msg = fut.result()
            if msg:
                tqdm.write(f"ℹ️ {msg}")
    return out_dir


# ======================= STAGE 3: OPTIMIZE + WATERMARK =======================
# (merged from your image_optimizer.py)

def optimize_image(input_path, output_path, max_width, max_height, quality):
    """Resize proportionally and save as JPEG."""
    with Image.open(input_path) as img:
        width, height = img.size

        # Proportional scaling
        if width > height:
            if width > max_width:
                height = int((max_width / width) * height)
                width = max_width
        else:
            if height > max_height:
                width = int((max_height / height) * width)
                height = max_height

        img = img.resize((width, height), RESAMPLE).convert("RGB")
        img.save(output_path, "JPEG", quality=int(quality), optimize=True)


def add_watermark(input_path, watermark_path, watermark_land_path,
                  output_path, opacity=0.5, quality=100):
    """Center watermark (portrait/landscape auto) and save JPEG."""
    base_img = Image.open(input_path).convert("RGBA")
    width, height = base_img.size

    # Choose watermark orientation
    wm = Image.open(watermark_land_path if width > height else watermark_path).convert("RGBA")

    # Scale watermark to ~95% of base width
    new_w = int(width * 0.95)
    new_h = int((new_w / wm.width) * wm.height)
    wm = wm.resize((new_w, new_h), RESAMPLE)

    # Apply opacity
    alpha = wm.split()[3].point(lambda p: int(p * float(opacity)))
    wm.putalpha(alpha)

    # Center position
    pos = (width // 2 - new_w // 2, height // 2 - new_h // 2)

    canvas = Image.new("RGBA", base_img.size)
    canvas.paste(base_img, (0, 0))
    canvas.paste(wm, pos, mask=wm)
    canvas.convert("RGB").save(output_path, "JPEG", quality=int(quality))


def _wm_one(index, filename, folder_path, output_folder,
           watermark_path, watermark_land_path,
           max_width, max_height, quality, opacity):
    """Single-file optimize + watermark."""
    in_path = os.path.join(folder_path, filename)
    folder_name = os.path.basename(folder_path)
    out_name = f"{folder_name}_{index}.jpg"
    out_path = os.path.join(output_folder, out_name)

    try:
        tmp_path = os.path.join(output_folder, f"tmp_{filename}")
        optimize_image(in_path, tmp_path, max_width, max_height, quality)
        add_watermark(tmp_path, watermark_path, watermark_land_path, out_path, opacity, quality)
        os.remove(tmp_path)
        # print(f"Processed: {in_path} -> {out_path}")
    except Exception as e:
        print(f"Failed to process {in_path}: {e}")


def optimize_images_in_folder(folder_path, output_folder,
                              watermark_path, watermark_land_path,
                              max_width, max_height, quality, opacity=0.5):
    """Batch optimize + watermark."""
    os.makedirs(output_folder, exist_ok=True)
    exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.gif')
    files = [f for f in os.listdir(folder_path) if os.path.splitext(f)[1].lower() in exts]

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as ex:
        futures = [
            ex.submit(
                _wm_one, i, fn, folder_path, output_folder,
                watermark_path, watermark_land_path,
                max_width, max_height, quality, opacity
            )
            for i, fn in enumerate(files, start=1)
        ]
        for _ in tqdm(as_completed(futures), total=len(files), desc="💧 Watermarking", unit="img"):
            pass

    return output_folder


# ======================= PUBLIC PIPELINE =======================

def run_blur_master(
    source_directory: str,
    enable_photo_copying: bool = False,
    copy_interval: int = 6,
    custom_dest_folder_name: str = "third_photos",
    # censoring:
    classes_to_check = None,
    blur_kernel_size: int = _BLUR_KERNEL_SIZE,
    padding: int = _PADDING if False else _PADDING,   # keep IDEs happy
    circle_radius_scale: float = _CIRCLE_RADIUS_SCALE,
    # watermark:
    watermark_brand: str | None = "JinXGirl",  # None/"" -> skip Stage 3
    watermark_sets: dict | None = None,
    max_width: int = 4000,
    max_height: int = 4000,
    img_quality: int = 80,
    wm_opacity: float = 0.7,
):
    """
    Full pipeline:
      1) (optional) copy photos every Nth image
      2) censor with NudeNet + circular Gaussian blur
      3) (optional) optimize + add watermark

    Returns dict: {input_used, censored_folder, watermarked_folder}
    """
    _init_tf()
    classes_to_check = classes_to_check or NUDENET_CLASSES
    wm_sets = watermark_sets or WATERMARK_SETS

    # --- Stage 1: copy (optional) ---
    if enable_photo_copying:
        if not PhotoCopier:
            raise RuntimeError("PhotoCopier (SelectIMG.py) not found but enable_photo_copying=True.")
        copier = PhotoCopier(
            source_folder=source_directory,
            n=copy_interval,
            dest_folder_name=custom_dest_folder_name,
            verbose=True
        )
        if not copier.run():
            raise RuntimeError("Photo copying failed.")
        folder_to_process = copier.dest_folder
    else:
        folder_to_process = source_directory

    # --- Stage 2: censor ---
    parent = os.path.abspath(os.path.join(folder_to_process, os.pardir))
    censored = os.path.join(parent, "CENSORED")
    _run_censoring(
        folder_to_process, censored,
        classes_to_check, padding, blur_kernel_size, circle_radius_scale
    )

    result = {"input_used": folder_to_process, "censored_folder": censored, "watermarked_folder": None}

    # --- Stage 3: optimize + watermark (optional) ---
    if watermark_brand:
        if watermark_brand not in wm_sets:
            raise ValueError(f"Unknown watermark brand: {watermark_brand}")
        wm = wm_sets[watermark_brand]
        wm_out = os.path.join(parent, "WATERMARK_DEMO")
        optimize_images_in_folder(
            folder_path=censored,
            output_folder=wm_out,
            watermark_path=wm["port"],
            watermark_land_path=wm["land"],
            max_width=max_width,
            max_height=max_height,
            quality=img_quality,
            opacity=wm_opacity
        )
        result["watermarked_folder"] = wm_out

    return result
