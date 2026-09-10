"""Layar penerbitan nomor antrian."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.services.master_data_service import MasterDataService
from app.services.queue_service import QueueInfo, QueueService
from app.services.ticket_service import TicketService
from app.ui.common import jalankan_aman, judul, keterangan, tombol
from app.ui.style import DANGER, FONT_SIZE_HUGE, PRIMARY, SUCCESS, TEXT_MUTED


class RegistrationPage(QWidget):
    """
    Penerbitan nomor antrian.

    Satu klik = satu nomor. Tombol dibuat besar dan diberi pintasan angka
    1–9 karena petugas menerbitkan nomor sambil berhadapan langsung dengan
    pengunjung, bukan sambil mengamati layar.
    """

    nomor_terbit = Signal(object)  # QueueInfo

    def __init__(
        self,
        queue: QueueService,
        master: MasterDataService,
        ticket: TicketService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.master = master
        self.ticket = ticket
        self.kategori: list = []
        self.terakhir: QueueInfo | None = None
        self.pendaftaran_dibuka = True

        self._bangun_tampilan()
        self.muat_ulang()

    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(32, 28, 32, 28)
        susunan.setSpacing(18)

        baris_judul = QHBoxLayout()
        baris_judul.addWidget(judul("Terbitkan Nomor Antrian"))
        baris_judul.addStretch()
        self.tombol_pendaftaran = tombol("Tutup Pendaftaran")
        self.tombol_pendaftaran.clicked.connect(self.alihkan_pendaftaran)
        baris_judul.addWidget(self.tombol_pendaftaran)
        susunan.addLayout(baris_judul)

        susunan.addWidget(
            keterangan(
                "Pilih jenis layanan yang dibutuhkan pengunjung. "
                "Tekan angka 1–9 sebagai pintasan."
            )
        )

        self.label_pendaftaran_tertutup = keterangan(
            "Pendaftaran antrian baru sedang ditutup. Nomor yang sudah "
            "terbit tetap dapat dilayani seperti biasa."
        )
        self.label_pendaftaran_tertutup.setStyleSheet(
            f"color: {DANGER}; font-weight: 600;"
        )
        self.label_pendaftaran_tertutup.setVisible(False)
        susunan.addWidget(self.label_pendaftaran_tertutup)

        self.kisi = QGridLayout()
        self.kisi.setSpacing(12)
        susunan.addLayout(self.kisi)

        susunan.addWidget(self._bangun_panel_hasil())
        susunan.addStretch()

    def _bangun_panel_hasil(self) -> QWidget:
        """Panel besar yang menampilkan nomor yang baru saja terbit."""
        self.panel_hasil = QFrame()
        # Selector harus memakai objectName. QLabel adalah turunan QFrame,
        # sehingga selector "QFrame" polos ikut memberi bingkai pada setiap
        # label di dalam panel ini.
        self.panel_hasil.setObjectName("panelHasil")
        self.panel_hasil.setStyleSheet(
            f"QFrame#panelHasil {{ background: white; border: 2px solid {SUCCESS};"
            " border-radius: 6px; }}"
        )
        self.panel_hasil.setVisible(False)

        susunan = QVBoxLayout(self.panel_hasil)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(6)

        label = QLabel("NOMOR ANTRIAN")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {TEXT_MUTED}; letter-spacing: 2px;")
        susunan.addWidget(label)

        self.label_nomor = QLabel("")
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_nomor.setStyleSheet(
            f"font-size: {FONT_SIZE_HUGE + 16}px; font-weight: 700; color: {PRIMARY};"
        )
        susunan.addWidget(self.label_nomor)

        self.label_layanan = QLabel("")
        self.label_layanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(self.label_layanan)

        self.label_posisi = QLabel("")
        self.label_posisi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_posisi.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_posisi)

        self.label_cetak = QLabel("")
        self.label_cetak.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_cetak.setWordWrap(True)
        self.label_cetak.setVisible(False)
        susunan.addWidget(self.label_cetak)

        self.tombol_cetak_ulang = tombol("Cetak Ulang Tiket")
        self.tombol_cetak_ulang.clicked.connect(self.cetak_ulang)
        self.tombol_cetak_ulang.setVisible(False)
        susunan.addWidget(self.tombol_cetak_ulang)

        return self.panel_hasil

    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Muat ulang daftar jenis layanan yang aktif dan status pendaftaran."""
        berhasil, terbuka = jalankan_aman(self, self.queue.pendaftaran_dibuka)
        self.pendaftaran_dibuka = terbuka if berhasil else True
        self.tombol_pendaftaran.setText(
            "Buka Pendaftaran" if not self.pendaftaran_dibuka else "Tutup Pendaftaran"
        )
        self.label_pendaftaran_tertutup.setVisible(not self.pendaftaran_dibuka)

        # only_leaf: yang ditawarkan kepada petugas hanyalah jenis layanan
        # yang benar-benar menerbitkan nomor. "Konsultasi" sudah menjadi
        # kelompok dan tidak punya nomor sendiri; menampilkannya di sini
        # hanya menyiapkan tombol yang pasti ditolak service.
        berhasil, data = jalankan_aman(
            self,
            lambda: self.master.list_categories(only_active=True, only_leaf=True),
        )
        if not berhasil:
            return

        self.kategori = data
        self._susun_tombol()

    def alihkan_pendaftaran(self) -> None:
        aksi = self.queue.buka_pendaftaran if not self.pendaftaran_dibuka else self.queue.tutup_pendaftaran
        berhasil, _ = jalankan_aman(self, aksi, "Gagal mengubah status pendaftaran")
        if berhasil:
            self.muat_ulang()

    def _susun_tombol(self) -> None:
        while self.kisi.count():
            item = self.kisi.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.kategori:
            self.kisi.addWidget(
                keterangan(
                    "Belum ada jenis layanan yang aktif. "
                    "Hubungi administrator untuk mengaktifkannya."
                ),
                0,
                0,
            )
            return

        for indeks, layanan in enumerate(self.kategori):
            btn = tombol(f"{layanan.name}\n{layanan.prefix}", variant="primary")
            btn.setMinimumHeight(96)
            btn.setStyleSheet("font-size: 17px; font-weight: 600;")
            btn.clicked.connect(
                lambda _=False, id_layanan=layanan.id: self.terbitkan(id_layanan)
            )
            btn.setEnabled(self.pendaftaran_dibuka)
            self.kisi.addWidget(btn, indeks // 3, indeks % 3)

            if indeks < 9:
                QShortcut(
                    QKeySequence(str(indeks + 1)),
                    self,
                    lambda id_layanan=layanan.id: self.terbitkan(id_layanan),
                )

    # -----------------------------------------------------------------

    def terbitkan(self, category_id: int) -> None:
        """Terbitkan satu nomor untuk jenis layanan yang dipilih."""
        berhasil, nomor = jalankan_aman(
            self, lambda: self.queue.create_queue(category_id), "Gagal menerbitkan nomor"
        )
        if not berhasil:
            return

        self.terakhir = nomor
        self._tampilkan_hasil(nomor)
        self._cetak(nomor)
        self.nomor_terbit.emit(nomor)

    def _tampilkan_hasil(self, nomor: QueueInfo) -> None:
        self.label_nomor.setText(nomor.queue_number)
        self.label_layanan.setText(nomor.category_name)

        berhasil, menunggu = jalankan_aman(self, self.queue.list_waiting)
        if berhasil:
            posisi = sum(1 for q in menunggu if q.created_at <= nomor.created_at)
            self.label_posisi.setText(
                f"Antrean ke-{posisi} dari {len(menunggu)} yang menunggu"
            )
        else:
            self.label_posisi.setText("")

        self.panel_hasil.setVisible(True)

    def _cetak(self, nomor: QueueInfo) -> None:
        """
        Cetak tiket.

        Kegagalan cetak TIDAK membatalkan antrian dan tidak memunculkan
        kotak dialog. Nomornya sudah sah dan sudah tampil besar di layar;
        petugas cukup menyebutkannya. Statusnya dilaporkan sebaris saja.
        """
        if self.ticket is None:
            self.label_cetak.setVisible(False)
            self.tombol_cetak_ulang.setVisible(False)
            return

        hasil = self.ticket.cetak(nomor)
        if hasil.berhasil:
            self.label_cetak.setText("Tiket tercetak.")
            self.label_cetak.setStyleSheet(f"color: {TEXT_MUTED};")
        else:
            self.label_cetak.setText(
                f"{hasil.pesan} Sebutkan nomor {nomor.queue_number} kepada pengunjung."
            )
            self.label_cetak.setStyleSheet(f"color: {DANGER}; font-weight: 600;")

        self.label_cetak.setVisible(True)
        self.tombol_cetak_ulang.setVisible(True)

    def cetak_ulang(self) -> None:
        """Cetak ulang tiket terakhir, misalnya karena kertas tersangkut."""
        if self.terakhir is not None:
            self._cetak(self.terakhir)
