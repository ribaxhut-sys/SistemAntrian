"""Pita pemberitahuan pembaruan aplikasi Windows."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from app.services.pembaruan_windows import InfoPembaruan
from app.ui.common import tombol
from app.ui.style import PRIMARY, PRIMARY_SOFT


class PitaPembaruan(QFrame):
    def __init__(self, pasang: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("pitaPembaruan")
        self.setStyleSheet(
            f"QFrame#pitaPembaruan {{ background: {PRIMARY_SOFT}; "
            f"border-bottom: 2px solid {PRIMARY}; }}"
        )
        susunan = QHBoxLayout(self)
        susunan.setContentsMargins(16, 9, 16, 9)
        susunan.setSpacing(12)
        self.pesan = QLabel()
        self.pesan.setWordWrap(True)
        self.pesan.setStyleSheet(f"font-weight: 600; color: {PRIMARY};")
        susunan.addWidget(self.pesan, stretch=1)
        self.tombol = tombol("Unduh & Perbarui", variant="primary")
        self.tombol.clicked.connect(pasang)
        susunan.addWidget(self.tombol, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.info: InfoPembaruan | None = None
        self.hide()

    def tampilkan(self, info: InfoPembaruan | None) -> None:
        self.info = info
        if info is None:
            self.hide()
            return
        self.pesan.setText(
            f"Pembaruan Sistem Antrian CRO versi {info.versi} tersedia di server."
        )
        self.tombol.setEnabled(True)
        self.tombol.setText("Unduh & Perbarui")
        self.show()

    def sedang_mengunduh(self) -> None:
        self.tombol.setEnabled(False)
        self.tombol.setText("Sedang mengunduh…")
