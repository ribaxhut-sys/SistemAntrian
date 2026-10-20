"""
Test antarmuka.

Yang diuji di sini bukan penampilannya, melainkan perilakunya: pesan
kesalahan tidak boleh berupa traceback, menu harus mengikuti hak akses,
dan dialog wajib tidak boleh dapat dilewati.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QPushButton, QStatusBar

from app.core.config import get_config
from app.core.errors import ValidationError
from app.models import UserRole
from app.services.master_data_service import MasterDataService
from app.services.user_service import UserService
from app.ui.common import PESAN_TAK_TERDUGA, pesan_untuk_user
from app.ui.login.change_password_dialog import ChangePasswordDialog
from app.ui.login.login_window import LoginWindow
from app.ui.main_window import SELANG_PERIKSA_KONEKSI_MS, MainWindow, PlaceholderPage
from app.ui.settings.dialogs import (
    CategoryDialog,
    CounterCategoryDialog,
    CounterDialog,
    UserDialog,
)
from app.ui.settings.master_data_page import MasterDataPage
from tests.conftest import TEST_PASSWORD


# ---------------------------------------------------------------------
# Penanganan pesan kesalahan
# ---------------------------------------------------------------------

def test_pesan_app_error_ditampilkan_apa_adanya():
    assert pesan_untuk_user(ValidationError("Nama loket belum diisi.")) == (
        "Nama loket belum diisi."
    )


@pytest.mark.parametrize(
    "kesalahan",
    [
        RuntimeError("UNIQUE constraint failed: queue.queue_number"),
        ValueError("invalid literal for int()"),
        KeyError("branch_id"),
    ],
)
def test_kesalahan_teknis_tidak_pernah_bocor_ke_petugas(kesalahan):
    """
    Pesan SQLite dan Python tidak boleh sampai ke layar. Petugas tidak
    dapat berbuat apa-apa dengannya, dan isinya membocorkan struktur data.
    """
    pesan = pesan_untuk_user(kesalahan)

    assert pesan == PESAN_TAK_TERDUGA
    assert "constraint" not in pesan.lower()
    assert "queue_number" not in pesan
    assert "Traceback" not in pesan


# ---------------------------------------------------------------------
# Layar masuk
# ---------------------------------------------------------------------

def test_login_berhasil_menutup_jendela(qtbot, auth):
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    jendela.input_username.setText("cro")
    jendela.input_password.setText(TEST_PASSWORD)
    jendela.coba_masuk()

    assert jendela.result() == QDialog.DialogCode.Accepted
    assert jendela.session is not None
    assert jendela.session.role is UserRole.CRO


def test_lupa_kata_sandi_admin_tersembunyi_sampai_gagal_berulang(qtbot, auth):
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)
    assert not jendela.tombol_lupa.isVisibleTo(jendela)

    jendela.input_username.setText("admin")
    for _ in range(2):
        jendela.input_password.setText("salah-salah")
        jendela.coba_masuk()
    assert not jendela.tombol_lupa.isVisibleTo(jendela)

    jendela.input_password.setText("salah-salah")
    jendela.coba_masuk()
    assert jendela.tombol_lupa.isVisibleTo(jendela)


def test_lupa_kata_sandi_tidak_muncul_bila_nama_berganti(qtbot, auth):
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    for nama in ("admin", "cro", "admin", "cro"):
        jendela.input_username.setText(nama)
        jendela.input_password.setText("salah-salah")
        jendela.coba_masuk()
    assert not jendela.tombol_lupa.isVisibleTo(jendela)


def test_layar_masuk_menawarkan_atur_komputer_tanpa_pemilih_mode(qtbot, auth):
    """Windows langsung login; pengaturan mesin tersedia sebagai aksi sekunder."""
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.tombol_atur_komputer.text() == "Atur komputer ini"
    assert not hasattr(jendela, "tombol_kembali")
    assert jendela.session is None
    assert not auth.is_authenticated


def test_kata_sandi_salah_tampil_sebaris_bukan_dialog(qtbot, auth):
    """
    Kotak dialog memaksa petugas menutupnya dulu sebelum mengetik ulang.
    Pesan sebaris jauh lebih cepat saat ada antrean orang menunggu.
    """
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    jendela.input_username.setText("cro")
    jendela.input_password.setText("salah-sekali")
    jendela.coba_masuk()

    assert jendela.pesan_kesalahan.isVisibleTo(jendela)
    assert jendela.pesan_kesalahan.text()
    assert not auth.is_authenticated
    assert jendela.result() != QDialog.DialogCode.Accepted


def test_kata_sandi_dikosongkan_setelah_gagal(qtbot, auth):
    """Petugas cukup mengetik ulang kata sandi, tidak perlu menghapusnya."""
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    jendela.input_username.setText("cro")
    jendela.input_password.setText("salah-sekali")
    jendela.coba_masuk()

    assert jendela.input_password.text() == ""
    assert jendela.input_username.text() == "cro"


def test_pesan_gagal_tidak_membocorkan_nama_pengguna_terdaftar(qtbot, auth):
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    jendela.input_username.setText("cro")
    jendela.input_password.setText("salah-sekali")
    jendela.coba_masuk()
    pesan_sandi_salah = jendela.pesan_kesalahan.text()

    jendela.input_username.setText("tidak-ada")
    jendela.input_password.setText(TEST_PASSWORD)
    jendela.coba_masuk()

    assert jendela.pesan_kesalahan.text() == pesan_sandi_salah


@pytest.mark.parametrize(
    ("username", "password", "potongan"),
    [("", TEST_PASSWORD, "Nama pengguna"), ("cro", "", "Kata sandi")],
)
def test_isian_kosong_ditolak_sebelum_menghubungi_service(
    qtbot, auth, username, password, potongan
):
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    jendela.input_username.setText(username)
    jendela.input_password.setText(password)
    jendela.coba_masuk()

    assert potongan in jendela.pesan_kesalahan.text()
    assert not auth.is_authenticated


def test_enter_pada_kata_sandi_langsung_mencoba_masuk(qtbot, auth):
    """Petugas mengetik nama, Tab, kata sandi, Enter — tanpa menyentuh mouse."""
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    jendela.input_username.setText("cro")
    jendela.input_password.setText(TEST_PASSWORD)
    qtbot.keyClick(jendela.input_password, Qt.Key.Key_Return)

    assert jendela.result() == QDialog.DialogCode.Accepted


def test_enter_saat_sandi_salah_tidak_mengatakan_belum_diisi(qtbot, auth):
    """
    Enter pada isian kata sandi memicu returnPressed DAN tombol MASUK
    bawaan dialog. Percobaan kedua melihat isian yang sudah dikosongkan
    setelah gagal, lalu menimpa pesan yang sebenarnya.
    """
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    jendela.input_username.setText("cro")
    jendela.input_password.setText("salah-sekali")
    qtbot.keyClick(jendela.input_password, Qt.Key.Key_Return)

    assert jendela.pesan_kesalahan.isVisibleTo(jendela)
    assert "belum diisi" not in jendela.pesan_kesalahan.text().lower()
    assert not auth.is_authenticated


def test_pesan_kesalahan_hilang_saat_kata_sandi_diketik(qtbot, auth):
    """Label sisa percobaan sebelumnya tidak boleh tetap menempel."""
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    jendela.input_username.setText("cro")
    jendela.coba_masuk()
    assert "belum diisi" in jendela.pesan_kesalahan.text().lower()

    jendela.input_password.setText("x")

    assert not jendela.pesan_kesalahan.isVisibleTo(jendela)


def test_login_enter_tidak_menjalankan_dua_kali(qtbot, auth):
    """
    Tombol MASUK tidak boleh menjadi default dialog. Enter pada isian
    sudah terhubung ke coba_masuk; default button akan menjalankannya lagi.
    """
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    assert not jendela.tombol_masuk.isDefault()
    assert not jendela.tombol_masuk.autoDefault()


def test_fokus_awal_pada_nama_pengguna(qtbot, auth):
    """Petugas dapat langsung mengetik tanpa mengklik isian terlebih dahulu."""
    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    # focusWidget() menunjukkan isian yang akan menerima ketikan di dalam
    # jendela ini. hasFocus() tidak dapat dipakai karena pada mode offscreen
    # tidak ada sistem jendela yang mengaktifkan jendela.
    assert jendela.focusWidget() is jendela.input_username


def test_kata_sandi_disamarkan(qtbot, auth):
    from PySide6.QtWidgets import QLineEdit

    jendela = LoginWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.input_password.echoMode() == QLineEdit.EchoMode.Password


# ---------------------------------------------------------------------
# Ganti kata sandi
# ---------------------------------------------------------------------

def test_ganti_kata_sandi_berhasil(qtbot, auth):
    auth.login("cro", TEST_PASSWORD)
    dialog = ChangePasswordDialog(auth)
    qtbot.addWidget(dialog)

    dialog.input_lama.setText(TEST_PASSWORD)
    dialog.input_baru.setText("sandibaru123")
    dialog.input_ulangi.setText("sandibaru123")
    dialog.simpan()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_ulangan_kata_sandi_tidak_sama_ditolak_di_ui(qtbot, auth):
    """Salah ketik bukan urusan service, jadi diperiksa di UI."""
    auth.login("cro", TEST_PASSWORD)
    dialog = ChangePasswordDialog(auth)
    qtbot.addWidget(dialog)

    dialog.input_lama.setText(TEST_PASSWORD)
    dialog.input_baru.setText("sandibaru123")
    dialog.input_ulangi.setText("sandibaru124")
    dialog.simpan()

    assert "tidak sama" in dialog.pesan_kesalahan.text()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_kata_sandi_lama_salah_ditampilkan_sebaris(qtbot, auth):
    auth.login("cro", TEST_PASSWORD)
    dialog = ChangePasswordDialog(auth)
    qtbot.addWidget(dialog)

    dialog.input_lama.setText("bukan-sandi-saya")
    dialog.input_baru.setText("sandibaru123")
    dialog.input_ulangi.setText("sandibaru123")
    dialog.simpan()

    assert dialog.pesan_kesalahan.isVisibleTo(dialog)
    assert dialog.pesan_kesalahan.text()
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_dialog_wajib_tidak_dapat_dibatalkan(qtbot, auth):
    """
    Akun berkata sandi bawaan tidak boleh lolos begitu saja dengan menekan
    Esc atau tombol silang.
    """
    auth.login("cro", TEST_PASSWORD)
    dialog = ChangePasswordDialog(auth, wajib=True)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.isVisible()
    dialog.reject()
    assert dialog.isVisible(), "dialog wajib seharusnya tetap terbuka"


def test_dialog_biasa_dapat_dibatalkan(qtbot, auth):
    auth.login("cro", TEST_PASSWORD)
    dialog = ChangePasswordDialog(auth, wajib=False)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.reject()
    assert not dialog.isVisible()
    assert dialog.result() == QDialog.DialogCode.Rejected


# ---------------------------------------------------------------------
# Jendela utama dan menu
# ---------------------------------------------------------------------

def test_admin_melihat_menu_data_master(qtbot, admin_auth):
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert "Data Master" in menu


def test_menu_pelayanan_aktif_hanya_untuk_admin_dan_cro(qtbot, auth):
    auth.login("admin", TEST_PASSWORD)
    admin = MainWindow(auth)
    qtbot.addWidget(admin)
    menu_admin = [
        admin.navigasi.item(i).text() for i in range(admin.navigasi.count())
    ]
    assert "Pelayanan Aktif" in menu_admin

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    petugas = MainWindow(auth)
    qtbot.addWidget(petugas)
    menu_petugas = [
        petugas.navigasi.item(i).text() for i in range(petugas.navigasi.count())
    ]
    # CRO melihatnya untuk mengambil alih nomor yang ditinggal petugas lain.
    assert "Pelayanan Aktif" in menu_petugas

    for peran in ("supervisor", "registration"):
        auth.logout()
        auth.login(peran, TEST_PASSWORD)
        lain = MainWindow(auth)
        qtbot.addWidget(lain)
        menu_lain = [lain.navigasi.item(i).text() for i in range(lain.navigasi.count())]
        assert "Pelayanan Aktif" not in menu_lain, peran


@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration", "display"])
def test_selain_admin_tidak_melihat_menu_data_master(qtbot, auth, peran):
    auth.login(peran, TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert "Data Master" not in menu


def test_layar_antrian_hanya_melihat_menunya_sendiri(qtbot, auth):
    """Komputer display menghadap publik dan tidak diawasi."""
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert menu == ["Layar Antrian"]


# ---------------------------------------------------------------------
# Mode kios layar antrian
# ---------------------------------------------------------------------

def test_akun_layar_antrian_masuk_mode_kios(qtbot, auth):
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.mode_kios


@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration", "admin"])
def test_peran_lain_tidak_masuk_mode_kios(qtbot, auth, users, peran):
    auth.login(peran, TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert not jendela.mode_kios


def test_kios_menyembunyikan_identitas_petugas_dan_tombol(qtbot, auth):
    """
    Pengunjung tidak boleh melihat nama petugas maupun tombol Keluar.

    Tombol Keluar yang terpampang di layar publik mengundang orang menutup
    aplikasi antrian.
    """
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.navigasi.parent() is None
    assert jendela.findChild(QPushButton) is None
    assert jendela.findChild(QFrame, "panelHeader") is None


def test_kios_tidak_menampilkan_lokasi_database(qtbot, auth):
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.findChild(QStatusBar) is None
    assert jendela.findChild(QLabel, "statusDatabase") is None
    assert getattr(jendela, "_pewaktu_db", None) is None


def test_kios_tetap_bersih_setelah_muat_ulang(qtbot, auth):
    """statusBar() membuat bilahnya sendiri bila belum ada."""
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    jendela.muat_ulang_halaman()

    assert jendela.findChild(QStatusBar) is None
    assert jendela.findChild(QLabel, "statusDatabase") is None


def test_bilah_status_loket_menampilkan_lokasi_database(qtbot, admin_auth):
    """A9: petugas harus melihat database yang sedang dipakai, bukan tebakan."""
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    cfg = get_config()
    label = jendela.findChild(QLabel, "statusDatabase")
    assert label is not None
    assert label.text() == "Database: ● tersambung"
    assert cfg.teks_lokasi in label.toolTip()
    assert "tidak terjangkau" not in label.text()
    if not cfg.memakai_sqlite:
        assert "PostgreSQL @" in label.toolTip()
        assert "queue.db" not in label.toolTip()
    assert jendela._pewaktu_db.isActive()
    assert jendela._pewaktu_db.interval() == SELANG_PERIKSA_KONEKSI_MS


def test_bilah_status_saat_tidak_terjangkau(qtbot, admin_auth):
    """A14: server mati tampil sebagai status, bukan traceback."""
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    jendela._tampilkan_status_database(False)

    label = jendela.findChild(QLabel, "statusDatabase")
    teks = label.toolTip()
    assert "tidak terjangkau" in teks
    assert str(get_config().teks_lokasi) in teks


def test_pita_server_muncul_setelah_dua_kegagalan_dan_hilang_saat_pulih(
    qtbot, auth, antrian_siap
):
    """Server mati menghentikan semua loket: petugas biasa pun harus melihatnya."""
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    pita = jendela.pita_database

    assert pita.isHidden()
    jendela._tampilkan_status_database(False)
    assert pita.isHidden(), "satu kegagalan bisa sekadar paket hilang"
    jendela._tampilkan_status_database(False)
    assert not pita.isHidden()
    assert "nomor manual" in pita.saran.text()
    assert "PostgreSQL" not in pita.saran.text(), "saran teknis hanya untuk admin"

    jendela._tampilkan_status_database(True)
    assert pita.isHidden()
    jendela._tampilkan_status_database(False)
    assert pita.isHidden(), "hitungan kegagalan mulai lagi sesudah pulih"


def test_pita_server_untuk_admin_menyebut_langkah_teknis(qtbot, admin_auth):
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    jendela._tampilkan_status_database(False)
    jendela._tampilkan_status_database(False)
    assert "PostgreSQL" in jendela.pita_database.saran.text()


def test_bilah_status_tetap_setelah_muat_ulang(qtbot, admin_auth):
    """F5 tidak boleh menghapus lokasi database dari bilah status."""
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    label = jendela.findChild(QLabel, "statusDatabase")

    jendela.muat_ulang_halaman()

    assert jendela.findChild(QLabel, "statusDatabase") is label
    assert str(get_config().teks_lokasi) in label.toolTip()


def test_judul_jendela_kios_tanpa_nama_petugas(qtbot, auth, users):
    """Judul terbaca di bilah tugas, yang juga di depan mata pengunjung."""
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    sesi = auth.require_session()
    assert sesi.full_name not in jendela.windowTitle()


def test_pintasan_keluar_dan_layar_penuh_terpasang_di_kios(qtbot, auth):
    """
    Layar kios tidak punya tombol Keluar. Petugas tetap harus bisa
    menutupnya dan keluar dari layar penuh tanpa mouse.
    """
    from PySide6.QtGui import QKeySequence, QShortcut

    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    kunci = {
        pintasan.key().toString(QKeySequence.SequenceFormat.PortableText)
        for pintasan in jendela.findChildren(QShortcut)
    }
    assert "Ctrl+Q" in kunci
    assert "F11" in kunci
    assert "F5" in kunci
    assert "Esc" in kunci
    assert "Ctrl+1" not in kunci


def test_esc_hanya_keluar_dari_layar_penuh(qtbot, auth):
    """Esc menurunkan layar penuh, tidak menutup aplikasi, dan tidak menyalakannya kembali."""
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    jendela.tampilkan()
    assert jendela.isFullScreen()

    jendela.keluar_layar_penuh()
    assert not jendela.isFullScreen()
    assert jendela.isVisible()

    jendela.keluar_layar_penuh()
    assert not jendela.isFullScreen()
    assert jendela.isVisible()


def test_esc_dari_layar_penuh_awal_menaruh_jendela_di_tengah(qtbot, auth):
    """
    Regresi: anjungan dan layar antrian dibuka langsung layar penuh, jadi
    posisi jendela biasanya tercatat (0, 0) sebelum jendela pernah tampil.
    Esc memulihkan titik itu — pojok kiri atas, dengan bilah judul lewat
    tepi atas layar sehingga jendela tidak dapat digeser dengan mouse.
    """
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    jendela.tampilkan()

    jendela.keluar_layar_penuh()

    area = jendela.screen().availableGeometry()
    bingkai = jendela.frameGeometry()
    assert bingkai.top() >= area.top(), "bilah judul lewat tepi atas layar"
    assert abs(bingkai.center().x() - area.center().x()) <= 2
    assert abs(bingkai.center().y() - area.center().y()) <= 2
    assert jendela.width() <= area.width()
    assert jendela.height() <= area.height()


def test_layar_petugas_dibuka_di_tengah(qtbot, admin_auth, monkeypatch):
    """Jendela petugas tampil di tengah layar, bukan di pojok kiri atas."""
    from app.ui import main_window

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    # Layar offscreen pada test lebih sempit dari jendela petugas, jadi
    # yang diperiksa adalah permintaannya, bukan letak akhirnya.
    panggilan = []
    monkeypatch.setattr(
        jendela, "_pusatkan", lambda area, ukuran: panggilan.append((area, ukuran))
    )

    ukuran = jendela.size()

    jendela.tampilkan()

    assert not jendela.isFullScreen()
    assert panggilan == [(main_window._area_layar_utama(), ukuran)]


def test_layar_petugas_dibuka_maksimal_dengan_ukuran_biasa_tercatat(
    qtbot, admin_auth, monkeypatch
):
    """
    Jendela kerja langsung memenuhi area kerja (taskbar tetap terlihat),
    sementara ukuran biasa yang dipusatkan tetap dicatat untuk restore.
    """
    from app.ui import main_window

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    ukuran_normal = jendela.size()
    panggilan = []
    monkeypatch.setattr(
        jendela, "_pusatkan", lambda area, ukuran: panggilan.append((area, ukuran))
    )

    jendela.tampilkan()

    assert jendela.isMaximized()
    assert not jendela.isFullScreen()
    assert panggilan == [(main_window._area_layar_utama(), ukuran_normal)]


def test_argumen_jendela_mempertahankan_jendela_biasa(qtbot, admin_auth):
    jendela = MainWindow(admin_auth, berjendela=True)
    qtbot.addWidget(jendela)

    jendela.tampilkan()

    assert not jendela.isMaximized()
    assert not jendela.isFullScreen()


def test_esc_dari_layar_penuh_kembali_ke_maksimal(qtbot, admin_auth):
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    jendela.tampilkan()
    qtbot.waitExposed(jendela)
    assert jendela.isMaximized()

    jendela.ganti_layar_penuh()
    assert jendela.isFullScreen()
    jendela.keluar_layar_penuh()

    assert not jendela.isFullScreen()
    assert jendela.isMaximized()


def test_ukuran_awal_mengikuti_area_kerja_monitor(admin_auth, monkeypatch):
    """Layar kecil dan skala Windows tinggi tidak boleh dilewati jendela."""
    from PySide6.QtCore import QRect, QSize

    from app.ui import main_window

    monkeypatch.setattr(
        main_window, "_area_layar_utama", lambda: QRect(0, 0, 1024, 768)
    )
    jendela = MainWindow(admin_auth)

    assert jendela.size() == QSize(942, 707)


def test_semua_halaman_kerja_memiliki_fallback_gulir(qtbot, admin_auth):
    """Form tetap dapat dicapai walau minimum layout melebihi ukuran layar."""
    from app.ui.main_window import HalamanAdaptif

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    for indeks in range(jendela.halaman.count()):
        halaman = jendela.halaman.widget(indeks)
        assert isinstance(halaman, HalamanAdaptif)
        assert halaman.widgetResizable()
        assert (
            halaman.horizontalScrollBarPolicy()
            is Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        assert halaman.verticalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_kepala_diringkas_pada_jendela_kecil(qtbot, admin_auth):
    """Identitas panjang tidak boleh mendorong menu dan form keluar jendela."""
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    jendela.resize(900, 650)
    jendela.show()
    qtbot.wait(10)

    assert not jendela._chip_pengguna.isVisibleTo(jendela)
    assert jendela._tombol_ganti_kata_sandi.text() == "Kata Sandi"

    jendela.resize(1280, 720)
    qtbot.wait(10)
    assert jendela._chip_pengguna.isVisibleTo(jendela)
    assert jendela._tombol_ganti_kata_sandi.text() == "Ganti Kata Sandi"


def test_jendela_admin_benar_benar_muat_pada_800_x_600(
    qtbot, admin_auth, monkeypatch
):
    """Minimum layout tidak boleh memaksa tepi jendela keluar monitor kecil."""
    from PySide6.QtCore import QRect

    from app.ui import main_window

    monkeypatch.setattr(
        main_window, "_area_layar_utama", lambda: QRect(0, 0, 870, 652)
    )
    # Jendela biasa: yang diuji adalah batas ukuran, bukan mode maksimal.
    jendela = MainWindow(admin_auth, berjendela=True)
    qtbot.addWidget(jendela)
    jendela.tampilkan()
    qtbot.wait(10)

    assert (jendela.width(), jendela.height()) == (800, 600)
    assert jendela.minimumSizeHint().width() <= 800
    assert jendela.minimumSizeHint().height() <= 600
    # Menu boleh muat atau bergulir, asal tidak memaksa jendela melebar.
    # Dengan font Windows sungguhan menunya muat pada 800 px; dulu test ini
    # mengandaikan huruf kotak selebar "M" yang selalu membuatnya bergulir.
    assert jendela.navigasi.minimumSizeHint().width() <= jendela.width()


def test_window_admin_penuh_tanpa_scrollbar_luar(qtbot, admin_auth):
    """
    Pada layar penuh 1366 x 768, monitor tersempit di kantor, halaman admin
    harus muat dalam satu layar.
    """
    lebar = 1366
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    jendela.show()
    jendela.resize(lebar, 768)
    qtbot.wait(10)

    assert jendela.navigasi._gulir.horizontalScrollBar().maximum() == 0
    bermasalah = []
    for indeks in range(jendela.halaman.count()):
        jendela.navigasi.setCurrentRow(indeks)
        qtbot.wait(1)
        halaman = jendela.halaman.widget(indeks)
        horizontal = halaman.horizontalScrollBar().maximum()
        vertikal = halaman.verticalScrollBar().maximum()
        if horizontal or vertikal:
            bermasalah.append(
                (jendela.menu_aktif[indeks].judul, horizontal, vertikal)
            )

    assert bermasalah == []


@pytest.mark.parametrize("server", [False, True], ids=["loket", "server"])
def test_form_admin_penuh_tanpa_scrollbar_form(qtbot, admin_auth, monkeypatch, server):
    """
    Area form ikut muat pada 1366 x 768, termasuk SETIAP kelompok
    Pengaturan, bukan hanya kelompok yang terbuka pertama kali.

    Varian server memunculkan Layanan Anjungan, yang hanya ada di komputer
    server (di lapangan selalu PostgreSQL), lengkap dengan perangkat yang
    terdaftar; di atas SQLite halaman itu tidak pernah ikut diperiksa.
    """
    from PySide6.QtWidgets import QScrollArea

    from app.ui.settings.settings_page import SettingsPage

    monkeypatch.setattr("app.ui.main_window._komputer_server", lambda: server)
    if server:
        from app.services import device_service

        monkeypatch.setattr(
            "app.services.kiosk_server.api_sudah_berjalan", lambda port=8765: False
        )
        from app.services.paket_suara import InfoPaket

        _status_palsu(
            monkeypatch,
            paket=InfoPaket("v1", "Microsoft David Desktop (en-US)", {"angka_1": "angka_1.wav"}),
        )
        for nomor, (nama, jenis) in enumerate(
            [
                ("Tablet Lobi", "anjungan"),
                ("Tablet Pintu", "anjungan"),
                ("Tablet Lantai 2", "anjungan"),
                ("TV Ruang Tunggu", "layar_antrian"),
            ]
        ):
            device_service.catat_kontak(
                f"perangkat-uji-{nomor:04d}", nama=nama, jenis=jenis,
                alamat_ip=f"192.168.1.{30 + nomor}", versi_nama="2.4.21",
            )

    lebar = 1366

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    jendela.show()
    jendela.resize(lebar, 768)
    qtbot.wait(10)

    bermasalah = []

    def periksa(halaman, judul_halaman):
        for gulir in halaman.findChildren(QScrollArea):
            if not gulir.isVisibleTo(jendela):
                continue
            horizontal = gulir.horizontalScrollBar().maximum()
            vertikal = gulir.verticalScrollBar().maximum()
            if horizontal or vertikal:
                bermasalah.append(
                    (
                        judul_halaman,
                        gulir.objectName() or type(gulir).__name__,
                        horizontal,
                        vertikal,
                    )
                )

    for indeks in range(jendela.halaman.count()):
        jendela.navigasi.setCurrentRow(indeks)
        qtbot.wait(1)
        halaman = jendela.halaman.widget(indeks)
        judul_halaman = jendela.menu_aktif[indeks].judul
        pengaturan = (
            [halaman] if isinstance(halaman, SettingsPage)
            else halaman.findChildren(SettingsPage)
        )
        if not pengaturan:
            # Dashboard adalah halaman pemantauan yang panjang dan sengaja
            # bergulir vertikal; yang dijaga di sini hanyalah form.
            if judul_halaman != "Dashboard":
                periksa(halaman, judul_halaman)
            continue
        rail = pengaturan[0].rail
        for baris in range(rail.count()):
            rail.setCurrentRow(baris)
            qtbot.wait(1)
            periksa(halaman, f"{judul_halaman} / {rail.item(baris).text()}")

    assert bermasalah == []


def test_esc_setelah_f11_kembali_ke_posisi_terakhir(qtbot, admin_auth):
    """Jendela yang sudah digeser petugas kembali ke tempatnya, bukan ke tengah."""
    from PySide6.QtCore import QRect

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    jendela.tampilkan()
    jendela.move(40, 60)
    sebelum = QRect(jendela.geometry())

    jendela.ganti_layar_penuh()
    jendela.keluar_layar_penuh()

    assert jendela.geometry() == sebelum


def test_kios_dibuka_layar_penuh(qtbot, auth):
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    jendela.tampilkan()

    assert jendela.isFullScreen()

    jendela.ganti_layar_penuh()
    assert not jendela.isFullScreen()

    jendela.ganti_layar_penuh()
    assert jendela.isFullScreen()


def test_petugas_tetap_melihat_bilah_atas(qtbot, admin_auth):
    """Mode kios tidak boleh ikut mengosongkan layar kerja petugas."""
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    assert jendela.findChild(QFrame, "panelHeader") is not None
    assert jendela.navigasi.parent() is not None


def test_navigasi_di_kepala_bukan_sidebar(qtbot, admin_auth):
    """Menu kerja menempel di kepala jendela, bukan kolom kiri."""
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    kepala = jendela.findChild(QFrame, "panelHeader")
    assert jendela.navigasi.parent() is kepala
    assert jendela.navigasi.parent() is not jendela.halaman.parent()


def test_supervisor_melihat_ringkasan(qtbot, auth):
    auth.login("supervisor", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert "Dashboard" in menu


def test_menu_pertama_langsung_terpilih(qtbot, admin_auth):
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    assert jendela.navigasi.currentRow() == 0
    assert jendela.halaman.currentIndex() == 0


def test_berpindah_menu_mengganti_halaman(qtbot, admin_auth):
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    jendela.navigasi.setCurrentRow(1)
    assert jendela.halaman.currentIndex() == 1


def test_klik_pil_navigasi_mengganti_halaman(qtbot, admin_auth):
    """Jalur klik pada pil harus sama dengan setCurrentRow yang dipakai tes lain."""
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    pil = jendela.navigasi.findChildren(QPushButton, "navPil")
    assert len(pil) >= 2
    qtbot.mouseClick(pil[1], Qt.MouseButton.LeftButton)
    assert jendela.halaman.currentIndex() == 1
    assert jendela.navigasi.currentRow() == 1


def test_pil_terpilih_tidak_menebal():
    """
    Lebar pil dihitung dari huruf keadaan biasa. Huruf yang lebih tebal
    saat terpilih tidak muat lagi: "Pengaduan" tampil "Pengaduar".
    """
    import re

    from app.ui.style import STYLESHEET

    tebal = {
        pemilih.strip(): bobot
        for pemilih, isi in re.findall(r"(QPushButton#navPil[^{]*)\{([^}]*)\}", STYLESHEET)
        for bobot in re.findall(r"font-weight:\s*(\d+)", isi)
    }
    assert set(tebal.values()) == {"600"}, tebal


def test_ctrl_angka_mengganti_menu(qtbot, admin_auth):
    """Petugas loket jarang menyentuh mouse; Ctrl+angka berpindah menu."""
    from PySide6.QtGui import QKeySequence, QShortcut

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    kunci = {
        pintasan.key().toString(QKeySequence.SequenceFormat.PortableText): pintasan
        for pintasan in jendela.findChildren(QShortcut)
    }
    assert "Ctrl+1" in kunci
    assert "Ctrl+2" in kunci

    kunci["Ctrl+2"].activated.emit()
    assert jendela.navigasi.currentRow() == 1
    assert jendela.halaman.currentIndex() == 1

    kunci["Ctrl+1"].activated.emit()
    assert jendela.navigasi.currentRow() == 0
    assert jendela.halaman.currentIndex() == 0


def test_peran_tanpa_menu_dinyatakan_terus_terang(qtbot, auth, users):
    """Lebih baik menyatakan tidak ada akses daripada layar kosong tanpa sebab."""
    from app.core.database import session_scope
    from app.models import User

    auth.login("supervisor", TEST_PASSWORD)
    # Akun yang masih wajib mengganti kata sandi kehilangan seluruh
    # kewenangannya, sehingga tidak ada satu pun menu yang tersedia.
    with session_scope() as session:
        session.get(User, users["SUPERVISOR"]).must_change_password = True
    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)

    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.navigasi.count() == 0
    assert isinstance(jendela.halaman.currentWidget(), PlaceholderPage)


def test_menutup_jendela_mengakhiri_sesi(qtbot, admin_auth):
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    assert admin_auth.is_authenticated
    jendela.close()
    assert not admin_auth.is_authenticated


def test_menutup_jendela_membatalkan_pemeriksa_anjungan_awal(
    qtbot, admin_auth, monkeypatch
):
    """Timer tertunda tidak boleh memulai QThread sesudah jendela ditutup."""
    from app.ui import main_window as modul

    monkeypatch.setattr(modul, "TUNDA_PERIKSA_ANJUNGAN_AWAL_MS", 20)
    # Pemeriksa hanya dipasang di komputer server atau pemasangan
    # PostgreSQL; tanpa ini hasil tes bergantung pada mesin yang menjalankan.
    monkeypatch.setattr(modul, "_komputer_server", lambda: True)
    monkeypatch.setattr(modul.MainWindow, "_periksa_api", lambda _self: None)
    dimulai = []
    monkeypatch.setattr(
        modul._PemeriksaAnjungan,
        "start",
        lambda pemeriksa: dimulai.append(pemeriksa),
    )

    jendela = modul.MainWindow(admin_auth)
    pewaktu = jendela._pewaktu_anjungan_awal
    assert pewaktu.isActive()

    jendela.close()
    assert not pewaktu.isActive()
    qtbot.wait(50)

    assert dimulai == []


# ---------------------------------------------------------------------
# Halaman data master
# ---------------------------------------------------------------------

@pytest.fixture
def halaman_master(qtbot, admin_auth):
    halaman = MasterDataPage(
        MasterDataService(admin_auth), UserService(admin_auth)
    )
    qtbot.addWidget(halaman)
    return halaman


def test_tab_data_master_lengkap(halaman_master):
    tab = [halaman_master.tab.tabText(i) for i in range(halaman_master.tab.count())]
    assert tab == ["Loket", "Jenis Layanan", "Akun Petugas", "Identitas Kantor"]


def test_tabel_loket_terisi_dari_database(halaman_master):
    tab = halaman_master.tab_loket
    tabel = tab.tabel
    kolom = {nama: i for i, nama in enumerate(tab.kolom)}

    assert tabel.rowCount() == 3
    assert tabel.item(0, kolom["Kode"]).text() == "LOKET-1"
    assert tabel.item(0, kolom["Status"]).text() == "Aktif"


def test_tabel_loket_menampilkan_semua_untuk_loket_tanpa_batasan(halaman_master):
    """
    Kosong berarti loket melayani SEMUA jenis layanan, bukan tidak ada.

    Kolom yang dibiarkan kosong akan dibaca terbalik oleh admin, lalu ia
    mengira loketnya belum siap dipakai.
    """
    tab = halaman_master.tab_loket
    kolom = {nama: i for i, nama in enumerate(tab.kolom)}

    assert tab.tabel.item(0, kolom["Jenis Layanan"]).text() == "Semua"


def test_tabel_jenis_layanan_menampilkan_contoh_nomor(halaman_master):
    """Petugas harus bisa melihat langsung nomor seperti apa yang dihasilkan."""
    tabel = halaman_master.tab_layanan.tabel
    assert tabel.rowCount() == 3
    assert tabel.item(0, 2).text() == "A"
    assert tabel.item(0, 3).text() == "A-001"


def test_tabel_akun_tidak_menampilkan_kata_sandi(halaman_master):
    tabel = halaman_master.tab_akun.tabel
    isi = " ".join(
        tabel.item(b, k).text()
        for b in range(tabel.rowCount())
        for k in range(tabel.columnCount())
        if tabel.item(b, k)
    )
    assert "scrypt" not in isi
    assert TEST_PASSWORD not in isi


def test_tombol_aksi_nonaktif_selama_belum_ada_baris_terpilih(halaman_master):
    """Mencegah petugas menekan tombol yang sudah pasti gagal."""
    tab = halaman_master.tab_loket
    tab.tabel.clearSelection()
    tab.tabel.setCurrentCell(-1, -1)
    tab._perbarui_tombol()

    assert all(not btn.isEnabled() for btn in tab._tombol_perlu_pilihan)


def test_memilih_baris_mengaktifkan_tombol_aksi(halaman_master):
    tab = halaman_master.tab_loket
    tab.tabel.setCurrentCell(0, 0)

    assert all(btn.isEnabled() for btn in tab._tombol_perlu_pilihan)
    assert tab.id_terpilih() == tab.data[0].id


def test_tombol_status_menyesuaikan_kondisi_baris(halaman_master, admin_auth):
    """Tombol harus menyebut tindakan yang akan terjadi, bukan status saat ini."""
    tab = halaman_master.tab_loket
    tab.tabel.setCurrentCell(0, 0)
    assert tab.tombol_status.text() == "Nonaktifkan"

    MasterDataService(admin_auth).set_counter_status(tab.data[0].id, False)
    tab.muat_ulang()
    tab.tabel.setCurrentCell(0, 0)
    assert tab.tombol_status.text() == "Aktifkan"


def test_muat_ulang_menampilkan_data_terbaru(halaman_master, admin_auth):
    MasterDataService(admin_auth).create_counter(code="LOKET-9", name="Loket 9")

    halaman_master.tab_loket.muat_ulang()
    assert halaman_master.tab_loket.tabel.rowCount() == 4


def test_pita_peringatan_tersembunyi_saat_semua_layanan_terlayani(halaman_master):
    for tab in (halaman_master.tab_loket, halaman_master.tab_layanan):
        assert not tab.peringatan.isVisibleTo(tab)


def _batasi_semua_loket(admin_auth, prefix: str = "A") -> None:
    """Buat keadaan "ada layanan yang tidak dilayani loket mana pun"."""
    master = MasterDataService(admin_auth)
    kategori = next(k for k in master.list_categories() if k.prefix == prefix)
    for loket in master.list_counters():
        master.set_counter_categories(loket.id, [kategori.id])


def test_pita_peringatan_menyebut_layanan_tanpa_loket(halaman_master, admin_auth):
    """
    Keadaan ini tidak ditolak aturan mana pun dan tidak terlihat di mana
    pun kecuali di sini: nomornya tetap terbit, dan tidak ada yang bisa
    memanggilnya.
    """
    _batasi_semua_loket(admin_auth)
    halaman_master.muat_ulang()

    pita = halaman_master.tab_loket.peringatan
    assert pita.isVisibleTo(halaman_master.tab_loket)
    assert "Pengaduan" in pita.text()
    assert "Informasi" in pita.text()
    assert "Konsultasi" not in pita.text()


def test_pita_peringatan_juga_tampil_di_tab_jenis_layanan(halaman_master, admin_auth):
    """Keadaannya lahir dari hubungan dua tab; keduanya harus mengabarkan."""
    _batasi_semua_loket(admin_auth)
    halaman_master.muat_ulang()

    tab = halaman_master.tab_layanan
    assert tab.peringatan.isVisibleTo(tab)
    assert "Pengaduan" in tab.peringatan.text()


def test_pita_peringatan_hilang_setelah_loket_melayani_lagi(
    halaman_master, admin_auth
):
    _batasi_semua_loket(admin_auth)
    halaman_master.muat_ulang()

    master = MasterDataService(admin_auth)
    master.set_counter_categories(master.list_counters()[0].id, [])
    halaman_master.muat_ulang()

    tab = halaman_master.tab_loket
    assert not tab.peringatan.isVisibleTo(tab)
    assert tab.peringatan.text() == ""


def test_berpindah_tab_menyegarkan_peringatan(halaman_master, admin_auth):
    """
    Tab Jenis Layanan dibuka sebelum pembatasan dibuat, jadi pitanya masih
    kosong sampai tabnya sendiri dimuat ulang.
    """
    _batasi_semua_loket(admin_auth)
    tab_layanan = halaman_master.tab_layanan
    assert not tab_layanan.peringatan.isVisibleTo(tab_layanan)

    halaman_master.tab.setCurrentWidget(tab_layanan)

    assert tab_layanan.peringatan.isVisibleTo(tab_layanan)


def test_tombol_naik_mati_pada_baris_teratas(halaman_master):
    tab = halaman_master.tab_layanan
    tab.tabel.setCurrentCell(0, 0)

    assert not tab.tombol_naik.isEnabled()
    assert tab.tombol_turun.isEnabled()


def test_tombol_turun_mati_pada_baris_terbawah(halaman_master):
    tab = halaman_master.tab_layanan
    tab.tabel.setCurrentCell(tab.tabel.rowCount() - 1, 0)

    assert tab.tombol_naik.isEnabled()
    assert not tab.tombol_turun.isEnabled()


def test_menggeser_jenis_layanan_mengubah_urutan_tabel(halaman_master):
    """Urutan baris di sini adalah urutan tombol di anjungan."""
    tab = halaman_master.tab_layanan
    tab.tabel.setCurrentCell(0, 0)

    tab.pindahkan(naik=False)

    assert [tab.data[b].prefix for b in range(len(tab.data))] == ["B", "A", "C"]


def test_pilihan_ikut_berpindah_setelah_digeser(halaman_master):
    """
    Tanpa ini tombolnya hanya bisa ditekan sekali: tabel disusun ulang,
    pilihannya hilang, dan admin harus mengklik barisnya lagi untuk setiap
    satu langkah.
    """
    tab = halaman_master.tab_layanan
    tab.tabel.setCurrentCell(0, 0)
    layanan = tab.data[0]

    tab.pindahkan(naik=False)

    assert tab.baris_terpilih() == 1
    assert tab.id_terpilih() == layanan.id


def test_identitas_kantor_terisi(halaman_master):
    assert halaman_master.tab_kantor.label_kode.text() == "PUSAT"
    assert halaman_master.tab_kantor.input_nama.text() == "Kantor Pelayanan"


# ---------------------------------------------------------------------
# Dialog isian
# ---------------------------------------------------------------------

def test_dialog_loket_menolak_isian_kosong(qtbot):
    dialog = CounterDialog()
    qtbot.addWidget(dialog)

    dialog.simpan()
    assert "Kode loket" in dialog.pesan_kesalahan.text()

    dialog.input_kode.setText("LOKET-4")
    dialog.simpan()
    assert "Nama loket" in dialog.pesan_kesalahan.text()


def test_dialog_loket_mengunci_kode_saat_mengubah(qtbot, halaman_master):
    """Kode melekat pada riwayat pemanggilan, jadi tidak boleh berubah."""
    loket = halaman_master.tab_loket.data[0]
    dialog = CounterDialog(counter=loket)
    qtbot.addWidget(dialog)

    assert not dialog.input_kode.isEnabled()
    assert dialog.input_kode.text() == loket.code
    assert dialog.input_nama.isEnabled()


def test_dialog_jenis_layanan_menampilkan_contoh_nomor_saat_diketik(qtbot):
    """Akibat prefix harus terlihat sebelum disimpan, bukan sesudahnya."""
    dialog = CategoryDialog()
    qtbot.addWidget(dialog)

    dialog.input_prefix.setText("d")
    assert "D-001" in dialog.contoh.text()

    dialog.input_prefix.clear()
    assert "—" in dialog.contoh.text()


def test_dialog_jenis_layanan_dapat_mengunci_prefix(qtbot, halaman_master):
    layanan = halaman_master.tab_layanan.data[0]
    dialog = CategoryDialog(category=layanan, prefix_terkunci=True)
    qtbot.addWidget(dialog)

    assert not dialog.input_prefix.isEnabled()
    assert dialog.input_nama.isEnabled()


def test_dialog_akun_menyediakan_peran_petugas(qtbot):
    """KIOSK bukan akun, jadi tidak ditawarkan saat membuat petugas."""
    dialog = UserDialog()
    qtbot.addWidget(dialog)

    tersedia = {dialog.pilih_peran.itemData(i) for i in range(dialog.pilih_peran.count())}
    assert UserRole.KIOSK not in tersedia
    assert tersedia == {r.value for r in UserRole if r is not UserRole.KIOSK}
    assert isinstance(dialog.peran, UserRole)
    assert dialog.peran is UserRole.ADMIN


def test_dialog_akun_menyembunyikan_kata_sandi_saat_mengubah(qtbot, halaman_master):
    """Kata sandi tidak dapat dilihat admin, hanya dapat disetel ulang."""
    akun = halaman_master.tab_akun.data[0]
    dialog = UserDialog(user=akun)
    qtbot.addWidget(dialog)

    assert dialog.input_password is None
    assert not dialog.input_username.isEnabled()


def test_dialog_akun_meminta_kata_sandi_saat_menambah(qtbot):
    dialog = UserDialog()
    qtbot.addWidget(dialog)

    dialog.input_username.setText("cro2")
    dialog.input_nama.setText("Petugas Dua")
    dialog.simpan()

    assert "Kata sandi" in dialog.pesan_kesalahan.text()


def test_tab_bar_tidak_memakai_panah_gulir(halaman_master):
    """
    Panah gulir Qt menutupi tab pertama dan terakhir padahal ruangnya cukup,
    sehingga tab "Loket" dan "Identitas Kantor" jadi setengah tertutup.
    """
    assert not halaman_master.tab.tabBar().usesScrollButtons()


def test_label_tab_admin_tidak_dielipsis_saat_dipilih(halaman_master):
    """Memilih tab panjang tidak boleh memotong ujung labelnya."""
    bar = halaman_master.tab.tabBar()
    label = ["Loket", "Jenis Layanan", "Akun Petugas", "Identitas Kantor"]

    assert bar.elideMode() is Qt.TextElideMode.ElideNone
    for indeks, teks in enumerate(label):
        halaman_master.tab.setCurrentIndex(indeks)
        assert halaman_master.tab.tabText(indeks) == teks
        assert bar.tabSizeHint(indeks).width() >= bar.fontMetrics().horizontalAdvance(teks)


def test_dialog_data_master_panjang_muat_di_monitor_dan_dapat_digulir(qtbot):
    """Daftar layanan panjang tidak boleh mendorong tombol Simpan keluar layar."""
    from types import SimpleNamespace

    loket = SimpleNamespace(name="Loket Uji", category_ids=())
    kategori = [
        SimpleNamespace(
            id=indeks,
            name=f"Jenis layanan panjang nomor {indeks}",
            prefix=f"X{indeks}",
            level=indeks % 3,
            punya_anak=False,
            is_active=True,
        )
        for indeks in range(1, 41)
    ]
    dialog = CounterCategoryDialog(counter=loket, categories=kategori)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    area = dialog.screen().availableGeometry()
    assert dialog.width() <= area.width() - 32
    assert dialog.height() <= area.height() - 32
    assert dialog._gulir_form.verticalScrollBar().maximum() > 0
    assert dialog.tombol_simpan.isVisibleTo(dialog)


# ---------------------------------------------------------------------
# Halaman penerbitan nomor (Phase 4)
# ---------------------------------------------------------------------

@pytest.fixture
def halaman_daftar(qtbot, auth, antrian_siap):
    from app.services.master_data_service import MasterDataService
    from app.services.queue_service import QueueService
    from app.ui.registration.registration_page import RegistrationPage

    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    halaman = RegistrationPage(QueueService(auth), MasterDataService(auth))
    qtbot.addWidget(halaman)
    return halaman


def test_tombol_dibuat_untuk_tiap_jenis_layanan_aktif(halaman_daftar):
    assert halaman_daftar.kisi.count() == 3
    assert [c.prefix for c in halaman_daftar.kategori] == ["A", "B", "C"]


def test_menerbitkan_nomor_menampilkan_hasil_besar(halaman_daftar, antrian_siap):
    """Nomor harus terbaca sekilas agar petugas dapat menyebutkannya."""
    assert not halaman_daftar.panel_hasil.isVisibleTo(halaman_daftar)

    halaman_daftar.terbitkan(antrian_siap["kategori"]["A"])

    assert halaman_daftar.panel_hasil.isVisibleTo(halaman_daftar)
    assert halaman_daftar.label_nomor.text() == "A-001"
    assert halaman_daftar.label_layanan.text() == "Konsultasi"
    assert "Antrean ke-1" in halaman_daftar.label_posisi.text()


def test_nomor_berurutan_saat_tombol_ditekan_berkali_kali(halaman_daftar, antrian_siap):
    kategori = antrian_siap["kategori"]["A"]
    for harapan in ("A-001", "A-002", "A-003"):
        halaman_daftar.terbitkan(kategori)
        assert halaman_daftar.label_nomor.text() == harapan


def test_pintasan_pendaftaran_tidak_bertambah_setelah_refresh(halaman_daftar):
    """F5 tidak boleh membuat shortcut angka ambigu dan berhenti bekerja."""
    from PySide6.QtGui import QShortcut

    awal = len(halaman_daftar.findChildren(QShortcut))
    halaman_daftar.muat_ulang()
    halaman_daftar.muat_ulang()

    assert len(halaman_daftar.findChildren(QShortcut)) == awal


def test_jalur_ui_pendaftaran_menahan_klik_ganda(
    qtbot, halaman_daftar, antrian_siap
):
    kategori = antrian_siap["kategori"]["A"]

    halaman_daftar._minta_terbitkan(kategori)
    halaman_daftar._minta_terbitkan(kategori)

    assert halaman_daftar.label_nomor.text() == "A-001"
    assert len(halaman_daftar.queue.list_waiting()) == 1
    qtbot.wait(550)


def test_sinyal_dipancarkan_saat_nomor_terbit(qtbot, halaman_daftar, antrian_siap):
    """Layar display (Phase 5) akan menumpang sinyal ini."""
    with qtbot.waitSignal(halaman_daftar.nomor_terbit, timeout=1000) as tertangkap:
        halaman_daftar.terbitkan(antrian_siap["kategori"]["B"])

    assert tertangkap.args[0].queue_number == "B-001"


def test_jenis_layanan_nonaktif_hilang_dari_pilihan(
    halaman_daftar, antrian_siap, auth, master_service
):
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master_service.set_category_status(antrian_siap["kategori"]["C"], False)
    auth.logout()
    auth.login("registration", TEST_PASSWORD)

    halaman_daftar.muat_ulang()
    assert [c.prefix for c in halaman_daftar.kategori] == ["A", "B"]


# ---------------------------------------------------------------------
# Panel pelayanan CRO (Phase 4)
# ---------------------------------------------------------------------

@pytest.fixture
def halaman_layanan(qtbot, auth, antrian_siap):
    from app.services.master_data_service import MasterDataService
    from app.services.queue_service import QueueService
    from app.services.settings_service import SettingsService
    from app.services.survey_service import SurveyService
    from app.ui.queue.service_page import ServicePage

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = ServicePage(
        QueueService(auth),
        MasterDataService(auth),
        SurveyService(auth),
        SettingsService(auth),
    )
    qtbot.addWidget(halaman)
    return halaman


def test_pilihan_loket_terisi(halaman_layanan):
    assert halaman_layanan.pilih_loket.count() == 3
    assert halaman_layanan.loket_id is not None


def test_tanpa_antrian_hanya_tombol_panggil_yang_aktif(halaman_layanan):
    assert halaman_layanan.tombol_panggil.isEnabled()
    assert all(not btn.isEnabled() for btn in halaman_layanan.aksi.values())
    assert halaman_layanan.label_nomor.text() == "—"


def test_tombol_menyesuaikan_status_sepanjang_alur(halaman_layanan, terbitkan, auth):
    """
    Tombol yang tidak sah dinonaktifkan, bukan disembunyikan, agar posisinya
    tidak berpindah-pindah setiap status berubah.
    """
    terbitkan("A", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()

    halaman_layanan.panggil_berikutnya()
    assert halaman_layanan.label_nomor.text() == "A-001"
    assert not halaman_layanan.tombol_panggil.isEnabled()
    assert halaman_layanan.aksi["mulai_layani"].isEnabled()
    assert halaman_layanan.aksi["panggil_ulang"].isEnabled()
    assert not halaman_layanan.aksi["selesai"].isEnabled()

    halaman_layanan.mulai_melayani()
    assert halaman_layanan.aksi["selesai"].isEnabled()
    assert halaman_layanan.aksi["tunda"].isEnabled()
    assert not halaman_layanan.aksi["mulai_layani"].isEnabled()

    halaman_layanan.tunda()
    assert halaman_layanan.aksi["lanjutkan"].isEnabled()
    assert not halaman_layanan.aksi["selesai"].isEnabled()

    halaman_layanan.lanjutkan()
    halaman_layanan.selesaikan()
    assert halaman_layanan.label_nomor.text() == "—"
    assert halaman_layanan.tombol_panggil.isEnabled()


def test_lewati_sementara_masuk_daftar_dan_dapat_dipanggil_kembali(
    halaman_layanan, terbitkan, monkeypatch
):
    monkeypatch.setattr(
        "app.ui.queue.service_page.konfirmasi", lambda *_args, **_kwargs: True
    )
    terbitkan("A", 2)
    halaman_layanan.muat_ulang()

    halaman_layanan.panggil_berikutnya()
    assert halaman_layanan.aksi["lewati"].isEnabled()
    halaman_layanan.lewati_sementara()

    assert halaman_layanan.label_nomor.text() == "—"
    assert halaman_layanan.tombol_panggil.isEnabled()
    tab = halaman_layanan.tab_kanan
    assert tab.tabText(tab.indexOf(halaman_layanan.panel_dilewati)) == "Dilewati (1)"
    assert halaman_layanan.tabel_dilewati.item(0, 0).text() == "A-001"
    assert halaman_layanan.tabel_dilewati.item(0, 2).text() == "1x"

    halaman_layanan.tabel_dilewati.selectRow(0)
    assert halaman_layanan.tombol_panggil_kembali.isEnabled()
    halaman_layanan.panggil_kembali_dilewati()

    assert halaman_layanan.label_nomor.text() == "A-001"
    assert "2x" in halaman_layanan.label_status.text()
    assert halaman_layanan.tabel_dilewati.rowCount() == 0
    assert not halaman_layanan.tombol_panggil.isEnabled()


def test_nomor_dilewati_dapat_ditandai_tidak_hadir_dari_tabnya(
    halaman_layanan, terbitkan, monkeypatch
):
    monkeypatch.setattr(
        "app.ui.queue.service_page.konfirmasi", lambda *_args, **_kwargs: True
    )
    terbitkan("A", 2)
    halaman_layanan.muat_ulang()
    halaman_layanan.panggil_berikutnya()
    halaman_layanan.lewati_sementara()
    halaman_layanan.panggil_berikutnya()

    assert not halaman_layanan.tombol_dilewati_tidak_hadir.isEnabled()
    halaman_layanan.tabel_dilewati.selectRow(0)
    assert not halaman_layanan.tombol_panggil_kembali.isEnabled()
    assert halaman_layanan.tombol_dilewati_tidak_hadir.isEnabled()
    assert halaman_layanan.tombol_dilewati_batal.isEnabled()

    halaman_layanan.tidak_hadir_dilewati()

    assert halaman_layanan.tabel_dilewati.rowCount() == 0
    tab = halaman_layanan.tab_kanan
    assert tab.tabText(tab.indexOf(halaman_layanan.panel_dilewati)) == "Dilewati (0)"
    assert halaman_layanan.label_nomor.text() == "A-002", "loket tidak terganggu"


def test_pilihan_dilewati_tidak_berpindah_ke_nomor_lain(
    halaman_layanan, terbitkan, monkeypatch
):
    monkeypatch.setattr(
        "app.ui.queue.service_page.konfirmasi", lambda *_args, **_kwargs: True
    )
    terbitkan("A", 2)
    halaman_layanan.muat_ulang()
    for _ in range(2):
        halaman_layanan.panggil_berikutnya()
        halaman_layanan.lewati_sementara()
    assert halaman_layanan.tabel_dilewati.rowCount() == 2

    # Nomor terpilih (A-002, terbaru di atas) ditutup dari komputer lain.
    halaman_layanan.tabel_dilewati.selectRow(0)
    terpilih = halaman_layanan._id_dilewati_terpilih()
    halaman_layanan.queue.cancel(terpilih)
    halaman_layanan.muat_ulang()

    assert halaman_layanan.tabel_dilewati.rowCount() == 1
    assert halaman_layanan._id_dilewati_terpilih() is None
    assert not halaman_layanan.tombol_panggil_kembali.isEnabled()
    assert not halaman_layanan.tombol_dilewati_batal.isEnabled()


def test_panggil_ulang_menaikkan_hitungan_pada_layar(halaman_layanan, terbitkan, auth):
    terbitkan("A", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()

    halaman_layanan.panggil_berikutnya()
    halaman_layanan.panggil_ulang()

    assert "2x" in halaman_layanan.label_status.text()


def test_daftar_menunggu_tampil_di_tabel(halaman_layanan, terbitkan, auth):
    terbitkan("A", 2)
    terbitkan("B", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()

    tabel = halaman_layanan.tabel
    assert tabel.rowCount() == 3
    assert tabel.item(0, 0).text() == "A-001"
    assert tabel.item(2, 0).text() == "B-001"
    assert "menit" in tabel.item(0, 3).text()


def test_klik_kartu_papan_menyaring_daftar_menunggu(
    halaman_layanan, terbitkan, auth, antrian_siap
):
    terbitkan("A", 2)
    terbitkan("B", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()
    papan = halaman_layanan.papan_tunggu
    assert halaman_layanan.tabel.rowCount() == 3

    papan.pilih(antrian_siap["kategori"]["B"])

    tabel = halaman_layanan.tabel
    assert tabel.rowCount() == 1
    assert tabel.item(0, 0).text() == "B-001"
    # Judul tab tetap menghitung seluruh antrian.
    assert "(3)" in halaman_layanan.tab_kanan.tabText(
        halaman_layanan.tab_kanan.indexOf(halaman_layanan.panel_menunggu)
    )

    papan.pilih(None)
    assert halaman_layanan.tabel.rowCount() == 3


def test_tombol_istirahat_sejajar_dengan_kotak_pilihan(halaman_layanan):
    """Kolom tombol tidak boleh bergeser terhadap LOKET dan JENIS LAYANAN."""
    from PySide6.QtWidgets import QApplication

    from app.ui.style import STYLESHEET

    QApplication.instance().setStyleSheet(STYLESHEET)
    halaman_layanan.show()
    QApplication.processEvents()

    def posisi(w):
        return w.mapTo(halaman_layanan, w.rect().topLeft()).y(), w.height()

    assert posisi(halaman_layanan.tombol_istirahat) == posisi(
        halaman_layanan.pilih_loket
    )
    assert posisi(halaman_layanan.pilih_kategori) == posisi(
        halaman_layanan.pilih_loket
    )


def test_kartu_berikutnya_menampilkan_nomor_dan_ringkasan(
    qtbot, halaman_layanan, terbitkan, auth
):
    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.resize(900, 1100)
    halaman_layanan.show()
    halaman_layanan.muat_ulang()  # halaman terlihat: dimuat di latar

    kartu = halaman_layanan.kartu_berikutnya
    qtbot.waitUntil(
        lambda: "A-001" in " ".join(kartu.baris_tampil), timeout=5000
    )
    assert "A-002" in " ".join(kartu.baris_tampil)


def _terbit_mandiri(auth, antrian_siap, perangkat: str):
    """Nomor prioritas yang dicentang pengunjung di anjungan."""
    from app.services.queue_service import QueueService

    auth.logout()
    auth.mulai_sesi_kios()
    return QueueService(auth).create_queue(
        antrian_siap["kategori"]["A"], perangkat=perangkat, prioritas_mandiri=True
    )


def test_petugas_mencabut_prioritas_dari_daftar(
    halaman_layanan, terbitkan, auth, antrian_siap
):
    terbitkan("A", 1)
    _terbit_mandiri(auth, antrian_siap, "tab-ui-1")
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()
    tabel = halaman_layanan.tabel
    # Prioritas lebih dulu dan berbintang.
    assert tabel.item(0, 0).text().startswith("★")
    assert not halaman_layanan.tombol_cabut_prioritas.isEnabled()

    tabel.setCurrentCell(0, 0)
    assert halaman_layanan.tombol_cabut_prioritas.isEnabled()
    halaman_layanan._cabut_prioritas(halaman_layanan._nomor_menunggu_terpilih())

    assert not tabel.item(0, 0).text().startswith("★")
    assert tabel.item(0, 0).text() == "A-001"


def test_petugas_tidak_memiliki_tombol_tandai_prioritas(halaman_layanan):
    assert not hasattr(halaman_layanan, "tombol_tandai_prioritas")


def test_pita_prioritas_tampil_pada_nomor_aktif(
    halaman_layanan, auth, antrian_siap
):
    _terbit_mandiri(auth, antrian_siap, "tab-ui-2")
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()

    halaman_layanan.panggil_berikutnya()

    assert halaman_layanan.pil_prioritas.isVisibleTo(halaman_layanan)
    assert "PRIORITAS" in halaman_layanan.pil_prioritas.text()
    assert "mohon periksa" in halaman_layanan.pil_prioritas.text()
    assert halaman_layanan.tombol_ubah_prioritas.isVisibleTo(halaman_layanan)


def test_tabel_menyusut_setelah_dipanggil(halaman_layanan, terbitkan, auth):
    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()
    assert halaman_layanan.tabel.rowCount() == 3

    halaman_layanan.panggil_berikutnya()
    assert halaman_layanan.tabel.rowCount() == 2


def test_menekan_panggil_saat_nonaktif_tidak_melakukan_apa_pun(
    halaman_layanan, terbitkan, auth
):
    """Pintasan papan ketik dapat menembus tombol yang tampak nonaktif."""
    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()

    halaman_layanan.panggil_berikutnya()
    halaman_layanan.panggil_berikutnya()  # tidak boleh mengambil A-002

    assert halaman_layanan.label_nomor.text() == "A-001"
    assert halaman_layanan.tabel.rowCount() == 1


def test_menu_petugas_cro_dan_pendaftaran_tidak_tumpang_tindih(qtbot, auth, antrian_siap):
    """Satu peran tidak boleh mendapat dua menu untuk pekerjaan yang sama."""
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    # "Pengaduan" BUKAN pekerjaan yang sama dengan "Pelayanan":
    # panel pelayanan menulis lembar untuk nomor yang sedang di depan meja,
    # layar ini mencari lembar milik hari-hari sebelumnya.
    assert menu == [
        "Pelayanan",
        "Ringkasan Saya",
        "Survey Kepuasan",
        "Pengaduan",
        # Untuk mengambil alih nomor yang ditinggal petugas lain.
        "Pelayanan Aktif",
        # Riwayat milik CRO sendiri; disaring lagi oleh ReportService.
        "Laporan Saya",
        "Tampilan",
    ]

    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    jendela2 = MainWindow(auth)
    qtbot.addWidget(jendela2)
    menu2 = [jendela2.navigasi.item(i).text() for i in range(jendela2.navigasi.count())]
    assert menu2 == ["Terbitkan Nomor", "Ringkasan Saya", "Tampilan"]


# ---------------------------------------------------------------------
# Tampilan panel petugas
# ---------------------------------------------------------------------

def test_kartu_antrian_berganti_warna_mengikuti_status(
    halaman_layanan, terbitkan, auth
):
    """
    Petugas mengenali keadaan loketnya dari warna sebelum sempat membaca.
    Warna yang tidak ikut berubah membuat kartu berbohong: hijau padahal
    orangnya belum datang.
    """
    from app.ui.style import SUCCESS, WARNING

    terbitkan("A", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()

    halaman_layanan.panggil_berikutnya()
    assert WARNING in halaman_layanan.panel_antrian.styleSheet()

    halaman_layanan.mulai_melayani()
    assert SUCCESS in halaman_layanan.panel_antrian.styleSheet()


def test_loket_istirahat_terlihat_pada_kartu_dan_tombolnya(halaman_layanan):
    from app.ui.style import WARNING

    halaman_layanan.alihkan_istirahat()

    assert "istirahat" in halaman_layanan.label_status.text().lower()
    assert WARNING in halaman_layanan.panel_antrian.styleSheet()
    assert halaman_layanan.tombol_istirahat.property("variant") == "warning"
    assert not halaman_layanan.tombol_panggil.isEnabled()

    halaman_layanan.alihkan_istirahat()
    assert halaman_layanan.tombol_istirahat.property("variant") == ""
    assert halaman_layanan.tombol_panggil.isEnabled()


def test_penghitung_waktu_berjalan_saat_melayani_dan_kosong_saat_menganggur(
    halaman_layanan, terbitkan, auth
):
    """
    Penghitung ini yang membuat petugas tahu ada pengunjung yang sudah
    lama dipanggil tetapi belum juga datang, tanpa perlu melihat jam.
    """
    terbitkan("A", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()
    assert halaman_layanan.label_durasi.text() == ""

    halaman_layanan.panggil_berikutnya()
    halaman_layanan.mulai_melayani()
    assert "00:" in halaman_layanan.label_durasi.text()

    halaman_layanan.selesaikan()
    assert halaman_layanan.label_durasi.text() == ""


def test_penghitung_waktu_tidak_menyentuh_database(halaman_layanan, terbitkan, auth):
    """
    Dipanggil sedetik sekali di setiap loket. Satu query per detik per
    loket akan membebani server hanya untuk menampilkan angka yang sudah
    dapat dihitung dari data di tangan.
    """
    terbitkan("A", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()
    halaman_layanan.panggil_berikutnya()

    class ServiceTerlarang:
        def __getattr__(self, nama):
            raise AssertionError(f"penghitung waktu memanggil service: {nama}")

    queue, master = halaman_layanan.queue, halaman_layanan.master
    halaman_layanan.queue = ServiceTerlarang()
    halaman_layanan.master = ServiceTerlarang()
    try:
        halaman_layanan._perbarui_durasi()
    finally:
        halaman_layanan.queue, halaman_layanan.master = queue, master

    assert halaman_layanan.label_durasi.text()


def test_baris_terdepan_daftar_tunggu_ditandai(halaman_layanan, terbitkan, auth):
    """Nomor yang akan terpanggil bila PANGGIL BERIKUTNYA ditekan sekarang."""
    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()

    assert halaman_layanan.tabel.item(0, 0).font().bold()
    assert not halaman_layanan.tabel.item(1, 0).font().bold()


def test_lama_menunggu_diberi_warna_menurut_ambangnya(halaman_layanan):
    """
    Angka menit tidak berarti apa-apa tanpa pembanding. Warnanya yang
    memberi tahu petugas siapa yang sudah terlalu lama duduk.
    """
    from PySide6.QtWidgets import QTableWidgetItem

    from app.ui.queue.service_page import (
        TUNGGU_LAMA_MENIT,
        TUNGGU_SANGAT_LAMA_MENIT,
    )
    from app.ui.style import DANGER, TEXT_MUTED, WARNING

    def warna(menit: int) -> str:
        sel = QTableWidgetItem("x")
        halaman_layanan._gayai_sel(sel, baris=1, kolom=3, menit=menit)
        return sel.foreground().color().name().upper()

    assert warna(0) == TEXT_MUTED.upper()
    assert warna(TUNGGU_LAMA_MENIT) == WARNING.upper()
    assert warna(TUNGGU_SANGAT_LAMA_MENIT) == DANGER.upper()


def test_daftar_kosong_menjelaskan_dirinya(halaman_layanan):
    """Tabel kosong tanpa satu barispun terbaca seperti aplikasi menggantung."""
    assert halaman_layanan.label_jumlah.text() == "0"
    assert halaman_layanan.label_kosong.isVisibleTo(halaman_layanan)
    assert not halaman_layanan.tabel.isVisibleTo(halaman_layanan)


def test_jumlah_menunggu_ikut_terhitung(halaman_layanan, terbitkan, auth):
    terbitkan("A", 2)
    terbitkan("B", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_layanan.muat_ulang()

    assert halaman_layanan.label_jumlah.text() == "3"
    assert halaman_layanan.tabel.isVisibleTo(halaman_layanan)


# ---------------------------------------------------------------------
# Survey kepuasan (Phase 6)
# ---------------------------------------------------------------------

@pytest.fixture
def halaman_survey(qtbot, auth, antrian_siap):
    from app.services.settings_service import SettingsService
    from app.services.survey_service import SurveyService
    from app.ui.survey.survey_page import SurveyPage

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = SurveyPage(SurveyService(auth), SettingsService(auth))
    qtbot.addWidget(halaman)
    return halaman


def test_daftar_survey_kosong_saat_belum_ada_pelayanan_selesai(halaman_survey):
    assert halaman_survey.daftar.count() == 0
    assert not halaman_survey.tombol_kirim.isEnabled()


def test_antrian_selesai_muncul_di_layar_survey(
    halaman_survey, layani_sampai_selesai
):
    antrian = layani_sampai_selesai()
    halaman_survey.muat_ulang()

    assert halaman_survey.daftar.count() == 1
    assert antrian.queue_number in halaman_survey.daftar.item(0).text()


def test_kirim_aktif_setelah_nomor_dan_nilai_dipilih(
    halaman_survey, layani_sampai_selesai
):
    layani_sampai_selesai()
    halaman_survey.muat_ulang()

    halaman_survey.daftar.setCurrentRow(0)
    assert not halaman_survey.tombol_kirim.isEnabled()

    halaman_survey.rating.pilih(5)
    assert halaman_survey.tombol_kirim.isEnabled()


def test_nomor_hilang_dari_layar_setelah_dinilai(
    halaman_survey, layani_sampai_selesai
):
    layani_sampai_selesai()
    halaman_survey.muat_ulang()
    halaman_survey.daftar.setCurrentRow(0)
    halaman_survey.rating.pilih(4)

    halaman_survey.kirim()

    assert halaman_survey.daftar.count() == 0


def test_layar_survey_mati_saat_pengaturan_dinonaktifkan(
    qtbot, auth, antrian_siap, admin_auth
):
    """Administrator dapat mematikan survey tanpa mengubah kode."""
    from app.services.settings_service import SettingsService
    from app.services.survey_service import SurveyService
    from app.ui.survey.survey_page import SurveyPage

    SettingsService(admin_auth).set("survey.enabled", "false")

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = SurveyPage(SurveyService(auth), SettingsService(auth))
    qtbot.addWidget(halaman)

    assert halaman.daftar.count() == 0
    assert not halaman.rating.isEnabled()
    assert "dinonaktifkan" in halaman.catatan.text()


# ---------------------------------------------------------------------
# Kegagalan menghubungi database
# ---------------------------------------------------------------------

def test_kegagalan_database_menyebut_tujuan_tanpa_kata_sandi(app_config, monkeypatch):
    """
    Petugas harus tahu database mana yang tidak terjangkau.

    Kata sandi TIDAK boleh ikut tampil: pesan ini muncul di layar yang bisa
    dilihat siapa saja yang kebetulan lewat.
    """
    from app.core import config as config_module
    from app.main import _laporkan_kegagalan_database

    monkeypatch.setenv(
        "ANTRIAN_DB_URL", "postgresql+psycopg://antrian:rahasia@server:5432/antrian"
    )
    config_module.reset_config()
    cfg = config_module.get_config()

    dicetak: list[str] = []
    monkeypatch.setattr(
        "builtins.print", lambda *a, **k: dicetak.append(" ".join(str(x) for x in a))
    )

    _laporkan_kegagalan_database(cfg, berjendela=False)

    pesan = "\n".join(dicetak)
    assert "server" in pesan
    assert "antrian" in pesan
    assert "rahasia" not in pesan


def test_kegagalan_database_menunjuk_file_log(app_config, monkeypatch):
    """Traceback tidak ditampilkan, jadi petugas harus diberi tahu letaknya."""
    from app.main import _laporkan_kegagalan_database

    dicetak: list[str] = []
    monkeypatch.setattr(
        "builtins.print", lambda *a, **k: dicetak.append(" ".join(str(x) for x in a))
    )

    _laporkan_kegagalan_database(app_config, berjendela=False)

    assert "app.log" in "\n".join(dicetak)


# ---------------------------------------------------------------------
# Pengaturan aplikasi
# ---------------------------------------------------------------------

@pytest.fixture
def halaman_pengaturan(qtbot, admin_auth, seeded):
    from app.services.settings_service import SettingsService
    from app.ui.settings.settings_page import SettingsPage

    halaman = SettingsPage(SettingsService(admin_auth))
    qtbot.addWidget(halaman)
    return halaman


def test_pengaturan_terisi_dari_nilai_tersimpan(halaman_pengaturan):
    from app.services.settings_service import SKEMA

    # Setiap pengaturan yang dikenali harus punya kontrolnya di layar,
    # kalau tidak ia hanya bisa diubah lewat database. Kecuali yang
    # sengaja disembunyikan: nilainya ditulis sistem sendiri secara
    # berpasangan, dan formulir ini hanya menyetel satu kunci sekaligus.
    assert set(halaman_pengaturan.baris) == {p.kunci for p in SKEMA if p.tampil}
    assert halaman_pengaturan.baris["ticket.printer"].nilai() == "pdf"
    assert halaman_pengaturan.baris["survey.enabled"].nilai() == "true"
    assert halaman_pengaturan.baris["display.next_count"].nilai() == "3"


def test_daftar_putar_tidak_berubah_hanya_karena_dibuka(
    qtbot, admin_auth, seeded, tmp_path, monkeypatch
):
    from PySide6.QtCore import Qt

    from app.services.settings_service import SettingsService
    from app.ui.settings import settings_page

    folder = tmp_path / "media" / "kiosk"
    folder.mkdir(parents=True)
    for nama in ("a.jpg", "b.mp4", "c.mp4"):
        (folder / nama).write_bytes(b"isi")
    monkeypatch.setattr(settings_page, "daftar_media_kios",
                        lambda: sorted(folder.iterdir()))
    halaman = settings_page.SettingsPage(SettingsService(admin_auth))
    qtbot.addWidget(halaman)
    baris = halaman.baris["kiosk.daftar_putar"]
    daftar = baris.kontrol

    # Belum diatur: semua tercentang, nilainya tetap kosong.
    assert daftar.daftar.count() == 3
    assert baris.nilai() == ""
    assert not baris.sudah_berubah()

    # Matikan b.mp4, lalu naikkan c.mp4 ke paling atas.
    daftar.daftar.item(1).setCheckState(Qt.CheckState.Unchecked)
    daftar.daftar.setCurrentRow(2)
    daftar._geser(-1)
    daftar._geser(-1)

    assert baris.nilai() == '["c.mp4", "a.jpg"]'
    assert baris.sudah_berubah()


def test_pengaturan_berkas_anjungan_punya_tombol_pilih(halaman_pengaturan):
    from PySide6.QtWidgets import QPushButton

    baris = halaman_pengaturan.baris["kiosk.welcome_file"]
    pilih = baris.findChild(QPushButton, "tombolPilihBerkas")
    assert pilih is not None
    assert "pilih" in pilih.text().lower()


def test_memilih_berkas_menyalin_ke_folder_media(
    qtbot, halaman_pengaturan, tmp_path, monkeypatch
):
    """Dialog hanya memilih; yang tersimpan adalah nama berkas di media/kiosk."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFileDialog, QPushButton

    from app.ui import settings as settings_ui
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    sumber = tmp_path / "poster.png"
    sumber.write_bytes(b"png")
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)
    monkeypatch.setattr(
        settings_ui.settings_page, "folder_media_kios", lambda: folder
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(sumber), ""),
    )

    pilih = halaman_pengaturan.baris["kiosk.welcome_file"].findChild(
        QPushButton, "tombolPilihBerkas"
    )
    qtbot.mouseClick(pilih, Qt.MouseButton.LeftButton)

    assert halaman_pengaturan.baris["kiosk.welcome_file"].nilai() == "poster.png"
    assert halaman_pengaturan.baris["kiosk.welcome_kind"].nilai() == "media"
    assert (folder / "poster.png").is_file()
    # Jenis tampilan yang ikut berganti tetap terhitung sebagai perubahan
    # yang harus disimpan. Dianggap sebagai nilai tersimpan, tombol Simpan
    # akan diam saja dan pilihannya hilang begitu layar ditutup.
    assert halaman_pengaturan.berubah()["kiosk.welcome_kind"] == "media"


