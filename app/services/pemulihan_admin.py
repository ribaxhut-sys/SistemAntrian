"""
Pemulihan akun admin yang lupa kata sandinya, lewat kunci dari pengembang.

Tanpa akun ADMIN lain, tidak ada yang dapat mereset admin. Rancangannya
tantangan-respons dengan tanda tangan digital (Ed25519):

1. Aplikasi membuat KODE TANTANGAN: ID pemasangan, nama akun, nomor acak
   sekali pakai, dan masa berlaku.
2. Admin mengirimkannya kepada pengembang, yang menandatanganinya dengan
   kunci rahasia miliknya dan mengirim balik KUNCI RESPONS.
3. Aplikasi memverifikasi tanda tangan dengan kunci PUBLIK yang tertanam
   (`app/core/kunci_publik.py`) lalu mengizinkan kata sandi baru.

Yang tertanam hanya kunci publik, sehingga tidak dapat dipakai membuat
tanda tangan. Respons berlaku untuk satu pemasangan, satu akun, dan satu
kali pakai.

Batasnya, secara jujur: orang yang memegang akun `postgres` atau
administrator Windows di server tetap dapat mengubah database langsung.
Ini melindungi dari upaya lewat aplikasi, bukan dari akses penuh ke server.
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import AuthenticationError, ValidationError
from app.core.kunci_publik import KUNCI_PUBLIK_BASE64
from app.core.logger import get_logger
from app.core.security import hash_password
from app.models import ApplicationSetting, AuditLog, RecordStatus, User, UserRole
from app.services import audit_service

logger = get_logger("pemulihan_admin")

#: Pemisah domain: tanda tangan untuk tujuan lain tidak dapat dipakai di sini.
DOMAIN = b"antrian-reset-admin-v1\x00"
VERSI = 1
MASA_BERLAKU = timedelta(hours=24)

AWALAN_TANTANGAN = "ANTR"
AWALAN_RESPONS = "RESP"

#: Percobaan respons yang salah sebelum ditunda.
BATAS_GAGAL = 5
JENDELA_GAGAL = timedelta(minutes=5)

KUNCI_INSTALASI = "instalasi.id"
KUNCI_NONCE_TERPAKAI = "pemulihan.nonce_terpakai"
AKSI_RESET = "RESET_ADMIN_KEY"
AKSI_GAGAL = "RESET_ADMIN_GAGAL"

#: Nonce terpakai yang diingat. Masa berlaku 24 jam membuat daftar pendek cukup.
_NONCE_DIINGAT = 50


@dataclass(frozen=True)
class Tantangan:
    instalasi: str
    username: str
    nonce: bytes
    kedaluwarsa: datetime
    mentah: bytes

    @property
    def nonce_hex(self) -> str:
        return self.nonce.hex()


# =====================================================================
# Pengodean kode
# =====================================================================


def _kodekan(awalan: str, data: bytes) -> str:
    teks = base64.b32encode(data).decode("ascii").rstrip("=")
    kelompok = [teks[i : i + 4] for i in range(0, len(teks), 4)]
    return "-".join([awalan, *kelompok])


def _urai(awalan: str, kode: str) -> bytes:
    bersih = "".join(ch for ch in kode.upper() if ch.isalnum())
    if not bersih.startswith(awalan):
        raise ValidationError("Kode tidak dikenali.")
    isi = bersih[len(awalan) :]
    isi += "=" * (-len(isi) % 8)
    try:
        return base64.b32decode(isi)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError("Kode tidak valid; periksa apakah tersalin utuh.") from exc


def _ke_epoch(waktu: datetime) -> int:
    return int(waktu.replace(tzinfo=clock.tzinfo()).timestamp())


def _dari_epoch(detik: int) -> datetime:
    return datetime.fromtimestamp(detik, clock.tzinfo()).replace(tzinfo=None)


def kemas_tantangan(
    instalasi: str, username: str, nonce: bytes, kedaluwarsa: datetime
) -> bytes:
    nama = username.encode("utf-8")
    if not 1 <= len(nama) <= 60:
        raise ValidationError("Nama pengguna tidak valid.")
    return (
        struct.pack(">B16s8sIB", VERSI, bytes.fromhex(instalasi), nonce,
                    _ke_epoch(kedaluwarsa), len(nama))
        + nama
    )


def baca_tantangan(kode: str) -> Tantangan:
    """Urai kode tantangan. Tidak memeriksa masa berlaku maupun tanda tangan."""
    mentah = _urai(AWALAN_TANTANGAN, kode)
    ukuran = struct.calcsize(">B16s8sIB")
    if len(mentah) < ukuran:
        raise ValidationError("Kode tantangan tidak lengkap.")
    versi, instalasi, nonce, epoch, panjang = struct.unpack(">B16s8sIB", mentah[:ukuran])
    if versi != VERSI:
        raise ValidationError("Versi kode tantangan tidak didukung.")
    nama = mentah[ukuran : ukuran + panjang]
    if len(nama) != panjang or len(mentah) != ukuran + panjang:
        raise ValidationError("Kode tantangan tidak lengkap.")
    try:
        username = nama.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("Kode tantangan tidak valid.") from exc
    return Tantangan(
        instalasi=instalasi.hex(),
        username=username,
        nonce=nonce,
        kedaluwarsa=_dari_epoch(epoch),
        mentah=mentah,
    )


def data_ditandatangani(mentah: bytes) -> bytes:
    """Byte yang ditandatangani pengembang: domain + isi tantangan."""
    return DOMAIN + mentah


def kode_respons(tanda_tangan: bytes) -> str:
    return _kodekan(AWALAN_RESPONS, tanda_tangan)


def baca_respons(kode: str) -> bytes:
    tanda = _urai(AWALAN_RESPONS, kode)
    if len(tanda) != 64:
        raise ValidationError("Kunci respons tidak lengkap; periksa apakah tersalin utuh.")
    return tanda


def verifikasi(mentah: bytes, tanda_tangan: bytes, kunci_publik_b64: str) -> bool:
    """Benar bila `tanda_tangan` sah atas tantangan oleh pemilik kunci publik."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        # Toleran terhadap "=" yang terpotong saat disalin.
        bersih = kunci_publik_b64.strip()
        bersih += "=" * (-len(bersih) % 4)
        kunci = Ed25519PublicKey.from_public_bytes(base64.b64decode(bersih))
        kunci.verify(tanda_tangan, data_ditandatangani(mentah))
    except (InvalidSignature, ValueError, binascii.Error):
        return False
    return True


