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
    assert len(keadaan.loket) == 3
    assert all(item.antrian is None for item in keadaan.loket)
    assert [item.counter_name for item in keadaan.loket] == [
        "Loket 1",
        "Loket 2",
        "Loket 3",
    ]


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


def test_layar_menampilkan_panggilan_per_loket(terbitkan, antrian_siap, auth):
    """Setiap loket menampilkan nomornya sendiri, bukan hanya yang terakhir."""
    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    q = QueueService(auth)
    q.call_next(antrian_siap["loket"][0])
    q.call_next(antrian_siap["loket"][1])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    keadaan = QueueService(auth).display_state()

    per_nama = {item.counter_name: item.antrian for item in keadaan.loket}
    assert per_nama["Loket 1"].queue_number == "A-001"
    assert per_nama["Loket 2"].queue_number == "A-002"
    assert per_nama["Loket 3"] is None
    assert keadaan.terkini.queue_number == "A-002"


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
    assert len(halaman_layar.kartu_loket) == 3
    for kartu in halaman_layar.kartu_loket:
        assert kartu.label_nomor.text() == "—"
        assert kartu.label_status.text() == "KOSONG"
        assert "Siap" in kartu.label_layanan.text()


def test_layar_menampilkan_nomor_dan_loket(halaman_layar, terbitkan, antrian_siap, auth):
    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][1])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    per_nama = {k.label_nama.text(): k for k in halaman_layar.kartu_loket}
    assert per_nama["LOKET 2"].label_nomor.text() == "A-001"
    assert per_nama["LOKET 2"].label_layanan.text() == "Konsultasi"
    assert per_nama["LOKET 2"].label_status.text() == "SEDANG DIPANGGIL"
    assert per_nama["LOKET 1"].label_nomor.text() == "—"
    assert per_nama["LOKET 3"].label_nomor.text() == "—"


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


def test_label_kartu_tidak_membawa_latarnya_sendiri(halaman_layar):
    """
    Label di dalam kartu tidak boleh melukis latarnya sendiri; kotak
    berwarna yang tidak diminta terbaca sebagai cacat, bukan desain.

    Pengecualiannya satu dan disengaja: pil status memang berlatar, dan
    warnanya diambil dari palet tema.
    """
    kartu = halaman_layar.kartu_loket[0]
    for label in (kartu.label_nomor, kartu.label_nama, kartu.label_layanan):
        assert "background: transparent" in label.styleSheet()

    palet = halaman_layar.palet
    if palet.status_berpil:
        assert palet.pil_latar_mati in kartu.label_status.styleSheet()
    else:
        assert "background: transparent" in kartu.label_status.styleSheet()


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


def test_nomor_berikutnya_memakai_warna_palet(halaman_layar, terbitkan, auth):
    """
    Nomor berikutnya mengambil warna dari palet tema, bukan dari warna yang
    ditulis lepas di tempat lain.
    """
    terbitkan("A", 3)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    widget = halaman_layar.baris_berikutnya.itemAt(0).widget()
    gaya = widget.styleSheet()
    assert halaman_layar.palet.chip_teks in gaya
    assert halaman_layar.palet.chip in gaya


def test_loket_unggulan_saat_baru_dipanggil(
    halaman_layar, terbitkan, antrian_siap, auth
):
    from app.ui.style import DISPLAY_AKSEN

    for kartu in halaman_layar.kartu_loket:
        assert kartu.label_status.text() == "KOSONG"

    terbitkan("A", 1)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    unggulan = halaman_layar.kartu_loket[0]
    assert unggulan.label_status.text() == "SEDANG DIPANGGIL"
    assert unggulan.label_nomor.text() == "A-001"
    assert DISPLAY_AKSEN in unggulan.styleSheet()


# ---------------------------------------------------------------------
# Televisi ruang tunggu vs papan di dalam kios
# ---------------------------------------------------------------------

def _ukuran_huruf(widget) -> int:
    """Ukuran huruf yang benar-benar tertulis pada stylesheet widget."""
    import re

    cocok = re.search(r"font-size:\s*(\d+)px", widget.styleSheet())
    assert cocok is not None, widget.styleSheet()
    return int(cocok.group(1))


@pytest.fixture
def papan_kios(qtbot, auth, antrian_siap):
    """Papan versi kompak, seperti yang dipasang di dalam layar kios."""
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        kompak=True,
    )
    qtbot.addWidget(halaman)
    return halaman


