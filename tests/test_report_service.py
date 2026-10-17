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


def test_laporan_mencatat_prioritas_dan_yang_dicabut(auth, antrian_siap):
    from app.services.queue_service import QueueService
    from app.services.report_service import ReportService

    auth.logout()
    auth.mulai_sesi_kios()
    nomor = QueueService(auth).create_queue(
        antrian_siap["kategori"]["A"],
        perangkat="tablet-laporan",
        prioritas_mandiri=True,
    )
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).cabut_prioritas(nomor.id)
    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)

    laporan = ReportService(auth).laporan(clock.today(), clock.today())

    assert laporan.total.prioritas == 1
    assert laporan.total.prioritas_dicabut == 1
    assert laporan.per_hari[0].prioritas == 1
    assert laporan.riwayat[0].prioritas
    assert laporan.riwayat[0].prioritas_dicabut


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


def test_laporan_petugas_hanya_memuat_nomor_miliknya(
    auth, laporan_hari_ini
):
    from app.services.report_service import ReportService

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    hari = clock.today()

    laporan = ReportService(auth).laporan_petugas(hari, hari)

    assert laporan.nama_petugas == "Petugas Cro"
    assert laporan.total.terbit == 3
    assert len(laporan.riwayat) == 3
    assert {baris.petugas for baris in laporan.riwayat} == {"Petugas Cro"}
    assert "Menunggu" not in {baris.status for baris in laporan.riwayat}


def test_admin_tidak_dapat_memakai_jalur_laporan_pribadi(auth, antrian_siap):
    from app.services.report_service import ReportService

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    hari = clock.today()

    with pytest.raises(AuthorizationError):
        ReportService(auth).laporan_petugas(hari, hari)


def test_ekspor_pdf_dan_excel(laporan_hari_ini, tmp_path):
    from openpyxl import load_workbook

    from app.services.report_export import ekspor_excel, ekspor_pdf

    pdf = ekspor_pdf(laporan_hari_ini, tmp_path / "lap.pdf", "KANTOR UJI")
    assert pdf.read_bytes().startswith(b"%PDF")

    xlsx = ekspor_excel(laporan_hari_ini, tmp_path / "lap.xlsx")
    buku = load_workbook(xlsx)
    assert buku.sheetnames == [
        "Ringkasan",
        "Per hari",
        "Per layanan",
        "Per loket",
        "Per petugas",
        "Petugas per layanan",
        "Riwayat pelayanan",
    ]
    loket = buku["Per loket"]
    assert loket["A1"].value == "Loket"
    assert loket["C2"].value == 2  # angka, bukan teks
    assert loket["G2"].value == 5

    rincian = buku["Petugas per layanan"]
    assert [sel.value for sel in rincian[1]][:4] == ["Petugas", "Jenis layanan", "Dipanggil", "Selesai"]
    assert rincian["D2"].value == 2
    assert rincian.auto_filter.ref

    riwayat = buku["Riwayat pelayanan"]
    assert riwayat.max_row == 1 + 4  # judul + satu baris per nomor
    assert riwayat["G2"].is_date  # jam terbit tersimpan sebagai waktu
    assert sorted(riwayat.cell(row=r, column=13).value or 0 for r in range(2, 6)) == [0, 0, 0, 5]


def test_ekspor_pribadi_tidak_memuat_tabel_petugas_lain(
    auth, laporan_hari_ini, tmp_path
):
    from openpyxl import load_workbook

    from app.services.report_export import ekspor_excel, ekspor_pdf, nama_berkas_bawaan
    from app.services.report_service import ReportService

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    hari = clock.today()
    laporan = ReportService(auth).laporan_petugas(hari, hari)

    assert nama_berkas_bawaan(laporan, "pdf").startswith("laporan-saya-petugas-cro-")
    pdf = ekspor_pdf(laporan, tmp_path / "saya.pdf", "KANTOR UJI")
    assert pdf.read_bytes().startswith(b"%PDF")
    xlsx = ekspor_excel(laporan, tmp_path / "saya.xlsx")
    buku = load_workbook(xlsx)
    assert buku["Ringkasan"]["A1"].value == "Laporan Pelayanan Saya"
    assert buku["Ringkasan"]["A3"].value == "Petugas Cro"
    assert "Per petugas" not in buku.sheetnames
    assert "Petugas per layanan" not in buku.sheetnames


