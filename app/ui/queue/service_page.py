"""Panel pelayanan petugas CRO."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import clock
from app.models import QueueStatus
from app.models.enums import LABEL_PRIORITAS, AlasanPrioritas
from app.services.auth_service import AuthService
from app.services.dashboard_service import DashboardService
from app.services.master_data_service import MasterDataService
from app.services.note_service import NoteService
from app.services.queue_service import QueueInfo, QueueService
from app.services.settings_service import SettingsService
from app.services.survey_service import SurveyService
from app.ui.common import (
    PekerjaLatar,
    jalankan_aman,
    judul,
    lepaskan_pekerja,
    konfirmasi,
    setel_variant,
    tombol,
    tampilkan_error,
    tampilkan_peringatan,
)
from app.ui.efek import pasang_efek
from app.ui.queue.note_panel import NotePanel
from app.services.urutan_prioritas import MODE_BIASA, MODE_OTOMATIS, MODE_PRIORITAS
from app.ui.queue.kartu_berikutnya import KartuBerikutnya
from app.ui.queue.papan_tunggu import PapanTunggu
from app.ui.queue.pelapor_form import PelaporForm
from app.ui.style import (
    BORDER,
    DANGER,
    DANGER_SOFT,
    FONT_SIZE_HUGE,
    FONT_SIZE_LARGE,
    FONT_SIZE_SMALL,
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

#: Data dari kios dan komputer lain harus segera terlihat, tetapi tidak perlu
#: membebani PostgreSQL setiap detik seperti penghitung durasi lokal.
SELANG_DATA_MS = 5_000

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


def _beri_bayangan(widget: QWidget) -> None:
    """Beri kedalaman tipis pada kartu utama tanpa membuatnya tampak melayang."""
    efek = QGraphicsDropShadowEffect(widget)
    efek.setBlurRadius(24)
    efek.setOffset(0, 4)
    efek.setColor(QColor(15, 23, 42, 28))
    pasang_efek(widget, efek)


#: Judul tab ruang kerja pengaduan di panel kanan (tab pertama).
# "&&": satu "&" dibaca Qt sebagai tanda mnemonik dan hilang dari label.
JUDUL_TAB_PENGADUAN = "Pengaduan && Catatan"


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
        #: (id, status) nomor yang dipegang pada penyegaran sebelumnya.
        #: Tab Pengaduan dibuka pada PERISTIWA — nomor dipanggil atau mulai
        #: dilayani — bukan pada setiap penyegaran.
        self._kunci_antrian_sebelumnya: tuple | None = None
        #: Dipakai untuk memilih loket petugas ini sendiri saat halaman
        #: dibuka, dan mengingat kepindahannya bila ia berganti meja.
        self.auth = auth
        self._loket_terkonfirmasi: int | None = None
        self._mode_ganti_loket = False
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
        self._otomatis = otomatis
        self._pekerja_data: PekerjaLatar | None = None
        self._pekerja_aksi: PekerjaLatar | None = None
        self._data_ditunda = False
        self._sedang_sibuk = False
        self._menunggu_snapshot_aksi = False
        self._sinkron_gagal = False

        self._bangun_tampilan()
        self._pasang_pintasan()

        # Penghitung lama pelayanan. Dipisahkan dari penyegaran data supaya
        # angka detiknya berjalan tanpa membebani database sedetik sekali.
        self.pewaktu_durasi = QTimer(self)
        self.pewaktu_durasi.setInterval(SELANG_DURASI_MS)
        self.pewaktu_durasi.timeout.connect(self._perbarui_durasi)
        self.pewaktu_data = QTimer(self)
        self.pewaktu_data.setInterval(SELANG_DATA_MS)
        self.pewaktu_data.timeout.connect(self._segarkan_otomatis)

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
        susunan.setContentsMargins(20, 12, 20, 12)
        susunan.setSpacing(10)

        self.label_sinkron = QLabel("● Menyiapkan data…")
        self.label_sinkron.setObjectName("statusSinkron")
        self.label_sinkron.setStyleSheet(
            f"background: {SURFACE_ALT}; color: {TEXT_MUTED};"
            f" border-radius: 10px; padding: 4px 10px;"
            f" font-size: {FONT_SIZE_SMALL}px; font-weight: 650;"
        )

        susunan.addWidget(self._bangun_kepala())

        isi = QHBoxLayout()
        isi.setSpacing(18)
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
            "QFrame#panelKepala {"
            " background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            " stop:0 #FFFFFF, stop:0.62 #FFFFFF, stop:1 #EEF2FF);"
            f" border: 1px solid {BORDER}; border-left: 5px solid {PRIMARY};"
            f" border-radius: {RADIUS}px; }}"
        )

        susunan = QHBoxLayout(kepala)
        susunan.setContentsMargins(20, 13, 18, 13)
        susunan.setSpacing(16)

        teks = QVBoxLayout()
        teks.setSpacing(5)
        teks.addWidget(judul("Pelayanan Antrian"))
        teks.addWidget(self.label_sinkron, alignment=Qt.AlignmentFlag.AlignLeft)
        susunan.addLayout(teks)
        susunan.addStretch()

        self.pilih_loket = QComboBox()
        self.pilih_loket.setMinimumWidth(170)
        self.pilih_loket.currentIndexChanged.connect(self.loket_diganti)
        self.tombol_ganti_loket = tombol("Ganti Loket", variant="secondary")
        self.tombol_ganti_loket.setAutoDefault(False)
        self.tombol_ganti_loket.clicked.connect(self.ganti_loket)
        baris_loket = QWidget()
        isi_loket = QHBoxLayout(baris_loket)
        isi_loket.setContentsMargins(0, 0, 0, 0)
        isi_loket.setSpacing(6)
        isi_loket.addWidget(self.pilih_loket)
        isi_loket.addWidget(self.tombol_ganti_loket)
        susunan.addLayout(self._berlabel("LOKET", baris_loket))

        self.pilih_kategori = QComboBox()
        self.pilih_kategori.setMinimumWidth(200)
        susunan.addLayout(self._berlabel("JENIS LAYANAN", self.pilih_kategori))

        # Pilihan sekali pakai untuk panggilan berikutnya: otomatis mengikuti
        # rasio prioritas; petugas dapat langsung memilih yang prioritas atau
        # yang biasa. Kembali ke otomatis sesudah dipakai.
        self.pilih_urutan = QComboBox()
        self.pilih_urutan.addItem("Otomatis", MODE_OTOMATIS)
        self.pilih_urutan.addItem("Prioritas dulu", MODE_PRIORITAS)
        self.pilih_urutan.addItem("Biasa dulu", MODE_BIASA)
        self.pilih_urutan.setMinimumWidth(130)
        self.pilih_urutan.setToolTip(
            "Urutan panggil untuk nomor berikutnya. Otomatis mengikuti rasio "
            "prioritas di Pengaturan."
        )
        susunan.addLayout(self._berlabel("URUTAN PANGGIL", self.pilih_urutan))

        self.tombol_istirahat = tombol("Mulai Istirahat")
        # Padding bawaan tombol (9 px) membuatnya 42 px, dua piksel lebih
        # tinggi daripada kotak pilihan di sebelahnya.
        self.tombol_istirahat.setStyleSheet(
            "padding-top: 8px; padding-bottom: 8px;"
        )
        self.tombol_istirahat.clicked.connect(self.alihkan_istirahat)
        # Keterangan kosong (spasi tak terputus) menyamakan tinggi kolom ini
        # dengan kolom LOKET dan JENIS LAYANAN, sehingga tombol sejajar
        # dengan kotak pilihannya, bukan dengan keterangannya.
        susunan.addLayout(self._berlabel(" ", self.tombol_istirahat))

        _beri_bayangan(kepala)
        return kepala

    @staticmethod
    def _berlabel(kapsi: str, kontrol: QWidget) -> QVBoxLayout:
        """Satu kontrol beserta keterangan kecil di atasnya."""
        kotak = QVBoxLayout()
        kotak.setSpacing(4)
        if kapsi:
            label = QLabel(kapsi)
            label.setProperty("kapsi", "true")
            kotak.addWidget(label)
        kotak.addWidget(kontrol)
        return kotak

    def _bangun_kolom_kerja(self) -> QVBoxLayout:
        kolom = QVBoxLayout()
        kolom.setSpacing(8)
        kolom.addWidget(self._bangun_panel_antrian())
        kolom.addWidget(self._bangun_tombol_aksi())

        self.pelapor: PelaporForm | None = None
        if self.note is not None:
            # Identitas ditulis sambil BERTANYA kepada orang di depan meja,
            # sedangkan keluhannya ditulis sambil MENDENGARKAN. Isian pendek
            # ini karena itu tetap di layar; kotak keluhan yang panjang
            # mendapat tempatnya sendiri di panel kanan — lihat
            # `_bangun_panel_kanan`.
            self.pelapor = PelaporForm()
            kolom.addWidget(self.pelapor)

        # Papan tunggu mengisi sisa tinggi kolom kiri: apa yang dilihat
        # pengunjung di layar antrian, tanpa berpindah tab.
        # (Papan tunggu pindah ke tab Menunggu Dilayani di panel kanan.)
        # Kartu ini hanya memakai sisa tinggi kolom dan tidak tampak bila
        # sisanya terlalu kecil, jadi tidak pernah membuat halaman bergulir.
        self.kartu_berikutnya = KartuBerikutnya(TUNGGU_LAMA_MENIT)
        kolom.addWidget(self.kartu_berikutnya, stretch=1)
        # Baris survey tidak lagi di sini: ia pindah ke bawah panel kanan,
        # yang punya sisa tinggi, supaya kolom kerja muat tanpa gulir.
        self._baris_survey = self._bangun_baris_survey()
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
        panel.setMinimumHeight(120)
        self.panel_antrian = panel

        # Kiri: keadaan dan nomor. Kanan: tombol memanggil, tepat di tempat
        # kalimat "Loket siap melayani" dibaca, dan tidak menambah tinggi.
        utama = QHBoxLayout(panel)
        utama.setContentsMargins(22, 14, 22, 14)
        utama.setSpacing(18)
        susunan = QVBoxLayout()
        susunan.setSpacing(4)
        utama.addLayout(susunan, stretch=1)

        # Dibuat di sini, bukan di panel tindakan: kamus `aksi` dimulai di
        # kartu ini dan dilengkapi `_bangun_tombol_aksi`.
        self.aksi: dict[str, object] = {}
        kolom_tombol = QVBoxLayout()
        kolom_tombol.setSpacing(8)
        self.tombol_panggil = tombol("Panggil Berikutnya  ·  F2", variant="primary")
        self.tombol_panggil.setObjectName("tombolUtamaPelayanan")
        self.tombol_panggil.setMinimumHeight(52)
        self.tombol_panggil.setStyleSheet(
            f"font-size: {FONT_SIZE_LARGE}px; letter-spacing: 0.4px;"
        )
        self.tombol_panggil.clicked.connect(self.panggil_berikutnya)
        kolom_tombol.addWidget(self.tombol_panggil)
        panggil_ulang = tombol("Panggil Ulang  ·  F3", variant="secondary")
        panggil_ulang.setMinimumHeight(38)
        panggil_ulang.clicked.connect(self.panggil_ulang)
        self.aksi["panggil_ulang"] = panggil_ulang
        kolom_tombol.addWidget(panggil_ulang)
        # Lebar tetap: tombol tidak boleh bergeser ketika status berganti.
        pembungkus_tombol = QWidget()
        pembungkus_tombol.setFixedWidth(250)
        pembungkus_tombol.setLayout(kolom_tombol)
        kolom_tombol.setContentsMargins(0, 0, 0, 0)
        utama.addWidget(pembungkus_tombol, alignment=Qt.AlignmentFlag.AlignVCenter)

        baris_atas = QHBoxLayout()
        self.label_status = QLabel("")
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        baris_atas.addWidget(self.label_status)

        # Nomor prioritas ditandai di sini, di baris yang sudah ada, supaya
        # kartu ini tidak bertambah tinggi. Menu "Ubah" memperinci alasannya
        # atau mencabut prioritas yang dipilih pengunjung di anjungan.
        self.pil_prioritas = QLabel("")
        self.pil_prioritas.setStyleSheet(
            f"background: {WARNING_SOFT}; color: {WARNING}; font-weight: 700;"
            " border-radius: 10px; padding: 3px 10px;"
        )
        self.pil_prioritas.setVisible(False)
        baris_atas.addWidget(self.pil_prioritas)
        self.tombol_ubah_prioritas = QPushButton("Ubah ▾")
        self.tombol_ubah_prioritas.setFlat(True)
        self.tombol_ubah_prioritas.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tombol_ubah_prioritas.setMenu(self._menu_prioritas(cabut=True))
        self.tombol_ubah_prioritas.setVisible(False)
        baris_atas.addWidget(self.tombol_ubah_prioritas)
        baris_atas.addStretch()

        self.label_durasi = QLabel("")
        self.label_durasi.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_LARGE}px; font-weight: 700;"
        )
        baris_atas.addWidget(self.label_durasi)
        susunan.addLayout(baris_atas)

        susunan.addStretch()

        self.label_idle_judul = QLabel("Loket siap melayani")
        self.label_idle_judul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_idle_judul.setStyleSheet(
            f"color: {PRIMARY_DARK}; font-size: {FONT_SIZE_HUGE}px; font-weight: 750;"
        )
        susunan.addWidget(self.label_idle_judul)

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
        _beri_bayangan(panel)
        return panel

    def _bangun_tombol_aksi(self) -> QWidget:
        """
        Tombol tindakan, disusun menurun dari yang paling sering ditekan.

        PANGGIL BERIKUTNYA mendapat satu barisnya sendiri karena itulah
        tombol yang ditekan ratusan kali sehari; sisanya berkelompok tiga
        kolom. Dua tindakan yang menutup antrian tanpa melayani dipisahkan
        ke kelompok terakhir supaya tidak tertekan karena refleks.
        """
        panel = QFrame()
        panel.setObjectName("panelAksi")
        panel.setStyleSheet(
            f"QFrame#panelAksi {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )

        kotak = QVBoxLayout(panel)
        kotak.setContentsMargins(12, 10, 12, 12)
        kotak.setSpacing(8)

        kepala = QHBoxLayout()
        kepala.setSpacing(8)
        kapsi = QLabel("TINDAKAN PELAYANAN")
        kapsi.setProperty("kapsi", "true")
        kepala.addWidget(kapsi)
        kepala.addStretch()
        self.label_petunjuk_aksi = QLabel("Loket siap menerima nomor berikutnya")
        self.label_petunjuk_aksi.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )
        kepala.addWidget(self.label_petunjuk_aksi)
        kotak.addLayout(kepala)

        def buat_aksi(kunci: str, teks: str, handler) -> object:
            btn = tombol(teks, variant="secondary")
            btn.setMinimumHeight(38)
            btn.clicked.connect(handler)
            self.aksi[kunci] = btn
            return btn

        # Panggil Berikutnya dan Panggil Ulang ada di kartu loket di atas.
        baris_utama = QHBoxLayout()
        baris_utama.setSpacing(8)
        for kunci, teks, handler in (
            ("mulai_layani", "Mulai Melayani  ·  F4", self.mulai_melayani),
            ("selesai", "Selesai  ·  F8", self.selesaikan),
            ("tunda", "Tunda", self.tunda),
            ("lanjutkan", "Lanjutkan", self.lanjutkan),
        ):
            baris_utama.addWidget(buat_aksi(kunci, teks, handler), stretch=1)
        kotak.addLayout(baris_utama)

        baris_tutup = QHBoxLayout()
        baris_tutup.setSpacing(8)
        lewati = buat_aksi("lewati", "Lewati Sementara", self.lewati_sementara)
        baris_tutup.addWidget(lewati, stretch=1)
        for kunci, teks, handler in (
            ("tidak_hadir", "Tidak Hadir", self.tidak_hadir),
            ("batal", "Batalkan Antrian", self.batalkan),
        ):
            btn = tombol(teks, variant="danger")
            btn.setMinimumHeight(38)
            btn.clicked.connect(handler)
            baris_tutup.addWidget(btn, stretch=1)
            self.aksi[kunci] = btn
        kotak.addLayout(baris_tutup)

        _beri_bayangan(panel)
        return panel

    def _bangun_baris_survey(self) -> QWidget:
        """
        Permintaan pengisian survey, terpisah dari tombol alur pelayanan.

        Sengaja tidak muncul sendiri setelah pelayanan selesai. Petugaslah
        yang tahu apakah pengunjung masih di depan meja dan bersedia menilai;
        dialog yang menyembul sendiri justru menghambat antrian berikutnya.
        """
        panel = QFrame()
        panel.setObjectName("panelSurvey")
        self.panel_survey = panel
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

        self.tombol_survey = tombol("Minta Survey", variant="secondary")
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

        # Pengaduan & Catatan selalu tab pertama: itu tempat petugas
        # bekerja begitu seseorang dipanggil, jadi letaknya tetap di awal.
        self.panel_pengaduan: NotePanel | None = None
        if self.note is not None and self.pelapor is not None:
            self.panel_pengaduan = NotePanel(self.note, self.pelapor)
            self.tab_kanan.addTab(self.panel_pengaduan, JUDUL_TAB_PENGADUAN)
            # Penanda isian yang belum disimpan, supaya tidak terlewat
            # ketika petugas berpindah ke tab lain.
            self.panel_pengaduan.isian_deskripsi.textChanged.connect(
                self._perbarui_judul_pengaduan
            )
            self.panel_pengaduan.isian_catatan.textChanged.connect(
                self._perbarui_judul_pengaduan
            )
            self._pewaktu_judul_pengaduan = QTimer(self)
            self._pewaktu_judul_pengaduan.setInterval(1000)
            self._pewaktu_judul_pengaduan.timeout.connect(
                self._perbarui_judul_pengaduan
            )
            self._pewaktu_judul_pengaduan.start()

        self.tab_kanan.addTab(self._bangun_panel_menunggu(), "Menunggu Dilayani")
        self.tab_kanan.addTab(self._bangun_panel_dilewati(), "Dilewati (0)")

        _beri_bayangan(self.tab_kanan)
        kanan = QWidget()
        susunan = QVBoxLayout(kanan)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(10)
        susunan.addWidget(self.tab_kanan, stretch=1)
        susunan.addWidget(self._baris_survey)
        return kanan

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

        # Ringkasan per layanan yang sedang ada antriannya, di atas daftar
        # nomor: mengisi sisa tinggi panel dan memberi gambaran sekilas.
        self.papan_tunggu = PapanTunggu(
            TUNGGU_LAMA_MENIT, tinggi_menurut_isi=True
        )
        # Klik kartu layanan menyaring daftar nomor di bawahnya.
        self.papan_tunggu.layananDipilih.connect(self._saring_menunggu)
        self._menunggu_penuh: list[QueueInfo] = []
        self._sedang_segar = False
        susunan.addWidget(self.papan_tunggu)

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

        # Menandai pengunjung yang menunggu (mis. lansia yang terlanjur
        # mengambil nomor biasa). Bekerja pada baris yang dipilih.
        baris_prioritas = QHBoxLayout()
        baris_prioritas.setSpacing(8)
        self.tombol_tandai_prioritas = QPushButton("★ Tandai prioritas ▾")
        self.tombol_tandai_prioritas.setMenu(self._menu_prioritas(cabut=False))
        baris_prioritas.addWidget(self.tombol_tandai_prioritas)
        self.tombol_cabut_prioritas = QPushButton("Cabut prioritas")
        self.tombol_cabut_prioritas.clicked.connect(
            lambda: self._ubah_prioritas_terpilih(None)
        )
        baris_prioritas.addWidget(self.tombol_cabut_prioritas)
        baris_prioritas.addStretch()
        self.baris_prioritas = QWidget()
        self.baris_prioritas.setLayout(baris_prioritas)
        baris_prioritas.setContentsMargins(0, 0, 0, 0)
        susunan.addWidget(self.baris_prioritas)
        self._tampil_menunggu: list[QueueInfo] = []
        self.tabel.itemSelectionChanged.connect(self._perbarui_tombol_prioritas)
        self._perbarui_tombol_prioritas()

        self.panel_kosong = QFrame()
        self.panel_kosong.setObjectName("panelKosongMenunggu")
        self.panel_kosong.setStyleSheet(
            "QFrame#panelKosongMenunggu { background: #F8FAFF;"
            " border: 1px solid #E0E7FF; border-radius: 16px; }"
        )
        kosong = QVBoxLayout(self.panel_kosong)
        kosong.setContentsMargins(24, 24, 24, 24)
        kosong.setSpacing(10)
        kosong.addStretch()

        ikon_kosong = QLabel("✓")
        ikon_kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ikon_kosong.setFixedSize(64, 64)
        ikon_kosong.setStyleSheet(
            f"background: {PRIMARY_SOFT}; color: {PRIMARY_DARK};"
            " border: 1px solid #C7D2FE; border-radius: 32px;"
            " font-size: 28px; font-weight: 800;"
        )
        kosong.addWidget(ikon_kosong, alignment=Qt.AlignmentFlag.AlignCenter)

        judul_kosong = QLabel("Semua antrian tertangani")
        judul_kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
        judul_kosong.setStyleSheet(
            f"color: {TEXT}; font-size: {FONT_SIZE_LARGE}px; font-weight: 750;"
        )
        kosong.addWidget(judul_kosong)

        self.label_kosong = QLabel(
            "Belum ada nomor yang menunggu.\nDaftar akan diperbarui secara otomatis."
        )
        self.label_kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_kosong.setWordWrap(True)
        self.label_kosong.setStyleSheet(f"color: {TEXT_MUTED};")
        kosong.addWidget(self.label_kosong)
        kosong.addStretch()

        self.panel_kosong.setVisible(False)
        susunan.addWidget(self.panel_kosong, stretch=1)

        return panel

    def _bangun_panel_dilewati(self) -> QWidget:
        """Daftar nomor yang belum batal, tetapi sedang tidak memegang loket."""
        panel = QFrame()
        panel.setObjectName("panelDilewati")
        panel.setStyleSheet(
            f"QFrame#panelDilewati {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )
        self.panel_dilewati = panel

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(16, 14, 16, 14)
        susunan.setSpacing(10)

        petunjuk = QLabel(
            "Pilih nomor ketika pengunjung sudah kembali. Nomor akan "
            "dipanggil ke loket yang sedang Anda gunakan."
        )
        petunjuk.setWordWrap(True)
        petunjuk.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(petunjuk)

        self.tabel_dilewati = QTableWidget(0, 4)
        self.tabel_dilewati.setHorizontalHeaderLabels(
            ["Nomor", "Layanan", "Panggilan", "Terakhir"]
        )
        self.tabel_dilewati.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tabel_dilewati.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tabel_dilewati.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tabel_dilewati.setShowGrid(False)
        self.tabel_dilewati.setWordWrap(False)
        self.tabel_dilewati.verticalHeader().setVisible(False)
        self.tabel_dilewati.verticalHeader().setDefaultSectionSize(40)
        kepala = self.tabel_dilewati.horizontalHeader()
        kepala.setHighlightSections(False)
        for kolom, mode in (
            (0, QHeaderView.ResizeMode.ResizeToContents),
            (1, QHeaderView.ResizeMode.Stretch),
            (2, QHeaderView.ResizeMode.ResizeToContents),
            (3, QHeaderView.ResizeMode.ResizeToContents),
        ):
            kepala.setSectionResizeMode(kolom, mode)
        self.tabel_dilewati.itemSelectionChanged.connect(
            self._perbarui_tombol_panggil_kembali
        )
        susunan.addWidget(self.tabel_dilewati, stretch=1)

        self.label_dilewati_kosong = QLabel("Belum ada nomor yang dilewati.")
        self.label_dilewati_kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_dilewati_kosong.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_dilewati_kosong, stretch=1)

        self.tombol_panggil_kembali = tombol(
            "Panggil Kembali", variant="secondary"
        )
        self.tombol_panggil_kembali.setMinimumHeight(42)
        self.tombol_panggil_kembali.setEnabled(False)
        self.tombol_panggil_kembali.clicked.connect(
            self.panggil_kembali_dilewati
        )
        susunan.addWidget(self.tombol_panggil_kembali)

        # Pengunjung yang dilewati dan tidak pernah kembali harus bisa
        # ditutup sebagai Tidak Hadir, bukan menunggu Tutup Hari yang akan
        # mencatatnya sebagai Batal.
        baris_tutup = QHBoxLayout()
        baris_tutup.setSpacing(8)
        self.tombol_dilewati_tidak_hadir = tombol("Tidak Hadir", variant="danger")
        self.tombol_dilewati_tidak_hadir.clicked.connect(
            self.tidak_hadir_dilewati
        )
        self.tombol_dilewati_batal = tombol("Batalkan", variant="danger")
        self.tombol_dilewati_batal.clicked.connect(self.batalkan_dilewati)
        for btn in (self.tombol_dilewati_tidak_hadir, self.tombol_dilewati_batal):
            btn.setMinimumHeight(38)
            btn.setEnabled(False)
            baris_tutup.addWidget(btn, stretch=1)
        susunan.addLayout(baris_tutup)
        self._dilewati_by_id: dict[int, QueueInfo] = {}
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
        if self.auth is not None:
            self.pilih_loket.addItem("Pilih loket…", None)
        for loket in data:
            self.pilih_loket.addItem(loket.name, loket.id)

        bawaan = self.auth.current_session.default_counter_id if self.auth else None
        self._loket_terkonfirmasi = None
        if bawaan is not None:
            baris = self.pilih_loket.findData(bawaan)
            if baris >= 0:
                self.pilih_loket.setCurrentIndex(baris)
                self._loket_terkonfirmasi = bawaan
        elif self.auth is None and self.pilih_loket.count():
            # Jalur kompatibilitas untuk pemakaian panel tanpa AuthService,
            # terutama test widget dan pratinjau pengembang.
            self._loket_terkonfirmasi = self.loket_id
        self.pilih_loket.blockSignals(False)
        self._mode_ganti_loket = False
        self._perbarui_kontrol_loket()
        self._perbarui_tombol_istirahat()
        self._perbarui_tombol()
        self.muat_ulang()

    def loket_diganti(self) -> None:
        """
        Konfirmasi loket baru, ingat pilihannya, lalu muat ulang.

        Combo dikunci setelah berhasil supaya roda mouse atau satu klik yang
        meleset tidak memindahkan petugas diam-diam. Akun yang belum punya
        bawaan wajib memilih satu kali; selanjutnya perpindahan dibuka lewat
        tombol Ganti Loket.
        """
        if self.auth is None:
            self._loket_terkonfirmasi = self.loket_id
            self.muat_ulang()
            return

        tujuan = self.loket_id
        semula = self._loket_terkonfirmasi
        if tujuan is None or tujuan == semula:
            return

        nama_tujuan = self.pilih_loket.currentText()
        if semula is None:
            pertanyaan = (
                f"Gunakan {nama_tujuan} untuk sesi ini?\n\n"
                "Pilihan ini akan menjadi loket bawaan akun Anda."
            )
        else:
            baris_semula = self.pilih_loket.findData(semula)
            nama_semula = (
                self.pilih_loket.itemText(baris_semula)
                if baris_semula >= 0
                else "loket sebelumnya"
            )
            pertanyaan = f"Pindah dari {nama_semula} ke {nama_tujuan}?"

        if not konfirmasi(self, pertanyaan, "Konfirmasi Loket"):
            self._pulihkan_pilihan_loket(semula)
            return

        berhasil, _ = jalankan_aman(
            self,
            lambda: self.auth.pindah_loket(tujuan),
            "Gagal mengganti loket",
        )
        if not berhasil:
            self._pulihkan_pilihan_loket(semula)
            return

        self._loket_terkonfirmasi = tujuan
        self._mode_ganti_loket = False
        self._perbarui_kontrol_loket()
        self._perbarui_tombol_istirahat()
        self._perbarui_tombol()
        self.muat_ulang()

    def ganti_loket(self) -> None:
        """Buka atau batalkan pemilihan loket lain."""
        if self._mode_ganti_loket:
            self._pulihkan_pilihan_loket(self._loket_terkonfirmasi)
            return
        if self.antrian is not None and not self._dialihkan_ke_petugas_lain():
            tampilkan_peringatan(
                self,
                f"Selesaikan antrian {self.antrian.queue_number} sebelum "
                "berpindah loket.",
                "Loket masih melayani",
            )
            return
        self._mode_ganti_loket = True
        self._perbarui_kontrol_loket()
        self._perbarui_tombol_istirahat()
        self._perbarui_tombol()
        self.pilih_loket.setFocus()

    def _pulihkan_pilihan_loket(self, counter_id: int | None) -> None:
        self.pilih_loket.blockSignals(True)
        baris = self.pilih_loket.findData(counter_id)
        self.pilih_loket.setCurrentIndex(max(baris, 0))
        self.pilih_loket.blockSignals(False)
        self._mode_ganti_loket = False
        self._perbarui_kontrol_loket()
        self._perbarui_tombol_istirahat()
        self._perbarui_tombol()

    def _perbarui_kontrol_loket(self, *, diblokir: bool = False) -> None:
        tanpa_bawaan = self._loket_terkonfirmasi is None
        boleh_memilih = (
            not diblokir
            and (
                self.auth is None
                or tanpa_bawaan
                or self._mode_ganti_loket
            )
        )
        self.pilih_loket.setEnabled(boleh_memilih)
        self.tombol_ganti_loket.setVisible(
            self.auth is not None and not tanpa_bawaan
        )
        self.tombol_ganti_loket.setEnabled(not diblokir)
        self.tombol_ganti_loket.setText(
            "Batal" if self._mode_ganti_loket else "Ganti Loket"
        )

    def muat_kategori(self, data=None) -> None:
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
        if data is None:
            berhasil, data = jalankan_aman(
                self,
                lambda: self.master.list_categories(only_active=True, only_leaf=True),
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
        if self.loket_id is None and self.auth is None:
            return

        # Konstruktor dan test yang tidak menampilkan widget tetap sinkron.
        # Pada jendela sungguhan seluruh I/O database berjalan di worker.
        if self.isVisible():
            self._mulai_muat_latar()
            return

        try:
            snapshot = self._ambil_snapshot(self.loket_id)
        except Exception as exc:  # satu kegagalan, satu dialog; keadaan lama dipertahankan
            tampilkan_error(self, exc, "Gagal memuat pelayanan")
            self._tandai_gagal_sinkron()
            return
        self._terapkan_snapshot(snapshot)

    def _ambil_snapshot(self, loket_id: int | None):
        """Ambil seluruh keadaan loket; jangan ubah widget dari thread ini."""
        diminta = loket_id
        if self.auth is not None:
            # Admin dapat mengubah loket akun atau mengalihkan pelayanan saat
            # halaman ini terbuka. Baca sumber kebenaran database di worker,
            # lalu pindahkan pilihan widget ketika hasil diterapkan.
            loket_id = self.auth.sinkronkan_loket().default_counter_id

        loket = self.master.get_counter(loket_id) if loket_id is not None else None
        antrian = (
            self.queue.current_for_counter(loket_id)
            if loket_id is not None
            else None
        )
        menunggu = self.queue.list_waiting()
        dilewati = self.queue.list_skipped()
        kategori = self.master.list_categories(only_active=True, only_leaf=True)
        # Ringkasan kerja hari ini untuk kartu "Berikutnya & hari ini".
        # Kegagalannya tidak boleh menggagalkan penyegaran pelayanan.
        ringkasan = None
        if self.auth is not None:
            try:
                ringkasan = DashboardService(self.auth).ringkasan_petugas()
            except Exception:  # noqa: BLE001 - hanya hiasan
                ringkasan = None
        return (
            diminta, loket_id, loket, antrian, menunggu, dilewati, kategori,
            ringkasan,
        )

    def _mulai_muat_latar(self) -> None:
        if self.loket_id is None and self.auth is None:
            return
        if self._pekerja_data is not None and self._pekerja_data.isRunning():
            self._data_ditunda = True
            return
        loket_id = self.loket_id
        pekerja = PekerjaLatar(lambda: self._ambil_snapshot(loket_id), self)
        pekerja.berhasil.connect(self._selesai_muat_latar)
        pekerja.gagal.connect(self._gagal_muat_latar)
        pekerja.finished.connect(self._bersihkan_pekerja_data)
        self._pekerja_data = pekerja
        pekerja.start()

    def _selesai_muat_latar(self, snapshot) -> None:
        # Petugas bisa mengganti loket ketika query lama masih berjalan.
        if snapshot[0] == self.loket_id:
            self._terapkan_snapshot(snapshot)

    def _gagal_muat_latar(self, exc: Exception) -> None:
        from app.core.logger import get_logger

        get_logger("ui.service").warning("Penyegaran pelayanan gagal: %s", exc)
        self._tandai_gagal_sinkron()

    def _bersihkan_pekerja_data(self) -> None:
        pekerja = self._pekerja_data
        self._pekerja_data = None
        if pekerja is not None:
            pekerja.deleteLater()
        if self._data_ditunda and self.isVisible():
            self._data_ditunda = False
            self._mulai_muat_latar()
            # Snapshot lama dapat selesai ketika aksi masih berjalan. Bila
            # aksi telah meminta snapshot baru, jangan buka kontrol pada
            # celah di antara keduanya.
            self._set_sibuk(
                self._pekerja_aksi is not None or self._menunggu_snapshot_aksi
            )
            return
        self._menunggu_snapshot_aksi = False
        self._set_sibuk(self._pekerja_aksi is not None)

    def _terapkan_snapshot(self, snapshot) -> None:
        _, loket_id, loket, antrian, menunggu, dilewati, kategori, ringkasan = (
            snapshot
        )
        if loket_id != self.loket_id:
            self.pilih_loket.blockSignals(True)
            indeks = self.pilih_loket.findData(loket_id)
            self.pilih_loket.setCurrentIndex(max(indeks, 0))
            self.pilih_loket.blockSignals(False)
            self._loket_terkonfirmasi = loket_id if indeks >= 0 else None
            self._mode_ganti_loket = False
            self._perbarui_kontrol_loket()

        self._sinkron_gagal = False
        self.label_sinkron.setText("● Tersinkron otomatis")
        self.label_sinkron.setStyleSheet(
            f"background: {SUCCESS_SOFT}; color: {SUCCESS};"
            f" border-radius: 10px; padding: 4px 10px;"
            f" font-size: {FONT_SIZE_SMALL}px; font-weight: 650;"
        )
        self.loket_istirahat = loket.on_break if loket is not None else False
        self._perbarui_tombol_istirahat()

        # Loket khusus boleh berubah daftarnya dari sesi admin sementara
        # halaman ini terbuka, jadi pilihan jenis layanan disusun ulang
        # begitu daftarnya tidak lagi sama.
        kategori_loket = loket.category_ids if loket is not None else ()
        if kategori_loket != self.loket_kategori:
            self.loket_kategori = kategori_loket
            self.muat_kategori(kategori)

        self.antrian = antrian
        self._tampilkan_antrian()
        # Papan lebih dulu: ia mengembalikan pilihan ke "Semua" bila
        # layanan yang dipilih sudah tidak punya antrian.
        # Tabel digambar sekali di bawah; sinyal pilihan yang dikembalikan
        # papan selama setel() tidak perlu menggambarnya dengan data lama.
        self._sedang_segar = True
        try:
            self.papan_tunggu.setel(menunggu, self.loket_kategori, clock.now())
        finally:
            self._sedang_segar = False
        self._isi_tabel(menunggu)
        self.kartu_berikutnya.setel(
            menunggu, self.loket_kategori, clock.now(), ringkasan
        )
        self._isi_tabel_dilewati(dilewati)

    def _tandai_gagal_sinkron(self) -> None:
        self._sinkron_gagal = True
        self.label_sinkron.setText(
            "● Tidak tersinkron — tampilan terakhir dipertahankan"
        )
        self.label_sinkron.setStyleSheet(
            f"background: {DANGER_SOFT}; color: {DANGER};"
            f" border-radius: 10px; padding: 4px 10px;"
            f" font-size: {FONT_SIZE_SMALL}px; font-weight: 700;"
        )
        self._set_sibuk(True)

    def _segarkan_otomatis(self) -> None:
        if self.isVisible() and self._pekerja_aksi is None:
            self._mulai_muat_latar()

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        super().showEvent(event)
        if self._otomatis:
            self.pewaktu_durasi.start()
            self.pewaktu_data.start()
        self.muat_ulang()

    def hideEvent(self, event) -> None:  # noqa: N802 - nama Qt
        self.pewaktu_durasi.stop()
        self.pewaktu_data.stop()
        super().hideEvent(event)

    def _tampilkan_antrian(self) -> None:
        if self.antrian is None:
            self.label_nomor.setText("—")
            self.label_nomor.setVisible(False)
            self.label_idle_judul.setVisible(True)
            self.label_idle_judul.setText(
                "Loket sedang istirahat"
                if self.loket_istirahat
                else "Loket siap melayani"
            )
            self.label_layanan.setText(
                "Akhiri istirahat untuk kembali menerima antrian"
                if self.loket_istirahat
                else "Tekan Panggil Berikutnya untuk memulai pelayanan"
            )
            self.label_status.setText(
                "Loket sedang istirahat" if self.loket_istirahat else "Siap memanggil"
            )
        else:
            self.label_idle_judul.setVisible(False)
            self.label_nomor.setVisible(True)
            self.label_nomor.setText(self.antrian.queue_number)
            self.label_layanan.setText(self.antrian.category_name)
            keterangan_panggilan = (
                f" · dipanggil {self.antrian.jumlah_panggilan}x"
                if self.antrian.jumlah_panggilan > 1
                else ""
            )
            self.label_status.setText(
                f"{self.antrian.label_status}{keterangan_panggilan}"
                + (
                    f" · dialihkan ke {self.antrian.served_by_name}"
                    if self._dialihkan_ke_petugas_lain()
                    else ""
                )
            )

        self._tampilkan_prioritas_aktif()
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
        self.label_idle_judul.setStyleSheet(
            f"color: {aksen}; font-size: {FONT_SIZE_HUGE}px; font-weight: 750;"
        )
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
            return PRIMARY, "#F8FAFF", PRIMARY_DARK, PRIMARY_SOFT
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
                "Lewati sementara atau tandai Tidak Hadir."
            )
            self.label_batas.setVisible(True)
        else:
            self.label_batas.setVisible(False)

    def _perbarui_tombol(self) -> None:
        if self._mode_ganti_loket or self._dialihkan_ke_petugas_lain():
            self.tombol_panggil.setEnabled(False)
            self.tombol_survey.setEnabled(False)
            for btn in self.aksi.values():
                btn.setEnabled(False)
            self._perbarui_tombol_panggil_kembali()
            self._sorot_aksi_utama()
            return

        tersedia = set(self.antrian.aksi_tersedia()) if self.antrian else set()

        # Loket yang masih menangani seseorang, atau sedang istirahat,
        # belum boleh memanggil berikutnya.
        self.tombol_panggil.setEnabled(
            self.antrian is None and self.loket_id is not None and not self.loket_istirahat
        )
        for kunci, btn in self.aksi.items():
            btn.setEnabled(kunci in tersedia)

        self._perbarui_tombol_survey()
        self._perbarui_tombol_panggil_kembali()
        self._sorot_aksi_utama()

    def _sorot_aksi_utama(self) -> None:
        """Tonjolkan tepat satu langkah berikutnya tanpa memindahkan tombol."""
        setel_variant(
            self.tombol_panggil,
            "primary" if self.tombol_panggil.isEnabled() else "",
        )

        for kunci in (
            "panggil_ulang",
            "mulai_layani",
            "selesai",
            "tunda",
            "lanjutkan",
            "lewati",
        ):
            setel_variant(self.aksi[kunci], "secondary")

        if self._dialihkan_ke_petugas_lain():
            self.label_petunjuk_aksi.setText("Pelayanan dialihkan ke petugas lain")
            return
        if self._mode_ganti_loket:
            self.label_petunjuk_aksi.setText("Selesaikan pemilihan loket")
            return
        if self.antrian is None:
            self.label_petunjuk_aksi.setText(
                "Loket sedang istirahat"
                if self.loket_istirahat
                else "Loket siap menerima nomor berikutnya"
            )
            return
        if self.antrian.status is QueueStatus.CALLED:
            if (
                self.antrian.melewati_batas_panggilan
                and self.aksi["lewati"].isEnabled()
            ):
                setel_variant(self.aksi["lewati"], "warning")
                self.label_petunjuk_aksi.setText(
                    "Pengunjung belum hadir setelah beberapa kali dipanggil"
                )
                return
            if self.aksi["mulai_layani"].isEnabled():
                setel_variant(self.aksi["mulai_layani"], "primary")
            self.label_petunjuk_aksi.setText("Mulai ketika pengunjung tiba di loket")
            return
        if self.antrian.status is QueueStatus.PAUSED:
            if self.aksi["lanjutkan"].isEnabled():
                setel_variant(self.aksi["lanjutkan"], "primary")
            self.label_petunjuk_aksi.setText("Pelayanan sedang ditunda")
            return
        if self.aksi["selesai"].isEnabled():
            setel_variant(self.aksi["selesai"], "success")
        self.label_petunjuk_aksi.setText("Pelayanan sedang berjalan")

    def _dialihkan_ke_petugas_lain(self) -> bool:
        if self.auth is None or self.antrian is None:
            return False
        sesi = self.auth.current_session
        if sesi is None:
            # Sesi sudah berakhir (logout/jendela ditutup) selagi muat latar
            # masih berjalan; tidak ada lagi yang dapat "dialihkan".
            return False
        return (
            self.antrian.served_by_id is not None
            and self.antrian.served_by_id != sesi.user_id
        )

    def _perbarui_tombol_istirahat(self) -> None:
        self.tombol_istirahat.setEnabled(
            self.loket_id is not None
            and not self._mode_ganti_loket
            and not self._dialihkan_ke_petugas_lain()
        )
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
            if self._dialihkan_ke_petugas_lain():
                self.panel_pengaduan.setEnabled(False)
                if self.pelapor is not None:
                    self.pelapor.set_aktif(False)

        aktif = self.antrian is not None
        kunci = (
            (self.antrian.id, self.antrian.status) if self.antrian is not None else None
        )
        # Nomor dipanggil, mulai dilayani, atau berganti: buka Pengaduan.
        # Selain itu pilihan tab petugas dibiarkan. Muatan pertama dengan
        # nomor yang sudah dipegang juga termasuk peristiwa (kunci awal None).
        peristiwa = kunci != self._kunci_antrian_sebelumnya
        self._kunci_antrian_sebelumnya = kunci
        berubah_aktif = aktif != self._kanan_aktif_sebelumnya
        self._kanan_aktif_sebelumnya = aktif
        if self.panel_pengaduan is not None:
            if aktif and peristiwa:
                self.tab_kanan.setCurrentWidget(self.panel_pengaduan)
            elif not aktif and berubah_aktif:
                self.tab_kanan.setCurrentWidget(self.panel_menunggu)
            self._perbarui_judul_pengaduan()

    def _perbarui_judul_pengaduan(self) -> None:
        """Beri tanda ● pada judul tab bila ada isian yang belum disimpan."""
        panel = self.panel_pengaduan
        if panel is None:
            return
        judul = JUDUL_TAB_PENGADUAN
        if self.antrian is not None and panel.berubah:
            judul += " ●"
        indeks = self.tab_kanan.indexOf(panel)
        if indeks >= 0 and self.tab_kanan.tabText(indeks) != judul:
            self.tab_kanan.setTabText(indeks, judul)

    def _perbarui_tombol_survey(self) -> None:
        aktif = self.settings.get_bool("survey.enabled", True)
        if not aktif:
            self.tombol_survey.setEnabled(False)
            self._gayai_panel_survey(False)
            self.label_survey.setText("Survey kepuasan sedang dinonaktifkan.")
            return

        if self.baru_selesai is None:
            self.tombol_survey.setEnabled(False)
            self._gayai_panel_survey(False)
            self.label_survey.setText(
                "Survey ditawarkan setelah sebuah pelayanan diselesaikan."
            )
            return

        self.tombol_survey.setEnabled(True)
        self._gayai_panel_survey(True)
        self.label_survey.setText(
            f"{self.baru_selesai.queue_number} belum dinilai pengunjung."
        )

    def _gayai_panel_survey(self, aktif: bool) -> None:
        """Sorot survey hanya ketika memang ada pengunjung yang dapat menilai."""
        if aktif:
            latar, garis, warna, variant = (
                PRIMARY_SOFT,
                "#C7D2FE",
                PRIMARY_DARK,
                "primary",
            )
        else:
            latar, garis, warna, variant = (
                SURFACE_ALT,
                BORDER,
                TEXT_MUTED,
                "secondary",
            )

        self.panel_survey.setStyleSheet(
            f"QFrame#panelSurvey {{ background: {latar};"
            f" border: 1px solid {garis}; border-radius: {RADIUS}px; }}"
        )
        self.label_survey.setStyleSheet(f"color: {warna};")
        setel_variant(self.tombol_survey, variant)

    def _isi_tabel(self, menunggu: list[QueueInfo]) -> None:
        from app.core import clock

        sekarang = clock.now()
        self._menunggu_penuh = list(menunggu)
        pilihan = self.papan_tunggu.pilihan
        tampil = (
            [q for q in menunggu if q.category_id == pilihan]
            if pilihan is not None
            else list(menunggu)
        )
        if pilihan is not None and tampil:
            self.label_jumlah.setText(f"{tampil[0].category_name} · {len(tampil)}")
        else:
            self.label_jumlah.setText(str(len(menunggu)))
        self.tabel.setVisible(bool(menunggu))
        self.panel_kosong.setVisible(not menunggu)

        self.tabel.setRowCount(len(tampil))
        self._tampil_menunggu = list(tampil)
        # Judul tab dan warnanya selalu menghitung SELURUH antrian, bukan
        # hanya yang sedang disaring.
        lama_menit = [
            int((sekarang - q.created_at).total_seconds() // 60) for q in menunggu
        ]
        for baris, q in enumerate(tampil):
            lama = int((sekarang - q.created_at).total_seconds() // 60)
            nilai = [
                f"★ {q.queue_number}" if q.prioritas else q.queue_number,
                q.category_name,
                q.created_at.strftime("%H:%M"),
                f"{lama} menit",
            ]
            for kolom, teks in enumerate(nilai):
                sel = QTableWidgetItem(teks)
                self._gayai_sel(sel, baris=baris, kolom=kolom, menit=lama)
                self.tabel.setItem(baris, kolom, sel)

        self._perbarui_judul_tab_menunggu(len(menunggu), lama_menit)

    # -----------------------------------------------------------------
    # Prioritas
    # -----------------------------------------------------------------

    def _menu_prioritas(self, *, cabut: bool) -> QMenu:
        """Menu pilihan alasan prioritas; `cabut` menambah "Cabut prioritas"."""
        menu = QMenu(self)
        for alasan in (
            AlasanPrioritas.LANSIA,
            AlasanPrioritas.DISABILITAS,
            AlasanPrioritas.IBU_HAMIL,
        ):
            aksi = menu.addAction(LABEL_PRIORITAS[alasan.value])
            aksi.triggered.connect(
                lambda _=False, a=alasan.value: self._ubah_prioritas_terpilih(
                    a, nomor_aktif=cabut
                )
            )
        if cabut:
            menu.addSeparator()
            aksi = menu.addAction("Cabut prioritas")
            aksi.triggered.connect(
                lambda _=False: self._ubah_prioritas_terpilih(None, nomor_aktif=True)
            )
        return menu

    def _tampilkan_prioritas_aktif(self) -> None:
        """Pita prioritas pada nomor yang sedang ditangani loket ini."""
        antrian = self.antrian
        ada = antrian is not None and antrian.prioritas is not None
        self.pil_prioritas.setVisible(ada)
        self.tombol_ubah_prioritas.setVisible(ada)
        if not ada:
            return
        teks = f"★ PRIORITAS · {antrian.label_prioritas}"
        if antrian.prioritas_mandiri:
            teks += " · dipilih pengunjung, mohon periksa"
        self.pil_prioritas.setText(teks)

    def _perbarui_tombol_prioritas(self) -> None:
        dipilih = self._nomor_menunggu_terpilih()
        self.tombol_tandai_prioritas.setEnabled(dipilih is not None)
        self.tombol_cabut_prioritas.setEnabled(
            dipilih is not None and dipilih.prioritas is not None
        )

    def _nomor_menunggu_terpilih(self) -> QueueInfo | None:
        baris = self.tabel.currentRow()
        if 0 <= baris < len(self._tampil_menunggu):
            return self._tampil_menunggu[baris]
        return None

    def _ubah_prioritas_terpilih(
        self, alasan: str | None, *, nomor_aktif: bool = False
    ) -> None:
        """Tandai atau cabut prioritas pada nomor aktif atau baris terpilih."""
        target = self.antrian if nomor_aktif else self._nomor_menunggu_terpilih()
        if target is None:
            return
        antrian_id = target.id
        self._jalankan(
            lambda: self.queue.ubah_prioritas(antrian_id, alasan),
            "Gagal mengubah prioritas",
        )

    def _saring_menunggu(self, _kategori_id=None) -> None:
        """Pilihan kartu berubah: gambar ulang daftar dari data terakhir."""
        if self._sedang_segar:
            return
        self._isi_tabel(self._menunggu_penuh)

    def _isi_tabel_dilewati(self, dilewati: list[QueueInfo]) -> None:
        """Perbarui tab dilewati sambil mempertahankan pilihan petugas."""
        terpilih = self._id_dilewati_terpilih()
        self._dilewati_by_id = {antrian.id: antrian for antrian in dilewati}
        # Pilihan dihapus dulu: bila nomor terpilih sudah hilang (misalnya
        # dipanggil kembali loket lain), baris aktif tidak boleh diam-diam
        # berpindah ke nomor yang tidak dipilih petugas.
        self.tabel_dilewati.blockSignals(True)
        self.tabel_dilewati.clearSelection()
        self.tabel_dilewati.setCurrentCell(-1, -1)
        self.tabel_dilewati.setRowCount(len(dilewati))
        for baris, antrian in enumerate(dilewati):
            nilai = [
                antrian.queue_number,
                antrian.category_name,
                f"{antrian.jumlah_panggilan}x",
                antrian.called_at.strftime("%H:%M") if antrian.called_at else "—",
            ]
            for kolom, teks in enumerate(nilai):
                sel = QTableWidgetItem(teks)
                if kolom == 0:
                    sel.setData(Qt.ItemDataRole.UserRole, antrian.id)
                    sel.setForeground(QBrush(QColor(WARNING)))
                    huruf = QFont()
                    huruf.setBold(True)
                    sel.setFont(huruf)
                self.tabel_dilewati.setItem(baris, kolom, sel)
            if antrian.id == terpilih:
                self.tabel_dilewati.selectRow(baris)
        self.tabel_dilewati.blockSignals(False)

        ada = bool(dilewati)
        self.tabel_dilewati.setVisible(ada)
        self.label_dilewati_kosong.setVisible(not ada)
        self.tab_kanan.setTabText(
            self.tab_kanan.indexOf(self.panel_dilewati), f"Dilewati ({len(dilewati)})"
        )
        self._perbarui_tombol_panggil_kembali()

    def _id_dilewati_terpilih(self) -> int | None:
        baris = self.tabel_dilewati.currentRow()
        if baris < 0:
            return None
        sel = self.tabel_dilewati.item(baris, 0)
        return sel.data(Qt.ItemDataRole.UserRole) if sel is not None else None

    def _perbarui_tombol_panggil_kembali(self) -> None:
        """Panggilan kembali hanya boleh dilakukan oleh loket yang kosong."""
        if getattr(self, "tombol_dilewati_batal", None) is None:
            return
        tombol_kembali = self.tombol_panggil_kembali
        tombol_kembali.setEnabled(
            self._id_dilewati_terpilih() is not None
            and self.antrian is None
            and self.loket_id is not None
            and not self.loket_istirahat
            and not self._mode_ganti_loket
            and not self._sedang_sibuk
            and not self._sinkron_gagal
        )
        # Menutup nomor dilewati tidak memakai loket, jadi tetap boleh
        # walau loket sedang memegang pengunjung lain atau beristirahat.
        bisa_tutup = (
            self._id_dilewati_terpilih() is not None
            and not self._sedang_sibuk
            and not self._sinkron_gagal
        )
        self.tombol_dilewati_tidak_hadir.setEnabled(bisa_tutup)
        self.tombol_dilewati_batal.setEnabled(bisa_tutup)

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
        self.tab_kanan.setTabText(self.tab_kanan.indexOf(self.panel_menunggu), judul)

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
        elif menit >= TUNGGU_SANGAT_LAMA_MENIT:
            sel.setBackground(QBrush(QColor(DANGER_SOFT)))
        elif menit >= TUNGGU_LAMA_MENIT:
            sel.setBackground(QBrush(QColor(WARNING_SOFT)))

        if baris == 0:
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

    def _set_sibuk(self, sibuk: bool) -> None:
        self._sedang_sibuk = sibuk
        diblokir = sibuk or self._sinkron_gagal
        self._perbarui_kontrol_loket(diblokir=diblokir)
        self.pilih_kategori.setEnabled(not diblokir)
        if diblokir:
            self.tombol_panggil.setEnabled(False)
            self.tombol_istirahat.setEnabled(False)
            self.tombol_survey.setEnabled(False)
            for btn in self.aksi.values():
                btn.setEnabled(False)
            self.tombol_panggil_kembali.setEnabled(False)
            self.tombol_dilewati_tidak_hadir.setEnabled(False)
            self.tombol_dilewati_batal.setEnabled(False)
            self.label_petunjuk_aksi.setText(
                "Tindakan dikunci sampai koneksi pulih"
                if self._sinkron_gagal
                else "Memproses perubahan…"
            )
            return
        self._perbarui_tombol_istirahat()
        self._perbarui_tombol()

    def _jalankan(self, aksi, judul_gagal: str = "Gagal", setelah=None) -> None:
        if self._sedang_sibuk:
            return
        if not self.isVisible():
            berhasil, hasil = jalankan_aman(self, aksi, judul_gagal)
            if berhasil:
                if setelah is not None:
                    setelah(hasil)
                self.muat_ulang()
            return

        self._set_sibuk(True)
        pekerja = PekerjaLatar(aksi, self)
        pekerja.berhasil.connect(
            lambda hasil: self._selesai_aksi(hasil, setelah)
        )
        pekerja.gagal.connect(lambda exc: self._gagal_aksi(exc, judul_gagal))
        pekerja.finished.connect(self._bersihkan_pekerja_aksi)
        self._pekerja_aksi = pekerja
        pekerja.start()

    def _selesai_aksi(self, hasil, setelah) -> None:
        if setelah is not None:
            setelah(hasil)
        self._menunggu_snapshot_aksi = True
        self._mulai_muat_latar()

    def _gagal_aksi(self, exc: Exception, judul: str) -> None:
        tampilkan_error(self, exc, judul)

    def _bersihkan_pekerja_aksi(self) -> None:
        pekerja = self._pekerja_aksi
        self._pekerja_aksi = None
        if pekerja is not None:
            pekerja.deleteLater()
        self._set_sibuk(
            self._pekerja_data is not None or self._menunggu_snapshot_aksi
        )

    def alihkan_istirahat(self) -> None:
        """
        Mulai atau akhiri istirahat loket yang sedang dipilih.

        Boleh dilakukan kapan pun, termasuk saat loket masih menangani
        seseorang — istirahat hanya menghentikan panggilan BERIKUTNYA,
        pengunjung yang sudah di depan meja tetap harus diselesaikan.
        """
        if self.loket_id is None:
            return
        loket_id = self.loket_id
        istirahat = not self.loket_istirahat
        self._jalankan(
            lambda: self.queue.set_istirahat(loket_id, istirahat),
            "Gagal mengubah status istirahat",
        )

    def panggil_berikutnya(self) -> None:
        if self.loket_id is None or not self.tombol_panggil.isEnabled():
            return
        category_id = self.pilih_kategori.currentData()
        urutan = self.pilih_urutan.currentData() or MODE_OTOMATIS
        loket_id = self.loket_id
        survey_lama = self.baru_selesai

        def setelah(_hasil) -> None:
            # Pilihan manual hanya berlaku untuk satu panggilan.
            self.pilih_urutan.setCurrentIndex(0)
            if survey_lama is not None:
                self._lewati_survey_lama(survey_lama)

        self._jalankan(
            lambda: self.queue.call_next(
                loket_id, category_id=category_id, urutan=urutan
            ),
            "Gagal memanggil antrian",
            setelah,
        )

    def _lewati_survey_lama(self, survey_lama: QueueInfo) -> None:
        """Nomor berikutnya sudah dipanggil; survey pengunjung lama ditutup."""
        if self.baru_selesai is survey_lama:
            self.baru_selesai = None
            self._perbarui_tombol_survey()

    def panggil_ulang(self) -> None:
        if self.antrian is None or not self.aksi["panggil_ulang"].isEnabled():
            return
        antrian_id = self.antrian.id
        self._jalankan(lambda: self.queue.recall(antrian_id))

    def mulai_melayani(self) -> None:
        if self.antrian is None or not self.aksi["mulai_layani"].isEnabled():
            return
        antrian_id = self.antrian.id
        self._jalankan(lambda: self.queue.start_service(antrian_id))

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
        antrian_id = self.antrian.id
        self._jalankan(
            lambda: self.queue.complete(antrian_id),
            "Gagal menyelesaikan pelayanan",
            self._simpan_antrian_baru_selesai,
        )

    def _simpan_antrian_baru_selesai(self, selesai: QueueInfo) -> None:
        self.baru_selesai = selesai
        self._perbarui_tombol_survey()

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
        antrian_id = self.antrian.id
        self._jalankan(lambda: self.queue.pause(antrian_id))

    def lewati_sementara(self) -> None:
        if self.antrian is None or not self.aksi["lewati"].isEnabled():
            return
        if not konfirmasi(
            self,
            f"Lewati {self.antrian.queue_number} untuk sementara dan kosongkan loket?\n\n"
            "Nomor tetap tersimpan di tab Dilewati dan dapat dipanggil kembali.",
            "Lewati Sementara",
        ):
            return
        antrian_id = self.antrian.id
        self._jalankan(
            lambda: self.queue.skip(antrian_id),
            "Gagal melewati antrian",
        )

    def panggil_kembali_dilewati(self) -> None:
        antrian_id = self._id_dilewati_terpilih()
        if (
            antrian_id is None
            or self.loket_id is None
            or not self.tombol_panggil_kembali.isEnabled()
        ):
            return
        antrian = self._dilewati_by_id.get(antrian_id)
        if antrian is None:
            return
        if not konfirmasi(
            self,
            f"Panggil kembali {antrian.queue_number} ke "
            f"{self.pilih_loket.currentText()}?",
            "Panggil Kembali",
        ):
            return
        loket_id = self.loket_id
        self._jalankan(
            lambda: self.queue.recall_skipped(antrian_id, loket_id),
            "Gagal memanggil kembali antrian",
        )

    def _dilewati_terpilih(self, btn) -> QueueInfo | None:
        antrian_id = self._id_dilewati_terpilih()
        if antrian_id is None or not btn.isEnabled():
            return None
        return self._dilewati_by_id.get(antrian_id)

    def tidak_hadir_dilewati(self) -> None:
        antrian = self._dilewati_terpilih(self.tombol_dilewati_tidak_hadir)
        if antrian is None:
            return
        if not konfirmasi(
            self,
            f"Tandai {antrian.queue_number} sebagai tidak hadir?\n\n"
            f"Nomor ini sudah dipanggil {antrian.jumlah_panggilan}x.",
        ):
            return
        antrian_id = antrian.id
        self._jalankan(
            lambda: self.queue.no_show(antrian_id),
            "Gagal menandai antrian tidak hadir",
        )

    def batalkan_dilewati(self) -> None:
        antrian = self._dilewati_terpilih(self.tombol_dilewati_batal)
        if antrian is None:
            return
        if not konfirmasi(self, f"Batalkan antrian {antrian.queue_number}?"):
            return
        antrian_id = antrian.id
        self._jalankan(
            lambda: self.queue.cancel(antrian_id),
            "Gagal membatalkan antrian",
        )

    def lanjutkan(self) -> None:
        if self.antrian is None:
            return
        antrian_id = self.antrian.id
        self._jalankan(lambda: self.queue.resume(antrian_id))

    def tidak_hadir(self) -> None:
        if self.antrian is None:
            return
        if not konfirmasi(
            self,
            f"Tandai {self.antrian.queue_number} sebagai tidak hadir?\n\n"
            f"Nomor ini sudah dipanggil {self.antrian.jumlah_panggilan}x.",
        ):
            return
        antrian_id = self.antrian.id
        self._jalankan(lambda: self.queue.no_show(antrian_id))

    def batalkan(self) -> None:
        if self.antrian is None:
            return
        if not konfirmasi(self, f"Batalkan antrian {self.antrian.queue_number}?"):
            return
        antrian_id = self.antrian.id
        self._jalankan(lambda: self.queue.cancel(antrian_id))

    def hentikan(self) -> None:
        """Hentikan timer dan tunggu singkat worker sebelum halaman dibuang."""
        self.pewaktu_durasi.stop()
        self.pewaktu_data.stop()
        for pekerja in (self._pekerja_data, self._pekerja_aksi):
            if pekerja is None:
                continue
            try:
                if pekerja.isRunning():
                    pekerja.wait(3_500)
                if pekerja.isRunning():
                    lepaskan_pekerja(pekerja)
            except RuntimeError:
                pass
