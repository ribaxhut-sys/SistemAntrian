"""
Test ringkasan harian.

Angka di layar ini dipakai supervisor untuk menilai pelayanan hari itu.
Yang dikunci di sini terutama: rata-rata hanya menghitung antrian yang
benar-benar mencapai tahapnya, dan "belum ada data" tidak boleh tampil
sebagai nol.
"""

from __future__ import annotations

import pytest

from app.core.errors import AuthorizationError
from app.models import QueueStatus
from app.services.dashboard_service import DashboardService
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def dashboard(auth, antrian_siap):
    """DashboardService dengan sesi supervisor."""

    def _sebagai_supervisor() -> DashboardService:
        auth.logout()
        auth.login("supervisor", TEST_PASSWORD)
        return DashboardService(auth)

    return _sebagai_supervisor


# ---------------------------------------------------------------------
# Keadaan kosong
# ---------------------------------------------------------------------

def test_ringkasan_kosong_saat_belum_ada_antrian(dashboard):
    hasil = dashboard().ringkasan_hari_ini()

    assert hasil.total == 0
    assert hasil.belum_selesai == 0
    assert all(jumlah == 0 for jumlah in hasil.per_status.values())


def test_durasi_kosong_ditampilkan_sebagai_strip_bukan_nol(dashboard):
    """Nol detik dan belum ada datanya adalah dua hal yang berbeda."""
    hasil = dashboard().ringkasan_hari_ini()

    assert hasil.rata_menunggu_detik is None
    assert hasil.rata_layanan_detik is None
    assert hasil.label_rata_menunggu == "—"
    assert hasil.label_rata_layanan == "—"


def test_kehadiran_kosong_saat_belum_ada_yang_tuntas(dashboard):
    assert dashboard().ringkasan_hari_ini().persen_kehadiran is None


def test_jenis_layanan_tanpa_antrian_tetap_muncul(dashboard):
    """Susunan kartu tidak boleh berubah-ubah sepanjang hari."""
    hasil = dashboard().ringkasan_hari_ini()

    assert len(hasil.per_kategori) >= 2
    assert all(jumlah == 0 for jumlah in hasil.per_kategori.values())


# ---------------------------------------------------------------------
# Perhitungan
# ---------------------------------------------------------------------

def test_antrian_baru_dihitung_sebagai_menunggu(dashboard, terbitkan):
    terbitkan("A", 3)

    hasil = dashboard().ringkasan_hari_ini()

    assert hasil.total == 3
    assert hasil.per_status[QueueStatus.WAITING] == 3
    assert hasil.belum_selesai == 3


def test_antrian_dihitung_per_jenis_layanan(dashboard, terbitkan):
    terbitkan("A", 2)
    terbitkan("B", 1)

    per_kategori = dashboard().ringkasan_hari_ini().per_kategori

    assert sum(per_kategori.values()) == 3
    assert sorted(per_kategori.values(), reverse=True)[:2] == [2, 1]


def test_dilewati_tetap_dihitung_sebagai_belum_selesai(
    dashboard, cro_queue, terbitkan, antrian_siap
):
    terbitkan("A")
    dipanggil = cro_queue.call_next(antrian_siap["loket"][0])
    cro_queue.skip(dipanggil.id)

    hasil = dashboard().ringkasan_hari_ini()

    assert hasil.per_status[QueueStatus.SKIPPED] == 1
    assert hasil.belum_selesai == 1


def test_pelayanan_selesai_mengurangi_belum_selesai(
    dashboard, layani_sampai_selesai, terbitkan
):
    layani_sampai_selesai()
    terbitkan("A")

    hasil = dashboard().ringkasan_hari_ini()

    assert hasil.total == 2
    assert hasil.per_status[QueueStatus.COMPLETED] == 1
    assert hasil.belum_selesai == 1


def test_rata_rata_terisi_setelah_ada_pelayanan(dashboard, layani_sampai_selesai):
    layani_sampai_selesai()

    hasil = dashboard().ringkasan_hari_ini()

    assert hasil.rata_menunggu_detik is not None
    assert hasil.rata_layanan_detik is not None
    assert hasil.rata_menunggu_detik >= 0
    assert hasil.label_rata_layanan != "—"


def test_antrian_batal_tidak_mencemari_rata_rata_menunggu(
    dashboard, cro_queue, terbitkan
):
    """Nomor yang dibatalkan sebelum dipanggil tidak pernah menunggu dipanggil."""
    antrian = terbitkan("A")[0]
    cro_queue.cancel(antrian.id)

    hasil = dashboard().ringkasan_hari_ini()

    assert hasil.per_status[QueueStatus.CANCELLED] == 1
    assert hasil.rata_menunggu_detik is None


def test_persen_kehadiran_dihitung_dari_yang_tuntas(
    antrian_siap, dashboard, cro_queue, layani_sampai_selesai, terbitkan
):
    layani_sampai_selesai()
    terbitkan("A")
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    cro_queue.no_show(antrian.id)

    hasil = dashboard().ringkasan_hari_ini()

    assert hasil.per_status[QueueStatus.NO_SHOW] == 1
    assert hasil.persen_kehadiran == pytest.approx(50.0)


# ---------------------------------------------------------------------
# Kepuasan
# ---------------------------------------------------------------------

def test_survey_hari_ini_ikut_dalam_ringkasan(
    dashboard, cro_survey, layani_sampai_selesai
):
    cro_survey.submit(layani_sampai_selesai().id, 5)
    cro_survey.submit(layani_sampai_selesai().id, 3)

    survey = dashboard().ringkasan_hari_ini().survey

    assert survey.jumlah == 2
    assert survey.rata_rata == pytest.approx(4.0)
    assert survey.distribusi[5] == 1
    assert survey.distribusi[3] == 1


def test_ringkasan_survey_kosong_saat_belum_ada_penilaian(
    dashboard, layani_sampai_selesai
):
    layani_sampai_selesai()

    survey = dashboard().ringkasan_hari_ini().survey

    assert survey.jumlah == 0
    assert survey.label_rata_rata == "-"


# ---------------------------------------------------------------------
# Hak akses
# ---------------------------------------------------------------------

@pytest.mark.parametrize("peran", ["cro", "registration", "display"])
def test_petugas_dan_layar_tidak_boleh_melihat_ringkasan(auth, antrian_siap, peran):
    """Ringkasan operasional bukan urusan petugas loket, pendaftaran, atau layar."""
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        DashboardService(auth).ringkasan_hari_ini()


def test_admin_boleh_melihat_ringkasan(auth, antrian_siap):
    """Admin memantau seluruh cabang; hanya membaca, tidak mengubah antrian."""
    auth.logout()
    auth.login("admin", TEST_PASSWORD)

    assert DashboardService(auth).ringkasan_hari_ini().total == 0
