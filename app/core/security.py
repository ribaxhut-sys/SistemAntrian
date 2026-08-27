"""
Hashing kata sandi.

Memakai scrypt dari hashlib (pustaka standar Python), sehingga tidak ada
dependency tambahan. scrypt sengaja dibuat lambat dan boros memori supaya
percobaan menebak kata sandi secara massal menjadi mahal.

Format hash yang disimpan:

    scrypt$n$r$p$<salt base64>$<turunan base64>

Parameter ikut disimpan agar hash lama tetap dapat diverifikasi ketika
parameter dinaikkan di kemudian hari.

Kata sandi asli TIDAK PERNAH disimpan, dicatat ke log, atau dimasukkan ke
audit log.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from app.core.errors import ValidationError

_ALGORITHM = "scrypt"
_N = 2**14  # faktor biaya CPU/memori (~16 MB per verifikasi)
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16

MIN_PASSWORD_LENGTH = 6


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=_DKLEN
    )


def validate_password_strength(password: str) -> None:
    """
    Periksa syarat minimal kata sandi.

    Sengaja tidak berlebihan: aplikasi ini dipakai petugas loket pada
    komputer kantor tanpa akses jaringan, dan aturan yang terlalu rumit
    justru mendorong kata sandi ditempel di monitor.
    """
    if not password or not password.strip():
        raise ValidationError("Kata sandi tidak boleh kosong.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Kata sandi minimal {MIN_PASSWORD_LENGTH} karakter."
        )


def hash_password(password: str) -> str:
    """Ubah kata sandi menjadi hash yang aman disimpan."""
    validate_password_strength(password)
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = _derive(password, salt, _N, _R, _P)
    return f"{_ALGORITHM}${_N}${_R}${_P}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Cocokkan kata sandi dengan hash tersimpan.

    Selalu mengembalikan True/False, tidak pernah melempar exception karena
    format hash rusak. Hash yang tidak dikenali dianggap tidak cocok.
    Perbandingan memakai compare_digest agar lamanya proses tidak
    membocorkan seberapa banyak karakter yang benar.
    """
    if not password or not stored_hash:
        return False
    try:
        algorithm, n, r, p, salt_b64, expected_b64 = stored_hash.split("$")
        if algorithm != _ALGORITHM:
            return False
        derived = _derive(password, _unb64(salt_b64), int(n), int(r), int(p))
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(derived, _unb64(expected_b64))


def needs_rehash(stored_hash: str) -> bool:
    """
    True bila hash dibuat dengan parameter lama.

    Dipakai untuk memperkuat hash secara diam-diam saat user berhasil login.
    """
    try:
        algorithm, n, r, p, _, _ = stored_hash.split("$")
    except ValueError:
        return True
    return (algorithm, int(n), int(r), int(p)) != (_ALGORITHM, _N, _R, _P)
