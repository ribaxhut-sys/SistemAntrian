"""Jendela utama aplikasi."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.config import APP_NAME, get_config, teks_status_database
from app.core.logger import get_logger
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService
from app.services.dashboard_service import DashboardService
from app.services.device_service import PerangkatService
from app.services.report_service import ReportService
from app.services.master_data_service import MasterDataService
from app.services.permissions import Permission
from app.services.queue_service import QueueService
from app.services.settings_service import SettingsService
from app.services.sound_service import buat_pemutar, suara_diaktifkan
from app.services.note_service import NoteService
from app.services.survey_service import SurveyService
from app.services.ticket_service import TicketService, buat_printer, mode_pencetak
from app.services.user_service import UserService
from app.ui.common import judul, keterangan, konfirmasi, tombol
from app.ui.dashboard.dashboard_page import DashboardPage
from app.ui.dashboard.survey_result_page import SurveyResultPage
from app.ui.login.change_password_dialog import ChangePasswordDialog
from app.ui.settings.dialogs import LABEL_PERAN
from app.ui.dashboard.report_page import LaporanPage
from app.ui.indikator_anjungan import PitaAnjungan
from app.ui.display.display_page import DisplayPage
from app.ui.notes.note_page import NotePage
from app.ui.queue.service_page import ServicePage
from app.ui.registration.registration_page import RegistrationPage
from app.ui.settings.layanan_anjungan_page import LayananAnjunganPage
from app.ui.settings.backup_page import BackupPage
from app.ui.settings.active_service_page import ActiveServicePage
from app.ui.settings.close_day_page import CloseDayPage
from app.ui.settings.master_data_page import MasterDataPage
from app.ui.settings.settings_page import SettingsPage
from app.ui.style import DANGER, SUCCESS, WARNING
from app.ui.survey.survey_page import SurveyPage

logger = get_logger("ui.main")

def _area_layar_utama() -> QRect:
    """Area kerja layar utama, atau 1280×720 bila Qt belum mengenal layar apa pun."""
    layar = QApplication.primaryScreen()
    return layar.availableGeometry() if layar is not None else QRect(0, 0, 1280, 720)


#: Bagian terbesar area layar yang boleh dipakai jendela yang diletakkan di
#: tengah. 1280 x 720 lebih besar dari laptop 1366 x 768 berskala 150%
#: (±910 x 512); jendela yang lebih besar dari layarnya tidak terlihat utuh.
BAGIAN_LAYAR_MAKS = 0.92

# Ukuran nyaman pada monitor besar. Pada laptop kecil atau Windows dengan
# skala tampilan tinggi, ukuran ini otomatis dipotong oleh area kerja layar.
UKURAN_JENDELA_PREFERENSI = QSize(1440, 900)

#: Selang uji koneksi di bilah status, dalam milidetik.
#:
#: Cukup jarang agar SELECT 1 dari tiap loket tidak menjadi beban, cukup
#: rapat agar petugas melihat server mati tanpa harus menekan F5.
SELANG_PERIKSA_KONEKSI_MS = 10_000

#: Selang pemeriksaan anjungan (API, Firewall, tablet). Lebih jarang dari uji
#: database karena di komputer server ia ikut menjalankan PowerShell, dan
#: kontak tablet sendiri hanya tercatat paling sering 30 detik sekali.
SELANG_PERIKSA_ANJUNGAN_MS = 30_000

#: Judul menu halaman Layanan Anjungan; juga dipakai pita peringatan untuk
#: membuka halaman itu.
MENU_LAYANAN_ANJUNGAN = "Layanan Anjungan"

#: Utas pemeriksa yang masih berjalan saat jendelanya ditutup. Dilepas dari
#: jendela dan disimpan di sini sampai selesai: QThread yang ikut dihapus
#: bersama induknya selagi masih berjalan membuat Qt menghentikan proses.
_UTAS_TERTINGGAL: set[QThread] = set()


def _lepas_utas_berjalan(utas: QThread) -> None:
    utas.setParent(None)
    _UTAS_TERTINGGAL.add(utas)

    def selesai() -> None:
        _UTAS_TERTINGGAL.discard(utas)
        utas.deleteLater()

    utas.finished.connect(selesai)
    # Bisa saja selesai di antara pemeriksaan dan penyambungan di atas.
    if utas.isFinished():
        selesai()


class _PemeriksaKoneksi(QThread):
    """
    SELECT 1 di utas sendiri.

    Bila komputer server mati, percobaan TCP bisa menahan beberapa detik
    meski connect_timeout sudah dipasang. Dijalankan di sini supaya meja
    loket tetap dapat diklik selama pemeriksaan.
    """

    selesai = Signal(bool)

    def run(self) -> None:
        from app.core.database import periksa_koneksi

        self.selesai.emit(periksa_koneksi())


class _PemeriksaAnjungan(QThread):
    """Pemeriksaan anjungan di utas sendiri: HTTP, PowerShell, dan database."""

    selesai = Signal(object)

    def run(self) -> None:
        from app.services.status_anjungan import periksa_status_anjungan

        try:
            self.selesai.emit(periksa_status_anjungan())
        except Exception:  # noqa: BLE001 - indikator tidak boleh menjatuhkan jendela
            logger.warning("Pemeriksaan anjungan gagal", exc_info=True)


@dataclass(frozen=True)
class _Menu:
    """Satu butir navigasi beserta hak akses yang dibutuhkannya."""

    judul: str
    permission: Permission | None
    pembuat: object
    #: Bila sesi memiliki salah satu hak ini, menu disembunyikan. Dipakai
    #: agar satu peran tidak mendapat dua menu untuk pekerjaan yang sama.
    kecuali: tuple[Permission, ...] = ()
    #: Hanya di komputer yang berperan server database.
    hanya_server: bool = False


def _komputer_server() -> bool:
    from app.services.kiosk_server import komputer_server

    try:
        return komputer_server()
    except Exception:  # noqa: BLE001 - menu tidak boleh menggagalkan jendela
        return False


def _inisial(nama: str) -> str:
    """Dua huruf dari nama petugas, untuk tanda di chip identitas."""
    bagian = [p for p in nama.split() if p]
    if not bagian:
        return "?"
    if len(bagian) == 1:
        return bagian[0][:2].upper()
    return f"{bagian[0][0]}{bagian[-1][0]}".upper()


class _ButirNavigasi:
    """Cerminan QListWidgetItem yang cukup untuk tes: hanya `.text()`."""

    def __init__(self, teks: str) -> None:
        self._teks = teks

    def text(self) -> str:
        return self._teks


class BilahNavigasi(QFrame):
    """
    Menu kerja sebagai deretan pil, bukan daftar vertikal.

    API-nya sengaja meniru QListWidget yang dulu dipakai di kolom kiri
    (`addItem`, `count`, `item`, `currentRow`, `setCurrentRow`, sinyal
    `currentRowChanged`) supaya tes hak akses tidak perlu diubah. Yang
    berubah hanya letak dan wujudnya.
    """

    currentRowChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navigasi")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Tinggi ekstra menampung scrollbar horizontal ketika menu admin
        # tidak muat. Teks tombol tetap utuh; menu digeser, bukan diciutkan.
        self.setFixedHeight(64)

        self._tombol: list[QPushButton] = []
        self._baris = -1
        self._grup = QButtonGroup(self)
        self._grup.setExclusive(True)
        self._grup.idClicked.connect(self.setCurrentRow)

        luar = QVBoxLayout(self)
        luar.setContentsMargins(0, 0, 0, 0)
        luar.setSpacing(0)

        self._gulir = QScrollArea()
        self._gulir.setObjectName("gulirNavigasi")
        self._gulir.setFrameShape(QFrame.Shape.NoFrame)
        # Konten sengaja tidak mengikuti lebar viewport. Bila semua tombol
        # lebih lebar daripada jendela, viewport menggulirnya; bila True,
        # Qt sempat menjadikan total lebar tombol sebagai minimum window
        # sebelum frame native Windows selesai dibangun.
        self._gulir.setWidgetResizable(False)
        self._gulir.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self._gulir.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._gulir.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._gulir.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self._gulir.setMinimumSize(0, 0)
        self._gulir.viewport().setAutoFillBackground(False)

        self._wadah = QWidget()
        self._wadah.setObjectName("wadahNavigasi")
        self._susunan = QHBoxLayout(self._wadah)
        self._susunan.setContentsMargins(4, 4, 4, 4)
        self._susunan.setSpacing(2)
        self._gulir.setWidget(self._wadah)
        luar.addWidget(self._gulir)

    def addItem(self, teks: str) -> None:
        tombol_menu = QPushButton(teks)
        tombol_menu.setObjectName("navPil")
        tombol_menu.setCheckable(True)
        tombol_menu.setAutoDefault(False)
        tombol_menu.setDefault(False)
        tombol_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        tombol_menu.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        indeks = len(self._tombol)
        self._grup.addButton(tombol_menu, indeks)
        self._tombol.append(tombol_menu)
        self._susunan.addWidget(tombol_menu)
        self._wadah.adjustSize()
        if indeks < 9:
            tombol_menu.setToolTip(f"{teks}  ·  Ctrl+{indeks + 1}")

    def count(self) -> int:
        return len(self._tombol)

    def item(self, baris: int) -> _ButirNavigasi | None:
        if 0 <= baris < len(self._tombol):
            return _ButirNavigasi(self._tombol[baris].text())
        return None

    def currentRow(self) -> int:
        return self._baris

    def setCurrentRow(self, baris: int) -> None:
        if baris < 0 or baris >= len(self._tombol):
            return
        if baris == self._baris:
            return
        self._baris = baris
        self._tombol[baris].setChecked(True)
        self.currentRowChanged.emit(baris)


class PlaceholderPage(QWidget):
    """
    Halaman untuk fitur yang belum dibangun.

    Lebih jujur daripada menu yang diklik lalu tidak terjadi apa-apa;
    petugas jadi tahu fiturnya memang belum ada, bukan sedang rusak.
    """

    def __init__(self, nama: str, keterangan_teks: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(32, 32, 32, 32)
        susunan.setSpacing(12)
        susunan.addWidget(judul(nama))
        susunan.addWidget(keterangan(keterangan_teks))
        susunan.addStretch()


class HalamanAdaptif(QScrollArea):
    """Wadah halaman kerja yang mencegah form terpotong pada layar kecil."""

    def __init__(self, isi: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("halamanAdaptif")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWidget(isi)

    @property
    def isi(self) -> QWidget | None:
        return self.widget()

    def sizeHint(self) -> QSize:  # noqa: N802 - nama Qt
        # QStackedWidget mengambil hint TERBESAR dari semua halaman, termasuk
        # halaman tersembunyi. Tanpa batas ini, form Pengaturan yang panjang
        # dapat memaksa window melebar sebelum scrollbar sempat aktif.
        return QSize(640, 400)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - nama Qt
        return QSize(160, 120)

    def muat_ulang(self) -> None:
        isi = self.isi
        segarkan = getattr(isi, "muat_ulang", None)
        if callable(segarkan):
            segarkan()

    def hentikan(self) -> None:
        isi = self.isi
        hentikan = getattr(isi, "hentikan", None)
        if callable(hentikan):
            hentikan()


class MainWindow(QMainWindow):
    """
    Kerangka aplikasi: kepala dengan menu pil, dan isi halaman penuh lebar.

    Menu disusun berdasarkan hak akses sesi yang sedang berjalan. Petugas
    tidak melihat menu yang memang bukan urusannya. Penegakan sebenarnya
    tetap di service layer; menu ini hanya mengurangi kebingungan.

    Navigasi menempel di kepala, bukan di kolom kiri: panel pelayanan
    disusun dua kolom dan butuh lebar, sedangkan petugas CRO hanya punya
    tiga menu — tidak cukup alasan untuk menyisihkan 220 piksel sepanjang
    tinggi jendela.
    """

    def __init__(
        self,
        auth: AuthService,
        parent: QWidget | None = None,
        *,
        berjendela: bool | None = None,
    ) -> None:
        super().__init__(parent)
        # Sejak keluar dari layar kembali ke Login/Pilihan Mode alih-alih
        # menutup aplikasi (lihat _jalankan_ui di app/main.py), close()
        # tanpa ini hanya menyembunyikan jendela — QTimer auto-refresh di
        # halaman-halaman anaknya (Layar Antrian, Dashboard, dst.) tetap
        # berdetak di latar belakang, dan begitu sesi logout, detak
        # berikutnya gagal dengan AuthenticationError yang muncul sebagai
        # kotak "Gagal" di atas layar berikutnya. WA_DeleteOnClose memastikan
        # jendela beserta seluruh anak dan timer-nya benar-benar dihapus.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.auth = auth
        #: True = jangan layar penuh (`--jendela`), untuk menguji layar
        #: antrian di laptop.
        self.berjendela = bool(berjendela)
        self.master_service = MasterDataService(auth)
        self.user_service = UserService(auth)
        self.queue_service = QueueService(auth)
        self.settings_service = SettingsService(auth)
        self.survey_service = SurveyService(auth)
        self.note_service = NoteService(auth)
        self.dashboard_service = DashboardService(auth)
        self.backup_service = BackupService(auth, self.settings_service)

        sesi = auth.require_session()

        config = get_config()
        # Pencetak dan pengeras suara menempel pada MESIN, bukan pada sistem.
        # Keduanya diselesaikan lewat resolver yang mendahulukan setelan
        # mesin ini di atas pengaturan bersama di database — lihat
        # ANTRIAN_PRINTER dan ANTRIAN_SUARA.
        self.ticket_service = TicketService(
            buat_printer(
                mode_pencetak(self.settings_service),
                config.base_dir / "tiket",
            ),
            self.settings_service,
            self.master_service,
            self.queue_service,
        )
        # Pemutar suara dibuat sekali dan dipakai bersama, supaya tidak ada
        # dua sumber bunyi yang berebut perangkat audio.
        self.sound_player = buat_pemutar(
            suara_diaktifkan(self.settings_service, anjungan=sesi.kios)
        )

        #: Layar antrian (cadangan TV Android) yang menghadap pengunjung,
        #: bukan meja petugas: sesi layar tanpa login, atau akun DISPLAY
        #: yang hanya boleh melihat layar antrian dan tidak boleh apa-apa lagi.
        #: Anjungan tidak lagi berjalan di Windows (lihat docs/istilah.md).
        #:
        #: Untuk DISPLAY, penentunya hak akses dan bukan nama peran. Bila
        #: suatu saat peran itu diberi kewenangan tambahan, akunnya berhenti
        #: dianggap kios — dan itu memang yang seharusnya terjadi, karena
        #: akun berkemampuan lebih tidak boleh terkunci di layar tanpa jalan
        #: keluar yang terlihat.
        self.mode_kios = sesi.kios or sesi.permissions == frozenset(
            {Permission.DISPLAY_VIEW}
        )
        #: Peran mesin, status API anjungan, dan alamat database hanya untuk
        #: admin — yang dapat menindaklanjutinya di Pengaturan.
        self._info_teknis = auth.has_permission(Permission.CONFIG_MANAGE)

        if self.mode_kios:
            # Nama petugas tidak ikut ditampilkan. Judul jendela terbaca
            # pada bilah tugas dan pengalih jendela, yang keduanya berada di
            # depan mata pengunjung.
            self.setWindowTitle(APP_NAME)
        else:
            self.setWindowTitle(f"{APP_NAME} — {sesi.full_name}")
        # Ukuran awal mengikuti area kerja dalam piksel logis Qt, sehingga
        # skala Windows 125%/150% ikut diperhitungkan. Batas preferensi
        # mencegah jendela terlalu melebar pada monitor 2K/4K.
        area_awal = _area_layar_utama()
        self.resize(
            min(
                UKURAN_JENDELA_PREFERENSI.width(),
                round(area_awal.width() * BAGIAN_LAYAR_MAKS),
            ),
            min(
                UKURAN_JENDELA_PREFERENSI.height(),
                round(area_awal.height() * BAGIAN_LAYAR_MAKS),
            ),
        )
        #: Geometri jendela biasa, untuk F11. Layar antrian dibuka langsung
        #: fullscreen; tanpa ini, restore Qt memakai ukuran bawaan kecil.
        self._geometri_normal = QRect(self.geometry())
        #: Ukurannya sah, posisinya belum: jendela yang belum pernah
        #: tampil masih berada di (0, 0). Lihat _turunkan_layar_penuh.
        self._posisi_normal_diketahui = False

        self._bangun_tampilan()
        self._pasang_pintasan()

    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        pusat = QWidget()
        susunan_utama = QVBoxLayout(pusat)
        susunan_utama.setContentsMargins(0, 0, 0, 0)
        susunan_utama.setSpacing(0)

        # Widget navigasi tetap dibuat walau tidak ditampilkan, supaya
        # penyusunan menu berjalan seperti biasa dan pemeriksaan hak akses
        # tetap melewati jalur yang sama. Pada mode kios ia tidak dipasang
        # ke kepala, sehingga parent()-nya tetap None.
        self.navigasi = BilahNavigasi()
        self.navigasi.currentRowChanged.connect(self._ganti_halaman)

        # Pada mode kios, bilah atas tidak dibangun sama sekali. Isinya —
        # nama petugas, tombol Ganti Kata Sandi, dan tombol Keluar — bukan
        # konsumsi pengunjung, dan tombol Keluar yang terlihat di layar
        # publik mengundang orang menutupnya.
        if not self.mode_kios:
            susunan_utama.addWidget(self._bangun_kepala())
        # Pita peringatan anjungan, tepat di bawah kepala. Tersembunyi
        # selama semuanya normal; lihat _pasang_bilah_database. Hanya untuk
        # admin: petugas loket tidak dapat memperbaiki Firewall atau API,
        # jadi peringatan itu hanya membuat cemas.
        if not self.mode_kios and self._info_teknis:
            boleh_buka_layanan = _komputer_server() and self.auth.has_permission(
                Permission.CONFIG_MANAGE
            )
            self.pita_anjungan = PitaAnjungan(
                self._jadwalkan_periksa_anjungan,
                self._buka_layanan_anjungan if boleh_buka_layanan else None,
            )
            susunan_utama.addWidget(self.pita_anjungan)

        self.halaman = QStackedWidget()
        susunan_utama.addWidget(self.halaman, stretch=1)
        self.setCentralWidget(pusat)

        self._susun_menu()

        # Bilah status memuat lokasi database. Tidak ada alasan pengunjung
        # perlu mengetahuinya, dan path/host itu tidak boleh tampil di
        # anjungan maupun televisi.
        if not self.mode_kios:
            self._pasang_bilah_database()

    def _bangun_kepala(self) -> QWidget:
        kepala = QFrame()
        kepala.setObjectName("panelHeader")

        susunan = QVBoxLayout(kepala)
        susunan.setContentsMargins(16, 8, 16, 8)
        susunan.setSpacing(7)

        baris_atas = QHBoxLayout()
        baris_atas.setSpacing(12)

        sesi = self.auth.require_session()

        merek = QFrame()
        merek.setObjectName("klasterMerek")
        susunan_merek = QHBoxLayout(merek)
        susunan_merek.setContentsMargins(0, 0, 0, 0)
        susunan_merek.setSpacing(10)

        tanda = QLabel("SA")
        tanda.setObjectName("tandaMerek")
        tanda.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tanda.setFixedSize(32, 32)
        susunan_merek.addWidget(tanda)

        nama = QLabel(APP_NAME)
        nama.setObjectName("judulMerek")
        susunan_merek.addWidget(nama)
        baris_atas.addWidget(merek)
        baris_atas.addStretch()

        chip = QFrame()
        chip.setObjectName("chipPengguna")
        susunan_chip = QHBoxLayout(chip)
        susunan_chip.setContentsMargins(6, 4, 12, 4)
        susunan_chip.setSpacing(8)

        inisial = QLabel(_inisial(sesi.full_name))
        inisial.setObjectName("inisialPengguna")
        inisial.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inisial.setFixedSize(28, 28)
        susunan_chip.addWidget(inisial)

        identitas = QLabel(
            f"{sesi.full_name}  ·  {LABEL_PERAN.get(sesi.role, sesi.role.value)}"
        )
        identitas.setObjectName("namaPengguna")
        susunan_chip.addWidget(identitas)
        self._chip_pengguna = chip
        baris_atas.addWidget(chip)

        ganti = tombol("Ganti Kata Sandi")
        ganti.setObjectName("tombolKepala")
        ganti.clicked.connect(self.ganti_kata_sandi)
        self._tombol_ganti_kata_sandi = ganti
        baris_atas.addWidget(ganti)

        keluar = tombol("Keluar", variant="danger")
        keluar.setObjectName("tombolKepala")
        keluar.clicked.connect(self.keluar)
        baris_atas.addWidget(keluar)

        susunan.addLayout(baris_atas)
        # Navigasi mendapat satu baris penuh. Pada admin jumlah menunya jauh
        # lebih banyak daripada petugas, dan menaruhnya di antara merek serta
        # profil membuat label menyusut atau keluar layar pada laptop kecil.
        susunan.addWidget(self.navigasi)

        return kepala

    def _susun_menu(self) -> None:
        """Susun menu sesuai hak akses sesi yang berjalan."""
        daftar: list[_Menu] = [
            _Menu(
                "Terbitkan Nomor",
                Permission.QUEUE_CREATE,
                lambda: RegistrationPage(
                    self.queue_service, self.master_service, self.ticket_service
                ),
            ),
            _Menu(
                "Pelayanan",
                Permission.QUEUE_CALL,
                lambda: ServicePage(
                    self.queue_service,
                    self.master_service,
                    self.survey_service,
                    self.settings_service,
                    self.auth,
                    note=self.note_service,
                ),
            ),
            _Menu(
                "Survey Kepuasan",
                Permission.SURVEY_SUBMIT,
                lambda: SurveyPage(self.survey_service, self.settings_service),
            ),
            # Terpisah dari panel pelayanan karena menjawab pertanyaan yang
            # berbeda: panel menjawab "apa yang terjadi di meja ini
            # sekarang", layar ini menjawab "apa yang pernah diadukan
            # orang ini sebelumnya" — dan yang kedua ditanyakan justru
            # ketika nomornya sudah lewat berhari-hari.
            _Menu(
                "Pengaduan",
                Permission.NOTE_VIEW,
                lambda: NotePage(self.note_service, self.auth),
            ),
            _Menu(
                "Data Master",
                Permission.MASTER_MANAGE,
                lambda: MasterDataPage(self.master_service, self.user_service),
            ),
            _Menu(
                "Pengaturan",
                Permission.CONFIG_MANAGE,
                lambda: SettingsPage(self.settings_service, self.master_service),
            ),
            # Hanya di komputer server: API anjungan berjalan di pemilik
            # database, dan anjungan Android hanya klien yang menyambung.
            _Menu(
                MENU_LAYANAN_ANJUNGAN,
                Permission.CONFIG_MANAGE,
                lambda: LayananAnjunganPage(PerangkatService(self.auth)),
                hanya_server=True,
            ),
            _Menu(
                "Backup",
                Permission.BACKUP_MANAGE,
                lambda: BackupPage(self.backup_service),
            ),
            _Menu(
                "Pelayanan Aktif",
                Permission.QUEUE_REASSIGN,
                lambda: ActiveServicePage(self.queue_service),
            ),
            _Menu(
                "Tutup Hari",
                Permission.QUEUE_CLOSE_DAY,
                lambda: CloseDayPage(self.queue_service, self.backup_service),
            ),
            # Cadangan TV Android. Akan hilang bersama --tv begitu aplikasi
            # layar antrian Android siap (docs/istilah.md).
            _Menu(
                "Layar Antrian",
                Permission.DISPLAY_VIEW,
                self._halaman_layar_antrian,
                # Petugas pendaftaran tidak perlu papan di mejanya.
                kecuali=(Permission.QUEUE_CREATE,),
            ),
            # Satu menu saja untuk pemantauan. Ringkasan harian sudah memuat
            # keadaan antrian sekaligus kepuasan, sehingga memisahkannya
            # menjadi "Antrian" dan "Laporan" hanya membuat supervisor
            # berpindah-pindah untuk membaca satu keadaan yang sama.
            _Menu(
                "Ringkasan Harian",
                Permission.DASHBOARD_VIEW,
                lambda: DashboardPage(self.dashboard_service, self.settings_service),
            ),
            # Rentang tanggal, per loket dan per petugas: pertanyaan sesudah
            # "bagaimana hari ini", dan sebab hak REPORT_VIEW sudah ada.
            _Menu(
                "Laporan",
                Permission.REPORT_VIEW,
                lambda: LaporanPage(
                    ReportService(self.auth),
                    self.settings_service.get("ticket.header", ""),
                ),
            ),
            # Terpisah dari ringkasan harian karena isinya berbeda jenis:
            # ringkasan menjawab "bagaimana hari ini", daftar ini menjawab
            # "apa kata pengunjung" — dan yang kedua dibaca kalimat per
            # kalimat, bukan sekilas.
            _Menu(
                "Hasil Survey",
                Permission.SURVEY_VIEW,
                lambda: SurveyResultPage(self.survey_service),
            ),
        ]

        self.auth.require_session()
        self.menu_aktif: list[_Menu] = []
        for butir in daftar:
            if any(self.auth.has_permission(p) for p in butir.kecuali):
                continue
            if butir.hanya_server and not _komputer_server():
                continue
            if butir.permission is None or self.auth.has_permission(butir.permission):
                self.menu_aktif.append(butir)
                self.navigasi.addItem(butir.judul)
                halaman = butir.pembuat()
                # Papan antrian menyusun dirinya sendiri berdasarkan bentuk
                # monitor dan harus mengisi layar tanpa bilah gulir. Halaman
                # kerja biasa diberi fallback gulir agar semua kontrol tetap
                # dapat dicapai ketika tinggi/lebar layar tidak mencukupi.
                if isinstance(halaman, DisplayPage):
                    self.halaman.addWidget(halaman)
                else:
                    self.halaman.addWidget(HalamanAdaptif(halaman))

        if not self.menu_aktif:
            # Terjadi bila perannya tidak punya satu pun halaman, misalnya
            # akun yang masih diwajibkan mengganti kata sandi.
            self.navigasi.hide()
            self.halaman.addWidget(
                PlaceholderPage(
                    "Tidak ada menu tersedia",
                    "Akun Anda belum memiliki akses ke menu mana pun. "
                    "Hubungi administrator.",
                )
            )
            return

        self.navigasi.setCurrentRow(0)

    def _halaman_layar_antrian(self) -> QWidget:
        """Papan antrian televisi, yang melapor bila bentuk layarnya lain."""
        papan = DisplayPage(
            self.queue_service, self.settings_service, self.sound_player
        )
        papan.bentuk_berubah.connect(
            lambda bentuk, lama=papan: self._ganti_bentuk_layar(lama, bentuk)
        )
        return papan

    def _ganti_bentuk_layar(self, lama: DisplayPage, bentuk: str) -> None:
        """
        Bangun ulang papan antrian untuk bentuk layar yang sebenarnya.

        Halaman dibangun di `_susun_menu`, yaitu SEBELUM jendela ini pernah
        tampil, sehingga papan hanya sanggup menebak layarnya dari monitor
        utama. Televisi ruang tunggu sering justru monitor kedua, dan pita
        LED di atas pintu hampir selalu.

        Yang dibuat adalah papan BARU, bukan papan lama yang ditata ulang.
        Kerangka papan menyebar ke belasan atribut, dan satu saja yang lupa
        dinolkan akan menunjuk objek C++ yang sudah dihapus — lalu
        menjatuhkan layar yang seharusnya menyala sepanjang hari kerja.
        Membuang seluruh papan lama tidak menyisakan atribut untuk dilupakan.
        """
        indeks = self.halaman.indexOf(lama)
        if indeks < 0:
            return
        baru = DisplayPage(
            self.queue_service,
            self.settings_service,
            self.sound_player,
            bentuk=bentuk,
        )
        sedang_tampil = self.halaman.currentWidget() is lama
        # Disisipkan pada indeks yang sama lalu yang lama dicabut: nomor
        # halaman dipakai langsung sebagai baris menu di `_ganti_halaman`,
        # dan indeks yang bergeser berarti menu menunjuk halaman lain.
        self.halaman.insertWidget(indeks, baru)
        self.halaman.removeWidget(lama)
        lama.hentikan()
        lama.deleteLater()
        if sedang_tampil:
            self.halaman.setCurrentIndex(indeks)
        logger.info("Papan antrian dibangun ulang untuk layar %s.", bentuk)

    def _pasang_pintasan(self) -> None:
        """Pintasan papan ketik: petugas loket jarang menyentuh mouse."""
        QShortcut(QKeySequence("F5"), self, self.muat_ulang_halaman)
        QShortcut(QKeySequence("Ctrl+Q"), self, self.keluar)
        # Satu-satunya jalan keluar dari layar penuh selain Ctrl+Q. Petugas
        # membutuhkannya saat memindahkan jendela ke monitor yang benar.
        QShortcut(QKeySequence("F11"), self, self.ganti_layar_penuh)
        # Esc hanya menurunkan layar penuh, tidak menutup aplikasi. Menutup
        # lewat Esc di komputer publik terlalu mudah tertekan tanpa sengaja.
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.keluar_layar_penuh)

        # Ganti menu tanpa mouse. Angka tanpa Ctrl sudah dipakai menerbitkan
        # nomor di meja pendaftaran (1–9), jadi yang di kepala wajib Ctrl.
        # Layar antrian tidak mendapatkannya: menunya tersembunyi, dan
        # menekan Ctrl+1 di sana tidak boleh memindahkan apa pun.
        if not self.mode_kios:
            for indeks in range(min(9, len(self.menu_aktif))):
                pintasan = QShortcut(QKeySequence(f"Ctrl+{indeks + 1}"), self)
                pintasan.activated.connect(
                    lambda baris=indeks: self.navigasi.setCurrentRow(baris)
                )

    # -----------------------------------------------------------------

    def tampilkan(self) -> None:
        """
        Buka jendela sesuai perannya.

        Layar yang menghadap pengunjung dibuka penuh sejak awal, tanpa
        bingkai jendela dan tanpa tombol tutup yang menggoda untuk ditekan.
        `--jendela` meniadakan itu, untuk menguji di laptop.
        """
        if self.mode_kios and not self.berjendela:
            self.showFullScreen()
            return
        # Paksa kembali ke mode normal: shortcut Windows dapat dikonfigurasi
        # "Run: Maximized", dan status itu akan mengalahkan move()/resize()
        # bila tidak dibersihkan lebih dulu. Pusatkan SETELAH showNormal()
        # supaya frameGeometry sudah memuat bingkai native Windows; sebelum
        # jendela tampil, tinggi bilah judul belum selalu ikut dihitung.
        ukuran = (
            self._geometri_normal.size()
            if self._geometri_normal is not None and self._geometri_normal.isValid()
            else QSize(self.size())
        )
        area = _area_layar_utama()
        self.showNormal()
        self._pusatkan(area, ukuran)
        batas = QSize(
            round(area.width() * BAGIAN_LAYAR_MAKS),
            round(area.height() * BAGIAN_LAYAR_MAKS),
        )
        target = ukuran.boundedTo(batas)
        if self.size() != target:
            # Pada Windows, minimum native sempat dihitung dari sizeHint
            # seluruh halaman tersembunyi sebelum QScrollArea aktif. Ulangi
            # sesudah event show diproses agar batas yang sudah mengecil
            # benar-benar diterapkan oleh window manager.
            def ulangi_geometri() -> None:
                if not self.isVisible() or self.isFullScreen():
                    return
                self.setMinimumSize(0, 0)
                self.updateGeometry()
                self._pusatkan(area, ukuran)
                self._geometri_normal = QRect(self.geometry())

            QTimer.singleShot(0, ulangi_geometri)
        self._geometri_normal = QRect(self.geometry())
        self._posisi_normal_diketahui = True

    def ganti_layar_penuh(self) -> None:
        if self.isFullScreen():
            self._turunkan_layar_penuh()
        else:
            self._geometri_normal = QRect(self.geometry())
            self._posisi_normal_diketahui = self.isVisible()
            self.showFullScreen()

    def keluar_layar_penuh(self) -> None:
        """Turunkan layar penuh. Tidak melakukan apa-apa bila sudah jendela."""
        if self.isFullScreen():
            self._turunkan_layar_penuh()

    def _turunkan_layar_penuh(self) -> None:
        """
        Kembali ke jendela biasa: ke posisi terakhirnya bila pernah ada,
        selain itu ke tengah layar tempat jendela ini sedang tampil.

        Layar antrian dibuka langsung layar penuh, jadi tidak
        pernah punya posisi jendela biasa. Geometri yang dicatat konstruktor
        berposisi (0, 0) karena jendelanya belum tampil; memulihkannya
        menaruh jendela di pojok kiri atas dengan bilah judul lewat tepi atas
        layar — dan jendela tanpa bilah judul tidak dapat digeser dengan mouse.
        """
        # Dibaca sebelum showNormal: layar TV sering monitor kedua, dan
        # jendela harus turun di layar yang sedang ditatap, bukan melompat
        # ke monitor utama.
        area = self._area_layar_sekarang()
        geometri = self._geometri_normal
        sah = geometri is not None and geometri.isValid()

        self.showNormal()
        if sah and self._posisi_normal_diketahui:
            self.setGeometry(geometri)
        else:
            self._pusatkan(area, geometri.size() if sah else QSize(1280, 720))

    def _area_layar_sekarang(self) -> QRect:
        """Area kerja monitor tempat jendela ini tampil."""
        layar = self.screen()
        return layar.availableGeometry() if layar is not None else _area_layar_utama()

    def _pusatkan(self, area: QRect, ukuran: QSize) -> None:
        """Letakkan jendela di tengah `area`, tidak lebih besar dari BAGIAN_LAYAR_MAKS."""
        batas = QSize(
            round(area.width() * BAGIAN_LAYAR_MAKS),
            round(area.height() * BAGIAN_LAYAR_MAKS),
        )
        self.resize(ukuran.boundedTo(batas))
        bingkai = self.frameGeometry()
        bingkai.moveCenter(area.center())
        # Bilah judul wajib di dalam layar, apa pun ukurannya.
        bingkai.moveTop(max(bingkai.top(), area.top()))
        self.move(bingkai.topLeft())

    def _ganti_halaman(self, baris: int) -> None:
        if baris >= 0:
            self.halaman.setCurrentIndex(baris)

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama Qt
        """Ringkaskan kepala saat lebar jendela terbatas."""
        super().resizeEvent(event)
        ringkas = event.size().width() < 1100
        chip = getattr(self, "_chip_pengguna", None)
        if chip is not None:
            chip.setVisible(not ringkas)
        ganti = getattr(self, "_tombol_ganti_kata_sandi", None)
        if ganti is not None:
            ganti.setText("Kata Sandi" if ringkas else "Ganti Kata Sandi")

    def _pasang_bilah_database(self) -> None:
        """
        Widget tetap di kanan bilah status, supaya F5 tidak menghapusnya.

        showMessage("Data dimuat ulang.") bersifat sementara; widget biasa
        ikut tersembunyi, sedangkan permanent widget tetap terlihat. Itulah
        yang dibutuhkan petugas: lokasi server tidak boleh hilang hanya
        karena ia menyegarkan daftar antrian.
        """
        # Peran mesin di kiri lokasi database. Saat memasang tujuh
        # komputer, memastikan sekilas mana yang mana — tanpa membuka
        # dialog satu per satu — menghemat lebih banyak waktu daripada
        # yang terlihat. Mesin yang belum ditetapkan tidak menampilkan
        # apa-apa: ruang kosong lebih jujur daripada kata "(tidak ada)".
        from app.core.peran import baca_peran, path_berkas_peran

        peran = baca_peran(path_berkas_peran(get_config().db_path))
        if peran.label and self._info_teknis:
            self._label_peran = QLabel(peran.label)
            self._label_peran.setObjectName("statusPeran")
            self.statusBar().addPermanentWidget(self._label_peran)

        # Anjungan Android hanya ada pada pemasangan PostgreSQL; API-nya
        # berjalan di komputer server. Setiap petugas — di server maupun di
        # loket — perlu tahu sekilas bila anjungan tidak dapat mengambil
        # nomor, tanpa menunggu pengunjung datang mengeluh. Bilah status
        # memberi ringkasannya, pita di bawah kepala memberi sarannya.
        self._sedang_memeriksa_anjungan = False
        self._pemeriksa_anjungan: _PemeriksaAnjungan | None = None
        di_server = _komputer_server()
        if self._info_teknis and (di_server or not get_config().memakai_sqlite):
            self._label_api = QLabel("API anjungan: memeriksa…")
            self._label_api.setObjectName("statusApiAnjungan")
            self.statusBar().addPermanentWidget(self._label_api)
            if di_server:
                # Ketukan ke 127.0.0.1 ditolak seketika bila port tertutup,
                # jadi aman di utas UI dan label langsung bermakna.
                self._periksa_api()
            # Pemeriksaan lengkap menunggu jendela selesai tampil.
            QTimer.singleShot(1500, self._jadwalkan_periksa_anjungan)
            self._pewaktu_api = QTimer(self)
            self._pewaktu_api.setInterval(SELANG_PERIKSA_ANJUNGAN_MS)
            self._pewaktu_api.timeout.connect(self._jadwalkan_periksa_anjungan)
            self._pewaktu_api.start()

        self._label_database = QLabel()
        self._label_database.setObjectName("statusDatabase")
        self._label_database.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._label_database.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.statusBar().addPermanentWidget(self._label_database)
        self._sedang_memeriksa_db = False
        self._pemeriksa_db: _PemeriksaKoneksi | None = None
        # Jendela ini hanya terbuka setelah siapkan_database() berhasil,
        # jadi status awal "terhubung" akurat tanpa menunggu SELECT 1.
        self._tampilkan_status_database(True)
        self._pewaktu_db = QTimer(self)
        self._pewaktu_db.setInterval(SELANG_PERIKSA_KONEKSI_MS)
        self._pewaktu_db.timeout.connect(self._jadwalkan_periksa_database)
        self._pewaktu_db.start()

    def _jadwalkan_periksa_database(self) -> None:
        """Mulai SELECT 1 di utas sendiri, atau lewati bila yang lalu belum selesai."""
        if self.mode_kios or self._sedang_memeriksa_db:
            return
        self._sedang_memeriksa_db = True
        pemeriksa = _PemeriksaKoneksi(self)
        pemeriksa.selesai.connect(self._tampilkan_status_database)
        pemeriksa.finished.connect(self._selesai_periksa_database)
        pemeriksa.start()
        self._pemeriksa_db = pemeriksa

    def _selesai_periksa_database(self) -> None:
        self._sedang_memeriksa_db = False
        pemeriksa = self._pemeriksa_db
        self._pemeriksa_db = None
        if pemeriksa is not None:
            pemeriksa.deleteLater()

    def _periksa_api(self) -> None:
        """Ketuk /health di 127.0.0.1. Port yang tertutup ditolak seketika."""
        from app.services.kiosk_server import api_sudah_berjalan, port_api

        label = getattr(self, "_label_api", None)
        if label is None:
            return
        if api_sudah_berjalan(port_api()):
            label.setText("API anjungan: ● berjalan")
            label.setStyleSheet(f"color: {SUCCESS};")
        else:
            label.setText("API anjungan: ● mati")
            label.setStyleSheet(f"color: {DANGER};")

    def _jadwalkan_periksa_anjungan(self) -> None:
        """Mulai pemeriksaan anjungan di utas sendiri, bila belum berjalan."""
        if self.mode_kios or self._sedang_memeriksa_anjungan:
            return
        if getattr(self, "_label_api", None) is None:
            return
        self._sedang_memeriksa_anjungan = True
        pemeriksa = _PemeriksaAnjungan(self)
        pemeriksa.selesai.connect(self._tampilkan_status_anjungan)
        pemeriksa.finished.connect(self._selesai_periksa_anjungan)
        pemeriksa.start()
        self._pemeriksa_anjungan = pemeriksa

    def _selesai_periksa_anjungan(self) -> None:
        self._sedang_memeriksa_anjungan = False
        pemeriksa = self._pemeriksa_anjungan
        self._pemeriksa_anjungan = None
        if pemeriksa is not None:
            pemeriksa.deleteLater()

    def _tampilkan_status_anjungan(self, status) -> None:
        from app.services.status_anjungan import MASALAH, NORMAL

        label = getattr(self, "_label_api", None)
        if label is None or status is None:
            return
        label.setText(status.ringkas)
        warna = {NORMAL: SUCCESS, MASALAH: DANGER}.get(status.tingkat, WARNING)
        label.setStyleSheet(f"color: {warna};")
        label.setToolTip(status.judul)
        pita = getattr(self, "pita_anjungan", None)
        if pita is not None:
            pita.tampilkan(status)

    def _buka_layanan_anjungan(self) -> None:
        for baris, butir in enumerate(self.menu_aktif):
            if butir.judul == MENU_LAYANAN_ANJUNGAN:
                self.navigasi.setCurrentRow(baris)
                return

    def _tampilkan_status_database(self, terhubung: bool) -> None:
        label = getattr(self, "_label_database", None)
        if label is None:
            return
        if self._info_teknis:
            detail = teks_status_database(terhubung=terhubung)
            label.setToolTip(detail)
            label.setText(
                "Database: ● tersambung"
                if terhubung
                else "Database: ● tidak tersambung — cek server"
            )
        else:
            # Petugas cukup tahu tersambung atau tidak; alamat server dan
            # jenis database hanya berguna bagi admin yang memperbaikinya.
            label.setText(
                "Database: ● tersambung"
                if terhubung
                else "Database: ● tidak tersambung — hubungi admin"
            )
            label.setToolTip("")
        label.setStyleSheet("" if terhubung else f"color: {DANGER};")

    def muat_ulang_halaman(self) -> None:
        halaman = self.halaman.currentWidget()
        if hasattr(halaman, "muat_ulang"):
            halaman.muat_ulang()
            # statusBar() membuat bilah status baru bila belum ada, sehingga
            # tanpa penjagaan ini menekan F5 justru memunculkan bilah yang
            # sengaja tidak dibangun pada mode kios.
            if not self.mode_kios:
                self.statusBar().showMessage("Memuat ulang data…", 2000)
                self._jadwalkan_periksa_database()

    def ganti_kata_sandi(self) -> None:
        ChangePasswordDialog(self.auth, self).exec()

    def keluar(self) -> None:
        # Mesin publik tidak pernah sampai ke layar masuk: keluar dari sana
        # mengembalikan ke pilihan layar. Menjanjikan "layar masuk" kepada
        # orang yang menekan Ctrl+Q di layar antrian hanya membuatnya mengira
        # aplikasinya salah.
        pertanyaan = (
            "Tutup layar ini dan kembali ke pilihan layar?"
            if self.mode_kios
            else "Keluar dan kembali ke layar masuk?"
        )
        if not konfirmasi(self, pertanyaan):
            return
        self.auth.logout()
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - nama dari Qt
        """Pastikan sesi berakhir walau jendela ditutup lewat tombol silang."""
        for indeks in range(self.halaman.count()):
            halaman = self.halaman.widget(indeks)
            hentikan = getattr(halaman, "hentikan", None)
            if callable(hentikan):
                hentikan()
        pewaktu_api = getattr(self, "_pewaktu_api", None)
        if pewaktu_api is not None:
            pewaktu_api.stop()
        pewaktu = getattr(self, "_pewaktu_db", None)
        if pewaktu is not None:
            pewaktu.stop()
        for nama, batas_ms in (("_pemeriksa_db", 400), ("_pemeriksa_anjungan", 3000)):
            pemeriksa = getattr(self, nama, None)
            if pemeriksa is None:
                continue
            try:
                pemeriksa.selesai.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                if pemeriksa.isRunning() and not pemeriksa.wait(batas_ms):
                    _lepas_utas_berjalan(pemeriksa)
            except RuntimeError:
                pass
        if self.auth.is_authenticated:
            self.auth.logout()
        super().closeEvent(event)
