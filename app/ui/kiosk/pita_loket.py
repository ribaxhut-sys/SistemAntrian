"""Pita loket mini di sepertiga bawah anjungan berdiri (totem)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from app.services.queue_service import DisplayState
from app.ui.display.display_page import KartuLoket
from app.ui.display.tema import Palet


#: Tinggi acuan kartu di pita, supaya nomor tetap besar meski pita pendek.
TINGGI_ACUAN_PITA = 520


class PitaLoketKios(QFrame):
    """
    Tiga kartu loket besar plus hitungan yang menunggu.

    Bukan salinan TV ruang tunggu: tidak ada daftar menunggu berkolom, dan
    tidak ada tombol. Pita ini terlalu rendah untuk disentuh; yang dibaca
    orang dewasa sambil menunduk hanyalah nomor yang sedang dipanggil.
    """

    def __init__(self, palet: Palet, parent=None) -> None:
        super().__init__(parent)
        self.palet = palet
        self.kartu_loket: list[KartuLoket] = []
        self._kunci_loket: tuple | None = None
        self.setObjectName("pitaLoketKios")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._tulis_latar()

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(20, 12, 20, 16)
        susunan.setSpacing(8)

        self.label_judul = QLabel("SEDANG DILAYANI")
        self.label_judul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_judul.setMinimumSize(1, 1)
        susunan.addWidget(self.label_judul)

        self.baris_kartu = QHBoxLayout()
        self.baris_kartu.setSpacing(14)
        susunan.addLayout(self.baris_kartu, stretch=1)

        self.label_menunggu = QLabel("Tidak ada yang menunggu")
        self.label_menunggu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_menunggu.setMinimumSize(1, 1)
        susunan.addWidget(self.label_menunggu)
        self._tulis_judul()

    def _tulis_latar(self) -> None:
        self.setStyleSheet(
            f"QFrame#pitaLoketKios {{ background: {self.palet.panel};"
            " border-top-left-radius: 20px; border-top-right-radius: 20px; }}"
        )

    def _tulis_judul(self) -> None:
        p = self.palet
        self.label_judul.setStyleSheet(
            f"color: {p.panel_judul}; background: transparent;"
            " font-size: 18px; font-weight: 800; letter-spacing: 4px;"
        )
        self.label_menunggu.setStyleSheet(
            f"color: {p.panel_judul}; background: transparent;"
            " font-size: 20px; font-weight: 700;"
        )

    def tampilkan(self, keadaan: DisplayState) -> None:
        """Isi kartu dari keadaan papan yang sama dengan televisi."""
        terkini = keadaan.terkini
        id_unggulan = terkini.id if terkini is not None else None
        self._susun_kartu(keadaan.loket)
        for kartu, loket in zip(self.kartu_loket, keadaan.loket, strict=False):
            unggulan = (
                loket.antrian is not None and loket.antrian.id == id_unggulan
            )
            kartu.tampilkan(loket, unggulan=unggulan)
        n = keadaan.total_menunggu
        if n <= 0:
            self.label_menunggu.setText("Tidak ada yang menunggu")
        elif n == 1:
            self.label_menunggu.setText("1 orang menunggu")
        else:
            self.label_menunggu.setText(f"{n} orang menunggu")
        self._skala_kartu()

    def _susun_kartu(self, loket) -> None:
        kunci = tuple((item.counter_id, item.counter_name) for item in loket)
        if kunci == self._kunci_loket and self.kartu_loket:
            return
        while self.baris_kartu.count():
            item = self.baris_kartu.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.kartu_loket = []
        self._kunci_loket = kunci
        for _item in loket:
            kartu = KartuLoket(
                self, kompak=False, palet=self.palet, varian="kisi"
            )
            kartu.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.baris_kartu.addWidget(kartu, stretch=1)
            self.kartu_loket.append(kartu)

    def _skala_kartu(self) -> None:
        tinggi = self.height()
        if tinggi <= 0:
            return
        skala = min(1.15, max(0.55, tinggi / TINGGI_ACUAN_PITA))
        for kartu in self.kartu_loket:
            kartu.set_skala(skala)
            kartu.muatkan_huruf()

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama API Qt
        super().resizeEvent(event)
        self._skala_kartu()
