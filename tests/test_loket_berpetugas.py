"""
Layar antrian hanya menampilkan loket yang ada petugasnya.

Yang dikunci: tanda hadir dari jendela petugas memunculkan loketnya, logout
dan tanda yang basi menyembunyikannya, loket yang masih memanggil nomor
tetap tampil, dan pengaturan "semua" mengembalikan perilaku lama.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.models import Counter
from app.services.queue_service import BATAS_HADIR_PETUGAS_DETIK, QueueService
from app.services.settings_service import SettingsService
from tests.conftest import TEST_PASSWORD

pytestmark = pytest.mark.loket_berpetugas


def _loket_di_layar(auth) -> list[int]:
    """Loket di papan, dibaca lewat sesi layar yang terpisah."""
    from app.services.auth_service import AuthService

    layar = AuthService()
    layar.login("display", TEST_PASSWORD)
    return [b.counter_id for b in QueueService(layar).display_state().loket]


@pytest.fixture
def petugas(auth, antrian_siap):
    """Petugas CRO yang login dan duduk di loket pertama."""
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    auth.pindah_loket(antrian_siap["loket"][0])
    return auth


def test_tanpa_petugas_tidak_ada_loket_di_layar(auth, antrian_siap):
    assert _loket_di_layar(auth) == []


def test_loket_petugas_yang_login_tampil(petugas, antrian_siap):
    # pindah_loket langsung memberi tanda hadir, tanpa menunggu 30 detik.
    assert _loket_di_layar(petugas) == [antrian_siap["loket"][0]]


def test_logout_menyembunyikan_loket(petugas, antrian_siap):
    petugas.logout()
    assert _loket_di_layar(petugas) == []


def test_tanda_hadir_basi_menyembunyikan_loket(petugas, antrian_siap):
    """PC loket yang mati listrik tidak sempat logout."""
    with session_scope() as session:
        session.execute(
            sa.update(Counter)
            .where(Counter.id == antrian_siap["loket"][0])
            .values(
                petugas_terlihat_pada=clock.now()
                - timedelta(seconds=BATAS_HADIR_PETUGAS_DETIK + 5)
            )
        )
    assert _loket_di_layar(petugas) == []

    petugas.tanda_hadir_loket()
    assert _loket_di_layar(petugas) == [antrian_siap["loket"][0]]


def test_pindah_loket_memindahkan_tanda_hadir(petugas, antrian_siap):
    petugas.pindah_loket(antrian_siap["loket"][1])
    assert _loket_di_layar(petugas) == [antrian_siap["loket"][1]]


def test_loket_yang_memanggil_tetap_tampil_sesudah_logout(
    petugas, terbitkan, antrian_siap
):
    """Pengunjung yang sudah dipanggil tidak boleh kehilangan nomornya."""
    loket = antrian_siap["loket"][0]
    terbitkan("A", 1)
    QueueService(petugas).call_next(loket)

    petugas.logout()
    assert _loket_di_layar(petugas) == [loket]


def test_pengaturan_semua_menampilkan_semua_loket_aktif(auth, antrian_siap):
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.loket_tampil", "semua")
    assert _loket_di_layar(auth) == antrian_siap["loket"]


def test_tanda_hadir_tidak_mengubah_updated_at_loket(petugas, antrian_siap):
    """updated_at loket menandai perubahan data master, bukan keadaan."""
    loket = antrian_siap["loket"][0]
    with session_scope() as session:
        sebelum = session.scalar(sa.select(Counter.updated_at).where(Counter.id == loket))
    petugas.tanda_hadir_loket()
    with session_scope() as session:
        sesudah = session.scalar(sa.select(Counter.updated_at).where(Counter.id == loket))
    assert sesudah == sebelum