def test_petugas_per_layanan_dan_riwayat(laporan_hari_ini):
    (pasangan,) = laporan_hari_ini.petugas_layanan
    total, rincian = pasangan
    assert total is laporan_hari_ini.per_petugas[0]
    (layanan,) = rincian
    assert layanan.kelompok == total.nama
    assert (layanan.dipanggil, layanan.selesai, layanan.tidak_hadir) == (3, 2, 1)
    assert layanan.jumlah_survey == 1

    riwayat = laporan_hari_ini.riwayat
    assert len(riwayat) == 4
    assert [t.terbit for t in riwayat] == sorted(t.terbit for t in riwayat)
    assert sorted(t.status for t in riwayat) == ["Menunggu", "Selesai", "Selesai", "Tidak Hadir"]
    selesai = [t for t in riwayat if t.status == "Selesai"]
    assert all(t.layanan_detik is not None for t in selesai)
    assert all(t.petugas == total.nama for t in selesai)
    assert sorted(t.nilai or 0 for t in selesai) == [0, 5]
    menunggu = [t for t in riwayat if t.dipanggil is None]
    assert len(menunggu) == 1 and menunggu[0].petugas == ""


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


def test_halaman_laporan_pribadi_menyimpan_excel_secara_atomik(
    qtbot, laporan_hari_ini, auth, monkeypatch, tmp_path
):
    from app.services.report_service import ReportService
    from app.ui.dashboard.report_page import LaporanPage

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = LaporanPage(ReportService(auth), "KANTOR", pribadi=True)
    qtbot.addWidget(halaman)
    tujuan_tanpa_akhiran = tmp_path / "laporan-saya"
    monkeypatch.setattr(
        "app.ui.dashboard.report_page.QFileDialog.getSaveFileName",
        lambda *_: (str(tujuan_tanpa_akhiran), "Excel (*.xlsx)"),
    )

    halaman._ekspor("xlsx")

    tujuan = tujuan_tanpa_akhiran.with_suffix(".xlsx")
    assert tujuan.is_file()
    assert not tujuan.with_name(f".{tujuan.name}.sementara").exists()
    assert tujuan.name in halaman.status_ekspor.text()


@pytest.mark.parametrize("peran", ["supervisor", "admin"])
def test_menu_laporan_untuk_supervisor_dan_admin(qtbot, auth, antrian_siap, peran):
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.login(peran, TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert "Laporan" in menu
    assert "Laporan Saya" not in menu


def test_menu_laporan_saya_hanya_untuk_cro(qtbot, auth, antrian_siap):
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]

    assert "Laporan Saya" in menu
    assert "Laporan" not in menu


def _audit_unduhan():
    import json

    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditAction, AuditLog

    with session_scope() as s:
        return [
            (user_id, json.loads(meta))
            for user_id, meta in s.execute(
                sa.select(AuditLog.user_id, AuditLog.meta)
                .where(AuditLog.action == AuditAction.EXPORT_REPORT.value)
                .order_by(AuditLog.id)
            )
        ]


def test_unduhan_laporan_tercatat_siapa_dan_cakupannya(auth, users, antrian_siap):
    from app.services.report_service import ReportService

    hari = clock.today()
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    layanan = ReportService(auth)
    layanan.catat_unduhan(layanan.laporan(hari, hari), "pdf")

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    layanan = ReportService(auth)
    layanan.catat_unduhan(layanan.laporan_petugas(hari, hari), "xlsx")

    (admin, cro) = _audit_unduhan()
    assert admin[0] == users["ADMIN"]
    assert admin[1]["cakupan"] == "cabang" and admin[1]["format"] == "pdf"
    assert cro[0] == users["CRO"]
    assert cro[1]["cakupan"] == "pribadi" and cro[1]["format"] == "xlsx"
    assert cro[1]["dari"] == hari.isoformat()


def test_cro_tidak_dapat_mencatat_unduhan_laporan_cabang(auth, antrian_siap):
    from app.services.report_service import ReportService

    hari = clock.today()
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    cabang = ReportService(auth).laporan(hari, hari)

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    with pytest.raises(AuthorizationError):
        ReportService(auth).catat_unduhan(cabang, "pdf")
