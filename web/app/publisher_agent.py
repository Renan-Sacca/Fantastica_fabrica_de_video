"""Publicador de jobs de correção de texto no RabbitMQ.

Publica na fila separada `text_correction_jobs` (diferente da `video_jobs`).
"""
from __future__ import annotations

import json
import logging

import aio_pika

from app.config import RABBITMQ_AGENT_QUEUE, RABBITMQ_URL

logger = logging.getLogger(__name__)


async def publish_correction_job(job_id: str, raw_text: str, provider: str = "chatgpt") -> None:
    """Publica um job de correção de texto na fila do agente.

    Args:
        job_id: ID único do job.
        raw_text: Texto bruto a ser corrigido.
        provider: 'chatgpt' ou 'gemini'.
    """
    payload = json.dumps({
        "job_id": job_id,
        "raw_text": raw_text,
        "provider": provider,
    })

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()

        await channel.declare_queue(RABBITMQ_AGENT_QUEUE, durable=True)

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=payload.encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=RABBITMQ_AGENT_QUEUE,
        )

    logger.info(f"[{job_id}] Publicado na fila do agente → provider={provider}")
