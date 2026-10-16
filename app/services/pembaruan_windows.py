"""Pembaruan aplikasi Windows yang dibagikan komputer server lewat LAN."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app import __version__
from app.core.config import AppConfig, get_config
from app.core.errors import AppError

NAMA_FOLDER = "pembaruan"
NAMA_INSTALLER = "Pembaruan-AntrianCRO.exe"
NAMA_VERSI = "Pembaruan-AntrianCRO.version"
BATAS_MANIFEST_BYTE = 64 * 1024
BATAS_INSTALLER_BYTE = 750 * 1024 * 1024


class PembaruanError(AppError):
    default_message = "Pembaruan belum dapat diunduh. Periksa jaringan lalu coba lagi."


@dataclass(frozen=True)
class InfoPembaruan:
    versi: str
    berkas: Path
    ukuran_byte: int
    sha256: str


def folder_pembaruan(base: Path) -> Path:
    return Path(base) / NAMA_FOLDER


def bagian_versi(versi: str) -> tuple[int, ...]:
    bagian = versi.strip().split(".")
    if not bagian or len(bagian) > 4 or any(not nilai.isdigit() for nilai in bagian):
        raise ValueError("Format versi tidak sah")
    return tuple(int(nilai) for nilai in bagian)


def lebih_baru(calon: str, terpasang: str = __version__) -> bool:
    a = bagian_versi(calon)
    b = bagian_versi(terpasang)
    panjang = max(len(a), len(b))
    return a + (0,) * (panjang - len(a)) > b + (0,) * (panjang - len(b))


@lru_cache(maxsize=8)
def _sha256_tersimpan(path_teks: str, ukuran: int, waktu_ubah_ns: int) -> str:
    # ukuran dan waktu_ubah_ns menjadi bagian kunci cache; bila installer
    # diganti saat rilis berikutnya, checksum otomatis dihitung ulang.
    path = Path(path_teks)
    ringkasan = hashlib.sha256()
    with path.open("rb") as berkas:
        for blok in iter(lambda: berkas.read(1024 * 1024), b""):
            ringkasan.update(blok)
    return ringkasan.hexdigest()


def _sha256(path: Path) -> str:
    stat = path.stat()
    return _sha256_tersimpan(str(path.resolve()), stat.st_size, stat.st_mtime_ns)


def info_pembaruan(folder: Path) -> InfoPembaruan | None:
    """Installer server yang lengkap, atau None bila belum dipublikasikan."""
    folder = Path(folder)
    installer = folder / NAMA_INSTALLER
    try:
        versi = (folder / NAMA_VERSI).read_text(encoding="utf-8-sig").strip()
        bagian_versi(versi)
        ukuran = installer.stat().st_size
        if ukuran <= 0 or ukuran > BATAS_INSTALLER_BYTE:
            return None
        sha256 = _sha256(installer)
    except (OSError, ValueError):
        return None
    return InfoPembaruan(versi, installer, ukuran, sha256)


def alamat_api_pembaruan(config: AppConfig | None = None) -> str | None:
    """Alamat API diturunkan dari host database yang telah dikonfigurasi."""
    config = config or get_config()
    if config.memakai_sqlite:
        return None
    host = config.url_database.host
    if not host:
        return None
    port = int(os.environ.get("ANTRIAN_KIOS_API_PORT", "8765"))
    return f"http://{host}:{port}"


def periksa_pembaruan(
    alamat_api: str | None = None, *, versi_terpasang: str = __version__
) -> InfoPembaruan | None:
    """Tanya server; kegagalan jaringan tidak mengganggu pekerjaan petugas."""
    alamat_api = alamat_api or alamat_api_pembaruan()
    if not alamat_api:
        return None
    try:
        with urllib.request.urlopen(  # noqa: S310 - host dari konfigurasi lokal
            f"{alamat_api.rstrip('/')}/v1/windows/update", timeout=4
        ) as jawaban:
            mentah = jawaban.read(BATAS_MANIFEST_BYTE + 1)
        if len(mentah) > BATAS_MANIFEST_BYTE:
            return None
        data = json.loads(mentah)
        versi = str(data["latest_version"])
        ukuran = int(data["size"])
        sha256 = str(data["sha256"]).lower()
        if not lebih_baru(versi, versi_terpasang):
            return None
        if not (0 < ukuran <= BATAS_INSTALLER_BYTE):
            return None
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            return None
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return InfoPembaruan(versi, Path(NAMA_INSTALLER), ukuran, sha256)


def unduh_pembaruan(info: InfoPembaruan, alamat_api: str | None = None) -> Path:
    """Unduh atomik dan verifikasi ukuran serta SHA-256 sebelum dipakai."""
    alamat_api = alamat_api or alamat_api_pembaruan()
    if not alamat_api:
        raise PembaruanError("Alamat komputer server belum tersedia.")
    tujuan_dir = Path(tempfile.gettempdir()) / "AntrianCRO" / "pembaruan"
    tujuan_dir.mkdir(parents=True, exist_ok=True)
    tujuan = tujuan_dir / f"AntrianCRO-Setup-{info.versi}.exe"
    sementara = tujuan.with_suffix(".exe.tmp")
    ringkasan = hashlib.sha256()
    jumlah = 0
    try:
        with urllib.request.urlopen(  # noqa: S310 - host dari konfigurasi lokal
            f"{alamat_api.rstrip('/')}/v1/windows/update/download", timeout=30
        ) as sumber, sementara.open("wb") as keluaran:
            while blok := sumber.read(1024 * 1024):
                jumlah += len(blok)
                if jumlah > BATAS_INSTALLER_BYTE or jumlah > info.ukuran_byte:
                    raise PembaruanError("Ukuran berkas pembaruan tidak sesuai.")
                ringkasan.update(blok)
                keluaran.write(blok)
        if jumlah != info.ukuran_byte or ringkasan.hexdigest() != info.sha256:
            raise PembaruanError("Berkas pembaruan tidak lolos pemeriksaan keamanan.")
        sementara.replace(tujuan)
        return tujuan
    except PembaruanError:
        sementara.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError) as exc:
        sementara.unlink(missing_ok=True)
        raise PembaruanError(detail=type(exc).__name__) from exc
