"""Utilitários para o renderer WhatsApp."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional


def image_to_data_uri(image_path: str) -> Optional[str]:
    path = Path(image_path)
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    mime_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                  ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
    mime = mime_types.get(suffix, "image/png")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_. ").strip()
