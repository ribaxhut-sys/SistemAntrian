"""
Pilihan layar saat aplikasi dibuka.

Yang dipilih di sini sebenarnya sifat MESIN, bukan sifat momen: komputer
layar antrian selalu menjadi layar pengunjung, komputer loket selalu layar
petugas. Karena itu dialog ini dapat dilewati sepenuhnya dengan menjalankan
aplikasi memakai --layar, dan itulah yang dipasang pada shortcut komputer
kios: ia pulih sendiri setelah mati listrik tanpa perlu ada yang mengklik.

Dialog ini untuk mesin yang belum diatur, atau yang sesekali dipakai untuk
keduanya.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from app.core.config import APP_NAME
from app.ui.common import judul, keterangan, tombol
from app.ui.style import PRIMARY_DARK, TEXT_MUTED

#: Hasil pilihan.
LAYAR_PENGUNJUNG = "pengunjung"
LAYAR_PETUGAS = "petugas"


class ModeDialog(QDialog):
    """Tanya layar mana yang akan dibuka pada komputer ini."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pilihan: str | None = None

        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(560)
        self._bangun_tampilan()

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(36, 32, 36, 32)
        susunan.setSpacing(14)

        nama = QLabel(APP_NAME)
        nama.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nama.setStyleSheet(
            f"color: {PRIMARY_DARK}; font-size: 26px; font-weight: 700;"
        )
        susunan.addWidget(nama)

        tanya = judul("Layar mana yang akan dibuka di komputer ini?")
        tanya.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(tanya)
        susunan.addSpacing(8)

        susunan.addWidget(
            self._bangun_pilihan(
                "LAYAR PENGUNJUNG",
                "Papan nomor antrian dan tempat pengunjung mengambil nomor "
                "sendiri. Tidak perlu masuk.",
                LAYAR_PENGUNJUNG,
                utama=True,
            )
        )
        susunan.addWidget(
            self._bangun_pilihan(
                "LAYAR PETUGAS",
                "Melayani antrian, mengelola data, dan melihat laporan. "
                "Wajib masuk dengan akun petugas.",
                LAYAR_PETUGAS,
            )
        )

        susunan.addSpacing(6)
        catatan = keterangan(
            "Komputer layar antrian sebaiknya dijalankan dengan pintasan "
            "AntrianCRO.exe --layar agar langsung terbuka sendiri setelah "
            "komputer menyala."
        )
        catatan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        catatan.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        susunan.addWidget(catatan)

    def _bangun_pilihan(
        self, teks: str, penjelasan: str, nilai: str, *, utama: bool = False
    ) -> QWidget:
        bungkus = QWidget()
        susunan = QVBoxLayout(bungkus)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(4)

        btn = tombol(teks, variant="primary" if utama else "")
        btn.setMinimumHeight(64)
        btn.setStyleSheet("font-size: 18px; font-weight: 700;")
        btn.clicked.connect(lambda: self._pilih(nilai))
        susunan.addWidget(btn)

        label = keterangan(penjelasan)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(label)

        return bungkus

    def _pilih(self, nilai: str) -> None:
        self.pilihan = nilai
        self.accept()
