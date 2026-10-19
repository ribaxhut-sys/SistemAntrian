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
    KOLOM_TABEL,
    Laporan,
    ReportService,
    angka_ringkasan,
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
from app.ui.style import DANGER, SUCCESS, TEXT, WARNING

logger = get_logger("laporan")

WARNA_ANGKA = (TEXT, SUCCESS, DANGER, TEXT, TEXT, WARNING)


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
    awal_bulan = hari_ini.replace(day=1)
    if nama == "bulan_ini":
        return awal_bulan, hari_ini
    akhir_lalu = awal_bulan - timedelta(days=1)
    return akhir_lalu.replace(day=1), akhir_lalu


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
        self.status_ekspor = keterangan("")
        self.status_ekspor.hide()
        susunan.addWidget(self.status_ekspor)

        kisi = QGridLayout()
        kisi.setSpacing(10)
        self.kartu: list[KartuAngka] = []
        for i, (nama, _) in enumerate(angka_ringkasan_kosong()):
            kartu = KartuAngka(nama, WARNA_ANGKA[i])
            self.kartu.append(kartu)
            kisi.addWidget(kartu, 0, i)
        susunan.addLayout(kisi)

        self.tab = QTabWidget()
        self.tabel: dict[str, QTableWidget] = {}
        for kunci, label in JUDUL_TABEL.items():
            if self.pribadi and kunci == "per_petugas":
                continue
            kolom = KOLOM_TABEL[kunci]
            tabel = QTableWidget(0, len(kolom))
            tabel.setHorizontalHeaderLabels([k[0] for k in kolom])
            tabel.verticalHeader().setVisible(False)
            tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            tabel.setAlternatingRowColors(True)
            kepala = tabel.horizontalHeader()
            kepala.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            kepala.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.tabel[kunci] = tabel
            self.tab.addTab(tabel, label)
        susunan.addWidget(self.tab, stretch=1)

        self.kosong = keterangan("Belum ada antrian pada rentang ini.")
        self.kosong.hide()
        susunan.addWidget(self.kosong)

        self.dari.dateChanged.connect(self._rentang_diubah)
        self.sampai.dateChanged.connect(self._rentang_diubah)

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

    def _tampilkan(self) -> None:
        laporan = self.laporan
        ada = laporan is not None and laporan.total.terbit > 0
        self.ekspor_pdf.setEnabled(laporan is not None)
        self.ekspor_excel.setEnabled(laporan is not None)
        self.kosong.setVisible(not ada)
        angka = angka_ringkasan(laporan) if laporan else angka_ringkasan_kosong()
        for kartu, (nama, nilai) in zip(self.kartu, angka, strict=True):
            kartu.setel(nilai)
            label = kartu.findChildren(QLabel)[-1]
            label.setText(nama)
        for kunci, tabel in self.tabel.items():
            baris = getattr(laporan, kunci) if laporan else []
            kolom = KOLOM_TABEL[kunci]
            tabel.setRowCount(len(baris))
            for r, b in enumerate(baris):
                for c, k in enumerate(kolom):
                    item = QTableWidgetItem(k[1](b))
                    if k[3]:
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        )
                    if k[0] == "Kepuasan" and b.rata_kepuasan is not None:
                        item.setForeground(QColor(WARNING))
                    tabel.setItem(r, c, item)

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
        if self._pekerja_ekspor is not None and self._pekerja_ekspor.isRunning():
            self._pekerja_ekspor.wait(3_500)
        if self._pekerja_ekspor is not None and self._pekerja_ekspor.isRunning():
            lepaskan_pekerja(self._pekerja_ekspor)
        kejadian.accept()


def angka_ringkasan_kosong() -> list[tuple[str, str]]:
    return [
        ("Nomor terbit", "0"),
        ("Selesai dilayani", "0"),
        ("Tidak hadir", "0"),
        ("Rata-rata menunggu", "—"),
        ("Rata-rata pelayanan", "—"),
        ("Kepuasan (0 survey)", "—"),
    ]

