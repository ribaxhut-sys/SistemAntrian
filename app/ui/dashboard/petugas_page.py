"""
Dashboard petugas loket: keadaan kerja pribadi hari ini.

Layar ini menjawab "bagaimana meja saya sekarang": nomor yang sedang
dipegang, siapa berikutnya, berapa sisa antrean, dan apa yang sudah
dikerjakan hari ini. Isinya hanya milik petugas yang sedang masuk (lihat
`DashboardService.ringkasan_petugas`) dan tidak memuat data pribadi apa pun.

Tombol tindakan (panggil, panggil ulang, selesai, lewati, batalkan) tetap
hanya ada di menu Pelayanan. Mengulang tombol itu di sini berarti dua layar
yang sama-sama dapat mengubah satu nomor, lengkap dengan dua salinan
konfirmasi dan aturan survey/pengaduannya — sumber regresi yang sengaja
dihindari. Tombol di layar ini hanya berpindah ke menu Pelayanan.
"""

from __future__ import annotations

from collections.abc import Callable

from datetime import date

from PySide6.QtCore import QDate, QEvent, QLocale, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import clock
from app.models import QueueStatus
from app.services.dashboard_service import (
    PETUGAS_AKTIF,
    PETUGAS_ISTIRAHAT,
    DashboardPetugas,
    DashboardService,
)
from app.services.settings_service import SettingsService
from app.ui.common import (
    PekerjaLatar,
    judul,
    keterangan,
    lepaskan_pekerja,
    pesan_untuk_user,
    tombol,
)
from app.ui.dashboard.dashboard_page import KartuAngka
from app.ui.style import (
    BORDER,
    DANGER,
    PRIMARY,
    SUCCESS,
    TEXT,
    TEXT_MUTED,
    WARNING,
)
from app.utils.formatting import durasi_singkat, hari_dan_tanggal

#: Jeda penyegaran paling lama; petugas butuh angka yang lebih segar daripada
#: supervisor, sehingga nilai `dashboard.refresh_seconds` dipotong ke sini.
JEDA_MAKS_DETIK = 15

WARNA_STATUS_PETUGAS = {PETUGAS_AKTIF: SUCCESS, PETUGAS_ISTIRAHAT: WARNING}


def _kotak_tanggal() -> QDateEdit:
    kotak = QDateEdit()
    kotak.setCalendarPopup(True)
    kotak.setLocale(QLocale(QLocale.Language.Indonesian, QLocale.Country.Indonesia))
    kotak.setDisplayFormat("d MMM yyyy")
    hari = clock.today()
    kotak.setMaximumDate(QDate(hari.year, hari.month, hari.day))
    kotak.setDate(QDate(hari.year, hari.month, hari.day))
    return kotak


def _tanggal_dipilih(kotak: QDateEdit) -> date:
    nilai = kotak.date()
    return date(nilai.year(), nilai.month(), nilai.day())


