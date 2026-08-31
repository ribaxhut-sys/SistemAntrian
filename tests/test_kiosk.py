"""
Test dua mesin publik: anjungan ambil nomor dan layar antrian.

Keduanya berjalan TANPA login di komputer yang menghadap publik dan tidak
diawasi. Yang dikunci di sini terutama batas kewenangannya: anjungan boleh
menampilkan papan nomor dan menerbitkan nomor, layar antrian hanya boleh
melihat, dan keduanya tidak boleh apa pun selain itu.
"""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QFrame, QStatusBar

from app.core.errors import AuthorizationError, BusinessRuleError
from app.models import UserRole
from app.services.permissions import Permission, permissions_for
from app.services.queue_service import QueueService
from app.services.settings_service import SettingsService


@pytest.fixture
def kios(auth, antrian_siap):
    """QueueService dengan sesi kios, tanpa login."""
    auth.logout()
    auth.mulai_sesi_kios()
    return QueueService(auth)


# ---------------------------------------------------------------------
# Sesi tanpa login
# ---------------------------------------------------------------------

def test_kios_berjalan_tanpa_login(auth, antrian_siap):
    """Kata sandi tidak boleh perlu disimpan di komputer publik."""
    auth.logout()

    sesi = auth.mulai_sesi_kios()

    assert auth.is_authenticated
    assert sesi.kios
    assert sesi.role is UserRole.KIOSK


def test_sesi_kios_bukan_milik_orang(auth, antrian_siap):
    """
    Tidak ada akun di baliknya, sehingga audit mencatatnya sebagai NULL.

    Kolom user_id pada audit_log memang dirancang boleh kosong untuk
    aktivitas yang tidak berpemilik.
    """
    auth.logout()

    sesi = auth.mulai_sesi_kios()

    assert sesi.user_id is None


def test_sesi_petugas_tetap_punya_pemilik(cro_queue, auth):
    """Penjaga agar user_id yang boleh kosong tidak diam-diam merembet."""
    assert auth.require_session().user_id is not None
    assert not auth.require_session().kios


# ---------------------------------------------------------------------
# Batas kewenangan
# ---------------------------------------------------------------------

def test_kios_boleh_menerbitkan_nomor(kios, antrian_siap):
    nomor = kios.create_queue(antrian_siap["kategori"]["A"])

    assert nomor.queue_number == "A-001"


def test_kios_boleh_melihat_papan_nomor(kios):
    keadaan = kios.display_state()

    assert keadaan.terkini is None


@pytest.mark.parametrize(
    "permission",
    [
        Permission.QUEUE_CALL,
        Permission.QUEUE_SERVE,
        Permission.QUEUE_COMPLETE,
        Permission.QUEUE_CANCEL,
        Permission.QUEUE_NO_SHOW,
        Permission.QUEUE_VIEW,
        Permission.USER_MANAGE,
        Permission.MASTER_MANAGE,
        Permission.CONFIG_MANAGE,
        Permission.BACKUP_MANAGE,
        Permission.REPORT_VIEW,
        Permission.SURVEY_VIEW,
        Permission.SURVEY_SUBMIT,
    ],
)
def test_kios_tidak_berwenang_atas_hal_lain(permission):
    """
    Komputernya berdiri di ruang publik tanpa diawasi.

    Yang boleh hanya dua hal yang memang dikerjakan pengunjung sendiri.
    """
    assert permission not in permissions_for(UserRole.KIOSK)


def test_kios_hanya_punya_tiga_kewenangan():
    assert permissions_for(UserRole.KIOSK) == frozenset(
        {
            Permission.DISPLAY_VIEW,
            Permission.QUEUE_CREATE,
            Permission.TICKET_PRINT,
        }
    )


def test_kios_tidak_dapat_memanggil_antrian(kios, antrian_siap):
    kios.create_queue(antrian_siap["kategori"]["A"])

    with pytest.raises(AuthorizationError):
        kios.call_next(antrian_siap["loket"][0])


def test_kios_tidak_dapat_melihat_daftar_antrian(kios, antrian_siap):
    """Papan nomor cukup; daftar penuh bukan urusan pengunjung."""
    kios.create_queue(antrian_siap["kategori"]["A"])

    with pytest.raises(AuthorizationError):
        kios.list_today()


# ---------------------------------------------------------------------
# Jeda antar-pengambilan
# ---------------------------------------------------------------------

