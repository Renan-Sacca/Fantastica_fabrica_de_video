"""Implementação do tipo de vídeo WhatsApp."""
from .base import VideoTypeConfig


class WhatsAppVideoType(VideoTypeConfig):
    @property
    def video_type(self) -> str:
        return "whatsapp"

    @property
    def display_name(self) -> str:
        return "WhatsApp"

    @property
    def drive_folder_name(self) -> str:
        return "WhatsApp"

    @property
    def icon(self) -> str:
        return "💬"
