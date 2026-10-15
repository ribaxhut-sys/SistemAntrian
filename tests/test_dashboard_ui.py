"""
Test tampilan dashboard admin/supervisor dan dashboard petugas.

Layar ini murni membaca. Yang dikunci: angka tampil dari service, akses
cepat hanya muncul sesuai hak, audit log hanya untuk admin, peringatan
petugas, dan menu per peran.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.core.database import session_scope
from app.models import User
from app.services.dashboard_service import DashboardService
from app.services.settings_service import SettingsService
from tests.conftest import TEST_PASSWORD


def _masuk(auth, peran: str) -> None:
    auth.logout()
    auth.login(peran, TEST_PASSWORD)


def _halaman_admin(qtbot, auth, peran: str, buka_menu=None):
    from app.ui.dashboard.dashboard_page import DashboardPage

    _masuk(auth, peran)
    halaman = DashboardPage(
        DashboardService(auth), SettingsService(auth), buka_menu=buka_menu
    )
    qtbot.addWidget(halaman)
    return halaman


def test_dashboard_admin_menampilkan_angka_nyata(qtbot, auth, antrian_siap, terbitkan):
    terbitkan("A", 3)

    halaman = _halaman_admin(qtbot, auth, "admin")

    assert halaman.kartu_total.nilai.text() == "3"
    assert halaman.kartu_n_menunggu.nilai.text() == "3"
    assert halaman.kartu_n_dilayani.nilai.text() == "0"
    assert halaman.kartu_n_selesai.nilai.text() == "0"
    assert halaman.kartu_n_batal.nilai.text() == "0"
    assert not halaman.grafik.kosong
    assert halaman.tabel_loket.rowCount() == len(antrian_siap["loket"])
    assert not halaman.label_kosong.isVisibleTo(halaman)


def test_dashboard_kosong_menyatakan_terus_terang(qtbot, auth, antrian_siap):
    halaman = _halaman_admin(qtbot, auth, "admin")

    assert halaman.kartu_total.nilai.text() == "0"
    assert halaman.kartu_menunggu.nilai.text() == "—"
    assert halaman.grafik.kosong
    assert halaman.label_kosong.isVisibleTo(halaman)


def test_saringan_layanan_mengubah_angka(qtbot, auth, antrian_siap, terbitkan):
    terbitkan("A", 2)
    terbitkan("B", 1)
    halaman = _halaman_admin(qtbot, auth, "admin")
    assert halaman.kartu_total.nilai.text() == "3"

    indeks = halaman.pilih_layanan.findText(
        next(n for n in _nama_layanan(halaman) if n)
    )
    halaman.pilih_layanan.setCurrentIndex(indeks)

    assert halaman.kartu_total.nilai.text() in {"1", "2"}
    assert halaman.saringan().category_id is not None


def _nama_layanan(halaman) -> list[str]:
    return [
        halaman.pilih_layanan.itemText(i) for i in range(1, halaman.pilih_layanan.count())
    ]


def test_akses_cepat_admin_lengkap_dan_memanggil_menu(qtbot, auth, antrian_siap):
    dibuka: list[str] = []
    halaman = _halaman_admin(qtbot, auth, "admin", buka_menu=dibuka.append)

    assert set(halaman.tombol_akses) == {
        "Laporan",
        "Data Master",
        "Pengaturan",
        "Backup",
        "Kesehatan Sistem",
    }
    halaman.tombol_akses["Backup"].click()
    assert dibuka == ["Backup"]


def test_supervisor_hanya_melihat_akses_laporan_dan_tanpa_audit(
    qtbot, auth, antrian_siap
):
    halaman = _halaman_admin(qtbot, auth, "supervisor")

    assert set(halaman.tombol_akses) == {"Laporan"}
    assert not halaman.panel_aktivitas.isVisibleTo(halaman)
    assert halaman.tabel_aktivitas.rowCount() == 0


def test_admin_melihat_aktivitas_terakhir(qtbot, auth, antrian_siap):
    halaman = _halaman_admin(qtbot, auth, "admin")

    assert halaman.panel_aktivitas.isVisibleTo(halaman)
    assert halaman.tabel_aktivitas.rowCount() >= 1


def test_kegagalan_memuat_tidak_menjatuhkan_layar(
    qtbot, auth, antrian_siap, terbitkan, monkeypatch
):
    terbitkan("A", 2)
    halaman = _halaman_admin(qtbot, auth, "admin")
    assert halaman.kartu_total.nilai.text() == "2"

    def rusak(*_a, **_k):
        raise RuntimeError("database mati")

    monkeypatch.setattr(halaman.dashboard, "ringkasan", rusak)
    halaman.muat_ulang()

    assert halaman.label_galat.isVisibleTo(halaman)
    assert "belum dapat dimuat" in halaman.label_galat.text()
    # Angka terakhir yang berhasil tetap tampil.
    assert halaman.kartu_total.nilai.text() == "2"
    # Pesan teknis tidak bocor ke layar.
    assert "database mati" not in halaman.label_galat.text()


# ---------------------------------------------------------------------
# Dashboard petugas
# ---------------------------------------------------------------------


def _halaman_petugas(qtbot, auth, buka_menu=None):
    from app.ui.dashboard.petugas_page import DashboardPetugasPage

    _masuk(auth, "cro")
    halaman = DashboardPetugasPage(
        DashboardService(auth), SettingsService(auth), buka_menu=buka_menu
    )
    qtbot.addWidget(halaman)
    return halaman


def _ikat(users: dict, loket: int) -> None:
    with session_scope() as s:
        s.execute(
            sa.update(User).where(User.id == users["CRO"]).values(default_counter_id=loket)
        )


def test_dashboard_petugas_peringatan_loket_belum_dipilih(qtbot, auth, antrian_siap):
    halaman = _halaman_petugas(qtbot, auth)

    assert halaman.label_peringatan.isVisibleTo(halaman)
    assert "Loket belum dipilih" in halaman.label_peringatan.text()
    assert halaman.label_nomor.text() == "—"


def test_dashboard_petugas_menampilkan_nomor_dan_antrean(
    qtbot, auth, antrian_siap, terbitkan, users
):
    from app.services.queue_service import QueueService

    loket = antrian_siap["loket"][0]
    _ikat(users, loket)
    terbitkan("A", 3)
    _masuk(auth, "cro")
    dipanggil = QueueService(auth).call_next(loket)

    halaman = _halaman_petugas(qtbot, auth)

    assert halaman.label_nomor.text() == dipanggil.queue_number
    assert halaman.label_sisa.text() == "2"
    assert halaman.tabel_berikutnya.rowCount() == 2
    assert "Dipanggil" in halaman.label_waktu.text()
    assert not halaman.label_peringatan.isVisibleTo(halaman)


def test_tombol_pelayanan_berpindah_menu(qtbot, auth, antrian_siap):
    dibuka: list[str] = []
    halaman = _halaman_petugas(qtbot, auth, buka_menu=dibuka.append)

    halaman.tombol_pelayanan.click()

    assert dibuka == ["Pelayanan"]


# ---------------------------------------------------------------------
# Menu per peran
# ---------------------------------------------------------------------


def test_menu_dashboard_per_peran(qtbot, auth, antrian_siap):
    from app.ui.main_window import MainWindow

    harapan = {
        "admin": ("Dashboard", True),
        "supervisor": ("Dashboard", True),
        "cro": ("Dashboard", False),
        "registration": ("Dashboard", False),
    }
    for peran, (judul, ada) in harapan.items():
        _masuk(auth, peran)
        jendela = MainWindow(auth)
        qtbot.addWidget(jendela)
        menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
        assert (judul in menu) is ada, peran
        assert ("Ringkasan Saya" in menu) is (peran in {"cro", "registration"}), peran


def test_buka_menu_berpindah_halaman(qtbot, auth, antrian_siap):
    from app.ui.main_window import MainWindow

    _masuk(auth, "admin")
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    jendela.buka_menu("Laporan")

    assert jendela.menu_aktif[jendela.navigasi.currentRow()].judul == "Laporan"
    # Menu yang tidak dimiliki sesi diabaikan, bukan galat.
    sebelum = jendela.navigasi.currentRow()
    jendela.buka_menu("Menu Tidak Ada")
    assert jendela.navigasi.currentRow() == sebelum


def test_tabel_pekerjaan_petugas_tampil_untuk_admin(qtbot, auth, antrian_siap, terbitkan):
    from app.services.queue_service import QueueService

    terbitkan("A", 1)
    _masuk(auth, "cro")
    QueueService(auth).call_next(antrian_siap["loket"][0])

    halaman = _halaman_admin(qtbot, auth, "admin")

    nama = [halaman.tabel_petugas.item(i, 0).text() for i in range(halaman.tabel_petugas.rowCount())]
    assert "Petugas Cro" in nama
    assert "Petugas Registration" in nama


def test_dashboard_pendaftaran_menampilkan_nomor_milik_sendiri(qtbot, auth, antrian_siap):
    from app.services.queue_service import QueueService
    from app.ui.dashboard.petugas_page import DashboardPendaftaranPage

    _masuk(auth, "registration")
    for _ in range(2):
        QueueService(auth).create_queue(antrian_siap["kategori"]["A"])
    halaman = DashboardPendaftaranPage(DashboardService(auth), SettingsService(auth))
    qtbot.addWidget(halaman)

    assert halaman.kartu_total.nilai.text() == "2"
    assert halaman.tabel.rowCount() == 2


def test_dashboard_petugas_muat_tanpa_scrollbar_di_1366x768(
    qtbot, auth, antrian_siap, terbitkan, users
):
    """Petugas tidak boleh menggulir; baris yang tak muat jadi "+N lainnya"."""
    from PySide6.QtWidgets import QAbstractScrollArea, QScrollArea

    from app.services.queue_service import QueueService
    from app.ui.main_window import MainWindow

    loket = antrian_siap["loket"][0]
    _ikat(users, loket)
    terbitkan("A", 14)
    _masuk(auth, "cro")
    layanan = QueueService(auth)
    for _ in range(4):
        dipanggil = layanan.call_next(loket)
        layanan.start_service(dipanggil.id)
        layanan.complete(dipanggil.id)
    layanan.call_next(loket)

    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    jendela.show()
    jendela.resize(1366, 768)
    baris = next(
        i for i, m in enumerate(jendela.menu_aktif) if m.judul == "Ringkasan Saya"
    )
    jendela.navigasi.setCurrentRow(baris)
    qtbot.wait(50)

    pembungkus = jendela.halaman.widget(baris)
    assert isinstance(pembungkus, QScrollArea)
    assert pembungkus.verticalScrollBar().maximum() == 0
    assert pembungkus.horizontalScrollBar().maximum() == 0
    halaman = pembungkus.widget()
    for tabel in (halaman.tabel_berikutnya, halaman.tabel_riwayat):
        assert isinstance(tabel, QAbstractScrollArea)
        assert tabel.verticalScrollBar().maximum() == 0
    assert halaman.label_lainnya_berikut.isVisibleTo(halaman)
    assert "lainnya" in halaman.label_lainnya_berikut.text()
