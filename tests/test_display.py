"""Test layar antrian untuk pengunjung."""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QApplication

from app.core.errors import AuthorizationError
from app.services.queue_service import QueueService
from app.services.settings_service import SettingsService
from app.services.sound_service import NullSoundPlayer
from app.ui.display.tema import PALET
from tests.conftest import TEST_PASSWORD

#: Seluruh kode tema yang ada, dibaca dari palet alih-alih ditulis ulang.
#: Ditulis ulang, setiap tema baru akan lolos tanpa pernah sekali pun
#: dibuka oleh test — dan tema yang tidak pernah dibuka adalah tema yang
#: tidak pernah diketahui rusak.
TEMA_SEMUA: tuple[str, ...] = tuple(PALET)


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
    # Tepi yang menyala diambil dari palet tema, bukan dari satu warna
    # aksen aplikasi: sejak papan bertema, setiap tema membawa warna
    # penandanya sendiri.
    assert halaman_layar.palet.tepi_unggulan in unggulan.styleSheet()


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

    Selisihnya harus tegas untuk nomor, nama loket, dan jenis layanan —
    itu yang mendesak dibaca dari jarak jauh. Judul kepala papan dikecualikan
    dengan sengaja: di kios, judul berdiri sendiri di kepala papan (bukan
    berbagi baris dengan kartu loket) dan boleh besar untuk keterbacaan
    sejak pengunjung mendekat, bukan hanya mengikuti rasio panel lain.
    """
    for kunci in ("nomor", "nama", "layanan"):
        assert halaman_layar.px(kunci) > papan_kios.px(kunci) * 1.4, kunci
    assert halaman_layar.px("judul") >= papan_kios.px("judul")


def test_margin_televisi_lebih_lapang_daripada_kios(halaman_layar, papan_kios):
    tv = halaman_layar.susunan.contentsMargins()
    kios = papan_kios.susunan.contentsMargins()

    assert tv.left() > kios.left()
    assert tv.top() > kios.top()
    assert halaman_layar.susunan.spacing() > papan_kios.susunan.spacing()


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
    sebelum = _ukuran_huruf(papan_kios.label_info_kios)

    assert papan_kios.hitung_skala(1080) == 1.0
    papan_kios.resize(1920, 1080)
    papan_kios.show()
    qtbot.waitExposed(papan_kios)

    assert papan_kios.skala == 1.0
    assert _ukuran_huruf(papan_kios.label_info_kios) == sebelum


def test_papan_kios_tidak_menampilkan_daftar_menunggu(papan_kios):
    """
    Anjungan sudah tidak punya kartu loket (lihat test di bawah); ia juga
    tidak lagi menampilkan daftar nomor menunggu di sampingnya. Pengunjung
    yang belum memegang nomor tidak mencari nomornya sendiri di sana —
    seluruh papan kios diserahkan pada informasi/pengumuman yang berputar.
    """
    assert papan_kios.susunan.indexOf(papan_kios.panel_berikutnya) == -1
    assert papan_kios.susunan.indexOf(papan_kios.panel_info_kios) >= 0


def test_papan_kios_tidak_menampilkan_kartu_loket(papan_kios):
    """
    Anjungan belum memegang nomor apa pun; loket mana yang kosong bukan
    urusannya. Ditegaskan langsung di sini, terpisah dari test lain di
    atas yang membuktikannya secara tidak langsung lewat perbandingan
    ukuran dan porsi.
    """
    assert papan_kios.kartu_loket == []
    assert papan_kios.kisi_loket is None


def test_papan_kios_menyambut_sebelum_layanan_disentuh(papan_kios):
    """
    Belum ada layanan yang disentuh pengunjung.

    Panel tidak boleh tampil kosong — pengunjung yang melihat panel hampa
    mengiranya rusak, bukan sekadar belum ada yang disentuh.
    """
    from app.ui.display.display_page import TEKS_SAMBUTAN_KIOS

    assert papan_kios.label_info_kios.text() == TEKS_SAMBUTAN_KIOS


def test_tampilkan_info_kios_berganti_lewat_transisi_pudar(qtbot, papan_kios):
    """
    Isinya berganti SETELAH pudar-keluar selesai, bukan seketika dipanggil
    — supaya pergantiannya terbaca sebagai transisi, bukan kedipan.
    """
    from app.ui.display.display_page import TEKS_SAMBUTAN_KIOS, DURASI_FADE_INFO_KIOS_MS

    papan_kios.tampilkan_info_kios("Bawa fotokopi KTP dan KK.")
    assert papan_kios.label_info_kios.text() == TEKS_SAMBUTAN_KIOS

    qtbot.wait(DURASI_FADE_INFO_KIOS_MS + 100)
    assert papan_kios.label_info_kios.text() == "Bawa fotokopi KTP dan KK."

    # Kembali ke sambutan bawaan saat dipanggil dengan None.
    papan_kios.tampilkan_info_kios(None)
    qtbot.wait(DURASI_FADE_INFO_KIOS_MS + 100)
    assert papan_kios.label_info_kios.text() == TEKS_SAMBUTAN_KIOS


def test_tampilkan_info_kios_kosong_kembali_ke_sambutan(qtbot, papan_kios):
    """Layanan tanpa info anjungan tidak boleh menyisakan panel kosong."""
    from app.ui.display.display_page import TEKS_SAMBUTAN_KIOS, DURASI_FADE_INFO_KIOS_MS

    papan_kios.tampilkan_info_kios("Layanan ini tidak butuh berkas apa pun.")
    qtbot.wait(DURASI_FADE_INFO_KIOS_MS * 2 + 200)
    assert papan_kios.label_info_kios.text() == "Layanan ini tidak butuh berkas apa pun."

    # Layanan berikutnya tidak mengisi info anjungan sama sekali.
    papan_kios.tampilkan_info_kios("")
    qtbot.wait(DURASI_FADE_INFO_KIOS_MS * 2 + 200)
    assert papan_kios.label_info_kios.text() == TEKS_SAMBUTAN_KIOS


def test_path_media_kios_menolak_rayapan_keluar_folder(tmp_path, monkeypatch):
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    (tmp_path / "rahasia.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    assert modul.path_media_kios("../rahasia.txt") is None
    assert modul.path_media_kios("") is None
    assert modul.jenis_sambutan_dari_berkas("poster.PNG") == "media"
    assert modul.jenis_sambutan_dari_berkas("sambutan.mp4") == "media"
    assert modul.jenis_sambutan_dari_berkas("catatan.txt") is None


def test_salin_ke_media_kios_menyalin_berkas(tmp_path, monkeypatch):
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    sumber = tmp_path / "sambutan.mp4"
    sumber.write_bytes(b"mp4")
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    tujuan = modul.salin_ke_media_kios(sumber)

    assert tujuan == folder / "sambutan.mp4"
    assert tujuan.is_file()
    assert tujuan.read_bytes() == b"mp4"


def test_sambutan_gambar_hilang_kembali_ke_teks(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    """Folder media kosong tidak boleh mengosongkan panel anjungan."""
    from app.ui.display.display_page import DisplayPage, TEKS_SAMBUTAN_KIOS
    from app.ui.kiosk import sambutan as modul
    from app.ui.kiosk.sambutan import HALAMAN_TEKS

    folder = tmp_path / "kiosk"
    folder.mkdir()
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")
    SettingsService(admin_auth).set("kiosk.welcome_file", "tidak-ada.png")

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

    assert halaman.panel_info_kios.tumpukan.currentIndex() == HALAMAN_TEKS
    assert halaman.label_info_kios.text() == TEKS_SAMBUTAN_KIOS


def test_sambutan_menampilkan_gambar_bila_berkasnya_ada(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    from PySide6.QtGui import QColor, QImage

    from app.ui.display.display_page import DisplayPage, DURASI_FADE_INFO_KIOS_MS
    from app.ui.kiosk import sambutan as modul
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR, HALAMAN_TEKS

    folder = tmp_path / "kiosk"
    folder.mkdir()
    gambar = QImage(80, 40, QImage.Format.Format_RGB32)
    gambar.fill(QColor("#0F766E"))
    assert gambar.save(str(folder / "poster.png"))
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "gambar")
    SettingsService(admin_auth).set("kiosk.welcome_file", "poster.png")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    assert halaman.panel_info_kios.tumpukan.currentIndex() == HALAMAN_GAMBAR
    pixmap = halaman.panel_info_kios.label_gambar.pixmap()
    assert pixmap is not None and not pixmap.isNull()

    halaman.tampilkan_info_kios("Bawa fotokopi KTP.")
    qtbot.wait(DURASI_FADE_INFO_KIOS_MS + 100)
    assert halaman.panel_info_kios.tumpukan.currentIndex() == HALAMAN_TEKS
    assert halaman.label_info_kios.text() == "Bawa fotokopi KTP."

    halaman.tampilkan_info_kios(None)
    qtbot.wait(DURASI_FADE_INFO_KIOS_MS + 100)
    assert halaman.panel_info_kios.tumpukan.currentIndex() == HALAMAN_GAMBAR


def test_daftar_media_kios_urut_nama_mengabaikan_titik(tmp_path, monkeypatch):
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    (folder / ".gitkeep").write_text("", encoding="utf-8")
    (folder / "02_b.jpg").write_bytes(b"x")
    (folder / "01_a.png").write_bytes(b"x")
    (folder / "catatan.txt").write_text("bukan media", encoding="utf-8")
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    nama = [p.name for p in modul.daftar_media_kios()]
    assert nama == ["01_a.png", "02_b.jpg"]


def test_jejak_media_berubah_bila_isi_berkas_diganti(tmp_path, monkeypatch):
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    berkas = folder / "poster.png"
    berkas.write_bytes(b"aaa")
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    sebelum = modul.jejak_media(modul.daftar_media_kios())
    berkas.write_bytes(b"bbb-lebih-panjang")
    sesudah = modul.jejak_media(modul.daftar_media_kios())
    assert sebelum != sesudah


def test_ganti_berkas_di_folder_mengulang_putaran_dari_awal(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    """Tambah/ganti file di media/kiosk langsung dipakai, tanpa buka ulang aplikasi."""
    from PySide6.QtGui import QColor, QImage

    from app.ui.display.display_page import DisplayPage
    from app.ui.kiosk import sambutan as modul
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR

    folder = tmp_path / "kiosk"
    folder.mkdir()

    def _tulis(nama: str, warna: str) -> None:
        gambar = QImage(80, 40, QImage.Format.Format_RGB32)
        gambar.fill(QColor(warna))
        assert gambar.save(str(folder / nama))

    _tulis("01_a.png", "#0F766E")
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    assert panel.berkas_tampil is not None
    assert panel.berkas_tampil.name == "01_a.png"
    assert panel._jantung.isActive()

    _tulis("02_b.png", "#B45309")
    panel.muat_pengaturan()

    assert [p.name for p in panel._daftar] == ["01_a.png", "02_b.png"]
    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR
    assert panel.berkas_tampil.name == "01_a.png"
    assert panel._jantung.isActive()
    assert panel._jam_item.isValid()


def test_sambutan_folder_bergantian_gambar(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    from PySide6.QtGui import QColor, QImage

    from app.ui.display.display_page import DisplayPage, DURASI_FADE_INFO_KIOS_MS
    from app.ui.kiosk import sambutan as modul
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR, HALAMAN_TEKS

    folder = tmp_path / "kiosk"
    folder.mkdir()
    for nama, warna in (("01_a.png", "#0F766E"), ("02_b.png", "#B45309")):
        gambar = QImage(80, 40, QImage.Format.Format_RGB32)
        gambar.fill(QColor(warna))
        assert gambar.save(str(folder / nama))
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")
    SettingsService(admin_auth).set("kiosk.welcome_slide_seconds", "5")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR
    assert panel.berkas_tampil is not None
    assert panel.berkas_tampil.name == "01_a.png"
    assert panel._jantung.isActive()

    panel._item_berikutnya()
    assert panel.berkas_tampil.name == "02_b.png"

    panel._item_berikutnya()
    assert panel.berkas_tampil.name == "01_a.png"

    halaman.tampilkan_info_kios("Bawa KTP.")
    qtbot.wait(DURASI_FADE_INFO_KIOS_MS + 100)
    assert panel.tumpukan.currentIndex() == HALAMAN_TEKS
    assert not panel._jantung.isActive()

    halaman.tampilkan_info_kios(None)
    qtbot.wait(DURASI_FADE_INFO_KIOS_MS + 100)
    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR
    assert panel.berkas_tampil.name == "01_a.png"


def test_jaga_putaran_video_terakhir_selesai_kembali_ke_awal(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    """
    Habis video terakhir, putaran wajib kembali ke berkas pertama.

    Dideteksi lewat _jaga_putaran() (posisi >= durasi) — jalur yang
    sungguh dipakai di mesin nyata saat sinyal EndOfMedia/StoppedState
    Qt absen — BUKAN dengan memanggil _video_selesai() secara manual
    setelah menyetel currentIndex sendiri; pola itu lolos tes tapi
    terbukti gagal di lapangan.

    Sekaligus regresi untuk balapan nyata di Windows: stop()/setSource()
    yang dipanggil _lepaskan_berkas_video() saat pindah ke gambar
    pertama bisa memancarkan playbackStateChanged(StoppedState) SEREMPAK
    (bukan diantre di event loop). Tanpa penjagaan di _item_berikutnya(),
    sinyal itu memicu pergantian item kedua kalinya secara bersarang di
    tengah pergantian pertama, merusak indeks dan mengunci lagi berkas
    video yang baru saja dilepas — itulah akar penyebab putaran macet di
    item terakhir walau semua tes lama hijau.
    """
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtMultimedia import QMediaPlayer

    from app.ui.display.display_page import DisplayPage
    from app.ui.kiosk import sambutan as modul
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR, HALAMAN_VIDEO

    folder = tmp_path / "kiosk"
    folder.mkdir()
    gambar = QImage(80, 40, QImage.Format.Format_RGB32)
    gambar.fill(QColor("#0F766E"))
    assert gambar.save(str(folder / "01_a.png"))
    (folder / "02_b.mp4").write_bytes(b"bukan video sungguhan, cukup ada namanya")
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    assert panel.berkas_tampil.name == "01_a.png"

    # Anggap video (item terakhir) sedang tampil dan sudah sampai akhir,
    # tanpa benar-benar memutar berkas palsu itu.
    panel._indeks = 1
    panel.berkas_tampil = folder / "02_b.mp4"
    panel._tampilkan_halaman(HALAMAN_VIDEO)
    panel._dijeda_sengaja = False
    panel._abaikan_selesai_video = False
    panel._sedang_ganti_item = False
    monkeypatch.setattr(panel._pemutar, "duration", lambda: 5000)
    monkeypatch.setattr(panel._pemutar, "position", lambda: 5000)

    def stop_serempak() -> None:
        panel._keadaan_putar(QMediaPlayer.PlaybackState.StoppedState)

    monkeypatch.setattr(panel._pemutar, "stop", stop_serempak)
    panel._mulai_jam_item()

    panel._jaga_putaran()

    assert panel._indeks == 0
    assert panel.berkas_tampil.name == "01_a.png"
    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR
    assert panel._jantung.isActive()
    assert not panel._sedang_ganti_item


def test_durasi_slide_gambar_bawaan_sepuluh_detik(
    qtbot, auth, antrian_siap, tmp_path, monkeypatch
):
    """kiosk.welcome_slide_seconds bawaan 10, dipakai apa adanya jadi ms."""
    from app.ui.display.display_page import DisplayPage
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    assert panel._durasi_slide_ms() == 10_000

    # Ganti nilainya lewat sesi admin (sesi "display" tidak boleh), lalu
    # kembali ke "display": panel harus ikut nilai baru, bukan menyimpan
    # nilai lama.
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("kiosk.welcome_slide_seconds", "8")
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    assert panel._durasi_slide_ms() == 8000


def test_gambar_tampil_penuh_sebelum_pindah_ke_item_berikutnya(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    """
    Gambar wajib tampil selama durasi yang dikonfigurasi (bukan lebih
    cepat) sebelum pindah — diverifikasi lewat jam sungguhan (qtbot.wait),
    bukan panggilan manual, supaya detak (_jantung) yang benar-benar
    dipakai di produksi yang diuji.
    """
    from PySide6.QtGui import QColor, QImage

    from app.ui.display.display_page import DisplayPage
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    for nama, warna in (("01_a.png", "#0F766E"), ("02_b.png", "#B45309")):
        gambar = QImage(80, 40, QImage.Format.Format_RGB32)
        gambar.fill(QColor(warna))
        assert gambar.save(str(folder / nama))
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")
    # Durasi minimum yang diizinkan (3 detik) supaya tes cepat; mekanismenya
    # sama dengan bawaan 5 detik.
    SettingsService(admin_auth).set("kiosk.welcome_slide_seconds", "3")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    assert panel.berkas_tampil.name == "01_a.png"

    # Sebelum durasinya (3 detik) lewat, harus TETAP di gambar pertama.
    qtbot.wait(2400)
    assert panel.berkas_tampil.name == "01_a.png"

    # Setelah durasinya lewat (3 detik + jeda detak), baru pindah.
    qtbot.wait(1000)
    assert panel.berkas_tampil.name == "02_b.png"


def test_sinyal_error_video_basi_tidak_memotong_durasi_gambar(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    """
    Regresi: setSource(QUrl()) yang dipanggil _lepaskan_berkas_video() saat
    pindah dari video ke gambar bisa memicu errorOccurred Qt yang basi
    ("no media"/"immediate exit requested"). _gagal_video() dulu tidak
    memeriksa halaman yang sedang tampil sama sekali, jadi sinyal basi itu
    langsung memotong durasi tampil gambar sebelum 5 detiknya lewat.
    """
    from PySide6.QtGui import QColor, QImage

    from app.ui.display.display_page import DisplayPage
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    gambar = QImage(80, 40, QImage.Format.Format_RGB32)
    gambar.fill(QColor("#0F766E"))
    assert gambar.save(str(folder / "01_a.png"))
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    assert panel.berkas_tampil.name == "01_a.png"

    from PySide6.QtMultimedia import QMediaPlayer

    # Sinyal errorOccurred basi tiba SAAT gambar sedang tampil (bukan
    # video) — persis seperti setSource(QUrl()) yang telat dipancarkan
    # dari pergantian item sebelumnya.
    panel._gagal_video(QMediaPlayer.Error.ResourceError, "no media")

    assert panel.berkas_tampil.name == "01_a.png"


def test_kembali_dari_video_ke_gambar_tidak_dirusak_efek_bayangan(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    """
    Regresi akar penyebab "gambar tampil kurang dari 5 detik".

    QWidget MEMILIKI QGraphicsEffect-nya: setGraphicsEffect(None) —
    dipakai _lepas_bayangan() saat pindah ke video — MENGHAPUS objek C++
    efeknya, meninggalkan referensi Python yang menunjuk objek mati. Saat
    putaran kembali ke gambar, _pulihkan_bayangan() melempar RuntimeError
    di tengah _tampilkan_item(), SEBELUM berkas_tampil diisi dan
    _mulai_jam_item() dipanggil. Gambar jadi tidak pernah tercatat tampil
    dan jam itemnya tidak di-restart, sehingga detak 250ms berikutnya
    membaca elapsed basi (dari video) dan langsung melompat balik ke
    video — gambar hanya berkedip sekejap.

    Hanya muncul bila ada VIDEO di folder (hanya video yang memanggil
    _lepas_bayangan), itulah sebabnya semua tes gambar-saja lolos.
    """
    from PySide6.QtGui import QColor, QImage

    from app.ui.display.display_page import DisplayPage
    from app.ui.kiosk import sambutan as modul
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR

    folder = tmp_path / "kiosk"
    folder.mkdir()
    for nama, warna in (("01_a.png", "#0F766E"), ("02_b.png", "#B45309")):
        gambar = QImage(80, 40, QImage.Format.Format_RGB32)
        gambar.fill(QColor(warna))
        assert gambar.save(str(folder / nama))
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    # DisplayPage memasang bayangan pada panel ini; tanpa itu bug-nya
    # tidak mungkin terpicu.
    assert panel.graphicsEffect() is not None
    assert panel.berkas_tampil.name == "01_a.png"

    # Tiru pergantian ke video: bayangan dilepas.
    panel._lepas_bayangan()

    # Lalu putaran kembali ke gambar. Dulu baris ini melempar
    # RuntimeError dari _pulihkan_bayangan() dan menggagalkan pencatatan.
    panel._item_berikutnya()

    assert panel.berkas_tampil.name == "02_b.png"
    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR
    # Jam item WAJIB di-restart, kalau tidak detak berikutnya langsung
    # menganggap durasinya sudah lewat.
    assert panel._jam_item.isValid()
    assert panel._jam_item.elapsed() < 1000
    # Bayangannya hidup lagi, bukan objek mati.
    assert panel.graphicsEffect() is not None
    assert panel.graphicsEffect().isEnabled()


def test_sinyal_folder_berubah_basi_tidak_mengulang_dari_awal(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    """
    Regresi: QFileSystemWatcher Windows bisa memancarkan directoryChanged/
    fileChanged tanpa isi folder sungguh berubah (waktu akses disentuh
    antivirus/pengindeks, dsb). _muat_ulang_dari_folder() dulu memaksa
    _kunci_aktif=None sebelum memeriksa ulang, jadi SETIAP sinyal (basi
    atau bukan) membuat muat_pengaturan() menganggap "berubah" dan
    me-reset putaran ke item pertama — memotong gambar/video yang sedang
    tampil sebelum durasinya lewat, walau isi foldernya sama persis.
    """
    from PySide6.QtGui import QColor, QImage

    from app.ui.display.display_page import DisplayPage
    from app.ui.kiosk import sambutan as modul
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR

    folder = tmp_path / "kiosk"
    folder.mkdir()
    for nama, warna in (("01_a.png", "#0F766E"), ("02_b.png", "#B45309")):
        gambar = QImage(80, 40, QImage.Format.Format_RGB32)
        gambar.fill(QColor(warna))
        assert gambar.save(str(folder / nama))
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    assert panel.berkas_tampil.name == "01_a.png"

    # Pindah ke item kedua (bukan indeks 0) sebelum sinyal folder basi tiba.
    panel._item_berikutnya()
    assert panel.berkas_tampil.name == "02_b.png"
    elapsed_sebelum = panel._jam_item.elapsed()

    # Isi folder TIDAK berubah sama sekali — simulasikan sinyal watcher
    # basi yang tetap terpancar (mis. waktu akses disentuh proses lain).
    panel._folder_media_berubah()
    qtbot.wait(500)  # lewati debounce 400ms _timer_folder

    assert panel.berkas_tampil.name == "02_b.png"
    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR
    # Jam item tidak di-reset oleh sinyal basi — pergantian sungguhan
    # ditolak karena kuncinya memang sama, bukan diam-diam diizinkan.
    assert panel._jam_item.elapsed() >= elapsed_sebelum


def test_jaga_putaran_dari_gambar_terakhir_kembali_ke_awal(
    qtbot, admin_auth, auth, antrian_siap, tmp_path, monkeypatch
):
    from PySide6.QtGui import QColor, QImage

    from app.ui.display.display_page import DisplayPage
    from app.ui.kiosk import sambutan as modul
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR

    folder = tmp_path / "kiosk"
    folder.mkdir()
    for nama, warna in (("01_a.png", "#0F766E"), ("02_b.png", "#B45309")):
        gambar = QImage(80, 40, QImage.Format.Format_RGB32)
        gambar.fill(QColor(warna))
        assert gambar.save(str(folder / nama))
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    SettingsService(admin_auth).set("kiosk.welcome_kind", "media")

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
    halaman.resize(800, 480)
    halaman.show()
    qtbot.waitExposed(halaman)

    panel = halaman.panel_info_kios
    panel._item_berikutnya()
    assert panel.berkas_tampil.name == "02_b.png"
    monkeypatch.setattr(panel, "_durasi_slide_ms", lambda: 0)
    panel._jam_item.start()
    panel._dijeda_sengaja = False
    panel._sedang_ganti_item = False
    panel._jaga_putaran()

    assert panel.berkas_tampil.name == "01_a.png"
    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR


def test_teks_sambutan_dapat_diganti_dari_pengaturan(
    qtbot, admin_auth, auth, antrian_siap
):
    from app.ui.display.display_page import DisplayPage

    SettingsService(admin_auth).set("kiosk.welcome_text", "Selamat datang.")

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

    assert halaman.label_info_kios.text() == "Selamat datang."


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


def test_kepala_papan_judul_tengah_jam_di_bawah(halaman_layar, papan_kios, qtbot):
    """
    Nama instansi yang panjang tidak boleh berebut baris dengan jam.

    Ditulis sebaris, judul terpotong di huruf terakhir dan jam kehilangan
    nama hari. Ditumpuk dan rata tengah, keduanya mendapat lebar penuh.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QVBoxLayout

    for halaman in (halaman_layar, papan_kios):
        halaman.resize(1280, 720)
        halaman.show()
        qtbot.waitExposed(halaman)
        QApplication.processEvents()
        halaman.layout().activate()

        assert isinstance(halaman.kepala, QVBoxLayout)
        assert halaman.label_judul.alignment() & Qt.AlignmentFlag.AlignHCenter
        assert halaman.label_jam.alignment() & Qt.AlignmentFlag.AlignHCenter
        assert halaman.label_judul.height() > 0
        assert halaman.label_jam.height() > 0
        assert halaman.label_jam.y() > halaman.label_judul.y()
        assert halaman.label_jam.geometry().top() >= halaman.label_judul.geometry().bottom()


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


