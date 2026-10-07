"""
Layanan Anjungan: API yang dipakai anjungan Android untuk mengambil nomor.

Halaman ini hanya muncul di komputer SERVER. Anjungan Android hanya
klien; ia tidak punya database dan menyambung ke komputer ini.

Pemeriksaan status (PowerShell untuk Task Scheduler dan Firewall) dan
pemasangan (yang menunggu jawaban dialog UAC) dijalankan di utas sendiri,
supaya jendela tidak membeku selama Windows menjawab.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.config import get_config
from app.services.apk_anjungan import VERSI_MINIMAL, InfoApk, folder_apk, info_apk
from app.services.kiosk_server import (
    StatusTugas,
    _firewall_sudah_siap,
    api_sudah_berjalan,
    hapus_layanan_api,
    muat_api_otomatis,
    muat_token,
    pasang_layanan_api,
    perintah_api,
    port_api,
    simpan_api_otomatis,
    simpan_token,
    status_tugas_api,
    token_baru,
)
from app.ui.common import judul, keterangan, konfirmasi, tampilkan_peringatan, tombol
from app.ui.style import DANGER, SUCCESS, TEXT_MUTED, WARNING


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


@dataclass(frozen=True)
class StatusLayanan:
    api: bool
    tugas: StatusTugas
    firewall: bool
    apk: InfoApk | None = None


def periksa_status() -> StatusLayanan:
    return StatusLayanan(
        api=api_sudah_berjalan(port_api()),
        tugas=status_tugas_api(),
        firewall=_firewall_sudah_siap(),
        apk=info_apk(folder_apk(get_config().base_dir)),
    )


class _Pekerja(QObject):
    """Jalankan satu fungsi di utas lain; hasil atau galat kembali lewat sinyal."""

    selesai = Signal(object)
    gagal = Signal(object)

    def jalankan(self, fungsi: Callable[[], object]) -> None:
        def kerja() -> None:
            try:
                hasil = fungsi()
            except Exception as exc:  # noqa: BLE001 - diteruskan ke layar
                self.gagal.emit(exc)
            else:
                self.selesai.emit(hasil)

        threading.Thread(target=kerja, daemon=True).start()


LABEL_PASANG = "Pasang & nyalakan"
LABEL_PASANG_ULANG = "Pasang ulang & nyalakan ulang"


def _teks_tombol(label: str) -> str:
    """Qt membaca & sebagai pintasan keyboard; && menampilkannya apa adanya."""
    return label.replace("&", "&&")


#: (warna titik, teks lencana)
_NORMAL = (SUCCESS, "Normal")
_BELUM = (WARNING, "Belum")
_TINDAKAN = (DANGER, "Perlu tindakan")
_MEMERIKSA = (TEXT_MUTED, "Memeriksa…")


class _BarisStatus:
    def __init__(self, grid: QGridLayout, baris: int, nama: str) -> None:
        label = QLabel(nama)
        label.setStyleSheet("font-weight: 600;")
        self.titik = QLabel("●")
        self.teks = QLabel()
        self.teks.setWordWrap(True)
        self.lencana = QLabel()
        grid.addWidget(label, baris, 0)
        grid.addWidget(self.titik, baris, 1)
        grid.addWidget(self.teks, baris, 2)
        grid.addWidget(self.lencana, baris, 3, alignment=Qt.AlignmentFlag.AlignRight)

    def setel(self, keadaan: tuple[str, str], teks: str) -> None:
        warna, lencana = keadaan
        self.titik.setStyleSheet(f"color: {warna};")
        self.teks.setText(teks)
        self.lencana.setText(lencana)
        self.lencana.setStyleSheet(f"color: {warna}; font-weight: 600;")


def _kartu(judul_kartu: str) -> tuple[QFrame, QVBoxLayout]:
    kartu = QFrame()
    kartu.setObjectName("kartuLayanan")
    kartu.setStyleSheet(
        "QFrame#kartuLayanan { background: #FFFFFF; border: 1px solid #E2E8F0;"
        " border-radius: 10px; }"
    )
    isi = QVBoxLayout(kartu)
    isi.setContentsMargins(18, 14, 18, 14)
    kepala = QLabel(judul_kartu.upper())
    kepala.setStyleSheet(f"color: {TEXT_MUTED}; font-weight: 600; letter-spacing: 1px;")
    isi.addWidget(kepala)
    return kartu, isi


class LayananAnjunganPage(QWidget):
    """Status, pemasangan, dan data sambungan API anjungan di komputer server."""

    def __init__(self, perangkat=None, parent: QWidget | None = None) -> None:
        """`perangkat`: PerangkatService; tanpa itu kartu Perangkat tidak dibangun."""
        super().__init__(parent)
        self._sibuk = False
        self._status: StatusLayanan | None = None
        self._alamat = alamat_ipv4_lan()

        # Isi halaman lebih tinggi dari jendela 1280x720 sejak ada daftar
        # perangkat, jadi seluruhnya digulir.
        luar = QVBoxLayout(self)
        luar.setContentsMargins(0, 0, 0, 0)
        gulir = QScrollArea()
        gulir.setWidgetResizable(True)
        gulir.setFrameShape(QFrame.Shape.NoFrame)
        isi_halaman = QWidget()
        gulir.setWidget(isi_halaman)
        luar.addWidget(gulir)

        layout = QVBoxLayout(isi_halaman)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)
        layout.addWidget(judul("Layanan Anjungan"))
        layout.addWidget(
            keterangan(
                "Anjungan Android hanya mengambil nomor dan harus tersambung ke "
                "komputer server ini. Halaman ini hanya muncul di komputer server."
            )
        )

        # --- Status ---------------------------------------------------------
        kartu_status, isi_status = _kartu("Status")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(2, 1)
        self.baris_api = _BarisStatus(grid, 0, "API")
        self.baris_tugas = _BarisStatus(grid, 1, "Task Scheduler")
        self.baris_firewall = _BarisStatus(grid, 2, "Firewall")
        self.baris_apk = _BarisStatus(grid, 3, "APK anjungan")
        for baris in (self.baris_api, self.baris_tugas, self.baris_firewall, self.baris_apk):
            baris.setel(_MEMERIKSA, "")
        isi_status.addLayout(grid)
        layout.addWidget(kartu_status)

        # --- Sambungkan tablet ----------------------------------------------
        kartu_tablet, isi_tablet = _kartu("Sambungkan tablet")
        grid_tablet = QGridLayout()
        grid_tablet.setHorizontalSpacing(8)
        grid_tablet.setColumnStretch(1, 1)

        grid_tablet.addWidget(QLabel("Alamat server"), 0, 0)
        alamat = (
            f"http://{self._alamat[0]}:{port_api()}" if self._alamat
            else "Alamat IPv4 belum terdeteksi; periksa dengan ipconfig."
        )
        self.alamat = QLineEdit(alamat)
        self.alamat.setReadOnly(True)
        grid_tablet.addWidget(self.alamat, 0, 1)
        salin_alamat = tombol("Salin")
        salin_alamat.clicked.connect(lambda: self._salin(self.alamat.text()))
        baris_alamat = QHBoxLayout()
        baris_alamat.addWidget(salin_alamat)
        baris_alamat.addStretch()
        grid_tablet.addLayout(baris_alamat, 0, 2)

        grid_tablet.addWidget(QLabel("Token"), 1, 0)
        # Token yang belum ada langsung dibuat DAN disimpan. Token yang
        # hanya ditampilkan tetapi belum tersimpan membuat API saat Windows
        # menyala berhenti dengan "token belum disiapkan".
        token = muat_token()
        if len(token) < 8:
            token = token_baru()
            try:
                simpan_token(token)
            except (OSError, ValueError):
                pass
        self.token = QLineEdit(token)
        self.token.setReadOnly(True)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        grid_tablet.addWidget(self.token, 1, 1)
        tombol_token = QHBoxLayout()
        self.tampilkan_token = tombol("Tampilkan")
        self.tampilkan_token.clicked.connect(self._ubah_tampilan_token)
        salin_token = tombol("Salin")
        salin_token.clicked.connect(lambda: self._salin(self.token.text()))
        self.ganti_token = tombol("Buat token baru")
        self.ganti_token.clicked.connect(self._buat_token_baru)
        for btn in (self.tampilkan_token, salin_token, self.ganti_token):
            tombol_token.addWidget(btn)
        grid_tablet.addLayout(tombol_token, 1, 2)
        isi_tablet.addLayout(grid_tablet)
        isi_tablet.addWidget(
            keterangan(
                "Di tablet: ⚙ Pengaturan Server → Cari Server Otomatis, atau isi "
                "alamat dan token di atas. Profil jaringan Windows harus Private."
            )
        )
        layout.addWidget(kartu_tablet)

        # --- Tindakan -------------------------------------------------------
        self.catatan = QLabel()
        self.catatan.setWordWrap(True)
        self.catatan.setStyleSheet(
            "background: #FFFBEB; color: #92400E; border: 1px solid #FDE68A;"
            " border-radius: 8px; padding: 10px 14px;"
        )
        self.catatan.hide()
        layout.addWidget(self.catatan)

        tindakan = QHBoxLayout()
        self.pasang = tombol(_teks_tombol(LABEL_PASANG), variant="primary")
        self.pasang.clicked.connect(self._pasang)
        self.hapus = tombol("Hapus dari Task Scheduler", variant="danger")
        self.hapus.clicked.connect(self._hapus)
        tindakan.addWidget(self.pasang)
        tindakan.addWidget(self.hapus)
        tindakan.addStretch()
        layout.addLayout(tindakan)

        self.api_otomatis = QCheckBox(
            "Nyalakan API juga saat aplikasi ini dibuka "
            "(cadangan bila Task Scheduler gagal)"
        )
        self.api_otomatis.setChecked(muat_api_otomatis())
        self.api_otomatis.toggled.connect(self._ubah_api_otomatis)
        layout.addWidget(self.api_otomatis)

        self.kartu_perangkat = None
        if perangkat is not None:
            from app.ui.settings.kartu_perangkat import KartuPerangkat

            self.kartu_perangkat = KartuPerangkat(perangkat)
            layout.addWidget(self.kartu_perangkat)
        layout.addStretch()

        self._pekerja: _Pekerja | None = None
        self.muat_ulang()

    # --- Status -------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Periksa ulang status di latar. Dipanggil juga oleh F5."""
        if getattr(self, "kartu_perangkat", None) is not None:
            self.kartu_perangkat.muat_ulang()
        if self._sibuk:
            return
        self._jalankan(periksa_status, self._tampilkan_status)

    def _tampilkan_status(self, status: StatusLayanan) -> None:
        self._status = status
        alamat = f"{self._alamat[0]}:{port_api()}" if self._alamat else f"port {port_api()}"
        if status.api:
            self.baris_api.setel(_NORMAL, f"Berjalan di {alamat}")
        else:
            self.baris_api.setel(_TINDAKAN, "Mati — anjungan tidak dapat mengambil nomor")

        program, argumen = perintah_api()
        tugas = status.tugas
        if tugas.terdaftar is None:
            self.baris_tugas.setel(_BELUM, "Tidak dapat diperiksa dari akun ini")
        elif not tugas.terdaftar:
            self.baris_tugas.setel(
                _BELUM, "Belum terdaftar — API tidak menyala sendiri setelah PC dinyalakan"
            )
        elif not tugas.cocok_dengan(program, argumen):
            self.baris_tugas.setel(
                _TINDAKAN,
                f"Menunjuk lokasi lain ({tugas.program}) — tekan Pasang ulang",
            )
        else:
            self.baris_tugas.setel(
                _NORMAL, "Terdaftar — menyala sendiri 30 detik setelah Windows menyala"
            )

        if status.firewall:
            self.baris_firewall.setel(_NORMAL, "TCP 8765 & UDP 8766 terbuka (jaringan Private)")
        else:
            self.baris_firewall.setel(
                _BELUM, "Belum dibuka — tablet tidak dapat menjangkau komputer ini"
            )

        apk = status.apk
        if apk is None:
            self.baris_apk.setel(
                _BELUM,
                "Belum ada di folder apk\\ — tablet tidak dapat diperbarui dari "
                "server. Jalankan build-android-kiosk.ps1.",
            )
        elif apk.kode_versi < VERSI_MINIMAL:
            self.baris_apk.setel(
                _TINDAKAN,
                f"Versi {apk.nama_versi} di server lebih lama dari yang dibutuhkan "
                "— build ulang APK",
            )
        else:
            self.baris_apk.setel(
                _NORMAL, f"Versi {apk.nama_versi} siap diunduh tablet"
            )

        terpasang = bool(tugas.terdaftar)
        label_pasang = LABEL_PASANG_ULANG if terpasang else LABEL_PASANG
        self.pasang.setText(_teks_tombol(label_pasang))
        self.hapus.setEnabled(terpasang)
        perlu = not (status.api and terpasang and status.firewall)
        self.catatan.setVisible(perlu)
        if perlu:
            self.catatan.setText(
                f"Tekan {label_pasang}. Windows meminta izin Administrator "
                "sekali untuk Firewall dan Task Scheduler. Setelah itu API menyala "
                "sendiri setiap kali PC dinyalakan."
            )

    # --- Tindakan -----------------------------------------------------------

    def _jalankan(self, fungsi: Callable[[], object], sesudah: Callable[[object], None]) -> None:
        """Satu pekerja baru per tugas, supaya hasil tugas lama tidak tertukar."""
        self._sibuk = True
        self.pasang.setEnabled(False)
        self.hapus.setEnabled(False)
        pekerja = _Pekerja(self)
        self._pekerja = pekerja

        def selesai(hasil: object) -> None:
            self._sibuk = False
            self.pasang.setEnabled(True)
            sesudah(hasil)

        def gagal(exc: object) -> None:
            self._sibuk = False
            self.pasang.setEnabled(True)
            tampilkan_peringatan(self, str(exc), "Layanan Anjungan")
            self.muat_ulang()

        pekerja.selesai.connect(selesai)
        pekerja.gagal.connect(gagal)
        pekerja.jalankan(fungsi)

    def _pasang(self) -> None:
        folder = get_config().base_dir

        def kerja() -> StatusLayanan:
            pasang_layanan_api(folder)
            # Tugas baru dinyalakan; beri API waktu membuka port sebelum diperiksa.
            import time

            for _ in range(20):
                if api_sudah_berjalan(port_api()):
                    break
                time.sleep(0.5)
            return periksa_status()

        for baris in (self.baris_api, self.baris_tugas, self.baris_firewall):
            baris.setel(_MEMERIKSA, "Menunggu izin Administrator…")
        self._jalankan(kerja, self._tampilkan_status)

    def _hapus(self) -> None:
        if not konfirmasi(
            self,
            "Hapus API dari Task Scheduler?\n\nAPI berhenti sekarang dan tidak "
            "menyala sendiri saat PC dinyalakan. Anjungan Android tidak dapat "
            "mengambil nomor sampai dipasang lagi.",
        ):
            return

        def kerja() -> StatusLayanan:
            hapus_layanan_api()
            return periksa_status()

        self._jalankan(kerja, self._tampilkan_status)

    def _ubah_tampilan_token(self) -> None:
        if self.token.echoMode() == QLineEdit.EchoMode.Password:
            self.token.setEchoMode(QLineEdit.EchoMode.Normal)
            self.tampilkan_token.setText("Sembunyikan")
        else:
            self.token.setEchoMode(QLineEdit.EchoMode.Password)
            self.tampilkan_token.setText("Tampilkan")

    def _buat_token_baru(self) -> None:
        if not konfirmasi(
            self,
            "Buat token baru?\n\nSemua tablet harus diisi token baru, dan API "
            "harus dinyalakan ulang dengan tombol Pasang ulang.",
        ):
            return
        token = token_baru()
        try:
            simpan_token(token)
        except (OSError, ValueError) as exc:
            tampilkan_peringatan(self, str(exc), "Token gagal disimpan")
            return
        self.token.setText(token)
        self.catatan.setText(
            f"Token baru tersimpan. Tekan {LABEL_PASANG_ULANG} agar API "
            "memakainya, lalu isi token baru di setiap tablet."
        )
        self.catatan.show()

    def _ubah_api_otomatis(self, aktif: bool) -> None:
        try:
            simpan_api_otomatis(aktif)
        except (OSError, RuntimeError) as exc:
            self.api_otomatis.blockSignals(True)
            self.api_otomatis.setChecked(not aktif)
            self.api_otomatis.blockSignals(False)
            tampilkan_peringatan(self, str(exc), "Gagal menyimpan pengaturan")

    def _salin(self, teks: str) -> None:
        QApplication.clipboard().setText(teks)
