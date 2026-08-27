"""Pengguna aplikasi."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import RecordStatus, UserRole

if TYPE_CHECKING:
    from app.models.branch import Branch


class User(TimestampMixin, Base):
    """
    Petugas pengguna aplikasi.

    password_hash HANYA menyimpan hash. Password asli tidak pernah disimpan,
    tidak pernah di-log, dan tidak pernah dikirim ke mana pun.
    Mekanisme hashing diimplementasikan pada Phase 2.
    """

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        sa.ForeignKey("branch.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(sa.String(50), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, native_enum=False, length=20), nullable=False
    )
    status: Mapped[RecordStatus] = mapped_column(
        sa.Enum(RecordStatus, native_enum=False, length=10),
        nullable=False,
        default=RecordStatus.ACTIVE,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(sa.DateTime)
    # True memaksa user mengganti kata sandi sebelum dapat memakai aplikasi.
    # Dipakai untuk akun admin bawaan yang kata sandinya diketahui umum.
    must_change_password: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )

    branch: Mapped[Branch] = relationship(back_populates="users")

    @property
    def is_active(self) -> bool:
        return self.status is RecordStatus.ACTIVE

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role.value}>"
