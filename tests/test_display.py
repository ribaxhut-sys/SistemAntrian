"""Test layar antrian untuk pengunjung."""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QApplication

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


def test_layar_menampilkan_seluruh_yang_menunggu(halaman_layar, terbitkan, auth):
    """
    Televisi menampilkan SELURUH yang menunggu, bukan tiga teratas.

    Yang dicari orang yang sudah duduk menunggu adalah nomornya sendiri.
    Daftar tiga nomor hanya menjawab "siapa berikutnya" — pertanyaan
    petugas, bukan pertanyaan pengunjung.
    """
    terbitkan("A", 4)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman_layar.muat_ulang()

    assert _nomor_tampil(halaman_layar) == ["A-001", "A-002", "A-003", "A-004"]


def test_papan_kios_tetap_ringkas(papan_kios, terbitkan, auth):
    """
    Papan di dalam anjungan tetap memakai `display.next_count`.

    Tempatnya dibutuhkan tombol ambil nomor di bawahnya, dan pengunjung
    yang berdiri di sana sedang mengambil nomor — bukan mencari nomornya
    sendiri di dalam daftar.
    """
    terbitkan("A", 6)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    papan_kios.muat_ulang()

    assert papan_kios.baris_berikutnya.count() == 3


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

    widget = halaman_layar.label_berikutnya[0]
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


def test_daftar_menunggu_mendapat_porsi_besar_di_televisi(
    halaman_layar, papan_kios
):
    """
    Televisi membagi layarnya rata antara kartu loket dan daftar menunggu.

    Di anjungan pembagian itu tidak berlaku: papannya harus tetap ringkas
    karena tombol ambil nomor di bawahnya yang lebih dibutuhkan orang yang
    sedang berdiri di sana.
    """
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

    assert berikutnya_tv / loket_tv > berikutnya_kios / loket_kios
    assert berikutnya_tv >= loket_tv


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


# ---------------------------------------------------------------------
# Daftar menunggu berhalaman
# ---------------------------------------------------------------------

@pytest.fixture
def layar_berhalaman(qtbot, auth, antrian_siap):
    """
    Layar televisi dengan halaman kecil, agar pergantiannya mudah diuji.

    Dua baris per kolom, dan setiap layanan mendapat dua kolom, sehingga
    satu halaman memuat empat nomor per jenis layanan.
    """
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.list_rows", "2")
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    return halaman


def _nomor_tampil(halaman) -> list[str]:
    """
    Nomor yang sedang tampil di daftar menunggu, tanpa judul kolomnya.

    Dibaca dari `label_berikutnya`, bukan dari kisinya: sejak daftar
    dipecah per jenis layanan, kisi itu juga memuat baris judul kolom.
    """
    return [label.text() for label in halaman.label_berikutnya]


def test_halaman_pertama_menampilkan_sebanyak_pengaturan(
    layar_berhalaman, terbitkan, auth
):
    terbitkan("A", 7)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    assert _nomor_tampil(layar_berhalaman) == ["A-001", "A-002", "A-003", "A-004"]
    assert layar_berhalaman.jumlah_halaman == 2


def test_halaman_berputar_dan_kembali_ke_awal(layar_berhalaman, terbitkan, auth):
    terbitkan("A", 7)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    layar_berhalaman.putar_halaman()
    assert _nomor_tampil(layar_berhalaman) == ["A-005", "A-006", "A-007"]

    layar_berhalaman.putar_halaman()
    assert _nomor_tampil(layar_berhalaman) == ["A-001", "A-002", "A-003", "A-004"]


def test_penyegaran_tidak_mengembalikan_ke_halaman_pertama(
    layar_berhalaman, terbitkan, auth
):
    """
    Inti dari fitur ini.

    Papan menyegar dua detik sekali sedangkan halaman berganti tiga detik
    sekali. Bila penyegaran ikut mengembalikan halaman ke satu, pengunjung
    tidak akan pernah melihat halaman kedua sama sekali.
    """
    terbitkan("A", 7)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()
    layar_berhalaman.putar_halaman()

    layar_berhalaman.muat_ulang()

    assert _nomor_tampil(layar_berhalaman) == ["A-005", "A-006", "A-007"]


