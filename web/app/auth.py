"""Utilitários de autenticação — sessões via cookies assinados."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from functools import wraps
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "fabrica_video_secret_2025")
SESSION_COOKIE = "ffv_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 dias


# ── Assinatura de sessão ──

def _sign(payload: str) -> str:
    return hashlib.sha256(f"{SECRET_KEY}{payload}".encode()).hexdigest()


def create_session_token(user_id: int) -> str:
    """Cria um token de sessão assinado: base64(payload)|signature."""
    import base64
    data = json.dumps({"user_id": user_id, "ts": int(time.time())})
    encoded = base64.b64encode(data.encode()).decode()
    sig = _sign(encoded)
    return f"{encoded}.{sig}"


def decode_session_token(token: str) -> Optional[dict]:
    """Valida e decodifica um token de sessão. Retorna None se inválido."""
    import base64
    try:
        encoded, sig = token.rsplit(".", 1)
        if _sign(encoded) != sig:
            return None
        data = json.loads(base64.b64decode(encoded).decode())
        # Expiração
        if time.time() - data.get("ts", 0) > SESSION_MAX_AGE:
            return None
        return data
    except Exception:
        return None


# ── Helpers para request ──

def get_current_user(request: Request) -> Optional[dict]:
    """Lê a sessão do cookie e retorna o dict do usuário ou None."""
    from app.repositories import users as users_repo

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = decode_session_token(token)
    if not session:
        return None
    user = users_repo.get_user_by_id(session["user_id"])
    return user


def login_required(func):
    """Decorator de rota FastAPI — redireciona para /auth/login se não logado."""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return RedirectResponse(url="/auth/login", status_code=302)
        return await func(request, *args, **kwargs)
    return wrapper


def permission_required(permission: str):
    """Decorator de rota que exige permissão específica além de estar logado."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            user = get_current_user(request)
            if not user:
                return RedirectResponse(url="/auth/login", status_code=302)
            if permission not in user.get("permissions", []):
                from fastapi.templating import Jinja2Templates
                from app.config import TEMPLATES_DIR
                templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
                return templates.TemplateResponse(
                    "403.html",
                    {"request": request, "user": user, "required_permission": permission},
                    status_code=403,
                )
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
