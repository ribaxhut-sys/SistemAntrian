"""
Pembaruan aplikasi Windows yang dibagikan komputer server lewat LAN.

Metadata dan installer datang lewat HTTP polos dari server yang sama, jadi
SHA-256 di metadata hanya menangkap unduhan rusak, bukan installer yang
sengaja diganti (penyerang yang menyamar sebagai server dapat mengganti
keduanya). Yang dipercaya adalah TANDA TANGAN Ed25519 pengembang atas
(versi, ukuran, SHA-256), diverifikasi terhadap kunci publik tertanam
(`app/core/kunci_publik.py`). Kunci rahasianya tidak pernah ada di server
maupun di installer; berkas `.sig` dibuat dengan
`alat/tandatangani_pembaruan.py` di komputer pengembang.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app import __version__
from app.core.config import AppConfig, get_config
from app.core.errors import AppError
from app.core.kunci_publik import KUNCI_PUBLIK_BASE64
from app.core.logger import get_logger
from app.services.auth_service import AuthService

logger = get_logger("pembaruan")

NAMA_FOLDER = "pembaruan"
NAMA_INSTALLER = "Pembaruan-AntrianCRO.exe"
NAMA_VERSI = "Pembaruan-AntrianCRO.version"
NAMA_TANDA = "Pembaruan-AntrianCRO.sig"
#: Pemisah domain: kunci yang sama juga menandatangani pemulihan admin
#: (`pemulihan_admin.DOMAIN`); tanda tangan satu jenis tidak boleh sah
#: sebagai jenis lainnya.
DOMAIN_PEMBARUAN = b"antrian-pembaruan-windows-v1\x00"
BATAS_MANIFEST_BYTE = 64 * 1024
BATAS_INSTALLER_BYTE = 750 * 1024 * 1024
CADANGAN_RUANG_BYTE = 64 * 1024 * 1024


class PembaruanError(AppError):
    default_message = "Pembaruan belum dapat diunduh. Periksa jaringan lalu coba lagi."


@dataclass(frozen=True)
class InfoPembaruan:
    versi: str
    berkas: Path
    ukuran_byte: int
    sha256: str
    #: Tanda tangan Ed25519 (base64) atas `pesan_tanda_tangan`; "" bila tidak ada.
    tanda: str = ""


def pesan_tanda_tangan(versi: str, ukuran_byte: int, sha256: str) -> bytes:
    """Byte yang ditandatangani pengembang untuk satu rilis installer."""
    return DOMAIN_PEMBARUAN + f"{versi}\n{int(ukuran_byte)}\n{sha256.lower()}".encode(
        "ascii"
    )


def tanda_sah(info: InfoPembaruan, kunci_publik_b64: str | None = None) -> bool:
    """Benar bila `info.tanda` dibuat pemilik kunci publik untuk rilis ini."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    kunci_b64 = (KUNCI_PUBLIK_BASE64 if kunci_publik_b64 is None else kunci_publik_b64).strip()
    if not kunci_b64 or not info.tanda:
        return False
    try:
        kunci_b64 += "=" * (-len(kunci_b64) % 4)
        kunci = Ed25519PublicKey.from_public_bytes(base64.b64decode(kunci_b64))
        tanda = base64.b64decode(info.tanda.strip(), validate=True)
        kunci.verify(tanda, pesan_tanda_tangan(info.versi, info.ukuran_byte, info.sha256))
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True


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
    try:
        tanda = (folder / NAMA_TANDA).read_text(encoding="utf-8-sig").strip()
    except OSError:
        # Tetap dibagikan: klien yang memegang kunci publik menolaknya
        # sendiri, dan Kesehatan/log server yang memberi tahu pemasang.
        tanda = ""
    return InfoPembaruan(versi, installer, ukuran, sha256, tanda)


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
    alamat_api: str | None = None,
    *,
    versi_terpasang: str = __version__,
    kunci_publik_b64: str | None = None,
) -> InfoPembaruan | None:
    """
    Tanya server; kegagalan jaringan tidak mengganggu pekerjaan petugas.

    Pembaruan tanpa tanda tangan sah tidak ditawarkan sama sekali bila
    kunci publik tertanam. Tanpa kunci publik (build tanpa fitur kunci)
    perilaku lama berlaku: hanya SHA-256 dari server.
    """
    kunci = KUNCI_PUBLIK_BASE64 if kunci_publik_b64 is None else kunci_publik_b64
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
        tanda = str(data.get("signature") or "")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        return None
    info = InfoPembaruan(versi, Path(NAMA_INSTALLER), ukuran, sha256, tanda)
    if kunci.strip() and not tanda_sah(info, kunci):
        logger.warning(
            "Pembaruan %s dari server diabaikan: tanda tangan %s",
            versi,
            "tidak ada" if not tanda else "tidak sah",
        )
        return None
    return info


def unduh_pembaruan(
    info: InfoPembaruan,
    alamat_api: str | None = None,
    *,
    kemajuan: Callable[[int, int], None] | None = None,
) -> Path:
    """Unduh atomik sambil melaporkan progres, lalu verifikasi sebelum dipakai."""
    alamat_api = alamat_api or alamat_api_pembaruan()
    if not alamat_api:
        raise PembaruanError("Alamat komputer server belum tersedia.")
    tujuan_dir = Path(tempfile.gettempdir()) / "AntrianCRO" / "pembaruan"
    tujuan_dir.mkdir(parents=True, exist_ok=True)
    ruang_bebas = shutil.disk_usage(tujuan_dir).free
    if ruang_bebas < info.ukuran_byte + CADANGAN_RUANG_BYTE:
        raise PembaruanError(
            "Ruang penyimpanan tidak cukup untuk mengunduh pembaruan. "
            "Kosongkan sedikit ruang lalu coba lagi."
        )
    tujuan = tujuan_dir / f"AntrianCRO-Setup-{info.versi}.exe"
    sementara = tujuan.with_suffix(".exe.tmp")
    ringkasan = hashlib.sha256()
    jumlah = 0
    if kemajuan is not None:
        kemajuan(0, info.ukuran_byte)
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
                if kemajuan is not None:
                    kemajuan(jumlah, info.ukuran_byte)
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


class PembaruanWindowsService:
    """Aturan pemasangan yang bergantung pada sesi dan keadaan pelayanan."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    def pastikan_pemasangan_diizinkan(self) -> None:
        """
        CRO tidak boleh ditutup ketika masih bertanggung jawab atas pengunjung.

        Admin dan peran baca tidak memegang nomor pelayanan, sehingga tidak
        perlu melewati pemeriksaan ini. Penjaga berada di service, bukan hanya
        pada keadaan tombol, agar jalur UI lain tidak dapat melewatinya.
        """
        from app.core import clock
        from app.core.database import session_scope
        from app.core.errors import BusinessRuleError
        from app.models.enums import UserRole
        from app.repositories.queue_repository import QueueRepository

        sesi = self.auth.require_session()
        if sesi.role is not UserRole.CRO:
            return
        with session_scope() as session:
            aktif = QueueRepository(session).list_sedang_ditangani(
                sesi.branch_id, clock.today()
            )
            milik_petugas = next(
                (baris for baris in aktif if baris.served_by_user_id == sesi.user_id),
                None,
            )
        if milik_petugas is not None:
            raise BusinessRuleError(
                f"Selesaikan atau alihkan nomor {milik_petugas.queue_number} "
                "sebelum memasang pembaruan."
            )
