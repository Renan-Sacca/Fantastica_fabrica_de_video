"""Renderer do tipo 'video_compositor' — composição visual por camadas.

Usa FFmpeg para:
1. Escalar imagem de fundo para a resolução alvo
2. Sobrepor imagem overlay na posição configurada
3. Aplicar efeitos visuais (vinheta, gradientes, molduras)
4. Gerar animações via filtros FFmpeg (partículas, brilho, etc.)
5. Mixar áudio principal + secundário com volumes independentes
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
# Usamos expressões FFmpeg com W,H (output), w,h (overlay)
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
    """Renderer para vídeo compositor com camadas."""

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

        _progress("rendering", 5, "Preparando composição...")

        # ── Extrair parâmetros ──
        resolution = job_data.get("resolution", {"width": 1080, "height": 1920})
        res_w = resolution.get("width", 1080)
        res_h = resolution.get("height", 1920)
        files_info = job_data.get("files", {})

        bg_ext = files_info.get("bg_image_ext", ".png")
        bg_path = work_dir / f"bg_image{bg_ext}"

        audio_ext = files_info.get("audio_ext", ".mp3")
        audio_path = work_dir / f"audio{audio_ext}"

        overlay_ext = files_info.get("overlay_image_ext", ".png")
        overlay_path = work_dir / f"overlay_image{overlay_ext}"
        has_overlay = overlay_path.exists()

        sec_audio_ext = files_info.get("secondary_audio_ext", ".mp3")
        sec_audio_path = work_dir / f"secondary_audio{sec_audio_ext}"
        has_sec_audio = sec_audio_path.exists()

        overlay_position = job_data.get("overlay_position", "centro")
        overlay_scale_pct = float(job_data.get("overlay_scale", 50))
        sec_volume = float(job_data.get("secondary_audio_volume", 20)) / 100.0

        animations = job_data.get("animations", [])
        elements = job_data.get("elements", [])

        if not bg_path.exists():
            raise FileNotFoundError(f"Imagem de fundo não encontrada: {bg_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

        # ── 1. Obter duração do áudio ──
        _progress("rendering", 10, "Analisando duração do áudio...")
        audio_duration = self._get_duration(audio_path)
        logger.info(f"Duração do áudio principal: {audio_duration:.2f}s")

        # ── 2. Compor o vídeo final ──
        _progress("composing", 20, "Compondo vídeo com camadas...")
        output_path = work_dir / "output.mp4"

        self._compose_video(
            bg_path=bg_path,
            audio_path=audio_path,
            output_path=output_path,
            res_w=res_w,
            res_h=res_h,
            duration=audio_duration,
            overlay_path=overlay_path if has_overlay else None,
            overlay_position=overlay_position,
            overlay_scale_pct=overlay_scale_pct,
            sec_audio_path=sec_audio_path if has_sec_audio else None,
            sec_volume=sec_volume,
            animations=animations,
            elements=elements,
            progress_fn=_progress,
        )

        # ── 3. Gerar thumbnail ──
        _progress("composing", 90, "Gerando thumbnail...")
        thumbnail_path = work_dir / "thumbnail.jpg"
        self._generate_thumbnail(output_path, thumbnail_path)

        _progress("composing", 95, "Vídeo renderizado com sucesso!")
        return output_path

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

    def _compose_video(
        self,
        bg_path: Path,
        audio_path: Path,
        output_path: Path,
        res_w: int,
        res_h: int,
        duration: float,
        overlay_path: Optional[Path] = None,
        overlay_position: str = "centro",
        overlay_scale_pct: float = 50.0,
        sec_audio_path: Optional[Path] = None,
        sec_volume: float = 0.2,
        animations: list = None,
        elements: list = None,
        progress_fn: Optional[Callable] = None,
    ):
        """Compõe o vídeo final usando FFmpeg em uma única passagem.

        Estratégia:
        - Converte a imagem de fundo em um "vídeo" estático com a duração do áudio
        - Sobrepõe overlay se existir, na posição configurada
        - Aplica filtros visuais para animações/elementos
        - Mixa áudios com volumes independentes
        """
        inputs = ["-y"]

        # Input 0: imagem de fundo como vídeo (loop pela duração do áudio)
        inputs += [
            "-loop", "1",
            "-t", str(duration),
            "-i", str(bg_path),
        ]

        # Input 1: áudio principal
        inputs += ["-i", str(audio_path)]

        # Input 2 (opcional): overlay
        input_idx = 2
        overlay_input = None
        if overlay_path and overlay_path.exists():
            inputs += ["-i", str(overlay_path)]
            overlay_input = input_idx
            input_idx += 1

        # Input N (opcional): áudio secundário
        sec_audio_input = None
        if sec_audio_path and sec_audio_path.exists():
            inputs += ["-stream_loop", "-1", "-i", str(sec_audio_path)]
            sec_audio_input = input_idx
            input_idx += 1

        # ── Construir filtro complexo ──
        fc_parts = []

        # Escalar fundo para resolução alvo
        fc_parts.append(
            f"[0:v]scale={res_w}:{res_h}:force_original_aspect_ratio=increase,"
            f"crop={res_w}:{res_h},setsar=1,format=yuv420p[bg]"
        )
        cur_video = "bg"

        # Aplicar elementos visuais (vinheta, gradientes)
        if elements:
            cur_video = self._apply_elements(fc_parts, cur_video, elements, res_w, res_h)

        # Overlay da imagem sobreposta
        if overlay_input is not None:
            if progress_fn:
                progress_fn("composing", 40, "Adicionando imagem sobreposta...")

            # Calcular escala do overlay
            overlay_w = int(res_w * overlay_scale_pct / 100)
            pos_expr = POSITION_MAP.get(overlay_position, POSITION_MAP["centro"])

            fc_parts.append(
                f"[{overlay_input}:v]scale={overlay_w}:-1,format=rgba[ov]"
            )
            fc_parts.append(
                f"[{cur_video}][ov]overlay={pos_expr}:format=auto[vov]"
            )
            cur_video = "vov"

        # Aplicar animações via filtros FFmpeg
        if animations:
            if progress_fn:
                progress_fn("composing", 55, "Aplicando animações...")
            cur_video = self._apply_animations(fc_parts, cur_video, animations, res_w, res_h, duration)

        # ── Áudio ──
        audio_filter = None
        if sec_audio_input is not None:
            if progress_fn:
                progress_fn("composing", 70, "Mixando áudios...")
            # Mixar áudio principal (volume 1.0) + secundário (volume configurado)
            fc_parts.append(
                f"[1:a]volume=1.0[amain]"
            )
            fc_parts.append(
                f"[{sec_audio_input}:a]volume={sec_volume:.2f}[asec]"
            )
            fc_parts.append(
                f"[amain][asec]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            audio_filter = "aout"

        filter_complex = ";".join(fc_parts)

        # ── Montar comando ffmpeg ──
        cmd = [
            "ffmpeg", *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{cur_video}]",
        ]

        if audio_filter:
            cmd += ["-map", f"[{audio_filter}]"]
        else:
            cmd += ["-map", "1:a:0"]

        cmd += [
            "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration),
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]

        if progress_fn:
            progress_fn("composing", 75, "Codificando vídeo final...")

        logger.info(f"Compondo vídeo compositor ({res_w}x{res_h}, {duration:.0f}s)...")
        timeout = max(1800, int(duration * 10))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.error(f"FFmpeg stderr: {result.stderr[-800:]}")
            raise RuntimeError(f"ffmpeg falhou ao compor vídeo: {result.stderr[-600:]}")

        logger.info(
            f"Vídeo compositor gerado: {output_path} "
            f"({output_path.stat().st_size / 1024 / 1024:.1f} MB)"
        )

    def _apply_elements(
        self, fc_parts: list, cur_video: str,
        elements: list, res_w: int, res_h: int,
    ) -> str:
        """Aplica elementos decorativos via filtros FFmpeg."""
        elem_idx = 0

        for elem in elements:
            out_label = f"velem{elem_idx}"

            if elem == "sombra_vinheta":
                # Efeito vinheta — escurece as bordas
                fc_parts.append(
                    f"[{cur_video}]vignette=PI/4[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "sombra_radial":
                # Vinheta mais suave
                fc_parts.append(
                    f"[{cur_video}]vignette=PI/3:max_radius={res_w//3}[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "gradiente_top":
                # Gradiente escuro no topo (drawbox com transparência)
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y=0:w={res_w}:h={res_h//4}:"
                    f"color=black@0.4:t=fill[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "gradiente_bottom":
                # Gradiente escuro na parte inferior
                y_start = res_h - res_h // 4
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y={y_start}:w={res_w}:h={res_h//4}:"
                    f"color=black@0.4:t=fill[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "moldura_gold":
                # Borda dourada fina
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
                # Borda neon roxa
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
                # Barra escura na parte inferior para texto
                bar_h = res_h // 8
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y={res_h - bar_h}:w={res_w}:h={bar_h}:"
                    f"color=black@0.6:t=fill[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem == "caixa_texto":
                # Caixa de texto centralizada semi-transparente
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

    def _apply_animations(
        self, fc_parts: list, cur_video: str,
        animations: list, res_w: int, res_h: int, duration: float,
    ) -> str:
        """Aplica animações via filtros FFmpeg (simuladas com filtros nativos)."""
        anim_idx = 0

        for anim in animations:
            out_label = f"vanim{anim_idx}"

            if anim == "brilho":
                # Pulso de brilho sutil (eq com oscilação)
                fc_parts.append(
                    f"[{cur_video}]eq=brightness=0.03:saturation=1.1[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "particulas":
                # Simular partículas com noise overlay sutil
                fc_parts.append(
                    f"[{cur_video}]noise=alls=8:allf=t+u[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "neve":
                # Simulação de neve com noise + threshold
                fc_parts.append(
                    f"[{cur_video}]noise=alls=15:allf=t[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "fogo":
                # Simular efeito quente — ajuste de cor
                fc_parts.append(
                    f"[{cur_video}]colorbalance=rs=0.15:gs=-0.05:bs=-0.15,"
                    f"eq=brightness=0.02:saturation=1.3[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "chuva":
                # Simular chuva com noise + blur direcional leve
                fc_parts.append(
                    f"[{cur_video}]noise=alls=12:allf=t,"
                    f"eq=brightness=-0.03:contrast=1.05[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "fumaca":
                # Efeito de neblina — blur leve + brilho
                fc_parts.append(
                    f"[{cur_video}]gblur=sigma=1.5,"
                    f"eq=brightness=0.05:contrast=0.95[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "luz":
                # Efeito de luz — brilho pulsante usando eq
                fc_parts.append(
                    f"[{cur_video}]eq=brightness=0.06:gamma=1.1[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "faiscas":
                # Faíscas — noise colorido mais forte
                fc_parts.append(
                    f"[{cur_video}]noise=alls=20:allf=t+u,"
                    f"eq=saturation=1.2[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "explosao":
                # Efeito de explosão leve — saturação + brilho
                fc_parts.append(
                    f"[{cur_video}]eq=brightness=0.08:saturation=1.4:contrast=1.1[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim == "loop_bg":
                # Loop de fundo — não faz nada extra (o fundo já é loop)
                # Mas vamos adicionar um leve zoom lento (ken burns)
                fc_parts.append(
                    f"[{cur_video}]zoompan=z='min(zoom+0.0005,1.15)':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={int(duration*25)}:s={res_w}x{res_h}:fps=25[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

        return cur_video

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
