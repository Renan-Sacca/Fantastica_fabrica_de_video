import logging
import cv2
import numpy as np
from paddleocr import PaddleOCR
import paddle

logger = logging.getLogger(__name__)


class OCREngine:
    def __init__(self, lang: str = "pt"):
        use_gpu = paddle.device.is_compiled_with_cuda()
        logger.info(f"Inicializando PaddleOCR (lang={lang}). Suporte GPU/CUDA detectado: {use_gpu}")

        # Desabilitando debug logger do paddleocr para não poluir
        logging.getLogger("ppocr").setLevel(logging.WARNING)

        # lang='pt' usa o modelo de reconhecimento latino treinado para português.
        # Mantemos apenas UM idioma para evitar leituras conflitantes.
        self.ocr = PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=use_gpu, show_log=False)

    def _upscale_if_small(self, img: np.ndarray, min_height: int = 720) -> np.ndarray:
        """Amplia o frame quando ele é pequeno, melhorando a leitura de fontes finas."""
        h, w = img.shape[:2]
        if h < min_height:
            scale = min_height / float(h)
            img = cv2.resize(img, (int(w * scale), min_height), interpolation=cv2.INTER_CUBIC)
        return img

    def extract_lines(self, img: np.ndarray, min_conf: float = 0.6):
        """
        Executa OCR no frame inteiro e retorna cada linha detectada com sua caixa
        delimitadora. Isso permite agrupar linhas em mensagens e descobrir o autor
        pela posição horizontal do balão.

        Retorna: [{ 'text', 'conf', 'left', 'right', 'top', 'bottom' }, ...]
        """
        img = self._upscale_if_small(img)
        result = self.ocr.ocr(img, cls=True)

        lines = []
        if result and result[0]:
            for line in result[0]:
                box = line[0]  # 4 pontos [x, y]
                text_info = line[1]
                text = (text_info[0] or "").strip()
                conf = float(text_info[1])
                if not text or conf < min_conf:
                    continue

                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                lines.append({
                    "text": text,
                    "conf": conf,
                    "left": min(xs),
                    "right": max(xs),
                    "top": min(ys),
                    "bottom": max(ys),
                })
        return lines

    def extract_text(self, img: np.ndarray) -> str:
        """Mantido por compatibilidade: retorna apenas o texto concatenado."""
        lines = self.extract_lines(img)
        return "\n".join(l["text"] for l in lines).strip()