def test_nomor_kedua_ditahan_sejenak(kios, antrian_siap):
    """Satu orang menekan tombol berulang kali tidak boleh memenuhi antrian."""
    kios.create_queue(antrian_siap["kategori"]["A"])

    with pytest.raises(BusinessRuleError) as info:
        kios.create_queue(antrian_siap["kategori"]["A"])

    assert "tunggu" in info.value.user_message.lower()


def test_jeda_dapat_dimatikan_administrator(antrian_siap, admin_auth, auth):
    """Kantor yang ramai boleh mematikannya tanpa mengubah kode."""
    SettingsService(admin_auth).set("kiosk.cooldown_seconds", "0")

    auth.logout()
    auth.mulai_sesi_kios()
    layanan = QueueService(auth)

    a = layanan.create_queue(antrian_siap["kategori"]["A"])
    b = layanan.create_queue(antrian_siap["kategori"]["A"])

    assert (a.queue_number, b.queue_number) == ("A-001", "A-002")


def test_sisa_jeda_menyusut_setelah_nomor_terbit(kios, antrian_siap):
    assert kios.sisa_jeda_kios() == 0

    kios.create_queue(antrian_siap["kategori"]["A"])

    assert 0 < kios.sisa_jeda_kios() <= kios.jeda_kios_detik()


def test_petugas_pendaftaran_tidak_ikut_diperlambat(reg_queue, antrian_siap):
    """
    Meja pendaftaran melayani rombongan yang datang bersamaan.

    Jeda kios sengaja tidak berlaku bagi petugas; memperlambat meja resmi
    adalah akibat yang tidak diinginkan dari aturan yang ditujukan kepada
    pengunjung.
    """
    nomor = [
        reg_queue.create_queue(antrian_siap["kategori"]["A"]).queue_number
        for _ in range(3)
    ]

    assert nomor == ["A-001", "A-002", "A-003"]


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def test_nomor_dari_kios_tercatat_tanpa_pelaku(kios, antrian_siap):
    """
    Terbaca berbeda dari nomor yang diterbitkan petugas.

    Supervisor jadi dapat membedakan mana yang diambil pengunjung sendiri
    dan mana yang diterbitkan di meja pendaftaran.
    """
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    kios.create_queue(antrian_siap["kategori"]["A"])

    with session_scope() as session:
        baris = session.scalars(
            sa.select(AuditLog).where(AuditLog.action == "CREATE_QUEUE")
        ).all()

    assert len(baris) == 1
    assert baris[0].user_id is None


# ---------------------------------------------------------------------
# UI kios
# ---------------------------------------------------------------------

@pytest.fixture
def halaman_kios(qtbot, kios, auth):
    """Layar kios tanpa timer, supaya test mengendalikan waktunya."""
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.services.sound_service import NullSoundPlayer
    from app.ui.kiosk.kiosk_page import KioskPage

    halaman = KioskPage(
        kios,
        MasterDataService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
    )
    qtbot.addWidget(halaman)
    halaman.papan.hentikan()
    halaman._penghitung.stop()
    return halaman


def test_halaman_kios_membuat_tombol_jenis_layanan(halaman_kios):
    assert len(halaman_kios.tombol_layanan) == 3
    assert [c.prefix for c in halaman_kios.kategori] == ["A", "B", "C"]


def test_tulisan_tombol_layanan_berwarna_terang(halaman_kios):
    """Huruf A/B/C harus putih di atas tombol teal, bukan gelap dari stylesheet global."""
    from PySide6.QtWidgets import QLabel

    from app.ui.style import DISPLAY_KIOS_TOMBOL_TEKS

    for btn in halaman_kios.tombol_layanan:
        prefix = btn.findChild(QLabel, "prefixLayanan")
        nama = btn.findChild(QLabel, "namaLayanan")
        assert prefix is not None
        assert nama is not None
        assert DISPLAY_KIOS_TOMBOL_TEKS in prefix.styleSheet()
        assert DISPLAY_KIOS_TOMBOL_TEKS in nama.styleSheet()


def test_nama_layanan_tetap_tampil_pada_jendela_biasa(qtbot, halaman_kios):
    """
    Papan nomor huruf besar merebut tinggi jendela. Nama di bawah A/B/C
    tidak boleh ikut terpotong saat petugas menekan F11.
    """
    from PySide6.QtWidgets import QLabel

    halaman_kios.resize(1100, 700)
    halaman_kios.show()
    qtbot.waitExposed(halaman_kios)

    nama_tampil = []
    for btn in halaman_kios.tombol_layanan:
        label = btn.findChild(QLabel, "namaLayanan")
        assert label is not None
        assert label.text()
        assert btn.height() >= 80
        nama_tampil.append(label.text())

    assert nama_tampil == ["Konsultasi", "Pengaduan", "Informasi"]


