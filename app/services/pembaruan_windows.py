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
import logging
import os
import shutil
import socket
import threading
import time
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from datetime import date, timedelta

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
#: Catatan rilis opsional, teks biasa, ditulis alat tanda tangan.
NAMA_CATATAN = "Pembaruan-AntrianCRO.catatan.txt"
BATAS_CATATAN = 1500
#: Pemisah domain: kunci yang sama juga menandatangani pemulihan admin
#: (`pemulihan_admin.DOMAIN`); tanda tangan satu jenis tidak boleh sah
#: sebagai jenis lainnya.
DOMAIN_PEMBARUAN = b"antrian-pembaruan-windows-v1\x00"
BATAS_MANIFEST_BYTE = 64 * 1024
BATAS_INSTALLER_BYTE = 750 * 1024 * 1024
CADANGAN_RUANG_BYTE = 64 * 1024 * 1024
NAMA_STATUS_LOKAL = "pembaruan-lokal.json"


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
    #: "Apa yang baru" untuk petugas. TIDAK ikut ditandatangani: hanya
    #: keterangan yang ditampilkan sebagai teks biasa, bukan penentu apa
    #: pun; installer tetap dijaga tanda tangan atas versi, ukuran, SHA-256.
    catatan: str = ""


def bersihkan_catatan(teks: str) -> str:
    """Teks biasa tanpa karakter kendali, dipotong ke BATAS_CATATAN."""
    baris = [
        "".join(c for c in b if c == "\t" or c.isprintable()).rstrip()
        for b in str(teks or "").strip().splitlines()
    ]
    bersih = "\n".join(baris).strip()
    if len(bersih) > BATAS_CATATAN:
        bersih = bersih[: BATAS_CATATAN - 1].rstrip() + "…"
    return bersih


def _path_status_lokal(config: AppConfig | None = None) -> Path:
    return (config or get_config()).db_path.parent / NAMA_STATUS_LOKAL


