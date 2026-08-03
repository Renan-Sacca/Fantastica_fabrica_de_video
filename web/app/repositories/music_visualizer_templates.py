"""Persistência dos templates do Music Visualizer."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.database import SessionLocal
from app.models.music_visualizer_template import MusicVisualizerTemplate

MAX_TEMPLATE_DATA_BYTES = 64 * 1024


def _serialize(data: dict) -> str:
    serialized = json.dumps(data or {}, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_TEMPLATE_DATA_BYTES:
        raise ValueError("As configurações do template são muito grandes.")
    return serialized


def create_template(user_id: int, name: str, description: str = "", template_data: dict = None) -> dict:
    with SessionLocal() as session:
        template = MusicVisualizerTemplate(
            template_id=uuid.uuid4().hex[:8], user_id=user_id, name=name,
            description=description, template_data=_serialize(template_data or {}),
        )
        session.add(template)
        session.commit()
        session.refresh(template)
        return template.to_dict()


def get_template(template_id: str) -> Optional[dict]:
    with SessionLocal() as session:
        template = session.scalar(
            select(MusicVisualizerTemplate)
            .where(MusicVisualizerTemplate.template_id == template_id)
            .where(MusicVisualizerTemplate.is_deleted == False)  # noqa: E712
        )
        return template.to_dict() if template else None


def get_user_templates(user_id: int) -> list[dict]:
    with SessionLocal() as session:
        stmt = (
            select(MusicVisualizerTemplate)
            .where(MusicVisualizerTemplate.user_id == user_id)
            .where(MusicVisualizerTemplate.is_deleted == False)  # noqa: E712
            .order_by(MusicVisualizerTemplate.created_at.desc())
        )
        return [item.to_dict() for item in session.scalars(stmt).all()]


def update_template(template_id: str, name: str = None, description: str = None,
                    template_data: dict = None) -> bool:
    with SessionLocal() as session:
        template = session.scalar(
            select(MusicVisualizerTemplate)
            .where(MusicVisualizerTemplate.template_id == template_id)
            .where(MusicVisualizerTemplate.is_deleted == False)  # noqa: E712
        )
        if not template:
            return False
        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if template_data is not None:
            template.template_data = _serialize(template_data)
        session.commit()
        return True


def soft_delete_template(template_id: str) -> bool:
    with SessionLocal() as session:
        template = session.scalar(
            select(MusicVisualizerTemplate)
            .where(MusicVisualizerTemplate.template_id == template_id)
        )
        if not template:
            return False
        template.is_deleted = True
        template.deleted_at = datetime.utcnow()
        session.commit()
        return True
