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
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
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


@app.get("/jobs", response_class=HTMLResponse)
async def all_jobs(request: Request):
    """Página com a lista completa de jobs."""
    jobs = jobs_store.get_all_jobs()
    return templates.TemplateResponse(
        "jobs_list.html",
        {"request": request, "jobs": jobs},
    )


@app.get("/video/{job_id}", response_class=HTMLResponse)
async def video_detail(request: Request, job_id: str):
    """Tela de detalhes de um vídeo específico."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return HTMLResponse("<h1>Job não encontrado</h1>", status_code=404)

    drive = get_drive(TOKEN_FILE)
    try:
        metadata = await asyncio.get_event_loop().run_in_executor(
            None, drive.read_json, job_info["metadata_file_id"]
        )
    except Exception as e:
        metadata = {**job_info, "status": "error", "error": str(e)}

    # Buscar texto da conversa para preencher a edição
    conversa_text = ""
    conversa_file_id = metadata.get("files", {}).get("conversa")
    if conversa_file_id:
        try:
            bytes_content = await asyncio.get_event_loop().run_in_executor(
                None, drive.read_bytes, conversa_file_id
            )
            conversa_text = bytes_content.decode('utf-8', errors="replace")
        except Exception as e:
            logger.warning(f"Não foi possível ler a conversa do Drive: {e}")

    drive_link = drive.get_folder_link(job_info["drive_folder_id"])

    return templates.TemplateResponse(
        "video_detail.html",
        {
            "request": request,
            "job": metadata,
            "job_info": job_info,
            "drive_link": drive_link,
            "conversa_text": conversa_text,
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
        try:
            vt = get_video_type(video_type)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

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

        try:
            messages = parse_conversation(conv_text, conv_filename)
        except ValueError as e:
            return JSONResponse({"error": f"Erro ao parsear conversa: {e}"}, status_code=400)

        if not messages:
            return JSONResponse(
                {"error": "Nenhuma mensagem encontrada. Verifique o formato da conversa."},
                status_code=400,
            )

        job_id = uuid.uuid4().hex[:8]
        drive = get_drive(TOKEN_FILE)

        job_folder_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.create_job_folder, title, job_id, vt.drive_folder_name
        )

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

        conv_bytes = conv_text.encode("utf-8")
        conv_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_bytes, conv_bytes, "conversa.txt", job_folder_id, "text/plain",
        )
        metadata["files"]["conversa"] = conv_file_id

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

        imagens_folder_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.get_or_create_folder, "imagens", job_folder_id
        )
        metadata["files"]["imagens"] = {}
        metadata["files"]["imagens_folder_id"] = imagens_folder_id

        for img in conversation_images:
            if img and img.filename:
                content = await img.read()
                file_id = await asyncio.get_event_loop().run_in_executor(
                    None, drive.upload_bytes, content, img.filename,
                    imagens_folder_id, img.content_type or "image/jpeg",
                )
                metadata["files"]["imagens"][img.filename] = file_id

        metadata_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_json, metadata, "metadata.json", job_folder_id
        )

        jobs_store.add_job(
            job_id=job_id, title=title, video_type=video_type,
            drive_folder_id=job_folder_id, metadata_file_id=metadata_file_id,
        )

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

@app.post("/video/{job_id}/edit")
async def edit_video(
    job_id: str,
    title: str = Form(...),
    video_type: str = Form("whatsapp"),
    contact_name: str = Form("Contato"),
    contact_status: str = Form("online"),
    video_format: str = Form("vertical"),
    fps: int = Form(30),
    speed: float = Form(1.0),
    reading_speed: float = Form(1.0),
    scroll_speed: float = Form(1.0),
    animation_style: str = Form("fade"),
    conversation_text: str = Form(""),
    contact_photo: Optional[UploadFile] = File(None),
    wallpaper: Optional[UploadFile] = File(None),
    background_music: Optional[UploadFile] = File(None),
    conversation_images: List[UploadFile] = File(default=[]),
    active_image_names: str = Form("[]"),  # JSON array de nomes de imagens que devem permanecer
):
    """Atualiza as configs do vídeo no Drive e publica no RabbitMQ para recriar."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    drive = get_drive(TOKEN_FILE)
    loop = asyncio.get_event_loop()

    try:
        # 1. Ler metadata atual
        metadata = await loop.run_in_executor(
            None, drive.read_json, job_info["metadata_file_id"]
        )

        # 2. Atualizar campos
        metadata.update({
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
            "detail": "Aguardando worker (Edição)...",
            "error": None,
        })
        
        # Como o worker apagará o vídeo antigo do Drive se ele tiver o mesmo nome?
        # O Drive permite arquivos com mesmo nome, então o ideal é só remover
        # ou o worker fará upload de outro. Mas deixamos o worker lidar com o upload.

        # 3. Atualizar a conversa se modificada
        if conversation_text.strip():
            # Apenas fazemos um update no arquivo conversa.txt se ele existir,
            # ou criamos um novo
            conversa_file_id = metadata.get("files", {}).get("conversa")
            conv_bytes = conversation_text.strip().encode("utf-8")
            if conversa_file_id:
                # Update no arquivo
                from googleapiclient.http import MediaIoBaseUpload
                from io import BytesIO
                media = MediaIoBaseUpload(BytesIO(conv_bytes), mimetype="text/plain")
                await loop.run_in_executor(
                    None, 
                    lambda: drive.service.files().update(fileId=conversa_file_id, media_body=media).execute(num_retries=5)
                )
            else:
                # Se não tinha, cria
                new_id = await loop.run_in_executor(
                    None, drive.upload_bytes, conv_bytes, "conversa.txt", job_info["drive_folder_id"], "text/plain"
                )
                metadata["files"]["conversa"] = new_id

        # 4. Processar novas mídias e atualizar metadata["files"]
        job_folder_id = job_info["drive_folder_id"]

        # 4.1 Foto de Perfil
        if contact_photo and contact_photo.filename:
            content = await contact_photo.read()
            ext = Path(contact_photo.filename).suffix or ".jpg"
            file_id = await loop.run_in_executor(
                None, drive.upload_bytes, content, f"foto_perfil{ext}", job_folder_id, "image/jpeg"
            )
            metadata["files"]["foto_perfil"] = file_id
            metadata["files"]["foto_perfil_ext"] = ext

        # 4.2 Papel de Parede
        if wallpaper and wallpaper.filename:
            content = await wallpaper.read()
            ext = Path(wallpaper.filename).suffix or ".jpg"
            file_id = await loop.run_in_executor(
                None, drive.upload_bytes, content, f"papel_parede{ext}", job_folder_id, "image/jpeg"
            )
            metadata["files"]["papel_parede"] = file_id
            metadata["files"]["papel_parede_ext"] = ext

        # 4.3 Música de Fundo
        if background_music and background_music.filename:
            content = await background_music.read()
            ext = Path(background_music.filename).suffix or ".mp3"
            file_id = await loop.run_in_executor(
                None, drive.upload_bytes, content, f"musica{ext}", job_folder_id, "audio/mpeg"
            )
            metadata["files"]["musica"] = file_id
            metadata["files"]["musica_ext"] = ext

        # 4.4 Imagens da Conversa (Sincronização)
        if "imagens" not in metadata["files"]:
            metadata["files"]["imagens"] = {}
            metadata["files"]["imagens_folder_id"] = await loop.run_in_executor(
                None, drive.get_or_create_folder, "imagens", job_folder_id
            )
            
        imagens_folder_id = metadata["files"]["imagens_folder_id"]
        
        # Limpar imagens removidas pelo usuário baseado nas tags
        try:
            active_names = json.loads(active_image_names)
            current_images = metadata["files"]["imagens"]
            # Manter apenas as que estão na lista de ativas
            metadata["files"]["imagens"] = {
                name: fid for name, fid in current_images.items() if name in active_names
            }
        except Exception as e:
            logger.warning(f"Erro ao parsear active_image_names: {e}")

        # Subir novas imagens da conversa
        for img in conversation_images:
            if img and img.filename:
                content = await img.read()
                file_id = await loop.run_in_executor(
                    None, drive.upload_bytes, content, img.filename,
                    imagens_folder_id, img.content_type or "image/jpeg",
                )
                metadata["files"]["imagens"][img.filename] = file_id

        # 5. Salvar metadata.json modificado
        await loop.run_in_executor(
            None, drive.update_json, job_info["metadata_file_id"], metadata
        )

        # 6. Publicar no RabbitMQ
        await publish_job(job_id, video_type)

        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.error(f"Erro ao editar/recriar job: {e}")
        return JSONResponse({"error": f"Erro interno: {e}"}, status_code=500)


@app.post("/api/sync")
async def sync_drive(request: Request):
    """Sincroniza os jobs com o Drive manualmente."""
    drive = get_drive(TOKEN_FILE)
    await asyncio.get_event_loop().run_in_executor(None, jobs_store.sync_with_drive, drive)
    return {"status": "ok"}
