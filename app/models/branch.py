"""Cabang / unit kantor pelayanan."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import RecordStatus

if TYPE_CHECKING:
    from app.models.counter import Counter
    from app.models.queue import Queue
    from app.models.service_category import ServiceCategory
    from app.models.user import User


class Branch(TimestampMixin, Base):
    """
    Kantor pelayanan.

    Saat ini aplikasi berjalan pada satu lokasi, tetapi seluruh data
    tetap membawa branch_id agar struktur tidak perlu dirombak bila
    ke depan digunakan di lebih dari satu kantor.
    """

    __tablename__ = "branch"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(sa.String(255))
    status: Mapped[RecordStatus] = mapped_column(
        sa.Enum(RecordStatus, native_enum=False, length=10),
        nullable=False,
        default=RecordStatus.ACTIVE,
    )

    users: Mapped[list[User]] = relationship(back_populates="branch")
    counters: Mapped[list[Counter]] = relationship(back_populates="branch")
    categories: Mapped[list[ServiceCategory]] = relationship(back_populates="branch")
    queues: Mapped[list[Queue]] = relationship(back_populates="branch")

    def __repr__(self) -> str:
        return f"<Branch {self.code} {self.name!r}>"
