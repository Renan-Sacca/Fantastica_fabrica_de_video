"""Worker de geração de áudio com OmniVoice (k2-fsa).

Consome a fila própria `omni_audio_jobs` no RabbitMQ, gera o áudio na GPU e
publica o progresso no exchange `omni_audio_progress` (consumido via SSE pela web).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import aio_pika
import soundfile as sf
from dotenv import load_dotenv

from omni_engine import OmniEngine

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise ValueError("RABBITMQ_URL não encontrada no .env")
OMNI_QUEUE = os.getenv("RABBITMQ_OMNI_QUEUE", "omni_audio_jobs")
PROGRESS_EXCHANGE = os.getenv("RABBITMQ_OMNI_PROGRESS_EXCHANGE", "omni_audio_progress")

DATA_DIR = Path("/app/data")
VOICES_DIR = DATA_DIR / "voices"
OUTPUTS_DIR = DATA_DIR / "outputs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("OmniWorker")


class OmniWorker:
    def __init__(self) -> None:
        self.engine = OmniEngine()
        self.connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.Channel] = None
        self._progress_exchange: Optional[aio_pika.Exchange] = None

    async def start(self) -> None:
        VOICES_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(self.engine.load)

        logger.info(f"Conectando ao RabbitMQ: {RABBITMQ_URL.split('@')[-1]}")
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)

        async with self.connection:
            channel = await self.connection.channel()
            self._channel = channel
            await channel.set_qos(prefetch_count=1)

            queue = await channel.declare_queue(OMNI_QUEUE, durable=True)
            logger.info(f"Escutando fila '{OMNI_QUEUE}'... Aguardando jobs (OmniVoice).")

            async with queue.iterator() as q_iter:
                async for message in q_iter:
                    async with message.process():
                        await self._process_message(message.body.decode())

    async def _get_progress_exchange(self) -> aio_pika.Exchange:
        if self._progress_exchange is None:
            self._progress_exchange = await self._channel.declare_exchange(
                PROGRESS_EXCHANGE,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
                auto_delete=False,
            )
        return self._progress_exchange

    async def _publish_progress(
        self, job_id: str, status: str, progress: float, detail: str, audio_url: str | None = None
    ) -> None:
        if not self._channel:
            return
        try:
            exchange = await self._get_progress_exchange()
            payload = json.dumps({
                "job_id": job_id,
                "status": status,
                "progress": progress,
                "detail": detail,
                "audio_url": audio_url,
            })
            await exchange.publish(
                aio_pika.Message(
                    body=payload.encode(),
                    delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
                ),
                routing_key=job_id,
            )
        except Exception as e:
            logger.warning(f"[{job_id}] Falha ao publicar progresso: {e}")
            self._progress_exchange = None

    async def _process_message(self, body: str) -> None:
        job_id = None
        try:
            payload = json.loads(body)
            job_id = payload.get("job_id")
            text = (payload.get("text") or "").strip()
            mode = payload.get("mode", "auto")
            ref_filename = payload.get("ref_filename")
            ref_text = payload.get("ref_text", "") or ""
            instruct = payload.get("instruct", "") or ""
            gen_params = payload.get("gen_params", {}) or {}

            if not job_id:
                logger.error("Payload inválido: sem job_id")
                return
            if not text:
                await self._publish_progress(job_id, "error", 0, "Texto vazio.")
                return

            ref_audio = None
            if mode == "clone":
                ref = VOICES_DIR / ref_filename if ref_filename else None
                if not ref or not ref.exists():
                    await self._publish_progress(job_id, "error", 0, "Voz de referência não encontrada.")
                    return
                ref_audio = str(ref)

            logger.info(f"[{job_id}] Gerando áudio (OmniVoice, modo={mode})")
            await self._publish_progress(job_id, "processing", 25, "Gerando áudio...")

            audio = await asyncio.to_thread(
                self.engine.generate,
                text,
                mode,
                ref_audio,
                ref_text,
                instruct,
                gen_params,
            )

            out_path = OUTPUTS_DIR / f"{job_id}.wav"
            sf.write(str(out_path), audio, self.engine.sample_rate)
            logger.info(f"[{job_id}] Áudio gerado: {out_path}")

            await self._publish_progress(
                job_id, "done", 100, "Áudio gerado com sucesso.", audio_url=f"/audio3-files/{job_id}.wav"
            )

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao gerar áudio:")
            if job_id:
                await self._publish_progress(job_id, "error", 0, f"Erro: {e}")


if __name__ == "__main__":
    worker = OmniWorker()
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Worker encerrado pelo usuário.")