def test_menyimpan_perubahan_pengaturan(halaman_pengaturan, admin_auth):
    from app.services.settings_service import SettingsService

    halaman_pengaturan.baris["survey.enabled"].kontrol.setChecked(False)
    halaman_pengaturan.baris["display.next_count"].kontrol.setValue(5)
    halaman_pengaturan.simpan()

    layanan = SettingsService(admin_auth)
    assert layanan.get("survey.enabled") == "false"
    assert layanan.get("display.next_count") == "5"


def test_membatalkan_mengembalikan_nilai_tersimpan(halaman_pengaturan, admin_auth):
    from app.services.settings_service import SettingsService

    halaman_pengaturan.baris["display.next_count"].kontrol.setValue(9)
    halaman_pengaturan.muat_ulang()

    assert halaman_pengaturan.baris["display.next_count"].nilai() == "3"
    assert SettingsService(admin_auth).get("display.next_count") == "3"


def test_tombol_batal_meminta_konfirmasi(halaman_pengaturan, monkeypatch):
    """Ketukan salah pada Batalkan tidak boleh membuang pekerjaan diam-diam."""
    ditanya = []

    def _konfirmasi(*_args, **_kwargs):
        ditanya.append(True)
        return True

    monkeypatch.setattr(
        "app.ui.settings.settings_page.konfirmasi", _konfirmasi
    )
    halaman_pengaturan.baris["display.next_count"].kontrol.setValue(9)
    halaman_pengaturan.tombol_batal.click()

    assert ditanya
    assert halaman_pengaturan.baris["display.next_count"].nilai() == "3"


