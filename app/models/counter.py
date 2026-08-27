"""Loket / meja pelayanan CRO."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import RecordStatus

if TYPE_CHECKING:
    from app.models.branch import Branch


class Counter(TimestampMixin, Base):
    """Loket tempat petugas CRO melayani pengunjung."""

    __tablename__ = "counter"
    __table_args__ = (
        sa.UniqueConstraint("branch_id", "code", name="uq_counter_branch_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        sa.ForeignKey("branch.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        sa.Enum(RecordStatus, native_enum=False, length=10),
        nullable=False,
        default=RecordStatus.ACTIVE,
    )

    branch: Mapped[Branch] = relationship(back_populates="counters")

    def __repr__(self) -> str:
        return f"<Counter {self.code} {self.name!r}>"
