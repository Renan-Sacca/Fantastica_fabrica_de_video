import asyncio
import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, permission_required
from app.config import BASE_DIR, TEMPLATES_DIR
from app.drive import get_drive
from app.parser import parse_conversation
from app.publisher import publish_job
from app.publisher_agent import publish_correction_job
from app.repositories import jobs as jobs_repo
from app.repositories import text_corrections as corrections_repo
from app.video_types import get_video_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
TOKEN_FILE = os.getenv("TOKEN_FILE", str(BASE_DIR.parent / "token.json"))


def _require_permission(request: Request, perm: str):
    """Retorna (user, error_response). Se ok, error_response é None."""
    user = get_current_user(request)
    if not user:
        return None, RedirectResponse(url="/auth/login", status_code=302)
    if perm not in user.get("permissions", []):
        resp = templates.TemplateResponse(
            "403.html",
            {"request": request, "user": user, "required_permission": perm},
            status_code=403,
        )
        return user, resp
    return user, None

@router.get("", response_class=HTMLResponse)
async def whatsapp_dashboard(request: Request):
    """Página principal de criação de vídeo de WhatsApp."""
    user, err = _require_permission(request, "whatsapp_videos")
    if err:
        return err
    jobs = jobs_repo.get_all_jobs("whatsapp", user_id=user["id"])
    return templates.TemplateResponse(
        "whatsapp/create.html",
        {"request": request, "jobs": jobs, "user": user},
    )

@router.get("/jobs", response_class=HTMLResponse)
async def whatsapp_jobs(request: Request):
    """Página com a lista de jobs de WhatsApp."""
    user, err = _require_permission(request, "whatsapp_videos")
    if err:
        return err
    jobs = jobs_repo.get_all_jobs("whatsapp", user_id=user["id"])
    return templates.TemplateResponse(
        "whatsapp/jobs_list.html",
        {"request": request, "jobs": jobs, "user": user},
    )