@pytest.mark.parametrize("kode_tema", list(TEMA_SEMUA))
def test_setiap_tema_dapat_dibuka_dan_menampilkan_loket(
    qtbot, auth, antrian_siap, terbitkan, kode_tema
):
    """Setiap tema harus bisa dibuka dan menampilkan seluruh loket, bukan sebagian."""
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


def _luminans(warna: str) -> float:
    """Luminans relatif WCAG dari sebuah "#RRGGBB"."""
    r, g, b = (int(warna[i : i + 2], 16) / 255 for i in (1, 3, 5))

    def kanal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b)


def _kontras(depan: str, belakang: str) -> float:
    a, b = _luminans(depan), _luminans(belakang)
    terang, gelap = max(a, b), min(a, b)
    return (terang + 0.05) / (gelap + 0.05)


@pytest.mark.parametrize("kode", sorted(PALET))
def test_kartu_nomor_kios_terbaca_di_setiap_tema(
    qtbot, admin_auth, auth, antrian_siap, kode
):
    """
    Nomor yang baru terbit tidak boleh menghilang di tema mana pun.

    Pernah hilang sungguhan: kartu ini menumpang latar `panel` sambil
    memakai warna tulisan `nomor` yang dirancang untuk `kartu`. Di tema
    Split keduanya berlawanan — kartunya putih, panelnya tembus ke papan
    yang nyaris hitam — sehingga nomornya tampil hitam di atas hitam,
    tepat pada keadaan yang membuatnya paling penting: tiket gagal
    dicetak, dan layar inilah satu-satunya catatan yang tersisa.

    Karena itu yang diperiksa bukan sekadar "warnanya cerah", melainkan
    bahwa latar dan tulisannya berasal dari SATU pasangan — pasangan yang
    dipakai kartu loket, dan yang karenanya sudah terbukti terbaca.
    """
    from app.ui.display.display_page import DisplayPage

    SettingsService(admin_auth).set("display.theme", kode)

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
    halaman.tampilkan_kartu_kios(nomor="B-002", layanan="Pengaduan", sisa="Sisa: 1")

    palet = halaman.palet
    panel = halaman.panel_info_kios
    latar_kartu = panel.kartu_kios.styleSheet()

    assert palet.kartu in latar_kartu
    assert f"color: {palet.nomor};" in panel.label_kartu_nomor.styleSheet()
    for label in (
        panel.label_kartu_layanan,
        panel.label_kartu_judul,
        panel.label_kartu_sisa,
    ):
        assert f"color: {palet.nama};" in label.styleSheet()

    # Warna kaca (rgba) tidak bisa dihitung tanpa tahu apa yang ada di
    # baliknya; sisanya pekat dan wajib lolos ambang WCAG.
    if palet.kartu.startswith("#"):
        assert _kontras(palet.nomor, palet.kartu) >= 4.5, kode
        assert _kontras(palet.nama, palet.kartu) >= 3.0, kode

    halaman.hentikan()


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


