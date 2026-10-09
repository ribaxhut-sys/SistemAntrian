"""
Keadaan sambungan anjungan Android, untuk indikator di jendela petugas.

Petugas biasanya baru tahu anjungan bermasalah ketika pengunjung datang
mengeluh tidak bisa mengambil nomor. Modul ini menjawab tiga pertanyaan,
berurutan dari yang paling menentukan:

1. Apakah API anjungan menjawab? Di komputer server diketuk di 127.0.0.1;
   di komputer loket diketuk di alamat server database, karena API selalu
   berjalan di sana.
2. (Hanya di server) Apakah jaringan yang dipakai tercatat Public? Aturan
   Firewall API hanya dibuka untuk jaringan Private, sehingga API yang
   berjalan pun tidak terjangkau tablet.
3. Apakah ada tablet anjungan yang benar-benar menyambung? Tablet mencatat
   kontaknya ke database lewat API (lihat device_service.catat_kontak).

Penilaiannya (`nilai_status`) murni, tanpa I/O, supaya setiap kombinasi
dapat diuji. `periksa_status_anjungan` mengumpulkan faktanya dan memanggil
penilaian itu; ia lambat (HTTP, PowerShell, database) dan harus dipanggil
di luar utas UI.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core import clock
from app.core.logger import get_logger

logger = get_logger("status_anjungan")

NORMAL = "normal"
PERINGATAN = "peringatan"
MASALAH = "masalah"

#: Tablet mengetuk API setiap beberapa detik, tetapi kontaknya ditulis ke
#: database paling sering 30 detik sekali. Dua menit memberi ruang satu
#: tulisan terlewat tanpa membuat indikator berkedip.
BATAS_TERPUTUS = timedelta(minutes=2)

_LANGKAH_LAYANAN = "Pengaturan › Layanan Anjungan"


@dataclass(frozen=True)
class TabletAnjungan:
    nama: str
    terakhir_terlihat: datetime | None


@dataclass(frozen=True)
class StatusAnjungan:
    tingkat: str
    #: Teks pendek untuk bilah status.
    ringkas: str
    #: Kalimat utama pita peringatan; kosong bila NORMAL.
    judul: str = ""
    saran: tuple[str, ...] = field(default_factory=tuple)

    @property
    def bermasalah(self) -> bool:
        return self.tingkat != NORMAL


def _jam(waktu: datetime | None) -> str:
    return waktu.strftime("%H:%M") if waktu else "belum pernah"


def nilai_status(
    *,
    di_server: bool,
    host: str,
    port: int,
    api_hidup: bool,
    berkas_token_ada: bool = True,
    jaringan_public: tuple[str, ...] = (),
    tablet: tuple[TabletAnjungan, ...] = (),
    sekarang: datetime | None = None,
) -> StatusAnjungan:
    """Ubah fakta yang terkumpul menjadi status beserta sarannya."""
    sekarang = sekarang or clock.now()

    if not api_hidup:
        if di_server:
            saran = []
            if not berkas_token_ada:
                saran.append(
                    f"Token API belum tersimpan. Buka {_LANGKAH_LAYANAN} — "
                    "halaman itu menyimpannya otomatis."
                )
            saran += [
                f"Buka {_LANGKAH_LAYANAN}, lalu tekan Pasang ulang "
                "(perlu izin Administrator).",
                "API dicoba dinyalakan lagi otomatis setiap 5 menit. Bila tetap "
                "mati, lihat logs\\app.log baris 'antrian.kiosk_api'.",
            ]
            return StatusAnjungan(
                MASALAH,
                "API anjungan: ● mati",
                "API anjungan mati — tablet tidak dapat mengambil nomor.",
                tuple(saran),
            )
        return StatusAnjungan(
            MASALAH,
            "API anjungan: ● tidak terjangkau",
            f"API anjungan di server {host}:{port} tidak terjangkau dari komputer ini.",
            (
                "Pastikan komputer server menyala dan aplikasi Antrian di server "
                "sudah dibuka.",
                f"Minta admin di komputer server membuka {_LANGKAH_LAYANAN} dan "
                "memeriksa status API.",
                "Pastikan jaringan di komputer server bertipe Private — Firewall "
                f"hanya membuka port {port} di jaringan Private.",
            ),
        )

    if jaringan_public:
        nama = ", ".join(f"'{n}'" for n in jaringan_public)
        return StatusAnjungan(
            MASALAH,
            "API anjungan: ● diblokir Firewall",
            f"API berjalan, tetapi jaringan {nama} tercatat Public sehingga "
            "Firewall menolak tablet.",
            (
                "Ubah di Settings › Network & internet › Wi-Fi/Ethernet › "
                f"{jaringan_public[0]} › Network profile type › Private network.",
                "Jaringan baru (misalnya router pengganti) selalu dianggap Public "
                "oleh Windows; ulangi langkah ini setiap berganti jaringan.",
            ),
        )

    tersambung = [
        t
        for t in tablet
        if t.terakhir_terlihat is not None
        and sekarang - t.terakhir_terlihat <= BATAS_TERPUTUS
    ]
    # Hanya tablet yang sudah menyambung hari ini yang dianggap terputus.
    # Tablet cadangan di lemari tidak boleh membuat pita peringatan menyala
    # sepanjang hari.
    terputus = [
        t
        for t in tablet
        if t not in tersambung
        and t.terakhir_terlihat is not None
        and t.terakhir_terlihat.date() == sekarang.date()
    ]
    saran_tablet = (
        "Pastikan tablet menyala dan aplikasi anjungan terbuka.",
        "Tablet harus tersambung ke Wi-Fi yang sama dengan komputer server — "
        "bukan jaringan tamu (guest) atau hotspot yang memisahkan perangkat.",
        "Di tablet, cari ulang server atau isi alamatnya secara manual.",
    )

    if tablet and not tersambung:
        return StatusAnjungan(
            PERINGATAN,
            "API anjungan: ● berjalan · tablet belum tersambung",
            "API berjalan, tetapi belum ada tablet anjungan yang tersambung.",
            saran_tablet,
        )
    if terputus:
        daftar = ", ".join(
            f"{t.nama or 'tanpa nama'} (terakhir {_jam(t.terakhir_terlihat)})"
            for t in terputus
        )
        return StatusAnjungan(
            PERINGATAN,
            f"API anjungan: ● berjalan · {len(terputus)} tablet terputus",
            f"Tablet anjungan terputus: {daftar}.",
            saran_tablet,
        )

    ringkas = "API anjungan: ● berjalan"
    if tersambung:
        ringkas += f" · {len(tersambung)} tablet tersambung"
    return StatusAnjungan(NORMAL, ringkas)


# ---------------------------------------------------------------------
# Pengumpulan fakta (lambat; jangan dipanggil di utas UI)
# ---------------------------------------------------------------------


def api_terjangkau(host: str, port: int, *, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as jawab:
            return jawab.status == 200 and jawab.read(256) == b'{"status":"ok"}'
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False


def jaringan_public() -> tuple[str, ...]:
    """Nama jaringan tersambung yang tercatat Public. Kosong bila tidak dapat diperiksa."""
    from app.services.kiosk_server import _jalankan_powershell

    try:
        hasil = _jalankan_powershell(
            "Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' } "
            "| ForEach-Object { $_.Name }"
        )
    except Exception:  # noqa: BLE001 - indikator tidak boleh menggagalkan apa pun
        return ()
    if hasil.returncode != 0:
        return ()
    return tuple(b.strip() for b in (hasil.stdout or "").splitlines() if b.strip())


def periksa_status_anjungan() -> StatusAnjungan | None:
    """
    Kumpulkan fakta lalu nilai. None bila komputer ini tidak memakai anjungan.

    Anjungan Android hanya ada pada pemasangan PostgreSQL: API berjalan di
    komputer server dan membaca database yang sama dengan loket.
    """
    from app.core.config import get_config
    from app.services import device_service
    from app.services.kiosk_server import komputer_server, path_berkas_token, port_api

    config = get_config()
    if config.memakai_sqlite:
        return None

    di_server = komputer_server()
    port = port_api()
    host = "127.0.0.1" if di_server else (config.url_database.host or "127.0.0.1")
    hidup = api_terjangkau(host, port)

    berkas_token_ada = True
    public: tuple[str, ...] = ()
    if di_server:
        try:
            berkas_token_ada = bool(
                path_berkas_token().read_text(encoding="utf-8").strip()
            )
        except OSError:
            berkas_token_ada = False
        if hidup:
            public = jaringan_public()

    try:
        tablet = tuple(
            TabletAnjungan(p.nama, p.terakhir_terlihat)
            for p in device_service.daftar_anjungan()
        )
    except Exception:  # noqa: BLE001
        logger.warning("Daftar anjungan gagal dibaca", exc_info=True)
        tablet = ()

    return nilai_status(
        di_server=di_server,
        host=host,
        port=port,
        api_hidup=hidup,
        berkas_token_ada=berkas_token_ada,
        jaringan_public=public,
        tablet=tablet,
    )
