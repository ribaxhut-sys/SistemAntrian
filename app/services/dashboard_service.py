"""
Dashboard operasional.

Dua sudut pandang, satu service:

* ``ringkasan(filter)`` — dashboard admin/supervisor (DASHBOARD_VIEW): seluruh
  cabang, dapat disaring menurut tanggal, jenis layanan, loket, dan petugas.
* ``ringkasan_petugas()`` — dashboard petugas loket (QUEUE_CALL): hanya
  loket dan nomor milik sesi yang sedang masuk.

Seluruh angka diambil dalam satu panggilan dan satu transaksi. Bila diambil
sepotong-sepotong, angka pada layar bisa saling tidak cocok — misalnya
jumlah "selesai" sudah bertambah sementara jumlah survey masih yang lama.

Angka dashboard dihitung di Python dari baris-baris pada satu tanggal,
dengan cara yang sama seperti ``ReportService``: hasilnya dijamin sama di
SQLite maupun PostgreSQL dan jumlah barisnya kecil (satu hari). Definisi
setiap metrik ada di ``docs/dashboard.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import BusinessRuleError
from app.core.logger import get_logger
from app.models import (
    AuditAction,
    AuditLog,
    Counter,
    Queue,
    QueueStatus,
    RecordStatus,
    SatisfactionSurvey,
    ServiceCategory,
    User,
    UserRole,
)
from app.repositories.queue_repository import STATUS_SIBUK, QueueRepository
from app.repositories.survey_repository import SurveyRepository
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission
from app.services.queue_service import BATAS_HADIR_PETUGAS_DETIK, LABEL_STATUS
from app.services.settings_service import SettingsService
from app.services.survey_service import SurveySummary
from app.utils.formatting import durasi_singkat

logger = get_logger("dashboard")

#: Status yang ditampilkan pada ringkasan, berurutan sesuai alur pelayanan.
#: Sengaja tidak memakai seluruh isi QueueStatus supaya urutannya bermakna
#: bagi pembaca, bukan sekadar urutan deklarasi enum.
STATUS_RINGKASAN: tuple[QueueStatus, ...] = (
    QueueStatus.WAITING,
    QueueStatus.CALLED,
    QueueStatus.SKIPPED,
    QueueStatus.SERVING,
    QueueStatus.PAUSED,
    QueueStatus.COMPLETED,
    QueueStatus.NO_SHOW,
    QueueStatus.CANCELLED,
)

#: Status yang berarti antrian sudah tidak akan dilayani lagi hari ini.
STATUS_SELESAI: tuple[QueueStatus, ...] = (
    QueueStatus.COMPLETED,
    QueueStatus.NO_SHOW,
    QueueStatus.CANCELLED,
)

#: "Sedang dilayani": sudah dipanggil dan masih dipegang loket.
STATUS_DILAYANI: tuple[QueueStatus, ...] = STATUS_SIBUK

#: "Batal atau dilewati": tidak berakhir (atau belum berakhir) dengan layanan.
STATUS_BATAL_LEWATI: tuple[QueueStatus, ...] = (
    QueueStatus.CANCELLED,
    QueueStatus.NO_SHOW,
    QueueStatus.SKIPPED,
)

#: Nomor yang masuk riwayat petugas.
STATUS_RIWAYAT: tuple[QueueStatus, ...] = (
    QueueStatus.COMPLETED,
    QueueStatus.NO_SHOW,
    QueueStatus.CANCELLED,
    QueueStatus.SKIPPED,
)

#: Keadaan loket pada papan dashboard admin.
LOKET_AKTIF = "AKTIF"
LOKET_ISTIRAHAT = "ISTIRAHAT"
LOKET_TIDAK_AKTIF = "TIDAK_AKTIF"

LABEL_LOKET: dict[str, str] = {
    LOKET_AKTIF: "Aktif",
    LOKET_ISTIRAHAT: "Istirahat",
    LOKET_TIDAK_AKTIF: "Tidak aktif",
}

#: Keadaan petugas pada dashboard petugas.
PETUGAS_AKTIF = "AKTIF"
PETUGAS_ISTIRAHAT = "ISTIRAHAT"
PETUGAS_LOKET_NONAKTIF = "LOKET_NONAKTIF"
PETUGAS_BELUM_ADA_LOKET = "BELUM_ADA_LOKET"

LABEL_PETUGAS: dict[str, str] = {
    PETUGAS_AKTIF: "Aktif",
    PETUGAS_ISTIRAHAT: "Istirahat",
    PETUGAS_LOKET_NONAKTIF: "Loket dinonaktifkan",
    PETUGAS_BELUM_ADA_LOKET: "Loket belum dipilih",
}

#: Aktivitas audit terakhir yang boleh dibaca dashboard admin.
BATAS_AKTIVITAS = 15
#: Nomor berikutnya dan riwayat yang ditampilkan pada dashboard petugas.
BATAS_BERIKUTNYA = 8
BATAS_RIWAYAT = 30


def _detik(awal: datetime | None, akhir: datetime | None) -> float | None:
    if awal is None or akhir is None:
        return None
    nilai = (akhir - awal).total_seconds()
    return nilai if nilai >= 0 else None


def _rata(nilai: list[float]) -> float | None:
    return sum(nilai) / len(nilai) if nilai else None


# =====================================================================
# Ringkasan harian (tidak tersaring; dipertahankan untuk pemanggil lama)
# =====================================================================


@dataclass(frozen=True)
class DashboardSummary:
    """Seluruh isi layar ringkasan harian dalam satu objek."""

    tanggal: date
    per_status: dict[QueueStatus, int]
    per_kategori: dict[str, int]
    rata_menunggu_detik: float | None
    rata_layanan_detik: float | None
    survey: SurveySummary

    @property
    def total(self) -> int:
        return sum(self.per_status.values())

    @property
    def belum_selesai(self) -> int:
        """Antrian yang masih akan dilayani hari ini."""
        return self.total - sum(self.per_status.get(s, 0) for s in STATUS_SELESAI)

    @property
    def label_rata_menunggu(self) -> str:
        return durasi_singkat(self.rata_menunggu_detik)

    @property
    def label_rata_layanan(self) -> str:
        return durasi_singkat(self.rata_layanan_detik)

    def label_status(self, status: QueueStatus) -> str:
        return LABEL_STATUS.get(status, status.value)

    @property
    def persen_kehadiran(self) -> float | None:
        """
        Porsi antrian yang benar-benar dilayani terhadap yang dipanggil.

        None bila belum ada satu pun antrian yang tuntas hari ini — nol
        persen dan "belum ada datanya" adalah dua hal yang berbeda.
        """
        tuntas = sum(self.per_status.get(s, 0) for s in STATUS_SELESAI)
        if tuntas == 0:
            return None
        return self.per_status.get(QueueStatus.COMPLETED, 0) / tuntas * 100


# =====================================================================
# Dashboard admin / supervisor
# =====================================================================


@dataclass(frozen=True)
class FilterDashboard:
    """
    Penyaring dashboard. None berarti "semua" (tanggal None = hari ini).

    Menyaring menurut loket atau petugas hanya mencakup nomor yang sudah
    dipanggil: nomor yang masih menunggu belum dimiliki loket maupun
    petugas mana pun.
    """

    tanggal: date | None = None
    category_id: int | None = None
    counter_id: int | None = None
    user_id: int | None = None


@dataclass(frozen=True)
class OpsiFilter:
    """Isi kotak pilihan saringan: (id, nama) untuk tiap dimensi."""

    layanan: list[tuple[int, str]]
    loket: list[tuple[int, str]]
    petugas: list[tuple[int, str]]


@dataclass(frozen=True)
class StatusLoket:
    """Keadaan sebuah loket beserta petugasnya, pada saat dashboard dibuka."""

    counter_id: int
    nama: str
    status: str
    #: None bila tidak ada petugas yang tanda hidupnya masih segar.
    petugas: str | None
    #: Nomor yang sedang dipegang loket saat ini (bukan menurut tanggal saringan).
    nomor_aktif: str | None
    #: Pada tanggal dan saringan yang dipilih.
    dipanggil: int
    selesai: int

    @property
    def label_status(self) -> str:
        return LABEL_LOKET.get(self.status, self.status)


@dataclass(frozen=True)
class AktivitasTerakhir:
    """Satu aktivitas audit tanpa isi `meta` (bisa memuat detail internal)."""

    waktu: datetime
    aksi: str
    pelaku: str


LABEL_PERAN: dict[UserRole, str] = {
    UserRole.CRO: "Petugas loket",
    UserRole.REGISTRATION: "Pendaftaran",
    UserRole.ADMIN: "Admin",
    UserRole.SUPERVISOR: "Supervisor",
}


@dataclass(frozen=True)
class BarisPetugas:
    """Pekerjaan satu petugas pada tanggal dan saringan dashboard."""

    user_id: int
    nama: str
    peran: str
    #: Nomor yang diterbitkan petugas pendaftaran (dari audit CREATE_QUEUE).
    diterbitkan: int
    dipanggil: int
    selesai: int
    tidak_hadir: int
    dilewati: int
    dibatalkan: int
    rata_layanan_detik: float | None
    survey_jumlah: int
    kepuasan: float | None

    @property
    def label_rata_layanan(self) -> str:
        return durasi_singkat(self.rata_layanan_detik)

    @property
    def label_kepuasan(self) -> str:
        return "—" if self.kepuasan is None else f"{self.kepuasan:.1f}".replace(".", ",")


@dataclass(frozen=True)
class DashboardOperasional:
    """Seluruh isi dashboard admin/supervisor dalam satu objek."""

    filter: FilterDashboard
    tanggal: date
    total: int
    menunggu: int
    dilayani: int
    selesai: int
    batal_lewati: int
    per_status: dict[QueueStatus, int]
    rata_menunggu_detik: float | None
    rata_layanan_detik: float | None
    per_layanan: dict[str, int]
    #: Jam (0-23) -> jumlah nomor terbit pada jam itu. Selalu 24 butir.
    per_jam: dict[int, int]
    loket: list[StatusLoket]
    survey: SurveySummary
    #: Pekerjaan setiap petugas; hanya untuk pembaca dashboard.
    per_petugas: list[BarisPetugas] = field(default_factory=list)
    diambil_pada: datetime = field(default_factory=clock.now)

    @property
    def label_rata_menunggu(self) -> str:
        return durasi_singkat(self.rata_menunggu_detik)

    @property
    def label_rata_layanan(self) -> str:
        return durasi_singkat(self.rata_layanan_detik)

    @property
    def jumlah_loket_aktif(self) -> int:
        return sum(1 for b in self.loket if b.status == LOKET_AKTIF)

    @property
    def jumlah_loket_istirahat(self) -> int:
        return sum(1 for b in self.loket if b.status == LOKET_ISTIRAHAT)

    @property
    def jumlah_loket_tidak_aktif(self) -> int:
        return sum(1 for b in self.loket if b.status == LOKET_TIDAK_AKTIF)


# =====================================================================
# Dashboard petugas
# =====================================================================


@dataclass(frozen=True)
class NomorAktif:
    """Nomor yang sedang dipegang loket petugas."""

    id: int
    nomor: str
    layanan: str
    status: QueueStatus
    dipanggil_pada: datetime | None
    dilayani_pada: datetime | None
    jumlah_panggilan: int

    @property
    def label_status(self) -> str:
        return LABEL_STATUS.get(self.status, self.status.value)


@dataclass(frozen=True)
class NomorBerikut:
    nomor: str
    layanan: str
    menunggu_detik: float


@dataclass(frozen=True)
class RiwayatPetugas:
    """Satu nomor yang sudah ditangani petugas hari ini."""

    nomor: str
    layanan: str
    loket: str
    status: QueueStatus
    waktu: datetime | None
    menunggu_detik: float | None
    layanan_detik: float | None

    @property
    def label_status(self) -> str:
        return LABEL_STATUS.get(self.status, self.status.value)


@dataclass(frozen=True)
class DashboardPetugas:
    """Keadaan kerja satu petugas hari ini: loketnya, nomornya, dan riwayatnya."""

    tanggal: date
    nama_petugas: str
    counter_id: int | None
    nama_loket: str | None
    status: str
    aktif: NomorAktif | None
    #: Seluruh nomor menunggu yang boleh dipanggil loket ini.
    sisa_antrian: int
    berikutnya: list[NomorBerikut]
    selesai: int
    tidak_hadir: int
    dilewati: int
    dibatalkan: int
    rata_layanan_detik: float | None
    riwayat: list[RiwayatPetugas]
    #: Detik sejak nomor aktif dipanggil; None bila tidak ada.
    sejak_dipanggil_detik: float | None
    diambil_pada: datetime = field(default_factory=clock.now)

    @property
    def label_status(self) -> str:
        return LABEL_PETUGAS.get(self.status, self.status)

    @property
    def label_rata_layanan(self) -> str:
        return durasi_singkat(self.rata_layanan_detik)

    @property
    def peringatan(self) -> str | None:
        """Satu kalimat yang perlu dibaca petugas sebelum bekerja; None bila aman."""
        if self.status == PETUGAS_BELUM_ADA_LOKET:
            return "Loket belum dipilih. Buka menu Pelayanan lalu pilih loket Anda."
        if self.status == PETUGAS_LOKET_NONAKTIF:
            return "Loket Anda dinonaktifkan administrator. Hubungi administrator."
        if self.status == PETUGAS_ISTIRAHAT:
            return (
                "Loket sedang istirahat. Akhiri istirahat di menu Pelayanan "
                "untuk memanggil."
            )
        if self.aktif is None and self.sisa_antrian == 0:
            return "Tidak ada antrian yang menunggu untuk loket Anda."
        return None


@dataclass(frozen=True)
class NomorTerbit:
    nomor: str
    layanan: str
    waktu: datetime
    status: QueueStatus

    @property
    def label_status(self) -> str:
        return LABEL_STATUS.get(self.status, self.status.value)


@dataclass(frozen=True)
class DashboardPendaftaran:
    """Nomor yang diterbitkan satu petugas pendaftaran pada satu tanggal."""

    tanggal: date
    nama_petugas: str
    total: int
    per_layanan: dict[str, int]
    terakhir: list[NomorTerbit]
    diambil_pada: datetime = field(default_factory=clock.now)


class DashboardService:
    """Ringkasan operasional harian."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    # -----------------------------------------------------------------
    # Ringkasan harian lama
    # -----------------------------------------------------------------

    def ringkasan_hari_ini(self) -> DashboardSummary:
        """Seluruh angka hari ini, diambil sekali jalan."""
        sesi = self.auth.require_permission(Permission.DASHBOARD_VIEW)
        hari = clock.today()

        with session_scope() as session:
            antrian = QueueRepository(session)
            survey = SurveyRepository(session)

            per_status = antrian.hitung_per_status(sesi.branch_id, hari)
            per_kategori = antrian.hitung_per_kategori(sesi.branch_id, hari)
            rata_menunggu, rata_layanan = antrian.rata_rata_durasi(sesi.branch_id, hari)

            distribusi = survey.hitung_per_rating(sesi.branch_id, sejak=hari, sampai=hari)
            ringkasan_survey = SurveySummary(
                jumlah=sum(distribusi.values()),
                rata_rata=survey.rata_rata(sesi.branch_id, sejak=hari, sampai=hari),
                distribusi=distribusi,
            )

        return DashboardSummary(
            tanggal=hari,
            per_status={s: per_status.get(s, 0) for s in STATUS_RINGKASAN},
            per_kategori=per_kategori,
            rata_menunggu_detik=rata_menunggu,
            rata_layanan_detik=rata_layanan,
            survey=ringkasan_survey,
        )

    # -----------------------------------------------------------------
    # Dashboard admin / supervisor
    # -----------------------------------------------------------------

    def opsi_filter(self) -> OpsiFilter:
        """Isi kotak pilihan saringan. Hanya nama dan id, tanpa data pribadi."""
        sesi = self.auth.require_permission(Permission.DASHBOARD_VIEW)
        with session_scope() as session:
            layanan = session.execute(
                sa.select(ServiceCategory.id, ServiceCategory.name)
                .where(
                    ServiceCategory.branch_id == sesi.branch_id,
                    ~ServiceCategory.id.in_(self._induk_layanan()),
                )
                .order_by(ServiceCategory.prefix, ServiceCategory.name)
            ).all()
            loket = session.execute(
                sa.select(Counter.id, Counter.name)
                .where(Counter.branch_id == sesi.branch_id)
                .order_by(Counter.code)
            ).all()
            petugas = session.execute(
                sa.select(User.id, User.full_name)
                .where(User.branch_id == sesi.branch_id, User.role == UserRole.CRO)
                .order_by(User.full_name)
            ).all()
        return OpsiFilter(
            layanan=[(i, n) for i, n in layanan],
            loket=[(i, n) for i, n in loket],
            petugas=[(i, n) for i, n in petugas],
        )

    @staticmethod
    def _induk_layanan():
        """Subquery id jenis layanan yang menjadi kelompok (punya anak)."""
        return sa.select(ServiceCategory.parent_id).where(
            ServiceCategory.parent_id.is_not(None)
        )

    def ringkasan(self, saringan: FilterDashboard | None = None) -> DashboardOperasional:
        """
        Dashboard admin/supervisor untuk satu tanggal dan saringan.

        Satu transaksi: antrian (satu query baris), survey (satu query),
        loket dan petugasnya (satu query dengan join), serta nomor aktif
        per loket. Tidak ada query per baris.
        """
        sesi = self.auth.require_permission(Permission.DASHBOARD_VIEW)
        saringan = saringan or FilterDashboard()
        sekarang = clock.now()
        hari = saringan.tanggal or sekarang.date()

        kondisi = [Queue.branch_id == sesi.branch_id, Queue.queue_date == hari]
        if saringan.category_id is not None:
            kondisi.append(Queue.category_id == saringan.category_id)
        if saringan.counter_id is not None:
            kondisi.append(Queue.counter_id == saringan.counter_id)
        if saringan.user_id is not None:
            kondisi.append(Queue.served_by_user_id == saringan.user_id)

        awal_hari = datetime.combine(hari, datetime.min.time())
        kondisi_survey = [
            SatisfactionSurvey.branch_id == sesi.branch_id,
            SatisfactionSurvey.submitted_at >= awal_hari,
            SatisfactionSurvey.submitted_at < awal_hari + timedelta(days=1),
        ]
        if saringan.category_id is not None:
            kondisi_survey.append(SatisfactionSurvey.category_id == saringan.category_id)
        if saringan.counter_id is not None:
            kondisi_survey.append(SatisfactionSurvey.counter_id == saringan.counter_id)
        if saringan.user_id is not None:
            kondisi_survey.append(SatisfactionSurvey.officer_id == saringan.user_id)

        with session_scope() as session:
            baris = session.execute(
                sa.select(
                    Queue.status,
                    Queue.category_id,
                    Queue.counter_id,
                    Queue.created_at,
                    Queue.called_at,
                    Queue.serving_at,
                    Queue.completed_at,
                    Queue.served_by_user_id,
                ).where(*kondisi)
            ).all()
            kategori = session.execute(
                sa.select(ServiceCategory.id, ServiceCategory.name)
                .where(
                    ServiceCategory.branch_id == sesi.branch_id,
                    ~ServiceCategory.id.in_(self._induk_layanan()),
                )
                .order_by(ServiceCategory.prefix, ServiceCategory.name)
            ).all()
            loket_baris = session.execute(
                sa.select(
                    Counter.id,
                    Counter.name,
                    Counter.status,
                    Counter.on_break,
                    Counter.petugas_user_id,
                    Counter.petugas_terlihat_pada,
                    User.full_name,
                )
                .outerjoin(User, User.id == Counter.petugas_user_id)
                .where(Counter.branch_id == sesi.branch_id)
                .order_by(Counter.code)
            ).all()
            nomor_aktif = dict(
                session.execute(
                    sa.select(Queue.counter_id, Queue.queue_number).where(
                        Queue.branch_id == sesi.branch_id,
                        Queue.queue_date == sekarang.date(),
                        Queue.status.in_(STATUS_SIBUK),
                        Queue.counter_id.is_not(None),
                    )
                ).all()
            )
            survey_baris = session.execute(
                sa.select(SatisfactionSurvey.rating, SatisfactionSurvey.officer_id).where(
                    *kondisi_survey
                )
            ).all()
            nilai = [r for r, _ in survey_baris]

            # Nomor yang diterbitkan per petugas pendaftaran. Penerbitan
            # tidak punya loket, sehingga saringan loket meniadakannya.
            diterbitkan: dict[int, int] = {}
            if saringan.counter_id is None:
                kondisi_terbit = [
                    AuditLog.action == AuditAction.CREATE_QUEUE.value,
                    AuditLog.entity_type == "queue",
                    AuditLog.user_id.is_not(None),
                    Queue.branch_id == sesi.branch_id,
                    Queue.queue_date == hari,
                ]
                if saringan.category_id is not None:
                    kondisi_terbit.append(Queue.category_id == saringan.category_id)
                if saringan.user_id is not None:
                    kondisi_terbit.append(AuditLog.user_id == saringan.user_id)
                diterbitkan = dict(
                    session.execute(
                        sa.select(AuditLog.user_id, sa.func.count())
                        .join(Queue, Queue.id == AuditLog.entity_id)
                        .where(*kondisi_terbit)
                        .group_by(AuditLog.user_id)
                    ).all()
                )

            id_petugas = {b[7] for b in baris if b[7] is not None}
            id_petugas |= set(diterbitkan)
            id_petugas |= {o for _, o in survey_baris if o is not None}
            identitas = {
                uid: (nama, peran)
                for uid, nama, peran in session.execute(
                    sa.select(User.id, User.full_name, User.role).where(
                        User.id.in_(id_petugas or {-1})
                    )
                ).all()
            }

        per_status = {s: 0 for s in STATUS_RINGKASAN}
        per_jam = {jam: 0 for jam in range(24)}
        per_kategori_id: dict[int, int] = {}
        per_loket_dipanggil: dict[int, int] = {}
        per_loket_selesai: dict[int, int] = {}
        menunggu: list[float] = []
        layanan: list[float] = []

        kerja: dict[int, dict] = {}
        for (status, kategori_id, loket_id, dibuat, dipanggil, mulai, selesai,
             petugas_id) in baris:
            per_status[status] = per_status.get(status, 0) + 1
            per_kategori_id[kategori_id] = per_kategori_id.get(kategori_id, 0) + 1
            if dibuat is not None:
                per_jam[dibuat.hour] += 1
            tunggu = _detik(dibuat, dipanggil)
            if tunggu is not None:
                menunggu.append(tunggu)
            if status is QueueStatus.COMPLETED:
                lama = _detik(mulai, selesai)
                if lama is not None:
                    layanan.append(lama)
            if petugas_id is not None:
                k = kerja.setdefault(
                    petugas_id,
                    {"dipanggil": 0, "selesai": 0, "tidak_hadir": 0, "dilewati": 0,
                     "dibatalkan": 0, "lama": []},
                )
                if dipanggil is not None:
                    k["dipanggil"] += 1
                if status is QueueStatus.COMPLETED:
                    k["selesai"] += 1
                    lama_petugas = _detik(mulai, selesai)
                    if lama_petugas is not None:
                        k["lama"].append(lama_petugas)
                elif status is QueueStatus.NO_SHOW:
                    k["tidak_hadir"] += 1
                elif status is QueueStatus.SKIPPED:
                    k["dilewati"] += 1
                elif status is QueueStatus.CANCELLED:
                    k["dibatalkan"] += 1
            if loket_id is not None:
                if dipanggil is not None:
                    per_loket_dipanggil[loket_id] = per_loket_dipanggil.get(loket_id, 0) + 1
                if status is QueueStatus.COMPLETED:
                    per_loket_selesai[loket_id] = per_loket_selesai.get(loket_id, 0) + 1

        # Jenis layanan tanpa nomor tetap tampil dengan nol, kecuali bila
        # sedang menyaring satu layanan: kolom lain hanya akan menjadi noise.
        per_layanan = {
            nama: per_kategori_id.get(kategori_id, 0)
            for kategori_id, nama in kategori
            if saringan.category_id in (None, kategori_id)
        }

        papan: list[StatusLoket] = []
        for loket_id, nama, status, istirahat, petugas_id, terlihat, nama_petugas in loket_baris:
            if saringan.counter_id is not None and loket_id != saringan.counter_id:
                continue
            if saringan.user_id is not None and not (
                petugas_id == saringan.user_id or loket_id in per_loket_dipanggil
            ):
                continue
            hadir = (
                petugas_id is not None
                and terlihat is not None
                and (sekarang - terlihat).total_seconds() <= BATAS_HADIR_PETUGAS_DETIK
            )
            if status is not RecordStatus.ACTIVE or not hadir:
                keadaan = LOKET_TIDAK_AKTIF
            elif istirahat:
                keadaan = LOKET_ISTIRAHAT
            else:
                keadaan = LOKET_AKTIF
            papan.append(
                StatusLoket(
                    counter_id=loket_id,
                    nama=nama,
                    status=keadaan,
                    petugas=nama_petugas if hadir else None,
                    nomor_aktif=nomor_aktif.get(loket_id),
                    dipanggil=per_loket_dipanggil.get(loket_id, 0),
                    selesai=per_loket_selesai.get(loket_id, 0),
                )
            )

        distribusi = {n: 0 for n in range(1, 6)}
        for rating in nilai:
            distribusi[rating] = distribusi.get(rating, 0) + 1

        nilai_petugas: dict[int, list[float]] = {}
        for rating, officer in survey_baris:
            if officer is not None:
                nilai_petugas.setdefault(officer, []).append(float(rating))
        rincian: list[BarisPetugas] = []
        for uid in set(kerja) | set(diterbitkan) | set(nilai_petugas):
            nama, peran = identitas.get(uid, ("—", None))
            k = kerja.get(uid, {})
            skor = nilai_petugas.get(uid, [])
            rincian.append(
                BarisPetugas(
                    user_id=uid,
                    nama=nama,
                    peran=LABEL_PERAN.get(peran, "—") if peran is not None else "—",
                    diterbitkan=diterbitkan.get(uid, 0),
                    dipanggil=k.get("dipanggil", 0),
                    selesai=k.get("selesai", 0),
                    tidak_hadir=k.get("tidak_hadir", 0),
                    dilewati=k.get("dilewati", 0),
                    dibatalkan=k.get("dibatalkan", 0),
                    rata_layanan_detik=_rata(k.get("lama", [])),
                    survey_jumlah=len(skor),
                    kepuasan=_rata(skor),
                )
            )
        rincian.sort(key=lambda b: (-(b.selesai + b.diterbitkan), b.nama.lower()))

        return DashboardOperasional(
            filter=saringan,
            tanggal=hari,
            total=len(baris),
            menunggu=per_status[QueueStatus.WAITING],
            dilayani=sum(per_status[s] for s in STATUS_DILAYANI),
            selesai=per_status[QueueStatus.COMPLETED],
            batal_lewati=sum(per_status[s] for s in STATUS_BATAL_LEWATI),
            per_status=per_status,
            rata_menunggu_detik=_rata(menunggu),
            rata_layanan_detik=_rata(layanan),
            per_layanan=per_layanan,
            per_jam=per_jam,
            loket=papan,
            survey=SurveySummary(
                jumlah=len(nilai),
                rata_rata=_rata([float(n) for n in nilai]),
                distribusi=distribusi,
            ),
            per_petugas=rincian,
            diambil_pada=sekarang,
        )

    def aktivitas_terakhir(self, batas: int = BATAS_AKTIVITAS) -> list[AktivitasTerakhir]:
        """
        Audit log terbaru, hanya untuk pemegang CONFIG_MANAGE (admin).

        Isi `meta` sengaja tidak dibawa: audit menyimpan rincian internal
        yang tidak perlu berada di layar ringkasan.
        """
        self.auth.require_permission(Permission.CONFIG_MANAGE)
        return [
            AktivitasTerakhir(waktu=e.created_at, aksi=e.action, pelaku=e.pelaku)
            for e in audit_service.list_terakhir(batas=max(1, min(batas, 100)))
        ]

    # -----------------------------------------------------------------
    # Dashboard petugas
    # -----------------------------------------------------------------

    def ringkasan_petugas(self, tanggal: date | None = None) -> DashboardPetugas:
        """
        Keadaan kerja petugas yang sedang masuk — dan hanya dia.

        Tidak menerima id petugas atau loket: ruang lingkupnya ditetapkan
        dari sesi dan loket bawaan akunnya di database, sehingga petugas
        tidak dapat meminta data milik rekannya walau memanggil service
        langsung.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)
        if sesi.user_id is None:
            raise BusinessRuleError("Sesi ini tidak mewakili petugas tertentu.")
        sekarang = clock.now()
        hari_ini = sekarang.date()
        # Pekerjaan hari-hari lalu boleh dibuka; bagian "saat ini" (nomor
        # aktif dan antrean) selalu hari ini.
        hari = tanggal or hari_ini

        with session_scope() as session:
            petugas = session.get(User, sesi.user_id)
            if petugas is None:
                raise BusinessRuleError("Akun petugas tidak ditemukan.")
            loket = (
                session.get(Counter, petugas.default_counter_id)
                if petugas.default_counter_id is not None
                else None
            )
            if loket is not None and loket.branch_id != sesi.branch_id:
                loket = None

            if loket is None:
                status = PETUGAS_BELUM_ADA_LOKET
            elif loket.status is not RecordStatus.ACTIVE:
                status = PETUGAS_LOKET_NONAKTIF
            elif loket.on_break:
                status = PETUGAS_ISTIRAHAT
            else:
                status = PETUGAS_AKTIF

            repo = QueueRepository(session)
            aktif: NomorAktif | None = None
            sisa = 0
            berikutnya: list[NomorBerikut] = []
            sejak = None
            if loket is not None:
                sedang = repo.sedang_ditangani_loket(loket.id, hari_ini)
                if sedang is not None:
                    aktif = NomorAktif(
                        id=sedang.id,
                        nomor=sedang.queue_number,
                        layanan=sedang.category.name,
                        status=sedang.status,
                        dipanggil_pada=sedang.called_at,
                        dilayani_pada=sedang.serving_at,
                        jumlah_panggilan=repo.jumlah_pemanggilan(sedang.id),
                    )
                    sejak = _detik(sedang.called_at, sekarang)

                # Daftar kosong berarti loket boleh memanggil semua layanan.
                diizinkan = [k.id for k in loket.categories] or None
                menunggu_baris = repo.list_menunggu_berurutan(
                    sesi.branch_id,
                    hari_ini,
                    rasio=max(
                        0,
                        SettingsService(self.auth).get_int(
                            "queue.rasio_prioritas", 3
                        ),
                    ),
                    category_ids=diizinkan,
                )
                sisa = len(menunggu_baris)
                berikutnya = [
                    NomorBerikut(
                        nomor=r.queue_number,
                        layanan=r.category.name,
                        menunggu_detik=max(0.0, (sekarang - r.created_at).total_seconds()),
                    )
                    for r in menunggu_baris[:BATAS_BERIKUTNYA]
                ]

            milik = session.execute(
                sa.select(
                    Queue.queue_number,
                    ServiceCategory.name,
                    Counter.name,
                    Queue.status,
                    Queue.created_at,
                    Queue.called_at,
                    Queue.serving_at,
                    Queue.completed_at,
                    Queue.updated_at,
                )
                .join(ServiceCategory, ServiceCategory.id == Queue.category_id)
                .outerjoin(Counter, Counter.id == Queue.counter_id)
                .where(
                    Queue.branch_id == sesi.branch_id,
                    Queue.queue_date == hari,
                    Queue.served_by_user_id == sesi.user_id,
                    Queue.status.in_(STATUS_RIWAYAT),
                )
            ).all()
            nama_petugas = petugas.full_name
            nama_loket = loket.name if loket is not None else None
            counter_id = loket.id if loket is not None else None

        hitung = {s: 0 for s in STATUS_RIWAYAT}
        lama: list[float] = []
        riwayat: list[RiwayatPetugas] = []
        for nomor, layanan, nama, st, dibuat, dipanggil, mulai, selesai, diubah in milik:
            hitung[st] += 1
            durasi = _detik(mulai, selesai) if st is QueueStatus.COMPLETED else None
            if durasi is not None:
                lama.append(durasi)
            riwayat.append(
                RiwayatPetugas(
                    nomor=nomor,
                    layanan=layanan,
                    loket=nama or "",
                    status=st,
                    waktu=selesai or diubah,
                    menunggu_detik=_detik(dibuat, dipanggil),
                    layanan_detik=durasi,
                )
            )
        riwayat.sort(key=lambda r: r.waktu or datetime.min, reverse=True)

        return DashboardPetugas(
            tanggal=hari,
            nama_petugas=nama_petugas,
            counter_id=counter_id,
            nama_loket=nama_loket,
            status=status,
            aktif=aktif,
            sisa_antrian=sisa,
            berikutnya=berikutnya,
            selesai=hitung[QueueStatus.COMPLETED],
            tidak_hadir=hitung[QueueStatus.NO_SHOW],
            dilewati=hitung[QueueStatus.SKIPPED],
            dibatalkan=hitung[QueueStatus.CANCELLED],
            rata_layanan_detik=_rata(lama),
            riwayat=riwayat[:BATAS_RIWAYAT],
            sejak_dipanggil_detik=sejak,
            diambil_pada=sekarang,
        )

    # -----------------------------------------------------------------
    # Dashboard petugas pendaftaran
    # -----------------------------------------------------------------

    def ringkasan_pendaftaran(self, tanggal: date | None = None) -> DashboardPendaftaran:
        """
        Nomor yang diterbitkan petugas pendaftaran yang sedang masuk.

        Seperti `ringkasan_petugas`, cakupannya dari sesi: tanpa parameter
        id petugas. Sumbernya audit CREATE_QUEUE milik sesi ini.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CREATE)
        if sesi.user_id is None:
            raise BusinessRuleError("Sesi ini tidak mewakili petugas tertentu.")
        hari = tanggal or clock.today()

        with session_scope() as session:
            baris = session.execute(
                sa.select(
                    Queue.queue_number,
                    ServiceCategory.name,
                    AuditLog.created_at,
                    Queue.status,
                )
                .join(Queue, Queue.id == AuditLog.entity_id)
                .join(ServiceCategory, ServiceCategory.id == Queue.category_id)
                .where(
                    AuditLog.action == AuditAction.CREATE_QUEUE.value,
                    AuditLog.entity_type == "queue",
                    AuditLog.user_id == sesi.user_id,
                    Queue.branch_id == sesi.branch_id,
                    Queue.queue_date == hari,
                )
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            ).all()

        per_layanan: dict[str, int] = {}
        for _, layanan, _, _ in baris:
            per_layanan[layanan] = per_layanan.get(layanan, 0) + 1
        return DashboardPendaftaran(
            tanggal=hari,
            nama_petugas=sesi.full_name,
            total=len(baris),
            per_layanan=per_layanan,
            terakhir=[
                NomorTerbit(nomor=n, layanan=lay, waktu=w, status=st)
                for n, lay, w, st in baris[:BATAS_RIWAYAT]
            ],
        )