def test_menolak_batal_mempertahankan_perubahan(halaman_pengaturan, monkeypatch):
    monkeypatch.setattr(
        "app.ui.settings.settings_page.konfirmasi", lambda *_a, **_k: False
    )
    halaman_pengaturan.baris["display.next_count"].kontrol.setValue(9)
    halaman_pengaturan.tombol_batal.click()

    assert halaman_pengaturan.baris["display.next_count"].nilai() == "9"
    assert halaman_pengaturan.tombol_simpan.isEnabled()


def test_pilihan_cara_cetak_tidak_dapat_diisi_bebas(halaman_pengaturan):
    """Kontrolnya daftar pilihan, sehingga nilai asal tidak mungkin diketik."""
    kotak = halaman_pengaturan.baris["ticket.printer"].kontrol
    nilai = [kotak.itemData(i) for i in range(kotak.count())]

    assert nilai == ["pdf", "system", "none"]


def test_kotak_angka_menahan_nilai_di_luar_batas(halaman_pengaturan):
    """Batasnya diambil dari skema yang sama dengan yang dipakai service."""
    kotak = halaman_pengaturan.baris["dashboard.refresh_seconds"].kontrol
    kotak.setValue(1)

    assert kotak.value() == 5


def test_setiap_kelompok_pengaturan_punya_halamannya_sendiri(halaman_pengaturan):
    """
    Dua puluh dua pengaturan pada satu halaman gulung hanya dapat
    ditemukan dengan menggulung sampai ketemu. Daftar kelompok di kiri
    adalah daftar isinya, dan setiap kelompok berdiri sebagai halaman
    tersendiri.
    """
    from app.services.settings_service import kelompok_pengaturan

    nama_kelompok = list(kelompok_pengaturan())

    assert halaman_pengaturan.rail.count() == len(nama_kelompok)
    assert [
        halaman_pengaturan.rail.item(i).text()
        for i in range(halaman_pengaturan.rail.count())
    ] == nama_kelompok

    halaman_pengaturan.rail.setCurrentRow(2)
    assert halaman_pengaturan.tumpukan.currentIndex() == 2


