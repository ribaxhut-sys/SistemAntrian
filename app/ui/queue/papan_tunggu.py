"""
Papan tunggu mini di halaman Pelayanan: apa yang dilihat pengunjung di
layar antrian, tersedia di meja petugas tanpa berpindah tab.

Hanya membaca. Satu kartu untuk SETIAP jenis layanan yang sedang ada
antriannya, disusun sebagai grid yang menyesuaikan lebar dan tinggi yang
tersedia (tanpa scrollbar): makin sempit ruangnya, makin ringkas isi
kartu. Daftar lengkap yang dapat disaring tetap ada di tab Menunggu
Dilayani.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from html import escape
from math import ceil

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.services.queue_service import QueueInfo
from app.ui.style import (
    BORDER,
    PRIMARY,
    PRIMARY_SOFT,
    SURFACE,
    TEXT,
    TEXT_MUTED,
    WARNING,
    WARNING_SOFT,
)

TINGGI_BARIS = 20
#: Padding atas-bawah kartu.
PADDING_KARTU = 12
#: Ruang di luar grid: margin, kepala papan, dan jarak.
TINGGI_KEPALA = 48
LEBAR_KARTU_MIN = 160
JARAK = 8
#: Batas baris kartu pada mode tinggi menurut isi.
MAKS_BARIS_MENURUT_ISI = 4


class _Kartu(QLabel):
    """Satu kartu: dapat diklik dengan mouse maupun keyboard."""

    diklik = Signal()

    def __init__(self, html: str, parent: QWidget | None = None) -> None:
        super().__init__(html, parent)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - nama Qt
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.diklik.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - nama Qt
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.diklik.emit()
            return
        super().keyPressEvent(event)


def _label_menit(detik: float) -> str:
    menit = int(detik // 60)
    return "<1 mnt" if menit < 1 else f"{menit} mnt"


class PapanTunggu(QFrame):
    """
    Kartu antrian per jenis layanan. Mengklik kartu memilih layanan itu
    (`layananDipilih`); kartu "Semua" mencabut pilihan.
    """

    #: id kategori yang dipilih, atau None untuk "Semua".
    layananDipilih = Signal(object)

    def __init__(
        self,
        batas_lama_menit: int = 10,
        parent: QWidget | None = None,
        *,
        tinggi_menurut_isi: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("papanTunggu")
        self.setStyleSheet(
            f"QFrame#papanTunggu {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: 12px; }}"
        )
        # Dua mode tinggi. Bawaan: papan mengisi sisa ruang yang diberikan
        # dan tidak boleh membuat halaman bergulir. `tinggi_menurut_isi`:
        # tinggi mengikuti jumlah kartu, sisanya untuk widget lain.
        self._menurut_isi = tinggi_menurut_isi
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
            if tinggi_menurut_isi
            else QSizePolicy.Policy.Ignored,
        )
        self._batas_lama = batas_lama_menit
        self._data: tuple | None = None
        self._tanda: tuple | None = None
        self._pilihan: int | None = None

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

        self.grid = QGridLayout()
        self.grid.setSpacing(JARAK)
        susunan.addLayout(self.grid, stretch=1)

        self.label_kosong = QLabel("Tidak ada yang menunggu.")
        self.label_kosong.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_kosong)

        #: Judul kartu yang tampil ("Layanan (jumlah)"), untuk test.
        self.judul_kolom: list[str] = []
        #: Teks tiap kartu, untuk test dan pembacaan layar.
        self.teks_kartu: list[str] = []

    # -----------------------------------------------------------------

    @property
    def pilihan(self) -> int | None:
        """Id layanan yang dipilih, atau None bila "Semua"."""
        return self._pilihan

    def pilih(self, kategori_id: int | None) -> None:
        if kategori_id == self._pilihan:
            return
        self._pilihan = kategori_id
        if self._data is not None:
            self._gambar()
        self.layananDipilih.emit(kategori_id)

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

    def _susunan(self, jumlah: int) -> tuple[int, int]:
        """
        (baris, kolom) terbaik: sedikit baris dulu, supaya tiap kartu
        setinggi mungkin. Bila semua layanan tidak muat, isi sebanyak
        kapasitas.
        """
        lebar = max(0, self.width() - 28)
        tinggi = max(0, self.height() - TINGGI_KEPALA)
        maks_kolom = max(1, (lebar + JARAK) // (LEBAR_KARTU_MIN + JARAK))
        tinggi_min = PADDING_KARTU + TINGGI_BARIS
        maks_baris = max(1, (tinggi + JARAK) // (tinggi_min + JARAK))
        for baris in range(1, maks_baris + 1):
            kolom = ceil(jumlah / baris)
            if kolom <= maks_kolom:
                return baris, kolom
        return maks_baris, maks_kolom

    def _susunan_menurut_isi(self, jumlah: int) -> tuple[int, int, int]:
        """(baris, kolom, baris teks) bila tinggi papan mengikuti isinya."""
        lebar = max(0, self.width() - 28)
        maks_kolom = max(1, (lebar + JARAK) // (LEBAR_KARTU_MIN + JARAK))
        kolom = max(1, min(jumlah, maks_kolom))
        baris = max(1, min(MAKS_BARIS_MENURUT_ISI, ceil(jumlah / kolom)))
        isi = 2
        if jumlah:
            tinggi = (
                TINGGI_KEPALA
                + baris * (PADDING_KARTU + isi * TINGGI_BARIS)
                + (baris - 1) * JARAK
            )
        else:
            tinggi = TINGGI_KEPALA
        if self.height() != tinggi:
            self.setFixedHeight(tinggi)
        return baris, kolom, isi

    def _baris_isi(self, baris: int) -> int:
        """Baris teks yang muat dalam satu kartu pada susunan ini."""
        tinggi = max(0, self.height() - TINGGI_KEPALA)
        tinggi_kartu = (tinggi - JARAK * (baris - 1)) // max(1, baris)
        return max(1, (tinggi_kartu - PADDING_KARTU) // TINGGI_BARIS)

    def _gambar(self) -> None:
        menunggu, dilayani, sekarang = self._data

        self.label_total.setText(f"{len(menunggu)} menunggu" if menunggu else "")
        self.label_kosong.setVisible(not menunggu)

        per_layanan: dict[int, list[QueueInfo]] = {}
        for antrian in menunggu:
            per_layanan.setdefault(antrian.category_id, []).append(antrian)
        # Layanan loket ini lebih dulu; lalu yang paling lama ditunggu,
        # sama lamanya menurut nama.
        urutan = sorted(
            per_layanan.values(),
            key=lambda d: (
                bool(dilayani) and d[0].category_id not in dilayani,
                min(a.created_at for a in d),
                d[0].category_name,
            ),
        )

        # Pilihan yang layanannya sudah tidak punya antrian kembali ke
        # "Semua"; kartu "Semua" sendiri menempati satu tempat di grid.
        if self._pilihan is not None and self._pilihan not in per_layanan:
            self._pilihan = None
            self.layananDipilih.emit(None)

        n_kartu = len(urutan) + 1 if urutan else 0
        if self._menurut_isi:
            baris, kolom, isi = self._susunan_menurut_isi(n_kartu)
        else:
            baris, kolom = self._susunan(n_kartu) if urutan else (1, 1)
            isi = self._baris_isi(baris)
        kapasitas = max(0, baris * kolom - 1) if urutan else 0
        tampil, tersisa = urutan[:kapasitas], urutan[kapasitas:]

        kartu = [
            self._kartu(sorted(d, key=lambda a: a.created_at), dilayani, sekarang, isi)
            for d in tampil
        ]
        if tersisa:
            jumlah = sum(len(d) for d in tersisa)
            self.label_total.setText(
                f"{len(menunggu)} menunggu · +{len(tersisa)} layanan lain ({jumlah})"
            )

        semua = self._kartu_semua(menunggu, sekarang, isi) if urutan else None
        tanda = (
            baris,
            kolom,
            self._pilihan,
            semua[1] if semua else None,
            tuple(k[:3] for k in kartu),
        )
        if tanda == self._tanda:
            return  # tidak ada yang berubah: jangan berkedip
        self._tanda = tanda

        while self.grid.count():
            butir = self.grid.takeAt(0)
            if butir.widget() is not None:
                butir.widget().deleteLater()
        for i in range(self.grid.rowCount()):
            self.grid.setRowStretch(i, 0)
        for j in range(self.grid.columnCount()):
            self.grid.setColumnStretch(j, 0)
        self.judul_kolom = [k[0] for k in kartu]
        self.teks_kartu = [k[1] for k in kartu]

        self.kartu_semua: _Kartu | None = None
        self.kartu_layanan: dict[int, _Kartu] = {}
        entri: list[tuple[int | None, tuple[str, str, str, str]]] = []
        if semua is not None:
            entri.append((None, semua))
        entri.extend((d[0].category_id, k) for d, k in zip(tampil, kartu))
        for indeks, (kid, (_judul, html, gaya, tip)) in enumerate(entri):
            label = _Kartu(html)
            terpilih = kid == self._pilihan
            label.setStyleSheet(
                gaya
                if not terpilih
                else gaya + f" border: 2px solid {PRIMARY}; font-weight: 600;"
            )
            label.setToolTip(tip + " — klik untuk menyaring daftar")
            label.setProperty("terpilih", terpilih)
            label.diklik.connect(lambda k=kid: self.pilih(k))
            if kid is None:
                self.kartu_semua = label
            else:
                self.kartu_layanan[kid] = label
            self.grid.addWidget(label, indeks // kolom, indeks % kolom)
        for i in range(baris):
            self.grid.setRowStretch(i, 1)
        for j in range(kolom):
            self.grid.setColumnStretch(j, 1)

    def _kartu_semua(
        self, menunggu: Sequence[QueueInfo], sekarang: datetime, baris_isi: int
    ) -> tuple[str, str, str, str]:
        """Kartu "Semua": jumlah seluruh antrian dan nomor terlamanya."""
        terlama = min(menunggu, key=lambda a: a.created_at)
        detik = max(0.0, (sekarang - terlama.created_at).total_seconds())
        html = (
            f"<b style='color:{TEXT}'>Semua</b> "
            f"<span style='color:{TEXT}'>({len(menunggu)})</span>"
            + ("" if baris_isi <= 1 else "<br>")
            + f"<span style='color:{TEXT}'>{'· ' if baris_isi <= 1 else ''}"
            f"{escape(terlama.queue_number)} · {escape(_label_menit(detik))}</span>"
        )
        gaya = (
            f"background: {SURFACE}; border: 1px dashed {PRIMARY};"
            " border-radius: 8px; padding: 5px 8px;"
        )
        tip = f"Semua layanan: {len(menunggu)} menunggu"
        return "Semua", html, gaya, tip

    def _kartu(
        self,
        daftar: list[QueueInfo],
        dilayani: tuple[int, ...],
        sekarang: datetime,
        baris_isi: int,
    ) -> tuple[str, str, str, str]:
        """(judul, html, gaya, tooltip) satu kartu layanan."""
        terlama = daftar[0]
        milik_lain = bool(dilayani) and terlama.category_id not in dilayani
        detik = max(0.0, (sekarang - terlama.created_at).total_seconds())
        lama = detik >= self._batas_lama * 60 and not milik_lain
        judul = f"{terlama.category_name} ({len(daftar)})"
        warna = TEXT_MUTED if milik_lain else TEXT
        warna_lama = WARNING if lama else warna
        penanda = " ●" if lama else ""

        nama = escape(terlama.category_name)
        if baris_isi <= 1:
            html = (
                f"<b style='color:{warna}'>{nama}</b> "
                f"<span style='color:{warna}'>{len(daftar)}</span> "
                f"<span style='color:{warna_lama}'>· {escape(_label_menit(detik))}"
                f"{penanda}</span>"
            )
        else:
            baris = [
                f"<b style='color:{warna}'>{nama}</b> "
                f"<span style='color:{warna}'>({len(daftar)})</span>"
                + (
                    f" <i style='color:{TEXT_MUTED}'>loket lain</i>"
                    if milik_lain
                    else ""
                ),
                f"<span style='color:{warna_lama}'>"
                f"{escape(terlama.queue_number)} · {escape(_label_menit(detik))}"
                f"{penanda}</span>",
            ]
            tambahan = baris_isi - 2
            berikut = daftar[1:]
            for antrian in berikut[:tambahan]:
                d = max(0.0, (sekarang - antrian.created_at).total_seconds())
                baris.append(
                    f"<span style='color:{warna}'>{escape(antrian.queue_number)}"
                    f" &nbsp; {escape(_label_menit(d))}</span>"
                )
            sisa = len(berikut) - tambahan
            if sisa > 0:
                baris.append(f"<span style='color:{TEXT_MUTED}'>+{sisa} lagi</span>")
            html = "<br>".join(baris)

        if lama:
            latar, tepi = WARNING_SOFT, WARNING
        elif milik_lain:
            latar, tepi = SURFACE, BORDER
        else:
            latar, tepi = PRIMARY_SOFT, BORDER
        gaya = (
            f"background: {latar}; border: 1px solid {tepi};"
            " border-radius: 8px; padding: 5px 8px;"
        )
        tip = (
            f"{terlama.category_name}: {len(daftar)} menunggu, terlama "
            f"{terlama.queue_number} ({escape(_label_menit(detik))})"
        )
        return judul, html, gaya, tip
