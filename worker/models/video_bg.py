"""Model específico para vídeos com fundo + áudio (worker)."""
from __future__ import annotations

from .job import Job


class VideoBgJob(Job):
    """Configurações de um vídeo de fundo. Usa a mesma tabela de Job (Single Table Inheritance)."""

    __mapper_args__ = {"polymorphic_identity": "video_bg"}
