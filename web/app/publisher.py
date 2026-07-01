"""Publicador de mensagens no RabbitMQ."""
from __future__ import annotations

import json
import logging

import aio_pika

from app.config import RABBITMQ_QUEUE, RABBITMQ_URL

logger = logging.getLogger(__name__)


async def publish_job(job_id: str, video_type: str) -> None:
    """
    Publica um job na fila do RabbitMQ.
    O worker usa job_id + video_type para buscar os dados no Drive.
    """
    payload = json.dumps({"job_id": job_id, "video_type": video_type})

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()

        # Garante que a fila existe (durable = sobrevive a reinicializações)
        await channel.declare_queue(RABBITMQ_QUEUE, durable=True)

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=payload.encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=RABBITMQ_QUEUE,
        )

    logger.info(f"[{job_id}] Publicado no RabbitMQ → tipo={video_type}")


async def publish_omni_job(
    job_id: str,
    text: str,
    mode: str,
    ref_filename: str | None,
    ref_text: str,
    instruct: str,
    gen_params: dict,
    drive_folder_id: str | None = None,
) -> None:
    """Publica um job de geração de áudio (OmniVoice) na fila própria."""
    from app.config import RABBITMQ_OMNI_QUEUE

    payload = json.dumps({
        "job_id": job_id,
        "text": text,
        "mode": mode,
        "ref_filename": ref_filename,
        "ref_text": ref_text,
        "instruct": instruct,
        "gen_params": gen_params,
        "drive_folder_id": drive_folder_id,
    })

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(RABBITMQ_OMNI_QUEUE, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=payload.encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=RABBITMQ_OMNI_QUEUE,
        )

    logger.info(f"[{job_id}] Job de áudio (OmniVoice) publicado → fila={RABBITMQ_OMNI_QUEUE}")
