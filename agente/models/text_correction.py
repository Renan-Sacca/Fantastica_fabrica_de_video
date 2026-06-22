"""Model para jobs de correção de texto via IA."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TextCorrectionJob(Base):
    """Tabela de jobs de correção de texto — independente dos jobs de vídeo."""

    __tablename__ = "text_correction_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    status: Mapped[str] = mapped_column(String(30), default="pending")
    provider: Mapped[str] = mapped_column(String(30), default="chatgpt")

    raw_text: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT().with_variant(Text, "sqlite"), nullable=True
    )
    corrected_text: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT().with_variant(Text, "sqlite"), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
