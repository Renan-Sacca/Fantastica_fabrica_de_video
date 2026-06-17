import os
import cv2
import logging
from typing import Generator, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self, video_path: str, sample_interval_sec: float = 2.0,
                 dup_threshold: float = 0.015, motion_threshold: float = 0.02):
        self.video_path = video_path
        self.sample_interval_sec = sample_interval_sec
        # Mudança mínima em relação ao último frame analisado para reprocessar
        self.dup_threshold = dup_threshold
        # Movimento máximo (vs frame anterior) para o frame ser considerado nítido
        self.motion_threshold = motion_threshold
        self.video_capture = cv2.VideoCapture(video_path)

        if not self.video_capture.isOpened():
            raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

        self.original_fps = self.video_capture.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self.video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
        # 1 amostra a cada N segundos de vídeo (não precisa olhar todo frame)
        self.frame_interval = max(1, int(self.original_fps * self.sample_interval_sec))

        logger.info(
            f"Video {video_path}: {self.original_fps:.1f} FPS, {self.total_frames} frames. "
            f"Amostrando 1 frame a cada {self.sample_interval_sec}s (~{self.frame_interval} frames)."
        )

    def _calculate_difference(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """Calcula o percentual de pixels diferentes entre dois frames em escala de cinza."""
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

        diff = cv2.absdiff(gray1, gray2)
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        non_zero_count = np.count_nonzero(thresh)
        total_pixels = thresh.size

        return non_zero_count / total_pixels

    def extract_frames(self) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        Amostra 1 frame a cada `sample_interval_sec` segundos.

        - Pula amostras que estão em pleno scroll (borradas), comparando com o
          frame imediatamente anterior: se houve muito movimento, procura um
          frame parado logo em seguida.
        - Pula amostras praticamente idênticas à anterior (tela não mudou).
        """
        frame_idx = 0
        prev_frame: Optional[np.ndarray] = None
        last_yielded: Optional[np.ndarray] = None
        max_lookahead = max(1, int(self.original_fps * 0.8))  # até ~0.8s buscando frame nítido

        while True:
            ret, frame = self.video_capture.read()
            if not ret:
                break

            if frame_idx % self.frame_interval == 0:
                # Procura um frame nítido (parado) a partir deste ponto
                steady = frame
                steady_idx = frame_idx
                look = 0
                while prev_frame is not None and look < max_lookahead:
                    motion = self._calculate_difference(prev_frame, steady)
                    if motion <= self.motion_threshold:
                        break  # frame parado/nítido
                    prev_frame = steady
                    ret2, nxt = self.video_capture.read()
                    if not ret2:
                        break
                    steady = nxt
                    steady_idx += 1
                    look += 1

                if last_yielded is not None:
                    diff = self._calculate_difference(last_yielded, steady)
                    if diff < self.dup_threshold:
                        prev_frame = steady
                        frame_idx = steady_idx + 1
                        continue  # tela idêntica, pula
                last_yielded = steady.copy()
                prev_frame = steady
                yield steady_idx, steady
                frame_idx = steady_idx + 1
                continue

            prev_frame = frame
            frame_idx += 1

    def release(self):
        self.video_capture.release()
