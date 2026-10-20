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

from app.core.identitas import NAMA_TAMPIL
from app.core.errors import AppError
from app.core.logger import get_logger
from app.services.auth_service import AuthService, AuthSession
from app.ui.common import keterangan, label_error, tombol

logger = get_logger("ui.login")

# Tombol pemulihan admin baru muncul setelah sekian kali gagal masuk
# berturut-turut dengan nama pengguna yang sama.
GAGAL_SEBELUM_PEMULIHAN = 3


class LoginWindow(QDialog):
    """
    Jendela masuk.

    Kesalahan kredensial ditampilkan sebaris di dalam form, bukan sebagai
    kotak dialog. Petugas yang salah ketik cukup mengetik ulang tanpa
    harus menutup dialog terlebih dahulu.

    Aplikasi Windows sekarang khusus petugas. Karena itu tidak ada lagi
    layar pemilih mode di depannya: menutup dialog berarti menutup aplikasi,
    sedangkan pengaturan koneksi mesin tersedia langsung dari sini.
    """

    def __init__(self, auth: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.auth = auth
        self.session: AuthSession | None = None
        self._gagal_berturut = 0
        self._username_gagal = ""

        self.setWindowTitle(f"{NAMA_TAMPIL} — Masuk")
        self.setMinimumWidth(400)
        self._bangun_tampilan()

    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(32, 28, 32, 28)
        susunan.setSpacing(16)

        judul_aplikasi = QLabel(NAMA_TAMPIL)
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

        self.tombol_masuk = tombol("MASUK", variant="primary")
        self.tombol_masuk.clicked.connect(self.coba_masuk)
        susunan.addWidget(self.tombol_masuk)

        self.tombol_lupa = tombol("Lupa kata sandi admin?")
        self.tombol_lupa.setToolTip(
            "Pulihkan akun admin dengan kunci dari pengembang."
        )
        self.tombol_lupa.clicked.connect(self.lupa_kata_sandi)
        self.tombol_lupa.setVisible(False)
        susunan.addWidget(self.tombol_lupa)

        self.tombol_atur_komputer = tombol("Atur komputer ini")
        self.tombol_atur_komputer.setToolTip(
            "Atur komputer ini sebagai server, klien, atau satu komputer."
        )
        self.tombol_atur_komputer.clicked.connect(self.atur_komputer)
        susunan.addWidget(self.tombol_atur_komputer)

        # Enter pada isian, bukan tombol default dialog. Bila keduanya
        # aktif, Qt menjalankan login dua kali: yang kedua melihat isian
        # yang baru dikosongkan dan menampilkan "Kata sandi belum diisi."
        self.input_username.returnPressed.connect(self.coba_masuk)
        self.input_password.returnPressed.connect(self.coba_masuk)
        self.input_username.textChanged.connect(self._bersihkan_kesalahan)
        self.input_password.textChanged.connect(self._bersihkan_kesalahan)

        self.input_username.setFocus()

    # -----------------------------------------------------------------

    def _tampilkan_kesalahan(self, pesan: str) -> None:
        self.pesan_kesalahan.setText(pesan)
        self.pesan_kesalahan.setVisible(True)
        # Pengosongan memicu textChanged. Tanpa pemblokiran, pesan yang
        # baru tampil langsung dihapus lagi.
        self.input_password.blockSignals(True)
        self.input_password.clear()
        self.input_password.blockSignals(False)
        self.input_password.setFocus()

    def _bersihkan_kesalahan(self, _teks: str = "") -> None:
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
            self._catat_gagal(username)
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

    def _catat_gagal(self, username: str) -> None:
        """Hitung gagal berturut-turut; tombol pemulihan muncul di ambang."""
        if username != self._username_gagal:
            self._username_gagal = username
            self._gagal_berturut = 0
        self._gagal_berturut += 1
        if self._gagal_berturut >= GAGAL_SEBELUM_PEMULIHAN:
            self.tombol_lupa.setVisible(True)

    def lupa_kata_sandi(self) -> None:
        """Pemulihan akun admin lewat kunci dari pengembang."""
        from PySide6.QtWidgets import QDialog

        from app.ui.common import tampilkan_info
        from app.ui.login.pemulihan_admin_dialog import PemulihanAdminDialog

        dialog = PemulihanAdminDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.input_username.setText(dialog.username_dipulihkan or "")
        tampilkan_info(
            self,
            "Kata sandi telah dipulihkan. Masuk dengan kata sandi baru; Anda "
            "akan diminta menggantinya.",
            "Pemulihan admin",
        )

    def atur_komputer(self) -> None:
        """Buka pengaturan mesin tanpa harus berhasil masuk lebih dahulu."""
        from PySide6.QtWidgets import QDialog

        from app.core.mesin import env_url_mengalahkan
        from app.ui.common import tampilkan_info, tampilkan_peringatan
        from app.ui.login.setup_mesin_dialog import SetupMesinDialog

        dialog = SetupMesinDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if env_url_mengalahkan():
            tampilkan_peringatan(
                self,
                "Isian disimpan, tetapi ANTRIAN_DB_URL masih mengalahkan "
                "pengaturan komputer. Hapus variabel itu, lalu buka ulang aplikasi.",
                "Koneksi belum berubah",
            )
            return
        if dialog.memerlukan_buka_ulang:
            tampilkan_info(
                self,
                "Pengaturan komputer telah disimpan. Tutup aplikasi, lalu buka "
                "kembali agar koneksi baru dipakai.",
                "Komputer ini",
            )
