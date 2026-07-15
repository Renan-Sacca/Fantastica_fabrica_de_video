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
        layers_json = form_data.get("layers_json", "[]")

        # Animações e elementos agora são objetos expandidos com tempo/intensidade
        animations_meta: list = _json.loads(form_data.get("animations_json", "[]"))
        elements_meta: list = _json.loads(form_data.get("elements_json", "[]"))
        custom_anims_meta: list = _json.loads(form_data.get("custom_anims_json", "[]"))

        audio_items_meta: list = _json.loads(form_data.get("audio_items_json", "[]"))
        bg_segments_meta: list = _json.loads(form_data.get("bg_segments_json", "[]"))
        overlay_segments_meta: list = _json.loads(form_data.get("overlay_segments_json", "[]"))
        text_overlays_meta: list = _json.loads(form_data.get("text_overlays_json", "[]"))
        sec_audios_meta: list = _json.loads(form_data.get("sec_audios_json", "[]"))

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
            "animations": animations_meta,
            "elements": elements_meta,
            "custom_anims": [],
            "text_overlays": text_overlays_meta,
            "secondary_audios": [],
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
            trim_start = item_meta.get("trim_start")
            trim_end = item_meta.get("trim_end")

            if item_type == "upload" or item_type == "omni_pregenerated":
                # Tanto upload normal quanto IA pré-gerada enviam arquivo via FormData
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
                entry = {
                    "index": idx,
                    "type": "upload",  # Normaliza para "upload" pois já tem o arquivo
                    "volume": volume,
                    "file_id": audio_file_id,
                    "file_ext": audio_ext,
                }
                if trim_start is not None:
                    entry["trim_start"] = float(trim_start)
                if trim_end is not None:
                    entry["trim_end"] = float(trim_end)
                metadata["audio_items"].append(entry)

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
                if trim_start is not None:
                    omni_entry["trim_start"] = float(trim_start)
                if trim_end is not None:
                    omni_entry["trim_end"] = float(trim_end)

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

        # ── Upload das animações customizadas ──
        for anim_meta in custom_anims_meta:
            idx = anim_meta["index"]
            anim_upload: Optional[UploadFile] = form_data.get(f"custom_anim_{idx}")
            if not anim_upload or not anim_upload.filename:
                continue
            anim_content = await anim_upload.read()
            anim_ext = Path(anim_upload.filename).suffix or ".mp4"
            anim_file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, anim_content, f"custom_anim_{idx}{anim_ext}",
                job_folder_id, anim_upload.content_type or "video/mp4",
            )
            metadata["custom_anims"].append({
                "index": idx,
                "file_id": anim_file_id,
                "file_ext": anim_ext,
                "start_sec": anim_meta.get("start_sec", 0),
                "end_sec": anim_meta.get("end_sec"),
                "position": anim_meta.get("position", "centro"),
                "scale": anim_meta.get("scale", 30),
                "loop": anim_meta.get("loop", True),
            })

        # ── Áudios secundários (múltiplos) ──
        for sa_meta in sec_audios_meta:
            idx = sa_meta["index"]
            sa_upload: Optional[UploadFile] = form_data.get(f"sec_audio_file_{idx}")
            if not sa_upload or not getattr(sa_upload, "filename", None):
                continue
            sa_content = await sa_upload.read()
            sa_ext = Path(sa_upload.filename).suffix or ".mp3"
            sa_file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, sa_content, f"sec_audio_{idx}{sa_ext}",
                job_folder_id, sa_upload.content_type or "audio/mpeg",
            )
            metadata["secondary_audios"].append({
                "index": idx,
                "file_id": sa_file_id,
                "file_ext": sa_ext,
                "volume": sa_meta.get("volume", 20),
                "start_sec": sa_meta.get("start_sec", 0),
                "end_sec": sa_meta.get("end_sec"),
                "loop": sa_meta.get("loop", True),
            })

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