def test_pengaturan_menandai_baris_yang_belum_disimpan(halaman_pengaturan):
    """
    "Apa saja yang tadi saya ubah" harus dapat dijawab dengan melihat,
    bukan dengan mengingat — terutama pada layar yang perubahannya baru
    berlaku setelah layar lain dimuat ulang.
    """
    baris = halaman_pengaturan.baris["display.next_count"]
    assert baris.property("berubah") in (None, "false")
    assert not halaman_pengaturan.tombol_simpan.isEnabled()

    baris.kontrol.setValue(7)

    assert baris.property("berubah") == "true"
    assert halaman_pengaturan.berubah() == {"display.next_count": "7"}
    assert halaman_pengaturan.tombol_simpan.isEnabled()
    assert "1" in halaman_pengaturan.pesan.text()

    # Dikembalikan ke nilai semula: penandanya ikut padam, bukan menetap
    # sampai disimpan.
    baris.kontrol.setValue(3)
    assert baris.property("berubah") == "false"
    assert not halaman_pengaturan.tombol_simpan.isEnabled()


def test_pengaturan_bersih_lagi_setelah_disimpan(halaman_pengaturan):
    halaman_pengaturan.baris["display.next_count"].kontrol.setValue(6)
    halaman_pengaturan.simpan()

    assert halaman_pengaturan.berubah() == {}
    assert not halaman_pengaturan.tombol_simpan.isEnabled()
    assert halaman_pengaturan.baris["display.next_count"].property("berubah") == "false"


