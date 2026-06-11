"""Classe base abstrata para renderers de vídeo."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional


class BaseRenderer(ABC):
    """
    Contrato que todo renderer deve implementar.

    Para criar um novo tipo de vídeo:
    1. Crie worker/renderers/<tipo>/__init__.py implementando esta classe
    2. Registre em worker/renderers/__init__.py
    """

    @property
    @abstractmethod
    def video_type(self) -> str:
        """Identificador único do tipo: 'whatsapp', 'reddit', etc."""
        ...

    @abstractmethod
    def render(
        self,
        job_data: dict,
        work_dir: Path,
        progress_callback: Optional[Callable] = None,
    ) -> Path:
        """
        Renderiza o vídeo.

        Args:
            job_data: Conteúdo do metadata.json do Drive
            work_dir: Diretório local com todos os arquivos baixados do Drive
            progress_callback: Função chamada com (status, progress, detail)

        Returns:
            Path para o arquivo .mp4 gerado
        """
        ...
