"""
Layar Laporan: antrian dan kepuasan pada rentang tanggal, untuk supervisor.

Murni membaca. Rentang dipilih dari dua tanggal atau tombol cepat, lalu
angka ringkasan dan empat tabel (per hari, layanan, loket, petugas) diisi
dari satu panggilan ReportService. Ekspor PDF dan Excel memakai laporan
yang sedang tampil, bukan menghitung ulang — yang dicetak persis yang dilihat.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QLocale, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import clock
from app.core.logger import get_logger
from app.services.report_export import ekspor_excel, ekspor_pdf, nama_berkas_bawaan
from app.services.report_service import (
    JUDUL_TABEL,
    KartuRingkasan,
    Laporan,
    ReportService,
    deret_tren,
    kartu_ringkasan,
    kolom_riwayat,
    kolom_tabel,
    sorotan,
)
from app.ui.common import (
    PekerjaLatar,
    judul,
    keterangan,
    lepaskan_pekerja,
    pesan_untuk_user,
    tampilkan_peringatan,
    tombol,
)
from app.ui.dashboard.dashboard_page import KartuAngka
from app.ui.dashboard.grafik_tren import GrafikTren
from app.ui.style import (
    DANGER,
    FONT_SIZE_HUGE,
    PRIMARY_SOFT,
    SUCCESS,
    TEXT,
    TEXT_MUTED,
    WARNING,
)
from app.utils.formatting import tanggal_pendek

logger = get_logger("laporan")

WARNA_NADA = {"netral": TEXT, "baik": SUCCESS, "waspada": WARNING, "buruk": DANGER}
WARNA_PERUBAHAN = {"netral": TEXT_MUTED, "baik": SUCCESS, "buruk": DANGER}

#: Persen catatan identik (dari catatan yang ditulis sendiri) yang diberi warna
#: peringatan pada tabel Per petugas.
AMBANG_CATATAN_IDENTIK = 30

PESAN_KOSONG = "Belum ada antrian pada rentang ini. Coba pilih rentang tanggal lain."

#: Kolom riwayat per nomor di layar (Excel memuat semuanya).
KOLOM_RIWAYAT_LAYAR = (
    "Tanggal",
    "Nomor",
    "Jenis layanan",
    "Status",
    "Jam mulai dilayani",
    "Jam selesai",
    "Lama pelayanan",
    "Nilai survey",
)


def _ke_qdate(nilai: date) -> QDate:
    return QDate(nilai.year, nilai.month, nilai.day)


def _dari_qdate(nilai: QDate) -> date:
    return date(nilai.year(), nilai.month(), nilai.day())


def rentang_cepat(nama: str, hari_ini: date) -> tuple[date, date]:
    """Rentang untuk tombol cepat."""
    if nama == "hari_ini":
        return hari_ini, hari_ini
    if nama == "7_hari":
        return hari_ini - timedelta(days=6), hari_ini
    if nama == "tahun_ini":
        return hari_ini.replace(month=1, day=1), hari_ini
    awal_bulan = hari_ini.replace(day=1)
    if nama == "bulan_ini":
        return awal_bulan, hari_ini
    akhir_lalu = awal_bulan - timedelta(days=1)
    return akhir_lalu.replace(day=1), akhir_lalu


def label_rentang(dari: date, sampai: date) -> str:
    """'1 Okt – 19 Okt 2026 (19 hari)'; tahun ditulis di kedua ujung bila berbeda."""
    hari = (sampai - dari).days + 1
    if dari == sampai:
        awal = f"{tanggal_pendek(dari)} {dari.year}"
    elif dari.year == sampai.year:
        awal = f"{tanggal_pendek(dari)} – {tanggal_pendek(sampai)} {sampai.year}"
    else:
        awal = (
            f"{tanggal_pendek(dari)} {dari.year} – "
            f"{tanggal_pendek(sampai)} {sampai.year}"
        )
    return f"{awal} ({hari} hari)"


def _warna_kepuasan(nilai: float) -> str:
    return SUCCESS if nilai >= 4 else WARNING if nilai >= 3 else DANGER


class ItemUrut(QTableWidgetItem):
    """Sel yang diurutkan menurut nilainya (angka, tanggal, jam), bukan teksnya."""

    def __init__(self, teks: str, nilai) -> None:
        super().__init__(teks)
        if nilai is None:
            self._kunci = (0, 0)
        elif isinstance(nilai, str):
            self._kunci = (1, nilai.lower())
        else:
            self._kunci = (1, nilai)

    def __lt__(self, lain) -> bool:
        if isinstance(lain, ItemUrut):
            try:
                return self._kunci < lain._kunci
            except TypeError:
                return str(self._kunci) < str(lain._kunci)
        return super().__lt__(lain)


#: Judul kolom di layar yang dipecah dua baris agar kolom tidak melebar;
#: PDF dan Excel tetap memakai judul aslinya.
JUDUL_LAYAR = {
    "Rata-rata menunggu": "Rata-rata\nmenunggu",
    "Rata-rata pelayanan": "Rata-rata\npelayanan",
    "Lama pelayanan": "Lama\npelayanan",
    "Jam mulai dilayani": "Jam mulai\ndilayani",
}

#: Ruang di luar teks judul: bantalan sel dan panah urutan.
RUANG_JUDUL = 16 + 14


class TabelLaporan(QTableWidget):
    """
    Tabel tanpa gulir mendatar: lebar kolom mengikuti lebar tabel.

    Tiap kolom minimal selebar judulnya (baris terpanjang); sisanya dibagi
    menurut lebar alami isi, dan isi yang terlalu panjang dipotong dengan
    elipsis. Gulir tegak tetap ada untuk riwayat yang panjang.
    """

    def __init__(self, judul: list[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(judul), parent)
        self.setHorizontalHeaderLabels(judul)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        kepala = self.horizontalHeader()
        kepala.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        kepala.setStretchLastSection(False)
        kepala.setSectionsClickable(True)
        self._alami: list[int] = [0] * len(judul)

    def lebar_judul(self, kolom: int) -> int:
        """Lebar minimal kolom: baris judul terpanjang beserta ruangnya."""
        metrik = self.horizontalHeader().fontMetrics()
        teks = self.horizontalHeaderItem(kolom).text()
        return max(metrik.horizontalAdvance(b) for b in teks.split("\n")) + RUANG_JUDUL

    def ukur_isi(self) -> None:
        """Ukur lebar alami tiap kolom dari isinya; panggil setelah tabel diisi."""
        self.resizeColumnsToContents()
        self._alami = [self.columnWidth(c) for c in range(self.columnCount())]
        self.sesuaikan()

    def sesuaikan(self) -> None:
        jumlah = self.columnCount()
        lebar_tersedia = self.viewport().width()
        if jumlah == 0 or lebar_tersedia <= 0:
            return
        minimum = [self.lebar_judul(c) for c in range(jumlah)]
        alami = [max(a, m) for a, m in zip(self._alami, minimum, strict=True)]
        if sum(alami) <= lebar_tersedia:
            sisa = lebar_tersedia - sum(alami)
            lebar = [a + sisa * a / sum(alami) for a in alami]
        elif sum(minimum) <= lebar_tersedia:
            sisa = lebar_tersedia - sum(minimum)
            lebihan = [a - m for a, m in zip(alami, minimum, strict=True)]
            lebar = [m + sisa * x / sum(lebihan) for m, x in zip(minimum, lebihan, strict=True)]
        else:
            lebar = [lebar_tersedia * m / sum(minimum) for m in minimum]
        bulat = [int(x) for x in lebar]
        bulat[-1] += lebar_tersedia - sum(bulat)
        for kolom, nilai in enumerate(bulat):
            self.setColumnWidth(kolom, nilai)

    def resizeEvent(self, kejadian) -> None:  # noqa: N802 - nama Qt
        super().resizeEvent(kejadian)
        self.sesuaikan()


class KartuRingkas(KartuAngka):
    """Kartu angka dengan warna menurut makna, keterangan, dan perubahan periode."""

    def __init__(self, nama: str, parent: QWidget | None = None) -> None:
        super().__init__(nama, TEXT, parent)
        self.label_nama = self.findChildren(QLabel)[-1]
        self.catatan = self._label_kecil()
        self.perubahan = self._label_kecil()
        self.layout().addWidget(self.catatan)
        self.layout().addWidget(self.perubahan)

    @staticmethod
    def _label_kecil() -> QLabel:
        label = QLabel("")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        label.hide()
        return label

    def isi(self, kartu: KartuRingkasan) -> None:
        self.label_nama.setText(kartu.nama)
        self.nilai.setText(kartu.nilai)
        self.nilai.setStyleSheet(
            f"font-size: {FONT_SIZE_HUGE}px; font-weight: 700;"
            f" color: {WARNA_NADA.get(kartu.nada, TEXT)};"
        )
        self.catatan.setText(kartu.catatan)
        self.catatan.setVisible(bool(kartu.catatan))
        self.perubahan.setText(kartu.perubahan)
        self.perubahan.setStyleSheet(
            f"color: {WARNA_PERUBAHAN.get(kartu.nada_perubahan, TEXT_MUTED)};"
            " font-size: 12px;"
        )
        self.perubahan.setVisible(bool(kartu.perubahan))


class LaporanPage(QWidget):
    """Laporan rentang tanggal."""

    def __init__(
        self,
        layanan: ReportService,
        kantor: str = "",
        parent: QWidget | None = None,
        *,
        pribadi: bool = False,
    ) -> None:
        super().__init__(parent)
        self.layanan = layanan
        self.kantor = kantor
        self.pribadi = pribadi
        self.laporan: Laporan | None = None
        self._pekerja_ekspor: PekerjaLatar | None = None
        self._tujuan_ekspor: Path | None = None
        self._sementara_ekspor: Path | None = None
        self._bangun()
        self._pakai_rentang("bulan_ini")

    # -----------------------------------------------------------------

    def _bangun(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(14)
        susunan.addWidget(judul("Laporan Saya" if self.pribadi else "Laporan"))
        susunan.addWidget(
            keterangan(
                "Riwayat pelayanan Anda pada rentang tanggal yang dipilih."
                if self.pribadi
                else "Antrian dan kepuasan pada rentang tanggal yang dipilih."
            )
        )

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(QLabel("Dari"))
        self.dari = self._kotak_tanggal()
        bar.addWidget(self.dari)
        bar.addWidget(QLabel("sampai"))
        self.sampai = self._kotak_tanggal()
        bar.addWidget(self.sampai)
        self.tombol_cepat: dict[str, QPushButton] = {}
        for kunci, label in (
            ("hari_ini", "Hari ini"),
            ("7_hari", "7 hari"),
            ("bulan_ini", "Bulan ini"),
            ("bulan_lalu", "Bulan lalu"),
            ("tahun_ini", "Tahun ini"),
        ):
            btn = tombol(label)
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton:checked { background: #EFF6FF; color: #1D4ED8;"
                " border: 1px solid #93C5FD; }"
            )
            btn.clicked.connect(lambda _=False, k=kunci: self._pakai_rentang(k))
            self.tombol_cepat[kunci] = btn
            bar.addWidget(btn)
        bar.addStretch()
        self.ekspor_pdf = tombol("Unduh PDF")
        self.ekspor_pdf.clicked.connect(lambda: self._ekspor("pdf"))
        self.ekspor_excel = tombol("Unduh Excel")
        self.ekspor_excel.clicked.connect(lambda: self._ekspor("xlsx"))
        bar.addWidget(self.ekspor_pdf)
        bar.addWidget(self.ekspor_excel)
        susunan.addLayout(bar)
        self.label_rentang = keterangan("")
        susunan.addWidget(self.label_rentang)
        self.status_ekspor = keterangan("")
        self.status_ekspor.hide()
        susunan.addWidget(self.status_ekspor)

        kisi = QGridLayout()
        kisi.setSpacing(10)
        self.kartu: list[KartuRingkas] = []
        for i, (nama, _) in enumerate(angka_ringkasan_kosong(self.pribadi)):
            kartu = KartuRingkas(nama)
            self.kartu.append(kartu)
            kisi.addWidget(kartu, 0, i)
        susunan.addLayout(kisi)

        self.sorotan = QLabel("")
        self.sorotan.setWordWrap(True)
        self.sorotan.setTextFormat(Qt.TextFormat.RichText)
        self.sorotan.setStyleSheet(
            f"background: {PRIMARY_SOFT}; color: {TEXT}; border-radius: 6px;"
            " padding: 8px 12px;"
        )
        self.sorotan.hide()
        susunan.addWidget(self.sorotan)

        self.judul_tren = keterangan("")
        self.judul_tren.hide()
        susunan.addWidget(self.judul_tren)
        self.grafik = GrafikTren()
        self.grafik.hide()
        susunan.addWidget(self.grafik)

        self.tab = QTabWidget()
        self.tabel: dict[str, QTableWidget] = {}
        self.kolom: dict[str, list] = {}
        for kunci, label in self._daftar_tab():
            if kunci == "riwayat":
                kolom = [
                    k
                    for k in kolom_riwayat(pribadi=True)
                    if k[0] in KOLOM_RIWAYAT_LAYAR
                ]
            else:
                kolom = kolom_tabel(kunci, pribadi=self.pribadi, layar=True)
            tabel = TabelLaporan([JUDUL_LAYAR.get(k[0], k[0]) for k in kolom])
            kepala = tabel.horizontalHeader()
            kepala.sectionClicked.connect(
                lambda kol, t=tabel: self._urutkan(t, kol)
            )
            self.tabel[kunci] = tabel
            self.kolom[kunci] = kolom
            self.tab.addTab(tabel, label)
        susunan.addWidget(self.tab, stretch=1)
        self.tab.currentChanged.connect(lambda _=0: self._perbarui_total())

        self.total_periode = QLabel("")
        self.total_periode.setWordWrap(True)
        self.total_periode.setStyleSheet(f"color: {TEXT}; font-weight: 600;")
        self.total_periode.hide()
        susunan.addWidget(self.total_periode)

        self.kosong = QLabel(PESAN_KOSONG)
        self.kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.kosong.setWordWrap(True)
        self.kosong.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 16px; padding: 40px;")
        self.kosong.hide()
        susunan.addWidget(self.kosong, stretch=1)

        self.dari.dateChanged.connect(self._rentang_diubah)
        self.sampai.dateChanged.connect(self._rentang_diubah)

    def _daftar_tab(self) -> list[tuple[str, str]]:
        """Tab yang tampil: laporan pribadi tanpa Per petugas, dengan Riwayat saya."""
        tab = []
        for kunci, label in JUDUL_TABEL.items():
            if self.pribadi and kunci == "per_petugas":
                continue
            tab.append((kunci, label))
            if self.pribadi and kunci == "per_hari":
                tab.append(("riwayat", "Riwayat saya"))
        return tab

    def _urutkan(self, tabel: QTableWidget, kolom: int) -> None:
        """Klik judul kolom: urut naik, klik lagi: urut turun."""
        kepala = tabel.horizontalHeader()
        naik = not (
            kepala.isSortIndicatorShown()
            and kepala.sortIndicatorSection() == kolom
            and kepala.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
        )
        urutan = Qt.SortOrder.AscendingOrder if naik else Qt.SortOrder.DescendingOrder
        tabel.sortItems(kolom, urutan)
        kepala.setSortIndicator(kolom, urutan)
        kepala.setSortIndicatorShown(True)

    def _kotak_tanggal(self) -> QDateEdit:
        kotak = QDateEdit()
        kotak.setCalendarPopup(True)
        # Nama bulan berbahasa Indonesia, apa pun bahasa Windows-nya.
        kotak.setLocale(QLocale(QLocale.Language.Indonesian, QLocale.Country.Indonesia))
        kotak.setDisplayFormat("d MMM yyyy")
        kotak.setMaximumDate(_ke_qdate(clock.today()))
        return kotak

    # -----------------------------------------------------------------

    def _pakai_rentang(self, kunci: str) -> None:
        dari, sampai = rentang_cepat(kunci, clock.today())
        for k, btn in self.tombol_cepat.items():
            btn.setChecked(k == kunci)
        self._setel_tanggal(dari, sampai)

    def _setel_tanggal(self, dari: date, sampai: date) -> None:
        for kotak in (self.dari, self.sampai):
            kotak.blockSignals(True)
        self.dari.setDate(_ke_qdate(dari))
        self.sampai.setDate(_ke_qdate(sampai))
        for kotak in (self.dari, self.sampai):
            kotak.blockSignals(False)
        self.muat_ulang()

    def _rentang_diubah(self) -> None:
        for btn in self.tombol_cepat.values():
            btn.setChecked(False)
        self.muat_ulang()

    def muat_ulang(self) -> None:
        dari = _dari_qdate(self.dari.date())
        sampai = _dari_qdate(self.sampai.date())
        self.label_rentang.setText(self._teks_rentang(dari, sampai))
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.laporan = (
                self.layanan.laporan_petugas(dari, sampai)
                if self.pribadi
                else self.layanan.laporan(dari, sampai)
            )
        except Exception as exc:  # noqa: BLE001 - tampilkan ke supervisor
            self.laporan = None
            tampilkan_peringatan(self, pesan_untuk_user(exc), "Laporan")
        finally:
            QApplication.restoreOverrideCursor()
        self._tampilkan()

    @staticmethod
    def _teks_rentang(dari: date, sampai: date) -> str:
        if sampai < dari:
            return ""
        akhir_lalu = dari - timedelta(days=1)
        awal_lalu = akhir_lalu - timedelta(days=(sampai - dari).days)
        return (
            f"{label_rentang(dari, sampai)} · "
            f"dibandingkan dengan {label_rentang(awal_lalu, akhir_lalu)}"
        )

    def _perbarui_total(self) -> None:
        laporan = self.laporan
        indeks = self.tab.currentIndex()
        if laporan is None or indeks < 0 or laporan.total.terbit == 0:
            self.total_periode.hide()
            return
        kunci = list(self.tabel)[indeks]
        if kunci == "riwayat":
            teks = f"Total periode — {len(laporan.riwayat)} nomor"
        else:
            bagian = [
                f"{k[0]}: {k[1](laporan.total)}" for k in self.kolom[kunci][1:]
            ]
            teks = "Total periode — " + " · ".join(bagian)
        self.total_periode.setText(teks)
        self.total_periode.show()

    def _tampilkan(self) -> None:
        laporan = self.laporan
        ada = laporan is not None and laporan.total.terbit > 0
        self.ekspor_pdf.setEnabled(laporan is not None)
        self.ekspor_excel.setEnabled(laporan is not None)
        self.kosong.setVisible(not ada)
        self.tab.setVisible(ada)
        if laporan is not None and ada:
            for kartu, data in zip(self.kartu, kartu_ringkasan(laporan), strict=True):
                kartu.isi(data)
        else:
            for kartu, (nama, nilai) in zip(
                self.kartu, angka_ringkasan_kosong(self.pribadi), strict=True
            ):
                kartu.isi(KartuRingkasan(nama, nilai))

        temuan = sorotan(laporan) if laporan is not None and ada else []
        self.sorotan.setText(
            " &nbsp;·&nbsp; ".join(f"{nama}: <b>{nilai}</b>" for nama, nilai in temuan)
        )
        self.sorotan.setVisible(bool(temuan))

        tampil_grafik = False
        if laporan is not None and ada and laporan.jumlah_hari > 1:
            judul_tren, deret = deret_tren(laporan)
            self.judul_tren.setText(judul_tren)
            self.grafik.setel(deret)
            tampil_grafik = not self.grafik.kosong
        self.judul_tren.setVisible(tampil_grafik)
        self.grafik.setVisible(tampil_grafik)

        for kunci, tabel in self.tabel.items():
            if kunci == "riwayat":
                baris = laporan.riwayat if laporan else []
            else:
                baris = getattr(laporan, kunci) if laporan else []
            self._isi_tabel(tabel, self.kolom[kunci], baris)
        self._perbarui_total()

    @staticmethod
    def _isi_tabel(tabel: TabelLaporan, kolom: list, baris: list) -> None:
        kepala = tabel.horizontalHeader()
        kepala.setSortIndicatorShown(False)
        tabel.setRowCount(len(baris))
        for r, b in enumerate(baris):
            for c, k in enumerate(kolom):
                item = ItemUrut(k[1](b), k[2](b))
                if k[3]:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if k[0] == "Catatan identik":
                    persen = b.persen_catatan_identik
                    if persen is not None and persen >= AMBANG_CATATAN_IDENTIK:
                        item.setForeground(QColor(WARNING))
                if k[0] in ("Kepuasan", "Nilai survey"):
                    nilai = k[2](b)
                    if isinstance(nilai, (int, float)):
                        item.setForeground(QColor(_warna_kepuasan(nilai)))
                tabel.setItem(r, c, item)
        tabel.ukur_isi()

    def _ekspor(self, akhiran: str) -> None:
        if self.laporan is None:
            return
        folder_awal = Path.home() / "Documents"
        if not folder_awal.is_dir():
            folder_awal = Path.home()
        awal = str(folder_awal / nama_berkas_bawaan(self.laporan, akhiran))
        saring = "PDF (*.pdf)" if akhiran == "pdf" else "Excel (*.xlsx)"
        path, _ = QFileDialog.getSaveFileName(self, "Simpan laporan", awal, saring)
        if not path:
            return
        tujuan = Path(path)
        ekstensi = f".{akhiran}"
        if tujuan.suffix.lower() != ekstensi:
            tujuan = tujuan.with_suffix(ekstensi)
        sementara = tujuan.with_name(f".{tujuan.name}.sementara")
        self.ekspor_pdf.setEnabled(False)
        self.ekspor_excel.setEnabled(False)
        self.status_ekspor.setText(
            f"Menyusun {'PDF' if akhiran == 'pdf' else 'Excel'}…"
        )
        self.status_ekspor.show()
        laporan = self.laporan
        self._tujuan_ekspor = tujuan
        self._sementara_ekspor = sementara
        self._pekerja_ekspor = PekerjaLatar(
            lambda: (
                ekspor_pdf(laporan, sementara, self.kantor)
                if akhiran == "pdf"
                else ekspor_excel(laporan, sementara)
            ),
            self,
        )
        self._pekerja_ekspor.berhasil.connect(
            lambda _hasil: self._ekspor_selesai(akhiran)
        )
        self._pekerja_ekspor.gagal.connect(self._ekspor_gagal)
        self._pekerja_ekspor.finished.connect(self._bersihkan_pekerja_ekspor)
        self._pekerja_ekspor.start()

    def _bersihkan_pekerja_ekspor(self) -> None:
        pekerja = self._pekerja_ekspor
        self._pekerja_ekspor = None
        if pekerja is not None:
            pekerja.deleteLater()

    def _ekspor_selesai(self, akhiran: str) -> None:
        tujuan = self._tujuan_ekspor
        sementara = self._sementara_ekspor
        if tujuan is None or sementara is None:
            return
        try:
            sementara.replace(tujuan)
        except Exception as exc:  # noqa: BLE001
            self._ekspor_gagal(exc)
            return
        try:
            self.layanan.catat_unduhan(self.laporan, akhiran)
        except Exception:  # noqa: BLE001 - berkas sudah tersimpan; audit pelengkap
            logger.warning("Unduhan laporan gagal dicatat di audit", exc_info=True)
        jenis = "PDF" if akhiran == "pdf" else "Excel"
        self.status_ekspor.setText(f"{jenis} tersimpan: {tujuan.name}")
        self.status_ekspor.setToolTip(str(tujuan))
        self._akhir_ekspor()

    def _ekspor_gagal(self, exc: Exception) -> None:
        if self._sementara_ekspor is not None:
            self._sementara_ekspor.unlink(missing_ok=True)
        self.status_ekspor.setText("Laporan belum berhasil disimpan.")
        tampilkan_peringatan(
            self,
            f"Laporan gagal disimpan: {pesan_untuk_user(exc)}",
            "Laporan",
        )
        self._akhir_ekspor()

    def _akhir_ekspor(self) -> None:
        self.ekspor_pdf.setEnabled(self.laporan is not None)
        self.ekspor_excel.setEnabled(self.laporan is not None)
        self._tujuan_ekspor = None
        self._sementara_ekspor = None

    def closeEvent(self, kejadian) -> None:  # noqa: N802
        self.hentikan()
        kejadian.accept()

    def hentikan(self) -> None:
        """Hentikan ekspor sebelum halaman induk menghancurkan worker."""
        if self._pekerja_ekspor is not None and self._pekerja_ekspor.isRunning():
            self._pekerja_ekspor.wait(3_500)
        if self._pekerja_ekspor is not None and self._pekerja_ekspor.isRunning():
            lepaskan_pekerja(self._pekerja_ekspor)


def angka_ringkasan_kosong(pribadi: bool = False) -> list[tuple[str, str]]:
    return [
        ("Nomor ditangani" if pribadi else "Nomor terbit", "0"),
        ("Selesai dilayani", "0"),
        ("Tidak hadir", "0"),
        ("Nomor dipanggil" if pribadi else "Rata-rata menunggu", "0" if pribadi else "—"),
        ("Rata-rata pelayanan", "—"),
        ("Kepuasan", "—"),
    ]
