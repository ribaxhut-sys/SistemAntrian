"""Loket / meja pelayanan CRO."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import RecordStatus

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.service_category import ServiceCategory


#: Jenis layanan yang boleh dipanggil sebuah loket.
#:
#: Loket yang TIDAK punya satu baris pun di sini boleh memanggil seluruh
#: jenis layanan. Kosong sengaja berarti "semua", bukan "tidak ada":
#: pemasangan baru dan loket yang belum sempat diatur harus tetap bekerja,
#: dan loket tidak boleh menganggur hanya karena daftarnya lupa diisi.
counter_category = sa.Table(
    "counter_category",
    Base.metadata,
    sa.Column(
        "counter_id",
        sa.ForeignKey("counter.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "category_id",
        sa.ForeignKey("service_category.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


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
    #: Ditunda sementara oleh petugasnya sendiri (mis. istirahat), berbeda
    #: dari `status`: loket tetap ACTIVE dan terdaftar, hanya sedang tidak
    #: menerima panggilan baru. Admin tidak perlu dilibatkan untuk hal
    #: sesingkat jam istirahat.
    on_break: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)

    branch: Mapped[Branch] = relationship(back_populates="counters")
    #: Lihat `counter_category`: daftar kosong berarti boleh memanggil semua.
    categories: Mapped[list[ServiceCategory]] = relationship(
        secondary=counter_category, lazy="selectin", order_by="ServiceCategory.display_order"
    )

    def __repr__(self) -> str:
        return f"<Counter {self.code} {self.name!r}>"
