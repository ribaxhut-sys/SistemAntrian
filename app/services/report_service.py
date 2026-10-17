"""
Laporan antrian dan kepuasan pada rentang tanggal.

Melengkapi Ringkasan Harian, yang hanya menjawab "bagaimana hari ini".
Laporan menjawab pertanyaan sesudahnya: bagaimana sebulan kemarin, loket
mana yang paling lama melayani, petugas mana yang paling dinilai baik.

Angka dihitung di Python dari baris-baris rentang itu. Satu kantor menerbitkan
ratusan nomor sehari; setahun penuh masih puluhan ribu baris dan rentang
dibatasi satu tahun supaya tidak ada yang memuat seluruh sejarah tanpa sengaja.

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
    AuditAction,
    AuditLog,
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
from app.services.queue_service import LABEL_STATUS
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
    prioritas: int = 0
    prioritas_dicabut: int = 0
    #: Nama kelompok baris, misalnya petugas pada tabel petugas per layanan.
    kelompok: str = ""
    _menunggu: list[float] = field(default_factory=list, repr=False)
    _layanan: list[float] = field(default_factory=list, repr=False)
    _rating: list[int] = field(default_factory=list, repr=False)
    _menunggu_prioritas: list[float] = field(default_factory=list, repr=False)

    @property
    def rata_menunggu_detik(self) -> float | None:
        return sum(self._menunggu) / len(self._menunggu) if self._menunggu else None

    @property
    def rata_layanan_detik(self) -> float | None:
        return sum(self._layanan) / len(self._layanan) if self._layanan else None

    @property
    def rata_menunggu_prioritas_detik(self) -> float | None:
        return (
            sum(self._menunggu_prioritas) / len(self._menunggu_prioritas)
            if self._menunggu_prioritas
            else None
        )

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
    def label_menunggu_prioritas(self) -> str:
        return durasi_singkat(self.rata_menunggu_prioritas_detik)

    @property
    def label_kepuasan(self) -> str:
        nilai = self.rata_kepuasan
        return "—" if nilai is None else f"{nilai:.1f}".replace(".", ",")


@dataclass(frozen=True)
class TiketRiwayat:
    """Satu nomor antrian pada riwayat pelayanan, untuk ditelusuri per petugas."""

    tanggal: date
    nomor: str
    layanan: str
    loket: str
    petugas: str
    status: str
    terbit: datetime | None
    dipanggil: datetime | None
    mulai: datetime | None
    selesai: datetime | None
    nilai: int | None
    prioritas: bool = False
    prioritas_dicabut: bool = False

    @property
    def menunggu_detik(self) -> float | None:
        return _detik(self.terbit, self.dipanggil)

    @property
    def layanan_detik(self) -> float | None:
        return _detik(self.mulai, self.selesai)


@dataclass(frozen=True)
class Laporan:
    dari: date
    sampai: date
    total: BarisLaporan
    per_hari: list[BarisLaporan]
    per_layanan: list[BarisLaporan]
    per_loket: list[BarisLaporan]
    per_petugas: list[BarisLaporan]
    #: Per petugas: baris totalnya (sama dengan per_petugas) dan rincian
    #: per jenis layanan yang ditanganinya, nama layanan di `nama`.
    petugas_layanan: list[tuple[BarisLaporan, list[BarisLaporan]]] = field(default_factory=list)
    #: Setiap nomor pada rentang, urut waktu terbit. Hanya untuk Excel.
    riwayat: list[TiketRiwayat] = field(default_factory=list)
    #: Terisi hanya untuk laporan pribadi CRO; kosong berarti seluruh cabang.
    nama_petugas: str = ""

    @property
    def jumlah_hari(self) -> int:
        return (self.sampai - self.dari).days + 1


def _detik(awal: datetime | None, akhir: datetime | None) -> float | None:
    if awal is None or akhir is None:
        return None
    nilai = (akhir - awal).total_seconds()
    return nilai if nilai >= 0 else None


def _catat(
    baris: BarisLaporan,
    status,
    created,
    called,
    serving,
    completed,
    prioritas=False,
    prioritas_dicabut=False,
) -> None:
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
        if prioritas:
            baris._menunggu_prioritas.append(tunggu)
    if prioritas:
        baris.prioritas += 1
    if prioritas_dicabut:
        baris.prioritas_dicabut += 1
    layanan = _detik(serving, completed)
    if layanan is not None:
        baris._layanan.append(layanan)


class ReportService:
    """Laporan cabang untuk pengawas, atau laporan pribadi untuk CRO."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    def laporan(self, dari: date, sampai: date) -> Laporan:
        sesi = self.auth.require_permission(Permission.REPORT_VIEW)
        return self._susun(dari, sampai, sesi.branch_id)

    def laporan_petugas(self, dari: date, sampai: date) -> Laporan:
        """Riwayat milik CRO yang sedang masuk, tanpa parameter id yang dapat dipalsukan."""
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)
        return self._susun(
            dari,
            sampai,
            sesi.branch_id,
            petugas_id=sesi.user_id,
            nama_petugas=sesi.full_name,
        )

    def _susun(
        self,
        dari: date,
        sampai: date,
        branch_id: int,
        *,
        petugas_id: int | None = None,
        nama_petugas: str = "",
    ) -> Laporan:
        if sampai < dari:
            raise ValidationError("Tanggal akhir tidak boleh sebelum tanggal awal.")
        if (sampai - dari).days + 1 > RENTANG_MAKS_HARI:
            raise ValidationError("Rentang laporan paling panjang satu tahun.")

        with session_scope() as session:
            nama_layanan = dict(session.execute(sa.select(ServiceCategory.id, ServiceCategory.name)).all())
            nama_loket = dict(session.execute(sa.select(Counter.id, Counter.name)).all())
            nama_petugas_per_id = dict(
                session.execute(sa.select(User.id, User.full_name)).all()
            )
            dalam_rentang = (
                Queue.branch_id == branch_id,
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
                    Queue.queue_number,
                    Queue.status,
                    Queue.category_id,
                    Queue.counter_id,
                    Queue.served_by_user_id,
                    Queue.created_at,
                    Queue.called_at,
                    Queue.serving_at,
                    Queue.completed_at,
                    Queue.prioritas,
                )
                .where(*dalam_rentang)
                .order_by(Queue.created_at, Queue.id)
            ).all()
            prioritas_dicabut = set(
                session.scalars(
                    sa.select(AuditLog.entity_id)
                    .join(Queue, Queue.id == AuditLog.entity_id)
                    .where(
                        *dalam_rentang,
                        AuditLog.action == AuditAction.CLEAR_PRIORITY.value,
                        AuditLog.entity_type == "queue",
                    )
                )
            )
            syarat_survey = [
                SatisfactionSurvey.branch_id == branch_id,
                SatisfactionSurvey.submitted_at
                >= datetime.combine(dari, datetime.min.time()),
                SatisfactionSurvey.submitted_at
                < datetime.combine(sampai + timedelta(days=1), datetime.min.time()),
            ]
            if petugas_id is not None:
                syarat_survey.append(SatisfactionSurvey.officer_id == petugas_id)
            survey = session.execute(
                sa.select(
                    SatisfactionSurvey.queue_id,
                    SatisfactionSurvey.category_id,
                    SatisfactionSurvey.counter_id,
                    SatisfactionSurvey.officer_id,
                    SatisfactionSurvey.rating,
                    SatisfactionSurvey.submitted_at,
                ).where(*syarat_survey)
            ).all()

        total = BarisLaporan("Total")
        per_hari: dict[date, BarisLaporan] = {}
        per_layanan: dict[int, BarisLaporan] = {}
        per_loket: dict[int, BarisLaporan] = {}
        per_petugas: dict[int, BarisLaporan] = {}
        per_petugas_layanan: dict[tuple[int, int], BarisLaporan] = {}
        nilai_tiket = {queue_id: rating for queue_id, _, _, _, rating, _ in survey}
        riwayat: list[TiketRiwayat] = []
        id_termasuk: set[int] = set()

        def ambil(kamus: dict, kunci, nama: str) -> BarisLaporan:
            if kunci not in kamus:
                kamus[kunci] = BarisLaporan(nama)
            return kamus[kunci]

        def ambil_rincian(petugas: int, kategori: int) -> BarisLaporan:
            kunci = (petugas, kategori)
            if kunci not in per_petugas_layanan:
                per_petugas_layanan[kunci] = BarisLaporan(
                    nama_layanan.get(kategori, "—"),
                    kelompok=nama_petugas_per_id.get(petugas, "—"),
                )
            return per_petugas_layanan[kunci]

        for (
            queue_id,
            tanggal,
            nomor,
            status,
            kategori,
            loket,
            petugas,
            created,
            called,
            serving,
            completed,
            alasan_prioritas,
        ) in antrian:
            petugas = petugas if petugas is not None else pemanggil.get(queue_id)
            if petugas_id is not None and petugas != petugas_id:
                continue
            id_termasuk.add(queue_id)
            dicabut = queue_id in prioritas_dicabut
            waktu = (
                status,
                created,
                called,
                serving,
                completed,
                bool(alasan_prioritas) or dicabut,
                dicabut,
            )
            _catat(total, *waktu)
            _catat(ambil(per_hari, tanggal, tanggal.isoformat()), *waktu)
            _catat(ambil(per_layanan, kategori, nama_layanan.get(kategori, "—")), *waktu)
            if loket is not None:
                _catat(ambil(per_loket, loket, nama_loket.get(loket, "—")), *waktu)
            if petugas is not None:
                _catat(
                    ambil(
                        per_petugas,
                        petugas,
                        nama_petugas_per_id.get(petugas, "—"),
                    ),
                    *waktu,
                )
                _catat(ambil_rincian(petugas, kategori), *waktu)
            riwayat.append(
                TiketRiwayat(
                    tanggal=tanggal,
                    nomor=nomor,
                    layanan=nama_layanan.get(kategori, "—"),
                    loket=nama_loket.get(loket, "") if loket is not None else "",
                    petugas=(
                        nama_petugas_per_id.get(petugas, "")
                        if petugas is not None
                        else ""
                    ),
                    status=LABEL_STATUS.get(status, getattr(status, "value", str(status))),
                    terbit=created,
                    dipanggil=called,
                    mulai=serving,
                    selesai=completed,
                    nilai=nilai_tiket.get(queue_id),
                    prioritas=bool(alasan_prioritas) or dicabut,
                    prioritas_dicabut=dicabut,
                )
            )

        for queue_id, kategori, loket, petugas, rating, waktu in survey:
            if petugas_id is not None and queue_id not in id_termasuk:
                continue
            total._rating.append(rating)
            ambil(per_hari, waktu.date(), waktu.date().isoformat())._rating.append(rating)
            ambil(per_loket, loket, nama_loket.get(loket, "—"))._rating.append(rating)
            ambil(
                per_petugas, petugas, nama_petugas_per_id.get(petugas, "—")
            )._rating.append(rating)
            ambil_rincian(petugas, kategori)._rating.append(rating)

        def urut_nama(kamus: dict) -> list[BarisLaporan]:
            return sorted(kamus.values(), key=lambda b: b.nama.lower())

        rincian: dict[int, list[BarisLaporan]] = {}
        for (petugas, _), baris in per_petugas_layanan.items():
            rincian.setdefault(petugas, []).append(baris)
        petugas_layanan = [
            (
                per_petugas[petugas],
                sorted(daftar, key=lambda b: (-b.selesai, -b.dipanggil, b.nama.lower())),
            )
            for petugas, daftar in rincian.items()
        ]
        petugas_layanan.sort(key=lambda p: p[0].nama.lower())

        return Laporan(
            dari=dari,
            sampai=sampai,
            total=total,
            per_hari=[per_hari[k] for k in sorted(per_hari)],
            per_layanan=sorted(per_layanan.values(), key=lambda b: -b.terbit),
            per_loket=urut_nama(per_loket),
            per_petugas=urut_nama(per_petugas),
            petugas_layanan=petugas_layanan,
            riwayat=riwayat,
            nama_petugas=nama_petugas,
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
        _k("Prioritas", lambda b: str(b.prioritas), lambda b: b.prioritas),
        _k("Dicabut", lambda b: str(b.prioritas_dicabut), lambda b: b.prioritas_dicabut),
        _k("Rata-rata menunggu", lambda b: b.label_menunggu, lambda b: _menit(b.rata_menunggu_detik)),
        _k("Tunggu prioritas", lambda b: b.label_menunggu_prioritas, lambda b: _menit(b.rata_menunggu_prioritas_detik)),
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
        _k("Prioritas", lambda b: str(b.prioritas), lambda b: b.prioritas),
        _k("Dicabut", lambda b: str(b.prioritas_dicabut), lambda b: b.prioritas_dicabut),
        _k("Rata-rata menunggu", lambda b: b.label_menunggu, lambda b: _menit(b.rata_menunggu_detik)),
        _k("Tunggu prioritas", lambda b: b.label_menunggu_prioritas, lambda b: _menit(b.rata_menunggu_prioritas_detik)),
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

#: Rincian petugas per jenis layanan. Tidak tampil di layar, hanya di
#: PDF (dikelompokkan per petugas) dan Excel (satu baris per pasangan,
#: supaya mudah difilter dan dibuat PivotTable).
KOLOM_PETUGAS_LAYANAN: list[Kolom] = [
    _k("Petugas", lambda b: b.kelompok, kanan=False),
    _k("Jenis layanan", lambda b: b.nama, kanan=False),
    _k("Dipanggil", lambda b: str(b.dipanggil), lambda b: b.dipanggil),
    _k("Selesai", lambda b: str(b.selesai), lambda b: b.selesai),
    _k("Tidak hadir", lambda b: str(b.tidak_hadir), lambda b: b.tidak_hadir),
    _k("Rata-rata pelayanan", lambda b: b.label_layanan, lambda b: _menit(b.rata_layanan_detik)),
    _k("Survey", lambda b: str(b.jumlah_survey), lambda b: b.jumlah_survey),
    _k("Kepuasan", lambda b: b.label_kepuasan, lambda b: b.rata_kepuasan),
]


def _jam(waktu: datetime | None) -> str:
    return "" if waktu is None else f"{waktu:%H:%M:%S}"


#: Riwayat pelayanan per nomor antrian, hanya untuk Excel. Jam disimpan
#: sebagai waktu Excel agar dapat diurutkan dan dihitung.
KOLOM_RIWAYAT: list[Kolom] = [
    _k("Tanggal", lambda t: t.tanggal.isoformat(), lambda t: t.tanggal, False),
    _k("Nomor", lambda t: t.nomor, kanan=False),
    _k("Jenis layanan", lambda t: t.layanan, kanan=False),
    _k("Loket", lambda t: t.loket, kanan=False),
    _k("Petugas", lambda t: t.petugas, kanan=False),
    _k("Status", lambda t: t.status, kanan=False),
    _k("Jam terbit", lambda t: _jam(t.terbit), lambda t: t.terbit),
    _k("Jam dipanggil", lambda t: _jam(t.dipanggil), lambda t: t.dipanggil),
    _k("Jam mulai dilayani", lambda t: _jam(t.mulai), lambda t: t.mulai),
    _k("Jam selesai", lambda t: _jam(t.selesai), lambda t: t.selesai),
    _k("Lama menunggu", lambda t: durasi_singkat(t.menunggu_detik), lambda t: _menit(t.menunggu_detik)),
    _k("Lama pelayanan", lambda t: durasi_singkat(t.layanan_detik), lambda t: _menit(t.layanan_detik)),
    _k("Nilai survey", lambda t: "" if t.nilai is None else str(t.nilai), lambda t: t.nilai),
    _k("Prioritas", lambda t: "Ya" if t.prioritas else "Tidak", kanan=False),
    _k("Prioritas dicabut", lambda t: "Ya" if t.prioritas_dicabut else "Tidak", kanan=False),
]


def angka_prioritas(laporan: Laporan) -> list[tuple[str, str]]:
    """Angka operasional prioritas dipisah agar enam kartu utama tetap terbaca."""
    total = laporan.total
    return [
        ("Nomor prioritas", f"{total.prioritas:,}".replace(",", ".")),
        ("Prioritas dicabut", f"{total.prioritas_dicabut:,}".replace(",", ".")),
        ("Rata-rata tunggu prioritas", total.label_menunggu_prioritas),
    ]

JUDUL_TABEL = {
    "per_hari": "Per hari",
    "per_layanan": "Per layanan",
    "per_loket": "Per loket",
    "per_petugas": "Per petugas",
}
JUDUL_TABEL_PETUGAS_LAYANAN = "Petugas per layanan"
JUDUL_TABEL_RIWAYAT = "Riwayat pelayanan"


def angka_ringkasan(laporan: Laporan) -> list[tuple[str, str]]:
    """Enam angka besar di atas tabel, dalam urutan tampilnya."""
    t = laporan.total
    kepuasan = t.label_kepuasan
    return [
        (
            "Nomor ditangani" if laporan.nama_petugas else "Nomor terbit",
            f"{t.terbit:,}".replace(",", "."),
        ),
        ("Selesai dilayani", f"{t.selesai:,}".replace(",", ".")),
        ("Tidak hadir", f"{t.tidak_hadir:,}".replace(",", ".")),
        ("Rata-rata menunggu", t.label_menunggu),
        ("Rata-rata pelayanan", t.label_layanan),
        (f"Kepuasan ({t.jumlah_survey} survey)", kepuasan),
    ]
