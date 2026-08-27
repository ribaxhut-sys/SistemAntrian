"""Layar masuk."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.config import APP_NAME
from app.core.errors import AppError
from app.core.logger import get_logger
from app.services.auth_service import AuthService, AuthSession
from app.ui.common import keterangan, label_error, pesan_untuk_user, tombol

logger = get_logger("ui.login")


class LoginWindow(QDialog):
    """
    Jendela masuk.

    Kesalahan kredensial ditampilkan sebaris di dalam form, bukan sebagai
    kotak dialog. Petugas yang salah ketik cukup mengetik ulang tanpa
    harus menutup dialog terlebih dahulu.
    """

    def __init__(self, auth: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.auth = auth
        self.session: AuthSession | None = None

        self.setWindowTitle(f"{APP_NAME} — Masuk")
        self.setMinimumWidth(400)
        self._bangun_tampilan()

    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(32, 28, 32, 28)
        susunan.setSpacing(16)

        judul_aplikasi = QLabel(APP_NAME)
        judul_aplikasi.setProperty("heading", "true")
        judul_aplikasi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(judul_aplikasi)

        susunan.addWidget(
            keterangan("Masukkan nama pengguna dan kata sandi Anda.")
        )

        garis = QFrame()
        garis.setFrameShape(QFrame.Shape.HLine)
        garis.setFrameShadow(QFrame.Shadow.Sunken)
        susunan.addWidget(garis)

        form = QFormLayout()
        form.setSpacing(12)

        self.input_username = QLineEdit()
        self.input_username.setPlaceholderText("nama pengguna")
        self.input_username.setMaxLength(50)
        form.addRow("Nama Pengguna", self.input_username)

        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setPlaceholderText("kata sandi")
        form.addRow("Kata Sandi", self.input_password)

        susunan.addLayout(form)

        self.pesan_kesalahan = label_error()
        susunan.addWidget(self.pesan_kesalahan)

        self.tombol_masuk = tombol("MASUK", variant="primary", default=True)
        self.tombol_masuk.clicked.connect(self.coba_masuk)
        susunan.addWidget(self.tombol_masuk)

        self.tombol_keluar = tombol("Keluar")
        self.tombol_keluar.clicked.connect(self.reject)
        susunan.addWidget(self.tombol_keluar)

        # Enter pada salah satu isian langsung mencoba masuk: petugas
        # mengetik nama pengguna, Tab, kata sandi, Enter — tanpa menyentuh mouse.
        self.input_username.returnPressed.connect(self.coba_masuk)
        self.input_password.returnPressed.connect(self.coba_masuk)

        self.input_username.setFocus()

    # -----------------------------------------------------------------

    def _tampilkan_kesalahan(self, pesan: str) -> None:
        self.pesan_kesalahan.setText(pesan)
        self.pesan_kesalahan.setVisible(True)
        self.input_password.clear()
        self.input_password.setFocus()

    def _bersihkan_kesalahan(self) -> None:
        self.pesan_kesalahan.setVisible(False)
        self.pesan_kesalahan.setText("")

    def coba_masuk(self) -> None:
        """Coba masuk dengan isian saat ini."""
        self._bersihkan_kesalahan()

        username = self.input_username.text().strip()
        password = self.input_password.text()

        if not username:
            self._tampilkan_kesalahan("Nama pengguna belum diisi.")
            self.input_username.setFocus()
            return
        if not password:
            self._tampilkan_kesalahan("Kata sandi belum diisi.")
            return

        self.tombol_masuk.setEnabled(False)
        try:
            self.session = self.auth.login(username, password)
        except AppError as exc:
            self._tampilkan_kesalahan(exc.user_message)
            return
        except Exception:  # noqa: BLE001 - batas UI
            logger.exception("Kesalahan tak terduga saat masuk")
            self._tampilkan_kesalahan(
                "Terjadi kesalahan yang tidak terduga. Silakan coba kembali."
            )
            return
        finally:
            self.tombol_masuk.setEnabled(True)

        self.accept()
