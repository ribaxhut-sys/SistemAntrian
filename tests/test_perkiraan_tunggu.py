"""
Test perkiraan waktu tunggu di tiket.

Yang paling penting: tiket DIAM bila tidak ada perkiraan yang jujur —
tanpa loket berpetugas atau tanpa riwayat pelayanan — dan angka yang
dicetak berupa rentang yang dibulatkan ke atas, bukan janji menit.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core import clock
from app.core.database import session_scope
from app.models import Counter, Queue, QueueStatus
from app.services.queue_service import _lama_layanan_tipikal


def _riwayat(antrian_siap, prefix: str, menit: list[float], hari_lalu: int = 0) -> None:
    """Sisipkan pelayanan SELESAI dengan lama layanan tertentu."""
    tanggal = clock.today() - timedelta(days=hari_lalu)
    awal = datetime.combine(tanggal, datetime.min.time()).replace(hour=8)
    with session_scope() as session:
        for i, lama in enumerate(menit):
            mulai = awal + timedelta(minutes=10 * i)
            session.add(
                Queue(
                    branch_id=antrian_siap["branch_id"],
                    category_id=antrian_siap["kategori"][prefix],
                    queue_date=tanggal,
                    queue_number=f"{prefix}-9{hari_lalu}{i:02d}",
                    sequence_number=900 + i,
                    status=QueueStatus.COMPLETED,
                    created_at=mulai,
                    called_at=mulai,
                    serving_at=mulai,
                    completed_at=mulai + timedelta(minutes=lama),
                )
            )


def _loket(antrian_siap, jumlah: int, layanan: list[str] | None = None, **ubah) -> None:
    """Tandai `jumlah` loket pertama berpetugas; sisanya kosong."""
    from app.models import ServiceCategory

    with session_scope() as session:
        for urutan, counter_id in enumerate(antrian_siap["loket"]):
            counter = session.get(Counter, counter_id)
            counter.on_break = False
            counter.petugas_terlihat_pada = clock.now() if urutan < jumlah else None
            counter.categories = [
                session.get(ServiceCategory, antrian_siap["kategori"][p])
                for p in (layanan or [])
            ]
            for kunci, nilai in ubah.items():
                setattr(counter, kunci, nilai)


@pytest.fixture
def cukup_loket(antrian_siap):
    if len(antrian_siap["loket"]) < 2:
        pytest.skip("butuh dua loket dari data awal")


def test_median_tidak_terseret_satu_pelayanan_yang_sangat_lama():
    hari = clock.today()
    sampel = [(1, hari, 300.0)] * 6 + [(1, hari, 5400.0)]
    tipikal, gabungan = _lama_layanan_tipikal(sampel, hari)
    assert tipikal[1] == 300.0
    assert gabungan == 300.0


def test_riwayat_lama_dipakai_bila_hari_ini_belum_cukup():
    hari = clock.today()
    kemarin = hari - timedelta(days=1)
    sampel = [(1, hari, 600.0)] * 2 + [(1, kemarin, 300.0)] * 5
    tipikal, _ = _lama_layanan_tipikal(sampel, hari)
    assert tipikal[1] == 300.0


def test_tanpa_cukup_sampel_tidak_ada_perkiraan():
    hari = clock.today()
    tipikal, gabungan = _lama_layanan_tipikal([(1, hari, 300.0)] * 4, hari)
    assert tipikal == {}
    assert gabungan is None


# ---------------------------------------------------------------------
# Perhitungan dari database
# ---------------------------------------------------------------------

def test_perkiraan_dibagi_banyaknya_loket_berpetugas(
    reg_queue, antrian_siap, cukup_loket
):
    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 2)
    for _ in range(4):
        reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    # 4 orang × 6 menit ÷ 2 loket = 12 menit.
    assert reg_queue.perkiraan_tunggu(nomor) == pytest.approx(12 * 60)


def test_orang_di_depan_memakai_lama_layanan_jenisnya_sendiri(
    reg_queue, antrian_siap
):
    _riwayat(antrian_siap, "A", [4] * 5)
    _riwayat(antrian_siap, "B", [20] * 5)
    _loket(antrian_siap, 1)
    reg_queue.create_queue(antrian_siap["kategori"]["B"])
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert reg_queue.perkiraan_tunggu(nomor) == pytest.approx(24 * 60)


def test_loket_istirahat_atau_tanpa_petugas_tidak_dihitung(reg_queue, antrian_siap):
    _riwayat(antrian_siap, "A", [6] * 5)
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    _loket(antrian_siap, 0)
    assert reg_queue.perkiraan_tunggu(nomor) is None

    _loket(antrian_siap, 1, on_break=True)
    assert reg_queue.perkiraan_tunggu(nomor) is None


def test_loket_yang_tidak_melayani_jenisnya_tidak_dihitung(reg_queue, antrian_siap):
    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1, layanan=["B"])
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert reg_queue.perkiraan_tunggu(nomor) is None


def test_antrian_jenis_lain_yang_tidak_terjangkau_loket_tidak_menambah(
    reg_queue, antrian_siap
):
    _riwayat(antrian_siap, "A", [6] * 5)
    _riwayat(antrian_siap, "B", [30] * 5)
    _loket(antrian_siap, 1, layanan=["A"])
    reg_queue.create_queue(antrian_siap["kategori"]["B"])
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert reg_queue.perkiraan_tunggu(nomor) == pytest.approx(6 * 60)


def test_kios_boleh_membaca_perkiraan(auth, reg_queue, antrian_siap):
    from app.services.queue_service import QueueService

    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1)
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    auth.logout()
    auth.mulai_sesi_kios()
    kios = QueueService(auth)
    nomor = kios.create_queue(antrian_siap["kategori"]["A"])

    assert kios.perkiraan_tunggu(nomor) == pytest.approx(6 * 60)


# ---------------------------------------------------------------------
# Nomor prioritas yang datang belakangan menyalip nomor biasa
# ---------------------------------------------------------------------

def test_sisipan_prioritas_nol_tanpa_kedatangan_prioritas():
    from app.services.queue_service import sisipan_prioritas

    assert sisipan_prioritas(
        600, laju_per_detik=0, lama_per_orang=300, loket=1, rasio=3, biasa_di_depan=2
    ) == 0.0


def test_sisipan_prioritas_mengikuti_laju_dan_lama_layanan():
    from app.services.queue_service import sisipan_prioritas

    # 6 prioritas/jam, dasar 20 menit: 2 penyalip (+10 menit) pada putaran
    # pertama; tunggu 30 menit itu mendatangkan 3 penyalip (+15 menit).
    tambahan = sisipan_prioritas(
        1200, laju_per_detik=6 / 3600, lama_per_orang=300, loket=1, rasio=3,
        biasa_di_depan=5,
    )
    assert tambahan == pytest.approx(900)
    # Dua loket membagi tambahannya.
    berdua = sisipan_prioritas(
        1200, laju_per_detik=6 / 3600, lama_per_orang=300, loket=2, rasio=3,
        biasa_di_depan=5,
    )
    assert berdua < tambahan


def test_sisipan_prioritas_dibatasi_rasio():
    """Rasio 3:1 — sebelum tiket terdepan paling banyak 3 prioritas menyalip."""
    from app.services.queue_service import sisipan_prioritas

    tambahan = sisipan_prioritas(
        3600, laju_per_detik=60 / 3600, lama_per_orang=300, loket=1, rasio=3,
        biasa_di_depan=0,
    )
    assert tambahan == pytest.approx(3 * 300)


def _prioritas_terbit(antrian_siap, jumlah: int, menit_lalu: int) -> None:
    """Nomor prioritas yang terbit lalu dibatalkan: dihitung lajunya saja."""
    with session_scope() as session:
        for i in range(jumlah):
            session.add(
                Queue(
                    branch_id=antrian_siap["branch_id"],
                    category_id=antrian_siap["kategori"]["A"],
                    queue_date=clock.today(),
                    queue_number=f"A-8{menit_lalu:02d}{i}",
                    sequence_number=800 + menit_lalu * 10 + i,
                    status=QueueStatus.CANCELLED,
                    prioritas="LANSIA",
                    created_at=clock.now() - timedelta(minutes=menit_lalu),
                )
            )


def test_nomor_biasa_diperpanjang_oleh_laju_prioritas(reg_queue, antrian_siap):
    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1)
    for _ in range(2):
        reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])
    dasar = reg_queue.perkiraan_tunggu(nomor)
    assert dasar == pytest.approx(12 * 60)

    # Prioritas di luar jendela satu jam tidak dihitung.
    _prioritas_terbit(antrian_siap, 5, menit_lalu=90)
    assert reg_queue.perkiraan_tunggu(nomor) == pytest.approx(dasar)

    _prioritas_terbit(antrian_siap, 6, menit_lalu=20)
    assert reg_queue.perkiraan_tunggu(nomor) > dasar


def test_nomor_prioritas_tidak_disalip_prioritas_baru(reg_queue, antrian_siap):
    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1)
    reg_queue.create_queue(antrian_siap["kategori"]["A"], prioritas="LANSIA")
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"], prioritas="LANSIA")
    dasar = reg_queue.perkiraan_tunggu(nomor)

    _prioritas_terbit(antrian_siap, 6, menit_lalu=20)

    assert reg_queue.perkiraan_tunggu(nomor) == pytest.approx(dasar)
