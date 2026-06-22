"""Repositório de usuários — autenticação e permissões."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.models.permission import Permission
from app.models.user import User

logger = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    """Hash SHA-256 + salt fixo por variável de ambiente."""
    salt = os.getenv("SECRET_KEY", "fabrica_video_secret_2025")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def create_user(email: str, password: str) -> Optional[User]:
    """Cria um novo usuário. Retorna None se o e-mail já existir."""
    with SessionLocal() as session:
        existing = session.scalar(select(User).where(User.email == email.lower()))
        if existing:
            return None
        user = User(
            email=email.lower(),
            password_hash=_hash_password(password),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info(f"Usuário criado: {email}")
        return user


def authenticate(email: str, password: str) -> Optional[dict]:
    """Verifica credenciais e retorna o dict do usuário ou None."""
    with SessionLocal() as session:
        user = session.scalar(
            select(User)
            .where(User.email == email.lower())
            .options(selectinload(User.permissions))
        )
        if not user:
            return None
        if not user.is_active:
            return None
        if user.password_hash != _hash_password(password):
            return None
        return user.to_dict()


def get_user_by_id(user_id: int) -> Optional[dict]:
    """Retorna um usuário pelo ID."""
    with SessionLocal() as session:
        user = session.scalar(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.permissions))
        )
        return user.to_dict() if user else None


def get_all_users() -> list[dict]:
    """Lista todos os usuários (para admin)."""
    with SessionLocal() as session:
        users = session.scalars(
            select(User).options(selectinload(User.permissions))
        ).all()
        return [u.to_dict() for u in users]


def set_permissions(user_id: int, permissions: list[str]) -> bool:
    """Define as permissões de um usuário (substitui todas as existentes)."""
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.id == user_id))
        if not user:
            return False
        # Remover as antigas
        existing = session.scalars(
            select(Permission).where(Permission.user_id == user_id)
        ).all()
        for p in existing:
            session.delete(p)
        # Adicionar as novas
        for perm in permissions:
            if perm in Permission.ALL:
                session.add(Permission(user_id=user_id, permission=perm))
        session.commit()
        logger.info(f"Permissões atualizadas para user {user_id}: {permissions}")
        return True


def has_permission(user_id: int, permission: str) -> bool:
    """Verifica se um usuário tem uma permissão específica."""
    with SessionLocal() as session:
        result = session.scalar(
            select(Permission).where(
                Permission.user_id == user_id,
                Permission.permission == permission,
            )
        )
        return result is not None
