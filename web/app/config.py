"""Configurações do serviço web."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── RabbitMQ ──
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://financepowder:rgs050601@rabbitmq.financepowder.cloud/"
)
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "video_jobs")

# ── Google Drive ──
SERVICE_ACCOUNT_FILE = os.getenv(
    "SERVICE_ACCOUNT_FILE",
    str(BASE_DIR / "service_account.json")
)
DRIVE_ROOT = "FantasticaFabricaDeVideo"

# ── Caminhos ──
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
JOBS_FILE = DATA_DIR / "jobs.json"

# Garantir diretórios
DATA_DIR.mkdir(parents=True, exist_ok=True)
