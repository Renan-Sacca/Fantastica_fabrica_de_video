"""Renderer do tipo 'video_bg' — combina vídeo de fundo + áudio + legendas.

Usa ffmpeg para:
1. Fatiar/fazer loop do vídeo de fundo
2. Combinar vídeo + áudio
3. Queimar legendas SRT geradas por faster-whisper
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from renderers.base import BaseRenderer

logger = logging.getLogger("VideoBgRenderer")


class VideoBgRenderer(BaseRenderer):
    """Renderer para vídeo com fundo + áudio + legendas."""

    @property
    def video_type(self) -> str:
        return "video_bg"

    def render(
        self,
        job_data: dict,
        work_dir: Path,
        progress_callback: Optional[Callable] = None,
    ) -> Path:
        def _progress(status, pct, detail):
            if progress_callback:
                progress_callback(status=status, progress=pct, detail=detail)

        _progress("rendering", 5, "Preparando arquivos...")

        # Localizar arquivos
        bg_video_ext = job_data.get("files", {}).get("bg_video_ext", ".mp4")
        bg_video_path = work_dir / f"bg_video{bg_video_ext}"
        audio_ext = job_data.get("files", {}).get("audio_ext", ".mp3")
        audio_path = work_dir / f"audio{audio_ext}"
        generate_subtitles = job_data.get("generate_subtitles", True)
        offset = float(job_data.get("bg_video_offset", 0))
        
        # Parâmetros de intro/thumbnail (card estilo Reddit)
        title = job_data.get("title", "")
        intro_enabled = job_data.get("intro_enabled", True)
        intro_duration = float(job_data.get("intro_duration", 2))
        intro_theme = job_data.get("intro_theme", "light")  # light ou dark
        intro_color = job_data.get("intro_color", "#FF4500")
        intro_username = job_data.get("intro_username", "Anônimo")
        
        if not bg_video_path.exists():
            raise FileNotFoundError(f"Vídeo de fundo não encontrado: {bg_video_path}")
        if not audio_path.exists():
            raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

        # 1. Obter duração do áudio
        _progress("rendering", 10, "Analisando duração do áudio...")
        audio_duration = self._get_duration(audio_path)
        logger.info(f"Duração do áudio: {audio_duration:.2f}s")

        # 2. Obter duração do vídeo de fundo
        bg_duration = self._get_duration(bg_video_path)
        logger.info(f"Duração do vídeo de fundo: {bg_duration:.2f}s, offset: {offset}s")

        # 3. Preparar vídeo de fundo (fatiar + loop se necessário)
        _progress("rendering", 20, "Preparando vídeo de fundo...")
        prepared_video_path = work_dir / "bg_prepared.mp4"
        self._prepare_bg_video(
            bg_video_path, prepared_video_path,
            offset, audio_duration, bg_duration
        )

        # 4. Gerar card estilo Reddit (PNG transparente) para intro/thumbnail
        _progress("rendering", 28, "Gerando card estilo Reddit...")
        card_png_path = work_dir / "reddit_card.png"
        self._generate_card(
            card_png_path, title, intro_username, intro_theme, intro_color
        )

        # 5. Gerar thumbnail (primeiro frame + card)
        _progress("rendering", 32, "Gerando thumbnail...")
        thumbnail_path = work_dir / "thumbnail.jpg"
        self._generate_thumbnail(prepared_video_path, card_png_path, thumbnail_path)

        # 6. Gerar legendas se solicitado
        srt_path = None
        if generate_subtitles:
            _progress("generating_subtitles", 40, "Gerando legendas com Whisper...")
            srt_path = work_dir / "subtitles.srt"
            self._generate_subtitles(audio_path, srt_path, _progress)

        # 7. Compor vídeo final (vídeo + áudio + legendas)
        _progress("composing", 80, "Compondo vídeo final...")
        if intro_enabled and title.strip():
            # Compõe o vídeo completo (áudio + legendas) e sobrepõe o card estilo
            # Reddit nos primeiros segundos — a narração já toca durante a intro.
            composed_path = work_dir / "composed.mp4"
            self._compose_final(prepared_video_path, audio_path, srt_path, composed_path)

            _progress("composing", 90, "Adicionando card de intro...")
            output_path = work_dir / "output.mp4"
            self._overlay_intro_card(
                composed_path, card_png_path, output_path, intro_duration, title
            )
        else:
            # Sem intro
            output_path = work_dir / "output.mp4"
            self._compose_final(
                prepared_video_path, audio_path, srt_path, output_path, title
            )

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

    def _prepare_bg_video(
        self,
        input_path: Path,
        output_path: Path,
        offset: float,
        target_duration: float,
        bg_duration: float,
    ):
        """Prepara o vídeo de fundo: offset + loop se necessário + redimensiona para 1080x1920 (Full HD vertical)."""
        available_duration = bg_duration - offset
        
        # Filtro para redimensionar e fazer crop centralizado para formato vertical (9:16)
        # 1080x1920 é Full HD em formato vertical para celular
        video_filter = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"

        if available_duration >= target_duration:
            # Caso simples: vídeo é longo o suficiente, apenas fatiar
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(offset),
                "-i", str(input_path),
                "-t", str(target_duration),
                "-vf", video_filter,
                "-c:v", "libx264", "-preset", "fast",
                "-an",  # remove áudio do vídeo de fundo
                "-movflags", "+faststart",
                str(output_path),
            ]
        else:
            # Vídeo é curto: precisamos fazer loop
            # Usar o filtro loop do ffmpeg
            # Calcular quantas vezes precisamos repetir
            loops_needed = int(target_duration / (bg_duration - offset)) + 2

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(offset),
                "-stream_loop", str(loops_needed),
                "-i", str(input_path),
                "-t", str(target_duration),
                "-vf", video_filter,
                "-c:v", "libx264", "-preset", "fast",
                "-an",
                "-movflags", "+faststart",
                str(output_path),
            ]

        logger.info(f"Preparando vídeo de fundo: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou ao preparar vídeo: {result.stderr[-500:]}")

    def _generate_subtitles(self, audio_path: Path, srt_path: Path, _progress: Callable):
        """Gera legendas SRT a partir do áudio usando faster-whisper."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.warning("faster-whisper não disponível. Tentando whisper padrão...")
            self._generate_subtitles_fallback(audio_path, srt_path)
            return

        _progress("generating_subtitles", 45, "Carregando modelo Whisper...")
        model = WhisperModel("base", device="cpu", compute_type="int8")

        _progress("generating_subtitles", 50, "Transcrevendo áudio...")
        segments, info = model.transcribe(str(audio_path), language=None)

        _progress("generating_subtitles", 65, f"Idioma detectado: {info.language} ({info.language_probability:.0%})")

        # Gerar SRT
        srt_content = []
        segments_list = []
        for i, segment in enumerate(segments, 1):
            start = self._format_srt_time(segment.start)
            end = self._format_srt_time(segment.end)
            text = segment.text.strip()
            if text:
                srt_content.append(f"{i}\n{start} --> {end}\n{text}\n")
                segments_list.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": text
                })

        srt_path.write_text("\n".join(srt_content), encoding="utf-8")
        
        # Gerar também arquivo ASS com animações
        ass_path = srt_path.with_suffix(".ass")
        self._generate_animated_ass(segments_list, ass_path)
        
        logger.info(f"Legendas geradas: {len(srt_content)} segmentos → {srt_path}")

    def _generate_subtitles_fallback(self, audio_path: Path, srt_path: Path):
        """Fallback usando whisper CLI se faster-whisper não estiver disponível."""
        try:
            cmd = [
                "whisper", str(audio_path),
                "--model", "base",
                "--output_format", "srt",
                "--output_dir", str(audio_path.parent),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.warning(f"whisper CLI falhou: {result.stderr}")
                # Criar SRT vazio se falhar
                srt_path.write_text("", encoding="utf-8")
                return

            # whisper cria o arquivo com o nome do áudio, renomear
            generated_srt = audio_path.with_suffix(".srt")
            if generated_srt.exists() and generated_srt != srt_path:
                generated_srt.rename(srt_path)
        except Exception as e:
            logger.warning(f"Fallback whisper falhou: {e}")
            srt_path.write_text("", encoding="utf-8")

    def _format_srt_time(self, seconds: float) -> str:
        """Formata segundos para o formato SRT: HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def _format_ass_time(self, seconds: float) -> str:
        """Formata segundos para o formato ASS: H:MM:SS.cc"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
    
    def _generate_animated_ass(self, segments: list, ass_path: Path):
        """Gera arquivo ASS com animações de fade-in e scale para as legendas."""
        # Cabeçalho ASS com estilos
        # Alignment: 2 = embaixo centralizado
        # MarginV: distância da borda inferior (menor = mais embaixo)
        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,2,10,10,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # Gerar eventos com animações
        events = []
        for segment in segments:
            start_time = self._format_ass_time(segment["start"])
            end_time = self._format_ass_time(segment["end"])
            text = segment["text"].replace("\n", "\\N")
            
            # Animação: fade in (0.3s) + scale up suave
            # \\fad(300,0) = fade in 300ms, fade out 0ms
            # \\t(0,300,\\fscx110\\fscy110) = scale de 100% para 110% nos primeiros 300ms
            # \\t(300,400,\\fscx100\\fscy100) = volta para 100% entre 300-400ms
            animated_text = f"{{\\fad(300,0)\\t(0,300,\\fscx110\\fscy110)\\t(300,400,\\fscx100\\fscy100)}}{text}"
            
            events.append(
                f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{animated_text}"
            )
        
        # Escrever arquivo ASS
        ass_content = ass_header + "\n".join(events)
        ass_path.write_text(ass_content, encoding="utf-8")
        logger.info(f"Legendas animadas ASS geradas: {ass_path}")

    def _compose_final(
        self,
        video_path: Path,
        audio_path: Path,
        srt_path: Optional[Path],
        output_path: Path,
        title: str = "",
    ):
        """Combina vídeo + áudio + legendas (se houver) no vídeo final.

        Usa -map_metadata -1 para descartar os metadados do vídeo de fundo (evita que o
        título original apareça em players como VLC/Windows) e grava o título do projeto.
        """
        meta_args = ["-map_metadata", "-1"]
        if title:
            meta_args += ["-metadata", f"title={title}"]

        if srt_path and srt_path.exists() and srt_path.stat().st_size > 0:
            # Tentar usar arquivo ASS (com animações) se existir, senão usar SRT
            ass_path = srt_path.with_suffix(".ass")
            subtitle_file = ass_path if ass_path.exists() else srt_path
            
            # Escapar path para o filtro (especialmente no Windows)
            subtitle_escaped = str(subtitle_file).replace("\\", "/").replace(":", "\\:")

            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-vf", f"ass='{subtitle_escaped}'" if ass_path.exists() else f"subtitles='{subtitle_escaped}'",
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                *meta_args,
                "-shortest",
                "-movflags", "+faststart",
                str(output_path),
            ]
        else:
            # Sem legendas: apenas combinar vídeo + áudio
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                *meta_args,
                "-shortest",
                "-movflags", "+faststart",
                str(output_path),
            ]

        logger.info(f"Compondo vídeo final: {' '.join(cmd[:8])}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou ao compor vídeo final: {result.stderr[-500:]}")

        logger.info(f"Vídeo final gerado: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")

    def _generate_card(
        self,
        card_png_path: Path,
        title: str,
        username: str,
        theme: str,
        color: str,
    ):
        """Gera o card PNG estilo Reddit usando Pillow."""
        try:
            from renderers.video_bg.reddit_card import generate_reddit_card
        except ImportError:
            from reddit_card import generate_reddit_card
        generate_reddit_card(
            output_path=card_png_path,
            title=title or "Sem título",
            username=username or "Anônimo",
            theme=theme,
            accent_color=color,
        )

    def _generate_thumbnail(
        self,
        video_path: Path,
        card_png_path: Path,
        thumbnail_path: Path,
    ):
        """Gera thumbnail: primeiro frame do vídeo + card estilo Reddit sobreposto."""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(card_png_path),
            "-filter_complex",
            "[0:v]scale=1080:1920[bg];[bg][1:v]overlay=0:0",
            "-frames:v", "1",
            "-q:v", "2",
            str(thumbnail_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.warning(f"Falha ao gerar thumbnail: {result.stderr[-300:]}")
        else:
            logger.info(f"Thumbnail gerada: {thumbnail_path}")

    def _overlay_intro_card(
        self,
        composed_path: Path,
        card_png_path: Path,
        output_path: Path,
        duration: float,
        title: str = "",
    ):
        """Sobrepõe o card estilo Reddit nos primeiros segundos do vídeo já composto.

        A narração e as legendas continuam tocando normalmente por baixo — o card
        apenas aparece (com fade-in) e some (com fade-out) durante os primeiros
        `duration` segundos. A duração total do vídeo não muda.
        """
        duration = max(0.5, float(duration))
        fade = 0.3
        fade_out_start = max(0.0, duration - fade)

        # IMPORTANTE: a imagem do card é um único frame. Para o fade funcionar ao longo
        # do tempo, transformamos o PNG em um stream de vídeo com "-loop 1 -t duration".
        # Sem isso, o fade-in deixaria o único frame com alpha 0 (card invisível).
        filter_complex = (
            f"[1:v]format=rgba,"
            f"fade=t=in:st=0:d={fade}:alpha=1,"
            f"fade=t=out:st={fade_out_start:.2f}:d={fade}:alpha=1[card];"
            f"[0:v][card]overlay=0:0:enable='between(t,0,{duration})':eof_action=pass,"
            f"format=yuv420p[outv]"
        )

        # Descarta metadados originais e grava o título do projeto
        meta_args = ["-map_metadata", "-1"]
        if title:
            meta_args += ["-metadata", f"title={title}"]

        cmd = [
            "ffmpeg", "-y",
            "-i", str(composed_path),
            "-loop", "1", "-t", str(duration), "-i", str(card_png_path),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "0:a",  # mantém a narração original intacta
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            *meta_args,
            "-movflags", "+faststart",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"Falha ao sobrepor card de intro: {result.stderr[-500:]}")

        logger.info(f"Card de intro sobreposto ({duration}s) — narração preservada")

