"""
Laporan antrian dan kepuasan pada rentang tanggal.

Melengkapi Ringkasan Harian, yang hanya menjawab "bagaimana hari ini".
Laporan menjawab pertanyaan sesudahnya: bagaimana sebulan kemarin, loket
mana yang paling lama melayani, petugas mana yang paling dinilai baik.

Angka dihitung di Python dari baris-baris rentang itu, bukan dengan
agregasi SQL per dialect. Satu kantor menerbitkan ratusan nomor sehari;
setahun penuh masih puluhan ribu baris bertiga-empat kolom waktu, dan
hasilnya dijamin sama persis di SQLite maupun PostgreSQL. Rentang dibatasi
satu tahun supaya tidak ada yang tidak sengaja memuat seluruh sejarah.

Definisi waktu sama dengan Ringkasan Harian (QueueRepository.rata_rata_durasi):
menunggu = terbit → pertama dipanggil, pelayanan = mulai dilayani → selesai.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import sqlalchemy as sa

from app.core.database import session_scope
from app.core.errors import ValidationError
from app.models import (
    Counter,
    Queue,
    QueueCall,
    QueueStatus,
    SatisfactionSurvey,
    ServiceCategory,
    User,
)
from app.services.auth_service import AuthService
from app.services.permissions import Permission
from app.utils.formatting import durasi_singkat

RENTANG_MAKS_HARI = 366


@dataclass
class BarisLaporan:
    """Satu baris pada tabel laporan (per hari, layanan, loket, atau petugas)."""

    nama: str
    terbit: int = 0
    dipanggil: int = 0
    selesai: int = 0
    tidak_hadir: int = 0
    batal: int = 0
    _menunggu: list[float] = field(default_factory=list, repr=False)
    _layanan: list[float] = field(default_factory=list, repr=False)
    _rating: list[int] = field(default_factory=list, repr=False)

    @property
    def rata_menunggu_detik(self) -> float | None:
        return sum(self._menunggu) / len(self._menunggu) if self._menunggu else None

    @property
    def rata_layanan_detik(self) -> float | None:
        return sum(self._layanan) / len(self._layanan) if self._layanan else None

    @property
    def jumlah_survey(self) -> int:
        return len(self._rating)

    @property
    def rata_kepuasan(self) -> float | None:
        return sum(self._rating) / len(self._rating) if self._rating else None

    @property
    def label_menunggu(self) -> str:
        return durasi_singkat(self.rata_menunggu_detik)

    @property
    def label_layanan(self) -> str:
        return durasi_singkat(self.rata_layanan_detik)

    @property
    def label_kepuasan(self) -> str:
        nilai = self.rata_kepuasan
        return "—" if nilai is None else f"{nilai:.1f}".replace(".", ",")


@dataclass(frozen=True)
class Laporan:
    dari: date
    sampai: date
    total: BarisLaporan
    per_hari: list[BarisLaporan]
    per_layanan: list[BarisLaporan]
    per_loket: list[BarisLaporan]
    per_petugas: list[BarisLaporan]

    @property
    def jumlah_hari(self) -> int:
        return (self.sampai - self.dari).days + 1


def _detik(awal: datetime | None, akhir: datetime | None) -> float | None:
    if awal is None or akhir is None:
        return None
    nilai = (akhir - awal).total_seconds()
    return nilai if nilai >= 0 else None


def _catat(baris: BarisLaporan, status, created, called, serving, completed) -> None:
    baris.terbit += 1
    if called is not None:
        baris.dipanggil += 1
    if status == QueueStatus.COMPLETED:
        baris.selesai += 1
    elif status == QueueStatus.NO_SHOW:
        baris.tidak_hadir += 1
    elif status == QueueStatus.CANCELLED:
        baris.batal += 1
    tunggu = _detik(created, called)
    if tunggu is not None:
        baris._menunggu.append(tunggu)
    layanan = _detik(serving, completed)
    if layanan is not None:
        baris._layanan.append(layanan)


class ReportService:
    """Laporan rentang tanggal untuk SUPERVISOR."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    def laporan(self, dari: date, sampai: date) -> Laporan:
        sesi = self.auth.require_permission(Permission.REPORT_VIEW)
        if sampai < dari:
            raise ValidationError("Tanggal akhir tidak boleh sebelum tanggal awal.")
        if (sampai - dari).days + 1 > RENTANG_MAKS_HARI:
            raise ValidationError("Rentang laporan paling panjang satu tahun.")

        with session_scope() as session:
            nama_layanan = dict(session.execute(sa.select(ServiceCategory.id, ServiceCategory.name)).all())
            nama_loket = dict(session.execute(sa.select(Counter.id, Counter.name)).all())
            nama_petugas = dict(session.execute(sa.select(User.id, User.full_name)).all())
            dalam_rentang = (
                Queue.branch_id == sesi.branch_id,
                Queue.queue_date >= dari,
                Queue.queue_date <= sampai,
            )
            # Data lama dapat belum mempunyai `served_by_user_id`; untuk
            # baris itu pemanggil terakhir menjadi petugas penanganannya.
            pemanggil: dict[int, int] = {}
            for queue_id, user_id, _ in session.execute(
                sa.select(QueueCall.queue_id, QueueCall.user_id, QueueCall.call_number)
                .join(Queue, Queue.id == QueueCall.queue_id)
                .where(*dalam_rentang)
                .order_by(QueueCall.queue_id, QueueCall.call_number)
            ).all():
                pemanggil[queue_id] = user_id
            antrian = session.execute(
                sa.select(
                    Queue.id,
                    Queue.queue_date,
                    Queue.status,
                    Queue.category_id,
                    Queue.counter_id,
                    Queue.served_by_user_id,
                    Queue.created_at,
                    Queue.called_at,
                    Queue.serving_at,
                    Queue.completed_at,
                ).where(*dalam_rentang)
            ).all()
            survey = session.execute(
                sa.select(
                    SatisfactionSurvey.counter_id,
                    SatisfactionSurvey.officer_id,
                    SatisfactionSurvey.rating,
                    SatisfactionSurvey.submitted_at,
                ).where(
                    SatisfactionSurvey.branch_id == sesi.branch_id,
                    SatisfactionSurvey.submitted_at >= datetime.combine(dari, datetime.min.time()),
                    SatisfactionSurvey.submitted_at
                    < datetime.combine(sampai + timedelta(days=1), datetime.min.time()),
                )
            ).all()

        total = BarisLaporan("Total")
        per_hari: dict[date, BarisLaporan] = {}
        per_layanan: dict[int, BarisLaporan] = {}
        per_loket: dict[int, BarisLaporan] = {}
        per_petugas: dict[int, BarisLaporan] = {}

        def ambil(kamus: dict, kunci, nama: str) -> BarisLaporan:
            if kunci not in kamus:
                kamus[kunci] = BarisLaporan(nama)
            return kamus[kunci]

        for (queue_id, tanggal, status, kategori, loket, petugas, created, called, serving,
             completed) in antrian:
            petugas = petugas if petugas is not None else pemanggil.get(queue_id)
            waktu = (status, created, called, serving, completed)
            _catat(total, *waktu)
            _catat(ambil(per_hari, tanggal, tanggal.isoformat()), *waktu)
            _catat(ambil(per_layanan, kategori, nama_layanan.get(kategori, "—")), *waktu)
            if loket is not None:
                _catat(ambil(per_loket, loket, nama_loket.get(loket, "—")), *waktu)
            if petugas is not None:
                _catat(ambil(per_petugas, petugas, nama_petugas.get(petugas, "—")), *waktu)

        for loket, petugas, rating, waktu in survey:
            total._rating.append(rating)
            ambil(per_hari, waktu.date(), waktu.date().isoformat())._rating.append(rating)
            ambil(per_loket, loket, nama_loket.get(loket, "—"))._rating.append(rating)
            ambil(per_petugas, petugas, nama_petugas.get(petugas, "—"))._rating.append(rating)

        def urut_nama(kamus: dict) -> list[BarisLaporan]:
            return sorted(kamus.values(), key=lambda b: b.nama.lower())

        return Laporan(
            dari=dari,
            sampai=sampai,
            total=total,
            per_hari=[per_hari[k] for k in sorted(per_hari)],
            per_layanan=sorted(per_layanan.values(), key=lambda b: -b.terbit),
            per_loket=urut_nama(per_loket),
            per_petugas=urut_nama(per_petugas),
        )


