"""Model específico de vídeos de WhatsApp."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .job import Job


class WhatsAppJob(Job):
    """Configurações específicas de um vídeo de conversa de WhatsApp."""

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

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "contact_name": self.contact_name,
            "contact_status": self.contact_status,
            "video_format": self.video_format,
            "fps": self.fps,
            "speed": self.speed,
            "reading_speed": self.reading_speed,
            "scroll_speed": self.scroll_speed,
            "animation_style": self.animation_style,
        })
        return data
