"""Layar penerbitan nomor antrian."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
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
from app.ui.common import (
    PekerjaLatar,
    jalankan_aman,
    judul,
    keterangan,
    lepaskan_pekerja,
    tampilkan_error,
    tombol,
)
from app.ui.style import DANGER, FONT_SIZE_HUGE, PRIMARY, SUCCESS, TEXT_MUTED

_BELUM_DISEDIAKAN = object()


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
        self._pintasan_kategori: list[QShortcut] = []
        self._tombol_kategori: list = []
        self._sedang_menerbitkan = False
        self._pekerja_terbit: PekerjaLatar | None = None
        self._pekerja_cetak: PekerjaLatar | None = None
        self._pekerja_refresh: PekerjaLatar | None = None
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

        self.label_sinkron = keterangan("")
        self.label_sinkron.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
        self.label_sinkron.setVisible(False)
        susunan.addWidget(self.label_sinkron)

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
        if self.isVisible():
            self._mulai_refresh_latar()
            return
        try:
            data = self._ambil_data_pendaftaran()
        except Exception as exc:  # satu kegagalan cukup dilaporkan sekali
            tampilkan_error(self, exc, "Gagal memuat pendaftaran")
            self._gagal_refresh_latar(exc)
            return
        self._terapkan_data_pendaftaran(data)

    def _ambil_data_pendaftaran(self):
        terbuka = self.queue.pendaftaran_dibuka()
        kategori = self.master.list_categories(only_active=True, only_leaf=True)
        return terbuka, kategori

    def _mulai_refresh_latar(self) -> None:
        if self._pekerja_refresh is not None:
            return
        pekerja = PekerjaLatar(self._ambil_data_pendaftaran, self)
        pekerja.berhasil.connect(self._terapkan_data_pendaftaran)
        pekerja.gagal.connect(self._gagal_refresh_latar)
        pekerja.finished.connect(self._bersihkan_pekerja_refresh)
        self._pekerja_refresh = pekerja
        pekerja.start()

    def _terapkan_data_pendaftaran(self, data) -> None:
        terbuka, kategori = data
        self.pendaftaran_dibuka = bool(terbuka)
        self.label_sinkron.setVisible(False)
        self.tombol_pendaftaran.setEnabled(True)
        self.tombol_pendaftaran.setText(
            "Buka Pendaftaran" if not self.pendaftaran_dibuka else "Tutup Pendaftaran"
        )
        self.label_pendaftaran_tertutup.setVisible(not self.pendaftaran_dibuka)

        # only_leaf: yang ditawarkan kepada petugas hanyalah jenis layanan
        # yang benar-benar menerbitkan nomor. "Konsultasi" sudah menjadi
        # kelompok dan tidak punya nomor sendiri; menampilkannya di sini
        # hanya menyiapkan tombol yang pasti ditolak service.
        self.kategori = kategori
        self._susun_tombol()

    def _gagal_refresh_latar(self, _exc: Exception) -> None:
        self.label_sinkron.setText(
            "Status pendaftaran tidak dapat diperbarui. Penerbitan nomor "
            "dinonaktifkan sampai koneksi pulih."
        )
        self.label_sinkron.setVisible(True)
        self.tombol_pendaftaran.setEnabled(False)
        for btn in self._tombol_kategori:
            btn.setEnabled(False)
        for pintasan in self._pintasan_kategori:
            pintasan.setEnabled(False)

    def _bersihkan_pekerja_refresh(self) -> None:
        pekerja = self._pekerja_refresh
        self._pekerja_refresh = None
        if pekerja is not None:
            pekerja.deleteLater()

    def alihkan_pendaftaran(self) -> None:
        aksi = self.queue.buka_pendaftaran if not self.pendaftaran_dibuka else self.queue.tutup_pendaftaran
        berhasil, _ = jalankan_aman(self, aksi, "Gagal mengubah status pendaftaran")
        if berhasil:
            self.muat_ulang()

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().showEvent(event)
        self.muat_ulang()

    def _susun_tombol(self) -> None:
        for pintasan in self._pintasan_kategori:
            pintasan.setEnabled(False)
            pintasan.setParent(None)
            pintasan.deleteLater()
        self._pintasan_kategori.clear()
        self._tombol_kategori.clear()

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
                lambda _=False, id_layanan=layanan.id: self._minta_terbitkan(id_layanan)
            )
            btn.setEnabled(self.pendaftaran_dibuka)
            self._tombol_kategori.append(btn)
            self.kisi.addWidget(btn, indeks // 3, indeks % 3)

            if indeks < 9:
                pintasan = QShortcut(
                    QKeySequence(str(indeks + 1)),
                    self,
                    lambda id_layanan=layanan.id: self._minta_terbitkan(id_layanan),
                )
                pintasan.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                pintasan.setEnabled(self.pendaftaran_dibuka)
                self._pintasan_kategori.append(pintasan)

    # -----------------------------------------------------------------

    def _minta_terbitkan(self, category_id: int) -> None:
        """Jalur tombol/shortcut dengan penahan klik ganda singkat."""
        if self._sedang_menerbitkan or not self.pendaftaran_dibuka:
            return
        self._sedang_menerbitkan = True
        for btn in self._tombol_kategori:
            btn.setEnabled(False)
        for pintasan in self._pintasan_kategori:
            pintasan.setEnabled(False)
        if not self.isVisible():
            try:
                self.terbitkan(category_id)
            finally:
                QTimer.singleShot(500, self._akhiri_jeda_penerbitan)
            return

        pekerja = PekerjaLatar(lambda: self._terbitkan_dan_hitung(category_id), self)
        pekerja.berhasil.connect(self._selesai_terbit_latar)
        pekerja.gagal.connect(self._gagal_terbit_latar)
        pekerja.finished.connect(self._bersihkan_pekerja_terbit)
        self._pekerja_terbit = pekerja
        pekerja.start()

    def _terbitkan_dan_hitung(self, category_id: int):
        nomor = self.queue.create_queue(category_id)
        try:
            menunggu = self.queue.list_waiting()
        except Exception:  # nomor sudah sah; ringkasan posisi boleh gagal
            menunggu = None
        return nomor, menunggu

    def _selesai_terbit_latar(self, hasil) -> None:
        nomor, menunggu = hasil
        self.terakhir = nomor
        self._tampilkan_hasil(nomor, menunggu=menunggu)
        self.nomor_terbit.emit(nomor)
        self._mulai_cetak_latar(nomor)

    def _gagal_terbit_latar(self, exc: Exception) -> None:
        tampilkan_error(self, exc, "Gagal menerbitkan nomor")
        QTimer.singleShot(500, self._akhiri_jeda_penerbitan)

    def _bersihkan_pekerja_terbit(self) -> None:
        pekerja = self._pekerja_terbit
        self._pekerja_terbit = None
        if pekerja is not None:
            pekerja.deleteLater()

    def _akhiri_jeda_penerbitan(self) -> None:
        self._sedang_menerbitkan = False
        for btn in self._tombol_kategori:
            btn.setEnabled(self.pendaftaran_dibuka)
        for pintasan in self._pintasan_kategori:
            pintasan.setEnabled(self.pendaftaran_dibuka)

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

    def _tampilkan_hasil(
        self, nomor: QueueInfo, *, menunggu=_BELUM_DISEDIAKAN
    ) -> None:
        self.label_nomor.setText(nomor.queue_number)
        self.label_layanan.setText(nomor.category_name)

        berhasil = menunggu is not None
        if menunggu is _BELUM_DISEDIAKAN:
            berhasil, menunggu = jalankan_aman(self, self.queue.list_waiting)
        if berhasil and menunggu is not None:
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
        self._tampilkan_status_cetak(nomor, hasil)

    def _tampilkan_status_cetak(self, nomor: QueueInfo, hasil) -> None:
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

    def _mulai_cetak_latar(self, nomor: QueueInfo) -> None:
        if self.ticket is None:
            self.label_cetak.setVisible(False)
            self.tombol_cetak_ulang.setVisible(False)
            QTimer.singleShot(500, self._akhiri_jeda_penerbitan)
            return
        self.label_cetak.setText("Mencetak tiket…")
        self.label_cetak.setStyleSheet(f"color: {TEXT_MUTED};")
        self.label_cetak.setVisible(True)
        self.tombol_cetak_ulang.setVisible(False)
        pekerja = PekerjaLatar(lambda: self.ticket.cetak(nomor), self)
        pekerja.berhasil.connect(lambda hasil: self._tampilkan_status_cetak(nomor, hasil))
        pekerja.gagal.connect(lambda exc: self._gagal_cetak_latar(nomor, exc))
        pekerja.finished.connect(self._bersihkan_pekerja_cetak)
        self._pekerja_cetak = pekerja
        pekerja.start()

    def _gagal_cetak_latar(self, nomor: QueueInfo, exc: Exception) -> None:
        self.label_cetak.setText(
            f"Tiket gagal dicetak. Sebutkan nomor {nomor.queue_number} kepada pengunjung."
        )
        self.label_cetak.setStyleSheet(f"color: {DANGER}; font-weight: 600;")
        self.label_cetak.setVisible(True)
        self.tombol_cetak_ulang.setVisible(True)

    def _bersihkan_pekerja_cetak(self) -> None:
        pekerja = self._pekerja_cetak
        self._pekerja_cetak = None
        if pekerja is not None:
            pekerja.deleteLater()
        QTimer.singleShot(500, self._akhiri_jeda_penerbitan)

    def cetak_ulang(self) -> None:
        """Cetak ulang tiket terakhir, misalnya karena kertas tersangkut."""
        if self.terakhir is not None:
            if self.isVisible() and self._pekerja_cetak is None:
                self._mulai_cetak_latar(self.terakhir)
            else:
                self._cetak(self.terakhir)

    def hentikan(self) -> None:
        """Tunggu singkat pekerjaan database/printer sebelum halaman dibuang."""
        for pekerja in (
            self._pekerja_refresh,
            self._pekerja_terbit,
            self._pekerja_cetak,
        ):
            if pekerja is None:
                continue
            try:
                if pekerja.isRunning():
                    pekerja.wait(3_500)
                if pekerja.isRunning():
                    lepaskan_pekerja(pekerja)
            except RuntimeError:
                pass