@pytest.mark.parametrize("kode_tema", list(TEMA_SEMUA))
def test_papan_terbagi_wajar_antara_kartu_dan_daftar(
    qtbot, auth, antrian_siap, master_service, terbitkan, kode_tema
):
    """
    Kartu loket dan daftar menunggu harus sama-sama mendapat tempat.

    Keduanya menghitung ukurannya sendiri dari tinggi yang tersisa, dan
    tanpa batas, yang satu memakan jatah yang lain: papan bento yang
    kartunya bertumpuk dua baris pernah menyisakan satu baris nomor saja
    untuk daftar menunggu, dan papan bertumpuk lima loket pernah menggusur
    judulnya sendiri sampai terpotong di tepi atas layar.
    """
    from PySide6.QtWidgets import QApplication

    from app.ui.display.display_page import DisplayPage

    # Lima loket, bukan tiga. Papan tiga loket muat pada hampir semua
    # pembagian tinggi; yang memaksa keduanya berebut adalah loket yang
    # bertumpuk dua baris — dan lima loket itulah pemasangan yang
    # sebenarnya direncanakan.
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master = master_service
    for nomor in (4, 5):
        master.create_counter(
            code=f"L{nomor}",
            name=f"Loket {nomor}",
            branch_id=antrian_siap["branch_id"],
        )

    terbitkan("A", 6)
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
        tema=kode_tema,
    )
    qtbot.addWidget(halaman)
    halaman.resize(1600, 900)
    halaman.show()
    qtbot.waitExposed(halaman)
    QApplication.processEvents()
    halaman.layout().activate()

    # Judul papan tidak boleh ikut diperas menjadi separuh hurufnya.
    judul = halaman.label_judul
    assert judul.height() >= judul.sizeHint().height(), kode_tema

    # Daftar menunggu tidak boleh mengambil lebih dari separuh papan.
    assert halaman.panel_berikutnya.height() <= round(halaman.height() * 0.55), kode_tema

    # Dan kartu loket harus tetap punya tinggi yang wajar untuk nomornya.
    assert min(kartu.height() for kartu in halaman.kartu_loket) >= 60, kode_tema


