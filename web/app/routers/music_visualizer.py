"""Router Music Visualizer — imagem de fundo + logo + áudio → vídeo visualizador."""
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
from app.repositories import music_visualizer_templates as templates_repo
from app.video_types import get_video_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/music-visualizer", tags=["music_visualizer"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

PERM = "music_visualizer"


def _require_permission(request: Request):
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


# ── Páginas ──────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def mv_create(request: Request):
    user, err = _require_permission(request)
    if err:
        return err
    return templates.TemplateResponse(
        "music_visualizer/create.html",
        {"request": request, "user": user},
    )


@router.get("/jobs", response_class=HTMLResponse)
async def mv_jobs(request: Request):
    user, err = _require_permission(request)
    if err:
        return err
    jobs = jobs_repo.get_all_jobs("music_visualizer", user_id=user["id"])
    return templates.TemplateResponse(
        "music_visualizer/jobs_list.html",
        {"request": request, "jobs": jobs, "user": user},
    )


@router.get("/video/{job_id}", response_class=HTMLResponse)
async def mv_detail(request: Request, job_id: str):
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
        "music_visualizer/video_detail.html",
        {
            "request": request,
            "job": metadata,
            "job_info": job_info,
            "drive_link": drive_link,
            "user": user,
        },
    )


# ── Templates de configurações ────────────────────────────────────────────────

def _template_api_user(request: Request):
    user = get_current_user(request)
    if not user:
        return None, JSONResponse({"error": "Não autenticado"}, status_code=401)
    if PERM not in user.get("permissions", []):
        return None, JSONResponse({"error": "Sem permissão"}, status_code=403)
    return user, None


def _validate_template_payload(body: dict, require_name: bool = True):
    if not isinstance(body, dict):
        return None, JSONResponse({"error": "JSON inválido."}, status_code=400)
    name = body.get("name")
    if name is not None and not isinstance(name, str):
        return None, JSONResponse({"error": "O nome do template deve ser texto."}, status_code=400)
    if require_name:
        name = (name or "").strip()
        if not name:
            return None, JSONResponse({"error": "Informe o nome do template."}, status_code=400)
        if len(name) > 255:
            return None, JSONResponse({"error": "O nome deve ter no máximo 255 caracteres."}, status_code=400)
    elif name is not None:
        name = name.strip()
        if not name or len(name) > 255:
            return None, JSONResponse({"error": "Nome de template inválido."}, status_code=400)

    template_data = body.get("template_data")
    if template_data is not None and not isinstance(template_data, dict):
        return None, JSONResponse({"error": "template_data deve ser um objeto JSON."}, status_code=400)
    description = body.get("description")
    if description is not None:
        description = str(description).strip()
        if len(description) > 2000:
            return None, JSONResponse({"error": "A descrição deve ter no máximo 2000 caracteres."}, status_code=400)
    return {"name": name, "description": description, "template_data": template_data}, None


@router.get("/api/templates")
async def list_templates(request: Request):
    user, error = _template_api_user(request)
    if error:
        return error
    return JSONResponse({"templates": templates_repo.get_user_templates(user["id"])})


@router.get("/api/templates/{template_id}")
async def get_template(request: Request, template_id: str):
    user, error = _template_api_user(request)
    if error:
        return error
    template = templates_repo.get_template(template_id)
    if not template:
        return JSONResponse({"error": "Template não encontrado"}, status_code=404)
    if template["user_id"] != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)
    return JSONResponse({"template": template})


@router.post("/api/templates")
async def create_template(request: Request):
    user, error = _template_api_user(request)
    if error:
        return error
    try:
        payload, error = _validate_template_payload(await request.json())
        if error:
            return error
        template = templates_repo.create_template(
            user_id=user["id"], name=payload["name"],
            description=payload["description"] or "",
            template_data=payload["template_data"] or {},
        )
        return JSONResponse({"template": template}, status_code=201)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        logger.exception("Erro ao criar template do Music Visualizer")
        return JSONResponse({"error": "Não foi possível salvar o template."}, status_code=500)


