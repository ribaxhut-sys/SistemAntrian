"""Layar antrian untuk pengunjung."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.core.logger import get_logger
from app.services.queue_service import DisplayState, QueueService
from app.services.settings_service import SettingsService
from app.services.sound_service import SoundPlayer
from app.ui.common import jalankan_aman
from app.ui.style import PRIMARY_DARK

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
        # putih dan setiap label ikut berlatar biru dan isinya hilang.
        self.setObjectName("layarAntrian")
        self.setStyleSheet(
            f"QWidget#layarAntrian {{ background: {PRIMARY_DARK}; }}"
        )

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(40, 32, 40, 32)
        susunan.setSpacing(24)

        self.label_judul = QLabel(self.settings.get("display.title"))
        self.label_judul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_judul.setStyleSheet(
            "color: white; background: transparent;"
            " font-size: 34px; font-weight: 700; letter-spacing: 3px;"
        )
        susunan.addWidget(self.label_judul)

        susunan.addWidget(self._bangun_panel_utama(), stretch=3)
        susunan.addWidget(self._bangun_panel_berikutnya(), stretch=1)

    def _bangun_panel_utama(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelUtama")
        panel.setStyleSheet(
            "QFrame#panelUtama { background: white; border-radius: 12px; }"
        )

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(32, 24, 32, 24)
        susunan.setSpacing(4)

        self.label_nomor = QLabel("—")
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_nomor.setStyleSheet(
            f"color: {PRIMARY_DARK}; background: transparent;"
            " font-size: 150px; font-weight: 800;"
        )
        susunan.addWidget(self.label_nomor, stretch=1)

        self.label_loket = QLabel("")
        self.label_loket.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_loket.setStyleSheet(
            "color: #263238; background: transparent;"
            " font-size: 52px; font-weight: 700;"
        )
        susunan.addWidget(self.label_loket)

        self.label_layanan = QLabel("")
        self.label_layanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_layanan.setStyleSheet(
            "color: #5F6368; background: transparent; font-size: 24px;"
        )
        susunan.addWidget(self.label_layanan)

        return panel

    def _bangun_panel_berikutnya(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelBerikutnya")
        panel.setStyleSheet(
            "QFrame#panelBerikutnya { background: rgba(255,255,255,0.12);"
            " border-radius: 12px; }"
        )

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(24, 16, 24, 16)
        susunan.setSpacing(8)

        label = QLabel("BERIKUTNYA")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "color: rgba(255,255,255,0.75); background: transparent;"
            " font-size: 20px; letter-spacing: 3px;"
        )
        susunan.addWidget(label)

        self.baris_berikutnya = QHBoxLayout()
        self.baris_berikutnya.setSpacing(20)
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
            self.label_nomor.setText("—")
            self.label_loket.setText("")
            self.label_layanan.setText("Belum ada nomor yang dipanggil")
        else:
            self.label_nomor.setText(terkini.queue_number)
            self.label_loket.setText((terkini.counter_name or "").upper())
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
                "color: rgba(255,255,255,0.6); background: transparent;"
                " font-size: 22px;"
            )
            self.baris_berikutnya.addWidget(kosong)
            return

        for antrian in berikutnya:
            label = QLabel(antrian.queue_number)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # rgba(), bukan #RRGGBBAA. Qt tidak mendukung heksadesimal
            # delapan digit dan akan membacanya sebagai warna yang sama
            # sekali berbeda.
            label.setStyleSheet(
                "color: white; background: rgba(255,255,255,0.18);"
                " border-radius: 8px; font-size: 44px; font-weight: 700;"
                " padding: 8px 16px;"
            )
            self.baris_berikutnya.addWidget(label)

    # -----------------------------------------------------------------

    def hentikan(self) -> None:
        """Hentikan penyegaran berkala. Dipanggil saat layar ditutup."""
        self.pewaktu.stop()
