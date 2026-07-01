"""Configurações do serviço web."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ── RabbitMQ ──
RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise ValueError("RABBITMQ_URL não encontrada no .env")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "video_jobs")
RABBITMQ_AGENT_QUEUE = os.getenv("RABBITMQ_AGENT_QUEUE", "text_correction_jobs")

# ── Áudio (OmniVoice) ──
RABBITMQ_OMNI_QUEUE = os.getenv("RABBITMQ_OMNI_QUEUE", "omni_audio_jobs")
RABBITMQ_OMNI_PROGRESS_EXCHANGE = os.getenv("RABBITMQ_OMNI_PROGRESS_EXCHANGE", "omni_audio_progress")

# Pasta compartilhada com o worker do OmniVoice (tts3/data montada no container)
OMNI_DATA_DIR = Path(os.getenv("OMNI_DATA_DIR", "/app/tts3_audio"))
OMNI_VOICES_DIR = OMNI_DATA_DIR / "voices"
OMNI_OUTPUTS_DIR = OMNI_DATA_DIR / "outputs"
OMNI_CUSTOM_INDEX = OMNI_VOICES_DIR / "_custom_voices.json"

# ── MySQL ──
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "fabrica_video_db")

# ── Autenticação ──
SECRET_KEY = os.getenv("SECRET_KEY", "fabrica_video_secret_2025")

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

# Garantir diretórios compartilhados de áudio (podem não existir no 1º boot)
try:
    OMNI_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    OMNI_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
