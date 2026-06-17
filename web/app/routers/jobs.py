import asyncio
import os
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import jobs_store
from app.config import BASE_DIR
from app.drive import get_drive

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)

TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

@router.get("")
async def list_jobs():
    """Lista todos os jobs com status atual do Drive."""
    all_jobs = jobs_store.get_all_jobs()
    drive = get_drive(TOKEN_FILE)
    result = []
    
    async def fetch_meta(j_info):
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, drive.read_json, j_info["metadata_file_id"]
            )
        except Exception:
            return {
                **j_info, "status": "unknown", "progress": 0,
                "detail": "Não foi possível ler status do Drive",
            }

    result = await asyncio.gather(*(fetch_meta(ji) for ji in all_jobs))
    return result

@router.get("/{job_id}")
async def job_status(job_id: str):
    """Status atual de um job específico."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    drive = get_drive(TOKEN_FILE)
    try:
        metadata = await asyncio.get_event_loop().run_in_executor(
            None, drive.read_json, job_info["metadata_file_id"]
        )
        return metadata
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.delete("/{job_id}")
async def api_delete_job(job_id: str, delete_drive: bool = False):
    """Remove um job. Opcionalmente remove a pasta do Drive também."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
        
    try:
        if delete_drive:
            drive = get_drive(TOKEN_FILE)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, drive.delete_file, job_info["drive_folder_id"])
            
        jobs_store.delete_job(job_id)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Erro ao remover job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/{job_id}/details")
async def api_job_details(job_id: str):
    """Retorna os metadados brutos (JSON) de um job para listagem no modal de duplicação."""
    job_info = jobs_store.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    drive = get_drive(TOKEN_FILE)
    try:
        loop = asyncio.get_event_loop()
        metadata = await loop.run_in_executor(None, drive.read_json, job_info["metadata_file_id"])
        return JSONResponse(metadata)
    except Exception as e:
        logger.error(f"Erro ao buscar metadados do job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
