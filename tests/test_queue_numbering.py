"""
Test penomoran antrian.

Ini bagian paling rawan di seluruh sistem. Nomor kembar berarti dua
pengunjung dipanggil dengan nomor yang sama, dan kesalahannya baru
ketahuan di depan orang banyak.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.models import Queue, QueueStatus
from app.repositories.queue_repository import terbitkan_nomor

JUMLAH_UTAS = 8
NOMOR_PER_UTAS = 12


# ---------------------------------------------------------------------
# Penerbitan biasa
# ---------------------------------------------------------------------

def test_nomor_pertama_dimulai_dari_satu(reg_queue, antrian_siap):
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert nomor.queue_number == "A-001"
    assert nomor.sequence_number == 1
    assert nomor.status is QueueStatus.WAITING
    assert nomor.queue_date == clock.today()


def test_nomor_berurutan(reg_queue, antrian_siap):
    kategori = antrian_siap["kategori"]["A"]
    nomor = [reg_queue.create_queue(kategori).queue_number for _ in range(5)]

    assert nomor == ["A-001", "A-002", "A-003", "A-004", "A-005"]


def test_tiap_jenis_layanan_punya_urutan_sendiri(reg_queue, antrian_siap):
    """A-001 dan B-001 sah berdampingan; prefix memisahkan urutannya."""
    kategori = antrian_siap["kategori"]
    a1 = reg_queue.create_queue(kategori["A"])
    b1 = reg_queue.create_queue(kategori["B"])
    a2 = reg_queue.create_queue(kategori["A"])
    c1 = reg_queue.create_queue(kategori["C"])

    assert (a1.queue_number, a2.queue_number) == ("A-001", "A-002")
    assert b1.queue_number == "B-001"
    assert c1.queue_number == "C-001"


def test_nomor_diisi_nol_di_depan(reg_queue, antrian_siap):
    """A-007 lebih mudah dibaca dari kejauhan daripada A-7."""
    kategori = antrian_siap["kategori"]["A"]
    for _ in range(6):
        reg_queue.create_queue(kategori)

    assert reg_queue.create_queue(kategori).queue_number == "A-007"


def test_antrian_bersifat_anonim(reg_queue, antrian_siap):
    """Tidak ada satu pun data pribadi pengunjung yang tersimpan."""
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    with session_scope() as s:
        baris = s.get(Queue, nomor.id)
        kolom = {c.name for c in baris.__table__.columns}

    assert not kolom & {"name", "visitor_name", "identity_number", "phone", "email", "address"}


# ---------------------------------------------------------------------
# Reset harian
# ---------------------------------------------------------------------

def test_nomor_dimulai_lagi_dari_satu_esok_hari(antrian_siap):
    """
    Nomor direset setiap hari. Diuji langsung pada lapisan penerbitan
    karena tanggalnya perlu dipaksa.
    """
    hari_ini = clock.today()
    besok = hari_ini + timedelta(days=1)
    kategori = antrian_siap["kategori"]["A"]
    cabang = antrian_siap["branch_id"]

    for _ in range(3):
        terbitkan_nomor(
            branch_id=cabang, category_id=kategori, prefix="A", tanggal=hari_ini
        )

    esok = terbitkan_nomor(
        branch_id=cabang, category_id=kategori, prefix="A", tanggal=besok
    )

    assert esok.queue_number == "A-001"
    assert esok.sequence_number == 1


def test_nomor_sama_di_hari_berbeda_tidak_bertabrakan(antrian_siap):
    hari_ini = clock.today()
    kategori = antrian_siap["kategori"]["A"]
    cabang = antrian_siap["branch_id"]

    for hari in (hari_ini, hari_ini + timedelta(days=1), hari_ini + timedelta(days=2)):
        hasil = terbitkan_nomor(
            branch_id=cabang, category_id=kategori, prefix="A", tanggal=hari
        )
        assert hasil.queue_number == "A-001"

    with session_scope() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(Queue)) == 3


# ---------------------------------------------------------------------
# Konkurensi
# ---------------------------------------------------------------------

def test_penerbitan_bersamaan_tidak_menghasilkan_nomor_kembar(antrian_siap):
    """
    Syarat mutlak spesifikasi: dua permintaan bersamaan harus menghasilkan
    A-024 dan A-025, bukan A-024 dua kali.

    Delapan utas menerbitkan 12 nomor masing-masing, seluruhnya pada jenis
    layanan yang sama agar semuanya memperebutkan baris sequence yang sama.
    """
    kategori = antrian_siap["kategori"]["A"]
    cabang = antrian_siap["branch_id"]
    total = JUMLAH_UTAS * NOMOR_PER_UTAS

    def terbitkan_banyak() -> list[str]:
        return [
            terbitkan_nomor(
                branch_id=cabang, category_id=kategori, prefix="A"
            ).queue_number
            for _ in range(NOMOR_PER_UTAS)
        ]

    with ThreadPoolExecutor(max_workers=JUMLAH_UTAS) as pool:
        hasil = [f.result() for f in [pool.submit(terbitkan_banyak) for _ in range(JUMLAH_UTAS)]]

    semua = [nomor for batch in hasil for nomor in batch]

    assert len(semua) == total
    assert len(set(semua)) == total, f"ada nomor kembar: {len(semua) - len(set(semua))}"
    assert set(semua) == {f"A-{i:03d}" for i in range(1, total + 1)}


def test_penerbitan_bersamaan_tersimpan_lengkap_di_database(antrian_siap):
    """Tidak boleh ada nomor terpakai tanpa barisan antriannya."""
    kategori = antrian_siap["kategori"]["A"]
    cabang = antrian_siap["branch_id"]
    total = JUMLAH_UTAS * NOMOR_PER_UTAS

    def terbitkan_banyak() -> None:
        for _ in range(NOMOR_PER_UTAS):
            terbitkan_nomor(branch_id=cabang, category_id=kategori, prefix="A")

    with ThreadPoolExecutor(max_workers=JUMLAH_UTAS) as pool:
        for f in [pool.submit(terbitkan_banyak) for _ in range(JUMLAH_UTAS)]:
            f.result()

    with session_scope() as s:
        tersimpan = list(s.scalars(sa.select(Queue.queue_number)))
        urutan = sorted(s.scalars(sa.select(Queue.sequence_number)))

    assert len(tersimpan) == total
    assert len(set(tersimpan)) == total
    assert urutan == list(range(1, total + 1)), "ada nomor urut yang bolong"


def test_penerbitan_bersamaan_lintas_jenis_layanan(antrian_siap):
    """Layanan berbeda memakai baris sequence berbeda dan tidak saling mengunci."""
    kategori = antrian_siap["kategori"]
    cabang = antrian_siap["branch_id"]
    per_layanan = 15

    def terbitkan_untuk(prefix: str) -> list[str]:
        return [
            terbitkan_nomor(
                branch_id=cabang, category_id=kategori[prefix], prefix=prefix
            ).queue_number
            for _ in range(per_layanan)
        ]

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(terbitkan_untuk, prefix)
            for prefix in ("A", "B", "C", "A", "B", "C")
        ]
        hasil = [f.result() for f in futures]

    semua = [n for batch in hasil for n in batch]
    assert len(set(semua)) == len(semua), "ada nomor kembar"

    for prefix in ("A", "B", "C"):
        milik = sorted(n for n in semua if n.startswith(f"{prefix}-"))
        assert milik == [f"{prefix}-{i:03d}" for i in range(1, per_layanan * 2 + 1)]


def test_constraint_database_menolak_nomor_kembar(antrian_siap):
    """
    Pertahanan terakhir bila mekanisme penomoran suatu saat rusak.

    Nomor disisipkan langsung ke database, melewati seluruh service.
    """
    kategori = antrian_siap["kategori"]["A"]
    cabang = antrian_siap["branch_id"]
    terbitkan_nomor(branch_id=cabang, category_id=kategori, prefix="A")

    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as s:
            s.add(
                Queue(
                    branch_id=cabang,
                    category_id=kategori,
                    queue_date=clock.today(),
                    queue_number="A-001",
                    sequence_number=1,
                )
            )