def test_tema_lama_dipetakan_ke_tema_penggantinya(qtbot, auth, antrian_siap):
    """
    Kode tema tersimpan di database. Kantor yang sudah pernah memilih
    temanya tidak boleh mendapati papannya kembali ke tema bawaan setelah
    pembaruan, hanya karena nama temanya berganti.
    """
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema="gelap",
    )
    qtbot.addWidget(halaman)

    assert halaman.palet.kode == "kaca"


def test_peta_bento_tidak_menyisakan_sel_kosong():
    """
    Lubang di tengah papan publik terbaca sebagai layar yang rusak, bukan
    sebagai ruang kosong yang disengaja. Diperiksa untuk setiap jumlah
    loket yang wajar, karena bentuk bento ditulis per jumlah.
    """
    from app.ui.display.display_page import _peta_bento

    for jumlah in range(1, 10):
        peta = _peta_bento(jumlah)
        assert len(peta) == jumlah

        terisi: list[tuple[int, int]] = []
        for baris, kolom, tinggi, lebar in peta:
            for b in range(baris, baris + tinggi):
                for k in range(kolom, kolom + lebar):
                    terisi.append((b, k))

        # Tidak ada sel yang ditempati dua kartu sekaligus.
        assert len(terisi) == len(set(terisi)), jumlah
        # Dan tidak ada sel kosong di dalam persegi yang dipakainya.
        baris_akhir = max(b for b, _ in terisi) + 1
        kolom_akhir = max(k for _, k in terisi) + 1
        assert len(terisi) == baris_akhir * kolom_akhir, jumlah


