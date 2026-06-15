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

import aio_pika
from fastapi import FastAPI, File, Form, Request, UploadFile, Header
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import jobs_store
from app.config import BASE_DIR, STATIC_DIR, TEMPLATES_DIR
from app.drive import get_drive
from app.parser import parse_conversation
from app.publisher import publish_job
from app.video_types import all_video_types, get_video_type
from app.routers import whatsapp

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

app.include_router(whatsapp.router)


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
                **job_info, "status": "unknown", "progress": 0,
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


@app.delete("/api/jobs/{job_id}")
async def api_delete_job(job_id: str, delete_drive: bool = False):
    """Remove um job. Opcionalmente remove a pasta do Drive também."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
        
    try:
        if delete_drive:
            drive = get_drive(TOKEN_FILE)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, drive.delete_file, job_info["drive_folder_id"])
            
        jobs_store.delete_job(job_id)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Erro ao remover job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ──────────────────────────────────────────────────────────────
# SSE: helpers
# ──────────────────────────────────────────────────────────────

async def _watch_disconnect(request: Request, stop_event: asyncio.Event) -> None:
    """
    Task independente: verifica request.is_disconnected() a cada 500ms.
    Seta stop_event quando detecta desconexao do cliente.
    Roda em paralelo ao loop SSE e nao depende de yields para funcionar.
    """
    while not stop_event.is_set():
        await asyncio.sleep(0.5)  # cede ao event loop — uvicorn pode processar TCP events
        try:
            if await request.is_disconnected():
                logger.info("SSE watcher: cliente desconectou")
                stop_event.set()
                return
        except Exception:
            pass


async def _create_sse_connection(routing_key: str):
    """
    Cria conexao aio_pika NAO-robusta (connect, nao connect_robust).
    Sem auto-reconexao: quando close() for chamado, encerra definitivamente.
    Declara fila exclusive com x-expires=30s como rede de seguranca:
    se por qualquer motivo close() nao rodar, o RabbitMQ destroi a fila apos 30s.
    """
    msg_queue: asyncio.Queue = asyncio.Queue()

    connection = await aio_pika.connect(RABBITMQ_URL)  # SEM auto-reconexao
    channel = await connection.channel()

    exchange = await channel.declare_exchange(
        "video_progress",
        aio_pika.ExchangeType.TOPIC,
        durable=True,
        auto_delete=False,
    )

    rabbit_queue = await channel.declare_queue(
        "",
        exclusive=True,
        auto_delete=True,
        durable=False,
        arguments={"x-expires": 30_000},  # some apos 30s sem consumer (safety net)
    )
    await rabbit_queue.bind(exchange, routing_key=routing_key)

    async def on_message(message: aio_pika.IncomingMessage):
        async with message.process():
            await msg_queue.put(message.body)

    await rabbit_queue.consume(on_message)
    return connection, msg_queue, rabbit_queue.name


def _sse_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────────
# SSE Global — 1 fila por sessao de navegador
# ──────────────────────────────────────────────────────────────

@app.get("/api/progress/stream")
async def progress_stream(request: Request):
    """
    SSE global: 1 fila exclusive por sessao.
    - Watcher task detecta disconnect em ~500ms (independente de yields).
    - finally() chama connection.close() → RabbitMQ destroi fila imediatamente.
    - x-expires=30s como ultima linha de defesa.
    """
    async def event_generator():
        connection = None
        stop_event = asyncio.Event()
        watcher: Optional[asyncio.Task] = None

        try:
            connection, msg_queue, qname = await _create_sse_connection(routing_key="#")
            logger.info(f"SSE global: fila criada → {qname}")

            watcher = asyncio.create_task(
                _watch_disconnect(request, stop_event),
                name=f"sse-watcher-{qname[-8:]}",
            )

            while not stop_event.is_set():
                try:
                    body = await asyncio.wait_for(msg_queue.get(), timeout=1.0)
                    if stop_event.is_set():
                        break
                    data = json.loads(body.decode())
                    yield f"data: {json.dumps(data, default=str)}\n\n"
                except asyncio.TimeoutError:
                    if stop_event.is_set():
                        break
                    yield ": keepalive\n\n"

            logger.info(f"SSE global: loop encerrado — fila: {qname}")

        except (asyncio.CancelledError, GeneratorExit):
            logger.info("SSE global: gerador cancelado")
        except Exception as e:
            logger.warning(f"SSE global: erro — {e}")
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
                logger.info("SSE global: conexao fechada → fila destruida")

    return _sse_response(event_generator())


# ──────────────────────────────────────────────────────────────
# SSE por Job — usado no video_detail
# ──────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/stream")
async def job_stream(request: Request, job_id: str):
    """
    SSE por job especifico.
    Mesma logica do SSE global, binding filtrado por job_id.
    Encerra automaticamente em status done|error.
    Fallback para polling no Drive se RabbitMQ falhar.
    """
    job_info = jobs_store.get_job(job_id)

    async def event_generator():
        connection = None
        stop_event = asyncio.Event()
        watcher: Optional[asyncio.Task] = None

        try:
            connection, msg_queue, qname = await _create_sse_connection(routing_key=job_id)
            logger.info(f"[{job_id}] SSE detail: fila criada → {qname}")

            watcher = asyncio.create_task(
                _watch_disconnect(request, stop_event),
                name=f"sse-watcher-{job_id}",
            )

            while not stop_event.is_set():
                try:
                    body = await asyncio.wait_for(msg_queue.get(), timeout=1.0)
                    if stop_event.is_set():
                        break
                    data = json.loads(body.decode())
                    yield f"data: {json.dumps(data, default=str)}\n\n"
                    if data.get("status") in ("done", "error"):
                        logger.info(f"[{job_id}] SSE encerrado — status: {data.get('status')}")
                        break
                except asyncio.TimeoutError:
                    if stop_event.is_set():
                        break
                    yield ": keepalive\n\n"

        except (asyncio.CancelledError, GeneratorExit):
            logger.info(f"[{job_id}] SSE gerador cancelado")
        except Exception as e:
            logger.warning(f"[{job_id}] SSE erro: {e} — fallback Drive")
            async for event in _stream_from_drive(job_id, job_info):
                yield event
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
                logger.info(f"[{job_id}] SSE: conexao fechada → fila destruida")

    return _sse_response(event_generator())


# ──────────────────────────────────────────────────────────────
# Fallback: polling no Drive
# ──────────────────────────────────────────────────────────────

async def _stream_from_drive(job_id: str, job_info: dict):
    """Fallback: polling no Drive caso RabbitMQ falhe."""
    loop = asyncio.get_event_loop()
    while True:
        if not job_info:
            yield f"data: {json.dumps({'error': 'Job não encontrado'})}\n\n"
            break

        metadata_file_id = job_info.get("metadata_file_id")
        drive = get_drive(TOKEN_FILE)

        if not metadata_file_id:
            try:
                metadata_file_id = await loop.run_in_executor(
                    None, drive.find_file_in_folder, job_info["drive_folder_id"], "metadata.json"
                )
                if metadata_file_id:
                    jobs_store.update_job(job_id, {"metadata_file_id": metadata_file_id})
                else:
                    yield f"data: {json.dumps({'status': 'error', 'error': 'metadata.json não encontrado'})}\n\n"
                    break
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
                break

        try:
            metadata = await loop.run_in_executor(None, drive.read_json, metadata_file_id)
            yield f"data: {json.dumps(metadata, default=str)}\n\n"
            if metadata.get("status") in ("done", "error"):
                break
            await asyncio.sleep(3)
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
            break


# ──────────────────────────────────────────────────────────────
# Outras rotas
# ──────────────────────────────────────────────────────────────

@app.get("/api/drive/media/{file_id}")
async def get_drive_media(file_id: str, range: str = Header(None)):
    """Retorna o conteúdo binário de um arquivo do Drive (usado para preview)."""
    drive = get_drive(TOKEN_FILE)
    loop = asyncio.get_event_loop()
    try:
        content = await loop.run_in_executor(None, drive.read_bytes, file_id)
        file_size = len(content)
        
        if range:
            start_str, end_str = range.replace("bytes=", "").split("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
            chunk = content[start:end+1]
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(chunk)),
            }
            return Response(content=chunk, status_code=206, headers=headers)
            
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size)
        }
        return Response(content=content, headers=headers)
    except Exception as e:
        logger.error(f"Erro ao obter mídia {file_id}: {e}")
        return Response(content=b"Not found", status_code=404)

@app.get("/api/jobs/{job_id}/details")
async def api_job_details(job_id: str):
    """Retorna os metadados brutos (JSON) de um job para listagem no modal de duplicação."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    drive = get_drive(TOKEN_FILE)
    try:
        loop = asyncio.get_event_loop()
        metadata = await loop.run_in_executor(None, drive.read_json, job_info["metadata_file_id"])
        return JSONResponse(metadata)
    except Exception as e:
        logger.error(f"Erro ao buscar metadados do job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/sync")
async def sync_drive(request: Request):
    """Sincroniza os jobs com o Drive manualmente."""
    drive = get_drive(TOKEN_FILE)
    await asyncio.get_event_loop().run_in_executor(None, jobs_store.sync_with_drive, drive)
    return {"status": "ok"}
