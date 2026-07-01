"""Acesso ao MySQL para o worker do OmniVoice (tabela omnivoice_audio_jobs)."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, Text, create_engine, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

logger = logging.getLogger("OmniDB")

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "fabrica_video_db")


def _url() -> str:
    return (
        f"mysql+pymysql://{quote_plus(MYSQL_USER)}:{quote_plus(MYSQL_PASSWORD)}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
    )


class Base(DeclarativeBase):
    pass


class AudioJob(Base):
    """Espelha a tabela criada pelo serviço web."""

    __tablename__ = "omnivoice_audio_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="Áudio")
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="auto")
    instruct: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    drive_folder_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metadata_file_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    audio_drive_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


_engine = create_engine(_url(), pool_pre_ping=True, pool_recycle=3600, echo=False)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    try:
        Base.metadata.create_all(bind=_engine)
        logger.info("Tabela omnivoice_audio_jobs verificada/criada (worker).")
    except Exception as e:
        logger.warning(f"Falha ao verificar/criar tabela: {e}")


def update_status(
    job_id: str,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    detail: Optional[str] = None,
    error: Optional[str] = None,
    audio_drive_id: Optional[str] = None,
    audio_url: Optional[str] = None,
) -> None:
    try:
        with SessionLocal() as session:
            job = session.scalar(select(AudioJob).where(AudioJob.job_id == job_id))
            if not job:
                logger.warning(f"[{job_id}] Job não encontrado no MySQL.")
                return
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if detail is not None:
                job.detail = detail
            if error is not None:
                job.error = error
            if audio_drive_id is not None:
                job.audio_drive_id = audio_drive_id
            if audio_url is not None:
                job.audio_url = audio_url
            session.commit()
    except Exception as e:
        logger.warning(f"[{job_id}] Falha ao atualizar MySQL: {e}")
