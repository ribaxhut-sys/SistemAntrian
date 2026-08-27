"""
Dialog pengisian survey, dibuka petugas CRO.

Dialog ini diserahkan kepada pengunjung untuk diisi sendiri, karena itu
tidak ada satu pun tombol di sini yang menyentuh antrian. Yang bisa terjadi
hanyalah menyimpan nilai atau menutup dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.queue_service import QueueInfo
from app.services.survey_service import PANJANG_FEEDBACK_MAKSIMUM, SurveyService
from app.ui.common import jalankan_aman, judul, keterangan, label_error, tombol
from app.ui.style import FONT_SIZE_HUGE, PRIMARY
from app.ui.survey.rating_bar import RatingBar


class SurveyDialog(QDialog):
    """Penilaian satu antrian oleh pengunjung."""

    def __init__(
        self,
        survey: SurveyService,
        antrian: QueueInfo,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.survey = survey
        self.antrian = antrian

        self.setWindowTitle("Survey Kepuasan Pelayanan")
        self.setMinimumWidth(620)
        self._bangun_tampilan()

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(28, 24, 28, 24)
        susunan.setSpacing(14)

        susunan.addWidget(judul("Bagaimana pelayanan yang Anda terima?"))

        nomor = QLabel(self.antrian.queue_number)
        nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nomor.setStyleSheet(
            f"font-size: {FONT_SIZE_HUGE}px; font-weight: 700; color: {PRIMARY};"
        )
        susunan.addWidget(nomor)

        rincian = [self.antrian.category_name]
        if self.antrian.counter_name:
            rincian.append(self.antrian.counter_name)
        if self.antrian.served_by_name:
            rincian.append(self.antrian.served_by_name)
        keterangan_antrian = keterangan("  ·  ".join(rincian))
        keterangan_antrian.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(keterangan_antrian)

        self.rating = RatingBar()
        self.rating.dipilih.connect(self._saat_rating_dipilih)
        susunan.addWidget(self.rating)

        susunan.addWidget(keterangan("Masukan (boleh dikosongkan)"))
        self.masukan = QTextEdit()
        self.masukan.setFixedHeight(80)
        self.masukan.setPlaceholderText(
            "Tuliskan saran atau keluhan Anda di sini bila ada."
        )
        susunan.addWidget(self.masukan)

        self.pesan = label_error()
        susunan.addWidget(self.pesan)

        baris = QHBoxLayout()
        baris.addStretch()
        lewati = tombol("Lewati")
        lewati.clicked.connect(self.reject)
        baris.addWidget(lewati)

        self.tombol_kirim = tombol("KIRIM PENILAIAN", variant="primary")
        self.tombol_kirim.setMinimumHeight(46)
        self.tombol_kirim.setEnabled(False)
        self.tombol_kirim.clicked.connect(self.kirim)
        baris.addWidget(self.tombol_kirim)
        susunan.addLayout(baris)

    def _saat_rating_dipilih(self, _nilai: int) -> None:
        self.tombol_kirim.setEnabled(True)
        self.pesan.setVisible(False)

    def kirim(self) -> None:
        if self.rating.nilai is None:
            self.pesan.setText("Pilih salah satu nilai kepuasan terlebih dahulu.")
            self.pesan.setVisible(True)
            return

        masukan = self.masukan.toPlainText().strip()
        if len(masukan) > PANJANG_FEEDBACK_MAKSIMUM:
            self.pesan.setText(
                f"Masukan terlalu panjang, maksimum {PANJANG_FEEDBACK_MAKSIMUM} karakter."
            )
            self.pesan.setVisible(True)
            return

        berhasil, _ = jalankan_aman(
            self,
            lambda: self.survey.submit(self.antrian.id, self.rating.nilai, masukan),
            "Gagal menyimpan penilaian",
        )
        if berhasil:
            self.accept()
