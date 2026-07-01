"""Cliente Google Drive para o worker do OmniVoice."""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger("OmniDrive")
SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveClient:
    def __init__(self, token_file: str):
        self.creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        self.service = build("drive", "v3", credentials=self.creds, cache_discovery=False)
        logger.info("Worker OmniVoice autenticado no Google Drive (OAuth2).")

    def upload_bytes(
        self, content: bytes, filename: str, parent_id: str,
        mime_type: str = "application/octet-stream",
    ) -> str:
        metadata = {"name": filename, "parents": [parent_id]}
        media = MediaIoBaseUpload(BytesIO(content), mimetype=mime_type)
        file = self.service.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute(num_retries=5)
        return file["id"]

    def make_public(self, file_id: str) -> str:
        try:
            self.service.permissions().create(
                fileId=file_id, body={"type": "anyone", "role": "reader"},
            ).execute(num_retries=5)
        except Exception as e:
            logger.warning(f"Não foi possível tornar público {file_id}: {e}")
        return f"https://drive.google.com/file/d/{file_id}/view"

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
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
