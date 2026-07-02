"""Tipo de vídeo: Vídeo com Fundo + Áudio."""
from .base import VideoTypeConfig


class VideoBgVideoType(VideoTypeConfig):
    """Configuração do tipo 'video_bg'."""

    @property
    def video_type(self) -> str:
        return "video_bg"

    @property
    def display_name(self) -> str:
        return "Vídeo com Fundo"

    @property
    def drive_folder_name(self) -> str:
        return "VideoBg"

    @property
    def icon(self) -> str:
        return "🎬"
