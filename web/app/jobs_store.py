"""Armazenamento local de jobs (índice persistente em JSON).

Mapeia job_id → informações mínimas para localizar os dados no Drive.
A fonte de verdade dos dados do job é sempre o Drive (metadata.json).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from threading import Lock
from typing import Optional

from app.config import JOBS_FILE

logger = logging.getLogger(__name__)
_lock = Lock()
_store: dict[str, dict] = {}


def init() -> None:
    """Carrega o índice de jobs do disco na inicialização."""
    global _store
    if JOBS_FILE.exists():
        try:
            _store = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
            logger.info(f"Jobs carregados: {len(_store)} registros")
        except Exception as e:
            logger.warning(f"Falha ao carregar jobs.json: {e}")
            _store = {}


def _save() -> None:
    JOBS_FILE.write_text(
        json.dumps(_store, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def add_job(
    job_id: str,
    title: str,
    video_type: str,
    drive_folder_id: str,
    metadata_file_id: str,
) -> None:
    """Registra um novo job no índice local."""
    with _lock:
        _store[job_id] = {
            "job_id": job_id,
            "title": title,
            "video_type": video_type,
            "drive_folder_id": drive_folder_id,
            "metadata_file_id": metadata_file_id,
            "created_at": datetime.now().isoformat(),
        }
        _save()



def update_job(job_id: str, updates: dict) -> None:
    """Atualiza campos de um job existente."""
    with _lock:
        if job_id in _store:
            _store[job_id].update(updates)
            _save()

def get_job(job_id: str) -> Optional[dict]:
    """Retorna as informações de um job pelo ID."""
    return _store.get(job_id)


def get_all_jobs() -> list[dict]:
    """Retorna todos os jobs, do mais recente para o mais antigo."""
    return sorted(
        _store.values(),
        key=lambda x: x.get("created_at", ""),
        reverse=True,
    )


def delete_job(job_id: str) -> Optional[dict]:
    """Remove um job do índice. Retorna o job removido."""
    with _lock:
        job = _store.pop(job_id, None)
        if job:
            _save()
        return job

from datetime import datetime

def sync_with_drive(drive_client) -> None:
    """Sincroniza o cache local lendo apenas as pastas de jobs do Drive (mais rápido)."""
    try:
        root_id = drive_client.get_or_create_folder("FantasticaFabricaDeVideo")
        zap_id = drive_client.get_or_create_folder("WhatsApp", root_id)
        criados_id = drive_client.get_or_create_folder("Criados", zap_id)
        
        query = f"'{criados_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        response = drive_client.service.files().list(
            q=query, spaces='drive', fields='files(id, name, createdTime)'
        ).execute(num_retries=5)
        folders = response.get('files', [])

        global _store
        with _lock:
            _store.clear()
            for f in folders:
                folder_id = f['id']
                name = f['name']
                
                parts = name.rsplit("-", 1)
                if len(parts) == 2:
                    title, job_id = parts
                else:
                    title, job_id = name, folder_id[:8]
                    
                _store[job_id] = {
                    "job_id": job_id,
                    "title": title,
                    "video_type": "whatsapp",
                    "drive_folder_id": folder_id,
                    "metadata_file_id": None,  # Buscado apenas sob demanda quando abrir o job
                    "created_at": f.get('createdTime', datetime.now().isoformat()),
                }
            _save()
        logger.info(f"Sincronização rápida com Drive concluída. {len(_store)} jobs.")
    except Exception as e:
        logger.error(f"Erro ao sincronizar com o Drive: {e}")
