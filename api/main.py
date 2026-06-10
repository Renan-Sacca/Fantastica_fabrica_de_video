"""FastAPI Application - Fantástica Fábrica de Vídeo."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.config import (
    ASSETS_DIR,
    CONVERSATIONS_DIR,
    FRONTEND_ASSETS_DIR,
    FRONTEND_DIR,
    OUTPUT_DIR,
    STATIC_DIR,
    TEMPLATES_DIR,
    UPLOADS_DIR,
)
from api.jobs import (
    create_job,
    delete_job,
    get_all_jobs,
    get_job,
    read_progress_file,
    start_render_job,
    sync_job_from_progress_file,
)
from api.models import (
    AnimationStyle,
    ConversationConfig,
    JobStatus,
    RenderJob,
    VideoFormat,
)
from api.parser import parse_conversation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fantástica Fábrica de Vídeo",
    description="Geração automatizada de vídeos simulando conversas WhatsApp",
    version="1.0.0",
)

# Montar arquivos estáticos
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount(
    "/frontend",
    StaticFiles(directory=str(FRONTEND_DIR.parent)),
    name="frontend",
)
app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOADS_DIR)),
    name="uploads",
)
app.mount(
    "/assets",
    StaticFiles(directory=str(ASSETS_DIR)),
    name="assets_dir",
)
app.mount(
    "/conversations",
    StaticFiles(directory=str(CONVERSATIONS_DIR)),
    name="conversations",
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ──────────────────────────────────────────────────────────────
# Rotas Web (Dashboard)
# ──────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal do dashboard."""
    jobs = get_all_jobs()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "jobs": jobs},
    )


@app.post("/render")
async def render_from_form(
    request: Request,
    conversation_text: str = Form(""),
    conversation_file: Optional[UploadFile] = File(None),
    contact_name: str = Form("Contato"),
    contact_status: str = Form("online"),
    video_format: str = Form("vertical"),
    fps: int = Form(30),
    speed: float = Form(1.0),
    reading_speed: float = Form(1.0),
    scroll_speed: float = Form(1.0),
    animation_style: str = Form("fade"),
    contact_photo: Optional[UploadFile] = File(None),
    wallpaper: Optional[UploadFile] = File(None),
    background_music: Optional[UploadFile] = File(None),
):
    """Receber formulário do dashboard e iniciar renderização."""
    try:
        # Obter texto da conversa
        conv_text = ""
        conv_filename = "conversation.txt"

        if conversation_file and conversation_file.filename:
            content_bytes = await conversation_file.read()
            conv_text = content_bytes.decode("utf-8", errors="replace")
            conv_filename = conversation_file.filename
        elif conversation_text.strip():
            conv_text = conversation_text.strip()
        else:
            return JSONResponse(
                {"error": "Nenhuma conversa fornecida. Cole o texto ou envie um arquivo."},
                status_code=400,
            )

        # Parsear conversa
        messages = parse_conversation(conv_text, conv_filename)
        if not messages:
            return JSONResponse(
                {"error": "Nenhuma mensagem encontrada na conversa. Verifique o formato."},
                status_code=400,
            )

        # Configuração
        config = ConversationConfig(
            contact_name=contact_name,
            contact_status=contact_status,
            video_format=VideoFormat(video_format),
            fps=fps,
            speed=speed,
            reading_speed=reading_speed,
            scroll_speed=scroll_speed,
            animation_style=AnimationStyle(animation_style),
        )

        # Criar job
        job = RenderJob(config=config, messages=messages)

        # Salvar uploads
        job_upload_dir = UPLOADS_DIR / job.job_id
        job_upload_dir.mkdir(parents=True, exist_ok=True)

        if contact_photo and contact_photo.filename:
            photo_path = job_upload_dir / f"avatar_{contact_photo.filename}"
            with open(photo_path, "wb") as f:
                content = await contact_photo.read()
                f.write(content)
            job.contact_photo_path = str(photo_path)

        if wallpaper and wallpaper.filename:
            wp_path = job_upload_dir / f"wallpaper_{wallpaper.filename}"
            with open(wp_path, "wb") as f:
                content = await wallpaper.read()
                f.write(content)
            job.wallpaper_path = str(wp_path)

        if background_music and background_music.filename:
            music_path = job_upload_dir / f"music_{background_music.filename}"
            with open(music_path, "wb") as f:
                content = await background_music.read()
                f.write(content)
            job.background_music_path = str(music_path)

        # Registrar e iniciar
        create_job(job)
        await start_render_job(job)

        return JSONResponse({"job_id": job.job_id, "status": "queued"})

    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"Erro ao processar renderização: {e}")
        return JSONResponse(
            {"error": f"Erro interno: {e}"},
            status_code=500,
        )


# ──────────────────────────────────────────────────────────────
# Rotas API REST
# ──────────────────────────────────────────────────────────────


@app.get("/api/jobs")
async def list_jobs():
    """Listar todos os jobs."""
    jobs = get_all_jobs()
    # Sincronizar progresso dos jobs em execução
    for job in jobs:
        if job.status in (JobStatus.RENDERING, JobStatus.COMPOSING, JobStatus.PREPARING):
            sync_job_from_progress_file(job.job_id)
    return [job.to_progress().model_dump() for job in jobs]


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    """Status de um job específico."""
    job = get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    # Sincronizar com arquivo de progresso
    if job.status in (JobStatus.RENDERING, JobStatus.COMPOSING, JobStatus.PREPARING, JobStatus.PARSING):
        sync_job_from_progress_file(job.job_id)

    return job.to_progress().model_dump()


@app.get("/api/jobs/{job_id}/stream")
async def job_stream(job_id: str):
    """SSE stream de progresso em tempo real."""
    job = get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    async def event_generator():
        while True:
            # Sincronizar com arquivo de progresso
            sync_job_from_progress_file(job_id)
            current_job = get_job(job_id)

            if not current_job:
                yield f"data: {json.dumps({'status': 'error', 'error': 'Job removido'})}\n\n"
                break

            data = current_job.to_progress().model_dump()
            yield f"data: {json.dumps(data, default=str)}\n\n"

            if current_job.status in (JobStatus.DONE, JobStatus.ERROR):
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    """Download do vídeo gerado."""
    job = get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    if job.status != JobStatus.DONE or not job.output_path:
        return JSONResponse(
            {"error": "Vídeo ainda não está pronto"},
            status_code=400,
        )

    output_file = Path(job.output_path)
    if not output_file.exists():
        return JSONResponse(
            {"error": "Arquivo de vídeo não encontrado"},
            status_code=404,
        )

    return FileResponse(
        str(output_file),
        media_type="video/mp4",
        filename=f"whatsapp_video_{job_id}.mp4",
    )


@app.delete("/api/jobs/{job_id}")
async def remove_job(job_id: str):
    """Remover um job."""
    if delete_job(job_id):
        # Limpar arquivo de progresso
        progress_file = OUTPUT_DIR / f".progress_{job_id}.json"
        progress_file.unlink(missing_ok=True)
        # Limpar uploads
        upload_dir = UPLOADS_DIR / job_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        return {"status": "deleted"}
    return JSONResponse({"error": "Job não encontrado"}, status_code=404)
