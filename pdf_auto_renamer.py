#!/usr/bin/env python3
"""掃描 PDF 自動辨識並重新命名。

檔名格式：YYYYMMDD_客戶姓名_保單號碼_變更項目.pdf
若保單號碼不存在則略過該欄位。
"""

from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = {".pdf"}


@dataclass
class PdfMeta:
    customer_name: str | None = None
    policy_number: str | None = None
    change_item: str | None = None
    scan_date: str | None = None


def normalize_text(text: str) -> str:
    return re.sub(r"[ \t\u3000]+", " ", text.replace("\r", "")).strip()


def extract_text_with_pypdf(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    try:
        reader = PdfReader(str(pdf_path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def extract_text_with_ocr(pdf_path: Path, max_pages: int = 5, dpi: int = 250) -> str:
    """使用 OCR 辨識，最多前 max_pages 頁避免速度過慢。"""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return ""

    try:
        images = convert_from_path(str(pdf_path), dpi=dpi, first_page=1, last_page=max_pages)
    except Exception:
        return ""

    chunks: list[str] = []
    for img in images:
        try:
            chunks.append(pytesseract.image_to_string(img, lang="chi_tra+eng"))
        except Exception:
            continue
    return "\n".join(chunks)


def infer_customer_name(text: str) -> str | None:
    patterns = [
        r"(?:要保人|被保險人|姓名|客戶姓名)[:：\s]*([\u4e00-\u9fff]{2,6})",
        r"([\u4e00-\u9fff]{2,6})\s*(?:先生|小姐|女士)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def infer_policy_number(text: str) -> str | None:
    patterns = [
        r"(?:保單號碼|保單號|保單編號|保單No\.?|Policy\s*No\.?)[:：\s]*([A-Za-z0-9\-]{6,30})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def infer_change_item(text: str) -> str | None:
    patterns = [
        r"(?:申請項目|變更項目|異動項目|辦理項目)[:：\s]*([^\n]{2,30})",
        r"(受益人變更|地址變更|投資標的變更|自動扣款變更|契約內容變更)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return sanitize_segment(m.group(1))
    return None


def infer_scan_date(text: str, fallback_ts: float) -> str:
    patterns = [
        r"(20\d{2})[\-/年\.](\d{1,2})[\-/月\.](\d{1,2})",
        r"(1\d{2})[\-/年\.](\d{1,2})[\-/月\.](\d{1,2})",  # 民國年
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        year, month, day = map(int, m.groups())
        if year < 1911:
            year += 1911
        try:
            return datetime(year, month, day).strftime("%Y%m%d")
        except ValueError:
            continue
    return datetime.fromtimestamp(fallback_ts).strftime("%Y%m%d")


def sanitize_segment(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"[\\/:*?\"<>|]", "-", value)
    value = value.strip(" ._-")
    return value[:40] if value else ""


def build_filename(meta: PdfMeta, source: Path) -> str:
    date = sanitize_segment(meta.scan_date or "") or datetime.fromtimestamp(source.stat().st_mtime).strftime("%Y%m%d")
    name = sanitize_segment(meta.customer_name or "未辨識姓名") or "未辨識姓名"
    change_item = sanitize_segment(meta.change_item or "文件") or "文件"

    parts = [date, name]
    if meta.policy_number:
        parts.append(sanitize_segment(meta.policy_number))
    parts.append(change_item)
    return "_".join(parts) + source.suffix.lower()


def extract_meta(pdf_path: Path, ocr: bool) -> PdfMeta:
    raw_text = extract_text_with_pypdf(pdf_path)
    if ocr and len(raw_text.strip()) < 20:
        raw_text = extract_text_with_ocr(pdf_path)

    text = normalize_text(raw_text)
    return PdfMeta(
        customer_name=infer_customer_name(text),
        policy_number=infer_policy_number(text),
        change_item=infer_change_item(text),
        scan_date=infer_scan_date(text, pdf_path.stat().st_mtime),
    )


def unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    idx = 1
    while True:
        candidate = target.with_name(f"{target.stem}_{idx}{target.suffix}")
        if not candidate.exists():
            return candidate
        idx += 1


def iter_pdfs(folder: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        yield from (p for p in folder.rglob("*") if p.suffix.lower() in SUPPORTED_EXTENSIONS)
    else:
        yield from (p for p in folder.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)


def process_folder(folder: Path, recursive: bool, dry_run: bool, enable_ocr: bool, backup: bool) -> None:
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"資料夾不存在或不是目錄：{folder}")

    backup_dir = folder / "_backup_original_names"
    if backup and not dry_run:
        backup_dir.mkdir(exist_ok=True)

    for pdf_path in iter_pdfs(folder, recursive):
        meta = extract_meta(pdf_path, ocr=enable_ocr)
        new_name = build_filename(meta, pdf_path)
        target = unique_path(pdf_path.with_name(new_name))

        if pdf_path.name == target.name:
            print(f"[SKIP] {pdf_path.name}（已符合格式）")
            continue

        print(f"[RENAME] {pdf_path.name} -> {target.name}")
        if dry_run:
            continue
        if backup:
            shutil.copy2(pdf_path, backup_dir / pdf_path.name)
        pdf_path.rename(target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="掃描 PDF 自動辨識後重新命名")
    parser.add_argument("folder", help="要處理的 PDF 目錄")
    parser.add_argument("--recursive", action="store_true", help="遞迴掃描子資料夾")
    parser.add_argument("--dry-run", action="store_true", help="只顯示預計更名，不真的改檔")
    parser.add_argument("--no-ocr", action="store_true", help="不做 OCR（僅擷取 PDF 內嵌文字）")
    parser.add_argument("--no-backup", action="store_true", help="不備份原始檔名")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    process_folder(
        folder=Path(args.folder).expanduser().resolve(),
        recursive=args.recursive,
        dry_run=args.dry_run,
        enable_ocr=not args.no_ocr,
        backup=not args.no_backup,
    )


if __name__ == "__main__":
    main()
