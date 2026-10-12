"""
Parser clipboard profil wajib pajak dari ECMP.

Petugas menyalin di ECMP (Salin profil atau ikon salin ID WP), lalu menempel
di kartu Data Pelapor. Aplikasi ini tidak memanggil ECMP dan tidak membaca
MIME HTML/JSON: yang sampai ke sini sudah berupa text/plain.

Yang ditolak sama pentingnya dengan yang diterima. Nama orang, kalimat, atau
sampah HTML yang kebetulan ada di papan klip tidak boleh mengisi Nama —
satu tempelan salah berarti keluhan tersimpan atas nama orang lain.
Isi clipboard tidak pernah dicatat ke log: itu data pribadi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PENANDA_PROFIL = "ECMP-WP-1"

JENIS_PROFIL = "profile"
JENIS_ID_WP = "idWp"
JENIS_INVALID = "invalid"

_DIGIT_MINIMUM = 8
_ALNUM_MINIMUM = 8
_ALNUM_MAKSIMUM = 64

#: Huruf/angka, boleh strip di tengah; contoh ECMP: CN-10000001.
_POLA_ALNUM = re.compile(
    rf"^[A-Za-z0-9][A-Za-z0-9\-]{{{_ALNUM_MINIMUM - 1},{_ALNUM_MAKSIMUM - 1}}}$"
)

_LABEL = {
    "nama": "nama",
    "id wp": "id_wp",
    "telepon": "telepon",
    "email": "email",
}


@dataclass(frozen=True)
class HasilClipboardWp:
    """Hasil parse yang aman dibawa ke UI — tanpa teks clipboard mentah."""

    jenis: str
    nama: str = ""
    id_wp: str = ""
    telepon: str = ""
    email: str = ""


_KOSONG = HasilClipboardWp(JENIS_INVALID)


def parse_clipboard_wp(teks: str) -> HasilClipboardWp:
    """
    Ubah text/plain clipboard menjadi profil, ID WP, atau invalid.

    Urutannya disengaja: penanda protokol dicek dulu, baru seluruh teks
    sebagai identifier. Tanpa itu, blok yang gagal parse bisa jatuh ke
    cabang ID WP hanya karena salah satu barisnya kebetulan panjang.
    """
    if not teks:
        return _KOSONG

    rapi = _rapikan_teks(teks)
    if not rapi:
        return _KOSONG

    baris = rapi.splitlines()
    pertama = baris[0].strip()
    if pertama == PENANDA_PROFIL:
        return _parse_profil(baris[1:])

    id_wp = _parse_id_wp(rapi)
    if id_wp is not None:
        return HasilClipboardWp(JENIS_ID_WP, id_wp=id_wp)
    return _KOSONG


def _rapikan_teks(teks: str) -> str:
    """Buang BOM dan ruang di tepi; normalisasi baris ditangani splitlines."""
    return teks.replace("\ufeff", "").strip()


def _parse_profil(baris: list[str]) -> HasilClipboardWp:
    nilai = {"nama": "", "id_wp": "", "telepon": "", "email": ""}
    for item in baris:
        if not item.strip() or ":" not in item:
            continue
        label, isi = item.split(":", 1)
        kunci = _LABEL.get(label.strip().lower())
        if kunci is None:
            continue
        nilai[kunci] = isi.strip()

    nilai["id_wp"] = _rapikan_id_profil(nilai["id_wp"])
    # Nama, No. Pelanggan, dan Telepon wajib. Email boleh kosong — ECMP
    # sering tidak punya alamat email, tetapi tanpa telepon lembarnya
    # tidak dapat dihubungi kembali.
    if not (nilai["nama"] and nilai["id_wp"] and nilai["telepon"]):
        return _KOSONG
    return HasilClipboardWp(JENIS_PROFIL, **nilai)


def _rapikan_id_profil(nilai: str) -> str:
    """
    ID di dalam blok profil.

    Angka berkelompok (spasi/strip) disimpan sebagai digit mentah. Selain
    itu dibiarkan apa adanya: field kosong tetap kosong, dan identifier
    seperti CN-10000001 tidak boleh dipaksa jadi digit-only.
    """
    mentah = nilai.strip()
    if not mentah:
        return ""
    digit = _sebagai_digit(mentah)
    return digit if digit is not None else mentah


def _parse_id_wp(teks: str) -> str | None:
    """Seluruh clipboard sebagai identifier, atau None bila teks bebas."""
    digit = _sebagai_digit(teks)
    if digit is not None:
        return digit
    if re.search(r"\s", teks):
        # Spasi pada cabang ini berarti nama orang atau kalimat, bukan
        # grouping angka — grouping sudah ditangani _sebagai_digit.
        return None
    if _POLA_ALNUM.fullmatch(teks):
        return teks
    return None


def _sebagai_digit(teks: str) -> str | None:
    """Digit murni bila spasi dan strip disingkirkan dan sisanya angka ≥ 8."""
    digit = re.sub(r"[\s-]+", "", teks)
    if digit.isdigit() and len(digit) >= _DIGIT_MINIMUM:
        return digit
    return None