def test_halaman_dijepit_saat_antrian_menyusut(
    layar_berhalaman, terbitkan, auth, antrian_siap
):
    """
    Nomor dipanggil satu per satu sepanjang hari, sehingga halaman terakhir
    dapat lenyap justru sementara layar sedang menampilkannya.

    Tanpa penjepitan, indeks halaman menunjuk ke potongan daftar yang sudah
    tidak ada dan panel bawah menjadi kosong — terbaca sebagai "tidak ada
    yang menunggu" padahal ruangannya masih penuh.
    """
    terbitkan("A", 7)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()
    layar_berhalaman.putar_halaman()
    assert layar_berhalaman._halaman == 1

    # Lima nomor dipanggil, menyisakan dua — dari tiga halaman tinggal satu.
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    layanan = QueueService(auth)
    for indeks in range(5):
        loket = antrian_siap["loket"][indeks % 2]
        antrian = layanan.call_next(loket)
        layanan.start_service(antrian.id)
        layanan.complete(antrian.id)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    layar_berhalaman.muat_ulang()

    assert layar_berhalaman.jumlah_halaman == 1
    assert layar_berhalaman._halaman == 0
    assert _nomor_tampil(layar_berhalaman) == ["A-006", "A-007"]

    # Halaman kedua memang sudah tidak ada lagi untuk dituju.
    layar_berhalaman.putar_halaman()
    assert layar_berhalaman._halaman == 0


def test_satu_halaman_tidak_berputar(layar_berhalaman, terbitkan, auth):
    """Halaman yang berpindah ke dirinya sendiri terbaca sebagai layar rusak."""
    terbitkan("A", 2)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    assert layar_berhalaman.jumlah_halaman == 1
    layar_berhalaman.putar_halaman()

    assert layar_berhalaman._halaman == 0
    assert _nomor_tampil(layar_berhalaman) == ["A-001", "A-002"]


def test_judul_memuat_nomor_halaman(layar_berhalaman, terbitkan, auth):
    """
    Tanpa nomor halaman, pengunjung yang tidak menemukan nomornya
    menyimpulkan nomornya hilang dan bertanya ke loket.
    """
    terbitkan("A", 7)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    assert "1 / 2" in layar_berhalaman.label_judul_berikutnya.text()
    layar_berhalaman.putar_halaman()
    assert "2 / 2" in layar_berhalaman.label_judul_berikutnya.text()


def test_judul_tanpa_nomor_halaman_bila_hanya_satu(layar_berhalaman, terbitkan, auth):
    terbitkan("A", 2)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    assert layar_berhalaman.label_judul_berikutnya.text() == "MENUNGGU GILIRAN"


def test_papan_kios_tidak_berotasi(papan_kios):
    """Daftar yang berpindah sendiri di anjungan menarik mata dari tombolnya."""
    assert papan_kios.berotasi is False


def test_rotasi_dapat_dimatikan_lewat_pengaturan(qtbot, auth, antrian_siap):
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.rotate_seconds", "0")
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)

    assert halaman.berotasi is False


def test_jeda_rotasi_mengikuti_pengaturan(qtbot, auth, antrian_siap):
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.rotate_seconds", "7")
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)

    assert halaman.berotasi is True
    assert halaman.pewaktu_halaman.interval() == 7000


def test_kolom_daftar_lebih_sedikit_pada_tema_berkolom_sempit(qtbot, auth, antrian_siap):
    """
    Sorotan dan Split menaruh daftar menunggu di kolom kanan yang sempit.

    Lima kolom nomor di ruang selebar itu saling menempel dan justru tidak
    terbaca dari jarak yang menjadi alasan papan ini dipasang.
    """
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("display", TEST_PASSWORD)

    lebar = {}
    for kode_tema in ("gelap", "sorotan", "split"):
        halaman = DisplayPage(
            QueueService(auth),
            SettingsService(auth),
            NullSoundPlayer(),
            otomatis=False,
            tema=kode_tema,
        )
        qtbot.addWidget(halaman)
        lebar[kode_tema] = halaman.kolom_daftar

    assert lebar["gelap"] > lebar["sorotan"]
    assert lebar["sorotan"] == lebar["split"]


