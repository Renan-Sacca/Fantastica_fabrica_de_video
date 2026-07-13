"""Renderer do tipo 'video_compositor' — composição visual por camadas (v2).

Suporta:
1. Múltiplos áudios principais, concatenados em sequência (com corte/trim e
   volume individuais) — define a duração total do vídeo.
2. Múltiplas imagens de fundo, cada uma visível em uma janela de tempo
   [start_sec, end_sec) — troca de fundo ao longo do vídeo.
3. Múltiplas imagens sobrepostas, cada uma visível em sua própria janela de
   tempo, com posição/tamanho por percentual OU controle fino em pixels.
4. Elementos decorativos e animações via filtros FFmpeg (aplicados sobre
   todo o vídeo).
5. Áudio secundário (música de fundo) com volume independente, em loop.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Callable, Optional

from renderers.base import BaseRenderer

logger = logging.getLogger("VideoCompositorRenderer")


# Mapeamento de posições para coordenadas overlay do FFmpeg
# Usamos expressões FFmpeg com W,H (output), w,h (overlay) — resolvidas em tempo de filtro.
POSITION_MAP = {
    "centro":            "(W-w)/2:(H-h)/2",
    "superior":          "(W-w)/2:H*0.05",
    "inferior":          "(W-w)/2:H*0.95-h",
    "esquerda":          "W*0.05:(H-h)/2",
    "direita":           "W*0.95-w:(H-h)/2",
    "superior esquerda": "W*0.05:H*0.05",
    "superior direita":  "W*0.95-w:H*0.05",
    "inferior esquerda": "W*0.05:H*0.95-h",
    "inferior direita":  "W*0.95-w:H*0.95-h",
}


class VideoCompositorRenderer(BaseRenderer):
    """Renderer para vídeo compositor com camadas, múltiplos áudios e imagens por tempo."""

    @property
    def video_type(self) -> str:
        return "video_compositor"

    def render(
        self,
        job_data: dict,
        work_dir: Path,
        progress_callback: Optional[Callable] = None,
    ) -> Path:
        def _progress(status, pct, detail):
            if progress_callback:
                progress_callback(status=status, progress=pct, detail=detail)

        _progress("rendering", 50, "Preparando composição...")

        # ── Extrair parâmetros ──
        resolution = job_data.get("resolution", {"width": 1080, "height": 1920})
        res_w = resolution.get("width", 1080)
        res_h = resolution.get("height", 1920)
        files_info = job_data.get("files", {})

        audio_items = sorted(job_data.get("audio_items", []), key=lambda x: x.get("index", 0))
        bg_segments = job_data.get("bg_segments", [])
        overlay_segments = job_data.get("overlay_segments", [])

        if not audio_items:
            raise ValueError("Nenhum áudio principal configurado.")
        if not bg_segments:
            raise ValueError("Nenhuma imagem de fundo configurada.")

        sec_audio_ext = files_info.get("secondary_audio_ext", ".mp3")
        sec_audio_path = work_dir / f"secondary_audio{sec_audio_ext}"
        has_sec_audio = sec_audio_path.exists()

        sec_volume = float(job_data.get("secondary_audio_volume", 20)) / 100.0
        animations = job_data.get("animations", [])
        elements = job_data.get("elements", [])

        # ── 1. Resolver caminhos e durações dos áudios (com corte aplicado) ──
        _progress("rendering", 52, "Analisando áudios...")
        audio_tracks = self._resolve_audio_tracks(audio_items, work_dir)
        total_duration = sum(t["duration"] for t in audio_tracks)
        if total_duration <= 0:
            raise ValueError("Duração total dos áudios é zero — verifique os arquivos/corte.")
        logger.info(f"Duração total do vídeo (áudios concatenados): {total_duration:.2f}s")

        # ── 2. Resolver janelas de tempo das imagens de fundo (preenche lacunas) ──
        bg_clips = self._resolve_bg_clips(bg_segments, work_dir, total_duration)
        if not bg_clips:
            raise ValueError("Nenhuma imagem de fundo válida encontrada.")

        # ── 3. Resolver janelas de tempo das imagens sobrepostas ──
        overlay_clips = self._resolve_overlay_clips(overlay_segments, work_dir, total_duration)

        # ── 4. Compor o vídeo final ──
        _progress("composing", 55, "Compondo vídeo com camadas...")
        output_path = work_dir / "output.mp4"

        self._compose_video(
            output_path=output_path,
            res_w=res_w,
            res_h=res_h,
            duration=total_duration,
            audio_tracks=audio_tracks,
            bg_clips=bg_clips,
            overlay_clips=overlay_clips,
            sec_audio_path=sec_audio_path if has_sec_audio else None,
            sec_volume=sec_volume,
            animations=animations,
            elements=elements,
            progress_fn=_progress,
        )

        # ── 5. Gerar thumbnail ──
        _progress("composing", 90, "Gerando thumbnail...")
        thumbnail_path = work_dir / "thumbnail.jpg"
        self._generate_thumbnail(output_path, thumbnail_path)

        _progress("composing", 95, "Vídeo renderizado com sucesso!")
        return output_path

    # ══════════════════════════════════════════
    # Resolução de arquivos e durações
    # ══════════════════════════════════════════

    def _find_file(self, work_dir: Path, stem: str, hint_ext: Optional[str] = None) -> Optional[Path]:
        """Encontra um arquivo `stem.<ext>` em work_dir, tentando a extensão sugerida primeiro."""
        if hint_ext:
            candidate = work_dir / f"{stem}{hint_ext}"
            if candidate.exists():
                return candidate
        matches = sorted(work_dir.glob(f"{stem}.*"))
        return matches[0] if matches else None

    def _resolve_audio_tracks(self, audio_items: list, work_dir: Path) -> list[dict]:
        """Localiza cada arquivo de áudio, aplica corte e calcula a duração efetiva.

        Retorna lista ordenada (mesma ordem de `audio_items`) de:
        {"path": Path, "volume": float(0..1), "trim_start": float, "trim_end": float|None, "duration": float}
        """
        tracks = []
        for item in audio_items:
            idx = item.get("index", 0)
            ext = item.get("file_ext")
            path = self._find_file(work_dir, f"audio_{idx}", ext)
            if not path:
                raise FileNotFoundError(f"Áudio {idx+1}: arquivo não encontrado em {work_dir}")

            raw_duration = self._get_duration(path)
            trim_start = max(0.0, float(item.get("trim_start") or 0.0))
            trim_end_raw = item.get("trim_end")
            trim_end = min(raw_duration, float(trim_end_raw)) if trim_end_raw is not None else raw_duration
            effective_duration = max(0.0, trim_end - trim_start)

            volume = max(0.0, float(item.get("volume", 100)) / 100.0)

            tracks.append({
                "path": path,
                "volume": volume,
                "trim_start": trim_start,
                "trim_end": trim_end if trim_end_raw is not None else None,
                "raw_duration": raw_duration,
                "duration": effective_duration,
            })
        return tracks

    def _resolve_bg_clips(self, bg_segments: list, work_dir: Path, total_duration: float) -> list[dict]:
        """Calcula a janela [start, end) de cada imagem de fundo, preenchendo lacunas.

        A primeira imagem sempre cobre a partir de t=0. Se `end_sec` não for
        informado, usa o início da próxima imagem (ordenadas por start_sec) ou
        o fim do vídeo. Lacunas entre imagens são preenchidas estendendo a
        imagem anterior.
        """
        segs_sorted = sorted(bg_segments, key=lambda s: s.get("start_sec", 0) or 0)
        clips = []
        cursor = 0.0

        for i, seg in enumerate(segs_sorted):
            idx = seg.get("index", 0)
            ext = seg.get("file_ext")
            path = self._find_file(work_dir, f"bg_image_{idx}", ext)
            if not path:
                logger.warning(f"Imagem de fundo {idx+1}: arquivo não encontrado, ignorando.")
                continue

            end_sec = seg.get("end_sec")
            if end_sec is None:
                end_sec = segs_sorted[i + 1].get("start_sec", total_duration) if i + 1 < len(segs_sorted) else total_duration
            end_sec = min(float(end_sec), total_duration)

            if end_sec <= cursor:
                continue  # segmento totalmente fora da timeline útil

            clips.append({"path": path, "start": cursor, "end": end_sec})
            cursor = end_sec

        # Se restou tempo sem cobertura no final, estende o último clipe
        if clips and cursor < total_duration:
            clips[-1]["end"] = total_duration
        elif not clips:
            return []

        return clips

    def _resolve_overlay_clips(self, overlay_segments: list, work_dir: Path, total_duration: float) -> list[dict]:
        """Calcula a janela [start, end) de cada imagem sobreposta (sem preencher lacunas —
        overlays podem ter períodos sem nenhuma imagem visível)."""
        clips = []
        for seg in sorted(overlay_segments, key=lambda s: s.get("start_sec", 0) or 0):
            idx = seg.get("index", 0)
            ext = seg.get("file_ext")
            path = self._find_file(work_dir, f"overlay_image_{idx}", ext)
            if not path:
                logger.warning(f"Imagem sobreposta {idx+1}: arquivo não encontrado, ignorando.")
                continue

            start = max(0.0, float(seg.get("start_sec", 0) or 0))
            end_raw = seg.get("end_sec")
            end = min(float(end_raw), total_duration) if end_raw is not None else total_duration
            if end <= start:
                continue

            clips.append({
                "path": path,
                "start": start,
                "end": end,
                "position": seg.get("position", "centro"),
                "scale": float(seg.get("scale", 50)),
                "px_width": seg.get("px_width"),
                "px_height": seg.get("px_height"),
                "px_x": seg.get("px_x"),
                "px_y": seg.get("px_y"),
            })
        return clips

    def _get_duration(self, file_path: Path) -> float:
        """Obtém a duração de um arquivo de mídia via ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(file_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe falhou: {result.stderr}")
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
