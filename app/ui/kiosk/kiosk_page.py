"""
Anjungan ambil nomor.

Satu layar mengerjakan dua hal: menyediakan tombol bagi pengunjung untuk
mengambil nomornya sendiri, dan menampilkan papan nomor kecil yang sedang
dipanggil. Papan besarnya ada di komputer televisi ruang tunggu, mesin
tersendiri yang dibuka dengan `--tv`.

Dirancang untuk dipakai orang yang belum pernah melihatnya, sambil berdiri,
dari jarak satu lengan. Karena itu tidak ada menu, tidak ada pilihan yang
perlu dipahami dahulu, dan tidak ada tombol yang tidak jelas akibatnya.

Layar ini berjalan TANPA login. Kewenangannya dibatasi peran KIOSK di
service layer dan oleh hak user PostgreSQL mesin itu di database.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import AppError
from app.core.logger import get_logger
from app.services.master_data_service import MasterDataService
from app.services.queue_service import QueueInfo, QueueService
from app.services.settings_service import SettingsService
from app.services.sound_service import SoundPlayer
from app.services.ticket_service import TicketService, baris_sisa_antrian, mode_pencetak
from app.ui.common import pesan_untuk_user, tombol
from app.ui.display.display_page import DisplayPage
from app.ui.kiosk.sambutan import media_layanan
from app.ui.style import (
    DISPLAY_KIOS_TOMBOL,
    DISPLAY_KIOS_TOMBOL_HOVER,
    DISPLAY_KIOS_TOMBOL_MATI,
    DISPLAY_KIOS_TOMBOL_MATI_TEKS,
    DISPLAY_KIOS_TOMBOL_TEKAN,
    DISPLAY_KIOS_TOMBOL_TEKS,
    KIOS_JUDUL,
    KIOS_KOTAK_HURUF,
    KIOS_KOTAK_HURUF_MATI,
    KIOS_PANEL_ATAS,
    KIOS_PANEL_BAWAH,
    KIOS_PIL,
    KIOS_SUKSES,
    KIOS_SUKSES_TEKAN,
    TEXT_MUTED,
)

logger = get_logger("ui.kiosk")

#: Lama nomor yang baru terbit tampil sebelum layar bersiap untuk pengunjung
#: berikutnya, dalam milidetik. Batas BAWAH saja: bila jeda pengambilan
#: nomor lebih panjang daripada ini, hasilnya ikut ditahan selama itu —
#: lihat `_lama_hasil_ms`.
JEDA_HASIL = 8000

#: Hasil cetak tiket, penentu kalimat arahan pada kartu nomor.
CETAK_TANPA_PRINTER = "tanpa"
CETAK_BERHASIL = "berhasil"
CETAK_GAGAL = "gagal"

#: Arahan yang menyertai nomor, satu kalimat per keadaan cetak.
#:
#: Disusun di satu tempat lalu dipakai kartu nomor DAN label petunjuk di
#: panel bawah: dua tempat yang menjawab pertanyaan yang sama tidak boleh
#: menyebut kalimat yang berbeda.
#:
#: Kalimat "gagal" adalah alasan terkuat kartu nomor dibuat sebesar itu.
#: `_cetak()` sengaja tidak pernah menggagalkan pengambilan nomor, jadi
#: saat printer kehabisan kertas nomornya tetap sah — dan layar menjadi
#: satu-satunya catatan yang dipegang pengunjung.
ARAHAN_CETAK = {
    CETAK_TANPA_PRINTER: "Silakan tunggu hingga nomor Anda dipanggil.",
    CETAK_BERHASIL: "Ambil tiket Anda, lalu tunggu hingga nomor Anda dipanggil.",
    CETAK_GAGAL: (
        "Tiket gagal dicetak. Foto atau catat nomor Anda, lalu tunggu dipanggil."
    ),
}

#: Lama layar konfirmasi menunggu sebelum otomatis batal, dalam milidetik.
#: Kios tidak berpenjaga: pengunjung yang berbalik pergi tanpa menekan
#: apa pun tidak boleh meninggalkan layar tersangkut menunggu konfirmasi
#: untuk orang berikutnya.
JEDA_KONFIRMASI = 15000

#: Selang pembaruan hitung mundur jeda pengambilan nomor.
SELANG_HITUNG_MS = 500

#: Selang pemeriksaan perubahan daftar jenis layanan, dalam milidetik.
#:
#: Anjungan berdiri tanpa penjaga dan tidak ada yang menekan F5 di sana.
#: Tanpa pemeriksaan ini, jenis layanan yang baru ditambah, diganti nama,
#: digeser urutannya, atau dinonaktifkan admin tidak pernah sampai ke layar
#: anjungan sampai aplikasinya ditutup dan dibuka lagi — dan yang menutup
#: aplikasi di mesin itu tidak ada.
#:
#: Sengaja TIDAK ikut pewaktu hitung mundur yang berdetak tiap setengah
#: detik: yang ini menambah satu pembacaan database, dan daftar jenis
#: layanan berubah beberapa kali setahun, bukan beberapa kali semenit.
SELANG_PERIKSA_LAYANAN_MS = 20000

#: Tinggi minimum panel ambil nomor. Tanpa ini, papan antrian merebut
#: seluruh tinggi jendela biasa dan nama layanan di bawah A/B/C terpotong.
TINGGI_PANEL_AMBIL_MIN = 268
TINGGI_TOMBOL_MIN = 120
#: Banyaknya kolom terbanyak. Lebih dari ini tiap kartu terlalu sempit
#: untuk disentuh dengan jari, bukan dengan mouse.
KOLOM_MAKS = 3

#: Tinggi maksimum tombol pilih layanan. Tanpa batas atas, kebijakan
#: Expanding membuatnya memakai seluruh sisa panel ambil nomor pada
#: jendela besar — kartu setinggi hampir separuh layar terasa berlebihan
#: untuk sekadar tombol, bukan lagi mengundang sentuhan.
TINGGI_TOMBOL_MAKS = 260
#: Lebar dijepit supaya tiga tombol tidak meregang jadi batang pipih
#: selebar panel pada monitor 1080p.
LEBAR_TOMBOL_MIN = 180
LEBAR_TOMBOL_MAKS = 480
#: Tinggi kartu = lebar × rasio, lalu dijepit TINGGI_TOMBOL_MAKS.
#: Lebar 480 tidak ikut dipangkas agar ukuran sentuhannya tetap.
RASIO_TINGGI_TOMBOL = 0.70
#: Pengali batas ukuran kartu menurut banyaknya KOLOM, bukan banyaknya
#: layanan.
#:
#: Kantor yang hanya melayani satu atau dua jenis layanan tidak seharusnya
#: mendapat dua kartu berukuran sama seperti kantor berlayanan enam, lalu
#: menyisakan separuh panel kosong di kiri dan kanannya. Batas 480×260 di
#: atas adalah ukuran untuk tiga kolom — jatah yang lebih lapang boleh
#: dipakai, tetapi tetap ada batasnya: kartu selebar panel terbaca sebagai
#: pita, bukan sebagai tombol.
PEMBESAR_KARTU = {1: 1.35, 2: 1.15}
#: Batas pelebaran kartu pada baris terakhir yang tidak penuh, sebagai
#: kelipatan lebar kartu di baris penuh. Melebar sampai barisnya benar-benar
#: sama panjang membuat dua kartu terakhir jauh lebih besar daripada kartu
#: di atasnya — dan ukuran yang berbeda terbaca sebagai derajat yang
#: berbeda, padahal semua layanan setara.
PEMBESAR_BARIS_AKHIR = 1.4
CELAH_TOMBOL = 50
MARGIN_KISI = 16
#: Sudut atas panel ambil nomor. Cukup besar untuk terbaca sebagai lembar
#: yang diletakkan di atas papan, cukup kecil untuk tidak memakan sudut
#: kartu layanan yang ada di dalamnya.
RADIUS_PANEL = 28
#: Lebar maksimum pil petunjuk. Kalimat kegagalan yang panjang membungkus
#: ke baris kedua di dalam pil, bukan meregang selebar panel.
LEBAR_PIL_MAKS = 900
UKURAN_PIL = 18
PADDING_PIL = 24
#: Kelonggaran lebar pil. Lebar huruf yang dihitung di sini tidak persis
#: sama dengan yang digambar Qt sesudah stylesheet dipasang, dan kurang
#: satu piksel saja sudah cukup untuk melipat kalimatnya jadi dua baris.
KELONGGARAN_PIL = 24
MARGIN_ISI_TOMBOL = 16
CELAH_ISI_TOMBOL = 10
#: Sudut kartu layanan dan tombol konfirmasi.
RADIUS_KARTU = 26
#: Sisi kotak huruf di dalam kartu, sebagai bagian dari tinggi isi kartu.
#: Kotaknya bujur sangkar, jadi angka ini sekaligus batas lebarnya.
BAGIAN_KOTAK_HURUF = 0.62

#: Sisi kotak huruf pada layar konfirmasi. Tetap, bukan menskala: layar
#: itu hanya berisi dua tombol dan satu judul, jadi ukurannya tidak pernah
#: berebut ruang dengan apa pun.
SISI_KOTAK_KONFIRMASI = 112

#: Tinggi minimum tombol BATAL/YA pada layar konfirmasi. Lebih tinggi
#: daripada tombol pilih layanan: hanya ada dua tombol di layar itu, jadi
#: keduanya boleh memakai ruang yang jauh lebih lapang, dan salah tap di
#: sini berarti nomor sudah terlanjur terbit atau pengunjung mengulang
#: dari awal.
TINGGI_TOMBOL_KONFIRMASI_MIN = 220


def baris_kisi(jumlah: int) -> list[int]:
    """
    Banyaknya kartu pada tiap baris.

    Barisnya diisi serata mungkin, bukan tiga-tiga sampai habis. Empat
    layanan yang disusun 3+1 meninggalkan satu kartu sendirian di bawah —
    terbaca sebagai kartu yang berbeda derajat, padahal semua jenis
    layanan setara. Baris yang lebih panjang ditaruh di ATAS, karena
    itulah yang pertama dibaca.

        1 -> [1]      4 -> [2, 2]     7 -> [3, 2, 2]
        2 -> [2]      5 -> [3, 2]     8 -> [3, 3, 2]
        3 -> [3]      6 -> [3, 3]     9 -> [3, 3, 3]
    """
    if jumlah <= 0:
        return []
    baris = -(-jumlah // KOLOM_MAKS)  # pembulatan ke atas
    dasar, sisa = divmod(jumlah, baris)
    return [dasar + (1 if urutan < sisa else 0) for urutan in range(baris)]


def _bayangan(widget: QWidget, radius: int, y: int, alpha: int) -> None:
    """Bayangan tipis, sama seperti kartu loket dan panel sorotan di TV."""
    efek = QGraphicsDropShadowEffect(widget)
    efek.setBlurRadius(radius)
    efek.setOffset(0, y)
    efek.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(efek)


class KioskPage(QWidget):
    """Papan nomor sekaligus tempat pengunjung mengambil nomor."""

    def __init__(
        self,
        queue: QueueService,
        master: MasterDataService,
        settings: SettingsService,
        sound: SoundPlayer,
        ticket: TicketService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.master = master
        self.settings = settings
        self.sound = sound
        self.ticket = ticket
        self.kategori: list = []
        self.tombol_layanan: list = []
        self.pendaftaran_dibuka = True
        #: True selama label petunjuk menampilkan kesalahan, supaya
        #: penyegaran jeda tidak menimpanya dengan ajakan mengambil nomor.
        self._tahan_petunjuk = False
        #: True selama layar konfirmasi tampil, supaya penyegaran jeda
        #: tidak menimpa petunjuknya dan tidak mengembalikan ke kisi pilihan.
        self._menunggu_konfirmasi = False
        #: Kategori yang sedang menunggu konfirmasi pengunjung.
        self._kategori_terpilih = None

        # Timer dimiliki widget ini, bukan QTimer.singleShot yang statis.
        # singleShot tetap menyala setelah halamannya dihapus lalu menyentuh
        # label yang sudah tidak ada.
        self._penghapus_hasil = QTimer(self)
        self._penghapus_hasil.setSingleShot(True)
        self._penghapus_hasil.timeout.connect(self._bersihkan_hasil)

        self._pembatal_konfirmasi = QTimer(self)
        self._pembatal_konfirmasi.setSingleShot(True)
        self._pembatal_konfirmasi.timeout.connect(self._batal_konfirmasi)

        self._bangun_tampilan()
        self.muat_ulang()

        self._penghitung = QTimer(self)
        self._penghitung.timeout.connect(self._perbarui_jeda)
        self._penghitung.start(SELANG_HITUNG_MS)

        self._pemeriksa_layanan = QTimer(self)
        self._pemeriksa_layanan.timeout.connect(self._periksa_perubahan_layanan)
        self._pemeriksa_layanan.start(SELANG_PERIKSA_LAYANAN_MS)

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        self.setObjectName("layarKios")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(0)

        # Papan nomor memakai layar antrian yang sudah ada, bukan salinannya.
        # Pengunjung melihat isi yang persis sama dengan layar besar di ruang
        # tunggu, dan perbaikan pada salah satunya berlaku bagi keduanya.
        #
        # kompak=True bukan sekadar huruf lebih kecil: papan kios sengaja
        # TIDAK ikut membesar mengikuti tinggi layar seperti papan televisi.
        # Di layar penuh 1080p, papan yang menskala akan menelan panel ambil
        # nomor dan memotong nama layanan di bawah A/B/C.
        self.papan = DisplayPage(
            self.queue, self.settings, self.sound, kompak=True
        )
        self.papan.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored
        )
        susunan.addWidget(self.papan, stretch=3)

        # Latar kios mengikuti tema papan. Yang terlihat hanyalah sela
        # tipis di sekeliling papan, tetapi sela berwarna biru di bawah
        # papan hitam bertema LED langsung terbaca sebagai cacat.
        self.setStyleSheet(
            f"QWidget#layarKios {{ background: {self.papan.palet.latar}; }}"
        )

        self.panel_ambil = self._bangun_panel_ambil()
        susunan.addWidget(self.panel_ambil, stretch=2)

    def _bangun_panel_ambil(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelAmbil")
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        panel.setMinimumHeight(TINGGI_PANEL_AMBIL_MIN)
        # Sudut atas dibulatkan supaya panel terbaca sebagai lembar yang
        # DILETAKKAN di atas papan, bukan sebagai layar kedua yang dijahit
        # ke bawahnya. Warna garis atasnya tetap ikut tema papan: itulah
        # satu-satunya benang yang menyambungkan dua bidang ini.
        panel.setStyleSheet(
            "QFrame#panelAmbil { background: qlineargradient(x1:0, y1:0,"
            f" x2:0, y2:1, stop:0 {KIOS_PANEL_ATAS}, stop:1 {KIOS_PANEL_BAWAH});"
            f" border-top: 5px solid {self.papan.palet.tepi_unggulan};"
            f" border-top-left-radius: {RADIUS_PANEL}px;"
            f" border-top-right-radius: {RADIUS_PANEL}px; }}"
        )

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(32, 18, 32, 24)
        susunan.setSpacing(10)

        self.label_ajakan = QLabel("AMBIL NOMOR ANTRIAN ANDA")
        self.label_ajakan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gaya_ajakan(sukses=False)
        susunan.addWidget(self.label_ajakan)

        # Petunjuk berdiri di dalam pil berwarna, bukan sebagai tulisan abu
        # yang menggantung. Pil itu perlu selebar isinya saja, sehingga
        # labelnya diapit dua pegas alih-alih diregangkan selebar panel.
        baris_petunjuk = QHBoxLayout()
        baris_petunjuk.addStretch(1)
        self.label_petunjuk = QLabel()
        self.label_petunjuk.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_petunjuk.setWordWrap(True)
        self.label_petunjuk.setMaximumWidth(LEBAR_PIL_MAKS)
        self._set_petunjuk("Sentuh jenis layanan yang Anda butuhkan", "ajak")
        baris_petunjuk.addWidget(self.label_petunjuk)
        baris_petunjuk.addStretch(1)
        susunan.addLayout(baris_petunjuk)

        # Kisi pilihan dan layar konfirmasi bertukar tempat lewat satu
        # tumpukan, bukan disembunyikan/dimunculkan satu per satu: dengan
        # tumpukan, hanya satu yang pernah menerima sentuhan pada satu saat.
        self.tumpukan = QStackedWidget()
        susunan.addWidget(self.tumpukan, stretch=1)

        self.halaman_pilihan = QWidget()
        self.halaman_pilihan.installEventFilter(self)
        self.kisi = QVBoxLayout(self.halaman_pilihan)
        self.kisi.setSpacing(CELAH_TOMBOL)
        self.kisi.setContentsMargins(
            MARGIN_KISI, MARGIN_KISI, MARGIN_KISI, MARGIN_KISI
        )
        # Kartu tidak mengisi seluruh kisi: ukurannya dihitung di
        # _sesuaikan_ukuran_tombol. Sisa ruang dibagi rata di sekeliling
        # kelompok, bukan di antara kartu, supaya A/B/C tetap rapat.
        self.kisi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tumpukan.addWidget(self.halaman_pilihan)

        self.halaman_konfirmasi = self._bangun_halaman_konfirmasi()
        self.tumpukan.addWidget(self.halaman_konfirmasi)

        return panel

    def _bangun_halaman_konfirmasi(self) -> QWidget:
        halaman = QWidget()
        susunan = QVBoxLayout(halaman)
        susunan.setSpacing(16)

        # Judul konfirmasi memakai kotak huruf yang sama dengan kartu yang
        # barusan disentuh. Itulah yang menjawab "apakah saya menekan yang
        # benar" tanpa perlu dibaca: yang dilihat pengunjung di sini adalah
        # benda yang sama dengan yang tadi disentuhnya, diperbesar.
        baris_judul = QHBoxLayout()
        baris_judul.setSpacing(24)
        baris_judul.addStretch(1)

        self.label_konfirmasi_kode = QLabel("")
        self.label_konfirmasi_kode.setObjectName("kodeKonfirmasi")
        self.label_konfirmasi_kode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_konfirmasi_kode.setFixedSize(
            SISI_KOTAK_KONFIRMASI, SISI_KOTAK_KONFIRMASI
        )
        self.label_konfirmasi_kode.setStyleSheet(
            f"color: {DISPLAY_KIOS_TOMBOL_TEKS}; background: {DISPLAY_KIOS_TOMBOL};"
            f" border-radius: {round(SISI_KOTAK_KONFIRMASI * 0.28)}px;"
            " font-size: 68px; font-weight: 800;"
        )
        baris_judul.addWidget(self.label_konfirmasi_kode)

        self.label_konfirmasi_layanan = QLabel("")
        self.label_konfirmasi_layanan.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.label_konfirmasi_layanan.setWordWrap(True)
        self.label_konfirmasi_layanan.setStyleSheet(
            f"color: {KIOS_JUDUL}; font-size: 54px; font-weight: 800;"
        )
        baris_judul.addWidget(self.label_konfirmasi_layanan)
        baris_judul.addStretch(1)
        susunan.addLayout(baris_judul, stretch=1)

        baris_tombol = QHBoxLayout()
        baris_tombol.setSpacing(20)

        # Batal dibuat bergaris, bukan berlatar penuh. Dua bidang penuh
        # berdampingan tampak sederajat, padahal salah satunya hanya jalan
        # kembali dan satunya lagi menerbitkan nomor.
        btn_batal = tombol("BATAL, PILIH LAGI")
        btn_batal.setMinimumHeight(TINGGI_TOMBOL_KONFIRMASI_MIN)
        btn_batal.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_batal.setStyleSheet(
            f"QPushButton {{ color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS};"
            " background: #FFFFFF; border: 3px solid #94A3B8;"
            f" border-radius: {RADIUS_KARTU}px;"
            " font-size: 32px; font-weight: 700; }}"
            "QPushButton:hover { background: #F1F5F9; border: 3px solid #64748B; }"
            "QPushButton:pressed { background: #E2E8F0; }"
        )
        btn_batal.clicked.connect(self._batal_konfirmasi)
        _bayangan(btn_batal, 18, 6, 35)
        baris_tombol.addWidget(btn_batal, stretch=2)

        btn_konfirmasi = tombol("YA, AMBIL NOMOR")
        btn_konfirmasi.setMinimumHeight(TINGGI_TOMBOL_KONFIRMASI_MIN)
        btn_konfirmasi.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_konfirmasi.setStyleSheet(
            f"QPushButton {{ color: white; background: {KIOS_SUKSES};"
            f" border: none; border-radius: {RADIUS_KARTU}px;"
            " font-size: 36px; font-weight: 800; }}"
            f"QPushButton:hover {{ background: {KIOS_SUKSES_TEKAN}; }}"
            "QPushButton:pressed { background: #065F46; }"
        )
        btn_konfirmasi.clicked.connect(self._konfirmasi_ambil)
        _bayangan(btn_konfirmasi, 28, 10, 95)
        # Tombol yang menerbitkan nomor mendapat jatah lebih lebar. Pada
        # layar sentuh, lebar adalah bagian dari seberapa jelas sebuah
        # tombol menawarkan diri untuk ditekan.
        baris_tombol.addWidget(btn_konfirmasi, stretch=3)

        # Tombolnya diberi jatah dua kali lipat label di atasnya: keduanya
        # yang benar-benar disentuh, jadi keduanya yang paling berhak atas
        # ruang lebih begitu panel lebih lapang daripada jendela pengembang.
        susunan.addLayout(baris_tombol, stretch=2)
        return halaman

    def _gaya_ajakan(self, *, sukses: bool) -> None:
        """Judul panel: ajakan biasa, atau kabar nomor yang baru terbit."""
        if sukses:
            self.label_ajakan.setStyleSheet(
                f"color: {KIOS_SUKSES}; font-size: 38px; font-weight: 800;"
                " letter-spacing: 2px;"
            )
        else:
            self.label_ajakan.setStyleSheet(
                f"color: {KIOS_JUDUL}; font-size: 30px; font-weight: 800;"
                " letter-spacing: 3px;"
            )

    def _gaya_petunjuk(self, nada: str) -> None:
        """Warnai pil petunjuk sesuai keadaan yang sedang dilaporkannya."""
        latar, tulisan = KIOS_PIL.get(nada, KIOS_PIL["ajak"])
        self.label_petunjuk.setStyleSheet(
            f"color: {tulisan}; background: {latar};"
            f" border-radius: 20px; padding: 9px {PADDING_PIL}px;"
            f" font-size: {UKURAN_PIL}px; font-weight: 600;"
        )

    def _set_petunjuk(self, teks: str, nada: str) -> None:
        """
        Ganti isi pil petunjuk beserta warnanya.

        Lebar minimumnya dihitung dari kalimatnya sendiri. QLabel yang
        boleh membungkus lebih suka melipat teksnya menjadi kotak hampir
        bujur sangkar daripada memanjang, sehingga tanpa perhitungan ini
        ajakan sesingkat "Sentuh jenis layanan yang Anda butuhkan" pun
        tampil dua baris di tengah panel yang masih sangat lapang.
        """
        self.label_petunjuk.setText(teks)
        font = QFont(self.font())
        font.setWeight(QFont.Weight(600))
        font.setPixelSize(UKURAN_PIL)
        lebar = QFontMetrics(font).horizontalAdvance(teks) + 2 * PADDING_PIL + KELONGGARAN_PIL
        self.label_petunjuk.setMinimumWidth(min(LEBAR_PIL_MAKS, lebar))
        self._gaya_petunjuk(nada)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Segarkan papan nomor dan daftar jenis layanan."""
        self.papan.muat_ulang()

        try:
            self.pendaftaran_dibuka = self.queue.pendaftaran_dibuka()
            data = self.master.list_categories(only_active=True)
        except Exception as exc:  # noqa: BLE001 - batas UI kios, tanpa dialog
            self._tampilkan_kesalahan(exc)
            return

        self.kategori = data or []
        self._susun_tombol()
        self._perbarui_jeda()

    def _sidik_layanan(self, kategori) -> tuple:
        """
        Sidik daftar layanan: yang menentukan tampilan kartu, itu saja.

        `info_text` tidak ikut. Isinya hanya dibaca ketika layanannya
        disentuh — dan memang dibaca ulang setiap kali disentuh — sehingga
        perubahannya tidak perlu menyusun ulang kartu apa pun.
        """
        return tuple(
            (baris.id, baris.name, baris.prefix, baris.display_order)
            for baris in kategori
        )

    def _periksa_perubahan_layanan(self) -> None:
        """
        Susun ulang kartu bila admin mengubah daftar jenis layanan.

        Hanya ketika layarnya sedang menganggur. Menyusun ulang kartu tepat
        saat pengunjung berada di layar konfirmasi akan membatalkan
        pilihannya tanpa ia mengerti mengapa, dan menyusunnya ulang saat
        kartu nomor sedang tampil merebut layar yang sedang dibaca orang.
        Perubahan daftar layanan tidak pernah mendesak; menunggu satu
        putaran lagi selalu boleh.
        """
        if self._menunggu_konfirmasi or self._penghapus_hasil.isActive():
            return

        try:
            kategori = self.master.list_categories(only_active=True) or []
        except Exception:  # noqa: BLE001 - layar publik tidak boleh mati di sini
            logger.exception(
                "Daftar jenis layanan tidak terbaca; kartu anjungan dibiarkan"
            )
            return

        if self._sidik_layanan(kategori) == self._sidik_layanan(self.kategori):
            return

        logger.info(
            "Daftar jenis layanan berubah (%d -> %d); kartu anjungan disusun ulang",
            len(self.kategori),
            len(kategori),
        )
        self.kategori = kategori
        self._susun_tombol()
        # Tombol yang baru dibangun selalu lahir hidup. Tanpa baris ini,
        # kartu yang muncul tepat di tengah jeda pengambilan nomor bisa
        # disentuh padahal jedanya belum habis.
        self._perbarui_jeda()

    def _susun_tombol(self) -> None:
        while self.kisi.count():
            butir = self.kisi.takeAt(0)
            widget = butir.widget()
            if widget is not None:
                widget.deleteLater()
            susun = butir.layout()
            if susun is not None:
                while susun.count():
                    dalam = susun.takeAt(0)
                    isi = dalam.widget()
                    if isi is not None:
                        isi.deleteLater()
        self.tombol_layanan = []

        if not self.kategori:
            kosong = QLabel("Belum ada jenis layanan yang dibuka.")
            kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kosong.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 20px;")
            self.kisi.addWidget(kosong)
            return

        # Tinggi panel TIDAK ikut dinaikkan untuk baris kedua. Tinggi
        # minimum yang lebih besar memang membuat panelnya setinggi yang
        # diminta, tetapi papan di atasnya tidak ikut mengalah: jumlah
        # keduanya melebihi tinggi jendela, dan yang meluber keluar layar
        # justru baris kartu paling bawah — tepat bagian yang harus
        # disentuh. Yang mengalah adalah tinggi kartunya, di
        # `_sesuaikan_ukuran_tombol`.
        self.kisi.addStretch(1)
        awal = 0
        for banyak in baris_kisi(len(self.kategori)):
            baris = QHBoxLayout()
            baris.setSpacing(CELAH_TOMBOL)
            baris.addStretch(1)
            for layanan in self.kategori[awal : awal + banyak]:
                btn = self._bangun_tombol_layanan(layanan)
                self.tombol_layanan.append(btn)
                baris.addWidget(btn)
            baris.addStretch(1)
            self.kisi.addLayout(baris)
            awal += banyak
        self.kisi.addStretch(1)
        self._sesuaikan_ukuran_tombol()

    def _bangun_tombol_layanan(self, layanan):
        btn = tombol("", variant="primary")
        btn.setMinimumSize(LEBAR_TOMBOL_MIN, TINGGI_TOMBOL_MIN)
        btn.setMaximumSize(LEBAR_TOMBOL_MAKS, TINGGI_TOMBOL_MAKS)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setStyleSheet(
            f"QPushButton {{ color: {DISPLAY_KIOS_TOMBOL_TEKS};"
            f" background: {DISPLAY_KIOS_TOMBOL};"
            f" border: none; border-radius: {RADIUS_KARTU}px; }}"
            f"QPushButton:hover {{ background: {DISPLAY_KIOS_TOMBOL_HOVER}; }}"
            f"QPushButton:pressed {{ background: {DISPLAY_KIOS_TOMBOL_TEKAN}; }}"
            f"QPushButton:disabled {{ background: {DISPLAY_KIOS_TOMBOL_MATI};"
            f" color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS}; }}"
        )
        _bayangan(btn, 26, 8, 60)

        isi = QVBoxLayout(btn)
        isi.setContentsMargins(
            MARGIN_ISI_TOMBOL,
            MARGIN_ISI_TOMBOL,
            MARGIN_ISI_TOMBOL,
            MARGIN_ISI_TOMBOL,
        )
        isi.setSpacing(CELAH_ISI_TOMBOL)

        prefix = QLabel(layanan.prefix)
        prefix.setObjectName("prefixLayanan")
        prefix.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prefix.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        prefix.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        isi.addStretch(1)
        isi.addWidget(prefix, alignment=Qt.AlignmentFlag.AlignHCenter)

        nama = QLabel(layanan.name)
        nama.setObjectName("namaLayanan")
        nama.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nama.setWordWrap(True)
        nama.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        nama.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        isi.addWidget(nama)
        isi.addStretch(1)

        self._warnai_tulisan_tombol(btn, aktif=True)
        btn.installEventFilter(self)
        btn.clicked.connect(lambda _, layanan=layanan: self._pilih_layanan(layanan))
        return btn

    def _sesuaikan_ukuran_tombol(self) -> None:
        """
        Hitung ukuran kartu dari ruang yang benar-benar ada.

        Tanpa jepitan lebar, kebijakan Expanding membuat kartu meregang
        selebar panel — pada 1080p itu batang ~600×120, bukan kartu yang
        mengundang sentuhan. Tetapi jepitannya TIDAK tetap: batasnya
        melonggar ketika kolomnya sedikit (lihat PEMBESAR_KARTU), supaya
        kantor berlayanan satu atau dua tidak menyisakan separuh panel
        kosong di kiri dan kanan kartunya.

        Baris terakhir yang tidak penuh — 3+2 pada lima layanan — kartunya
        dilebarkan sampai barisnya sama panjang dengan baris di atasnya.
        Dua kartu seukuran kartu di baris atas menyisakan lubang di kanan
        dan kiri, dan lubang itu terbaca sebagai ada yang hilang.
        """
        if not self.tombol_layanan:
            return

        pola = baris_kisi(len(self.tombol_layanan))
        n_kolom, n_baris = max(pola), len(pola)
        lebar_area = self.halaman_pilihan.width() - 2 * MARGIN_KISI
        tinggi_area = self.halaman_pilihan.height() - 2 * MARGIN_KISI

        if lebar_area <= 0 or tinggi_area <= 0:
            lebar, tinggi = LEBAR_TOMBOL_MIN, TINGGI_TOMBOL_MIN
        else:
            pembesar = PEMBESAR_KARTU.get(n_kolom, 1.0)
            lebar_maks = round(LEBAR_TOMBOL_MAKS * pembesar)
            tinggi_maks = round(TINGGI_TOMBOL_MAKS * pembesar)

            lebar = (lebar_area - CELAH_TOMBOL * (n_kolom - 1)) // n_kolom
            lebar = min(lebar_maks, max(LEBAR_TOMBOL_MIN, lebar))
            tinggi = round(lebar * RASIO_TINGGI_TOMBOL)
            tinggi = min(tinggi_maks, max(TINGGI_TOMBOL_MIN, tinggi))
            tinggi_baris = (tinggi_area - CELAH_TOMBOL * (n_baris - 1)) // n_baris
            if tinggi_baris > 0:
                # Jatah barisnya ditaati apa adanya, TANPA batas bawah.
                # Batas bawah apa pun di sini akan membuat baris-baris
                # kartu saling menindih begitu panel tidak cukup tinggi —
                # dan kartu yang tertindih kehilangan nama layanannya.
                # Kartu yang sedikit terlalu pendek masih bisa disentuh;
                # kartu yang tertimbun kartu lain tidak.
                tinggi = min(tinggi, tinggi_baris)

        lebar_penuh = n_kolom * lebar + (n_kolom - 1) * CELAH_TOMBOL
        awal = 0
        for banyak in pola:
            lebar_baris = lebar
            if banyak < n_kolom:
                lebar_rata = (lebar_penuh - CELAH_TOMBOL * (banyak - 1)) // banyak
                # Melebar secukupnya, dan tidak pernah menyempit. Pada
                # jendela yang pendek kartunya sudah terjepit tinggi;
                # menyempitkannya lagi di baris yang tidak penuh membuat
                # kartu di situ tampak lebih kecil daripada kartu di
                # atasnya, bukan lebih rapi.
                lebar_baris = max(
                    lebar, min(lebar_rata, round(lebar * PEMBESAR_BARIS_AKHIR))
                )
            for btn in self.tombol_layanan[awal : awal + banyak]:
                if btn.width() != lebar_baris or btn.height() != tinggi:
                    btn.setFixedSize(lebar_baris, tinggi)
            awal += banyak
        self.kisi.activate()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - nama API Qt
        if event.type() == QEvent.Type.Resize:
            if obj is self.halaman_pilihan:
                self._sesuaikan_ukuran_tombol()
            elif obj in self.tombol_layanan:
                self._warnai_tulisan_tombol(obj, aktif=obj.isEnabled())
        return super().eventFilter(obj, event)

    def _warnai_tulisan_tombol(self, btn, *, aktif: bool) -> None:
        """
        Susun ulang huruf di dalam kartu, mengikuti ukuran kartu sekarang.

        Warna ditulis di label, bukan diwarisi dari tombol. Stylesheet
        global `QWidget { color }` mengalahkan `color` pada QPushButton,
        sehingga huruf A/B/C sempat tampak gelap di atas latar berwarna
        dan hampir tidak terbaca.

        Ukuran huruf mengikuti tinggi kartu (bukan angka tetap), supaya
        kartu besar di layar lebar tidak menyisakan huruf kecil di
        tengahnya — tetapi dijepit ke lebar DAN tinggi kartu yang
        SUNGGUHAN, bukan sekadar TINGGI_TOMBOL_MIN yang cuma titik awal
        permintaan. Kartu yang terperas lebih pendek daripada itu —
        jendela kios yang tidak setinggi dugaan, atau tiga baris tombol
        yang berdesakan — tanpa jepitan ini tetap mendapat huruf seukuran
        kartu yang lebih tinggi, dan huruf layanan bertumpuk dengan nama
        layanan di bawahnya.
        """
        warna = DISPLAY_KIOS_TOMBOL_TEKS if aktif else DISPLAY_KIOS_TOMBOL_MATI_TEKS
        latar_kotak = KIOS_KOTAK_HURUF if aktif else KIOS_KOTAK_HURUF_MATI
        tinggi_kartu = max(1, btn.height())
        padding = 2 * MARGIN_ISI_TOMBOL
        lebar_tersedia = max(1, btn.width() - padding)
        tinggi_isi = max(1, btn.height() - padding - CELAH_ISI_TOMBOL)
        # Huruf layanan mendapat porsi lebih tinggi daripada nama layanan
        # di bawahnya. Angka di bawah adalah BATAS ATAS metrik huruf, bukan
        # jatah layout: sisa tinggi dipakai stretch supaya keduanya tetap
        # di tengah kartu.
        tinggi_prefix = round(tinggi_isi * 0.52)
        tinggi_nama = round(tinggi_isi * 0.30)

        # Huruf layanan duduk di dalam kotak bujur sangkar tembus pandang,
        # seperti kotak ikon di layar pembuka. Kotak itu yang memberi
        # hurufnya tempat yang tetap: tanpa kotak, "A" dan "M" tampak
        # bergeser naik-turun dari kartu ke kartu karena tinggi hurufnya
        # sendiri berbeda.
        prefix = btn.findChild(QLabel, "prefixLayanan")
        if prefix is not None:
            # Tanpa batas bawah: kotak yang dipaksa berukuran tetap akan
            # lebih besar daripada kartunya sendiri begitu kartunya
            # terjepit, lalu tergambar melimpah keluar tepi kartu.
            sisi = max(1, min(tinggi_prefix, lebar_tersedia))
            ukuran = self._pas_ukuran(
                prefix.text(),
                max(14, round(sisi * BAGIAN_KOTAK_HURUF)),
                sisi - 8,
                sisi - 6,
                800,
            )
            prefix.setFixedSize(sisi, sisi)
            prefix.setStyleSheet(
                f"color: {warna}; background: {latar_kotak};"
                f" border-radius: {round(sisi * 0.28)}px;"
                f" font-size: {ukuran}px; font-weight: 800;"
            )

        nama = btn.findChild(QLabel, "namaLayanan")
        if nama is not None:
            ukuran = self._pas_ukuran(
                nama.text(),
                max(14, round(tinggi_kartu * 0.15)),
                lebar_tersedia,
                max(1, tinggi_nama),
                700,
            )
            nama.setStyleSheet(
                f"color: {warna}; background: transparent;"
                f" font-size: {ukuran}px; font-weight: 700;"
            )
            font = QFont(self.font())
            font.setWeight(QFont.Weight(700))
            font.setPixelSize(ukuran)
            nama.setMinimumHeight(QFontMetrics(font).height())
            nama.updateGeometry()

    def _pas_ukuran(
        self, teks: str, mula: int, lebar_tersedia: int, tinggi_tersedia: int, berat: int
    ) -> int:
        """
        Kecilkan ukuran huruf sampai `teks` muat pada lebar DAN tinggi yang ada.

        `setWordWrap` pada label tidak menolong satu kata panjang tanpa
        spasi — Qt hanya membungkus di antara kata, bukan di tengah huruf
        — sehingga kata tunggal yang lebih lebar daripada kartunya tetap
        melimpah keluar berapa pun `wordWrap` disetel. Batas tingginya
        mencegah dua label bertumpuk saat kartunya sendiri terperas lebih
        pendek daripada jumlah tinggi kedua huruf pada ukuran nominalnya.
        """
        font = QFont(self.font())
        font.setWeight(QFont.Weight(berat))
        ukuran = mula
        while ukuran > 10:
            font.setPixelSize(ukuran)
            metrik = QFontMetrics(font)
            if (
                metrik.horizontalAdvance(teks) <= lebar_tersedia
                and metrik.height() <= tinggi_tersedia
            ):
                break
            ukuran -= 1
        return ukuran

    # -----------------------------------------------------------------
    # Tindakan
    # -----------------------------------------------------------------

    def _pilih_layanan(self, layanan) -> None:
        """
        Tampilkan layar konfirmasi, dan jangan langsung menerbitkan nomor.

        Menerbitkan nomor sekaligus mencetaknya di satu sentuhan tidak
        memberi pengunjung kesempatan membatalkan salah pilih: begitu
        tersentuh, nomornya sudah sah dan tiketnya sudah keluar.
        """
        self._kategori_terpilih = layanan
        self.label_konfirmasi_kode.setText(layanan.prefix)
        self.label_konfirmasi_layanan.setText(layanan.name)
        self._menunggu_konfirmasi = True
        self._set_petunjuk("Pastikan pilihan Anda sudah benar", "konfirmasi")
        self.tumpukan.setCurrentWidget(self.halaman_konfirmasi)
        self._pembatal_konfirmasi.start(JEDA_KONFIRMASI)
        # Panel papan nomor beralih dari sambutan ke info layanan yang
        # baru disentuh, supaya pengunjung membaca sesuatu yang relevan
        # dengan pilihannya sementara menunggu konfirmasi.
        #
        # Berkasnya dicari setiap kali disentuh, bukan sekali saat halaman
        # dibangun: admin boleh mengganti media layanan selagi anjungan
        # menyala, dan pembacaan folder sekali sentuh tidak mahal.
        self.papan.tampilkan_info_kios(
            layanan.info_text, berkas=media_layanan(layanan.code)
        )

    def _batal_konfirmasi(self) -> None:
        """Kembali ke kisi pilihan tanpa menerbitkan nomor apa pun."""
        self._pembatal_konfirmasi.stop()
        self._menunggu_konfirmasi = False
        self._kategori_terpilih = None
        self.tumpukan.setCurrentWidget(self.halaman_pilihan)
        self.papan.tampilkan_info_kios(None)
        self._perbarui_jeda()

    def _konfirmasi_ambil(self) -> None:
        """
        Baru di sinilah nomor benar-benar diterbitkan dan dicetak.

        Panel papan SENGAJA tidak dikembalikan ke sambutan di sini. Media
        layanan tetap dipegang sampai `_tampilkan_hasil()` menggantinya
        dengan kartu nomor — mengembalikannya lebih dulu membuat sambutan
        menyembul sekejap di antara keduanya, dan itu terbaca sebagai
        kedipan. Jalur gagalnya diurus `ambil_nomor()`.
        """
        self._pembatal_konfirmasi.stop()
        self._menunggu_konfirmasi = False
        layanan = self._kategori_terpilih
        self._kategori_terpilih = None
        self.tumpukan.setCurrentWidget(self.halaman_pilihan)
        if layanan is not None:
            self.ambil_nomor(layanan.id)
        else:
            self.papan.tampilkan_info_kios(None)

    def ambil_nomor(self, category_id: int) -> None:
        """Terbitkan satu nomor untuk pengunjung yang menekan tombol."""
        try:
            nomor = self.queue.create_queue(category_id)
        except Exception as exc:  # noqa: BLE001 - dialog modal menyangkut layar publik
            self._tampilkan_kesalahan(exc)
            self._kunci_tombol()
            # Nomornya tidak jadi terbit, jadi kartu nomor tidak akan
            # pernah tampil. Tanpa baris ini panel tersangkut memegang
            # media layanan yang tadi disentuh, dan tidak ada lagi yang
            # akan membebaskannya.
            self.papan.tampilkan_info_kios(None)
            return

        self._tahan_petunjuk = False
        hasil_cetak = self._cetak(nomor)
        self._tampilkan_hasil(nomor, hasil_cetak)
        self.papan.muat_ulang()
        self._perbarui_jeda()

    def _tampilkan_kesalahan(self, exc: Exception) -> None:
        """
        Tampilkan kegagalan di label, bukan kotak dialog.

        Dialog modal menyangkut begitu pengunjung berbalik pergi, dan orang
        berikutnya menemukan layar yang tidak bisa dipakai.
        """
        if isinstance(exc, AppError):
            logger.warning("%s: %s", type(exc).__name__, exc.user_message)
        else:
            logger.exception("Kesalahan tak terduga pada kios")
        self._tahan_petunjuk = True
        self._set_petunjuk(pesan_untuk_user(exc), "salah")

    def _kunci_tombol(self) -> None:
        """
        Sesuaikan tombol dengan jeda yang masih berjalan.

        Dipanggil dari penanganan kegagalan `ambil_nomor()`, sehingga
        pembacaan jedanya WAJIB ikut dijaga: bila kegagalan tadi memang
        karena database tidak terjangkau, membacanya lagi di sini akan
        gagal untuk alasan yang sama — tepat di dalam blok except — dan
        exception-nya lolos dari slot Qt. Layar kios lalu berhenti bekerja
        justru pada saat penanganan kegagalannya sedang dibutuhkan.
        """
        try:
            sisa = self.queue.sisa_jeda_kios()
        except Exception:  # noqa: BLE001 - layar publik tidak boleh mati di sini
            logger.exception("Gagal membaca sisa jeda kios; tombol dimatikan sementara")
            sisa = float("inf")

        aktif = sisa <= 0 and self.pendaftaran_dibuka
        for btn in self.tombol_layanan:
            btn.setEnabled(aktif)
            self._warnai_tulisan_tombol(btn, aktif=aktif)

    def _cetak(self, nomor: QueueInfo) -> str:
        """
        Cetak tiket, dan jangan pernah menggagalkan pengambilan nomor.

        Nomor sudah terbit dan tersimpan sebelum tiket dicetak. Printer yang
        kehabisan kertas tidak boleh membuat pengunjung kehilangan gilirannya
        — nomornya tetap sah, dan petugas cukup menyebutkannya.

        TicketService.cetak() memang tidak pernah melempar exception;
        kegagalan dilaporkan sebagai hasil.

        Hasilnya DIKEMBALIKAN, tidak cukup dicatat di log: kalimat arahan
        pada kartu nomor bergantung padanya, dan menyuruh pengunjung
        "ambil tiket Anda" di depan printer yang tidak mengeluarkan apa
        pun jauh lebih menyesatkan daripada tidak berkata apa-apa.
        """
        if self.ticket is None or self._mode_cetak() == "none":
            return CETAK_TANPA_PRINTER
        hasil = self.ticket.cetak(nomor)
        if not hasil.berhasil:
            logger.warning("Tiket %s gagal dicetak: %s", nomor.queue_number, hasil.pesan)
            return CETAK_GAGAL
        return CETAK_BERHASIL

    def _mode_cetak(self) -> str:
        """
        Cara mesin ini mencetak, atau "none" bila pengaturannya tak terbaca.

        Dibaca setiap kali, bukan sekali saat halaman dibangun: `pdf` dan
        `system` sama-sama menghasilkan kertas — PdfTicketPrinter memang
        dipakai printer thermal yang menerima PDF — sehingga hanya "none"
        yang berarti benar-benar tidak ada tiket yang keluar.
        """
        try:
            return (mode_pencetak(self.settings) or "").strip().lower()
        except Exception:  # noqa: BLE001 - layar publik tidak boleh mati di sini
            logger.exception("Mode pencetak tidak terbaca; dianggap tanpa printer")
            return "none"

    def _tampilkan_hasil(self, nomor: QueueInfo, hasil_cetak: str) -> None:
        arahan = ARAHAN_CETAK.get(hasil_cetak, ARAHAN_CETAK[CETAK_TANPA_PRINTER])
        self.label_ajakan.setText(f"NOMOR ANDA:  {nomor.queue_number}")
        self._gaya_ajakan(sukses=True)
        self._set_petunjuk(arahan, "hasil")
        # Kartu nomor di panel papan. Nomornya sengaja diulang di dua
        # tempat — itu satu-satunya hal yang layak diulang — sedangkan
        # kalimat arahannya berasal dari sumber yang sama persis.
        self.papan.tampilkan_kartu_kios(
            nomor=nomor.queue_number,
            layanan=nomor.category_name,
            sisa=baris_sisa_antrian(self._sisa_antrian(nomor)),
            arahan=arahan,
        )
        self._penghapus_hasil.start(self._lama_hasil_ms())

    def _sisa_antrian(self, nomor: QueueInfo) -> int | None:
        """
        Banyaknya nomor yang masih menunggu di depan pengunjung ini.

        Kegagalannya ditelan, persis seperti `TicketService._ringkasan()`:
        angka sisa antrian adalah tambahan yang menyenangkan, sedangkan
        nomornya adalah alasan pengunjung berdiri di depan mesin. Database
        yang sedang tersendat tidak boleh membuat kartu nomornya kosong.
        """
        try:
            return self.queue.ringkasan_tiket(nomor).sisa_antrian
        except Exception:  # noqa: BLE001 - kartu nomor tidak boleh gagal karenanya
            logger.warning(
                "Sisa antrian untuk %s tidak terbaca; kartu tampil tanpa baris itu",
                nomor.queue_number,
                exc_info=True,
            )
            return None

    def _lama_hasil_ms(self) -> int:
        """
        Tahan kartu nomor setidaknya sampai tombol A/B/C hidup lagi.

        Jeda pengambilan nomor bawaannya 10 detik sedangkan JEDA_HASIL 8
        detik, sehingga tanpa penyelarasan ini ada dua detik kosong: panel
        sudah kembali ke sambutan padahal tombolnya masih mati, dan layar
        tampak siap dipakai padahal belum.
        """
        try:
            jeda_ms = max(0, self.queue.jeda_kios_detik()) * 1000
        except Exception:  # noqa: BLE001 - pewaktu hasil tidak boleh gagal terbit
            logger.exception("Jeda kios tidak terbaca; kartu nomor memakai jeda bawaan")
            jeda_ms = 0
        return max(JEDA_HASIL, jeda_ms)

    def _bersihkan_hasil(self) -> None:
        self.label_ajakan.setText("AMBIL NOMOR ANTRIAN ANDA")
        self._gaya_ajakan(sukses=False)
        # Satu-satunya tempat panel dibebaskan setelah nomor terbit.
        self.papan.tampilkan_info_kios(None)
        self._perbarui_jeda()

    def _perbarui_jeda(self) -> None:
        """
        Matikan tombol selama jeda, dan katakan alasannya.

        Tombol yang mati tanpa keterangan membuat pengunjung menekannya
        berulang kali dan mengira layarnya rusak.
        """
        # Keduanya membaca database, dan keduanya dipanggil dari pewaktu
        # yang berdetak terus. Kegagalan di sini tidak boleh menghentikan
        # pewaktunya — kios akan berhenti menghitung mundur dan tombolnya
        # tinggal mati selamanya — tetapi tetap wajib tercatat, sebab kios
        # berdiri tanpa penjaga dan tidak ada yang akan melaporkannya.
        try:
            self.pendaftaran_dibuka = self.queue.pendaftaran_dibuka()
            sisa = self.queue.sisa_jeda_kios()
        except Exception:  # noqa: BLE001 - pewaktu tidak boleh berhenti karenanya
            logger.exception("Gagal membaca status kios; memakai nilai terakhir")
            sisa = 0.0

        aktif = sisa <= 0 and self.pendaftaran_dibuka

        for btn in self.tombol_layanan:
            btn.setEnabled(aktif)
            self._warnai_tulisan_tombol(btn, aktif=aktif)

        if self._penghapus_hasil.isActive() or self._menunggu_konfirmasi:
            return
        if not self.pendaftaran_dibuka:
            self._tahan_petunjuk = False
            self._set_petunjuk(
                "Pendaftaran nomor antrian sedang ditutup sementara.", "tunggu"
            )
        elif not aktif:
            self._tahan_petunjuk = False
            self._set_petunjuk(
                f"Mohon tunggu {int(sisa) + 1} detik sebelum mengambil nomor berikutnya.",
                "tunggu",
            )
        elif not self._tahan_petunjuk:
            # "Jenis layanan yang Anda butuhkan" mengandaikan ada yang
            # perlu dipilih. Pada kantor berlayanan tunggal tidak ada
            # pilihan apa pun, dan kalimat itu justru membuat pengunjung
            # mencari tombol lain yang tidak ada.
            self._set_petunjuk(
                "Sentuh tombol di bawah untuk mengambil nomor"
                if len(self.kategori) == 1
                else "Sentuh jenis layanan yang Anda butuhkan",
                "ajak",
            )
