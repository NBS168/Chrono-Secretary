#!/usr/bin/env python3
"""
批次圖檔處理工具：
1) 去白邊
2) 去背景 + 轉為 LINE 貼圖尺寸 370x320（等比例置中）
3) 檔名改為 [前綴文字]+[圖片 OCR 文字]

使用範例：
python image_sticker_processor.py \
  --input ./uploads \
  --output ./processed \
  --prefix 貼圖_
"""

from __future__ import annotations

import argparse
import io
import re
from pathlib import Path
from typing import Iterable

from PIL import Image

TARGET_SIZE = (370, 320)
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


def iter_images(input_path: Path) -> Iterable[Path]:
    if input_path.is_file() and input_path.suffix.lower() in SUPPORTED_EXTS:
        yield input_path
        return

    for p in input_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            yield p


def trim_white_border(img: Image.Image, threshold: int = 245) -> Image.Image:
    """裁掉接近白色的外框。"""
    rgba = img.convert("RGBA")
    px = rgba.load()
    width, height = rgba.size

    def is_non_white(x: int, y: int) -> bool:
        r, g, b, a = px[x, y]
        if a == 0:
            return False
        return not (r >= threshold and g >= threshold and b >= threshold)

    left, top = width, height
    right, bottom = -1, -1

    for y in range(height):
        for x in range(width):
            if is_non_white(x, y):
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

    if right == -1:
        # 整張幾乎全白時，回傳原圖避免裁切失敗。
        return rgba

    return rgba.crop((left, top, right + 1, bottom + 1))


def remove_bg(img: Image.Image) -> Image.Image:
    """優先使用 rembg；若不可用則退回簡易白底透明化。"""
    try:
        from rembg import remove  # type: ignore

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out = remove(buf.getvalue())
        return Image.open(io.BytesIO(out)).convert("RGBA")
    except Exception:
        rgba = img.convert("RGBA")
        data = []
        for r, g, b, a in rgba.getdata():
            if r > 245 and g > 245 and b > 245:
                data.append((255, 255, 255, 0))
            else:
                data.append((r, g, b, a))
        rgba.putdata(data)
        return rgba


def fit_to_line_sticker(img: Image.Image, target_size: tuple[int, int] = TARGET_SIZE) -> Image.Image:
    tw, th = target_size
    src = img.convert("RGBA")
    w, h = src.size
    if w == 0 or h == 0:
        raise ValueError("圖片尺寸不合法。")

    scale = min(tw / w, th / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", target_size, (255, 255, 255, 0))
    x = (tw - nw) // 2
    y = (th - nh) // 2
    canvas.paste(resized, (x, y), resized)
    return canvas


def extract_text_for_filename(img: Image.Image, fallback: str) -> str:
    """OCR 擷取文字當檔名。若無 OCR，使用 fallback。"""
    try:
        import pytesseract  # type: ignore

        text = pytesseract.image_to_string(img, lang="chi_tra+eng")
        cleaned = sanitize_filename(text)
        return cleaned or fallback
    except Exception:
        return fallback


def sanitize_filename(text: str) -> str:
    text = text.strip().replace("\n", " ")
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w\-\u4e00-\u9fff]", "", text)
    return text[:60]


def ensure_unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    idx = 2
    while True:
        candidate = path.with_name(f"{stem}_{idx}{suffix}")
        if not candidate.exists():
            return candidate
        idx += 1


def process_one(image_path: Path, output_dir: Path, prefix: str, index: int) -> Path:
    img = Image.open(image_path)
    trimmed = trim_white_border(img)
    no_bg = remove_bg(trimmed)
    sticker = fit_to_line_sticker(no_bg)

    ocr_text = extract_text_for_filename(trimmed, fallback=f"image_{index:03d}")
    name = sanitize_filename(f"{prefix}{ocr_text}") or f"{prefix}image_{index:03d}"
    out_path = ensure_unique(output_dir / f"{name}.png")
    sticker.save(out_path, format="PNG")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="批次圖片轉 LINE 貼圖工具")
    parser.add_argument("--input", required=True, help="輸入圖檔或資料夾")
    parser.add_argument("--output", required=True, help="輸出資料夾")
    parser.add_argument("--prefix", required=True, help="檔名前綴，例如：角色A_")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = list(iter_images(input_path))
    if not images:
        raise SystemExit("找不到可處理的圖片檔。")

    print(f"找到 {len(images)} 張圖片，開始處理...")
    for idx, image_path in enumerate(images, start=1):
        try:
            out = process_one(image_path, output_dir, args.prefix, idx)
            print(f"[{idx}/{len(images)}] ✅ {image_path} -> {out}")
        except Exception as e:
            print(f"[{idx}/{len(images)}] ❌ {image_path} 失敗：{e}")


if __name__ == "__main__":
    main()