def test_pencarian_menyaring_baris_dan_kelompoknya(halaman_pengaturan):
    """
    Pencarian menyaring seluruh kelompok, bukan hanya yang sedang terbuka.
    Kalau tidak, hasil yang berada di kelompok lain tampak seperti tidak
    ada hasil sama sekali.
    """
    halaman_pengaturan.cari.setText("backup")

    tampil = [
        kunci
        for kunci, baris in halaman_pengaturan.baris.items()
        if not baris.isHidden()
    ]
    assert set(tampil) == {
        "backup.auto_enabled",
        "backup.pg_dump_path",
        "backup.retention_days",
        "backup.salinan_folder",
    }

    terlihat = [
        halaman_pengaturan.rail.item(i).text()
        for i in range(halaman_pengaturan.rail.count())
        if not halaman_pengaturan.rail.item(i).isHidden()
    ]
    assert len(terlihat) == 1
    assert terlihat[0].startswith("Backup")
    # Jumlah hasilnya ikut disebut, supaya daftar kiri berfungsi sebagai
    # daftar hasil.
    assert "4" in terlihat[0]

    halaman_pengaturan.cari.setText("")
    assert not halaman_pengaturan.baris["ticket.footer"].isHidden()


def test_pencarian_tanpa_hasil_menjelaskan_dirinya(halaman_pengaturan):
    """Layar kosong tanpa keterangan terbaca sebagai layar yang gagal termuat."""
    halaman_pengaturan.cari.setText("zzz tidak ada")

    assert (
        halaman_pengaturan.tumpukan.currentWidget()
        is halaman_pengaturan._halaman_kosong
    )
    assert "zzz tidak ada" in halaman_pengaturan.label_kosong.text()


