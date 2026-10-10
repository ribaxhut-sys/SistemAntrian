"""
Catatan tayang iklan anjungan, dilaporkan oleh tablet.

Satu baris per hari, per tablet, per berkas. Angkanya dijumlah di tablet
lalu dikirim berkala, bukan satu permintaan per tayang: tablet di loket
ramai memutar ratusan iklan sehari dan tidak perlu membebani API.

Gunanya dua: bukti tayang untuk iklan pihak ketiga, dan tanda bagi admin
bila sebuah berkas gagal diputar di tablet tertentu (format video yang
tidak didukung pemutar Android, berkas rusak).
"""

from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class KioskMediaTayang(TimestampMixin, Base):
    """Jumlah tayang dan gagal satu berkas di satu tablet pada satu hari."""

    __tablename__ = "kiosk_media_tayang"
    __table_args__ = (sa.UniqueConstraint("tanggal", "device_id", "nama_berkas"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tanggal: Mapped[date] = mapped_column(sa.Date, nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    nama_berkas: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    jumlah_tayang: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    jumlah_gagal: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    galat_terakhir: Mapped[str] = mapped_column(sa.String(200), nullable=False, default="")
    tayang_terakhir_pada: Mapped[datetime | None] = mapped_column(sa.DateTime)
    gagal_terakhir_pada: Mapped[datetime | None] = mapped_column(sa.DateTime)
