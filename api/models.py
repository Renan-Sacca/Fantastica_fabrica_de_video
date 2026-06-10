"""Modelos Pydantic para o projeto."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    EMOJI = "emoji"
    DATE_SEPARATOR = "date_separator"


class MessageStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class Message(BaseModel):
    """Uma mensagem individual na conversa."""
    sender: str  # "me" para mensagens enviadas, nome do contato para recebidas
    text: Optional[str] = None
    time: str = "12:00"
    type: MessageType = MessageType.TEXT
    media_path: Optional[str] = None
    status: MessageStatus = MessageStatus.READ


class VideoFormat(str, Enum):
    VERTICAL = "vertical"      # 1080x1920
    HORIZONTAL = "horizontal"  # 1920x1080
    SQUARE = "square"          # 1080x1080


class AnimationStyle(str, Enum):
    FADE = "fade"
    SLIDE = "slide"
    TYPING = "typing"


class ConversationConfig(BaseModel):
    """Configuração completa para renderização do vídeo."""
    contact_name: str = "Contato"
    contact_status: str = "online"
    user_name: str = "Eu"
    video_format: VideoFormat = VideoFormat.VERTICAL
    fps: int = Field(default=30, ge=15, le=60)
    speed: float = Field(default=1.0, ge=0.5, le=3.0)
    reading_speed: float = Field(default=1.0, ge=0.5, le=3.0)
    scroll_speed: float = Field(default=1.0, ge=0.5, le=3.0)
    animation_style: AnimationStyle = AnimationStyle.FADE
    send_sound: bool = False
    receive_sound: bool = False

    # Cores customizáveis
    sent_message_color: Optional[str] = None
    received_message_color: Optional[str] = None

    @property
    def width(self) -> int:
        if self.video_format == VideoFormat.HORIZONTAL:
            return 1920
        return 1080

    @property
    def height(self) -> int:
        if self.video_format == VideoFormat.HORIZONTAL:
            return 1080
        if self.video_format == VideoFormat.SQUARE:
            return 1080
        return 1920


class JobStatus(str, Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    PREPARING = "preparing"
    RENDERING = "rendering"
    COMPOSING = "composing"
    DONE = "done"
    ERROR = "error"


class JobProgress(BaseModel):
    """Progresso de um job de renderização."""
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0  # 0-100
    detail: str = "Aguardando..."
    error: Optional[str] = None
    output_path: Optional[str] = None
    created_at: str = ""
    total_frames: int = 0
    current_frame: int = 0


class RenderJob(BaseModel):
    """Job completo de renderização."""
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    config: ConversationConfig = ConversationConfig()
    messages: list[Message] = []
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    detail: str = "Aguardando..."
    error: Optional[str] = None
    output_path: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    total_frames: int = 0
    current_frame: int = 0

    # Caminhos de assets enviados pelo usuário
    contact_photo_path: Optional[str] = None
    wallpaper_path: Optional[str] = None
    background_music_path: Optional[str] = None

    def to_progress(self) -> JobProgress:
        return JobProgress(
            job_id=self.job_id,
            status=self.status,
            progress=self.progress,
            detail=self.detail,
            error=self.error,
            output_path=self.output_path,
            created_at=self.created_at,
            total_frames=self.total_frames,
            current_frame=self.current_frame,
        )
