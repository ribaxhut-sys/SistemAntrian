"""Dialog penggantian kata sandi."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import AppError
from app.core.logger import get_logger
from app.core.security import MIN_PASSWORD_LENGTH
from app.services.auth_service import AuthService
from app.ui.common import judul, keterangan, label_error, pesan_untuk_user, tombol

logger = get_logger("ui.password")


class ChangePasswordDialog(QDialog):
    """
    Penggantian kata sandi sendiri.

    Dipakai dua keadaan: petugas mengganti kata sandi atas kemauan sendiri,
    dan petugas yang DIWAJIBKAN mengganti sebelum dapat bekerja. Pada
    keadaan kedua, dialog tidak dapat dibatalkan.
    """

    def __init__(
        self,
        auth: AuthService,
        parent: QWidget | None = None,
        *,
        wajib: bool = False,
    ) -> None:
        super().__init__(parent)
        self.auth = auth
        self.wajib = wajib

        self.setWindowTitle("Ganti Kata Sandi")
        self.setMinimumWidth(420)
        self._bangun_tampilan()

    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(28, 24, 28, 24)
        susunan.setSpacing(14)

        susunan.addWidget(judul("Ganti Kata Sandi"))

        if self.wajib:
            susunan.addWidget(
                keterangan(
                    "Kata sandi akun ini masih kata sandi bawaan yang tidak "
                    "rahasia. Ganti terlebih dahulu sebelum menggunakan aplikasi."
                )
            )
        else:
            susunan.addWidget(
                keterangan(f"Kata sandi baru minimal {MIN_PASSWORD_LENGTH} karakter.")
            )

        form = QFormLayout()
        form.setSpacing(12)

        self.input_lama = QLineEdit()
        self.input_lama.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Kata Sandi Lama", self.input_lama)

        self.input_baru = QLineEdit()
        self.input_baru.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Kata Sandi Baru", self.input_baru)

        self.input_ulangi = QLineEdit()
        self.input_ulangi.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Ulangi Kata Sandi Baru", self.input_ulangi)

        susunan.addLayout(form)

        self.pesan_kesalahan = label_error()
        susunan.addWidget(self.pesan_kesalahan)

        baris_tombol = QHBoxLayout()
        baris_tombol.addStretch()

        if not self.wajib:
            batal = tombol("Batal")
            batal.clicked.connect(self.reject)
            baris_tombol.addWidget(batal)

        self.tombol_simpan = tombol("SIMPAN", variant="primary", default=True)
        self.tombol_simpan.clicked.connect(self.simpan)
        baris_tombol.addWidget(self.tombol_simpan)

        susunan.addLayout(baris_tombol)

        for isian in (self.input_lama, self.input_baru, self.input_ulangi):
            isian.returnPressed.connect(self.simpan)

        self.input_lama.setFocus()

    # -----------------------------------------------------------------

    def _tampilkan_kesalahan(self, pesan: str, fokus: QLineEdit | None = None) -> None:
        self.pesan_kesalahan.setText(pesan)
        self.pesan_kesalahan.setVisible(True)
        if fokus is not None:
            fokus.setFocus()
            fokus.selectAll()

    def simpan(self) -> None:
        self.pesan_kesalahan.setVisible(False)

        lama = self.input_lama.text()
        baru = self.input_baru.text()
        ulangi = self.input_ulangi.text()

        if not lama:
            self._tampilkan_kesalahan("Kata sandi lama belum diisi.", self.input_lama)
            return
        if not baru:
            self._tampilkan_kesalahan("Kata sandi baru belum diisi.", self.input_baru)
            return
        if baru != ulangi:
            # Diperiksa di UI karena ini semata soal salah ketik, bukan
            # aturan bisnis. Service tidak perlu tahu soal isian "ulangi".
            self._tampilkan_kesalahan(
                "Ulangan kata sandi tidak sama.", self.input_ulangi
            )
            return

        self.tombol_simpan.setEnabled(False)
        try:
            self.auth.change_password(lama, baru)
        except AppError as exc:
            self._tampilkan_kesalahan(exc.user_message, self.input_lama)
            return
        except Exception as exc:  # noqa: BLE001 - batas UI
            logger.exception("Kesalahan tak terduga saat mengganti kata sandi")
            self._tampilkan_kesalahan(pesan_untuk_user(exc))
            return
        finally:
            self.tombol_simpan.setEnabled(True)

        self.accept()

    def reject(self) -> None:
        """Dialog wajib tidak dapat ditutup dengan Esc maupun tombol silang."""
        if self.wajib:
            return
        super().reject()
