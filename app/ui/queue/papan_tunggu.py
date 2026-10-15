"""
Papan tunggu mini di halaman Pelayanan: apa yang dilihat pengunjung di
layar antrian, tersedia di meja petugas tanpa berpindah tab.

Hanya membaca. Satu kolom per jenis layanan, nomor berurut menurut waktu
terbit beserta lama menunggunya. Jumlah baris mengikuti tinggi yang tersedia
(tanpa scrollbar); sisanya disebut "+N lagi". Daftar lengkap yang dapat
disaring tetap ada di tab Menunggu Dilayani.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.services.queue_service import QueueInfo
from app.ui.style import BORDER, SURFACE, TEXT, TEXT_MUTED, WARNING

TINGGI_BARIS = 20
#: Tinggi kepala kartu dan judul kolom; sisanya untuk baris nomor.
TINGGI_KEPALA = 62
KOLOM_MAKSIMUM = 4


def _label_menit(detik: float) -> str:
    menit = int(detik // 60)
    return "<1 mnt" if menit < 1 else f"{menit} mnt"


class PapanTunggu(QFrame):
    """Daftar tunggu per jenis layanan, hanya untuk dibaca."""

    def __init__(
        self,
        batas_lama_menit: int = 10,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("papanTunggu")
        self.setStyleSheet(
            f"QFrame#papanTunggu {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: 12px; }}"
        )
        # Tinggi minimum diabaikan: papan hanya mengisi sisa ruang kolom
        # kiri dan tidak boleh membuat halaman Pelayanan bergulir.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self._batas_lama = batas_lama_menit
        self._data: tuple | None = None

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(14, 10, 14, 10)
        susunan.setSpacing(6)

        kepala = QHBoxLayout()
        judul = QLabel("PAPAN TUNGGU")
        judul.setProperty("kapsi", "true")
        kepala.addWidget(judul)
        kepala.addStretch()
        self.label_total = QLabel("")
        self.label_total.setStyleSheet(f"color: {TEXT_MUTED};")
        kepala.addWidget(self.label_total)
        susunan.addLayout(kepala)

        self.kolom = QHBoxLayout()
        self.kolom.setSpacing(12)
        susunan.addLayout(self.kolom, stretch=1)

        self.label_kosong = QLabel("Tidak ada yang menunggu.")
        self.label_kosong.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_kosong)

        #: Judul kolom yang tampil, untuk test dan pembacaan layar.
        self.judul_kolom: list[str] = []

    # -----------------------------------------------------------------

    def setel(
        self,
        menunggu: Sequence[QueueInfo],
        kategori_dilayani: Sequence[int],
        sekarang: datetime,
    ) -> None:
        """
        `kategori_dilayani` kosong berarti loket ini melayani semua layanan.
        """
        self._data = (list(menunggu), tuple(kategori_dilayani), sekarang)
        self._gambar()

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().resizeEvent(event)
        if self._data is not None:
            self._gambar()

    def _baris_muat(self) -> int:
        """Baris nomor yang muat; bisa nol pada layar yang sangat pendek."""
        return max(0, (self.height() - TINGGI_KEPALA) // TINGGI_BARIS)

    def _gambar(self) -> None:
        menunggu, dilayani, sekarang = self._data
        while self.kolom.count():
            butir = self.kolom.takeAt(0)
            if butir.widget() is not None:
                butir.widget().deleteLater()
        self.judul_kolom = []

        self.label_total.setText(f"{len(menunggu)} menunggu" if menunggu else "")
        self.label_kosong.setVisible(not menunggu)
        if not menunggu:
            return

        per_layanan: dict[int, list[QueueInfo]] = {}
        for antrian in menunggu:
            per_layanan.setdefault(antrian.category_id, []).append(antrian)
        # Layanan yang paling lama ditunggu lebih dulu; sama lamanya, nama.
        urutan = sorted(
            per_layanan.values(),
            key=lambda d: (d[0].created_at, d[0].category_name),
        )
        tampil, tersisa = urutan[:KOLOM_MAKSIMUM], urutan[KOLOM_MAKSIMUM:]
        muat = self._baris_muat()

        if muat < 1:
            # Tidak ada tempat untuk kolom: satu baris ringkas saja, supaya
            # halaman Pelayanan tidak digulir demi papan ini.
            terlama = min(menunggu, key=lambda a: a.created_at)
            detik = max(0.0, (sekarang - terlama.created_at).total_seconds())
            ringkas = " · ".join(f"{d[0].category_name} {len(d)}" for d in urutan)
            ket = QLabel(
                f"Terlama {terlama.queue_number} ({_label_menit(detik)}) · {ringkas}"
            )
            ket.setWordWrap(True)
            ket.setStyleSheet(f"color: {TEXT};")
            self.kolom.addWidget(ket)
            self.judul_kolom = []
            return

        for daftar in tampil:
            contoh = daftar[0]
            milik_loket_lain = bool(dilayani) and contoh.category_id not in dilayani
            judul = f"{contoh.category_name} ({len(daftar)})"
            self.judul_kolom.append(judul)

            teks = [
                f"<b style='color:{TEXT_MUTED if milik_loket_lain else TEXT}'>"
                f"{escape(judul)}</b>"
            ]
            if milik_loket_lain:
                teks.append(
                    f"<span style='color:{TEXT_MUTED}'><i>bagian loket lain</i></span>"
                )
            baris_nomor = muat - (1 if milik_loket_lain else 0)
            for antrian in daftar[: max(1, baris_nomor)]:
                detik = max(0.0, (sekarang - antrian.created_at).total_seconds())
                lama = detik >= self._batas_lama * 60
                warna = (
                    TEXT_MUTED if milik_loket_lain else (WARNING if lama else TEXT)
                )
                teks.append(
                    f"<span style='color:{warna}'>"
                    f"{escape(antrian.queue_number)} &nbsp; {_label_menit(detik)}"
                    f"{' ●' if lama and not milik_loket_lain else ''}</span>"
                )
            sisa = len(daftar) - max(1, baris_nomor)
            if sisa > 0:
                teks.append(f"<span style='color:{TEXT_MUTED}'>+{sisa} lagi</span>")

            label = QLabel("<br>".join(teks))
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            # Tinggi mengikuti papan, bukan isi: jumlah baris sudah
            # dibatasi `_baris_muat`.
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
            self.kolom.addWidget(label, stretch=1)

        if tersisa:
            jumlah = sum(len(d) for d in tersisa)
            ket = QLabel(f"+{len(tersisa)} layanan lain ({jumlah})")
            ket.setStyleSheet(f"color: {TEXT_MUTED};")
            ket.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.kolom.addWidget(ket)