def test_satuan_angka_ditulis_di_dalam_kotaknya(halaman_pengaturan):
    """
    Satuan yang menempel pada angkanya terbaca bersama angka itu; pada
    nama pengaturannya, ia terbaca beberapa detik sebelumnya.
    """
    assert halaman_pengaturan.baris["display.rotate_seconds"].kontrol.suffix() == " detik"
    # Dan nilai terkecil yang punya arti khusus ditulis dengan artinya,
    # bukan sebagai angka 0 yang harus dicari dulu maksudnya.
    assert (
        halaman_pengaturan.baris["display.list_font_size"].kontrol.specialValueText()
        == "Otomatis"
    )


def test_menu_pengaturan_hanya_untuk_admin(qtbot, auth, antrian_siap):
    from app.ui.main_window import MainWindow

    for peran in ("cro", "supervisor", "registration", "display"):
        auth.logout()
        auth.login(peran, TEST_PASSWORD)
        jendela = MainWindow(auth)
        qtbot.addWidget(jendela)
        menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
        assert "Pengaturan" not in menu


def test_admin_melihat_menu_pengaturan(qtbot, admin_auth, monkeypatch):
    # Ditetapkan, bukan disimpulkan dari jenis database: suite yang
    # dijalankan di atas PostgreSQL lokal membuat komputer ini terbaca
    # sebagai server.
    monkeypatch.setattr("app.ui.main_window._komputer_server", lambda: False)
    from app.ui.main_window import MainWindow

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]

    assert "Pengaturan" in menu
    assert "Layanan Anjungan" not in menu


def test_layanan_anjungan_hanya_di_komputer_server(qtbot, admin_auth, monkeypatch):
    """API anjungan berjalan di pemilik database; komputer lain tidak diberi menunya."""
    monkeypatch.setattr("app.ui.main_window._komputer_server", lambda: True)
    monkeypatch.setattr(
        "app.services.kiosk_server.api_sudah_berjalan", lambda port=8765: False
    )
    _status_palsu(monkeypatch)
    from app.ui.main_window import MainWindow

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]

    assert "Layanan Anjungan" in menu
    assert jendela._label_api.text() == "API anjungan: ● mati"


def _status_palsu(
    monkeypatch, *, api=False, terdaftar=False, firewall=False, apk=None, berjaga=True,
    paket=None,
):
    from app.services.kiosk_server import StatusTugas, perintah_api
    from app.ui.settings import layanan_anjungan_page as halaman_modul

    program, argumen = perintah_api()
    monkeypatch.setattr(
        halaman_modul,
        "periksa_status",
        lambda: halaman_modul.StatusLayanan(
            api=api,
            tugas=StatusTugas(terdaftar, program, " ".join(argumen), berjaga=berjaga),
            firewall=firewall,
            apk=apk,
            paket=paket,
        ),
    )


def test_halaman_layanan_anjungan_membuat_dan_menyimpan_token(
    qtbot, monkeypatch, app_config
):
    monkeypatch.delenv("ANTRIAN_KIOS_API_TOKEN", raising=False)
    monkeypatch.setattr(
        "app.services.kiosk_server.muat_token_pengguna", lambda: ""
    )
    _status_palsu(monkeypatch)
    from app.services.kiosk_server import muat_token
    from app.ui.settings.layanan_anjungan_page import LayananAnjunganPage

    halaman = LayananAnjunganPage()
    qtbot.addWidget(halaman)

    assert len(halaman.token.text()) >= 64
    assert halaman.token.isReadOnly()
    # Tersimpan saat itu juga, supaya API saat Windows menyala dapat membacanya.
    monkeypatch.delenv("ANTRIAN_KIOS_API_TOKEN", raising=False)
    assert muat_token() == halaman.token.text()


def test_halaman_layanan_anjungan_menunjukkan_yang_belum_dipasang(
    qtbot, monkeypatch, app_config
):
    _status_palsu(monkeypatch)
    from app.ui.settings.layanan_anjungan_page import LayananAnjunganPage

    halaman = LayananAnjunganPage()
    qtbot.addWidget(halaman)
    qtbot.waitUntil(lambda: halaman._status is not None, timeout=3000)

    assert halaman.pasang.text().replace("&&", "&") == "Pasang & nyalakan"
    assert not halaman.hapus.isEnabled()
    assert not halaman.catatan.isHidden()
    assert "Mati" in halaman.baris_api.teks.text()


def test_halaman_layanan_anjungan_normal_bila_semua_terpasang(
    qtbot, monkeypatch, app_config
):
    _status_palsu(monkeypatch, api=True, terdaftar=True, firewall=True)
    from app.ui.settings.layanan_anjungan_page import LayananAnjunganPage

    halaman = LayananAnjunganPage()
    qtbot.addWidget(halaman)
    qtbot.waitUntil(lambda: halaman._status is not None, timeout=3000)

    assert halaman.pasang.text().replace("&&", "&") == "Pasang ulang & nyalakan ulang"
    assert halaman.hapus.isEnabled()
    assert halaman.catatan.isHidden()
    assert halaman.baris_tugas.lencana.text() == "Normal"


def test_tugas_lama_tanpa_pemeriksa_berkala_diminta_pasang_ulang(
    qtbot, monkeypatch, app_config
):
    """Tugas versi lama tidak menyalakan lagi API yang berhenti di tengah hari."""
    _status_palsu(monkeypatch, api=True, terdaftar=True, firewall=True, berjaga=False)
    from app.ui.settings.layanan_anjungan_page import LayananAnjunganPage

    halaman = LayananAnjunganPage()
    qtbot.addWidget(halaman)
    qtbot.waitUntil(lambda: halaman._status is not None, timeout=3000)

    assert halaman.baris_tugas.lencana.text() == "Belum"
    assert "Pasang ulang" in halaman.baris_tugas.teks.text()


def test_dialog_survey_menyimpan_penilaian(qtbot, auth, layani_sampai_selesai):
    """Jalur pengisian yang dibuka petugas CRO untuk pengunjung."""
    from app.services.survey_service import SurveyService
    from app.ui.survey.survey_dialog import SurveyDialog

    antrian = layani_sampai_selesai()
    layanan = SurveyService(auth)
    dialog = SurveyDialog(layanan, antrian)
    qtbot.addWidget(dialog)

    # Belum boleh terkirim sebelum pengunjung memilih nilai.
    assert not dialog.tombol_kirim.isEnabled()

    dialog.rating.pilih(4)
    dialog.masukan.setPlainText("Petugasnya membantu sekali.")
    assert dialog.tombol_kirim.isEnabled()

    dialog.kirim()

    tersimpan = layanan.get_by_queue(antrian.id)
    assert tersimpan is not None
    assert tersimpan.rating == 4
    assert tersimpan.feedback == "Petugasnya membantu sekali."


def test_dialog_survey_menolak_masukan_terlalu_panjang(
    qtbot, auth, layani_sampai_selesai
):
    """Ditolak di layar dengan pesan sebaris, bukan lewat kegagalan database."""
    from app.services.survey_service import SurveyService
    from app.ui.survey.survey_dialog import SurveyDialog

    antrian = layani_sampai_selesai()
    layanan = SurveyService(auth)
    dialog = SurveyDialog(layanan, antrian)
    qtbot.addWidget(dialog)

    dialog.rating.pilih(3)
    dialog.masukan.setPlainText("x" * 1001)
    dialog.kirim()

    # isVisibleTo, bukan isVisible: dialognya sendiri tidak pernah
    # ditampilkan pada test, dan anak dari widget tersembunyi selalu
    # terbaca tidak terlihat.
    assert dialog.pesan.isVisibleTo(dialog)
    assert "terlalu panjang" in dialog.pesan.text()
    assert layanan.get_by_queue(antrian.id) is None


def test_layar_backup_menampilkan_berkas_dan_audit(
    qtbot, admin_auth, antrian_siap, mesin_backup_tersedia
):
    from app.services.backup_service import BackupService
    from app.ui.settings.backup_page import BackupPage

    layanan = BackupService(admin_auth)
    halaman = BackupPage(layanan)
    qtbot.addWidget(halaman)

    assert halaman.tabel_backup.rowCount() == 0
    assert not halaman.tombol_pulihkan.isEnabled()

    layanan.backup()
    halaman.muat_ulang()

    assert halaman.tabel_backup.rowCount() == 1
    # Backup yang barusan dibuat harus tampak juga pada jejak aktivitas.
    tindakan = [
        halaman.tabel_audit.item(b, 2).text()
        for b in range(halaman.tabel_audit.rowCount())
    ]
    assert "BACKUP" in tindakan


def test_menu_backup_hanya_untuk_admin(qtbot, auth, antrian_siap):
    from app.ui.main_window import MainWindow

    for peran in ("cro", "supervisor", "registration"):
        auth.logout()
        auth.login(peran, TEST_PASSWORD)
        jendela = MainWindow(auth)
        qtbot.addWidget(jendela)
        menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
        assert "Backup" not in menu


def test_ringkasan_harian_menampilkan_angka(qtbot, auth, antrian_siap, terbitkan):
    from app.services.dashboard_service import DashboardService
    from app.services.settings_service import SettingsService
    from app.ui.dashboard.dashboard_page import DashboardPage

    terbitkan("A", 2)
    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    halaman = DashboardPage(DashboardService(auth), SettingsService(auth))
    qtbot.addWidget(halaman)

    assert halaman.kartu_total.nilai.text() == "2"
    assert halaman.kartu_belum.nilai.text() == "2"
    assert halaman.kartu_menunggu.nilai.text() == "—"


