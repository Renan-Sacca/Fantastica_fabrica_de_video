"""Repositório de configurações salvas de áudio."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.audio_preset import AudioPreset

logger = logging.getLogger(__name__)


def create_preset(
    user_id: int,
    name: str,
    description: str = "",
    **params
) -> dict:
    """Cria uma nova configuração de parâmetros."""
    with SessionLocal() as session:
        preset = AudioPreset(
            preset_id=uuid.uuid4().hex[:8],
            user_id=user_id,
            name=name,
            description=description,
            **params
        )
        session.add(preset)
        session.commit()
        session.refresh(preset)
        logger.info(f"[{preset.preset_id}] Preset criado para usuário {user_id}.")
        return preset.to_dict()


def get_preset(preset_id: str) -> Optional[dict]:
    """Retorna um preset pelo ID."""
    with SessionLocal() as session:
        preset = session.scalar(
            select(AudioPreset)
            .where(AudioPreset.preset_id == preset_id)
            .where(AudioPreset.is_deleted == False)  # noqa: E712
        )
        return preset.to_dict() if preset else None


def get_user_presets(user_id: int) -> list[dict]:
    """Retorna todos os presets de um usuário (não deletados)."""
    with SessionLocal() as session:
        stmt = (
            select(AudioPreset)
            .where(AudioPreset.user_id == user_id)
            .where(AudioPreset.is_deleted == False)  # noqa: E712
            .order_by(AudioPreset.created_at.desc())
        )
        return [p.to_dict() for p in session.scalars(stmt).all()]


def count_user_presets(user_id: int) -> int:
    """Conta quantos presets o usuário possui (não deletados)."""
    with SessionLocal() as session:
        count = session.scalar(
            select(func.count(AudioPreset.id))
            .where(AudioPreset.user_id == user_id)
            .where(AudioPreset.is_deleted == False)  # noqa: E712
        )
        return count or 0


def update_preset(preset_id: str, name: str = None, description: str = None, **params) -> bool:
    """Atualiza informações de um preset."""
    with SessionLocal() as session:
        preset = session.scalar(
            select(AudioPreset).where(AudioPreset.preset_id == preset_id)
        )
        if not preset:
            return False
        if name is not None:
            preset.name = name
        if description is not None:
            preset.description = description
        # Atualiza parâmetros
        for key, value in params.items():
            if hasattr(preset, key):
                setattr(preset, key, value)
        session.commit()
        return True


def soft_delete_preset(preset_id: str) -> bool:
    """Marca um preset como deletado (soft delete)."""
    with SessionLocal() as session:
        preset = session.scalar(
            select(AudioPreset).where(AudioPreset.preset_id == preset_id)
        )
        if not preset:
            return False
        preset.is_deleted = True
        preset.deleted_at = datetime.utcnow()
        session.commit()
        logger.info(f"[{preset_id}] Preset deletado (soft delete).")
        return True


def check_preset_limit(user_id: int, max_presets: int, is_unlimited: bool) -> bool:
    """
    Verifica se o usuário pode criar mais presets.
    Retorna True se pode criar, False se atingiu o limite.
    """
    if is_unlimited:
        return True
    current_count = count_user_presets(user_id)
    return current_count < max_presets