def test_daftar_menyebut_sisa_yang_tidak_termuat(qtbot, auth, antrian_siap, terbitkan):
    """
    Hari ramai melampaui batas halaman yang diputar.

    Menyebut sisanya sebagai jumlah lebih jujur daripada memutar dua puluh
    halaman yang tidak pernah sampai kepada orang yang sedang mencarinya.
    """
    from app.ui.display.display_page import (
        KOLOM_PER_LAYANAN,
        MAKS_HALAMAN,
        DisplayPage,
    )

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.list_rows", "1")
    auth.logout()

    # Satu baris x dua kolom x lima halaman = sepuluh nomor yang terbawa.
    muat = 1 * KOLOM_PER_LAYANAN * MAKS_HALAMAN
    terbitkan("A", muat + 3)
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.muat_ulang()

    assert halaman.jumlah_halaman == MAKS_HALAMAN
    assert "DAN 3 LAINNYA" in halaman.label_judul_berikutnya.text()


def test_daftar_terbagi_sebanyak_jenis_layanan(layar_berhalaman, terbitkan, auth):
    """
    Tiga jenis layanan berarti daftar bawah terbagi tiga kolom.

    Loket dapat dibatasi jenis layanan yang boleh dipanggilnya, sehingga
    urutan panggil memang berjalan per layanan. Satu antrean gabungan
    menyiratkan urutan yang tidak pernah terjadi — A-020 tampak akan
    dipanggil sebelum B-003 padahal keduanya antre di loket yang berbeda.
    """
    terbitkan("A", 3)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    from app.ui.display.display_page import KOLOM_PER_LAYANAN

    assert layar_berhalaman.berkolom_layanan
    assert len(layar_berhalaman._layanan) == 3
    assert layar_berhalaman.baris_berikutnya.columnCount() == 3 * KOLOM_PER_LAYANAN


def test_nomor_masuk_kolom_layanannya_sendiri(layar_berhalaman, terbitkan, auth):
    """Kolom kedua berisi antrian B, bukan lanjutan antrian A."""
    terbitkan("A", 2)
    terbitkan("B", 1)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    kisi = layar_berhalaman.baris_berikutnya

    def _kolom(indeks: int) -> list[str]:
        isi = []
        for baris in range(1, kisi.rowCount()):
            item = kisi.itemAtPosition(baris, indeks)
            if item is not None and item.widget() is not None:
                isi.append(item.widget().text())
        return isi

    from app.ui.display.display_page import KOLOM_PER_LAYANAN

    assert _kolom(0) == ["A-001", "A-002"]
    assert _kolom(KOLOM_PER_LAYANAN) == ["B-001"]


def test_judul_kolom_menyebut_nama_layanan(layar_berhalaman, terbitkan, auth):
    """
    Tiga kolom nomor berdampingan tidak memberi tahu kolom mana yang
    milik pengunjung. Huruf depan nomor saja terlalu kecil untuk dipakai
    menebak dari seberang ruangan.
    """
    terbitkan("A", 1)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    judul = layar_berhalaman.baris_berikutnya.itemAtPosition(0, 0).widget().text()
    assert judul.startswith("A · ")

    # Judulnya melintang di atas kedua sub-kolom layanan itu.
    petak = layar_berhalaman.baris_berikutnya.getItemPosition(
        layar_berhalaman.baris_berikutnya.indexOf(
            layar_berhalaman.baris_berikutnya.itemAtPosition(0, 0).widget()
        )
    )
    assert petak[3] == 2  # rentang kolom


def test_layanan_sepi_tetap_mendapat_kolomnya(layar_berhalaman, terbitkan, auth):
    """
    Kolom yang muncul dan hilang mengikuti isinya membuat lebar seluruh
    papan berubah beberapa detik sekali, dan pengunjung yang sedang
    membaca kehilangan tempat matanya.
    """
    terbitkan("A", 2)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    from app.ui.display.display_page import KOLOM_PER_LAYANAN

    assert layar_berhalaman.baris_berikutnya.columnCount() == 3 * KOLOM_PER_LAYANAN
    # Layanan B adalah yang kedua, sehingga kolom kisinya dimulai di 1x2.
    kosong = layar_berhalaman.baris_berikutnya.itemAtPosition(1, KOLOM_PER_LAYANAN)
    assert kosong is not None
    assert kosong.widget().text() == "—"


