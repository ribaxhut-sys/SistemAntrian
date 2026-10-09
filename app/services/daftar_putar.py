"""
Daftar putar media anjungan: berkas mana yang diputar dan urutannya.

Disimpan sebagai pengaturan `kiosk.daftar_putar` berisi larik JSON nama
berkas di folder media/kiosk, urut sesuai urutan putar. Berkas yang tidak
disebut tetap tersimpan di folder, hanya tidak diputar — iklan musiman
dapat dinyalakan lagi tanpa diunggah ulang.

Nilai kosong berarti daftar putar belum pernah diatur: semua berkas di
folder diputar menurut nama, seperti sebelum fitur ini ada. Larik kosong
("[]") berbeda artinya: semua berkas sengaja dimatikan.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import ValidationError

KUNCI = "kiosk.daftar_putar"


def baca(nilai: str) -> list[str] | None:
    """Nama berkas yang diputar, berurutan; None bila belum diatur."""
    nilai = (nilai or "").strip()
    if not nilai:
        return None
    try:
        isi = json.loads(nilai)
    except ValueError:
        return None
    if not isinstance(isi, list):
        return None
    return [nama for nama in isi if isinstance(nama, str) and nama.strip()]


def tulis(nama: list[str]) -> str:
    return json.dumps(list(nama), ensure_ascii=False)


def baku(nilai: str) -> str:
    """Bentuk baku untuk disimpan; menolak isi yang bukan daftar nama berkas."""
    nilai = (nilai or "").strip()
    if not nilai:
        return ""
    try:
        isi = json.loads(nilai)
    except ValueError:
        raise ValidationError("Daftar putar media tidak terbaca.") from None
    if not isinstance(isi, list) or not all(isinstance(n, str) for n in isi):
        raise ValidationError("Daftar putar media harus berupa daftar nama berkas.")
    hasil: list[str] = []
    for nama in isi:
        nama = nama.strip()
        # Hanya nama berkas di folder media/kiosk, bukan path ke tempat lain.
        if not nama or nama != Path(nama).name or nama in (".", ".."):
            raise ValidationError(f"Nama berkas daftar putar tidak sah: {nama!r}.")
        if nama not in hasil:
            hasil.append(nama)
    return tulis(hasil)


def terapkan(berkas: list[Path], nilai: str) -> list[Path]:
    """
    Saring dan urutkan `berkas` (isi folder) menurut daftar putar.

    Nama di daftar yang berkasnya sudah tidak ada dilewati diam-diam.
    """
    daftar = baca(nilai)
    if daftar is None:
        return list(berkas)
    per_nama = {path.name: path for path in berkas}
    return [per_nama[nama] for nama in daftar if nama in per_nama]