# =====================================================================
# Kolom tabel: dipakai layar, PDF, dan Excel, supaya ketiganya sama.
# =====================================================================

HARI_SINGKAT = ("Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min")


def _label_tanggal(iso: str) -> str:
    from app.utils.formatting import tanggal_pendek

    tanggal = date.fromisoformat(iso)
    return f"{HARI_SINGKAT[tanggal.weekday()]}, {tanggal_pendek(tanggal)} {tanggal.year}"


#: (judul kolom, fungsi teks untuk layar/PDF, fungsi nilai untuk Excel, rata kanan)
Kolom = tuple


def _k(judul, teks, nilai=None, kanan=True) -> Kolom:
    return (judul, teks, nilai or teks, kanan)


def _menit(detik: float | None):
    return None if detik is None else round(detik / 60, 1)


KOLOM_TABEL: dict[str, list[Kolom]] = {
    "per_hari": [
        _k("Tanggal", lambda b: _label_tanggal(b.nama), lambda b: date.fromisoformat(b.nama), False),
        _k("Terbit", lambda b: str(b.terbit), lambda b: b.terbit),
        _k("Selesai", lambda b: str(b.selesai), lambda b: b.selesai),
        _k("Tidak hadir", lambda b: str(b.tidak_hadir), lambda b: b.tidak_hadir),
        _k("Batal", lambda b: str(b.batal), lambda b: b.batal),
        _k("Rata-rata menunggu", lambda b: b.label_menunggu, lambda b: _menit(b.rata_menunggu_detik)),
        _k("Rata-rata pelayanan", lambda b: b.label_layanan, lambda b: _menit(b.rata_layanan_detik)),
        _k("Survey", lambda b: str(b.jumlah_survey), lambda b: b.jumlah_survey),
        _k("Kepuasan", lambda b: b.label_kepuasan, lambda b: b.rata_kepuasan),
    ],
    "per_layanan": [
        _k("Jenis layanan", lambda b: b.nama, kanan=False),
        _k("Terbit", lambda b: str(b.terbit), lambda b: b.terbit),
        _k("Selesai", lambda b: str(b.selesai), lambda b: b.selesai),
        _k("Tidak hadir", lambda b: str(b.tidak_hadir), lambda b: b.tidak_hadir),
        _k("Batal", lambda b: str(b.batal), lambda b: b.batal),
        _k("Rata-rata menunggu", lambda b: b.label_menunggu, lambda b: _menit(b.rata_menunggu_detik)),
        _k("Rata-rata pelayanan", lambda b: b.label_layanan, lambda b: _menit(b.rata_layanan_detik)),
    ],
    "per_loket": [
        _k("Loket", lambda b: b.nama, kanan=False),
        _k("Dipanggil", lambda b: str(b.dipanggil), lambda b: b.dipanggil),
        _k("Selesai", lambda b: str(b.selesai), lambda b: b.selesai),
        _k("Tidak hadir", lambda b: str(b.tidak_hadir), lambda b: b.tidak_hadir),
        _k("Rata-rata pelayanan", lambda b: b.label_layanan, lambda b: _menit(b.rata_layanan_detik)),
        _k("Survey", lambda b: str(b.jumlah_survey), lambda b: b.jumlah_survey),
        _k("Kepuasan", lambda b: b.label_kepuasan, lambda b: b.rata_kepuasan),
    ],
    "per_petugas": [
        _k("Petugas", lambda b: b.nama, kanan=False),
        _k("Dipanggil", lambda b: str(b.dipanggil), lambda b: b.dipanggil),
        _k("Selesai", lambda b: str(b.selesai), lambda b: b.selesai),
        _k("Tidak hadir", lambda b: str(b.tidak_hadir), lambda b: b.tidak_hadir),
        _k("Rata-rata pelayanan", lambda b: b.label_layanan, lambda b: _menit(b.rata_layanan_detik)),
        _k("Survey", lambda b: str(b.jumlah_survey), lambda b: b.jumlah_survey),
        _k("Kepuasan", lambda b: b.label_kepuasan, lambda b: b.rata_kepuasan),
    ],
}

JUDUL_TABEL = {
    "per_hari": "Per hari",
    "per_layanan": "Per layanan",
    "per_loket": "Per loket",
    "per_petugas": "Per petugas",
}


def angka_ringkasan(laporan: Laporan) -> list[tuple[str, str]]:
    """Enam angka besar di atas tabel, dalam urutan tampilnya."""
    t = laporan.total
    kepuasan = t.label_kepuasan
    return [
        ("Nomor terbit", f"{t.terbit:,}".replace(",", ".")),
        ("Selesai dilayani", f"{t.selesai:,}".replace(",", ".")),
        ("Tidak hadir", f"{t.tidak_hadir:,}".replace(",", ".")),
        ("Rata-rata menunggu", t.label_menunggu),
        ("Rata-rata pelayanan", t.label_layanan),
        (f"Kepuasan ({t.jumlah_survey} survey)", kepuasan),
    ]
