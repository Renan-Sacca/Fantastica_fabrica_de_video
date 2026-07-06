"""Processador do tipo 'video_compositor' — orquestra download, áudio e renderização.

Fluxo:
1. Baixa metadata.json do Drive
2. Baixa imagem de fundo
3. Baixa overlay e áudio secundário (se existirem)
4. Se audio_source == 'omni': gera áudio via OmniVoice
5. Se audio_source == 'upload': baixa o áudio do Drive
6. Chama o renderer para compor o vídeo final
7. Faz upload do resultado
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Coroutine

from drive import DriveClient
import jobs_repository

logger = logging.getLogger("VideoCompositorProcessor")


class VideoCompositorProcessor:
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
        try:
            logger.info(f"[{job_id}] ------------------------------------------")
            logger.info(f"[{job_id}] INICIANDO JOB (video_compositor)")

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

            # ── 3. Criar diretório de trabalho ──
            work_dir = Path(tempfile.mkdtemp(prefix=f"job_{job_id}_compositor_"))
            logger.info(f"[{job_id}] Diretório local: {work_dir}")

            # ── 4. Baixar imagem de fundo ──
            await self._publish(job_id, "preparing", 2, "Baixando imagem de fundo...")
            files_info = metadata.get("files", {})

            bg_image_id = files_info.get("bg_image")
            bg_ext = files_info.get("bg_image_ext", ".png")
            if bg_image_id:
                bg_dest = work_dir / f"bg_image{bg_ext}"
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, bg_image_id, bg_dest
                )

            # ── 5. Baixar overlay (se existir) ──
            overlay_id = files_info.get("overlay_image")
            if overlay_id:
                await self._publish(job_id, "preparing", 3, "Baixando imagem sobreposta...")
                ov_ext = files_info.get("overlay_image_ext", ".png")
                ov_dest = work_dir / f"overlay_image{ov_ext}"
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, overlay_id, ov_dest
                )

            # ── 6. Lidar com áudio principal ──
            audio_source = metadata.get("audio_source", "upload")

            if audio_source == "upload":
                await self._publish(job_id, "preparing", 5, "Baixando áudio principal...")
                audio_id = files_info.get("audio")
                audio_ext = files_info.get("audio_ext", ".mp3")
                if audio_id:
                    audio_dest = work_dir / f"audio{audio_ext}"
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.drive.download_file, audio_id, audio_dest
                    )
                else:
                    raise ValueError("Arquivo de áudio não encontrado no metadata.")

            elif audio_source == "omni":
                await self._publish(job_id, "generating_audio", 5, "Gerando áudio via OmniVoice...")
                await self._generate_omni_audio(metadata, work_dir, folder_id, metadata_file_id)

            else:
                raise ValueError(f"Fonte de áudio desconhecida: {audio_source}")

            # ── 7. Baixar áudio secundário (se existir) ──
            sec_audio_id = files_info.get("secondary_audio")
            if sec_audio_id:
                await self._publish(job_id, "preparing", 7, "Baixando áudio secundário...")
                sec_ext = files_info.get("secondary_audio_ext", ".mp3")
                sec_dest = work_dir / f"secondary_audio{sec_ext}"
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, sec_audio_id, sec_dest
                )

            # ── 8. Renderizar ──
            _loop = asyncio.get_event_loop()

            def progress_callback(status=None, progress=0, detail=""):
                self._update_progress(metadata_file_id, metadata, status, progress, detail)
                asyncio.run_coroutine_threadsafe(
                    self.publish_progress_fn(
                        job_id, status or metadata.get("status", ""), progress, detail
                    ),
                    _loop,
                )

            progress_callback(status="preparing", progress=8, detail="Arquivos prontos. Iniciando renderização...")

            from renderers.video_compositor.renderer import VideoCompositorRenderer
            renderer = VideoCompositorRenderer()
            output_path = await asyncio.get_event_loop().run_in_executor(
                None, renderer.render, metadata, work_dir, progress_callback
            )

            # ── 9. Upload do vídeo gerado ──
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

            # ── 9.5. Upload da thumbnail (se existir) ──
            thumbnail_path = work_dir / "thumbnail.jpg"
            thumbnail_url = None
            if thumbnail_path.exists():
                logger.info(f"[{job_id}] Fazendo upload da thumbnail...")
                thumbnail_bytes = thumbnail_path.read_bytes()
                thumbnail_filename = f"thumbnail_{job_id}.jpg"

                thumbnail_file_id = await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.upload_bytes, thumbnail_bytes, thumbnail_filename, folder_id, "image/jpeg"
                )

                thumbnail_url = await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.make_public, thumbnail_file_id
                )

                logger.info(f"[{job_id}] Thumbnail uploaded! ID: {thumbnail_file_id}")

            # ── 10. Marcar como concluído ──
            metadata["video_drive_id"] = video_file_id
            metadata["video_url"] = video_url
            if thumbnail_url:
                metadata["thumbnail_url"] = thumbnail_url
                metadata["thumbnail_drive_id"] = thumbnail_file_id
            self._update_progress(
                metadata_file_id, metadata,
                status="done", progress=100, detail="Vídeo pronto!"
            )
            await self.publish_progress_fn(job_id, "done", 100, "Vídeo pronto!")
            logger.info(f"[{job_id}] JOB VIDEO_COMPOSITOR FINALIZADO COM SUCESSO")

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao processar job video_compositor:")
            if job_id:
                try:
                    folder_id = self.drive.find_folder_by_job_id(job_id)
                    if folder_id:
                        meta_id = self.drive.find_file_in_folder(folder_id, "metadata.json")
                        if meta_id:
                            meta = self.drive.read_json(meta_id)
                            meta["error"] = str(e)
                            self._update_progress(
                                meta_id, meta,
                                status="error", progress=0, detail=f"Erro: {e}"
                            )
                    await self.publish_progress_fn(job_id, "error", 0, f"Erro: {e}")
                except Exception as meta_err:
                    logger.error(f"[{job_id}] Não foi possível atualizar status de erro no Drive: {meta_err}")
        finally:
            if work_dir and work_dir.exists():
                shutil.rmtree(work_dir, ignore_errors=True)

    async def _generate_omni_audio(
        self, metadata: dict, work_dir: Path,
        folder_id: str, metadata_file_id: str,
    ):
        """Gera áudio via OmniVoice (mesmo mecanismo do video_bg)."""
        omni_config = metadata.get("omni", {})
        text = omni_config.get("text", "")
        ref_filename = omni_config.get("ref_filename")
        ref_text = omni_config.get("ref_text", "")
        gen_params = omni_config.get("gen_params", {})

        if not text:
            raise ValueError("Texto para geração de áudio não fornecido.")

        await self._publish(self.job_id, "generating_audio", 10, "Gerando áudio...")
        out = await self._omni_generate_one(
            text, ref_filename, ref_text, gen_params, folder_id, work_dir, "audio"
        )
        ext = out.suffix
        metadata["files"]["audio_ext"] = ext
        audio_bytes = out.read_bytes()
        audio_file_id = self.drive.upload_bytes(
            audio_bytes, f"audio{ext}", folder_id, "audio/wav"
        )
        metadata["files"]["audio"] = audio_file_id
        self.drive.update_json(metadata_file_id, metadata)

    async def _omni_generate_one(
        self, text: str, ref_filename, ref_text: str, gen_params: dict,
        folder_id: str, work_dir: Path, out_name: str,
    ) -> Path:
        """Publica sub-job OmniVoice, aguarda e retorna o path local."""
        import aio_pika
        import uuid

        omni_job_id = uuid.uuid4().hex[:8]
        rabbitmq_url = os.getenv("RABBITMQ_URL")
        omni_queue = os.getenv("RABBITMQ_OMNI_QUEUE", "omni_audio_jobs")
        omni_progress_exchange = os.getenv("RABBITMQ_OMNI_PROGRESS_EXCHANGE", "omni_audio_progress")

        payload = json.dumps({
            "job_id": omni_job_id,
            "text": text,
            "mode": "clone",
            "ref_filename": ref_filename,
            "ref_text": ref_text,
            "instruct": "",
            "gen_params": gen_params,
            "drive_folder_id": folder_id,
        })

        connection = await aio_pika.connect_robust(rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue(omni_queue, durable=True)
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=payload.encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=omni_queue,
            )
        logger.info(f"[{self.job_id}] Sub-job OmniVoice publicado: {omni_job_id}")

        # Aguardar via exchange de progresso
        connection2 = await aio_pika.connect_robust(rabbitmq_url)
        audio_done = False
        try:
            channel2 = await connection2.channel()
            exchange = await channel2.declare_exchange(
                omni_progress_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
                auto_delete=False,
            )
            queue = await channel2.declare_queue(
                "", exclusive=True, auto_delete=True, durable=False,
                arguments={"x-expires": 300_000},
            )
            await queue.bind(exchange, routing_key=omni_job_id)

            timeout = 300
            start_time = time.time()
            async with queue.iterator() as q_iter:
                async for message in q_iter:
                    async with message.process():
                        data = json.loads(message.body.decode())
                        status = data.get("status", "")
                        progress = data.get("progress", 0)
                        detail = data.get("detail", "")

                        await self._publish(
                            self.job_id, "generating_audio",
                            10 + int(progress * 0.2),
                            f"Gerando áudio: {detail}"
                        )

                        if status == "done":
                            audio_done = True
                            break
                        elif status == "error":
                            raise RuntimeError(f"OmniVoice falhou: {detail}")

                        if time.time() - start_time > timeout:
                            raise TimeoutError("Timeout aguardando geração de áudio OmniVoice")
        finally:
            if not connection2.is_closed:
                await connection2.close()

        if not audio_done:
            raise RuntimeError("Geração de áudio não concluída.")

        omni_outputs_dir = Path(os.getenv("OMNI_OUTPUTS_DIR", "/app/tts3_audio/outputs"))
        for ext in [".wav", ".mp3", ".ogg"]:
            candidate = omni_outputs_dir / f"{omni_job_id}{ext}"
            if candidate.exists():
                dest = work_dir / f"{out_name}{ext}"
                shutil.copy2(candidate, dest)
                logger.info(f"[{self.job_id}] Áudio encontrado localmente: {candidate}")
                return dest

        for ext in [".wav", ".mp3"]:
            fname = f"audio_{omni_job_id}{ext}"
            fid = self.drive.find_file_in_folder(folder_id, fname)
            if fid:
                dest = work_dir / f"{out_name}{ext}"
                self.drive.download_file(fid, dest)
                logger.info(f"[{self.job_id}] Áudio baixado do Drive: {fname}")
                return dest

        raise RuntimeError("Não foi possível localizar o áudio gerado pelo OmniVoice.")

    async def _publish(self, job_id: str, status: str, progress: float, detail: str):
        """Publica progresso."""
        await self.publish_progress_fn(job_id, status, progress, detail)

    def _update_progress(
        self, file_id: str, metadata: dict,
        status: str = None, progress: float = None, detail: str = None,
    ):
        """Atualiza o metadata.json no Drive e espelha no MySQL."""
        if status:
            metadata["status"] = status
        if progress is not None:
            metadata["progress"] = progress
        if detail is not None:
            metadata["detail"] = detail

        try:
            self.drive.update_json(file_id, metadata)
        except Exception as e:
            logger.warning(f"Erro ao atualizar progresso no Drive: {e}")

        jobs_repository.update_status(
            metadata.get("job_id", self.job_id),
            status=metadata.get("status"),
            progress=metadata.get("progress"),
            detail=metadata.get("detail"),
            error=metadata.get("error"),
            video_drive_id=metadata.get("video_drive_id"),
            video_url=metadata.get("video_url"),
        )
