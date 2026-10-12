"""
Enkripsi berkas backup.

Sejak ada lembar pengaduan, backup berisi nama, telepon, dan alamat
pelapor. Folder backup biasanya ikut disalin ke flashdisk atau disk lain
(lihat `backup.salinan_folder`) — tempat yang jauh lebih mudah hilang
daripada komputer server. Backup terenkripsi yang hilang hanyalah berkas
acak.

KUNCINYA berupa frasa sandi di berkas `kunci-backup.txt`, di folder
database bersebelahan dengan token API anjungan. Bukan di database: kunci
yang ikut ter-backup di dalam backup yang dikuncinya tidak melindungi apa
pun. Bukan diketik setiap kali: backup otomatis berjalan saat aplikasi
dibuka, tanpa ada orang yang mengetik. Akibatnya yang WAJIB diingat
administrator: frasa itu harus dicatat di tempat lain. Disk server rusak +
frasa tidak tercatat = seluruh backup tidak dapat dibuka siapa pun.

Format berkas (.enc), semuanya biner:

    MAGIC (8) | salt scrypt (16) | awalan nonce (8)
    lalu potongan berurutan: panjang (4, big-endian) | ciphertext AES-GCM

Isi dipotong per 1 MiB supaya dump ratusan MB tidak harus dimuat utuh ke
memori. Nonce tiap potongan = awalan + nomor urut, dan data tambahan
(AAD) memuat nomor urut serta tanda potongan terakhir — potongan yang
ditukar, dibuang, atau berkas yang terpotong di tengah ditolak, bukan
dipulihkan diam-diam sebagai database setengah jadi.
"""

from __future__ import annotations

import os
import secrets
import struct
from pathlib import Path

from app.core.errors import ValidationError

MAGIC = b"ANTRENC1"
AKHIRAN = ".enc"
NAMA_BERKAS_KUNCI = "kunci-backup.txt"
UKURAN_POTONGAN = 1024 * 1024
PANJANG_FRASA_MINIMAL = 16

#: Parameter scrypt. n=2**15 ±100 ms dan 32 MB memori per turunan kunci:
#: cukup mahal untuk menebak frasa, cukup murah untuk dua kali per backup.
_SCRYPT = {"n": 2**15, "r": 8, "p": 1}


def path_berkas_kunci(db_path: Path | None = None) -> Path:
    """Letak berkas kunci: folder database, seperti token API anjungan."""
    if db_path is None:
        from app.core.config import get_config

        db_path = get_config().db_path
    return Path(db_path).expanduser().resolve().parent / NAMA_BERKAS_KUNCI


def frasa_baru() -> str:
    """
    Frasa acak yang masih dapat disalin tangan ke kertas.

    Enam kelompok berisi lima huruf/angka, tanpa huruf yang mudah tertukar
    (0/O, 1/l/I). 30 karakter dari 31 simbol ≈ 148 bit.
    """
    abjad = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    karakter = "".join(secrets.choice(abjad) for _ in range(30))
    return "-".join(karakter[i : i + 5] for i in range(0, 30, 5))


def normalkan_frasa(frasa: str) -> str:
    """Spasi dan huruf kecil dari salinan tangan tidak boleh membuat frasa beda."""
    return "".join(frasa.split()).upper()


