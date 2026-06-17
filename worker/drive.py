"""Cliente Google Drive para o serviço worker."""
from __future__ import annotations

import json
import logging
from io import BytesIO
from pathlib import Path
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
            self.creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            self.service = build("drive", "v3", credentials=self.creds)
            logger.info("Worker autenticado no Google Drive com sucesso (OAuth2)!")
        except Exception as e:
            logger.error(f"Erro ao carregar token.json: {e}")
            raise RuntimeError(f"Falha na autenticação do Drive no Worker: {e}")

    def _fresh_http(self):
        """Conexão HTTP autorizada nova e isolada por download (evita erro SSL)."""
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        return AuthorizedHttp(self.creds, http=httplib2.Http())

    def find_folder_by_job_id(self, job_id: str) -> Optional[str]:
        """
        Busca a pasta do job pelo job_id (que faz parte do nome da pasta).
        Ex: 'GarotaDaCaixa-a3f2c1' → job_id='a3f2c1'
        """
        query = (
            f"name contains '{job_id}' "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        results = self.service.files().list(
            q=query, fields="files(id, name)", spaces="drive"
        ).execute(num_retries=5)
        files = results.get("files", [])
        if not files:
            logger.warning(f"Pasta para job_id={job_id} não encontrada no Drive")
            return None
        logger.info(f"Pasta encontrada: {files[0]['name']} ({files[0]['id']})")
        return files[0]["id"]

    def find_file_in_folder(self, folder_id: str, filename: str) -> Optional[str]:
        """Busca um arquivo por nome em uma pasta."""
        query = (
            f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        )
        results = self.service.files().list(q=query, fields="files(id)").execute(num_retries=5)
        files = results.get("files", [])
        return files[0]["id"] if files else None

    def read_json(self, file_id: str) -> dict:
        """Lê e parseia um arquivo JSON."""
        from googleapiclient.http import MediaIoBaseDownload
        request = self.service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk(num_retries=5)
        return json.loads(fh.getvalue().decode("utf-8"))

    def update_json(self, file_id: str, data: dict) -> None:
        """Atualiza um arquivo JSON existente no Drive."""
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        media = MediaIoBaseUpload(BytesIO(content), mimetype="application/json")
        self.service.files().update(fileId=file_id, media_body=media).execute(num_retries=5)

    def download_file(self, file_id: str, dest_path: Path, max_attempts: int = 3) -> None:
        """Baixa um arquivo do Drive para o disco, em chunks e com conexão isolada.

        Cada tentativa usa uma conexão HTTP nova, evitando o erro de SSL
        (DECRYPTION_FAILED_OR_BAD_RECORD_MAC) por reuso de conexão corrompida.
        """
        from googleapiclient.http import MediaIoBaseDownload

        last_err = None
        for attempt in range(1, max_attempts + 1):
            try:
                request = self.service.files().get_media(fileId=file_id, acknowledgeAbuse=True)
                request.http = self._fresh_http()
                fh = BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    _, done = downloader.next_chunk(num_retries=3)
                dest_path.write_bytes(fh.getvalue())
                return
            except Exception as e:
                last_err = e
                logger.warning(
                    f"download_file({file_id}) tentativa {attempt}/{max_attempts} falhou: {e}"
                )
        raise last_err

    def upload_bytes(
        self,
        content: bytes,
        filename: str,
        parent_id: str,
        mime_type: str = "application/octet-stream",
    ) -> str:
        """Faz upload de bytes. Retorna o ID do arquivo criado."""
        metadata = {"name": filename, "parents": [parent_id]}
        media = MediaIoBaseUpload(BytesIO(content), mimetype=mime_type)
        file = self.service.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute(num_retries=5)
        return file["id"]

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """Obtém ou cria uma pasta."""
        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        if parent_id:
            query += f" and '{parent_id}' in parents"
        results = self.service.files().list(q=query, fields="files(id)").execute(num_retries=5)
        files = results.get("files", [])
        if files:
            return files[0]["id"]
        metadata: dict = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            metadata["parents"] = [parent_id]
        folder = self.service.files().create(body=metadata, fields="id").execute(num_retries=5)
        return folder["id"]

    def delete_file(self, file_id: str) -> None:
        """Deleta um arquivo permanentemente do Drive."""
        try:
            self.service.files().delete(fileId=file_id).execute(num_retries=5)
            logger.info(f"Arquivo deletado do Drive: {file_id}")
        except Exception as e:
            logger.warning(f"Erro ao deletar arquivo {file_id}: {e}")

    def make_public(self, file_id: str) -> str:
        """Torna o arquivo público e retorna o link."""
        try:
            self.service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute(num_retries=5)
        except Exception as e:
            logger.warning(f"Não foi possível tornar o arquivo público: {e}")
        return f"https://drive.google.com/file/d/{file_id}/view"
