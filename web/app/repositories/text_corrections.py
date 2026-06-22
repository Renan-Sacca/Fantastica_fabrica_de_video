"""Repositório de jobs de correção de texto — CRUD no MySQL."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.database import SessionLocal
from app.models.text_correction import TextCorrectionJob

logger = logging.getLogger(__name__)


def create_job(job_id: str, raw_text: str, provider: str = "chatgpt") -> None:
    """Cria um novo job de correção de texto no MySQL."""
    with SessionLocal() as session:
        job = TextCorrectionJob(
            job_id=job_id,
            raw_text=raw_text,
            provider=provider,
            status="pending",
        )
        session.add(job)
        session.commit()
        logger.info(f"[{job_id}] Job de correção criado no MySQL (provider={provider}).")


def get_job(job_id: str) -> Optional[dict]:
    """Retorna um job de correção pelo job_id."""
    with SessionLocal() as session:
        job = session.scalar(
            select(TextCorrectionJob).where(TextCorrectionJob.job_id == job_id)
        )
        return job.to_dict() if job else None


def get_all_jobs() -> list[dict]:
    """Lista todos os jobs de correção (mais recentes primeiro)."""
    with SessionLocal() as session:
        stmt = (
            select(TextCorrectionJob)
            .order_by(TextCorrectionJob.created_at.desc())
        )
        return [j.to_dict() for j in session.scalars(stmt).all()]
