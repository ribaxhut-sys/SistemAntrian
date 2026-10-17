"""
Peran komputer ini terhadap database.

Satu orang menunjuk SATU komputer sebagai server. Komputer lain boleh
mencari PostgreSQL di jaringan yang sama, tetapi bila lebih dari satu
yang menjawab, orang yang memasang yang memilih. Aplikasi tidak
menunjuk sendiri siapa yang menang: dua PostgreSQL yang sama-sama
"menang" menghasilkan nomor antrian pecah.

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

import ipaddress
import json
import logging
import os
import socket
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import URL, make_url

logger = logging.getLogger("antrian.mesin")

NAMA_BERKAS = "mesin.json"

SERVER = "server"
KLIEN = "klien"
PERAN_SAH = frozenset({SERVER, KLIEN})

PORT_BAWAAN = 5432
DATABASE_BAWAAN = "antrian"
PENGGUNA_BAWAAN = "antrian"
HOST_LOKAL = "127.0.0.1"
_HOST_LOKAL_LAIN = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})


@dataclass(frozen=True)
class PengaturanMesin:
    """Pilihan peran dan isian PostgreSQL pada satu komputer."""

    peran: str = SERVER
    host: str = ""
    port: int = PORT_BAWAAN
    nama_database: str = DATABASE_BAWAAN
    pengguna: str = PENGGUNA_BAWAAN
    sandi: str = ""

    def ke_url(self) -> str:
        """
        URL SQLAlchemy PostgreSQL untuk server lokal atau klien.

        Komputer server selalu menyambung ke 127.0.0.1, bukan ke IP
        jaringannya sendiri: firewall dan pg_hba sering menolak mesin
        yang memutar balik lewat alamat LAN.
        """
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
    """URL PostgreSQL dari berkas, atau kosong bila berkas tidak sah."""
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
    if terurai.get_backend_name() != "postgresql":
        raise ValueError("Sistem Antrian hanya mendukung PostgreSQL.")
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
    pemasangan lama lewat setx terlihat apa adanya. Selain itu: server lokal.
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
    if not (1 <= pengaturan.port <= 65535):
        return "Port harus berupa angka 1 sampai 65535."
    if not pengaturan.nama_database.strip():
        return "Nama database belum diisi."
    if not pengaturan.pengguna.strip():
        return "Nama pengguna database belum diisi."
    if pengaturan.peran == KLIEN and not pengaturan.host.strip():
        return "Alamat komputer server belum diisi."
    if not pengaturan.sandi:
        return (
            "Kata sandi database belum diisi. Yang diganti hanya sandi; "
            "port, nama database, dan pengguna sudah tetap."
        )
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


def pesan_kegagalan_koneksi(exc: BaseException) -> str:
    """
    Pesan petugas dari kegagalan sambungan.

    Teks mentah pengandar sering memuat untaian koneksi, dan untaian itu
    memuat kata sandi. Yang ditampilkan hanya golongan kesalahannya.
    """
    teks = str(exc).lower()
    if "password authentication failed" in teks or "no password supplied" in teks:
        if 'user "postgres"' in teks:
            return (
                "Kata sandi pengguna postgres ditolak. Isi sandi yang "
                "diketik saat PostgreSQL dipasang. Sandi itu tidak disimpan."
            )
        return (
            "PostgreSQL menolak pengguna antrian. Kata sandinya tidak "
            "cocok, atau pengguna itu belum dibuat. Pada komputer server, "
            "tekan Siapkan database."
        )
    if "database" in teks and "does not exist" in teks:
        return (
            "Database antrian belum ada. Pada komputer server, tekan "
            "Siapkan database."
        )
    if any(
        petunjuk in teks
        for petunjuk in ("refused", "could not connect", "timed out", "timeout", "10061")
    ):
        return (
            "Tidak dapat menghubungi database. PostgreSQL tidak menjawab "
            "di komputer yang dituju. Pastikan layanannya menyala dan "
            "komputer ini satu jaringan dengannya."
        )
    return (
        "Tidak dapat menghubungi database. Periksa alamat, PostgreSQL "
        "sedang menyala, dan komputer ini tersambung ke jaringan yang sama."
    )


def uji_koneksi(url: str) -> str | None:
    """
    None bila database merespons, pesan petugas bila gagal.

    Engine buatan sendiri, bukan engine aplikasi: tombol uji tidak boleh
    menukar koneksi yang sedang dipakai layar lain.
    """
    if not url:
        return "Alamat database masih kosong."
    try:
        if make_url(url).get_backend_name() != "postgresql":
            return "Sistem Antrian hanya mendukung database PostgreSQL."
    except (TypeError, ValueError):
        return "Alamat database tidak sah."

    import sqlalchemy as sa

    mesin = sa.create_engine(url, future=True, connect_args={"connect_timeout": 3})
    try:
        with mesin.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        return None
    except Exception as exc:
        logger.warning("Uji koneksi database gagal: %s", type(exc).__name__)
        return pesan_kegagalan_koneksi(exc)
    finally:
        mesin.dispose()


def alamat_calon_server(ip: str) -> tuple[str, ...]:
    """
    Alamat lain pada /24 yang sama.

    Subnet yang lebih besar tidak dipindai: kantor memakai /24, dan
    memindai 10.0.0.0/8 akan memeriksa jutaan alamat.
    """
    try:
        jaringan = ipaddress.IPv4Network(f"{ip}/24", strict=False)
    except ipaddress.AddressValueError:
        return ()
    return tuple(str(host) for host in jaringan.hosts() if str(host) != ip)


def subnet_kantor(alamat: tuple[str, ...] | None = None) -> tuple[str, ...]:
    """Prefiks /24 dari alamat mesin ini, untuk baris izin pg_hba."""
    sumber = alamat if alamat is not None else alamat_ipv4_lokal()
    hasil: list[str] = []
    for ip in sumber:
        try:
            jaringan = str(ipaddress.IPv4Network(f"{ip}/24", strict=False))
        except ipaddress.AddressValueError:
            continue
        if jaringan not in hasil:
            hasil.append(jaringan)
    return tuple(hasil)


def tambahan_izin_hba(isi: str, subnet: tuple[str, ...]) -> str:
    """
    Baris pg_hba yang belum ada.

    Hanya pengguna dan database antrian, hanya subnet kantor, dan hanya
    scram-sha-256. Tidak ada 0.0.0.0/0 dan tidak ada trust.
    """
    ada = isi.splitlines()
    tambahan: list[str] = []
    for jaringan in subnet:
        if any("antrian" in baris and jaringan in baris for baris in ada):
            continue
        tambahan.append(f"host\tantrian\tantrian\t{jaringan}\tscram-sha-256")
    if not tambahan:
        return ""
    awalan = "" if (not isi or isi.endswith("\n")) else "\n"
    return awalan + "\n".join(tambahan) + "\n"


def cari_server_jaringan(
    alamat: tuple[str, ...] | None = None,
    pemeriksa=None,
    port: int = PORT_BAWAAN,
) -> tuple[str, ...]:
    """
    Alamat PostgreSQL lain di /24 mesin ini, pada port yang sama.

    Pemeriksaan hanya mengetuk port itu dan membaca satu byte jawaban
    protokol. Kata sandi tidak dikirim. Alamat mesin ini sendiri tidak
    ikut: komputer server dipilih lewat peran, bukan lewat pindaian.
    """
    sumber = alamat if alamat is not None else alamat_ipv4_lokal()
    calon: list[str] = []
    terlihat: set[str] = set()
    for ip in sumber:
        for host in alamat_calon_server(ip):
            if host in terlihat:
                continue
            terlihat.add(host)
            calon.append(host)
    if not calon:
        return ()

    cek = pemeriksa or (lambda ip: _postgres_menjawab(ip, port=port))
    if pemeriksa is None:
        with ThreadPoolExecutor(max_workers=48) as kolam:
            jawaban = list(kolam.map(cek, calon))
    else:
        jawaban = [bool(cek(ip)) for ip in calon]
    return tuple(ip for ip, ya in zip(calon, jawaban) if ya)


def _postgres_menjawab(ip: str, waktu: float = 0.3, port: int = PORT_BAWAAN) -> bool:
    """Benar bila port itu menjawab seperti PostgreSQL, tanpa masuk."""
    try:
        with socket.create_connection((ip, port), waktu) as soket:
            soket.settimeout(waktu)
            # Permintaan SSL. Jawabannya satu byte: S, N, atau E.
            soket.sendall(struct.pack("!II", 8, 80877103))
            jawab = soket.recv(1)
    except OSError:
        return False
    return jawab in (b"S", b"N", b"E")


@dataclass(frozen=True)
class HasilSiapkan:
    """Akibat tombol Siapkan database. Sandi postgres tidak ikut pulang."""

    gagal: str | None = None
    peringatan: str | None = None


def siapkan_database_lokal(
    sandi_antrian: str,
    sandi_postgres: str,
    port: int = PORT_BAWAAN,
) -> HasilSiapkan:
    """
    Buat pengguna dan database antrian di PostgreSQL komputer ini.

    Sandi postgres dipakai sekali untuk perintah itu, lalu dibuang.
    Sandi antrian yang sedang di form menjadi sandi pengguna antrian.
    """
    if not sandi_antrian:
        return HasilSiapkan(
            gagal=(
                "Isi kata sandi database antrian terlebih dahulu. "
                "Sandi itulah yang akan dibuat."
            )
        )
    if not sandi_postgres:
        return HasilSiapkan(gagal="Kata sandi pengguna postgres belum diisi.")

    try:
        import psycopg
        from psycopg import sql
    except ImportError:
        return HasilSiapkan(gagal="Pengandar PostgreSQL tidak terpasang.")

    try:
        conn = psycopg.connect(
            host=HOST_LOKAL,
            port=port,
            dbname="postgres",
            user="postgres",
            password=sandi_postgres,
            connect_timeout=3,
            autocommit=True,
        )
    except Exception as exc:
        logger.warning("Penyiapan database gagal masuk: %s", type(exc).__name__)
        return HasilSiapkan(gagal=pesan_kegagalan_koneksi(exc))

    peringatan = None
    try:
        with conn.cursor() as cur:
            _pastikan_peran(cur, sql, PENGGUNA_BAWAAN, sandi_antrian)
            _pastikan_database(cur, sql, DATABASE_BAWAAN, PENGGUNA_BAWAAN)
            cur.execute("SHOW hba_file")
            baris = cur.fetchone()
            lokasi = Path(baris[0]) if baris and baris[0] else None
        if lokasi is not None:
            peringatan = _tambahkan_izin_jaringan(lokasi)
            if peringatan is None:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_reload_conf()")
    except Exception as exc:
        logger.warning("Penyiapan database gagal: %s", type(exc).__name__)
        return HasilSiapkan(
            gagal=(
                "Pengguna postgres masuk, tetapi database antrian tidak "
                "dapat dibuat."
            )
        )
    finally:
        conn.close()

    logger.info("Database antrian disiapkan di komputer ini")
    return HasilSiapkan(peringatan=peringatan)


def _pastikan_peran(cur, sql, nama: str, sandi: str) -> None:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (nama,))
    perintah = "ALTER ROLE {} WITH LOGIN PASSWORD {}"
    if cur.fetchone() is None:
        perintah = "CREATE ROLE {} WITH LOGIN PASSWORD {}"
    cur.execute(
        sql.SQL(perintah).format(sql.Identifier(nama), sql.Literal(sandi))
    )


def _pastikan_database(cur, sql, nama: str, pemilik: str) -> None:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nama,))
    if cur.fetchone() is None:
        cur.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(nama), sql.Identifier(pemilik)
            )
        )


def _tambahkan_izin_jaringan(path: Path) -> str | None:
    """
    Izinkan subnet kantor menyambung sebagai antrian.

    None bila sudah tertulis. Pesan bila berkasnya tidak dapat diubah:
    database lokal tetap jadi, komputer lain yang belum.
    """
    subnet = subnet_kantor()
    if not subnet:
        return (
            "Database dibuat di komputer ini. Alamat jaringan tidak "
            "terbaca, jadi komputer lain belum diizinkan masuk."
        )
    try:
        isi = path.read_text(encoding="utf-8")
    except OSError:
        return _pesan_hba_manual(subnet)
    tambahan = tambahan_izin_hba(isi, subnet)
    if not tambahan:
        return None
    try:
        with path.open("a", encoding="utf-8") as berkas:
            berkas.write(tambahan)
    except OSError:
        return _pesan_hba_manual(subnet)
    return None


def _pesan_hba_manual(subnet: tuple[str, ...]) -> str:
    baris = "\n".join(
        f"host    antrian    antrian    {jaringan}    scram-sha-256"
        for jaringan in subnet
    )
    return (
        "Database antrian sudah dibuat. Komputer lain belum diizinkan "
        "karena file pg_hba.conf tidak dapat ditulis. Tambahkan baris "
        f"berikut, lalu muat ulang PostgreSQL:\n{baris}"
    )
