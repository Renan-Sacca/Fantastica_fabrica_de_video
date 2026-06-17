"""Models do banco de dados, separados por domínio.

- Job: tabela base com os campos comuns a todos os tipos de vídeo.
- WhatsAppJob: dados específicos de vídeos de WhatsApp.
- WhatsAppExtractJob: dados específicos da extração de conversas de vídeo.

Usa herança por junção (joined-table inheritance) do SQLAlchemy: cada tipo
possui sua própria tabela, mantendo os models bem separados.
"""
from .job import Job
from .whatsapp import WhatsAppJob
from .whatsapp_extract import WhatsAppExtractJob

__all__ = ["Job", "WhatsAppJob", "WhatsAppExtractJob"]
