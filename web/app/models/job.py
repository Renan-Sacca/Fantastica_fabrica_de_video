"""Model base de Job — campos comuns a todos os tipos de vídeo."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Job(Base):
    """Tabela base com os campos comuns/básicos usados na listagem."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    video_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Estado do processamento (atualizado pelo worker)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Referências do Google Drive
    drive_folder_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    metadata_file_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    video_drive_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __mapper_args__ = {
        "polymorphic_identity": "job",
        "polymorphic_on": video_type,
    }

    def to_dict(self) -> dict:
        """Serializa os campos básicos comuns para uso nos templates/APIs."""
        return {
            "job_id": self.job_id,
            "title": self.title,
            "video_type": self.video_type,
            "status": self.status,
            "progress": self.progress,
            "detail": self.detail,
            "error": self.error,
            "drive_folder_id": self.drive_folder_id,
            "metadata_file_id": self.metadata_file_id,
            "video_drive_id": self.video_drive_id,
            "video_url": self.video_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
