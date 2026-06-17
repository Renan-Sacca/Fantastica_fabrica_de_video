import json
import logging
from typing import Optional, Dict, Any, Tuple, List
from .video_processor import VideoProcessor
from .ui_detector import UIDetector
from .ocr_engine import OCREngine
from .deduplicator import Deduplicator
from .post_processor import PostProcessor

logger = logging.getLogger(__name__)


class WhatsAppVideoExtractor:
    def __init__(self, sample_interval_sec: float = 2.0, similarity_threshold: float = 80.0,
                 crop_config: Optional[Dict[str, int]] = None,
                 gap_ratio: float = 0.75, left_align_threshold: float = 0.15):
        self.sample_interval_sec = sample_interval_sec
        self.similarity_threshold = similarity_threshold
        self.crop_config = crop_config
        # Quão grande precisa ser o espaço vertical (em relação à altura da linha)
        # para considerar que começou outra mensagem.
        self.gap_ratio = gap_ratio
        # Fração da largura abaixo da qual a linha "começa colada na esquerda"
        # (mensagem recebida = USER_1). Balões enviados são alinhados à direita
        # e nunca começam tão à esquerda, mesmo sendo longos.
        self.left_align_threshold = left_align_threshold

        self.ui_detector = UIDetector(crop_config=self.crop_config)
        self.ocr_engine = OCREngine(lang="pt")
        self.deduplicator = Deduplicator(similarity_threshold=self.similarity_threshold)
        self.post_processor = PostProcessor()

    def _group_messages(self, lines: List[Dict[str, Any]], frame_width: int, frame_idx: int) -> List[Dict[str, Any]]:
        """
        Separa as mensagens dentro de um frame.

        Estratégia (sem usar cor):
          1. Agrupa linhas próximas verticalmente (mesmo balão), quebrando
             quando o espaço é grande OU quando o lado muda claramente
             (esquerda <-> direita = autor diferente).
          2. O AUTOR é decidido pela linha MAIS LARGA do balão (que melhor
             mostra o alinhamento), comparada ao centro REAL da conversa
             (corrigido pelo corte assimétrico). Linhas curtas que quebram
             dentro de um balão largo (ex: "nada em casa") não atrapalham.
        """
        if not lines:
            return []

        lines.sort(key=lambda l: l["top"])

        heights = sorted(ln["bottom"] - ln["top"] for ln in lines)
        median_h = heights[len(heights) // 2] if heights else 20
        gap_threshold = max(median_h * self.gap_ratio, 8)

        def side(ln):
            # Lado pela borda esquerda: recebido cola na esquerda, enviado não.
            return "L" if (ln["left"] / float(frame_width)) < self.left_align_threshold else "R"

        groups: List[List[Dict[str, Any]]] = []
        cur: List[Dict[str, Any]] = []

        for ln in lines:
            if not cur:
                cur = [ln]
                continue
            gap = ln["top"] - cur[-1]["bottom"]
            flip = side(cur[-1]) != side(ln)
            if gap > gap_threshold or flip:
                groups.append(cur)
                cur = [ln]
            else:
                cur.append(ln)
        if cur:
            groups.append(cur)

        messages = []
        for g in groups:
            # Autor pela borda ESQUERDA da linha mais larga do balão.
            # Mensagens recebidas começam coladas na esquerda; enviadas (à
            # direita) nunca começam tão à esquerda, mesmo sendo longas.
            # Usar a linha mais larga ignora fragmentos soltos (ex: "t", "MaeC").
            widest = max(g, key=lambda l: l["right"] - l["left"])
            left_rel = widest["left"] / float(frame_width)
            author = "USER_1" if left_rel < self.left_align_threshold else "USER_2"

            text = " ".join(l["text"] for l in g).strip()
            if text:
                messages.append({"author": author, "text": text, "y": g[0]["top"], "frame": frame_idx})

        return messages

    def extract(self, video_path: str, json_out_path: str, txt_out_path: str, progress_callback=None) -> Tuple[bool, str]:
        """
        Executa todo o pipeline de extração e salva os resultados em arquivos.
        Retorna (sucesso, mensagem_de_erro_ou_vazio)
        """
        logger.info(f"Iniciando extração do vídeo: {video_path}")

        try:
            processor = VideoProcessor(video_path, sample_interval_sec=self.sample_interval_sec)
            estimated_frames = processor.total_frames / processor.frame_interval if processor.frame_interval > 0 else 1
        except Exception as e:
            return False, str(e)

        all_raw_messages = []
        frames_processed = 0

        try:
            for frame_idx, frame in processor.extract_frames():
                # 1. Recortar bordas inúteis (header do app, barra de comentários, botões)
                cropped_frame = self.ui_detector.crop_frame(frame)

                # 2. OCR no frame inteiro -> linhas com posição
                lines = self.ocr_engine.extract_lines(cropped_frame)

                # 3. Separar em mensagens por alinhamento + espaçamento vertical
                frame_width = cropped_frame.shape[1]
                msgs = self._group_messages(lines, frame_width, frame_idx)
                all_raw_messages.extend(msgs)

                frames_processed += 1
                if progress_callback and frames_processed % 3 == 0:
                    pct = min(1.0, frames_processed / estimated_frames)
                    curr_prog = 30.0 + (pct * 50.0)
                    progress_callback(curr_prog, f"Analisando quadro {frames_processed}...")

        except Exception as e:
            logger.error(f"Erro processando os frames: {e}", exc_info=True)
            return False, f"Erro processando os frames: {str(e)}"
        finally:
            processor.release()

        logger.info(f"Processamento finalizado. Mensagens detectadas (com duplicadas): {len(all_raw_messages)}")

        # 4. Remover duplicatas causadas pelo scroll ou frames idênticos
        unique_messages = self.deduplicator.remove_duplicates(all_raw_messages)
        logger.info(f"Duplicatas removidas. Mensagens exclusivas: {len(unique_messages)}")

        # 5. Aplicar formatação final e pequenos ajustes no texto
        final_convo = self.post_processor.finalize_conversation(unique_messages)

        # 6. Salvar em JSON e TXT
        try:
            with open(json_out_path, 'w', encoding='utf-8') as f:
                json.dump(final_convo, f, indent=2, ensure_ascii=False)

            with open(txt_out_path, 'w', encoding='utf-8') as f:
                for msg in final_convo:
                    f.write(f"{msg['author']}: {msg['texto']}\n")

            logger.info(f"Extração salva com sucesso em {json_out_path} e {txt_out_path}")
            return True, ""
        except Exception as e:
            logger.error(f"Erro salvando saída: {e}", exc_info=True)
            return False, f"Erro ao salvar arquivos: {str(e)}"