@router.get("/video/{job_id}", response_class=HTMLResponse)
async def whatsapp_video_detail(request: Request, job_id: str):
    """Tela de detalhes de um vídeo específico."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)

    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return HTMLResponse("<h1>Job não encontrado</h1>", status_code=404)
    # Verificar se o job pertence ao usuário
    if job_info.get("user_id") != user["id"]:
        return HTMLResponse("<h1>Acesso negado</h1>", status_code=403)

    drive = get_drive(TOKEN_FILE)
    try:
        metadata = await asyncio.get_event_loop().run_in_executor(
            None, drive.read_json, job_info["metadata_file_id"]
        )
    except Exception as e:
        metadata = {**job_info, "status": "error", "error": str(e)}

    # Buscar texto da conversa para preencher a edição
    conversa_text = ""
    conversa_file_id = metadata.get("files", {}).get("conversa")
    if conversa_file_id:
        try:
            bytes_content = await asyncio.get_event_loop().run_in_executor(
                None, drive.read_bytes, conversa_file_id
            )
            conversa_text = bytes_content.decode('utf-8', errors="replace")
        except Exception as e:
            logger.warning(f"Não foi possível ler a conversa do Drive: {e}")

    drive_link = drive.get_folder_link(job_info["drive_folder_id"])

    return templates.TemplateResponse(
        "whatsapp/video_detail.html",
        {
            "request": request,
            "job": metadata,
            "job_info": job_info,
            "drive_link": drive_link,
            "conversa_text": conversa_text,
            "user": user,
        },
    )

@router.post("/render")
async def render_whatsapp_video(
    request: Request,
    title: str = Form(...),
    video_type: str = Form("whatsapp"),
    conversation_text: str = Form(""),
    conversation_file: Optional[UploadFile] = File(None),
    contact_name: str = Form("Contato"),
    contact_status: str = Form("online"),
    video_format: str = Form("vertical"),
    fps: int = Form(30),
    speed: float = Form(1.0),
    reading_speed: float = Form(1.0),
    scroll_speed: float = Form(1.0),
    animation_style: str = Form("fade"),
    contact_photo: Optional[UploadFile] = File(None),
    wallpaper: Optional[UploadFile] = File(None),
    background_music: Optional[UploadFile] = File(None),
    conversation_images: List[UploadFile] = File(default=[]),
):
    """Recebe o formulário, sobe tudo no Drive e publica no RabbitMQ."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if "whatsapp_videos" not in user.get("permissions", []):
        return JSONResponse({"error": "Sem permissão"}, status_code=403)
    user_id = user["id"]
    try:
        try:
            vt = get_video_type(video_type)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        conv_text = ""
        conv_filename = "conversa.txt"
        if conversation_file and conversation_file.filename:
            content_bytes = await conversation_file.read()
            conv_text = content_bytes.decode("utf-8", errors="replace")
            conv_filename = conversation_file.filename
        elif conversation_text.strip():
            conv_text = conversation_text.strip()
        else:
            return JSONResponse(
                {"error": "Nenhuma conversa fornecida. Cole o texto ou envie um arquivo."},
                status_code=400,
            )

        try:
            messages = parse_conversation(conv_text, conv_filename)
        except ValueError as e:
            return JSONResponse({"error": f"Erro ao parsear conversa: {e}"}, status_code=400)

        if not messages:
            return JSONResponse(
                {"error": "Nenhuma mensagem encontrada. Verifique o formato da conversa."},
                status_code=400,
            )

        job_id = uuid.uuid4().hex[:8]
        drive = get_drive(TOKEN_FILE)

        job_folder_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.create_job_folder, title, job_id, vt.drive_folder_name
        )

        metadata: dict = {
            "job_id": job_id,
            "title": title,
            "video_type": video_type,
            "user_id": user_id,
            "contact_name": contact_name,
            "contact_status": contact_status,
            "video_format": video_format,
            "fps": fps,
            "speed": speed,
            "reading_speed": reading_speed,
            "scroll_speed": scroll_speed,
            "animation_style": animation_style,
            "status": "pending",
            "progress": 0,
            "detail": "Aguardando worker...",
            "error": None,
            "created_at": datetime.now().isoformat(),
            "video_drive_id": None,
            "video_url": None,
            "drive_folder_id": job_folder_id,
            "files": {},
        }

        conv_bytes = conv_text.encode("utf-8")
        conv_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_bytes, conv_bytes, "conversa.txt", job_folder_id, "text/plain",
        )
        metadata["files"]["conversa"] = conv_file_id

        if contact_photo and contact_photo.filename:
            content = await contact_photo.read()
            ext = Path(contact_photo.filename).suffix or ".jpg"
            file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, content, f"foto_perfil{ext}", job_folder_id, "image/jpeg"
            )
            metadata["files"]["foto_perfil"] = file_id
            metadata["files"]["foto_perfil_ext"] = ext

        if wallpaper and wallpaper.filename:
            content = await wallpaper.read()
            ext = Path(wallpaper.filename).suffix or ".jpg"
            file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, content, f"papel_parede{ext}", job_folder_id, "image/jpeg"
            )
            metadata["files"]["papel_parede"] = file_id
            metadata["files"]["papel_parede_ext"] = ext

        if background_music and background_music.filename:
            content = await background_music.read()
            ext = Path(background_music.filename).suffix or ".mp3"
            file_id = await asyncio.get_event_loop().run_in_executor(
                None, drive.upload_bytes, content, f"musica{ext}", job_folder_id, "audio/mpeg"
            )
            metadata["files"]["musica"] = file_id
            metadata["files"]["musica_ext"] = ext

        imagens_folder_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.get_or_create_folder, "imagens", job_folder_id
        )
        metadata["files"]["imagens"] = {}
        metadata["files"]["imagens_folder_id"] = imagens_folder_id

        for img in conversation_images:
            if img and img.filename:
                content = await img.read()
                file_id = await asyncio.get_event_loop().run_in_executor(
                    None, drive.upload_bytes, content, img.filename,
                    imagens_folder_id, img.content_type or "image/jpeg",
                )
                metadata["files"]["imagens"][img.filename] = file_id

        metadata_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_json, metadata, "metadata.json", job_folder_id
        )

        jobs_repo.save_job(metadata, job_folder_id, metadata_file_id)

        await publish_job(job_id, video_type)

        logger.info(f"[{job_id}] Job criado e publicado → Drive: {job_folder_id}")
        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.exception(f"Erro ao criar job: {e}")
        return JSONResponse({"error": f"Erro interno: {e}"}, status_code=500)

