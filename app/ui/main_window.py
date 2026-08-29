"""Jendela utama aplikasi."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.config import APP_NAME, get_config
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
from app.ui.notes.note_page import NotePage
from app.ui.queue.service_page import ServicePage
from app.ui.registration.registration_page import RegistrationPage
from app.ui.settings.backup_page import BackupPage
from app.ui.settings.close_day_page import CloseDayPage
from app.ui.settings.master_data_page import MasterDataPage
from app.ui.settings.settings_page import SettingsPage
from app.ui.survey.survey_page import SurveyPage

logger = get_logger("ui.main")


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
    Kerangka aplikasi: kepala, navigasi kiri, dan isi halaman.

    Menu disusun berdasarkan hak akses sesi yang sedang berjalan. Petugas
    tidak melihat menu yang memang bukan urusannya. Penegakan sebenarnya
    tetap di service layer; menu ini hanya mengurangi kebingungan.
    """

    def __init__(self, auth: AuthService, parent: QWidget | None = None) -> None:
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
        # di kiri, daftar tunggu di kanan. Pada 1100 px kolom kanan terdesak
        # sampai nama layanan terpotong menjadi "Kons…". 1280 x 720 masih
        # muat utuh pada layar 1366 x 768 yang paling sempit di kantor.
        self.resize(1280, 720)

        self._bangun_tampilan()
        self._pasang_pintasan()

    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        pusat = QWidget()
        susunan_utama = QVBoxLayout(pusat)
        susunan_utama.setContentsMargins(0, 0, 0, 0)
        susunan_utama.setSpacing(0)

        # Pada mode kios, bilah atas tidak dibangun sama sekali. Isinya —
        # nama petugas, tombol Ganti Kata Sandi, dan tombol Keluar — bukan
        # konsumsi pengunjung, dan tombol Keluar yang terlihat di layar
        # publik mengundang orang menutupnya.
        if not self.mode_kios:
            susunan_utama.addWidget(self._bangun_kepala())

        isi = QWidget()
        susunan_isi = QHBoxLayout(isi)
        susunan_isi.setContentsMargins(0, 0, 0, 0)
        susunan_isi.setSpacing(0)

        # Widget navigasi tetap dibuat walau tidak ditampilkan, supaya
        # penyusunan menu berjalan seperti biasa dan pemeriksaan hak akses
        # tetap melewati jalur yang sama.
        self.navigasi = QListWidget()
        self.navigasi.setObjectName("navigasi")
        self.navigasi.setFixedWidth(220)
        self.navigasi.currentRowChanged.connect(self._ganti_halaman)
        if not self.mode_kios:
            susunan_isi.addWidget(self.navigasi)

        self.halaman = QStackedWidget()
        susunan_isi.addWidget(self.halaman, stretch=1)

        susunan_utama.addWidget(isi, stretch=1)
        self.setCentralWidget(pusat)

        self._susun_menu()

        # Bilah status memuat lokasi lengkap file database. Tidak ada
        # alasan pengunjung perlu mengetahuinya.
        if not self.mode_kios:
            config = get_config()
            self.statusBar().showMessage(f"Database: {config.db_path}")

    def _bangun_kepala(self) -> QWidget:
        kepala = QFrame()
        kepala.setObjectName("panelHeader")
        kepala.setFixedHeight(64)

        susunan = QHBoxLayout(kepala)
        susunan.setContentsMargins(20, 10, 20, 10)
        susunan.setSpacing(12)

        sesi = self.auth.require_session()

        nama = QLabel(APP_NAME)
        nama.setProperty("heading", "true")
        susunan.addWidget(nama)
        susunan.addStretch()

        identitas = QLabel(
            f"{sesi.full_name}  ·  {LABEL_PERAN.get(sesi.role, sesi.role.value)}"
        )
        identitas.setProperty("muted", "true")
        susunan.addWidget(identitas)

        ganti = tombol("Ganti Kata Sandi")
        ganti.clicked.connect(self.ganti_kata_sandi)
        susunan.addWidget(ganti)

        keluar = tombol("Keluar", variant="danger")
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
                "Pengaduan & Catatan",
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
                lambda: SettingsPage(self.settings_service),
            ),
            _Menu(
                "Backup & Audit",
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
                lambda: KioskPage(
                    self.queue_service,
                    self.master_service,
                    self.settings_service,
                    self.sound_player,
                    self.ticket_service,
                ),
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
            self.halaman.addWidget(
                PlaceholderPage(
                    "Tidak ada menu tersedia",
                    "Akun Anda belum memiliki akses ke menu mana pun. "
                    "Hubungi administrator.",
                )
            )
            return

        self.navigasi.setCurrentRow(0)

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

    # -----------------------------------------------------------------

    def tampilkan(self) -> None:
        """
        Buka jendela sesuai perannya.

        Layar yang menghadap pengunjung dibuka penuh sejak awal, tanpa
        bingkai jendela dan tanpa tombol tutup yang menggoda untuk ditekan.
        """
        if self.mode_kios:
            self.showFullScreen()
        else:
            self.show()

    def ganti_layar_penuh(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keluar_layar_penuh(self) -> None:
        """Turunkan layar penuh. Tidak melakukan apa-apa bila sudah jendela."""
        if self.isFullScreen():
            self.showNormal()

    def _ganti_halaman(self, baris: int) -> None:
        if baris >= 0:
            self.halaman.setCurrentIndex(baris)

    def muat_ulang_halaman(self) -> None:
        halaman = self.halaman.currentWidget()
        if hasattr(halaman, "muat_ulang"):
            halaman.muat_ulang()
            # statusBar() membuat bilah status baru bila belum ada, sehingga
            # tanpa penjagaan ini menekan F5 justru memunculkan bilah yang
            # sengaja tidak dibangun pada mode kios.
            if not self.mode_kios:
                self.statusBar().showMessage("Data dimuat ulang.", 2000)

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
        if self.auth.is_authenticated:
            self.auth.logout()
        super().closeEvent(event)
