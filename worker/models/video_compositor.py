"""Model específico para vídeos do Compositor (worker)."""
from __future__ import annotations

from .job import Job


class VideoCompositorJob(Job):
    """Configurações de um vídeo compositor. Usa a mesma tabela de Job (Single Table Inheritance)."""

    __mapper_args__ = {"polymorphic_identity": "video_compositor"}
