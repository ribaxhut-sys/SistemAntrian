"""Jenis layanan CRO."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import RecordStatus

if TYPE_CHECKING:
    from app.models.branch import Branch


class ServiceCategory(TimestampMixin, Base):
    """
    Jenis layanan, sekaligus penentu prefix nomor antrian.

    Contoh: prefix "A" menghasilkan A-001, A-002, dan seterusnya.

    prefix wajib unik dalam satu cabang. Bila dua jenis layanan memakai
    prefix yang sama, nomor antrian keduanya akan bertabrakan.
    """

    __tablename__ = "service_category"
    __table_args__ = (
        sa.UniqueConstraint("branch_id", "code", name="uq_service_category_branch_code"),
        sa.UniqueConstraint(
            "branch_id", "prefix", name="uq_service_category_branch_prefix"
        ),
        sa.CheckConstraint(
            "length(prefix) BETWEEN 1 AND 2", name="prefix_length"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        sa.ForeignKey("branch.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    prefix: Mapped[str] = mapped_column(sa.String(2), nullable=False)
    display_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    status: Mapped[RecordStatus] = mapped_column(
        sa.Enum(RecordStatus, native_enum=False, length=10),
        nullable=False,
        default=RecordStatus.ACTIVE,
    )

    branch: Mapped[Branch] = relationship(back_populates="categories")

    def __repr__(self) -> str:
        return f"<ServiceCategory {self.prefix}={self.name!r}>"
