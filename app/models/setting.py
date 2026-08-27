"""Konfigurasi aplikasi yang tersimpan di database."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.models.base import Base


class ApplicationSetting(Base):
    """
    Pengaturan yang dapat diubah petugas ADMIN lewat aplikasi.

    Berbeda dari app.core.config yang mengatur lokasi file dan hanya bisa
    diubah lewat environment variable.
    """

    __tablename__ = "application_setting"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(sa.String(60), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(255))
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=clock.now, onupdate=clock.now
    )

    def __repr__(self) -> str:
        return f"<ApplicationSetting {self.key}={self.value!r}>"