def test_huruf_televisi_jauh_lebih_besar_daripada_kios(halaman_layar, papan_kios):
    """
    Televisi dibaca dari seberang ruangan, kios dari jarak satu lengan.

    Selisihnya harus tegas. Papan televisi yang hanya sedikit lebih besar
    daripada kios terbaca sebagai kios yang kehilangan panel bawahnya.
    """
    for kunci in ("nomor", "nama", "judul", "layanan"):
        assert halaman_layar.px(kunci) > papan_kios.px(kunci) * 1.4, kunci

    besar = halaman_layar.kartu_loket[0]
    kecil = papan_kios.kartu_loket[0]
    assert _ukuran_huruf(besar.label_nomor) > _ukuran_huruf(kecil.label_nomor) * 1.4


def test_margin_televisi_lebih_lapang_daripada_kios(halaman_layar, papan_kios):
    tv = halaman_layar.susunan.contentsMargins()
    kios = papan_kios.susunan.contentsMargins()

    assert tv.left() > kios.left()
    assert tv.top() > kios.top()
    assert halaman_layar.kisi_loket.spacing() > papan_kios.kisi_loket.spacing()


def test_huruf_televisi_membesar_mengikuti_tinggi_layar(halaman_layar):
    """Televisi 1080p harus mendapat huruf lebih besar daripada jendela kecil."""
    assert halaman_layar.hitung_skala(1080, 1920) > halaman_layar.hitung_skala(700, 1920)
    assert halaman_layar.hitung_skala(1080, 1920) > 1.0


def test_kartu_ikut_membesar_saat_layar_diperbesar(qtbot, halaman_layar):
    sebelum = _ukuran_huruf(halaman_layar.kartu_loket[0].label_nomor)

    halaman_layar.resize(1920, 1080)
    halaman_layar.show()
    qtbot.waitExposed(halaman_layar)

    assert halaman_layar.skala > 1.0
    assert halaman_layar.kartu_loket[0].skala == halaman_layar.skala
    assert _ukuran_huruf(halaman_layar.kartu_loket[0].label_nomor) > sebelum


def test_huruf_menyusut_pada_layar_lebar_tetapi_pendek(halaman_layar):
    """
    Tiga kartu berjajar: lebar layar ikut menentukan besar huruf.

    Tinggi yang cukup tidak menjamin nomor lima huruf muat di dalam kartu
    yang sempit.
    """
    lebar = halaman_layar.hitung_skala(1080, 900)
    lapang = halaman_layar.hitung_skala(1080, 1920)

    assert lebar < lapang


def test_papan_dapat_mengecil_lagi_setelah_layar_penuh(qtbot, halaman_layar):
    """
    Esc menurunkan layar penuh, dan jendelanya harus benar-benar mengecil.

    Bila huruf 112px milik tiga kartu ikut menentukan ukuran minimum,
    jendela "normal" tetap sebesar layar televisi dan Esc terasa tidak
    berfungsi.
    """
    from PySide6.QtWidgets import QApplication

    def _ubah_ukuran(lebar, tinggi):
        halaman_layar.resize(lebar, tinggi)
        QApplication.processEvents()
        halaman_layar.layout().activate()

    halaman_layar.show()
    qtbot.waitExposed(halaman_layar)

    _ubah_ukuran(1920, 1080)
    assert halaman_layar.skala > 1.0

    _ubah_ukuran(1100, 700)

    assert halaman_layar.size().toTuple() == (1100, 700)
    label = halaman_layar.kartu_loket[0].label_nomor
    assert label.sizeHint().width() <= label.width()


def test_papan_kios_tidak_ikut_membesar(qtbot, papan_kios):
    """
    Papan kios harus tetap kompak di layar penuh.

    Bila ikut membesar, ia menelan panel ambil nomor dan nama layanan di
    bawah tombol A/B/C terpotong.
    """
    sebelum = _ukuran_huruf(papan_kios.kartu_loket[0].label_nomor)

    assert papan_kios.hitung_skala(1080) == 1.0
    papan_kios.resize(1920, 1080)
    papan_kios.show()
    qtbot.waitExposed(papan_kios)

    assert papan_kios.skala == 1.0
    assert _ukuran_huruf(papan_kios.kartu_loket[0].label_nomor) == sebelum


