"""Cliente Google Drive para o serviço web."""
from __future__ import annotations

import json
import logging
import threading
from io import BytesIO
from typing import Optional

import httplib2
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

class DriveClient:
    """Cliente Drive via OAuth2 (token.json)."""

    def __init__(self, token_file: str):
        try:
            self.creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            # cache_discovery=False previne erros de concorrência no file_cache
            self.service = build("drive", "v3", credentials=self.creds, cache_discovery=False)
            logger.info("Autenticado no Google Drive com sucesso (OAuth2)!")
        except Exception as e:
            logger.error(f"Erro ao carregar token.json: {e}")
            raise RuntimeError(f"Falha na autenticação do Drive: {e}")
        self._folder_cache: dict[str, str] = {}

    def _fresh_http(self) -> AuthorizedHttp:
        """Cria uma conexão HTTP autorizada nova e isolada.

        Downloads paralelos não podem compartilhar a mesma conexão do
        ``self.service`` (httplib2 não é thread-safe) — isso causa erros de
        SSL (DECRYPTION_FAILED_OR_BAD_RECORD_MAC). Cada download usa a sua.
        """
        return AuthorizedHttp(self.creds, http=httplib2.Http())

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
        Cria a hierarquia de pastas para um job.
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

    def copy_file(self, file_id: str, new_parent_id: str, new_name: Optional[str] = None) -> str:
        """Copia um arquivo existente no Drive para uma nova pasta. Retorna o ID da cópia."""
        body = {"parents": [new_parent_id]}
        if new_name:
            body["name"] = new_name
            
        copied_file = self.service.files().copy(
            fileId=file_id, 
            body=body,
            fields="id"
        ).execute(num_retries=5)
        return copied_file["id"]

    # ── Leitura ──

    def read_bytes(self, file_id: str, max_attempts: int = 3) -> bytes:
        """Lê o conteúdo binário de um arquivo do Drive.

        Cada tentativa usa uma conexão HTTP nova e isolada, evitando o erro de
        SSL que ocorre quando downloads paralelos compartilham a mesma conexão.
        """
        from googleapiclient.http import MediaIoBaseDownload

        last_err: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                request = self.service.files().get_media(fileId=file_id)
                request.http = self._fresh_http()
                fh = BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    _, done = downloader.next_chunk(num_retries=3)
                return fh.getvalue()
            except Exception as e:
                last_err = e
                logger.warning(
                    f"read_bytes({file_id}) tentativa {attempt}/{max_attempts} falhou: {e}"
                )
        raise last_err  # type: ignore[misc]

    def read_json(self, file_id: str) -> dict:
        """Lê e parseia um arquivo JSON do Drive."""
        content = self.read_bytes(file_id)
        return json.loads(content.decode("utf-8"))

    def update_json(self, file_id: str, data: dict) -> None:
        """Atualiza o conteúdo de um arquivo JSON existente."""
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        media = MediaIoBaseUpload(BytesIO(content), mimetype="application/json")
        self.service.files().update(fileId=file_id, media_body=media).execute(num_retries=5)

    def update_file(self, file_id: str, content: bytes, mime_type: Optional[str] = None) -> None:
        """Atualiza o conteúdo de um arquivo existente (bytes)."""
        media = MediaIoBaseUpload(BytesIO(content), mimetype=mime_type or "application/octet-stream")
        self.service.files().update(fileId=file_id, media_body=media).execute(num_retries=5)

    def find_file_in_folder(self, folder_id: str, filename: str) -> Optional[str]:
        """Busca um arquivo por nome dentro de uma pasta. Retorna o ID."""
        query = (
            f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        )
        results = self.service.files().list(q=query, fields="files(id)").execute(num_retries=5)
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def delete_file(self, file_id: str) -> None:
        """Exclui permanentemente um arquivo ou pasta do Drive."""
        self.service.files().delete(fileId=file_id).execute(num_retries=5)

    def move_to_deleted(self, folder_id: str, drive_type_folder: Optional[str] = None) -> str:
        """Move uma pasta para 'Deletados' dentro do contexto correto do tipo de vídeo.

        Se drive_type_folder for passado (ex: 'WhatsApp', 'whatsapp_extracts'),
        a pasta vai para FantasticaFabricaDeVideo/{drive_type_folder}/Deletados.
        Caso contrário, vai para FantasticaFabricaDeVideo/Deletados (fallback).
        """
        root = self.get_or_create_folder("FantasticaFabricaDeVideo")

        if drive_type_folder:
            type_folder = self.get_or_create_folder(drive_type_folder, root)
            deleted_folder = self.get_or_create_folder("Deletados", type_folder)
        else:
            deleted_folder = self.get_or_create_folder("Deletados", root)

        file_meta = self.service.files().get(
            fileId=folder_id, fields="parents"
        ).execute(num_retries=5)
        current_parents = ",".join(file_meta.get("parents", []))

        self.service.files().update(
            fileId=folder_id,
            addParents=deleted_folder,
            removeParents=current_parents,
            fields="id, parents",
        ).execute(num_retries=5)

        logger.info(f"Pasta {folder_id} movida para Deletados ({drive_type_folder or 'raiz'})")
        return deleted_folder

    def rename_folder(self, folder_id: str, new_name: str) -> None:
        """Renomeia uma pasta ou arquivo no Drive."""
        self.service.files().update(
            fileId=folder_id,
            body={"name": new_name},
            fields="id, name",
        ).execute(num_retries=5)
        logger.info(f"Renomeado {folder_id} → {new_name}")

    def get_folder_link(self, folder_id: str) -> str:
        """Retorna o link web da pasta no Drive."""
        return f"https://drive.google.com/drive/folders/{folder_id}"


_thread_local = threading.local()

def get_drive(token_file: str) -> DriveClient:
    """Retorna uma instância única de DriveClient por thread. Garante thread-safety absoluto sem locks."""
    if not hasattr(_thread_local, "drive"):
        _thread_local.drive = DriveClient(token_file)
    return _thread_local.drive
