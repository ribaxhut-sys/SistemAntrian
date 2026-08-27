"""
Layar survey untuk diisi pengunjung sendiri.

Dirancang untuk monitor kedua atau tablet yang menghadap pengunjung: nomor
dipilih dari daftar antrian yang baru selesai dilayani, lalu nilainya
ditekan langsung di layar itu. Petugas tidak perlu menyentuh apa pun.

Halaman ini tidak dapat mengubah antrian sama sekali. Satu-satunya tulisan
yang dihasilkannya adalah baris survey baru.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.queue_service import QueueInfo
from app.services.settings_service import SettingsService
from app.services.survey_service import PANJANG_FEEDBACK_MAKSIMUM, SurveyService
from app.ui.common import jalankan_aman, judul, keterangan, label_error, tombol
from app.ui.style import FONT_SIZE_HUGE, PRIMARY, SUCCESS, TEXT_MUTED
from app.ui.survey.rating_bar import RatingBar

PESAN_TERIMA_KASIH = "Terima kasih. Penilaian Anda sudah kami terima."

#: Lama ucapan terima kasih tampil sebelum layar bersiap untuk pengunjung
#: berikutnya, dalam milidetik.
JEDA_TERIMA_KASIH = 4000


class SurveyPage(QWidget):
    """Layar kios pengisian survey kepuasan."""

    def __init__(
        self,
        survey: SurveyService,
        settings: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.survey = survey
        self.settings = settings
        self.terpilih: QueueInfo | None = None
        self.pending: list[QueueInfo] = []

        self._bangun_tampilan()
        self.muat_ulang()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(14)

        susunan.addWidget(judul("Survey Kepuasan Pelayanan"))
        self.catatan = keterangan(
            "Pilih nomor antrian Anda, lalu tekan salah satu nilai di bawahnya."
        )
        susunan.addWidget(self.catatan)

        isi = QHBoxLayout()
        isi.setSpacing(20)
        isi.addWidget(self._bangun_daftar(), stretch=1)
        isi.addWidget(self._bangun_penilaian(), stretch=2)
        susunan.addLayout(isi, stretch=1)

    def _bangun_daftar(self) -> QWidget:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)

        susunan.addWidget(keterangan("Nomor yang baru selesai dilayani"))

        self.daftar = QListWidget()
        self.daftar.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.daftar.currentRowChanged.connect(self._saat_nomor_dipilih)
        susunan.addWidget(self.daftar, stretch=1)

        segarkan = tombol("Muat Ulang Daftar")
        segarkan.clicked.connect(self.muat_ulang)
        susunan.addWidget(segarkan)

        return panel

    def _bangun_penilaian(self) -> QWidget:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(12)

        self.label_nomor = QLabel("—")
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_nomor.setStyleSheet(
            f"font-size: {FONT_SIZE_HUGE + 12}px; font-weight: 700; color: {PRIMARY};"
        )
        susunan.addWidget(self.label_nomor)

        self.label_rincian = QLabel("Belum ada nomor yang dipilih")
        self.label_rincian.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_rincian.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_rincian)

        self.rating = RatingBar(tinggi=110)
        self.rating.dipilih.connect(self._saat_rating_dipilih)
        susunan.addWidget(self.rating)

        susunan.addWidget(keterangan("Masukan (boleh dikosongkan)"))
        self.masukan = QTextEdit()
        self.masukan.setFixedHeight(70)
        self.masukan.setPlaceholderText(
            "Tuliskan saran atau keluhan Anda di sini bila ada."
        )
        susunan.addWidget(self.masukan)

        self.pesan = label_error()
        susunan.addWidget(self.pesan)

        self.tombol_kirim = tombol("KIRIM PENILAIAN", variant="primary")
        self.tombol_kirim.setMinimumHeight(56)
        self.tombol_kirim.setEnabled(False)
        self.tombol_kirim.clicked.connect(self.kirim)
        susunan.addWidget(self.tombol_kirim)

        susunan.addStretch()
        return panel

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Segarkan daftar antrian yang belum dinilai."""
        if not self.settings.get_bool("survey.enabled", True):
            self._matikan_survey()
            return

        berhasil, data = jalankan_aman(
            self, self.survey.list_pending, "Gagal memuat daftar antrian"
        )
        if not berhasil:
            return

        self.pending = data or []
        self.daftar.clear()
        for antrian in self.pending:
            butir = QListWidgetItem(
                f"{antrian.queue_number}   ·   {antrian.category_name}"
            )
            butir.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
            self.daftar.addItem(butir)

        self._bersihkan_pilihan()
        if not self.pending:
            self.label_rincian.setText(
                "Belum ada pelayanan yang selesai dan menunggu penilaian."
            )

    def _matikan_survey(self) -> None:
        """Survey dinonaktifkan administrator lewat pengaturan."""
        self.daftar.clear()
        self.pending = []
        self._bersihkan_pilihan()
        self.catatan.setText(
            "Survey kepuasan sedang dinonaktifkan oleh administrator."
        )
        self.rating.setEnabled(False)
        self.masukan.setEnabled(False)

    def _bersihkan_pilihan(self) -> None:
        self.terpilih = None
        self.label_nomor.setText("—")
        self.label_rincian.setText("Belum ada nomor yang dipilih")
        self.rating.bersihkan()
        self.masukan.clear()
        self.pesan.setVisible(False)
        self.tombol_kirim.setEnabled(False)

    def _saat_nomor_dipilih(self, baris: int) -> None:
        if baris < 0 or baris >= len(self.pending):
            return

        self.terpilih = self.pending[baris]
        self.label_nomor.setText(self.terpilih.queue_number)

        rincian = [self.terpilih.category_name]
        if self.terpilih.counter_name:
            rincian.append(self.terpilih.counter_name)
        self.label_rincian.setText("  ·  ".join(rincian))

        self.rating.bersihkan()
        self.masukan.clear()
        self.pesan.setVisible(False)
        self.tombol_kirim.setEnabled(False)

    def _saat_rating_dipilih(self, _nilai: int) -> None:
        self.tombol_kirim.setEnabled(self.terpilih is not None)
        self.pesan.setVisible(False)

    # -----------------------------------------------------------------
    # Tindakan
    # -----------------------------------------------------------------

    def kirim(self) -> None:
        if self.terpilih is None:
            self._pesan_salah("Pilih nomor antrian Anda terlebih dahulu.")
            return
        if self.rating.nilai is None:
            self._pesan_salah("Pilih salah satu nilai kepuasan terlebih dahulu.")
            return

        masukan = self.masukan.toPlainText().strip()
        if len(masukan) > PANJANG_FEEDBACK_MAKSIMUM:
            self._pesan_salah(
                f"Masukan terlalu panjang, maksimum {PANJANG_FEEDBACK_MAKSIMUM} karakter."
            )
            return

        berhasil, _ = jalankan_aman(
            self,
            lambda: self.survey.submit(self.terpilih.id, self.rating.nilai, masukan),
            "Gagal menyimpan penilaian",
        )
        if not berhasil:
            return

        # Daftar dimuat ulang supaya nomor yang baru dinilai langsung hilang
        # dan pengunjung berikutnya tidak menilai nomor orang lain.
        self.muat_ulang()
        self._ucapkan_terima_kasih()

    def _ucapkan_terima_kasih(self) -> None:
        """
        Ucapan yang hilang sendiri, bukan kotak dialog.

        Layar ini tidak diawasi petugas. Kotak dialog yang menunggu diklik
        akan menyangkut begitu pengunjung berbalik pergi, dan orang
        berikutnya menemukan layar yang tidak bisa dipakai.
        """
        self.label_rincian.setText(PESAN_TERIMA_KASIH)
        self.label_rincian.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
        QTimer.singleShot(JEDA_TERIMA_KASIH, self._kembalikan_rincian)

    def _kembalikan_rincian(self) -> None:
        self.label_rincian.setStyleSheet(f"color: {TEXT_MUTED};")
        if self.terpilih is None:
            self.label_rincian.setText("Belum ada nomor yang dipilih")

    def _pesan_salah(self, teks: str) -> None:
        self.pesan.setText(teks)
        self.pesan.setVisible(True)
