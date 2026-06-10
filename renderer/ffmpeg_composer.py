"""Composição de vídeo via FFmpeg."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from api.config import FFMPEG_AUDIO_BITRATE, FFMPEG_CRF, FFMPEG_PRESET

logger = logging.getLogger(__name__)


def compose_video(
    frames_dir: Path,
    output_path: Path,
    fps: int = 30,
    background_music: Optional[str] = None,
    width: int = 1080,
    height: int = 1920,
) -> None:
    """
    Compõe os frames em um vídeo MP4 usando FFmpeg.

    Args:
        frames_dir: Diretório contendo os frames (frame_000001.png, ...)
        output_path: Caminho do vídeo de saída
        fps: Frames por segundo
        background_music: Caminho opcional para música de fundo
        width: Largura do vídeo
        height: Altura do vídeo
    """
    frames_pattern = str(frames_dir / "frame_%06d.png")

    # Garantir que o diretório de saída existe
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if background_music and Path(background_music).exists():
        # Com áudio
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-i", background_music,
            "-c:v", "libx264",
            "-preset", FFMPEG_PRESET,
            "-crf", str(FFMPEG_CRF),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", FFMPEG_AUDIO_BITRATE,
            "-shortest",
            "-movflags", "+faststart",
            str(output_path),
        ]
    else:
        # Apenas vídeo
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-c:v", "libx264",
            "-preset", FFMPEG_PRESET,
            "-crf", str(FFMPEG_CRF),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]

    logger.info(f"FFmpeg command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutos de timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr[-1000:] if result.stderr else "Erro desconhecido"
            raise RuntimeError(f"FFmpeg falhou (code {result.returncode}): {error_msg}")

        logger.info(f"Vídeo criado: {output_path}")

    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg excedeu o timeout de 10 minutos")
    except FileNotFoundError:
        raise RuntimeError(
            "FFmpeg não encontrado. Instale o FFmpeg ou use o Docker."
        )
