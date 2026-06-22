"""Modelos para o renderer WhatsApp."""
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
    sender: str
    text: Optional[str] = None
    time: str = "12:00"
    type: MessageType = MessageType.TEXT
    media_path: Optional[str] = None
    status: MessageStatus = MessageStatus.READ


class VideoFormat(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    SQUARE = "square"


class AnimationStyle(str, Enum):
    FADE = "fade"
    SLIDE = "slide"
    TYPING = "typing"


class ConversationConfig(BaseModel):
    contact_name: str = "Contato"
    contact_status: str = "online"
    user_name: str = "Eu"
    video_format: VideoFormat = VideoFormat.VERTICAL
    fps: int = Field(default=30, ge=15, le=60)
    speed: float = Field(default=1.0, ge=0.5, le=3.0)
    reading_speed: float = Field(default=1.0, ge=0.5, le=3.0)
    scroll_speed: float = Field(default=1.0, ge=0.5, le=3.0)
    animation_style: AnimationStyle = AnimationStyle.FADE

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


class RenderJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    config: ConversationConfig = ConversationConfig()
    messages: list[Message] = []
    contact_photo_path: Optional[str] = None
    wallpaper_path: Optional[str] = None
    background_music_path: Optional[str] = None
    bg_color: Optional[str] = None  # cor de fundo quando não há wallpaper (ex: "#128c7e")
