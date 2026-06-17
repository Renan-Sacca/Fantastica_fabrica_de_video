import asyncio
import logging
import os
import tempfile
import traceback
from typing import Callable, Coroutine
from drive import DriveClient
from .pipeline import WhatsAppVideoExtractor
import jobs_repository

logger = logging.getLogger(__name__)

class WhatsAppExtractProcessor:
    def __init__(self, job_data: dict, drive: DriveClient, publish_progress: Callable[[str, str, float, str], Coroutine]):
        self.job_info = job_data
        self.job_id = job_data.get("job_id")
        self.drive = drive
        self.publish_progress = publish_progress

    async def _progress(self, status: str, progress: float, detail: str, error: str = None):
        """Publica progresso no RabbitMQ e espelha o estado no MySQL."""
        jobs_repository.update_status(
            self.job_id, status=status, progress=progress, detail=detail, error=error
        )
        await self.publish_progress(self.job_id, status, progress, detail)

    async def process(self):
        try:
            await self._progress("processing", 10.0, "Baixando vídeo do Drive...")
            
            loop = asyncio.get_event_loop()
            
            folder_id = await loop.run_in_executor(None, self.drive.find_folder_by_job_id, self.job_id)
            if not folder_id:
                raise ValueError(f"Pasta do job {self.job_id} não encontrada no Drive")

            metadata_file_id = await loop.run_in_executor(None, self.drive.find_file_in_folder, folder_id, "metadata.json")
            if not metadata_file_id:
                raise ValueError("metadata.json não encontrado na pasta")

            metadata = await loop.run_in_executor(None, self.drive.read_json, metadata_file_id)
            video_file_id = metadata.get("files", {}).get("video_original")
            if not video_file_id:
                raise ValueError("Nenhum vídeo original encontrado no metadata.")
                
            # Cria temp dir
            with tempfile.TemporaryDirectory() as tmp_dir:
                video_path = os.path.join(tmp_dir, "video.mp4")
                json_path = os.path.join(tmp_dir, "conversa.json")
                txt_path = os.path.join(tmp_dir, "conversa.txt")
                
                from pathlib import Path
                
                # Baixa o video
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.download_file, video_file_id, Path(video_path)
                )
                
                await self._progress("processing", 30.0, "Extraindo frames e lendo mensagens (Isso pode demorar bastante)...")
                
                extractor = WhatsAppVideoExtractor(
                    sample_interval_sec=2.0,
                    similarity_threshold=80.0,
                    # Deixamos o crop config padrão da classe UI
                    crop_config=None 
                )
                
                main_loop = asyncio.get_event_loop()
                def progress_wrapper(pct: float, detail: str):
                    jobs_repository.update_status(self.job_id, status="processing", progress=pct, detail=detail)
                    asyncio.run_coroutine_threadsafe(
                        self.publish_progress(self.job_id, "processing", pct, detail),
                        main_loop
                    )
                
                success, error_msg = await asyncio.get_event_loop().run_in_executor(
                    None, extractor.extract, video_path, json_path, txt_path, progress_wrapper
                )
                
                if not success:
                    raise RuntimeError(f"Erro na extração: {error_msg}")
                    
                await self._progress("processing", 85.0, "Extração concluída, enviando resultados...")
                
                with open(json_path, "r", encoding="utf-8") as f:
                    conversa_json = f.read()
                    
                with open(txt_path, "r", encoding="utf-8") as f:
                    conversa_txt = f.read()
                
                # Upload pro drive
                # folder_id já foi obtido acima
                txt_id = await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.upload_bytes, conversa_txt.encode("utf-8"), "conversa.txt", folder_id, "text/plain"
                )
                json_id = await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.upload_bytes, conversa_json.encode("utf-8"), "conversa.json", folder_id, "application/json"
                )
                
                metadata.setdefault("files", {})["conversa_txt"] = txt_id
                metadata["files"]["conversa_json"] = json_id
                
                metadata["status"] = "completed"
                metadata["progress"] = 100
                metadata["detail"] = "Extração concluída com sucesso."
                
                await asyncio.get_event_loop().run_in_executor(
                    None, self.drive.update_json, metadata_file_id, metadata
                )

                # Cacheia ids e texto extraído no MySQL para listagem rápida
                jobs_repository.update_extract_result(
                    self.job_id,
                    conversa_txt_id=txt_id,
                    conversa_json_id=json_id,
                    conversa_text=conversa_txt,
                )

                await self._progress("completed", 100.0, "Processo finalizado")
                
        except Exception as e:
            error_str = traceback.format_exc()
            logger.error(f"[{self.job_id}] Erro na extração:\n{error_str}")
            await self._progress("error", 0, f"Erro: {str(e)}", error=str(e))
            
            try:
                folder_id = self.drive.find_folder_by_job_id(self.job_id)
                if folder_id:
                    meta_id = self.drive.find_file_in_folder(folder_id, "metadata.json")
                    if meta_id:
                        metadata = self.drive.read_json(meta_id)
                        metadata["status"] = "error"
                        metadata["error"] = str(e)
                        self.drive.update_json(meta_id, metadata)
            except:
                pass
