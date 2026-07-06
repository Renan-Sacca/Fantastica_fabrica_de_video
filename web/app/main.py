"""FastAPI — Serviço Web da Fantástica Fábrica de Vídeo."""
from __future__ import annotations

import logging
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import STATIC_DIR, TEMPLATES_DIR, OMNI_OUTPUTS_DIR
from app.database import init_db
from app.routers import audio, auth, dashboard, drive, jobs, progress, video_bg, video_compositor, whatsapp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fantástica Fábrica de Vídeo",
    description="Dashboard para geração de vídeos automatizados",
    version="2.0.0",
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Servir os áudios gerados pelo OmniVoice (volume compartilhado tts3/data/outputs)
OMNI_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/audio-files", StaticFiles(directory=str(OMNI_OUTPUTS_DIR)), name="audio-files")

# Incluir roteadores
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(whatsapp.router)
app.include_router(audio.router)
app.include_router(video_bg.router)
app.include_router(video_compositor.router)
app.include_router(jobs.router)
app.include_router(drive.router)
app.include_router(progress.router)

@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Serviço web iniciado.")
