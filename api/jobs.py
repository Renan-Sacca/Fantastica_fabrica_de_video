"""Gerenciamento de jobs de renderização."""
from __future__ import annotations

import asyncio
import json
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from api.config import MAX_CONCURRENT_RENDERS, OUTPUT_DIR
from api.models import JobStatus, RenderJob

logger = logging.getLogger(__name__)

# Armazenamento em memória dos jobs
_jobs: dict[str, RenderJob] = {}

# Executor de threads (ThreadPoolExecutor para evitar problemas de serialização)
_executor: Optional[ThreadPoolExecutor] = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RENDERS)
    return _executor


def create_job(job: RenderJob) -> RenderJob:
    """Registra um novo job."""
    _jobs[job.job_id] = job
    logger.info(f"Job criado: {job.job_id}")
    return job


def get_job(job_id: str) -> Optional[RenderJob]:
    """Retorna um job pelo ID."""
    return _jobs.get(job_id)


def get_all_jobs() -> list[RenderJob]:
    """Retorna todos os jobs, mais recentes primeiro."""
    return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


def delete_job(job_id: str) -> bool:
    """Remove um job."""
    if job_id in _jobs:
        job = _jobs[job_id]
        # Remover arquivo de saída se existir
        if job.output_path:
            try:
                Path(job.output_path).unlink(missing_ok=True)
            except Exception:
                pass
        del _jobs[job_id]
        return True
    return False


def update_job_progress(
    job_id: str,
    status: Optional[JobStatus] = None,
    progress: Optional[float] = None,
    detail: Optional[str] = None,
    error: Optional[str] = None,
    output_path: Optional[str] = None,
    total_frames: Optional[int] = None,
    current_frame: Optional[int] = None,
) -> None:
    """Atualiza o progresso de um job."""
    job = _jobs.get(job_id)
    if not job:
        return

    if status is not None:
        job.status = status
    if progress is not None:
        job.progress = progress
    if detail is not None:
        job.detail = detail
    if error is not None:
        job.error = error
    if output_path is not None:
        job.output_path = output_path
    if total_frames is not None:
        job.total_frames = total_frames
    if current_frame is not None:
        job.current_frame = current_frame

    # Salvar progresso em arquivo para comunicação entre processos
    _write_progress_file(job_id, job)


def _write_progress_file(job_id: str, job: RenderJob) -> None:
    """Escreve progresso em arquivo JSON para comunicação inter-processos."""
    progress_file = OUTPUT_DIR / f".progress_{job_id}.json"
    try:
        data = {
            "status": job.status.value,
            "progress": job.progress,
            "detail": job.detail,
            "error": job.error,
            "output_path": job.output_path,
            "total_frames": job.total_frames,
            "current_frame": job.current_frame,
        }
        progress_file.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        logger.error(f"Erro ao escrever progresso: {e}")


def read_progress_file(job_id: str) -> Optional[dict]:
    """Lê progresso do arquivo JSON."""
    progress_file = OUTPUT_DIR / f".progress_{job_id}.json"
    try:
        if progress_file.exists():
            return json.loads(progress_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def sync_job_from_progress_file(job_id: str) -> None:
    """Sincroniza estado do job a partir do arquivo de progresso."""
    data = read_progress_file(job_id)
    if not data:
        return

    job = _jobs.get(job_id)
    if not job:
        return

    job.status = JobStatus(data["status"])
    job.progress = data["progress"]
    job.detail = data["detail"]
    job.error = data.get("error")
    job.output_path = data.get("output_path")
    job.total_frames = data.get("total_frames", 0)
    job.current_frame = data.get("current_frame", 0)


def _run_render_job(job: RenderJob) -> None:
    """Função de execução do job em thread separada."""
    from renderer.engine import render_video

    try:
        render_video(job)
    except Exception as e:
        logger.error(f"Erro no job {job.job_id}: {e}\n{traceback.format_exc()}")
        update_job_progress(
            job.job_id,
            status=JobStatus.ERROR,
            error=str(e),
            detail=f"Erro: {e}",
        )


async def start_render_job(job: RenderJob) -> None:
    """Inicia a renderização em uma thread separada."""
    loop = asyncio.get_event_loop()
    loop.run_in_executor(get_executor(), _run_render_job, job)
