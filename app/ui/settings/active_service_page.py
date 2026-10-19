"""Pengalihan dan pembatalan paksa pelayanan aktif oleh administrator."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.logger import get_logger
from app.services.queue_service import QueueInfo, QueueService, TransferTargetInfo
from app.services.permissions import Permission
from app.ui.common import (
    PekerjaLatar,
    jalankan_aman,
    judul,
    konfirmasi,
    lepaskan_pekerja,
    tampilkan_info,
    tombol,
)
from app.ui.style import TEXT_MUTED


SELANG_SEGAR_MS = 5_000
logger = get_logger("ui.active_service")


class ActiveServicePage(QWidget):
    """Daftar pelayanan yang boleh diambil alih hanya oleh admin."""

    def __init__(self, queue: QueueService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.queue = queue
        self.data: list[QueueInfo] = []
        self.targets: list[TransferTargetInfo] = []
        self._pekerja: PekerjaLatar | None = None
        self._muat_ditunda = False

        self._bangun_tampilan()
        self.pewaktu = QTimer(self)
        self.pewaktu.setInterval(SELANG_SEGAR_MS)
        self.pewaktu.timeout.connect(self.muat_ulang)
        self.muat_ulang()

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(12)
        susunan.addWidget(judul("Pelayanan Aktif"))

        self.label_kosong = QLabel("")
        self.label_kosong.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_kosong)

        self.tabel = QTableWidget(0, 5)
        self.tabel.setHorizontalHeaderLabels(
            ["Nomor", "Status", "Layanan", "Loket", "Petugas"]
        )
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setShowGrid(False)
        self.tabel.verticalHeader().setVisible(False)
        kepala = self.tabel.horizontalHeader()
        for kolom in range(5):
            kepala.setSectionResizeMode(
                kolom,
                QHeaderView.ResizeMode.Stretch
                if kolom in (2, 4)
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        self.tabel.itemSelectionChanged.connect(self._perbarui_tombol)
        susunan.addWidget(self.tabel, stretch=1)

        formulir = QFormLayout()
        formulir.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.pilih_petugas = QComboBox()
        self.pilih_petugas.currentIndexChanged.connect(self._perbarui_tombol)
        formulir.addRow("Petugas dan loket tujuan", self.pilih_petugas)
        self.input_alasan = QLineEdit()
        self.input_alasan.setMaxLength(300)
        self.input_alasan.textChanged.connect(self._perbarui_tombol)
        formulir.addRow("Alasan", self.input_alasan)
        susunan.addLayout(formulir)

        aksi = QHBoxLayout()
        aksi.addStretch()
        self.tombol_selesai = tombol("Selesaikan Paksa", variant="success")
        self.tombol_selesai.clicked.connect(self.selesaikan_paksa)
        aksi.addWidget(self.tombol_selesai)
        self.tombol_batal = tombol("Batalkan Paksa", variant="danger")
        self.tombol_batal.clicked.connect(self.batalkan_paksa)
        aksi.addWidget(self.tombol_batal)
        self.tombol_alihkan = tombol("Alihkan Pelayanan", variant="primary")
        self.tombol_alihkan.clicked.connect(self.alihkan)
        aksi.addWidget(self.tombol_alihkan)
        self.tombol_ambil_alih = tombol("Ambil Alih", variant="primary")
        self.tombol_ambil_alih.clicked.connect(self.ambil_alih)
        aksi.addWidget(self.tombol_ambil_alih)
        susunan.addLayout(aksi)
        self._perbarui_tombol()

    def muat_ulang(self) -> None:
        # Timer hanya menjadwalkan worker. Query PostgreSQL tidak boleh
        # menahan event loop dan membuat seluruh jendela admin membeku.
        if self.isVisible():
            if self._pekerja is not None and self._pekerja.isRunning():
                self._muat_ditunda = True
                return
            self._muat_ditunda = False
            pekerja = PekerjaLatar(self._ambil_data, self)
            pekerja.berhasil.connect(self._terapkan_data)
            pekerja.gagal.connect(self._gagal_muat)
            pekerja.finished.connect(self._bersihkan_pekerja)
            self._pekerja = pekerja
            pekerja.start()
            return

        berhasil, hasil = jalankan_aman(
            self, self._ambil_data, "Gagal memuat pelayanan aktif"
        )
        if berhasil and hasil is not None:
            self._terapkan_data(hasil)

    def _ambil_data(self) -> tuple[list[QueueInfo], list[TransferTargetInfo]]:
        return (
            self.queue.list_pelayanan_aktif(),
            self.queue.list_tujuan_pengalihan()
            if self.queue.auth.has_permission(Permission.QUEUE_REASSIGN)
            else [],
        )

    def _terapkan_data(
        self, hasil: tuple[list[QueueInfo], list[TransferTargetInfo]]
    ) -> None:
        terpilih = self._antrian_terpilih()
        id_terpilih = terpilih.id if terpilih else None
        self.data, self.targets = hasil
        self._isi_tabel(id_terpilih)
        self._isi_target()
        self.label_kosong.setText(
            "Tidak ada pelayanan aktif."
            if not self.data
            else f"{len(self.data)} pelayanan sedang aktif."
        )
        self._perbarui_tombol()

    def _gagal_muat(self, exc: Exception) -> None:
        # Penyegaran otomatis tidak boleh membuka dialog modal setiap lima
        # detik ketika jaringan putus. Data terakhir tetap terlihat.
        logger.warning("Penyegaran pelayanan aktif gagal: %s", exc)
        self.label_kosong.setText(
            "Data tidak dapat diperbarui. Tampilan terakhir dipertahankan."
        )

    def _bersihkan_pekerja(self) -> None:
        pekerja = self._pekerja
        self._pekerja = None
        if pekerja is not None:
            pekerja.deleteLater()
        if self._muat_ditunda and self.isVisible():
            self._muat_ditunda = False
            self.muat_ulang()

    def _isi_tabel(self, id_terpilih: int | None) -> None:
        self.tabel.setRowCount(len(self.data))
        baris_terpilih = -1
        for baris, antrian in enumerate(self.data):
            nilai = (
                antrian.queue_number,
                antrian.label_status,
                antrian.category_name,
                antrian.counter_name or "—",
                antrian.served_by_name or "Belum mulai melayani",
            )
            for kolom, teks in enumerate(nilai):
                item = QTableWidgetItem(teks)
                if kolom == 0:
                    item.setData(Qt.ItemDataRole.UserRole, antrian)
                self.tabel.setItem(baris, kolom, item)
            if antrian.id == id_terpilih:
                baris_terpilih = baris
        if baris_terpilih >= 0:
            self.tabel.selectRow(baris_terpilih)
        elif self.data:
            self.tabel.selectRow(0)

    def _isi_target(self) -> None:
        lama = self.pilih_petugas.currentData()
        lama_id = lama.user_id if isinstance(lama, TransferTargetInfo) else None
        self.pilih_petugas.blockSignals(True)
        self.pilih_petugas.clear()
        self.pilih_petugas.addItem("Pilih petugas tujuan…", None)
        for target in self.targets:
            self.pilih_petugas.addItem(
                f"{target.full_name} — {target.counter_name}", target
            )
        if lama_id is not None:
            for indeks in range(self.pilih_petugas.count()):
                target = self.pilih_petugas.itemData(indeks)
                if isinstance(target, TransferTargetInfo) and target.user_id == lama_id:
                    self.pilih_petugas.setCurrentIndex(indeks)
                    break
        self.pilih_petugas.blockSignals(False)

    def _antrian_terpilih(self) -> QueueInfo | None:
        baris = self.tabel.currentRow()
        if baris < 0:
            return None
        item = self.tabel.item(baris, 0)
        data = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return data if isinstance(data, QueueInfo) else None

    def _perbarui_tombol(self) -> None:
        ada_antrian = self._antrian_terpilih() is not None
        ada_alasan = bool(self.input_alasan.text().strip())
        self.tombol_batal.setEnabled(ada_antrian and ada_alasan)
        antrian = self._antrian_terpilih()
        self.tombol_selesai.setEnabled(
            ada_alasan
            and antrian is not None
            and antrian.status.value in ("SERVING", "PAUSED")
        )
        self.tombol_alihkan.setEnabled(
            ada_antrian
            and ada_alasan
            and isinstance(self.pilih_petugas.currentData(), TransferTargetInfo)
        )

    def alihkan(self) -> None:
        antrian = self._antrian_terpilih()
        target = self.pilih_petugas.currentData()
        alasan = self.input_alasan.text().strip()
        if antrian is None or not isinstance(target, TransferTargetInfo) or not alasan:
            return
        tambahan = (
            "\n\nPelayanan yang sedang berjalan akan dijeda terlebih dahulu."
            if antrian.status.value == "SERVING"
            else ""
        )
        if not konfirmasi(
            self,
            f"Alihkan {antrian.queue_number} dari {antrian.counter_name or 'loket lama'} "
            f"kepada {target.full_name} di {target.counter_name}?{tambahan}",
            "Alihkan Pelayanan",
        ):
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.queue.alihkan_pelayanan(
                antrian.id, target.user_id, alasan
            ),
            "Gagal mengalihkan pelayanan",
        )
        if berhasil:
            tampilkan_info(self, f"{antrian.queue_number} berhasil dialihkan.")
            self.input_alasan.clear()
            self.muat_ulang()

    def ambil_alih(self) -> None:
        """Ambil nomor aktif ke loket bawaan petugas yang sedang masuk."""
        antrian = self._antrian_terpilih()
        if antrian is None or antrian.status.value not in ("SERVING", "PAUSED"):
            return
        if not konfirmasi(self, f"Ambil alih pelayanan {antrian.queue_number}?"):
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.queue.ambil_alih_pelayanan(antrian.id),
            "Gagal mengambil alih pelayanan",
        )
        if berhasil:
            tampilkan_info(self, f"{antrian.queue_number} berhasil diambil alih.")
            self.muat_ulang()

    def selesaikan_paksa(self) -> None:
        antrian = self._antrian_terpilih()
        alasan = self.input_alasan.text().strip()
        if antrian is None or not alasan:
            return
        if not konfirmasi(
            self,
            f"Selesaikan {antrian.queue_number} sekarang?\n\n"
            "Untuk pelayanan yang sudah rampung tetapi belum ditutup petugasnya. "
            "Tindakan ini tidak menuntut catatan petugas dan tercatat di audit.",
            "Selesaikan Paksa",
        ):
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.queue.selesaikan_paksa(antrian.id, alasan),
            "Gagal menyelesaikan pelayanan",
        )
        if berhasil:
            tampilkan_info(self, f"{antrian.queue_number} diselesaikan.")
            self.input_alasan.clear()
            self.muat_ulang()

    def batalkan_paksa(self) -> None:
        antrian = self._antrian_terpilih()
        alasan = self.input_alasan.text().strip()
        if antrian is None or not alasan:
            return
        if not konfirmasi(
            self,
            f"Batalkan paksa {antrian.queue_number}?\n\n"
            "Tindakan ini hanya untuk pelayanan yang tidak akan dilanjutkan.",
            "Batalkan Paksa",
        ):
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.queue.batalkan_paksa(antrian.id, alasan),
            "Gagal membatalkan pelayanan",
        )
        if berhasil:
            tampilkan_info(self, f"{antrian.queue_number} dibatalkan.")
            self.input_alasan.clear()
            self.muat_ulang()

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().showEvent(event)
        self.muat_ulang()
        self.pewaktu.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - nama Qt
        self.pewaktu.stop()
        super().hideEvent(event)

    def hentikan(self) -> None:
        self.pewaktu.stop()
        if self._pekerja is not None and self._pekerja.isRunning():
            self._pekerja.wait(3_500)
        if self._pekerja is not None and self._pekerja.isRunning():
            lepaskan_pekerja(self._pekerja)
