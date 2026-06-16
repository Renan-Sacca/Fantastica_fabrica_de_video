"""Motor de renderização WhatsApp — adaptado para usar progress_callback."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import asyncio
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

    # Calcular viewport lógico CSS para que os elementos fiquem maiores na tela
    css_scale = 2.5
    logical_width = int(config.width / css_scale)
    logical_height = int(config.height / css_scale)

    # ── Fase 1: Timeline ──
    timeline = Timeline(
        messages=messages,
        fps=config.fps,
        speed=config.speed,
        reading_speed=config.reading_speed,
        scroll_speed=config.scroll_speed,
        animation_style=config.animation_style.value,
        viewport_height=float(logical_height),
        header_height=104.0,
        input_bar_height=76.0,
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
            width=logical_width,
            height=logical_height,
            css_scale=css_scale,
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

        report(status="composing", progress=95.0, detail="Renderização e composição concluídas. Aguardando upload...")
        logger.info(f"[{job_id}] Concluído localmente: {output_path}")

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


async def _render_chunk_async(
    context, 
    chunk_data: list[tuple[int, str]], 
    html_path: Path, 
    conversation_data: dict, 
    frames_dir: Path, 
    progress_queue: asyncio.Queue
):
    page = await context.new_page()
    await page.goto(f"file://{html_path.resolve()}")
    await page.wait_for_load_state("networkidle")
    await page.evaluate(f"window.initConversation({json.dumps(conversation_data)})")
    await page.wait_for_timeout(500)

    for frame_idx, state_json in chunk_data:
        await page.evaluate(f"window.renderFrame({state_json})")
        frame_path = frames_dir / f"frame_{frame_idx + 1:06d}.jpg"
        await page.screenshot(path=str(frame_path), type="jpeg", quality=90, animations="disabled")
        
        await progress_queue.put(frame_idx)
        
    await page.close()

async def _progress_reporter(frames_to_render: int, progress_queue: asyncio.Queue, report_callback):
    if frames_to_render == 0:
        return
        
    frames_done = 0
    last_reported_threshold = 0
    
    while frames_done < frames_to_render:
        await progress_queue.get()
        frames_done += 1
        
        raw_progress = 10.0 + (frames_done / max(1, frames_to_render - 1)) * 80.0
        for threshold in _PROGRESS_THRESHOLDS:
            if last_reported_threshold < threshold <= raw_progress:
                last_reported_threshold = threshold
                report_callback(raw_progress, f"Renderizando únicos: {frames_done}/{frames_to_render}")
                break

async def _render_frames_async(
    job_id: str,
    conversation_data: dict,
    timeline: Timeline,
    frames_dir: Path,
    width: int,
    height: int,
    css_scale: float,
    total_frames: int,
    progress_callback: Optional[Callable] = None,
) -> None:
    from playwright.async_api import async_playwright
    import os
    
    html_path = FRONTEND_DIR / "whatsapp" / "index.html"

    def report(progress, detail):
        if progress_callback:
            progress_callback(status="rendering", progress=progress, detail=detail)

    # ── Fase 1: Pré-computar estados e achar frames únicos ──
    unique_states = {}  # state_json -> master_frame_idx
    master_frames = []  # list of (frame_idx, state_json)
    frame_mapping = {}  # frame_idx -> master_frame_idx

    for i in range(total_frames):
        state = timeline.get_frame_state(i)
        state_json = json.dumps({
            "scrollY": state.scroll_y,
            "visibleMessages": state.visible_messages,
            "messageOpacity": {str(k): v for k, v in state.message_opacity.items()},
            "messageTranslateY": {str(k): v for k, v in state.message_translate_y.items()},
            "showTyping": state.show_typing,
            "typingSender": state.typing_sender,
            "statusBarTime": state.status_bar_time,
        }, sort_keys=True)
        
        if state_json not in unique_states:
            unique_states[state_json] = i
            master_frames.append((i, state_json))
            frame_mapping[i] = i
        else:
            frame_mapping[i] = unique_states[state_json]

    num_unique = len(master_frames)
    logger.info(f"[{job_id}] Otimização de Cache: {num_unique} frames únicos identificados em {total_frames} totais.")

    # ── Fase 2: Renderizar apenas os frames únicos ──
    NUM_CHUNKS = 12
    chunks = [[] for _ in range(NUM_CHUNKS)]
    for idx, (frame_idx, state_json) in enumerate(master_frames):
        chunks[idx % NUM_CHUNKS].append((frame_idx, state_json))
    
    chunks = [c for c in chunks if c]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--no-zygote",
                "--disable-extensions",
            ],
        )
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=css_scale,
        )
        
        progress_queue = asyncio.Queue()
        reporter_task = asyncio.create_task(_progress_reporter(num_unique, progress_queue, report))
        
        tasks = []
        for chunk in chunks:
            tasks.append(_render_chunk_async(
                context, chunk, html_path, conversation_data, frames_dir, progress_queue
            ))
            
        await asyncio.gather(*tasks)
        await reporter_task
        await browser.close()
        
    # ── Fase 3: Clonagem dos frames idênticos ──
    for i in range(total_frames):
        master_idx = frame_mapping[i]
        if master_idx != i:
            src = frames_dir / f"frame_{master_idx + 1:06d}.jpg"
            dst = frames_dir / f"frame_{i + 1:06d}.jpg"
            try:
                os.link(src, dst)
            except Exception:
                shutil.copyfile(src, dst)

    logger.info(f"[{job_id}] Clonagem completa: reconstruídos {total_frames} frames totais.")

def _render_frames(
    job_id: str,
    conversation_data: dict,
    timeline: Timeline,
    frames_dir: Path,
    width: int,
    height: int,
    css_scale: float,
    total_frames: int,
    progress_callback: Optional[Callable] = None,
) -> None:
    """Renderiza os frames delegando para o loop assíncrono."""
    asyncio.run(_render_frames_async(
        job_id, conversation_data, timeline, frames_dir, width, height, css_scale, total_frames, progress_callback
    ))
