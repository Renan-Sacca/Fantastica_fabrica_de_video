"""Repositório de jobs de áudio (OmniVoice) — CRUD no MySQL."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.database import SessionLocal
from app.models.audio_job import AudioJob

logger = logging.getLogger(__name__)


def create_job(
    job_id: str,
    user_id: Optional[int],
    title: str,
    text: str,
    mode: str,
    instruct: str,
    drive_folder_id: Optional[str] = None,
    metadata_file_id: Optional[str] = None,
) -> None:
    with SessionLocal() as session:
        job = AudioJob(
            job_id=job_id,
            user_id=user_id,
            title=title,
            text=text,
            mode=mode,
            instruct=instruct,
            status="pending",
            progress=0,
            detail="Aguardando worker...",
            drive_folder_id=drive_folder_id,
            metadata_file_id=metadata_file_id,
        )
        session.add(job)
        session.commit()
        logger.info(f"[{job_id}] Job de áudio criado no MySQL.")


def get_job(job_id: str) -> Optional[dict]:
    with SessionLocal() as session:
        job = session.scalar(select(AudioJob).where(AudioJob.job_id == job_id))
        return job.to_dict() if job else None


def get_all_jobs(user_id: Optional[int] = None) -> list[dict]:
    with SessionLocal() as session:
        stmt = select(AudioJob).where(AudioJob.is_deleted == False)  # noqa: E712
        if user_id is not None:
            stmt = stmt.where(AudioJob.user_id == user_id)
        stmt = stmt.order_by(AudioJob.created_at.desc())
        return [j.to_dict() for j in session.scalars(stmt).all()]


def rename_job(job_id: str, new_title: str) -> bool:
    with SessionLocal() as session:
        job = session.scalar(select(AudioJob).where(AudioJob.job_id == job_id))
        if not job:
            return False
        job.title = new_title
        session.commit()
        return True


def soft_delete_job(job_id: str) -> Optional[dict]:
    with SessionLocal() as session:
        job = session.scalar(select(AudioJob).where(AudioJob.job_id == job_id))
        if not job:
            return None
        job.is_deleted = True
        job.deleted_at = datetime.utcnow()
        session.commit()
        return job.to_dict()
