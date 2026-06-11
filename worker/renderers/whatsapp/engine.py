"""Motor de renderização WhatsApp — adaptado para usar progress_callback."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Optional

from renderers.whatsapp.animator import Timeline
from renderers.whatsapp.ffmpeg_composer import compose_video
from renderers.whatsapp.models import RenderJob
from renderers.whatsapp.utils import image_to_data_uri

logger = logging.getLogger(__name__)

# Diretório do frontend WhatsApp (relativo a este arquivo)
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

# Percentuais de progresso onde o Drive é atualizado (para reduzir chamadas de API)
_PROGRESS_THRESHOLDS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 92, 95, 100]


def render_video(
    job: RenderJob,
    output_path: Path,
    progress_callback: Optional[Callable] = None,
) -> None:
    """
    Renderiza um vídeo completo.

    Args:
        job: Job de renderização com config e mensagens
        output_path: Caminho de saída do .mp4
        progress_callback: fn(status, progress, detail) → chamada nos marcos
    """
    def report(status: str = None, progress: float = 0.0, detail: str = ""):
        if progress_callback:
            progress_callback(status=status, progress=progress, detail=detail)

    job_id = job.job_id
    config = job.config
    messages = job.messages

    logger.info(f"[{job_id}] Iniciando renderização WhatsApp...")

    report(status="preparing", progress=2.0, detail="Preparando conversa...")

    # ── Fase 1: Timeline ──
    timeline = Timeline(
        messages=messages,
        fps=config.fps,
        speed=config.speed,
        reading_speed=config.reading_speed,
        scroll_speed=config.scroll_speed,
        animation_style=config.animation_style.value,
        viewport_height=float(config.height),
    )
    total_frames = timeline.total_frames
    report(
        status="preparing",
        progress=5.0,
        detail=f"Timeline: {total_frames} frames, {timeline.total_duration_ms / 1000:.1f}s",
    )
    logger.info(f"[{job_id}] Timeline: {total_frames} frames")

    frames_dir = Path(tempfile.mkdtemp(prefix=f"fabrica_{job_id}_"))

    try:
        # ── Fase 2: Renderização ──
        report(status="rendering", progress=10.0, detail="Iniciando navegador headless...")

        conversation_data = _build_conversation_data(job)

        _render_frames(
            job_id=job_id,
            conversation_data=conversation_data,
            timeline=timeline,
            frames_dir=frames_dir,
            width=config.width,
            height=config.height,
            total_frames=total_frames,
            progress_callback=report,
        )

        # ── Fase 3: FFmpeg ──
        report(status="composing", progress=92.0, detail="Compondo vídeo com FFmpeg...")

        compose_video(
            frames_dir=frames_dir,
            output_path=output_path,
            fps=config.fps,
            background_music=job.background_music_path,
            width=config.width,
            height=config.height,
        )

        report(status="done", progress=100.0, detail="Vídeo pronto!")
        logger.info(f"[{job_id}] Concluído: {output_path}")

    except Exception as e:
        logger.error(f"[{job_id}] Erro: {e}")
        report(status="error", progress=0, detail=f"Erro: {e}")
        raise

    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


def _build_conversation_data(job: RenderJob) -> dict:
    config = job.config
    contact_photo_uri = image_to_data_uri(job.contact_photo_path) if job.contact_photo_path else None
    wallpaper_uri = image_to_data_uri(job.wallpaper_path) if job.wallpaper_path else None

    messages_data = []
    for msg in job.messages:
        md = {
            "sender": msg.sender,
            "text": msg.text,
            "time": msg.time,
            "type": msg.type.value,
            "status": msg.status.value,
            "media_path": None,
        }
        if msg.media_path:
            uri = image_to_data_uri(msg.media_path)
            if uri:
                md["media_uri"] = uri
            else:
                md["media_path"] = msg.media_path
        messages_data.append(md)

    return {
        "contact_name": config.contact_name,
        "contact_status": config.contact_status,
        "contact_photo": contact_photo_uri,
        "wallpaper": wallpaper_uri,
        "sent_color": None,
        "received_color": None,
        "messages": messages_data,
        "animation_style": config.animation_style.value,
    }


def _render_frames(
    job_id: str,
    conversation_data: dict,
    timeline: Timeline,
    frames_dir: Path,
    width: int,
    height: int,
    total_frames: int,
    progress_callback: Optional[Callable] = None,
) -> None:
    """Renderiza todos os frames usando Playwright headless."""
    from playwright.sync_api import sync_playwright

    html_path = FRONTEND_DIR / "whatsapp" / "index.html"

    def report(progress, detail):
        if progress_callback:
            progress_callback(status="rendering", progress=progress, detail=detail)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--no-zygote",
                "--single-process",
                "--disable-extensions",
            ],
        )
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=2,
        )
        page = context.new_page()
        page.goto(f"file://{html_path.resolve()}")
        page.wait_for_load_state("networkidle")
        page.evaluate(f"window.initConversation({json.dumps(conversation_data)})")
        page.wait_for_timeout(500)

        last_reported_threshold = 0

        for frame_idx in range(total_frames):
            state = timeline.get_frame_state(frame_idx)
            state_json = json.dumps({
                "scrollY": state.scroll_y,
                "visibleMessages": state.visible_messages,
                "messageOpacity": {str(k): v for k, v in state.message_opacity.items()},
                "messageTranslateY": {str(k): v for k, v in state.message_translate_y.items()},
                "showTyping": state.show_typing,
                "typingSender": state.typing_sender,
                "statusBarTime": state.status_bar_time,
            })
            page.evaluate(f"window.renderFrame({state_json})")
            frame_path = frames_dir / f"frame_{frame_idx + 1:06d}.png"
            page.screenshot(path=str(frame_path))

            # Reportar progresso apenas nos thresholds definidos
            raw_progress = 10.0 + (frame_idx / max(1, total_frames - 1)) * 80.0
            for threshold in _PROGRESS_THRESHOLDS:
                if last_reported_threshold < threshold <= raw_progress:
                    last_reported_threshold = threshold
                    report(raw_progress, f"Frame {frame_idx + 1}/{total_frames}")
                    break

        browser.close()

    logger.info(f"[{job_id}] {total_frames} frames renderizados")
