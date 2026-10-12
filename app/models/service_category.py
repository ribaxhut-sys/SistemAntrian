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

    Jenis layanan boleh BERTINGKAT lewat `parent_id`. Yang punya anak
    berubah peran menjadi KELOMPOK: di anjungan ia hanya membuka daftar
    anaknya dan tidak lagi menerbitkan nomor. Prefix-nya tetap ada dan
    tetap unik supaya nomor lama yang sudah terbit sebelum ia punya anak
    tidak kehilangan pemiliknya.
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
    #: Kelompok induk. NULL berarti jenis layanan ini berdiri di tingkat
    #: teratas anjungan. RESTRICT: kelompok yang masih punya anak tidak
    #: boleh hilang dan meninggalkan anaknya tanpa jalan menuju ke sana.
    parent_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("service_category.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    prefix: Mapped[str] = mapped_column(sa.String(2), nullable=False)
    display_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    #: Ditampilkan di panel informasi anjungan begitu pengunjung menyentuh
    #: layanan ini. Kosong berarti anjungan memakai teks sambutan bawaan.
    info_text: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    status: Mapped[RecordStatus] = mapped_column(
        sa.Enum(RecordStatus, native_enum=False, length=10),
        nullable=False,
        default=RecordStatus.ACTIVE,
    )

    branch: Mapped[Branch] = relationship(back_populates="categories")
    parent: Mapped[ServiceCategory | None] = relationship(
        back_populates="children", remote_side="ServiceCategory.id"
    )
    children: Mapped[list[ServiceCategory]] = relationship(
        back_populates="parent", order_by="ServiceCategory.display_order"
    )

    def __repr__(self) -> str:
        return f"<ServiceCategory {self.prefix}={self.name!r}>"
