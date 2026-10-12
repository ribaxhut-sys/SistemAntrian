"""
Pita peringatan "server database tidak terjangkau" di jendela petugas.

Bilah status sudah menyebutnya, tetapi dengan huruf kecil di pojok bawah
yang tidak dilihat petugas yang sedang berhadapan dengan pengunjung. Pada
pemasangan beberapa loket, server yang mati menghentikan SEMUA loket
sekaligus; yang paling dibutuhkan saat itu adalah tahu secepatnya dan tahu
langkah darurat apa yang harus diambil (docs/prosedur-darurat.md).

Pita tidak dapat disembunyikan, berbeda dari pita anjungan: selama ia
tampil, memanggil dan menyelesaikan nomor memang tidak bisa dilakukan,
jadi tidak ada pekerjaan yang terhalang olehnya. Ia hilang sendiri begitu
sambungan pulih.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.ui.common import tombol
from app.ui.style import DANGER, DANGER_SOFT

#: Kegagalan berturut-turut sebelum pita muncul. Satu SELECT 1 yang gagal
#: bisa sekadar paket yang hilang; dua berarti ±20 detik tanpa server, dan
#: itu sudah pasti dirasakan pengunjung.
GAGAL_SEBELUM_TAMPIL = 2

SARAN_PETUGAS = (
    "Jangan menutup aplikasi; sambungan pulih sendiri begitu server kembali.",
    "Pakai prosedur darurat: beri pengunjung nomor manual dan catat "
    "jam datangnya di lembar darurat.",
    "Hubungi administrator.",
)
SARAN_ADMIN = (
    "Pastikan komputer server menyala dan tersambung ke jaringan.",
    "Di server, periksa layanan PostgreSQL (services.msc → postgresql-x64-17) "
    "berjalan dan disk tidak penuh.",
    "Selama belum pulih, minta loket memakai nomor manual "
    "(docs/prosedur-darurat.md).",
)


class PitaDatabase(QFrame):
    """Peringatan server tidak terjangkau beserta langkah daruratnya."""

    def __init__(self, periksa_lagi: Callable[[], None], *, untuk_admin: bool) -> None:
        super().__init__()
        self.setObjectName("pitaDatabase")
        self.setStyleSheet(
            f"QFrame#pitaDatabase {{ background: {DANGER_SOFT}; "
            f"border-bottom: 2px solid {DANGER}; }}"
        )
        self._gagal_beruntun = 0

        susunan = QHBoxLayout(self)
        susunan.setContentsMargins(16, 10, 16, 10)
        susunan.setSpacing(16)

        teks = QVBoxLayout()
        teks.setSpacing(4)
        self.judul = QLabel(
            "Server database tidak terjangkau — loket tidak dapat memanggil "
            "maupun menyelesaikan nomor."
        )
        self.judul.setWordWrap(True)
        self.judul.setStyleSheet(f"font-weight: 600; color: {DANGER};")
        saran = SARAN_ADMIN if untuk_admin else SARAN_PETUGAS
        self.saran = QLabel(
            "<ul style='margin: 0;'>"
            + "".join(f"<li>{s}</li>" for s in saran)
            + "</ul>"
        )
        self.saran.setWordWrap(True)
        self.saran.setTextFormat(Qt.TextFormat.RichText)
        teks.addWidget(self.judul)
        teks.addWidget(self.saran)
        susunan.addLayout(teks, stretch=1)

        self.tombol_periksa = tombol("Periksa lagi")
        self.tombol_periksa.clicked.connect(periksa_lagi)
        susunan.addWidget(self.tombol_periksa, alignment=Qt.AlignmentFlag.AlignTop)

        self.hide()

    def perbarui(self, terhubung: bool) -> None:
        if terhubung:
            self._gagal_beruntun = 0
            self.hide()
            return
        self._gagal_beruntun += 1
        if self._gagal_beruntun >= GAGAL_SEBELUM_TAMPIL:
            self.show()
