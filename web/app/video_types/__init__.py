"""Registry de tipos de vídeo.

Para adicionar um novo tipo de vídeo:
1. Crie um arquivo <tipo>.py nesta pasta implementando VideoTypeConfig
2. Importe e registre em REGISTRY abaixo
3. No worker, crie worker/renderers/<tipo>/ com a implementação
"""
from .base import VideoTypeConfig
from .whatsapp import WhatsAppVideoType
from .whatsapp_extract import WhatsAppExtractVideoType
from .video_bg import VideoBgVideoType
from .video_compositor import VideoCompositorVideoType

# ── Registry ──
# Para adicionar novos tipos: basta inserir aqui
REGISTRY: dict[str, VideoTypeConfig] = {
    "whatsapp": WhatsAppVideoType(),
    "whatsapp_extract": WhatsAppExtractVideoType(),
    "video_bg": VideoBgVideoType(),
    "video_compositor": VideoCompositorVideoType(),
    # Futuramente:
    # "reddit": RedditVideoType(),
    # "twitter": TwitterVideoType(),
}


def get_video_type(name: str) -> VideoTypeConfig:
    """Retorna a configuração de um tipo de vídeo."""
    vt = REGISTRY.get(name)
    if not vt:
        raise ValueError(f"Tipo de vídeo desconhecido: '{name}'. Disponíveis: {list(REGISTRY)}")
    return vt


def all_video_types() -> list[VideoTypeConfig]:
    """Lista todos os tipos disponíveis."""
    return list(REGISTRY.values())
