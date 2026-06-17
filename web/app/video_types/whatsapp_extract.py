from .base import VideoTypeConfig

class WhatsAppExtractVideoType(VideoTypeConfig):
    @property
    def video_type(self) -> str:
        return "whatsapp_extract"

    @property
    def display_name(self) -> str:
        return "Extrator de Vídeo WhatsApp"

    @property
    def drive_folder_name(self) -> str:
        return "whatsapp_extracts"
        
    @property
    def icon(self) -> str:
        return "🎥"