# =====================================================================
# Keadaan pemasangan
# =====================================================================


def kunci_terpasang(kunci_publik_b64: str | None = None) -> bool:
    return bool((KUNCI_PUBLIK_BASE64 if kunci_publik_b64 is None else kunci_publik_b64).strip())


def _baca_setelan(session, kunci: str) -> str | None:
    baris = session.scalar(
        sa.select(ApplicationSetting).where(ApplicationSetting.key == kunci)
    )
    return baris.value if baris is not None else None


def _tulis_setelan(session, kunci: str, nilai: str) -> None:
    baris = session.scalar(
        sa.select(ApplicationSetting).where(ApplicationSetting.key == kunci)
    )
    if baris is None:
        session.add(ApplicationSetting(key=kunci, value=nilai))
    else:
        baris.value = nilai


def id_instalasi() -> str:
    """ID unik pemasangan ini (32 heksadesimal); dibuat sekali saat pertama dibutuhkan."""
    with session_scope() as session:
        nilai = _baca_setelan(session, KUNCI_INSTALASI)
        if nilai and len(nilai) == 32:
            return nilai
        baru = uuid.uuid4().hex
        _tulis_setelan(session, KUNCI_INSTALASI, baru)
        return baru


# =====================================================================
# Alur
# =====================================================================