def test_nama_layanan_tetap_tampil_pada_layar_penuh(qtbot, halaman_kios):
    """
    Kios dipasang layar penuh di monitor 1080p.

    Papan nomor tidak boleh ikut membesar sampai menelan panel ambil nomor;
    nama layanan di bawah A/B/C harus tetap muat seluruhnya.
    """
    from PySide6.QtWidgets import QLabel

    from app.ui.kiosk.kiosk_page import TINGGI_PANEL_AMBIL_MIN, TINGGI_TOMBOL_MIN

    halaman_kios.resize(1920, 1080)
    halaman_kios.show()
    qtbot.waitExposed(halaman_kios)

    panel = halaman_kios.findChild(QFrame, "panelAmbil")
    assert panel is not None
    assert panel.height() >= TINGGI_PANEL_AMBIL_MIN

    for btn in halaman_kios.tombol_layanan:
        label = btn.findChild(QLabel, "namaLayanan")
        assert label is not None
        assert btn.height() >= TINGGI_TOMBOL_MIN
        # QLabel memotong teksnya diam-diam bila tingginya kurang; yang
        # dijaga di sini adalah tinggi yang dibutuhkan pada lebar sekarang.
        assert label.height() >= label.heightForWidth(label.width())


def test_tombol_layanan_proporsional_pada_layar_penuh(qtbot, halaman_kios):
    """
    Tiga tombol A/B/C tidak boleh meregang jadi batang pipih selebar panel.

    Pada 1080p, Expanding tanpa batas lebar membuat tiap kartu ~600px
    lebar pada tinggi ~120px — terbaca sebagai pita, bukan tombol sentuh.
    """
    from app.ui.kiosk.kiosk_page import (
        CELAH_TOMBOL,
        LEBAR_TOMBOL_MAKS,
        TINGGI_TOMBOL_MAKS,
        TINGGI_TOMBOL_MIN,
    )

    halaman_kios.resize(1920, 1080)
    halaman_kios.show()
    qtbot.waitExposed(halaman_kios)
    halaman_kios._sesuaikan_ukuran_tombol()

    ukuran = {(btn.width(), btn.height()) for btn in halaman_kios.tombol_layanan}
    assert len(ukuran) == 1

    lebar, tinggi = next(iter(ukuran))
    assert TINGGI_TOMBOL_MIN <= tinggi <= TINGGI_TOMBOL_MAKS
    # Pada 1080p ruangnya cukup: lebar harus tepat angka yang diminta.
    assert lebar == LEBAR_TOMBOL_MAKS

    kotak = [btn.geometry() for btn in halaman_kios.tombol_layanan]
    for i, a in enumerate(kotak):
        for b in kotak[i + 1 :]:
            assert not a.intersects(b)

    urut = sorted(halaman_kios.tombol_layanan, key=lambda btn: btn.x())
    for kiri, kanan in zip(urut, urut[1:]):
        jarak = kanan.x() - (kiri.x() + kiri.width())
        assert jarak >= CELAH_TOMBOL


def test_papan_kios_tetap_kompak_di_layar_penuh(qtbot, halaman_kios):
    """Pembedanya `kompak`, bukan aplikasi yang berbeda."""
    sebelum = halaman_kios.papan.px("nomor")

    halaman_kios.resize(1920, 1080)
    halaman_kios.show()
    qtbot.waitExposed(halaman_kios)

    assert halaman_kios.papan.kompak is True
    assert halaman_kios.papan.skala == 1.0
    assert halaman_kios.papan.px("nomor") == sebelum


def test_papan_kios_juga_memiliki_jam(halaman_kios):
    """Satu DisplayPage: perbaikan pada papan televisi ikut ke kios."""
    assert halaman_kios.papan.label_jam.text()
    assert "·" in halaman_kios.papan.label_jam.text()


def test_mengambil_nomor_menampilkan_hasil_besar(halaman_kios, antrian_siap):
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])

    assert "A-001" in halaman_kios.label_ajakan.text()


