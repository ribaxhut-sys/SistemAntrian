"""
Dashboard admin dan supervisor.

Angka dibuat besar dan dikelompokkan supaya keadaan hari itu terbaca dalam
sekali pandang, bukan baris demi baris. Layar ini murni memantau — tidak ada
satu pun tombol yang mengubah antrian. Tombol akses cepat hanya berpindah ke
menu lain, dan hanya muncul bila sesi memang berhak membuka menu itu
(penegakan sesungguhnya tetap di service masing-masing).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from PySide6.QtCore import QDate, QLocale, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import clock
from app.models import RATING_LABELS, QueueStatus
from app.services.dashboard_service import (
    LOKET_AKTIF,
    LOKET_ISTIRAHAT,
    STATUS_RINGKASAN,
    AktivitasTerakhir,
    DashboardOperasional,
    DashboardService,
    FilterDashboard,
    OpsiFilter,
)
from app.services.permissions import Permission
from app.services.queue_service import LABEL_STATUS
from app.services.settings_service import SettingsService
from app.ui.common import (
    PekerjaLatar,
    judul,
    keterangan,
    lepaskan_pekerja,
    pesan_untuk_user,
    tombol,
)
from app.ui.tema_petugas import warna_tema
from app.ui.style import (
    BORDER,
    DANGER,
    FONT_SIZE_HUGE,
    FONT_SIZE_LARGE,
    PRIMARY,
    SUCCESS,
    TEXT,
    TEXT_MUTED,
    WARNING,
)
from app.utils.formatting import hari_dan_tanggal

#: Warna penanda per status. Menunggu, dilewati, dan tidak hadir sengaja
#: mencolok: ketiganya yang paling perlu ditindaklanjuti supervisor.
WARNA_STATUS: dict[QueueStatus, str] = {
    QueueStatus.WAITING: WARNING,
    QueueStatus.CALLED: PRIMARY,
    QueueStatus.SKIPPED: WARNING,
    QueueStatus.SERVING: PRIMARY,
    QueueStatus.PAUSED: TEXT_MUTED,
    QueueStatus.COMPLETED: SUCCESS,
    QueueStatus.NO_SHOW: DANGER,
    QueueStatus.CANCELLED: TEXT_MUTED,
}

WARNA_LOKET = {LOKET_AKTIF: SUCCESS, LOKET_ISTIRAHAT: WARNING}

#: Akses cepat: (label, hak yang dibutuhkan, judul menu tujuan).
AKSES_CEPAT: tuple[tuple[str, Permission, str], ...] = (
    ("Laporan Detail", Permission.REPORT_VIEW, "Laporan"),
    ("Pengguna, Petugas, Loket & Layanan", Permission.MASTER_MANAGE, "Data Master"),
    ("Pengaturan Sistem", Permission.CONFIG_MANAGE, "Pengaturan"),
    ("Backup & Pemulihan", Permission.BACKUP_MANAGE, "Backup"),
    ("Kesehatan Sistem", Permission.CONFIG_MANAGE, "Kesehatan Sistem"),
)

#: Jam yang selalu tampil pada grafik, supaya bentuknya tidak melompat.
JAM_KERJA_AWAL = 7
JAM_KERJA_AKHIR = 17


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


class GrafikBatang(QWidget):
    """
    Jumlah nomor terbit per jam, digambar sendiri.

    Sengaja tanpa pustaka grafik: yang dibutuhkan hanya 24 batang, dan
    menambah dependensi untuk itu tidak sebanding dengan manfaatnya.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.nilai: dict[int, int] = {}
        self.jam_tampil: list[int] = list(range(JAM_KERJA_AWAL, JAM_KERJA_AKHIR + 1))

    def setel(self, per_jam: dict[int, int]) -> None:
        self.nilai = dict(per_jam)
        aktif = [jam for jam, jumlah in per_jam.items() if jumlah > 0]
        awal = min([JAM_KERJA_AWAL, *aktif])
        akhir = max([JAM_KERJA_AKHIR, *aktif])
        self.jam_tampil = list(range(awal, akhir + 1))
        self.update()

    @property
    def kosong(self) -> bool:
        return not any(self.nilai.values())

    def paintEvent(self, event) -> None:  # noqa: N802 - nama Qt
        pelukis = QPainter(self)
        pelukis.setRenderHint(QPainter.RenderHint.Antialiasing)
        lebar, tinggi = self.width(), self.height()
        batas_bawah = tinggi - 22
        batas_atas = 18
        jumlah_batang = max(1, len(self.jam_tampil))
        sela = lebar / jumlah_batang
        terbesar = max([1, *self.nilai.values()])

        pelukis.setPen(QPen(QColor(warna_tema(BORDER)), 1))
        pelukis.drawLine(0, batas_bawah, lebar, batas_bawah)

        for indeks, jam in enumerate(self.jam_tampil):
            jumlah = self.nilai.get(jam, 0)
            kiri = indeks * sela + sela * 0.2
            lebar_batang = sela * 0.6
            tinggi_batang = (batas_bawah - batas_atas) * jumlah / terbesar
            if jumlah:
                pelukis.setPen(Qt.PenStyle.NoPen)
                pelukis.setBrush(QColor(warna_tema(PRIMARY)))
                pelukis.drawRoundedRect(
                    QRectF(kiri, batas_bawah - tinggi_batang, lebar_batang, tinggi_batang),
                    3,
                    3,
                )
                pelukis.setPen(QColor(warna_tema(TEXT, teks=True)))
                pelukis.drawText(
                    QRectF(indeks * sela, batas_bawah - tinggi_batang - 16, sela, 14),
                    Qt.AlignmentFlag.AlignCenter,
                    str(jumlah),
                )
            pelukis.setPen(QColor(warna_tema(TEXT_MUTED, teks=True)))
            pelukis.drawText(
                QRectF(indeks * sela, batas_bawah + 4, sela, 16),
                Qt.AlignmentFlag.AlignCenter,
                f"{jam:02d}",
            )
        pelukis.end()


