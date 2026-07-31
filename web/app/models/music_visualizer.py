"""Model específico para vídeos Music Visualizer."""
from __future__ import annotations

from .job import Job


class MusicVisualizerJob(Job):
    """Job de Music Visualizer. Usa a mesma tabela de Job (Single Table Inheritance)."""

    __mapper_args__ = {"polymorphic_identity": "music_visualizer"}

    def to_dict(self) -> dict:
        return super().to_dict()
