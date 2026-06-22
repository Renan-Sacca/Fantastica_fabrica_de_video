"""Router de autenticação — login, cadastro e logout."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    create_session_token,
    get_current_user,
)
from app.config import TEMPLATES_DIR
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    user = users_repo.authenticate(email, password)
    if not user:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "E-mail ou senha inválidos."},
            status_code=401,
        )

    token = create_session_token(user["id"])
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    logger.info(f"Login: {email}")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("auth/register.html", {"request": request, "error": None})


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "As senhas não coincidem."},
            status_code=400,
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "A senha deve ter pelo menos 6 caracteres."},
            status_code=400,
        )

    user = users_repo.create_user(email, password)
    if not user:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "Este e-mail já está cadastrado."},
            status_code=400,
        )

    logger.info(f"Novo usuário cadastrado: {email}")
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "error": None, "success": "Conta criada com sucesso! Faça login."},
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── API de permissões (admin) ──

@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    users = users_repo.get_all_users()
    from app.models.permission import Permission
    return templates.TemplateResponse(
        "auth/admin_users.html",
        {"request": request, "user": user, "users": users, "all_permissions": Permission.ALL},
    )


@router.post("/admin/users/{user_id}/permissions")
async def update_permissions(
    request: Request,
    user_id: int,
    permissions: str = Form(default=""),
):
    current_user = get_current_user(request)
    if not current_user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    perm_list = [p.strip() for p in permissions.split(",") if p.strip()] if permissions else []
    success = users_repo.set_permissions(user_id, perm_list)
    if not success:
        return JSONResponse({"error": "Usuário não encontrado"}, status_code=404)

    return RedirectResponse(url="/auth/admin/users", status_code=302)
