"""Composição de vídeo via FFmpeg — worker."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from renderers.whatsapp.config import FFMPEG_AUDIO_BITRATE, FFMPEG_CRF, FFMPEG_PRESET

logger = logging.getLogger(__name__)


def compose_video(
    frames_dir: Path,
    output_path: Path,
    fps: int = 30,
    background_music: Optional[str] = None,
    width: int = 1080,
    height: int = 1920,
) -> None:
    frames_pattern = str(frames_dir / "frame_%06d.jpg")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if background_music and Path(background_music).exists():
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-stream_loop", "-1",
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
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", frames_pattern,
            "-c:v", "libx264",
            "-preset", FFMPEG_PRESET,
            "-crf", str(FFMPEG_CRF),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]

    logger.info(f"FFmpeg: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg falhou: {result.stderr[-1000:]}")
        logger.info(f"Vídeo criado: {output_path}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg excedeu o timeout de 10 minutos")
    except FileNotFoundError:
        raise RuntimeError("FFmpeg não encontrado no container")
