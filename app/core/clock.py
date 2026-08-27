"""
Sumber waktu tunggal aplikasi.

Seluruh timestamp transaksi WAJIB berasal dari modul ini, bukan dari
datetime.now() yang tersebar di mana-mana. Alasannya:

1. Zona waktu harus selalu Asia/Jakarta (WIB, UTC+7, tanpa DST), apa pun
   zona waktu yang diset pada komputer petugas.
2. Waktu transaksi tidak boleh bergantung pada input user.

Nilai yang dikembalikan berupa datetime NAIVE dalam WIB. SQLite tidak
menyimpan informasi zona waktu, dan aplikasi ini hanya beroperasi pada satu
zona, sehingga menyimpan WIB polos jauh lebih sederhana dan menghindari
konversi yang rawan salah. Selisih waktu (waiting time, service time) tetap
akurat karena semua nilai berada pada zona yang sama.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import TIMEZONE

_TZ = ZoneInfo(TIMEZONE)


def now() -> datetime:
    """Waktu saat ini dalam WIB, tanpa tzinfo."""
    return datetime.now(_TZ).replace(tzinfo=None)


def today() -> date:
    """Tanggal hari ini menurut WIB."""
    return now().date()


def tzinfo() -> ZoneInfo:
    """Objek timezone WIB, untuk keperluan format tampilan."""
    return _TZ
