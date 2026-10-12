"""
Layar backup dan jejak aktivitas untuk administrator.

Pemulihan adalah satu-satunya tindakan di seluruh aplikasi yang dapat
menghapus data yang sudah tersimpan. Karena itu konfirmasinya bertingkat
dan menyebut secara terbuka apa yang akan hilang.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.services import audit_service
from app.services.backup_service import BackupInfo, BackupService
from app.ui.common import (
    jalankan_aman,
    judul,
    keterangan,
    konfirmasi,
    tampilkan_info,
    tampilkan_peringatan,
    tombol,
)
from app.ui.style import DANGER, TEXT_MUTED
from app.utils.formatting import hari_dan_tanggal, jam

#: Banyaknya baris audit yang ditampilkan. Cukup untuk menelusuri kejadian
#: beberapa hari terakhir tanpa membuat tabel berat dibuka.
BATAS_AUDIT = 200


class BackupPage(QWidget):
    """Pengelolaan backup database dan pembacaan audit log."""

    def __init__(self, backup: BackupService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.backup = backup
        self.daftar_backup: list[BackupInfo] = []

        self._bangun_tampilan()
        self.muat_ulang()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(14)

        susunan.addWidget(judul("Backup & Jejak Aktivitas"))

        tab = QTabWidget()
        tab.addTab(self._bangun_tab_backup(), "Backup")
        tab.addTab(self._bangun_tab_audit(), "Jejak Aktivitas")
        susunan.addWidget(tab, stretch=1)

    def _bangun_tab_backup(self) -> QWidget:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(16, 16, 16, 16)
        susunan.setSpacing(12)

        self.label_folder = keterangan("")
        susunan.addWidget(self.label_folder)

        # Waktu backup terakhir yang berhasil, dan kegagalan sesudahnya.
        # Tanpa ini backup otomatis yang gagal tiap pagi baru ketahuan
        # ketika backup itu dibutuhkan.
        self.label_status = keterangan("")
        self.label_status.setWordWrap(True)
        susunan.addWidget(self.label_status)

        # Backup berisi identitas pelapor pengaduan. Tanpa enkripsi,
        # flashdisk salinan kedua yang hilang berarti data itu ikut hilang
        # ke tangan siapa pun yang menemukannya.
        baris_kunci = QHBoxLayout()
        baris_kunci.setSpacing(8)
        self.label_enkripsi = keterangan("")
        self.label_enkripsi.setWordWrap(True)
        baris_kunci.addWidget(self.label_enkripsi, stretch=1)
        self.tombol_aktifkan_enkripsi = tombol("Aktifkan Enkripsi")
        self.tombol_aktifkan_enkripsi.clicked.connect(self.aktifkan_enkripsi)
        baris_kunci.addWidget(self.tombol_aktifkan_enkripsi)
        self.tombol_masukkan_kunci = tombol("Masukkan Kunci")
        self.tombol_masukkan_kunci.setToolTip(
            "Untuk komputer pengganti: ketik kunci yang dicatat saat enkripsi "
            "diaktifkan, supaya backup lama dapat dibuka."
        )
        self.tombol_masukkan_kunci.clicked.connect(self.masukkan_kunci)
        baris_kunci.addWidget(self.tombol_masukkan_kunci)
        susunan.addLayout(baris_kunci)

        baris = QHBoxLayout()
        baris.setSpacing(8)

        buat = tombol("Backup Sekarang", variant="primary")
        buat.clicked.connect(self.buat_backup)
        baris.addWidget(buat)

        self.tombol_uji = tombol("Uji Backup")
        self.tombol_uji.setToolTip(
            "Periksa checksum dan coba pulihkan ke database sementara. "
            "Database yang sedang dipakai tidak disentuh."
        )
        self.tombol_uji.setEnabled(False)
        self.tombol_uji.clicked.connect(self.uji)
        baris.addWidget(self.tombol_uji)

        self.tombol_pulihkan = tombol("Pulihkan", variant="danger")
        self.tombol_pulihkan.setEnabled(False)
        self.tombol_pulihkan.clicked.connect(self.pulihkan)
        baris.addWidget(self.tombol_pulihkan)

        bersihkan = tombol("Hapus yang Kedaluwarsa")
        bersihkan.clicked.connect(self.bersihkan)
        baris.addWidget(bersihkan)

        baris.addStretch()
        susunan.addLayout(baris)

        self.tabel_backup = QTableWidget(0, 5)
        self.tabel_backup.setHorizontalHeaderLabels(
            ["Berkas", "Dibuat", "Ukuran", "Checksum", "Enkripsi"]
        )
        self.tabel_backup.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tabel_backup.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tabel_backup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel_backup.verticalHeader().setVisible(False)
        self.tabel_backup.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tabel_backup.itemSelectionChanged.connect(self._saat_pilihan_berubah)
        susunan.addWidget(self.tabel_backup, stretch=1)

        return panel

    def _bangun_tab_audit(self) -> QWidget:
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(16, 16, 16, 16)
        susunan.setSpacing(12)

        susunan.addWidget(
            keterangan(
                f"{BATAS_AUDIT} aktivitas terakhir. Kata sandi tidak pernah "
                "dicatat di sini."
            )
        )

        self.tabel_audit = QTableWidget(0, 5)
        self.tabel_audit.setHorizontalHeaderLabels(
            ["Waktu", "Pelaku", "Tindakan", "Objek", "Keterangan"]
        )
        self.tabel_audit.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tabel_audit.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel_audit.verticalHeader().setVisible(False)
        self.tabel_audit.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        susunan.addWidget(self.tabel_audit, stretch=1)

        return panel

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        self.label_folder.setText(f"Folder backup: {self.backup.folder}")
        self._muat_status()
        self._muat_enkripsi()
        self._muat_backup()
        self._muat_audit()

    def _muat_enkripsi(self) -> None:
        aktif = self.backup.enkripsi_aktif
        if aktif:
            self.label_enkripsi.setText(
                "Enkripsi backup AKTIF. Backup baru hanya dapat dibuka dengan "
                "kunci yang sudah Anda catat."
            )
            self.label_enkripsi.setStyleSheet(f"color: {TEXT_MUTED};")
        else:
            self.label_enkripsi.setText(
                "Backup TIDAK dienkripsi, padahal berisi identitas pelapor "
                "pengaduan. Siapa pun yang menyalin folder backup dapat membacanya."
            )
            self.label_enkripsi.setStyleSheet(f"color: {DANGER};")
        self.tombol_aktifkan_enkripsi.setVisible(not aktif)

    def _muat_status(self) -> None:
        berhasil, status = jalankan_aman(
            self, self.backup.status_backup, "Gagal membaca status backup"
        )
        if not berhasil or status is None:
            return
        if status.terakhir_berhasil is None:
            teks = "Belum ada backup yang berhasil dibuat."
        else:
            w = status.terakhir_berhasil
            teks = f"Backup terakhir berhasil: {hari_dan_tanggal(w.date())}, {jam(w)}."
        warna = TEXT_MUTED
        if status.gagal_terakhir and status.terakhir_gagal is not None:
            g = status.terakhir_gagal
            teks += (
                f"\nBackup terakhir GAGAL ({hari_dan_tanggal(g.date())}, {jam(g)}): "
                f"{status.pesan_gagal}"
            )
            warna = DANGER
        self.label_status.setText(teks)
        self.label_status.setStyleSheet(f"color: {warna};")

    def _muat_backup(self) -> None:
        berhasil, data = jalankan_aman(
            self, self.backup.list_backup, "Gagal membaca daftar backup"
        )
        if not berhasil:
            return

        self.daftar_backup = data or []
        self.tabel_backup.setRowCount(len(self.daftar_backup))
        for baris, info in enumerate(self.daftar_backup):
            nilai = (
                info.nama,
                f"{hari_dan_tanggal(info.dibuat_pada.date())}, {jam(info.dibuat_pada)}",
                info.label_ukuran,
                "ada" if info.checksum_ada else "-",
                "terenkripsi" if info.terenkripsi else "tidak",
            )
            for kolom, teks in enumerate(nilai):
                self.tabel_backup.setItem(baris, kolom, QTableWidgetItem(teks))

        self._saat_pilihan_berubah()

    def _muat_audit(self) -> None:
        berhasil, data = jalankan_aman(
            self,
            lambda: audit_service.list_terakhir(batas=BATAS_AUDIT),
            "Gagal membaca jejak aktivitas",
        )
        if not berhasil:
            return

        baris_audit = data or []
        self.tabel_audit.setRowCount(len(baris_audit))
        for baris, entri in enumerate(baris_audit):
            objek = "-"
            if entri.entity_type:
                objek = entri.entity_type
                if entri.entity_id is not None:
                    objek = f"{objek} #{entri.entity_id}"

            nilai = (
                f"{entri.created_at:%d/%m %H:%M}",
                entri.pelaku,
                entri.action,
                objek,
                _ringkas_meta(entri.meta),
            )
            for kolom, teks in enumerate(nilai):
                self.tabel_audit.setItem(baris, kolom, QTableWidgetItem(teks))

    @property
    def terpilih(self) -> BackupInfo | None:
        baris = self.tabel_backup.currentRow()
        if baris < 0 or baris >= len(self.daftar_backup):
            return None
        return self.daftar_backup[baris]

    def _saat_pilihan_berubah(self) -> None:
        self.tombol_pulihkan.setEnabled(self.terpilih is not None)
        self.tombol_uji.setEnabled(self.terpilih is not None)

    # -----------------------------------------------------------------
    # Tindakan
    # -----------------------------------------------------------------

    def buat_backup(self) -> None:
        berhasil, info = jalankan_aman(
            self, self.backup.backup, "Gagal membuat backup"
        )
        if not berhasil or info is None:
            return
        tampilkan_info(self, f"Backup dibuat: {info.nama} ({info.label_ukuran})")
        self.muat_ulang()

    def uji(self) -> None:
        info = self.terpilih
        if info is None:
            return
        berhasil, hasil = jalankan_aman(
            self, lambda: self.backup.uji_backup(info.berkas), "Gagal menguji backup"
        )
        if not berhasil or hasil is None:
            return
        pesan = "\n".join([hasil.ringkasan, "", *hasil.rincian]).strip()
        if hasil.berhasil:
            tampilkan_info(self, pesan, "Uji Backup")
        else:
            tampilkan_peringatan(self, pesan, "Uji Backup")

    def bersihkan(self) -> None:
        berhasil, dihapus = jalankan_aman(
            self, self.backup.hapus_kedaluwarsa, "Gagal menghapus backup lama"
        )
        if not berhasil:
            return
        jumlah = len(dihapus or [])
        tampilkan_info(
            self,
            "Tidak ada backup yang kedaluwarsa."
            if jumlah == 0
            else f"{jumlah} backup kedaluwarsa dihapus.",
        )
        self.muat_ulang()

    def pulihkan(self) -> None:
        """
        Ganti database aktif dengan sebuah backup.

        Dikonfirmasi dua kali dengan sengaja. Yang pertama menjelaskan
        akibatnya, yang kedua memaksa berhenti sejenak sebelum data
        sungguh-sungguh ditimpa.
        """
        info = self.terpilih
        if info is None:
            return

        if not konfirmasi(
            self,
            f"Pulihkan database dari {info.nama}?\n\n"
            "SELURUH antrian dan survey yang tercatat setelah "
            f"{hari_dan_tanggal(info.dibuat_pada.date())} akan hilang.",
            "Pulihkan Database",
        ):
            return
        if not konfirmasi(
            self,
            "Tindakan ini tidak dapat dibatalkan. Lanjutkan?\n\n"
            "Database yang sekarang akan disalin lebih dahulu sebagai "
            "cadangan pengaman.",
            "Konfirmasi Terakhir",
        ):
            return

        berhasil, _ = jalankan_aman(
            self, lambda: self.backup.restore(info.berkas), "Gagal memulihkan database"
        )
        if not berhasil:
            return

        tampilkan_info(
            self,
            "Database berhasil dipulihkan.\n\n"
            "Tutup dan buka kembali aplikasi agar seluruh layar membaca "
            "data yang baru.",
        )
        self.muat_ulang()

    def aktifkan_enkripsi(self) -> None:
        """
        Buat kunci enkripsi dan tampilkan SEKALI untuk dicatat.

        Dialog modal di sini disengaja: layar ini dibuka administrator yang
        sedang duduk di depannya, dan kunci yang terlewat dibaca berarti
        backup yang tidak dapat dibuka bila disk server rusak.
        """
        if not konfirmasi(
            self,
            "Aktifkan enkripsi backup?\n\n"
            "Kunci akan ditampilkan satu kali. CATAT kunci itu di kertas dan "
            "simpan di tempat aman yang terpisah dari komputer ini. Tanpa "
            "kunci itu, backup tidak dapat dipulihkan di komputer lain.",
            "Enkripsi Backup",
        ):
            return
        berhasil, frasa = jalankan_aman(
            self, self.backup.buat_kunci_enkripsi, "Gagal mengaktifkan enkripsi"
        )
        if not berhasil or not frasa:
            return
        kotak = QMessageBox(self)
        kotak.setIcon(QMessageBox.Icon.Warning)
        kotak.setWindowTitle("Catat Kunci Enkripsi")
        kotak.setText(
            "Kunci enkripsi backup:\n\n"
            f"{frasa}\n\n"
            "Catat sekarang. Kunci juga tersimpan di komputer ini, tetapi "
            "bila disk komputer ini rusak, hanya catatan Anda yang tersisa."
        )
        kotak.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        kotak.setStandardButtons(QMessageBox.StandardButton.Ok)
        kotak.button(QMessageBox.StandardButton.Ok).setText("Sudah Saya Catat")
        kotak.exec()
        self.muat_ulang()

    def masukkan_kunci(self) -> None:
        frasa, ok = QInputDialog.getText(
            self,
            "Masukkan Kunci Enkripsi",
            "Ketik kunci enkripsi backup yang tercatat:",
            QLineEdit.EchoMode.Normal,
        )
        if not ok or not frasa.strip():
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.backup.pasang_kunci_enkripsi(frasa),
            "Kunci tidak dapat dipasang",
        )
        if not berhasil:
            return
        tampilkan_info(self, "Kunci enkripsi tersimpan di komputer ini.")
        self.muat_ulang()


def _ringkas_meta(meta: str | None) -> str:
    """
    Ubah meta JSON menjadi satu baris yang terbaca.

    Meta yang tidak dapat dibaca ditampilkan apa adanya, bukan menggagalkan
    seluruh tabel — audit log justru paling dibutuhkan ketika ada yang tidak
    beres.
    """
    if not meta:
        return ""
    try:
        isi = json.loads(meta)
    except ValueError:
        return meta
    if not isinstance(isi, dict):
        return str(isi)
    return "  ".join(f"{k}={v}" for k, v in isi.items())
