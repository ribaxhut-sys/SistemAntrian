"""Dialog petugas saat mencabut prioritas dari nomor yang sudah dipanggil."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.services.queue_service import ALASAN_CABUT_PRIORITAS, QueueInfo
from app.ui.common import judul, keterangan, tombol


class DialogCabutPrioritas(QDialog):
    """
    Dua tindak lanjut sesudah prioritas dicabut dari nomor yang baru dipanggil.

    Pengunjungnya sudah berdiri di loket, jadi petugas memilih: mengembalikan
    nomornya ke antrian biasa (bawaan, adil bagi yang sudah menunggu lebih
    lama) lalu memanggil berikutnya, atau tetap melayaninya sekarang sebagai
    nomor biasa. Alasan pencabutan wajib dan dicatat di audit.
    """

    def __init__(self, parent: QWidget | None, antrian: QueueInfo) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cabut prioritas")
        self.setMinimumWidth(460)

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(28, 24, 28, 24)
        susunan.setSpacing(14)
        susunan.addWidget(judul(f"Cabut prioritas {antrian.queue_number}"))
        susunan.addWidget(
            keterangan(
                "Nomor ini sedang dipanggil. Pilih tindak lanjut sesudah "
                "prioritasnya dicabut."
            )
        )

        self.pilihan_kembalikan = QRadioButton(
            "Kembalikan ke antrian dan panggil berikutnya (disarankan)"
        )
        self.pilihan_kembalikan.setChecked(True)
        self.pilihan_layani = QRadioButton("Tetap layani sebagai nomor biasa")
        susunan.addWidget(self.pilihan_kembalikan)
        susunan.addWidget(
            keterangan(
                "Pengunjung kembali duduk dan dipanggil pada gilirannya, sesuai "
                "urutan datang."
            )
        )
        susunan.addWidget(self.pilihan_layani)

        susunan.addWidget(keterangan("Alasan pencabutan"))
        self.pilihan_alasan = QComboBox()
        for kunci, label in ALASAN_CABUT_PRIORITAS.items():
            self.pilihan_alasan.addItem(label, kunci)
        susunan.addWidget(self.pilihan_alasan)

        # Tiket yang sudah dipegang pengunjung masih bertuliskan "Prioritas".
        self.kotak_cetak_ulang = QCheckBox(
            "Cetak ulang tiket tanpa tanda prioritas"
        )
        self.kotak_cetak_ulang.setChecked(True)
        susunan.addWidget(self.kotak_cetak_ulang)

        baris = QHBoxLayout()
        baris.addStretch()
        batal = tombol("Batal")
        batal.clicked.connect(self.reject)
        baris.addWidget(batal)
        self.tombol_cabut = tombol("CABUT PRIORITAS", variant="primary", default=True)
        self.tombol_cabut.clicked.connect(self.accept)
        baris.addWidget(self.tombol_cabut)
        susunan.addLayout(baris)

    @property
    def kembalikan(self) -> bool:
        return self.pilihan_kembalikan.isChecked()

    @property
    def cetak_ulang(self) -> bool:
        return self.kotak_cetak_ulang.isChecked()

    @property
    def alasan(self) -> str:
        return str(self.pilihan_alasan.currentData())
