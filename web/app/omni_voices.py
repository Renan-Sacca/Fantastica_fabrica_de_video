"""Gerenciamento de vozes de referência do OmniVoice (clonagem)."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import List

from app.config import OMNI_CUSTOM_INDEX, OMNI_VOICES_DIR


def _load_index() -> dict:
    if OMNI_CUSTOM_INDEX.exists():
        try:
            return json.loads(OMNI_CUSTOM_INDEX.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_index(index: dict) -> None:
    OMNI_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    OMNI_CUSTOM_INDEX.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def list_custom() -> List[dict]:
    index = _load_index()
    result = []
    for voice_id, info in index.items():
        if (OMNI_VOICES_DIR / info["filename"]).exists():
            result.append({
                "id": voice_id,
                "name": info["name"],
                "filename": info["filename"],
                "reference_text": info.get("reference_text", ""),
            })
    return sorted(result, key=lambda v: v["name"].lower())


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "voz"


def save_custom(name: str, content: bytes, original_filename: str, reference_text: str) -> dict:
    OMNI_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(original_filename).suffix.lower() or ".wav"
    voice_id = uuid.uuid4().hex[:8]
    filename = f"omni_{_slugify(name)}_{voice_id}{ext}"

    (OMNI_VOICES_DIR / filename).write_bytes(content)

    index = _load_index()
    index[voice_id] = {
        "name": name.strip(),
        "filename": filename,
        "reference_text": (reference_text or "").strip(),
    }
    _save_index(index)

    return {"id": voice_id, "name": name.strip(), "filename": filename}


def get_custom(voice_id: str) -> dict | None:
    index = _load_index()
    info = index.get(voice_id)
    if info and (OMNI_VOICES_DIR / info["filename"]).exists():
        return {"id": voice_id, **info}
    return None


def delete_custom(voice_id: str) -> bool:
    index = _load_index()
    info = index.pop(voice_id, None)
    if not info:
        return False
    try:
        (OMNI_VOICES_DIR / info["filename"]).unlink(missing_ok=True)
    except Exception:
        pass
    _save_index(index)
    return True
