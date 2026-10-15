"""
Layar "Lupa kata sandi admin": pemulihan dengan kunci dari pengembang.

Alurnya (lihat `app/services/pemulihan_admin.py`): buat kode tantangan,
kirim kepada pengembang, tempel kunci respons yang diterima, lalu pilih
kata sandi baru.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import AppError
from app.services import pemulihan_admin as pa
from app.ui.common import judul, keterangan, label_error, tombol


class PemulihanAdminDialog(QDialog):
    """Pulihkan akun admin dengan kunci respons dari pengembang."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        kunci_publik_b64: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pemulihan akun admin")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._kunci = kunci_publik_b64
        #: Nama akun yang berhasil dipulihkan; None sebelum berhasil.
        self.username_dipulihkan: str | None = None

        susunan = QVBoxLayout(self)
        susunan.setSpacing(10)
        susunan.addWidget(judul("Pemulihan akun admin"))

        self.label_nonaktif = keterangan(
            "Pemulihan lewat pengembang belum diaktifkan pada pemasangan ini. "
            "Minta admin lain menyetel ulang kata sandi lewat Data Master."
        )
        self.label_nonaktif.setVisible(not pa.kunci_terpasang(self._kunci))
        susunan.addWidget(self.label_nonaktif)

        susunan.addWidget(
            keterangan(
                "1. Buat kode tantangan dan kirim kepada pengembang.\n"
                "2. Tempel kunci respons yang Anda terima.\n"
                "3. Pilih kata sandi baru (minimal 8 karakter)."
            )
        )

        self.input_username = QLineEdit("admin")
        form = QFormLayout()
        form.addRow("Akun admin", self.input_username)
        susunan.addLayout(form)

        self.tombol_buat = tombol("Buat kode tantangan")
        self.tombol_buat.clicked.connect(self.buat_tantangan)
        susunan.addWidget(self.tombol_buat)

        self.kotak_tantangan = QPlainTextEdit()
        self.kotak_tantangan.setReadOnly(True)
        self.kotak_tantangan.setMaximumHeight(70)
        self.kotak_tantangan.setPlaceholderText("Kode tantangan akan tampil di sini.")
        susunan.addWidget(self.kotak_tantangan)

        baris_salin = QHBoxLayout()
        self.tombol_salin = tombol("Salin kode")
        self.tombol_salin.clicked.connect(self._salin)
        baris_salin.addWidget(self.tombol_salin)
        baris_salin.addStretch()
        susunan.addLayout(baris_salin)

        susunan.addWidget(QLabel("Kunci respons dari pengembang"))
        self.kotak_respons = QPlainTextEdit()
        self.kotak_respons.setMaximumHeight(90)
        self.kotak_respons.setPlaceholderText("RESP-...")
        susunan.addWidget(self.kotak_respons)

        form2 = QFormLayout()
        self.input_sandi = QLineEdit()
        self.input_sandi.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_ulang = QLineEdit()
        self.input_ulang.setEchoMode(QLineEdit.EchoMode.Password)
        form2.addRow("Kata sandi baru", self.input_sandi)
        form2.addRow("Ulangi kata sandi", self.input_ulang)
        susunan.addLayout(form2)

        self.pesan = label_error()
        susunan.addWidget(self.pesan)

        baris = QHBoxLayout()
        baris.addStretch()
        self.tombol_batal = tombol("Batal")
        self.tombol_batal.clicked.connect(self.reject)
        baris.addWidget(self.tombol_batal)
        self.tombol_pulihkan = tombol("PULIHKAN", variant="primary")
        self.tombol_pulihkan.clicked.connect(self.pulihkan)
        baris.addWidget(self.tombol_pulihkan)
        susunan.addLayout(baris)

        if not pa.kunci_terpasang(self._kunci):
            for widget in (
                self.input_username,
                self.tombol_buat,
                self.kotak_respons,
                self.input_sandi,
                self.input_ulang,
                self.tombol_pulihkan,
                self.tombol_salin,
            ):
                widget.setEnabled(False)

    # -----------------------------------------------------------------

    def _tampilkan_galat(self, teks: str) -> None:
        self.pesan.setText(teks)
        self.pesan.setVisible(bool(teks))

    def buat_tantangan(self) -> None:
        self._tampilkan_galat("")
        try:
            kode = pa.buat_tantangan(self.input_username.text())
        except AppError as exc:
            self._tampilkan_galat(exc.user_message)
            return
        self.kotak_tantangan.setPlainText(kode)

    def _salin(self) -> None:
        QApplication.clipboard().setText(self.kotak_tantangan.toPlainText())

    def pulihkan(self) -> None:
        self._tampilkan_galat("")
        tantangan = self.kotak_tantangan.toPlainText().strip()
        if not tantangan:
            self._tampilkan_galat("Buat kode tantangan lebih dahulu.")
            return
        if self.input_sandi.text() != self.input_ulang.text():
            self._tampilkan_galat("Kata sandi baru tidak sama.")
            return
        try:
            self.username_dipulihkan = pa.pulihkan(
                tantangan,
                self.kotak_respons.toPlainText().strip(),
                self.input_sandi.text(),
                kunci_publik_b64=self._kunci,
            )
        except AppError as exc:
            self._tampilkan_galat(exc.user_message)
            self.input_sandi.clear()
            self.input_ulang.clear()
            return
        self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - nama Qt
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return  # Enter di kotak teks tidak boleh memicu pemulihan
        super().keyPressEvent(event)
