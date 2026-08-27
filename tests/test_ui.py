"""
Test antarmuka.

Yang diuji di sini bukan penampilannya, melainkan perilakunya: pesan
kesalahan tidak boleh berupa traceback, menu harus mengikuti hak akses,
dan dialog wajib tidak boleh dapat dilewati.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QPushButton, QStatusBar

from app.core.errors import AppError, ValidationError
from app.models import UserRole
from app.services.master_data_service import MasterDataService
from app.services.user_service import UserService
from app.ui.common import PESAN_TAK_TERDUGA, pesan_untuk_user
from app.ui.login.change_password_dialog import ChangePasswordDialog
from app.ui.login.login_window import LoginWindow
from app.ui.main_window import MainWindow, PlaceholderPage
from app.ui.settings.dialogs import CategoryDialog, CounterDialog, UserDialog
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


def test_kios_tetap_bersih_setelah_muat_ulang(qtbot, auth):
    """statusBar() membuat bilahnya sendiri bila belum ada."""
    auth.login("display", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    jendela.muat_ulang_halaman()

    assert jendela.findChild(QStatusBar) is None


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


def test_supervisor_melihat_ringkasan(qtbot, auth):
    auth.login("supervisor", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert "Ringkasan Harian" in menu


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
    tabel = halaman_master.tab_loket.tabel
    assert tabel.rowCount() == 3
    assert tabel.item(0, 0).text() == "LOKET-1"
    assert tabel.item(0, 2).text() == "Aktif"


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
    assert menu == ["Pelayanan", "Survey Kepuasan"]

    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    jendela2 = MainWindow(auth)
    qtbot.addWidget(jendela2)
    menu2 = [jendela2.navigasi.item(i).text() for i in range(jendela2.navigasi.count())]
    assert menu2 == ["Terbitkan Nomor"]


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
    # kalau tidak ia hanya bisa diubah lewat database.
    assert set(halaman_pengaturan.baris) == {p.kunci for p in SKEMA}
    assert halaman_pengaturan.baris["ticket.printer"].nilai() == "pdf"
    assert halaman_pengaturan.baris["survey.enabled"].nilai() == "true"
    assert halaman_pengaturan.baris["display.next_count"].nilai() == "3"


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


def test_menu_pengaturan_hanya_untuk_admin(qtbot, auth, antrian_siap):
    from app.ui.main_window import MainWindow

    for peran in ("cro", "supervisor", "registration", "display"):
        auth.logout()
        auth.login(peran, TEST_PASSWORD)
        jendela = MainWindow(auth)
        qtbot.addWidget(jendela)
        menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
        assert "Pengaturan" not in menu


def test_admin_melihat_menu_pengaturan(qtbot, admin_auth):
    from app.ui.main_window import MainWindow

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]

    assert "Pengaturan" in menu


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
        assert "Backup & Audit" not in menu


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
    assert menu == ["Ringkasan Harian", "Hasil Survey"]

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

    assert menu == ["Ringkasan Harian", "Hasil Survey"]


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


@pytest.mark.parametrize(
    ("nama_fixture", "atribut"),
    [("halaman_daftar", "panel_hasil")],
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
