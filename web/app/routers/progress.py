import asyncio
import json
import logging
import os
from typing import Optional

import aio_pika
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.config import BASE_DIR, RABBITMQ_URL
from app.drive import get_drive
from app.repositories import jobs as jobs_repo

router = APIRouter(prefix="/api", tags=["progress"])
logger = logging.getLogger(__name__)

TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

async def _watch_disconnect(request: Request, stop_event: asyncio.Event) -> None:
    """
    Task independente: verifica request.is_disconnected() a cada 500ms.
    Seta stop_event quando detecta desconexao do cliente.
    Roda em paralelo ao loop SSE e nao depende de yields para funcionar.
    """
    while not stop_event.is_set():
        await asyncio.sleep(0.5)
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
    """
    msg_queue: asyncio.Queue = asyncio.Queue()

    connection = await aio_pika.connect(RABBITMQ_URL)
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
        arguments={"x-expires": 30_000},
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

@router.get("/progress/stream")
async def progress_stream(request: Request):
    """SSE global: 1 fila exclusive por sessao."""
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

@router.get("/jobs/{job_id}/stream")
async def job_stream(request: Request, job_id: str):
    """SSE por job especifico."""
    job_info = jobs_repo.get_job(job_id)

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
                    jobs_repo.update_basic(job_id, metadata_file_id=metadata_file_id)
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


# ── SSE para Correção de Texto (agente IA) ──

async def _create_sse_connection_correction(routing_key: str):
    """Cria conexão SSE para o exchange de correção de texto."""
    msg_queue: asyncio.Queue = asyncio.Queue()

    connection = await aio_pika.connect(RABBITMQ_URL)
    channel = await connection.channel()

    exchange = await channel.declare_exchange(
        "text_correction_progress",
        aio_pika.ExchangeType.TOPIC,
        durable=True,
        auto_delete=False,
    )

    rabbit_queue = await channel.declare_queue(
        "",
        exclusive=True,
        auto_delete=True,
        durable=False,
        arguments={"x-expires": 30_000},
    )
    await rabbit_queue.bind(exchange, routing_key=routing_key)

    async def on_message(message: aio_pika.IncomingMessage):
        async with message.process():
            await msg_queue.put(message.body)

    await rabbit_queue.consume(on_message)
    return connection, msg_queue, rabbit_queue.name


@router.get("/correction/{job_id}/stream")
async def correction_stream(request: Request, job_id: str):
    """SSE para acompanhar o progresso de um job de correção de texto."""

    async def event_generator():
        connection = None
        stop_event = asyncio.Event()
        watcher: Optional[asyncio.Task] = None

        try:
            connection, msg_queue, qname = await _create_sse_connection_correction(
                routing_key=job_id
            )
            logger.info(f"[{job_id}] SSE correção: fila criada → {qname}")

            watcher = asyncio.create_task(
                _watch_disconnect(request, stop_event),
                name=f"sse-correction-{job_id}",
            )

            while not stop_event.is_set():
                try:
                    body = await asyncio.wait_for(msg_queue.get(), timeout=1.0)
                    if stop_event.is_set():
                        break
                    data = json.loads(body.decode())
                    yield f"data: {json.dumps(data, default=str)}\n\n"
                    if data.get("status") in ("done", "error"):
                        logger.info(
                            f"[{job_id}] SSE correção encerrado — status: {data.get('status')}"
                        )
                        break
                except asyncio.TimeoutError:
                    if stop_event.is_set():
                        break
                    yield ": keepalive\n\n"

        except (asyncio.CancelledError, GeneratorExit):
            logger.info(f"[{job_id}] SSE correção: gerador cancelado")
        except Exception as e:
            logger.warning(f"[{job_id}] SSE correção erro: {e}")
            # Fallback: retorna status do MySQL
            from app.repositories import text_corrections as corrections_repo

            job_data = corrections_repo.get_job(job_id)
            if job_data:
                yield f"data: {json.dumps(job_data, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'error', 'error': str(e)})}\n\n"
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
                logger.info(f"[{job_id}] SSE correção: conexão fechada")

    return _sse_response(event_generator())