def test_kartu_loket_mendapat_porsi_layar_lebih_besar_di_televisi(
    halaman_layar, papan_kios
):
    """Di televisi, kartu loket yang mengisi layar — bukan panel bawahnya."""
    def _stretch(halaman):
        panel_loket = halaman.kisi_loket.parentWidget()
        return (
            halaman.susunan.stretch(halaman.susunan.indexOf(panel_loket)),
            halaman.susunan.stretch(
                halaman.susunan.indexOf(halaman.panel_berikutnya)
            ),
        )

    loket_tv, berikutnya_tv = _stretch(halaman_layar)
    loket_kios, berikutnya_kios = _stretch(papan_kios)

    assert loket_tv / berikutnya_tv > loket_kios / berikutnya_kios


# ---------------------------------------------------------------------
# Jam pada kepala papan
# ---------------------------------------------------------------------

def test_teks_waktu_memakai_nama_hari_dan_bulan_indonesia():
    """
    Komputer layar sering berbahasa Inggris. Papan yang menghadap publik
    tidak boleh berbunyi "Wednesday, August".
    """
    from datetime import datetime

    from app.ui.display.display_page import teks_waktu

    teks = teks_waktu(datetime(2026, 8, 26, 9, 5, 3))

    assert teks == "Rabu, 26 Agustus 2026  ·  09:05:03"


def test_kepala_papan_menampilkan_tanggal_dan_jam(halaman_layar, monkeypatch):
    from datetime import datetime

    from app.core import clock

    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 8, 26, 14, 30, 0))
    halaman_layar.perbarui_jam()

    assert halaman_layar.label_jam.text() == "Rabu, 26 Agustus 2026  ·  14:30:00"


def test_jam_ikut_diperbarui_saat_data_disegarkan(halaman_layar, monkeypatch):
    from datetime import datetime

    from app.core import clock

    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 8, 26, 7, 0, 1))
    halaman_layar.muat_ulang()

    assert "07:00:01" in halaman_layar.label_jam.text()


def test_jam_berdetik_tiap_detik(qtbot, auth, antrian_siap):
    """
    Jam berdetik sendiri, tidak menunggu penyegaran data.

    Papan yang jamnya berhenti membuat pengunjung mengira layarnya
    menggantung.
    """
    from app.ui.display.display_page import SELANG_JAM_MS, DisplayPage

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=True
    )
    qtbot.addWidget(halaman)

    assert SELANG_JAM_MS == 1_000
    assert halaman.pewaktu_jam.isActive()
    assert halaman.pewaktu_jam.interval() == SELANG_JAM_MS

    halaman.hentikan()
    assert not halaman.pewaktu_jam.isActive()


def test_jam_tidak_lebih_menonjol_daripada_nomor_loket(halaman_layar, papan_kios):
    """Yang dicari pengunjung dari jauh adalah nomornya, bukan jamnya."""
    for halaman in (halaman_layar, papan_kios):
        assert halaman.px("jam") < halaman.px("nomor")
        assert halaman.px("jam") <= halaman.px("judul")

    assert _ukuran_huruf(halaman_layar.label_jam) < _ukuran_huruf(
        halaman_layar.kartu_loket[0].label_nomor
    )


# ---------------------------------------------------------------------
# Tema layar antrian
# ---------------------------------------------------------------------

def test_seluruh_tema_terdaftar_di_pengaturan():
    """
    Daftar pilihan di SKEMA pengaturan ditulis ulang, terpisah dari
    app.ui.display.tema, karena service tidak boleh bergantung pada
    lapisan tampilan. Keduanya wajib berisi kode tema yang sama persis,
    supaya memilih sebuah tema di layar Pengaturan tidak pernah menunjuk
    ke tema yang sebenarnya tidak ada.
    """
    from app.services.settings_service import SKEMA
    from app.ui.display.tema import PALET

    butir = next(p for p in SKEMA if p.kunci == "display.theme")
    kode_pengaturan = {kode for kode, _ in butir.pilihan}

    assert kode_pengaturan == set(PALET)


@pytest.mark.parametrize("kode_tema", ["gelap", "terang", "sorotan", "split", "led"])
def test_setiap_tema_dapat_dibuka_dan_menampilkan_loket(
    qtbot, auth, antrian_siap, terbitkan, kode_tema
):
    """Kelima tema harus bisa dibuka dan menampilkan seluruh loket, bukan sebagian."""
    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 2)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema=kode_tema,
    )
    qtbot.addWidget(halaman)

    assert halaman.palet.kode == kode_tema
    assert len(halaman.kartu_loket) == 3
    assert [k.label_nama.text() for k in halaman.kartu_loket] == [
        "LOKET 1",
        "LOKET 2",
        "LOKET 3",
    ]