def test_halaman_mengikuti_kolom_terpanjang(layar_berhalaman, terbitkan, auth):
    """Halaman berhenti setelah layanan paling ramai habis, bukan yang paling sepi."""
    terbitkan("A", 7)
    terbitkan("B", 1)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    # Fixture ini memakai 2 baris x 2 kolom = 4 nomor per layanan.
    assert layar_berhalaman.jumlah_halaman == 2


def test_papan_kios_tidak_berkolom(papan_kios, terbitkan, auth):
    """Papan kios hanya sederet nomor; tidak ada tempat untuk berkolom."""
    terbitkan("A", 2)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    papan_kios.muat_ulang()

    assert papan_kios.berkolom_layanan is False


def test_papan_kosong_tetap_memakai_satu_kalimat(layar_berhalaman):
    """Tiga kolom berisi strip tidak menjawab apa pun sebelum pengunjung datang."""
    layar_berhalaman.muat_ulang()

    assert _nomor_tampil(layar_berhalaman) == []
    tampil = layar_berhalaman.baris_berikutnya.itemAtPosition(0, 0).widget().text()
    assert tampil == "Tidak ada antrian menunggu"


# ---------------------------------------------------------------------
# Pengelompokan per layanan (service)
# ---------------------------------------------------------------------

def test_pengelompokan_tidak_disusun_bila_tidak_diminta(display_queue, terbitkan, auth):
    """Papan kios tidak berkolom, jadi pengelompokannya tidak perlu dibangun."""
    terbitkan("A", 2)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    assert display_queue.display_state(3).layanan == []


def test_pengelompokan_memuat_setiap_layanan_aktif(display_queue, terbitkan, auth):
    terbitkan("A", 2)
    terbitkan("C", 1)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    layanan = display_queue.display_state(3, jumlah_per_layanan=10).layanan

    assert [l.category_prefix for l in layanan] == ["A", "B", "C"]
    assert [len(l.menunggu) for l in layanan] == [2, 0, 1]
    assert [l.total for l in layanan] == [2, 0, 1]


def test_total_per_layanan_tetap_utuh_walau_dipotong(display_queue, terbitkan, auth):
    """`total` menghitung seluruhnya, supaya sisa yang tidak muat dapat disebut."""
    terbitkan("A", 5)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    layanan = display_queue.display_state(3, jumlah_per_layanan=2).layanan
    kolom_a = next(l for l in layanan if l.category_prefix == "A")

    assert len(kolom_a.menunggu) == 2
    assert kolom_a.total == 5


def test_layanan_nonaktif_tetap_tampil_selama_masih_ada_yang_menunggu(
    display_queue, terbitkan, auth, antrian_siap, master_service
):
    """
    Dinonaktifkan di tengah hari tidak membatalkan nomor yang sudah terbit.

    Orangnya masih duduk di ruangan itu; menghilangkan kolomnya berarti
    nomor mereka lenyap dari papan tanpa pernah dipanggil.
    """
    terbitkan("B", 1)
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master_service.set_category_status(antrian_siap["kategori"]["B"], False)

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layanan = display_queue.display_state(3, jumlah_per_layanan=10).layanan

    assert [l.category_prefix for l in layanan] == ["A", "B", "C"]
    assert [q.queue_number for q in layanan[1].menunggu] == ["B-001"]


def test_layanan_nonaktif_yang_kosong_tidak_lagi_mendapat_kolom(
    display_queue, auth, antrian_siap, master_service
):
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master_service.set_category_status(antrian_siap["kategori"]["B"], False)

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layanan = display_queue.display_state(3, jumlah_per_layanan=10).layanan

    assert [l.category_prefix for l in layanan] == ["A", "C"]


