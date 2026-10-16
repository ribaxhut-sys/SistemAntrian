"""
Kartu "Berikutnya & hari ini" di kolom kerja halaman Pelayanan.

Menjawab dua pertanyaan petugas tanpa berpindah tab: siapa yang akan
terpanggil bila Panggil Berikutnya ditekan, dan bagaimana kerjanya hari ini.
Hanya membaca. Isinya mengisi sisa tinggi kolom dan menyusut sendiri:
makin pendek ruangnya, makin sedikit baris yang tampil, dan pada ruang
yang terlalu sempit kartu tidak tampak sama sekali (tanpa bingkai),
sehingga halaman tidak pernah dibuat bergulir demi kartu ini.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.models import QueueStatus
from app.ui.style import BORDER, SURFACE, TEXT, TEXT_MUTED, WARNING

TINGGI_BARIS = 20
#: Margin atas-bawah kartu ditambah baris judul.
TINGGI_KEPALA = 44
#: Di bawah tinggi ini kartu tidak digambar (bingkai ikut hilang).
TINGGI_MINIMUM = TINGGI_KEPALA + 2 * TINGGI_BARIS
BERIKUTNYA_MAKSIMUM = 3


def _label_menit(detik: float) -> str:
    menit = int(detik // 60)
    return "<1 mnt" if menit < 1 else f"{menit} mnt"


class KartuBerikutnya(QFrame):
    """Tiga nomor berikutnya untuk loket ini, dan ringkasan kerja hari ini."""

    def __init__(
        self, batas_lama_menit: int = 10, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("kartuBerikutnya")
        self.setStyleSheet(
            f"QFrame#kartuBerikutnya {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: 12px; }}"
            'QFrame#kartuBerikutnya[kecil="true"] { background: transparent;'
            " border: none; }"
        )
        # Tinggi minimum diabaikan: kartu hanya memakai sisa ruang kolom.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self._batas_lama = batas_lama_menit
        self._data: tuple | None = None
        self._tanda: tuple | None = None

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(14, 10, 14, 10)
        susunan.setSpacing(0)

        self.label = QLabel("")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        susunan.addWidget(self.label)

        #: Baris yang tampil (teks polos), untuk test dan pembacaan layar.
        self.baris_tampil: list[str] = []
        self.kecil = False

    # -----------------------------------------------------------------

    def setel(
        self,
        menunggu: Sequence,
        kategori_dilayani: Sequence[int],
        sekarang: datetime,
        ringkasan=None,
    ) -> None:
        """
        `kategori_dilayani` kosong berarti loket melayani semua layanan.
        `ringkasan` adalah DashboardPetugas, atau None bila belum tersedia.
        """
        self._data = (list(menunggu), tuple(kategori_dilayani), sekarang, ringkasan)
        self._gambar()

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().resizeEvent(event)
        if self._data is not None:
            self._gambar()

    def _baris_muat(self) -> int:
        return max(0, (self.height() - TINGGI_KEPALA) // TINGGI_BARIS)

    def _gambar(self) -> None:
        menunggu, dilayani, sekarang, ringkasan = self._data
        milik = sorted(
            (
                a
                for a in menunggu
                if not dilayani or a.category_id in dilayani
            ),
            key=lambda a: a.created_at,
        )

        # Setiap butir: (prioritas, urutan tampil, HTML, teks polos).
        butir: list[tuple[int, int, str, str]] = []

        def tambah(prioritas: int, urutan: int, teks: str, warna: str = TEXT) -> None:
            butir.append(
                (
                    prioritas,
                    urutan,
                    f"<span style='color:{warna}'>{escape(teks)}</span>",
                    teks,
                )
            )

        for i, antrian in enumerate(milik[:BERIKUTNYA_MAKSIMUM], start=1):
            detik = max(0.0, (sekarang - antrian.created_at).total_seconds())
            lama = detik >= self._batas_lama * 60
            tambah(
                1 if i == 1 else 3,
                10 + i,
                f"{i}. {antrian.queue_number} · {antrian.category_name}"
                f" · {_label_menit(detik)}{' ●' if lama else ''}",
                WARNING if lama else TEXT,
            )
        if not milik:
            tambah(1, 11, "Tidak ada nomor menunggu untuk loket ini", TEXT_MUTED)
        elif len(milik) > BERIKUTNYA_MAKSIMUM:
            tambah(5, 20, f"+{len(milik) - BERIKUTNYA_MAKSIMUM} lagi menunggu", TEXT_MUTED)

        if ringkasan is not None:
            tambah(
                2,
                30,
                f"Hari ini: dilayani {ringkasan.selesai}"
                f" · rata-rata {ringkasan.label_rata_layanan}",
            )
            selesai = [
                r
                for r in ringkasan.riwayat
                if r.status is QueueStatus.COMPLETED and r.waktu is not None
            ]
            if selesai:
                terakhir = max(selesai, key=lambda r: r.waktu)
                tambah(
                    4,
                    31,
                    f"Terakhir selesai: {terakhir.nomor}"
                    f" · {terakhir.waktu.strftime('%H:%M')}",
                    TEXT_MUTED,
                )

        muat = self._baris_muat()
        # Prioritas dulu sampai penuh, lalu kembalikan ke urutan tampil.
        terpilih = sorted(butir, key=lambda b: (b[0], b[1]))[:muat]
        terpilih.sort(key=lambda b: b[1])

        kecil = self.height() < TINGGI_MINIMUM
        if kecil != self.kecil or self.property("kecil") != kecil:
            self.kecil = kecil
            self.setProperty("kecil", kecil)
            self.style().unpolish(self)
            self.style().polish(self)

        tanda = (kecil, tuple(b[2] for b in terpilih))
        if tanda == self._tanda:
            return
        self._tanda = tanda
        self.baris_tampil = [b[3] for b in terpilih]
        if kecil or not terpilih:
            self.label.setText("")
            return
        judul = (
            f"<b style='color:{TEXT_MUTED}'>BERIKUTNYA &amp; HARI INI</b>"
        )
        self.label.setText("<br>".join([judul, *(b[2] for b in terpilih)]))
