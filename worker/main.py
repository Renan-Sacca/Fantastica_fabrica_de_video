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

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://financepowder:rgs050601@rabbitmq.financepowder.cloud/")
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

    async def start(self):
        """Inicia a conexão e começa a consumir a fila."""
        logger.info(f"Conectando ao RabbitMQ: {RABBITMQ_URL.split('@')[-1]}")
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)

        async with self.connection:
            channel = await self.connection.channel()
            # Permitir processar apenas 1 job por vez
            await channel.set_qos(prefetch_count=1)

            queue = await channel.declare_queue(RABBITMQ_QUEUE, durable=True)
            logger.info(f"Escutando fila '{RABBITMQ_QUEUE}'... Aguardando jobs.")

            async with queue.iterator() as q_iter:
                async for message in q_iter:
                    async with message.process():
                        await self._process_message(message.body.decode())

    async def _process_message(self, body: str):
        job_id = None
        work_dir = None
        try:
            payload = json.loads(body)
            job_id = payload.get('job_id')
            video_type = payload.get('video_type', 'whatsapp')
            self.drive = DriveClient(TOKEN_FILE)
            if not job_id:
                logger.error("Payload inválido: sem job_id")
                return

            logger.info(f"[{job_id}] ------------------------------------------")
            logger.info(f"[{job_id}] INICIANDO JOB ({video_type})")

            # ── 1. Localizar pasta no Drive ──
            folder_id = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.find_folder_by_job_id, job_id
            )
            if not folder_id:
                raise ValueError(f"Pasta do job {job_id} não encontrada no Drive")

            # ── 2. Baixar metadata.json ──
            metadata_file_id = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.find_file_in_folder, folder_id, "metadata.json"
            )
            if not metadata_file_id:
                raise ValueError("metadata.json não encontrado na pasta")

            metadata = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.read_json, metadata_file_id
            )

            # ── 3. Criar diretório de trabalho temporário ──
            work_dir = Path(tempfile.mkdtemp(prefix=f"job_{job_id}_"))
            logger.info(f"[{job_id}] Diretório local: {work_dir}")

            # ── 4. Baixar todos os arquivos ──
            await self._download_files(metadata, folder_id, work_dir)

            # ── 5. Preparar função de progresso ──
            def progress_callback(status=None, progress=0, detail=""):
                self._update_progress(metadata_file_id, metadata, status, progress, detail)

            progress_callback(status="preparing", progress=2, detail="Arquivos baixados. Iniciando...")

            # ── 6. Instanciar renderer e gerar vídeo ──
            renderer = get_renderer(video_type)
            output_path = await asyncio.get_event_loop().run_in_executor(
                None, renderer.render, metadata, work_dir, progress_callback
            )

            # ── 7. Upload do vídeo gerado ──
            progress_callback(status="composing", progress=98, detail="Fazendo upload do vídeo...")

            video_bytes = output_path.read_bytes()
            video_filename = f"{metadata.get('title', 'Video')}_{job_id}.mp4"
            
            video_file_id = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.upload_bytes, video_bytes, video_filename, folder_id, "video/mp4"
            )

            # Tornar vídeo público
            video_url = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.make_public, video_file_id
            )

            logger.info(f"[{job_id}] Upload concluído! ID: {video_file_id}")

            # ── 8. Marcar como concluído ──
            metadata["video_drive_id"] = video_file_id
            metadata["video_url"] = video_url
            self._update_progress(metadata_file_id, metadata, status="done", progress=100, detail="Vídeo pronto!")
            logger.info(f"[{job_id}] JOB FINALIZADO COM SUCESSO")

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao processar job:")
            if job_id:
                try:
                    # Tentar avisar no metadata.json que deu erro
                    folder_id = self.drive.find_folder_by_job_id(job_id)
                    if folder_id:
                        meta_id = self.drive.find_file_in_folder(folder_id, "metadata.json")
                        if meta_id:
                            meta = self.drive.read_json(meta_id)
                            meta["error"] = str(e)
                            self._update_progress(meta_id, meta, status="error", progress=0, detail=f"Erro: {e}")
                except Exception as meta_err:
                    logger.error(f"[{job_id}] Não foi possível atualizar status de erro no Drive: {meta_err}")
        finally:
            if work_dir and work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    def _update_progress(self, file_id: str, metadata: dict, status: str = None, progress: float = None, detail: str = None):
        """Atualiza o arquivo metadata.json no Drive."""
        if status: metadata["status"] = status
        if progress is not None: metadata["progress"] = progress
        if detail is not None: metadata["detail"] = detail

        try:
            self.drive.update_json(file_id, metadata)
        except Exception as e:
            logger.warning(f"Erro ao atualizar progresso no Drive: {e}")

    async def _download_files(self, metadata: dict, folder_id: str, work_dir: Path):
        """Baixa todos os arquivos registrados no metadata sequencialmente (httplib2 não é thread-safe)."""
        files_info = metadata.get("files", {})
        
        # Arquivos raiz
        for key in ["conversa", "foto_perfil", "papel_parede", "musica"]:
            file_id = files_info.get(key)
            if file_id:
                ext = files_info.get(f"{key}_ext", "")
                if key == "conversa": ext = ".txt"
                dest_path = work_dir / f"{key}{ext}"
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, file_id, dest_path
                )
        
        # Imagens da conversa
        imagens_info = files_info.get("imagens", {})
        if imagens_info:
            img_dir = work_dir / "imagens"
            img_dir.mkdir(exist_ok=True)
            for filename, file_id in imagens_info.items():
                dest_path = img_dir / filename
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, file_id, dest_path
                )


if __name__ == "__main__":
    worker = VideoWorker()
    try:
        asyncio.run(worker.start())
    except KeyboardInterrupt:
        logger.info("Worker encerrado pelo usuário.")
