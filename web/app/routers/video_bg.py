"""Router de Vídeo com Fundo — upload de vídeo + áudio, geração de legendas.

Fluxo:
1. Usuário faz upload do vídeo de fundo
2. Escolhe áudio (upload direto ou gerar via OmniVoice)
3. Define offset (segundo inicial do vídeo de fundo)
4. Worker processa: fatia vídeo, combina com áudio, gera legendas
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.config import BASE_DIR, TEMPLATES_DIR
from app.drive import get_drive
from app.publisher import publish_job
from app.repositories import jobs as jobs_repo
from app.video_types import get_video_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video-bg", tags=["video_bg"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

PERM = "video_bg"


def _require_permission(request: Request):
    """Retorna (user, error_response). error_response None se ok."""
    user = get_current_user(request)
    if not user:
        return None, RedirectResponse(url="/auth/login", status_code=302)
    if PERM not in user.get("permissions", []):
        resp = templates.TemplateResponse(
            "403.html",
            {"request": request, "user": user, "required_permission": PERM},
            status_code=403,
        )
        return user, resp
    return user, None


# ── Páginas ──

@router.get("", response_class=HTMLResponse)
async def video_bg_create(request: Request):
    """Página principal de criação de vídeo com fundo."""
    user, err = _require_permission(request)
    if err:
        return err
    return templates.TemplateResponse(
        "video_bg/create.html",
        {"request": request, "user": user},
    )


@router.get("/jobs", response_class=HTMLResponse)
async def video_bg_jobs(request: Request):
    """Página com a lista de jobs de vídeo com fundo."""
    user, err = _require_permission(request)
    if err:
        return err
    jobs = jobs_repo.get_all_jobs("video_bg", user_id=user["id"])
    return templates.TemplateResponse(
        "video_bg/jobs_list.html",
        {"request": request, "jobs": jobs, "user": user},
    )


@router.get("/video/{job_id}", response_class=HTMLResponse)
async def video_bg_detail(request: Request, job_id: str):
    """Tela de detalhes de um vídeo específico."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)

    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return HTMLResponse("<h1>Job não encontrado</h1>", status_code=404)
    if job_info.get("user_id") != user["id"]:
        return HTMLResponse("<h1>Acesso negado</h1>", status_code=403)

    drive = get_drive(TOKEN_FILE)
    try:
        metadata = await asyncio.get_event_loop().run_in_executor(
            None, drive.read_json, job_info["metadata_file_id"]
        )
    except Exception as e:
        metadata = {**job_info, "status": "error", "error": str(e)}

    drive_link = drive.get_folder_link(job_info["drive_folder_id"])

    return templates.TemplateResponse(
        "video_bg/video_detail.html",
        {
            "request": request,
            "job": metadata,
            "job_info": job_info,
            "drive_link": drive_link,
            "user": user,
        },
    )


# ── Submit ──