class DashboardPetugasPage(QWidget):
    """
    Ringkasan kerja satu petugas loket, disusun agar muat tanpa gulir.

    Dua kolom: kiri nomor yang sedang dipegang, kanan antrean berikutnya
    dan riwayat. Tabel tidak memakai scrollbar; jumlah baris yang tampil
    mengikuti tinggi yang tersedia dan sisanya disebut sebagai "+N lainnya"
    (daftar lengkap ada di Pelayanan dan Laporan).
    """

    #: Paling sedikit sekian baris tabel selalu tampil, sehingga tata letak
    #: yang belum sempat diukur tidak menampilkan tabel kosong.
    BARIS_MINIMUM = 3

    def __init__(
        self,
        dashboard: DashboardService,
        settings: SettingsService,
        parent: QWidget | None = None,
        *,
        buka_menu: Callable[[str], None] | None = None,
        menu_pelayanan: str = "Pelayanan",
    ) -> None:
        super().__init__(parent)
        self.dashboard = dashboard
        self.settings = settings
        self._buka_menu = buka_menu
        self._menu_pelayanan = menu_pelayanan
        self._pekerja: PekerjaLatar | None = None
        self.data: DashboardPetugas | None = None

        self._bangun_tampilan()
        self._pasang_penyegar()
        self.muat_ulang()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(20, 14, 20, 14)
        susunan.setSpacing(10)

        atas = QHBoxLayout()
        atas.setSpacing(12)
        atas.addWidget(judul("Ringkasan Saya"))
        self.label_identitas = QLabel("")
        self.label_identitas.setStyleSheet(f"font-size: 15px; color: {TEXT};")
        atas.addWidget(self.label_identitas)
        self.label_status = QLabel("")
        self.label_status.setStyleSheet("font-weight: 700;")
        atas.addWidget(self.label_status)
        atas.addStretch()
        self.tombol_pelayanan = tombol("Buka Pelayanan", variant="primary")
        self.tombol_pelayanan.setMinimumHeight(40)
        self.tombol_pelayanan.setToolTip(
            "Panggil, panggil ulang, selesai, lewati, dan batalkan ada di menu Pelayanan."
        )
        self.tombol_pelayanan.clicked.connect(self._buka_pelayanan)
        atas.addWidget(self.tombol_pelayanan)
        susunan.addLayout(atas)

        self.label_peringatan = QLabel("")
        self.label_peringatan.setWordWrap(True)
        self.label_peringatan.setStyleSheet(
            f"background: #FFFBEB; color: {WARNING}; border: 1px solid {BORDER};"
            " border-radius: 6px; padding: 8px;"
        )
        self.label_peringatan.hide()
        susunan.addWidget(self.label_peringatan)

        self.label_galat = QLabel("")
        self.label_galat.setWordWrap(True)
        self.label_galat.setStyleSheet(f"color: {DANGER};")
        self.label_galat.hide()
        susunan.addWidget(self.label_galat)

        badan = QHBoxLayout()
        badan.setSpacing(12)
        badan.addWidget(self._bangun_aktif(), stretch=2)
        badan.addLayout(self._bangun_kanan(), stretch=3)
        susunan.addLayout(badan, stretch=1)

    def _bungkus(self, objek: str) -> tuple[QFrame, QVBoxLayout]:
        kotak = QFrame()
        kotak.setObjectName(objek)
        kotak.setStyleSheet(
            f"QFrame#{objek} {{ background: white; border: 1px solid {BORDER};"
            " border-radius: 8px; }"
        )
        dalam = QVBoxLayout(kotak)
        dalam.setContentsMargins(16, 12, 16, 12)
        dalam.setSpacing(4)
        return kotak, dalam

    def _bangun_aktif(self) -> QWidget:
        kotak, dalam = self._bungkus("kotakAktif")
        dalam.addWidget(keterangan("Sedang dilayani"))
        dalam.addStretch(1)
        self.label_nomor = QLabel("—")
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dalam.addWidget(self.label_nomor)
        self._ukuran_nomor(64)
        self.label_layanan = QLabel("Belum ada nomor yang dipegang")
        self.label_layanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_layanan.setWordWrap(True)
        self.label_layanan.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 15px;")
        dalam.addWidget(self.label_layanan)
        self.label_waktu = QLabel("")
        self.label_waktu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_waktu.setStyleSheet("font-size: 15px; font-weight: 600;")
        dalam.addWidget(self.label_waktu)
        dalam.addStretch(1)
        # Hitungan sehari dalam satu baris, bukan lima kartu.
        self.label_hitungan = QLabel("")
        self.label_hitungan.setWordWrap(True)
        self.label_hitungan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_hitungan.setStyleSheet(
            f"color: {TEXT}; font-size: 13px; border-top: 1px solid {BORDER};"
            " padding-top: 8px;"
        )
        dalam.addWidget(self.label_hitungan)
        return kotak

    def _bangun_kanan(self) -> QVBoxLayout:
        kanan = QVBoxLayout()
        kanan.setSpacing(10)

        berikut, dalam = self._bungkus("kotakBerikutnya")
        kepala = QHBoxLayout()
        kepala.addWidget(keterangan("Antrean berikutnya"))
        kepala.addStretch()
        self.label_sisa = QLabel("0")
        self.label_sisa.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {WARNING};"
        )
        kepala.addWidget(self.label_sisa)
        kepala.addWidget(keterangan("tersisa"))
        dalam.addLayout(kepala)
        self.tabel_berikutnya = self._tabel(["Nomor", "Layanan", "Menunggu"])
        dalam.addWidget(self.tabel_berikutnya, stretch=1)
        self.label_lainnya_berikut = keterangan("")
        dalam.addWidget(self.label_lainnya_berikut)
        kanan.addWidget(berikut, stretch=1)

        riwayat, dalam = self._bungkus("kotakRiwayat")
        kepala = QHBoxLayout()
        kepala.addWidget(keterangan("Riwayat pelayanan saya"))
        kepala.addStretch()
        self.kotak_tanggal = _kotak_tanggal()
        self.kotak_tanggal.dateChanged.connect(lambda *_: self.muat_ulang())
        kepala.addWidget(self.kotak_tanggal)
        dalam.addLayout(kepala)
        self.tabel_riwayat = self._tabel(
            ["Waktu", "Nomor", "Layanan", "Status", "Menunggu", "Pelayanan"]
        )
        dalam.addWidget(self.tabel_riwayat, stretch=1)
        self.label_riwayat_kosong = keterangan(
            "Belum ada nomor yang Anda tangani pada tanggal ini."
        )
        dalam.addWidget(self.label_riwayat_kosong)
        self.label_lainnya_riwayat = keterangan("")
        dalam.addWidget(self.label_lainnya_riwayat)
        kanan.addWidget(riwayat, stretch=1)
        return kanan

    def _tabel(self, kolom: list[str]) -> QTableWidget:
        tabel = QTableWidget(0, len(kolom))
        tabel.setHorizontalHeaderLabels(kolom)
        tabel.verticalHeader().setVisible(False)
        tabel.verticalHeader().setDefaultSectionSize(26)
        tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tabel.setAlternatingRowColors(True)
        tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Tanpa scrollbar: baris yang tidak muat disebut "+N lainnya".
        tabel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tabel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tabel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tabel.setMinimumHeight(30 + 26 * self.BARIS_MINIMUM)
        # Tabel baru mendapat ukuran sesudah halaman; isi ulang saat itu.
        tabel.viewport().installEventFilter(self)
        return tabel

    def eventFilter(self, sumber, event) -> bool:  # noqa: N802 - nama Qt
        if (
            event.type() == QEvent.Type.Resize
            and self.data is not None
            and sumber in (
                getattr(self, "tabel_berikutnya", None) and self.tabel_berikutnya.viewport(),
                getattr(self, "tabel_riwayat", None) and self.tabel_riwayat.viewport(),
            )
        ):
            QTimer.singleShot(0, self._isi_ulang)
        return super().eventFilter(sumber, event)

    def _isi_ulang(self) -> None:
        if self.data is not None:
            self._isi_tabel(self.data)

    def _ukuran_nomor(self, piksel: int) -> None:
        self.label_nomor.setStyleSheet(
            f"font-size: {piksel}px; font-weight: 800; color: {PRIMARY};"
        )

    # -----------------------------------------------------------------
    # Ukuran
    # -----------------------------------------------------------------

    def _baris_muat(self, tabel: QTableWidget) -> int:
        tinggi = tabel.viewport().height()
        return max(self.BARIS_MINIMUM, tinggi // 26)

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().resizeEvent(event)
        self._ukuran_nomor(64 if self.height() >= 640 else 40)
        if self.data is not None:
            self._isi_tabel(self.data)

    # -----------------------------------------------------------------
    # Penyegar
    # -----------------------------------------------------------------

    def _pasang_penyegar(self) -> None:
        detik = max(5, self.settings.get_int("dashboard.refresh_seconds", 30))
        self.penyegar = QTimer(self)
        self.penyegar.timeout.connect(self.muat_ulang)
        self.penyegar.setInterval(min(detik, JEDA_MAKS_DETIK) * 1000)

        # Hanya menggeser label "sudah berapa lama dipanggil"; tidak
        # menyentuh database.
        self.detik_label = QTimer(self)
        self.detik_label.timeout.connect(self._perbarui_waktu)
        self.detik_label.setInterval(1000)

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().showEvent(event)
        self.muat_ulang()
        self.penyegar.start()
        self.detik_label.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - nama Qt
        self.penyegar.stop()
        self.detik_label.stop()
        super().hideEvent(event)

    def hentikan(self) -> None:
        self.penyegar.stop()
        self.detik_label.stop()
        if self._pekerja is not None and self._pekerja.isRunning():
            self._pekerja.wait(3_500)
        if self._pekerja is not None and self._pekerja.isRunning():
            lepaskan_pekerja(self._pekerja)

    def _buka_pelayanan(self) -> None:
        if self._buka_menu is not None:
            self._buka_menu(self._menu_pelayanan)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        if self.isVisible():
            if self._pekerja is not None:
                return
            tanggal = _tanggal_dipilih(self.kotak_tanggal)
            pekerja = PekerjaLatar(
                lambda: self.dashboard.ringkasan_petugas(tanggal), self
            )
            pekerja.berhasil.connect(self._tampilkan)
            pekerja.gagal.connect(self._galat_memuat)
            pekerja.finished.connect(self._bersihkan_pekerja)
            self._pekerja = pekerja
            pekerja.start()
            return
        try:
            data = self.dashboard.ringkasan_petugas(_tanggal_dipilih(self.kotak_tanggal))
        except Exception as exc:  # noqa: BLE001 - batas UI
            self._galat_memuat(exc)
            return
        self._tampilkan(data)

    def _bersihkan_pekerja(self) -> None:
        pekerja = self._pekerja
        self._pekerja = None
        if pekerja is not None:
            pekerja.deleteLater()

    def _galat_memuat(self, exc: Exception) -> None:
        self.label_galat.setText(
            f"Data belum dapat dimuat: {pesan_untuk_user(exc)} "
            "Angka di bawah adalah yang terakhir berhasil dimuat."
        )
        self.label_galat.show()

    def _tampilkan(self, data: DashboardPetugas) -> None:
        self.data = data
        self.label_galat.hide()
        self.label_identitas.setText(
            f"{data.nama_petugas}  ·  "
            f"{data.nama_loket if data.nama_loket else 'Loket belum dipilih'}"
        )
        self.label_status.setText(f"● {data.label_status}")
        self.label_status.setStyleSheet(
            f"font-weight: 700; color: {WARNA_STATUS_PETUGAS.get(data.status, DANGER)};"
        )

        peringatan = data.peringatan
        self.label_peringatan.setText(peringatan or "")
        self.label_peringatan.setVisible(peringatan is not None)

        if data.aktif is not None:
            self.label_nomor.setText(data.aktif.nomor)
            self.label_layanan.setText(f"{data.aktif.layanan}  ·  {data.aktif.label_status}")
        else:
            self.label_nomor.setText("—")
            self.label_layanan.setText("Belum ada nomor yang dipegang")
        self._perbarui_waktu()

        self.label_hitungan.setText(
            f"Selesai {data.selesai}  ·  Tidak hadir {data.tidak_hadir}  ·  "
            f"Dilewati {data.dilewati}  ·  Batal {data.dibatalkan}  ·  "
            f"Rata-rata {data.label_rata_layanan}"
        )
        self.label_sisa.setText(str(data.sisa_antrian))
        self._isi_tabel(data)

    def _isi_tabel(self, data: DashboardPetugas) -> None:
        """Isi tabel sebanyak baris yang muat; sisanya jadi "+N lainnya"."""
        muat = self._baris_muat(self.tabel_berikutnya)
        tampil = data.berikutnya[:muat]
        self.tabel_berikutnya.setRowCount(len(tampil))
        for baris, butir in enumerate(tampil):
            for kolom, teks in enumerate(
                (butir.nomor, butir.layanan, durasi_singkat(butir.menunggu_detik))
            ):
                self.tabel_berikutnya.setItem(baris, kolom, QTableWidgetItem(teks))
        sisa = data.sisa_antrian - len(tampil)
        self.label_lainnya_berikut.setText(f"+{sisa} lainnya" if sisa > 0 else "")
        self.label_lainnya_berikut.setVisible(sisa > 0)

        muat = self._baris_muat(self.tabel_riwayat)
        tampil_r = data.riwayat[:muat]
        self.tabel_riwayat.setRowCount(len(tampil_r))
        self.label_riwayat_kosong.setVisible(not data.riwayat)
        for baris, r in enumerate(tampil_r):
            nilai = (
                r.waktu.strftime("%H:%M:%S") if r.waktu else "—",
                r.nomor,
                r.layanan,
                r.label_status,
                durasi_singkat(r.menunggu_detik),
                durasi_singkat(r.layanan_detik),
            )
            for kolom, teks in enumerate(nilai):
                butir = QTableWidgetItem(teks)
                if kolom == 3 and r.status is not QueueStatus.COMPLETED:
                    butir.setForeground(QColor(WARNING))
                self.tabel_riwayat.setItem(baris, kolom, butir)
        lebih = len(data.riwayat) - len(tampil_r)
        self.label_lainnya_riwayat.setText(
            f"+{lebih} lainnya (lengkap di Laporan)" if lebih > 0 else ""
        )
        self.label_lainnya_riwayat.setVisible(lebih > 0)

    def _perbarui_waktu(self) -> None:
        """Berapa lama nomor aktif sudah dipanggil, dihitung dari jam sekarang."""
        data = self.data
        if data is None or data.aktif is None or data.aktif.dipanggil_pada is None:
            self.label_waktu.setText("")
            return
        selisih = max(0.0, (clock.now() - data.aktif.dipanggil_pada).total_seconds())
        self.label_waktu.setText(f"Dipanggil {durasi_singkat(selisih)} lalu")


class DashboardPendaftaranPage(QWidget):
    """Nomor yang diterbitkan petugas pendaftaran yang sedang masuk."""

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
        self.data = None

        luar = QVBoxLayout(self)
        luar.setContentsMargins(24, 20, 24, 20)
        luar.setSpacing(14)

        atas = QHBoxLayout()
        atas.addWidget(judul("Ringkasan Saya"))
        atas.addStretch()
        atas.addWidget(QLabel("Pekerjaan pada"))
        self.kotak_tanggal = _kotak_tanggal()
        self.kotak_tanggal.dateChanged.connect(lambda *_: self.muat_ulang())
        atas.addWidget(self.kotak_tanggal)
        luar.addLayout(atas)

        self.label_identitas = QLabel("")
        luar.addWidget(self.label_identitas)

        self.label_galat = QLabel("")
        self.label_galat.setWordWrap(True)
        self.label_galat.setStyleSheet(f"color: {DANGER};")
        self.label_galat.hide()
        luar.addWidget(self.label_galat)

        baris = QHBoxLayout()
        self.kartu_total = KartuAngka("Nomor diterbitkan", PRIMARY)
        baris.addWidget(self.kartu_total, stretch=1)
        self.baris_layanan = QHBoxLayout()
        baris.addLayout(self.baris_layanan, stretch=4)
        luar.addLayout(baris)

        luar.addWidget(keterangan("Nomor terakhir yang saya terbitkan"))
        self.tabel = QTableWidget(0, 4)
        self.tabel.setHorizontalHeaderLabels(["Waktu", "Nomor", "Layanan", "Status"])
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        luar.addWidget(self.tabel, stretch=1)
        self.label_kosong = keterangan("Belum ada nomor yang Anda terbitkan pada tanggal ini.")
        luar.addWidget(self.label_kosong)

        detik = max(5, self.settings.get_int("dashboard.refresh_seconds", 30))
        self.penyegar = QTimer(self)
        self.penyegar.timeout.connect(self.muat_ulang)
        self.penyegar.setInterval(detik * 1000)
        self.muat_ulang()

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().showEvent(event)
        self.muat_ulang()
        self.penyegar.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - nama Qt
        self.penyegar.stop()
        super().hideEvent(event)

    def hentikan(self) -> None:
        self.penyegar.stop()
        if self._pekerja is not None and self._pekerja.isRunning():
            self._pekerja.wait(3_500)
        if self._pekerja is not None and self._pekerja.isRunning():
            lepaskan_pekerja(self._pekerja)

    def muat_ulang(self) -> None:
        tanggal = _tanggal_dipilih(self.kotak_tanggal)
        if self.isVisible():
            if self._pekerja is not None:
                return
            pekerja = PekerjaLatar(
                lambda: self.dashboard.ringkasan_pendaftaran(tanggal), self
            )
            pekerja.berhasil.connect(self._tampilkan)
            pekerja.gagal.connect(self._galat)
            pekerja.finished.connect(self._bersihkan)
            self._pekerja = pekerja
            pekerja.start()
            return
        try:
            data = self.dashboard.ringkasan_pendaftaran(tanggal)
        except Exception as exc:  # noqa: BLE001 - batas UI
            self._galat(exc)
            return
        self._tampilkan(data)

    def _bersihkan(self) -> None:
        pekerja = self._pekerja
        self._pekerja = None
        if pekerja is not None:
            pekerja.deleteLater()

    def _galat(self, exc: Exception) -> None:
        self.label_galat.setText(
            f"Data belum dapat dimuat: {pesan_untuk_user(exc)} "
            "Angka di bawah adalah yang terakhir berhasil dimuat."
        )
        self.label_galat.show()

    def _tampilkan(self, data) -> None:
        self.data = data
        self.label_galat.hide()
        self.label_identitas.setText(
            f"{data.nama_petugas}  ·  {hari_dan_tanggal(data.tanggal)}"
        )
        self.kartu_total.setel(str(data.total))
        while self.baris_layanan.count():
            butir = self.baris_layanan.takeAt(0)
            if butir.widget() is not None:
                butir.widget().deleteLater()
        for nama, jumlah in data.per_layanan.items():
            kartu = KartuAngka(nama)
            kartu.setel(str(jumlah))
            self.baris_layanan.addWidget(kartu)
        self.tabel.setRowCount(len(data.terakhir))
        self.label_kosong.setVisible(not data.terakhir)
        for baris, n in enumerate(data.terakhir):
            for kolom, teks in enumerate(
                (n.waktu.strftime("%H:%M:%S"), n.nomor, n.layanan, n.label_status)
            ):
                self.tabel.setItem(baris, kolom, QTableWidgetItem(teks))
