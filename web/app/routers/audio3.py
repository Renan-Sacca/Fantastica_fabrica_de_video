"""Geração de áudio com OmniVoice — página, vozes, geração, histórico e SSE.

Salva o áudio no Google Drive e o registro no MySQL. Histórico por usuário.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

import aio_pika
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app import omni_voices as voices_mgr
from app.auth import get_current_user
from app.config import (
    BASE_DIR,
    RABBITMQ_OMNI_PROGRESS_EXCHANGE,
    RABBITMQ_URL,
    TEMPLATES_DIR,
)
from app.drive import get_drive
from app.publisher import publish_omni_job
from app.repositories import audio_jobs as audio_repo

router = APIRouter(prefix="/audio3", tags=["audio3"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
logger = logging.getLogger(__name__)

TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))
PERM = "omnivoice_audio"
DRIVE_TYPE_FOLDER = "OmniVoiceAudios"


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


def _to_bool(v, default):
    if v is None or v == "":
        return default
    return str(v).strip().lower() in ("1", "true", "on", "yes", "sim")


def _to_float(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _to_int(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


@router.get("", response_class=HTMLResponse)
async def audio3_page(request: Request):
    user, err = _require_permission(request)
    if err:
        return err
    return templates.TemplateResponse(
        "audio3/create.html", {"request": request, "user": user}
    )


@router.get("/history", response_class=HTMLResponse)
async def audio3_history(request: Request):
    user, err = _require_permission(request)
    if err:
        return err
    jobs = audio_repo.get_all_jobs(user_id=user["id"])
    return templates.TemplateResponse(
        "audio3/history.html", {"request": request, "user": user, "jobs": jobs}
    )


# ── Vozes de referência ──

@router.get("/api/voices")
async def get_voices(request: Request):
    user, err = _require_permission(request)
    if err:
        return JSONResponse({"error": "Sem acesso"}, status_code=403)
    return JSONResponse({"custom": voices_mgr.list_custom()})


@router.post("/api/voices")
async def create_voice(
    request: Request,
    name: str = Form(...),
    reference_text: str = Form(""),
    reference_audio: UploadFile = File(...),
):
    user, err = _require_permission(request)
    if err:
        return JSONResponse({"error": "Sem acesso"}, status_code=403)
    if not name.strip():
        return JSONResponse({"error": "Informe um nome para a voz."}, status_code=400)
    if not reference_audio or not reference_audio.filename:
        return JSONResponse({"error": "Envie um áudio de referência."}, status_code=400)
    content = await reference_audio.read()
    if len(content) < 1024:
        return JSONResponse({"error": "Áudio muito curto/inválido."}, status_code=400)
    voice = voices_mgr.save_custom(name, content, reference_audio.filename, reference_text)
    return JSONResponse({"voice": voice})


@router.delete("/api/voices/{voice_id}")
async def remove_voice(request: Request, voice_id: str):
    user, err = _require_permission(request)
    if err:
        return JSONResponse({"error": "Sem acesso"}, status_code=403)
    if not voices_mgr.delete_custom(voice_id):
        return JSONResponse({"error": "Voz não encontrada."}, status_code=404)
    return JSONResponse({"ok": True})


# ── Geração ──

@router.post("/api/generate")
async def generate_audio(
    request: Request,
    text: str = Form(...),
    title: str = Form(""),
    mode: str = Form("auto"),
    voice: str = Form(""),
    instruct: str = Form(""),
    num_step: str = Form(""),
    guidance_scale: str = Form(""),
    t_shift: str = Form(""),
    position_temperature: str = Form(""),
    class_temperature: str = Form(""),
    layer_penalty_factor: str = Form(""),
    speed: str = Form(""),
    duration: str = Form(""),
    audio_chunk_duration: str = Form(""),
    audio_chunk_threshold: str = Form(""),
    language_id: str = Form(""),
    denoise: str = Form(""),
    preprocess_prompt: str = Form(""),
    postprocess_output: str = Form(""),
):
    user, err = _require_permission(request)
    if err:
        return JSONResponse({"error": "Sem acesso"}, status_code=403)
    if not text.strip():
        return JSONResponse({"error": "Digite um texto para gerar o áudio."}, status_code=400)

    ref_filename = None
    ref_text = ""
    if mode == "clone":
        info = voices_mgr.get_custom(voice)
        if not info:
            return JSONResponse({"error": "Voz de referência não encontrada."}, status_code=400)
        ref_filename = info["filename"]
        ref_text = info.get("reference_text", "")
    elif mode == "design":
        if not instruct.strip():
            return JSONResponse({"error": "Descreva os atributos da voz (Voice Design)."}, status_code=400)

    gen_params: dict = {}
    for key, val in [
        ("num_step", _to_int(num_step)),
        ("guidance_scale", _to_float(guidance_scale)),
        ("t_shift", _to_float(t_shift)),
        ("position_temperature", _to_float(position_temperature)),
        ("class_temperature", _to_float(class_temperature)),
        ("layer_penalty_factor", _to_float(layer_penalty_factor)),
        ("speed", _to_float(speed)),
        ("duration", _to_float(duration)),
        ("audio_chunk_duration", _to_float(audio_chunk_duration)),
        ("audio_chunk_threshold", _to_float(audio_chunk_threshold)),
        ("language_id", language_id.strip() or None),
    ]:
        if val is not None:
            gen_params[key] = val
    if denoise != "":
        gen_params["denoise"] = _to_bool(denoise, True)
    if preprocess_prompt != "":
        gen_params["preprocess_prompt"] = _to_bool(preprocess_prompt, True)
    if postprocess_output != "":
        gen_params["postprocess_output"] = _to_bool(postprocess_output, True)

    job_id = uuid.uuid4().hex[:8]
    final_title = (title.strip() or text.strip()[:40] or "Áudio")

    # Cria a pasta no Drive e sobe o metadata
    loop = asyncio.get_event_loop()
    drive_folder_id = None
    metadata_file_id = None
    try:
        drive = get_drive(TOKEN_FILE)

        def _create_folder():
            root = drive.get_or_create_folder("FantasticaFabricaDeVideo")
            type_folder = drive.get_or_create_folder(DRIVE_TYPE_FOLDER, root)
            criados = drive.get_or_create_folder("Criados", type_folder)
            return drive.get_or_create_folder(f"{final_title}-{job_id}", criados)

        drive_folder_id = await loop.run_in_executor(None, _create_folder)

        metadata = {
            "job_id": job_id,
            "title": final_title,
            "text": text.strip(),
            "mode": mode,
            "instruct": instruct.strip(),
            "ref_text": ref_text,
            "gen_params": gen_params,
            "user_id": user["id"],
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        metadata_file_id = await loop.run_in_executor(
            None, drive.upload_json, metadata, "metadata.json", drive_folder_id
        )
    except Exception as e:
        logger.warning(f"[{job_id}] Falha ao criar pasta/metadata no Drive: {e}")

    # Registro no MySQL
    audio_repo.create_job(
        job_id, user["id"], final_title, text.strip(), mode, instruct.strip(),
        drive_folder_id=drive_folder_id, metadata_file_id=metadata_file_id,
    )

    await publish_omni_job(
        job_id, text.strip(), mode, ref_filename, ref_text, instruct.strip(),
        gen_params, drive_folder_id=drive_folder_id,
    )
    logger.info(f"[{job_id}] Job OmniVoice enfileirado (modo={mode}).")
    return JSONResponse({"job_id": job_id, "status": "queued"})


# ── Histórico: ações ──

@router.delete("/api/jobs/{job_id}")
async def delete_job(request: Request, job_id: str):
    user, err = _require_permission(request)
    if err:
        return JSONResponse({"error": "Sem acesso"}, status_code=403)
    job = audio_repo.get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    if job.get("user_id") != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)
    # Move a pasta no Drive para Deletados (best-effort)
    if job.get("drive_folder_id"):
        try:
            drive = get_drive(TOKEN_FILE)
            await asyncio.get_event_loop().run_in_executor(
                None, drive.move_to_deleted, job["drive_folder_id"], DRIVE_TYPE_FOLDER
            )
        except Exception as e:
            logger.warning(f"[{job_id}] Falha ao mover pasta no Drive: {e}")
    audio_repo.soft_delete_job(job_id)
    return {"status": "ok"}


@router.patch("/api/jobs/{job_id}/rename")
async def rename_job(request: Request, job_id: str):
    user, err = _require_permission(request)
    if err:
        return JSONResponse({"error": "Sem acesso"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON inválido"}, status_code=400)
    new_title = (body.get("title") or "").strip()
    if not new_title:
        return JSONResponse({"error": "Título não pode ser vazio"}, status_code=400)
    job = audio_repo.get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    if job.get("user_id") != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)
    if job.get("drive_folder_id"):
        try:
            drive = get_drive(TOKEN_FILE)
            await asyncio.get_event_loop().run_in_executor(
                None, drive.rename_folder, job["drive_folder_id"], f"{new_title}-{job_id}"
            )
        except Exception as e:
            logger.warning(f"[{job_id}] Falha ao renomear pasta no Drive: {e}")
    audio_repo.rename_job(job_id, new_title)
    return {"status": "ok", "title": new_title}


# ── SSE de progresso ──

async def _create_sse_connection(routing_key: str):
    msg_queue: asyncio.Queue = asyncio.Queue()
    connection = await aio_pika.connect(RABBITMQ_URL)
    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        RABBITMQ_OMNI_PROGRESS_EXCHANGE,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
        auto_delete=False,
    )
    rabbit_queue = await channel.declare_queue(
        "", exclusive=True, auto_delete=True, durable=False,
        arguments={"x-expires": 60_000},
    )
    await rabbit_queue.bind(exchange, routing_key=routing_key)

    async def on_message(message: aio_pika.IncomingMessage):
        async with message.process():
            await msg_queue.put(message.body)

    await rabbit_queue.consume(on_message)
    return connection, msg_queue


async def _watch_disconnect(request: Request, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(0.5)
        try:
            if await request.is_disconnected():
                stop_event.set()
                return
        except Exception:
            pass


@router.get("/api/progress/{job_id}/stream")
async def progress_stream(request: Request, job_id: str):
    async def event_generator():
        connection = None
        stop_event = asyncio.Event()
        watcher: Optional[asyncio.Task] = None
        try:
            connection, msg_queue = await _create_sse_connection(routing_key=job_id)
            watcher = asyncio.create_task(_watch_disconnect(request, stop_event))

            while not stop_event.is_set():
                try:
                    body = await asyncio.wait_for(msg_queue.get(), timeout=1.0)
                    if stop_event.is_set():
                        break
                    data = json.loads(body.decode())
                    yield f"data: {json.dumps(data, default=str)}\n\n"
                    if data.get("status") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    if stop_event.is_set():
                        break
                    yield ": keepalive\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        except Exception as e:
            logger.warning(f"[{job_id}] SSE Omni erro: {e}")
            yield f"data: {json.dumps({'status': 'error', 'detail': str(e)})}\n\n"
        finally:
            stop_event.set()
            if watcher and not watcher.done():
                watcher.cancel()
                try:
                    await watcher
                except (asyncio.CancelledError, Exception):
                    pass
            if connection and not connection.is_closed:
                await connection.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
