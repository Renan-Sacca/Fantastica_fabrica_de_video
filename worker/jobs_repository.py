"""Repositório de Jobs do worker — escreve status/progresso no MySQL.

Mantém o MySQL como índice rápido para a listagem do serviço web, em paralelo
à atualização do metadata.json no Drive (fonte completa).
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from database import SessionLocal
from models import Job

logger = logging.getLogger("JobsRepository")


def update_status(
    job_id: str,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    detail: Optional[str] = None,
    error: Optional[str] = None,
    video_drive_id: Optional[str] = None,
    video_url: Optional[str] = None,
) -> None:
    """Atualiza o estado de processamento de um job no MySQL."""
    try:
        with SessionLocal() as session:
            job = session.scalar(select(Job).where(Job.job_id == job_id))
            if not job:
                logger.warning(f"[{job_id}] Job não encontrado no MySQL para update_status.")
                return
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if detail is not None:
                job.detail = detail
            if error is not None:
                job.error = error
            if video_drive_id is not None:
                job.video_drive_id = video_drive_id
            if video_url is not None:
                job.video_url = video_url
            session.commit()
    except Exception as e:
        logger.warning(f"[{job_id}] Falha ao atualizar status no MySQL: {e}")


def update_extract_result(
    job_id: str,
    conversa_txt_id: Optional[str] = None,
    conversa_json_id: Optional[str] = None,
    conversa_text: Optional[str] = None,
) -> None:
    """Salva no MySQL o resultado da extração (ids + texto em cache)."""
    try:
        from models import WhatsAppExtractJob

        with SessionLocal() as session:
            job = session.scalar(
                select(WhatsAppExtractJob).where(WhatsAppExtractJob.job_id == job_id)
            )
            if not job:
                logger.warning(f"[{job_id}] Extract job não encontrado no MySQL.")
                return
            if conversa_txt_id is not None:
                job.conversa_txt_id = conversa_txt_id
            if conversa_json_id is not None:
                job.conversa_json_id = conversa_json_id
            if conversa_text is not None:
                job.conversa_text = conversa_text
            session.commit()
    except Exception as e:
        logger.warning(f"[{job_id}] Falha ao salvar resultado da extração no MySQL: {e}")
