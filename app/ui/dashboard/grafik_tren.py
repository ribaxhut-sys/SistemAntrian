"""
Grafik batang tren laporan: nomor selesai per hari (atau per minggu).

Digambar sendiri seperti GrafikBatang pada dashboard; dua puluh sampai lima
puluh batang tidak sebanding dengan menambah pustaka grafik.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.ui.style import BORDER, PRIMARY, TEXT, TEXT_MUTED
from app.ui.tema_petugas import warna_tema

#: Lebar minimal tiap label sumbu-x; label dijarangkan agar tidak bertumpuk.
LEBAR_LABEL = 34
#: Batang sesempit ini tidak lagi diberi angka di atasnya.
LEBAR_ANGKA = 22


class GrafikTren(QWidget):
    """Deret (label, nilai) sebagai batang, dengan batang tertinggi diberi angka."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.deret: list[tuple[str, int]] = []

    def setel(self, deret: list[tuple[str, int]]) -> None:
        self.deret = list(deret)
        self.update()

    @property
    def kosong(self) -> bool:
        return not any(nilai for _, nilai in self.deret)

    def langkah_label(self, lebar: float) -> int:
        """Setiap berapa batang satu label ditulis, menurut lebar yang tersedia."""
        sela = lebar / max(1, len(self.deret))
        return max(1, math.ceil(LEBAR_LABEL / max(sela, 1)))

    def paintEvent(self, event) -> None:  # noqa: N802 - nama Qt
        pelukis = QPainter(self)
        pelukis.setRenderHint(QPainter.RenderHint.Antialiasing)
        lebar, tinggi = self.width(), self.height()
        batas_bawah = tinggi - 22
        batas_atas = 20
        jumlah = max(1, len(self.deret))
        sela = lebar / jumlah
        terbesar = max([1, *(nilai for _, nilai in self.deret)])
        langkah = self.langkah_label(lebar)

        pelukis.setPen(QPen(QColor(warna_tema(BORDER)), 1))
        pelukis.drawLine(0, batas_bawah, lebar, batas_bawah)

        for indeks, (label, nilai) in enumerate(self.deret):
            kiri = indeks * sela + sela * 0.15
            lebar_batang = sela * 0.7
            tinggi_batang = (batas_bawah - batas_atas) * nilai / terbesar
            if nilai:
                pelukis.setPen(Qt.PenStyle.NoPen)
                pelukis.setBrush(QColor(warna_tema(PRIMARY)))
                pelukis.drawRoundedRect(
                    QRectF(kiri, batas_bawah - tinggi_batang, lebar_batang, tinggi_batang),
                    3,
                    3,
                )
                if sela >= LEBAR_ANGKA or nilai == terbesar:
                    pelukis.setPen(QColor(warna_tema(TEXT, teks=True)))
                    pelukis.drawText(
                        QRectF(indeks * sela - 8, batas_bawah - tinggi_batang - 16, sela + 16, 14),
                        Qt.AlignmentFlag.AlignCenter,
                        str(nilai),
                    )
            if indeks % langkah == 0:
                pelukis.setPen(QColor(warna_tema(TEXT_MUTED, teks=True)))
                pelukis.drawText(
                    QRectF(indeks * sela - 8, batas_bawah + 4, sela + 16, 16),
                    Qt.AlignmentFlag.AlignCenter,
                    label,
                )
        pelukis.end()
