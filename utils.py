"""
Shared helpers: logging setup, PDF text extraction, safe JSON parsing.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import sys
from typing import Any


def setup_logging(level_name: str = "INFO") -> None:
    """Configure JSON structured logging with optional contextvars."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    try:
        import structlog
    except ImportError:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
            stream=sys.stdout,
            force=True,
        )
        return

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
    ]

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def bind_log_context(**kwargs: Any) -> None:
    """Bind request/task-scoped context for structured logs."""
    try:
        from structlog.contextvars import bind_contextvars
    except ImportError:
        return
    safe = {k: v for k, v in kwargs.items() if v not in (None, "")}
    if safe:
        bind_contextvars(**safe)


def clear_log_context() -> None:
    """Clear bound request/task-scoped context."""
    try:
        from structlog.contextvars import clear_contextvars
    except ImportError:
        return
    clear_contextvars()


def extract_pdf_text(data: bytes, max_chars: int = 120_000) -> str:
    """
    Best-effort text extraction from PDF bytes (optional dependency pypdf).
    Returns empty string if pypdf is missing or parsing fails.
    """
    if not data:
        return ""
    try:
        from io import BytesIO

        from pypdf import PdfReader
    except ImportError:
        logging.getLogger(__name__).warning("pypdf not installed; skipping PDF text extraction")
        return ""

    try:
        reader = PdfReader(BytesIO(data))
        parts: list[str] = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                parts.append(t.strip())
            if sum(len(p) for p in parts) >= max_chars:
                break
        out = "\n\n".join(parts)
        return out[:max_chars].strip()
    except Exception as exc:
        logging.getLogger(__name__).warning("PDF parse failed: %s", exc)
        return ""


def decode_graph_attachment_bytes(payload: dict[str, Any]) -> bytes | None:
    """Decode base64 contentBytes from a Graph fileAttachment JSON object."""
    raw = payload.get("contentBytes")
    if not raw or not isinstance(raw, str):
        return None
    try:
        return base64.b64decode(raw)
    except Exception:
        return None


_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def parse_json_loose(text: str) -> Any:
    """Parse JSON from model output, allowing optional ```json fences."""
    t = (text or "").strip()
    m = _JSON_FENCE.search(t)
    if m:
        t = m.group(1).strip()
    return json.loads(t)
