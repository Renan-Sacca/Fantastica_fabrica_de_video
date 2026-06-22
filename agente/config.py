"""Configurações do serviço agente (corretor de texto via IA)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ── RabbitMQ ──
RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise ValueError("RABBITMQ_URL não encontrada no .env")
RABBITMQ_AGENT_QUEUE = os.getenv("RABBITMQ_AGENT_QUEUE", "text_correction_jobs")

# ── MySQL ──
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "fabrica_video_db")

# ── Agente ──
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "chatgpt")
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
CHROME_DATA_DIR = os.getenv("CHROME_DATA_DIR", str(BASE_DIR / "chrome_data"))