@router.post("/render")
async def render_video_bg(
    request: Request,
    title: str = Form(...),
    bg_video: UploadFile = File(...),
    bg_video_offset: float = Form(0.0),
    generate_subtitles: str = Form("on"),
    audio_source: str = Form("upload"),
    # Parâmetros de intro (card estilo Reddit)
    intro_enabled: str = Form("on"),
    intro_duration: float = Form(2.0),
    intro_theme: str = Form("light"),
    intro_color: str = Form("#FF4500"),
    intro_username: str = Form("Anônimo"),
    # Opção upload direto
    audio_file: Optional[UploadFile] = File(None),
    # Opção gerar via OmniVoice
    omni_voice_id: str = Form(""),
    omni_preset_id: str = Form(""),
    omni_text: str = Form(""),
):
    """Recebe o formulário, sobe tudo no Drive e publica no RabbitMQ."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if PERM not in user.get("permissions", []):
        return JSONResponse({"error": "Sem permissão"}, status_code=403)

    user_id = user["id"]

    try:
        # Validar vídeo de fundo
        if not bg_video or not bg_video.filename:
            return JSONResponse(
                {"error": "Envie um vídeo de fundo."},
                status_code=400,
            )

        # Validar áudio
        if audio_source == "upload":
            if not audio_file or not audio_file.filename:
                return JSONResponse(
                    {"error": "Envie um arquivo de áudio ou selecione 'Gerar com OmniVoice'."},
                    status_code=400,
                )
        elif audio_source == "omni":
            if not omni_text.strip():
                return JSONResponse(
                    {"error": "Informe o texto para gerar o áudio via OmniVoice."},
                    status_code=400,
                )
            if not omni_voice_id:
                return JSONResponse(
                    {"error": "Selecione uma voz para gerar o áudio."},
                    status_code=400,
                )
        else:
            return JSONResponse({"error": "Fonte de áudio inválida."}, status_code=400)

        video_type = "video_bg"
        vt = get_video_type(video_type)
        job_id = uuid.uuid4().hex[:8]
        drive = get_drive(TOKEN_FILE)

        job_folder_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.create_job_folder, title, job_id, vt.drive_folder_name
        )

        metadata: dict = {
            "job_id": job_id,
            "title": title,
            "video_type": video_type,
            "user_id": user_id,
            "bg_video_offset": bg_video_offset,
            "generate_subtitles": generate_subtitles in ("on", "true", "1", "yes"),
            "audio_source": audio_source,
            "intro_enabled": intro_enabled in ("on", "true", "1", "yes"),
            "intro_duration": intro_duration,
            "intro_theme": intro_theme,
            "intro_color": intro_color,
            "intro_username": intro_username,
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

        # Upload do vídeo de fundo
        bg_content = await bg_video.read()
        bg_ext = Path(bg_video.filename).suffix or ".mp4"
        bg_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_bytes, bg_content, f"bg_video{bg_ext}",
            job_folder_id, bg_video.content_type or "video/mp4",
        )
        metadata["files"]["bg_video"] = bg_file_id
        metadata["files"]["bg_video_ext"] = bg_ext

        # Upload ou geração do áudio
        if audio_source == "upload":
            audio_content = await audio_file.read()
            audio_ext = Path(audio_file.filename).suffix or ".mp3"
            audio_file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, audio_content, f"audio{audio_ext}",
                job_folder_id, audio_file.content_type or "audio/mpeg",
            )
            metadata["files"]["audio"] = audio_file_id
            metadata["files"]["audio_ext"] = audio_ext
        elif audio_source == "omni":
            # Dados para o worker gerar o áudio via OmniVoice
            from app import omni_voices as voices_mgr
            voice_info = voices_mgr.get_custom(omni_voice_id, user_id)
            if not voice_info:
                return JSONResponse(
                    {"error": "Voz não encontrada."},
                    status_code=400,
                )
            metadata["omni"] = {
                "voice_id": omni_voice_id,
                "ref_filename": voice_info["filename"],
                "ref_text": voice_info.get("reference_text", ""),
                "preset_id": omni_preset_id,
                "text": omni_text.strip(),
            }

            # Se tiver preset, carregar os parâmetros
            if omni_preset_id:
                from app.repositories import audio_presets
                preset = audio_presets.get_preset(omni_preset_id)
                if preset and preset["user_id"] == user_id:
                    metadata["omni"]["gen_params"] = {
                        k: v for k, v in preset.items()
                        if k not in ("id", "user_id", "name", "description",
                                     "created_at", "updated_at", "is_deleted")
                        and v is not None
                    }

        metadata_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_json, metadata, "metadata.json", job_folder_id
        )

        jobs_repo.save_job(metadata, job_folder_id, metadata_file_id)

        await publish_job(job_id, video_type)

        logger.info(f"[{job_id}] Job video_bg criado e publicado → Drive: {job_folder_id}")
        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.exception(f"Erro ao criar job video_bg: {e}")
        return JSONResponse({"error": f"Erro interno: {e}"}, status_code=500)
