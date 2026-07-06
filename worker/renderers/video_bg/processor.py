"""Processador do tipo 'video_bg' — orquestra download, geração de áudio e renderização.

Fluxo:
1. Baixa metadata.json do Drive
2. Baixa vídeo de fundo
3. Se audio_source == 'omni': gera áudio via OmniVoice e espera conclusão
4. Se audio_source == 'upload': baixa o áudio do Drive
5. Chama o renderer para compor o vídeo final
6. Faz upload do resultado
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

logger = logging.getLogger("VideoBgProcessor")


class VideoBgProcessor:
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
            logger.info(f"[{job_id}] INICIANDO JOB (video_bg)")

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
            work_dir = Path(tempfile.mkdtemp(prefix=f"job_{job_id}_videobg_"))
            logger.info(f"[{job_id}] Diretório local: {work_dir}")

            # ── 4. Baixar vídeo de fundo ──
            await self._publish(job_id, "preparing", 2, "Baixando vídeo de fundo...")
            files_info = metadata.get("files", {})

            bg_video_id = files_info.get("bg_video")
            bg_ext = files_info.get("bg_video_ext", ".mp4")
            if bg_video_id:
                bg_dest = work_dir / f"bg_video{bg_ext}"
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, bg_video_id, bg_dest
                )

            # ── 5. Lidar com áudio ──
            audio_source = metadata.get("audio_source", "upload")

            if audio_source == "upload":
                # Baixar áudio direto do Drive
                await self._publish(job_id, "preparing", 5, "Baixando áudio...")
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
                # Gerar áudio via OmniVoice
                await self._publish(job_id, "generating_audio", 5, "Gerando áudio via OmniVoice...")
                await self._generate_omni_audio(metadata, work_dir, folder_id, metadata_file_id)

            else:
                raise ValueError(f"Fonte de áudio desconhecida: {audio_source}")

            # ── 6. Renderizar ──
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

            from renderers.video_bg.renderer import VideoBgRenderer
            renderer = VideoBgRenderer()
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

            # ── 7.5. Upload da thumbnail (se existir) ──
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

            # ── 8. Marcar como concluído ──
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
            logger.info(f"[{job_id}] JOB VIDEO_BG FINALIZADO COM SUCESSO")

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao processar job video_bg:")
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
        """Gera áudio via OmniVoice.

        Se `narrate_title` estiver ativo, gera dois áudios (título e conteúdo),
        concatena-os (título + pequena pausa + conteúdo) e ajusta a intro para durar
        exatamente o tempo da fala do título — o card fica na tela enquanto o título
        é narrado.
        """
        omni_config = metadata.get("omni", {})
        text = omni_config.get("text", "")
        ref_filename = omni_config.get("ref_filename")
        ref_text = omni_config.get("ref_text", "")
        gen_params = omni_config.get("gen_params", {})
        narrate_title = omni_config.get("narrate_title", False)
        title_text = (omni_config.get("title_text") or "").strip()

        if not text:
            raise ValueError("Texto para geração de áudio não fornecido.")

        # ── Modo: título narrado + conteúdo ──
        if narrate_title and title_text:
            await self._publish(self.job_id, "generating_audio", 8, "Gerando áudio do título...")
            title_audio = await self._omni_generate_one(
                title_text, ref_filename, ref_text, gen_params, folder_id, work_dir, "title_audio"
            )

            await self._publish(self.job_id, "generating_audio", 20, "Gerando áudio do conteúdo...")
            content_audio = await self._omni_generate_one(
                text, ref_filename, ref_text, gen_params, folder_id, work_dir, "content_audio"
            )

            # Concatenar título + pausa + conteúdo
            title_dur = self._probe_duration(title_audio)
            gap = 0.4
            final_audio = work_dir / "audio.wav"
            self._concat_audios(title_audio, content_audio, final_audio, gap)
            metadata["files"]["audio_ext"] = ".wav"

            audio_bytes = final_audio.read_bytes()
            audio_file_id = self.drive.upload_bytes(
                audio_bytes, "audio.wav", folder_id, "audio/wav"
            )
            metadata["files"]["audio"] = audio_file_id

            # A intro (card) fica visível enquanto o título é falado (+ a pausa)
            metadata["intro_enabled"] = True
            metadata["intro_duration"] = round(title_dur + gap, 2)
            self.drive.update_json(metadata_file_id, metadata)
            logger.info(
                f"[{self.job_id}] Título narrado ({title_dur:.2f}s) + conteúdo concatenados. "
                f"Intro ajustada para {metadata['intro_duration']}s"
            )
            return

        # ── Modo padrão: apenas o conteúdo ──
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
        """Publica um sub-job OmniVoice, aguarda concluir e retorna o path local do áudio.

        O arquivo é salvo em work_dir/{out_name}{ext}.
        """
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
        logger.info(f"[{self.job_id}] Sub-job OmniVoice publicado: {omni_job_id} ({out_name})")

        # Aguardar conclusão via exchange de progresso
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

        # Localizar o áudio gerado (local ou no Drive)
        omni_outputs_dir = Path(os.getenv("OMNI_OUTPUTS_DIR", "/app/tts3_audio/outputs"))
        for ext in [".wav", ".mp3", ".ogg"]:
            candidate = omni_outputs_dir / f"{omni_job_id}{ext}"
            if candidate.exists():
                dest = work_dir / f"{out_name}{ext}"
                shutil.copy2(candidate, dest)
                logger.info(f"[{self.job_id}] Áudio '{out_name}' encontrado localmente: {candidate}")
                return dest

        for ext in [".wav", ".mp3"]:
            fname = f"audio_{omni_job_id}{ext}"
            fid = self.drive.find_file_in_folder(folder_id, fname)
            if fid:
                dest = work_dir / f"{out_name}{ext}"
                self.drive.download_file(fid, dest)
                logger.info(f"[{self.job_id}] Áudio '{out_name}' baixado do Drive: {fname}")
                return dest

        raise RuntimeError("Não foi possível localizar o áudio gerado pelo OmniVoice.")

    def _probe_duration(self, path: Path) -> float:
        """Duração de um arquivo de mídia (segundos) via ffprobe."""
        res = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(json.loads(res.stdout)["format"]["duration"])

    def _concat_audios(self, first: Path, second: Path, out: Path, gap: float = 0.4):
        """Concatena dois áudios com uma pequena pausa de silêncio entre eles."""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(first),
            "-f", "lavfi", "-t", str(gap),
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-i", str(second),
            "-filter_complex",
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
            "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
            "[2:a]aformat=sample_rates=44100:channel_layouts=stereo[a2];"
            "[a0][a1][a2]concat=n=3:v=0:a=1[a]",
            "-map", "[a]",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Falha ao concatenar áudios: {result.stderr[-400:]}")
        logger.info(f"[{self.job_id}] Áudios concatenados (título + {gap}s + conteúdo): {out}")

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
