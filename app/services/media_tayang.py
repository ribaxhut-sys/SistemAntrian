"""
Catatan tayang iklan anjungan: dicatat dari laporan tablet, dibaca di
halaman Pengaturan.

Tablet menjumlah sendiri berapa kali tiap berkas mulai tampil dan berapa
kali gagal diputar, lalu mengirim jumlah itu berkala ke API. Di sini jumlah
itu ditambahkan ke baris hari ini milik tablet tersebut.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.core import clock
from app.core.database import session_scope
from app.models.kiosk_device import KioskDevice
from app.models.media_tayang import KioskMediaTayang

#: Batas wajar satu laporan, supaya tablet rusak tidak mengisi tabel sembarangan.
MAKS_BUTIR_LAPORAN = 100
MAKS_JUMLAH_PER_BUTIR = 100_000

#: Rentang angka "30 hari" di halaman Pengaturan.
RENTANG_HARI = 30


@dataclass(frozen=True)
class LaporanBerkas:
    """Satu butir laporan tablet."""

    nama: str
    tayang: int = 0
    gagal: int = 0
    galat: str = ""
    #: Percobaan terakhir di tablet itu gagal. Laporan yang memuat tayang
    #: dan gagal sekaligus tidak menyebut mana yang lebih dulu; ini yang
    #: menentukan tanda gagal di halaman Pengaturan tetap menyala atau padam.
    terakhir_gagal: bool = False


@dataclass(frozen=True)
class GagalDiTablet:
    tablet: str
    pesan: str
    waktu: datetime


@dataclass
class RingkasanBerkas:
    tayang_hari_ini: int = 0
    tayang_rentang: int = 0
    #: Tablet yang terakhir kali GAGAL memutar berkas ini, dan sejak itu
    #: belum berhasil memutarnya lagi.
    gagal: list[GagalDiTablet] = field(default_factory=list)


def _batas(angka: int) -> int:
    return max(0, min(int(angka), MAKS_JUMLAH_PER_BUTIR))


def catat(device_id: str, laporan: list[LaporanBerkas]) -> None:
    """Tambahkan laporan satu tablet ke baris hari ini."""
    device_id = (device_id or "").strip()[:64]
    if not device_id:
        return
    try:
        _catat(device_id, laporan)
    except IntegrityError:
        # Dua laporan tablet yang sama tiba bersamaan dan keduanya membuat
        # baris baru: yang kalah cukup diulang, barisnya sekarang sudah ada.
        _catat(device_id, laporan)


def _catat(device_id: str, laporan: list[LaporanBerkas]) -> None:
    sekarang = clock.now()
    hari = sekarang.date()
    with session_scope() as session:
        for butir in laporan[:MAKS_BUTIR_LAPORAN]:
            nama = (butir.nama or "").strip()[:255]
            tayang, gagal = _batas(butir.tayang), _batas(butir.gagal)
            if not nama or not (tayang or gagal):
                continue
            baris = session.scalar(
                sa.select(KioskMediaTayang).where(
                    KioskMediaTayang.tanggal == hari,
                    KioskMediaTayang.device_id == device_id,
                    KioskMediaTayang.nama_berkas == nama,
                )
            )
            if baris is None:
                baris = KioskMediaTayang(
                    tanggal=hari,
                    device_id=device_id,
                    nama_berkas=nama,
                    jumlah_tayang=0,
                    jumlah_gagal=0,
                    galat_terakhir="",
                )
                session.add(baris)
            baris.jumlah_tayang += tayang
            baris.jumlah_gagal += gagal
            if gagal:
                baris.gagal_terakhir_pada = sekarang
                baris.galat_terakhir = (butir.galat or "").strip()[:200]
            if tayang and not butir.terakhir_gagal:
                baris.tayang_terakhir_pada = sekarang
            session.flush()


def ringkasan(hari_ini: date | None = None) -> dict[str, RingkasanBerkas]:
    """Angka tayang dan tanda gagal per nama berkas, untuk halaman Pengaturan."""
    hari_ini = hari_ini or clock.today()
    awal = hari_ini - timedelta(days=RENTANG_HARI - 1)
    hasil: dict[str, RingkasanBerkas] = {}
    with session_scope() as session:
        # Dikelompokkan per tanggal biasa, bukan per ekspresi "tanggal = hari
        # ini": PostgreSQL menganggap ekspresi berparameter di SELECT dan di
        # GROUP BY sebagai dua ekspresi berbeda lalu menolak query-nya.
        jumlah = session.execute(
            sa.select(
                KioskMediaTayang.nama_berkas,
                KioskMediaTayang.tanggal,
                sa.func.sum(KioskMediaTayang.jumlah_tayang),
            )
            .where(
                KioskMediaTayang.tanggal >= awal,
                KioskMediaTayang.tanggal <= hari_ini,
            )
            .group_by(KioskMediaTayang.nama_berkas, KioskMediaTayang.tanggal)
        )
        for nama, tanggal, total in jumlah:
            info = hasil.setdefault(nama, RingkasanBerkas())
            info.tayang_rentang += int(total or 0)
            if tanggal == hari_ini:
                info.tayang_hari_ini += int(total or 0)

        # Tanda gagal hanya dari kemarin dan hari ini: galat lama yang sudah
        # tidak terulang tidak perlu lagi mengkhawatirkan admin.
        terakhir: dict[tuple[str, str], _Terakhir] = {}
        for baris in session.scalars(
            sa.select(KioskMediaTayang)
            .where(
                KioskMediaTayang.tanggal >= hari_ini - timedelta(days=1),
                KioskMediaTayang.tanggal <= hari_ini,
            )
            .order_by(KioskMediaTayang.tanggal)
        ):
            terakhir.setdefault(
                (baris.nama_berkas, baris.device_id), _Terakhir()
            ).serap(baris)
        nama_tablet = {
            d.device_id: d.nama
            for d in session.scalars(
                sa.select(KioskDevice).where(
                    KioskDevice.device_id.in_({d for _, d in terakhir})
                )
            )
        }
    for (nama, device_id), akhir in terakhir.items():
        if not akhir.masih_gagal:
            continue
        hasil.setdefault(nama, RingkasanBerkas()).gagal.append(
            GagalDiTablet(
                tablet=nama_tablet.get(device_id) or device_id[:8],
                pesan=akhir.galat,
                waktu=akhir.gagal_pada,
            )
        )
    return hasil


@dataclass
class _Terakhir:
    """Waktu tayang dan gagal terakhir satu berkas di satu tablet, lintas hari."""

    tayang_pada: datetime | None = None
    gagal_pada: datetime | None = None
    galat: str = ""

    def serap(self, baris: KioskMediaTayang) -> None:
        """Baris dibaca urut tanggal, jadi yang datang belakangan lebih baru."""
        if baris.tayang_terakhir_pada is not None:
            self.tayang_pada = baris.tayang_terakhir_pada
        if baris.gagal_terakhir_pada is not None:
            self.gagal_pada = baris.gagal_terakhir_pada
            self.galat = baris.galat_terakhir

    @property
    def masih_gagal(self) -> bool:
        """Gagal, dan sejak itu belum berhasil diputar lagi."""
        if self.gagal_pada is None:
            return False
        return self.tayang_pada is None or self.tayang_pada < self.gagal_pada