def test_tema_dibaca_dari_pengaturan_bila_tidak_ditentukan(qtbot, auth, antrian_siap):
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.theme", "led")

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)

    assert halaman.palet.kode == "led"


def test_tema_tidak_dikenal_jatuh_ke_tema_bawaan(qtbot, auth, antrian_siap):
    """
    Nilai rusak di database (sisa versi lama, atau suntingan langsung) tidak
    boleh membuat layar publik gagal terbuka.
    """
    from app.ui.display.display_page import DisplayPage
    from app.ui.display.tema import TEMA_BAWAAN

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema="tema-yang-tidak-ada",
    )
    qtbot.addWidget(halaman)

    assert halaman.palet.kode == TEMA_BAWAAN


def test_tema_sorotan_menampilkan_panggilan_terbaru_di_panel_besar(
    qtbot, auth, antrian_siap, terbitkan
):
    """Hanya tema Sorotan yang punya panel besar terpisah untuk panggilan terbaru."""
    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema="sorotan",
    )
    qtbot.addWidget(halaman)

    assert halaman.kartu_sorot is not None
    assert halaman.kartu_sorot.label_nomor.text() == "A-001"
    # Seluruh loket tetap tampil di kolom, bukan hanya yang sedang dipanggil.
    assert len(halaman.kartu_loket) == 3


def test_tema_split_menampilkan_seluruh_loket_di_kolom(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Split tidak punya panel sorotan terpisah — panggilan terbaru ditandai
    lewat kartu yang menyala pada kolom yang sama dengan loket lain.
    """
    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema="split",
    )
    qtbot.addWidget(halaman)

    assert halaman.kartu_sorot is None
    assert len(halaman.kartu_loket) == 3
    per_nama = {k.label_nama.text(): k for k in halaman.kartu_loket}
    assert per_nama["LOKET 1"].label_nomor.text() == "A-001"


def test_tema_split_menampilkan_pengumuman_dari_pengaturan(qtbot, auth, antrian_siap):
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.info", "Bawa fotokopi KTP untuk pengurusan berkas.")

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema="split",
    )
    qtbot.addWidget(halaman)

    assert halaman.panel_info is not None
    assert "fotokopi KTP" in halaman.label_info.text()


def test_kios_selalu_kisi_walau_tema_sorotan(qtbot, auth, antrian_siap):
    """
    Sorotan dan Split menuntut tinggi yang tidak dimiliki separuh layar
    kios; memaksakannya berarti nama layanan di panel ambil nomor yang
    mengalah. Kios sengaja selalu memakai tata letak kisi, warna tetap
    mengikuti tema yang dipilih.
    """
    from app.ui.display.display_page import DisplayPage
    from app.ui.display.tema import KISI

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        kompak=True,
        tema="sorotan",
    )
    qtbot.addWidget(halaman)

    assert halaman.tata_letak == KISI
    assert halaman.kartu_sorot is None
    assert len(halaman.kartu_loket) == 3


def test_tidak_ada_warna_delapan_digit_di_seluruh_tema(qtbot, auth, antrian_siap, terbitkan):
    """
    Qt tidak mendukung #RRGGBBAA dan membacanya sebagai warna lain — sumber
    warna kuning yang tidak pernah diminta. Diperiksa untuk kelima tema,
    bukan hanya tema bawaan.
    """
    import re

    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])

    auth.logout()
    auth.login("display", TEST_PASSWORD)

    for kode_tema in ("gelap", "terang", "sorotan", "split", "led"):
        halaman = DisplayPage(
            QueueService(auth),
            SettingsService(auth),
            NullSoundPlayer(),
            otomatis=False,
            tema=kode_tema,
        )
        qtbot.addWidget(halaman)
        halaman.muat_ulang()

        gaya = [halaman.styleSheet()]
        for kartu in halaman.kartu_loket:
            gaya.append(kartu.styleSheet())
        for i in range(halaman.baris_berikutnya.count()):
            widget = halaman.baris_berikutnya.itemAt(i).widget()
            if widget is not None:
                gaya.append(widget.styleSheet())

        for potongan in gaya:
            assert not re.search(r"#[0-9A-Fa-f]{8}\b", potongan), (kode_tema, potongan)
