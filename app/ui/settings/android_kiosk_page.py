"""Kontrol server API yang menghubungkan aplikasi Windows dengan anjungan Android."""

from __future__ import annotations

import ipaddress
import os
import socket
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import get_config
from app.services.kiosk_server import (
    api_sudah_berjalan,
    muat_api_otomatis,
    muat_token_pengguna,
    siapkan_firewall,
    simpan_api_otomatis,
    simpan_token_pengguna,
    token_baru,
)
from app.ui.common import judul, keterangan, tombol


def alamat_ipv4_lan() -> list[str]:
    """Kembalikan alamat IPv4 privat yang mungkin dipakai klien Android."""
    try:
        hasil = {
            info[4][0]
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
            if ipaddress.ip_address(info[4][0]).is_private
            and not ipaddress.ip_address(info[4][0]).is_loopback
        }
    except OSError:
        return []
    return sorted(
        hasil, key=lambda alamat: tuple(int(bagian) for bagian in alamat.split("."))
    )


class AndroidKioskServerPage(QWidget):
    """Halaman untuk mengatur akses jaringan dan menjalankan API anjungan."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._server_process: QProcess | None = None
        self._alamat = alamat_ipv4_lan()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)
        layout.addWidget(judul("Server Anjungan Android"))
        layout.addWidget(
            keterangan(
                "Server ini berjalan di komputer Windows, memakai database aplikasi "
                "yang sedang aktif, dan menerima koneksi anjungan melalui jaringan lokal."
            )
        )

        token_label = QLabel("Token API (salin ke Pengaturan Server di Android)")
        self.token = QLineEdit(
            os.environ.get("ANTRIAN_KIOS_API_TOKEN", "").strip()
            or muat_token_pengguna()
            or token_baru()
        )
        self.token.setReadOnly(True)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        token_row = QHBoxLayout()
        token_row.addWidget(self.token, stretch=1)
        self.tampilkan_token = tombol("Tampilkan")
        self.tampilkan_token.clicked.connect(self._ubah_tampilan_token)
        token_row.addWidget(self.tampilkan_token)
        self.ganti_token = tombol("Buat token baru")
        self.ganti_token.clicked.connect(self._buat_token_baru)

        alamat = ", ".join(self._alamat) if self._alamat else (
            "Alamat IPv4 belum terdeteksi; periksa dengan perintah ipconfig."
        )
        self.alamat = QLabel(f"Alamat komputer ini: {alamat}")
        self.alamat.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.alamat.setWordWrap(True)
        api_running = api_sudah_berjalan(
            int(os.environ.get("ANTRIAN_KIOS_API_PORT", "8765"))
        )
        self.status = QLabel(
            "API aktif di latar hingga PC dimatikan."
            if api_running
            else "API belum dijalankan."
        )
        self.status.setWordWrap(True)

        self.mulai = tombol(
            "Siapkan Firewall & Jalankan Server" if not api_running
            else "API Sudah Berjalan",
            variant="primary",
        )
        self.mulai.setEnabled(not api_running)
        self.mulai.clicked.connect(self._siapkan_dan_mulai)
        self.hentikan = tombol("Hentikan Server")
        self.hentikan.setEnabled(False)
        self.hentikan.clicked.connect(self._hentikan_server)
        self.api_otomatis = QCheckBox(
            "Mulai API otomatis saat aplikasi Windows dibuka; "
            "API tetap hidup sampai PC dimatikan"
        )
        self.api_otomatis.setToolTip(
            "Berlaku untuk komputer yang peran databasenya SERVER. "
            "Gunakan akun Windows yang sama saat mengatur dan menjalankan aplikasi."
        )
        self.api_otomatis.setChecked(muat_api_otomatis())
        self.api_otomatis.toggled.connect(self._ubah_api_otomatis)

        layout.addWidget(token_label)
        layout.addLayout(token_row)
        layout.addWidget(self.ganti_token, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.alamat)
        layout.addWidget(
            keterangan(
                "Di BlueStacks, masukkan http://IP-KOMPUTER:8765 dan token di atas. "
                "Pilih IP yang dapat dijangkau dari BlueStacks; jangan gunakan localhost. "
                "Profil jaringan Windows harus Private."
            )
        )
        layout.addWidget(self.mulai, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.api_otomatis)
        layout.addWidget(self.hentikan, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.status)
        layout.addStretch()

    def _ubah_tampilan_token(self) -> None:
        if self.token.echoMode() == QLineEdit.EchoMode.Password:
            self.token.setEchoMode(QLineEdit.EchoMode.Normal)
            self.tampilkan_token.setText("Sembunyikan")
        else:
            self.token.setEchoMode(QLineEdit.EchoMode.Password)
            self.tampilkan_token.setText("Tampilkan")

    def _buat_token_baru(self) -> None:
        if self._server_process is not None:
            QMessageBox.warning(
                self, "Server sedang berjalan",
                "Hentikan server sebelum membuat token baru.",
            )
            return
        self.token.setText(token_baru())

    def _ubah_api_otomatis(self, aktif: bool) -> None:
        try:
            simpan_api_otomatis(aktif)
        except (OSError, RuntimeError) as exc:
            self.api_otomatis.blockSignals(True)
            self.api_otomatis.setChecked(not aktif)
            self.api_otomatis.blockSignals(False)
            QMessageBox.warning(
                self, "Gagal menyimpan pengaturan", str(exc)
            )
            return
        if aktif:
            self.status.setText(
                "API akan mulai otomatis saat aplikasi Windows dibuka lagi. "
                "Pastikan token dan Firewall sudah disiapkan."
            )
        elif not api_sudah_berjalan(
            int(os.environ.get("ANTRIAN_KIOS_API_PORT", "8765"))
        ):
            self.status.setText("API otomatis dinonaktifkan.")

    def _siapkan_dan_mulai(self) -> None:
        if self._server_process is not None:
            return
        if len(self.token.text().strip()) < 8:
            QMessageBox.warning(
                self, "Token tidak valid", "Token API harus minimal 8 karakter."
            )
            return
        try:
            simpan_token_pengguna(self.token.text())
            siapkan_firewall()
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "Gagal menyiapkan server", str(exc))
            return

        process = QProcess(self)
        process.setProgram(sys.executable)
        if getattr(sys, "frozen", False):
            process.setArguments(["--kios-api"])
        else:
            process.setArguments(["-m", "app.main", "--kios-api"])
        process.setWorkingDirectory(str(get_config().base_dir))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("ANTRIAN_KIOS_API_TOKEN", self.token.text())
        process.setProcessEnvironment(environment)
        log_dir = get_config().log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        process.setStandardOutputFile(str(log_dir / "kiosk-api-stdout.log"))
        process.setStandardErrorFile(str(log_dir / "kiosk-api-stderr.log"))
        process.started.connect(self._server_started)
        process.finished.connect(self._server_finished)
        process.errorOccurred.connect(self._server_error)
        self._server_process = process
        self.mulai.setEnabled(False)
        self.status.setText("Menjalankan server API…")
        process.start()

    def _server_started(self) -> None:
        self.status.setText(
            "Server API sudah dijalankan. Tetap buka aplikasi ini selama "
            "anjungan Android digunakan."
        )
        self.hentikan.setEnabled(True)

    def _server_error(self, error: QProcess.ProcessError) -> None:
        process = self._server_process
        detail = process.errorString() if process is not None else str(error)
        self.status.setText(f"Server gagal dijalankan: {detail}")
        if error == QProcess.ProcessError.FailedToStart:
            self._server_process = None
        self.mulai.setEnabled(True)
        self.hentikan.setEnabled(False)

    def _server_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        self._server_process = None
        self.mulai.setEnabled(True)
        self.hentikan.setEnabled(False)
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self.status.setText("Server dihentikan.")
        else:
            self.status.setText(
                "Server berhenti atau gagal mulai. Periksa logs\\app.log "
                "dan logs\\kiosk-api-stderr.log."
            )

    def _hentikan_server(self) -> None:
        process = self._server_process
        if process is None:
            return
        process.terminate()
        if not process.waitForFinished(3000):
            process.kill()
            process.waitForFinished(1000)

    def hentikan_server(self) -> None:
        """Hentikan proses API saat aplikasi Windows ditutup."""
        self._hentikan_server()
