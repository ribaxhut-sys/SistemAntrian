"""
Pratinjau totem di laptop: kaca 1080×1920 yang diperkecil utuh.

Bukan tata letak yang disusun ulang ke jendela sempit. Isinya sama
dengan mesin Onesia; yang menyusut hanya skala gambarnya.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, QSizeF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QSizePolicy,
    QWidget,
)

#: Ukuran kaca totem Onesia, piksel.
LEBAR_TOTEM_ASLI = 1080
TINGGI_TOTEM_ASLI = 1920

#: 30% (324×576) terlalu kecil untuk dibaca. 50% (540×960) muat di laptop
#: 1080p dan masih bisa diklik. Pratinjau memakai 50%, atau lebih kecil
#: bila layarnya tidak muat.
SKALA_PRATINJAU_MAKS = 0.5
#: Batas persentase yang boleh diminta lewat `--jendela=PERSEN`. Di bawah
#: 25% tulisan pil dan nama loket tidak lagi terbaca sama sekali.
PERSEN_PRATINJAU_MIN = 25
PERSEN_PRATINJAU_MAKS = 100


def layar_mendatar(area: QRect) -> bool:
    """
    True bila area kerja lebih lebar daripada tingginya.

    Kaca totem selalu berdiri tegak. Totem yang dibuka layar penuh di layar
    mendatar — laptop, monitor meja — membentangkan ketiga pitanya menjadi
    pita pipih yang sama sekali tidak mirip mesin sungguhannya.
    """
    return area.width() > area.height()


def skala_pratinjau_totem(area: QRect, persen: int | None = None) -> float:
    """
    Skala yang membuat 1080×1920 muat di area kerja.

    Tanpa `persen`: sebesar yang muat, paling besar 50%. Dengan `persen`
    (`--jendela=40`): sebesar yang diminta, dijepit 25–100%, tetapi tetap
    tidak pernah melebihi yang muat. Jendela yang lebih tinggi daripada
    layarnya memotong pita loket di bawah — justru pita yang paling sering
    dicari saat menguji alur ambil nomor sampai dipanggil.
    """
    tepi = 32
    sisa = area.adjusted(tepi, tepi, -tepi, -tepi)
    if sisa.width() < 100 or sisa.height() < 100:
        sisa = area
    muat = min(
        sisa.width() / LEBAR_TOTEM_ASLI,
        sisa.height() / TINGGI_TOTEM_ASLI,
        1.0,
    )
    if persen is None:
        batas = SKALA_PRATINJAU_MAKS
    else:
        batas = min(max(persen, PERSEN_PRATINJAU_MIN), PERSEN_PRATINJAU_MAKS) / 100
    return min(muat, batas)


def ukuran_jendela_totem(area: QRect, persen: int | None = None) -> QRect:
    """Jendela tegak sebesar kaca totem yang sudah diskalakan."""
    skala = skala_pratinjau_totem(area, persen)
    lebar = max(1, round(LEBAR_TOTEM_ASLI * skala))
    tinggi = max(1, round(TINGGI_TOTEM_ASLI * skala))
    kiri = area.x() + (area.width() - lebar) // 2
    atas = area.y() + (area.height() - tinggi) // 2
    return QRect(kiri, atas, lebar, tinggi)


class PratinjauTotem(QGraphicsView):
    """
    Halaman totem tetap 1080×1920; jendela hanya menampilkan skalanya.

    Tanpa ini QGraphicsProxyWidget ikut mengecil ke ukuran jendela, kartu
    tersusun ulang jadi pita, dan judul terpotong kiri-kanan.
    """

    def __init__(self, isi: QWidget, skala: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.isi = isi
        self._skala = skala
        self._lebar_jendela = max(1, round(LEBAR_TOTEM_ASLI * skala))
        self._tinggi_jendela = max(1, round(TINGGI_TOTEM_ASLI * skala))
        self.setObjectName("pratinjauTotem")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        ukuran = QSize(LEBAR_TOTEM_ASLI, TINGGI_TOTEM_ASLI)
        isi.setFixedSize(ukuran)
        isi.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        adegan = QGraphicsScene(self)
        adegan.setSceneRect(0, 0, LEBAR_TOTEM_ASLI, TINGGI_TOTEM_ASLI)
        self.setScene(adegan)

        proxy = QGraphicsProxyWidget()
        proxy.setWidget(isi)
        proxy.setMinimumSize(QSizeF(ukuran))
        proxy.setMaximumSize(QSizeF(ukuran))
        proxy.resize(QSizeF(ukuran))
        adegan.addItem(proxy)
        self._proxy = proxy

        self.setFixedSize(self._lebar_jendela, self._tinggi_jendela)
        self._kunci_kaca()
        QTimer.singleShot(0, self._muatkan)

    def sizeHint(self) -> QSize:  # noqa: N802 - nama API Qt
        return QSize(self._lebar_jendela, self._tinggi_jendela)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - nama API Qt
        return self.sizeHint()

    def showEvent(self, event) -> None:  # noqa: N802 - nama API Qt
        super().showEvent(event)
        self._muatkan()

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama API Qt
        super().resizeEvent(event)
        self._muatkan()

    def _kunci_kaca(self) -> None:
        ukuran = QSize(LEBAR_TOTEM_ASLI, TINGGI_TOTEM_ASLI)
        self.isi.setFixedSize(ukuran)
        self._proxy.setMinimumSize(QSizeF(ukuran))
        self._proxy.setMaximumSize(QSizeF(ukuran))
        self._proxy.resize(QSizeF(ukuran))

    def _muatkan(self) -> None:
        """Isi tetap 1080×1920; yang diskalakan hanya tampilan jendela."""
        self._kunci_kaca()
        if self.viewport().width() <= 0 or self.viewport().height() <= 0:
            return
        self.fitInView(
            self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
        )
