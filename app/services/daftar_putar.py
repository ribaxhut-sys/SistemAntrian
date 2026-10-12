"""
Daftar putar media anjungan: berkas mana yang diputar dan urutannya.

Disimpan sebagai pengaturan `kiosk.daftar_putar` berisi larik JSON, urut
sesuai urutan putar. Berkas yang tidak disebut tetap tersimpan di folder,
hanya tidak diputar — iklan musiman dapat dinyalakan lagi tanpa diunggah
ulang.

Tiap butir larik berupa nama berkas saja, atau objek bila iklannya punya
aturan sendiri::

    {"nama": "promo.jpg", "mulai": "2026-11-01", "selesai": "2026-11-30",
     "detik": 20}

`mulai`/`selesai` membatasi tanggal tayang (keduanya ikut dihitung),
`detik` lama tampil gambar itu menggantikan pengaturan umum. Butir tanpa
aturan tetap ditulis sebagai nama saja, jadi nilai lama terbaca apa adanya.

Nilai kosong berarti daftar putar belum pernah diatur: semua berkas di
folder diputar menurut nama, seperti sebelum fitur ini ada. Larik kosong
("[]") berbeda artinya: semua berkas sengaja dimatikan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.core.errors import ValidationError

KUNCI = "kiosk.daftar_putar"

#: Batas lama tampil per gambar, sama dengan pengaturan umumnya.
DETIK_MIN = 3
DETIK_MAKS = 60


@dataclass(frozen=True)
class Butir:
    """Satu berkas di daftar putar beserta aturannya sendiri."""

    nama: str
    mulai: date | None = None
    selesai: date | None = None
    #: Lama tampil gambar ini; None = ikut pengaturan umum.
    detik: int | None = None

    @property
    def berjadwal(self) -> bool:
        return self.mulai is not None or self.selesai is not None

    def tayang_pada(self, hari: date) -> bool:
        if self.mulai is not None and hari < self.mulai:
            return False
        return not (self.selesai is not None and hari > self.selesai)

    def ke_json(self) -> str | dict:
        if not self.berjadwal and self.detik is None:
            return self.nama
        isi: dict = {"nama": self.nama}
        if self.mulai is not None:
            isi["mulai"] = self.mulai.isoformat()
        if self.selesai is not None:
            isi["selesai"] = self.selesai.isoformat()
        if self.detik is not None:
            isi["detik"] = self.detik
        return isi


def _tanggal(nilai, ketat: bool) -> date | None:
    if nilai in (None, ""):
        return None
    try:
        return date.fromisoformat(str(nilai))
    except ValueError:
        if ketat:
            raise ValidationError(f"Tanggal daftar putar tidak sah: {nilai!r}.") from None
        return None


def _detik(nilai, ketat: bool) -> int | None:
    if nilai in (None, ""):
        return None
    try:
        angka = int(nilai)
    except (TypeError, ValueError):
        if ketat:
            raise ValidationError(f"Lama tampil tidak sah: {nilai!r}.") from None
        return None
    if not DETIK_MIN <= angka <= DETIK_MAKS:
        if ketat:
            raise ValidationError(
                f"Lama tampil gambar harus {DETIK_MIN}–{DETIK_MAKS} detik."
            )
        return None
    return angka


def _butir(isi, ketat: bool) -> Butir | None:
    """Satu elemen larik JSON menjadi Butir; None bila tidak terbaca."""
    if isinstance(isi, str):
        nama = isi.strip()
        return Butir(nama) if nama else None
    if not isinstance(isi, dict) or not isinstance(isi.get("nama"), str):
        if ketat:
            raise ValidationError("Daftar putar media harus berupa daftar nama berkas.")
        return None
    nama = isi["nama"].strip()
    if not nama:
        return None
    mulai = _tanggal(isi.get("mulai"), ketat)
    selesai = _tanggal(isi.get("selesai"), ketat)
    if mulai is not None and selesai is not None and selesai < mulai:
        if ketat:
            raise ValidationError(
                f"Tanggal selesai {nama} lebih awal dari tanggal mulainya."
            )
        selesai = None
    return Butir(nama, mulai, selesai, _detik(isi.get("detik"), ketat))


def baca_butir(nilai: str) -> list[Butir] | None:
    """Butir daftar putar, berurutan; None bila belum diatur."""
    nilai = (nilai or "").strip()
    if not nilai:
        return None
    try:
        isi = json.loads(nilai)
    except ValueError:
        return None
    if not isinstance(isi, list):
        return None
    hasil = []
    for elemen in isi:
        butir = _butir(elemen, ketat=False)
        if butir is not None:
            hasil.append(butir)
    return hasil


def baca(nilai: str) -> list[str] | None:
    """Nama berkas yang diputar, berurutan; None bila belum diatur."""
    daftar = baca_butir(nilai)
    return None if daftar is None else [butir.nama for butir in daftar]


def tulis(daftar: list[str] | list[Butir]) -> str:
    return json.dumps(
        [b.ke_json() if isinstance(b, Butir) else b for b in daftar],
        ensure_ascii=False,
    )


def baku(nilai: str) -> str:
    """Bentuk baku untuk disimpan; menolak isi yang bukan daftar nama berkas."""
    nilai = (nilai or "").strip()
    if not nilai:
        return ""
    try:
        isi = json.loads(nilai)
    except ValueError:
        raise ValidationError("Daftar putar media tidak terbaca.") from None
    if not isinstance(isi, list):
        raise ValidationError("Daftar putar media harus berupa daftar nama berkas.")
    hasil: list[Butir] = []
    for elemen in isi:
        if isinstance(elemen, str):
            nama = elemen.strip()
            butir = Butir(nama) if nama else None
        else:
            butir = _butir(elemen, ketat=True)
            nama = butir.nama if butir is not None else ""
        # Hanya nama berkas di folder media/kiosk, bukan path ke tempat lain.
        if butir is None or nama != Path(nama).name or nama in (".", ".."):
            raise ValidationError(f"Nama berkas daftar putar tidak sah: {nama!r}.")
        if all(b.nama != nama for b in hasil):
            hasil.append(butir)
    return tulis(hasil)


def terapkan(berkas: list[Path], nilai: str, hari: date | None = None) -> list[Path]:
    """
    Saring dan urutkan `berkas` (isi folder) menurut daftar putar.

    Nama di daftar yang berkasnya sudah tidak ada dilewati diam-diam. Bila
    `hari` diberikan, berkas di luar tanggal tayangnya ikut dilewati.
    """
    daftar = baca_butir(nilai)
    if daftar is None:
        return list(berkas)
    per_nama = {path.name: path for path in berkas}
    return [
        per_nama[butir.nama]
        for butir in daftar
        if butir.nama in per_nama and (hari is None or butir.tayang_pada(hari))
    ]


def detik_per_berkas(nilai: str) -> dict[str, int]:
    """Lama tampil khusus tiap gambar; yang ikut pengaturan umum tidak disebut."""
    return {
        butir.nama: butir.detik
        for butir in baca_butir(nilai) or []
        if butir.detik is not None
    }
