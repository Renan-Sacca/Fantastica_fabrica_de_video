"""Model específico da extração de conversas a partir de vídeos."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from .job import Job


class WhatsAppExtractJob(Job):
    """Dados específicos de um job de extração de conversa de vídeo.

    Mantém em cache o texto extraído para que a listagem não precise
    ler o conteúdo do Drive a cada carregamento.
    """

    __tablename__ = "whatsapp_extract_jobs"

    id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)

    video_original_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversa_txt_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversa_json_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    conversa_text: Mapped[Optional[str]] = mapped_column(
        MEDIUMTEXT().with_variant(Text, "sqlite"), nullable=True
    )

    __mapper_args__ = {"polymorphic_identity": "whatsapp_extract"}

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            "video_original_id": self.video_original_id,
            "conversa_txt_id": self.conversa_txt_id,
            "conversa_json_id": self.conversa_json_id,
            "conversa_text": self.conversa_text,
        })
        return data
