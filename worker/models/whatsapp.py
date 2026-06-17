"""Model específico de vídeos de WhatsApp (worker)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .job import Job


class WhatsAppJob(Job):
    __tablename__ = "whatsapp_jobs"

    id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)

    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_status: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    video_format: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    fps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reading_speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    scroll_speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    animation_style: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __mapper_args__ = {"polymorphic_identity": "whatsapp"}
