import cv2
import numpy as np
from typing import List, Dict, Any


class BubbleDetector:
    """
    Detecta os balões de mensagem pela COR (não por bordas).

    - Balão enviado: esverdeado  -> USER_2
    - Balão recebido: claro/branco (tema claro) -> USER_1

    Retorna as caixas (bounding boxes) de cada balão. O pipeline usa essas
    caixas para saber a quais balões cada linha de texto pertence.
    """

    def __init__(
        self,
        green_lo=(35, 25, 60),
        green_hi=(95, 255, 255),
        recv_v_min: int = 238,
        recv_s_max: int = 30,
    ):
        self.green_lo = np.array(green_lo, dtype=np.uint8)
        self.green_hi = np.array(green_hi, dtype=np.uint8)
        self.recv_v_min = recv_v_min
        self.recv_s_max = recv_s_max

    def detect_bubbles(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        green_mask = cv2.inRange(hsv, self.green_lo, self.green_hi)

        recv_mask = cv2.inRange(
            hsv,
            np.array((0, 0, self.recv_v_min), dtype=np.uint8),
            np.array((180, self.recv_s_max, 255), dtype=np.uint8),
        )
        # Garante que o branco não invada onde já é verde
        recv_mask = cv2.bitwise_and(recv_mask, cv2.bitwise_not(green_mask))

        bubbles: List[Dict[str, Any]] = []
        bubbles += self._boxes_from_mask(green_mask, "USER_2", w, h)
        bubbles += self._boxes_from_mask(recv_mask, "USER_1", w, h)
        return bubbles

    def _boxes_from_mask(self, mask: np.ndarray, author: str, w: int, h: int) -> List[Dict[str, Any]]:
        # Fecha buracos do texto dentro do balão para virar um bloco sólido
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 9))
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        frame_area = w * h
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
            area = bw * bh

            # Filtros para ignorar ruído e regiões que ocupam a tela toda
            if bw < w * 0.06 or bw > w * 0.93:
                continue
            if bh < 14:
                continue
            if area < frame_area * 0.0012:
                continue

            boxes.append({
                "x1": x,
                "y1": y,
                "x2": x + bw,
                "y2": y + bh,
                "author": author,
            })
        return boxes
