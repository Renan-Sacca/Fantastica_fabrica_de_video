"""Registry de renderers de vídeo.

Para adicionar um novo tipo:
1. Crie worker/renderers/<tipo>/ implementando BaseRenderer
2. Importe e registre abaixo
"""
from __future__ import annotations

from renderers.base import BaseRenderer
from renderers.whatsapp import WhatsAppRenderer

# ── Registry ──
# Mapeamento: video_type → classe do renderer
RENDERER_REGISTRY: dict[str, type[BaseRenderer]] = {
    "whatsapp": WhatsAppRenderer,
    # Futuramente:
    # "reddit": RedditRenderer,
    # "twitter": TwitterRenderer,
}


def get_renderer(video_type: str) -> BaseRenderer:
    """Retorna uma instância do renderer para o tipo especificado."""
    cls = RENDERER_REGISTRY.get(video_type)
    if not cls:
        available = list(RENDERER_REGISTRY.keys())
        raise ValueError(
            f"Renderer desconhecido: '{video_type}'. Disponíveis: {available}"
        )
    return cls()
