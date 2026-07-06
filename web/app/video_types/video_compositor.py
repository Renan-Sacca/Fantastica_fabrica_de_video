"""Tipo de vídeo: Vídeo Compositor — composição visual avançada por camadas."""
from .base import VideoTypeConfig


class VideoCompositorVideoType(VideoTypeConfig):
    """Configuração do tipo 'video_compositor'."""

    @property
    def video_type(self) -> str:
        return "video_compositor"

    @property
    def display_name(self) -> str:
        return "Vídeo Compositor"

    @property
    def drive_folder_name(self) -> str:
        return "VideoCompositor"

    @property
    def icon(self) -> str:
        return "🎨"
