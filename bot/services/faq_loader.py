from __future__ import annotations

import hashlib
from pathlib import Path

from bot.config import get_settings

_cached_text: str | None = None
_cached_mtime: float | None = None


def load_faq(path: str | None = None) -> str:
    global _cached_text, _cached_mtime

    settings = get_settings()
    faq_path = Path(path or settings.faq_path)
    if not faq_path.is_file():
        return (
            "База знаний пуста. Отвечайте вежливо и предлагайте позвать оператора."
        )

    mtime = faq_path.stat().st_mtime
    if _cached_text is not None and _cached_mtime == mtime:
        return _cached_text

    text = faq_path.read_text(encoding="utf-8").strip()
    _cached_text = text
    _cached_mtime = mtime
    return text


def faq_content_hash() -> str | None:
    text = load_faq()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