def muat_frasa(db_path: Path | None = None) -> str | None:
    """Frasa tersimpan, atau None bila enkripsi belum diaktifkan."""
    try:
        isi = path_berkas_kunci(db_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    frasa = normalkan_frasa(isi)
    return frasa or None


def simpan_frasa(frasa: str, db_path: Path | None = None) -> None:
    """Tulis frasa lewat berkas sementara lalu diganti, seperti token API."""
    frasa = normalkan_frasa(frasa)
    if len(frasa.replace("-", "")) < PANJANG_FRASA_MINIMAL:
        raise ValidationError(
            f"Kunci enkripsi minimal {PANJANG_FRASA_MINIMAL} huruf atau angka."
        )
    path = path_berkas_kunci(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sementara = path.with_suffix(path.suffix + ".tmp")
    sementara.write_text(frasa + "\n", encoding="utf-8")
    sementara.replace(path)


def _kunci(frasa: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=salt, length=32, **_SCRYPT).derive(
        normalkan_frasa(frasa).encode("utf-8")
    )


def _aad(urutan: int, terakhir: bool) -> bytes:
    return MAGIC + struct.pack(">I?", urutan, terakhir)


def terenkripsi(berkas: Path) -> bool:
    """Berkas ini berformat backup terenkripsi (dilihat dari isinya)."""
    try:
        with berkas.open("rb") as f:
            return f.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def enkripsi(sumber: Path, tujuan: Path, frasa: str) -> None:
    """Enkripsi `sumber` ke `tujuan`. `tujuan` yang setengah jadi dihapus."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    awalan = os.urandom(8)
    aes = AESGCM(_kunci(frasa, salt))
    try:
        with sumber.open("rb") as masuk, tujuan.open("wb") as keluar:
            keluar.write(MAGIC + salt + awalan)
            urutan = 0
            potongan = masuk.read(UKURAN_POTONGAN)
            while True:
                berikut = masuk.read(UKURAN_POTONGAN)
                terakhir = not berikut
                sandi = aes.encrypt(
                    awalan + struct.pack(">I", urutan), potongan, _aad(urutan, terakhir)
                )
                keluar.write(struct.pack(">I", len(sandi)) + sandi)
                if terakhir:
                    break
                potongan = berikut
                urutan += 1
    except BaseException:
        tujuan.unlink(missing_ok=True)
        raise


_PESAN_KUNCI_SALAH = (
    "Backup ini tidak dapat dibuka dengan kunci enkripsi yang tersimpan di "
    "komputer ini. Masukkan kunci yang dipakai saat backup itu dibuat "
    "(menu Backup → Kunci Enkripsi), atau berkasnya rusak."
)


def dekripsi(sumber: Path, tujuan: Path, frasa: str | None) -> None:
    """
    Buka `sumber` ke `tujuan`. Kunci salah atau berkas rusak → ValidationError.

    `tujuan` yang setengah jadi dihapus: database separuh tidak boleh
    tertinggal di folder backup untuk dikira salinan yang sah.
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not frasa:
        raise ValidationError(
            "Backup ini terenkripsi, tetapi komputer ini belum menyimpan kunci "
            "enkripsinya. Masukkan kuncinya lewat menu Backup → Kunci Enkripsi."
        )
    try:
        with sumber.open("rb") as masuk, tujuan.open("wb") as keluar:
            kepala = masuk.read(len(MAGIC) + 24)
            if len(kepala) != len(MAGIC) + 24 or not kepala.startswith(MAGIC):
                raise ValidationError("Berkas ini bukan backup terenkripsi yang sah.")
            salt = kepala[len(MAGIC) : len(MAGIC) + 16]
            awalan = kepala[len(MAGIC) + 16 :]
            aes = AESGCM(_kunci(frasa, salt))
            urutan = 0
            panjang_teks = masuk.read(4)
            while True:
                if len(panjang_teks) != 4:
                    # Habis sebelum potongan bertanda terakhir: berkas terpotong.
                    raise ValidationError(_PESAN_KUNCI_SALAH)
                (panjang,) = struct.unpack(">I", panjang_teks)
                sandi = masuk.read(panjang)
                panjang_teks = masuk.read(4)
                terakhir = not panjang_teks
                try:
                    keluar.write(
                        aes.decrypt(
                            awalan + struct.pack(">I", urutan),
                            sandi,
                            _aad(urutan, terakhir),
                        )
                    )
                except InvalidTag:
                    raise ValidationError(_PESAN_KUNCI_SALAH) from None
                if terakhir:
                    break
                urutan += 1
    except BaseException:
        tujuan.unlink(missing_ok=True)
        raise


def cocok(berkas: Path, frasa: str | None) -> bool:
    """Frasa ini membuka potongan pertama `berkas` — tanpa membuka seluruhnya."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not frasa:
        return False
    try:
        with berkas.open("rb") as f:
            kepala = f.read(len(MAGIC) + 24)
            if not kepala.startswith(MAGIC):
                return False
            salt = kepala[len(MAGIC) : len(MAGIC) + 16]
            awalan = kepala[len(MAGIC) + 16 :]
            (panjang,) = struct.unpack(">I", f.read(4))
            sandi = f.read(panjang)
            terakhir = not f.read(1)
        AESGCM(_kunci(frasa, salt)).decrypt(
            awalan + struct.pack(">I", 0), sandi, _aad(0, terakhir)
        )
        return True
    except (OSError, struct.error, InvalidTag):
        return False