@router.put("/api/templates/{template_id}")
async def update_template(request: Request, template_id: str):
    user, error = _template_api_user(request)
    if error:
        return error
    existing = templates_repo.get_template(template_id)
    if not existing:
        return JSONResponse({"error": "Template não encontrado"}, status_code=404)
    if existing["user_id"] != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)
    try:
        payload, error = _validate_template_payload(await request.json(), require_name=False)
        if error:
            return error
        if payload["name"] is None and payload["description"] is None and payload["template_data"] is None:
            return JSONResponse({"error": "Nenhuma alteração informada."}, status_code=400)
        ok = templates_repo.update_template(
            template_id, name=payload["name"], description=payload["description"],
            template_data=payload["template_data"],
        )
        if not ok:
            return JSONResponse({"error": "Falha ao atualizar"}, status_code=500)
        return JSONResponse({"ok": True})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        logger.exception("Erro ao atualizar template do Music Visualizer")
        return JSONResponse({"error": "Não foi possível atualizar o template."}, status_code=500)


@router.delete("/api/templates/{template_id}")
async def delete_template(request: Request, template_id: str):
    user, error = _template_api_user(request)
    if error:
        return error
    existing = templates_repo.get_template(template_id)
    if not existing:
        return JSONResponse({"error": "Template não encontrado"}, status_code=404)
    if existing["user_id"] != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)
    if not templates_repo.soft_delete_template(template_id):
        return JSONResponse({"error": "Falha ao excluir"}, status_code=500)
    return JSONResponse({"ok": True})


# ── Submit ────────────────────────────────────────────────────────────────────

