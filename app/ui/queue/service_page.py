"""Panel pelayanan petugas CRO."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.models import QueueStatus
from app.services.auth_service import AuthService
from app.services.master_data_service import MasterDataService
from app.services.note_service import NoteService
from app.services.queue_service import QueueInfo, QueueService
from app.services.settings_service import SettingsService
from app.services.survey_service import SurveyService
from app.ui.common import (
    jalankan_aman,
    judul,
    keterangan,
    konfirmasi,
    setel_variant,
    tombol,
)
from app.ui.queue.note_panel import NotePanel
from app.ui.queue.pelapor_form import PelaporForm
from app.ui.style import (
    BORDER,
    BORDER_STRONG,
    DANGER,
    FONT_SIZE_HUGE,
    FONT_SIZE_LARGE,
    FONT_SIZE_SMALL,
    FONT_SIZE_XL,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_SOFT,
    RADIUS,
    SUCCESS,
    SUCCESS_SOFT,
    SURFACE,
    SURFACE_ALT,
    TEXT,
    TEXT_MUTED,
    WARNING,
    WARNING_SOFT,
)
from app.ui.survey.survey_dialog import SurveyDialog

#: Selang perbaruan penghitung lama pelayanan, dalam milidetik.
#:
#: Hanya menghitung ulang selisih waktu dan menulis satu label — TIDAK
#: menyentuh database. Penyegaran data tetap terjadi saat petugas menekan
#: tombol atau F5, seperti sebelumnya.
SELANG_DURASI_MS = 1000

#: Ambang lama menunggu yang diberi warna pada daftar tunggu, dalam menit.
#:
#: Angka pada kolom "Menunggu" tidak berarti apa-apa sampai ada
#: pembandingnya. Warna memberi pembanding itu tanpa menambah satu kolom
#: pun: petugas melihat siapa yang sudah terlalu lama duduk tanpa membaca
#: satu angka pun.
TUNGGU_LAMA_MENIT = 10
TUNGGU_SANGAT_LAMA_MENIT = 20


def _pil(warna_teks: str, latar: str) -> str:
    """Gaya label berbentuk kapsul, dipakai untuk menandai keadaan."""
    return (
        f"background: {latar}; color: {warna_teks}; border-radius: 11px;"
        f" padding: 5px 14px; font-size: {FONT_SIZE_SMALL}px; font-weight: 700;"
    )


class ServicePage(QWidget):
    """
    Panel kerja petugas CRO.

    Tata letaknya dua kolom: kolom kiri untuk satu antrian yang sedang
    ditangani beserta seluruh tindakannya, kolom kanan untuk daftar yang
    menunggu. Pemisahan ini disengaja — petugas hampir sepanjang hari hanya
    melihat kolom kiri, dan kolom kanan cukup dilirik.

    Tombol yang tidak sah untuk status saat ini dinonaktifkan, bukan
    disembunyikan — posisinya tetap sehingga petugas tidak perlu mencari
    ulang setiap kali status berubah. Aturan ini yang menentukan bentuk
    kisi tombolnya: seluruh tombol selalu tampak, yang berubah hanya
    warna dan keaktifannya.
    """

    def __init__(
        self,
        queue: QueueService,
        master: MasterDataService,
        survey: SurveyService,
        settings: SettingsService,
        auth: AuthService | None = None,
        parent: QWidget | None = None,
        *,
        note: NoteService | None = None,
        otomatis: bool = True,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.master = master
        self.survey = survey
        self.settings = settings
        #: Ruang kerja pengaduan/catatan. Boleh None: panel kanan lalu
        #: hanya berisi Menunggu Dilayani, dipakai test yang hanya menguji
        #: alur pelayanan. Pemasangan sungguhan selalu mengirimkannya.
        self.note = note
        #: Antrian aktif pada penyegaran SEBELUMNYA. Dipakai mendeteksi
        #: transisi loket kosong <-> sedang melayani, satu-satunya saat
        #: panel kanan berpindah tab sendiri — lihat `_perbarui_panel_kanan`.
        self._kanan_aktif_sebelumnya: bool | None = None
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

        # Penghitung lama pelayanan. Dipisahkan dari penyegaran data supaya
        # angka detiknya berjalan tanpa membebani database sedetik sekali.
        self.pewaktu_durasi = QTimer(self)
        self.pewaktu_durasi.setInterval(SELANG_DURASI_MS)
        self.pewaktu_durasi.timeout.connect(self._perbarui_durasi)
        if otomatis:
            self.pewaktu_durasi.start()

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
        susunan.setContentsMargins(18, 14, 18, 14)
        susunan.setSpacing(12)

        susunan.addWidget(self._bangun_kepala())

        isi = QHBoxLayout()
        isi.setSpacing(16)
        isi.addLayout(self._bangun_kolom_kerja(), stretch=5)
        isi.addWidget(self._bangun_panel_kanan(), stretch=4)
        susunan.addLayout(isi, stretch=1)

    def _bangun_kepala(self) -> QWidget:
        """
        Bilah judul beserta pilihan loket dan jenis layanan.

        Loket dan jenis layanan diletakkan di sini, bukan di dekat tombol,
        karena keduanya diatur sekali di awal giliran lalu tidak disentuh
        lagi sepanjang hari. Menaruhnya bersebelahan dengan tombol yang
        ditekan ratusan kali hanya menambah peluang tersenggol.
        """
        kepala = QFrame()
        kepala.setObjectName("panelKepala")
        kepala.setStyleSheet(
            f"QFrame#panelKepala {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )

        susunan = QHBoxLayout(kepala)
        susunan.setContentsMargins(18, 12, 18, 12)
        susunan.setSpacing(14)

        teks = QVBoxLayout()
        teks.setSpacing(2)
        teks.addWidget(judul("Pelayanan Antrian"))
        petunjuk = keterangan("F2 panggil · F3 ulangi · F4 mulai · F8 selesai")
        petunjuk.setWordWrap(False)
        petunjuk.setStyleSheet(f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;")
        teks.addWidget(petunjuk)
        susunan.addLayout(teks)
        susunan.addStretch()

        self.pilih_loket = QComboBox()
        self.pilih_loket.setMinimumWidth(170)
        self.pilih_loket.currentIndexChanged.connect(self.loket_diganti)
        susunan.addLayout(self._berlabel("LOKET", self.pilih_loket))

        self.pilih_kategori = QComboBox()
        self.pilih_kategori.setMinimumWidth(200)
        susunan.addLayout(self._berlabel("JENIS LAYANAN", self.pilih_kategori))

        self.tombol_istirahat = tombol("Mulai Istirahat")
        self.tombol_istirahat.setMinimumHeight(40)
        self.tombol_istirahat.clicked.connect(self.alihkan_istirahat)
        susunan.addLayout(self._berlabel("", self.tombol_istirahat))

        return kepala

    @staticmethod
    def _berlabel(kapsi: str, kontrol: QWidget) -> QVBoxLayout:
        """Satu kontrol beserta keterangan kecil di atasnya."""
        kotak = QVBoxLayout()
        kotak.setSpacing(4)
        label = QLabel(kapsi)
        label.setProperty("kapsi", "true")
        kotak.addWidget(label)
        kotak.addWidget(kontrol)
        return kotak

    def _bangun_kolom_kerja(self) -> QVBoxLayout:
        kolom = QVBoxLayout()
        kolom.setSpacing(10)
        kolom.addWidget(self._bangun_panel_antrian())
        kolom.addLayout(self._bangun_tombol_aksi())

        self.pelapor: PelaporForm | None = None
        if self.note is not None:
            # Identitas ditulis sambil BERTANYA kepada orang di depan meja,
            # sedangkan keluhannya ditulis sambil MENDENGARKAN. Isian pendek
            # ini karena itu tetap di layar; kotak keluhan yang panjang
            # mendapat tempatnya sendiri di panel kanan — lihat
            # `_bangun_panel_kanan`.
            self.pelapor = PelaporForm()
            kolom.addWidget(self.pelapor)

        kolom.addStretch()
        kolom.addWidget(self._bangun_baris_survey())
        return kolom

    def _bangun_panel_antrian(self) -> QWidget:
        """
        Kartu antrian yang sedang ditangani.

        Warnanya berubah mengikuti status — abu-abu saat menganggur, jingga
        saat nomor sudah dipanggil tetapi orangnya belum datang, hijau saat
        pelayanan berjalan. Petugas mengenali keadaannya dari sudut mata,
        sebelum sempat membaca satu kata pun.
        """
        panel = QFrame()
        # objectName wajib: QLabel turunan QFrame, dan selector "QFrame"
        # polos akan membingkai setiap label di dalam panel.
        panel.setObjectName("panelAntrian")
        panel.setMinimumHeight(150)
        self.panel_antrian = panel

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(22, 14, 22, 14)
        susunan.setSpacing(4)

        baris_atas = QHBoxLayout()
        self.label_status = QLabel("")
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        baris_atas.addWidget(self.label_status)
        baris_atas.addStretch()

        self.label_durasi = QLabel("")
        self.label_durasi.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_LARGE}px; font-weight: 700;"
        )
        baris_atas.addWidget(self.label_durasi)
        susunan.addLayout(baris_atas)

        susunan.addStretch()

        self.label_nomor = QLabel("—")
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(self.label_nomor)

        self.label_layanan = QLabel("Tidak ada antrian yang sedang ditangani")
        self.label_layanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_layanan.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_LARGE}px;"
        )
        susunan.addWidget(self.label_layanan)

        susunan.addStretch()

        self.label_batas = QLabel("")
        self.label_batas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_batas.setWordWrap(True)
        self.label_batas.setStyleSheet(
            f"background: {WARNING_SOFT}; color: {WARNING}; font-weight: 700;"
            " border-radius: 6px; padding: 8px 12px;"
        )
        self.label_batas.setVisible(False)
        susunan.addWidget(self.label_batas)

        self._warnai_panel_antrian()
        return panel

    def _bangun_tombol_aksi(self) -> QVBoxLayout:
        """
        Tombol tindakan, disusun menurun dari yang paling sering ditekan.

        PANGGIL BERIKUTNYA mendapat satu barisnya sendiri karena itulah
        tombol yang ditekan ratusan kali sehari; sisanya berkelompok tiga
        kolom. Dua tindakan yang menutup antrian tanpa melayani dipisahkan
        ke kelompok terakhir supaya tidak tertekan karena refleks.
        """
        kotak = QVBoxLayout()
        kotak.setSpacing(8)

        self.tombol_panggil = tombol("PANGGIL BERIKUTNYA  ·  F2", variant="primary")
        self.tombol_panggil.setMinimumHeight(56)
        self.tombol_panggil.setStyleSheet(f"font-size: {FONT_SIZE_XL}px;")
        self.tombol_panggil.clicked.connect(self.panggil_berikutnya)
        kotak.addWidget(self.tombol_panggil)

        kotak.addWidget(self._kapsi("ALUR PELAYANAN"))

        self.aksi: dict[str, object] = {}
        kisi = QGridLayout()
        kisi.setSpacing(8)
        for kolom in range(3):
            kisi.setColumnStretch(kolom, 1)

        for posisi, (kunci, teks, handler, variant) in enumerate(
            (
                ("panggil_ulang", "Panggil Ulang  ·  F3", self.panggil_ulang, ""),
                ("mulai_layani", "Mulai Melayani  ·  F4", self.mulai_melayani, ""),
                ("selesai", "Selesai  ·  F8", self.selesaikan, "success"),
                ("tunda", "Tunda", self.tunda, ""),
                ("lanjutkan", "Lanjutkan", self.lanjutkan, ""),
            )
        ):
            btn = tombol(teks, variant=variant)
            btn.setMinimumHeight(42)
            btn.clicked.connect(handler)
            kisi.addWidget(btn, posisi // 3, posisi % 3)
            self.aksi[kunci] = btn
        kotak.addLayout(kisi)

        kotak.addWidget(self._kapsi("BILA PENGUNJUNG TIDAK DATANG"))

        baris_tutup = QHBoxLayout()
        baris_tutup.setSpacing(8)
        for kunci, teks, handler in (
            ("tidak_hadir", "Tidak Hadir", self.tidak_hadir),
            ("batal", "Batalkan Antrian", self.batalkan),
        ):
            btn = tombol(teks, variant="danger")
            btn.setMinimumHeight(38)
            btn.clicked.connect(handler)
            baris_tutup.addWidget(btn)
            self.aksi[kunci] = btn
        baris_tutup.addStretch()
        kotak.addLayout(baris_tutup)

        return kotak

    @staticmethod
    def _kapsi(teks: str) -> QLabel:
        label = QLabel(teks)
        label.setProperty("kapsi", "true")
        return label

    def _bangun_baris_survey(self) -> QWidget:
        """
        Permintaan pengisian survey, terpisah dari tombol alur pelayanan.

        Sengaja tidak muncul sendiri setelah pelayanan selesai. Petugaslah
        yang tahu apakah pengunjung masih di depan meja dan bersedia menilai;
        dialog yang menyembul sendiri justru menghambat antrian berikutnya.
        """
        panel = QFrame()
        panel.setObjectName("panelSurvey")
        panel.setStyleSheet(
            f"QFrame#panelSurvey {{ background: {SURFACE_ALT};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )

        baris = QHBoxLayout(panel)
        baris.setContentsMargins(14, 8, 14, 8)
        baris.setSpacing(8)

        self.label_survey = QLabel("")
        self.label_survey.setStyleSheet(f"color: {TEXT_MUTED};")
        self.label_survey.setWordWrap(True)
        baris.addWidget(self.label_survey, stretch=1)

        self.tombol_survey = tombol("Minta Survey")
        self.tombol_survey.setMinimumHeight(36)
        self.tombol_survey.setEnabled(False)
        self.tombol_survey.clicked.connect(self.minta_survey)
        baris.addWidget(self.tombol_survey)

        return panel

    def _bangun_panel_kanan(self) -> QWidget:
        """
        Menunggu Dilayani dan ruang kerja pengaduan, berbagi satu tempat.

        Berpindah SENDIRI mengikuti status loket — lihat
        `_perbarui_panel_kanan` — karena keduanya menjawab pertanyaan yang
        berbeda pada saat yang berbeda: siapa berikutnya (loket kosong)
        atau apa yang perlu dicatat (loket sedang melayani). Tab tetap
        dapat dibuka manual kapan pun, sehingga daftar tunggu tidak pernah
        benar-benar terkunci di belakang apa pun — beda dengan dialog yang
        sempat dipakai sebelumnya, yang menutup akses ke keduanya sampai
        jendelanya ditutup.
        """
        self.tab_kanan = QTabWidget()
        self.tab_kanan.setMinimumWidth(320)
        self.tab_kanan.addTab(self._bangun_panel_menunggu(), "Menunggu Dilayani")

        self.panel_pengaduan: NotePanel | None = None
        if self.note is not None and self.pelapor is not None:
            self.panel_pengaduan = NotePanel(self.note, self.pelapor)
            self.tab_kanan.addTab(self.panel_pengaduan, "Pengaduan & Catatan")

        return self.tab_kanan

    def _bangun_panel_menunggu(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panelMenunggu")
        panel.setStyleSheet(
            f"QFrame#panelMenunggu {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )
        self.panel_menunggu = panel

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(16, 14, 16, 14)
        susunan.setSpacing(10)

        # Tidak ada lagi judul "MENUNGGU DILAYANI" di sini — tab di atasnya
        # sudah menyebutnya. Yang tersisa hanya pil jumlahnya.
        baris_judul = QHBoxLayout()
        baris_judul.addStretch()
        self.label_jumlah = QLabel("0")
        self.label_jumlah.setStyleSheet(_pil(PRIMARY_DARK, PRIMARY_SOFT))
        baris_judul.addWidget(self.label_jumlah)
        susunan.addLayout(baris_judul)

        self.tabel = QTableWidget(0, 4)
        # Judul kolom sengaja sesingkat mungkin. Panel ini hanya sepertiga
        # lebar halaman, dan judul yang tidak muat TIDAK dipotong dengan
        # "…" oleh Qt melainkan dipangkas di kedua sisinya — "Jenis
        # Layanan" terbaca "nis Layana", yang lebih buruk daripada
        # singkatannya.
        self.tabel.setHorizontalHeaderLabels(
            ["Nomor", "Layanan", "Diambil", "Menunggu"]
        )
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setShowGrid(False)
        self.tabel.setWordWrap(False)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.verticalHeader().setDefaultSectionSize(40)

        kepala = self.tabel.horizontalHeader()
        kepala.setHighlightSections(False)
        # Hanya nama layanan yang boleh memuai. Tiga kolom lainnya
        # panjangnya tetap — nomor, jam, dan hitungan menit — sehingga
        # seluruh sisa lebar jatuh ke kolom yang isinya memang paling
        # bervariasi.
        for kolom, mode in (
            (0, QHeaderView.ResizeMode.ResizeToContents),
            (1, QHeaderView.ResizeMode.Stretch),
            (2, QHeaderView.ResizeMode.ResizeToContents),
            (3, QHeaderView.ResizeMode.ResizeToContents),
        ):
            kepala.setSectionResizeMode(kolom, mode)
        susunan.addWidget(self.tabel, stretch=1)

        self.label_kosong = QLabel(
            "Tidak ada yang menunggu.\nSemua nomor hari ini sudah dipanggil."
        )
        self.label_kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_kosong.setWordWrap(True)
        self.label_kosong.setStyleSheet(f"color: {TEXT_MUTED};")
        self.label_kosong.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.label_kosong.setVisible(False)
        susunan.addWidget(self.label_kosong, stretch=1)

        return panel

    def _pasang_pintasan(self) -> None:
        """Pintasan untuk tindakan yang paling sering dipakai."""
        for kombinasi, handler in (
            ("F2", self.panggil_berikutnya),
            ("F3", self.panggil_ulang),
            ("F4", self.mulai_melayani),
            ("F8", self.selesaikan),
            ("F9", self.buka_ruang_kerja),
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
            self.label_status.setText(
                "Loket sedang istirahat" if self.loket_istirahat else "Siap memanggil"
            )
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

        self._perbarui_panel_kanan()
        self._warnai_panel_antrian()
        self._perbarui_durasi()
        self._tampilkan_pengingat_panggilan()
        self._perbarui_tombol()

    def _warnai_panel_antrian(self) -> None:
        """
        Selaraskan warna kartu dengan status antrian yang dipegang loket.

        Satu tempat untuk seluruh warnanya. Tersebar di beberapa tempat,
        kartu dan kapsul statusnya cepat atau lambat akan menyebut dua
        keadaan yang berbeda pada saat yang sama.
        """
        aksen, latar, teks_pil, latar_pil = self._palet_keadaan()

        self.panel_antrian.setStyleSheet(
            f"QFrame#panelAntrian {{ background: {latar};"
            f" border: 1px solid {BORDER}; border-left: 6px solid {aksen};"
            f" border-radius: {RADIUS}px; }}"
        )
        self.label_status.setStyleSheet(_pil(teks_pil, latar_pil))
        self.label_nomor.setStyleSheet(
            f"font-size: {FONT_SIZE_HUGE + 22}px; font-weight: 800;"
            f" color: {aksen if self.antrian else TEXT_MUTED};"
        )

    def _palet_keadaan(self) -> tuple[str, str, str, str]:
        """
        Warna aksen kartu, latar kartu, teks kapsul, dan latar kapsul.

        Kapsul mendapat latarnya sendiri karena kartu yang menganggur
        berlatar putih: kapsul putih di atasnya tidak akan terlihat sebagai
        kapsul sama sekali, hanya sebagai tulisan yang menggantung.
        """
        if self.antrian is None:
            if self.loket_istirahat:
                return WARNING, WARNING_SOFT, WARNING, SURFACE
            return BORDER_STRONG, SURFACE, TEXT_MUTED, SURFACE_ALT
        if self.antrian.status is QueueStatus.SERVING:
            return SUCCESS, SUCCESS_SOFT, SUCCESS, SURFACE
        if self.antrian.status is QueueStatus.PAUSED:
            return PRIMARY, PRIMARY_SOFT, PRIMARY_DARK, SURFACE
        # CALLED: nomor sudah disebut, orangnya belum tentu datang.
        return WARNING, WARNING_SOFT, WARNING, SURFACE

    def _perbarui_durasi(self) -> None:
        """
        Perbarui penghitung waktu pada kartu antrian.

        Sengaja TIDAK menyentuh database: dipanggil sedetik sekali, dan
        satu query per detik per loket akan membebani server hanya untuk
        menampilkan angka yang bisa dihitung sendiri dari data yang sudah
        ada di tangan.
        """
        if self.antrian is None:
            self.label_durasi.setText("")
            return

        from app.core import clock

        sejak = (
            self.antrian.called_at
            if self.antrian.status is QueueStatus.CALLED
            else self.antrian.serving_at
        )

        if sejak is None:
            self.label_durasi.setText("")
            return

        detik = max(0, int((clock.now() - sejak).total_seconds()))
        menit, sisa = divmod(detik, 60)
        jam, menit = divmod(menit, 60)
        waktu = f"{jam}:{menit:02d}:{sisa:02d}" if jam else f"{menit:02d}:{sisa:02d}"

        aksen = self._palet_keadaan()[0]
        self.label_durasi.setText(f"berjalan {waktu}")
        self.label_durasi.setStyleSheet(
            f"color: {aksen}; font-size: {FONT_SIZE_LARGE}px; font-weight: 700;"
        )

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
        setel_variant(self.tombol_istirahat, "warning" if self.loket_istirahat else "")

    def _perbarui_panel_kanan(self) -> None:
        """
        Berpindah tab sendiri mengikuti transisi loket kosong <-> melayani.

        Hanya bereaksi pada TRANSISI, bukan setiap penyegaran: memanggil
        ulang (F3) atau menunda (F4) tidak mengganti antrian yang dipegang
        loket, dan memaksa tab berganti setiap `muat_ulang()` akan menyeret
        petugas keluar dari tab yang sengaja ia buka sendiri untuk melirik
        daftar tunggu sambil tetap melayani.
        """
        if self.panel_pengaduan is not None:
            self.panel_pengaduan.set_antrian(self.antrian)

        aktif = self.antrian is not None
        if aktif != self._kanan_aktif_sebelumnya:
            self._kanan_aktif_sebelumnya = aktif
            if self.panel_pengaduan is not None:
                self.tab_kanan.setCurrentIndex(1 if aktif else 0)

    def _perbarui_tombol_survey(self) -> None:
        aktif = self.settings.get_bool("survey.enabled", True)
        if not aktif:
            self.tombol_survey.setEnabled(False)
            self.label_survey.setText("Survey kepuasan sedang dinonaktifkan.")
            return

        if self.baru_selesai is None:
            self.tombol_survey.setEnabled(False)
            self.label_survey.setText(
                "Survey ditawarkan setelah sebuah pelayanan diselesaikan."
            )
            return

        self.tombol_survey.setEnabled(True)
        self.label_survey.setText(
            f"{self.baru_selesai.queue_number} belum dinilai pengunjung."
        )

    def _isi_tabel(self, menunggu: list[QueueInfo]) -> None:
        from app.core import clock

        sekarang = clock.now()
        self.label_jumlah.setText(str(len(menunggu)))
        self.tabel.setVisible(bool(menunggu))
        self.label_kosong.setVisible(not menunggu)

        self.tabel.setRowCount(len(menunggu))
        lama_menit: list[int] = []
        for baris, q in enumerate(menunggu):
            lama = int((sekarang - q.created_at).total_seconds() // 60)
            lama_menit.append(lama)
            nilai = [
                q.queue_number,
                q.category_name,
                q.created_at.strftime("%H:%M"),
                f"{lama} menit",
            ]
            for kolom, teks in enumerate(nilai):
                sel = QTableWidgetItem(teks)
                self._gayai_sel(sel, baris=baris, kolom=kolom, menit=lama)
                self.tabel.setItem(baris, kolom, sel)

        self._perbarui_judul_tab_menunggu(len(menunggu), lama_menit)

    def _perbarui_judul_tab_menunggu(
        self, jumlah: int, lama_menit: list[int]
    ) -> None:
        """
        Sebut jumlah menunggu, dan yang sudah lama, pada judul tabnya.

        Panel kanan berpindah ke tab Pengaduan & Catatan begitu sebuah
        nomor dipanggil, dan sejak itu daftar tunggu tidak lagi terlihat
        tanpa mengklik tabnya. Judul tab inilah satu-satunya yang tersisa
        untuk memberi tahu ada yang sudah menunggu terlalu lama — tanpanya,
        petugas yang sedang fokus melayani tidak akan pernah melihatnya.
        """
        judul = f"Menunggu Dilayani ({jumlah})"
        terlambat = sum(1 for m in lama_menit if m >= TUNGGU_LAMA_MENIT)
        if terlambat:
            judul += f" · {terlambat} lama"
        self.tab_kanan.setTabText(0, judul)

    def _gayai_sel(
        self, sel: QTableWidgetItem, *, baris: int, kolom: int, menit: int
    ) -> None:
        """
        Beri warna satu sel daftar tunggu.

        Dua hal yang ditandai: baris paling depan — nomor yang akan terpanggil
        bila PANGGIL BERIKUTNYA ditekan sekarang — dan lama menunggu yang
        sudah melewati ambang. Keduanya pertanyaan yang dijawab petugas
        berkali-kali sehari, dan keduanya kini terjawab tanpa membaca.
        """
        if baris == 0:
            sel.setBackground(QBrush(QColor(PRIMARY_SOFT)))
            huruf = QFont()
            huruf.setBold(True)
            sel.setFont(huruf)

        if kolom == 3:
            if menit >= TUNGGU_SANGAT_LAMA_MENIT:
                sel.setForeground(QBrush(QColor(DANGER)))
            elif menit >= TUNGGU_LAMA_MENIT:
                sel.setForeground(QBrush(QColor(WARNING)))
            else:
                sel.setForeground(QBrush(QColor(TEXT_MUTED)))
        elif kolom == 0:
            sel.setForeground(QBrush(QColor(TEXT)))

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

    def buka_ruang_kerja(self) -> None:
        """
        Pindah ke tab Pengaduan & Catatan dan taruh kursor di kotaknya.

        Bukan lagi membuka dialog — panel ini sudah selalu ada di panel
        kanan, hanya belum tentu sedang terlihat bila petugas sebelumnya
        membuka tab Menunggu Dilayani sendiri. F9 karena itu sekadar
        berpindah tab, bukan menyalakan sesuatu yang sebelumnya mati.
        """
        if self.panel_pengaduan is None or self.antrian is None:
            return
        self.tab_kanan.setCurrentWidget(self.panel_pengaduan)
        kotak = (
            self.panel_pengaduan.isian_catatan
            if self.panel_pengaduan.ada_pengaduan
            else self.panel_pengaduan.isian_deskripsi
        )
        kotak.setFocus()

    def selesaikan(self) -> None:
        """
        Tutup pelayanan, setelah ruang kerjanya ikut tersimpan.

        Pengaduan disimpan LEBIH DAHULU, dan kegagalannya membatalkan
        seluruh tindakan. Begitu antrian selesai, kartunya berganti kosong
        dan isian ruang kerja ikut terhapus — pengaduan yang gagal
        tersimpan pada detik itu hilang tanpa dapat diketik ulang, karena
        yang menceritakannya sudah berdiri meninggalkan meja.
        """
        if self.antrian is None or not self.aksi["selesai"].isEnabled():
            return
        if (
            self.panel_pengaduan is not None
            and self.panel_pengaduan.ada_isian
            and not self.panel_pengaduan.simpan()
        ):
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
