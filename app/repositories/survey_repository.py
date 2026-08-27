"""
Akses data survey kepuasan.

Agregasi rating dikerjakan di SQL, bukan dengan menarik seluruh baris ke
Python. Jumlah survey bertambah terus setiap hari, sedangkan yang dibutuhkan
layar ringkasan hanya beberapa angka.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session, selectinload

from app.models import Queue, QueueStatus, SatisfactionSurvey


class SurveyRepository:
    """Pembacaan dan penyimpanan survey kepuasan."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -----------------------------------------------------------------
    # Pembacaan
    # -----------------------------------------------------------------

    def get_by_id(self, survey_id: int) -> SatisfactionSurvey | None:
        return self.session.get(SatisfactionSurvey, survey_id)

    def get_by_queue(self, queue_id: int) -> SatisfactionSurvey | None:
        return self.session.scalar(
            sa.select(SatisfactionSurvey).where(
                SatisfactionSurvey.queue_id == queue_id
            )
        )

    def list_belum_disurvey(self, branch_id: int, tanggal: date) -> list[Queue]:
        """
        Antrian yang sudah selesai dilayani tetapi belum dinilai.

        Hanya yang berstatus COMPLETED. Antrian yang dibatalkan atau tidak
        hadir tidak pernah menerima pelayanan, sehingga tidak ada yang bisa
        dinilai pengunjung.
        """
        sudah_dinilai = sa.select(SatisfactionSurvey.queue_id)
        return list(
            self.session.scalars(
                sa.select(Queue)
                .options(
                    selectinload(Queue.category),
                    selectinload(Queue.counter),
                    selectinload(Queue.served_by),
                )
                .where(
                    Queue.branch_id == branch_id,
                    Queue.queue_date == tanggal,
                    Queue.status == QueueStatus.COMPLETED,
                    Queue.id.not_in(sudah_dinilai),
                )
                .order_by(Queue.completed_at.desc(), Queue.id.desc())
            )
        )

    def hitung_per_rating(
        self,
        branch_id: int,
        *,
        sejak: date | None = None,
        sampai: date | None = None,
    ) -> dict[int, int]:
        """Jumlah survey per nilai rating, selalu memuat kunci 1 sampai 5."""
        stmt = (
            sa.select(SatisfactionSurvey.rating, sa.func.count())
            .where(SatisfactionSurvey.branch_id == branch_id)
            .group_by(SatisfactionSurvey.rating)
        )
        stmt = self._batasi_tanggal(stmt, sejak, sampai)

        hasil = {nilai: 0 for nilai in range(1, 6)}
        for rating, jumlah in self.session.execute(stmt).all():
            hasil[rating] = jumlah
        return hasil

    def rata_rata(
        self,
        branch_id: int,
        *,
        sejak: date | None = None,
        sampai: date | None = None,
    ) -> float | None:
        """Rata-rata rating; None bila belum ada satu pun survey."""
        stmt = sa.select(sa.func.avg(SatisfactionSurvey.rating)).where(
            SatisfactionSurvey.branch_id == branch_id
        )
        nilai = self.session.scalar(self._batasi_tanggal(stmt, sejak, sampai))
        return None if nilai is None else float(nilai)

    def list_terakhir(
        self, branch_id: int, *, batas: int = 20
    ) -> list[SatisfactionSurvey]:
        return list(
            self.session.scalars(
                sa.select(SatisfactionSurvey)
                .options(
                    selectinload(SatisfactionSurvey.queue),
                    selectinload(SatisfactionSurvey.category),
                    selectinload(SatisfactionSurvey.counter),
                )
                .where(SatisfactionSurvey.branch_id == branch_id)
                .order_by(SatisfactionSurvey.submitted_at.desc())
                .limit(batas)
            )
        )

    # -----------------------------------------------------------------
    # Penyimpanan
    # -----------------------------------------------------------------

    def simpan(self, survey: SatisfactionSurvey) -> SatisfactionSurvey:
        self.session.add(survey)
        self.session.flush()
        return survey

    # -----------------------------------------------------------------

    @staticmethod
    def _batasi_tanggal(stmt, sejak: date | None, sampai: date | None):
        """
        Batasi rentang waktu survey.

        `sampai` bersifat inklusif: batasnya dinaikkan ke awal hari
        berikutnya, karena `submitted_at` menyimpan jam sehingga
        perbandingan `<= tanggal` akan membuang survey yang masuk pada
        hari itu juga.
        """
        if sejak is not None:
            stmt = stmt.where(SatisfactionSurvey.submitted_at >= _awal_hari(sejak))
        if sampai is not None:
            stmt = stmt.where(SatisfactionSurvey.submitted_at < _awal_hari_berikutnya(sampai))
        return stmt


def _awal_hari(tanggal: date) -> datetime:
    return datetime.combine(tanggal, time.min)


def _awal_hari_berikutnya(tanggal: date) -> datetime:
    return _awal_hari(tanggal + timedelta(days=1))
