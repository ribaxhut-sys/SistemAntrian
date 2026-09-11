"""Jendela utama aplikasi."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
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
from app.ui.display.display_page import DisplayPage
from app.ui.kiosk.kiosk_page import KioskPage
from app.ui.efek import setel_efek_grafis
from app.ui.kiosk.pratinjau import (
    LEBAR_TOTEM_ASLI,
    PratinjauTotem,
    layar_mendatar,
    ukuran_jendela_totem,
)
from app.ui.notes.note_page import NotePage
from app.ui.queue.service_page import ServicePage
from app.ui.registration.registration_page import RegistrationPage
from app.ui.settings.backup_page import BackupPage
from app.ui.settings.close_day_page import CloseDayPage
from app.ui.settings.master_data_page import MasterDataPage
from app.ui.settings.settings_page import SettingsPage
from app.ui.style import DANGER
from app.ui.survey.survey_page import SurveyPage

logger = get_logger("ui.main")

TINGGI_TAK_TERBATAS = (1 << 24) - 1


def _area_layar_utama() -> QRect:
    """Area kerja layar utama, atau 1280×720 bila Qt belum mengenal layar apa pun."""
    layar = QApplication.primaryScreen()
    return layar.availableGeometry() if layar is not None else QRect(0, 0, 1280, 720)

#: Selang uji koneksi di bilah status, dalam milidetik.
#:
#: Cukup jarang agar SELECT 1 dari tiap loket tidak menjadi beban, cukup
#: rapat agar petugas melihat server mati tanpa harus menekan F5.
SELANG_PERIKSA_KONEKSI_MS = 10_000


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


@dataclass(frozen=True)
class _Menu:
    """Satu butir navigasi beserta hak akses yang dibutuhkannya."""

    judul: str
    permission: Permission | None
    pembuat: object
    #: Bila sesi memiliki salah satu hak ini, menu disembunyikan. Dipakai
    #: agar satu peran tidak mendapat dua menu untuk pekerjaan yang sama.
    kecuali: tuple[Permission, ...] = ()
    #: Hanya untuk sesi kios. Hak akses saja tidak cukup membedakannya:
    #: petugas pendaftaran juga berhak menerbitkan nomor, tetapi layar
    #: pengunjung bukan untuk meja berpetugas.
    hanya_kios: bool = False


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
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self._tombol: list[QPushButton] = []
        self._baris = -1
        self._grup = QButtonGroup(self)
        self._grup.setExclusive(True)
        self._grup.idClicked.connect(self.setCurrentRow)

        self._susunan = QHBoxLayout(self)
        self._susunan.setContentsMargins(4, 4, 4, 4)
        self._susunan.setSpacing(2)

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
        anjungan_totem: bool = False,
        berjendela: bool | None = None,
        persen_pratinjau: int | None = None,
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
        self.anjungan_totem = anjungan_totem
        area = _area_layar_utama()
        if berjendela is None:
            # Kaca totem selalu berdiri tegak. Dibuka layar penuh di layar
            # mendatar — laptop, lewat dialog pilihan yang tidak bisa menulis
            # --jendela — ketiga pitanya terbentang menjadi pita pipih yang
            # tidak mirip mesin sungguhannya. Totem sungguhan berdiri tegak,
            # jadi di sana tetap layar penuh. Mesin publik lain tidak
            # tersentuh: layarnya memang mendatar.
            berjendela = anjungan_totem and layar_mendatar(area)
        #: True = jangan layar penuh. Untuk melihat totem utuh di laptop.
        self.berjendela = berjendela
        #: Persentase pratinjau totem dari `--jendela=PERSEN`. None berarti
        #: sebesar yang muat di layar, paling besar 50%.
        self.persen_pratinjau = persen_pratinjau
        # Pratinjau totem membungkus halaman anjungan dalam
        # QGraphicsProxyWidget, dan Qt tidak menggambar efek grafis di
        # dalam proxy: kartu layanan berbayangan hilang dari layar — lihat
        # app/ui/efek.py. Disetel pada SETIAP jendela, bukan hanya
        # dimatikan untuk pratinjau: `_jalankan_ui` membuka jendela
        # berikutnya di proses yang sama, dan layar televisi yang dibuka
        # sesudah pratinjau tidak boleh ikut kehilangan bayangannya.
        setel_efek_grafis(not (anjungan_totem and berjendela))
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

        #: Layar yang menghadap pengunjung, bukan meja petugas.
        #:
        #: Tiga bentuk, semuanya dipasang di komputer publik: sesi anjungan
        #: dan sesi layar antrian yang berjalan tanpa login, serta akun
        #: DISPLAY yang hanya boleh melihat layar antrian dan tidak boleh
        #: apa-apa lagi.
        #:
        #: Untuk DISPLAY, penentunya hak akses dan bukan nama peran. Bila
        #: suatu saat peran itu diberi kewenangan tambahan, akunnya berhenti
        #: dianggap kios — dan itu memang yang seharusnya terjadi, karena
        #: akun berkemampuan lebih tidak boleh terkunci di layar tanpa jalan
        #: keluar yang terlihat.
        self.mode_kios = sesi.kios or sesi.permissions == frozenset(
            {Permission.DISPLAY_VIEW}
        )

        if self.mode_kios:
            # Nama petugas tidak ikut ditampilkan. Judul jendela terbaca
            # pada bilah tugas dan pengalih jendela, yang keduanya berada di
            # depan mata pengunjung.
            self.setWindowTitle(APP_NAME)
        else:
            self.setWindowTitle(f"{APP_NAME} — {sesi.full_name}")
        # Panel pelayanan disusun dua kolom: kartu antrian beserta tombolnya
        # di kiri, daftar tunggu di kanan. Menu di kepala (bukan kolom kiri)
        # menyisakan lebar penuh untuk keduanya. 1280 x 720 masih muat utuh
        # pada layar 1366 x 768 yang paling sempit di kantor.
        #
        # Totem + --jendela: miniatur 1080×1920 (sekitar 50% di laptop
        # 1080p), bukan tata letak yang disusun ulang ke jendela mendatar.
        if self.anjungan_totem:
            self._geometri_normal = ukuran_jendela_totem(area, self.persen_pratinjau)
            self.resize(self._geometri_normal.size())
            self.move(self._geometri_normal.topLeft())
        else:
            self.resize(1280, 720)
            #: Geometri jendela biasa, untuk F11. Anjungan dibuka langsung
            #: fullscreen; tanpa ini, restore Qt memakai ukuran bawaan kecil
            #: dan kartu layanan dihitung ulang jadi pita.
            self._geometri_normal = QRect(self.geometry())

        self._bangun_tampilan()
        self._pasang_pintasan()
        if self.anjungan_totem:
            self._kunci_ukuran_totem(True)

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

        susunan = QHBoxLayout(kepala)
        susunan.setContentsMargins(16, 10, 16, 10)
        susunan.setSpacing(12)

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
        susunan.addWidget(merek)

        susunan.addWidget(self.navigasi)
        susunan.addStretch()

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
        susunan.addWidget(chip)

        ganti = tombol("Ganti Kata Sandi")
        ganti.setObjectName("tombolKepala")
        ganti.clicked.connect(self.ganti_kata_sandi)
        susunan.addWidget(ganti)

        keluar = tombol("Keluar", variant="danger")
        keluar.setObjectName("tombolKepala")
        keluar.clicked.connect(self.keluar)
        susunan.addWidget(keluar)

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
            _Menu(
                "Backup",
                Permission.BACKUP_MANAGE,
                lambda: BackupPage(self.backup_service),
            ),
            _Menu(
                "Tutup Hari",
                Permission.QUEUE_CLOSE_DAY,
                lambda: CloseDayPage(self.queue_service, self.backup_service),
            ),
            # Anjungan menggabungkan papan nomor kecil dengan pengambilan
            # nomor pada satu layar. Televisi ruang tunggu mendapat papan
            # besarnya saja lewat menu berikutnya.
            _Menu(
                "Anjungan Ambil Nomor",
                Permission.QUEUE_CREATE,
                self._halaman_anjungan,
                hanya_kios=True,
            ),
            _Menu(
                "Layar Antrian",
                Permission.DISPLAY_VIEW,
                lambda: DisplayPage(
                    self.queue_service, self.settings_service, self.sound_player
                ),
                # Kios sudah memuat papan nomor di dalam layarnya sendiri;
                # tanpa syarat ini ia mendapat dua menu untuk hal yang sama.
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

        sesi = self.auth.require_session()
        self.menu_aktif: list[_Menu] = []
        for butir in daftar:
            if butir.hanya_kios and not sesi.kios:
                continue
            # Anjungan hanya boleh halaman anjungan. Tanpa ini ia juga
            # mendapat "Terbitkan Nomor" karena sama-sama berhak
            # QUEUE_CREATE, dan halaman pertamanya justru meja pendaftaran —
            # bukan layar yang menghadap pengunjung.
            if sesi.kios and not butir.hanya_kios:
                continue
            if any(self.auth.has_permission(p) for p in butir.kecuali):
                continue
            if butir.permission is None or self.auth.has_permission(butir.permission):
                self.menu_aktif.append(butir)
                self.navigasi.addItem(butir.judul)
                self.halaman.addWidget(butir.pembuat())

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

    def _halaman_anjungan(self) -> QWidget:
        """Halaman anjungan, atau miniaturnya bila `--jendela` pada totem."""
        halaman = KioskPage(
            self.queue_service,
            self.master_service,
            self.settings_service,
            self.sound_player,
            self.ticket_service,
            totem=self.anjungan_totem,
        )
        if not (self.anjungan_totem and self.berjendela):
            return halaman
        skala = self._geometri_normal.width() / LEBAR_TOTEM_ASLI
        return PratinjauTotem(halaman, skala)

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
        # Mesin publik tidak mendapatkannya: menunya tersembunyi, dan
        # menekan Ctrl+1 di anjungan tidak boleh memindahkan apa pun.
        if not self.mode_kios:
            for indeks in range(min(9, len(self.menu_aktif))):
                pintasan = QShortcut(QKeySequence(f"Ctrl+{indeks + 1}"), self)
                pintasan.activated.connect(
                    lambda baris=indeks: self.navigasi.setCurrentRow(baris)
                )

    # -----------------------------------------------------------------

    def _kunci_ukuran_totem(self, kunci: bool) -> None:
        """
        Kunci jendela totem pada ukuran pratinjau.

        Tanpa ini, sizeHint tiga kartu layanan melebar ke 1280×720 begitu
        jendela ditampilkan, dan pita iklan kembali pipih.

        HANYA untuk pratinjau `--jendela`, di mana isinya adalah kaca
        1080×1920 yang diperkecil utuh. Totem sungguhan menaruh halaman
        anjungan langsung di jendela: mengunci jendela itu pada 540×960
        begitu Esc atau F11 ditekan akan menyusun ulang tiga pita totem ke
        lebar 540 px, dalam jendela yang tidak bisa diperbesar lagi.
        """
        if not (self.anjungan_totem and self.berjendela):
            return
        if self._geometri_normal is None:
            return
        if kunci:
            ukuran = self._geometri_normal.size()
            self.setFixedSize(ukuran)
            self.move(self._geometri_normal.topLeft())
        else:
            self.setMinimumSize(0, 0)
            self.setMaximumSize(TINGGI_TAK_TERBATAS, TINGGI_TAK_TERBATAS)

    def tampilkan(self) -> None:
        """
        Buka jendela sesuai perannya.

        Layar yang menghadap pengunjung dibuka penuh sejak awal, tanpa
        bingkai jendela dan tanpa tombol tutup yang menggoda untuk ditekan.
        `--jendela` meniadakan itu: totem dibuka sebagai miniatur 50%
        dari kaca 1080×1920, supaya tiga pita terlihat utuh di laptop.
        """
        if self.mode_kios and not self.berjendela:
            self._kunci_ukuran_totem(False)
            self.showFullScreen()
            return
        self.show()
        if self.anjungan_totem:
            self._kunci_ukuran_totem(True)

    def ganti_layar_penuh(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            if self._geometri_normal is not None and self._geometri_normal.isValid():
                self.setGeometry(self._geometri_normal)
            self._kunci_ukuran_totem(True)
        else:
            self._geometri_normal = QRect(self.geometry())
            self._kunci_ukuran_totem(False)
            self.showFullScreen()

    def keluar_layar_penuh(self) -> None:
        """Turunkan layar penuh. Tidak melakukan apa-apa bila sudah jendela."""
        if self.isFullScreen():
            self.showNormal()
            if self._geometri_normal is not None and self._geometri_normal.isValid():
                self.setGeometry(self._geometri_normal)
            self._kunci_ukuran_totem(True)

    def _ganti_halaman(self, baris: int) -> None:
        if baris >= 0:
            self.halaman.setCurrentIndex(baris)

    def _pasang_bilah_database(self) -> None:
        """
        Widget tetap di kanan bilah status, supaya F5 tidak menghapusnya.

        showMessage("Data dimuat ulang.") bersifat sementara; widget biasa
        ikut tersembunyi, sedangkan permanent widget tetap terlihat. Itulah
        yang dibutuhkan petugas: lokasi server tidak boleh hilang hanya
        karena ia menyegarkan daftar antrian.
        """
        self._label_database = QLabel()
        self._label_database.setObjectName("statusDatabase")
        self._label_database.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
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

    def _tampilkan_status_database(self, terhubung: bool) -> None:
        label = getattr(self, "_label_database", None)
        if label is None:
            return
        label.setText(teks_status_database(terhubung=terhubung))
        label.setStyleSheet("" if terhubung else f"color: {DANGER};")

    def muat_ulang_halaman(self) -> None:
        halaman = self.halaman.currentWidget()
        if isinstance(halaman, PratinjauTotem):
            halaman = halaman.isi
        if hasattr(halaman, "muat_ulang"):
            halaman.muat_ulang()
            # statusBar() membuat bilah status baru bila belum ada, sehingga
            # tanpa penjagaan ini menekan F5 justru memunculkan bilah yang
            # sengaja tidak dibangun pada mode kios.
            if not self.mode_kios:
                self.statusBar().showMessage("Data dimuat ulang.", 2000)
                self._jadwalkan_periksa_database()

    def ganti_kata_sandi(self) -> None:
        ChangePasswordDialog(self.auth, self).exec()

    def keluar(self) -> None:
        # Mesin publik tidak pernah sampai ke layar masuk: keluar dari sana
        # mengembalikan ke pilihan layar. Menjanjikan "layar masuk" kepada
        # orang yang menekan Ctrl+Q di anjungan hanya membuatnya mengira
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
        pewaktu = getattr(self, "_pewaktu_db", None)
        if pewaktu is not None:
            pewaktu.stop()
        pemeriksa = getattr(self, "_pemeriksa_db", None)
        if pemeriksa is not None:
            try:
                pemeriksa.selesai.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                if pemeriksa.isRunning():
                    pemeriksa.wait(400)
            except RuntimeError:
                pass
        if self.auth.is_authenticated:
            self.auth.logout()
        super().closeEvent(event)
