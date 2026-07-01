"""Repositório de vozes personalizadas dos usuários."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.user_voice import UserVoice

logger = logging.getLogger(__name__)


def create_voice(
    voice_id: str,
    user_id: int,
    name: str,
    filename: str,
    reference_text: str = "",
) -> dict:
    """Cria uma nova voz personalizada para o usuário."""
    with SessionLocal() as session:
        voice = UserVoice(
            voice_id=voice_id,
            user_id=user_id,
            name=name,
            filename=filename,
            reference_text=reference_text,
        )
        session.add(voice)
        session.commit()
        session.refresh(voice)
        logger.info(f"[{voice_id}] Voz criada para usuário {user_id}.")
        return voice.to_dict()


def get_voice(voice_id: str) -> Optional[dict]:
    """Retorna uma voz pelo ID."""
    with SessionLocal() as session:
        voice = session.scalar(
            select(UserVoice)
            .where(UserVoice.voice_id == voice_id)
            .where(UserVoice.is_deleted == False)  # noqa: E712
        )
        return voice.to_dict() if voice else None


def get_user_voices(user_id: int) -> list[dict]:
    """Retorna todas as vozes de um usuário (não deletadas)."""
    with SessionLocal() as session:
        stmt = (
            select(UserVoice)
            .where(UserVoice.user_id == user_id)
            .where(UserVoice.is_deleted == False)  # noqa: E712
            .order_by(UserVoice.created_at.desc())
        )
        return [v.to_dict() for v in session.scalars(stmt).all()]


def count_user_voices(user_id: int) -> int:
    """Conta quantas vozes o usuário possui (não deletadas)."""
    with SessionLocal() as session:
        count = session.scalar(
            select(func.count(UserVoice.id))
            .where(UserVoice.user_id == user_id)
            .where(UserVoice.is_deleted == False)  # noqa: E712
        )
        return count or 0


def update_voice(voice_id: str, name: str = None, reference_text: str = None) -> bool:
    """Atualiza informações de uma voz."""
    with SessionLocal() as session:
        voice = session.scalar(
            select(UserVoice).where(UserVoice.voice_id == voice_id)
        )
        if not voice:
            return False
        if name is not None:
            voice.name = name
        if reference_text is not None:
            voice.reference_text = reference_text
        session.commit()
        return True


def soft_delete_voice(voice_id: str) -> bool:
    """Marca uma voz como deletada (soft delete)."""
    with SessionLocal() as session:
        voice = session.scalar(
            select(UserVoice).where(UserVoice.voice_id == voice_id)
        )
        if not voice:
            return False
        voice.is_deleted = True
        voice.deleted_at = datetime.utcnow()
        session.commit()
        logger.info(f"[{voice_id}] Voz deletada (soft delete).")
        return True


def check_voice_limit(user_id: int, max_voices: int, is_unlimited: bool) -> bool:
    """
    Verifica se o usuário pode criar mais vozes.
    Retorna True se pode criar, False se atingiu o limite.
    """
    if is_unlimited:
        return True
    current_count = count_user_voices(user_id)
    return current_count < max_voices
