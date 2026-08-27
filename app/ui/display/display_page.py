"""Layar antrian untuk pengunjung."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.logger import get_logger
from app.services.queue_service import DisplayState, QueueService
from app.services.settings_service import SettingsService
from app.services.sound_service import SoundPlayer
from app.ui.common import jalankan_aman
from app.ui.style import (
    DISPLAY_AKSEN,
    DISPLAY_BG_ATAS,
    DISPLAY_BG_BAWAH,
    DISPLAY_BERIKUTNYA_JUDUL,
    DISPLAY_BERIKUTNYA_KARTU,
    DISPLAY_BERIKUTNYA_KOSONG,
    DISPLAY_BERIKUTNYA_TEKS,
    DISPLAY_JUDUL,
    DISPLAY_KARTU,
    DISPLAY_KETERANGAN,
    DISPLAY_LAYANAN,
    DISPLAY_LOKET_BG,
    DISPLAY_LOKET_TEKS,
    DISPLAY_NOMOR,
    DISPLAY_PANEL_BERIKUTNYA,
)

logger = get_logger("ui.display")

#: Selang penyegaran. Layar ini menghadap pengunjung yang sedang menunggu,
#: sehingga jeda beberapa detik sudah terasa lama.
SELANG_SEGAR_MS = 2_000


class DisplayPage(QWidget):
    """
    Papan nomor antrian.

    Sengaja tidak memiliki satu pun fungsi administrasi. Komputer layar
    biasanya menghadap publik dan tidak diawasi, jadi tidak ada tombol yang
    dapat mengubah data.

    Isinya dibuat dengan kontras tinggi dan huruf sangat besar karena dibaca
    dari seberang ruangan, bukan dari depan meja.
    """

    def __init__(
        self,
        queue: QueueService,
        settings: SettingsService,
        sound: SoundPlayer,
        parent: QWidget | None = None,
        *,
        otomatis: bool = True,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.settings = settings
        self.sound = sound

        self.jumlah_berikutnya = settings.get_int("display.next_count", 3)
        self.suara_aktif = settings.get_bool("display.sound_enabled", True)
        #: Nomor yang terakhir dibunyikan, supaya nada tidak berulang setiap
        #: penyegaran untuk panggilan yang sama.
        self._terakhir_dibunyikan: tuple[int, int] | None = None

        self._bangun_tampilan()
        self.muat_ulang()

        self.pewaktu = QTimer(self)
        self.pewaktu.setInterval(SELANG_SEGAR_MS)
        self.pewaktu.timeout.connect(self.muat_ulang)
        if otomatis:
            self.pewaktu.start()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        # Selector WAJIB dibatasi dengan objectName. Deklarasi "background"
        # tanpa selector merambat ke seluruh widget anak, sehingga panel
        # putih dan setiap label ikut berlatar gelap dan isinya hilang.
        self.setObjectName("layarAntrian")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#layarAntrian {{"
            f" background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            f"  stop:0 {DISPLAY_BG_ATAS}, stop:1 {DISPLAY_BG_BAWAH}); }}"
        )

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(48, 28, 48, 28)
        susunan.setSpacing(20)

        susunan.addLayout(self._bangun_kepala())
        susunan.addWidget(self._bangun_panel_utama(), stretch=5)
        susunan.addWidget(self._bangun_panel_berikutnya(), stretch=2)

    def _bangun_kepala(self) -> QVBoxLayout:
        kepala = QVBoxLayout()
        kepala.setSpacing(10)

        self.label_judul = QLabel(self.settings.get("display.title"))
        self.label_judul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_judul.setStyleSheet(
            f"color: {DISPLAY_JUDUL}; background: transparent;"
            " font-size: 28px; font-weight: 700; letter-spacing: 4px;"
        )
        kepala.addWidget(self.label_judul)

        baris_aksen = QHBoxLayout()
        baris_aksen.addStretch()
        garis = QFrame()
        garis.setFixedSize(72, 4)
        garis.setStyleSheet(
            f"background: {DISPLAY_AKSEN}; border: none; border-radius: 2px;"
        )
        baris_aksen.addWidget(garis)
        baris_aksen.addStretch()
        kepala.addLayout(baris_aksen)

        return kepala

    def _bangun_panel_utama(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelUtama")
        panel.setStyleSheet(
            f"QFrame#panelUtama {{ background: {DISPLAY_KARTU}; border-radius: 24px; }}"
        )
        bayangan = QGraphicsDropShadowEffect(panel)
        bayangan.setBlurRadius(18)
        bayangan.setOffset(0, 6)
        bayangan.setColor(QColor(0, 0, 0, 70))
        panel.setGraphicsEffect(bayangan)

        luar = QVBoxLayout(panel)
        luar.setContentsMargins(0, 0, 0, 0)
        luar.setSpacing(0)

        pita = QFrame()
        pita.setFixedHeight(6)
        pita.setStyleSheet(
            f"background: {DISPLAY_AKSEN}; border: none;"
            " border-top-left-radius: 24px; border-top-right-radius: 24px;"
        )
        luar.addWidget(pita)

        isi = QWidget()
        isi.setStyleSheet("background: transparent;")
        susunan = QVBoxLayout(isi)
        susunan.setContentsMargins(36, 18, 36, 28)
        susunan.setSpacing(6)

        self.label_status = QLabel("MENUNGGU PANGGILAN")
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_status.setStyleSheet(
            f"color: {DISPLAY_KETERANGAN}; background: transparent;"
            " font-size: 18px; font-weight: 700; letter-spacing: 5px;"
        )
        susunan.addWidget(self.label_status)

        self.label_nomor = QLabel("—")
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_nomor.setStyleSheet(
            f"color: {DISPLAY_NOMOR}; background: transparent;"
            " font-size: 132px; font-weight: 800; letter-spacing: 2px;"
        )
        susunan.addWidget(self.label_nomor, stretch=1)

        susunan.addLayout(self._bangun_baris_loket())

        self.label_layanan = QLabel("")
        self.label_layanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_layanan.setStyleSheet(
            f"color: {DISPLAY_LAYANAN}; background: transparent;"
            " font-size: 24px; font-weight: 600;"
        )
        susunan.addWidget(self.label_layanan)

        luar.addWidget(isi, stretch=1)
        return panel

    def _bangun_baris_loket(self) -> QHBoxLayout:
        """
        Nama loket dibungkus bingkai berwarna. Label di dalamnya tetap
        berlatar transparan agar tidak menutupi kartu putih di belakangnya.
        """
        self.bingkai_loket = QFrame()
        self.bingkai_loket.setObjectName("bingkaiLoket")
        self.bingkai_loket.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.bingkai_loket.setStyleSheet(
            f"QFrame#bingkaiLoket {{ background: {DISPLAY_LOKET_BG}; border-radius: 28px; }}"
        )
        self.bingkai_loket.setVisible(False)

        isi = QHBoxLayout(self.bingkai_loket)
        isi.setContentsMargins(36, 10, 36, 10)
        isi.setSpacing(0)

        self.label_loket = QLabel("")
        self.label_loket.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_loket.setStyleSheet(
            f"color: {DISPLAY_LOKET_TEKS}; background: transparent;"
            " font-size: 36px; font-weight: 700; letter-spacing: 2px;"
        )
        isi.addWidget(self.label_loket)

        baris = QHBoxLayout()
        baris.addStretch()
        baris.addWidget(self.bingkai_loket)
        baris.addStretch()
        return baris

    def _bangun_panel_berikutnya(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelBerikutnya")
        panel.setMinimumHeight(150)
        panel.setStyleSheet(
            f"QFrame#panelBerikutnya {{ background: {DISPLAY_PANEL_BERIKUTNYA};"
            f" border-radius: 20px; }}"
        )

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(24, 16, 24, 20)
        susunan.setSpacing(12)

        label = QLabel("BERIKUTNYA")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"color: {DISPLAY_BERIKUTNYA_JUDUL}; background: transparent;"
            " font-size: 16px; font-weight: 700; letter-spacing: 4px;"
        )
        susunan.addWidget(label)

        self.baris_berikutnya = QHBoxLayout()
        self.baris_berikutnya.setSpacing(16)
        susunan.addLayout(self.baris_berikutnya, stretch=1)

        return panel

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Ambil keadaan terbaru dan perbarui layar."""
        berhasil, keadaan = jalankan_aman(self, lambda: self.queue.display_state(
            self.jumlah_berikutnya
        ))
        if not berhasil or keadaan is None:
            return
        self.tampilkan(keadaan)

    def tampilkan(self, keadaan: DisplayState) -> None:
        """Perbarui layar dari sebuah keadaan. Dipisah agar mudah diuji."""
        terkini = keadaan.terkini

        if terkini is None:
            self.label_status.setText("MENUNGGU PANGGILAN")
            self.label_nomor.setText("—")
            self.label_loket.setText("")
            self.bingkai_loket.setVisible(False)
            self.label_layanan.setText("Belum ada nomor yang dipanggil")
        else:
            self.label_status.setText("SEDANG DIPANGGIL")
            self.label_nomor.setText(terkini.queue_number)
            self.label_loket.setText((terkini.counter_name or "").upper())
            self.bingkai_loket.setVisible(bool(terkini.counter_name))
            self.label_layanan.setText(terkini.category_name)
            self._bunyikan_bila_baru(terkini)

        self._isi_berikutnya(keadaan.berikutnya)

    def _bunyikan_bila_baru(self, terkini) -> None:
        """
        Bunyikan nada hanya untuk panggilan yang benar-benar baru.

        Penandanya adalah pasangan (id antrian, jumlah panggilan), sehingga
        panggilan ULANG pada nomor yang sama tetap berbunyi, sementara
        penyegaran biasa tidak.
        """
        penanda = (terkini.id, terkini.jumlah_panggilan)
        if penanda == self._terakhir_dibunyikan:
            return

        self._terakhir_dibunyikan = penanda
        if self.suara_aktif:
            self.sound.announce(terkini.queue_number, terkini.counter_name)

    def _isi_berikutnya(self, berikutnya: list) -> None:
        while self.baris_berikutnya.count():
            item = self.baris_berikutnya.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not berikutnya:
            kosong = QLabel("Tidak ada antrian menunggu")
            kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kosong.setStyleSheet(
                f"color: {DISPLAY_BERIKUTNYA_KOSONG}; background: transparent;"
                " font-size: 22px;"
            )
            self.baris_berikutnya.addWidget(kosong)
            return

        for antrian in berikutnya:
            label = QLabel(antrian.queue_number)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            # Kartu terang dengan angka gelap: dibaca jauh lebih jelas
            # daripada teks putih di atas kaca transparan.
            # rgba(), bukan #RRGGBBAA. Qt tidak mendukung heksadesimal
            # delapan digit dan akan membacanya sebagai warna yang sama
            # sekali berbeda.
            label.setStyleSheet(
                f"color: {DISPLAY_BERIKUTNYA_TEKS};"
                f" background: {DISPLAY_BERIKUTNYA_KARTU};"
                " border-radius: 14px; font-size: 42px; font-weight: 800;"
                " padding: 12px 16px;"
            )
            self.baris_berikutnya.addWidget(label)

    # -----------------------------------------------------------------

    def hentikan(self) -> None:
        """Hentikan penyegaran berkala. Dipanggil saat layar ditutup."""
        self.pewaktu.stop()
