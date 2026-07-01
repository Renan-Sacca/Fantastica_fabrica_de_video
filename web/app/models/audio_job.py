"""Model para jobs de geração de áudio (OmniVoice) — tabela independente."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AudioJob(Base):
    """Job de geração de áudio do OmniVoice (independente dos jobs de vídeo)."""

    __tablename__ = "omnivoice_audio_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Áudio")

    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Entrada
    text: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT().with_variant(Text, "sqlite"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(20), default="auto")  # clone|design|auto
    instruct: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Estado
    status: Mapped[str] = mapped_column(String(30), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Google Drive
    drive_folder_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metadata_file_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    audio_drive_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "user_id": self.user_id,
            "text": self.text,
            "mode": self.mode,
            "instruct": self.instruct,
            "status": self.status,
            "progress": self.progress,
            "detail": self.detail,
            "error": self.error,
            "is_deleted": self.is_deleted,
            "drive_folder_id": self.drive_folder_id,
            "metadata_file_id": self.metadata_file_id,
            "audio_drive_id": self.audio_drive_id,
            "audio_url": self.audio_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
