"""Test model, relasi, dan constraint database."""

from __future__ import annotations

import sqlalchemy as sa
import pytest

from app.core import clock
from app.core.database import session_scope
from app.models import (
    Branch,
    Counter,
    Queue,
    QueueCall,
    QueueSequence,
    QueueStatus,
    SatisfactionSurvey,
    ServiceCategory,
    User,
    UserRole,
)


def _buat_antrian(master, nomor="A-001", urutan=1, tanggal=None) -> int:
    with session_scope() as s:
        q = Queue(
            branch_id=master["branch_id"],
            category_id=master["category_id"],
            queue_date=tanggal or clock.today(),
            queue_number=nomor,
            sequence_number=urutan,
        )
        s.add(q)
        s.flush()
        return q.id


# ---------------------------------------------------------------------
# Relasi
# ---------------------------------------------------------------------

def test_relasi_branch_ke_data_master(seeded):
    with session_scope() as s:
        branch = s.scalar(sa.select(Branch).where(Branch.code == "PUSAT"))
        assert len(branch.counters) == 3
        assert len(branch.categories) == 3
        assert {c.prefix for c in branch.categories} == {"A", "B", "C"}


def test_relasi_antrian_ke_kategori_dan_loket(master):
    queue_id = _buat_antrian(master)
    with session_scope() as s:
        q = s.get(Queue, queue_id)
        assert q.category.prefix == "A"
        assert q.branch.code == "PUSAT"
        assert q.counter is None  # belum dipanggil
        assert q.calls == []
        assert q.survey is None


def test_relasi_pemanggilan_terurut(master):
    queue_id = _buat_antrian(master)
    with session_scope() as s:
        for n in (1, 2, 3):
            s.add(
                QueueCall(
                    queue_id=queue_id,
                    counter_id=master["counter_id"],
                    user_id=master["user_id"],
                    call_number=n,
                )
            )
    with session_scope() as s:
        q = s.get(Queue, queue_id)
        assert [c.call_number for c in q.calls] == [1, 2, 3]


# ---------------------------------------------------------------------
# Constraint antrian
# ---------------------------------------------------------------------

def test_nomor_antrian_tidak_boleh_kembar_pada_hari_yang_sama(master):
    """Pertahanan terakhir terhadap A-001 ganda."""
    _buat_antrian(master, "A-001", 1)
    with pytest.raises(sa.exc.IntegrityError):
        _buat_antrian(master, "A-001", 1)


def test_nomor_yang_sama_boleh_dipakai_lagi_di_hari_berbeda(master):
    """Nomor antrian direset setiap hari."""
    from datetime import timedelta

    _buat_antrian(master, "A-001", 1, clock.today())
    _buat_antrian(master, "A-001", 1, clock.today() + timedelta(days=1))

    with session_scope() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(Queue)) == 2


def test_prefix_berbeda_boleh_punya_angka_sama(master):
    """A-001 dan B-001 sah berdampingan di hari yang sama."""
    with session_scope() as s:
        kategori_b = s.scalar(
            sa.select(ServiceCategory).where(ServiceCategory.prefix == "B")
        )
        b_id = kategori_b.id

    _buat_antrian(master, "A-001", 1)
    with session_scope() as s:
        s.add(
            Queue(
                branch_id=master["branch_id"],
                category_id=b_id,
                queue_date=clock.today(),
                queue_number="B-001",
                sequence_number=1,
            )
        )
    with session_scope() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(Queue)) == 2


def test_status_awal_antrian_adalah_waiting(master):
    queue_id = _buat_antrian(master)
    with session_scope() as s:
        assert s.get(Queue, queue_id).status is QueueStatus.WAITING


def test_satu_loket_hanya_boleh_memegang_satu_nomor_aktif(master):
    """Pertahanan DB bila dua komputer memanggil lewat loket yang sama."""
    with session_scope() as s:
        s.add(
            Queue(
                branch_id=master["branch_id"],
                category_id=master["category_id"],
                queue_date=clock.today(),
                queue_number="A-001",
                sequence_number=1,
                status=QueueStatus.CALLED,
                counter_id=master["counter_id"],
                called_at=clock.now(),
            )
        )

    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as s:
            s.add(
                Queue(
                    branch_id=master["branch_id"],
                    category_id=master["category_id"],
                    queue_date=clock.today(),
                    queue_number="A-002",
                    sequence_number=2,
                    status=QueueStatus.CALLED,
                    counter_id=master["counter_id"],
                    called_at=clock.now(),
                )
            )


def test_sequence_number_harus_positif(master):
    with pytest.raises(sa.exc.IntegrityError):
        _buat_antrian(master, "A-000", 0)


def test_call_number_tidak_boleh_kembar_dalam_satu_antrian(master):
    queue_id = _buat_antrian(master)
    with session_scope() as s:
        s.add(
            QueueCall(
                queue_id=queue_id,
                counter_id=master["counter_id"],
                user_id=master["user_id"],
                call_number=1,
            )
        )
    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as s:
            s.add(
                QueueCall(
                    queue_id=queue_id,
                    counter_id=master["counter_id"],
                    user_id=master["user_id"],
                    call_number=1,
                )
            )


def test_queue_sequence_unik_per_cabang_tanggal_kategori(master):
    with session_scope() as s:
        s.add(
            QueueSequence(
                branch_id=master["branch_id"],
                queue_date=clock.today(),
                category_id=master["category_id"],
                last_number=5,
            )
        )
    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as s:
            s.add(
                QueueSequence(
                    branch_id=master["branch_id"],
                    queue_date=clock.today(),
                    category_id=master["category_id"],
                    last_number=1,
                )
            )


