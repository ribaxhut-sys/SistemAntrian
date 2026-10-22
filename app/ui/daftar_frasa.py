"""
Kalimat cepat sebagai satu paragraf berkoma, tanpa kotak dan tanpa gulir.

Tiap kalimat adalah tautan yang dapat diklik; kalimat yang sudah ada di
catatan berubah menjadi teks abu-abu bertanda ✓ dan tidak bisa diklik lagi.
Paragraf membungkus sendiri sehingga seluruh kalimat selalu terbaca; dengan
daftar bawaan hanya makan dua sampai tiga baris.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from app.ui.style import FONT_SIZE_SMALL, PRIMARY, TEXT_MUTED

TANDA_TERPAKAI = "✓ "


class ItemFrasa:
    """Satu kalimat cepat beserta keadaan 'sudah ada di catatan'."""

    def __init__(self, kalimat: str) -> None:
        self.kalimat = kalimat
        self.terpakai = False


class DaftarFrasa(QLabel):
    """Paragraf kalimat cepat. `dipilih` memancarkan kalimat yang diklik."""

    dipilih = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item: list[ItemFrasa] = []
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        palet = self.palette()
        palet.setColor(QPalette.ColorRole.Link, QColor(PRIMARY))
        self.setPalette(palet)
        self.setStyleSheet(f"font-size: {FONT_SIZE_SMALL}px; background: transparent;")
        self.linkActivated.connect(self._tautan)
        self.setVisible(False)

    def set_kalimat(self, kalimat: list[str]) -> None:
        self.item = [ItemFrasa(k) for k in kalimat]
        self.setVisible(bool(self.item))
        self._gambar()

    def tandai_terpakai(self, indeks: int, terpakai: bool) -> None:
        if self.item[indeks].terpakai != terpakai:
            self.item[indeks].terpakai = terpakai
            self._gambar()

    def pilih(self, indeks: int) -> None:
        """Pilih kalimat ke-`indeks`, seperti mengklik tautannya."""
        if not self.item[indeks].terpakai:
            self.dipilih.emit(self.item[indeks].kalimat)

    def _tautan(self, tujuan: str) -> None:
        try:
            self.pilih(int(tujuan))
        except (ValueError, IndexError):
            pass

    def _gambar(self) -> None:
        potongan = []
        for urutan, butir in enumerate(self.item):
            teks = escape(butir.kalimat.rstrip(". "))
            if butir.terpakai:
                potongan.append(
                    f'<span style="color:{TEXT_MUTED}">{TANDA_TERPAKAI}{teks}</span>'
                )
            else:
                potongan.append(
                    f'<a href="{urutan}" style="text-decoration:none">{teks}</a>'
                )
        self.setText(", ".join(potongan) + ("." if potongan else ""))
