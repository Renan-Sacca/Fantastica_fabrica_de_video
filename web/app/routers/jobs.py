import asyncio
import os
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.config import BASE_DIR
from app.drive import get_drive
from app.repositories import jobs as jobs_repo

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)

TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))


@router.get("")
async def list_jobs(request: Request):
    """Lista jobs do usuário logado (excluindo deletados)."""
    user = get_current_user(request)
    user_id = user["id"] if user else None
    return jobs_repo.get_all_jobs(user_id=user_id)


@router.get("/{job_id}")
async def job_status(job_id: str):
    """Status atual de um job específico (lido do MySQL)."""
    job = jobs_repo.get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    return job


@router.delete("/{job_id}")
async def api_delete_job(request: Request, job_id: str):
    """Soft delete: marca como deletado no MySQL e move pasta para 'Deletados' no Drive."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    # Verificar ownership
    if job_info.get("user_id") != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)

    try:
        loop = asyncio.get_event_loop()

        # Mover pasta no Drive para "Deletados" dentro do contexto do tipo de vídeo
        if job_info.get("drive_folder_id"):
            drive = get_drive(TOKEN_FILE)
            # Determinar pasta de contexto pelo video_type
            _type_folders = {
                "whatsapp": "WhatsApp",
                "whatsapp_extract": "whatsapp_extracts",
            }
            drive_type_folder = _type_folders.get(job_info.get("video_type", ""), None)
            await loop.run_in_executor(
                None, drive.move_to_deleted, job_info["drive_folder_id"], drive_type_folder
            )

        # Soft delete no MySQL
        jobs_repo.soft_delete_job(job_id)

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Erro ao deletar job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.patch("/{job_id}/rename")
async def api_rename_job(request: Request, job_id: str):
    """Renomeia o título de um job no MySQL e no Drive (pasta + metadata.json)."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON inválido"}, status_code=400)

    new_title = (body.get("title") or "").strip()
    if not new_title:
        return JSONResponse({"error": "Título não pode ser vazio"}, status_code=400)

    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)

    if job_info.get("user_id") != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)

    try:
        loop = asyncio.get_event_loop()
        drive = get_drive(TOKEN_FILE)

        # 1. Renomear pasta no Drive: "TituloAntigo-jobid" → "TituloNovo-jobid"
        if job_info.get("drive_folder_id"):
            new_folder_name = f"{new_title}-{job_id}"
            await loop.run_in_executor(
                None, drive.rename_folder, job_info["drive_folder_id"], new_folder_name
            )

        # 2. Atualizar title no metadata.json do Drive
        if job_info.get("metadata_file_id"):
            try:
                metadata = await loop.run_in_executor(
                    None, drive.read_json, job_info["metadata_file_id"]
                )
                metadata["title"] = new_title
                await loop.run_in_executor(
                    None, drive.update_json, job_info["metadata_file_id"], metadata
                )
            except Exception as e:
                logger.warning(f"[{job_id}] Não foi possível atualizar metadata.json: {e}")

        # 3. Atualizar título no MySQL
        jobs_repo.rename_job(job_id, new_title)

        return {"status": "ok", "title": new_title}
    except Exception as e:
        logger.error(f"Erro ao renomear job {job_id}: {e}")
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