# ---------------------------------------------------------------------
# Constraint data master
# ---------------------------------------------------------------------

def test_prefix_jenis_layanan_unik_per_cabang(master):
    """Dua layanan berprefix sama akan membuat nomor antrian bertabrakan."""
    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as s:
            s.add(
                ServiceCategory(
                    branch_id=master["branch_id"],
                    code="LAIN",
                    name="Layanan Lain",
                    prefix="A",
                )
            )


def test_kode_loket_unik_per_cabang(master):
    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as s:
            s.add(
                Counter(
                    branch_id=master["branch_id"], code="LOKET-1", name="Duplikat"
                )
            )


def test_username_unik(master):
    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as s:
            s.add(
                User(
                    branch_id=master["branch_id"],
                    username="cro1",
                    full_name="Kembar",
                    password_hash="x",
                    role=UserRole.CRO,
                )
            )


def test_panjang_prefix_dibatasi(master):
    """
    Prefix lebih dari dua huruf harus ditolak database.

    Yang menolaknya berbeda per dialect, dan keduanya sah. SQLite
    mengabaikan panjang VARCHAR sepenuhnya sehingga yang bekerja adalah
    CheckConstraint `prefix_length` (IntegrityError); PostgreSQL menolak
    lebih dahulu lewat tipe kolomnya (DataError). Karena itu yang dikunci
    di sini adalah penolakannya, bukan nama exception-nya.
    """
    with pytest.raises(sa.exc.DatabaseError):
        with session_scope() as s:
            s.add(
                ServiceCategory(
                    branch_id=master["branch_id"],
                    code="PANJANG",
                    name="Prefix Kepanjangan",
                    prefix="ABC",
                )
            )


# ---------------------------------------------------------------------
# Survey
# ---------------------------------------------------------------------

def _buat_survey(master, queue_id: int, rating: int, feedback=None):
    with session_scope() as s:
        s.add(
            SatisfactionSurvey(
                queue_id=queue_id,
                branch_id=master["branch_id"],
                counter_id=master["counter_id"],
                category_id=master["category_id"],
                officer_id=master["user_id"],
                rating=rating,
                feedback=feedback,
            )
        )


@pytest.mark.parametrize("rating", [1, 2, 3, 4, 5])
def test_rating_sah_diterima(master, rating):
    queue_id = _buat_antrian(master, f"A-00{rating}", rating)
    _buat_survey(master, queue_id, rating)
    with session_scope() as s:
        survey = s.scalar(sa.select(SatisfactionSurvey))
        assert survey.rating == rating


@pytest.mark.parametrize("rating", [0, 6, -1, 100])
def test_rating_di_luar_1_sampai_5_ditolak(master, rating):
    queue_id = _buat_antrian(master)
    with pytest.raises(sa.exc.IntegrityError):
        _buat_survey(master, queue_id, rating)


def test_satu_antrian_hanya_boleh_punya_satu_survey(master):
    queue_id = _buat_antrian(master)
    _buat_survey(master, queue_id, 5)
    with pytest.raises(sa.exc.IntegrityError):
        _buat_survey(master, queue_id, 1)


def test_label_rating_sesuai_skala(master):
    queue_id = _buat_antrian(master)
    _buat_survey(master, queue_id, 1, feedback="Antrian terlalu lama")
    with session_scope() as s:
        survey = s.scalar(sa.select(SatisfactionSurvey))
        assert survey.rating_label == "Sangat Tidak Puas"
        assert survey.feedback == "Antrian terlalu lama"


def test_survey_tidak_mengubah_status_antrian(master):
    """
    Aturan bisnis: rating mengukur kepuasan, bukan menentukan selesai
    atau tidaknya pelayanan. Antrian COMPLETED tetap COMPLETED walau rating 1.
    """
    queue_id = _buat_antrian(master)
    with session_scope() as s:
        q = s.get(Queue, queue_id)
        q.status = QueueStatus.COMPLETED
        q.completed_at = clock.now()

    _buat_survey(master, queue_id, 1)

    with session_scope() as s:
        assert s.get(Queue, queue_id).status is QueueStatus.COMPLETED


# ---------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------

def test_audit_log_menerima_aksi_tanpa_user(database):
    """Aktivitas sistem seperti backup terjadwal tidak punya user."""
    from app.models import AuditAction, AuditLog

    with session_scope() as s:
        s.add(
            AuditLog(
                action=AuditAction.BACKUP.value,
                entity_type="database",
                meta='{"file": "backup.db"}',
            )
        )
    with session_scope() as s:
        log = s.scalar(sa.select(AuditLog))
        assert log.user_id is None
        assert log.action == "BACKUP"
        assert log.created_at is not None


# ---------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------

def test_created_at_dan_updated_at_terisi_otomatis(seeded):
    with session_scope() as s:
        branch = s.scalar(sa.select(Branch))
        assert branch.created_at is not None
        assert branch.updated_at is not None


def test_updated_at_berubah_saat_data_diubah(seeded):
    import time

    with session_scope() as s:
        sebelum = s.scalar(sa.select(Branch)).updated_at

    time.sleep(0.01)

    with session_scope() as s:
        s.scalar(sa.select(Branch)).name = "Kantor Pelayanan Utama"

    with session_scope() as s:
        assert s.scalar(sa.select(Branch)).updated_at > sebelum