def test_tema_bento_memberi_sel_besar_kepada_loket_yang_memanggil(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Inti tema bento: hierarki datang dari UKURAN kartu, bukan dari warnanya
    saja. Loket yang sedang memanggil menempati sel dua kali lebih besar,
    dan sel itu berpindah mengikuti panggilan berikutnya.
    """
    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][1])

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema="bento",
    )
    qtbot.addWidget(halaman)

    def sel(kartu):
        return halaman.kisi_loket.getItemPosition(halaman.kisi_loket.indexOf(kartu))

    assert len(halaman.kartu_loket) == 3
    assert sel(halaman.kartu_loket[1]) == (0, 0, 2, 2)
    assert sel(halaman.kartu_loket[0])[2:] == (1, 2)

    # Panggilan berikutnya memindahkan sel besar, bukan sekadar mengganti
    # warnanya.
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][2])
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman.muat_ulang()

    assert sel(halaman.kartu_loket[2]) == (0, 0, 2, 2)
    assert sel(halaman.kartu_loket[1])[2:] == (1, 2)


def test_nomor_sel_kecil_bento_tidak_terpotong(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Sel kecil bento tingginya setengah sel besar.

    Huruf nomor televisi (132px) tidak muat di situ: A-003 terpotong di
    tepi atas kartunya dan nama layanan menempel ke tepi bawah.
    """
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    layanan = QueueService(auth)
    for loket in antrian_siap["loket"]:
        layanan.call_next(loket)

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema="bento",
    )
    qtbot.addWidget(halaman)
    halaman.resize(1280, 800)
    halaman.show()
    qtbot.waitExposed(halaman)
    for _ in range(6):
        QApplication.processEvents()
        halaman.layout().activate()
        QApplication.processEvents()
    halaman._sesuaikan_daftar()
    halaman._muatkan_huruf_kartu()

    kecil = [
        kartu
        for indeks, kartu in enumerate(halaman.kartu_loket)
        if indeks != halaman._indeks_besar
    ]
    assert kecil
    for kartu in kecil:
        nomor = kartu.label_nomor
        assert nomor.text() not in ("", "—")
        fm = QFontMetrics(nomor.font())
        assert fm.height() <= nomor.height() + 1, (
            f"{nomor.text()} huruf={fm.height()} label={nomor.height()} "
            f"kartu={kartu.height()}"
        )
        layanan_lbl = kartu.label_layanan
        assert layanan_lbl.sizeHint().height() <= layanan_lbl.height() + 1


