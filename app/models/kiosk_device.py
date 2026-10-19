"""
Perangkat Android yang menyambung ke API aplikasi server.

Dua jenis saja (lihat docs/istilah.md):

* ``anjungan``       tablet tempat pengunjung memilih layanan dan mencetak nomor.
* ``layar_antrian``  TV yang menampilkan nomor yang dipanggil.

Disimpan di database, bukan di memori API, karena API dan aplikasi Windows
adalah dua proses: API berjalan sebagai tugas Task Scheduler di bawah akun
SYSTEM, sedangkan daftar perangkat dibaca petugas dari layar Layanan
Anjungan. Satu-satunya tempat yang dibaca keduanya adalah database.

Token perangkat disimpan sebagai hash SHA-256, bukan teks asli. Token
adalah 48 byte acak, sehingga hash cepat sudah cukup; yang dicegah hanyalah
token terbaca utuh dari backup atau dari layar database.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class KioskDevice(TimestampMixin, Base):
    """Satu tablet atau TV yang pernah menghubungi API."""

    __tablename__ = "kiosk_device"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: UUID buatan perangkat sendiri, tersimpan di perangkat itu.
    device_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    nama: Mapped[str] = mapped_column(sa.String(80), nullable=False, default="")
    #: "anjungan" atau "layar_antrian".
    jenis: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="anjungan")
    #: Kosong = perangkat masih memakai token bersama (belum dipasangkan).
    token_hash: Mapped[str | None] = mapped_column(sa.String(64), unique=True)
    dicabut_pada: Mapped[datetime | None] = mapped_column(sa.DateTime)

    terakhir_terlihat: Mapped[datetime | None] = mapped_column(sa.DateTime)
    alamat_ip: Mapped[str] = mapped_column(sa.String(45), nullable=False, default="")
    versi_nama: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="")
    versi_kode: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    #: Hasil cetak terakhir: None belum pernah, True berhasil, False gagal.
    printer_ok: Mapped[bool | None] = mapped_column(sa.Boolean)
    printer_pesan: Mapped[str] = mapped_column(sa.String(200), nullable=False, default="")
    printer_waktu: Mapped[datetime | None] = mapped_column(sa.DateTime)

    # Status salinan media di tablet: berapa berkas dari daftar putar server
    # yang sudah tersalin utuh, berapa byte, dan kapan dilaporkan.
    media_total: Mapped[int | None] = mapped_column(sa.Integer)
    media_tersalin: Mapped[int | None] = mapped_column(sa.Integer)
    media_byte: Mapped[int | None] = mapped_column(sa.BigInteger)
    media_waktu: Mapped[datetime | None] = mapped_column(sa.DateTime)
    # Admin meminta tablet menyegarkan salinan media sekarang. Tablet
    # membandingkan nilainya dengan yang terakhir ia tangani.
    media_segarkan: Mapped[datetime | None] = mapped_column(sa.DateTime)


class KioskPairingCode(TimestampMixin, Base):
    """
    Kode 6 angka untuk memasangkan perangkat baru.

    Berumur pendek dan sekali pakai: kode inilah satu-satunya rahasia yang
    diketik orang, dan ia hanya berarti selama petugas sedang berdiri di
    depan tablet yang dipasangkan.
    """

    __tablename__ = "kiosk_pairing_code"

    id: Mapped[int] = mapped_column(primary_key=True)
    kode: Mapped[str] = mapped_column(sa.String(6), nullable=False, index=True)
    kedaluwarsa: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    dipakai_pada: Mapped[datetime | None] = mapped_column(sa.DateTime)


class KioskTicketRequest(TimestampMixin, Base):
    """
    Kunci idempotensi satu permintaan tiket dari anjungan Android.

    Tablet membuat `request_id` (UUID) sekali per tombol yang ditekan dan
    mengirim ulang UUID yang sama bila jawaban API tidak sampai. Baris ini
    disisipkan dalam TRANSAKSI YANG SAMA dengan baris antriannya (lihat
    `terbitkan_nomor`), sehingga tidak pernah ada nomor terbit tanpa
    kuncinya — termasuk bila API mati tepat sesudah commit. Permintaan
    ulang menemukan baris ini dan menerima tiket yang sama.

    Kuncinya pasangan (device_id, request_id): UUID hanya dijamin unik di
    perangkat pembuatnya. `device_id` kosong berarti tablet lama dengan
    token bersama yang tidak menyebut dirinya; semuanya berbagi satu ruang
    kunci, yang tetap aman karena UUID acak praktis tidak pernah kembar.
    """

    __tablename__ = "kiosk_ticket_request"
    __table_args__ = (sa.UniqueConstraint("device_id", "request_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, default="")
    request_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    #: Jenis layanan yang diminta. UUID yang sama dengan jenis layanan lain
    #: adalah kesalahan tablet, bukan permintaan ulang, dan ditolak.
    category_id: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    queue_id: Mapped[int] = mapped_column(
        sa.ForeignKey("queue.id", ondelete="CASCADE"), nullable=False, index=True
    )
