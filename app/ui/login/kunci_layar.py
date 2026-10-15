"""
Kunci layar petugas setelah menganggur.

PC loket sering ditinggal sebentar dengan data pengaduan terbuka. Layar
menutup seluruh jendela dan meminta kata sandi akun yang sedang masuk. Nomor
yang sedang dipegang loket tidak dilepas; layar hanya disembunyikan.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import AppError
from app.services.auth_service import AuthService
from app.ui.common import judul, keterangan, tombol
from app.ui.style import BACKGROUND, DANGER

#: Jenis peristiwa yang dianggap aktivitas petugas.
_PERISTIWA_AKTIVITAS = (
    QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseMove,
    QEvent.Type.KeyPress,
    QEvent.Type.Wheel,
    QEvent.Type.TouchBegin,
)


class PengamatAktivitas(QObject):
    """Mencatat kapan terakhir ada papan ketik atau mouse yang disentuh."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.terakhir = time.monotonic()

    def eventFilter(self, sumber, event) -> bool:  # noqa: N802 - nama Qt
        if event.type() in _PERISTIWA_AKTIVITAS:
            self.terakhir = time.monotonic()
        return False

    def menganggur_detik(self) -> float:
        return time.monotonic() - self.terakhir

    def catat(self) -> None:
        self.terakhir = time.monotonic()


class KunciLayarDialog(QDialog):
    """Menutup jendela sampai kata sandi akun yang masuk dimasukkan."""

    def __init__(self, auth: AuthService, induk: QWidget | None = None) -> None:
        super().__init__(induk)
        self.auth = auth
        #: True bila petugas memilih keluar, bukan membuka kunci.
        self.keluar = False

        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setObjectName("kunciLayar")
        self.setStyleSheet(f"QDialog#kunciLayar {{ background: {BACKGROUND}; }}")
        if induk is not None:
            self.setGeometry(induk.frameGeometry())

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(40, 40, 40, 40)
        susunan.addStretch(1)

        sesi = auth.current_session
        nama = sesi.full_name if sesi is not None else ""
        kepala = judul("Layar dikunci")
        kepala.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(kepala)
        ket = keterangan(
            f"Tidak ada aktivitas. Masukkan kata sandi {nama} untuk melanjutkan."
        )
        ket.setAlignment(Qt.AlignmentFlag.AlignCenter)
        susunan.addWidget(ket)

        self.isian = QLineEdit()
        self.isian.setEchoMode(QLineEdit.EchoMode.Password)
        self.isian.setPlaceholderText("Kata sandi")
        self.isian.setMaximumWidth(320)
        self.isian.returnPressed.connect(self.coba_buka)
        susunan.addWidget(self.isian, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.label_galat = QLabel("")
        self.label_galat.setStyleSheet(f"color: {DANGER};")
        self.label_galat.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_galat.setWordWrap(True)
        susunan.addWidget(self.label_galat)

        self.tombol_buka: QPushButton = tombol("Buka", variant="primary", default=True)
        self.tombol_buka.clicked.connect(self.coba_buka)
        susunan.addWidget(self.tombol_buka, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.tombol_keluar: QPushButton = tombol("Keluar dari aplikasi")
        self.tombol_keluar.clicked.connect(self._pilih_keluar)
        susunan.addWidget(self.tombol_keluar, alignment=Qt.AlignmentFlag.AlignHCenter)
        susunan.addStretch(2)

    def coba_buka(self) -> None:
        try:
            sah = self.auth.verifikasi_kata_sandi(self.isian.text())
        except AppError as exc:
            self.label_galat.setText(exc.user_message)
            self.isian.clear()
            return
        if sah:
            self.isian.clear()
            self.accept()
            return
        self.label_galat.setText("Kata sandi salah.")
        self.isian.clear()
        self.isian.setFocus()

    def _pilih_keluar(self) -> None:
        self.keluar = True
        self.reject()

    def reject(self) -> None:  # noqa: D102 - Esc tidak boleh menutup kunci
        if self.keluar:
            super().reject()
