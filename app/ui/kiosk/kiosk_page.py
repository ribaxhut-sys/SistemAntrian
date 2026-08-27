"""
Layar kios pengunjung.

Satu layar mengerjakan dua hal: menampilkan papan nomor yang sedang
dipanggil, dan menyediakan tombol bagi pengunjung untuk mengambil nomornya
sendiri.

Dirancang untuk dipakai orang yang belum pernah melihatnya, sambil berdiri,
dari jarak satu lengan. Karena itu tidak ada menu, tidak ada pilihan yang
perlu dipahami dahulu, dan tidak ada tombol yang tidak jelas akibatnya.

Layar ini berjalan TANPA login. Kewenangannya dibatasi peran KIOSK di
service layer dan oleh hak user PostgreSQL mesin itu di database.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
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
    DISPLAY_BG_ATAS,
    DISPLAY_KIOS_PANEL,
    DISPLAY_KIOS_TOMBOL,
    DISPLAY_KIOS_TOMBOL_HOVER,
    DISPLAY_KIOS_TOMBOL_MATI,
    DISPLAY_KIOS_TOMBOL_MATI_TEKS,
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
        self.setStyleSheet(
            f"QWidget#layarKios {{ background: {DISPLAY_BG_ATAS}; }}"
        )

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(0)

        # Papan nomor memakai layar antrian yang sudah ada, bukan salinannya.
        # Pengunjung melihat tampilan yang persis sama dengan layar besar di
        # ruang tunggu, dan perbaikan pada salah satunya berlaku bagi keduanya.
        self.papan = DisplayPage(self.queue, self.settings, self.sound)
        susunan.addWidget(self.papan, stretch=5)

        susunan.addWidget(self._bangun_panel_ambil(), stretch=2)

    def _bangun_panel_ambil(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelAmbil")
        panel.setStyleSheet(
            f"QFrame#panelAmbil {{ background: {DISPLAY_KIOS_PANEL};"
            f" border-top: 4px solid {DISPLAY_LOKET_BG}; }}"
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
            data = self.master.list_categories(only_active=True)
        except Exception as exc:  # noqa: BLE001 - batas UI kios, tanpa dialog
            self._tampilkan_kesalahan(exc)
            return

        self.kategori = data or []
        self._susun_tombol()

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
        btn = tombol(f"{layanan.prefix}\n{layanan.name}", variant="primary")
        btn.setMinimumHeight(120)
        btn.setStyleSheet(
            f"QPushButton {{ font-size: 22px; font-weight: 700; color: white;"
            f" background: {DISPLAY_KIOS_TOMBOL}; border: none;"
            f" border-radius: 16px; }}"
            f"QPushButton:hover {{ background: {DISPLAY_KIOS_TOMBOL_HOVER}; }}"
            f"QPushButton:pressed {{ background: {DISPLAY_LOKET_BG}; }}"
            f"QPushButton:disabled {{ background: {DISPLAY_KIOS_TOMBOL_MATI};"
            f" color: {DISPLAY_KIOS_TOMBOL_MATI_TEKS}; }}"
        )
        btn.clicked.connect(lambda _, k=layanan.id: self.ambil_nomor(k))
        return btn

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
        aktif = self.queue.sisa_jeda_kios() <= 0
        for btn in self.tombol_layanan:
            btn.setEnabled(aktif)

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
        sisa = self.queue.sisa_jeda_kios()
        aktif = sisa <= 0

        for btn in self.tombol_layanan:
            btn.setEnabled(aktif)

        if self._penghapus_hasil.isActive():
            return
        if not aktif:
            self._tahan_petunjuk = False
            self.label_petunjuk.setText(
                f"Mohon tunggu {int(sisa) + 1} detik sebelum mengambil nomor berikutnya."
            )
        elif not self._tahan_petunjuk:
            self.label_petunjuk.setText("Sentuh jenis layanan yang Anda butuhkan")
