"""Ponto de entrada do Agente de Correção de Texto.

Consome a fila `text_correction_jobs` do RabbitMQ, envia texto para
ChatGPT/Gemini via Playwright e salva o resultado no MySQL.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

import aio_pika
from dotenv import load_dotenv
from sqlalchemy import select

from config import RABBITMQ_URL, RABBITMQ_AGENT_QUEUE, DEFAULT_PROVIDER, HEADLESS, CHROME_DATA_DIR
from database import SessionLocal, init_db
from models import TextCorrectionJob
from browser import BrowserEngine
from agent import TextCorrectionAgent

# ── Configuração ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("AgentWorker")


class AgentWorker:
    """Worker que consome jobs de correção de texto do RabbitMQ."""

    def __init__(self):
        self.browser: Optional[BrowserEngine] = None
        self.agent: Optional[TextCorrectionAgent] = None
        self.connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.Channel] = None
        self._progress_exchange: Optional[aio_pika.Exchange] = None

    async def start(self):
        """Inicia o browser, conecta ao RabbitMQ e começa a consumir."""
        init_db()

        # Iniciar browser
        self.browser = BrowserEngine(
            provider=DEFAULT_PROVIDER,
            headless=HEADLESS,
            chrome_data_dir=CHROME_DATA_DIR,
        )
        await self.browser.start()

        # Tentar navegar — se falhar por login, loga warning mas continua
        try:
            await self.browser.navigate_to_chat()
        except RuntimeError as e:
            logger.warning(f"Navegação inicial falhou: {e}")
            logger.warning("O agente vai tentar novamente ao processar o primeiro job.")

        self.agent = TextCorrectionAgent(self.browser)

        # Conectar ao RabbitMQ
        logger.info(f"Conectando ao RabbitMQ: {RABBITMQ_URL.split('@')[-1]}")
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)

        async with self.connection:
            channel = await self.connection.channel()
            self._channel = channel
            await channel.set_qos(prefetch_count=1)

            queue = await channel.declare_queue(RABBITMQ_AGENT_QUEUE, durable=True)
            logger.info(f"Escutando fila '{RABBITMQ_AGENT_QUEUE}'... Aguardando jobs.")

            async with queue.iterator() as q_iter:
                async for message in q_iter:
                    async with message.process():
                        await self._process_message(message.body.decode())

    async def _get_progress_exchange(self) -> aio_pika.Exchange:
        """Retorna o exchange de progresso, criando-o se necessário."""
        if self._progress_exchange is None:
            self._progress_exchange = await self._channel.declare_exchange(
                "text_correction_progress",
                aio_pika.ExchangeType.TOPIC,
                durable=True,
                auto_delete=False,
            )
        return self._progress_exchange

    async def _publish_progress(self, job_id: str, status: str, detail: str):
        """Publica atualização de progresso no exchange (SSE para a web)."""
        if not self._channel:
            return
        try:
            exchange = await self._get_progress_exchange()
            payload = json.dumps({
                "job_id": job_id,
                "status": status,
                "detail": detail,
            })
            await exchange.publish(
                aio_pika.Message(
                    body=payload.encode(),
                    delivery_mode=aio_pika.DeliveryMode.NOT_PERSISTENT,
                ),
                routing_key=job_id,
            )
            logger.debug(f"[{job_id}] Progresso publicado: {status}")
        except Exception as e:
            logger.warning(f"[{job_id}] Falha ao publicar progresso: {e}")
            self._progress_exchange = None

    def _update_db(self, job_id: str, **fields) -> None:
        """Atualiza campos do job no MySQL."""
        try:
            with SessionLocal() as session:
                job = session.scalar(
                    select(TextCorrectionJob).where(TextCorrectionJob.job_id == job_id)
                )
                if not job:
                    logger.warning(f"[{job_id}] Job não encontrado no MySQL.")
                    return
                for key, value in fields.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                session.commit()
        except Exception as e:
            logger.warning(f"[{job_id}] Falha ao atualizar MySQL: {e}")

    async def _process_message(self, body: str):
        """Processa uma mensagem da fila."""
        job_id = None
        try:
            payload = json.loads(body)
            job_id = payload.get("job_id")
            raw_text = payload.get("raw_text", "")
            provider = payload.get("provider", DEFAULT_PROVIDER)

            if not job_id:
                logger.error("Payload inválido: sem job_id")
                return

            if not raw_text:
                logger.error(f"[{job_id}] Payload inválido: sem raw_text")
                self._update_db(job_id, status="error", error="Texto bruto vazio")
                await self._publish_progress(job_id, "error", "Texto bruto vazio")
                return

            logger.info(f"[{job_id}] Processando correção — provider: {provider}, texto: {len(raw_text)} chars")

            # Atualizar status → processing
            self._update_db(job_id, status="processing")
            await self._publish_progress(job_id, "processing", "Enviando para a IA...")

            # Enviar para a IA
            corrected = await self.agent.correct_text(raw_text, provider)

            # Salvar resultado
            self._update_db(
                job_id,
                status="done",
                corrected_text=corrected,
                error=None,
            )
            await self._publish_progress(job_id, "done", "Correção concluída")

            logger.info(f"[{job_id}] Correção concluída — {len(corrected)} chars")

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao processar job:")
            if job_id:
                self._update_db(job_id, status="error", error=str(e))
                await self._publish_progress(job_id, "error", f"Erro: {e}")

    async def shutdown(self):
        """Encerra o browser e a conexão."""
        if self.browser:
            await self.browser.close()


if __name__ == "__main__":
    worker = AgentWorker()
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Agente encerrado pelo usuário.")