def test_terlalu_banyak_layanan_kembali_ke_daftar_gabungan(
    qtbot, auth, antrian_siap, terbitkan, master_service
):
    """
    Tujuh kolom pada satu televisi semuanya terpotong.

    Daftar gabungan yang berhalaman lebih terbaca daripada tujuh kolom
    yang tak satu pun memuat nomornya secara utuh.
    """
    from app.ui.display.display_page import MAKS_KOLOM_LAYANAN, DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    ada = len(master_service.list_categories())
    # Prefix wajib satu atau dua HURUF, sehingga penomoran tambahan
    # memakai huruf pula.
    for huruf in "PQRSTUVW"[: MAKS_KOLOM_LAYANAN + 1 - ada]:
        master_service.create_category(
            code=f"EKSTRA{huruf}", name=f"Layanan {huruf}", prefix=huruf
        )

    auth.logout()
    terbitkan("A", 2)
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.muat_ulang()

    assert halaman.berkolom_layanan is False
    assert _nomor_tampil(halaman) == ["A-001", "A-002"]


def test_kolom_layanan_yang_hilang_tidak_meninggalkan_lubang(
    layar_berhalaman, terbitkan, auth, antrian_siap, master_service
):
    """
    Regangan kolom tidak ikut terhapus bersama widget-nya.

    Tanpa dikembalikan ke nol, kolom milik layanan yang baru dinonaktifkan
    tetap memakan lebarnya sendiri dan meninggalkan lubang di tengah papan.
    """
    terbitkan("A", 1)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()
    assert layar_berhalaman.baris_berikutnya.columnStretch(4) == 1

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master_service.set_category_status(antrian_siap["kategori"]["C"], False)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    assert layar_berhalaman.baris_berikutnya.columnStretch(4) == 0


# ---------------------------------------------------------------------
# Huruf menyesuaikan tinggi papan
# ---------------------------------------------------------------------

def _tinggi_dibutuhkan(halaman, px: int) -> int:
    return halaman._tinggi_baris_untuk(px)


