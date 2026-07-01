"""Model para configurações salvas de parâmetros de áudio."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AudioPreset(Base):
    """Configurações salvas de parâmetros avançados de geração de áudio."""

    __tablename__ = "audio_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    preset_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Parâmetros de geração
    num_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    guidance_scale: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    t_shift: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    class_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    layer_penalty_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    audio_chunk_duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    audio_chunk_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    language_id: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    denoise: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    preprocess_prompt: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    postprocess_output: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        """Retorna dict com todos os parâmetros."""
        return {
            "id": self.id,
            "preset_id": self.preset_id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "params": {
                "num_step": self.num_step,
                "guidance_scale": self.guidance_scale,
                "t_shift": self.t_shift,
                "position_temperature": self.position_temperature,
                "class_temperature": self.class_temperature,
                "layer_penalty_factor": self.layer_penalty_factor,
                "speed": self.speed,
                "duration": self.duration,
                "audio_chunk_duration": self.audio_chunk_duration,
                "audio_chunk_threshold": self.audio_chunk_threshold,
                "language_id": self.language_id,
                "denoise": self.denoise,
                "preprocess_prompt": self.preprocess_prompt,
                "postprocess_output": self.postprocess_output,
            },
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
