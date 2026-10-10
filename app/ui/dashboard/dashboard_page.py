"""
Layar ringkasan harian untuk supervisor.

Angka dibuat besar dan dikelompokkan supaya keadaan hari itu terbaca dalam
sekali pandang, bukan dibaca baris demi baris. Layar ini murni memantau —
tidak ada satu pun tombol yang mengubah antrian.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models import RATING_LABELS, QueueStatus
from app.services.dashboard_service import (
    STATUS_RINGKASAN,
    DashboardService,
    DashboardSummary,
)
from app.services.queue_service import LABEL_STATUS
from app.services.settings_service import SettingsService
from app.ui.common import PekerjaLatar, jalankan_aman, judul, keterangan, lepaskan_pekerja
from app.ui.style import (
    BORDER,
    DANGER,
    FONT_SIZE_HUGE,
    FONT_SIZE_LARGE,
    PRIMARY,
    SUCCESS,
    TEXT_MUTED,
    WARNING,
)
from app.utils.formatting import hari_dan_tanggal

#: Warna penanda per status. Menunggu dan tidak hadir sengaja mencolok:
#: keduanya yang paling perlu ditindaklanjuti supervisor.
WARNA_STATUS: dict[QueueStatus, str] = {
    QueueStatus.WAITING: WARNING,
    QueueStatus.CALLED: PRIMARY,
    QueueStatus.SERVING: PRIMARY,
    QueueStatus.PAUSED: TEXT_MUTED,
    QueueStatus.COMPLETED: SUCCESS,
    QueueStatus.NO_SHOW: DANGER,
    QueueStatus.CANCELLED: TEXT_MUTED,
}


class KartuAngka(QFrame):
    """Satu angka besar beserta namanya."""

    def __init__(
        self, nama: str, warna: str = PRIMARY, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        # objectName wajib: tanpa itu selector "QFrame" polos akan membingkai
        # setiap label di dalam kartu.
        self.setObjectName("kartuAngka")
        self.setStyleSheet(
            f"QFrame#kartuAngka {{ background: white; border: 1px solid {BORDER};"
            " border-radius: 6px; }"
        )

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(16, 14, 16, 14)
        susunan.setSpacing(2)

        self.nilai = QLabel("0")
        self.nilai.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nilai.setStyleSheet(
            f"font-size: {FONT_SIZE_HUGE}px; font-weight: 700; color: {warna};"
        )
        susunan.addWidget(self.nilai)

        label = QLabel(nama)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(label)

    def setel(self, teks: str) -> None:
        self.nilai.setText(teks)


class DashboardPage(QWidget):
    """Ringkasan antrian dan kepuasan hari berjalan."""

    def __init__(
        self,
        dashboard: DashboardService,
        settings: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.dashboard = dashboard
        self.settings = settings
        self._pekerja: PekerjaLatar | None = None

        self._bangun_tampilan()
        self.muat_ulang()
        self._pasang_penyegar()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        luar = QVBoxLayout(self)
        luar.setContentsMargins(0, 0, 0, 0)

        gulung = QScrollArea()
        gulung.setWidgetResizable(True)
        gulung.setFrameShape(QFrame.Shape.NoFrame)
        luar.addWidget(gulung)

        isi = QWidget()
        susunan = QVBoxLayout(isi)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(18)

        baris_atas = QHBoxLayout()
        baris_atas.addWidget(judul("Ringkasan Hari Ini"))
        baris_atas.addStretch()
        self.label_tanggal = keterangan("")
        baris_atas.addWidget(self.label_tanggal)
        susunan.addLayout(baris_atas)

        susunan.addWidget(self._bangun_status())
        susunan.addWidget(self._bangun_durasi())
        susunan.addWidget(self._bangun_kategori())
        susunan.addWidget(self._bangun_survey())
        susunan.addStretch()

        gulung.setWidget(isi)

    def _bangun_status(self) -> QWidget:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)
        susunan.addWidget(keterangan("Antrian per status"))

        baris = QHBoxLayout()
        baris.setSpacing(10)
        self.kartu_status: dict[QueueStatus, KartuAngka] = {}
        for status in STATUS_RINGKASAN:
            kartu = KartuAngka(LABEL_STATUS[status], WARNA_STATUS[status])
            self.kartu_status[status] = kartu
            baris.addWidget(kartu, stretch=1)

        susunan.addLayout(baris)
        return panel

    def _bangun_durasi(self) -> QWidget:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)
        susunan.addWidget(keterangan("Waktu dan capaian"))

        baris = QHBoxLayout()
        baris.setSpacing(10)
        self.kartu_total = KartuAngka("Total antrian")
        self.kartu_belum = KartuAngka("Belum selesai", WARNING)
        self.kartu_menunggu = KartuAngka("Rata-rata menunggu")
        self.kartu_layanan = KartuAngka("Rata-rata pelayanan")
        self.kartu_kehadiran = KartuAngka("Tuntas dilayani", SUCCESS)
        for kartu in (
            self.kartu_total,
            self.kartu_belum,
            self.kartu_menunggu,
            self.kartu_layanan,
            self.kartu_kehadiran,
        ):
            baris.addWidget(kartu, stretch=1)

        susunan.addLayout(baris)
        return panel

    def _bangun_kategori(self) -> QWidget:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)
        susunan.addWidget(keterangan("Antrian per jenis layanan"))

        self.baris_kategori = QHBoxLayout()
        self.baris_kategori.setSpacing(10)
        susunan.addLayout(self.baris_kategori)
        return panel

    def _bangun_survey(self) -> QWidget:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)
        susunan.addWidget(keterangan("Kepuasan pelayanan hari ini"))

        baris = QHBoxLayout()
        baris.setSpacing(10)

        self.kartu_rata_rating = KartuAngka("Rata-rata nilai", SUCCESS)
        baris.addWidget(self.kartu_rata_rating, stretch=1)
        self.kartu_jumlah_survey = KartuAngka("Survey masuk")
        baris.addWidget(self.kartu_jumlah_survey, stretch=1)

        kisi = QGridLayout()
        kisi.setHorizontalSpacing(14)
        kisi.setVerticalSpacing(4)
        self.label_distribusi: dict[int, QLabel] = {}
        for kolom, nilai in enumerate(range(5, 0, -1)):
            nama = QLabel(f"{nilai} · {RATING_LABELS[nilai]}")
            nama.setStyleSheet(f"color: {TEXT_MUTED};")
            kisi.addWidget(nama, 0, kolom, Qt.AlignmentFlag.AlignCenter)

            angka = QLabel("0")
            angka.setAlignment(Qt.AlignmentFlag.AlignCenter)
            angka.setStyleSheet(
                f"font-size: {FONT_SIZE_LARGE}px; font-weight: 700;"
            )
            self.label_distribusi[nilai] = angka
            kisi.addWidget(angka, 1, kolom, Qt.AlignmentFlag.AlignCenter)

        bungkus = QFrame()
        bungkus.setObjectName("kartuDistribusi")
        bungkus.setStyleSheet(
            f"QFrame#kartuDistribusi {{ background: white; border: 1px solid {BORDER};"
            " border-radius: 6px; }"
        )
        dalam = QVBoxLayout(bungkus)
        dalam.setContentsMargins(16, 14, 16, 14)
        dalam.addLayout(kisi)
        baris.addWidget(bungkus, stretch=3)

        susunan.addLayout(baris)
        return panel

    def _pasang_penyegar(self) -> None:
        """
        Segarkan berkala supaya angka tidak basi tanpa perlu ditekan F5.

        Intervalnya dapat diatur administrator; nilai yang tidak masuk akal
        diabaikan agar layar tidak menyiksa database dengan query beruntun.
        """
        detik = max(5, self.settings.get_int("dashboard.refresh_seconds", 30))
        self.penyegar = QTimer(self)
        self.penyegar.timeout.connect(self.muat_ulang)
        self.penyegar.setInterval(detik * 1000)

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().showEvent(event)
        self.muat_ulang()
        self.penyegar.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - nama Qt
        self.penyegar.stop()
        super().hideEvent(event)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        if self.isVisible():
            if self._pekerja is not None:
                return
            pekerja = PekerjaLatar(self.dashboard.ringkasan_hari_ini, self)
            pekerja.berhasil.connect(self._tampilkan)
            pekerja.finished.connect(self._bersihkan_pekerja)
            self._pekerja = pekerja
            pekerja.start()
            return
        berhasil, data = jalankan_aman(
            self, self.dashboard.ringkasan_hari_ini, "Gagal memuat ringkasan"
        )
        if berhasil and data is not None:
            self._tampilkan(data)

    def _bersihkan_pekerja(self) -> None:
        pekerja = self._pekerja
        self._pekerja = None
        if pekerja is not None:
            pekerja.deleteLater()

    def hentikan(self) -> None:
        self.penyegar.stop()
        if self._pekerja is not None and self._pekerja.isRunning():
            self._pekerja.wait(3_500)
        if self._pekerja is not None and self._pekerja.isRunning():
            lepaskan_pekerja(self._pekerja)

    def _tampilkan(self, ringkasan: DashboardSummary) -> None:
        self.label_tanggal.setText(hari_dan_tanggal(ringkasan.tanggal))

        for status, kartu in self.kartu_status.items():
            kartu.setel(str(ringkasan.per_status.get(status, 0)))

        self.kartu_total.setel(str(ringkasan.total))
        self.kartu_belum.setel(str(ringkasan.belum_selesai))
        self.kartu_menunggu.setel(ringkasan.label_rata_menunggu)
        self.kartu_layanan.setel(ringkasan.label_rata_layanan)
        self.kartu_kehadiran.setel(
            "-"
            if ringkasan.persen_kehadiran is None
            else f"{ringkasan.persen_kehadiran:.0f}%"
        )

        self._isi_kategori(ringkasan.per_kategori)

        self.kartu_rata_rating.setel(ringkasan.survey.label_rata_rata)
        self.kartu_jumlah_survey.setel(str(ringkasan.survey.jumlah))
        for nilai, label in self.label_distribusi.items():
            label.setText(str(ringkasan.survey.distribusi.get(nilai, 0)))

    def _isi_kategori(self, per_kategori: dict[str, int]) -> None:
        """
        Bangun ulang kartu jenis layanan.

        Jenis layanan bisa ditambah atau dinonaktifkan administrator saat
        aplikasi berjalan, sehingga kartunya tidak bisa dibuat sekali di awal.
        """
        while self.baris_kategori.count():
            butir = self.baris_kategori.takeAt(0)
            widget = butir.widget()
            if widget is not None:
                widget.deleteLater()

        if not per_kategori:
            self.baris_kategori.addWidget(
                keterangan("Belum ada jenis layanan yang aktif.")
            )
            return

        for nama, jumlah in per_kategori.items():
            kartu = KartuAngka(nama)
            kartu.setel(str(jumlah))
            self.baris_kategori.addWidget(kartu, stretch=1)
        self.baris_kategori.addStretch()
