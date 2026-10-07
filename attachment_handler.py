"""
Attachment text extraction helpers for requirement parsing context.

Goal:
- Convert common recruitment attachment formats into normalized text.
- Keep extraction best-effort and non-fatal.
"""

from __future__ import annotations

from io import BytesIO
import logging
from pathlib import Path
from typing import Callable

from utils import extract_pdf_text

_LOG = logging.getLogger(__name__)


def _ext_from_name(name: str) -> str:
    return Path(name or "").suffix.lower()


def _extract_docx(data: bytes) -> str:
    try:
        import docx  # type: ignore[import-not-found]
    except ImportError:
        _LOG.warning("python-docx not installed; skipping DOCX extraction")
        return ""
    try:
        doc = docx.Document(BytesIO(data))
        parts = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(parts).strip()
    except Exception as exc:
        _LOG.warning("DOCX parse failed: %s", exc)
        return ""


def _extract_xlsx(data: bytes) -> str:
    try:
        import pandas as pd  # type: ignore[import-not-found]
    except ImportError:
        _LOG.warning("pandas/openpyxl not installed; skipping XLSX extraction")
        return ""
    try:
        xl = pd.ExcelFile(BytesIO(data))
        chunks: list[str] = []
        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name=sheet_name)
            if df.empty:
                continue
            text = df.fillna("").astype(str).to_string(index=False)
            if text.strip():
                chunks.append(f"--- Sheet: {sheet_name} ---\n{text}")
        return "\n\n".join(chunks).strip()
    except Exception as exc:
        _LOG.warning("XLSX parse failed: %s", exc)
        return ""


def _extract_image_ocr(data: bytes) -> str:
    try:
        from PIL import Image  # type: ignore[import-not-found]
        import pytesseract  # type: ignore[import-not-found]
    except ImportError:
        _LOG.warning("Pillow/pytesseract not installed; skipping OCR extraction")
        return ""
    try:
        img = Image.open(BytesIO(data))
        txt = pytesseract.image_to_string(img)
        return (txt or "").strip()
    except Exception as exc:
        _LOG.warning("Image OCR failed: %s", exc)
        return ""


def _extract_plain(data: bytes) -> str:
    try:
        return data.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def extract_text_from_attachment(
    data: bytes,
    *,
    name: str = "",
    content_type: str = "",
    max_chars: int = 150_000,
) -> str:
    """
    Best-effort converter for attachment bytes -> text.
    Returns empty string when unsupported/unreadable.
    """
    if not data:
        return ""

    ext = _ext_from_name(name)
    ct = (content_type or "").lower()

    mapping: list[tuple[Callable[[], bool], Callable[[bytes], str]]] = [
        (lambda: ext == ".pdf" or "pdf" in ct, extract_pdf_text),
        (
            lambda: ext == ".docx"
            or "wordprocessingml.document" in ct
            or "msword" in ct,
            _extract_docx,
        ),
        (
            lambda: ext in {".xlsx", ".xlsm"}
            or "spreadsheetml.sheet" in ct
            or "excel" in ct,
            _extract_xlsx,
        ),
        (
            lambda: ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
            or ct.startswith("image/"),
            _extract_image_ocr,
        ),
        (lambda: ext in {".txt", ".csv", ".tsv"}, _extract_plain),
    ]

    for predicate, extractor in mapping:
        try:
            if predicate():
                out = extractor(data) or ""
                out = out[:max_chars].strip()
                if out:
                    from requirement_segmenter import is_candidate_profile_text, strip_all_exclusion_zones
                    if is_candidate_profile_text(out):
                        _LOG.info("attachment_rejected_as_candidate_profile name=%r", name)
                        return ""
                    return strip_all_exclusion_zones(out)
                return ""
        except Exception:
            continue
    return ""

