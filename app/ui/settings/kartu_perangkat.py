"""
Kartu Perangkat di Layanan Anjungan: anjungan dan layar antrian Android.

Pembacaannya langsung dari database lokal (komputer ini server), sehingga
cukup cepat untuk dijalankan di utas tampilan setiap beberapa detik.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import clock
from app.services.device_service import JENIS_LAYAR_ANTRIAN, PerangkatInfo, PerangkatService
from app.ui.common import (
    keterangan,
    konfirmasi,
    pesan_untuk_user,
    tampilkan_peringatan,
    tombol,
)
from app.ui.style import DANGER, SUCCESS, TEXT_MUTED, WARNING
from app.utils.formatting import tanggal_pendek

SELANG_SEGARKAN_MS = 10_000
TINGGI_BARIS = 46
TINGGI_TOMBOL_BARIS = 32
KOLOM = ("Nama", "Jenis", "Terakhir terlihat", "Alamat", "Versi", "Printer", "")


def teks_terakhir_terlihat(perangkat: PerangkatInfo, sekarang: datetime) -> tuple[str, str]:
    """(teks, warna titik) untuk kolom Terakhir terlihat."""
    if perangkat.dicabut_pada is not None:
        return f"dicabut {tanggal_pendek(perangkat.dicabut_pada.date())}", TEXT_MUTED
    waktu = perangkat.terakhir_terlihat
    if waktu is None:
        return "belum pernah", TEXT_MUTED
    detik = max(0, int((sekarang - waktu).total_seconds()))
    warna = SUCCESS if perangkat.aktif(sekarang) else WARNING
    if detik < 15:
        return "baru saja", warna
    if detik < 60:
        return f"{detik} detik lalu", warna
    if detik < 3600:
        return f"{detik // 60} menit lalu", warna
    if waktu.date() == sekarang.date():
        return f"pukul {waktu:%H:%M}", warna
    return tanggal_pendek(waktu.date()), warna


def teks_printer(perangkat: PerangkatInfo) -> tuple[str, str]:
    """(teks, warna) untuk kolom Printer. Layar antrian tidak punya printer."""
    if perangkat.jenis == JENIS_LAYAR_ANTRIAN or perangkat.printer_ok is None:
        return "—", TEXT_MUTED
    jam = f"{perangkat.printer_waktu:%H:%M}" if perangkat.printer_waktu else ""
    if perangkat.printer_ok:
        return "Siap · cetak terakhir berhasil", SUCCESS
    return f"Cetak terakhir gagal ({jam})", DANGER


class DialogKodePasang(QDialog):
    """Kode 6 angka yang diketik di tablet atau TV."""

    def __init__(self, kode: str, kedaluwarsa: datetime, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tambah perangkat")
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 18)
        judul = QLabel("Tambah perangkat")
        judul.setStyleSheet("font-size: 16px; font-weight: 700;")
        susunan.addWidget(judul)
        susunan.addWidget(
            keterangan(
                "Di tablet atau TV: ⚙ Pengaturan → Cari server → masukkan kode ini."
            )
        )
        self.label_kode = QLabel(f"{kode[:3]} {kode[3:]}")
        self.label_kode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_kode.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label_kode.setStyleSheet(
            "font-size: 44px; font-weight: 800; letter-spacing: 8px; color: #1D4ED8;"
            " padding: 12px 0;"
        )
        susunan.addWidget(self.label_kode)
        berlaku = QLabel(f"Berlaku sampai pukul {kedaluwarsa:%H:%M} · sekali pakai")
        berlaku.setAlignment(Qt.AlignmentFlag.AlignCenter)
        berlaku.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(berlaku)
        baris = QHBoxLayout()
        baris.addStretch()
        tutup = tombol("Tutup")
        tutup.clicked.connect(self.accept)
        baris.addWidget(tutup)
        susunan.addLayout(baris)
        self.setMinimumWidth(420)


class KartuPerangkat(QFrame):
    """Daftar perangkat beserta tindakannya."""

    def __init__(self, layanan: PerangkatService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layanan = layanan
        self.perangkat: list[PerangkatInfo] = []
        self.setObjectName("kartuLayanan")
        self.setStyleSheet(
            "QFrame#kartuLayanan { background: #FFFFFF; border: 1px solid #E2E8F0;"
            " border-radius: 10px; }"
        )
        isi = QVBoxLayout(self)
        isi.setContentsMargins(18, 14, 18, 14)

        kepala = QHBoxLayout()
        label = QLabel("PERANGKAT")
        label.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: 600; letter-spacing: 1px;")
        kepala.addWidget(label)
        kepala.addStretch()
        self.tambah = tombol("+ Tambah perangkat", variant="primary")
        self.tambah.clicked.connect(self._tambah)
        kepala.addWidget(self.tambah)
        isi.addLayout(kepala)

        self.tabel = QTableWidget(0, len(KOLOM))
        self.tabel.setHorizontalHeaderLabels(KOLOM)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.tabel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabel.setShowGrid(False)
        kepala_tabel = self.tabel.horizontalHeader()
        kepala_tabel.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        kepala_tabel.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        kepala_tabel.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.tabel.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        isi.addWidget(self.tabel)

        self.kosong = keterangan(
            "Belum ada perangkat. Tekan + Tambah perangkat, lalu masukkan kodenya "
            "di tablet atau TV."
        )
        isi.addWidget(self.kosong)
        isi.addWidget(
            keterangan(
                "Hijau: menghubungi server dalam 1 menit terakhir · kuning: lebih "
                "dari 1 menit · abu-abu: dicabut, tidak dapat lagi menerbitkan nomor."
            )
        )
        self.token_bersama = QCheckBox(
            "Terima token bersama (tablet lama yang belum dipasangkan dengan kode)"
        )
        self.token_bersama.toggled.connect(self._ubah_token_bersama)
        isi.addWidget(self.token_bersama)

        self._pewaktu = QTimer(self)
        self._pewaktu.setInterval(SELANG_SEGARKAN_MS)
        self._pewaktu.timeout.connect(self.muat_ulang)
        self._pewaktu.start()
        self.muat_ulang()

    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        try:
            self.perangkat = self.layanan.daftar()
            bersama = self.layanan.token_bersama_aktif()
        except Exception as exc:  # noqa: BLE001 - kartu tidak boleh menjatuhkan halaman
            self.kosong.setText(f"Daftar perangkat tidak terbaca: {pesan_untuk_user(exc)}")
            self.kosong.show()
            return
        self.token_bersama.blockSignals(True)
        self.token_bersama.setChecked(bersama)
        self.token_bersama.blockSignals(False)
        self._isi_tabel(clock.now())

    def _isi_tabel(self, sekarang: datetime) -> None:
        # Tombol hanya dibangun ulang bila daftar perangkatnya berubah.
        # Penyegaran tiap 10 detik yang membangun ulang tombol membuat
        # tombol yang sedang ditunjuk mouse lenyap di bawah kursor.
        kunci = [(p.id, p.dicabut, p.nama) for p in self.perangkat]
        bangun_tombol = kunci != getattr(self, "_kunci_tombol", None)
        self._kunci_tombol = kunci
        if bangun_tombol:
            self.tabel.clearContents()
            self.tabel.setRowCount(0)
        self.tabel.setRowCount(len(self.perangkat))
        self.kosong.setVisible(not self.perangkat)
        for baris, p in enumerate(self.perangkat):
            redup = p.dicabut

            def sel(kolom: int, teks: str, warna: str | None = None, tebal: bool = False,
                    titik: str | None = None, tip: str = "",
                    baris: int = baris, redup: bool = redup) -> None:
                item = QTableWidgetItem(f"● {teks}" if titik else teks)
                if redup:
                    item.setForeground(Qt.GlobalColor.gray)
                elif titik or warna:
                    from PySide6.QtGui import QColor

                    item.setForeground(QColor(titik or warna))
                if tebal and not redup:
                    huruf = item.font()
                    huruf.setBold(True)
                    item.setFont(huruf)
                if tip:
                    item.setToolTip(tip)
                self.tabel.setItem(baris, kolom, item)

            sel(0, p.nama, tebal=True,
                tip="" if p.dipasangkan else "Belum dipasangkan: memakai token bersama")
            sel(1, p.label_jenis)
            teks, warna = teks_terakhir_terlihat(p, sekarang)
            sel(2, teks, titik=warna)
            sel(3, p.alamat_ip or "—")
            sel(4, p.versi_nama or "—")
            teks, warna = teks_printer(p)
            sel(5, teks, titik=None if teks == "—" else warna, tip=p.printer_pesan)
            if bangun_tombol:
                self.tabel.setCellWidget(baris, 6, self._tombol_baris(p))

        # Tombol aplikasi bertinggi minimum sendiri; baris dan kolom aksi
        # mengikuti ukuran tombol, bukan sebaliknya, supaya tidak terpotong.
        tinggi = TINGGI_BARIS
        lebar_aksi = 0
        for baris in range(self.tabel.rowCount()):
            wadah = self.tabel.cellWidget(baris, 6)
            if wadah is not None:
                lebar_aksi = max(lebar_aksi, wadah.sizeHint().width())
        for baris in range(self.tabel.rowCount()):
            self.tabel.setRowHeight(baris, tinggi)
        if lebar_aksi:
            self.tabel.setColumnWidth(6, lebar_aksi + 8)
        # Halaman sudah digulir; tabel tidak perlu gulungan sendiri.
        self.tabel.setFixedHeight(
            self.tabel.horizontalHeader().height()
            + tinggi * max(1, self.tabel.rowCount())
            + 2 * self.tabel.frameWidth()
            + 2
        )

    def _tombol_baris(self, p: PerangkatInfo) -> QWidget:
        wadah = QWidget()
        baris = QHBoxLayout(wadah)
        baris.setContentsMargins(4, 0, 4, 0)
        baris.setSpacing(6)
        baris.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        if p.dicabut:
            hapus = tombol("Hapus")
            hapus.clicked.connect(lambda _=False, pid=p.id: self._hapus(pid))
            baris.addWidget(hapus)
        else:
            ganti = tombol("Ganti nama")
            ganti.clicked.connect(lambda _=False, info=p: self._ganti_nama(info))
            cabut = tombol("Cabut", variant="danger")
            cabut.clicked.connect(lambda _=False, info=p: self._cabut(info))
            baris.addWidget(ganti)
            baris.addWidget(cabut)
        baris.addStretch()
        for btn in wadah.findChildren(QPushButton):
            btn.setFixedHeight(TINGGI_TOMBOL_BARIS)
            btn.setStyleSheet("padding: 0 12px;")
        return wadah

    # -----------------------------------------------------------------

    def _jalankan(self, kerja) -> bool:
        try:
            kerja()
        except Exception as exc:  # noqa: BLE001 - ditampilkan ke admin
            tampilkan_peringatan(self, pesan_untuk_user(exc), "Perangkat")
            return False
        self.muat_ulang()
        return True

    def _tambah(self) -> None:
        try:
            kode = self.layanan.buat_kode()
        except Exception as exc:  # noqa: BLE001
            tampilkan_peringatan(self, pesan_untuk_user(exc), "Perangkat")
            return
        DialogKodePasang(kode.kode, kode.kedaluwarsa, self).exec()
        self.muat_ulang()

    def _ganti_nama(self, p: PerangkatInfo) -> None:
        nama, ok = QInputDialog.getText(self, "Ganti nama", "Nama perangkat:", text=p.nama)
        if ok:
            self._jalankan(lambda: self.layanan.ganti_nama(p.id, nama))

    def _cabut(self, p: PerangkatInfo) -> None:
        if konfirmasi(
            self,
            f"Cabut {p.nama}?\n\nPerangkat ini tidak dapat lagi menerbitkan nomor "
            "sampai dipasangkan ulang dengan kode baru. Perangkat lain tidak "
            "terganggu.",
        ):
            self._jalankan(lambda: self.layanan.cabut(p.id))

    def _hapus(self, perangkat_id: int) -> None:
        self._jalankan(lambda: self.layanan.hapus(perangkat_id))

    def _ubah_token_bersama(self, aktif: bool) -> None:
        if not aktif and not konfirmasi(
            self,
            "Matikan token bersama?\n\nTablet yang belum dipasangkan dengan kode "
            "berhenti tersambung sampai dipasangkan.",
        ):
            self.token_bersama.blockSignals(True)
            self.token_bersama.setChecked(True)
            self.token_bersama.blockSignals(False)
            return
        self._jalankan(lambda: self.layanan.setel_token_bersama(aktif))
