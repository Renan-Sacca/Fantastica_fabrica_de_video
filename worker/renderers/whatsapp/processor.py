import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Coroutine, Any

from drive import DriveClient
from renderers import get_renderer
import jobs_repository

logger = logging.getLogger("WhatsAppProcessor")

class WhatsAppProcessor:
    def __init__(self, job_id: str, drive: DriveClient, publish_progress_fn: Callable[[str, str, float, str], Coroutine[Any, Any, None]]):
        self.job_id = job_id
        self.drive = drive
        self.publish_progress_fn = publish_progress_fn

    async def process(self):
        job_id = self.job_id
        work_dir = None
        try:
            logger.info(f"[{job_id}] ------------------------------------------")
            logger.info(f"[{job_id}] INICIANDO JOB (whatsapp)")

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
            _loop = asyncio.get_event_loop()

            def progress_callback(status=None, progress=0, detail=""):
                self._update_progress(metadata_file_id, metadata, status, progress, detail)
                asyncio.run_coroutine_threadsafe(
                    self.publish_progress_fn(job_id, status or metadata.get("status", ""), progress, detail),
                    _loop,
                )

            progress_callback(status="preparing", progress=2, detail="Arquivos baixados. Iniciando...")

            # ── 6. Instanciar renderer e gerar vídeo ──
            renderer = get_renderer("whatsapp")
            output_path = await asyncio.get_event_loop().run_in_executor(
                None, renderer.render, metadata, work_dir, progress_callback
            )

            # ── 7. Upload do vídeo gerado ──
            progress_callback(status="composing", progress=98, detail="Fazendo upload do vídeo...")

            video_bytes = output_path.read_bytes()
            video_filename = f"{metadata.get('title', 'Video')}_{job_id}.mp4"

            old_video_id = metadata.get("video_drive_id")
            if old_video_id:
                logger.info(f"[{job_id}] Deletando vídeo antigo do Drive: {old_video_id}")
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.delete_file, old_video_id
                )

            video_file_id = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.upload_bytes, video_bytes, video_filename, folder_id, "video/mp4"
            )

            video_url = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.make_public, video_file_id
            )

            logger.info(f"[{job_id}] Upload concluído! ID: {video_file_id}")

            # ── 8. Marcar como concluído ──
            metadata["video_drive_id"] = video_file_id
            metadata["video_url"] = video_url
            self._update_progress(metadata_file_id, metadata, status="done", progress=100, detail="Vídeo pronto!")
            await self.publish_progress_fn(job_id, "done", 100, "Vídeo pronto!")
            logger.info(f"[{job_id}] JOB FINALIZADO COM SUCESSO")

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao processar job:")
            if job_id:
                try:
                    folder_id = self.drive.find_folder_by_job_id(job_id)
                    if folder_id:
                        meta_id = self.drive.find_file_in_folder(folder_id, "metadata.json")
                        if meta_id:
                            meta = self.drive.read_json(meta_id)
                            meta["error"] = str(e)
                            self._update_progress(meta_id, meta, status="error", progress=0, detail=f"Erro: {e}")
                    await self.publish_progress_fn(job_id, "error", 0, f"Erro: {e}")
                except Exception as meta_err:
                    logger.error(f"[{job_id}] Não foi possível atualizar status de erro no Drive: {meta_err}")
        finally:
            if work_dir and work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    def _update_progress(self, file_id: str, metadata: dict, status: str = None, progress: float = None, detail: str = None):
        """Atualiza o arquivo metadata.json no Drive e espelha o estado no MySQL."""
        if status: metadata["status"] = status
        if progress is not None: metadata["progress"] = progress
        if detail is not None: metadata["detail"] = detail

        try:
            self.drive.update_json(file_id, metadata)
        except Exception as e:
            logger.warning(f"Erro ao atualizar progresso no Drive: {e}")

        # Espelha o estado no MySQL (índice rápido para a listagem)
        jobs_repository.update_status(
            metadata.get("job_id", self.job_id),
            status=metadata.get("status"),
            progress=metadata.get("progress"),
            detail=metadata.get("detail"),
            error=metadata.get("error"),
            video_drive_id=metadata.get("video_drive_id"),
            video_url=metadata.get("video_url"),
        )

    async def _download_files(self, metadata: dict, folder_id: str, work_dir: Path):
        """Baixa todos os arquivos registrados no metadata sequencialmente."""
        files_info = metadata.get("files", {})

        for key in ["conversa", "foto_perfil", "papel_parede", "musica"]:
            file_id = files_info.get(key)
            if file_id:
                ext = files_info.get(f"{key}_ext", "")
                if key == "conversa": ext = ".txt"
                dest_path = work_dir / f"{key}{ext}"
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, file_id, dest_path
                )

        imagens_info = files_info.get("imagens", {})
        if imagens_info:
            img_dir = work_dir / "imagens"
            img_dir.mkdir(exist_ok=True)
            for filename, file_id in imagens_info.items():
                dest_path = img_dir / filename
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, file_id, dest_path
                )
