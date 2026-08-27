"""Panel pelayanan petugas CRO."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.master_data_service import MasterDataService
from app.services.queue_service import QueueInfo, QueueService
from app.services.settings_service import SettingsService
from app.services.survey_service import SurveyService
from app.ui.common import jalankan_aman, judul, keterangan, konfirmasi, tombol
from app.ui.style import BORDER, FONT_SIZE_HUGE, PRIMARY, TEXT_MUTED
from app.ui.survey.survey_dialog import SurveyDialog


class ServicePage(QWidget):
    """
    Panel kerja petugas CRO.

    Tombol yang tidak sah untuk status saat ini dinonaktifkan, bukan
    disembunyikan — posisinya tetap sehingga petugas tidak perlu mencari
    ulang setiap kali status berubah.
    """

    def __init__(
        self,
        queue: QueueService,
        master: MasterDataService,
        survey: SurveyService,
        settings: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.master = master
        self.survey = survey
        self.settings = settings
        self.antrian: QueueInfo | None = None
        #: Antrian yang barusan diselesaikan. Disimpan karena setelah
        #: `complete()` loket tidak lagi memegang antrian apa pun, sedangkan
        #: nomor itulah yang perlu dinilai pengunjung yang masih di depan meja.
        self.baru_selesai: QueueInfo | None = None

        self._bangun_tampilan()
        self._pasang_pintasan()
        self.muat_loket()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(16)

        baris_atas = QHBoxLayout()
        baris_atas.addWidget(judul("Pelayanan Antrian"))
        baris_atas.addStretch()
        baris_atas.addWidget(QLabel("Loket:"))
        self.pilih_loket = QComboBox()
        self.pilih_loket.setMinimumWidth(160)
        self.pilih_loket.currentIndexChanged.connect(self.muat_ulang)
        baris_atas.addWidget(self.pilih_loket)
        susunan.addLayout(baris_atas)

        susunan.addWidget(self._bangun_panel_antrian())
        susunan.addLayout(self._bangun_tombol_aksi())
        susunan.addLayout(self._bangun_baris_survey())

        susunan.addWidget(keterangan("Menunggu dilayani"))
        self.tabel = QTableWidget(0, 4)
        self.tabel.setHorizontalHeaderLabels(
            ["Nomor", "Jenis Layanan", "Diambil Pukul", "Menunggu"]
        )
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        susunan.addWidget(self.tabel, stretch=1)

    def _bangun_panel_antrian(self) -> QWidget:
        panel = QFrame()
        # objectName wajib: QLabel turunan QFrame, dan selector "QFrame"
        # polos akan membingkai setiap label di dalam panel.
        panel.setObjectName("panelAntrian")
        panel.setStyleSheet(
            f"QFrame#panelAntrian {{ background: white; border: 1px solid {BORDER};"
            " border-radius: 6px; }}"
        )
        panel.setMinimumHeight(150)

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(24, 18, 24, 18)
        susunan.setSpacing(4)

        self.label_nomor = QLabel("—")
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_nomor.setStyleSheet(
            f"font-size: {FONT_SIZE_HUGE + 12}px; font-weight: 700; color: {PRIMARY};"
        )
        susunan.addWidget(self.label_nomor)

        self.label_layanan = QLabel("Tidak ada antrian yang sedang ditangani")
        self.label_layanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(self.label_layanan)

        self.label_status = QLabel("")
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_status.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_status)

        return panel

    def _bangun_tombol_aksi(self) -> QHBoxLayout:
        baris = QHBoxLayout()
        baris.setSpacing(8)

        self.tombol_panggil = tombol("PANGGIL BERIKUTNYA", variant="primary")
        self.tombol_panggil.setMinimumHeight(52)
        self.tombol_panggil.clicked.connect(self.panggil_berikutnya)
        baris.addWidget(self.tombol_panggil, stretch=2)

        self.aksi: dict[str, object] = {}
        for kunci, teks, handler, variant in (
            ("panggil_ulang", "Panggil Ulang", self.panggil_ulang, ""),
            ("mulai_layani", "Mulai Melayani", self.mulai_melayani, ""),
            ("selesai", "Selesai", self.selesaikan, "primary"),
            ("tunda", "Tunda", self.tunda, ""),
            ("lanjutkan", "Lanjutkan", self.lanjutkan, ""),
            ("tidak_hadir", "Tidak Hadir", self.tidak_hadir, ""),
            ("batal", "Batal", self.batalkan, "danger"),
        ):
            btn = tombol(teks, variant=variant)
            btn.setMinimumHeight(52)
            btn.clicked.connect(handler)
            baris.addWidget(btn, stretch=1)
            self.aksi[kunci] = btn

        return baris

    def _bangun_baris_survey(self) -> QHBoxLayout:
        """
        Permintaan pengisian survey, terpisah dari tombol alur pelayanan.

        Sengaja tidak muncul sendiri setelah pelayanan selesai. Petugaslah
        yang tahu apakah pengunjung masih di depan meja dan bersedia menilai;
        dialog yang menyembul sendiri justru menghambat antrian berikutnya.
        """
        baris = QHBoxLayout()
        baris.setSpacing(8)

        self.label_survey = QLabel("")
        self.label_survey.setStyleSheet(f"color: {TEXT_MUTED};")
        baris.addWidget(self.label_survey)
        baris.addStretch()

        self.tombol_survey = tombol("Minta Survey")
        self.tombol_survey.setEnabled(False)
        self.tombol_survey.clicked.connect(self.minta_survey)
        baris.addWidget(self.tombol_survey)

        return baris

    def _pasang_pintasan(self) -> None:
        """Pintasan untuk tindakan yang paling sering dipakai."""
        for kombinasi, handler in (
            ("F2", self.panggil_berikutnya),
            ("F3", self.panggil_ulang),
            ("F4", self.mulai_melayani),
            ("F8", self.selesaikan),
        ):
            QShortcut(QKeySequence(kombinasi), self, handler)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_loket(self) -> None:
        berhasil, data = jalankan_aman(
            self, lambda: self.master.list_counters(only_active=True)
        )
        if not berhasil:
            return

        self.pilih_loket.blockSignals(True)
        self.pilih_loket.clear()
        for loket in data:
            self.pilih_loket.addItem(loket.name, loket.id)
        self.pilih_loket.blockSignals(False)
        self.muat_ulang()

    @property
    def loket_id(self) -> int | None:
        return self.pilih_loket.currentData()

    def muat_ulang(self) -> None:
        """Segarkan antrian yang sedang ditangani dan daftar yang menunggu."""
        if self.loket_id is None:
            return

        berhasil, antrian = jalankan_aman(
            self, lambda: self.queue.current_for_counter(self.loket_id)
        )
        self.antrian = antrian if berhasil else None
        self._tampilkan_antrian()

        berhasil, menunggu = jalankan_aman(self, self.queue.list_waiting)
        if berhasil:
            self._isi_tabel(menunggu)

    def _tampilkan_antrian(self) -> None:
        if self.antrian is None:
            self.label_nomor.setText("—")
            self.label_layanan.setText("Tidak ada antrian yang sedang ditangani")
            self.label_status.setText("")
        else:
            self.label_nomor.setText(self.antrian.queue_number)
            self.label_layanan.setText(self.antrian.category_name)
            keterangan_panggilan = (
                f" · dipanggil {self.antrian.jumlah_panggilan}x"
                if self.antrian.jumlah_panggilan > 1
                else ""
            )
            self.label_status.setText(
                f"{self.antrian.label_status}{keterangan_panggilan}"
            )

        self._perbarui_tombol()

    def _perbarui_tombol(self) -> None:
        tersedia = set(self.antrian.aksi_tersedia()) if self.antrian else set()

        # Loket yang masih menangani seseorang belum boleh memanggil berikutnya.
        self.tombol_panggil.setEnabled(self.antrian is None and self.loket_id is not None)
        for kunci, btn in self.aksi.items():
            btn.setEnabled(kunci in tersedia)

        self._perbarui_tombol_survey()

    def _perbarui_tombol_survey(self) -> None:
        aktif = self.settings.get_bool("survey.enabled", True)
        if not aktif:
            self.tombol_survey.setEnabled(False)
            self.label_survey.setText("Survey kepuasan sedang dinonaktifkan.")
            return

        if self.baru_selesai is None:
            self.tombol_survey.setEnabled(False)
            self.label_survey.setText("")
            return

        self.tombol_survey.setEnabled(True)
        self.label_survey.setText(
            f"{self.baru_selesai.queue_number} belum dinilai pengunjung."
        )

    def _isi_tabel(self, menunggu: list[QueueInfo]) -> None:
        from app.core import clock

        sekarang = clock.now()
        self.tabel.setRowCount(len(menunggu))
        for baris, q in enumerate(menunggu):
            lama = int((sekarang - q.created_at).total_seconds() // 60)
            nilai = [
                q.queue_number,
                q.category_name,
                q.created_at.strftime("%H:%M"),
                f"{lama} menit",
            ]
            for kolom, teks in enumerate(nilai):
                self.tabel.setItem(baris, kolom, QTableWidgetItem(teks))

    # -----------------------------------------------------------------
    # Tindakan
    # -----------------------------------------------------------------

    def _jalankan(self, aksi, judul_gagal: str = "Gagal") -> None:
        berhasil, _ = jalankan_aman(self, aksi, judul_gagal)
        if berhasil:
            self.muat_ulang()

    def panggil_berikutnya(self) -> None:
        if self.loket_id is None or not self.tombol_panggil.isEnabled():
            return
        self._jalankan(
            lambda: self.queue.call_next(self.loket_id), "Gagal memanggil antrian"
        )

    def panggil_ulang(self) -> None:
        if self.antrian is None or not self.aksi["panggil_ulang"].isEnabled():
            return
        self._jalankan(lambda: self.queue.recall(self.antrian.id))

    def mulai_melayani(self) -> None:
        if self.antrian is None or not self.aksi["mulai_layani"].isEnabled():
            return
        self._jalankan(lambda: self.queue.start_service(self.antrian.id))

    def selesaikan(self) -> None:
        if self.antrian is None or not self.aksi["selesai"].isEnabled():
            return
        berhasil, selesai = jalankan_aman(
            self, lambda: self.queue.complete(self.antrian.id)
        )
        if not berhasil:
            return
        self.baru_selesai = selesai
        self.muat_ulang()

    def minta_survey(self) -> None:
        """Serahkan layar kepada pengunjung untuk menilai pelayanan."""
        if self.baru_selesai is None:
            return

        dialog = SurveyDialog(self.survey, self.baru_selesai, self)
        dialog.exec()
        # Tombol dimatikan apa pun hasilnya. Bila terisi, nomor itu memang
        # sudah dinilai; bila dilewati, pengunjung sudah menolak sekali dan
        # tidak perlu ditawari berulang kali.
        self.baru_selesai = None
        self._perbarui_tombol_survey()

    def tunda(self) -> None:
        if self.antrian is None:
            return
        self._jalankan(lambda: self.queue.pause(self.antrian.id))

    def lanjutkan(self) -> None:
        if self.antrian is None:
            return
        self._jalankan(lambda: self.queue.resume(self.antrian.id))

    def tidak_hadir(self) -> None:
        if self.antrian is None:
            return
        if not konfirmasi(
            self,
            f"Tandai {self.antrian.queue_number} sebagai tidak hadir?\n\n"
            f"Nomor ini sudah dipanggil {self.antrian.jumlah_panggilan}x.",
        ):
            return
        self._jalankan(lambda: self.queue.no_show(self.antrian.id))

    def batalkan(self) -> None:
        if self.antrian is None:
            return
        if not konfirmasi(self, f"Batalkan antrian {self.antrian.queue_number}?"):
            return
        self._jalankan(lambda: self.queue.cancel(self.antrian.id))
