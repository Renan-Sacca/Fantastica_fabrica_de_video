"""Models do banco de dados do worker (espelham os do serviço web)."""
from .job import Job
from .whatsapp import WhatsAppJob
from .whatsapp_extract import WhatsAppExtractJob
from .video_bg import VideoBgJob

__all__ = ["Job", "WhatsAppJob", "WhatsAppExtractJob", "VideoBgJob"]
