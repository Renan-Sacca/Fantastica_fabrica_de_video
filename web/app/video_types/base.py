"""Tipos de vídeo suportados — ponto de extensão para novos formatos."""
from __future__ import annotations

from abc import ABC, abstractmethod


class VideoTypeConfig(ABC):
    """Classe base para configuração de um tipo de vídeo."""

    @property
    @abstractmethod
    def video_type(self) -> str:
        """Identificador único: 'whatsapp', 'reddit', etc."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Nome amigável para exibição no dashboard."""
        ...

    @property
    @abstractmethod
    def drive_folder_name(self) -> str:
        """Nome da pasta no Google Drive para este tipo."""
        ...

    @property
    @abstractmethod
    def icon(self) -> str:
        """Emoji representando o tipo."""
        ...