def test_tema_tabel_menyusun_loket_sebagai_baris_bergaris(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Papan LED tidak berkartu: setiap loket menjadi satu baris dengan nomor
    di kolom kiri, dipisahkan garis rambut.
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
        tema="led",
    )
    qtbot.addWidget(halaman)

    assert halaman.kisi_loket is None
    assert len(halaman.kartu_loket) == 3
    assert all(kartu.varian == "tabel" for kartu in halaman.kartu_loket)
    assert [label.text() for label in halaman.label_kolom_tabel] == [
        "NOMOR",
        "LOKET",
        "STATUS",
    ]
    # Barisnya dipisah garis bawah, bukan dijadikan kartu bertepi penuh.
    assert "border-bottom" in halaman.kartu_loket[0].styleSheet()
    assert halaman.kartu_loket[0].label_nomor.text() == "A-001"


def test_tema_fokus_menampilkan_panggilan_terbaru_dan_seluruh_loket(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Fokus memperbesar satu nomor, tetapi TIDAK menyembunyikan loket lain:
    pengunjung tetap harus tahu ke loket mana ia dipanggil.
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
        tema="fokus",
    )
    qtbot.addWidget(halaman)

    assert halaman.kartu_sorot is not None
    assert halaman.kartu_sorot.label_nomor.text() == "A-001"
    assert len(halaman.kartu_loket) == 3
    # Pita loket memakai kartu tegak yang diperkecil: pada lebar seperlima
    # layar, kartu melebar menaruh nomornya menimpa nama loketnya sendiri.
    assert all(kartu.varian == "kisi" for kartu in halaman.kartu_loket)


