"""Repositório de templates do Vídeo Compositor."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.database import SessionLocal
from app.models.compositor_template import CompositorTemplate

logger = logging.getLogger(__name__)


def create_template(
    user_id: int,
    name: str,
    description: str = "",
    template_data: dict = None,
) -> dict:
    """Cria um novo template."""
    with SessionLocal() as session:
        template = CompositorTemplate(
            template_id=uuid.uuid4().hex[:8],
            user_id=user_id,
            name=name,
            description=description,
            template_data=json.dumps(template_data or {}, ensure_ascii=False),
        )
        session.add(template)
        session.commit()
        session.refresh(template)
        logger.info(f"[{template.template_id}] Template compositor criado para usuário {user_id}.")
        return template.to_dict()


def get_template(template_id: str) -> Optional[dict]:
    """Retorna um template pelo ID."""
    with SessionLocal() as session:
        template = session.scalar(
            select(CompositorTemplate)
            .where(CompositorTemplate.template_id == template_id)
            .where(CompositorTemplate.is_deleted == False)  # noqa: E712
        )
        return template.to_dict() if template else None


def get_user_templates(user_id: int) -> list[dict]:
    """Retorna todos os templates de um usuário (não deletados)."""
    with SessionLocal() as session:
        stmt = (
            select(CompositorTemplate)
            .where(CompositorTemplate.user_id == user_id)
            .where(CompositorTemplate.is_deleted == False)  # noqa: E712
            .order_by(CompositorTemplate.created_at.desc())
        )
        return [t.to_dict() for t in session.scalars(stmt).all()]


def update_template(
    template_id: str,
    name: str = None,
    description: str = None,
    template_data: dict = None,
) -> bool:
    """Atualiza informações de um template."""
    with SessionLocal() as session:
        template = session.scalar(
            select(CompositorTemplate)
            .where(CompositorTemplate.template_id == template_id)
            .where(CompositorTemplate.is_deleted == False)  # noqa: E712
        )
        if not template:
            return False
        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if template_data is not None:
            template.template_data = json.dumps(template_data, ensure_ascii=False)
        session.commit()
        return True


def soft_delete_template(template_id: str) -> bool:
    """Marca um template como deletado (soft delete)."""
    with SessionLocal() as session:
        template = session.scalar(
            select(CompositorTemplate)
            .where(CompositorTemplate.template_id == template_id)
        )
        if not template:
            return False
        template.is_deleted = True
        template.deleted_at = datetime.utcnow()
        session.commit()
        logger.info(f"[{template_id}] Template compositor deletado (soft delete).")
        return True
