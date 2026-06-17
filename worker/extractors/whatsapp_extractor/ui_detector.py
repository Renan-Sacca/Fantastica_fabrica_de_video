import numpy as np
from typing import Optional, Dict

class UIDetector:
    def __init__(self, crop_config: Optional[Dict[str, int]] = None):
        """
        crop_config: dict com as chaves 'crop_top', 'crop_bottom', 'crop_left', 'crop_right'.
        Se None, aplicaremos uma heurística padrão para evitar barras do tiktok/reels.
        """
        self.crop_config = crop_config or {
            "crop_top": 210,    # Cabeçalho (nome do contato/online) — cortado mais alto
            "crop_bottom": 200, # Área de comentários / footer
            "crop_left": 10,
            "crop_right": 80    # Lado direito frequentemente tem botões de like/share em shorts/reels
        }

    def crop_frame(self, frame: np.ndarray) -> np.ndarray:
        """Corta o frame mantendo apenas a provável região de conversa."""
        h, w = frame.shape[:2]
        
        top = self.crop_config.get("crop_top", 0)
        bottom = self.crop_config.get("crop_bottom", 0)
        left = self.crop_config.get("crop_left", 0)
        right = self.crop_config.get("crop_right", 0)
        
        y1 = min(top, h - 1)
        y2 = max(0, h - bottom)
        x1 = min(left, w - 1)
        x2 = max(0, w - right)
        
        if y1 >= y2 or x1 >= x2:
            return frame # Configuração inválida, retorna original
            
        return frame[y1:y2, x1:x2]