def test_tombol_mati_selama_jeda_dan_menyebutkan_alasannya(halaman_kios, antrian_siap):
    """
    Tombol mati tanpa keterangan membuat pengunjung menekannya berulang
    kali dan mengira layarnya rusak.
    """
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])

    assert all(not btn.isEnabled() for btn in halaman_kios.tombol_layanan)

    halaman_kios._penghapus_hasil.stop()
    halaman_kios._perbarui_jeda()

    assert "tunggu" in halaman_kios.label_petunjuk.text().lower()


def test_pengambilan_kedua_tidak_membuka_dialog(halaman_kios, antrian_siap):
    """Dialog modal di layar publik membuat test hang dan layar tersangkut."""
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])

    assert "A-001" in halaman_kios.label_ajakan.text()
    assert "tunggu" in halaman_kios.label_petunjuk.text().lower()


def test_gagal_cetak_tidak_membatalkan_nomor_di_kios(qtbot, kios, antrian_siap, auth):
    """Printer kehabisan kertas tidak boleh menghapus giliran pengunjung."""
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import Queue, QueueStatus
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.services.sound_service import NullSoundPlayer
    from app.services.ticket_service import GagalTicketPrinter, TicketService
    from app.ui.kiosk.kiosk_page import KioskPage

    tiket = TicketService(
        GagalTicketPrinter("Kertas habis."),
        SettingsService(auth),
        MasterDataService(auth),
    )
    halaman = KioskPage(
        kios,
        MasterDataService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        tiket,
    )
    qtbot.addWidget(halaman)
    halaman.papan.hentikan()
    halaman._penghitung.stop()

    halaman.ambil_nomor(antrian_siap["kategori"]["A"])

    assert "A-001" in halaman.label_ajakan.text()
    with session_scope() as session:
        tersimpan = session.scalar(sa.select(Queue))
    assert tersimpan is not None
    assert tersimpan.queue_number == "A-001"
    assert tersimpan.status is QueueStatus.WAITING


def test_sesi_anjungan_hanya_menu_anjungan(qtbot, auth, antrian_siap):
    from app.ui.kiosk.kiosk_page import KioskPage
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert menu == ["Anjungan Ambil Nomor"]
    assert jendela.mode_kios
    assert isinstance(jendela.halaman.currentWidget(), KioskPage)
    assert jendela.findChild(QFrame, "panelHeader") is None
    assert jendela.findChild(QStatusBar) is None
    assert jendela.navigasi.parent() is None


