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

from app.services.auth_service import AuthService
from app.services.master_data_service import MasterDataService
from app.services.queue_service import QueueInfo, QueueService
from app.services.settings_service import SettingsService
from app.services.survey_service import SurveyService
from app.ui.common import jalankan_aman, judul, keterangan, konfirmasi, tombol
from app.ui.style import BORDER, FONT_SIZE_HUGE, PRIMARY, TEXT_MUTED, WARNING
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
        auth: AuthService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.master = master
        self.survey = survey
        self.settings = settings
        #: Dipakai untuk memilih loket petugas ini sendiri saat halaman
        #: dibuka, dan mengingat kepindahannya bila ia berganti meja.
        self.auth = auth
        self.antrian: QueueInfo | None = None
        #: Status istirahat loket yang sedang dipilih, dibaca ulang setiap
        #: `muat_ulang()` supaya tombolnya benar walau diubah dari sesi lain.
        self.loket_istirahat = False
        #: Jenis layanan yang dilayani loket terpilih. Kosong berarti semua.
        self.loket_kategori: tuple[int, ...] = ()
        #: Antrian yang barusan diselesaikan. Disimpan karena setelah
        #: `complete()` loket tidak lagi memegang antrian apa pun, sedangkan
        #: nomor itulah yang perlu dinilai pengunjung yang masih di depan meja.
        self.baru_selesai: QueueInfo | None = None

        self._bangun_tampilan()
        self._pasang_pintasan()
        self.muat_loket()
        # Wajib setelah muat_loket(): `muat_ulang()` hanya menyusun ulang
        # pilihan jenis layanan ketika daftar loketnya BERUBAH, dan pada
        # loket tanpa batasan daftarnya tetap kosong sejak awal sehingga
        # tidak pernah dianggap berubah. Tanpa baris ini pilihannya kosong.
        self.muat_kategori()

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
        self.pilih_loket.currentIndexChanged.connect(self.loket_diganti)
        baris_atas.addWidget(self.pilih_loket)

        baris_atas.addWidget(QLabel("Jenis Layanan:"))
        self.pilih_kategori = QComboBox()
        self.pilih_kategori.setMinimumWidth(160)
        baris_atas.addWidget(self.pilih_kategori)

        self.tombol_istirahat = tombol("Mulai Istirahat")
        self.tombol_istirahat.clicked.connect(self.alihkan_istirahat)
        baris_atas.addWidget(self.tombol_istirahat)
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

        self.label_batas = QLabel("")
        self.label_batas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_batas.setWordWrap(True)
        self.label_batas.setStyleSheet(f"color: {WARNING}; font-weight: 600;")
        self.label_batas.setVisible(False)
        susunan.addWidget(self.label_batas)

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
        """
        Isi pilihan loket, lalu pilih loket milik petugas ini sendiri.

        Tanpa pemilihan itu, daftarnya selalu jatuh ke loket pertama dan
        petugas di Loket 4 akan memanggil atas nama Loket 1 setiap kali ia
        lupa menggantinya — pengunjungnya berjalan ke meja yang salah.
        """
        berhasil, data = jalankan_aman(
            self, lambda: self.master.list_counters(only_active=True)
        )
        if not berhasil:
            return

        self.pilih_loket.blockSignals(True)
        self.pilih_loket.clear()
        for loket in data:
            self.pilih_loket.addItem(loket.name, loket.id)

        bawaan = self.auth.current_session.default_counter_id if self.auth else None
        if bawaan is not None:
            baris = self.pilih_loket.findData(bawaan)
            if baris >= 0:
                self.pilih_loket.setCurrentIndex(baris)
        self.pilih_loket.blockSignals(False)
        self.muat_ulang()

    def loket_diganti(self) -> None:
        """
        Petugas berpindah meja: ingat loket barunya, lalu muat ulang.

        Kepindahan disimpan supaya besok tidak perlu diulang. Bila
        penyimpanannya gagal, halaman tetap dimuat ulang — bekerja di loket
        yang benar hari ini lebih penting daripada mengingatnya untuk besok.
        """
        if self.auth is not None and self.loket_id is not None:
            jalankan_aman(self, lambda: self.auth.pindah_loket(self.loket_id))
        self.muat_ulang()

    def muat_kategori(self) -> None:
        """
        Isi pilihan jenis layanan yang boleh disaring saat memanggil.

        "Semua Jenis Layanan" (data None) berarti PANGGIL BERIKUTNYA
        memanggil antrian terdepan lintas jenis layanan seperti biasa;
        memilih satu jenis layanan membatasi panggilan hanya pada
        antrian jenis itu, tetap yang paling depan di antara sesamanya.

        Loket khusus hanya menampilkan jenis layanan yang memang
        dilayaninya. Menawarkan pilihan yang pasti ditolak service hanya
        membuat petugas menabrak pesan kesalahan tanpa sebab yang terlihat.
        """
        berhasil, data = jalankan_aman(
            self, lambda: self.master.list_categories(only_active=True)
        )
        if not berhasil:
            return

        if self.loket_kategori:
            data = [k for k in data if k.id in self.loket_kategori]

        sebelumnya = self.pilih_kategori.currentData()
        self.pilih_kategori.blockSignals(True)
        self.pilih_kategori.clear()
        self.pilih_kategori.addItem("Semua Jenis Layanan", None)
        for kategori in data:
            self.pilih_kategori.addItem(kategori.name, kategori.id)

        # Pilihan petugas dipertahankan bila loket barunya masih melayani
        # jenis itu, supaya penyaringan tidak diam-diam hilang saat halaman
        # disegarkan setiap beberapa detik.
        baris = self.pilih_kategori.findData(sebelumnya)
        self.pilih_kategori.setCurrentIndex(max(baris, 0))
        self.pilih_kategori.blockSignals(False)

    @property
    def loket_id(self) -> int | None:
        return self.pilih_loket.currentData()

    def muat_ulang(self) -> None:
        """Segarkan antrian yang sedang ditangani dan daftar yang menunggu."""
        if self.loket_id is None:
            return

        berhasil, loket = jalankan_aman(self, lambda: self.master.get_counter(self.loket_id))
        self.loket_istirahat = loket.on_break if berhasil and loket else False
        self._perbarui_tombol_istirahat()

        # Loket khusus boleh berubah daftarnya dari sesi admin sementara
        # halaman ini terbuka, jadi pilihan jenis layanan disusun ulang
        # begitu daftarnya tidak lagi sama.
        kategori_loket = loket.category_ids if berhasil and loket else ()
        if kategori_loket != self.loket_kategori:
            self.loket_kategori = kategori_loket
            self.muat_kategori()

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

        self._tampilkan_pengingat_panggilan()
        self._perbarui_tombol()

    def _tampilkan_pengingat_panggilan(self) -> None:
        """
        Ingatkan petugas bila nomor sudah dipanggil sampai batasnya.

        Hanya pengingat. Tombol Panggil Ulang tetap menyala, karena
        pengunjung yang lambat sampai ke loket tidak boleh kehilangan
        nomornya hanya karena hitungan.
        """
        if self.antrian is not None and self.antrian.melewati_batas_panggilan:
            self.label_batas.setText(
                f"Sudah dipanggil {self.antrian.jumlah_panggilan}x tanpa hadir. "
                "Pertimbangkan menandainya Tidak Hadir."
            )
            self.label_batas.setVisible(True)
        else:
            self.label_batas.setVisible(False)

    def _perbarui_tombol(self) -> None:
        tersedia = set(self.antrian.aksi_tersedia()) if self.antrian else set()

        # Loket yang masih menangani seseorang, atau sedang istirahat,
        # belum boleh memanggil berikutnya.
        self.tombol_panggil.setEnabled(
            self.antrian is None and self.loket_id is not None and not self.loket_istirahat
        )
        for kunci, btn in self.aksi.items():
            btn.setEnabled(kunci in tersedia)

        self._perbarui_tombol_survey()

    def _perbarui_tombol_istirahat(self) -> None:
        self.tombol_istirahat.setEnabled(self.loket_id is not None)
        self.tombol_istirahat.setText(
            "Akhiri Istirahat" if self.loket_istirahat else "Mulai Istirahat"
        )

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

    def alihkan_istirahat(self) -> None:
        """
        Mulai atau akhiri istirahat loket yang sedang dipilih.

        Boleh dilakukan kapan pun, termasuk saat loket masih menangani
        seseorang — istirahat hanya menghentikan panggilan BERIKUTNYA,
        pengunjung yang sudah di depan meja tetap harus diselesaikan.
        """
        if self.loket_id is None:
            return
        self._jalankan(
            lambda: self.queue.set_istirahat(self.loket_id, not self.loket_istirahat),
            "Gagal mengubah status istirahat",
        )

    def panggil_berikutnya(self) -> None:
        if self.loket_id is None or not self.tombol_panggil.isEnabled():
            return
        category_id = self.pilih_kategori.currentData()
        self._jalankan(
            lambda: self.queue.call_next(self.loket_id, category_id=category_id),
            "Gagal memanggil antrian",
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
