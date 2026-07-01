"""Repositório de planos de vozes."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.database import SessionLocal
from app.models.voice_plan import VoicePlan

logger = logging.getLogger(__name__)


def get_plan(plan_id: int) -> Optional[dict]:
    """Retorna um plano de voz pelo ID."""
    with SessionLocal() as session:
        plan = session.scalar(select(VoicePlan).where(VoicePlan.id == plan_id))
        return plan.to_dict() if plan else None


def get_all_plans(active_only: bool = True) -> list[dict]:
    """Retorna todos os planos de vozes."""
    with SessionLocal() as session:
        stmt = select(VoicePlan)
        if active_only:
            stmt = stmt.where(VoicePlan.is_active == True)  # noqa: E712
        stmt = stmt.order_by(VoicePlan.max_voices)
        return [p.to_dict() for p in session.scalars(stmt).all()]


def get_basic_plan() -> Optional[dict]:
    """Retorna o plano básico (não ilimitado)."""
    with SessionLocal() as session:
        plan = session.scalar(
            select(VoicePlan)
            .where(VoicePlan.is_unlimited == False)  # noqa: E712
            .where(VoicePlan.is_active == True)  # noqa: E712
            .order_by(VoicePlan.max_voices)
            .limit(1)
        )
        return plan.to_dict() if plan else None


def get_admin_plan() -> Optional[dict]:
    """Retorna o plano admin (ilimitado)."""
    with SessionLocal() as session:
        plan = session.scalar(
            select(VoicePlan)
            .where(VoicePlan.is_unlimited == True)  # noqa: E712
            .where(VoicePlan.is_active == True)  # noqa: E712
            .limit(1)
        )
        return plan.to_dict() if plan else None
