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
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
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

#: Selang pembaruan hitung mundur jeda pengambilan nomor.
SELANG_HITUNG_MS = 500

#: Tinggi minimum panel ambil nomor. Tanpa ini, papan antrian merebut
#: seluruh tinggi jendela biasa dan nama layanan di bawah A/B/C terpotong.
TINGGI_PANEL_AMBIL_MIN = 248
TINGGI_TOMBOL_MIN = 100


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

        # Timer dimiliki widget ini, bukan QTimer.singleShot yang statis.
        # singleShot tetap menyala setelah halamannya dihapus lalu menyentuh
        # label yang sudah tidak ada.
        self._penghapus_hasil = QTimer(self)
        self._penghapus_hasil.setSingleShot(True)
        self._penghapus_hasil.timeout.connect(self._bersihkan_hasil)

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

        self.kisi = QGridLayout()
        self.kisi.setSpacing(14)
        susunan.addLayout(self.kisi, stretch=1)

        return panel

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
        self.tombol_layanan = []

        if not self.kategori:
            kosong = QLabel("Belum ada jenis layanan yang dibuka.")
            kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kosong.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 20px;")
            self.kisi.addWidget(kosong, 0, 0)
            return

        # Maksimum tiga kolom. Lebih dari itu membuat tiap tombol terlalu
        # sempit untuk disentuh dengan jari, bukan dengan mouse.
        kolom_maks = min(3, len(self.kategori))
        for indeks, layanan in enumerate(self.kategori):
            btn = self._bangun_tombol_layanan(layanan)
            self.tombol_layanan.append(btn)
            self.kisi.addWidget(btn, indeks // kolom_maks, indeks % kolom_maks)

    def _bangun_tombol_layanan(self, layanan):
        btn = tombol("", variant="primary")
        btn.setMinimumHeight(TINGGI_TOMBOL_MIN)
        btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        btn.setStyleSheet(
            f"QPushButton {{ color: {DISPLAY_KIOS_TOMBOL_TEKS};"
            f" background: {DISPLAY_KIOS_TOMBOL};"
            " border: none; border-radius: 16px; }}"
            f"QPushButton:hover {{ background: {DISPLAY_KIOS_TOMBOL_HOVER}; }}"
            f"QPushButton:pressed {{ background: {DISPLAY_LOKET_BG}; }}"
            f"QPushButton:disabled {{ background: {DISPLAY_KIOS_TOMBOL_MATI};"
            f" color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS}; }}"
        )

        isi = QVBoxLayout(btn)
        isi.setContentsMargins(12, 12, 12, 12)
        isi.setSpacing(4)

        prefix = QLabel(layanan.prefix)
        prefix.setObjectName("prefixLayanan")
        prefix.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prefix.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        isi.addWidget(prefix)

        nama = QLabel(layanan.name)
        nama.setObjectName("namaLayanan")
        nama.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nama.setWordWrap(True)
        nama.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        isi.addWidget(nama)

        self._warnai_tulisan_tombol(btn, aktif=True)
        btn.installEventFilter(self)
        btn.clicked.connect(lambda _, k=layanan.id: self.ambil_nomor(k))
        return btn

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - nama API Qt
        if event.type() == QEvent.Type.Resize and obj in self.tombol_layanan:
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
        tengahnya.
        """
        warna = DISPLAY_KIOS_TOMBOL_TEKS if aktif else DISPLAY_KIOS_TOMBOL_MATI_TEKS
        tinggi = max(btn.height(), TINGGI_TOMBOL_MIN)
        for nama, dasar, faktor, berat in (
            ("prefixLayanan", 48, 0.42, 800),
            ("namaLayanan", 22, 0.18, 600),
        ):
            label = btn.findChild(QLabel, nama)
            if label is None:
                continue
            ukuran = max(dasar, round(tinggi * faktor))
            label.setStyleSheet(
                f"color: {warna}; background: transparent;"
                f" font-size: {ukuran}px; font-weight: {berat};"
            )

    # -----------------------------------------------------------------
    # Tindakan
    # -----------------------------------------------------------------

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

        if self._penghapus_hasil.isActive():
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
