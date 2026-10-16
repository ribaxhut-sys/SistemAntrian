"""
PIN pengaturan anjungan: satu PIN di server untuk semua tablet.

Menjaga tombol ⚙ di anjungan Android. Server hanya menyimpan HASH berbumbu
(PBKDF2-HMAC-SHA1, sama dengan yang dapat dihitung Android sejak API 24),
tidak pernah PIN aslinya. Tablet memverifikasi ke server (`POST
/v1/kiosk/pin/verifikasi`, dengan batas percobaan); hash terakhir juga dikirim
pada `/v1/kiosk/display` supaya tablet yang terputus masih dapat memeriksa PIN
secara lokal untuk jalan pulih. Tujuannya melawan sentuhan iseng pengunjung,
bukan penyerang yang membongkar tablet.

Disimpan sebagai pengaturan `kiosk.pin_pengaturan` berisi objek JSON
`{"salt", "hash", "iterations"}`. Kunci ini sengaja tidak ada di SKEMA
pengaturan, jadi tidak tampil di layar Pengaturan mana pun.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass

import sqlalchemy as sa

from app.core.database import session_scope
from app.core.errors import ValidationError
from app.models import ApplicationSetting

KUNCI = "kiosk.pin_pengaturan"
ITERASI = 100_000
PANJANG_PIN = 6
_POLA_PIN = re.compile(rf"^\d{{{PANJANG_PIN}}}$")


@dataclass(frozen=True)
class DataPin:
    salt: str
    hash: str
    iterations: int

    def ke_json(self) -> str:
        return json.dumps(
            {"salt": self.salt, "hash": self.hash, "iterations": self.iterations}
        )


def pin_sah(pin: str) -> bool:
    return bool(_POLA_PIN.match(pin or ""))


def hitung_hash(pin: str, salt_hex: str, iterasi: int = ITERASI) -> str:
    return hashlib.pbkdf2_hmac(
        "sha1", pin.encode("utf-8"), bytes.fromhex(salt_hex), iterasi
    ).hex()


def buat(pin: str) -> DataPin:
    """Hash baru berbumbu acak untuk `pin`; menolak yang bukan 6 angka."""
    if not pin_sah(pin):
        raise ValidationError(f"PIN harus {PANJANG_PIN} angka.")
    salt = secrets.token_hex(16)
    return DataPin(salt, hitung_hash(pin, salt), ITERASI)


def cocok(pin: str, data: DataPin) -> bool:
    if not pin_sah(pin):
        return False
    return hmac.compare_digest(
        hitung_hash(pin, data.salt, data.iterations), data.hash
    )


def baca() -> DataPin | None:
    """PIN yang tersimpan, atau None bila belum diatur / rusak."""
    with session_scope() as session:
        nilai = session.scalar(
            sa.select(ApplicationSetting.value).where(ApplicationSetting.key == KUNCI)
        )
    if not nilai:
        return None
    try:
        isi = json.loads(nilai)
        return DataPin(str(isi["salt"]), str(isi["hash"]), int(isi["iterations"]))
    except (ValueError, KeyError, TypeError):
        return None


def simpan(data: DataPin | None) -> None:
    """Simpan (atau hapus bila None). Pemanggil yang menegakkan hak admin."""
    with session_scope() as session:
        baris = session.scalar(
            sa.select(ApplicationSetting).where(ApplicationSetting.key == KUNCI)
        )
        nilai = data.ke_json() if data is not None else ""
        if baris is None:
            session.add(ApplicationSetting(key=KUNCI, value=nilai))
        else:
            baris.value = nilai


# ---------------------------------------------------------------------
# Batas percobaan per tablet (di memori server)
# ---------------------------------------------------------------------

#: (jumlah gagal beruntun, detik penundaan), dari yang terberat.
PENUNDAAN = ((15, 900), (10, 300), (5, 60))


class BatasPercobaan:
    """Penundaan bertingkat per tablet setelah PIN salah berulang."""

    def __init__(self) -> None:
        self._gagal: dict[str, int] = {}
        self._sampai: dict[str, float] = {}

    def sisa_tunda(self, perangkat: str, sekarang: float | None = None) -> int:
        sekarang = time.monotonic() if sekarang is None else sekarang
        sisa = self._sampai.get(perangkat, 0.0) - sekarang
        return int(sisa) + 1 if sisa > 0 else 0

    def catat_gagal(self, perangkat: str, sekarang: float | None = None) -> int:
        """Catat satu PIN salah; hasilnya detik penundaan yang berlaku (0 = tidak ada)."""
        sekarang = time.monotonic() if sekarang is None else sekarang
        jumlah = self._gagal.get(perangkat, 0) + 1
        self._gagal[perangkat] = jumlah
        for ambang, detik in PENUNDAAN:
            if jumlah >= ambang:
                self._sampai[perangkat] = sekarang + detik
                return detik
        return 0

    def catat_berhasil(self, perangkat: str) -> None:
        self._gagal.pop(perangkat, None)
        self._sampai.pop(perangkat, None)
