"""
Peran komputer ini terhadap database.

Bukan pemilihan otomatis di jaringan. Satu orang menunjuk SATU komputer
sebagai server, komputer lain menuliskan alamatnya. Dua PostgreSQL yang
sama-sama "menang" menghasilkan nomor antrian pecah — celah yang sudah
pernah nyata saat beberapa loket menulis bersamaan.

Isinya hidup di berkas `mesin.json` di folder database komputer ini,
bukan di tabel pengaturan bersama: pengaturan bersama baru terbaca
setelah koneksi database jadi, sedangkan yang diatur di sini adalah
koneksi itu sendiri.

ANTRIAN_DB_URL, bila diisi, tetap mengalahkan berkas ini. Pemasangan
lama yang sudah memakai setx tidak berubah perilakunya.

Kata sandi database tersimpan di berkas ini. Jangan menyalinnya ke
komputer anjungan, ke git, atau ke log.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import URL, make_url

logger = logging.getLogger("antrian.mesin")

NAMA_BERKAS = "mesin.json"

SENDIRI = "sendiri"
SERVER = "server"
KLIEN = "klien"
PERAN_SAH = frozenset({SENDIRI, SERVER, KLIEN})

PORT_BAWAAN = 5432
DATABASE_BAWAAN = "antrian"
PENGGUNA_BAWAAN = "antrian"
HOST_LOKAL = "127.0.0.1"
_HOST_LOKAL_LAIN = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


@dataclass(frozen=True)
class PengaturanMesin:
    """Pilihan peran dan isian PostgreSQL pada satu komputer."""

    peran: str = SENDIRI
    host: str = ""
    port: int = PORT_BAWAAN
    nama_database: str = DATABASE_BAWAAN
    pengguna: str = PENGGUNA_BAWAAN
    sandi: str = ""

    def ke_url(self) -> str:
        """
        URL SQLAlchemy, atau kosong bila mesin ini memakai SQLite.

        Komputer server selalu menyambung ke 127.0.0.1, bukan ke IP
        jaringannya sendiri: firewall dan pg_hba sering menolak mesin
        yang memutar balik lewat alamat LAN.
        """
        if self.peran == SENDIRI:
            return ""
        host = HOST_LOKAL if self.peran == SERVER else self.host.strip()
        # str(URL) menyembunyikan kata sandi sebagai "***". Itu aman untuk
        # ditampilkan, tetapi memutus koneksi: PostgreSQL akan menolak sandi
        # yang literal tiga bintang.
        return URL.create(
            "postgresql+psycopg",
            username=self.pengguna.strip() or PENGGUNA_BAWAAN,
            password=self.sandi,
            host=host,
            port=self.port,
            database=self.nama_database.strip() or DATABASE_BAWAAN,
        ).render_as_string(hide_password=False)

    def ringkasan(self) -> str:
        """Satu baris untuk log dan layar, tanpa kata sandi."""
        if self.peran == SENDIRI:
            return "satu komputer (SQLite)"
        if self.peran == SERVER:
            return (
                f"server PostgreSQL @ {HOST_LOKAL}:{self.port}/"
                f"{self.nama_database.strip() or DATABASE_BAWAAN}"
            )
        host = self.host.strip() or "?"
        return (
            f"klien PostgreSQL @ {host}:{self.port}/"
            f"{self.nama_database.strip() or DATABASE_BAWAAN}"
        )


def path_berkas_mesin(db_path: Path) -> Path:
    """
    Letak `mesin.json`.

    Mengikuti folder database supaya test yang mengarahkan ANTRIAN_DB_PATH
    ke folder sementara tidak membaca berkas milik pengembang. ANTRIAN_MESIN_PATH
    menimpa lokasi itu bila diisi.
    """
    override = os.environ.get("ANTRIAN_MESIN_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(db_path).expanduser().resolve().parent / NAMA_BERKAS


def baca_berkas_mesin(path: Path) -> PengaturanMesin | None:
    """Baca berkas, atau None bila tidak ada / tidak sah."""
    try:
        mentah = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("Berkas mesin tidak dapat dibaca: %s", path)
        return None

    try:
        data = json.loads(mentah)
    except json.JSONDecodeError:
        logger.warning("Berkas mesin rusak, diabaikan: %s", path)
        return None
    if not isinstance(data, dict):
        logger.warning("Berkas mesin bukan objek JSON, diabaikan: %s", path)
        return None

    peran = str(data.get("peran", "")).strip().lower()
    if peran not in PERAN_SAH:
        logger.warning("Peran mesin %r tidak dikenali, diabaikan", peran)
        return None

    try:
        port = int(data.get("port", PORT_BAWAAN) or PORT_BAWAAN)
    except (TypeError, ValueError):
        port = PORT_BAWAAN

    return PengaturanMesin(
        peran=peran,
        host=str(data.get("host", "") or "").strip(),
        port=port,
        nama_database=str(data.get("nama_database", "") or DATABASE_BAWAAN).strip()
        or DATABASE_BAWAAN,
        pengguna=str(data.get("pengguna", "") or PENGGUNA_BAWAAN).strip()
        or PENGGUNA_BAWAAN,
        sandi=str(data.get("sandi", "") or ""),
    )


def tulis_berkas_mesin(path: Path, pengaturan: PengaturanMesin) -> None:
    """Tulis berkas secara atomik. Kata sandi tidak masuk log."""
    kesalahan = kesalahan_isian(pengaturan)
    if kesalahan:
        raise ValueError(kesalahan)

    path.parent.mkdir(parents=True, exist_ok=True)
    isi = {
        "peran": pengaturan.peran,
        "host": pengaturan.host.strip(),
        "port": pengaturan.port,
        "nama_database": pengaturan.nama_database.strip() or DATABASE_BAWAAN,
        "pengguna": pengaturan.pengguna.strip() or PENGGUNA_BAWAAN,
        "sandi": pengaturan.sandi,
    }
    sementara = path.with_suffix(".json.tmp")
    sementara.write_text(
        json.dumps(isi, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sementara.replace(path)
    logger.info("Peran komputer ini disimpan: %s", pengaturan.ringkasan())


def url_dari_berkas_mesin(path: Path) -> str:
    """URL dari berkas, atau kosong bila SQLite / berkas tidak dipakai."""
    pengaturan = baca_berkas_mesin(path)
    if pengaturan is None:
        return ""
    if pengaturan.peran == KLIEN and not pengaturan.host.strip():
        logger.warning("Berkas mesin klien tanpa alamat server, diabaikan")
        return ""
    return pengaturan.ke_url()


def pengaturan_dari_url(url: str) -> PengaturanMesin:
    """Uraikan URL aktif menjadi isian dialog, tanpa kata sandi tersembunyi."""
    terurai = make_url(url)
    if terurai.get_backend_name() == "sqlite":
        return PengaturanMesin()
    host = (terurai.host or "").strip()
    peran = SERVER if host.lower() in _HOST_LOKAL_LAIN else KLIEN
    return PengaturanMesin(
        peran=peran,
        host="" if peran == SERVER else host,
        port=int(terurai.port or PORT_BAWAAN),
        nama_database=terurai.database or DATABASE_BAWAAN,
        pengguna=terurai.username or PENGGUNA_BAWAAN,
        sandi=terurai.password or "",
    )


def muat_pengaturan(db_path: Path) -> PengaturanMesin:
    """
    Isian yang ditampilkan di dialog.

    Berkas mesin menang. Bila belum ada, URL environment diuraikan supaya
    pemasangan lama lewat setx terlihat apa adanya. Selain itu: satu komputer.
    """
    dari_berkas = baca_berkas_mesin(path_berkas_mesin(db_path))
    if dari_berkas is not None:
        return dari_berkas
    env = os.environ.get("ANTRIAN_DB_URL", "").strip()
    if env:
        return pengaturan_dari_url(env)
    return PengaturanMesin()


def env_url_mengalahkan() -> bool:
    """True bila ANTRIAN_DB_URL terisi dan akan mengabaikan mesin.json."""
    return bool(os.environ.get("ANTRIAN_DB_URL", "").strip())


def kesalahan_isian(pengaturan: PengaturanMesin) -> str | None:
    """Pesan untuk petugas, atau None bila isian siap disimpan."""
    if pengaturan.peran not in PERAN_SAH:
        return "Pilih bagaimana komputer ini dipakai."
    if pengaturan.peran == SENDIRI:
        return None
    if not (1 <= pengaturan.port <= 65535):
        return "Port harus berupa angka 1 sampai 65535."
    if not pengaturan.nama_database.strip():
        return "Nama database belum diisi."
    if not pengaturan.pengguna.strip():
        return "Nama pengguna database belum diisi."
    if pengaturan.peran == KLIEN and not pengaturan.host.strip():
        return "Alamat komputer server belum diisi."
    return None


def alamat_ipv4_lokal() -> tuple[str, ...]:
    """
    Alamat IPv4 mesin INI di jaringan lokal.

    Bukan pencarian server. Yang ditampilkan adalah angka yang ditulis
    petugas di komputer klien, supaya mereka tidak menebak.
    """
    ketemu: list[str] = []

    try:
        soket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            soket.connect(("1.1.1.1", 80))
            ip = soket.getsockname()[0]
        finally:
            soket.close()
        if _layak_ditampilkan(ip):
            ketemu.append(ip)
    except OSError:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _layak_ditampilkan(ip) and ip not in ketemu:
                ketemu.append(ip)
    except OSError:
        pass

    return tuple(ketemu)


def _layak_ditampilkan(ip: str) -> bool:
    if not ip or ip.startswith("127.") or ip.startswith("169.254."):
        return False
    return True


def uji_koneksi(url: str) -> str | None:
    """
    None bila database merespons, pesan petugas bila gagal.

    Engine buatan sendiri, bukan engine aplikasi: tombol uji tidak boleh
    menukar koneksi yang sedang dipakai layar lain.
    """
    if not url:
        return "Alamat database masih kosong."

    import sqlalchemy as sa

    argumen = {"connect_timeout": 3} if "postgresql" in url else {}
    mesin = sa.create_engine(url, future=True, connect_args=argumen)
    try:
        with mesin.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return None
    except Exception:
        logger.warning("Uji koneksi database gagal")
        return (
            "Tidak dapat menghubungi database. Periksa alamat, PostgreSQL "
            "sedang menyala, dan komputer ini tersambung ke jaringan yang sama."
        )
    finally:
        mesin.dispose()
