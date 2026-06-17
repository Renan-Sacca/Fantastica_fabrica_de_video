import asyncio
import os
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import BASE_DIR
from app.drive import get_drive
from app.repositories import jobs as jobs_repo

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)

TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

@router.get("")
async def list_jobs():
    """Lista todos os jobs direto do MySQL (rápido, sem tocar no Drive)."""
    return jobs_repo.get_all_jobs()

@router.get("/{job_id}")
async def job_status(job_id: str):
    """Status atual de um job específico (lido do MySQL)."""
    job = jobs_repo.get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    return job

@router.delete("/{job_id}")
async def api_delete_job(job_id: str, delete_drive: bool = False):
    """Remove um job. Opcionalmente remove a pasta do Drive também."""
    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    try:
        if delete_drive and job_info.get("drive_folder_id"):
            drive = get_drive(TOKEN_FILE)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, drive.delete_file, job_info["drive_folder_id"])

        jobs_repo.delete_job(job_id)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Erro ao remover job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/{job_id}/details")
async def api_job_details(job_id: str):
    """Retorna os metadados completos (JSON do Drive) para o modal de duplicação."""
    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    if not job_info.get("metadata_file_id"):
        return JSONResponse({"error": "metadata_file_id ausente para este job"}, status_code=404)

    drive = get_drive(TOKEN_FILE)
    try:
        loop = asyncio.get_event_loop()
        metadata = await loop.run_in_executor(None, drive.read_json, job_info["metadata_file_id"])
        return JSONResponse(metadata)
    except Exception as e:
        logger.error(f"Erro ao buscar metadados do job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
