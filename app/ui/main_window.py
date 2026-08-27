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
from app.services.sound_service import buat_pemutar
from app.services.survey_service import SurveyService
from app.services.ticket_service import TicketService, buat_printer
from app.services.user_service import UserService
from app.ui.common import judul, keterangan, konfirmasi, tombol
from app.ui.dashboard.dashboard_page import DashboardPage
from app.ui.login.change_password_dialog import ChangePasswordDialog
from app.ui.settings.dialogs import LABEL_PERAN
from app.ui.display.display_page import DisplayPage
from app.ui.queue.service_page import ServicePage
from app.ui.registration.registration_page import RegistrationPage
from app.ui.settings.backup_page import BackupPage
from app.ui.settings.master_data_page import MasterDataPage
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
        self.auth = auth
        self.master_service = MasterDataService(auth)
        self.user_service = UserService(auth)
        self.queue_service = QueueService(auth)
        self.settings_service = SettingsService(auth)
        self.survey_service = SurveyService(auth)
        self.dashboard_service = DashboardService(auth)
        self.backup_service = BackupService(auth, self.settings_service)

        config = get_config()
        self.ticket_service = TicketService(
            buat_printer(
                self.settings_service.get("ticket.printer", "pdf"),
                config.base_dir / "tiket",
            ),
            self.settings_service,
            self.master_service,
        )
        # Pemutar suara dibuat sekali dan dipakai bersama, supaya tidak ada
        # dua sumber bunyi yang berebut perangkat audio.
        self.sound_player = buat_pemutar(
            self.settings_service.get_bool("display.sound_enabled", True)
        )

        sesi = auth.require_session()
        self.setWindowTitle(f"{APP_NAME} — {sesi.full_name}")
        self.resize(1100, 700)

        self._bangun_tampilan()
        self._pasang_pintasan()

    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        pusat = QWidget()
        susunan_utama = QVBoxLayout(pusat)
        susunan_utama.setContentsMargins(0, 0, 0, 0)
        susunan_utama.setSpacing(0)

        susunan_utama.addWidget(self._bangun_kepala())

        isi = QWidget()
        susunan_isi = QHBoxLayout(isi)
        susunan_isi.setContentsMargins(0, 0, 0, 0)
        susunan_isi.setSpacing(0)

        self.navigasi = QListWidget()
        self.navigasi.setObjectName("navigasi")
        self.navigasi.setFixedWidth(220)
        self.navigasi.currentRowChanged.connect(self._ganti_halaman)
        susunan_isi.addWidget(self.navigasi)

        self.halaman = QStackedWidget()
        susunan_isi.addWidget(self.halaman, stretch=1)

        susunan_utama.addWidget(isi, stretch=1)
        self.setCentralWidget(pusat)

        self._susun_menu()

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
                ),
            ),
            _Menu(
                "Survey Kepuasan",
                Permission.SURVEY_SUBMIT,
                lambda: SurveyPage(self.survey_service, self.settings_service),
            ),
            _Menu(
                "Data Master",
                Permission.MASTER_MANAGE,
                lambda: MasterDataPage(self.master_service, self.user_service),
            ),
            _Menu(
                "Backup & Audit",
                Permission.BACKUP_MANAGE,
                lambda: BackupPage(self.backup_service),
            ),
            _Menu(
                "Layar Antrian",
                Permission.DISPLAY_VIEW,
                lambda: DisplayPage(
                    self.queue_service, self.settings_service, self.sound_player
                ),
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
        ]

        self.menu_aktif: list[_Menu] = []
        for butir in daftar:
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

    # -----------------------------------------------------------------

    def _ganti_halaman(self, baris: int) -> None:
        if baris >= 0:
            self.halaman.setCurrentIndex(baris)

    def muat_ulang_halaman(self) -> None:
        halaman = self.halaman.currentWidget()
        if hasattr(halaman, "muat_ulang"):
            halaman.muat_ulang()
            self.statusBar().showMessage("Data dimuat ulang.", 2000)

    def ganti_kata_sandi(self) -> None:
        ChangePasswordDialog(self.auth, self).exec()

    def keluar(self) -> None:
        if not konfirmasi(self, "Keluar dari aplikasi?"):
            return
        self.auth.logout()
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - nama dari Qt
        """Pastikan sesi berakhir walau jendela ditutup lewat tombol silang."""
        if self.auth.is_authenticated:
            self.auth.logout()
        super().closeEvent(event)