@router.post("/video/{job_id}/edit")
async def edit_whatsapp_video(
    request: Request,
    job_id: str,
    title: str = Form(...),
    video_type: str = Form("whatsapp"),
    contact_name: str = Form("Contato"),
    contact_status: str = Form("online"),
    video_format: str = Form("vertical"),
    fps: int = Form(30),
    speed: float = Form(1.0),
    reading_speed: float = Form(1.0),
    scroll_speed: float = Form(1.0),
    animation_style: str = Form("fade"),
    conversation_text: str = Form(""),
    contact_photo: Optional[UploadFile] = File(None),
    wallpaper: Optional[UploadFile] = File(None),
    background_music: Optional[UploadFile] = File(None),
    conversation_images: List[UploadFile] = File(default=[]),
    active_image_names: str = Form("[]"),
):
    """Atualiza as configs do vídeo no Drive e publica no RabbitMQ para recriar."""
    import json
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    if job_info.get("user_id") != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)

    drive = get_drive(TOKEN_FILE)
    loop = asyncio.get_event_loop()

    try:
        metadata = await loop.run_in_executor(
            None, drive.read_json, job_info["metadata_file_id"]
        )

        metadata.update({
            "title": title,
            "video_type": video_type,
            "contact_name": contact_name,
            "contact_status": contact_status,
            "video_format": video_format,
            "fps": fps,
            "speed": speed,
            "reading_speed": reading_speed,
            "scroll_speed": scroll_speed,
            "animation_style": animation_style,
            "status": "pending",
            "progress": 0,
            "detail": "Edições salvas, aguardando worker...",
            "error": None,
        })

        if conversation_text.strip():
            conv_bytes = conversation_text.strip().encode("utf-8")
            if metadata.get("files", {}).get("conversa"):
                await loop.run_in_executor(None, drive.update_file, metadata["files"]["conversa"], conv_bytes)
            else:
                conv_file_id = await loop.run_in_executor(
                    None, drive.upload_bytes, conv_bytes, "conversa.txt", job_info["drive_folder_id"], "text/plain"
                )
                metadata.setdefault("files", {})["conversa"] = conv_file_id

        if contact_photo and contact_photo.filename:
            content = await contact_photo.read()
            if metadata.get("files", {}).get("foto_perfil"):
                await loop.run_in_executor(None, drive.update_file, metadata["files"]["foto_perfil"], content)
            else:
                ext = Path(contact_photo.filename).suffix or ".jpg"
                file_id = await loop.run_in_executor(
                    None, drive.upload_bytes, content, f"foto_perfil{ext}", job_info["drive_folder_id"], "image/jpeg"
                )
                metadata.setdefault("files", {})["foto_perfil"] = file_id
                metadata["files"]["foto_perfil_ext"] = ext

        if wallpaper and wallpaper.filename:
            content = await wallpaper.read()
            if metadata.get("files", {}).get("papel_parede"):
                await loop.run_in_executor(None, drive.update_file, metadata["files"]["papel_parede"], content)
            else:
                ext = Path(wallpaper.filename).suffix or ".jpg"
                file_id = await loop.run_in_executor(
                    None, drive.upload_bytes, content, f"papel_parede{ext}", job_info["drive_folder_id"], "image/jpeg"
                )
                metadata.setdefault("files", {})["papel_parede"] = file_id
                metadata["files"]["papel_parede_ext"] = ext

        if background_music and background_music.filename:
            content = await background_music.read()
            if metadata.get("files", {}).get("musica"):
                await loop.run_in_executor(None, drive.update_file, metadata["files"]["musica"], content)
            else:
                ext = Path(background_music.filename).suffix or ".mp3"
                file_id = await loop.run_in_executor(
                    None, drive.upload_bytes, content, f"musica{ext}", job_info["drive_folder_id"], "audio/mpeg"
                )
                metadata.setdefault("files", {})["musica"] = file_id
                metadata["files"]["musica_ext"] = ext

        if not metadata.get("files", {}).get("imagens_folder_id"):
            imagens_folder_id = await loop.run_in_executor(
                None, drive.get_or_create_folder, "imagens", job_info["drive_folder_id"]
            )
            metadata.setdefault("files", {})["imagens_folder_id"] = imagens_folder_id
        else:
            imagens_folder_id = metadata["files"]["imagens_folder_id"]

        active_names = json.loads(active_image_names)
        current_images = metadata.get("files", {}).get("imagens", {})
        
        for img_name, img_id in list(current_images.items()):
            if img_name not in active_names:
                await loop.run_in_executor(None, drive.delete_file, img_id)
                del current_images[img_name]

        for img in conversation_images:
            if img and img.filename:
                content = await img.read()
                if img.filename in current_images:
                    await loop.run_in_executor(None, drive.update_file, current_images[img.filename], content)
                else:
                    file_id = await loop.run_in_executor(
                        None, drive.upload_bytes, content, img.filename,
                        imagens_folder_id, img.content_type or "image/jpeg"
                    )
                    current_images[img.filename] = file_id

        metadata.setdefault("files", {})["imagens"] = current_images

        await loop.run_in_executor(
            None, drive.update_json, job_info["metadata_file_id"], metadata
        )

        jobs_repo.save_job(metadata, job_info["drive_folder_id"], job_info["metadata_file_id"])

        await publish_job(job_id, video_type)

        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.exception(f"Erro ao editar job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/video/{job_id}/duplicate")
