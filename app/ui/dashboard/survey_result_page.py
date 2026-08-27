"""
Hasil survey kepuasan untuk supervisor.

Ringkasan harian sudah menampilkan rata-rata dan sebarannya. Yang belum
terbaca di mana pun adalah tulisan masukan pengunjung — dan justru di
situlah keterangan mengapa sebuah nilai diberikan.

Layar ini murni membaca. Tidak ada tombol yang mengubah survey maupun
antrian; nilai yang sudah diberikan pengunjung tidak boleh disunting siapa
pun, termasuk supervisor.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.survey_service import SurveyInfo, SurveyService
from app.ui.common import jalankan_aman, judul, keterangan
from app.ui.style import TEXT_MUTED
from app.ui.survey.rating_bar import WARNA_RATING
from app.utils.formatting import hari_dan_tanggal, jam

#: Pilihan banyaknya baris. Supervisor biasanya cukup melihat yang terbaru,
#: tetapi sesekali perlu menelusuri lebih jauh ke belakang.
PILIHAN_JUMLAH: tuple[int, ...] = (20, 50, 100, 200)


class SurveyResultPage(QWidget):
    """Daftar penilaian terbaru beserta masukan pengunjung."""

    def __init__(self, survey: SurveyService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.survey = survey

        self._bangun_tampilan()
        self.muat_ulang()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(12)

        atas = QHBoxLayout()
        atas.addWidget(judul("Hasil Survey Kepuasan"))
        atas.addStretch()
        atas.addWidget(QLabel("Tampilkan:"))

        self.pilih_jumlah = QComboBox()
        for jumlah in PILIHAN_JUMLAH:
            self.pilih_jumlah.addItem(f"{jumlah} terbaru", jumlah)
        self.pilih_jumlah.currentIndexChanged.connect(self.muat_ulang)
        atas.addWidget(self.pilih_jumlah)
        susunan.addLayout(atas)

        susunan.addWidget(
            keterangan(
                "Penilaian bersifat anonim: tidak ada identitas pengunjung yang "
                "tercatat, hanya nomor antriannya."
            )
        )

        self.tabel = QTableWidget(0, 6)
        self.tabel.setHorizontalHeaderLabels(
            ["Waktu", "Nomor", "Jenis Layanan", "Loket", "Nilai", "Masukan"]
        )
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setVisible(False)

        kepala = self.tabel.horizontalHeader()
        kepala.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # Kolom masukan yang melar, bukan kolom lain: isinya kalimat bebas
        # dan justru itu yang perlu terbaca utuh.
        kepala.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        susunan.addWidget(self.tabel, stretch=1)

        self.label_kosong = QLabel("")
        self.label_kosong.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_kosong)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        batas = self.pilih_jumlah.currentData() or PILIHAN_JUMLAH[0]
        berhasil, data = jalankan_aman(
            self,
            lambda: self.survey.list_terakhir(batas),
            "Gagal membaca hasil survey",
        )
        if not berhasil:
            return
        self._isi_tabel(data or [])

    def _isi_tabel(self, daftar: list[SurveyInfo]) -> None:
        self.tabel.setRowCount(len(daftar))
        for baris, survey in enumerate(daftar):
            nilai = (
                f"{hari_dan_tanggal(survey.submitted_at.date())}, "
                f"{jam(survey.submitted_at)}",
                survey.queue_number,
                survey.category_name or "-",
                survey.counter_name or "-",
                f"{survey.rating} · {survey.rating_label}",
                survey.feedback or "",
            )
            for kolom, teks in enumerate(nilai):
                butir = QTableWidgetItem(teks)
                if kolom == 4:
                    # Warna nilai sama dengan yang dilihat pengunjung saat
                    # mengisi, sehingga nilai rendah langsung tertangkap mata.
                    butir.setForeground(_warna(survey.rating))
                self.tabel.setItem(baris, kolom, butir)

        self.label_kosong.setText(
            "Belum ada penilaian yang masuk."
            if not daftar
            else f"{len(daftar)} penilaian ditampilkan."
        )


def _warna(rating: int) -> QColor:
    return QColor(WARNA_RATING.get(rating, "#000000"))
