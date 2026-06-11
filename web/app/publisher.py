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
