"""
Survey kepuasan pelayanan.

Survey TIDAK pernah mengubah status antrian. Antrian yang sudah COMPLETED
tetap COMPLETED walaupun ratingnya 1 — rating mengukur kualitas pelayanan,
bukan menentukan selesai atau tidaknya pelayanan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.core import clock
from app.core.database import session_scope
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import (
    RATING_LABELS,
    AuditAction,
    QueueStatus,
    SatisfactionSurvey,
)
from app.repositories.queue_repository import QueueRepository
from app.repositories.survey_repository import SurveyRepository
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission
from app.services.queue_service import QueueInfo, _as_info

logger = get_logger("survey")

#: Batas nilai rating yang diterima. Sama dengan CheckConstraint pada tabel,
#: tetapi diperiksa lebih dahulu agar petugas menerima kalimat yang jelas,
#: bukan pesan kegagalan constraint dari SQLite.
RATING_MIN = 1
RATING_MAX = 5

#: Panjang maksimum masukan bebas. Kolomnya bertipe Text sehingga tidak
#: membatasi apa pun; batas ini mencegah satu baris menelan berkas besar
#: yang tidak sengaja tertempel.
PANJANG_FEEDBACK_MAKSIMUM = 1000


@dataclass(frozen=True)
class SurveyInfo:
    """Data survey yang aman dibawa ke UI, lepas dari session database."""

    id: int
    queue_id: int
    queue_number: str
    rating: int
    feedback: str | None
    counter_name: str | None
    category_name: str | None
    submitted_at: datetime

    @property
    def rating_label(self) -> str:
        return RATING_LABELS.get(self.rating, "-")


@dataclass(frozen=True)
class SurveySummary:
    """
    Ringkasan kepuasan untuk satu rentang waktu.

    Disusun sebagai satu objek agar layar ringkasan mengambil seluruh isinya
    dalam sekali panggil, bukan beberapa panggilan yang bisa saling tidak
    cocok ketika ada survey baru masuk di tengah penyegaran.
    """

    jumlah: int
    rata_rata: float | None
    distribusi: dict[int, int]

    @property
    def label_rata_rata(self) -> str:
        return "-" if self.rata_rata is None else f"{self.rata_rata:.2f}"

    def persentase(self, rating: int) -> float:
        """Porsi sebuah rating terhadap seluruh survey, dalam persen."""
        if self.jumlah == 0:
            return 0.0
        return self.distribusi.get(rating, 0) / self.jumlah * 100


def _as_survey_info(row: SatisfactionSurvey) -> SurveyInfo:
    return SurveyInfo(
        id=row.id,
        queue_id=row.queue_id,
        queue_number=row.queue.queue_number,
        rating=row.rating,
        feedback=row.feedback,
        counter_name=row.counter.name if row.counter else None,
        category_name=row.category.name if row.category else None,
        submitted_at=row.submitted_at,
    )


class SurveyService:
    """Pengisian dan pembacaan survey kepuasan."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    # =================================================================
    # Pengisian
    # =================================================================

    def submit(
        self, queue_id: int, rating: int, feedback: str | None = None
    ) -> SurveyInfo:
        """
        Simpan penilaian pengunjung atas satu antrian.

        Antrian wajib sudah COMPLETED: yang dinilai adalah pelayanan yang
        benar-benar diterima. Antrian yang dibatalkan atau tidak hadir tidak
        pernah dilayani sehingga tidak ada yang bisa dinilai.

        Satu antrian hanya boleh dinilai sekali. Aturan ini juga dijaga oleh
        constraint UNIQUE pada kolom queue_id, tetapi diperiksa di sini agar
        pesannya bisa dibaca petugas.
        """
        sesi = self.auth.require_permission(Permission.SURVEY_SUBMIT)

        if not isinstance(rating, int) or isinstance(rating, bool):
            raise ValidationError("Nilai kepuasan harus berupa angka.")
        if not RATING_MIN <= rating <= RATING_MAX:
            raise ValidationError(
                f"Nilai kepuasan harus antara {RATING_MIN} sampai {RATING_MAX}."
            )

        bersih = (feedback or "").strip() or None
        if bersih is not None and len(bersih) > PANJANG_FEEDBACK_MAKSIMUM:
            raise ValidationError(
                f"Masukan terlalu panjang, maksimum {PANJANG_FEEDBACK_MAKSIMUM} karakter."
            )

        with session_scope() as session:
            antrian = QueueRepository(session).get_by_id(queue_id)
            if antrian is None or antrian.branch_id != sesi.branch_id:
                raise NotFoundError("Antrian tidak ditemukan.")

            if antrian.status is not QueueStatus.COMPLETED:
                raise BusinessRuleError(
                    f"Antrian {antrian.queue_number} belum selesai dilayani "
                    "sehingga belum dapat dinilai."
                )
            if antrian.counter_id is None or antrian.served_by_user_id is None:
                raise BusinessRuleError(
                    f"Antrian {antrian.queue_number} tidak memiliki catatan loket "
                    "maupun petugas, sehingga penilaiannya tidak dapat disimpan."
                )

            repo = SurveyRepository(session)
            if repo.get_by_queue(queue_id) is not None:
                raise BusinessRuleError(
                    f"Antrian {antrian.queue_number} sudah pernah dinilai."
                )

            # Kolom cabang/loket/layanan/petugas disalin ke survey supaya
            # laporan kepuasan tetap dapat difilter walau data master antrian
            # berubah di kemudian hari.
            survey = repo.simpan(
                SatisfactionSurvey(
                    queue_id=antrian.id,
                    branch_id=antrian.branch_id,
                    counter_id=antrian.counter_id,
                    category_id=antrian.category_id,
                    officer_id=antrian.served_by_user_id,
                    rating=rating,
                    feedback=bersih,
                    submitted_at=clock.now(),
                )
            )

            audit_service.record(
                session,
                AuditAction.SUBMIT_SURVEY,
                user_id=sesi.user_id,
                entity_type="satisfaction_survey",
                entity_id=survey.id,
                nomor=antrian.queue_number,
                rating=rating,
            )
            logger.info(
                "Survey antrian %s tersimpan dengan rating %d",
                antrian.queue_number,
                rating,
            )
            return _as_survey_info(survey)

    # =================================================================
    # Pembacaan
    # =================================================================

    def list_pending(self) -> list[QueueInfo]:
        """
        Antrian hari ini yang sudah selesai tetapi belum dinilai.

        Memakai hak SURVEY_SUBMIT, bukan QUEUE_VIEW. Layar kios menghadap
        publik dan akunnya sengaja tidak diberi kemampuan melihat daftar
        antrian secara penuh — yang boleh dilihatnya hanya nomor-nomor yang
        memang sedang menunggu penilaian.
        """
        sesi = self.auth.require_permission(Permission.SURVEY_SUBMIT)
        with session_scope() as session:
            rows = SurveyRepository(session).list_belum_disurvey(
                sesi.branch_id, clock.today()
            )
            return [_as_info(r) for r in rows]

    def get_by_queue(self, queue_id: int) -> SurveyInfo | None:
        """Penilaian sebuah antrian, bila sudah ada."""
        self.auth.require_permission(Permission.SURVEY_SUBMIT)
        with session_scope() as session:
            row = SurveyRepository(session).get_by_queue(queue_id)
            return None if row is None else _as_survey_info(row)

    def ringkasan(
        self, *, sejak: date | None = None, sampai: date | None = None
    ) -> SurveySummary:
        """Ringkasan kepuasan untuk sebuah rentang tanggal."""
        sesi = self.auth.require_permission(Permission.SURVEY_VIEW)
        with session_scope() as session:
            repo = SurveyRepository(session)
            distribusi = repo.hitung_per_rating(
                sesi.branch_id, sejak=sejak, sampai=sampai
            )
            return SurveySummary(
                jumlah=sum(distribusi.values()),
                rata_rata=repo.rata_rata(sesi.branch_id, sejak=sejak, sampai=sampai),
                distribusi=distribusi,
            )

    def list_terakhir(self, batas: int = 20) -> list[SurveyInfo]:
        """Survey terbaru, untuk ditinjau supervisor."""
        sesi = self.auth.require_permission(Permission.SURVEY_VIEW)
        with session_scope() as session:
            rows = SurveyRepository(session).list_terakhir(sesi.branch_id, batas=batas)
            return [_as_survey_info(r) for r in rows]
