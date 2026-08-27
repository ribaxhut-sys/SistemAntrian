"""Test layar antrian untuk pengunjung."""

from __future__ import annotations

import pytest

from app.core.errors import AuthorizationError
from app.services.queue_service import QueueService
from app.services.settings_service import SettingsService
from app.services.sound_service import NullSoundPlayer
from tests.conftest import TEST_PASSWORD


# ---------------------------------------------------------------------
# Keadaan layar (service)
# ---------------------------------------------------------------------

def test_layar_kosong_saat_belum_ada_panggilan(display_queue):
    keadaan = display_queue.display_state()

    assert keadaan.terkini is None
    assert keadaan.berikutnya == []


def test_layar_menampilkan_nomor_yang_terakhir_dipanggil(
    display_queue, cro_queue, terbitkan, antrian_siap, auth
):
    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    keadaan = QueueService(auth).display_state()

    assert keadaan.terkini.queue_number == "A-001"
    assert keadaan.terkini.counter_name == "Loket 1"


def test_layar_menampilkan_panggilan_terbaru_bukan_yang_pertama(
    terbitkan, antrian_siap, auth
):
    """Yang tampil besar harus nomor yang barusan dipanggil."""
    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    q = QueueService(auth)
    q.call_next(antrian_siap["loket"][0])
    q.call_next(antrian_siap["loket"][1])
    q.call_next(antrian_siap["loket"][2])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    keadaan = QueueService(auth).display_state()

    assert keadaan.terkini.queue_number == "A-003"
    assert keadaan.terkini.counter_name == "Loket 3"


def test_daftar_berikutnya_dibatasi_jumlahnya(display_queue, terbitkan, auth):
    terbitkan("A", 6)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    keadaan = QueueService(auth).display_state(jumlah_berikutnya=3)
    assert [q.queue_number for q in keadaan.berikutnya] == ["A-001", "A-002", "A-003"]


def test_nomor_yang_sudah_dipanggil_hilang_dari_berikutnya(
    terbitkan, antrian_siap, auth
):
    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    keadaan = QueueService(auth).display_state()

    assert [q.queue_number for q in keadaan.berikutnya] == ["A-002", "A-003"]


@pytest.mark.parametrize("peran", ["cro", "registration", "supervisor", "admin"])
def test_hanya_akun_layar_yang_boleh_membaca_keadaan_layar(auth, antrian_siap, peran):
    """
    Hak DISPLAY_VIEW sengaja dipisah dari QUEUE_VIEW: komputer layar
    menghadap publik dan tidak diawasi.
    """
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        QueueService(auth).display_state()


# ---------------------------------------------------------------------
# Halaman layar (UI)
# ---------------------------------------------------------------------

@pytest.fixture
def halaman_layar(qtbot, auth, antrian_siap):
    """Layar tanpa penyegaran otomatis, agar test mengendalikan waktunya."""
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("display", TEST_PASSWORD)

    suara = NullSoundPlayer()
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), suara, otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.suara = suara
    return halaman


def test_layar_kosong_menyatakan_belum_ada_panggilan(halaman_layar):
    assert halaman_layar.label_nomor.text() == "—"
    assert "Belum ada nomor" in halaman_layar.label_layanan.text()


def test_layar_menampilkan_nomor_dan_loket(halaman_layar, terbitkan, antrian_siap, auth):
    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][1])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    assert halaman_layar.label_nomor.text() == "A-001"
    assert halaman_layar.label_loket.text() == "LOKET 2"
    assert halaman_layar.label_layanan.text() == "Konsultasi"


def test_layar_menampilkan_nomor_berikutnya(halaman_layar, terbitkan, auth):
    terbitkan("A", 4)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    tampil = [
        halaman_layar.baris_berikutnya.itemAt(i).widget().text()
        for i in range(halaman_layar.baris_berikutnya.count())
    ]
    assert tampil == ["A-001", "A-002", "A-003"]


def test_layar_menyatakan_saat_tidak_ada_yang_menunggu(halaman_layar):
    tampil = [
        halaman_layar.baris_berikutnya.itemAt(i).widget().text()
        for i in range(halaman_layar.baris_berikutnya.count())
    ]
    assert tampil == ["Tidak ada antrian menunggu"]


def test_layar_tidak_memiliki_tombol_apa_pun(halaman_layar):
    """
    Aturan tegas: layar antrian tidak boleh punya fungsi administrasi.
    Komputer ini menghadap publik dan tidak diawasi.
    """
    from PySide6.QtWidgets import QAbstractButton, QComboBox, QLineEdit

    for kelas in (QAbstractButton, QComboBox, QLineEdit):
        assert halaman_layar.findChildren(kelas) == [], (
            f"layar antrian tidak boleh memuat {kelas.__name__}"
        )


# ---------------------------------------------------------------------
# Suara
# ---------------------------------------------------------------------

