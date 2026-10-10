"""
Ringkasan harian untuk supervisor.

Seluruh angka diambil dalam satu panggilan dan satu transaksi. Bila diambil
sepotong-sepotong, angka pada layar bisa saling tidak cocok — misalnya
jumlah "selesai" sudah bertambah sementara jumlah survey masih yang lama.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core import clock
from app.core.database import session_scope
from app.core.logger import get_logger
from app.models import QueueStatus
from app.repositories.queue_repository import QueueRepository
from app.repositories.survey_repository import SurveyRepository
from app.services.auth_service import AuthService
from app.services.permissions import Permission
from app.services.queue_service import LABEL_STATUS
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


class DashboardService:
    """Ringkasan operasional harian."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

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
