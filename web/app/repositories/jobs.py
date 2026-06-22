"""Repositório de Jobs — toda a persistência básica passa por aqui (MySQL/ORM).

A listagem usa exclusivamente o banco (rápido). O Google Drive continua sendo a
fonte dos arquivos pesados (vídeos, imagens, conversa) e do metadata completo,
consultado apenas sob demanda na tela de detalhe.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import with_polymorphic

from app.database import SessionLocal
from app.models import Job, WhatsAppExtractJob, WhatsAppJob

logger = logging.getLogger(__name__)

# Entidade polimórfica: carrega as colunas de todas as subclasses num único JOIN,
# evitando N+1 queries na listagem.
JobPoly = with_polymorphic(Job, "*")

# Campos específicos por tipo de vídeo, mapeados a partir do metadata.
_WHATSAPP_FIELDS = (
    "contact_name", "contact_status", "video_format", "fps",
    "speed", "reading_speed", "scroll_speed", "animation_style",
)
_EXTRACT_FIELDS = ("conversa_txt_id", "conversa_json_id", "conversa_text")


def _model_for(video_type: str):
    if video_type == "whatsapp":
        return WhatsAppJob
    if video_type == "whatsapp_extract":
        return WhatsAppExtractJob
    return Job


def _apply_common(job: Job, metadata: dict, drive_folder_id: str, metadata_file_id: Optional[str]) -> None:
    job.title = metadata.get("title", job.title or "")
    job.status = metadata.get("status", job.status or "pending")
    job.progress = metadata.get("progress", job.progress or 0)
    job.detail = metadata.get("detail", job.detail)
    job.error = metadata.get("error", job.error)
    if drive_folder_id:
        job.drive_folder_id = drive_folder_id
    if metadata_file_id:
        job.metadata_file_id = metadata_file_id
    if metadata.get("video_drive_id") is not None:
        job.video_drive_id = metadata.get("video_drive_id")
    if metadata.get("video_url") is not None:
        job.video_url = metadata.get("video_url")
    if metadata.get("user_id") is not None:
        job.user_id = metadata.get("user_id")


def _apply_specific(job: Job, video_type: str, metadata: dict) -> None:
    if video_type == "whatsapp":
        for f in _WHATSAPP_FIELDS:
            if f in metadata:
                setattr(job, f, metadata[f])
    elif video_type == "whatsapp_extract":
        files = metadata.get("files", {})
        if "video_original" in files:
            job.video_original_id = files.get("video_original")
        if "conversa_txt" in files:
            job.conversa_txt_id = files.get("conversa_txt")
        if "conversa_json" in files:
            job.conversa_json_id = files.get("conversa_json")
        for f in _EXTRACT_FIELDS:
            if f in metadata:
                setattr(job, f, metadata[f])


def save_job(metadata: dict, drive_folder_id: str, metadata_file_id: Optional[str]) -> None:
    """Cria ou atualiza (upsert) um job a partir do dicionário de metadata."""
    job_id = metadata["job_id"]
    video_type = metadata.get("video_type", "whatsapp")
    with SessionLocal() as session:
        job = session.scalar(select(Job).where(Job.job_id == job_id))
        if job is None:
            model = _model_for(video_type)
            job = model(job_id=job_id, video_type=video_type)
            session.add(job)
        _apply_common(job, metadata, drive_folder_id, metadata_file_id)
        _apply_specific(job, video_type, metadata)
        session.commit()
        logger.info(f"[{job_id}] Job salvo no MySQL (tipo={video_type}).")


def update_extract_text(job_id: str, conversa_text: str) -> bool:
    """Atualiza o texto extraído de um WhatsAppExtractJob."""
    with SessionLocal() as session:
        job = session.scalar(select(JobPoly).where(Job.job_id == job_id))
        if not job:
            return False
        if hasattr(job, "conversa_text"):
            job.conversa_text = conversa_text
            session.commit()
            return True
        return False


def update_basic(job_id: str, **fields) -> None:
    """Atualiza campos básicos (ex.: title, video_type) de um job existente."""
    with SessionLocal() as session:
        job = session.scalar(select(Job).where(Job.job_id == job_id))
        if not job:
            return
        for key, value in fields.items():
            if hasattr(job, key):
                setattr(job, key, value)
        session.commit()


def get_job(job_id: str) -> Optional[dict]:
    with SessionLocal() as session:
        job = session.scalar(select(JobPoly).where(Job.job_id == job_id))
        return job.to_dict() if job else None


def get_all_jobs(video_type: Optional[str] = None, user_id: Optional[int] = None) -> list[dict]:
    """Lista jobs (mais recentes primeiro), opcionalmente filtrando por tipo e usuário."""
    with SessionLocal() as session:
        stmt = select(JobPoly)
        if video_type:
            stmt = stmt.where(Job.video_type == video_type)
        if user_id is not None:
            stmt = stmt.where(Job.user_id == user_id)
        stmt = stmt.order_by(Job.created_at.desc())
        return [j.to_dict() for j in session.scalars(stmt).all()]


def delete_job(job_id: str) -> Optional[dict]:
    with SessionLocal() as session:
        job = session.scalar(select(Job).where(Job.job_id == job_id))
        if not job:
            return None
        data = job.to_dict()
        session.delete(job)
        session.commit()
        return data


# ── Sincronização (migração de dados existentes no Drive) ──

# Pasta no Drive → tipo de vídeo
_DRIVE_TYPE_FOLDERS = {
    "WhatsApp": "whatsapp",
    "whatsapp_extracts": "whatsapp_extract",
}


def sync_with_drive(drive_client) -> None:
    """Varre as pastas de jobs no Drive e popula o MySQL.

    Lê o metadata.json de cada job para preencher todos os campos. É uma
    operação lenta, pensada para migração/recuperação manual (rota /api/sync).
    """
    try:
        root_id = drive_client.get_or_create_folder("FantasticaFabricaDeVideo")
        total = 0
        for folder_name, video_type in _DRIVE_TYPE_FOLDERS.items():
            type_id = drive_client.get_or_create_folder(folder_name, root_id)
            criados_id = drive_client.get_or_create_folder("Criados", type_id)

            query = (
                f"'{criados_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and trashed=false"
            )
            response = drive_client.service.files().list(
                q=query, spaces="drive", fields="files(id, name, createdTime)"
            ).execute(num_retries=5)

            for f in response.get("files", []):
                folder_id = f["id"]
                meta_id = drive_client.find_file_in_folder(folder_id, "metadata.json")
                if not meta_id:
                    continue
                try:
                    metadata = drive_client.read_json(meta_id)
                except Exception as e:
                    logger.warning(f"Falha ao ler metadata de {f['name']}: {e}")
                    continue
                metadata.setdefault("video_type", video_type)
                metadata.setdefault("title", f["name"].rsplit("-", 1)[0])
                save_job(metadata, folder_id, meta_id)
                total += 1

        logger.info(f"Sincronização Drive → MySQL concluída. {total} jobs importados.")
    except Exception as e:
        logger.error(f"Erro ao sincronizar com o Drive: {e}")
