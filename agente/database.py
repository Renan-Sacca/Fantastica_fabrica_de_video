"""Configuração da conexão MySQL (SQLAlchemy ORM) — serviço agente."""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)

logger = logging.getLogger(__name__)


def _build_url() -> str:
    user = quote_plus(MYSQL_USER)
    password = quote_plus(MYSQL_PASSWORD)
    return (
        f"mysql+pymysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/"
        f"{MYSQL_DATABASE}?charset=utf8mb4"
    )


class Base(DeclarativeBase):
    """Base declarativa compartilhada por todos os models."""


engine = create_engine(
    _build_url(),
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Cria as tabelas (caso não existam)."""
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Tabelas MySQL verificadas/criadas com sucesso (agente).")
