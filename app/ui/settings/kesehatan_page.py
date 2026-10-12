"""
Layar Kesehatan Sistem untuk administrator.

Pemeriksaan baru berjalan saat layar pertama kali dibuka, bukan saat login:
seluruh halaman menu dibangun ketika ADMIN masuk, sedangkan pemeriksaan ini
mengetuk API dan menjalankan PowerShell. Semuanya di utas latar supaya
jendela tidak membeku ketika server tidak terjangkau.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.kesehatan_service import (
    INFO,
    KesehatanService,
    LaporanKesehatan,
)
from app.services.status_anjungan import MASALAH, NORMAL, PERINGATAN
from app.ui.common import (
    PekerjaLatar,
    judul,
    keterangan,
    lepaskan_pekerja,
    pesan_untuk_user,
    tombol,
)
from app.ui.style import DANGER, SUCCESS, TEXT_MUTED, WARNING

_LABEL = {
    NORMAL: ("● Normal", SUCCESS),
    PERINGATAN: ("● Perhatian", WARNING),
    MASALAH: ("● Masalah", DANGER),
    INFO: ("○ Info", TEXT_MUTED),
}

_RINGKASAN = {
    NORMAL: "Semua pemeriksaan normal.",
    PERINGATAN: "Ada hal yang perlu diperhatikan.",
    MASALAH: "Ada masalah yang perlu segera ditangani.",
}


class KesehatanPage(QWidget):
    """Status database, migrasi, API, perangkat, backup, disk, dan galat."""

    def __init__(self, kesehatan: KesehatanService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kesehatan = kesehatan
        self._pekerja: PekerjaLatar | None = None
        self._sudah_diperiksa = False
        self.laporan: LaporanKesehatan | None = None
        self._bangun_tampilan()

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(14)

        susunan.addWidget(judul("Kesehatan Sistem"))
        susunan.addWidget(
            keterangan(
                "Periksa sebelum pelayanan dimulai. Kata sandi dan token tidak "
                "pernah ditampilkan di sini."
            )
        )

        baris = QHBoxLayout()
        self.tombol_periksa = tombol("Periksa Ulang", variant="primary")
        self.tombol_periksa.clicked.connect(self.muat_ulang)
        baris.addWidget(self.tombol_periksa)
        self.label_status = keterangan("Belum diperiksa.")
        baris.addWidget(self.label_status, stretch=1)
        susunan.addLayout(baris)

        self.tabel = QTableWidget(0, 3)
        self.tabel.setHorizontalHeaderLabels(["Status", "Pemeriksaan", "Keterangan"])
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.setWordWrap(True)
        kepala = self.tabel.horizontalHeader()
        kepala.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        kepala.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        kepala.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        susunan.addWidget(self.tabel, stretch=1)

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().showEvent(event)
        if not self._sudah_diperiksa:
            self.muat_ulang()

    def muat_ulang(self) -> None:
        if self._pekerja is not None:
            return
        self._sudah_diperiksa = True
        self.tombol_periksa.setEnabled(False)
        self.label_status.setText("Memeriksa…")
        pekerja = PekerjaLatar(self.kesehatan.periksa, self)
        pekerja.berhasil.connect(self._tampilkan)
        pekerja.gagal.connect(self._saat_gagal)
        pekerja.finished.connect(self._bersihkan_pekerja)
        self._pekerja = pekerja
        pekerja.start()

    def _bersihkan_pekerja(self) -> None:
        pekerja = self._pekerja
        self._pekerja = None
        self.tombol_periksa.setEnabled(True)
        if pekerja is not None:
            pekerja.deleteLater()

    def hentikan(self) -> None:
        if self._pekerja is not None and self._pekerja.isRunning():
            self._pekerja.wait(3_500)
        if self._pekerja is not None and self._pekerja.isRunning():
            lepaskan_pekerja(self._pekerja)

    def _saat_gagal(self, exc: Exception) -> None:
        # Label sebaris, bukan kotak dialog: pesan tetap terbaca tanpa
        # menahan jendela, dan detail teknisnya sudah dicatat PekerjaLatar.
        self.label_status.setText(pesan_untuk_user(exc))
        self.label_status.setStyleSheet(f"color: {DANGER};")

    def _tampilkan(self, laporan: LaporanKesehatan) -> None:
        self.laporan = laporan
        teks, warna = _RINGKASAN.get(laporan.tingkat, ""), _LABEL[laporan.tingkat][1]
        self.label_status.setText(
            f"{teks} Diperiksa {laporan.diperiksa_pada:%H:%M:%S}."
        )
        self.label_status.setStyleSheet(f"color: {warna}; font-weight: 600;")

        self.tabel.setRowCount(len(laporan.butir))
        for i, p in enumerate(laporan.butir):
            label, warna = _LABEL.get(p.tingkat, _LABEL[INFO])
            sel_status = QTableWidgetItem(label)
            sel_status.setForeground(QColor(warna))
            sel_status.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.tabel.setItem(i, 0, sel_status)

            sel_nama = QTableWidgetItem(p.nama)
            sel_nama.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.tabel.setItem(i, 1, sel_nama)

            baris = [p.ringkasan]
            baris += [f"  {r}" for r in p.rincian]
            baris += [f"→ {s}" for s in p.saran]
            self.tabel.setItem(i, 2, QTableWidgetItem("\n".join(baris)))
        self.tabel.resizeRowsToContents()
