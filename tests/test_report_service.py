"""Laporan rentang tanggal: angka, pembagian per loket/petugas, dan ekspor."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core import clock
from app.core.errors import AuthorizationError, ValidationError
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def laporan_hari_ini(auth, antrian_siap, cro_queue, cro_survey, terbitkan, layani_sampai_selesai):
    """Dua selesai (satu dinilai 5), satu tidak hadir, satu masih menunggu."""
    from app.services.report_service import ReportService

    pertama = layani_sampai_selesai("A")
    cro_survey.submit(pertama.id, 5)
    layani_sampai_selesai("A")
    terbitkan("A", 2)
    loket = antrian_siap["loket"][0]
    dipanggil = cro_queue.call_next(loket)
    cro_queue.no_show(dipanggil.id)

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    hari = clock.today()
    return ReportService(auth).laporan(hari, hari)


def test_angka_total(laporan_hari_ini):
    total = laporan_hari_ini.total
    assert total.terbit == 4
    assert total.selesai == 2
    assert total.tidak_hadir == 1
    assert total.dipanggil == 3
    assert total.jumlah_survey == 1
    assert total.rata_kepuasan == 5
    assert total.rata_layanan_detik is not None


def test_pembagian_per_loket_petugas_dan_hari(laporan_hari_ini):
    (loket,) = laporan_hari_ini.per_loket
    assert loket.selesai == 2
    assert loket.label_kepuasan == "5,0"
    (petugas,) = laporan_hari_ini.per_petugas
    assert petugas.dipanggil == 3
    (hari,) = laporan_hari_ini.per_hari
    assert hari.terbit == 4
    assert sum(b.terbit for b in laporan_hari_ini.per_layanan) == 4


def test_rentang_tanpa_data_kosong(auth, antrian_siap):
    from app.services.report_service import ReportService

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    kemarin = clock.today() - timedelta(days=1)
    laporan = ReportService(auth).laporan(kemarin, kemarin)
    assert laporan.total.terbit == 0
    assert laporan.per_hari == []


def test_rentang_tidak_sah_ditolak(auth, antrian_siap):
    from app.services.report_service import ReportService

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    hari = clock.today()
    layanan = ReportService(auth)
    with pytest.raises(ValidationError):
        layanan.laporan(hari, hari - timedelta(days=1))
    with pytest.raises(ValidationError):
        layanan.laporan(hari - timedelta(days=400), hari)


def test_hanya_supervisor(auth, antrian_siap):
    from app.services.report_service import ReportService

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    hari = clock.today()
    with pytest.raises(AuthorizationError):
        ReportService(auth).laporan(hari, hari)


def test_ekspor_pdf_dan_excel(laporan_hari_ini, tmp_path):
    from openpyxl import load_workbook

    from app.services.report_export import ekspor_excel, ekspor_pdf

    pdf = ekspor_pdf(laporan_hari_ini, tmp_path / "lap.pdf", "KANTOR UJI")
    assert pdf.read_bytes().startswith(b"%PDF")

    xlsx = ekspor_excel(laporan_hari_ini, tmp_path / "lap.xlsx")
    buku = load_workbook(xlsx)
    assert buku.sheetnames == ["Ringkasan", "Per hari", "Per layanan", "Per loket", "Per petugas"]
    loket = buku["Per loket"]
    assert loket["A1"].value == "Loket"
    assert loket["C2"].value == 2  # angka, bukan teks
    assert loket["G2"].value == 5


def test_rentang_cepat():
    from datetime import date

    from app.ui.dashboard.report_page import rentang_cepat

    hari = date(2026, 10, 7)
    assert rentang_cepat("hari_ini", hari) == (hari, hari)
    assert rentang_cepat("7_hari", hari) == (date(2026, 10, 1), hari)
    assert rentang_cepat("bulan_ini", hari) == (date(2026, 10, 1), hari)
    assert rentang_cepat("bulan_lalu", hari) == (date(2026, 9, 1), date(2026, 9, 30))


def test_halaman_laporan_tampil(qtbot, laporan_hari_ini, auth):
    from app.services.report_service import ReportService
    from app.ui.dashboard.report_page import LaporanPage

    halaman = LaporanPage(ReportService(auth), "KANTOR")
    qtbot.addWidget(halaman)
    halaman._pakai_rentang("hari_ini")

    assert halaman.kartu[0].nilai.text() == "4"
    assert halaman.tabel["per_loket"].rowCount() == 1
    assert halaman.ekspor_pdf.isEnabled()


@pytest.mark.parametrize("peran", ["supervisor", "admin"])
def test_menu_laporan_untuk_supervisor_dan_admin(qtbot, auth, antrian_siap, peran):
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.login(peran, TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert "Laporan" in menu
