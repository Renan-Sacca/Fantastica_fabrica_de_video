"""Tipo de vídeo: Music Visualizer — visualizador de áudio estilo YouTube."""
from .base import VideoTypeConfig


class MusicVisualizerVideoType(VideoTypeConfig):
    """Configuração do tipo 'music_visualizer'."""

    @property
    def video_type(self) -> str:
        return "music_visualizer"

    @property
    def display_name(self) -> str:
        return "Music Visualizer"

    @property
    def drive_folder_name(self) -> str:
        return "MusicVisualizer"

    @property
    def icon(self) -> str:
        return "🎵"