async def duplicate_whatsapp_video(request: Request, job_id: str):
    """Duplica um job de WhatsApp existente."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    try:
        data = await request.json()
    except:
        return JSONResponse({"error": "JSON inválido"}, status_code=400)

    new_title = data.get("new_title", "Cópia")
    files_to_copy = data.get("files_to_copy", [])

    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job original não encontrado"}, status_code=404)
    if job_info.get("user_id") != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)

    drive = get_drive(TOKEN_FILE)
    loop = asyncio.get_event_loop()

    try:
        metadata = await loop.run_in_executor(None, drive.read_json, job_info["metadata_file_id"])
        
        new_job_id = uuid.uuid4().hex[:8]
        video_type = metadata.get("video_type", "whatsapp")
        vt = get_video_type(video_type)

        new_folder_id = await loop.run_in_executor(
            None, drive.create_job_folder, new_title, new_job_id, vt.drive_folder_name
        )

        new_metadata = metadata.copy()
        new_metadata.update({
            "job_id": new_job_id,
            "title": new_title,
            "status": "draft",
            "user_id": user["id"],
            "progress": 0,
            "detail": "Projeto duplicado, pronto para edição.",
            "error": None,
            "created_at": datetime.now().isoformat(),
            "video_drive_id": None,
            "video_url": None,
            "drive_folder_id": new_folder_id,
            "files": {}
        })

        if "imagens" in files_to_copy:
            old_imagens_folder = metadata.get("files", {}).get("imagens_folder_id")
            if old_imagens_folder:
                new_img_folder_id = await loop.run_in_executor(
                    None, drive.copy_file, old_imagens_folder, new_folder_id, "imagens"
                )
                new_metadata["files"]["imagens_folder_id"] = new_img_folder_id
                
                # Update individual image IDs inside the folder
                new_metadata["files"]["imagens"] = {}
                old_imagens = metadata.get("files", {}).get("imagens", {})
                for img_name in old_imagens:
                    try:
                        new_img_id = await loop.run_in_executor(
                            None, drive.find_file_in_folder, new_img_folder_id, img_name
                        )
                        if new_img_id:
                            new_metadata["files"]["imagens"][img_name] = new_img_id
                    except:
                        pass
            files_to_copy.remove("imagens")

        for key in files_to_copy:
            old_file_id = metadata.get("files", {}).get(key)
            if old_file_id:
                try:
                    filename = f"{key}{metadata.get('files', {}).get(f'{key}_ext', '')}"
                    if key == "conversa":
                        filename = "conversa.txt"
                    
                    new_file_id = await loop.run_in_executor(
                        None, drive.copy_file, old_file_id, new_folder_id, filename
                    )
                    new_metadata["files"][key] = new_file_id
                    if f"{key}_ext" in metadata.get("files", {}):
                        new_metadata["files"][f"{key}_ext"] = metadata["files"][f"{key}_ext"]
                except Exception as e:
                    logger.warning(f"Erro ao copiar {key}: {e}")

        new_metadata_id = await loop.run_in_executor(
            None, drive.upload_json, new_metadata, "metadata.json", new_folder_id
        )

        jobs_repo.save_job(new_metadata, new_folder_id, new_metadata_id)

        return JSONResponse({"job_id": new_job_id})

    except Exception as e:
        logger.exception(f"Erro ao duplicar job {job_id}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/extract", response_class=HTMLResponse)
async def whatsapp_extract_page(request: Request):
    """Página de extração — mostra apenas o formulário de upload e a conversa gerada no momento."""
    user, err = _require_permission(request, "whatsapp_extract")
    if err:
        return err
    return templates.TemplateResponse(
        "whatsapp/extract.html",
        {"request": request, "user": user},
    )


@router.get("/extract/history", response_class=HTMLResponse)
async def whatsapp_extract_history(
    request: Request,
    title: Optional[str] = None,
    date: Optional[str] = None,
):
    """Histórico de extrações — filtro por título e data."""
    user, err = _require_permission(request, "whatsapp_extract")
    if err:
        return err

    jobs = jobs_repo.get_all_jobs("whatsapp_extract", user_id=user["id"])

    # Filtrar por título
    if title:
        jobs = [j for j in jobs if title.lower() in j.get("title", "").lower()]

    # Filtrar por data (formato YYYY-MM-DD)
    if date:
        jobs = [j for j in jobs if j.get("created_at", "").startswith(date)]

    return templates.TemplateResponse(
        "whatsapp/extract_history.html",
        {"request": request, "jobs": jobs, "user": user, "filter_title": title or "", "filter_date": date or ""},
    )


@router.get("/extract/{job_id}", response_class=HTMLResponse)
async def whatsapp_extract_detail(request: Request, job_id: str):
    """Tela de detalhe de uma extração — editar conversa + corrigir com IA."""
    user, err = _require_permission(request, "whatsapp_extract")
    if err:
        return err

    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return HTMLResponse("<h1>Extração não encontrada</h1>", status_code=404)
    if job_info.get("user_id") != user["id"]:
        return HTMLResponse("<h1>Acesso negado</h1>", status_code=403)

    return templates.TemplateResponse(
        "whatsapp/extract_detail.html",
        {"request": request, "job": job_info, "user": user},
    )

@router.post("/extract")
async def extract_whatsapp_from_video(
    request: Request,
    title: str = Form(...),
    video_original: UploadFile = File(...),
):
    """Cria um job para extrair as conversas de um vídeo existente."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if "whatsapp_extract" not in user.get("permissions", []):
        return JSONResponse({"error": "Sem permissão"}, status_code=403)
    user_id = user["id"]
    try:
        if not video_original or not video_original.filename:
            return JSONResponse({"error": "Vídeo não fornecido."}, status_code=400)

        job_id = uuid.uuid4().hex[:8]
        drive = get_drive(TOKEN_FILE)
        
        video_type = "whatsapp_extract"
        vt = get_video_type(video_type)

        job_folder_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.create_job_folder, title, job_id, vt.drive_folder_name
        )

        metadata = {
            "job_id": job_id,
            "title": title,
            "video_type": video_type,
            "user_id": user_id,
            "status": "pending",
            "progress": 0,
            "detail": "Aguardando worker para extração...",
            "error": None,
            "created_at": datetime.now().isoformat(),
            "drive_folder_id": job_folder_id,
            "files": {},
        }

        content = await video_original.read()
        ext = Path(video_original.filename).suffix or ".mp4"
        file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_bytes, content, f"video_original{ext}", job_folder_id, video_original.content_type or "video/mp4"
        )
        metadata["files"]["video_original"] = file_id

        metadata_file_id = await asyncio.get_event_loop().run_in_executor(
            None, drive.upload_json, metadata, "metadata.json", job_folder_id
        )

        jobs_repo.save_job(metadata, job_folder_id, metadata_file_id)

        await publish_job(job_id, video_type)

        logger.info(f"[{job_id}] Job de Extração criado → Drive: {job_folder_id}")
        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.exception(f"Erro ao criar job de extração: {e}")
        return JSONResponse({"error": f"Erro interno: {e}"}, status_code=500)

