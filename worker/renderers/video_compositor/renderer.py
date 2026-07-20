"""Renderer do tipo 'video_compositor' — composição visual por camadas (v3).

Suporta:
1. Múltiplos áudios principais, concatenados em sequência (com corte/trim e
   volume individuais) — define a duração total do vídeo.
2. Múltiplas imagens de fundo, cada uma visível em uma janela de tempo
   [start_sec, end_sec) — troca de fundo ao longo do vídeo.
3. Múltiplas imagens sobrepostas, cada uma visível em sua própria janela de
   tempo, com posição/tamanho por percentual OU controle fino em pixels.
4. Elementos decorativos com controle de intervalo de tempo (enable=between).
5. Animações via filtros FFmpeg com controle de intensidade e intervalo de
   tempo (enable=between).
6. Animações customizadas (upload de vídeo/GIF) como overlays animados,
   com posição, escala, tempo e opção de loop.
7. Áudio secundário (música de fundo) com volume independente, em loop.
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

        secondary_audios = job_data.get("secondary_audios", [])
        text_overlays = job_data.get("text_overlays", [])
        animations = job_data.get("animations", [])
        elements = job_data.get("elements", [])
        custom_anims = job_data.get("custom_anims", [])

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

        # ── 3.5. Resolver animações customizadas ──
        custom_anim_clips = self._resolve_custom_anim_clips(custom_anims, work_dir, total_duration)

        # ── 3.6. Resolver áudios secundários ──
        sec_audio_tracks = self._resolve_secondary_audios(secondary_audios, work_dir, total_duration)

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
            custom_anim_clips=custom_anim_clips,
            sec_audio_tracks=sec_audio_tracks,
            text_overlays=text_overlays,
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

            clips.append({
                "path": path, 
                "start": cursor, 
                "end": end_sec,
                "transition": seg.get("transition", "none")
            })
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
                "transition": seg.get("transition", "none"),
            })
        return clips

    def _resolve_custom_anim_clips(self, custom_anims: list, work_dir: Path, total_duration: float) -> list[dict]:
        """Resolve os clipes de animações customizadas (vídeo/GIF como overlay)."""
        clips = []
        for anim in sorted(custom_anims, key=lambda a: a.get("start_sec", 0) or 0):
            idx = anim.get("index", 0)
            ext = anim.get("file_ext")
            path = self._find_file(work_dir, f"custom_anim_{idx}", ext)
            if not path:
                logger.warning(f"Animação customizada {idx+1}: arquivo não encontrado, ignorando.")
                continue

            start = max(0.0, float(anim.get("start_sec", 0) or 0))
            end_raw = anim.get("end_sec")
            end = min(float(end_raw), total_duration) if end_raw is not None else total_duration
            if end <= start:
                continue

            clips.append({
                "path": path,
                "start": start,
                "end": end,
                "position": anim.get("position", "centro"),
                "scale": float(anim.get("scale", 30)),
                "loop": anim.get("loop", True),
                "transition": anim.get("transition", "none"),
            })
        return clips

    def _resolve_secondary_audios(self, secondary_audios: list, work_dir: Path, total_duration: float) -> list[dict]:
        """Resolve os caminhos e durações dos áudios secundários."""
        tracks = []
        for sa in sorted(secondary_audios, key=lambda s: s.get("index", 0)):
            idx = sa.get("index", 0)
            ext = sa.get("file_ext", ".mp3")
            path = self._find_file(work_dir, f"sec_audio_{idx}", ext)
            if not path:
                logger.warning(f"Áudio secundário {idx+1}: arquivo não encontrado em {work_dir}, ignorando.")
                continue

            start = max(0.0, float(sa.get("start_sec", 0) or 0))
            end_raw = sa.get("end_sec")
            end = min(float(end_raw), total_duration) if end_raw is not None else total_duration
            if end <= start:
                continue

            tracks.append({
                "path": path,
                "volume": float(sa.get("volume", 20)),
                "start_sec": start,
                "end_sec": end,
                "loop": sa.get("loop", True),
            })
        return tracks

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
        custom_anim_clips: list = None,
        sec_audio_tracks: list = None,
        text_overlays: list = None,
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
            
            fade_filter = ""
            if clip.get("transition") == "fade":
                fade_filter = ",fade=t=in:st=0:d=0.5"
                
            fc_parts.append(
                f"[{input_idx}:v]scale={res_w}:{res_h}:force_original_aspect_ratio=increase,"
                f"crop={res_w}:{res_h},setsar=1,format=yuv420p,fps={fps}{fade_filter}[{label}]"
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
            cur_video = self._apply_elements(fc_parts, cur_video, elements, res_w, res_h, duration)

        # ── Imagens sobrepostas, cada uma na sua janela de tempo ──
        if overlay_clips:
            if progress_fn:
                progress_fn("composing", 65, "Adicionando imagens sobrepostas...")
            for i, clip in enumerate(overlay_clips):
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

                # Transição Fade no Canal Alfa
                transition = clip.get("transition", "none")
                fade_filter = ""
                if transition == "fade":
                    fade_filter = f",fade=t=in:st={clip['start']}:d=0.5:alpha=1,fade=t=out:st={clip['end']-0.5}:d=0.5:alpha=1"

                fc_parts.append(f"[{ov_in_idx}:v]scale={scale_expr},format=rgba{fade_filter}[{ov_label}]")

                px_x = clip.get("px_x")
                px_y = clip.get("px_y")
                
                pos_expr = POSITION_MAP.get(clip["position"], POSITION_MAP["centro"])
                X_final, Y_final = pos_expr.split(':')
                if px_x is not None and px_y is not None:
                    X_final = str(px_x)
                    Y_final = str(px_y)

                pos_x_expr = X_final
                pos_y_expr = Y_final
                st = clip['start']
                dur = 0.5

                if transition == "slide_left":
                    pos_x_expr = f"if(lt(t,{st+dur}),-w+({X_final}+w)*(t-{st})/{dur},{X_final})"
                elif transition == "slide_right":
                    pos_x_expr = f"if(lt(t,{st+dur}),W+({X_final}-W)*(t-{st})/{dur},{X_final})"
                elif transition == "slide_up":
                    pos_y_expr = f"if(lt(t,{st+dur}),H+({Y_final}-H)*(t-{st})/{dur},{Y_final})"
                elif transition == "slide_down":
                    pos_y_expr = f"if(lt(t,{st+dur}),-h+({Y_final}+h)*(t-{st})/{dur},{Y_final})"

                out_label = f"vov{i}"
                enable_expr = f"between(t,{clip['start']:.3f},{clip['end']:.3f})"
                fc_parts.append(
                    f"[{cur_video}][{ov_label}]overlay={pos_x_expr}:{pos_y_expr}:"
                    f"enable='{enable_expr}':format=auto[{out_label}]"
                )
                cur_video = out_label

        # ── Animações customizadas (vídeo/GIF como overlay) ──
        if custom_anim_clips:
            if progress_fn:
                progress_fn("composing", 70, "Adicionando animações customizadas...")
            for i, clip in enumerate(custom_anim_clips):
                clip_duration = clip["end"] - clip["start"]
                loop_flag = ["-stream_loop", "-1"] if clip.get("loop", True) else []
                inputs += [*loop_flag, "-i", str(clip["path"])]
                ca_in_idx = input_idx
                input_idx += 1

                ca_label = f"ca{i}"
                ca_w = max(1, int(res_w * clip["scale"] / 100))

                transition = clip.get("transition", "none")
                fade_filter = ""
                if transition == "fade":
                    fade_filter = f",fade=t=in:st={clip['start']}:d=0.5:alpha=1,fade=t=out:st={clip['end']-0.5}:d=0.5:alpha=1"

                fc_parts.append(
                    f"[{ca_in_idx}:v]scale={ca_w}:-1,format=rgba{fade_filter}[{ca_label}]"
                )

                pos_expr = POSITION_MAP.get(clip["position"], POSITION_MAP["centro"])
                X_final, Y_final = pos_expr.split(':')
                pos_x_expr = X_final
                pos_y_expr = Y_final
                st = clip['start']
                dur = 0.5

                if transition == "slide_left":
                    pos_x_expr = f"if(lt(t,{st+dur}),-w+({X_final}+w)*(t-{st})/{dur},{X_final})"
                elif transition == "slide_right":
                    pos_x_expr = f"if(lt(t,{st+dur}),W+({X_final}-W)*(t-{st})/{dur},{X_final})"
                elif transition == "slide_up":
                    pos_y_expr = f"if(lt(t,{st+dur}),H+({Y_final}-H)*(t-{st})/{dur},{Y_final})"
                elif transition == "slide_down":
                    pos_y_expr = f"if(lt(t,{st+dur}),-h+({Y_final}+h)*(t-{st})/{dur},{Y_final})"

                out_label = f"vca{i}"
                enable_expr = f"between(t,{clip['start']:.3f},{clip['end']:.3f})"
                fc_parts.append(
                    f"[{cur_video}][{ca_label}]overlay={pos_x_expr}:{pos_y_expr}:"
                    f"enable='{enable_expr}':format=auto:shortest=1[{out_label}]"
                )
                cur_video = out_label

        # ── Animações sobre o vídeo final ──
        if animations:
            if progress_fn:
                progress_fn("composing", 75, "Aplicando animações...")
            cur_video = self._apply_animations(fc_parts, cur_video, animations, res_w, res_h, duration)

        # ── Textos sobrepostos (drawtext) ──
        if text_overlays:
            if progress_fn:
                progress_fn("composing", 76, "Adicionando textos...")
            cur_video = self._apply_text_overlays(fc_parts, cur_video, text_overlays, res_w, res_h, duration)

        # ── Áudios secundários (múltiplos, com tempo/loop/volume) ──
        if sec_audio_tracks:
            if progress_fn:
                progress_fn("composing", 78, "Mixando áudios secundários...")
            for j, sa in enumerate(sec_audio_tracks):
                sa_vol = max(0.0, float(sa.get("volume", 20)) / 100.0)
                sa_start = float(sa.get("start_sec", 0))
                sa_end = float(sa.get("end_sec") or duration)
                sa_loop = sa.get("loop", True)

                loop_flag = ["-stream_loop", "-1"] if sa_loop else []
                inputs += [*loop_flag, "-i", str(sa["path"])]
                sa_idx = input_idx
                input_idx += 1

                # Trim + volume + delay
                sa_label = f"asec{j}"
                sa_duration = sa_end - sa_start
                trim_expr = f"atrim=duration={sa_duration:.3f}," if sa_loop else ""
                delay_ms = int(sa_start * 1000)
                delay_expr = f"adelay={delay_ms}|{delay_ms}," if delay_ms > 0 else ""
                fc_parts.append(
                    f"[{sa_idx}:a]{trim_expr}{delay_expr}volume={sa_vol:.2f}[{sa_label}]"
                )

                # Mix into main audio
                out_label = f"amix{j}"
                fc_parts.append(
                    f"[{audio_label}][{sa_label}]amix=inputs=2:duration=first:dropout_transition=2[{out_label}]"
                )
                audio_label = out_label

        filter_complex = ";".join(fc_parts)

        cmd = [
            "ffmpeg", *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{cur_video}]",
            "-map", f"[{audio_label}]",
            "-c:v", "libx264", "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-crf", "23",
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
            f"{len(custom_anim_clips or [])} anim custom, "
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
    # Textos sobrepostos (com controle de tempo/posição)
    # ══════════════════════════════════════════

    def _apply_text_overlays(
        self, fc_parts: list, cur_video: str,
        text_overlays: list, res_w: int, res_h: int, duration: float,
    ) -> str:
        """Aplica textos sobrepostos ao vídeo usando o filtro drawtext do FFmpeg."""
        TEXT_POSITION_MAP = {
            "centro":            {"x": "(w-tw)/2", "y": "(h-th)/2"},
            "superior":          {"x": "(w-tw)/2", "y": "h*0.05"},
            "inferior":          {"x": "(w-tw)/2", "y": "h*0.95-th"},
            "esquerda":          {"x": "w*0.05", "y": "(h-th)/2"},
            "direita":           {"x": "w*0.95-tw", "y": "(h-th)/2"},
            "superior esquerda": {"x": "w*0.05", "y": "h*0.05"},
            "superior direita":  {"x": "w*0.95-tw", "y": "h*0.05"},
            "inferior esquerda": {"x": "w*0.05", "y": "h*0.95-th"},
            "inferior direita":  {"x": "w*0.95-tw", "y": "h*0.95-th"},
        }

        for i, text_obj in enumerate(text_overlays):
            text_str = text_obj.get("text", "").strip()
            if not text_str:
                continue

            fontfile = text_obj.get("font", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
            fontsize = int(text_obj.get("size", 48))
            fontcolor = text_obj.get("color", "#ffffff").replace("#", "0x")
            start = max(0.0, float(text_obj.get("start_sec", 0) or 0))
            end_raw = text_obj.get("end_sec")
            end = min(float(end_raw), duration) if end_raw is not None else duration

            if end <= start:
                continue

            pos_name = text_obj.get("position", "centro")
            pos = TEXT_POSITION_MAP.get(pos_name, TEXT_POSITION_MAP["centro"])

            px_x = text_obj.get("px_x")
            px_y = text_obj.get("px_y")
            X_final = pos["x"]
            Y_final = pos["y"]
            if px_x is not None: X_final = str(int(px_x))
            if px_y is not None: Y_final = str(int(px_y))

            x_expr = X_final
            y_expr = Y_final
            st = start
            dur = 0.5

            transition = text_obj.get("transition", "none")
            alpha_expr = ""
            if transition == "fade":
                alpha_expr = f":alpha='if(lt(t,{st+dur}),(t-{st})/{dur},if(gt(t,{end-dur}),({end}-t)/{dur},1))'"
            elif transition == "slide_left":
                x_expr = f"if(lt(t,{st+dur}),-tw+({X_final}+tw)*(t-{st})/{dur},{X_final})"
            elif transition == "slide_right":
                x_expr = f"if(lt(t,{st+dur}),w+({X_final}-w)*(t-{st})/{dur},{X_final})"
            elif transition == "slide_up":
                y_expr = f"if(lt(t,{st+dur}),h+({Y_final}-h)*(t-{st})/{dur},{Y_final})"
            elif transition == "slide_down":
                y_expr = f"if(lt(t,{st+dur}),-th+({Y_final}+th)*(t-{st})/{dur},{Y_final})"

            # Escapar texto para o FFmpeg drawtext
            escaped_text = text_str.replace('\\', '\\\\').replace("'", "'\\''").replace(':', '\\:').replace('%', '\\%')

            enable_expr = f"between(t,{start:.3f},{end:.3f})"
            out_label = f"vtxt{i}"

            # Filtro drawtext
            drawtext_filter = (
                f"drawtext=fontfile={fontfile}:text='{escaped_text}':"
                f"fontsize={fontsize}:fontcolor={fontcolor}:"
                f"x='{x_expr}':y='{y_expr}':"
                f"enable='{enable_expr}'{alpha_expr}"
            )

            fc_parts.append(f"[{cur_video}]{drawtext_filter}[{out_label}]")
            cur_video = out_label

        return cur_video

    # ══════════════════════════════════════════
    # Elementos decorativos (com controle de tempo)
    # ══════════════════════════════════════════

    def _apply_elements(
        self, fc_parts: list, cur_video: str,
        elements: list, res_w: int, res_h: int, duration: float,
    ) -> str:
        """Aplica elementos decorativos via filtros FFmpeg, com enable=between() quando necessário."""
        elem_idx = 0

        for elem in elements:
            # Formato expandido: {name: str, full_video: bool, start_sec, end_sec}
            # Formato legado (str simples): compatibilidade
            if isinstance(elem, str):
                elem_name = elem
                enable = None
            else:
                elem_name = elem.get("name", "")
                full_video = elem.get("full_video", True)
                start_sec = elem.get("start_sec")
                end_sec = elem.get("end_sec")
                if not full_video and start_sec is not None:
                    end_val = end_sec if end_sec is not None else duration
                    enable = f"between(t,{float(start_sec):.3f},{float(end_val):.3f})"
                else:
                    enable = None

            out_label = f"velem{elem_idx}"
            enable_suffix = f":enable='{enable}'" if enable else ""

            if elem_name == "sombra_vinheta":
                fc_parts.append(f"[{cur_video}]vignette=PI/4{enable_suffix}[{out_label}]")
                cur_video = out_label
                elem_idx += 1

            elif elem_name == "sombra_radial":
                fc_parts.append(
                    f"[{cur_video}]vignette=PI/3:max_radius={res_w//3}{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem_name == "gradiente_top":
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y=0:w={res_w}:h={res_h//4}:"
                    f"color=black@0.4:t=fill{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem_name == "gradiente_bottom":
                y_start = res_h - res_h // 4
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y={y_start}:w={res_w}:h={res_h//4}:"
                    f"color=black@0.4:t=fill{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem_name == "moldura_gold":
                border = 6
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y=0:w={res_w}:h={border}:color=0xFFD700@0.8:t=fill{enable_suffix},"
                    f"drawbox=x=0:y={res_h - border}:w={res_w}:h={border}:color=0xFFD700@0.8:t=fill{enable_suffix},"
                    f"drawbox=x=0:y=0:w={border}:h={res_h}:color=0xFFD700@0.8:t=fill{enable_suffix},"
                    f"drawbox=x={res_w - border}:y=0:w={border}:h={res_h}:color=0xFFD700@0.8:t=fill{enable_suffix}"
                    f"[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem_name == "moldura_neon":
                border = 4
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y=0:w={res_w}:h={border}:color=0xE040FB@0.9:t=fill{enable_suffix},"
                    f"drawbox=x=0:y={res_h - border}:w={res_w}:h={border}:color=0xE040FB@0.9:t=fill{enable_suffix},"
                    f"drawbox=x=0:y=0:w={border}:h={res_h}:color=0xE040FB@0.9:t=fill{enable_suffix},"
                    f"drawbox=x={res_w - border}:y=0:w={border}:h={res_h}:color=0xE040FB@0.9:t=fill{enable_suffix}"
                    f"[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem_name == "barra_inferior":
                bar_h = res_h // 8
                fc_parts.append(
                    f"[{cur_video}]drawbox=x=0:y={res_h - bar_h}:w={res_w}:h={bar_h}:"
                    f"color=black@0.6:t=fill{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

            elif elem_name == "caixa_texto":
                box_w = int(res_w * 0.8)
                box_h = res_h // 6
                box_x = (res_w - box_w) // 2
                box_y = res_h // 2 - box_h // 2
                fc_parts.append(
                    f"[{cur_video}]drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:"
                    f"color=black@0.5:t=fill{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                elem_idx += 1

        return cur_video

    # ══════════════════════════════════════════
    # Animações (com controle de tempo e intensidade)
    # ══════════════════════════════════════════

    def _apply_animations(
        self, fc_parts: list, cur_video: str,
        animations: list, res_w: int, res_h: int, duration: float,
    ) -> str:
        """Aplica animações via filtros FFmpeg com intensidade configurável e enable=between()."""
        anim_idx = 0

        for anim in animations:
            # Formato expandido: {name, full_video, start_sec, end_sec, intensity}
            # Formato legado (str simples): compatibilidade
            if isinstance(anim, str):
                anim_name = anim
                intensity = 50
                enable = None
            else:
                anim_name = anim.get("name", "")
                intensity = int(anim.get("intensity", 50))
                full_video = anim.get("full_video", True)
                start_sec = anim.get("start_sec")
                end_sec = anim.get("end_sec")
                if not full_video and start_sec is not None:
                    end_val = end_sec if end_sec is not None else duration
                    enable = f"between(t,{float(start_sec):.3f},{float(end_val):.3f})"
                else:
                    enable = None

            # Fator de intensidade: 0.2 (10%) a 2.0 (100%)
            factor = max(0.2, intensity / 50.0)
            out_label = f"vanim{anim_idx}"
            enable_suffix = f":enable='{enable}'" if enable else ""

            if anim_name == "brilho":
                brightness = 0.06 * factor
                saturation = 1.0 + 0.2 * factor
                fc_parts.append(
                    f"[{cur_video}]eq=brightness={brightness:.3f}:saturation={saturation:.2f}"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "particulas":
                noise_val = int(15 * factor)
                fc_parts.append(
                    f"[{cur_video}]noise=alls={noise_val}:allf=t+u"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "neve":
                noise_val = int(25 * factor)
                fc_parts.append(
                    f"[{cur_video}]noise=alls={noise_val}:allf=t"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "fogo":
                rs = 0.25 * factor
                bs = -0.25 * factor
                brightness = 0.04 * factor
                saturation = 1.0 + 0.5 * factor
                fc_parts.append(
                    f"[{cur_video}]colorbalance=rs={rs:.3f}:gs=-0.05:bs={-bs:.3f},"
                    f"eq=brightness={brightness:.3f}:saturation={saturation:.2f}"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "chuva":
                noise_val = int(20 * factor)
                brightness = -0.05 * factor
                fc_parts.append(
                    f"[{cur_video}]noise=alls={noise_val}:allf=t,"
                    f"eq=brightness={brightness:.3f}:contrast=1.08"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "fumaca":
                sigma = 2.5 * factor
                brightness = 0.08 * factor
                fc_parts.append(
                    f"[{cur_video}]gblur=sigma={sigma:.2f},"
                    f"eq=brightness={brightness:.3f}:contrast=0.92"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "luz":
                brightness = 0.1 * factor
                gamma = 1.0 + 0.2 * factor
                fc_parts.append(
                    f"[{cur_video}]eq=brightness={brightness:.3f}:gamma={gamma:.2f}"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "faiscas":
                noise_val = int(30 * factor)
                saturation = 1.0 + 0.4 * factor
                fc_parts.append(
                    f"[{cur_video}]noise=alls={noise_val}:allf=t+u,"
                    f"eq=saturation={saturation:.2f}"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "explosao":
                brightness = 0.12 * factor
                saturation = 1.0 + 0.6 * factor
                contrast = 1.0 + 0.15 * factor
                fc_parts.append(
                    f"[{cur_video}]eq=brightness={brightness:.3f}:"
                    f"saturation={saturation:.2f}:contrast={contrast:.2f}"
                    f"{enable_suffix}[{out_label}]"
                )
                cur_video = out_label
                anim_idx += 1

            elif anim_name == "loop_bg":
                zoom_speed = 0.0005 + 0.0005 * factor
                max_zoom = 1.1 + 0.1 * factor
                fc_parts.append(
                    f"[{cur_video}]zoompan=z='min(zoom+{zoom_speed:.5f},{max_zoom:.3f})':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={int(duration*25)}:s={res_w}x{res_h}:fps=25"
                    f"{enable_suffix}[{out_label}]"
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