def _ke_qdate(nilai: date) -> QDate:
    return QDate(nilai.year, nilai.month, nilai.day)


class DashboardPage(QWidget):
    """Dashboard antrian, loket, dan kepuasan pada satu tanggal."""

    def __init__(
        self,
        dashboard: DashboardService,
        settings: SettingsService,
        parent: QWidget | None = None,
        *,
        buka_menu: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.dashboard = dashboard
        self.settings = settings
        self._buka_menu = buka_menu
        self._pekerja: PekerjaLatar | None = None
        self.ringkasan: DashboardOperasional | None = None

        self._bangun_tampilan()
        self._muat_opsi()
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
        baris_atas.addWidget(judul("Dashboard"))
        baris_atas.addStretch()
        self.label_tanggal = keterangan("")
        baris_atas.addWidget(self.label_tanggal)
        susunan.addLayout(baris_atas)

        susunan.addLayout(self._bangun_saringan())

        # Pesan kegagalan memuat. Data terakhir yang berhasil tetap tampil.
        self.label_galat = QLabel("")
        self.label_galat.setWordWrap(True)
        self.label_galat.setStyleSheet(f"color: {DANGER};")
        self.label_galat.hide()
        susunan.addWidget(self.label_galat)

        self.label_kosong = keterangan(
            "Belum ada antrian pada tanggal dan saringan ini."
        )
        self.label_kosong.hide()
        susunan.addWidget(self.label_kosong)

        susunan.addWidget(self._bangun_sekilas())
        susunan.addWidget(self._bangun_durasi())
        susunan.addWidget(self._bangun_grafik())
        susunan.addWidget(self._bangun_kategori())
        susunan.addWidget(self._bangun_loket())
        susunan.addWidget(self._bangun_petugas())
        susunan.addWidget(self._bangun_status())
        susunan.addWidget(self._bangun_survey())
        self.panel_akses = self._bangun_akses()
        susunan.addWidget(self.panel_akses)
        self.panel_aktivitas = self._bangun_aktivitas()
        susunan.addWidget(self.panel_aktivitas)
        susunan.addStretch()

        gulung.setWidget(isi)

    def _panel(self, nama: str) -> tuple[QWidget, QVBoxLayout]:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)
        susunan.addWidget(keterangan(nama))
        return panel, susunan

    def _bangun_saringan(self) -> QHBoxLayout:
        baris = QHBoxLayout()
        baris.setSpacing(8)

        baris.addWidget(QLabel("Tanggal"))
        self.kotak_tanggal = QDateEdit()
        self.kotak_tanggal.setCalendarPopup(True)
        # Nama bulan berbahasa Indonesia, apa pun bahasa Windows-nya.
        self.kotak_tanggal.setLocale(
            QLocale(QLocale.Language.Indonesian, QLocale.Country.Indonesia)
        )
        self.kotak_tanggal.setDisplayFormat("d MMM yyyy")
        self.kotak_tanggal.setMaximumDate(_ke_qdate(clock.today()))
        self.kotak_tanggal.setDate(_ke_qdate(clock.today()))
        self.kotak_tanggal.dateChanged.connect(self._saringan_berubah)
        baris.addWidget(self.kotak_tanggal)

        self.pilih_layanan = self._kotak_pilihan("Semua layanan")
        self.pilih_loket = self._kotak_pilihan("Semua loket")
        self.pilih_petugas = self._kotak_pilihan("Semua petugas")
        for kotak in (self.pilih_layanan, self.pilih_loket, self.pilih_petugas):
            baris.addWidget(kotak)

        baris.addStretch()

        self.cek_otomatis = QCheckBox("Segarkan otomatis")
        self.cek_otomatis.setChecked(True)
        self.cek_otomatis.toggled.connect(self._otomatis_berubah)
        baris.addWidget(self.cek_otomatis)

        self.tombol_segarkan = tombol("Segarkan")
        self.tombol_segarkan.clicked.connect(self.muat_ulang)
        baris.addWidget(self.tombol_segarkan)
        return baris

    def _kotak_pilihan(self, semua: str) -> QComboBox:
        kotak = QComboBox()
        kotak.addItem(semua, None)
        kotak.setMinimumWidth(150)
        kotak.currentIndexChanged.connect(self._saringan_berubah)
        return kotak

    def _bangun_sekilas(self) -> QWidget:
        panel, susunan = self._panel("Antrian pada tanggal ini")
        baris = QHBoxLayout()
        baris.setSpacing(10)
        self.kartu_total = KartuAngka("Total antrian")
        self.kartu_n_menunggu = KartuAngka("Menunggu", WARNING)
        self.kartu_n_dilayani = KartuAngka("Sedang dilayani", PRIMARY)
        self.kartu_n_selesai = KartuAngka("Selesai", SUCCESS)
        self.kartu_n_batal = KartuAngka("Batal atau dilewati", DANGER)
        for kartu in (
            self.kartu_total,
            self.kartu_n_menunggu,
            self.kartu_n_dilayani,
            self.kartu_n_selesai,
            self.kartu_n_batal,
        ):
            baris.addWidget(kartu, stretch=1)
        susunan.addLayout(baris)
        return panel

    def _bangun_durasi(self) -> QWidget:
        panel, susunan = self._panel("Waktu dan capaian")
        baris = QHBoxLayout()
        baris.setSpacing(10)
        self.kartu_belum = KartuAngka("Belum selesai", WARNING)
        self.kartu_menunggu = KartuAngka("Rata-rata menunggu")
        self.kartu_layanan = KartuAngka("Rata-rata pelayanan")
        self.kartu_kehadiran = KartuAngka("Tuntas dilayani", SUCCESS)
        for kartu in (
            self.kartu_belum,
            self.kartu_menunggu,
            self.kartu_layanan,
            self.kartu_kehadiran,
        ):
            baris.addWidget(kartu, stretch=1)
        susunan.addLayout(baris)
        return panel

    def _bangun_grafik(self) -> QWidget:
        panel, susunan = self._panel("Nomor terbit per jam")
        self.grafik = GrafikBatang()
        susunan.addWidget(self.grafik)
        return panel

    def _bangun_kategori(self) -> QWidget:
        panel, susunan = self._panel("Antrian per jenis layanan")
        self.baris_kategori = QHBoxLayout()
        self.baris_kategori.setSpacing(10)
        susunan.addLayout(self.baris_kategori)
        return panel

    def _bangun_loket(self) -> QWidget:
        panel, susunan = self._panel(
            "Loket dan petugas (keadaan saat ini; jumlah mengikuti tanggal dan saringan)"
        )
        self.tabel_loket = QTableWidget(0, 6)
        self.tabel_loket.setHorizontalHeaderLabels(
            ["Loket", "Petugas", "Status", "Nomor aktif", "Dipanggil", "Selesai"]
        )
        self._rapikan_tabel(self.tabel_loket)
        susunan.addWidget(self.tabel_loket)
        self.label_ringkas_loket = keterangan("")
        susunan.addWidget(self.label_ringkas_loket)
        return panel

    def _bangun_petugas(self) -> QWidget:
        panel, susunan = self._panel(
            "Pekerjaan setiap petugas (mengikuti tanggal dan saringan)"
        )
        self.tabel_petugas = QTableWidget(0, 10)
        self.tabel_petugas.setHorizontalHeaderLabels(
            [
                "Petugas",
                "Peran",
                "Diterbitkan",
                "Dipanggil",
                "Selesai",
                "Tidak hadir",
                "Dilewati",
                "Dibatalkan",
                "Rata-rata pelayanan",
                "Kepuasan",
            ]
        )
        self._rapikan_tabel(self.tabel_petugas)
        susunan.addWidget(self.tabel_petugas)
        return panel

    def _bangun_status(self) -> QWidget:
        panel, susunan = self._panel("Rincian per status")
        baris = QHBoxLayout()
        baris.setSpacing(10)
        self.kartu_status: dict[QueueStatus, KartuAngka] = {}
        for status in STATUS_RINGKASAN:
            kartu = KartuAngka(LABEL_STATUS[status], WARNA_STATUS[status])
            self.kartu_status[status] = kartu
            baris.addWidget(kartu, stretch=1)
        susunan.addLayout(baris)
        return panel

    def _bangun_survey(self) -> QWidget:
        panel, susunan = self._panel("Kepuasan pelayanan")

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

    def _bangun_akses(self) -> QWidget:
        """Tombol pindah menu. Hanya yang hak aksesnya dimiliki sesi."""
        panel, susunan = self._panel("Akses cepat")
        baris = QHBoxLayout()
        baris.setSpacing(8)
        self.tombol_akses: dict[str, object] = {}
        for label, hak, menu in AKSES_CEPAT:
            if not self.dashboard.auth.has_permission(hak):
                continue
            btn = tombol(label)
            btn.clicked.connect(lambda _=False, m=menu: self._pindah(m))
            self.tombol_akses[menu] = btn
            baris.addWidget(btn)
        baris.addStretch()
        susunan.addLayout(baris)
        panel.setVisible(bool(self.tombol_akses))
        return panel

    def _bangun_aktivitas(self) -> QWidget:
        """Audit log terbaru; hanya untuk pemegang CONFIG_MANAGE."""
        panel, susunan = self._panel(
            "Aktivitas terakhir (audit log lengkap ada di menu Backup)"
        )
        self.tabel_aktivitas = QTableWidget(0, 3)
        self.tabel_aktivitas.setHorizontalHeaderLabels(["Waktu", "Pelaku", "Aktivitas"])
        self._rapikan_tabel(self.tabel_aktivitas)
        susunan.addWidget(self.tabel_aktivitas)
        panel.setVisible(self.dashboard.auth.has_permission(Permission.CONFIG_MANAGE))
        return panel

    @staticmethod
    def _rapikan_tabel(tabel: QTableWidget) -> None:
        tabel.verticalHeader().setVisible(False)
        tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tabel.setAlternatingRowColors(True)
        tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabel.setMinimumHeight(140)

    # -----------------------------------------------------------------
    # Saringan dan penyegar
    # -----------------------------------------------------------------

    def _muat_opsi(self) -> None:
        """Isi kotak pilihan sekali; gagal tidak boleh menjatuhkan layar."""
        try:
            opsi: OpsiFilter = self.dashboard.opsi_filter()
        except Exception as exc:  # noqa: BLE001 - batas UI
            self._tampilkan_galat(pesan_untuk_user(exc))
            return
        for kotak, daftar in (
            (self.pilih_layanan, opsi.layanan),
            (self.pilih_loket, opsi.loket),
            (self.pilih_petugas, opsi.petugas),
        ):
            kotak.blockSignals(True)
            for id_, nama in daftar:
                kotak.addItem(nama, id_)
            kotak.blockSignals(False)

    def saringan(self) -> FilterDashboard:
        tanggal = self.kotak_tanggal.date()
        return FilterDashboard(
            tanggal=date(tanggal.year(), tanggal.month(), tanggal.day()),
            category_id=self.pilih_layanan.currentData(),
            counter_id=self.pilih_loket.currentData(),
            user_id=self.pilih_petugas.currentData(),
        )

    def _saringan_berubah(self, *_args) -> None:
        self.muat_ulang()

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

    def _otomatis_berubah(self, aktif: bool) -> None:
        if aktif and self.isVisible():
            self.penyegar.start()
        else:
            self.penyegar.stop()

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().showEvent(event)
        self.muat_ulang()
        if self.cek_otomatis.isChecked():
            self.penyegar.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - nama Qt
        self.penyegar.stop()
        super().hideEvent(event)

    def _pindah(self, menu: str) -> None:
        if self._buka_menu is not None:
            self._buka_menu(menu)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def _ambil(self, saringan: FilterDashboard):
        """Berjalan di utas latar: ringkasan, lalu audit log bila berhak."""
        ringkasan = self.dashboard.ringkasan(saringan)
        aktivitas: list[AktivitasTerakhir] | None = None
        if self.dashboard.auth.has_permission(Permission.CONFIG_MANAGE):
            try:
                aktivitas = self.dashboard.aktivitas_terakhir()
            except Exception:  # noqa: BLE001 - audit tidak boleh menggagalkan angka
                aktivitas = None
        return ringkasan, aktivitas

    def muat_ulang(self) -> None:
        saringan = self.saringan()
        if self.isVisible():
            if self._pekerja is not None:
                return
            pekerja = PekerjaLatar(lambda: self._ambil(saringan), self)
            pekerja.berhasil.connect(self._tampilkan_hasil)
            pekerja.gagal.connect(self._galat_memuat)
            pekerja.finished.connect(self._bersihkan_pekerja)
            self._pekerja = pekerja
            pekerja.start()
            return
        try:
            hasil = self._ambil(saringan)
        except Exception as exc:  # noqa: BLE001 - batas UI
            self._galat_memuat(exc)
            return
        self._tampilkan_hasil(hasil)

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

    def _galat_memuat(self, exc: Exception) -> None:
        self._tampilkan_galat(pesan_untuk_user(exc))

    def _tampilkan_galat(self, pesan: str) -> None:
        self.label_galat.setText(
            f"Data belum dapat dimuat: {pesan} Angka di bawah adalah yang "
            "terakhir berhasil dimuat."
        )
        self.label_galat.show()

    def _tampilkan_hasil(self, hasil: tuple) -> None:
        ringkasan, aktivitas = hasil
        self.label_galat.hide()
        self._tampilkan(ringkasan)
        if aktivitas is not None:
            self._isi_aktivitas(aktivitas)

    def _tampilkan(self, ringkasan: DashboardOperasional) -> None:
        self.ringkasan = ringkasan
        self.label_tanggal.setText(hari_dan_tanggal(ringkasan.tanggal))
        self.label_kosong.setVisible(ringkasan.total == 0)

        self.kartu_total.setel(str(ringkasan.total))
        self.kartu_n_menunggu.setel(str(ringkasan.menunggu))
        self.kartu_n_dilayani.setel(str(ringkasan.dilayani))
        self.kartu_n_selesai.setel(str(ringkasan.selesai))
        self.kartu_n_batal.setel(str(ringkasan.batal_lewati))

        for status, kartu in self.kartu_status.items():
            kartu.setel(str(ringkasan.per_status.get(status, 0)))

        tuntas = sum(
            ringkasan.per_status.get(s, 0)
            for s in (QueueStatus.COMPLETED, QueueStatus.NO_SHOW, QueueStatus.CANCELLED)
        )
        self.kartu_belum.setel(str(ringkasan.total - tuntas))
        self.kartu_menunggu.setel(ringkasan.label_rata_menunggu)
        self.kartu_layanan.setel(ringkasan.label_rata_layanan)
        selesai = ringkasan.per_status.get(QueueStatus.COMPLETED, 0)
        self.kartu_kehadiran.setel(
            "-" if tuntas == 0 else f"{selesai / tuntas * 100:.0f}%"
        )

        self.grafik.setel(ringkasan.per_jam)
        self._isi_kategori(ringkasan.per_layanan)
        self._isi_loket(ringkasan)
        self._isi_petugas(ringkasan)

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

    def _isi_loket(self, ringkasan: DashboardOperasional) -> None:
        tabel = self.tabel_loket
        tabel.setRowCount(len(ringkasan.loket))
        for baris, loket in enumerate(ringkasan.loket):
            nilai = (
                loket.nama,
                loket.petugas or "—",
                loket.label_status,
                loket.nomor_aktif or "—",
                str(loket.dipanggil),
                str(loket.selesai),
            )
            for kolom, teks in enumerate(nilai):
                butir = QTableWidgetItem(teks)
                if kolom >= 4:
                    butir.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if kolom == 2:
                    butir.setForeground(QColor(WARNA_LOKET.get(loket.status, DANGER)))
                tabel.setItem(baris, kolom, butir)
        self.label_ringkas_loket.setText(
            f"{ringkasan.jumlah_loket_aktif} aktif · "
            f"{ringkasan.jumlah_loket_istirahat} istirahat · "
            f"{ringkasan.jumlah_loket_tidak_aktif} tidak aktif"
            if ringkasan.loket
            else "Belum ada loket."
        )

    def _isi_petugas(self, ringkasan: DashboardOperasional) -> None:
        tabel = self.tabel_petugas
        tabel.setRowCount(len(ringkasan.per_petugas))
        for baris, p in enumerate(ringkasan.per_petugas):
            nilai = (
                p.nama,
                p.peran,
                str(p.diterbitkan),
                str(p.dipanggil),
                str(p.selesai),
                str(p.tidak_hadir),
                str(p.dilewati),
                str(p.dibatalkan),
                p.label_rata_layanan,
                p.label_kepuasan,
            )
            for kolom, teks in enumerate(nilai):
                butir = QTableWidgetItem(teks)
                if kolom >= 2:
                    butir.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                tabel.setItem(baris, kolom, butir)

    def _isi_aktivitas(self, aktivitas: list[AktivitasTerakhir]) -> None:
        tabel = self.tabel_aktivitas
        tabel.setRowCount(len(aktivitas))
        for baris, entri in enumerate(aktivitas):
            for kolom, teks in enumerate(
                (entri.waktu.strftime("%d/%m %H:%M:%S"), entri.pelaku, entri.aksi)
            ):
                tabel.setItem(baris, kolom, QTableWidgetItem(teks))