def _baca_status_lokal(config: AppConfig | None = None) -> dict:
    try:
        isi = json.loads(_path_status_lokal(config).read_text(encoding="utf-8"))
        return isi if isinstance(isi, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _tulis_status_lokal(isi: dict, config: AppConfig | None = None) -> None:
    tujuan = _path_status_lokal(config)
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    sementara = tujuan.with_suffix(".json.tmp")
    sementara.write_text(json.dumps(isi, ensure_ascii=False), encoding="utf-8")
    sementara.replace(tujuan)


def tunda_pembaruan(
    versi: str,
    *,
    sampai: date | None = None,
    config: AppConfig | None = None,
) -> None:
    """Tunda satu versi sampai besok tanpa memengaruhi komputer lain."""
    bagian_versi(versi)
    isi = _baca_status_lokal(config)
    isi["tunda"] = {
        "versi": versi,
        "sampai": (sampai or (date.today() + timedelta(days=1))).isoformat(),
    }
    _tulis_status_lokal(isi, config)


def pembaruan_ditunda(
    versi: str, *, hari: date | None = None, config: AppConfig | None = None
) -> bool:
    """Berkas lokal rusak dianggap tidak menunda agar pembaruan tetap terlihat."""
    try:
        isi = _baca_status_lokal(config)["tunda"]
        batas = date.fromisoformat(str(isi["sampai"]))
        return str(isi["versi"]) == versi and (hari or date.today()) < batas
    except (ValueError, KeyError, TypeError):
        return False


def catat_pemasangan_dimulai(
    versi: str, *, config: AppConfig | None = None
) -> None:
    """Simpan target agar pembukaan aplikasi berikutnya dapat diaudit."""
    try:
        bagian_versi(versi)
        isi = _baca_status_lokal(config)
        isi["pemasangan"] = {"dari": __version__, "tujuan": versi}
        _tulis_status_lokal(isi, config)
    except (OSError, ValueError):
        logger.warning("Penanda hasil pembaruan tidak dapat disimpan", exc_info=True)


def audit_hasil_pembaruan(
    *, versi_terpasang: str = __version__, config: AppConfig | None = None
) -> bool | None:
    """Catat berhasil/gagal sekali sesudah aplikasi hidup kembali."""
    isi = _baca_status_lokal(config)
    pemasangan = isi.get("pemasangan")
    if not isinstance(pemasangan, dict) or not pemasangan.get("tujuan"):
        return None
    tujuan = str(pemasangan["tujuan"])
    berhasil = versi_terpasang == tujuan

    from app.core.database import session_scope
    from app.models import AuditAction
    from app.services import audit_service

    with session_scope() as session:
        audit_service.record(
            session,
            AuditAction.WINDOWS_UPDATE_RESULT,
            user_id=None,
            entity_type="windows_update",
            versi_dari=str(pemasangan.get("dari") or ""),
            versi_tujuan=tujuan,
            versi_terpasang=versi_terpasang,
            berhasil=berhasil,
        )
    isi.pop("pemasangan", None)
    try:
        _tulis_status_lokal(isi, config)
    except OSError:
        logger.warning("Penanda hasil pembaruan tidak dapat dibersihkan", exc_info=True)
    logger.log(
        logging.INFO if berhasil else logging.WARNING,
        "Hasil pembaruan ke %s: %s (terpasang %s)",
        tujuan,
        "berhasil" if berhasil else "gagal",
        versi_terpasang,
    )
    return berhasil


def pesan_tanda_tangan(
    versi: str, ukuran_byte: int, sha256: str, catatan: str = ""
) -> bytes:
    """Byte yang ditandatangani pengembang, termasuk catatan bila ada."""
    pesan = f"{versi}\n{int(ukuran_byte)}\n{sha256.lower()}"
    if catatan:
        pesan += f"\n{bersihkan_catatan(catatan)}"
    return DOMAIN_PEMBARUAN + pesan.encode("utf-8")


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
        kunci.verify(
            tanda,
            pesan_tanda_tangan(
                info.versi, info.ukuran_byte, info.sha256, info.catatan
            ),
        )
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
    try:
        catatan = bersihkan_catatan(
            (folder / NAMA_CATATAN).read_text(encoding="utf-8-sig")
        )
    except (OSError, UnicodeDecodeError):
        catatan = ""
    return InfoPembaruan(versi, installer, ukuran, sha256, tanda, catatan)


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
        permintaan = urllib.request.Request(  # noqa: S310 - host dari konfigurasi lokal
            f"{alamat_api.rstrip('/')}/v1/windows/update",
            headers={
                "X-Komputer": bersihkan_nama_pc(socket.gethostname()),
                "X-Versi-App": versi_terpasang,
            },
        )
        with urllib.request.urlopen(permintaan, timeout=4) as jawaban:  # noqa: S310
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
        catatan = bersihkan_catatan(data.get("release_notes") or "")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
        return None
    info = InfoPembaruan(versi, Path(NAMA_INSTALLER), ukuran, sha256, tanda, catatan)
    if kunci.strip() and not tanda_sah(info, kunci):
        logger.warning(
            "Pembaruan %s dari server diabaikan: tanda tangan %s",
            versi,
            "tidak ada" if not tanda else "tidak sah",
        )
        return None
    if pembaruan_ditunda(versi):
        return None
    return info


def unduh_pembaruan(
    info: InfoPembaruan,
    alamat_api: str | None = None,
    *,
    kemajuan: Callable[[int, int], None] | None = None,
) -> Path:
    """Lanjutkan unduhan terputus, lalu verifikasi penuh sebelum dipakai."""
    alamat_api = alamat_api or alamat_api_pembaruan()
    if not alamat_api:
        raise PembaruanError("Alamat komputer server belum tersedia.")
    tujuan_dir = Path(tempfile.gettempdir()) / "AntrianCRO" / "pembaruan"
    tujuan_dir.mkdir(parents=True, exist_ok=True)
    tujuan = tujuan_dir / f"Sistem-Antrian-CRO-Setup-Windows-{info.versi}.exe"
    sementara = tujuan.with_suffix(".exe.tmp")
    ringkasan = hashlib.sha256()
    try:
        jumlah = sementara.stat().st_size
    except OSError:
        jumlah = 0
    if jumlah < 0 or jumlah >= info.ukuran_byte:
        sementara.unlink(missing_ok=True)
        jumlah = 0
    if jumlah:
        with sementara.open("rb") as bagian_lama:
            for blok in iter(lambda: bagian_lama.read(1024 * 1024), b""):
                ringkasan.update(blok)

    ruang_bebas = shutil.disk_usage(tujuan_dir).free
    if ruang_bebas < (info.ukuran_byte - jumlah) + CADANGAN_RUANG_BYTE:
        raise PembaruanError(
            "Ruang penyimpanan tidak cukup untuk mengunduh pembaruan. "
            "Kosongkan sedikit ruang lalu coba lagi."
        )
    if kemajuan is not None:
        kemajuan(jumlah, info.ukuran_byte)
    try:
        alamat = f"{alamat_api.rstrip('/')}/v1/windows/update/download"
        header = {"Range": f"bytes={jumlah}-"} if jumlah else {}
        permintaan = urllib.request.Request(alamat, headers=header)
        with urllib.request.urlopen(  # noqa: S310 - host dari konfigurasi lokal
            permintaan, timeout=30
        ) as sumber:
            melanjutkan = jumlah > 0 and getattr(sumber, "status", None) == 206
            if jumlah and not melanjutkan:
                # Server lama boleh mengabaikan Range. Mulai ulang dari byte
                # pertama agar dua salinan installer tidak tergabung.
                jumlah = 0
                ringkasan = hashlib.sha256()
                if kemajuan is not None:
                    kemajuan(0, info.ukuran_byte)
            mode = "ab" if melanjutkan else "wb"
            keluaran = sementara.open(mode)
            try:
                while blok := sumber.read(1024 * 1024):
                    jumlah += len(blok)
                    if jumlah > BATAS_INSTALLER_BYTE or jumlah > info.ukuran_byte:
                        raise PembaruanError("Ukuran berkas pembaruan tidak sesuai.")
                    ringkasan.update(blok)
                    keluaran.write(blok)
                    if kemajuan is not None:
                        kemajuan(jumlah, info.ukuran_byte)
            finally:
                keluaran.close()
        if jumlah != info.ukuran_byte or ringkasan.hexdigest() != info.sha256:
            sementara.unlink(missing_ok=True)
            raise PembaruanError("Berkas pembaruan tidak lolos pemeriksaan keamanan.")
        sementara.replace(tujuan)
        return tujuan
    except PembaruanError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        # Bagian yang selesai ditulis sengaja dipertahankan. Percobaan
        # berikutnya meminta sisa byte dan checksum penuh tetap menjadi
        # penjaga sebelum installer boleh dijalankan.
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


# --- Denyut PC: PC yang membuka aplikasi melapor versinya ke server --------

JEDA_DENYUT_DETIK = 6 * 3600
BATAS_DENYUT_PER_JAM = 120
_kunci_denyut = threading.Lock()
_denyut_terakhir: dict[str, float] = {}
_denyut_jam: list[float] = []


def bersihkan_nama_pc(nama: str) -> str:
    """Nama komputer dari header: huruf/angka/-/_/. saja, maksimal 80."""
    bersih = "".join(c for c in str(nama) if c.isalnum() or c in "-_.")
    return bersih[:80]


def catat_denyut_pc(komputer: str, versi: str, alamat_ip: str = "") -> bool:
    """
    Catat satu PC Windows terlihat hidup. Endpoint pembaruan tidak berotentikasi,
    jadi penulisan dibatasi: satu catatan per PC per 6 jam dan paling banyak
    120 catatan per jam seluruhnya, supaya audit tidak dibanjiri.
    """
    komputer = bersihkan_nama_pc(komputer)
    versi = "".join(c for c in str(versi) if c.isdigit() or c == ".")[:20]
    if not komputer or not versi:
        return False
    sekarang = time.monotonic()
    with _kunci_denyut:
        if sekarang - _denyut_terakhir.get(komputer, -1e12) < JEDA_DENYUT_DETIK:
            return False
        _denyut_jam[:] = [t for t in _denyut_jam if sekarang - t < 3600]
        if len(_denyut_jam) >= BATAS_DENYUT_PER_JAM:
            return False
        _denyut_jam.append(sekarang)
        _denyut_terakhir[komputer] = sekarang
    try:
        from app.core.database import session_scope
        from app.models import AuditAction
        from app.services import audit_service

        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.WINDOWS_PC_PING,
                user_id=None,
                entity_type="windows_pc",
                komputer=komputer,
                versi_aplikasi=versi,
                alamat_ip=str(alamat_ip)[:45],
            )
    except Exception:  # noqa: BLE001 - denyut tidak boleh mengganggu pembaruan
        logger.warning("Denyut PC tidak dapat dicatat", exc_info=True)
        return False
    return True
