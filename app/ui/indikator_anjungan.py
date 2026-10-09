"""
Pita peringatan anjungan di jendela petugas.

Muncul di bawah kepala jendela hanya bila anjungan Android bermasalah:
judul satu kalimat, lalu langkah yang bisa langsung dikerjakan. Petugas
yang sedang melayani boleh menyembunyikannya; pita muncul lagi bila
masalahnya BERUBAH, bukan pada setiap pemeriksaan berkala.
"""

from __future__ import annotations

import html
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.services.status_anjungan import MASALAH, StatusAnjungan
from app.ui.common import tombol
from app.ui.style import DANGER, DANGER_SOFT, WARNING, WARNING_SOFT


class PitaAnjungan(QFrame):
    """Peringatan anjungan beserta sarannya."""

    def __init__(
        self,
        periksa_lagi: Callable[[], None],
        buka_layanan: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("pitaAnjungan")
        self._disembunyikan_untuk: tuple[str, str] | None = None

        susunan = QHBoxLayout(self)
        susunan.setContentsMargins(16, 10, 16, 10)
        susunan.setSpacing(16)

        teks = QVBoxLayout()
        teks.setSpacing(4)
        self.judul = QLabel()
        self.judul.setWordWrap(True)
        self.judul.setTextFormat(Qt.TextFormat.PlainText)
        self.judul.setStyleSheet("font-weight: 600;")
        self.saran = QLabel()
        self.saran.setWordWrap(True)
        self.saran.setTextFormat(Qt.TextFormat.RichText)
        teks.addWidget(self.judul)
        teks.addWidget(self.saran)
        susunan.addLayout(teks, stretch=1)

        tombol_tombol = QVBoxLayout()
        tombol_tombol.setSpacing(6)
        self.tombol_periksa = tombol("Periksa lagi")
        self.tombol_periksa.clicked.connect(periksa_lagi)
        tombol_tombol.addWidget(self.tombol_periksa)
        self.tombol_layanan = None
        if buka_layanan is not None:
            self.tombol_layanan = tombol("Buka Layanan Anjungan")
            self.tombol_layanan.clicked.connect(buka_layanan)
            tombol_tombol.addWidget(self.tombol_layanan)
        self.tombol_tutup = tombol("Sembunyikan")
        self.tombol_tutup.clicked.connect(self._sembunyikan)
        tombol_tombol.addWidget(self.tombol_tutup)
        tombol_tombol.addStretch()
        susunan.addLayout(tombol_tombol)

        self._status: StatusAnjungan | None = None
        self.hide()

    def tampilkan(self, status: StatusAnjungan | None) -> None:
        self._status = status
        if status is None or not status.bermasalah:
            self._disembunyikan_untuk = None
            self.hide()
            return

        kunci = (status.tingkat, status.judul)
        if self._disembunyikan_untuk == kunci:
            return
        self._disembunyikan_untuk = None

        warna, latar = (DANGER, DANGER_SOFT) if status.tingkat == MASALAH else (
            WARNING,
            WARNING_SOFT,
        )
        self.setStyleSheet(
            f"QFrame#pitaAnjungan {{ background: {latar}; "
            f"border-bottom: 2px solid {warna}; }}"
        )
        self.judul.setStyleSheet(f"font-weight: 600; color: {warna};")
        self.judul.setText(status.judul)
        butir = "".join(f"<li>{html.escape(s)}</li>" for s in status.saran)
        self.saran.setText(f"<b>Saran:</b><ul style='margin: 0;'>{butir}</ul>")
        self.show()

    def _sembunyikan(self) -> None:
        if self._status is not None:
            self._disembunyikan_untuk = (self._status.tingkat, self._status.judul)
        self.hide()
