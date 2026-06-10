"""Configurações padrão do projeto."""
import os
from pathlib import Path

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend" / "whatsapp"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = BASE_DIR / "assets"
FRONTEND_ASSETS_DIR = BASE_DIR / "frontend" / "assets"
CONVERSATIONS_DIR = BASE_DIR / "conversations"
OUTPUT_DIR = BASE_DIR / "output"
UPLOADS_DIR = BASE_DIR / "uploads"

# Garantir que diretórios existem
for d in [OUTPUT_DIR, UPLOADS_DIR, CONVERSATIONS_DIR, ASSETS_DIR / "imagens"]:
    d.mkdir(parents=True, exist_ok=True)

# Renderização
MAX_CONCURRENT_RENDERS = int(os.getenv("MAX_CONCURRENT_RENDERS", "2"))
DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
DEFAULT_FPS = 30
DEFAULT_SPEED = 1.0
DEFAULT_READING_SPEED = 1.0
DEFAULT_SCROLL_SPEED = 1.0

# Tempos de animação (ms)
MIN_MESSAGE_DELAY = 800
MAX_MESSAGE_DELAY = 2500
TYPING_INDICATOR_MIN = 500
TYPING_INDICATOR_MAX = 1500
SCROLL_DURATION_MIN = 300
SCROLL_DURATION_MAX = 600
IMAGE_PAUSE_MIN = 1500
IMAGE_PAUSE_MAX = 3000
MICRO_PAUSE_MIN = 200
MICRO_PAUSE_MAX = 500

# Variação humana
HUMAN_VARIATION_PERCENT = 0.20  # ±20%

# FFmpeg
FFMPEG_CRF = 18
FFMPEG_PRESET = "medium"
FFMPEG_AUDIO_BITRATE = "192k"

# Cores padrão WhatsApp
WHATSAPP_HEADER_COLOR = "#075e54"
WHATSAPP_SENT_COLOR = "#dcf8c6"
WHATSAPP_RECEIVED_COLOR = "#ffffff"
WHATSAPP_BG_COLOR = "#e5ddd5"