def test_pengingat_batas_panggilan_muncul_setelah_batasnya(
    halaman_layanan, terbitkan
):
    """Petugas diingatkan, bukan dihalangi."""
    terbitkan("A")
    halaman_layanan.muat_ulang()
    halaman_layanan.panggil_berikutnya()

    assert not halaman_layanan.label_batas.isVisibleTo(halaman_layanan)

    halaman_layanan.panggil_ulang()
    halaman_layanan.panggil_ulang()

    assert halaman_layanan.label_batas.isVisibleTo(halaman_layanan)
    assert "Tidak Hadir" in halaman_layanan.label_batas.text()
    assert halaman_layanan.aksi["lewati"].property("variant") == "warning"
    # Tombol Panggil Ulang tetap menyala: nomor yang sudah terbit tidak
    # dapat diterbitkan ulang, jadi pengunjung yang lambat tidak boleh
    # kehilangan gilirannya karena hitungan.
    assert halaman_layanan.aksi["panggil_ulang"].isEnabled()


def test_pengingat_hilang_setelah_mulai_dilayani(halaman_layanan, terbitkan):
    terbitkan("A")
    halaman_layanan.muat_ulang()
    halaman_layanan.panggil_berikutnya()
    halaman_layanan.panggil_ulang()
    halaman_layanan.panggil_ulang()

    halaman_layanan.mulai_melayani()

    assert not halaman_layanan.label_batas.isVisibleTo(halaman_layanan)


# ---------------------------------------------------------------------
# Hasil survey untuk supervisor
# ---------------------------------------------------------------------

def test_hasil_survey_menampilkan_masukan_pengunjung(
    qtbot, auth, cro_survey, layani_sampai_selesai
):
    """Yang tidak terbaca di mana pun sebelumnya adalah tulisan pengunjung."""
    from app.services.survey_service import SurveyService
    from app.ui.dashboard.survey_result_page import SurveyResultPage

    antrian = layani_sampai_selesai()
    cro_survey.submit(antrian.id, 2, "Menunggu terlalu lama.")

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    halaman = SurveyResultPage(SurveyService(auth))
    qtbot.addWidget(halaman)

    assert halaman.tabel.rowCount() == 1
    assert halaman.tabel.item(0, 1).text() == antrian.queue_number
    assert "2" in halaman.tabel.item(0, 4).text()
    assert halaman.tabel.item(0, 5).text() == "Menunggu terlalu lama."


def test_hasil_survey_kosong_dinyatakan_terus_terang(qtbot, auth, antrian_siap):
    from app.services.survey_service import SurveyService
    from app.ui.dashboard.survey_result_page import SurveyResultPage

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    halaman = SurveyResultPage(SurveyService(auth))
    qtbot.addWidget(halaman)

    assert halaman.tabel.rowCount() == 0
    assert "Belum ada penilaian" in halaman.label_kosong.text()


def test_hasil_survey_tanpa_masukan_tetap_tampil(
    qtbot, auth, cro_survey, layani_sampai_selesai
):
    """Masukan boleh dikosongkan; barisnya tetap harus ada."""
    from app.services.survey_service import SurveyService
    from app.ui.dashboard.survey_result_page import SurveyResultPage

    cro_survey.submit(layani_sampai_selesai().id, 5)

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    halaman = SurveyResultPage(SurveyService(auth))
    qtbot.addWidget(halaman)

    assert halaman.tabel.rowCount() == 1
    assert halaman.tabel.item(0, 5).text() == ""


def test_menu_hasil_survey_hanya_untuk_supervisor(qtbot, auth, antrian_siap):
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert menu == ["Pengaduan", "Dashboard", "Laporan", "Hasil Survey", "Tampilan"]

    for peran in ("cro", "admin", "registration"):
        auth.logout()
        auth.login(peran, TEST_PASSWORD)
        lain = MainWindow(auth)
        qtbot.addWidget(lain)
        menu_lain = [lain.navigasi.item(i).text() for i in range(lain.navigasi.count())]
        assert "Hasil Survey" not in menu_lain


def test_supervisor_hanya_memantau(qtbot, auth, antrian_siap):
    """Supervisor memantau; tidak ada satu pun menu yang mengubah antrian."""
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]

    # "Pengaduan" ikut ada, dan itu tetap memantau: supervisor
    # boleh MEMBACA lembar pengaduan, tidak boleh menulis maupun
    # menghapusnya — menulis milik CRO, menghapus milik ADMIN.
    assert menu == ["Pengaduan", "Dashboard", "Laporan", "Hasil Survey", "Tampilan"]


def test_timer_hanya_berjalan_pada_halaman_yang_terlihat(qtbot, auth, antrian_siap):
    from app.ui.dashboard.dashboard_page import DashboardPage
    from app.ui.main_window import MainWindow
    from app.ui.notes.note_page import NotePage

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    jendela.show()

    catatan = jendela.findChild(NotePage)
    ringkasan = jendela.findChild(DashboardPage)
    qtbot.waitUntil(lambda: catatan.penyegar.isActive())
    assert not ringkasan.penyegar.isActive()

    jendela.navigasi.setCurrentRow(1)
    qtbot.waitUntil(lambda: ringkasan.penyegar.isActive())
    assert not catatan.penyegar.isActive()


def test_tombol_minta_survey_aktif_setelah_pelayanan_selesai(
    halaman_layanan, antrian_siap, terbitkan
):
    assert not halaman_layanan.tombol_survey.isEnabled()

    terbitkan("A")
    halaman_layanan.muat_ulang()
    halaman_layanan.panggil_berikutnya()
    halaman_layanan.mulai_melayani()
    halaman_layanan.selesaikan()

    assert halaman_layanan.tombol_survey.isEnabled()
    assert "belum dinilai" in halaman_layanan.label_survey.text()


def test_pelayanan_terlihat_memuat_nomor_baru_di_worker(
    qtbot, halaman_layanan, terbitkan
):
    halaman_layanan.show()
    qtbot.waitUntil(lambda: halaman_layanan._pekerja_data is None, timeout=3000)
    halaman_layanan.pewaktu_data.stop()

    terbitkan("A")
    halaman_layanan.muat_ulang()

    # Label diisi dari sinyal `berhasil`, pekerja dilepas pada `finished` yang
    # datang sesudahnya; di mesin lambat keduanya tidak terjadi bersamaan.
    qtbot.waitUntil(
        lambda: halaman_layanan.label_jumlah.text() == "1"
        and halaman_layanan._pekerja_data is None,
        timeout=3000,
    )


def test_refresh_gagal_mempertahankan_keadaan_terakhir(
    qtbot, halaman_layanan, terbitkan, monkeypatch
):
    terbitkan("A")
    halaman_layanan.muat_ulang()
    halaman_layanan.panggil_berikutnya()
    nomor_lama = halaman_layanan.antrian.queue_number

    halaman_layanan.show()
    qtbot.waitUntil(lambda: halaman_layanan._pekerja_data is None, timeout=3000)
    halaman_layanan.pewaktu_data.stop()

    def gagal(_loket_id):
        raise RuntimeError("koneksi uji terputus")

    monkeypatch.setattr(halaman_layanan, "_ambil_snapshot", gagal)
    halaman_layanan.muat_ulang()
    qtbot.waitUntil(lambda: halaman_layanan._pekerja_data is None, timeout=3000)

    assert halaman_layanan.antrian.queue_number == nomor_lama
    assert halaman_layanan.label_sinkron.isVisibleTo(halaman_layanan)
    assert not halaman_layanan.tombol_panggil.isEnabled()


def test_refresh_selesai_tidak_membuka_tombol_saat_aksi_masih_berjalan(
    halaman_layanan,
):
    """Worker data dan worker aksi boleh selesai dalam urutan apa pun."""

    class PekerjaSelesai:
        def deleteLater(self):
            pass

    halaman_layanan._set_sibuk(True)
    halaman_layanan._pekerja_data = PekerjaSelesai()
    halaman_layanan._pekerja_aksi = object()

    halaman_layanan._bersihkan_pekerja_data()

    assert halaman_layanan._sedang_sibuk
    assert not halaman_layanan.tombol_panggil.isEnabled()
    halaman_layanan._pekerja_aksi = None


def test_aksi_worker_menangkap_id_antrian_sebelum_dijalankan(
    halaman_layanan, monkeypatch
):
    """Refresh paralel tidak boleh memindahkan aksi ke nomor lain."""
    from types import SimpleNamespace

    lama = SimpleNamespace(id=101)
    baru = SimpleNamespace(id=202)
    halaman_layanan.antrian = lama
    halaman_layanan.aksi["panggil_ulang"].setEnabled(True)
    tertunda = {}

    def simpan_aksi(aksi, *_args, **_kwargs):
        tertunda["aksi"] = aksi

    monkeypatch.setattr(halaman_layanan, "_jalankan", simpan_aksi)
    monkeypatch.setattr(halaman_layanan.queue, "recall", lambda queue_id: queue_id)

    halaman_layanan.panggil_ulang()
    halaman_layanan.antrian = baru

    assert tertunda["aksi"]() == 101


def test_memanggil_nomor_baru_menutup_survey_nomor_lama(
    halaman_layanan, antrian_siap, terbitkan
):
    terbitkan("A", 2)
    halaman_layanan.muat_ulang()
    halaman_layanan.panggil_berikutnya()
    halaman_layanan.mulai_melayani()
    halaman_layanan.selesaikan()
    nomor_lama = halaman_layanan.baru_selesai

    halaman_layanan.panggil_berikutnya()

    assert nomor_lama is not None
    assert halaman_layanan.antrian is not None
    assert halaman_layanan.antrian.queue_number == "A-002"
    assert halaman_layanan.baru_selesai is None
    assert not halaman_layanan.tombol_survey.isEnabled()


@pytest.mark.parametrize(
    ("nama_fixture", "atribut"),
    [
        ("halaman_daftar", "panel_hasil"),
        ("halaman_layanan", "panel_antrian"),
        ("halaman_layanan", "panel_menunggu"),
    ],
)
def test_gaya_panel_dibatasi_pada_panelnya_sendiri(request, nama_fixture, atribut):
    """
    QLabel adalah turunan QFrame. Selector "QFrame" polos akan membingkai
    setiap label di dalam panel, sehingga tiap baris teks tampak berkotak.
    """
    halaman = request.getfixturevalue(nama_fixture)
    gaya = getattr(halaman, atribut).styleSheet()

    assert "QFrame#" in gaya, "selector harus dibatasi dengan objectName"
    assert "QFrame {" not in gaya


@pytest.mark.parametrize("variant", ["primary", "danger"])
def test_tombol_bergaya_khusus_punya_tampilan_nonaktif(variant):
    """
    Selector [variant=...] lebih spesifik daripada QPushButton:disabled.
    Tanpa aturan khusus, tombol primer yang nonaktif tetap tampak biru dan
    petugas akan mengkliknya berulang kali tanpa hasil.
    """
    from app.ui.style import STYLESHEET

    assert f'QPushButton[variant="{variant}"]:disabled' in STYLESHEET


# ---------------------------------------------------------------------
# Loket bawaan petugas
# ---------------------------------------------------------------------

def _halaman_layanan(qtbot, auth):
    """Panel pelayanan untuk sesi CRO yang sedang masuk."""
    from app.services.master_data_service import MasterDataService
    from app.services.queue_service import QueueService
    from app.services.settings_service import SettingsService
    from app.services.survey_service import SurveyService
    from app.ui.queue.service_page import ServicePage

    halaman = ServicePage(
        QueueService(auth),
        MasterDataService(auth),
        SurveyService(auth),
        SettingsService(auth),
        auth,
    )
    qtbot.addWidget(halaman)
    return halaman


def test_loket_bawaan_langsung_terpilih_saat_masuk(qtbot, auth, antrian_siap, users):
    """
    Tanpa ini, daftarnya selalu jatuh ke loket pertama dan petugas Loket 3
    memanggil atas nama Loket 1 setiap kali lupa menggantinya.
    """
    from app.services.user_service import UserService

    loket = antrian_siap["loket"][2]
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    UserService(auth).update_user(
        users["CRO"], full_name="Petugas Cro", role="CRO", default_counter_id=loket
    )

    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    halaman = _halaman_layanan(qtbot, auth)

    assert halaman.loket_id == loket
    assert not halaman.pilih_loket.isEnabled()


def test_halaman_pelayanan_mengikuti_perubahan_loket_dari_admin(
    qtbot, auth, antrian_siap, users
):
    from app.services.auth_service import AuthService
    from app.services.user_service import UserService

    lama, baru = antrian_siap["loket"][:2]
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    UserService(auth).update_user(
        users["CRO"], full_name="Petugas Cro", role="CRO", default_counter_id=lama
    )
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    assert auth.current_session.default_counter_id == lama

    admin = AuthService()
    admin.login("admin", TEST_PASSWORD)
    UserService(admin).update_user(
        users["CRO"], full_name="Petugas Cro", role="CRO", default_counter_id=baru
    )

    halaman = _halaman_layanan(qtbot, auth)

    assert auth.current_session.default_counter_id == baru
    assert halaman.loket_id == baru
    assert halaman.tombol_ganti_loket.isVisibleTo(halaman)


def test_tanpa_loket_bawaan_wajib_memilih_dulu(qtbot, auth, antrian_siap):
    """Jangan diam-diam memakai loket pertama untuk akun yang belum diatur."""
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = _halaman_layanan(qtbot, auth)

    assert halaman.loket_id is None
    assert halaman.pilih_loket.isEnabled()
    assert not halaman.tombol_panggil.isEnabled()
    assert not halaman.tombol_ganti_loket.isVisibleTo(halaman)


def test_pilih_loket_pertama_dari_panel_diingat(
    qtbot, auth, antrian_siap, monkeypatch
):
    """Petugas pindah meja tanpa memanggil admin, dan besok tidak mengulang."""
    monkeypatch.setattr("app.ui.queue.service_page.konfirmasi", lambda *_args: True)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = _halaman_layanan(qtbot, auth)

    halaman.pilih_loket.setCurrentIndex(
        halaman.pilih_loket.findData(antrian_siap["loket"][1])
    )

    assert auth.current_session.default_counter_id == antrian_siap["loket"][1]
    assert not halaman.pilih_loket.isEnabled()
    assert halaman.tombol_ganti_loket.isVisibleTo(halaman)


def test_ganti_loket_memerlukan_tombol_dan_konfirmasi(
    qtbot, auth, antrian_siap, users, monkeypatch
):
    from app.services.user_service import UserService

    lama, baru = antrian_siap["loket"][:2]
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    UserService(auth).update_user(
        users["CRO"], full_name="Petugas Cro", role="CRO", default_counter_id=lama
    )
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = _halaman_layanan(qtbot, auth)

    pertanyaan = []
    monkeypatch.setattr(
        "app.ui.queue.service_page.konfirmasi",
        lambda _parent, pesan, _judul: pertanyaan.append(pesan) or True,
    )

    halaman.tombol_ganti_loket.click()
    assert halaman.pilih_loket.isEnabled()
    assert not halaman.tombol_panggil.isEnabled()

    halaman.pilih_loket.setCurrentIndex(halaman.pilih_loket.findData(baru))

    assert pertanyaan and "Pindah dari" in pertanyaan[0]
    assert auth.current_session.default_counter_id == baru
    assert not halaman.pilih_loket.isEnabled()


