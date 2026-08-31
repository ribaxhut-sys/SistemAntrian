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
from app.services.ticket_service import TicketService
from app.ui.common import pesan_untuk_user, tombol
from app.ui.display.display_page import DisplayPage
from app.ui.style import (
    DISPLAY_KIOS_PANEL,
    DISPLAY_KIOS_TOMBOL,
    DISPLAY_KIOS_TOMBOL_HOVER,
    DISPLAY_KIOS_TOMBOL_MATI,
    DISPLAY_KIOS_TOMBOL_MATI_TEKS,
    DISPLAY_KIOS_TOMBOL_TEKS,
    DISPLAY_LOKET_BG,
    DISPLAY_NOMOR,
    SUCCESS,
    TEXT_MUTED,
)

logger = get_logger("ui.kiosk")

#: Lama nomor yang baru terbit tampil sebelum layar bersiap untuk pengunjung
#: berikutnya, dalam milidetik.
JEDA_HASIL = 8000

#: Lama layar konfirmasi menunggu sebelum otomatis batal, dalam milidetik.
#: Kios tidak berpenjaga: pengunjung yang berbalik pergi tanpa menekan
#: apa pun tidak boleh meninggalkan layar tersangkut menunggu konfirmasi
#: untuk orang berikutnya.
JEDA_KONFIRMASI = 15000

#: Selang pembaruan hitung mundur jeda pengambilan nomor.
SELANG_HITUNG_MS = 500

#: Tinggi minimum panel ambil nomor. Tanpa ini, papan antrian merebut
#: seluruh tinggi jendela biasa dan nama layanan di bawah A/B/C terpotong.
TINGGI_PANEL_AMBIL_MIN = 268
TINGGI_TOMBOL_MIN = 120
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
CELAH_TOMBOL = 50
MARGIN_KISI = 16
MARGIN_ISI_TOMBOL = 16
CELAH_ISI_TOMBOL = 6

