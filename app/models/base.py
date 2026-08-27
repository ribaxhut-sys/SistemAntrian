"""Base declarative dan mixin bersama."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core import clock

# Penamaan constraint yang eksplisit. Tanpa ini, SQLite menghasilkan nama
# constraint otomatis yang tidak dapat dirujuk oleh migration saat perlu
# di-drop atau diubah.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base seluruh model."""

    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """
    Kolom waktu pembuatan dan perubahan.

    Nilai diambil dari app.core.clock (WIB), bukan dari fungsi waktu database,
    agar zona waktu tidak bergantung pada setelan komputer.
    """

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=clock.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=clock.now, onupdate=clock.now
    )
