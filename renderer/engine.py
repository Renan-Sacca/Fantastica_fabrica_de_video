"""
Motor de renderização principal.

Usa Playwright headless para capturar frames da página WhatsApp clone,
e FFmpeg para compor o vídeo final.
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path

from api.config import FRONTEND_DIR, OUTPUT_DIR
from api.jobs import update_job_progress
from api.models import JobStatus, Message, RenderJob
from renderer.animator import Timeline
from renderer.ffmpeg_composer import compose_video
from renderer.utils import image_to_data_uri

logger = logging.getLogger(__name__)


def render_video(job: RenderJob) -> None:
    """
    Renderiza um vídeo completo a partir de um job.

    1. Parsear conversa e construir timeline
    2. Abrir Playwright headless
    3. Renderizar frame a frame
    4. Compor com FFmpeg
    """
    job_id = job.job_id
    config = job.config
    messages = job.messages

    logger.info(f"[{job_id}] Iniciando renderização...")

    # ── Fase 1: Preparação ──
    update_job_progress(
        job_id,
        status=JobStatus.PREPARING,
        progress=2.0,
        detail="Preparando conversa...",
    )

    # Construir timeline
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
    update_job_progress(
        job_id,
        total_frames=total_frames,
        progress=5.0,
        detail=f"Timeline calculada: {total_frames} frames, {timeline.total_duration_ms / 1000:.1f}s",
    )

    logger.info(
        f"[{job_id}] Timeline: {total_frames} frames, "
        f"{timeline.total_duration_ms / 1000:.1f}s de vídeo"
    )

    # Criar diretório temporário para frames
    frames_dir = Path(tempfile.mkdtemp(prefix=f"fabrica_{job_id}_"))

    try:
        # ── Fase 2: Renderização ──
        update_job_progress(
            job_id,
            status=JobStatus.RENDERING,
            progress=10.0,
            detail="Iniciando navegador headless...",
        )

        # Preparar dados para o frontend
        conversation_data = _build_conversation_data(job)

        # Renderizar frames com Playwright
        _render_frames(
            job_id=job_id,
            conversation_data=conversation_data,
            timeline=timeline,
            frames_dir=frames_dir,
            width=config.width,
            height=config.height,
            total_frames=total_frames,
        )

        # ── Fase 3: Composição FFmpeg ──
        update_job_progress(
            job_id,
            status=JobStatus.COMPOSING,
            progress=92.0,
            detail="Compondo vídeo com FFmpeg...",
        )

        output_path = OUTPUT_DIR / f"whatsapp_{job_id}.mp4"
        compose_video(
            frames_dir=frames_dir,
            output_path=output_path,
            fps=config.fps,
            background_music=job.background_music_path,
            width=config.width,
            height=config.height,
        )

        # ── Fase 4: Finalização ──
        update_job_progress(
            job_id,
            status=JobStatus.DONE,
            progress=100.0,
            detail="Vídeo pronto!",
            output_path=str(output_path),
        )

        logger.info(f"[{job_id}] Renderização concluída: {output_path}")

    except Exception as e:
        logger.error(f"[{job_id}] Erro na renderização: {e}")
        update_job_progress(
            job_id,
            status=JobStatus.ERROR,
            error=str(e),
            detail=f"Erro: {e}",
        )
        raise

    finally:
        # Limpar frames temporários
        try:
            shutil.rmtree(frames_dir, ignore_errors=True)
        except Exception:
            pass


def _build_conversation_data(job: RenderJob) -> dict:
    """Constrói o JSON de dados para o frontend WhatsApp."""
    config = job.config

    # Converter imagens para data URI
    contact_photo_uri = None
    if job.contact_photo_path:
        contact_photo_uri = image_to_data_uri(job.contact_photo_path)

    wallpaper_uri = None
    if job.wallpaper_path:
        wallpaper_uri = image_to_data_uri(job.wallpaper_path)

    # Converter mensagens para dict
    messages_data = []
    for msg in job.messages:
        msg_dict = {
            "sender": msg.sender,
            "text": msg.text,
            "time": msg.time,
            "type": msg.type.value,
            "status": msg.status.value,
            "media_path": None,
        }

        # Converter imagem da mensagem para data URI
        if msg.media_path:
            uri = image_to_data_uri(msg.media_path)
            if uri:
                msg_dict["media_uri"] = uri
            else:
                msg_dict["media_path"] = msg.media_path

        messages_data.append(msg_dict)

    return {
        "contact_name": config.contact_name,
        "contact_status": config.contact_status,
        "contact_photo": contact_photo_uri,
        "wallpaper": wallpaper_uri,
        "sent_color": config.sent_message_color,
        "received_color": config.received_message_color,
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
) -> None:
    """Renderiza todos os frames usando Playwright headless."""
    from playwright.sync_api import sync_playwright

    html_path = FRONTEND_DIR / "index.html"

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
            device_scale_factor=2,  # Retina para qualidade HD
        )

        page = context.new_page()

        # Carregar a página do WhatsApp clone
        page.goto(f"file://{html_path.resolve()}")
        page.wait_for_load_state("networkidle")

        # Inicializar a conversa com os dados
        page.evaluate(
            f"window.initConversation({json.dumps(conversation_data)})"
        )

        # Aguardar renderização inicial
        page.wait_for_timeout(500)

        # Renderizar frame a frame
        for frame_idx in range(total_frames):
            # Calcular estado do frame
            state = timeline.get_frame_state(frame_idx)

            # Aplicar estado na página
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

            # Capturar screenshot
            frame_path = frames_dir / f"frame_{frame_idx + 1:06d}.png"
            page.screenshot(path=str(frame_path))

            # Atualizar progresso (10% a 90% é renderização)
            if frame_idx % 5 == 0 or frame_idx == total_frames - 1:
                progress = 10.0 + (frame_idx / max(1, total_frames - 1)) * 80.0
                update_job_progress(
                    job_id,
                    progress=progress,
                    detail=f"Frame {frame_idx + 1}/{total_frames}",
                    current_frame=frame_idx + 1,
                )

        browser.close()

    logger.info(f"[{job_id}] {total_frames} frames renderizados")
