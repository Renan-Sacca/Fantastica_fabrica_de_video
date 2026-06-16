import asyncio
import logging
import os
from fastapi import APIRouter, Header, Request, Response

from app import jobs_store
from app.config import BASE_DIR
from app.drive import get_drive

router = APIRouter(prefix="/api", tags=["drive"])
logger = logging.getLogger(__name__)

TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))

@router.get("/drive/media/{file_id}")
async def get_drive_media(file_id: str, range: str = Header(None)):
    """Retorna o conteúdo binário de um arquivo do Drive (usado para preview)."""
    drive = get_drive(TOKEN_FILE)
    loop = asyncio.get_event_loop()
    try:
        content = await loop.run_in_executor(None, drive.read_bytes, file_id)
        file_size = len(content)
        
        if range:
            start_str, end_str = range.replace("bytes=", "").split("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
            chunk = content[start:end+1]
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(chunk)),
            }
            return Response(content=chunk, status_code=206, headers=headers)
            
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size)
        }
        return Response(content=content, headers=headers)
    except Exception as e:
        logger.error(f"Erro ao obter mídia {file_id}: {e}")
        return Response(content=b"Not found", status_code=404)

@router.post("/sync")
async def sync_drive(request: Request):
    """Sincroniza os jobs com o Drive manualmente."""
    drive = get_drive(TOKEN_FILE)
    await asyncio.get_event_loop().run_in_executor(None, jobs_store.sync_with_drive, drive)
    return {"status": "ok"}