#: Tinggi minimum tombol BATAL/YA pada layar konfirmasi. Lebih tinggi
#: daripada tombol pilih layanan: hanya ada dua tombol di layar itu, jadi
#: keduanya boleh memakai ruang yang jauh lebih lapang, dan salah tap di
#: sini berarti nomor sudah terlanjur terbit atau pengunjung mengulang
#: dari awal.
TINGGI_TOMBOL_KONFIRMASI_MIN = 220


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

        susunan.addWidget(self._bangun_panel_ambil(), stretch=2)

    def _bangun_panel_ambil(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelAmbil")
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        panel.setMinimumHeight(TINGGI_PANEL_AMBIL_MIN)
        panel.setStyleSheet(
            f"QFrame#panelAmbil {{ background: {DISPLAY_KIOS_PANEL};"
            f" border-top: 4px solid {self.papan.palet.tepi_unggulan}; }}"
        )

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(32, 20, 32, 24)
        susunan.setSpacing(12)

        self.label_ajakan = QLabel("AMBIL NOMOR ANTRIAN ANDA")
        self.label_ajakan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_ajakan.setStyleSheet(
            f"color: {DISPLAY_NOMOR}; font-size: 26px; font-weight: 700;"
            " letter-spacing: 2px;"
        )
        susunan.addWidget(self.label_ajakan)

        self.label_petunjuk = QLabel("Sentuh jenis layanan yang Anda butuhkan")
        self.label_petunjuk.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_petunjuk.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 18px;")
        susunan.addWidget(self.label_petunjuk)

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

        self.label_konfirmasi_layanan = QLabel("")
        self.label_konfirmasi_layanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_konfirmasi_layanan.setWordWrap(True)
        self.label_konfirmasi_layanan.setStyleSheet(
            f"color: {DISPLAY_NOMOR}; font-size: 64px; font-weight: 800;"
        )
        susunan.addWidget(self.label_konfirmasi_layanan, stretch=1)

        baris_tombol = QHBoxLayout()
        baris_tombol.setSpacing(14)

        btn_batal = tombol("BATAL, PILIH LAGI")
        btn_batal.setMinimumHeight(TINGGI_TOMBOL_KONFIRMASI_MIN)
        btn_batal.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_batal.setStyleSheet(
            f"QPushButton {{ color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS};"
            f" background: {DISPLAY_KIOS_TOMBOL_MATI};"
            " border: none; border-radius: 20px;"
            " font-size: 34px; font-weight: 700; }}"
            "QPushButton:hover { background: #CBD5E1; }"
            "QPushButton:pressed { background: #94A3B8; }"
        )
        btn_batal.clicked.connect(self._batal_konfirmasi)
        _bayangan(btn_batal, 24, 8, 60)
        baris_tombol.addWidget(btn_batal, stretch=1)

        btn_konfirmasi = tombol("YA, AMBIL NOMOR")
        btn_konfirmasi.setMinimumHeight(TINGGI_TOMBOL_KONFIRMASI_MIN)
        btn_konfirmasi.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_konfirmasi.setStyleSheet(
            f"QPushButton {{ color: white; background: {SUCCESS};"
            " border: none; border-radius: 20px;"
            " font-size: 34px; font-weight: 700; }}"
            "QPushButton:hover { background: #166534; }"
            "QPushButton:pressed { background: #14532D; }"
        )
        btn_konfirmasi.clicked.connect(self._konfirmasi_ambil)
        _bayangan(btn_konfirmasi, 24, 8, 90)
        baris_tombol.addWidget(btn_konfirmasi, stretch=1)

        # Tombolnya diberi jatah dua kali lipat label di atasnya: keduanya
        # yang benar-benar disentuh, jadi keduanya yang paling berhak atas
        # ruang lebih begitu panel lebih lapang daripada jendela pengembang.
        susunan.addLayout(baris_tombol, stretch=2)
        return halaman

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

        # Maksimum tiga kolom. Lebih dari itu membuat tiap tombol terlalu
        # sempit untuk disentuh dengan jari, bukan dengan mouse.
        kolom_maks = min(3, len(self.kategori))
        self.kisi.addStretch(1)
        for awal in range(0, len(self.kategori), kolom_maks):
            baris = QHBoxLayout()
            baris.setSpacing(CELAH_TOMBOL)
            baris.addStretch(1)
            for layanan in self.kategori[awal : awal + kolom_maks]:
                btn = self._bangun_tombol_layanan(layanan)
                self.tombol_layanan.append(btn)
                baris.addWidget(btn)
            baris.addStretch(1)
            self.kisi.addLayout(baris)
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
            " border: none; border-radius: 20px; }}"
            f"QPushButton:hover {{ background: {DISPLAY_KIOS_TOMBOL_HOVER}; }}"
            f"QPushButton:pressed {{ background: {DISPLAY_LOKET_BG}; }}"
            f"QPushButton:disabled {{ background: {DISPLAY_KIOS_TOMBOL_MATI};"
            f" color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS}; }}"
        )
        _bayangan(btn, 20, 6, 70)

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
        isi.addWidget(prefix)

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
        Hitung satu ukuran kartu untuk semua tombol, lalu jepit ke rasio.

        Tanpa jepitan lebar, kebijakan Expanding membuat A/B/C meregang
        selebar panel — pada 1080p itu batang ~600×120, bukan kartu
        yang mengundang sentuhan.
        """
        if not self.tombol_layanan:
            return

        n_kolom = min(3, len(self.tombol_layanan))
        n_baris = (len(self.tombol_layanan) + n_kolom - 1) // n_kolom
        lebar_area = self.halaman_pilihan.width() - 2 * MARGIN_KISI
        tinggi_area = self.halaman_pilihan.height() - 2 * MARGIN_KISI

        if lebar_area <= 0 or tinggi_area <= 0:
            lebar, tinggi = LEBAR_TOMBOL_MIN, TINGGI_TOMBOL_MIN
        else:
            lebar = (lebar_area - CELAH_TOMBOL * (n_kolom - 1)) // n_kolom
            lebar = min(LEBAR_TOMBOL_MAKS, max(LEBAR_TOMBOL_MIN, lebar))
            tinggi = round(lebar * RASIO_TINGGI_TOMBOL)
            tinggi = min(TINGGI_TOMBOL_MAKS, max(TINGGI_TOMBOL_MIN, tinggi))
            tinggi_baris = (tinggi_area - CELAH_TOMBOL * (n_baris - 1)) // n_baris
            if tinggi_baris > 0:
                tinggi = min(tinggi, max(TINGGI_TOMBOL_MIN, tinggi_baris))

        for btn in self.tombol_layanan:
            if btn.width() != lebar or btn.height() != tinggi:
                btn.setFixedSize(lebar, tinggi)
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
        Warna ditulis di label, bukan diwarisi dari tombol.

        Stylesheet global `QWidget { color }` mengalahkan `color` pada
        QPushButton, sehingga huruf A/B/C sempat tampak gelap di atas
        latar teal dan hampir tidak terbaca.

        Ukuran font mengikuti tinggi kartu (bukan angka tetap), supaya
        kartu besar di layar lebar tidak menyisakan huruf kecil di
        tengahnya — tetapi dijepit ke lebar DAN tinggi kartu yang
        SUNGGUHAN, bukan sekadar TINGGI_TOMBOL_MIN yang cuma titik
        awal permintaan. Kartu yang terperas lebih pendek daripada itu
        — jendela kios yang tidak setinggi dugaan, atau tiga baris
        tombol yang berdesakan — tanpa jepitan ini tetap mendapat huruf
        seukuran kartu yang lebih tinggi, dan prefix bertumpuk dengan
        nama layanan di bawahnya.
        """
        warna = DISPLAY_KIOS_TOMBOL_TEKS if aktif else DISPLAY_KIOS_TOMBOL_MATI_TEKS
        tinggi_kartu = max(1, btn.height())
        padding = 2 * MARGIN_ISI_TOMBOL
        lebar_tersedia = max(1, btn.width() - padding)
        tinggi_isi = max(1, btn.height() - padding - CELAH_ISI_TOMBOL)
        # Prefix (huruf besar) mendapat porsi lebih tinggi daripada nama
        # layanan di bawahnya. Angka di bawah adalah BATAS ATAS metrik
        # huruf, bukan jatah layout: sisa tinggi dipakai stretch supaya
        # keduanya tetap di tengah kartu.
        tinggi_prefix = round(tinggi_isi * 0.52)
        tinggi_nama = round(tinggi_isi * 0.30)
        for nama, faktor, berat, tinggi_maks in (
            ("prefixLayanan", 0.40, 800, tinggi_prefix),
            ("namaLayanan", 0.15, 700, tinggi_nama),
        ):
            label = btn.findChild(QLabel, nama)
            if label is None:
                continue
            ukuran = max(14, round(tinggi_kartu * faktor))
            ukuran = self._pas_ukuran(
                label.text(), ukuran, lebar_tersedia, max(1, tinggi_maks), berat
            )
            label.setStyleSheet(
                f"color: {warna}; background: transparent;"
                f" font-size: {ukuran}px; font-weight: {berat};"
            )
            font = QFont(self.font())
            font.setWeight(QFont.Weight(berat))
            font.setPixelSize(ukuran)
            label.setMinimumHeight(QFontMetrics(font).height())
            label.updateGeometry()

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
        self.label_konfirmasi_layanan.setText(f"{layanan.prefix} — {layanan.name}")
        self._menunggu_konfirmasi = True
        self.label_petunjuk.setText("Pastikan pilihan Anda sudah benar")
        self.tumpukan.setCurrentWidget(self.halaman_konfirmasi)
        self._pembatal_konfirmasi.start(JEDA_KONFIRMASI)
        # Panel papan nomor beralih dari sambutan ke info layanan yang
        # baru disentuh, supaya pengunjung membaca sesuatu yang relevan
        # dengan pilihannya sementara menunggu konfirmasi.
        self.papan.tampilkan_info_kios(layanan.info_text)

    def _batal_konfirmasi(self) -> None:
        """Kembali ke kisi pilihan tanpa menerbitkan nomor apa pun."""
        self._pembatal_konfirmasi.stop()
        self._menunggu_konfirmasi = False
        self._kategori_terpilih = None
        self.tumpukan.setCurrentWidget(self.halaman_pilihan)
        self.papan.tampilkan_info_kios(None)
        self._perbarui_jeda()

    def _konfirmasi_ambil(self) -> None:
        """Baru di sinilah nomor benar-benar diterbitkan dan dicetak."""
        self._pembatal_konfirmasi.stop()
        self._menunggu_konfirmasi = False
        layanan = self._kategori_terpilih
        self._kategori_terpilih = None
        self.tumpukan.setCurrentWidget(self.halaman_pilihan)
        self.papan.tampilkan_info_kios(None)
        if layanan is not None:
            self.ambil_nomor(layanan.id)

    def ambil_nomor(self, category_id: int) -> None:
        """Terbitkan satu nomor untuk pengunjung yang menekan tombol."""
        try:
            nomor = self.queue.create_queue(category_id)
        except Exception as exc:  # noqa: BLE001 - dialog modal menyangkut layar publik
            self._tampilkan_kesalahan(exc)
            self._kunci_tombol()
            return

        self._tahan_petunjuk = False
        self._cetak(nomor)
        self._tampilkan_hasil(nomor)
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
        self.label_petunjuk.setText(pesan_untuk_user(exc))

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

    def _cetak(self, nomor: QueueInfo) -> None:
        """
        Cetak tiket, dan jangan pernah menggagalkan pengambilan nomor.

        Nomor sudah terbit dan tersimpan sebelum tiket dicetak. Printer yang
        kehabisan kertas tidak boleh membuat pengunjung kehilangan gilirannya
        — nomornya tetap sah, dan petugas cukup menyebutkannya.

        TicketService.cetak() memang tidak pernah melempar exception;
        kegagalan dilaporkan sebagai hasil dan cukup dicatat di log.
        """
        if self.ticket is None:
            return
        hasil = self.ticket.cetak(nomor)
        if not hasil.berhasil:
            logger.warning("Tiket %s gagal dicetak: %s", nomor.queue_number, hasil.pesan)

    def _tampilkan_hasil(self, nomor: QueueInfo) -> None:
        self.label_ajakan.setText(f"NOMOR ANDA:  {nomor.queue_number}")
        self.label_ajakan.setStyleSheet(
            f"color: {SUCCESS}; font-size: 34px; font-weight: 800;"
            " letter-spacing: 2px;"
        )
        self.label_petunjuk.setText(
            "Silakan menunggu hingga nomor Anda dipanggil."
            if self.ticket is None
            else "Ambil tiket Anda, lalu tunggu hingga nomor Anda dipanggil."
        )
        self._penghapus_hasil.start(JEDA_HASIL)

    def _bersihkan_hasil(self) -> None:
        self.label_ajakan.setText("AMBIL NOMOR ANTRIAN ANDA")
        self.label_ajakan.setStyleSheet(
            f"color: {DISPLAY_NOMOR}; font-size: 26px; font-weight: 700;"
            " letter-spacing: 2px;"
        )
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
            self.label_petunjuk.setText("Pendaftaran nomor antrian sedang ditutup sementara.")
        elif not aktif:
            self._tahan_petunjuk = False
            self.label_petunjuk.setText(
                f"Mohon tunggu {int(sisa) + 1} detik sebelum mengambil nomor berikutnya."
            )
        elif not self._tahan_petunjuk:
            self.label_petunjuk.setText("Sentuh jenis layanan yang Anda butuhkan")