def buat_tantangan(username: str) -> str:
    """Kode tantangan untuk akun admin `username`; berlaku 24 jam."""
    nama = username.strip().lower()
    if not nama:
        raise ValidationError("Nama akun belum diisi.")
    # Tidak memeriksa apakah akunnya ada atau berperan admin: jawaban yang
    # berbeda akan membuka daftar akun admin kepada siapa pun di layar masuk.
    # Pemeriksaan dilakukan saat `pulihkan`, setelah tanda tangan terbukti sah.
    mentah = kemas_tantangan(
        id_instalasi(), nama, secrets.token_bytes(8), clock.now() + MASA_BERLAKU
    )
    return _kodekan(AWALAN_TANTANGAN, mentah)


def _terlalu_banyak_gagal(session) -> bool:
    sejak = clock.now() - JENDELA_GAGAL
    jumlah = session.scalar(
        sa.select(sa.func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == AKSI_GAGAL, AuditLog.created_at >= sejak)
    )
    return (jumlah or 0) >= BATAS_GAGAL


def _catat_gagal(alasan: str) -> None:
    with session_scope() as session:
        audit_service.record(session, AKSI_GAGAL, alasan=alasan)


def pulihkan(
    kode_tantangan: str,
    kode_jawaban: str,
    password_baru: str,
    *,
    kunci_publik_b64: str | None = None,
) -> str:
    """
    Setel kata sandi admin bila respons sah. Mengembalikan nama akunnya.

    Akun ditandai wajib mengganti kata sandi pada login berikutnya, dan
    penundaan login akibat percobaan gagal sebelumnya dihapus lewat catatan
    audit `RESET_ADMIN_KEY` (lihat `AuthService._terlalu_banyak_gagal`).
    """
    kunci = (KUNCI_PUBLIK_BASE64 if kunci_publik_b64 is None else kunci_publik_b64).strip()
    if not kunci:
        raise ValidationError(
            "Pemulihan lewat pengembang belum diaktifkan pada pemasangan ini."
        )

    with session_scope() as session:
        if _terlalu_banyak_gagal(session):
            raise AuthenticationError(
                "Terlalu banyak percobaan yang gagal. Coba lagi dalam beberapa menit."
            )

    try:
        tantangan = baca_tantangan(kode_tantangan)
        tanda = baca_respons(kode_jawaban)
    except ValidationError:
        _catat_gagal("kode tidak terbaca")
        raise

    if tantangan.kedaluwarsa < clock.now():
        _catat_gagal("kedaluwarsa")
        raise ValidationError("Kode tantangan sudah kedaluwarsa. Buat kode baru.")
    if tantangan.instalasi != id_instalasi():
        _catat_gagal("pemasangan lain")
        raise ValidationError("Kode ini dibuat untuk pemasangan yang lain.")
    if not verifikasi(tantangan.mentah, tanda, kunci):
        _catat_gagal("tanda tangan salah")
        raise AuthenticationError("Kunci respons tidak cocok.")

    with session_scope() as session:
        terpakai = json.loads(_baca_setelan(session, KUNCI_NONCE_TERPAKAI) or "[]")
        if tantangan.nonce_hex in terpakai:
            raise ValidationError("Kunci ini sudah pernah dipakai. Buat kode baru.")

        user = session.scalar(
            sa.select(User).where(User.username == tantangan.username)
        )
        if user is None or user.role is not UserRole.ADMIN:
            raise ValidationError("Akun admin tidak ditemukan.")

        user.password_hash = hash_password(password_baru)  # memeriksa kekuatan
        user.must_change_password = True
        user.status = RecordStatus.ACTIVE

        terpakai.append(tantangan.nonce_hex)
        _tulis_setelan(
            session, KUNCI_NONCE_TERPAKAI, json.dumps(terpakai[-_NONCE_DIINGAT:])
        )
        audit_service.record(
            session,
            AKSI_RESET,
            user_id=user.id,
            entity_type="app_user",
            entity_id=user.id,
            username=user.username,
            nonce=tantangan.nonce_hex[:8],
        )
        logger.warning("Kata sandi admin %r dipulihkan dengan kunci pengembang", user.username)
        return user.username
