"""
Efek kilau pada tombol: pita cahaya miring yang menyapu tombol, lalu jeda,
terus berulang, ditambah bingkai yang berdenyut.

Dipakai untuk menunjuk SATU langkah berikutnya di halaman Pelayanan tanpa
memindahkan atau mengubah warna tombol. Efek ini hanya hiasan: dibuat
sebagai widget transparan di atas tombol yang tidak menangkap mouse, jadi
klik dan fokus keyboard tetap sampai ke tombolnya.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton, QWidget

from app.ui.tema_petugas import warna_tema

DURASI_SAPUAN_MS = 1000
JEDA_ANTAR_SAPUAN_MS = 1300
RADIUS = 8
#: Lebar pita sebagai bagian dari lebar tombol, dan kemiringannya.
LEBAR_PITA = 0.28
KEMIRINGAN = -0.35


class KilauTombol(QWidget):
    """Lapisan kilau di atas satu tombol; `aktifkan` menyalakan dan mematikannya."""

    def __init__(
        self, tombol: QPushButton, warna: str = "#FFFFFF", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent or tombol)
        self._tombol = tombol
        self._warna = warna
        self._aktif = False
        self._posisi = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._sapuan = QVariantAnimation(self)
        self._sapuan.setStartValue(0.0)
        self._sapuan.setEndValue(1.0)
        self._sapuan.setDuration(DURASI_SAPUAN_MS)
        self._sapuan.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._sapuan.valueChanged.connect(self._geser)
        self._sapuan.finished.connect(self._jeda_dulu)

        self._pewaktu_jeda = QTimer(self)
        self._pewaktu_jeda.setSingleShot(True)
        self._pewaktu_jeda.setInterval(JEDA_ANTAR_SAPUAN_MS)
        self._pewaktu_jeda.timeout.connect(self._mulai)

        tombol.installEventFilter(self)
        self.setGeometry(tombol.rect())
        self.hide()

    # -----------------------------------------------------------------

    @property
    def aktif(self) -> bool:
        return self._aktif

    @property
    def berjalan(self) -> bool:
        """Animasi benar-benar bergerak (aktif, tombol tampil dan menyala)."""
        return (
            self._sapuan.state() == QVariantAnimation.State.Running
            or self._pewaktu_jeda.isActive()
        )

    def aktifkan(self, ya: bool) -> None:
        if ya == self._aktif:
            return
        self._aktif = ya
        if ya:
            self._mulai()
        else:
            self._henti()

    def _boleh_tampil(self) -> bool:
        return self._aktif and self._tombol.isVisible() and self._tombol.isEnabled()

    def _mulai(self) -> None:
        if not self._boleh_tampil():
            return
        self.setGeometry(self._tombol.rect())
        self.raise_()
        self.show()
        self._sapuan.start()

    def _henti(self) -> None:
        self._pewaktu_jeda.stop()
        self._sapuan.stop()
        self._posisi = 0.0
        self.hide()

    def _jeda_dulu(self) -> None:
        if self._aktif:
            self._posisi = 0.0
            self.update()
            self._pewaktu_jeda.start()

    def _geser(self, nilai) -> None:
        self._posisi = float(nilai)
        self.update()

    # -----------------------------------------------------------------

    def eventFilter(self, sumber: QObject, kejadian: QEvent) -> bool:  # noqa: N802
        if sumber is self._tombol:
            jenis = kejadian.type()
            if jenis == QEvent.Type.Resize:
                self.setGeometry(self._tombol.rect())
            elif jenis in (QEvent.Type.Hide, QEvent.Type.EnabledChange):
                if not self._tombol.isVisible() or not self._tombol.isEnabled():
                    self._pewaktu_jeda.stop()
                    self._sapuan.stop()
                    self.hide()
                elif self._aktif:
                    self._mulai()
            elif jenis == QEvent.Type.Show and self._aktif:
                self._mulai()
        return False

    def paintEvent(self, kejadian) -> None:  # noqa: N802 - nama Qt
        if not self._boleh_tampil():
            return
        lebar, tinggi = self.width(), self.height()
        if lebar <= 0 or tinggi <= 0:
            return
        warna = QColor(warna_tema(self._warna))
        pelukis = QPainter(self)
        pelukis.setRenderHint(QPainter.RenderHint.Antialiasing)

        bentuk = QPainterPath()
        bentuk.addRoundedRect(QRectF(0.5, 0.5, lebar - 1, tinggi - 1), RADIUS, RADIUS)

        # Bingkai berdenyut: terang di tengah sapuan, redup di ujungnya.
        denyut = 1.0 - abs(2.0 * self._posisi - 1.0)
        bingkai = QColor(warna)
        bingkai.setAlpha(int(70 + 150 * denyut))
        pelukis.setPen(QPen(bingkai, 2))
        pelukis.setBrush(Qt.BrushStyle.NoBrush)
        pelukis.drawPath(bentuk)

        # Pita cahaya miring yang menyapu dari kiri ke kanan.
        pelukis.setClipPath(bentuk)
        setengah = lebar * LEBAR_PITA / 2
        tengah = -setengah + self._posisi * (lebar + 2 * setengah + tinggi * abs(KEMIRINGAN))
        pelukis.translate(tengah, 0)
        pelukis.shear(KEMIRINGAN, 0)
        gradien = QLinearGradient(-setengah, 0, setengah, 0)
        pucat = QColor(warna)
        pucat.setAlpha(0)
        terang = QColor(warna)
        terang.setAlpha(150)
        gradien.setColorAt(0.0, pucat)
        gradien.setColorAt(0.5, terang)
        gradien.setColorAt(1.0, pucat)
        pelukis.setPen(Qt.PenStyle.NoPen)
        pelukis.setBrush(gradien)
        pelukis.drawRect(QRectF(-setengah, 0, 2 * setengah, tinggi))
        pelukis.end()
