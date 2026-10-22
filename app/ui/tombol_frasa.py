"""
Tombol kalimat cepat: seluruh kalimat tampil, membungkus ke baris berikutnya.

QPushButton tidak membungkus teks, dan memotongnya dengan "…" membuat
petugas menyisipkan kalimat yang belum ia baca utuh. Tombol ini menaruh
satu QLabel pembungkus di dalamnya, lalu meneruskan tinggi-menurut-lebar
ke tata letak supaya tombolnya setinggi baris yang dibutuhkan.

Warnanya ditulis sendiri, bukan lewat gaya varian umum: label di dalam
tombol tidak ikut mewarisi warna teks dari aturan QPushButton.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from app.ui.style import (
    BORDER,
    FONT_SIZE_SMALL,
    PRIMARY,
    PRIMARY_SOFT,
    RADIUS_SM,
    SURFACE,
    SURFACE_ALT,
    TEXT,
    TEXT_MUTED,
)

TANDA_TERPAKAI = "✓ "


class TombolFrasa(QPushButton):
    """Satu kalimat cepat. `tandai_terpakai(True)` mematikannya dengan tanda ✓."""

    def __init__(self, kalimat: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kalimat = kalimat
        self._terpakai = False
        self.setObjectName("tombolFrasa")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoDefault(False)
        self.setToolTip(kalimat)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.label = QLabel(kalimat)
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        tata = QHBoxLayout(self)
        tata.setContentsMargins(8, 4, 8, 4)
        tata.addWidget(self.label)
        self._gayai()

    @property
    def terpakai(self) -> bool:
        return self._terpakai

    def tandai_terpakai(self, terpakai: bool) -> None:
        """Kalimat yang sudah ada di catatan tidak perlu disisipkan lagi."""
        if terpakai == self._terpakai:
            return
        self._terpakai = terpakai
        self.setEnabled(not terpakai)
        self.label.setText((TANDA_TERPAKAI if terpakai else "") + self.kalimat)
        self.setToolTip("Sudah ada di catatan" if terpakai else self.kalimat)
        self._gayai()

    def _gayai(self) -> None:
        warna_teks = TEXT_MUTED if self._terpakai else TEXT
        self.setStyleSheet(
            f"QPushButton#tombolFrasa {{ background: {SURFACE_ALT};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS_SM}px;"
            " text-align: left; }"
            f"QPushButton#tombolFrasa:hover:enabled {{ background: {PRIMARY_SOFT};"
            f" border-color: {PRIMARY}; }}"
            f"QPushButton#tombolFrasa:disabled {{ background: {SURFACE}; }}"
        )
        self.label.setStyleSheet(
            f"color: {warna_teks}; font-size: {FONT_SIZE_SMALL}px;"
            " background: transparent; border: none;"
        )

    # Tinggi mengikuti jumlah baris pada lebar yang tersedia: dibiarkan pada
    # perilaku bawaan QWidget, yang meneruskan heightForWidth ke tata letak
    # tombol. Mengganti heightForWidth/sizeHint sendiri membuat Qt berputar
    # tanpa ujung (proses tes berhenti tanpa pesan).