def test_loket_khusus_hanya_menawarkan_layanannya(
    qtbot, auth, antrian_siap, monkeypatch
):
    """
    Menawarkan jenis layanan yang pasti ditolak service hanya membuat
    petugas menabrak pesan kesalahan tanpa sebab yang terlihat.
    """
    from app.services.master_data_service import MasterDataService

    loket = antrian_siap["loket"][0]
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    MasterDataService(auth).set_counter_categories(
        loket, [antrian_siap["kategori"]["B"]]
    )

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = _halaman_layanan(qtbot, auth)
    monkeypatch.setattr("app.ui.queue.service_page.konfirmasi", lambda *_args: True)
    halaman.pilih_loket.setCurrentIndex(halaman.pilih_loket.findData(loket))

    tersedia = {
        halaman.pilih_kategori.itemData(i)
        for i in range(halaman.pilih_kategori.count())
    }
    assert tersedia == {None, antrian_siap["kategori"]["B"]}


def test_loket_tanpa_batasan_menawarkan_semua_layanan(
    qtbot, auth, antrian_siap, monkeypatch
):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = _halaman_layanan(qtbot, auth)
    monkeypatch.setattr("app.ui.queue.service_page.konfirmasi", lambda *_args: True)
    halaman.pilih_loket.setCurrentIndex(
        halaman.pilih_loket.findData(antrian_siap["loket"][0])
    )

    assert halaman.pilih_kategori.count() == len(antrian_siap["kategori"]) + 1


def test_pengaturan_punya_pemilih_media_tiap_jenis_layanan(
    qtbot, admin_auth, seeded, tmp_path, monkeypatch
):
    """
    Media A/B/C dipasang dari satu layar, bukan dengan membuka tiga dialog
    jenis layanan satu per satu.
    """
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.ui.kiosk import sambutan as modul
    from app.ui.settings.settings_page import SettingsPage

    folder = tmp_path / "kiosk"
    folder.mkdir()
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    halaman = SettingsPage(
        SettingsService(admin_auth), MasterDataService(admin_auth)
    )
    qtbot.addWidget(halaman)

    assert set(halaman.media_layanan) == {"KONSULTASI", "PENGADUAN", "INFORMASI"}
    assert any(
        halaman.rail.item(i).text() == "Media Anjungan"
        for i in range(halaman.rail.count())
    )


def test_pencarian_menemukan_media_lewat_nama_layanan(
    qtbot, admin_auth, seeded, tmp_path, monkeypatch
):
    """Nama layanan tidak ada di judul kelompok, tetapi itulah yang diketik orang."""
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.ui.kiosk import sambutan as modul
    from app.ui.settings.settings_page import SettingsPage

    folder = tmp_path / "kiosk"
    folder.mkdir()
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    halaman = SettingsPage(
        SettingsService(admin_auth), MasterDataService(admin_auth)
    )
    qtbot.addWidget(halaman)
    halaman.cari.setText("konsultasi")

    terlihat = [
        halaman.rail.item(i).text()
        for i in range(halaman.rail.count())
        if not halaman.rail.item(i).isHidden()
    ]
    assert any(teks.startswith("Media Anjungan") for teks in terlihat)


def test_pemilih_media_pengaturan_dan_dialog_widget_yang_sama(
    qtbot, admin_auth, seeded, tmp_path, monkeypatch
):
    """
    Dua pintu masuk ke hal yang sama tidak boleh berperilaku berbeda, jadi
    keduanya wajib memakai widget yang sama persis — bukan dua salinan
    yang kelak berubah sendiri-sendiri.
    """
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.ui.kiosk import sambutan as modul
    from app.ui.settings.dialogs import CategoryDialog, PemilihMediaLayanan
    from app.ui.settings.settings_page import SettingsPage

    folder = tmp_path / "kiosk"
    folder.mkdir()
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    master = MasterDataService(admin_auth)
    halaman = SettingsPage(SettingsService(admin_auth), master)
    qtbot.addWidget(halaman)

    layanan = next(k for k in master.list_categories() if k.code == "KONSULTASI")
    dialog = CategoryDialog(category=layanan)
    qtbot.addWidget(dialog)

    assert isinstance(halaman.media_layanan["KONSULTASI"], PemilihMediaLayanan)
    assert isinstance(dialog.media, PemilihMediaLayanan)


def test_dialog_jenis_layanan_baru_belum_bisa_pasang_media(qtbot, admin_auth, seeded):
    """Foldernya dinamai menurut kode, dan kode itu belum ada sebelum disimpan."""
    from app.ui.settings.dialogs import CategoryDialog

    dialog = CategoryDialog()
    qtbot.addWidget(dialog)

    assert dialog.media is None


def test_bilah_status_menyebut_peran_komputer(qtbot, admin_auth, app_config):
    """
    Saat memasang tujuh komputer, memastikan sekilas mana yang mana —
    tanpa membuka dialog satu per satu — menghemat lebih banyak waktu
    daripada yang terlihat.
    """
    from app.core.peran import PeranKomputer, path_berkas_peran, tulis_peran

    tulis_peran(
        path_berkas_peran(app_config.db_path), PeranKomputer(peran="petugas")
    )

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    assert jendela._label_peran.text() == "Loket petugas"


def test_bilah_status_diam_bila_peran_belum_ditetapkan(qtbot, admin_auth, app_config):
    """Ruang kosong lebih jujur daripada kata "(tidak ada)"."""
    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)

    assert not hasattr(jendela, "_label_peran")


def test_halaman_layanan_anjungan_menampilkan_apk_untuk_tablet(
    qtbot, monkeypatch, app_config, tmp_path
):
    from app.services.apk_anjungan import VERSI_MINIMAL, InfoApk
    from app.ui.settings.layanan_anjungan_page import LayananAnjunganPage

    apk = InfoApk(VERSI_MINIMAL, "1.4", tmp_path / "anjungan.apk", 1000)
    _status_palsu(monkeypatch, api=True, terdaftar=True, firewall=True, apk=apk)
    halaman = LayananAnjunganPage()
    qtbot.addWidget(halaman)
    qtbot.waitUntil(lambda: halaman._status is not None, timeout=3000)
    assert halaman.baris_apk.lencana.text() == "Normal"
    assert "1.4" in halaman.baris_apk.teks.text()

    _status_palsu(monkeypatch, api=True, terdaftar=True, firewall=True, apk=None)
    halaman.muat_ulang()
    qtbot.waitUntil(lambda: halaman._status.apk is None, timeout=3000)
    assert halaman.baris_apk.lencana.text() == "Belum"
    assert "build-android-kiosk.ps1" in halaman.baris_apk.teks.text()


def test_kartu_perangkat_menampilkan_dan_mencabut(qtbot, admin_auth, monkeypatch):
    from app.services import device_service
    from app.services.device_service import PerangkatService
    from app.ui.settings.kartu_perangkat import KartuPerangkat

    layanan = PerangkatService(admin_auth)
    token = device_service.pasangkan(
        layanan.buat_kode().kode, "dev-anjungan-0001", "Anjungan Lobi", "anjungan"
    )
    device_service.catat_kontak("dev-tv-0001", nama="TV", jenis="layar_antrian")
    device_service.catat_printer("dev-anjungan-0001", False, "Printer USB tidak ditemukan")

    kartu = KartuPerangkat(layanan)
    qtbot.addWidget(kartu)

    nama = {kartu.tabel.item(b, 0).text() for b in range(kartu.tabel.rowCount())}
    assert nama == {"Anjungan Lobi", "TV"}
    baris_anjungan = next(
        b for b in range(kartu.tabel.rowCount())
        if kartu.tabel.item(b, 0).text() == "Anjungan Lobi"
    )
    assert "gagal" in kartu.tabel.item(baris_anjungan, 5).text()
    assert kartu.tabel.item(baris_anjungan, 1).text() == "Anjungan"
    assert kartu.token_bersama.isChecked()

    monkeypatch.setattr("app.ui.settings.kartu_perangkat.konfirmasi", lambda *a, **k: True)
    info = next(p for p in kartu.perangkat if p.nama == "Anjungan Lobi")
    kartu._cabut(info)

    assert device_service.perangkat_dari_token(token) is None
    assert "dicabut" in kartu.tabel.item(
        next(b for b in range(kartu.tabel.rowCount())
             if kartu.tabel.item(b, 0).text() == "Anjungan Lobi"), 2
    ).text()


def test_kartu_perangkat_memilih_anjungan_bersuara(qtbot, admin_auth):
    from app.services import device_service
    from app.services.device_service import PerangkatService
    from app.ui.settings.kartu_perangkat import KartuPerangkat

    layanan = PerangkatService(admin_auth)
    device_service.pasangkan(
        layanan.buat_kode().kode, "dev-anjungan-0002", "Anjungan Lobi", "anjungan"
    )
    device_service.catat_kontak("dev-tv-0002", nama="TV", jenis="layar_antrian")
    device_service.catat_kontak("dev-lama-0002", nama="Tablet lama", jenis="anjungan")

    kartu = KartuPerangkat(layanan)
    qtbot.addWidget(kartu)

    pilihan = [kartu.pilih_suara.itemText(i) for i in range(kartu.pilih_suara.count())]
    assert pilihan == ["Tidak ada (anjungan diam)", "Anjungan Lobi"], (
        "layar antrian dan tablet bertoken bersama tidak dapat dipilih"
    )
    assert kartu.pilih_suara.currentIndex() == 1, "satu-satunya anjungan dipilih otomatis"

    kartu._ubah_anjungan_bersuara(0)
    assert device_service.anjungan_bersuara() == ""

    kartu.pilih_suara.setCurrentIndex(1)
    kartu._ubah_anjungan_bersuara(1)
    assert device_service.anjungan_bersuara() == "dev-anjungan-0002"

    kartu._ubah_anjungan_bersuara(0)
    assert device_service.anjungan_bersuara() == ""


def test_kartu_perangkat_menampilkan_kode_pasang(qtbot, admin_auth, monkeypatch):
    from app.services.device_service import PerangkatService
    from app.ui.settings import kartu_perangkat as modul

    tampil = {}

    def exec_palsu(dialog):
        tampil["kode"] = dialog.label_kode.text()
        return 1

    monkeypatch.setattr(modul.DialogKodePasang, "exec", exec_palsu)
    kartu = modul.KartuPerangkat(PerangkatService(admin_auth))
    qtbot.addWidget(kartu)

    kartu._tambah()

    angka = tampil["kode"].replace(" ", "")
    assert len(angka) == 6 and angka.isdigit()


def test_bilah_status_petugas_tanpa_info_teknis(qtbot, auth, app_config, monkeypatch):
    """Petugas loket tidak dapat memperbaiki Firewall atau API; jangan buat cemas."""
    from app.core.peran import PeranKomputer, path_berkas_peran, tulis_peran

    monkeypatch.setattr("app.ui.main_window._komputer_server", lambda: True)
    tulis_peran(
        path_berkas_peran(app_config.db_path), PeranKomputer(peran="petugas")
    )
    auth.login("cro", TEST_PASSWORD)

    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert not hasattr(jendela, "_label_peran")
    assert getattr(jendela, "_label_api", None) is None
    assert getattr(jendela, "pita_anjungan", None) is None
    teks = jendela.findChild(QLabel, "statusDatabase").text()
    assert teks == "Database: ● tersambung"
    jendela._tampilkan_status_database(False)
    assert "hubungi admin" in jendela.findChild(QLabel, "statusDatabase").text()


def test_kartu_perangkat_memperingatkan_suara_ganda(qtbot, admin_auth):
    from app.services import device_service
    from app.services.device_service import PerangkatService
    from app.services.settings_service import SettingsService
    from app.ui.settings.kartu_perangkat import KartuPerangkat

    layanan = PerangkatService(admin_auth)
    device_service.pasangkan(
        layanan.buat_kode().kode, "dev-anjungan-0003", "Anjungan Lobi", "anjungan"
    )
    device_service.catat_kontak("dev-tv-0003", nama="TV Lobi", jenis="layar_antrian")
    layanan.setel_anjungan_bersuara("dev-anjungan-0003")

    kartu = KartuPerangkat(layanan)
    qtbot.addWidget(kartu)
    assert not kartu.peringatan_suara.isHidden()
    assert "TV Lobi" in kartu.peringatan_suara.text()

    SettingsService(admin_auth).set("display.sound_enabled", "false")
    kartu.muat_ulang()
    assert kartu.peringatan_suara.isHidden(), "layar antrian sudah diam"

    SettingsService(admin_auth).set("display.sound_enabled", "true")
    layanan.setel_anjungan_bersuara(None)
    kartu.muat_ulang()
    assert kartu.peringatan_suara.isHidden(), "tidak ada anjungan bersuara"


def test_halaman_layanan_anjungan_memperingatkan_suara_bukan_indonesia(
    qtbot, monkeypatch, app_config
):
    from app.services.paket_suara import InfoPaket
    from app.ui.settings.layanan_anjungan_page import LayananAnjunganPage

    klip = {"angka_1": "angka_1.wav"}
    _status_palsu(
        monkeypatch, api=True, terdaftar=True, firewall=True,
        paket=InfoPaket("v1", "Microsoft David Desktop (en-US)", klip),
    )
    monkeypatch.setattr(
        "app.ui.settings.layanan_anjungan_page.nama_loket_aktif", lambda: []
    )
    halaman = LayananAnjunganPage()
    qtbot.addWidget(halaman)
    qtbot.waitUntil(lambda: halaman._status is not None, timeout=3000)
    assert halaman.baris_paket.lencana.text() == "Belum"
    assert "bukan Bahasa Indonesia" in halaman.baris_paket.teks.text()
    assert "Bahasa Indonesia" in halaman.baris_paket.teks.toolTip()

    _status_palsu(
        monkeypatch, api=True, terdaftar=True, firewall=True,
        paket=InfoPaket("v2", "Microsoft Andika (Indonesia)", klip),
    )
    halaman.muat_ulang()
    qtbot.waitUntil(lambda: halaman._status.paket.versi == "v2", timeout=3000)
    assert halaman.baris_paket.lencana.text() == "Normal"
    assert halaman.baris_paket.teks.toolTip() == ""



def test_layar_backup_menampilkan_status_gagal_dan_checksum(
    qtbot, admin_auth, antrian_siap, mesin_backup_tersedia, monkeypatch
):
    from app.services.backup_service import BackupService
    from app.ui.settings.backup_page import BackupPage

    layanan = BackupService(admin_auth)
    layanan.backup()
    halaman = BackupPage(layanan)
    qtbot.addWidget(halaman)

    assert "Backup terakhir berhasil" in halaman.label_status.text()
    assert halaman.tabel_backup.item(0, 3).text() == "ada"
    assert not halaman.tombol_uji.isEnabled()
    halaman.tabel_backup.selectRow(0)
    assert halaman.tombol_uji.isEnabled()

    def tanpa_izin(_tujuan):
        raise PermissionError("akses ditolak")

    monkeypatch.setattr(layanan.mesin, "salin", tanpa_izin)
    with pytest.raises(PermissionError):
        layanan.backup()
    halaman.muat_ulang()

    assert "GAGAL" in halaman.label_status.text()
    assert "tidak dapat ditulis" in halaman.label_status.text()


def test_aplikasi_lebih_lama_daripada_database_tidak_dilaporkan_sebagai_koneksi(capsys):
    """Pesannya menyuruh memperbarui aplikasi, bukan memeriksa jaringan/server."""
    from app.main import _laporkan_aplikasi_lebih_lama

    _laporkan_aplikasi_lebih_lama(berjendela=False)

    pesan = capsys.readouterr().err
    assert "versi aplikasi yang lebih baru" in pesan
    assert "Pasang versi terbaru" in pesan
    assert "jaringan" not in pesan
    assert "menghubungi database" not in pesan
