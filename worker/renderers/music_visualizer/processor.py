"""Processador do tipo 'music_visualizer'.

Fluxo:
1. Baixa metadata.json do Drive
2. Baixa a imagem de fundo (bg_image)
3. Baixa a logo (opcional)
4. Baixa o áudio
5. Chama o renderer para gerar o vídeo
6. Faz upload do resultado + thumbnail
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from drive import DriveClient
import jobs_repository

logger = logging.getLogger("MusicVisualizerProcessor")


class MusicVisualizerProcessor:
    def __init__(
        self,
        payload: dict,
        drive: DriveClient,
        publish_progress_fn: Callable[[str, str, float, str], Coroutine[Any, Any, None]],
    ):
        self.job_id = payload.get("job_id")
        self.drive = drive
        self.publish_progress_fn = publish_progress_fn

    async def process(self):
        job_id = self.job_id
        work_dir = None
        metadata = {}
        metadata_file_id = None

        try:
            logger.info(f"[{job_id}] INICIANDO JOB (music_visualizer)")

            # 1. Localizar pasta no Drive
            folder_id = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.find_folder_by_job_id, job_id
            )
            if not folder_id:
                raise ValueError(f"Pasta do job {job_id} não encontrada no Drive")

            # 2. Baixar metadata.json
            metadata_file_id = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.find_file_in_folder, folder_id, "metadata.json"
            )
            if not metadata_file_id:
                raise ValueError("metadata.json não encontrado na pasta")

            metadata = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.read_json, metadata_file_id
            )

            # 3. Criar diretório de trabalho
            work_dir = Path(tempfile.mkdtemp(prefix=f"job_{job_id}_musicviz_"))
            logger.info(f"[{job_id}] Diretório local: {work_dir}")

            files_info = metadata.get("files", {})

            # 4. Baixar imagem de fundo
            await self._publish(job_id, "preparing", 3, "Baixando imagem de fundo...")
            bg_id = files_info.get("bg_image")
            bg_ext = files_info.get("bg_image_ext", ".jpg")
            if not bg_id:
                raise ValueError("Imagem de fundo não encontrada no metadata.")
            await asyncio.get_event_loop().run_in_executor(
                None, self.drive.download_file, bg_id, work_dir / f"bg_image{bg_ext}"
            )

            # 5. Baixar logo (opcional)
            logo_id = files_info.get("logo")
            logo_ext = files_info.get("logo_ext", "")
            if logo_id and logo_ext:
                await self._publish(job_id, "preparing", 5, "Baixando logo...")
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, logo_id, work_dir / f"logo{logo_ext}"
                )

            # 6. Baixar áudio
            await self._publish(job_id, "preparing", 7, "Baixando áudio...")
            audio_id = files_info.get("audio")
            audio_ext = files_info.get("audio_ext", ".mp3")
            if not audio_id:
                raise ValueError("Arquivo de áudio não encontrado no metadata.")
            await asyncio.get_event_loop().run_in_executor(
                None, self.drive.download_file, audio_id, work_dir / f"audio{audio_ext}"
            )

            # 7. Renderizar
            _loop = asyncio.get_event_loop()

            def progress_callback(status=None, progress=0, detail=""):
                self._update_progress(metadata_file_id, metadata, status, progress, detail)
                asyncio.run_coroutine_threadsafe(
                    self.publish_progress_fn(
                        job_id, status or metadata.get("status", ""), progress, detail
                    ),
                    _loop,
                )

            progress_callback(status="preparing", progress=9, detail="Iniciando renderização...")

            from renderers.music_visualizer.renderer import MusicVisualizerRenderer
            renderer = MusicVisualizerRenderer()
            output_path = await asyncio.get_event_loop().run_in_executor(
                None, renderer.render, metadata, work_dir, progress_callback
            )

            # 8. Upload do vídeo
            progress_callback(status="composing", progress=98, detail="Fazendo upload...")
            video_bytes = output_path.read_bytes()
            video_filename = f"{metadata.get('title', 'MusicVisualizer')}_{job_id}.mp4"

            old_video_id = metadata.get("video_drive_id")
            if old_video_id:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.delete_file, old_video_id
                )

            video_file_id = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.upload_bytes, video_bytes, video_filename, folder_id, "video/mp4"
            )
            video_url = await asyncio.get_event_loop().run_in_executor(
                None, self.drive.make_public, video_file_id
            )

            # 9. Gerar e fazer upload da thumbnail (primeiro frame)
            thumbnail_url = None
            thumbnail_path = work_dir / "thumbnail.jpg"
            await asyncio.get_event_loop().run_in_executor(
                None, self._generate_thumbnail, output_path, thumbnail_path
            )
            if thumbnail_path.exists():
                tb_bytes = thumbnail_path.read_bytes()
                tb_id = await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.upload_bytes, tb_bytes,
                    f"thumbnail_{job_id}.jpg", folder_id, "image/jpeg"
                )
                thumbnail_url = await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.make_public, tb_id
                )
                metadata["thumbnail_url"] = thumbnail_url
                metadata["thumbnail_drive_id"] = tb_id

            # 10. Marcar como concluído
            metadata["video_drive_id"] = video_file_id
            metadata["video_url"] = video_url
            self._update_progress(
                metadata_file_id, metadata, status="done", progress=100, detail="Vídeo pronto!"
            )
            await self.publish_progress_fn(job_id, "done", 100, "Vídeo pronto!")
            logger.info(f"[{job_id}] JOB MUSIC_VISUALIZER FINALIZADO")

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao processar job music_visualizer:")
            try:
                if metadata_file_id:
                    meta = metadata or {}
                    meta["error"] = str(e)
                    self._update_progress(
                        metadata_file_id, meta, status="error", progress=0, detail=f"Erro: {e}"
                    )
                await self.publish_progress_fn(job_id, "error", 0, f"Erro: {e}")
            except Exception as inner:
                logger.error(f"[{job_id}] Não foi possível atualizar status de erro: {inner}")
        finally:
            if work_dir and work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    @staticmethod
    def _generate_thumbnail(video_path: Path, out_path: Path):
        """Extrai o primeiro frame do vídeo como thumbnail."""
        import subprocess
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-ss", "0", "-frames:v", "1", "-q:v", "2",
            str(out_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=60)

    async def _publish(self, job_id, status, progress, detail):
        await self.publish_progress_fn(job_id, status, progress, detail)

    def _update_progress(self, file_id, metadata, status=None, progress=None, detail=None):
        if status:
            metadata["status"] = status
        if progress is not None:
            metadata["progress"] = progress
        if detail is not None:
            metadata["detail"] = detail
        try:
            self.drive.update_json(file_id, metadata)
        except Exception as e:
            logger.warning(f"Erro ao atualizar Drive: {e}")
        jobs_repository.update_status(
            metadata.get("job_id", self.job_id),
            status=metadata.get("status"),
            progress=metadata.get("progress"),
            detail=metadata.get("detail"),
            error=metadata.get("error"),
            video_drive_id=metadata.get("video_drive_id"),
            video_url=metadata.get("video_url"),
        )
