"""Antrian dan sequence penomorannya."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import QueueStatus

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.counter import Counter
    from app.models.queue_call import QueueCall
    from app.models.service_category import ServiceCategory
    from app.models.queue_note import QueueNote
    from app.models.survey import SatisfactionSurvey
    from app.models.user import User


class Queue(TimestampMixin, Base):
    """
    Satu nomor antrian.

    Antrian bersifat ANONIM. Tidak ada nama, NIK, nomor telepon, maupun
    alamat pengunjung yang disimpan. Pengunjung memilih jenis layanan
    lalu menerima nomor.

    queue_number sudah termasuk prefix jenis layanan, misalnya "A-001".
    sequence_number menyimpan angka murninya (1) untuk keperluan pengurutan
    dan pelaporan.
    """

    __tablename__ = "queue"
    __table_args__ = (
        # Pertahanan terakhir terhadap nomor antrian kembar dalam satu hari.
        sa.UniqueConstraint(
            "branch_id", "queue_date", "queue_number", name="uq_queue_date_number"
        ),
        sa.Index("ix_queue_date_status", "branch_id", "queue_date", "status"),
        # Satu loket hanya boleh memegang satu nomor aktif per hari. SKIPPED
        # sengaja tidak termasuk: nomor itu tetap menyimpan loket terakhir,
        # tetapi loketnya sudah boleh memanggil pengunjung berikutnya. Indeks
        # parsial menjaga invariant ini juga bila dua proses lolos dari
        # pemeriksaan aplikasi pada saat yang persis bersamaan.
        sa.Index(
            "uq_queue_active_counter_date",
            "counter_id",
            "queue_date",
            unique=True,
            sqlite_where=sa.text(
                "counter_id IS NOT NULL AND status IN ('CALLED', 'SERVING', 'PAUSED')"
            ),
            postgresql_where=sa.text(
                "counter_id IS NOT NULL AND status IN ('CALLED', 'SERVING', 'PAUSED')"
            ),
        ),
        sa.CheckConstraint("sequence_number > 0", name="sequence_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        sa.ForeignKey("branch.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        sa.ForeignKey("service_category.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    queue_date: Mapped[date] = mapped_column(sa.Date, nullable=False, index=True)
    queue_number: Mapped[str] = mapped_column(sa.String(12), nullable=False)
    sequence_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # Alasan prioritas (lihat AlasanPrioritas); kosong berarti nomor biasa.
    # Hanya petugas pendaftaran yang dapat mengisinya, saat nomor terbit.
    prioritas: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)

    status: Mapped[QueueStatus] = mapped_column(
        sa.Enum(QueueStatus, native_enum=False, length=12),
        nullable=False,
        default=QueueStatus.WAITING,
        index=True,
    )

    # Terisi saat antrian dipanggil.
    counter_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("counter.id", ondelete="RESTRICT"), index=True
    )
    # Petugas yang bertanggung jawab sejak nomor dipanggil. Dapat dialihkan
    # ADMIN bila petugas meninggalkan pelayanan; hasil akhirnya dipakai
    # laporan per petugas dan survey.
    served_by_user_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )

    called_at: Mapped[datetime | None] = mapped_column(sa.DateTime)
    serving_at: Mapped[datetime | None] = mapped_column(sa.DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime)

    branch: Mapped[Branch] = relationship(back_populates="queues")
    category: Mapped[ServiceCategory] = relationship()
    counter: Mapped[Counter | None] = relationship()
    served_by: Mapped[User | None] = relationship()
    calls: Mapped[list[QueueCall]] = relationship(
        back_populates="queue", order_by="QueueCall.call_number"
    )
    survey: Mapped[SatisfactionSurvey | None] = relationship(back_populates="queue")
    note: Mapped[QueueNote | None] = relationship(
        back_populates="queue", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Queue {self.queue_number} {self.status.value}>"


class QueueSequence(Base):
    """
    Penghitung nomor antrian per cabang, per tanggal, per jenis layanan.

    Tabel teknis, bukan domain bisnis. Keberadaannya dibutuhkan agar
    penomoran tidak memakai SELECT MAX(...) + 1 yang rawan menghasilkan
    nomor kembar ketika dua nomor dibuat bersamaan.

    Cara pakainya (Phase 4): di dalam BEGIN IMMEDIATE, jalankan
    UPDATE ... SET last_number = last_number + 1 ... RETURNING last_number.
    Baris terkunci sejak awal transaksi sehingga hanya satu penulis yang
    dapat menaikkan nilainya pada satu waktu.

    Nomor otomatis dimulai lagi dari 1 setiap hari karena queue_date
    merupakan bagian dari primary key.
    """

    __tablename__ = "queue_sequence"

    branch_id: Mapped[int] = mapped_column(
        sa.ForeignKey("branch.id", ondelete="RESTRICT"), primary_key=True
    )
    queue_date: Mapped[date] = mapped_column(sa.Date, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        sa.ForeignKey("service_category.id", ondelete="RESTRICT"), primary_key=True
    )
    last_number: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<QueueSequence {self.queue_date} cat={self.category_id} n={self.last_number}>"
