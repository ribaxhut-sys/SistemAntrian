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
#: Batas skala huruf kartu di pita. Batas bawahnya serendah ini supaya
#: nama loket tetap utuh pada totem berskala Windows 200% (540 px, tiap
#: kartu sekitar 157 px): huruf kecil masih terbaca, "LOKET" tanpa
#: angkanya tidak menunjuk loket mana pun.
SKALA_PITA_MIN = 0.4
SKALA_PITA_MAKS = 1.15


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
        """
        Skala huruf kartu dari tinggi pita, lalu dijepit oleh LEBARNYA.

        Skala dari tinggi saja memotong kepala kartu: pada totem 1080x1920
        pita setinggi 640 px meminta skala 1,15, dan "LOKET 1" butuh 160 px
        sementara kartu hanya memberinya 131 — yang tampil "LOKET" tanpa
        angkanya, dan pil "KOSONG" terbaca ":OSON(". Pita ini hanya punya
        satu tugas, yaitu memberi tahu loket MANA yang memanggil, dan nama
        loket yang kehilangan angkanya menggagalkan tugas itu.

        `muatkan_huruf()` milik kartu hanya mengurus tinggi; lebar diurus di
        sini. Semua kartu memakai skala yang sama: kartu yang hurufnya lebih
        kecil dari tetangganya terbaca sebagai loket yang kurang penting.
        """
        tinggi = self.height()
        if tinggi <= 0:
            return
        skala = min(SKALA_PITA_MAKS, max(SKALA_PITA_MIN, tinggi / TINGGI_ACUAN_PITA))
        # Lebar kepala sebanding dengan skalanya, tetapi tidak persis:
        # ukuran huruf dibulatkan dan punya batas bawah. Beberapa putaran
        # cukup untuk mengejar sisa pembulatan itu.
        for _putaran in range(4):
            for kartu in self.kartu_loket:
                kartu.set_skala(skala)
                kartu.muatkan_huruf()
            lebih = max(
                (self._rasio_kepala(kartu) for kartu in self.kartu_loket),
                default=1.0,
            )
            if lebih <= 1.0 or skala <= SKALA_PITA_MIN:
                return
            skala = max(SKALA_PITA_MIN, skala / lebih * 0.97)

    @staticmethod
    def _rasio_kepala(kartu: KartuLoket) -> float:
        """
        Seberapa jauh kepala kartu melampaui lebarnya: tuntutan / lebar.

        Lebih dari 1 berarti nama loket atau pil statusnya terpotong. Dua
        cara mengukurnya, dan yang lebih besar yang dipakai, sebab masing-
        masing buta pada saat yang berbeda:

        * TAKSIRAN dari tulisan, tepi, dan celah kartu. Bekerja sebelum
          label ditata — saat pita baru saja mendapat tingginya, yaitu tepat
          ketika anjungan baru dinyalakan. Celahnya diambil dari susunan
          kepala yang sebenarnya: celah itu diwarisi dari susunan induknya
          dan ikut membesar bersama skala, dan angka tetap 12 px pernah
          membuatnya meleset cukup jauh untuk memotong angka loket.
        * PENGUKURAN langsung pada label yang sudah ditata, penangkap apa
          pun yang tidak terlihat oleh taksiran.

        Kartu yang belum punya lebar dianggap muat.
        """
        if kartu.width() <= 1:
            return 1.0
        nama, status = kartu.label_nama, kartu.label_status
        for label in (nama, status):
            label.ensurePolished()

        tepi = kartu.susunan_isi.contentsMargins()
        dalam = kartu.width() - tepi.left() - tepi.right() - 2 * kartu.palet.tebal_tepi
        dalam = max(1, dalam)
        if kartu.palet.status_berpil:
            # Nama dan pil berdampingan dalam satu susunan kepala: nama,
            # pegas, pil — dua celah.
            kepala = kartu.susunan_isi.itemAt(0)
            susunan_kepala = kepala.layout() if kepala is not None else None
            celah = max(0, susunan_kepala.spacing()) if susunan_kepala is not None else 0
            taksiran = (
                nama.sizeHint().width() + 2 * celah + status.sizeHint().width()
            ) / dalam
        else:
            taksiran = max(nama.sizeHint().width(), status.sizeHint().width()) / dalam

        susunan = kartu.layout()
        if susunan is not None:
            susunan.activate()
        langsung = 1.0
        for label in (nama, status):
            if label.isVisibleTo(kartu) and label.width() > 1:
                langsung = max(langsung, label.sizeHint().width() / label.width())

        return max(1.0, taksiran, langsung)

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama API Qt
        super().resizeEvent(event)
        self._skala_kartu()
