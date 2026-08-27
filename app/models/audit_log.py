"""Audit log aktivitas penting."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import clock
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    """
    Jejak aktivitas.

    JANGAN PERNAH menuliskan password, hash password, atau kredensial apa pun
    ke kolom meta.

    user_id boleh kosong untuk aktivitas yang dijalankan sistem, misalnya
    backup terjadwal.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        sa.Index("ix_audit_log_action_created", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(sa.String(40))
    entity_id: Mapped[int | None] = mapped_column(sa.Integer)
    # Nama atribut "metadata" tidak dapat dipakai karena bentrok dengan
    # atribut bawaan SQLAlchemy Declarative, sehingga atributnya bernama
    # "meta" sementara nama kolomnya tetap "metadata".
    meta: Mapped[str | None] = mapped_column("metadata", sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=clock.now, index=True
    )

    user: Mapped[User | None] = relationship()

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} user={self.user_id}>"