def test_tinggi_baris_tidak_pernah_lebih_pendek_dari_hurufnya(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Kegagalan yang memicu seluruh perubahan ini.

    Tinggi baris dahulu konstanta 68px berskala, sedangkan huruf 55px
    membutuhkan 93px — setiap kartu terpotong 11px di kedua ujungnya,
    bahkan sebelum kisinya diperas. Tinggi kini diturunkan dari metrik
    huruf, sehingga terpotong tidak mungkin lagi terjadi karena keduanya
    tidak dapat lagi berbeda.
    """
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.resize(1920, 1080)
    halaman.show()
    qtbot.waitExposed(halaman)
    halaman.muat_ulang()

    assert halaman._tinggi_baris >= _tinggi_dibutuhkan(halaman, halaman._font_daftar)


def test_huruf_mengecil_agar_seluruh_baris_muat(qtbot, auth, antrian_siap, terbitkan):
    """
    Lima baris pada papan setinggi ~400px hanya muat bila hurufnya
    mengecil. Yang tidak boleh terjadi adalah huruf tetap besar lalu
    barisnya terpotong.
    """
    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 10)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.resize(1920, 1080)
    halaman.show()
    qtbot.waitExposed(halaman)
    halaman.muat_ulang()

    baris = halaman.baris_daftar
    jarak = round(12 * halaman.skala)
    butuh = baris * halaman._tinggi_baris + (baris - 1) * jarak

    assert butuh <= halaman._tinggi_kisi_tersedia()
    assert halaman._font_daftar < halaman.px("berikutnya")


def test_lima_baris_dua_kolom_untuk_sepuluh_nomor(
    qtbot, auth, antrian_siap, terbitkan
):
    """Bawaan yang diminta: 2 kolom x 5 baris = 10 nomor per jenis layanan."""
    from app.ui.display.display_page import KOLOM_PER_LAYANAN, DisplayPage

    terbitkan("A", 10)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.resize(1920, 1080)
    halaman.show()
    qtbot.waitExposed(halaman)
    halaman.muat_ulang()

    assert KOLOM_PER_LAYANAN == 2
    assert halaman.baris_daftar == 5
    assert halaman.muat_per_halaman == 10
    assert halaman.jumlah_halaman == 1
    assert len(_nomor_tampil(halaman)) == 10


def test_baris_dan_ukuran_huruf_dapat_diatur(qtbot, auth, antrian_siap, terbitkan):
    """Keduanya pengaturan, bukan angka yang tertanam di kode."""
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    pengaturan = SettingsService(auth)
    pengaturan.set("display.list_rows", "3")
    pengaturan.set("display.list_font_size", "30")
    auth.logout()

    terbitkan("A", 6)
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.resize(1920, 1080)
    halaman.show()
    qtbot.waitExposed(halaman)
    halaman.muat_ulang()

    assert halaman.baris_daftar == 3
    assert halaman.muat_per_halaman == 6
    assert halaman._font_daftar == 30


def test_ukuran_huruf_yang_diminta_tetap_diperkecil_bila_tidak_muat(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Angka dari admin adalah batas ATAS, bukan perintah mati.

    Huruf 90px setinggi delapan baris tidak akan pernah muat di papan
    setinggi 400px, dan menurutinya berarti kembali ke nomor terpotong —
    persis kegagalan yang diperbaiki di sini.
    """
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    pengaturan = SettingsService(auth)
    pengaturan.set("display.list_rows", "8")
    pengaturan.set("display.list_font_size", "90")
    auth.logout()

    terbitkan("A", 8)
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.resize(1920, 1080)
    halaman.show()
    qtbot.waitExposed(halaman)
    halaman.muat_ulang()

    assert halaman._font_daftar < 90
    baris = halaman.baris_daftar
    jarak = round(12 * halaman.skala)
    butuh = baris * halaman._tinggi_baris + (baris - 1) * jarak
    assert butuh <= halaman._tinggi_kisi_tersedia()


def test_baris_dikurangi_bila_papan_terlalu_pendek(qtbot, auth, antrian_siap):
    """
    Di bawah huruf terkecil yang masih pantas, papan berhenti mengecilkan
    dan mulai mengurangi baris — satu halaman lagi lebih baik daripada
    nomor yang tidak terbaca.
    """
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("display.list_rows", "12")
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.resize(1280, 720)
    halaman.show()
    qtbot.waitExposed(halaman)
    halaman.muat_ulang()

    assert halaman.baris_diminta == 12
    assert halaman.baris_daftar < 12
    assert halaman.baris_daftar == halaman._baris_muat


def _papan_1080p(qtbot, auth):
    from app.ui.display.display_page import DisplayPage

    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.resize(1920, 1080)
    halaman.show()
    qtbot.waitExposed(halaman)
    halaman.muat_ulang()
    for _ in range(4):
        QApplication.processEvents()
        halaman.layout().activate()
        QApplication.processEvents()
    return halaman


def test_kartu_tidak_terpotong_sejak_gambar_pertama(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Papan harus benar sejak paint pertama, bukan setelah penyegaran.

    Tinggi panel baru diketahui SETELAH Qt menata isinya, sedangkan
    penggambaran pertama terjadi sebelum itu — hurufnya dihitung dari
    angka yang belum final dan nomor terpotong beberapa piksel sampai
    penyegaran dua detik berikutnya. Pengunjung melihat papan yang salah
    selama itu, dan pemasang yang memotret layarnya melihat cacat yang
    "hilang sendiri" saat diperiksa ulang.
    """
    terbitkan("A", 12)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = _papan_1080p(qtbot, auth)

    tinggi_kartu = min(label.height() for label in halaman.label_berikutnya)
    assert halaman._tinggi_baris <= tinggi_kartu


def test_panel_tidak_melewati_tepi_bawah_layar(qtbot, auth, antrian_siap, terbitkan):
    """
    Baris judul kolom ikut memakan tinggi kisi, terpisah dari judul panel.

    Terlewat dari perhitungan, kisi menuntut lebih dari jatah panelnya dan
    seluruh panel terdorong keluar tepi bawah layar — nomor paling bawah
    terpotong separuh, dan judul kolomnya bertumpuk dengan kartu.
    """
    terbitkan("A", 12)
    terbitkan("B", 4)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = _papan_1080p(qtbot, auth)

    assert halaman.panel_berikutnya.geometry().bottom() <= halaman.height()

    jarak = round(12 * halaman.skala)
    baris = halaman.baris_daftar
    butuh = baris * halaman._tinggi_baris + (baris - 1) * jarak
    tersedia = (
        halaman._tinggi_kisi_tersedia() - halaman._tinggi_judul_kolom() - jarak
    )
    assert butuh <= tersedia
