"""
Test dua mesin publik: anjungan ambil nomor dan layar antrian.

Keduanya berjalan TANPA login di komputer yang menghadap publik dan tidak
diawasi. Yang dikunci di sini terutama batas kewenangannya: anjungan boleh
menampilkan papan nomor dan menerbitkan nomor, layar antrian hanya boleh
melihat, dan keduanya tidak boleh apa pun selain itu.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QPushButton, QStatusBar

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


def test_jeda_berlaku_per_perangkat(kios, antrian_siap):
    """
    Tablet A yang baru menerbitkan nomor tidak boleh menahan Tablet B.

    Dulu jedanya satu untuk seluruh API: setiap nomor dari tablet mana pun
    membuat semua tablet lain menolak pengunjung berikutnya.
    """
    kategori = antrian_siap["kategori"]["A"]
    kios.create_queue(kategori, perangkat="tablet-a")

    with pytest.raises(BusinessRuleError):
        kios.create_queue(kategori, perangkat="tablet-a")

    assert kios.sisa_jeda_kios("tablet-b") == 0
    assert kios.create_queue(kategori, perangkat="tablet-b").queue_number == "A-002"
    assert 0 < kios.sisa_jeda_kios("tablet-a") <= kios.jeda_kios_detik()


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


def test_sesi_kios_tidak_boleh_mengubah_pengaturan_lain(kios, auth):
    """Menukar tata letak anjungan tidak membuka seluruh konfigurasi."""
    with pytest.raises(AuthorizationError):
        SettingsService(auth).set("display.title", "COBA")


def _jendela_pratinjau_totem(qtbot, auth):
    """Jendela pratinjau totem `--jendela`, beserta halaman anjungannya."""
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth, anjungan_totem=True, berjendela=True)
    qtbot.addWidget(jendela)
    wadah = jendela.halaman.currentWidget()
    halaman = wadah.isi
    halaman.papan.hentikan()
    halaman._penghitung.stop()
    halaman._pemeriksa_layanan.stop()
    return jendela, wadah, halaman


def _label_dijaga(halaman) -> list:
    """
    Label sebaris yang punya penjaga lebar: judul panel, judul papan, dan
    kepala kartu loket di pita.

    Hanya label-label ini yang diperiksa. Label lain tidak punya penjaga
    — cukup lebar pada huruf Windows sampai skala 200% — dan platform uji
    offscreen memakai huruf cadangan yang jauh lebih lebar daripada huruf
    yang pernah dilihat pengunjung. Menuntut semuanya muat di sini hanya
    mengukur huruf cadangan itu.
    """
    dijaga = [halaman.label_ajakan, halaman.papan.label_judul]
    for kartu in halaman.pita_loket.kartu_loket:
        dijaga += [kartu.label_nama, kartu.label_status]
    return dijaga


def _label_terpotong_tanpa_alasan(halaman) -> list:
    """
    Label dijaga yang terpotong padahal penjaganya masih punya ruang.

    Setiap penjaga boleh kalah hanya di batas bawahnya: judul panel pada
    16 px, judul papan pada 10 px, dan kepala kartu loket pada skala pita
    terkecil. Di sana huruf cadangan offscreen pada 150% masih menuntut
    sekitar 9% lebih lebar daripada yang ada — sedangkan dengan huruf
    Windows yang dilihat pengunjung, pita tetap utuh sampai skala 200%.

    Aturan ini tidak bergantung pada huruf, dan tetap menangkap pita yang
    lupa menyusut: kepala kartu yang terpotong pada skala 1,15 bukan
    batas huruf, melainkan penjaga yang tidak bekerja.
    """
    from app.ui.kiosk.pita_loket import SKALA_PITA_MIN

    from app.ui.kiosk.kiosk_page import HURUF_KONFIRMASI_MIN

    di_batas: set[int] = set()
    for kartu in halaman.pita_loket.kartu_loket:
        if kartu.skala <= SKALA_PITA_MIN + 0.01:
            di_batas.update({id(kartu.label_nama), id(kartu.label_status)})
    if halaman.label_ajakan.property("hurufSekarang") == HURUF_KONFIRMASI_MIN:
        di_batas.add(id(halaman.label_ajakan))
    if halaman.papan._ukuran_judul <= 10:
        di_batas.add(id(halaman.papan.label_judul))
    return _label_terpotong(
        [label for label in _label_dijaga(halaman) if id(label) not in di_batas]
    )


def _label_terpotong(labels) -> list:
    """Label sebaris yang tampak lebih sempit atau pendek daripada isinya."""
    hasil = []
    for label in labels:
        if not label.isVisible() or not label.text() or label.wordWrap():
            continue
        butuh = label.sizeHint()
        if label.width() + 1 < butuh.width() or label.height() + 1 < butuh.height():
            hasil.append((label.text()[:24], label.size().toTuple(), butuh.toTuple()))
    return hasil


# ---------------------------------------------------------------------
# Kisi kartu menyesuaikan banyaknya layanan
# ---------------------------------------------------------------------


def _per_baris(halaman) -> list[int]:
    """Banyaknya kartu pada tiap baris, urut dari atas."""
    baris: dict[int, list] = {}
    for btn in halaman.tombol_layanan:
        baris.setdefault(btn.y(), []).append(btn)
    return [len(isi) for _, isi in sorted(baris.items())]


# ---------------------------------------------------------------------
# Daftar layanan menyusul perubahan admin
# ---------------------------------------------------------------------

@pytest.fixture
def ubah_sebagai_admin(auth, master_service):
    """
    Jalankan perubahan data master, lalu kembali ke sesi kios.

    Anjungan berjalan tanpa login; sesinya harus utuh kembali sesudahnya,
    persis seperti keadaan sungguhan ketika admin mengubah data dari
    komputer lain.
    """
    from tests.conftest import TEST_PASSWORD

    def ubah(aksi):
        auth.logout()
        auth.login("admin", TEST_PASSWORD)
        try:
            return aksi(master_service)
        finally:
            auth.logout()
            auth.mulai_sesi_kios()

    return ubah


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


def test_mode_dialog_memilih_layar_antrian(qtbot):
    """
    Televisi ruang tunggu adalah pilihan tersendiri, bukan bagian dari
    anjungan. Sebelumnya keduanya satu tombol bernama "Layar Pengunjung",
    dan mesin televisi terpaksa dibuka lewat login akun DISPLAY.
    """
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


def test_mode_dialog_loket_satu_tombol(qtbot):
    """
    Loket satu tombol. Beberapa petugas berbagi komputer, jadi yang
    membedakan administrator dan petugas adalah akun yang masuk.
    """

    from app.ui.login.mode_dialog import LAYAR_ANTRIAN, LAYAR_PETUGAS, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)

    kartu = [
        b for b in dialog.findChildren(QPushButton) if b.objectName() == "kartuMode"
    ]
    teks = [b.text() for b in kartu]
    # Anjungan adalah tablet Android, bukan pilihan di Windows.
    assert len(teks) == 2
    assert any("ANTRIAN" in t for t in teks)
    assert any("PETUGAS" in t for t in teks)
    assert not any("ANJUNGAN" in t for t in teks)
    assert not any("ADMIN" in t for t in teks)
    assert LAYAR_ANTRIAN != LAYAR_PETUGAS
    assert any(
        b.text() == "Atur komputer ini" for b in dialog.findChildren(QPushButton)
    )


def test_mode_dialog_satu_tombol_petugas_bila_wajib_login(qtbot, monkeypatch):
    """Pada .exe, peran dipisah oleh akun yang masuk, bukan oleh tombol."""
    monkeypatch.setenv("ANTRIAN_LEWATI_LOGIN", "0")

    from app.ui.login.mode_dialog import ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)

    kartu = [
        b for b in dialog.findChildren(QPushButton) if b.objectName() == "kartuMode"
    ]
    teks = [b.text() for b in kartu]
    assert len(teks) == 2
    assert not any("ADMIN" in t for t in teks)
    assert any("PETUGAS" in t for t in teks)
    assert not any("ANJUNGAN" in t for t in teks)
    assert any(
        b.text() == "Atur komputer ini" for b in dialog.findChildren(QPushButton)
    )


def test_mode_dialog_memilih_layar_petugas(qtbot):
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


def test_mode_dialog_tidak_menawarkan_masuk_admin_tanpa_sandi(qtbot):
    """Tidak ada kartu yang masuk sebagai administrator tanpa akun."""

    from app.ui.login.mode_dialog import ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)
    kartu = [
        b for b in dialog.findChildren(QPushButton) if b.objectName() == "kartuMode"
    ]

    assert not any("ADMIN" in b.text() for b in kartu)


def test_dialog_mesin_bawaan_satu_komputer(qtbot, app_config):
    from PySide6.QtWidgets import QDialog

    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    assert dialog.radio_sendiri.isChecked()
    assert dialog._panel_postgres.isHidden()
    assert dialog._panel_server.isHidden()
    dialog._simpan()
    assert dialog.result() == int(QDialog.DialogCode.Accepted)
    assert dialog.pengaturan_tersimpan is not None
    assert dialog.pengaturan_tersimpan.peran == "sendiri"


def test_dialog_mesin_server_hanya_menampilkan_sandi(qtbot, app_config):
    """Port, database, dan pengguna tidak lagi diubah dari dialog ini."""
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_server.setChecked(True)
    dialog._perbarui_tampilan()

    assert dialog.isian_port.isHidden()
    assert dialog.isian_database.isHidden()
    assert dialog.isian_pengguna.isHidden()
    assert not dialog.isian_sandi.isHidden()
    assert not dialog._tombol_siapkan.isHidden()
    assert dialog._tombol_cari.isHidden()


def test_dialog_sandi_berubah_minta_diketik_ulang(qtbot, app_config):
    from PySide6.QtWidgets import QDialog

    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_server.setChecked(True)
    dialog._perbarui_tampilan()
    dialog._sandi_tersimpan = "sandi-lama"
    dialog.isian_sandi.setText("sandi-lama")
    dialog._perbarui_ulang_sandi()
    assert dialog._baris_ulang.isHidden()

    dialog.isian_sandi.setText("sandi-baru")
    assert not dialog._baris_ulang.isHidden()
    dialog.isian_ulang.setText("tidak-sama")
    dialog._simpan()
    assert dialog.result() != int(QDialog.DialogCode.Accepted)
    assert "ulang" in dialog._label_error.text().lower()


def test_dialog_penolakan_antrian_tidak_mengosongkan_sandi(qtbot, app_config):
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_server.setChecked(True)
    dialog._perbarui_tampilan()
    dialog.isian_sandi.setText("salah")
    dialog._sesudah_gagal_sambungan(
        "PostgreSQL menolak pengguna antrian. Kata sandinya tidak cocok."
    )

    assert dialog.isian_sandi.text() == "salah"
    assert dialog.isian_port.isHidden()
    assert "siapkan database" in dialog._label_error.text().lower()
    assert "belum ada" in dialog._label_error.text().lower()


def test_dialog_port_muncul_bila_tidak_menjawab(qtbot, app_config):
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_server.setChecked(True)
    dialog._perbarui_tampilan()
    assert dialog.isian_port.isHidden()

    dialog._sesudah_gagal_sambungan(
        "Tidak dapat menghubungi database. PostgreSQL tidak menjawab."
    )

    assert not dialog.isian_port.isHidden()
    dialog.isian_port.setValue(5433)
    assert dialog._pengaturan_dari_form().port == 5433


def test_dialog_dapat_menampilkan_sandi_lalu_menyembunyikannya(qtbot, app_config):
    from PySide6.QtWidgets import QLineEdit

    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.isian_sandi.setText("rahasia-db")
    dialog.isian_ulang.setText("rahasia-db")

    assert dialog.isian_sandi.echoMode() == QLineEdit.EchoMode.Password
    dialog._tukar_tampil_sandi()
    assert dialog.isian_sandi.echoMode() == QLineEdit.EchoMode.Normal
    assert dialog.isian_ulang.echoMode() == QLineEdit.EchoMode.Normal
    assert dialog._tombol_tampil_sandi.text() == "Sembunyikan"

    dialog._tukar_tampil_sandi()
    assert dialog.isian_sandi.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.isian_sandi.text() == "rahasia-db"


def test_dialog_ubah_port_hanya_untuk_loket_admin(qtbot, app_config):
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_server.setChecked(True)
    dialog._perbarui_tampilan()
    dialog._pilih_nilai(dialog.pilih_peran, "petugas")

    assert dialog._tombol_ubah_port.isHidden()
    dialog._buka_ubah_port()
    assert dialog.isian_port.isHidden()

    dialog._pilih_nilai(dialog.pilih_peran, "admin")
    assert not dialog._tombol_ubah_port.isHidden()
    dialog._buka_ubah_port()
    assert not dialog.isian_port.isHidden()


def test_dialog_mesin_server_menampilkan_alamat(qtbot, app_config):
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_server.setChecked(True)
    dialog._perbarui_tampilan()
    assert not dialog._panel_server.isHidden()
    assert not dialog._panel_postgres.isHidden()
    assert dialog.isian_host.isHidden()
    assert "alamat" in dialog._label_alamat.text().lower()


def test_dialog_mesin_klien_wajib_alamat_server(qtbot, app_config):
    from PySide6.QtWidgets import QDialog

    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_klien.setChecked(True)
    dialog._perbarui_tampilan()
    assert not dialog.isian_host.isHidden()
    dialog.isian_host.setText("")
    dialog._simpan()
    assert dialog.result() != int(QDialog.DialogCode.Accepted)
    assert dialog._label_error.isVisible() or dialog._label_error.text()
    assert "Alamat" in dialog._label_error.text()


def test_dialog_mesin_klien_menyimpan_alamat(qtbot, app_config):
    from PySide6.QtWidgets import QDialog

    from app.core.mesin import baca_berkas_mesin, path_berkas_mesin
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_klien.setChecked(True)
    dialog._perbarui_tampilan()
    dialog.isian_host.setText("192.168.1.10")
    dialog.isian_pengguna.setText("antrian")
    dialog.isian_sandi.setText("rahasia-loket")
    dialog._simpan()
    assert dialog.result() == int(QDialog.DialogCode.Accepted)
    tersimpan = baca_berkas_mesin(path_berkas_mesin(app_config.db_path))
    assert tersimpan is not None
    assert tersimpan.host == "192.168.1.10"
    assert tersimpan.sandi == "rahasia-loket"


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


def test_pencetak_mesin_dipakai_jendela_utama(qtbot, auth, antrian_siap, env_mesin):
    """
    Komputer loket tanpa pencetak tiket tidak boleh ikut mencoba mencetak
    hanya karena pengaturan bersama menyebut "Cetak ke printer Windows".
    """
    from app.services.ticket_service import NullTicketPrinter
    from app.ui.main_window import MainWindow
    from tests.conftest import TEST_PASSWORD

    env_mesin(ANTRIAN_PRINTER="none")
    SettingsService(auth).set("ticket.printer", "system")

    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert isinstance(jendela.ticket_service.printer, NullTicketPrinter)


# ---------------------------------------------------------------------
# Media per jenis layanan
# ---------------------------------------------------------------------

@pytest.fixture
def folder_media(tmp_path, monkeypatch):
    """Alihkan media/kiosk ke folder sementara milik test ini."""
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)
    return folder


def _gambar(path):
    """PNG 1x1 yang benar-benar dapat dimuat QPixmap."""
    from PySide6.QtGui import QImage

    gambar = QImage(1, 1, QImage.Format.Format_RGB32)
    gambar.fill(0)
    assert gambar.save(str(path))
    return path


def test_media_layanan_menolak_kode_yang_merayap_keluar(folder_media):
    """
    `code` datang dari isian admin dan tidak boleh jadi jalan ke luar
    folder media, persis seperti penjagaan pada path_media_kios.
    """
    from app.ui.kiosk.sambutan import folder_media_layanan

    assert folder_media_layanan("..") is None
    assert folder_media_layanan("../rahasia") is None
    assert folder_media_layanan("a/b") is None
    assert folder_media_layanan("") is None
    assert folder_media_layanan("   ") is None
    assert folder_media_layanan("KONSULTASI") is not None


def test_media_layanan_mengambil_berkas_pertama_menurut_nama(folder_media):
    """Satu berkas, bukan playlist — layar konfirmasi terlalu singkat."""
    from app.ui.kiosk.sambutan import folder_media_layanan, media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "02_kedua.png")
    _gambar(folder / "01_pertama.png")

    assert media_layanan("KONSULTASI").name == "01_pertama.png"


def test_media_layanan_kosong_bila_belum_ada_berkas(folder_media):
    from app.ui.kiosk.sambutan import media_layanan

    assert media_layanan("KONSULTASI") is None


def test_folder_layanan_tidak_ikut_diputar_sebagai_sambutan(folder_media):
    """
    Subfolder layanan hidup DI DALAM media/kiosk. Kalau ikut terbaca,
    putaran sambutan akan mencoba memutar sebuah folder.
    """
    from app.ui.kiosk.sambutan import daftar_media_kios, folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "info.png")
    _gambar(folder_media / "sambutan.png")

    assert [p.name for p in daftar_media_kios()] == ["sambutan.png"]


def test_pasang_media_layanan_mengganti_berkas_sebelumnya(folder_media):
    """
    Hanya berkas pertama menurut nama yang pernah tampil. Berkas lama yang
    dibiarkan menumpuk membuat pilihan admin tampak tidak berpengaruh.
    """
    from app.ui.kiosk.sambutan import (
        folder_media_layanan,
        media_layanan,
        salin_ke_media_layanan,
    )

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "01_lama.png")

    sumber = _gambar(folder_media.parent / "99_baru.png")
    salin_ke_media_layanan("KONSULTASI", sumber)

    assert [p.name for p in folder.iterdir()] == ["99_baru.png"]
    assert media_layanan("KONSULTASI").name == "99_baru.png"


def test_hapus_media_layanan_mengosongkan_folder(folder_media):
    from app.ui.kiosk.sambutan import (
        folder_media_layanan,
        hapus_media_layanan,
        media_layanan,
    )

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "info.png")

    hapus_media_layanan("KONSULTASI")

    assert media_layanan("KONSULTASI") is None


# ---------------------------------------------------------------------
# Panel anjungan: media layanan dan kartu nomor
# ---------------------------------------------------------------------


# ---------------------------------------------------------------------
# Video jenis layanan diulang sampai pengunjung memilih
# ---------------------------------------------------------------------

def _panel_dengan_video_layanan(halaman_kios, folder_media):
    """
    Panel anjungan yang sedang memegang video sebuah jenis layanan.

    Berkasnya palsu — yang diuji keputusan detaknya, bukan kemampuan Qt
    memutar berkas. Pola yang sama dipakai test putaran sambutan.
    """
    from app.ui.kiosk.sambutan import HALAMAN_VIDEO, folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    berkas = folder / "info.mp4"
    berkas.write_bytes(b"bukan video sungguhan, cukup ada namanya")

    layanan = next(k for k in halaman_kios.kategori if k.code == "KONSULTASI")
    halaman_kios._pilih_layanan(layanan)

    panel = halaman_kios.papan.panel_info_kios
    panel._berkas_layanan = berkas
    panel.berkas_tampil = berkas
    panel._tampilkan_halaman(HALAMAN_VIDEO)
    panel._dijeda_sengaja = False
    panel._sedang_ganti_item = False
    panel._mulai_jam_item()
    return panel


# ---------------------------------------------------------------------
# Dialog: komputer ini dipakai sebagai apa
# ---------------------------------------------------------------------

def test_dialog_mesin_bawaan_peran_belum_ditetapkan(qtbot, app_config):
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)

    assert dialog.pilih_peran.currentData() == ""
    assert dialog.pilih_pencetak.currentData() is None
    assert dialog.pilih_suara.currentData() is None
    assert dialog.pilih_bentuk.currentData() is None


def test_dialog_mesin_menyimpan_peran_ke_berkasnya_sendiri(qtbot, app_config):
    from app.core.peran import baca_peran, path_berkas_peran
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog._pilih_nilai(dialog.pilih_peran, "televisi")
    dialog._simpan()

    tersimpan = baca_peran(path_berkas_peran(app_config.db_path))

    assert tersimpan.peran == "televisi"
    assert tersimpan.mode == "antrian"
    assert not tersimpan.disesuaikan


def test_kata_sandi_database_tidak_pernah_masuk_berkas_peran(qtbot, app_config):
    """
    peran.json dirancang untuk DISALIN ke komputer lain sebagai contekan.
    Kata sandi yang ikut tersalin akan menyebar ke tujuh mesin sekaligus.
    """
    from app.core.peran import path_berkas_peran
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog.radio_klien.setChecked(True)
    dialog._perbarui_tampilan()
    dialog.isian_host.setText("192.168.1.10")
    dialog.isian_pengguna.setText("antrian")
    dialog.isian_sandi.setText("rahasia-sekali")
    dialog._pilih_nilai(dialog.pilih_peran, "anjungan")
    dialog._simpan()

    isi = path_berkas_peran(app_config.db_path).read_text(encoding="utf-8")

    assert "rahasia-sekali" not in isi
    assert "192.168.1.10" not in isi


def test_memilih_peran_memperlihatkan_apa_yang_disimpulkannya(qtbot, app_config):
    """
    Inilah yang membuat perannya terbaca tanpa membuka dokumen mana pun:
    memilih papan memanjang langsung memperlihatkan bahwa mesin itu DIAM.
    """
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)

    # Anjungan bukan lagi peran komputer Windows.
    assert "anjungan" not in [
        dialog.pilih_peran.itemData(i) for i in range(dialog.pilih_peran.count())
    ]
    dialog._pilih_nilai(dialog.pilih_peran, "papan-memanjang")
    assert "diam" in dialog.pilih_suara.itemText(0).lower()

    dialog._pilih_nilai(dialog.pilih_peran, "televisi")
    assert "ikut pengaturan" in dialog.pilih_suara.itemText(0).lower()
    assert "tidak mencetak" in dialog.pilih_pencetak.itemText(0).lower()

    dialog._pilih_nilai(dialog.pilih_peran, "papan-memanjang")
    assert "memanjang" in dialog.pilih_bentuk.itemText(0).lower()


def test_penimpaan_per_isian_tersimpan_sebagai_kehendak(qtbot, app_config):
    """
    Televisi yang dibuat diam menyimpan `False`, bukan mengikuti tabel.
    Isian yang dibiarkan tetap `null` supaya ikut bila tabelnya diperbaiki.
    """
    from app.core.peran import baca_peran, path_berkas_peran
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog._pilih_nilai(dialog.pilih_peran, "televisi")
    dialog._pilih_nilai(dialog.pilih_suara, False)
    dialog._simpan()

    tersimpan = baca_peran(path_berkas_peran(app_config.db_path))

    assert tersimpan.suara is False
    assert tersimpan.printer is None
    assert tersimpan.disesuaikan


def test_peran_yang_berganti_menuntut_buka_ulang(qtbot, app_config):
    """
    Mode dibaca sekali saat peluncuran, jadi televisi yang baru ditetapkan
    tetap menampilkan layar yang sedang terbuka sampai dijalankan lagi.
    """
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog._pilih_nilai(dialog.pilih_peran, "televisi")
    dialog._simpan()

    assert dialog.memerlukan_buka_ulang


def test_peran_yang_tidak_berubah_tidak_menuntut_buka_ulang(qtbot, app_config):
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog._simpan()

    assert not dialog.memerlukan_buka_ulang


def test_dialog_memuat_kembali_peran_yang_sudah_tersimpan(qtbot, app_config):
    from app.core.peran import PeranKomputer, path_berkas_peran, tulis_peran
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    tulis_peran(
        path_berkas_peran(app_config.db_path),
        PeranKomputer(peran="papan-memanjang", suara=True),
    )

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)

    assert dialog.pilih_peran.currentData() == "papan-memanjang"
    assert dialog.pilih_suara.currentData() is True
    assert dialog.pilih_bentuk.currentData() is None


def test_uji_cetak_menolak_mesin_yang_tidak_mencetak(qtbot, app_config):
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog._pilih_nilai(dialog.pilih_peran, "televisi")
    dialog._uji_cetak()

    assert "tidak mencetak" in dialog._label_error.text().lower()


def test_uji_cetak_mengatakan_bila_caranya_belum_dipilih(qtbot, app_config):
    """
    Anjungan mengikuti pengaturan bersama, yang baru terbaca sesudah
    database tersambung — sedangkan dialog ini tampil sebelum itu.
    """
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    dialog = SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog._pilih_nilai(dialog.pilih_peran, "anjungan")
    dialog._uji_cetak()

    assert "pilih cara mencetak" in dialog._label_error.text().lower()


def test_uji_cetak_pdf_menghasilkan_berkas(qtbot, app_config, monkeypatch):
    """
    Pasangan Uji koneksi. Pencetak yang keliru biasanya baru ketahuan
    ketika pengunjung pertama sudah berdiri di depan anjungan.
    """
    from app.ui import common
    from app.ui.login import setup_mesin_dialog as modul

    # Ditambal di app.ui.common, bukan di modul dialognya: dialog
    # mengimpornya DI DALAM fungsi, sehingga yang dipanggil selalu yang
    # asli — dan yang asli membuka kotak modal yang menggantung test.
    monkeypatch.setattr(common, "tampilkan_info", lambda *a, **k: None)

    dialog = modul.SetupMesinDialog()
    qtbot.addWidget(dialog)
    dialog._pilih_nilai(dialog.pilih_peran, "anjungan")
    dialog._pilih_nilai(dialog.pilih_pencetak, "pdf")
    dialog._uji_cetak()

    berkas = list((app_config.base_dir / "tiket").glob("*.pdf"))

    assert dialog._label_error.text() == ""
    assert berkas, "tiket contoh tidak tertulis"


def test_tiket_contoh_tidak_menyerupai_nomor_sungguhan():
    """
    Kertas uji yang tertinggal di meja anjungan tidak boleh terbaca
    sebagai giliran milik siapa pun.
    """
    from app.ui.login.setup_mesin_dialog import _tiket_contoh

    tiket = _tiket_contoh()

    assert "UJI" in tiket.queue_number
    assert "bukan nomor antrian" in tiket.footer.lower()
