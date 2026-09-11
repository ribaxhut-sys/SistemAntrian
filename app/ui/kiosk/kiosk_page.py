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

import re

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPalette, QShortcut
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
from app.services.settings_service import (
    URUTAN_PANEL_IKLAN_ATAS,
    URUTAN_PANEL_LAYANAN_ATAS,
    SettingsService,
)
from app.services.sound_service import SoundPlayer
from app.services.ticket_service import TicketService, baris_sisa_antrian, mode_pencetak
from app.ui.common import pesan_untuk_user, tombol
from app.ui.display.display_page import DisplayPage
from app.ui.kiosk.pita_loket import PitaLoketKios
from app.ui.kiosk.sambutan import media_layanan
from app.ui.style import (
    DISPLAY_KIOS_KELOMPOK,
    DISPLAY_KIOS_KELOMPOK_HOVER,
    DISPLAY_KIOS_KELOMPOK_TEKAN,
    DISPLAY_KIOS_KEMBALI,
    DISPLAY_KIOS_KEMBALI_HOVER,
    DISPLAY_KIOS_KEMBALI_TEKAN,
    DISPLAY_KIOS_KEMBALI_TEKS,
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
from app.ui.efek import pasang_efek

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
#: Tampil di SATU tempat: pil petunjuk di panel bawah, yang berada tepat
#: di depan tangan pengunjung dan di sebelah printernya. Kartu nomor di
#: papan atas sengaja tidak ikut menyebutkannya — kartu itu yang difoto,
#: dan yang perlu terbawa dalam foto hanya nomornya.
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

#: Lama menu kelompok dibiarkan terbuka tanpa disentuh sebelum anjungan
#: kembali sendiri ke menu utama, dalam milidetik.
#:
#: Pengunjung yang membuka Konsultasi lalu berbalik pergi — karena
#: dipanggil temannya, karena salah mesin, karena apa pun — tidak boleh
#: meninggalkan anjungan tersangkut di dalam menu untuk orang berikutnya.
#: Orang berikutnya itu tidak tahu ia sedang berada di dalam kelompok, dan
#: akan mencari layanan yang memang tidak ada di daftar yang ia lihat.
#:
#: Lebih panjang daripada JEDA_KONFIRMASI: di sini pengunjung sedang
#: MEMBACA daftar dan memilih, bukan menjawab satu pertanyaan ya/tidak.
JEDA_PULANG = 25000

#: Tanda pada kartu yang membuka submenu. Bukan prefix tiket (A/B/C) —
#: huruf itu hanya menjanjikan nomor. Tanda ini berdiri di samping nama,
#: seperti logo "masuk ke dalam".
TANDA_KELOMPOK = ">"
#: Tanda pada tombol KEMBALI (cadangan tersembunyi; kartu kisi memakai teks).
TANDA_KEMBALI = "‹"

#: Tinggi wadah kosong di kiri dan kanan pil petunjuk. Tombol KEMBALI
#: yang terlihat adalah kartu di dalam kisi, seukuran kartu submenu; kedua
#: wadah ini hanya memesan tinggi baris pil, supaya jatah tinggi kisi di
#: bawahnya sama di setiap tingkat menu. Lebarnya sengaja tidak dipesan —
#: lihat catatan baris pil di `_bangun_panel_ambil`.
TINGGI_TOMBOL_KEMBALI = 36

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
#: Nilai "tanpa batas" milik Qt (QWIDGETSIZE_MAX), untuk melepas batas
#: tinggi panel ambil nomor kembali.
TINGGI_TAK_TERBATAS = (1 << 24) - 1
#: Perbandingan lebar:tinggi panel informasi bila pengaturannya tak
#: terbaca atau berisi angka yang tidak masuk akal.
RASIO_INFO_BAWAAN = 3.0
#: Batas kewarasan `kiosk.info_ratio`. Di luar ini panelnya bukan lagi
#: bidang yang bisa diisi gambar: 1,0 berarti bujur sangkar setinggi
#: lebar layar, 8,0 berarti pita setipis judul.
RASIO_INFO_MIN = 1.0
RASIO_INFO_MAKS = 8.0
TINGGI_TOMBOL_MIN = 120
#: Batas atas banyaknya kolom, berapa pun lebar layarnya. Kartu yang
#: terlalu banyak berjajar membuat pengunjung memindai, bukan memilih.
#: Batas yang SUNGGUHAN dihitung dari lebar panel — lihat `_kolom_maks`.
KOLOM_MAKS = 6
#: Banyaknya kolom yang dipakai bila lebar panel belum diketahui, dan
#: batas atas kisi pada layar sempit.
KOLOM_BAWAAN = 3

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
#: Celah tegak di dalam kelompok berbaris dua. Celah 50 px milik menu
#: utama memakan hampir satu kartu utuh begitu lima anak harus 3+2 di
#: panel yang tingginya tidak boleh merampas papan informasi.
CELAH_BARIS_KELOMPOK = 16
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
#: Ruang kosong di kiri dan kanan tulisan tombol konfirmasi, dan batas
#: bawah huruf yang menyusut — tombol konfirmasi dan judul panel — saat
#: widgetnya lebih sempit daripada tulisannya. 12 px cukup untuk menjauhkan
#: tulisan dari lengkung sudut tombol; 24 px membuat "BATAL, PILIH LAGI"
#: mentok di batas bawah hurufnya pada skala 200% padahal masih muat.
TEPI_TULISAN_KONFIRMASI = 12
HURUF_KONFIRMASI_MIN = 16

#: Pintasan papan ketik untuk menukar posisi iklan dan kartu layanan.
#:
#: Sengaja BUKAN tombol di layar. Anjungan berdiri tanpa penjaga, dan
#: tombol yang terlihat akan ditekan pengunjung — seorang anak cukup
#: sekali menyentuhnya untuk memindahkan kartu layanan ke atas layar,
#: dan pilihan itu tersimpan untuk seluruh sistem sampai ada orang yang
#: tahu tombolnya ada. Orang yang memasang layar membawa papan ketik;
#: pengunjung tidak. Pengaturan `kiosk.panel_order` di halaman Pengaturan
#: menulis nilai yang sama.
PINTASAN_TUKAR_PANEL = "Ctrl+Shift+T"


def baris_kisi(jumlah: int, kolom_maks: int = KOLOM_BAWAAN) -> list[int]:
    """
    Banyaknya kartu pada tiap baris.

    Barisnya diisi serata mungkin, bukan sekolom-sekolom sampai habis.
    Empat layanan yang disusun 3+1 meninggalkan satu kartu sendirian di
    bawah — terbaca sebagai kartu yang berbeda derajat, padahal semua
    jenis layanan setara. Baris yang lebih panjang ditaruh di ATAS,
    karena itulah yang pertama dibaca.

    Pada `kolom_maks` tiga:

        1 -> [1]      4 -> [2, 2]     7 -> [3, 2, 2]
        2 -> [2]      5 -> [3, 2]     8 -> [3, 3, 2]
        3 -> [3]      6 -> [3, 3]     9 -> [3, 3, 3]

    `kolom_maks` datang dari lebar panel yang sesungguhnya, bukan angka
    tetap: baris kedua mahal sekarang. Tinggi panel informasi dikunci,
    jadi baris tambahan tidak lagi dibayar oleh papan di atasnya
    melainkan oleh tinggi kartunya sendiri — empat layanan yang dipaksa
    2+2 di layar selebar 1920 menghasilkan kartu 552x72, dan kartu
    sepipih itu bukan lagi tombol.
    """
    if jumlah <= 0:
        return []
    baris = -(-jumlah // max(1, kolom_maks))  # pembulatan ke atas
    dasar, sisa = divmod(jumlah, baris)
    return [dasar + (1 if urutan < sisa else 0) for urutan in range(baris)]


def _bayangan(widget: QWidget, radius: int, y: int, alpha: int) -> None:
    """Bayangan tipis, sama seperti kartu loket dan panel sorotan di TV."""
    efek = QGraphicsDropShadowEffect(widget)
    efek.setBlurRadius(radius)
    efek.setOffset(0, y)
    efek.setColor(QColor(0, 0, 0, alpha))
    pasang_efek(widget, efek)


class LabelPil(QLabel):
    """
    Pil petunjuk: sebaris bila ruangnya cukup, membungkus bila tidak.

    Dahulu lebar sebarisnya dipasang sebagai lebar MINIMUM. QLabel yang
    boleh membungkus memang lebih suka melipat teksnya menjadi kotak hampir
    bujur sangkar, dan minimum itulah yang mencegahnya — tetapi minimum
    juga tidak bisa ditawar. Pesan terpanjang ("Tiket gagal dicetak. …")
    menuntut sekitar 740 px, lebih lebar daripada seluruh panel totem pada
    skala Windows 150%, dan panelnya terdorong keluar layar.

    Lebar sebaris kini menjadi UKURAN YANG DIINGINKAN: diberikan selama
    ruangnya ada, dilepas — pil membungkus ke baris kedua — bila tidak.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lebar_sebaris = 0

    def setel_lebar_sebaris(self, lebar: int) -> None:
        """Lebar yang membuat kalimatnya muat sebaris."""
        self._lebar_sebaris = lebar
        self.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802 - nama API Qt
        dasar = super().sizeHint()
        if self._lebar_sebaris <= 0:
            return dasar
        tinggi = self.heightForWidth(self._lebar_sebaris)
        return QSize(self._lebar_sebaris, tinggi if tinggi > 0 else dasar.height())


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
        *,
        totem: bool = False,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.master = master
        self.settings = settings
        self.sound = sound
        self.ticket = ticket
        #: Anjungan berdiri (totem): tiga pita — iklan, kartu layanan,
        #: papan loket mini. Anjungan biasa membiarkan ini False.
        self.totem = totem
        self.kategori: list = []
        self.tombol_layanan: list = []
        self.pendaftaran_dibuka = True
        #: True selama label petunjuk menampilkan kesalahan, supaya
        #: penyegaran jeda tidak menimpanya dengan ajakan mengambil nomor.
        self._tahan_petunjuk = False
        #: True selama layar konfirmasi tampil, supaya penyegaran jeda
        #: tidak menimpa petunjuknya dan tidak mengembalikan ke kisi pilihan.
        self._menunggu_konfirmasi = False
        #: Banyaknya kolom yang dipakai kisi kartu saat ini. Dibandingkan
        #: dengan `_kolom_maks()` setiap kali panel berubah lebar.
        self._kolom_terpakai = KOLOM_BAWAAN
        #: Perbandingan panel informasi, dibaca ulang bersama daftar
        #: layanan supaya admin tidak perlu menutup anjungan untuk
        #: mengubahnya — tidak ada yang menutup aplikasi di mesin itu.
        self._rasio_info = RASIO_INFO_BAWAAN
        #: Urutan dua panel anjungan. Iklan di atas adalah bawaan; tombol
        #: Tukar dan pengaturan `kiosk.panel_order` menuliskan yang sama.
        self._urutan_panel = URUTAN_PANEL_IKLAN_ATAS
        #: Kategori yang sedang menunggu konfirmasi pengunjung.
        self._kategori_terpilih = None
        #: BATAL dan YA di layar konfirmasi, yang hurufnya mengecil
        #: bila tombolnya lebih sempit daripada tulisannya.
        self._tombol_konfirmasi: tuple = ()
        #: Seluruh widget yang hurufnya menyusut bila tidak muat — lihat
        #: `_siapkan_huruf_menyusut`. `eventFilter` mengukur ulang setiap
        #: kali salah satunya berubah ukuran.
        self._huruf_menyusut: list = []
        #: Fungsi ruang bagi widget yang lebarnya sendiri tidak bisa dipakai
        #: sebagai ukuran ruang — lihat `_siapkan_huruf_menyusut`.
        self._ruang_huruf: dict = {}
        #: Kelompok yang sedang terbuka, dari luar ke dalam. Kosong berarti
        #: pengunjung berada di menu utama. Disimpan sebagai daftar
        #: kategori, bukan satu id, supaya Konsultasi > PBJT dapat ditutup
        #: selangkah demi selangkah seperti pengunjung membukanya.
        self._jalur: list = []
        #: Kartu yang sedang terpasang di kisi, TERMASUK kartu kelompok.
        #: `tombol_layanan` hanya memuat yang benar-benar menerbitkan
        #: nomor, sebab hanya itu yang ikut dimatikan selama jeda
        #: pengambilan nomor. Tombol kembali tidak ada di keduanya: ia
        #: berdiri di baris pil, dan tidak pernah ikut dimatikan —
        #: menutup jalan pulang selama jeda akan mengurung pengunjung di
        #: dalam menu.
        self.kartu_kisi: list = []
        #: True selama `_sesuaikan_ukuran_tombol` sedang berjalan.
        #: `_setel_tinggi_panel` memanggil `setFixedHeight`, dan itu
        #: memicu Resize pada kisi yang memanggil metode ini lagi. Tanpa
        #: pengunci, putaran dalam dan luar menulis ukuran yang berbeda ke
        #: kartu yang sama, lalu kotak huruf mengikuti yang salah.
        self._sedang_menyesuaikan = False
        self._sedang_menyusun = False
        #: Ukuran kartu menu utama yang sudah dilihat pengunjung. Navigasi
        #: ke dalam kelompok mengubah geometri sesaat; tanpa kunci ini
        #: perhitungan ulang memakai angka yang sedang kacau dan ketiga
        #: kartu pulang dalam keadaan pipih.
        self._ukuran_kartu_menu: tuple[int, int] | None = None
        self._tinggi_panel_menu: int | None = None
        self._tinggi_jendela_kunci: int | None = None
        self._lebar_halaman_kunci: int | None = None
        #: Ukuran kartu yang sudah dihitung untuk setiap ukuran jendela.
        #: F11 penuh → restore → penuh harus mengembalikan kartu yang sama,
        #: bukan menghitung ulang dari tata letak yang sedang berubah.
        self._kunci_per_jendela: dict[tuple[int, int], tuple[int, int, int]] = {}

        # Timer dimiliki widget ini, bukan QTimer.singleShot yang statis.
        # singleShot tetap menyala setelah halamannya dihapus lalu menyentuh
        # label yang sudah tidak ada.
        self._penghapus_hasil = QTimer(self)
        self._penghapus_hasil.setSingleShot(True)
        self._penghapus_hasil.timeout.connect(self._bersihkan_hasil)

        self._pembatal_konfirmasi = QTimer(self)
        self._pembatal_konfirmasi.setSingleShot(True)
        self._pembatal_konfirmasi.timeout.connect(self._batal_konfirmasi)

        self._pemulang = QTimer(self)
        self._pemulang.setSingleShot(True)
        self._pemulang.timeout.connect(self._pulang)

        #: Satu kali setelah jendela selesai diubah ukurannya (F11).
        #: Tanpa ini, setiap langkah tata letak fullscreen/restore menghitung
        #: kartu dari kisi yang sedang mengerut, dan hurufnya tertinggal
        #: di ukuran yang salah.
        self._penyesuai_jendela = QTimer(self)
        self._penyesuai_jendela.setSingleShot(True)
        self._penyesuai_jendela.setInterval(0)
        self._penyesuai_jendela.timeout.connect(self._sesuaikan_setelah_ubah_jendela)

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

        # Latar kios mengikuti tema papan. Yang terlihat hanyalah sela
        # tipis di sekeliling papan, tetapi sela berwarna biru di bawah
        # papan hitam bertema LED langsung terbaca sebagai cacat.
        self.setStyleSheet(
            f"QWidget#layarKios {{ background: {self.papan.palet.latar}; }}"
        )

        self.panel_ambil = self._bangun_panel_ambil()
        self.pintasan_tukar_panel = None
        self.pita_loket = None

        if self.totem:
            # Tiga pita sama tinggi: iklan (dilihat), kartu (disentuh),
            # papan loket mini (terlalu rendah untuk disentuh).
            # Pintasan tukar tidak dipasang: pada totem kartu layanan sudah
            # di zona sentuh; menukarnya akan menaikkan kartu ke dahi.
            self.papan.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.panel_ambil.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.pita_loket = PitaLoketKios(self.papan.palet)
            self.papan.pita_loket_kios = self.pita_loket
            susunan.addWidget(self.papan, stretch=1)
            susunan.addWidget(self.panel_ambil, stretch=1)
            susunan.addWidget(self.pita_loket, stretch=1)
            self.papan.muat_ulang()
        else:
            # Dua banding satu, dan panel bawah dibatasi tingginya oleh
            # `_setel_tinggi_panel`. Perbandingan saja tidak cukup: pada
            # layar anjungan yang berdiri tegak (1080x1920) jatah 40% berarti
            # 768 piksel untuk panel yang isinya hanya menuntut sekitar 414 —
            # kartu layanan sudah mentok di batas atasnya jauh sebelum itu —
            # sehingga sisanya menjadi bidang putih kosong, sementara panel
            # informasi di atasnya yang justru dipandang dari jauh harus
            # mengalah.
            susunan.addWidget(self.papan, stretch=2)
            susunan.addWidget(self.panel_ambil, stretch=1)
            self._urutan_panel = self._baca_urutan_panel()
            self._terapkan_urutan_panel()
            self.pintasan_tukar_panel = QShortcut(
                QKeySequence(PINTASAN_TUKAR_PANEL), self, self._tukar_posisi_panel
            )

    def _baca_urutan_panel(self) -> str:
        """Nilai pengaturan, atau bawaan bila rusak."""
        try:
            nilai = self.settings.get("kiosk.panel_order", URUTAN_PANEL_IKLAN_ATAS)
        except Exception:  # noqa: BLE001 - layar publik tidak boleh mati di sini
            logger.warning(
                "Urutan panel anjungan tidak terbaca; memakai %s",
                URUTAN_PANEL_IKLAN_ATAS,
                exc_info=True,
            )
            return URUTAN_PANEL_IKLAN_ATAS
        if nilai not in {URUTAN_PANEL_IKLAN_ATAS, URUTAN_PANEL_LAYANAN_ATAS}:
            logger.warning(
                "Urutan panel anjungan %s tidak dikenali; memakai %s",
                nilai,
                URUTAN_PANEL_IKLAN_ATAS,
            )
            return URUTAN_PANEL_IKLAN_ATAS
        return nilai

    def _layanan_di_atas(self) -> bool:
        return self._urutan_panel == URUTAN_PANEL_LAYANAN_ATAS

    def _gaya_panel_ambil(self) -> None:
        """Lembaran menempel ke papan: sudut di tepi yang bersinggungan."""
        if self._layanan_di_atas():
            tepi = (
                f" border-bottom: 5px solid {self.papan.palet.tepi_unggulan};"
                f" border-bottom-left-radius: {RADIUS_PANEL}px;"
                f" border-bottom-right-radius: {RADIUS_PANEL}px;"
            )
        else:
            tepi = (
                f" border-top: 5px solid {self.papan.palet.tepi_unggulan};"
                f" border-top-left-radius: {RADIUS_PANEL}px;"
                f" border-top-right-radius: {RADIUS_PANEL}px;"
            )
        self.panel_ambil.setStyleSheet(
            "QFrame#panelAmbil { background: qlineargradient(x1:0, y1:0,"
            f" x2:0, y2:1, stop:0 {KIOS_PANEL_ATAS}, stop:1 {KIOS_PANEL_BAWAH});"
            f"{tepi} }}"
        )

    def _terapkan_urutan_panel(self) -> None:
        """Pasang iklan dan kartu layanan sesuai `_urutan_panel`."""
        if self.totem:
            return
        susunan = self.layout()
        if susunan is None:
            return
        for widget in (self.papan, self.panel_ambil):
            susunan.removeWidget(widget)
        if self._layanan_di_atas():
            susunan.addWidget(self.panel_ambil, stretch=1)
            susunan.addWidget(self.papan, stretch=2)
        else:
            susunan.addWidget(self.papan, stretch=2)
            susunan.addWidget(self.panel_ambil, stretch=1)
        self._gaya_panel_ambil()

    def _tukar_posisi_panel(self) -> None:
        """
        Pintasan di anjungan: simpan urutan baru, lalu pasang segera.

        Layar HANYA ditukar bila nilainya benar-benar tersimpan. Pemeriksaan
        berkala `_periksa_perubahan_layanan` membaca urutan dari database
        setiap 20 detik, sehingga tukar yang cuma terjadi di layar ini akan
        dibalikkan diam-diam tidak lama kemudian — dan orang yang menekannya
        melihat tata letaknya berbalik sendiri tanpa tahu sebabnya. Lebih
        jujur bila layar tidak berubah sama sekali: ia boleh mencoba lagi.
        """
        if self.totem:
            return
        try:
            self._urutan_panel = self.settings.tukar_urutan_panel_kios()
        except Exception:  # noqa: BLE001 - layar publik tidak boleh mati di sini
            logger.exception("Urutan panel anjungan tidak tersimpan; layar tidak ditukar")
            return
        logger.info("Urutan panel anjungan menjadi %s", self._urutan_panel)
        self._terapkan_urutan_panel()
        self._sesuaikan_ukuran_tombol()

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
        baris_petunjuk.setSpacing(16)
        # Wadah di kiri dan penyeimbang di kanan memesan TINGGI baris ini
        # sepanjang layar kios menyala, supaya tinggi baris pil — dan
        # karena itu jatah tinggi kisi di bawahnya — sama di setiap
        # tingkat menu.
        #
        # Lebarnya tidak ikut dipesan. Pil sudah berada di tengah karena
        # diapit dua pegas yang sama besar, dan dua wadah selebar 220 px
        # menuntut 472 px sebelum pil mendapat satu piksel pun: lebih
        # lebar daripada seluruh panel totem pada skala Windows 150%.
        self.wadah_kembali = self._bangun_wadah_kembali()
        baris_petunjuk.addWidget(self.wadah_kembali)
        baris_petunjuk.addStretch(1)
        self.label_petunjuk = LabelPil()
        self.label_petunjuk.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_petunjuk.setWordWrap(True)
        self.label_petunjuk.setMaximumWidth(LEBAR_PIL_MAKS)
        self._set_petunjuk("Sentuh jenis layanan yang Anda butuhkan", "ajak")
        baris_petunjuk.addWidget(self.label_petunjuk)
        baris_petunjuk.addStretch(1)
        penyeimbang = QWidget()
        penyeimbang.setFixedHeight(TINGGI_TOMBOL_KEMBALI)
        penyeimbang.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        baris_petunjuk.addWidget(penyeimbang)
        susunan.addLayout(baris_petunjuk)

        # Kisi pilihan dan layar konfirmasi bertukar tempat lewat satu
        # tumpukan, bukan disembunyikan/dimunculkan satu per satu: dengan
        # tumpukan, hanya satu yang pernah menerima sentuhan pada satu saat.
        self.tumpukan = QStackedWidget()
        # Expanding: jatah stretch tidak boleh ikut sizeHint halaman yang
        # mengerut saat kartu dibongkar. Tanpa ini, kisi kehilangan tinggi
        # setiap kali menu berganti, dan kartu baru lahir sebagai pil pipih.
        self.tumpukan.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        susunan.addWidget(self.tumpukan, stretch=1)

        self.halaman_pilihan = QWidget()
        # Lebar minimum kisi DIABAIKAN, bukan diteruskan ke jendela.
        #
        # Kartu dipasang dengan ukuran tetap. Diteruskan ke atas, tiga kartu
        # 251 px beserta celahnya menuntut jendela selebar 951 px, sehingga
        # totem pada skala Windows 125% (864 px) dan 150% (720 px) terdorong
        # keluar layar di tepi kanan. Dan karena jendelanya tidak pernah bisa
        # menyempit, kunci ukuran kartu pun tidak pernah batal: kisi tidak
        # sekali pun dihitung ulang untuk lebar yang sebenarnya.
        #
        # Diabaikan, jendela boleh menyempit, peristiwa Resize sampai ke
        # `eventFilter`, dan kolom serta kartunya dihitung ulang dari lebar
        # yang benar-benar ada.
        self.halaman_pilihan.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
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
        self.halaman_hasil = self._bangun_halaman_hasil()
        self.tumpukan.addWidget(self.halaman_hasil)

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

        self.label_konfirmasi_layanan = LabelPil()
        self.label_konfirmasi_layanan.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.label_konfirmasi_layanan.setWordWrap(True)
        self.label_konfirmasi_layanan.setStyleSheet(
            f"color: {KIOS_JUDUL}; font-size: 54px; font-weight: 800;"
        )
        # Nama layanan yang berupa satu kata panjang tidak bisa dibungkus,
        # dan pada totem berskala 200% kata itu beserta kotak kodenya bisa
        # lebih lebar daripada panelnya. Hurufnya yang mengalah.
        self._baris_judul_konfirmasi = baris_judul
        self._siapkan_huruf_menyusut(
            self.label_konfirmasi_layanan,
            dasar=54,
            tebal=800,
            tepi=0,
            per_kata=True,
            ruang=self._ruang_nama_konfirmasi,
        )
        # Ruangnya berubah bersama halaman, bukan bersama labelnya.
        halaman.installEventFilter(self)
        # Lebar minimum label yang membungkus adalah kata terpanjangnya pada
        # huruf SEKARANG. Diteruskan ke atas, kata itu menahan halaman tetap
        # lebar sebelum hurufnya sempat dipas — dan ruang yang dihitung dari
        # halaman yang tertahan itu pun tidak pernah menyempit. Lebar yang
        # dimintanya diatur `LabelPil`: sebaris selama muat, membungkus di
        # batas kata bila tidak.
        self.label_konfirmasi_layanan.setMinimumWidth(1)
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
        btn_batal.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_batal.setStyleSheet(
            f"QPushButton {{ color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS};"
            " background: #FFFFFF; border: 3px solid #94A3B8;"
            f" border-radius: {RADIUS_KARTU}px;"
            " font-size: 32px; font-weight: 700; }}"
            "QPushButton:hover { background: #F1F5F9; border: 3px solid #64748B; }"
            "QPushButton:pressed { background: #E2E8F0; }"
            "QPushButton:focus { border: 3px solid #94A3B8; outline: none; }"
        )
        self._siapkan_huruf_menyusut(btn_batal, dasar=32, tebal=700)
        btn_batal.clicked.connect(self._batal_konfirmasi)
        _bayangan(btn_batal, 18, 6, 35)
        baris_tombol.addWidget(btn_batal, stretch=2)

        btn_konfirmasi = tombol("YA, AMBIL NOMOR")
        btn_konfirmasi.setMinimumHeight(TINGGI_TOMBOL_KONFIRMASI_MIN)
        btn_konfirmasi.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_konfirmasi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_konfirmasi.setStyleSheet(
            f"QPushButton {{ color: white; background: {KIOS_SUKSES};"
            f" border: none; border-radius: {RADIUS_KARTU}px;"
            " font-size: 36px; font-weight: 800; }}"
            f"QPushButton:hover {{ background: {KIOS_SUKSES_TEKAN}; }}"
            "QPushButton:pressed { background: #065F46; }"
            f"QPushButton:focus {{ background: {KIOS_SUKSES}; border: none;"
            " outline: none; }"
        )
        self._siapkan_huruf_menyusut(btn_konfirmasi, dasar=36, tebal=800)
        btn_konfirmasi.clicked.connect(self._konfirmasi_ambil)
        _bayangan(btn_konfirmasi, 28, 10, 95)
        # Tombol yang menerbitkan nomor mendapat jatah lebih lebar. Pada
        # layar sentuh, lebar adalah bagian dari seberapa jelas sebuah
        # tombol menawarkan diri untuk ditekan.
        baris_tombol.addWidget(btn_konfirmasi, stretch=3)
        self._tombol_konfirmasi = (btn_batal, btn_konfirmasi)

        # Tombolnya diberi jatah dua kali lipat label di atasnya: keduanya
        # yang benar-benar disentuh, jadi keduanya yang paling berhak atas
        # ruang lebih begitu panel lebih lapang daripada jendela pengembang.
        susunan.addLayout(baris_tombol, stretch=2)
        return halaman

    def _siapkan_huruf_menyusut(
        self,
        widget: QWidget,
        *,
        dasar: int,
        tebal: int,
        renggang: int = 0,
        tepi: int = TEPI_TULISAN_KONFIRMASI,
        per_kata: bool = False,
        ruang=None,
    ) -> None:
        """
        Lebar widget bertulisan sebaris mengikuti panel, bukan tulisannya.

        Gaya yang baru dipasang dijadikan templat yang ukuran hurufnya bisa
        diganti, dan lebar minimum dari tulisannya diabaikan: widget yang
        menuntut lebar tulisannya sendiri mendorong seluruh halaman keluar
        layar totem pada skala Windows 150% ke atas. Yang mengalah adalah
        hurufnya — lihat `_muatkan_huruf`.

        Dipanggil lagi setiap kali gayanya diganti, sebab templat lama
        membawa warna lama.

        `per_kata` untuk label yang membungkus: yang harus muat adalah kata
        terpanjangnya, sebab label yang membungkus tidak bisa memotong satu
        kata dan lebar kata itulah lebar minimumnya.

        `ruang` untuk label yang membungkus: fungsi yang mengembalikan lebar
        yang tersedia baginya, dihitung dari susunan di sekitarnya. Lebar
        labelnya sendiri tidak bisa dipakai. Label yang membungkus meminta
        lebar sempit; huruf yang disusutkan agar muat di lebar itu membuat
        permintaannya makin sempit lagi, dan lingkaran itu baru berhenti di
        batas bawah — nama layanan 16 px pada layar yang lapang. Widget
        dengan `ruang` tidak disentuh kebijakan lebarnya; lebar minimum dan
        lebar yang dimintanya diurus pemanggilnya — lihat nama layanan di
        `_bangun_halaman_konfirmasi`.
        """
        templat = widget.styleSheet().replace(
            f"font-size: {dasar}px", "font-size: @HURUF@px"
        )
        sudut = re.search(r"border-radius: (\d+)px", templat)
        widget.setProperty("sudutDasar", int(sudut.group(1)) if sudut else 0)
        if sudut:
            templat = templat.replace(sudut.group(0), "border-radius: @SUDUT@px", 1)
        widget.setProperty("templatGaya", templat)
        widget.setProperty("hurufDasar", dasar)
        widget.setProperty("tebalHuruf", tebal)
        widget.setProperty("renggangHuruf", renggang)
        widget.setProperty("tepiTulisan", tepi)
        widget.setProperty("hurufSekarang", dasar)
        widget.setProperty("perKata", per_kata)
        if ruang is None:
            kebijakan = widget.sizePolicy()
            kebijakan.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
            widget.setSizePolicy(kebijakan)
        else:
            self._ruang_huruf[id(widget)] = ruang
        widget.installEventFilter(self)
        if widget not in self._huruf_menyusut:
            self._huruf_menyusut.append(widget)

    @staticmethod
    def _lebar_tulisan(metrik: QFontMetrics, widget: QWidget) -> int:
        """Lebar yang harus muat: seluruh tulisan, atau kata terpanjangnya."""
        teks = widget.text()
        if widget.property("perKata"):
            return max((metrik.horizontalAdvance(kata) for kata in teks.split()), default=0)
        return metrik.horizontalAdvance(teks)

    def _muatkan_huruf(self, widget: QWidget) -> None:
        """Pas huruf widget ke ruangnya, lalu perbarui lebar yang dimintanya."""
        self._pas_huruf(widget)
        if isinstance(widget, LabelPil):
            # Lebar yang diminta mengikuti huruf yang baru dipas: permintaan
            # dari huruf lama membuat labelnya membungkus padahal muat, atau
            # meminta lebih daripada ruang yang ada.
            widget.ensurePolished()
            widget.setel_lebar_sebaris(
                widget.fontMetrics().horizontalAdvance(widget.text()) + KELONGGARAN_PIL
            )

    def _tulis_gaya_menyusut(self, widget: QWidget, ukuran: int) -> None:
        """
        Tulis gaya dari templatnya: ukuran huruf, dan sudut yang muat.

        Qt tidak menggambar sudut yang lebih besar daripada separuh tinggi
        widgetnya. Ia jatuh ke gambar tombol bawaan — sudut siku, dan tepi
        dalam bawaan yang lebih lebar, yang memotong tulisan di kedua
        ujungnya. Tombol konfirmasi setinggi 46 px pada totem berskala 200%
        mengalami keduanya dengan sudut 26 px. Sudutnya karena itu dijepit
        ke separuh tinggi yang sebenarnya, persis seperti kartu layanan.

        Gaya hanya ditulis ulang bila hasilnya memang berbeda: tinggi yang
        berubah tanpa ukuran huruf ikut berubah tetap memperbarui sudutnya.
        """
        widget.setProperty("hurufSekarang", ukuran)
        gaya = widget.property("templatGaya").replace("@HURUF@", str(ukuran))
        sudut = int(widget.property("sudutDasar") or 0)
        if sudut:
            if widget.height() > 1:
                sudut = max(0, min(sudut, widget.height() // 2 - 1))
            gaya = gaya.replace("@SUDUT@", str(sudut))
        if gaya != widget.styleSheet():
            widget.setStyleSheet(gaya)

    def _pas_huruf(self, widget: QWidget) -> None:
        """
        Kecilkan huruf bila widgetnya lebih sempit daripada tulisannya.

        Pada totem berskala 150%, "BATAL, PILIH LAGI" hanya mendapat sekitar
        250 px. Huruf yang sedikit lebih kecil masih terbaca; tulisan yang
        terpotong di kedua ujungnya tidak.

        Jarak antarhuruf ikut dihitung. Judul panel direnggangkan 3 px per
        huruf, dan pada 24 huruf itu 70 px yang tidak terlihat oleh
        pengukuran huruf biasa.
        """
        dasar = widget.property("hurufDasar")
        templat = widget.property("templatGaya")
        if not dasar or not templat:
            return
        hitung_ruang = self._ruang_huruf.get(id(widget))
        if hitung_ruang is not None:
            ruang = hitung_ruang()
        elif widget.width() > 1:
            ruang = widget.width() - 2 * int(widget.property("tepiTulisan") or 0)
        else:
            return
        if ruang <= 0:
            return
        font = QFont(widget.font())
        font.setPixelSize(int(dasar))
        font.setWeight(QFont.Weight(int(widget.property("tebalHuruf") or 700)))
        font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            float(widget.property("renggangHuruf") or 0),
        )
        butuh = self._lebar_tulisan(QFontMetrics(font), widget)
        ukuran = int(dasar)
        if butuh > ruang > 0:
            ukuran = max(HURUF_KONFIRMASI_MIN, int(dasar * ruang / butuh))
        self._tulis_gaya_menyusut(widget, ukuran)
        # Taksiran di atas memakai SALINAN huruf. Pembulatan, pantulan
        # tepi huruf, dan jarak antarhuruf dari stylesheet dapat membuatnya
        # meleset beberapa piksel — pada huruf cadangan offscreen, judul
        # panel di skala 200% meleset 12 px. Hasilnya karena itu diperiksa
        # ulang dengan huruf yang benar-benar terpasang, dan diturunkan satu
        # piksel demi satu piksel sampai muat atau sampai batas bawahnya.
        while ukuran > HURUF_KONFIRMASI_MIN:
            widget.ensurePolished()
            if self._lebar_tulisan(widget.fontMetrics(), widget) <= ruang:
                break
            ukuran -= 1
            self._tulis_gaya_menyusut(widget, ukuran)

    def _ruang_nama_konfirmasi(self) -> int:
        """
        Lebar yang tersedia bagi nama layanan di baris judul konfirmasi.

        Lebar halaman konfirmasi dikurangi tepinya, kotak kode di sebelah
        nama, dan dua celah baris itu. Tumpukan menata halaman yang sedang
        tersembunyi dengan ukuran yang sama, jadi angkanya sudah benar
        sebelum pengunjung menyentuh kartu mana pun.
        """
        halaman = getattr(self, "halaman_konfirmasi", None)
        if halaman is None or halaman.width() <= 1:
            return 0
        tepi = halaman.layout().contentsMargins()
        celah = max(0, self._baris_judul_konfirmasi.spacing())
        return (
            halaman.width()
            - tepi.left()
            - tepi.right()
            - SISI_KOTAK_KONFIRMASI
            - 2 * celah
        )

    def _bangun_halaman_hasil(self) -> QWidget:
        """Kartu nomor di pita tengah totem, setinggi dada, siap difoto."""
        halaman = QFrame()
        halaman.setObjectName("halamanHasilKios")
        susunan = QVBoxLayout(halaman)
        susunan.setContentsMargins(24, 8, 24, 8)
        susunan.setSpacing(4)
        susunan.addStretch(1)

        self.label_hasil_judul = QLabel("NOMOR ANDA")
        self.label_hasil_nomor = QLabel("")
        self.label_hasil_layanan = QLabel("")
        self.label_hasil_sisa = QLabel("")
        for label, ukuran, tebal in (
            (self.label_hasil_judul, 20, 800),
            (self.label_hasil_nomor, 84, 800),
            (self.label_hasil_layanan, 28, 700),
            (self.label_hasil_sisa, 22, 600),
        ):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setMinimumSize(1, 1)
            label.setStyleSheet(
                f"color: {KIOS_JUDUL}; background: transparent;"
                f" font-size: {ukuran}px; font-weight: {tebal};"
            )
            susunan.addWidget(label)
        susunan.addStretch(1)
        return halaman

    def _info_papan(self, teks: str | None = None, *, berkas=None) -> None:
        """Anjungan biasa mengganti panel iklan; totem membiarkan iklan jalan."""
        if self.totem:
            return
        self.papan.tampilkan_info_kios(teks, berkas=berkas)

    def _gaya_ajakan(self, *, sukses: bool) -> None:
        """
        Judul panel: ajakan biasa, atau kabar nomor yang baru terbit.

        Hurufnya boleh menyusut. Judul sebaris ini dahulu penahan terakhir
        lebar halaman: "AMBIL NOMOR ANTRIAN ANDA" berhuruf 30 px menuntut
        sekitar 530 px, dan totem pada skala Windows 200% hanya menyisakan
        476 px di dalam panelnya — halamannya terdorong keluar layar.
        """
        if sukses:
            dasar, renggang = 38, 2
            self.label_ajakan.setStyleSheet(
                f"color: {KIOS_SUKSES}; font-size: 38px; font-weight: 800;"
                " letter-spacing: 2px;"
            )
        else:
            dasar, renggang = 30, 3
            self.label_ajakan.setStyleSheet(
                f"color: {KIOS_JUDUL}; font-size: 30px; font-weight: 800;"
                " letter-spacing: 3px;"
            )
        self._siapkan_huruf_menyusut(
            self.label_ajakan, dasar=dasar, tebal=800, renggang=renggang, tepi=4
        )
        self._muatkan_huruf(self.label_ajakan)

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

        Lebar sebarisnya dihitung dari kalimatnya sendiri. QLabel yang
        boleh membungkus lebih suka melipat teksnya menjadi kotak hampir
        bujur sangkar daripada memanjang, sehingga tanpa perhitungan ini
        ajakan sesingkat "Sentuh jenis layanan yang Anda butuhkan" pun
        tampil dua baris di tengah panel yang masih sangat lapang. Lebar
        itu diminta, bukan dipaksakan — lihat `LabelPil`.
        """
        self.label_petunjuk.setText(teks)
        font = QFont(self.font())
        font.setWeight(QFont.Weight(600))
        font.setPixelSize(UKURAN_PIL)
        lebar = QFontMetrics(font).horizontalAdvance(teks) + 2 * PADDING_PIL + KELONGGARAN_PIL
        self.label_petunjuk.setel_lebar_sebaris(min(LEBAR_PIL_MAKS, lebar))
        self._gaya_petunjuk(nada)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Segarkan papan nomor, bentuk panel informasi, dan jenis layanan."""
        self.papan.muat_ulang()
        self._rasio_info = self._baca_rasio_info()
        if not self.totem:
            urutan = self._baca_urutan_panel()
            if urutan != self._urutan_panel:
                self._urutan_panel = urutan
                self._terapkan_urutan_panel()

        try:
            self.pendaftaran_dibuka = self.queue.pendaftaran_dibuka()
            data = self.master.list_categories(only_active=True)
        except Exception as exc:  # noqa: BLE001 - batas UI kios, tanpa dialog
            self._tampilkan_kesalahan(exc)
            return

        self.kategori = data or []
        self._pangkas_jalur()
        self._susun_tombol()
        self._perbarui_jeda()

    def _baca_rasio_info(self) -> float:
        """
        Perbandingan panel informasi dari pengaturan, atau nilai bawaan.

        Angka rusak diperlakukan seperti tidak ada. Nilai di database
        boleh berasal dari versi lama atau suntingan langsung, dan layar
        publik tidak boleh gagal terbuka karenanya.
        """
        try:
            rasio = float(self.settings.get("kiosk.info_ratio"))
        except Exception:  # noqa: BLE001 - layar publik tidak boleh mati di sini
            logger.warning(
                "Perbandingan panel informasi tidak terbaca; memakai %s",
                RASIO_INFO_BAWAAN,
                exc_info=True,
            )
            return RASIO_INFO_BAWAAN
        if not RASIO_INFO_MIN <= rasio <= RASIO_INFO_MAKS:
            logger.warning(
                "Perbandingan panel informasi %s di luar batas; memakai %s",
                rasio,
                RASIO_INFO_BAWAAN,
            )
            return RASIO_INFO_BAWAAN
        return rasio

    def _sidik_layanan(self, kategori) -> tuple:
        """
        Sidik daftar layanan: yang menentukan tampilan kartu, itu saja.

        `info_text` tidak ikut. Isinya hanya dibaca ketika layanannya
        disentuh — dan memang dibaca ulang setiap kali disentuh — sehingga
        perubahannya tidak perlu menyusun ulang kartu apa pun.
        """
        return tuple(
            (
                baris.id,
                baris.name,
                baris.prefix,
                baris.display_order,
                baris.parent_id,
                baris.punya_anak,
            )
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

        rasio = self._baca_rasio_info()
        if rasio != self._rasio_info:
            logger.info(
                "Bentuk panel informasi berubah (%s -> %s)", self._rasio_info, rasio
            )
            self._rasio_info = rasio
            self._sesuaikan_ukuran_tombol()

        urutan = self._baca_urutan_panel()
        if not self.totem and urutan != self._urutan_panel:
            logger.info(
                "Urutan panel anjungan berubah (%s -> %s)", self._urutan_panel, urutan
            )
            self._urutan_panel = urutan
            self._terapkan_urutan_panel()
            self._sesuaikan_ukuran_tombol()

        if self._sidik_layanan(kategori) == self._sidik_layanan(self.kategori):
            return

        logger.info(
            "Daftar jenis layanan berubah (%d -> %d); kartu anjungan disusun ulang",
            len(self.kategori),
            len(kategori),
        )
        self.kategori = kategori
        self._pangkas_jalur()
        self._susun_tombol()
        # Tombol yang baru dibangun selalu lahir hidup. Tanpa baris ini,
        # kartu yang muncul tepat di tengah jeda pengambilan nomor bisa
        # disentuh padahal jedanya belum habis.
        self._perbarui_jeda()

    # -----------------------------------------------------------------
    # Menu bertingkat
    # -----------------------------------------------------------------

    def _anak_dari(self, induk_id: int | None) -> list:
        """Jenis layanan yang berdiri langsung di bawah `induk_id`."""
        ada = {baris.id for baris in self.kategori}
        return [
            baris
            for baris in self.kategori
            # Anak yang induknya tidak ikut terbaca — induknya baru saja
            # dinonaktifkan, misalnya — naik ke menu utama, bukan hilang.
            # Jenis layanan aktif harus selalu dapat dicapai dari layar.
            if (baris.parent_id if baris.parent_id in ada else None) == induk_id
        ]

    def _daftar_tampil(self) -> list:
        """Isi menu yang sedang dibuka pengunjung."""
        induk = self._jalur[-1].id if self._jalur else None
        return self._anak_dari(induk)

    def _pangkas_jalur(self) -> None:
        """
        Buang langkah jalur yang jenis layanannya sudah tidak ada lagi.

        Admin dapat menonaktifkan atau menghapus sebuah kelompok tepat
        ketika ada pengunjung berdiri di dalamnya. Tanpa pemangkasan,
        `_daftar_tampil()` akan mencari anak dari id yang sudah lenyap dan
        memberi daftar kosong — layar yang benar-benar kosong, tanpa satu
        kartu pun dan tanpa jalan keluar.

        Yang dipakai adalah baris TERBARU dengan id yang sama, bukan baris
        lama yang dipegang jalur: namanya mungkin baru saja diubah admin,
        dan remah jejak harus menyebut nama yang sekarang.
        """
        terbaru = {baris.id: baris for baris in self.kategori}
        jalur: list = []
        for langkah in self._jalur:
            baris = terbaru.get(langkah.id)
            if baris is None or not baris.punya_anak:
                break
            jalur.append(baris)
        if len(jalur) != len(self._jalur):
            logger.info(
                "Jalur menu anjungan dipangkas dari %d ke %d tingkat",
                len(self._jalur),
                len(jalur),
            )
        self._jalur = jalur
        if not self._jalur:
            self._pemulang.stop()

    def _remah(self) -> str:
        """Jalur yang sedang terbuka, untuk pil petunjuk."""
        return " › ".join(langkah.name for langkah in self._jalur)

    def _buka_kelompok(self, layanan) -> None:
        """Masuk ke dalam sebuah kelompok, dan susun ulang kartunya."""
        self._jalur.append(layanan)
        logger.info("Anjungan membuka kelompok %s", layanan.code)
        self._susun_tombol()
        self._perbarui_jeda()
        self._pemulang.start(JEDA_PULANG)
        # Panel papan ikut menampilkan info kelompoknya. Kelompok pun boleh
        # punya keterangan — "Siapkan SPPT dan KTP" pada Konsultasi berlaku
        # bagi seluruh isinya — dan pengunjung membacanya justru pada saat
        # ia sedang memilih di dalamnya.
        self._info_papan(
            layanan.info_text, berkas=media_layanan(layanan.code)
        )
        # Video layanan (Konsultasi 1920×540) merampas tinggi papan
        # sesudah kisi selesai disusun. Tanpa putaran berikutnya, kartu
        # dihitung ulang dari kisi yang sedang mengerut — pil pipih.
        self._jadwalkan_sesuaikan()

    def _kembali(self) -> None:
        """Naik satu tingkat."""
        if not self._jalur:
            return
        self._jalur.pop()
        self._susun_tombol()
        self._perbarui_jeda()
        if self._jalur:
            self._pemulang.start(JEDA_PULANG)
            self._info_papan(
                self._jalur[-1].info_text, berkas=media_layanan(self._jalur[-1].code)
            )
        else:
            self._pemulang.stop()
            self._info_papan(None)
        self._jadwalkan_sesuaikan()

    def _pulang(self) -> None:
        """Kembali ke menu utama, sejauh apa pun pengunjung sudah masuk."""
        self._pemulang.stop()
        if not self._jalur:
            return
        logger.info("Menu anjungan kembali sendiri ke menu utama")
        self._jalur = []
        self._susun_tombol()
        self._perbarui_jeda()
        # Panel papan TIDAK disentuh selama kartu nomor masih tampil di
        # sana. Membebaskannya di sini akan menghapus nomor yang baru
        # terbit dari layar, tepat ketika pemiliknya sedang membacanya
        # atau memfotonya. Yang membebaskannya nanti `_bersihkan_hasil`.
        if not self._penghapus_hasil.isActive():
            self._info_papan(None)
        self._jadwalkan_sesuaikan()

    def _kolom_maks(self) -> int:
        """
        Banyaknya kolom yang muat berjajar pada lebar panel sekarang.

        Di menu utama: sebanyak yang muat selama tiap kartu masih selebar
        `LEBAR_TOMBOL_MIN` — lima layanan tingkat teratas tetap satu
        baris, karena dua baris di sini memendekkan kartu jadi pita.

        Di dalam kelompok tiga kolom, sama dengan menu utama — kecuali
        tiga kolom memang tidak muat. Acuan 480 px membuat jendela biasa
        hanya "muat" dua kolom, lalu enam kartu menjadi 3×2 setinggi 23 px
        — pil pipih di tengah panel.
        """
        lebar_area = self.halaman_pilihan.width() - 2 * MARGIN_KISI
        if lebar_area <= 0:
            # Belum pernah ditata; jangan menebak dari angka yang belum ada.
            return KOLOM_BAWAAN
        muat = (lebar_area + CELAH_TOMBOL) // (LEBAR_TOMBOL_MIN + CELAH_TOMBOL)
        if self._jalur:
            # Tiga kolom, sama dengan menu utama. Acuan 480 px membuat
            # jendela 1280 hanya "muat" dua kolom, lalu enam kartu menjadi
            # 3×2 setinggi 23 px — pil pipih di tengah panel.
            #
            # Tetapi tidak pernah lebih daripada yang muat. Totem pada skala
            # Windows 150% hanya selebar 720 px: tiga kartu selebar
            # minimumnya beserta celahnya menuntut 640 px dari 624 yang ada,
            # dan kartu ketiga terpotong di tepi kanan layar.
            return max(1, min(KOLOM_BAWAAN, muat))
        return max(1, min(KOLOM_MAKS, muat))

    def _susun_tombol(self) -> None:
        if self._sedang_menyusun:
            return
        self._sedang_menyusun = True
        try:
            self._isi_kisi_tombol()
        finally:
            self._sedang_menyusun = False

    def _isi_kisi_tombol(self) -> None:
        # Lepas rujukan ke kartu KEMBALI di kisi sebelum kartunya dihapus.
        self._pasang_cadangan_kembali()
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
        self.kartu_kisi = []

        tampil = self._daftar_tampil()

        if not tampil and not self._jalur:
            # Tanpa kartu, tidak ada yang bisa dihitung; panelnya kembali
            # bebas seperti sebelum tinggi tetap ini ada. setFixedHeight
            # menulis batas bawah DAN batas atas sekaligus, jadi keduanya
            # yang harus dilepas.
            self.panel_ambil.setMinimumHeight(TINGGI_PANEL_AMBIL_MIN)
            self.panel_ambil.setMaximumHeight(TINGGI_TAK_TERBATAS)
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
        kartu: list = list(tampil)
        tombol_kisi = [self._bangun_tombol_layanan(layanan) for layanan in kartu]
        for layanan, btn in zip(kartu, tombol_kisi):
            if not layanan.punya_anak:
                self.tombol_layanan.append(btn)
            self.kartu_kisi.append(btn)
        if self._jalur:
            tombol_kisi.append(self._bangun_kartu_kembali())
            self.kartu_kisi.append(self.tombol_kembali)

        self._kolom_terpakai = self._kolom_maks()
        pola = baris_kisi(len(tombol_kisi), self._kolom_terpakai)
        self.kisi.setSpacing(self._celah_baris(len(pola)))
        self.kisi.addStretch(1)
        awal = 0
        for banyak in pola:
            baris = QHBoxLayout()
            baris.setSpacing(CELAH_TOMBOL)
            baris.addStretch(1)
            for btn in tombol_kisi[awal : awal + banyak]:
                baris.addWidget(btn)
            baris.addStretch(1)
            self.kisi.addLayout(baris)
            awal += banyak
        self.kisi.addStretch(1)
        self._sesuaikan_ukuran_tombol()

    def _bangun_kartu(
        self,
        *,
        tanda: str,
        nama_teks: str,
        latar: str,
        latar_hover: str,
        latar_tekan: str,
        warna_teks: str = DISPLAY_KIOS_TOMBOL_TEKS,
        latar_kotak: str = KIOS_KOTAK_HURUF,
        hanya_nama: bool = False,
        punya_submenu: bool = False,
        object_name: str = "kartuKios",
    ):
        """
        Kartu sentuh anjungan: layanan, kelompok, dan kembali sekaligus.

        Ketiganya berbagi satu bentuk karena ketiganya disentuh dengan cara
        yang sama, dan hanya warnanya yang membedakan apa yang terjadi
        sesudahnya. Warna tulisan ikut dititipkan ke kartunya sendiri —
        `_warnai_tulisan_tombol` menyusun ulang huruf setiap kali kartunya
        berubah ukuran, dan tanpa titipan itu ia akan memutihkan kembali
        tulisan kartu kembali yang berlatar abu muda.
        """
        # Tanpa variant="primary": selector global
        # QPushButton[variant="primary"]:hover lebih spesifik daripada
        # stylesheet kartu, dan setelah sentuhan pertama kartu toska
        # anjungan berubah jadi tombol biru berbingkai milik layar admin.
        btn = tombol("")
        btn.setObjectName(object_name)
        # Anjungan disentuh, bukan di-Tab. Fokus keyboard membuat Qt
        # menyerahkan sorotan native ke kartu yang baru lahir begitu
        # tombol KEMBALI disembunyikan di tengah klik — dan kartu itu
        # tampak "berubah" tanpa pengunjung menyentuhnya.
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setMinimumSize(LEBAR_TOMBOL_MIN, TINGGI_TOMBOL_MIN)
        btn.setMaximumSize(LEBAR_TOMBOL_MAKS, TINGGI_TOMBOL_MAKS)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setProperty("warnaTeksKartu", warna_teks)
        btn.setProperty("latarKartu", latar)
        btn.setProperty("latarHoverKartu", latar_hover)
        btn.setProperty("latarTekanKartu", latar_tekan)
        btn.setProperty("latarKotakKartu", latar_kotak)
        btn.setProperty("hanyaNamaKartu", hanya_nama)
        btn.setProperty("punyaSubmenuKartu", punya_submenu)
        btn.setProperty("radiusKartu", RADIUS_KARTU)
        btn.setStyleSheet(
            self._stylesheet_kartu(
                object_name,
                warna_teks=warna_teks,
                latar=latar,
                latar_hover=latar_hover,
                latar_tekan=latar_tekan,
                radius=RADIUS_KARTU,
            )
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

        isi.addStretch(1)

        baris_nama = QHBoxLayout()
        baris_nama.setSpacing(12)
        baris_nama.addStretch(1)

        nama = QLabel(nama_teks)
        nama.setObjectName("namaLayanan")
        nama.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nama.setWordWrap(True)
        nama.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        nama.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        baris_nama.addWidget(nama)

        if punya_submenu:
            # Logo ">", bukan kotak huruf A/B/C. Hanya kartu yang benar-
            # benar membuka daftar di dalamnya yang memakainya.
            tanda_l = QLabel(tanda or TANDA_KELOMPOK)
            tanda_l.setObjectName("tandaSubmenu")
            tanda_l.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            tanda_l.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
            baris_nama.addWidget(tanda_l)

        baris_nama.addStretch(1)
        isi.addLayout(baris_nama)
        isi.addStretch(1)

        self._warnai_tulisan_tombol(btn, aktif=True)
        btn.installEventFilter(self)
        return btn

    @staticmethod
    def _stylesheet_kartu(
        object_name: str,
        *,
        warna_teks: str,
        latar: str,
        latar_hover: str,
        latar_tekan: str,
        radius: int,
    ) -> str:
        """
        Gaya kartu, termasuk warna label di dalamnya.

        Stylesheet global `QWidget { color }` mengalahkan `color` pada
        QPushButton. Tanpa selector `QLabel`, tulisan KEMBALI kembali
        gelap di atas latar abu — persis yang terlihat di anjungan.
        """
        return (
            f"QPushButton#{object_name} {{ color: {warna_teks};"
            f" background: {latar};"
            f" border: none; border-radius: {radius}px; }}"
            f"QPushButton#{object_name} QLabel {{ color: {warna_teks}; }}"
            f"QPushButton#{object_name}:hover {{ background: {latar_hover}; }}"
            f"QPushButton#{object_name}:pressed {{ background: {latar_tekan}; }}"
            f"QPushButton#{object_name}:focus {{ background: {latar};"
            " border: none; outline: none; }"
            f"QPushButton#{object_name}:disabled {{ background: {DISPLAY_KIOS_TOMBOL_MATI};"
            f" color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS}; }}"
            f"QPushButton#{object_name}:disabled QLabel {{"
            f" color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS}; }}"
        )

    @staticmethod
    def _radius_kartu(tinggi: int) -> int:
        """Sudut mengikuti tinggi, supaya kartu pendek bukan kapsul pipih."""
        return min(RADIUS_KARTU, max(8, tinggi * 22 // 100))

    def _bangun_tombol_layanan(self, layanan):
        """
        Satu kartu jenis layanan — atau kartu kelompok, bila ia punya isi.

        Prefix tiket (A, B, PB) tidak dipajang di kartu: pengunjung
        membacanya sebagai nomor yang akan diterima, dan yang perlu
        dipilih adalah NAMA layanannya. Kartu kelompok mendapat tanda ">"
        di samping nama, supaya kentara bahwa sentuhan membuka daftar,
        bukan menerbitkan nomor.
        """
        kelompok = layanan.punya_anak
        btn = self._bangun_kartu(
            tanda=TANDA_KELOMPOK if kelompok else "",
            nama_teks=layanan.name,
            latar=DISPLAY_KIOS_KELOMPOK if kelompok else DISPLAY_KIOS_TOMBOL,
            latar_hover=(
                DISPLAY_KIOS_KELOMPOK_HOVER if kelompok else DISPLAY_KIOS_TOMBOL_HOVER
            ),
            latar_tekan=(
                DISPLAY_KIOS_KELOMPOK_TEKAN if kelompok else DISPLAY_KIOS_TOMBOL_TEKAN
            ),
            hanya_nama=True,
            punya_submenu=kelompok,
        )
        btn.clicked.connect(lambda _, layanan=layanan: self._pilih_layanan(layanan))
        return btn

    def _bangun_kartu_kembali(self):
        """Kartu KEMBALI seukuran submenu, abu, supaya tidak tertukar sebagai layanan."""
        btn = self._bangun_kartu(
            tanda="",
            nama_teks="KEMBALI",
            latar=DISPLAY_KIOS_KEMBALI,
            latar_hover=DISPLAY_KIOS_KEMBALI_HOVER,
            latar_tekan=DISPLAY_KIOS_KEMBALI_TEKAN,
            warna_teks=DISPLAY_KIOS_KEMBALI_TEKS,
            hanya_nama=True,
            object_name="tombolKembaliKios",
        )
        btn.clicked.connect(lambda _: self._kembali())
        self.tombol_kembali = btn
        tampak = not self._menunggu_konfirmasi
        btn.setVisible(tampak)
        return btn

    def _pasang_cadangan_kembali(self) -> None:
        """Jangan memegang kartu KEMBALI yang akan dihapus bersama kisi."""
        if (
            getattr(self, "_tombol_kembali_cadangan", None) is not None
            and self.tombol_kembali is not self._tombol_kembali_cadangan
        ):
            self.tombol_kembali = self._tombol_kembali_cadangan
        if getattr(self, "_tombol_kembali_cadangan", None) is not None:
            self._tombol_kembali_cadangan.setVisible(False)

    def _bangun_wadah_kembali(self) -> QWidget:
        """
        Cadangan lebar di ujung kiri baris pil, supaya pil tetap di tengah.

        Tombol KEMBALI yang disentuh pengunjung adalah kartu di kisi.
        Wadah ini kosong: ia hanya memesan tempat selebar yang sama di
        kanan dan kiri pil.
        """
        wadah = QWidget()
        # Tinggi saja: lihat catatan baris pil di `_bangun_panel_ambil`.
        wadah.setFixedHeight(TINGGI_TOMBOL_KEMBALI)
        self._tombol_kembali_cadangan = tombol(f"{TANDA_KEMBALI}  KEMBALI")
        self._tombol_kembali_cadangan.setObjectName("tombolKembaliKios")
        self._tombol_kembali_cadangan.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tombol_kembali_cadangan.setVisible(False)
        self._tombol_kembali_cadangan.setParent(self)
        self.tombol_kembali = self._tombol_kembali_cadangan
        return wadah

    def _perbarui_tombol_kembali(self) -> None:
        """
        Tombol kembali hanya ada saat memang ada yang bisa ditinggalkan.

        Layar konfirmasi ikut menyembunyikannya. Kartu kembali berdiri di
        kisi halaman pilihan; saat tumpukan menampilkan konfirmasi, kartu
        itu tidak kelihatan, tetapi tetap disembunyikan supaya tes dan
        klik sisa tidak mengenai tombol yang sudah tidak berlaku.
        """
        tampak = bool(self._jalur) and not self._menunggu_konfirmasi
        if self.tombol_kembali is self._tombol_kembali_cadangan:
            self.tombol_kembali.setVisible(False)
            return
        if not tampak:
            self.tombol_kembali.setDown(False)
            self.tombol_kembali.clearFocus()
            self.tombol_kembali.setAttribute(
                Qt.WidgetAttribute.WA_UnderMouse, False
            )
        self.tombol_kembali.setVisible(tampak)

    def _sesuaikan_ukuran_tombol(self) -> None:
        """
        Hitung ukuran kartu dari ruang yang benar-benar ada.

        Tanpa jepitan lebar, kebijakan Expanding membuat kartu meregang
        selebar panel — pada 1080p itu batang ~600×120, bukan kartu yang
        mengundang sentuhan. Tetapi jepitannya TIDAK tetap: batasnya
        melonggar ketika kolomnya sedikit (lihat PEMBESAR_KARTU), supaya
        kantor berlayanan satu atau dua tidak menyisakan separuh panel
        kosong di kiri dan kanan kartunya.

        Tingginya mengikuti lebar, tetapi tidak pernah menyerahkan jatah
        baris yang sudah dipesan: kartu yang berjajar lebih banyak di
        dalam kelompok menyempit lebarnya saja, tidak ikut memendek.

        Baris terakhir yang tidak penuh — 3+2 pada lima layanan — kartunya
        dilebarkan sampai barisnya sama panjang dengan baris di atasnya.
        Dua kartu seukuran kartu di baris atas menyisakan lubang di kanan
        dan kiri, dan lubang itu terbaca sebagai ada yang hilang.
        """
        if not self.kartu_kisi or self._sedang_menyesuaikan:
            return
        self._sedang_menyesuaikan = True
        try:
            self._pasang_ukuran_tombol()
        finally:
            self._sedang_menyesuaikan = False

    def _jadwalkan_sesuaikan(self) -> None:
        """Pasang ulang ukuran kunci setelah video selesai merampas tata letak."""
        QTimer.singleShot(0, self._sesuaikan_ukuran_tombol)

    def _kunci_masih_berlaku(self) -> bool:
        """
        Kunci ukuran hanya batal jika jendela benar-benar berubah.

        Selisih 1–2 piksel, atau kisi yang sempat mengerut karena video,
        bukan alasan menghitung ulang. Ambang 80 px: itu baru setara
        pengunjung mengubah ukuran jendela, bukan ganti menu.
        """
        if self._ukuran_kartu_menu is None:
            return False
        lebar_sekarang = self.halaman_pilihan.width()
        if (
            self._lebar_halaman_kunci is not None
            and lebar_sekarang > 400
            and abs(lebar_sekarang - self._lebar_halaman_kunci) > 80
        ):
            return False
        if (
            self._tinggi_jendela_kunci is not None
            and self.height() > 400
            and abs(self.height() - self._tinggi_jendela_kunci) > 80
        ):
            return False
        return True

    def _reset_kunci_ukuran(self) -> None:
        self._ukuran_kartu_menu = None
        self._tinggi_panel_menu = None
        self._tinggi_jendela_kunci = None
        self._lebar_halaman_kunci = None

    def _kunci_jendela(self) -> tuple[int, int]:
        """Ukuran jendela dibulatkan, supaya 1919×1079 masih sama dengan 1920×1080."""
        return (self.width() // 8 * 8, self.height() // 8 * 8)

    def _pulihkan_kunci_jendela(self) -> bool:
        """Pakai ukuran kartu yang pernah dihitung untuk jendela sebesar ini."""
        simpan = self._kunci_per_jendela.get(self._kunci_jendela())
        if simpan is None:
            return False
        lebar, tinggi, panel = simpan
        self._ukuran_kartu_menu = (lebar, tinggi)
        self._tinggi_panel_menu = panel
        self._tinggi_jendela_kunci = self.height()
        self._lebar_halaman_kunci = self.halaman_pilihan.width()
        return True

    def _geometri_siap(self) -> bool:
        """Jangan menghitung kartu dari jendela yang sedang transisi F11."""
        return (
            self.isVisible()
            and self.width() >= 400
            and self.height() >= 400
            and self.halaman_pilihan.width() >= 400
        )

    def _sesuaikan_setelah_ubah_jendela(self) -> None:
        """Hitung kartu sekali, sesudah putaran tata letak F11 selesai."""
        if self._sedang_menyusun or self._sedang_menyesuaikan:
            self._penyesuai_jendela.start()
            return
        if not self.kartu_kisi or not self._geometri_siap():
            return
        if self._kolom_maks() != self._kolom_terpakai:
            if not self._jalur:
                self._reset_kunci_ukuran()
            self._susun_tombol()
            return
        if not self._kunci_masih_berlaku():
            if not self._pulihkan_kunci_jendela():
                self._reset_kunci_ukuran()
        self._sesuaikan_ukuran_tombol()

    def _pasang_ukuran_tombol(self) -> None:
        pola = baris_kisi(len(self.kartu_kisi), self._kolom_terpakai)
        n_kolom, n_baris = max(pola), len(pola)

        if self._ukuran_kartu_menu is not None and not self._kunci_masih_berlaku():
            if self._geometri_siap() and not self._pulihkan_kunci_jendela():
                self._reset_kunci_ukuran()

        if self._ukuran_kartu_menu is None and self._geometri_siap():
            self._pulihkan_kunci_jendela()

        # Setelah pengunjung melihat menu utama, ukuran itu dikunci.
        # Menghitung ulang dari geometri sesaat (kisi kosong, video
        # Konsultasi 1920×540, setFixedHeight) menghasilkan pil pipih.
        #
        # Submenu tetap memakai jalur kelompok meski kunci menu ditolak
        # (jendela 720p: tinggi kartu sudah ≤ 120). Tanpa itu lima anak
        # dihitung sebagai dua baris menu utama: celah 50 px, kartu
        # ~26 px, pil di tengah panel.
        if self._jalur:
            if self._ukuran_kartu_menu is not None:
                lebar, tinggi = self._ukuran_kartu_menu
            else:
                if not self._geometri_siap():
                    return
                lebar = self._lebar_kartu_kolom(n_kolom)
                if lebar <= 0:
                    return
                tinggi = min(
                    TINGGI_TOMBOL_MAKS,
                    max(1, round(lebar * RASIO_TINGGI_TOMBOL)),
                )
            self._pasang_ukuran_kelompok(pola, n_kolom, n_baris, lebar, tinggi)
            return

        if self._ukuran_kartu_menu is not None:
            lebar, tinggi = self._ukuran_kartu_menu
            if self._tinggi_panel_menu:
                self.panel_ambil.setFixedHeight(self._tinggi_panel_menu)
            self._pasang_ukuran_tetap(pola, n_kolom, lebar, tinggi)
            return

        if not self._geometri_siap():
            return

        lebar_area = self.halaman_pilihan.width() - 2 * MARGIN_KISI
        tinggi_area = self.halaman_pilihan.height() - 2 * MARGIN_KISI

        if lebar_area <= 0:
            return

        pembesar = PEMBESAR_KARTU.get(n_kolom, 1.0)
        lebar_maks = round(LEBAR_TOMBOL_MAKS * pembesar)
        tinggi_maks = round(TINGGI_TOMBOL_MAKS * pembesar)

        lebar = (lebar_area - CELAH_TOMBOL * (n_kolom - 1)) // n_kolom
        lebar = min(lebar_maks, max(LEBAR_TOMBOL_MIN, lebar))
        tinggi = round(lebar * RASIO_TINGGI_TOMBOL)
        tinggi = min(tinggi_maks, max(TINGGI_TOMBOL_MIN, tinggi))
        # Tinggi kisi diambil dari yang BARU saja dipasang, bukan dari
        # `halaman_pilihan` yang masih memegang ukuran lama. Geometri
        # Qt baru menyusul pada putaran tata letak berikutnya, dan
        # menunggu putaran itu berarti satu gambar pertama dengan
        # kartu yang terpotong tepi bawahnya.
        tinggi_isi = self._setel_tinggi_panel(n_baris, tinggi_maks)
        if tinggi_isi > 0:
            tinggi_area = tinggi_isi - 2 * MARGIN_KISI
        elif tinggi_area <= 0:
            return
        tinggi_baris = (tinggi_area - CELAH_TOMBOL * (n_baris - 1)) // n_baris
        if tinggi_baris > 0:
            # Kartu yang menyempit karena kolomnya banyak boleh
            # MEMANJANG mengisi jatah barisnya.
            #
            # Tinggi kartu memang mengikuti lebarnya, tetapi ruang
            # tegak yang dipesan `_setel_tinggi_panel` dihitung dari
            # tinggi kartu TERBESAR. Enam kartu berjajar di dalam
            # sebuah kelompok karena itu menyisakan puluhan piksel
            # jatah baris yang tidak dipakai siapa-siapa — dan
            # kartunya menyusut pada KEDUA sisi sekaligus, tampak
            # kerdil di bawah papan yang lapang, padahal yang benar
            # menyempit hanyalah lebarnya. Menu utama tidak berubah
            # olehnya: kartunya sudah setinggi jatah barisnya.
            #
            # Batas atasnya tiga, dan ketiganya wajib ditaati: jatah
            # baris, batas tinggi kartu, dan LEBAR kartu itu sendiri
            # — kartu yang lebih tinggi daripada lebarnya terbaca
            # sebagai pilar, bukan sebagai tombol.
            tinggi = max(tinggi, min(tinggi_baris, tinggi_maks, lebar))
            # Jatah barisnya ditaati apa adanya, TANPA batas bawah.
            # Batas bawah apa pun di sini akan membuat baris-baris
            # kartu saling menindih begitu panel tidak cukup tinggi —
            # dan kartu yang tertindih kehilangan nama layanannya.
            # Kartu yang sedikit terlalu pendek masih bisa disentuh;
            # kartu yang tertimbun kartu lain tidak.
            tinggi = min(tinggi, tinggi_baris)

        self._pasang_ukuran_tetap(pola, n_kolom, lebar, tinggi)
        if not self._jalur:
            self._kunci_ukuran_menu(lebar, tinggi)

    def _celah_baris(self, n_baris: int) -> int:
        """Celah tegak: rapat di dalam kelompok berbaris dua, 50 px di menu utama."""
        if self._jalur and n_baris > 1:
            return CELAH_BARIS_KELOMPOK
        return CELAH_TOMBOL

    def _lebar_kartu_kolom(self, n_kolom: int) -> int:
        """Lebar kartu untuk n kolom pada halaman pilihan sekarang."""
        lebar_area = self.halaman_pilihan.width() - 2 * MARGIN_KISI
        if lebar_area <= 0 or n_kolom <= 0:
            return 0
        pembesar = PEMBESAR_KARTU.get(n_kolom, 1.0)
        lebar_maks = round(LEBAR_TOMBOL_MAKS * pembesar)
        lebar = (lebar_area - CELAH_TOMBOL * (n_kolom - 1)) // n_kolom
        return min(lebar_maks, max(LEBAR_TOMBOL_MIN, lebar))

    def _pasang_ukuran_kelompok(
        self,
        pola: list[int],
        n_kolom: int,
        n_baris: int,
        lebar: int,
        tinggi: int,
    ) -> None:
        """
        Kartu kelompok menyesuaikan tinggi di panel bawah yang sudah dikunci.

        Lebar mengikuti menu utama (tiga kolom 480, bukan lima kolom 324).
        Tingginya mengisi kisi yang tersisa — bukan tebakan chrome yang
        sering lebih besar daripada judul+pil sungguhan, lalu menyisakan
        pil di tengah bidang kosong.
        """
        if self._tinggi_panel_menu:
            self.panel_ambil.setFixedHeight(self._tinggi_panel_menu)
        celah = self._celah_baris(n_baris)
        self.kisi.setSpacing(celah)

        # Dua putaran: putaran pertama bisa mengukur kisi yang masih
        # mengerut; yang kedua memakai tinggi yang sudah dialokasikan
        # panel. Video 80 px tidak ikut dihitung — ukuran kartu yang
        # sudah terlihat pengunjung dipertahankan.
        for _ in range(2):
            susunan = self.panel_ambil.layout()
            if susunan is not None:
                susunan.activate()
            tinggi_area = self._tinggi_area_kelompok()
            if tinggi_area is None:
                return
            tinggi_baris = (tinggi_area - celah * (n_baris - 1)) // n_baris
            if tinggi_baris > 0:
                tinggi = min(tinggi_baris, TINGGI_TOMBOL_MAKS, lebar)
            self._pasang_ukuran_tetap(pola, n_kolom, lebar, tinggi)

    def _tinggi_area_kelompok(self) -> int | None:
        """
        Tinggi yang boleh dipakai kartu di dalam kisi.

        `None` = kisi sedang mengerut (video, bongkar kartu); jangan
        menulis ukuran baru. Nol = belum ada angka yang berarti.
        """
        tinggi_halaman = self.halaman_pilihan.height()
        if 0 < tinggi_halaman <= 80:
            return None
        if tinggi_halaman > 80:
            return max(0, tinggi_halaman - 2 * MARGIN_KISI)
        chrome = self._tinggi_chrome_ambil()
        tinggi_panel = self._tinggi_panel_menu or self.panel_ambil.height()
        return max(0, tinggi_panel - chrome - 2 * MARGIN_KISI)

    def _pasang_gaya_ukuran(self, btn, lebar: int, tinggi: int) -> None:
        """Ukuran tetap, sudut, dan huruf — selalu dari tinggi sungguhan."""
        if btn.width() != lebar or btn.height() != tinggi:
            btn.setFixedSize(lebar, tinggi)
        radius = self._radius_kartu(tinggi)
        if btn.property("radiusKartu") != radius:
            btn.setProperty("radiusKartu", radius)
            btn.setStyleSheet(
                self._stylesheet_kartu(
                    btn.objectName(),
                    warna_teks=(
                        btn.property("warnaTeksKartu") or DISPLAY_KIOS_TOMBOL_TEKS
                    ),
                    latar=btn.property("latarKartu") or DISPLAY_KIOS_TOMBOL,
                    latar_hover=(
                        btn.property("latarHoverKartu") or DISPLAY_KIOS_TOMBOL_HOVER
                    ),
                    latar_tekan=(
                        btn.property("latarTekanKartu") or DISPLAY_KIOS_TOMBOL_TEKAN
                    ),
                    radius=radius,
                )
            )

    def _pasang_ukuran_tetap(
        self, pola: list[int], n_kolom: int, lebar: int, tinggi: int
    ) -> None:
        lebar_penuh = n_kolom * lebar + (n_kolom - 1) * CELAH_TOMBOL
        awal = 0
        for banyak in pola:
            lebar_baris = lebar
            if banyak < n_kolom:
                lebar_rata = (lebar_penuh - CELAH_TOMBOL * (banyak - 1)) // banyak
                lebar_baris = max(
                    lebar, min(lebar_rata, round(lebar * PEMBESAR_BARIS_AKHIR))
                )
            for btn in self.kartu_kisi[awal : awal + banyak]:
                self._pasang_gaya_ukuran(btn, lebar_baris, tinggi)
            awal += banyak
        self.kisi.activate()
        for btn in self.kartu_kisi:
            self._warnai_tulisan_tombol(btn, aktif=btn.isEnabled())

    def _kunci_ukuran_menu(self, lebar: int, tinggi: int) -> None:
        """Simpan ukuran menu utama yang layak, jangan pernah mengecilkannya."""
        # 180×120 adalah hasil darurat saat kisi masih kosong — bukan
        # ukuran yang pernah dilihat pengunjung. Menguncinya membuat ketiga
        # kartu menu utama tetap pil setelah KEMBALI.
        if tinggi <= TINGGI_TOMBOL_MIN or lebar <= LEBAR_TOMBOL_MIN:
            return
        if not self.isVisible():
            return
        now = (lebar, tinggi)
        if self._ukuran_kartu_menu is None:
            self._ukuran_kartu_menu = now
            self._tinggi_panel_menu = self.panel_ambil.height()
            self._tinggi_jendela_kunci = self.height()
            self._lebar_halaman_kunci = self.halaman_pilihan.width()
            self._catat_kunci_jendela()
            return
        w0, h0 = self._ukuran_kartu_menu
        if lebar >= w0 and tinggi >= h0:
            self._ukuran_kartu_menu = now
            self._tinggi_panel_menu = self.panel_ambil.height()
            self._tinggi_jendela_kunci = self.height()
            self._lebar_halaman_kunci = self.halaman_pilihan.width()
            self._catat_kunci_jendela()

    def _catat_kunci_jendela(self) -> None:
        """Ingat ukuran ini untuk F11 kembali ke jendela sebesar ini."""
        if self._ukuran_kartu_menu is None:
            return
        kunci = self._kunci_jendela()
        if kunci in self._kunci_per_jendela:
            return
        lebar, tinggi = self._ukuran_kartu_menu
        self._kunci_per_jendela[kunci] = (
            lebar,
            tinggi,
            self.panel_ambil.height(),
        )

    def _setel_tinggi_panel(self, n_baris: int, tinggi_kartu_maks: int) -> int:
        """
        Tinggi panel bawah = sisa, sesudah panel informasi dapat bentuknya.

        Arahnya sengaja dibalik dari yang wajar. Dahulu panel bawah
        mengambil setinggi yang dituntut kartunya dan papan menerima
        sisanya, sehingga menambah satu jenis layanan saja sudah mengubah
        bentuk panel informasi — pada 1920x1080, dari 1864x615 menjadi
        1864x372 begitu layanannya empat. Gambar dan video sambutan
        dipasang sekali untuk bertahun-tahun, dan bidang yang berubah
        bentuk membuat semuanya salah bingkai.

        Sekarang panel informasilah yang dikunci pada perbandingan
        `kiosk.info_ratio`, dan kartu A/B/C yang mengalah.

        Dua jepitan menjaganya:

        * ke bawah `TINGGI_PANEL_AMBIL_MIN` — bentuk panel tidak pernah
          sepadan menghabiskan ruang tombolnya;
        * ke atas ruang yang MASIH BISA dipakai panel bawah, yaitu kisi
          kartu pada tinggi terbesarnya. Kartu punya batas tinggi, jadi
          pada layar tegak panelnya kenyang jauh sebelum jatahnya habis,
          dan sisanya hanya akan jadi bidang putih kosong. Layar setinggi
          itu tidak akan mencapai perbandingan yang diminta, dan memang
          tidak seharusnya: memaksakannya berarti membuang ratusan piksel
          papan demi bentuk yang tidak ada yang meminta.

          Yang dipakai batas TERBESAR kartu, bukan tinggi kartu sekarang.
          Enam layanan berjajar menghasilkan kartu yang sempit — dan
          karena tingginya mengikuti lebarnya, juga pendek — sehingga
          batas yang dihitung dari tinggi sekarang akan ikut mengerut dan
          menggeser bentuk panel informasi ke 2,64:1. Persis pergeseran
          yang seluruh perhitungan ini ada untuk mencegahnya.

        Setiap angka yang masuk ke perhitungan ini WAJIB tidak bergantung
        pada tinggi panel yang sedang dihitungnya. Itu bukan kerapian,
        melainkan syarat: metode ini dipanggil ulang oleh tata letak yang
        dipicunya sendiri. Percobaan pertama memakai `sizeHint()` panel
        sebagai lantai — dan sizeHint itu ikut berubah mengikuti tinggi
        kartu, yang ikut berubah mengikuti tinggi panel — sehingga
        panelnya berayun 268, 499, 268, 499 tanpa pernah diam.

        Yang dipakai karena itu hanya lebar (tidak pernah berubah oleh
        tinggi), tinggi jendela, dan dua selisih yang tetap: tinggi
        kepala papan, dan tinggi judul beserta pil di panel bawah.

        Kembaliannya tinggi yang tersisa bagi kisi kartu — nol bila belum
        ada yang bisa dihitung. Pemanggilnya butuh angka itu SEKARANG:
        geometri Qt baru menyusul pada putaran tata letak berikutnya.
        """
        if self.totem:
            sisa_bawah = self._tinggi_chrome_ambil()
            tinggi = self.panel_ambil.height()
            if sisa_bawah <= 0 or tinggi <= 0:
                return 0
            return max(0, tinggi - sisa_bawah)

        panel_info = self.papan.panel_info_kios
        if panel_info is None or panel_info.width() <= 0:
            return 0
        # Chrome panel bawah dihitung dari judul dan pil, BUKAN dari
        # `panel.height() - halaman_pilihan.height()`. Saat kartu dibongkar
        # kisi mengerut, selisih itu membengkak, dan kartu yang baru dipasang
        # mewarisi tinggi yang salah — pil pipih di tengah panel yang masih
        # lapang. Itulah yang terlihat setelah masuk Konsultasi lalu pulang.
        sisa_bawah = self._tinggi_chrome_ambil()
        kepala = self.papan.height() - panel_info.height()
        if sisa_bawah <= 0 or kepala <= 0:
            # Tata letak belum pernah dihitung; angkanya belum berarti.
            return 0

        terpakai = (
            sisa_bawah
            + n_baris * tinggi_kartu_maks
            + (n_baris - 1) * CELAH_TOMBOL
            + 2 * MARGIN_KISI
        )
        diinginkan = round(panel_info.width() / self._rasio_info)
        target = self.height() - kepala - diinginkan
        tinggi = max(TINGGI_PANEL_AMBIL_MIN, min(target, terpakai))
        self.panel_ambil.setFixedHeight(tinggi)
        return max(0, tinggi - sisa_bawah)

    def _tinggi_chrome_ambil(self) -> int:
        """
        Tinggi panel bawah di luar kisi: bingkai, judul, pil, margin.

        Angkanya tidak bergantung pada isi kisi, jadi tidak berubah ketika
        pengunjung masuk atau keluar kelompok.
        """
        susunan = self.panel_ambil.layout()
        if susunan is None:
            return 0
        tepi = susunan.contentsMargins()
        tinggi_judul = (
            self.label_ajakan.height() or self.label_ajakan.sizeHint().height()
        )
        tinggi_pil = max(
            self.wadah_kembali.height(),
            self.label_petunjuk.height()
            or self.label_petunjuk.sizeHint().height(),
            TINGGI_TOMBOL_KEMBALI,
        )
        bingkai = max(
            0,
            self.panel_ambil.height() - self.panel_ambil.contentsRect().height(),
        )
        return (
            bingkai
            + tepi.top()
            + tinggi_judul
            + susunan.spacing()
            + tinggi_pil
            + susunan.spacing()
            + tepi.bottom()
        )

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - nama API Qt
        if event.type() == QEvent.Type.Resize:
            if obj is self.halaman_pilihan:
                if self._sedang_menyusun or self._sedang_menyesuaikan:
                    return super().eventFilter(obj, event)
                # F11 mengirim beberapa Resize. Yang sesaat (jendela < 400)
                # diabaikan; yang siap dihitung sekarang, lalu sekali lagi
                # sesudah putaran tata letak terakhir.
                self._penyesuai_jendela.start()
                if not self._geometri_siap():
                    return super().eventFilter(obj, event)
                if self._kolom_maks() != self._kolom_terpakai:
                    if not self._jalur:
                        self._reset_kunci_ukuran()
                    self._susun_tombol()
                else:
                    if not self._kunci_masih_berlaku():
                        self._reset_kunci_ukuran()
                    self._sesuaikan_ukuran_tombol()
            elif obj in self._huruf_menyusut:
                self._muatkan_huruf(obj)
            elif obj is getattr(self, "halaman_konfirmasi", None):
                self._muatkan_huruf(self.label_konfirmasi_layanan)
            elif obj in self.kartu_kisi:
                # Kartu submenu di jendela 720p sering lebih pendek dari
                # TINGGI_TOMBOL_MIN. Melewati pewarnaan di sini membuat
                # tulisan KEMBALI kehilangan merahnya.
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
        # Warna tulisan dititipkan pada kartunya sendiri, sebab kartu
        # layanan dan kartu kelompok tidak sewarna.
        if aktif:
            warna = btn.property("warnaTeksKartu") or DISPLAY_KIOS_TOMBOL_TEKS
            latar_kotak = btn.property("latarKotakKartu") or KIOS_KOTAK_HURUF
        else:
            warna = DISPLAY_KIOS_TOMBOL_MATI_TEKS
            latar_kotak = KIOS_KOTAK_HURUF_MATI
        tinggi_kartu = max(1, btn.height())
        padding = 2 * MARGIN_ISI_TOMBOL
        lebar_tersedia = max(1, btn.width() - padding)
        tinggi_isi = max(1, btn.height() - padding - CELAH_ISI_TOMBOL)
        hanya_nama = bool(btn.property("hanyaNamaKartu"))
        tinggi_nama = round(tinggi_isi * (0.72 if hanya_nama else 0.30))

        nama = btn.findChild(QLabel, "namaLayanan")
        if nama is not None:
            if hanya_nama:
                mula = max(18, round(tinggi_kartu * 0.38))
                berat = 800
            else:
                mula = max(14, round(tinggi_kartu * 0.15))
                berat = 700
            tanda = btn.findChild(QLabel, "tandaSubmenu")
            lebar_nama = lebar_tersedia
            if tanda is not None:
                # Sisakan tempat untuk logo ">" di kanan nama.
                lebar_nama = max(1, round(lebar_tersedia * 0.78))
            ukuran = self._pas_ukuran(
                nama.text(),
                mula,
                lebar_nama,
                max(1, tinggi_nama),
                berat,
            )
            # Selector QLabel#... mengalahkan `QWidget { color }` global.
            nama.setStyleSheet(
                f"QLabel#namaLayanan {{ color: {warna}; background: transparent;"
                f" font-size: {ukuran}px; font-weight: {berat}; }}"
            )
            pal = nama.palette()
            pal.setColor(QPalette.ColorRole.WindowText, QColor(warna))
            pal.setColor(QPalette.ColorRole.Text, QColor(warna))
            nama.setPalette(pal)
            font = QFont(self.font())
            font.setWeight(QFont.Weight(berat))
            font.setPixelSize(ukuran)
            nama.setMinimumHeight(QFontMetrics(font).height())
            nama.updateGeometry()

            if tanda is not None:
                ukuran_tanda = max(14, round(ukuran * 0.85))
                tanda.setStyleSheet(
                    f"QLabel#tandaSubmenu {{ color: {warna}; background: transparent;"
                    f" font-size: {ukuran_tanda}px; font-weight: 800; }}"
                )
                font_t = QFont(self.font())
                font_t.setWeight(QFont.Weight(800))
                font_t.setPixelSize(ukuran_tanda)
                tanda.setMinimumHeight(QFontMetrics(font_t).height())

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

        KELOMPOK tidak pernah sampai ke layar konfirmasi: ia tidak punya
        nomor untuk dikonfirmasi, dan yang dibuka adalah daftar isinya.
        """
        if layanan.punya_anak:
            self._buka_kelompok(layanan)
            return

        # Pengunjung baru saja menyentuh sesuatu; hitungan pulang otomatis
        # dimulai lagi dari nol. Yang sedang membaca layar konfirmasi tidak
        # boleh dipulangkan ke menu utama di tengah-tengah membacanya.
        if self._jalur:
            self._pemulang.start(JEDA_PULANG)

        self._kategori_terpilih = layanan
        self.label_konfirmasi_kode.setText(layanan.prefix)
        self.label_konfirmasi_layanan.setText(layanan.name)
        # Nama baru, ukuran huruf baru: lebar labelnya mungkin tidak berubah,
        # jadi tidak ada resize yang akan memicunya.
        self._muatkan_huruf(self.label_konfirmasi_layanan)
        self._menunggu_konfirmasi = True
        self._perbarui_tombol_kembali()
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
        self._info_papan(
            layanan.info_text, berkas=media_layanan(layanan.code)
        )

    def _batal_konfirmasi(self) -> None:
        """Kembali ke kisi pilihan tanpa menerbitkan nomor apa pun."""
        self._pembatal_konfirmasi.stop()
        self._menunggu_konfirmasi = False
        self._kategori_terpilih = None
        self._perbarui_tombol_kembali()
        self.tumpukan.setCurrentWidget(self.halaman_pilihan)
        if self._jalur:
            # Kembali ke daftar kelompok yang tadi dibuka, bukan ke menu
            # utama: pengunjung yang membatalkan biasanya hendak memilih
            # yang di sebelahnya. Panel papan ikut menampilkan kembali info
            # kelompoknya, sebab itulah yang tampil sebelum ia menyentuh.
            self._pemulang.start(JEDA_PULANG)
            self._info_papan(
                self._jalur[-1].info_text, berkas=media_layanan(self._jalur[-1].code)
            )
        else:
            self._info_papan(None)
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
        # Hitungan pulang otomatis berhenti di sini dan diserahkan kepada
        # `_bersihkan_hasil`: sejak nomor terbit, yang menentukan kapan
        # layar dikembalikan adalah lamanya kartu nomor tampil, bukan lagi
        # lamanya menu dibiarkan terbuka.
        self._pemulang.stop()
        self._menunggu_konfirmasi = False
        layanan = self._kategori_terpilih
        self._kategori_terpilih = None
        self.tumpukan.setCurrentWidget(self.halaman_pilihan)
        if layanan is not None:
            self.ambil_nomor(layanan.id)
        else:
            self._info_papan(None)

    def ambil_nomor(self, category_id: int) -> None:
        """Terbitkan satu nomor untuk pengunjung yang menekan tombol."""
        try:
            nomor = self.queue.create_queue(category_id)
        except Exception as exc:  # noqa: BLE001 - dialog modal menyangkut layar publik
            # Pulang lebih dahulu, sebelum pesan kegagalannya dipasang:
            # `_pulang()` memanggil `_perbarui_jeda()`, dan penyegaran itu
            # akan menimpa pil kesalahan dengan kalimat ajakan biasa.
            self._pulang()
            self._tampilkan_kesalahan(exc)
            self._kunci_tombol()
            # Nomornya tidak jadi terbit, jadi kartu nomor tidak akan
            # pernah tampil. Tanpa baris ini panel tersangkut memegang
            # media layanan yang tadi disentuh, dan tidak ada lagi yang
            # akan membebaskannya.
            self._info_papan(None)
            return

        self._tahan_petunjuk = False
        hasil_cetak = self._cetak(nomor)
        self._tampilkan_hasil(nomor, hasil_cetak)
        # Kisi pulang ke menu utama SEKARANG, tidak menunggu kartu nomor
        # hilang sepuluh detik kemudian. Pemilik nomor sudah selesai
        # memilih, dan sepanjang sepuluh detik itu orang berikutnya sudah
        # berdiri di depan menu yang bukan menu utama — mencari layanan
        # pada daftar yang tidak memuatnya, tanpa tahu bahwa ia sedang
        # berada di dalam sebuah kelompok.
        #
        # Letaknya WAJIB sesudah `_tampilkan_hasil`: pewaktu
        # `_penghapus_hasil` sudah menyala di sana, sehingga `_pulang()`
        # tidak menyentuh papan yang sedang memegang kartu nomor. Ditaruh
        # sebelumnya, papan dibebaskan ke sambutan dan sambutan itu
        # menyembul sekejap sebelum kartu nomor muncul.
        self._pulang()
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
        """
        Satu keterangan, satu tempat.

        Layar ini punya dua panel yang saling berhadapan, dan sebelumnya
        keduanya menyebut nomor, jenis layanan, dan kalimat arahan yang
        sama persis — tiga fakta yang dicetak dua kali di satu layar.
        Sekarang tiap fakta punya satu rumah:

        * kartu papan di atas menyimpan nomornya, besar dan bisa difoto;
        * judul panel bawah mengabarkan keadaan yang tidak dikatakan
          bagian mana pun: nomornya sudah sah;
        * pil petunjuk mengatakan apa yang harus dilakukan sekarang.
        """
        arahan = ARAHAN_CETAK.get(hasil_cetak, ARAHAN_CETAK[CETAK_TANPA_PRINTER])
        self.label_ajakan.setText("NOMOR ANDA SUDAH TERBIT")
        self._gaya_ajakan(sukses=True)
        # Pil kuning bila kertasnya tidak keluar. Warnanya yang terbaca
        # lebih dulu, sebelum kalimatnya sempat dieja — dan yang membuat
        # pengunjung menoleh ke kartu nomor di atas alih-alih berdiri
        # menunggu tiket di depan printer yang diam.
        self._set_petunjuk(
            arahan, "gagal" if hasil_cetak == CETAK_GAGAL else "hasil"
        )
        sisa = baris_sisa_antrian(self._sisa_antrian(nomor))
        if self.totem:
            self.label_hasil_nomor.setText(nomor.queue_number)
            self.label_hasil_layanan.setText(nomor.category_name)
            self.label_hasil_sisa.setText(sisa)
            self.label_hasil_sisa.setVisible(bool(sisa))
            self.tumpukan.setCurrentWidget(self.halaman_hasil)
        else:
            self.papan.tampilkan_kartu_kios(
                nomor=nomor.queue_number,
                layanan=nomor.category_name,
                sisa=sisa,
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
        # Kisinya sudah dipulangkan `ambil_nomor()` begitu nomornya terbit.
        # Yang ini tinggal jaring pengaman bagi jalur yang tidak lewat
        # sana, dan tidak berbiaya: `_pulang()` langsung berhenti begitu
        # jalurnya memang sudah kosong.
        self._pulang()
        # Satu-satunya tempat panel dibebaskan setelah nomor terbit.
        self._info_papan(None)
        if self.totem:
            self.tumpukan.setCurrentWidget(self.halaman_pilihan)
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
            #
            # Di dalam kelompok, yang disebut pilnya adalah JALUR yang
            # sedang terbuka. Kartu KEMBALI saja tidak cukup menjelaskan
            # dari mana pengunjung akan kembali, dan daftar yang tampak
            # tanpa keterangan terbaca sebagai seluruh layanan kantor ini.
            if self._jalur:
                teks = f"{self._remah()} — pilih layanan, atau sentuh KEMBALI"
            elif len(self._daftar_tampil()) == 1:
                teks = "Sentuh tombol di bawah untuk mengambil nomor"
            else:
                teks = "Sentuh jenis layanan yang Anda butuhkan"
            self._set_petunjuk(teks, "ajak")
