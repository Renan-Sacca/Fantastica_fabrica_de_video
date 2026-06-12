"""Cliente Google Drive para o serviço web."""
from __future__ import annotations

import json
import logging
from io import BytesIO
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveClient:
    """Cliente Drive via OAuth2 (token.json)."""

    def __init__(self, token_file: str):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            self.service = build("drive", "v3", credentials=creds)
            logger.info("Autenticado no Google Drive com sucesso (OAuth2)!")
        except Exception as e:
            logger.error(f"Erro ao carregar token.json: {e}")
            raise RuntimeError(f"Falha na autenticação do Drive: {e}")
        self._folder_cache: dict[str, str] = {}

    # ── Pastas ──

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """Obtém ou cria uma pasta. Retorna o ID."""
        cache_key = f"{parent_id}:{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = self.service.files().list(
            q=query, fields="files(id)", spaces="drive"
        ).execute(num_retries=5)

        files = results.get("files", [])
        if files:
            folder_id = files[0]["id"]
        else:
            metadata: dict = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_id:
                metadata["parents"] = [parent_id]
            folder = self.service.files().create(
                body=metadata, fields="id"
            ).execute(num_retries=5)
            folder_id = folder["id"]

        self._folder_cache[cache_key] = folder_id
        return folder_id

    def create_job_folder(
        self, title: str, job_id: str, drive_type_folder: str
    ) -> str:
        """
        Cria a hierarquia de pastas para um job:
        FantasticaFabricaDeVideo/<Tipo>/Criados/<Titulo>-<job_id>/
        Retorna o ID da pasta do job.
        """
        root = self.get_or_create_folder("FantasticaFabricaDeVideo")
        type_folder = self.get_or_create_folder(drive_type_folder, root)
        criados = self.get_or_create_folder("Criados", type_folder)
        folder_name = f"{title}-{job_id}"
        job_folder = self.get_or_create_folder(folder_name, criados)
        # Criar subpasta de imagens
        self.get_or_create_folder("imagens", job_folder)
        logger.info(f"Pasta criada no Drive: {folder_name} ({job_folder})")
        return job_folder

    # ── Upload ──

    def upload_bytes(
        self,
        content: bytes,
        filename: str,
        parent_id: str,
        mime_type: str = "application/octet-stream",
    ) -> str:
        """Faz upload de bytes para o Drive. Retorna o ID do arquivo."""
        metadata = {"name": filename, "parents": [parent_id]}
        media = MediaIoBaseUpload(BytesIO(content), mimetype=mime_type)
        file = self.service.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute(num_retries=5)
        return file["id"]

    def upload_json(self, data: dict, filename: str, parent_id: str) -> str:
        """Upload de dicionário como JSON. Retorna o ID do arquivo."""
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        return self.upload_bytes(content, filename, parent_id, "application/json")

    # ── Leitura ──

    def read_bytes(self, file_id: str) -> bytes:
        """Lê o conteúdo binário de um arquivo do Drive."""
        return self.service.files().get_media(fileId=file_id).execute(num_retries=5)

    def read_json(self, file_id: str) -> dict:
        """Lê e parseia um arquivo JSON do Drive."""
        content = self.read_bytes(file_id)
        return json.loads(content.decode("utf-8"))

    def update_json(self, file_id: str, data: dict) -> None:
        """Atualiza o conteúdo de um arquivo JSON existente."""
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        media = MediaIoBaseUpload(BytesIO(content), mimetype="application/json")
        self.service.files().update(fileId=file_id, media_body=media).execute(num_retries=5)

    def find_file_in_folder(self, folder_id: str, filename: str) -> Optional[str]:
        """Busca um arquivo por nome dentro de uma pasta. Retorna o ID."""
        query = (
            f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        )
        results = self.service.files().list(q=query, fields="files(id)").execute(num_retries=5)
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def get_folder_link(self, folder_id: str) -> str:
        """Retorna o link web da pasta no Drive."""
        return f"https://drive.google.com/drive/folders/{folder_id}"


def get_drive(token_file: str) -> DriveClient:
    """Retorna uma nova instância para evitar stale connections (WRONG_VERSION_NUMBER)."""
    return DriveClient(token_file)
