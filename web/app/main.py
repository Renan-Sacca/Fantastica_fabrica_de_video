"""FastAPI — Serviço Web da Fantástica Fábrica de Vídeo."""
from __future__ import annotations

import asyncio
import os
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import jobs_store
from app.config import BASE_DIR, STATIC_DIR, TEMPLATES_DIR
from app.drive import get_drive
from app.parser import parse_conversation
from app.publisher import publish_job
from app.video_types import all_video_types, get_video_type

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://financepowder:rgs050601@rabbitmq.financepowder.cloud/")
TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fantástica Fábrica de Vídeo",
    description="Dashboard para geração de vídeos automatizados",
    version="2.0.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.on_event("startup")
async def startup():
    jobs_store.init()
    logger.info("Serviço web iniciado.")


# ──────────────────────────────────────────────────────────────
# Rotas Web
# ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal — lista de jobs e formulário."""
    jobs = jobs_store.get_all_jobs()
    video_types = all_video_types()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "jobs": jobs, "video_types": video_types},
    )


@app.get("/video/{job_id}", response_class=HTMLResponse)
async def video_detail(request: Request, job_id: str):
    """Tela de detalhes de um vídeo específico."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return HTMLResponse("<h1>Job não encontrado</h1>", status_code=404)

    # Buscar metadata atual do Drive
    drive = get_drive(TOKEN_FILE)
    try:
        metadata = await asyncio.get_event_loop().run_in_executor(
            None, drive.read_json, job_info["metadata_file_id"]
        )
    except Exception as e:
        metadata = {**job_info, "status": "error", "error": str(e)}

    drive_link = drive.get_folder_link(job_info["drive_folder_id"])

    return templates.TemplateResponse(
        "video_detail.html",
        {
            "request": request,
            "job": metadata,
            "job_info": job_info,
            "drive_link": drive_link,
        },
    )


# ──────────────────────────────────────────────────────────────
# Rota principal: criar job
# ──────────────────────────────────────────────────────────────

@app.post("/render")
async def render_from_form(
    title: str = Form(...),
    video_type: str = Form("whatsapp"),
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
    conversation_images: List[UploadFile] = File(default=[]),
):
    """Recebe o formulário, sobe tudo no Drive e publica no RabbitMQ."""
    try:
        # ── 1. Validar tipo de vídeo ──
        try:
            vt = get_video_type(video_type)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        # ── 2. Obter texto da conversa ──
        conv_text = ""
        conv_filename = "conversa.txt"
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

        # ── 3. Validar conversa ──
        try:
            messages = parse_conversation(conv_text, conv_filename)
        except ValueError as e:
            return JSONResponse({"error": f"Erro ao parsear conversa: {e}"}, status_code=400)

        if not messages:
            return JSONResponse(
                {"error": "Nenhuma mensagem encontrada. Verifique o formato da conversa."},
                status_code=400,
            )

        # ── 4. Gerar job_id ──
        job_id = uuid.uuid4().hex[:8]
        drive = get_drive(TOKEN_FILE)

        # ── 5. Criar pasta no Drive ──
        job_folder_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.create_job_folder, title, job_id, vt.drive_folder_name
        )

        # ── 6. Montar metadata inicial ──
        metadata: dict = {
            "job_id": job_id,
            "title": title,
            "video_type": video_type,
            "contact_name": contact_name,
            "contact_status": contact_status,
            "video_format": video_format,
            "fps": fps,
            "speed": speed,
            "reading_speed": reading_speed,
            "scroll_speed": scroll_speed,
            "animation_style": animation_style,
            "status": "pending",
            "progress": 0,
            "detail": "Aguardando worker...",
            "error": None,
            "created_at": datetime.now().isoformat(),
            "video_drive_id": None,
            "video_url": None,
            "drive_folder_id": job_folder_id,
            "files": {},
        }

        # ── 7. Upload da conversa ──
        conv_bytes = conv_text.encode("utf-8")
        conv_file_id = await asyncio.get_event_loop().run_in_executor(
            None,
            drive.upload_bytes,
            conv_bytes,
            "conversa.txt",
            job_folder_id,
            "text/plain",
        )
        metadata["files"]["conversa"] = conv_file_id

        # ── 8. Upload de arquivos opcionais ──
        if contact_photo and contact_photo.filename:
            content = await contact_photo.read()
            ext = Path(contact_photo.filename).suffix or ".jpg"
            file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, content, f"foto_perfil{ext}", job_folder_id, "image/jpeg"
            )
            metadata["files"]["foto_perfil"] = file_id
            metadata["files"]["foto_perfil_ext"] = ext

        if wallpaper and wallpaper.filename:
            content = await wallpaper.read()
            ext = Path(wallpaper.filename).suffix or ".jpg"
            file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, content, f"papel_parede{ext}", job_folder_id, "image/jpeg"
            )
            metadata["files"]["papel_parede"] = file_id
            metadata["files"]["papel_parede_ext"] = ext

        if background_music and background_music.filename:
            content = await background_music.read()
            ext = Path(background_music.filename).suffix or ".mp3"
            file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, content, f"musica{ext}", job_folder_id, "audio/mpeg"
            )
            metadata["files"]["musica"] = file_id
            metadata["files"]["musica_ext"] = ext

        # ── 9. Upload de imagens da conversa ──
        imagens_folder_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.get_or_create_folder, "imagens", job_folder_id
        )
        metadata["files"]["imagens"] = {}
        metadata["files"]["imagens_folder_id"] = imagens_folder_id

        for img in conversation_images:
            if img and img.filename:
                content = await img.read()
                file_id = await asyncio.get_event_loop().run_in_executor(
                    None,
                    drive.upload_bytes,
                    content,
                    img.filename,
                    imagens_folder_id,
                    img.content_type or "image/jpeg",
                )
                metadata["files"]["imagens"][img.filename] = file_id

        # ── 10. Upload do metadata.json ──
        metadata_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_json, metadata, "metadata.json", job_folder_id
        )

        # ── 11. Armazenar no índice local ──
        jobs_store.add_job(
            job_id=job_id,
            title=title,
            video_type=video_type,
            drive_folder_id=job_folder_id,
            metadata_file_id=metadata_file_id,
        )

        # ── 12. Publicar no RabbitMQ ──
        await publish_job(job_id, video_type)

        logger.info(f"[{job_id}] Job criado e publicado → Drive: {job_folder_id}")
        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.exception(f"Erro ao criar job: {e}")
        return JSONResponse({"error": f"Erro interno: {e}"}, status_code=500)


# ──────────────────────────────────────────────────────────────
# API REST
# ──────────────────────────────────────────────────────────────

@app.get("/api/jobs")
async def list_jobs():
    """Lista todos os jobs com status atual do Drive."""
    all_jobs = jobs_store.get_all_jobs()
    drive = get_drive(TOKEN_FILE)
    result = []

    for job_info in all_jobs:
        try:
            metadata = await asyncio.get_event_loop().run_in_executor(
                None, drive.read_json, job_info["metadata_file_id"]
            )
            result.append(metadata)
        except Exception:
            result.append({
                **job_info,
                "status": "unknown",
                "progress": 0,
                "detail": "Não foi possível ler status do Drive",
            })

    return result


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    """Status atual de um job específico."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    drive = get_drive(TOKEN_FILE)
    try:
        metadata = await asyncio.get_event_loop().run_in_executor(
            None, drive.read_json, job_info["metadata_file_id"]
        )
        return metadata
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/jobs/{job_id}/stream")
async def job_stream(job_id: str):
    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            job_info = jobs_store.get_job(job_id)
            if not job_info:
                yield f"data: {json.dumps({'error': 'Job não encontrado'})}\n\n"
                break
                
            metadata_file_id = job_info.get("metadata_file_id")
            drive = get_drive(TOKEN_FILE)
            
            # Buscar metadata ID sob demanda se não existir no cache local
            if not metadata_file_id:
                try:
                    metadata_file_id = await loop.run_in_executor(
                        None, drive.find_file_in_folder, job_info["drive_folder_id"], "metadata.json"
                    )
                    if metadata_file_id:
                        jobs_store.update_job(job_id, {"metadata_file_id": metadata_file_id})
                    else:
                        yield f"data: {json.dumps({'status': 'error', 'error': 'metadata.json não encontrado no Drive'})}\n\n"
                        break
                except Exception as e:
                    yield f"data: {json.dumps({'status': 'error', 'error': f'Erro ao buscar metadata no Drive: {e}'})}\n\n"
                    break

            try:
                metadata = await loop.run_in_executor(
                    None, drive.read_json, metadata_file_id
                )
                yield f"data: {json.dumps(metadata, default=str)}\n\n"

                if metadata.get("status") in ("done", "error"):
                    break

                await asyncio.sleep(3)  # Poll a cada 3s

            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/video/{job_id}/recriar")
async def recriar_video(job_id: str):
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    try:
        await publish_job(job_id, job_info.get("video_type", "whatsapp"))
    except Exception as e:
        import logging
        logging.error(f"Erro ao publicar no RabbitMQ: {e}")
        return JSONResponse({"error": "Falha ao enfileirar job"}, status_code=500)
    return RedirectResponse(url=f"/video/{job_id}", status_code=303)

@app.post("/api/sync")
async def sync_drive(request: Request):
    """Sincroniza os jobs com o Drive manualmente."""
    drive = get_drive(TOKEN_FILE)
    await asyncio.get_event_loop().run_in_executor(None, jobs_store.sync_with_drive, drive)
    return {"status": "ok"}
