"""
Deretan tombol nilai kepuasan 1–5.

Dipakai bersama oleh dialog CRO dan layar kios agar keduanya menampilkan
pilihan yang persis sama. Pengunjung yang pernah mengisi di satu layar tidak
perlu menebak-nebak arti tombol di layar yang lain.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.models import RATING_LABELS
from app.services.survey_service import RATING_MAX, RATING_MIN
from app.ui.style import BORDER, DANGER, PRIMARY, SUCCESS, WARNING

#: Warna per nilai. Merah ke hijau adalah isyarat yang dikenali tanpa perlu
#: membaca, penting karena pengunjung mengisi sambil berdiri dan terburu-buru.
WARNA_RATING: dict[int, str] = {
    1: DANGER,
    2: "#E65100",
    3: WARNING,
    4: "#558B2F",
    5: SUCCESS,
}


class RatingBar(QWidget):
    """Lima tombol nilai; memancarkan `dipilih` berisi angka 1–5."""

    dipilih = Signal(int)

    def __init__(self, *, tinggi: int = 96, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.nilai: int | None = None
        self._tombol: dict[int, QPushButton] = {}

        susunan = QHBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(10)

        for angka in range(RATING_MIN, RATING_MAX + 1):
            susunan.addWidget(self._bangun_tombol(angka, tinggi), stretch=1)

    def _bangun_tombol(self, angka: int, tinggi: int) -> QWidget:
        bungkus = QWidget()
        susunan = QVBoxLayout(bungkus)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(6)

        btn = QPushButton(str(angka))
        btn.setMinimumHeight(tinggi)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(True)
        btn.clicked.connect(lambda _, a=angka: self.pilih(a))
        self._tombol[angka] = btn
        self._warnai(angka, terpilih=False)
        susunan.addWidget(btn)

        label = QLabel(RATING_LABELS[angka])
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setProperty("muted", "true")
        susunan.addWidget(label)

        return bungkus

    def _warnai(self, angka: int, *, terpilih: bool) -> None:
        warna = WARNA_RATING[angka]
        btn = self._tombol[angka]
        if terpilih:
            btn.setStyleSheet(
                f"font-size: 34px; font-weight: 700; color: white;"
                f" background: {warna}; border: 3px solid {PRIMARY};"
                " border-radius: 8px;"
            )
        else:
            btn.setStyleSheet(
                f"font-size: 34px; font-weight: 700; color: {warna};"
                f" background: white; border: 2px solid {BORDER};"
                " border-radius: 8px;"
            )

    def pilih(self, angka: int) -> None:
        self.nilai = angka
        for a, btn in self._tombol.items():
            btn.setChecked(a == angka)
            self._warnai(a, terpilih=a == angka)
        self.dipilih.emit(angka)

    def bersihkan(self) -> None:
        self.nilai = None
        for a, btn in self._tombol.items():
            btn.setChecked(False)
            self._warnai(a, terpilih=False)