def test_tema_datar_tidak_memasang_bayangan(qtbot, auth, antrian_siap, terbitkan):
    """
    Tema Papan LED dan Kontras Tinggi sengaja datar. QGraphicsDropShadowEffect
    memaksa setiap kartu digambar lewat lapisan tersendiri — biaya yang tidak
    dibayar apa pun bila bayangannya memang tidak diinginkan.
    """
    from app.ui.display.display_page import DisplayPage

    terbitkan("A", 1)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    for kode_tema in ("led", "kontras"):
        halaman = DisplayPage(
            QueueService(auth),
            SettingsService(auth),
            NullSoundPlayer(),
            otomatis=False,
            tema=kode_tema,
        )
        qtbot.addWidget(halaman)
        assert halaman.palet.bayangan == 0, kode_tema
        assert all(
            kartu.graphicsEffect() is None for kartu in halaman.kartu_loket
        ), kode_tema


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
    # Kios tidak punya kartu loket sama sekali, kisi atau bukan — lihat
    # `test_papan_kios_tidak_menampilkan_kartu_loket`.
    assert halaman.kartu_loket == []
    assert halaman.kisi_loket is None


def test_tidak_ada_warna_delapan_digit_di_seluruh_tema(qtbot, auth, antrian_siap, terbitkan):
    """
    Qt tidak mendukung #RRGGBBAA dan membacanya sebagai warna lain — sumber
    warna kuning yang tidak pernah diminta. Diperiksa untuk seluruh tema,
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

    for kode_tema in TEMA_SEMUA:
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


def test_kolom_layanan_mengikuti_pengaturan_yang_aktif(
    display_queue, terbitkan, auth, antrian_siap, master_service
):
    """
    Layar memakai daftar layanan yang sama dengan anjungan.

    Layanan yang ditutup hilang dari kedua-duanya. Dua daftar yang
    bersumber pada aturan berbeda akan berselisih — anjungan satu kartu,
    layar dua kolom — tanpa ada yang tahu mana yang benar.
    """
    terbitkan("B", 1)
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master_service.set_category_status(antrian_siap["kategori"]["B"], False)

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    keadaan = display_queue.display_state(3, jumlah_per_layanan=10)

    assert [l.category_prefix for l in keadaan.layanan] == ["A", "C"]
    # Orangnya tetap terhitung. Papan menyebutnya "dan N lainnya", bukan
    # berpura-pura ruang tunggu sudah kosong.
    assert keadaan.total_menunggu == 1


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


def _sisakan_satu_layanan(auth, master_service, antrian_siap, sisa: str = "A") -> None:
    """Nonaktifkan semua jenis layanan kecuali satu, sebagai admin."""
    sebelumnya = auth.current_session
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    for prefix, id_kategori in antrian_siap["kategori"].items():
        if prefix != sisa:
            master_service.set_category_status(id_kategori, False)
    auth.logout()
    if sebelumnya is not None:
        auth.login(sebelumnya.username, TEST_PASSWORD)


def _papan_tv(qtbot, auth):
    """Layar televisi dengan pengaturan bawaan, sudah dimuat sekali."""
    from app.ui.display.display_page import DisplayPage

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth), SettingsService(auth), NullSoundPlayer(), otomatis=False
    )
    qtbot.addWidget(halaman)
    halaman.muat_ulang()
    return halaman


def test_satu_layanan_kembali_ke_daftar_gabungan(
    qtbot, auth, antrian_siap, terbitkan, master_service
):
    """
    Satu kolom tidak membedakan apa pun dari satu kolom.

    Judul kolom ada supaya pengunjung tahu kolom mana yang miliknya. Bila
    layanannya hanya satu, judul itu tinggal mengulang huruf depan setiap
    nomor di bawahnya sambil memakan tinggi panel.
    """
    _sisakan_satu_layanan(auth, master_service, antrian_siap)
    terbitkan("A", 2)
    halaman = _papan_tv(qtbot, auth)

    assert len(halaman._layanan) == 1
    assert halaman.berkolom_layanan is False
    # Baris nol milik nomor, bukan judul: daftar gabungan tidak berjudul.
    assert halaman.baris_berikutnya.itemAtPosition(0, 0).widget().text() == "A-001"
    assert _nomor_tampil(halaman) == ["A-001", "A-002"]


def test_satu_layanan_memakai_seluruh_lebar_kisi(
    qtbot, auth, antrian_siap, terbitkan, master_service
):
    """
    Halaman diiris menurut kisi yang benar-benar dipakai menggambar.

    Lima baris kali lima kolom memuat dua puluh lima nomor sekaligus.
    Diiris menurut `KOLOM_PER_LAYANAN` yang lebih sempit, papan menerima
    sepuluh, berhalaman tiga kali, dan menyisakan tiga baris kosong di
    bawah setiap halamannya.
    """
    from app.ui.display.display_page import KOLOM_DAFTAR

    _sisakan_satu_layanan(auth, master_service, antrian_siap)
    terbitkan("A", 25)
    halaman = _papan_tv(qtbot, auth)

    assert halaman.baris_daftar == 5
    assert halaman.muat_per_halaman == 5 * KOLOM_DAFTAR
    assert halaman.jumlah_halaman == 1
    assert len(_nomor_tampil(halaman)) == 25


def test_dua_layanan_tetap_berkolom(
    qtbot, auth, antrian_siap, terbitkan, master_service
):
    """Batas bawah yang baru berhenti di satu, bukan memakan dua."""
    _sisakan_satu_layanan(auth, master_service, antrian_siap, sisa="A")
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master_service.set_category_status(antrian_siap["kategori"]["B"], True)
    auth.logout()

    terbitkan("A", 1)
    halaman = _papan_tv(qtbot, auth)

    assert len(halaman._layanan) == 2
    assert halaman.berkolom_layanan is True


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


def test_panel_bento_jendela_sedang_tidak_terpotong(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Pratinjau di jendela admin, bukan televisi 1080p.

    Tema Bento menumpuk dua baris kartu bahkan dengan tiga loket. Panel
    menunggu yang dipaksa separuh tinggi mendorong baris nomor terakhir
    keluar bingkai, dan padding 14px menindih sudut membulat 20px sehingga
    tepi bawahnya tampak terpotong lurus.
    """
    from PySide6.QtWidgets import QApplication

    from app.ui.display.display_page import RADIUS_PANEL_TUNGGU, DisplayPage

    terbitkan("A", 4)
    terbitkan("B", 2)
    terbitkan("C", 2)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman = DisplayPage(
        QueueService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        otomatis=False,
        tema="bento",
    )
    qtbot.addWidget(halaman)
    halaman.resize(1100, 720)
    halaman.show()
    qtbot.waitExposed(halaman)
    for _ in range(4):
        QApplication.processEvents()
        halaman.layout().activate()
        QApplication.processEvents()
    halaman._sesuaikan_daftar()

    margin = halaman.susunan.contentsMargins()
    assert halaman.panel_berikutnya.geometry().bottom() <= (
        halaman.height() - margin.bottom()
    )
    dalam = halaman.susunan_berikutnya.contentsMargins()
    assert dalam.bottom() >= RADIUS_PANEL_TUNGGU
    assert halaman.label_berikutnya
    bawah_kartu = max(label.geometry().bottom() for label in halaman.label_berikutnya)
    assert bawah_kartu <= halaman.panel_berikutnya.height() - dalam.bottom()


