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
import warnings
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
from app.services.apk_anjungan import (
    VERSI_MINIMAL,
    VERSI_MINIMAL_LAYAR,
    InfoApk,
    folder_apk,
    info_apk,
)
from app.services.kiosk_server import (
    MENIT_JAGA_API,
    StatusTugas,
    _firewall_sudah_siap,
    api_sudah_berjalan,
    hapus_layanan_api,
    mulai_ulang_layanan_api,
    muat_api_otomatis,
    muat_token,
    pasang_layanan_api,
    pastikan_berkas_token,
    perintah_api,
    port_api,
    simpan_api_otomatis,
    simpan_token,
    status_tugas_api,
    token_baru,
)
from app.services.paket_suara import (
    InfoPaket,
    buat_paket,
    folder_paket,
    info_paket,
    nama_loket_aktif,
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
    apk_layar: InfoApk | None = None
    paket: InfoPaket | None = None
    #: Kata dari nama loket yang belum punya klip di paket suara.
    kata_kurang: tuple[str, ...] = ()


def periksa_status() -> StatusLayanan:
    base = get_config().base_dir
    paket = info_paket(folder_paket(base))
    try:
        kurang = tuple(paket.kurang(nama_loket_aktif())) if paket else ()
    except Exception:  # noqa: BLE001 - status tetap tampil walau database tersendat
        kurang = ()
    return StatusLayanan(
        api=api_sudah_berjalan(port_api()),
        tugas=status_tugas_api(),
        firewall=_firewall_sudah_siap(),
        apk=info_apk(folder_apk(base)),
        apk_layar=info_apk(folder_apk(base), "layar"),
        paket=paket,
        kata_kurang=kurang,
    )


class _Pekerja(QObject):
    """
    Jalankan satu fungsi di utas daemon; hasil atau galat kembali lewat sinyal.

    Sengaja TANPA induk. Pemeriksaan status (Firewall, Task Scheduler) bisa
    lebih lama daripada umur halamannya; objek sinyal yang ikut terhapus
    bersama halaman lalu dipancari dari utas ini membuat Qt mengakses
    memori yang sudah dibebaskan. Tanpa induk, objek ini hidup selama
    utasnya masih memegangnya. Utas daemon, bukan QThread: saat aplikasi
    ditutup ia ikut berhenti diam-diam, sedangkan QThread yang masih
    berjalan membuat Qt menghentikan proses dengan paksa.
    """

    selesai = Signal(object)
    gagal = Signal(object)

    def jalankan(self, fungsi: Callable[[], object]) -> None:
        def kerja() -> None:
            try:
                hasil = fungsi()
            except Exception as exc:  # noqa: BLE001 - diteruskan ke layar
                self._pancarkan(self.gagal, exc)
            else:
                self._pancarkan(self.selesai, hasil)

        threading.Thread(target=kerja, daemon=True).start()

    @staticmethod
    def _pancarkan(sinyal, isi: object) -> None:
        try:
            sinyal.emit(isi)
        except RuntimeError:
            # Aplikasi sudah menutup dan Qt membersihkan objek ini lebih
            # dulu daripada utasnya selesai: tidak ada lagi yang menunggu.
            pass

    def putuskan(self) -> None:
        """Hasil yang datang sesudah halaman ditutup tidak diteruskan ke mana pun."""
        for sinyal in (self.selesai, self.gagal):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    sinyal.disconnect()
                except (RuntimeError, TypeError):
                    pass


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

        # Gulir hanya cadangan untuk jendela yang diperkecil; pada layar
        # penuh 1366 x 768 susunan dua kolom di bawah sudah muat.
        luar = QVBoxLayout(self)
        luar.setContentsMargins(0, 0, 0, 0)
        gulir = QScrollArea()
        gulir.setWidgetResizable(True)
        gulir.setFrameShape(QFrame.Shape.NoFrame)
        isi_halaman = QWidget()
        gulir.setWidget(isi_halaman)
        luar.addWidget(gulir)

        layout = QVBoxLayout(isi_halaman)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)
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
        self.baris_apk_layar = _BarisStatus(grid, 4, "APK layar antrian")
        self.baris_paket = _BarisStatus(grid, 5, "Paket suara")
        for baris in (
            self.baris_api, self.baris_tugas, self.baris_firewall,
            self.baris_apk, self.baris_apk_layar, self.baris_paket,
        ):
            baris.setel(_MEMERIKSA, "")
        isi_status.addLayout(grid)
        baris_paket = QHBoxLayout()
        self.buat_paket = tombol("Buat ulang paket suara")
        self.buat_paket.clicked.connect(self._buat_paket_suara)
        baris_paket.addWidget(self.buat_paket)
        baris_paket.addStretch()
        isi_status.addLayout(baris_paket)
        isi_status.addWidget(
            keterangan(
                "Paket suara dipakai layar antrian yang tidak punya suara Bahasa "
                "Indonesia sendiri. Buat ulang bila nama loket berubah."
            )
        )
        # Dua kolom: pada 1366 x 768 seluruh halaman muat satu layar.
        # Ditumpuk satu kolom, status dan tablet saja sudah melewati tinggi
        # layar sebelum daftar perangkat sempat terlihat.
        dua_kolom = QHBoxLayout()
        dua_kolom.setSpacing(16)
        kiri = QVBoxLayout()
        kiri.setSpacing(12)
        kiri.addWidget(kartu_status)
        kiri.addStretch()
        kanan = QVBoxLayout()
        kanan.setSpacing(12)
        dua_kolom.addLayout(kiri, stretch=1)
        dua_kolom.addLayout(kanan, stretch=1)
        layout.addLayout(dua_kolom)

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
        # Token yang belum ada langsung dibuat DAN disimpan ke berkas — juga
        # token lama dari `setx` yang hanya ada di environment akun ini.
        # Token yang hanya ditampilkan tetapi belum tertulis di berkas
        # membuat API saat Windows menyala (akun SYSTEM) berhenti dengan
        # "token belum disiapkan".
        try:
            token = pastikan_berkas_token()
        except (OSError, ValueError):
            token = muat_token()
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
                "alamat dan token di atas. Tablet harus berada di jaringan lokal "
                "yang sama dengan komputer ini."
            )
        )
        kanan.addWidget(kartu_tablet)

        # --- Tindakan -------------------------------------------------------
        self.catatan = QLabel()
        self.catatan.setWordWrap(True)
        self.catatan.setStyleSheet(
            "background: #FFFBEB; color: #92400E; border: 1px solid #FDE68A;"
            " border-radius: 8px; padding: 10px 14px;"
        )
        self.catatan.hide()
        kanan.addWidget(self.catatan)

        tindakan = QHBoxLayout()
        self.pasang = tombol(_teks_tombol(LABEL_PASANG), variant="primary")
        self.pasang.clicked.connect(self._pasang)
        self.mulai_ulang = tombol("Restart API")
        self.mulai_ulang.clicked.connect(self._mulai_ulang)
        self.hapus = tombol("Hapus dari Task Scheduler", variant="danger")
        self.hapus.clicked.connect(self._hapus)
        tindakan.addWidget(self.pasang)
        tindakan.addWidget(self.mulai_ulang)
        tindakan.addWidget(self.hapus)

        # Kotak centang tidak melipat teksnya; kalimat panjang memaksa
        # kolom kanan melebar dan halaman bergulir ke samping.
        self.api_otomatis = QCheckBox("Nyalakan API juga saat aplikasi ini dibuka")
        self.api_otomatis.setToolTip(
            "Cadangan bila Task Scheduler gagal menyalakan API saat Windows mulai."
        )
        self.api_otomatis.setChecked(muat_api_otomatis())
        self.api_otomatis.toggled.connect(self._ubah_api_otomatis)
        # Sebaris dengan tombol tindakan: keduanya tentang cara API menyala.
        tindakan.addSpacing(8)
        tindakan.addWidget(self.api_otomatis)
        tindakan.addStretch()
        kanan.addLayout(tindakan)
        kanan.addStretch()

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
        elif not tugas.berjaga:
            self.baris_tugas.setel(
                _BELUM,
                "Terdaftar tanpa pemeriksa berkala — tekan Pasang ulang agar "
                "API yang berhenti dinyalakan lagi",
            )
        else:
            self.baris_tugas.setel(
                _NORMAL,
                "Terdaftar — menyala 30 detik setelah Windows menyala, "
                f"dinyalakan lagi bila mati (diperiksa tiap {MENIT_JAGA_API} menit)",
            )

        if status.firewall:
            self.baris_firewall.setel(
                _NORMAL, "TCP 8765 & UDP 8766 terbuka untuk jaringan lokal"
            )
        else:
            self.baris_firewall.setel(
                _BELUM,
                "Belum dibuka atau masih aturan lama (hanya jaringan Private) — "
                "tekan Pasang ulang",
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

        apk_layar = status.apk_layar
        if apk_layar is None:
            self.baris_apk_layar.setel(
                _BELUM,
                "Belum ada di folder apk\\ — layar antrian tidak dapat diperbarui "
                "dari server. Jalankan build-android-kiosk.ps1.",
            )
        elif apk_layar.kode_versi < VERSI_MINIMAL_LAYAR:
            self.baris_apk_layar.setel(
                _TINDAKAN, f"Versi {apk_layar.nama_versi} terlalu lama — build ulang APK"
            )
        else:
            self.baris_apk_layar.setel(
                _NORMAL, f"Versi {apk_layar.nama_versi} siap diunduh layar"
            )

        paket = status.paket
        if paket is None:
            self.baris_paket.setel(
                _BELUM, "Belum dibuat — layar tanpa suara Indonesia hanya berbunyi nada"
            )
        elif status.kata_kurang:
            kata = ", ".join(k.removeprefix("kata_") for k in status.kata_kurang)
            self.baris_paket.setel(_BELUM, f"Perlu dibuat ulang: kata baru {kata}")
        else:
            self.baris_paket.setel(_NORMAL, f"{paket.jumlah} klip · suara {paket.suara}")

        terpasang = bool(tugas.terdaftar)
        label_pasang = LABEL_PASANG_ULANG if terpasang else LABEL_PASANG
        self.pasang.setText(_teks_tombol(label_pasang))
        self.mulai_ulang.setEnabled(terpasang)
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
        self.mulai_ulang.setEnabled(False)
        self.hapus.setEnabled(False)
        pekerja = _Pekerja()
        if self._pekerja is not None:
            self._pekerja.putuskan()
        self._pekerja = pekerja

        def selesai(hasil: object) -> None:
            self._sibuk = False
            self.pasang.setEnabled(True)
            self.mulai_ulang.setEnabled(True)
            sesudah(hasil)

        def gagal(exc: object) -> None:
            self._sibuk = False
            self.pasang.setEnabled(True)
            self.mulai_ulang.setEnabled(True)
            tampilkan_peringatan(self, str(exc), "Layanan Anjungan")
            self.muat_ulang()

        pekerja.selesai.connect(selesai)
        pekerja.gagal.connect(gagal)
        # Halaman yang dihapus tanpa hentikan() (misalnya ikut jendela).
        self.destroyed.connect(lambda *_: pekerja.putuskan())
        pekerja.jalankan(fungsi)

    def hentikan(self) -> None:
        """Putuskan pemeriksaan yang masih berjalan; dipanggil saat halaman ditutup."""
        if self._pekerja is not None:
            self._pekerja.putuskan()
            self._pekerja = None

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

    def _mulai_ulang(self) -> None:
        def kerja() -> StatusLayanan:
            mulai_ulang_layanan_api()
            # Tugas baru perlu waktu singkat untuk membuka port API sebelum
            # statusnya dibaca kembali.
            import time

            for _ in range(20):
                if api_sudah_berjalan(port_api()):
                    break
                time.sleep(0.5)
            status = periksa_status()
            if not status.api:
                raise RuntimeError(
                    "API sudah dimulai ulang, tetapi belum merespons. "
                    "Periksa logs\\kiosk-api.log."
                )
            return status

        self.baris_api.setel(_MEMERIKSA, "Memulai ulang API…")
        self._jalankan(kerja, self._tampilkan_status)

    def _buat_paket_suara(self) -> None:
        folder = folder_paket(get_config().base_dir)

        def kerja() -> StatusLayanan:
            buat_paket(folder, nama_loket_aktif())
            return periksa_status()

        self.baris_paket.setel(_MEMERIKSA, "Membuat klip dengan suara Windows…")
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
