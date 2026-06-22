"""Models do banco de dados, separados por domínio."""
from .job import Job
from .whatsapp import WhatsAppJob
from .whatsapp_extract import WhatsAppExtractJob
from .text_correction import TextCorrectionJob
from .user import User
from .permission import Permission

__all__ = ["Job", "WhatsAppJob", "WhatsAppExtractJob", "TextCorrectionJob", "User", "Permission"]