# ---------------------------------------------------------------------
# Pergantian halaman berpudar
# ---------------------------------------------------------------------

def _siapkan_papan_tampil(qtbot, halaman, terbitkan, auth, jumlah: int = 7):
    """Isi papan, tampilkan jendelanya, lalu muat datanya sekali."""
    terbitkan("A", jumlah)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    halaman.resize(1280, 720)
    halaman.show()
    qtbot.waitExposed(halaman)
    halaman.muat_ulang()
    return halaman


def test_halaman_ditukar_hanya_sesudah_pudar_keluar(
    qtbot, layar_berhalaman, terbitkan, auth
):
    """
    Menukar isi lebih dahulu berarti nomor lama lenyap seketika, dan pudar
    sesudahnya tidak lagi menutupi apa pun.
    """
    from app.ui.display.display_page import PUDAR_KELUAR

    papan = _siapkan_papan_tampil(qtbot, layar_berhalaman, terbitkan, auth)
    assert papan.jumlah_halaman > 1
    nomor_lama = _nomor_tampil(papan)

    papan.putar_halaman()

    assert papan._fase_pudar == PUDAR_KELUAR
    # Masih halaman yang sama, dan masih nomor yang sama: yang berjalan
    # baru pudarnya.
    assert papan._halaman == 0
    assert _nomor_tampil(papan) == nomor_lama


def test_pudar_berakhir_pada_halaman_baru_yang_terbaca_penuh(
    qtbot, layar_berhalaman, terbitkan, auth
):
    """
    Kegagalan terburuk animasi ini adalah daftar yang tidak pernah kembali
    terlihat. Dijalankan dengan event loop sungguhan sampai kedua arah
    pudarnya selesai.
    """
    papan = _siapkan_papan_tampil(qtbot, layar_berhalaman, terbitkan, auth)
    nomor_lama = _nomor_tampil(papan)

    papan.putar_halaman()
    qtbot.waitUntil(lambda: papan._fase_pudar == "", timeout=5000)

    assert papan._halaman == 1
    assert _nomor_tampil(papan) != nomor_lama
    assert papan.efek_berikutnya.opacity() == 1.0


def test_penyegaran_data_tidak_ikut_memudarkan(
    qtbot, layar_berhalaman, terbitkan, auth
):
    """
    Papan digambar ulang setiap dua detik, jauh lebih sering daripada
    halamannya berganti. Memudarkan di sana membuatnya berkedip
    terus-menerus walau tidak ada satu pun yang berubah.
    """
    papan = _siapkan_papan_tampil(qtbot, layar_berhalaman, terbitkan, auth)

    papan.muat_ulang()

    assert papan._fase_pudar == ""
    assert papan.efek_berikutnya.opacity() == 1.0


def test_papan_yang_belum_tampil_menukar_halaman_seketika(
    layar_berhalaman, terbitkan, auth
):
    """
    Animasi yang tidak pernah dijalankan meninggalkan opacity pada nilai
    awalnya, dan daftar menunggu tidak terlihat sama sekali.
    """
    terbitkan("A", 7)
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layar_berhalaman.muat_ulang()

    layar_berhalaman.putar_halaman()

    assert layar_berhalaman._halaman == 1
    assert layar_berhalaman._fase_pudar == ""
    assert layar_berhalaman.efek_berikutnya.opacity() == 1.0


def test_menutup_layar_mengembalikan_panel_ke_utuh(
    qtbot, layar_berhalaman, terbitkan, auth
):
    """
    `stop()` tidak memancarkan `finished`, sehingga pudar-keluar yang
    dipotong di tengah akan meninggalkan daftar yang hilang sama sekali.
    """
    papan = _siapkan_papan_tampil(qtbot, layar_berhalaman, terbitkan, auth)
    papan.putar_halaman()

    papan.hentikan()

    assert papan._fase_pudar == ""
    assert papan.efek_berikutnya.opacity() == 1.0


def test_animasi_dipakai_ulang_tidak_menumpuk(
    qtbot, layar_berhalaman, terbitkan, auth
):
    """
    Papan berputar berhari-hari tanpa dibuka ulang. Animasi yang dibuat
    baru setiap pergantian meninggalkan ribuan objek per hari yang tidak
    pernah dibuang karena semuanya berinduk pada papan.
    """
    papan = _siapkan_papan_tampil(qtbot, layar_berhalaman, terbitkan, auth)

    papan.putar_halaman()
    pertama = papan._animasi_halaman
    qtbot.waitUntil(lambda: papan._fase_pudar == "", timeout=5000)
    papan.putar_halaman()
    qtbot.waitUntil(lambda: papan._fase_pudar == "", timeout=5000)

    assert papan._animasi_halaman is pertama
