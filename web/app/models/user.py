"""Model de Usuário."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    voice_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("voice_plans.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    permissions: Mapped[List["Permission"]] = relationship(  # noqa: F821
        "Permission", back_populates="user", cascade="all, delete-orphan", lazy="select"
    )
    
    voice_plan: Mapped[Optional["VoicePlan"]] = relationship(  # noqa: F821
        "VoicePlan", lazy="joined"
    )

    def has_permission(self, perm: str) -> bool:
        return any(p.permission == perm for p in self.permissions)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "voice_plan_id": self.voice_plan_id,
            "voice_plan": self.voice_plan.to_dict() if self.voice_plan else None,
            "permissions": [p.permission for p in self.permissions],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