def test_panggilan_baru_membunyikan_suara(halaman_layar, terbitkan, antrian_siap, auth):
    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    assert halaman_layar.suara.diumumkan == [("A-001", "Loket 1")]


def test_penyegaran_biasa_tidak_membunyikan_ulang(
    halaman_layar, terbitkan, antrian_siap, auth
):
    """
    Layar menyegar setiap dua detik. Tanpa penjaga, nada akan berbunyi
    terus-menerus untuk panggilan yang sama.
    """
    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    for _ in range(5):
        halaman_layar.muat_ulang()

    assert len(halaman_layar.suara.diumumkan) == 1


def test_panggil_ulang_membunyikan_lagi(halaman_layar, terbitkan, antrian_siap, auth):
    """
    Pemanggilan ULANG pada nomor yang sama harus berbunyi lagi — itulah
    gunanya memanggil ulang.
    """
    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    q = QueueService(auth)
    antrian = q.call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()
    halaman_layar.muat_ulang()
    assert len(halaman_layar.suara.diumumkan) == 1

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).recall(antrian.id)

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    assert len(halaman_layar.suara.diumumkan) == 2


def test_suara_dapat_dimatikan_lewat_pengaturan(
    qtbot, auth, antrian_siap, terbitkan, master_service
):
    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 1)
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.sound_enabled", "false")

    auth.login("cro", TEST_PASSWORD) if False else None
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    suara = NullSoundPlayer()
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), suara, otomatis=False
    )
    qtbot.addWidget(halaman)

    assert halaman.suara_aktif is False
    assert suara.diumumkan == []


# ---------------------------------------------------------------------
# Penyegaran berkala
# ---------------------------------------------------------------------

def test_penyegaran_otomatis_berjalan(qtbot, auth, antrian_siap, terbitkan):
    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 1)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=True
    )
    qtbot.addWidget(halaman)

    assert halaman.pewaktu.isActive()
    halaman.hentikan()
    assert not halaman.pewaktu.isActive()


# ---------------------------------------------------------------------
# Gaya tampilan
# ---------------------------------------------------------------------

def test_gaya_layar_dibatasi_pada_widgetnya_sendiri(halaman_layar):
    """
    Deklarasi "background" tanpa selector merambat ke seluruh widget anak.
    Akibatnya panel putih ikut berlatar biru dan nomor antrian — satu-satunya
    hal yang benar-benar dibaca pengunjung — menjadi tidak terlihat.
    """
    from PySide6.QtCore import Qt

    gaya = halaman_layar.styleSheet()

    assert "QWidget#" in gaya, "selector harus dibatasi dengan objectName"
    assert not gaya.strip().startswith("background")
    # Tanpa atribut ini, latar stylesheet tidak dilukis saat halaman
    # menempel sebagai anak (misalnya di kios), dan yang tampil hanya abu-abu Qt.
    assert halaman_layar.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)


def test_isi_panel_putih_memakai_latar_transparan(halaman_layar):
    """Label di atas panel putih tidak boleh membawa latarnya sendiri."""
    for label in (
        halaman_layar.label_nomor,
        halaman_layar.label_loket,
        halaman_layar.label_layanan,
        halaman_layar.label_status,
    ):
        assert "background: transparent" in label.styleSheet()


def test_tidak_ada_warna_heksadesimal_delapan_digit(halaman_layar, terbitkan, auth):
    """
    Qt tidak mendukung #RRGGBBAA dan membacanya sebagai warna lain —
    sumber warna kuning yang tidak pernah diminta.
    """
    import re

    terbitkan("A", 2)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    gaya = [halaman_layar.styleSheet()]
    for i in range(halaman_layar.baris_berikutnya.count()):
        widget = halaman_layar.baris_berikutnya.itemAt(i).widget()
        if widget is not None:
            gaya.append(widget.styleSheet())

    for potongan in gaya:
        assert not re.search(r"#[0-9A-Fa-f]{8}\b", potongan), potongan


def test_nomor_berikutnya_berkontras_tinggi(halaman_layar, terbitkan, auth):
    """
    Nomor berikutnya harus gelap di atas kartu terang. Teks putih di atas
    kaca transparan hampir tidak terbaca dari seberang ruangan.
    """
    from app.ui.style import DISPLAY_BERIKUTNYA_KARTU, DISPLAY_BERIKUTNYA_TEKS

    terbitkan("A", 3)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    widget = halaman_layar.baris_berikutnya.itemAt(0).widget()
    gaya = widget.styleSheet()
    assert DISPLAY_BERIKUTNYA_TEKS in gaya
    assert DISPLAY_BERIKUTNYA_KARTU in gaya


def test_loket_tampil_sebagai_lencana_saat_ada_panggilan(
    halaman_layar, terbitkan, antrian_siap, auth
):
    assert halaman_layar.bingkai_loket.isHidden()

    terbitkan("A", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    assert not halaman_layar.bingkai_loket.isHidden()
    assert halaman_layar.label_status.text() == "SEDANG DIPANGGIL"
