"""Router de Vídeo Compositor — composição visual avançada por camadas.

Fluxo:
1. Usuário configura camadas (fundo, imagens, animações, áudios)
2. Define posições, volumes e ordem das camadas
3. Worker processa: compõe tudo via FFmpeg em um vídeo final
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.config import BASE_DIR, TEMPLATES_DIR
from app.drive import get_drive
from app.publisher import publish_job
from app.repositories import jobs as jobs_repo
from app.video_types import get_video_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video-compositor", tags=["video_compositor"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

PERM = "video_compositor"


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
async def compositor_create(request: Request):
    """Página principal de criação do Vídeo Compositor."""
    user, err = _require_permission(request)
    if err:
        return err
    return templates.TemplateResponse(
        "video_compositor/create.html",
        {"request": request, "user": user},
    )


@router.get("/jobs", response_class=HTMLResponse)
async def compositor_jobs(request: Request):
    """Página com a lista de jobs do Vídeo Compositor."""
    user, err = _require_permission(request)
    if err:
        return err
    jobs = jobs_repo.get_all_jobs("video_compositor", user_id=user["id"])
    return templates.TemplateResponse(
        "video_compositor/jobs_list.html",
        {"request": request, "jobs": jobs, "user": user},
    )


@router.get("/video/{job_id}", response_class=HTMLResponse)
async def compositor_detail(request: Request, job_id: str):
    """Tela de detalhes de um vídeo compositor específico."""
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
        "video_compositor/video_detail.html",
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
async def render_compositor(request: Request):
    """Recebe o formulário do compositor v2 (múltiplos áudios e imagens por segmento)."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if PERM not in user.get("permissions", []):
        return JSONResponse({"error": "Sem permissão"}, status_code=403)

    user_id = user["id"]

    try:
        import json as _json

        form_data = await request.form()

        title = (form_data.get("title") or "").strip()
        if not title:
            return JSONResponse({"error": "Informe o título do vídeo."}, status_code=400)

        resolution = form_data.get("resolution", "1080x1920")
        secondary_audio_volume = float(form_data.get("secondary_audio_volume", 20.0))
        animations_json = form_data.get("animations_json", "[]")
        elements_json = form_data.get("elements_json", "[]")
        layers_json = form_data.get("layers_json", "[]")

        audio_items_meta: list = _json.loads(form_data.get("audio_items_json", "[]"))
        bg_segments_meta: list = _json.loads(form_data.get("bg_segments_json", "[]"))
        overlay_segments_meta: list = _json.loads(form_data.get("overlay_segments_json", "[]"))

        # Validações básicas
        if not audio_items_meta:
            return JSONResponse({"error": "Adicione ao menos um áudio principal."}, status_code=400)
        if not bg_segments_meta:
            return JSONResponse({"error": "Adicione ao menos uma imagem de fundo."}, status_code=400)

        # Parsear resolução
        try:
            res_w, res_h = resolution.split("x")
            res_w, res_h = int(res_w), int(res_h)
        except (ValueError, AttributeError):
            res_w, res_h = 1080, 1920

        video_type = "video_compositor"
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
            "resolution": {"width": res_w, "height": res_h},
            "secondary_audio_volume": secondary_audio_volume,
            "animations": _json.loads(animations_json),
            "elements": _json.loads(elements_json),
            "layers": _json.loads(layers_json),
            "audio_items": [],
            "bg_segments": [],
            "overlay_segments": [],
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

        # ── Upload dos áudios principais ──
        for item_meta in audio_items_meta:
            idx = item_meta["index"]
            item_type = item_meta.get("type", "upload")
            volume = item_meta.get("volume", 100)

            if item_type == "upload":
                audio_upload: Optional[UploadFile] = form_data.get(f"audio_file_{idx}")
                if not audio_upload or not audio_upload.filename:
                    return JSONResponse(
                        {"error": f"Áudio {idx+1}: envie um arquivo de áudio."},
                        status_code=400,
                    )
                audio_content = await audio_upload.read()
                audio_ext = Path(audio_upload.filename).suffix or ".mp3"
                audio_file_id = await asyncio.get_event_loop().run_in_executor(
                    None, drive.upload_bytes, audio_content, f"audio_{idx}{audio_ext}",
                    job_folder_id, audio_upload.content_type or "audio/mpeg",
                )
                metadata["audio_items"].append({
                    "index": idx,
                    "type": "upload",
                    "volume": volume,
                    "file_id": audio_file_id,
                    "file_ext": audio_ext,
                })

            elif item_type == "omni":
                text = (item_meta.get("text") or "").strip()
                if not text:
                    return JSONResponse(
                        {"error": f"Áudio {idx+1}: informe o texto para a IA."},
                        status_code=400,
                    )
                mode = item_meta.get("mode", "clone")
                voice_id = item_meta.get("voice_id", "")
                instruct = item_meta.get("instruct", "")
                preset_id = item_meta.get("preset_id", "")
                gen_params = item_meta.get("gen_params", {})

                omni_entry: dict = {
                    "index": idx,
                    "type": "omni",
                    "volume": volume,
                    "text": text,
                    "mode": mode,
                    "instruct": instruct,
                    "preset_id": preset_id,
                    "gen_params": gen_params,
                }

                if mode == "clone":
                    if not voice_id:
                        return JSONResponse(
                            {"error": f"Áudio {idx+1}: selecione uma voz para clonagem."},
                            status_code=400,
                        )
                    from app import omni_voices as voices_mgr
                    voice_info = voices_mgr.get_custom(voice_id, user_id)
                    if not voice_info:
                        return JSONResponse(
                            {"error": f"Áudio {idx+1}: voz não encontrada."},
                            status_code=400,
                        )
                    omni_entry["voice_id"] = voice_id
                    omni_entry["ref_filename"] = voice_info["filename"]
                    omni_entry["ref_text"] = voice_info.get("reference_text", "")

                if preset_id:
                    from app.repositories import audio_presets
                    preset = audio_presets.get_preset(preset_id)
                    if preset and preset["user_id"] == user_id:
                        preset_params = {
                            k: v for k, v in preset.items()
                            if k not in ("id", "user_id", "name", "description",
                                         "created_at", "updated_at", "is_deleted")
                            and v is not None
                        }
                        # preset_params override gen_params from form
                        merged = {**preset_params, **gen_params}
                        omni_entry["gen_params"] = merged

                metadata["audio_items"].append(omni_entry)

        # ── Upload das imagens de fundo ──
        for seg_meta in bg_segments_meta:
            idx = seg_meta["index"]
            bg_upload: Optional[UploadFile] = form_data.get(f"bg_image_{idx}")
            if not bg_upload or not bg_upload.filename:
                return JSONResponse(
                    {"error": f"Imagem de fundo {idx+1}: envie uma imagem."},
                    status_code=400,
                )
            bg_content = await bg_upload.read()
            bg_ext = Path(bg_upload.filename).suffix or ".png"
            bg_file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, bg_content, f"bg_image_{idx}{bg_ext}",
                job_folder_id, bg_upload.content_type or "image/png",
            )
            metadata["bg_segments"].append({
                "index": idx,
                "file_id": bg_file_id,
                "file_ext": bg_ext,
                "start_sec": seg_meta.get("start_sec", 0),
                "end_sec": seg_meta.get("end_sec"),  # None = até fim
            })

        # ── Upload das imagens sobrepostas ──
        for seg_meta in overlay_segments_meta:
            idx = seg_meta["index"]
            ov_upload: Optional[UploadFile] = form_data.get(f"overlay_image_{idx}")
            if not ov_upload or not ov_upload.filename:
                continue  # sobrepostas são opcionais
            ov_content = await ov_upload.read()
            ov_ext = Path(ov_upload.filename).suffix or ".png"
            ov_file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, ov_content, f"overlay_image_{idx}{ov_ext}",
                job_folder_id, ov_upload.content_type or "image/png",
            )
            metadata["overlay_segments"].append({
                "index": idx,
                "file_id": ov_file_id,
                "file_ext": ov_ext,
                "start_sec": seg_meta.get("start_sec", 0),
                "end_sec": seg_meta.get("end_sec"),
                "position": seg_meta.get("position", "centro"),
                "scale": seg_meta.get("scale", 50),
                # Campos de controle fino (opcionais)
                "px_width":  seg_meta.get("px_width"),
                "px_height": seg_meta.get("px_height"),
                "px_x":      seg_meta.get("px_x"),
                "px_y":      seg_meta.get("px_y"),
            })

        # ── Áudio secundário ──
        secondary_audio_file: Optional[UploadFile] = form_data.get("secondary_audio_file")
        if secondary_audio_file and getattr(secondary_audio_file, "filename", None):
            sec_content = await secondary_audio_file.read()
            sec_ext = Path(secondary_audio_file.filename).suffix or ".mp3"
            sec_file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, sec_content, f"secondary_audio{sec_ext}",
                job_folder_id, secondary_audio_file.content_type or "audio/mpeg",
            )
            metadata["files"]["secondary_audio"] = sec_file_id
            metadata["files"]["secondary_audio_ext"] = sec_ext

        # Salvar metadata
        metadata_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_json, metadata, "metadata.json", job_folder_id
        )

        jobs_repo.save_job(metadata, job_folder_id, metadata_file_id)
        await publish_job(job_id, video_type)

        logger.info(f"[{job_id}] Job video_compositor v2 criado → Drive: {job_folder_id}")
        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.exception(f"Erro ao criar job video_compositor: {e}")
        return JSONResponse({"error": f"Erro interno: {e}"}, status_code=500)
