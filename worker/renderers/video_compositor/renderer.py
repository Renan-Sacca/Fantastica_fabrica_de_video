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

    # ══════════════════════════════════════════
    # Composição principal via FFmpeg
    # ══════════════════════════════════════════

    def _compose_video(
        self,
        output_path: Path,
        res_w: int,
        res_h: int,
        duration: float,
        audio_tracks: list,
        bg_clips: list,
        overlay_clips: list,
        sec_audio_path: Optional[Path] = None,
        sec_volume: float = 0.2,
        animations: list = None,
        elements: list = None,
        progress_fn: Optional[Callable] = None,
    ):
        """Compõe o vídeo final em uma única passagem de FFmpeg.

        - Fundo: cada imagem de fundo entra como um clipe estático de duração
          igual à sua janela de tempo; os clipes são concatenados em sequência
          para formar o vídeo de base com a duração total.
        - Sobreposta: cada imagem overlay é adicionada com `enable=between(t,
          start,end)` para aparecer apenas em sua própria janela.
        - Áudio: cada faixa é recortada (trim) e tem seu volume aplicado, depois
          todas são concatenadas para formar o áudio principal.
        """
        inputs = ["-y"]
        fc_parts = []
        input_idx = 0
        fps = 30

        # ── Inputs + filtros de fundo (um por clipe) ──
        bg_labels = []
        for clip in bg_clips:
            clip_duration = max(0.05, clip["end"] - clip["start"])
            inputs += [
                "-loop", "1", "-framerate", str(fps),
                "-t", f"{clip_duration:.3f}",
                "-i", str(clip["path"]),
            ]
            label = f"bgsrc{input_idx}"
            fc_parts.append(
                f"[{input_idx}:v]scale={res_w}:{res_h}:force_original_aspect_ratio=increase,"
                f"crop={res_w}:{res_h},setsar=1,format=yuv420p,fps={fps}[{label}]"
            )
            bg_labels.append(label)
            input_idx += 1

        if len(bg_labels) > 1:
            concat_in = "".join(f"[{lbl}]" for lbl in bg_labels)
            fc_parts.append(f"{concat_in}concat=n={len(bg_labels)}:v=1:a=0[bgall]")
            cur_video = "bgall"
        else:
            cur_video = bg_labels[0]

        # ── Inputs de áudio principais (na ordem de concatenação) ──
        audio_labels = []
        for i, track in enumerate(audio_tracks):
            inputs += ["-i", str(track["path"])]
            trim_args = f"start={track['trim_start']:.3f}"
            if track["trim_end"] is not None:
                trim_args += f":end={track['trim_end']:.3f}"
            label = f"aud{i}"
            fc_parts.append(
                f"[{input_idx}:a]atrim={trim_args},asetpts=PTS-STARTPTS,"
                f"volume={track['volume']:.3f}[{label}]"
            )
            audio_labels.append(label)
            input_idx += 1

        if len(audio_labels) > 1:
            concat_a_in = "".join(f"[{lbl}]" for lbl in audio_labels)
            fc_parts.append(f"{concat_a_in}concat=n={len(audio_labels)}:v=0:a=1[amain]")
        else:
            fc_parts.append(f"[{audio_labels[0]}]anull[amain]")
        audio_label = "amain"

        # ── Elementos decorativos sobre o fundo concatenado ──
        if elements:
            cur_video = self._apply_elements(fc_parts, cur_video, elements, res_w, res_h)

        # ── Imagens sobrepostas, cada uma na sua janela de tempo ──
        if overlay_clips:
            if progress_fn:
                progress_fn("composing", 65, "Adicionando imagens sobrepostas...")
            for i, clip in enumerate(overlay_clips):
                # -loop 1 faz a imagem estática virar um "vídeo" contínuo,
                # necessário pois o enable=between(...) cobre vários segundos.
                inputs += ["-loop", "1", "-framerate", str(fps), "-i", str(clip["path"])]
                ov_in_idx = input_idx
                input_idx += 1

                ov_label = f"ov{i}"
                px_w = clip.get("px_width")
                px_h = clip.get("px_height")
                if px_w or px_h:
                    scale_expr = f"{int(px_w) if px_w else -1}:{int(px_h) if px_h else -1}"
                else:
                    ov_w = max(1, int(res_w * clip["scale"] / 100))
                    scale_expr = f"{ov_w}:-1"
                fc_parts.append(f"[{ov_in_idx}:v]scale={scale_expr},format=rgba[{ov_label}]")

                px_x = clip.get("px_x")
                px_y = clip.get("px_y")
                if px_x is not None and px_y is not None:
                    pos_expr = f"{int(px_x)}:{int(px_y)}"
                else:
                    pos_expr = POSITION_MAP.get(clip["position"], POSITION_MAP["centro"])

                out_label = f"vov{i}"
                enable_expr = f"between(t,{clip['start']:.3f},{clip['end']:.3f})"
                fc_parts.append(
                    f"[{cur_video}][{ov_label}]overlay={pos_expr}:"
                    f"enable='{enable_expr}':format=auto[{out_label}]"
                )
                cur_video = out_label

        # ── Animações sobre o vídeo final ──
        if animations:
            if progress_fn:
                progress_fn("composing", 72, "Aplicando animações...")
            cur_video = self._apply_animations(fc_parts, cur_video, animations, res_w, res_h, duration)

        # ── Áudio secundário (música de fundo em loop) ──
        if sec_audio_path is not None:
            if progress_fn:
                progress_fn("composing", 78, "Mixando áudios...")
            inputs += ["-stream_loop", "-1", "-i", str(sec_audio_path)]
            sec_idx = input_idx
            input_idx += 1
            fc_parts.append(f"[{sec_idx}:a]volume={sec_volume:.2f}[asec]")
            fc_parts.append(
                f"[{audio_label}][asec]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            audio_label = "aout"

        filter_complex = ";".join(fc_parts)

        cmd = [
            "ffmpeg", *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{cur_video}]",
            "-map", f"[{audio_label}]",
            "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{duration:.3f}",
            "-movflags", "+faststart",
            str(output_path),
        ]

        if progress_fn:
            progress_fn("composing", 80, "Codificando vídeo final...")

        logger.info(
            f"Compondo vídeo compositor ({res_w}x{res_h}, {duration:.1f}s, "
            f"{len(bg_clips)} fundo(s), {len(overlay_clips)} overlay(s), "
            f"{len(audio_tracks)} áudio(s))..."
        )
        timeout = max(1800, int(duration * 10))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.error(f"FFmpeg stderr: {result.stderr[-1200:]}")
            raise RuntimeError(f"ffmpeg falhou ao compor vídeo: {result.stderr[-800:]}")

        logger.info(
            f"Vídeo compositor gerado: {output_path} "
            f"({output_path.stat().st_size / 1024 / 1024:.1f} MB)"
        )

    # ══════════════════════════════════════════
    # Elementos decorativos
    # ══════════════════════════════════════════

    def _apply_elements(
        self, fc_parts: list, cur_video: str,
        elements: list, res_w: int, res_h: int,
    ) -> str:
        """Aplica elementos decorativos via filtros FFmpeg."""
        elem_idx = 0

        for elem in elements:
            out_label = f"velem{elem_idx}"

            if elem == "sombra_vinheta":
                fc_parts.append(f"[{cur_video}]vignette=PI/4[{out_label}]")
                cur_video = out_label
                elem_idx += 1

            elif elem == "sombra_radial":
                fc_parts.append(
                    f"[{cur_video}]vignette=PI/3:max_radius={res_w//3}[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "gradiente_top":
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y=0:w={res_w}:h={res_h//4}:"
                    f"color=black@0.4:t=fill[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "gradiente_bottom":
                y_start = res_h - res_h // 4
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y={y_start}:w={res_w}:h={res_h//4}:"
                    f"color=black@0.4:t=fill[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "moldura_gold":
                border = 6
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y=0:w={res_w}:h={border}:color=0xFFD700@0.8:t=fill,"
                    f"drawbox=x=0:y={res_h - border}:w={res_w}:h={border}:color=0xFFD700@0.8:t=fill,"
                    f"drawbox=x=0:y=0:w={border}:h={res_h}:color=0xFFD700@0.8:t=fill,"
                    f"drawbox=x={res_w - border}:y=0:w={border}:h={res_h}:color=0xFFD700@0.8:t=fill"
                    f"[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "moldura_neon":
                border = 4
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y=0:w={res_w}:h={border}:color=0xE040FB@0.9:t=fill,"
                    f"drawbox=x=0:y={res_h - border}:w={res_w}:h={border}:color=0xE040FB@0.9:t=fill,"
                    f"drawbox=x=0:y=0:w={border}:h={res_h}:color=0xE040FB@0.9:t=fill,"
                    f"drawbox=x={res_w - border}:y=0:w={border}:h={res_h}:color=0xE040FB@0.9:t=fill"
                    f"[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "barra_inferior":
                bar_h = res_h // 8
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y={res_h - bar_h}:w={res_w}:h={bar_h}:"
                    f"color=black@0.6:t=fill[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "caixa_texto":
                box_w = int(res_w * 0.8)
                box_h = res_h // 6
                box_x = (res_w - box_w) // 2
                box_y = res_h // 2 - box_h // 2
                fc_parts.append(
                    f"[{cur_video}]drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:"
                    f"color=black@0.5:t=fill[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

        return cur_video

    # ══════════════════════════════════════════
    # Animações
    # ══════════════════════════════════════════

    def _apply_animations(
        self, fc_parts: list, cur_video: str,
        animations: list, res_w: int, res_h: int, duration: float,
    ) -> str:
        """Aplica animações via filtros FFmpeg (simuladas com filtros nativos)."""
        anim_idx = 0

        for anim in animations:
            out_label = f"vanim{anim_idx}"

            if anim == "brilho":
                fc_parts.append(
                    f"[{cur_video}]eq=brightness=0.03:saturation=1.1[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "particulas":
                fc_parts.append(
                    f"[{cur_video}]noise=alls=8:allf=t+u[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "neve":
                fc_parts.append(f"[{cur_video}]noise=alls=15:allf=t[{out_label}]")
                cur_video = out_label
                anim_idx += 1

            elif anim == "fogo":
                fc_parts.append(
                    f"[{cur_video}]colorbalance=rs=0.15:gs=-0.05:bs=-0.15,"
                    f"eq=brightness=0.02:saturation=1.3[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "chuva":
                fc_parts.append(
                    f"[{cur_video}]noise=alls=12:allf=t,"
                    f"eq=brightness=-0.03:contrast=1.05[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "fumaca":
                fc_parts.append(
                    f"[{cur_video}]gblur=sigma=1.5,"
                    f"eq=brightness=0.05:contrast=0.95[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "luz":
                fc_parts.append(f"[{cur_video}]eq=brightness=0.06:gamma=1.1[{out_label}]")
                cur_video = out_label
                anim_idx += 1

            elif anim == "faiscas":
                fc_parts.append(
                    f"[{cur_video}]noise=alls=20:allf=t+u,"
                    f"eq=saturation=1.2[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "explosao":
                fc_parts.append(
                    f"[{cur_video}]eq=brightness=0.08:saturation=1.4:contrast=1.1[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "loop_bg":
                fc_parts.append(
                    f"[{cur_video}]zoompan=z='min(zoom+0.0005,1.15)':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={int(duration*25)}:s={res_w}x{res_h}:fps=25[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

        return cur_video

    # ══════════════════════════════════════════
    # Thumbnail
    # ══════════════════════════════════════════

    def _generate_thumbnail(self, video_path: Path, thumbnail_path: Path):
        """Gera thumbnail do primeiro frame do vídeo."""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(thumbnail_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"Falha ao gerar thumbnail: {result.stderr[-300:]}")
        else:
            logger.info(f"Thumbnail gerada: {thumbnail_path}")