@router.post("/render")
async def render_music_visualizer(
    request: Request,
    # Básico
    title: str = Form(...),
    audio_file: UploadFile = File(...),
    bg_image: UploadFile = File(...),
    logo_file: Optional[UploadFile] = File(None),
    # Círculo
    circle_radius: int = Form(180),
    circle_max_scale: float = Form(1.45),
    circle_border_color: str = Form("#ffffff"),
    circle_bg_color: str = Form("#000000cc"),
    circle_glow_color: str = Form("#ffffff"),
    circle_glow_intensity: float = Form(0.8),
    logo_text: str = Form("♫"),
    logo_font_size: int = Form(72),
    logo_font_color: str = Form("#ffffff"),
    # Ondas
    waves_enabled: str = Form("on"),
    wave_rings: int = Form(3),
    wave_color: str = Form("#ffffff"),
    wave_opacity_max: float = Form(0.6),
    # Fundo
    bg_zoom_speed: float = Form(0.04),
    bg_beat_shake: str = Form("on"),
    bg_beat_shake_px: int = Form(6),
    bg_brightness_boost: float = Form(0.18),
    bg_blur_ambient: float = Form(2.0),
    # Partículas
    particles_enabled: str = Form("on"),
    particle_count: int = Form(60),
    particle_color: str = Form("#ffffff"),
    particle_opacity_max: float = Form(0.55),
    particle_speed: float = Form(1.0),
    # Progresso
    progress_bar_enabled: str = Form("on"),
    progress_bar_color: str = Form("#ffffff"),
    progress_bar_position: str = Form("bottom"),
    # Título
    show_title: str = Form("on"),
    title_color: str = Form("#ffffff"),
    title_opacity: float = Form(0.85),
    title_position: str = Form("bottom-center"),
    # Áudio
    audio_sensitivity: float = Form(1.0),
    beat_threshold: float = Form(0.6),
    # Resolução
    width: int = Form(1920),
    height: int = Form(1080),
    fps: int = Form(30),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if PERM not in user.get("permissions", []):
        return JSONResponse({"error": "Sem permissão"}, status_code=403)

    if not audio_file or not audio_file.filename:
        return JSONResponse({"error": "Envie um arquivo de áudio."}, status_code=400)
    if not bg_image or not bg_image.filename:
        return JSONResponse({"error": "Envie uma imagem de fundo."}, status_code=400)

    try:
        video_type = "music_visualizer"
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
            "user_id": user["id"],
            "status": "pending",
            "progress": 0,
            "detail": "Aguardando worker...",
            "error": None,
            "created_at": datetime.now().isoformat(),
            "video_drive_id": None,
            "video_url": None,
            "drive_folder_id": job_folder_id,
            "files": {},
            # Todos os parâmetros do visualizador ficam dentro de "visualizer"
            "visualizer": {
                "width": width,
                "height": height,
                "fps": fps,
                "circle_radius": circle_radius,
                "circle_max_scale": circle_max_scale,
                "circle_border_color": circle_border_color,
                "circle_bg_color": circle_bg_color,
                "circle_glow_color": circle_glow_color,
                "circle_glow_intensity": circle_glow_intensity,
                "logo_text": logo_text,
                "logo_font_size": logo_font_size,
                "logo_font_color": logo_font_color,
                "waves_enabled": waves_enabled in ("on", "true", "1"),
                "wave_rings": wave_rings,
                "wave_color": wave_color,
                "wave_opacity_max": wave_opacity_max,
                "bg_zoom_speed": bg_zoom_speed,
                "bg_beat_shake": bg_beat_shake in ("on", "true", "1"),
                "bg_beat_shake_px": bg_beat_shake_px,
                "bg_brightness_boost": bg_brightness_boost,
                "bg_blur_ambient": bg_blur_ambient,
                "particles_enabled": particles_enabled in ("on", "true", "1"),
                "particle_count": particle_count,
                "particle_color": particle_color,
                "particle_opacity_max": particle_opacity_max,
                "particle_speed": particle_speed,
                "progress_bar_enabled": progress_bar_enabled in ("on", "true", "1"),
                "progress_bar_color": progress_bar_color,
                "progress_bar_position": progress_bar_position,
                "show_title": show_title in ("on", "true", "1"),
                "title_color": title_color,
                "title_opacity": title_opacity,
                "title_position": title_position,
                "audio_sensitivity": audio_sensitivity,
                "beat_threshold": beat_threshold,
            },
        }

        # Upload da imagem de fundo
        bg_content = await bg_image.read()
        bg_ext = Path(bg_image.filename).suffix or ".jpg"
        bg_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_bytes, bg_content, f"bg_image{bg_ext}",
            job_folder_id, bg_image.content_type or "image/jpeg",
        )
        metadata["files"]["bg_image"] = bg_file_id
        metadata["files"]["bg_image_ext"] = bg_ext

        # Upload da logo (opcional)
        if logo_file and logo_file.filename:
            logo_content = await logo_file.read()
            logo_ext = Path(logo_file.filename).suffix or ".png"
            logo_file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, logo_content, f"logo{logo_ext}",
                job_folder_id, logo_file.content_type or "image/png",
            )
            metadata["files"]["logo"] = logo_file_id
            metadata["files"]["logo_ext"] = logo_ext

        # Upload do áudio
        audio_content = await audio_file.read()
        audio_ext = Path(audio_file.filename).suffix or ".mp3"
        audio_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_bytes, audio_content, f"audio{audio_ext}",
            job_folder_id, audio_file.content_type or "audio/mpeg",
        )
        metadata["files"]["audio"] = audio_file_id
        metadata["files"]["audio_ext"] = audio_ext

        # Salvar metadata.json no Drive
        metadata_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_json, metadata, "metadata.json", job_folder_id
        )

        jobs_repo.save_job(metadata, job_folder_id, metadata_file_id)
        await publish_job(job_id, video_type)

        logger.info(f"[{job_id}] Job music_visualizer criado → Drive: {job_folder_id}")
        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.exception(f"Erro ao criar job music_visualizer: {e}")
        return JSONResponse({"error": f"Erro interno: {e}"}, status_code=500)
