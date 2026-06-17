"""FastAPI — Serviço Web da Fantástica Fábrica de Vídeo."""
from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR
from app.database import init_db
from app.routers import dashboard, drive, jobs, progress, whatsapp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fantástica Fábrica de Vídeo",
    description="Dashboard para geração de vídeos automatizados",
    version="2.0.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Incluir roteadores
app.include_router(dashboard.router)
app.include_router(whatsapp.router)
app.include_router(jobs.router)
app.include_router(drive.router)
app.include_router(progress.router)

@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Serviço web iniciado.")
