"""Ponto de entrada do Worker de Renderização."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import aio_pika
from dotenv import load_dotenv

from drive import DriveClient
from renderers import get_renderer

# ── Configuração ──
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise ValueError("RABBITMQ_URL não encontrada no .env")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "video_jobs")
TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Worker")


class VideoWorker:
    def __init__(self):
        self.drive = DriveClient(TOKEN_FILE)
        self.connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.Channel] = None
        self._progress_exchange: Optional[aio_pika.Exchange] = None

    async def start(self):
        """Inicia a conexão e começa a consumir a fila."""
        logger.info(f"Conectando ao RabbitMQ: {RABBITMQ_URL.split('@')[-1]}")
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)

        async with self.connection:
            channel = await self.connection.channel()
            self._channel = channel
            # Permitir processar apenas 1 job por vez
            await channel.set_qos(prefetch_count=1)

            queue = await channel.declare_queue(RABBITMQ_QUEUE, durable=True)
            logger.info(f"Escutando fila '{RABBITMQ_QUEUE}'... Aguardando jobs.")

            async with queue.iterator() as q_iter:
                async for message in q_iter:
                    async with message.process():
                        await self._process_message(message.body.decode())

    async def _get_progress_exchange(self) -> aio_pika.Exchange:
        """Retorna o exchange padrao de progresso, criando-o se necessario."""
        if self._progress_exchange is None:
            self._progress_exchange = await self._channel.declare_exchange(
                "video_progress",
                aio_pika.ExchangeType.TOPIC,
                durable=True,
                auto_delete=False,
            )
        return self._progress_exchange

    async def _publish_progress(self, job_id: str, status: str, progress: float, detail: str):
        """Publica atualizacao de progresso no exchange padrao (routing_key = job_id)."""
        if not self._channel:
            return
        try:
            exchange = await self._get_progress_exchange()
            payload = json.dumps({
                "job_id": job_id,
                "status": status,
                "progress": progress,
                "detail": detail,
            })
            await exchange.publish(
                aio_pika.Message(
                    body=payload.encode(),
                    delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
                ),
                routing_key=job_id,
            )
            logger.debug(f"[{job_id}] Progresso publicado: {status} {progress}%")
        except Exception as e:
            logger.warning(f"[{job_id}] Nao foi possivel publicar progresso no RabbitMQ: {e}")
            self._progress_exchange = None  # Forcar re-declaracao na proxima tentativa

    async def _process_message(self, body: str):
        job_id = None
        try:
            payload = json.loads(body)
            job_id = payload.get('job_id')
            video_type = payload.get('video_type', 'whatsapp')
            self.drive = DriveClient(TOKEN_FILE)
            if not job_id:
                logger.error("Payload inválido: sem job_id")
                return

            if video_type == "whatsapp":
                from renderers.whatsapp.processor import WhatsAppProcessor
                processor = WhatsAppProcessor(job_id, self.drive, self._publish_progress)
                await processor.process()
            else:
                logger.error(f"Video type '{video_type}' não suportado ou sem processador específico.")

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao delegar processamento do job:")
            if job_id:
                await self._publish_progress(job_id, "error", 0, f"Erro: {e}")

if __name__ == "__main__":
    worker = VideoWorker()
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Worker encerrado pelo usuário.")