@pytest.mark.parametrize(
    "peran", ["cro", "supervisor", "registration", "admin", "display"]
)
def test_petugas_tidak_melihat_menu_anjungan(qtbot, auth, peran):
    from app.ui.main_window import MainWindow
    from tests.conftest import TEST_PASSWORD

    auth.logout()
    auth.login(peran, TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert "Anjungan Ambil Nomor" not in menu


def test_mode_dialog_memilih_anjungan(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QPushButton

    from app.ui.login.mode_dialog import ANJUNGAN, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)
    tombol_anjungan = next(
        b for b in dialog.findChildren(QPushButton) if "ANJUNGAN" in b.text()
    )
    qtbot.mouseClick(tombol_anjungan, Qt.MouseButton.LeftButton)

    assert dialog.pilihan == ANJUNGAN
    assert dialog.result() == int(QDialog.DialogCode.Accepted)


def test_mode_dialog_memilih_layar_antrian(qtbot):
    """
    Televisi ruang tunggu adalah pilihan tersendiri, bukan bagian dari
    anjungan. Sebelumnya keduanya satu tombol bernama "Layar Pengunjung",
    dan mesin televisi terpaksa dibuka lewat login akun DISPLAY.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QPushButton

    from app.ui.login.mode_dialog import LAYAR_ANTRIAN, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)
    tombol_antrian = next(
        b for b in dialog.findChildren(QPushButton) if "LAYAR ANTRIAN" in b.text()
    )
    qtbot.mouseClick(tombol_antrian, Qt.MouseButton.LeftButton)

    assert dialog.pilihan == LAYAR_ANTRIAN
    assert dialog.result() == int(QDialog.DialogCode.Accepted)


def test_mode_dialog_menawarkan_tiga_mesin(qtbot):
    """Tiga mesin yang berbeda harus dapat dipilih tanpa saling menumpang."""
    from PySide6.QtWidgets import QPushButton

    from app.ui.login.mode_dialog import ANJUNGAN, LAYAR_ANTRIAN, LAYAR_PETUGAS, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)

    assert len(dialog.findChildren(QPushButton)) == 3
    assert len({LAYAR_ANTRIAN, ANJUNGAN, LAYAR_PETUGAS}) == 3


def test_mode_dialog_memilih_layar_petugas(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QPushButton

    from app.ui.login.mode_dialog import LAYAR_PETUGAS, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)
    tombol_petugas = next(
        b for b in dialog.findChildren(QPushButton) if "PETUGAS" in b.text()
    )
    qtbot.mouseClick(tombol_petugas, Qt.MouseButton.LeftButton)

    assert dialog.pilihan == LAYAR_PETUGAS
    assert dialog.result() == int(QDialog.DialogCode.Accepted)


# ---------------------------------------------------------------------
# Layar antrian sebagai mesin tersendiri
# ---------------------------------------------------------------------

def test_sesi_layar_hanya_menu_layar_antrian(qtbot, auth, antrian_siap):
    """
    Televisi ruang tunggu membuka papan besar, bukan halaman anjungan.

    Menu-nya dibuktikan di sini karena keduanya sama-sama berjalan tanpa
    login: yang membedakan hanyalah peran sesinya, dan tertukarnya berarti
    televisi memunculkan tombol ambil nomor yang tidak ada orang di
    depannya untuk menekan.
    """
    from app.ui.display.display_page import DisplayPage
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_layar()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert menu == ["Layar Antrian"]
    assert isinstance(jendela.halaman.currentWidget(), DisplayPage)


def test_sesi_layar_menyembunyikan_seluruh_perkakas_petugas(qtbot, auth, antrian_siap):
    """
    Sama seperti anjungan: tidak ada bilah atas, navigasi, maupun bilah
    status. Tombol "Keluar" yang terpampang di ruang tunggu hanya
    mengundang orang menutup aplikasi antrian.
    """
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_layar()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.mode_kios
    assert jendela.findChild(QFrame, "panelHeader") is None
    assert jendela.findChild(QStatusBar) is None
    assert jendela.navigasi.parent() is None


def test_papan_televisi_bukan_papan_kompak(qtbot, auth, antrian_siap):
    """
    Televisi dibaca dari seberang ruangan, anjungan dari jarak satu lengan.

    Papan kompak di televisi berarti nomor sebesar papan kios pada layar 50
    inci — terbaca, tetapi membuang seluruh alasan televisi itu dipasang.
    """
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_layar()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.halaman.currentWidget().kompak is False


# ---------------------------------------------------------------------
# Pencetak dan pengeras suara menempel pada mesin
# ---------------------------------------------------------------------

def test_anjungan_diam_walau_suara_dinyalakan_di_pengaturan(
    qtbot, auth, antrian_siap, env_mesin
):
    """
    Dua mesin publik dengan pengeras suara masing-masing akan mengumumkan
    nomor yang sama dua kali, saling menyusul, karena keduanya menyegarkan
    sendiri tiap dua detik.

    Yang dibuktikan di sini adalah pemutarnya benar-benar diam — bukan
    sekadar penanda `suara_aktif` di papan, yang masih menyisakan
    kemungkinan bunyi lewat jalur lain.
    """
    from app.services.sound_service import NullSoundPlayer
    from app.ui.main_window import MainWindow

    env_mesin(ANTRIAN_SUARA=None)
    SettingsService(auth).set("display.sound_enabled", "true")

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert isinstance(jendela.sound_player, NullSoundPlayer)
    assert jendela.halaman.currentWidget().papan.suara_aktif is False


def test_anjungan_bersuara_kembali_bila_mesin_memintanya(
    qtbot, auth, antrian_siap, env_mesin
):
    """Pemasangan satu-mesin yang anjungannya merangkap papan nomor."""
    from app.ui.main_window import MainWindow

    env_mesin(ANTRIAN_SUARA="1")
    SettingsService(auth).set("display.sound_enabled", "false")

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.halaman.currentWidget().papan.suara_aktif is True


def test_pencetak_mesin_dipakai_jendela_utama(qtbot, auth, antrian_siap, env_mesin):
    """
    Komputer loket tanpa pencetak tiket tidak boleh ikut mencoba mencetak
    hanya karena pengaturan bersama menyebut "Cetak ke printer Windows".
    """
    from app.services.ticket_service import NullTicketPrinter
    from app.ui.main_window import MainWindow

    env_mesin(ANTRIAN_PRINTER="none")
    SettingsService(auth).set("ticket.printer", "system")

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert isinstance(jendela.ticket_service.printer, NullTicketPrinter)