# ── Correção de Texto via IA ──

@router.post("/correct-text")
async def correct_text(
    request: Request,
    raw_text: str = Form(...),
):
    """Submete um texto para correção via agente IA (sempre Gemini, modo anônimo).

    Cria um registro no MySQL, publica na fila do agente e retorna o job_id.
    O frontend pode acompanhar o progresso via SSE em /api/correction/{job_id}/stream.
    """
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if "whatsapp_extract" not in user.get("permissions", []):
        return JSONResponse({"error": "Sem permissão"}, status_code=403)
    if "use_ai" not in user.get("permissions", []):
        return JSONResponse({"error": "Sem permissão para usar a IA"}, status_code=403)

    try:
        if not raw_text.strip():
            return JSONResponse(
                {"error": "Texto vazio. Forneça o texto para correção."},
                status_code=400,
            )

        # Sempre usa Gemini
        provider = "gemini"
        job_id = uuid.uuid4().hex[:8]

        # Salvar no MySQL
        corrections_repo.create_job(job_id, raw_text.strip(), provider, user_id=user["id"])

        # Publicar na fila do agente
        await publish_correction_job(job_id, raw_text.strip(), provider)

        logger.info(f"[{job_id}] Job de correção criado → provider={provider}")
        return JSONResponse({"job_id": job_id, "status": "queued"})

    except Exception as e:
        logger.exception(f"Erro ao criar job de correção: {e}")
        return JSONResponse({"error": f"Erro interno: {e}"}, status_code=500)


@router.get("/correct-text/{job_id}")
async def get_correction_result(job_id: str):
    """Consulta o resultado de uma correção de texto.

    Retorna o status atual e, se concluído, o texto corrigido.
    """
    job = corrections_repo.get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    return JSONResponse(job)


@router.post("/extract/{job_id}/save")
async def save_extract_text(
    request: Request,
    job_id: str,
    conversa_text: str = Form(...),
):
    """Salva edição manual do texto extraído."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    job_info = jobs_repo.get_job(job_id)
    if not job_info:
        return JSONResponse({"error": "Job não encontrado"}, status_code=404)
    if job_info.get("user_id") != user["id"]:
        return JSONResponse({"error": "Acesso negado"}, status_code=403)

    jobs_repo.update_extract_text(job_id, conversa_text)
    return JSONResponse({"ok": True})

