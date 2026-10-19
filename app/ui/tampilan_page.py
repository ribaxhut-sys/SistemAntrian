"""
Tab Tampilan: memilih tema layar petugas untuk komputer ini.

Pilihan tersimpan di komputer ini saja dan langsung berlaku. Pratinjau pada
kartu digambar sendiri (bukan lewat stylesheet) supaya warnanya tetap warna
tema yang dipratinjau, bukan warna tema yang sedang aktif.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui.common import judul, keterangan
from app.ui.tema_petugas import (
    TEMA,
    Tema,
    simpan_tema,
    tema_aktif,
    terapkan_tema,
)

KOLOM = 4


class _Pratinjau(QWidget):
    """Gambar mini layar: latar, kartu, bilah aksen, dan garis teks."""

    def __init__(self, tema: Tema, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tema = tema
        self.setFixedHeight(84)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _event) -> None:  # noqa: N802 - nama Qt
        latar, kartu, aksen, teks = (QColor(c) for c in self._tema.contoh)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(latar)
        p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)

        # Kepala berwarna aksen.
        p.setBrush(aksen)
        p.drawRoundedRect(QRectF(8, 8, w - 16, 16), 5, 5)

        # Dua kartu.
        garis = QColor(teks)
        garis.setAlpha(40)
        p.setPen(QPen(garis, 1))
        p.setBrush(kartu)
        lebar_kartu = (w - 16 - 8) / 2
        for kolom in range(2):
            x = 8 + kolom * (lebar_kartu + 8)
            p.drawRoundedRect(QRectF(x, 32, lebar_kartu, h - 40), 6, 6)

        # Garis teks dan tombol aksen pada kartu pertama.
        p.setPen(Qt.PenStyle.NoPen)
        isi = QColor(teks)
        isi.setAlpha(190)
        p.setBrush(isi)
        p.drawRoundedRect(QRectF(16, 42, lebar_kartu - 16, 5), 2.5, 2.5)
        isi.setAlpha(110)
        p.setBrush(isi)
        p.drawRoundedRect(QRectF(16, 54, (lebar_kartu - 16) * 0.6, 5), 2.5, 2.5)
        p.setBrush(aksen)
        p.drawRoundedRect(QRectF(16, h - 26, lebar_kartu - 16, 12), 4, 4)
        p.end()


class _KartuTema(QFrame):
    dipilih = Signal(str)

    def __init__(self, tema: Tema, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tema = tema
        self.setObjectName("kartuTema")
        self.setProperty("terpilih", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"Tema {tema.nama}")

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(12, 12, 12, 12)
        susunan.setSpacing(8)
        susunan.addWidget(_Pratinjau(tema))

        self.label_nama = QLabel(tema.nama)
        self.label_nama.setStyleSheet("font-weight: 700;")
        susunan.addWidget(self.label_nama)

        self.label_ket = QLabel(tema.keterangan)
        self.label_ket.setWordWrap(True)
        self.label_ket.setProperty("muted", "true")
        susunan.addWidget(self.label_ket)

    def tandai(self, aktif: bool) -> None:
        self.setProperty("terpilih", aktif)
        self.label_nama.setText(f"{self.tema.nama}  ✓" if aktif else self.tema.nama)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - nama Qt
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.dipilih.emit(self.tema.kunci)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - nama Qt
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.dipilih.emit(self.tema.kunci)
            return
        super().keyPressEvent(event)


class TampilanPage(QWidget):
    """Pilihan tema untuk komputer ini."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(14)

        susunan.addWidget(judul("Tampilan"))
        susunan.addWidget(
            keterangan(
                "Pilih tema layar petugas. Pilihan hanya berlaku di komputer ini "
                "dan langsung dipakai."
            )
        )

        grid = QGridLayout()
        grid.setSpacing(14)
        self.kartu: dict[str, _KartuTema] = {}
        for indeks, tema in enumerate(TEMA.values()):
            kartu = _KartuTema(tema)
            kartu.dipilih.connect(self.pilih)
            self.kartu[tema.kunci] = kartu
            grid.addWidget(kartu, indeks // KOLOM, indeks % KOLOM)
        for kolom in range(KOLOM):
            grid.setColumnStretch(kolom, 1)
        susunan.addLayout(grid)
        susunan.addStretch(1)

        self.label_status = QLabel("")
        self.label_status.setProperty("muted", "true")
        susunan.addWidget(self.label_status)

        self.setStyleSheet(
            "QFrame#kartuTema { background: #FFFFFF; border: 1px solid #E1E7EF;"
            " border-radius: 12px; }"
            "QFrame#kartuTema[terpilih=\"true\"] { border: 2px solid #4F46E5; }"
            "QFrame#kartuTema:focus { border: 2px solid #A5B4FC; }"
        )
        self._tandai(tema_aktif().kunci)

    def _tandai(self, kunci: str) -> None:
        for k, kartu in self.kartu.items():
            kartu.tandai(k == kunci)

    def pilih(self, kunci: str) -> None:
        """Simpan untuk komputer ini lalu terapkan langsung."""
        if kunci not in TEMA:
            return
        tersimpan = simpan_tema(kunci)
        terapkan_tema(QApplication.instance(), kunci)
        self._tandai(kunci)
        self.label_status.setText(
            f"Tema {TEMA[kunci].nama} dipakai."
            if tersimpan
            else f"Tema {TEMA[kunci].nama} dipakai, tetapi tidak dapat disimpan "
            "untuk pembukaan berikutnya."
        )
