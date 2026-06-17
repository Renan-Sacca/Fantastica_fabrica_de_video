"""Model específico da extração de conversas a partir de vídeos (worker)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from .job import Job


class WhatsAppExtractJob(Job):
    __tablename__ = "whatsapp_extract_jobs"

    id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)

    video_original_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversa_txt_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversa_json_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversa_text: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT().with_variant(Text, "sqlite"), nullable=True
    )

    __mapper_args__ = {"polymorphic_identity": "whatsapp_extract"}
