"""
Enkripsi salinan backup yang dibawa keluar server (folder kedua/flashdisk).

Keputusan pemilik (Oktober 2026): backup di server tetap biasa supaya
pemulihan cepat; yang dienkripsi hanya salinan kedua, karena salinan itulah
yang ikut berpindah tangan dan dapat hilang.

Kata sandi TIDAK disimpan di mana pun. Dari kata sandi admin diturunkan
pasangan kunci X25519 (scrypt); yang disimpan hanya kunci PUBLIK dan
garamnya. Backup otomatis tiap pagi cukup memegang kunci publik untuk
mengenkripsi, sedangkan membuka salinan membutuhkan kata sandi itu lagi.
Orang yang mencuri flashdisk, atau membaca database, tidak dapat membukanya.
Kata sandi yang hilang berarti salinan terenkripsi tidak dapat dibuka lagi —
backup di server tidak terpengaruh.

Format berkas `.antrianenc`:
    MAGIC | panjang kepala (4) | kepala JSON | potongan...
Tiap potongan: panjang (4) | AES-256-GCM(isi ≤ 1 MiB). Nonce = awalan acak
8 byte + nomor potongan; AAD = SHA-256 kepala + nomor + tanda akhir,
sehingga potongan tidak dapat ditukar, dipotong, atau disambung.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import struct
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa

from app.core.database import session_scope
from app.core.errors import ValidationError
from app.models import ApplicationSetting

MAGIC = b"ANTRENC1"
AKHIRAN = ".antrianenc"
UKURAN_POTONGAN = 1024 * 1024
#: Batas kepala dan potongan saat membaca: berkas rusak tidak boleh membuat
#: aplikasi memesan memori sebesar angka acak.
_BATAS_KEPALA = 16 * 1024
_TAMBAHAN_GCM = 16

#: Kunci pengaturan; bukan bagian SKEMA Pengaturan karena diatur dari layar
#: Backup, dan nilainya bukan teks yang pantas diubah tangan.
KUNCI = "backup.salinan_kunci_enkripsi"

MIN_PANJANG_SANDI = 12
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_INFO_HKDF = b"antrian-backup-salinan-v1"


@dataclass(frozen=True)
class KunciSalinan:
    publik: bytes
    garam: bytes
    n: int

    def ke_json(self) -> str:
        return json.dumps(
            {
                "publik": base64.b64encode(self.publik).decode("ascii"),
                "garam": base64.b64encode(self.garam).decode("ascii"),
                "n": self.n,
            }
        )


def _turunkan_rahasia(sandi: str, garam: bytes, n: int):
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    bahan = hashlib.scrypt(
        sandi.encode("utf-8"),
        salt=garam,
        n=n,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
        maxmem=128 * 1024 * 1024,
    )
    return X25519PrivateKey.from_private_bytes(bahan)


def _publik_mentah(kunci) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return kunci.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def buat_kunci(sandi: str) -> KunciSalinan:
    """Kunci publik baru dari kata sandi; menolak sandi yang terlalu pendek."""
    if len(sandi or "") < MIN_PANJANG_SANDI:
        raise ValidationError(
            f"Kata sandi salinan backup minimal {MIN_PANJANG_SANDI} karakter."
        )
    garam = secrets.token_bytes(16)
    rahasia = _turunkan_rahasia(sandi, garam, _SCRYPT_N)
    return KunciSalinan(_publik_mentah(rahasia.public_key()), garam, _SCRYPT_N)


def baca() -> KunciSalinan | None:
    with session_scope() as session:
        nilai = session.scalar(
            sa.select(ApplicationSetting.value).where(ApplicationSetting.key == KUNCI)
        )
    if not nilai:
        return None
    try:
        isi = json.loads(nilai)
        return KunciSalinan(
            base64.b64decode(isi["publik"]), base64.b64decode(isi["garam"]), int(isi["n"])
        )
    except (ValueError, KeyError, TypeError):
        return None


def simpan(kunci: KunciSalinan | None) -> None:
    """Simpan (atau hapus bila None). Pemanggil yang menegakkan hak admin."""
    with session_scope() as session:
        baris = session.scalar(
            sa.select(ApplicationSetting).where(ApplicationSetting.key == KUNCI)
        )
        nilai = kunci.ke_json() if kunci is not None else ""
        if baris is None:
            session.add(ApplicationSetting(key=KUNCI, value=nilai))
        else:
            baris.value = nilai


def _kunci_simetris(rahasia_bersama: bytes, publik_sementara: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=publik_sementara, info=_INFO_HKDF
    ).derive(rahasia_bersama)


def _aad(sidik_kepala: bytes, nomor: int, akhir: bool) -> bytes:
    return sidik_kepala + struct.pack(">I?", nomor, akhir)


def enkripsi(sumber: Path, tujuan: Path, kunci: KunciSalinan) -> None:
    """Tulis `sumber` terenkripsi ke `tujuan` (lewat berkas sementara)."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    sementara_kunci = X25519PrivateKey.generate()
    publik_sementara = _publik_mentah(sementara_kunci.public_key())
    aes = AESGCM(
        _kunci_simetris(
            sementara_kunci.exchange(X25519PublicKey.from_public_bytes(kunci.publik)),
            publik_sementara,
        )
    )
    ringkasan = hashlib.sha256()
    with sumber.open("rb") as isi:
        for blok in iter(lambda: isi.read(UKURAN_POTONGAN), b""):
            ringkasan.update(blok)
    awalan_nonce = secrets.token_bytes(8)
    kepala = json.dumps(
        {
            "v": 1,
            "nama": sumber.name,
            "ukuran": sumber.stat().st_size,
            "sha256": ringkasan.hexdigest(),
            "garam": base64.b64encode(kunci.garam).decode("ascii"),
            "n": kunci.n,
            "sementara": base64.b64encode(publik_sementara).decode("ascii"),
            "nonce": base64.b64encode(awalan_nonce).decode("ascii"),
        }
    ).encode("utf-8")
    sidik = hashlib.sha256(kepala).digest()

    sementara = tujuan.with_name(tujuan.name + ".tmp")
    try:
        with sumber.open("rb") as isi, sementara.open("wb") as keluar:
            keluar.write(MAGIC + struct.pack(">I", len(kepala)) + kepala)
            nomor = 0
            blok = isi.read(UKURAN_POTONGAN)
            while True:
                berikut = isi.read(UKURAN_POTONGAN)
                akhir = not berikut
                sandi_blok = aes.encrypt(
                    awalan_nonce + struct.pack(">I", nomor), blok, _aad(sidik, nomor, akhir)
                )
                keluar.write(struct.pack(">I", len(sandi_blok)) + sandi_blok)
                if akhir:
                    break
                blok = berikut
                nomor += 1
            keluar.flush()
            os.fsync(keluar.fileno())
        sementara.replace(tujuan)
    except BaseException:
        sementara.unlink(missing_ok=True)
        raise


def nama_asli(berkas: Path) -> str:
    """Nama backup di dalam berkas terenkripsi (tanpa membuka isinya)."""
    return _baca_kepala(berkas)[0]["nama"]


def _baca_kepala(berkas: Path) -> tuple[dict, int]:
    with berkas.open("rb") as isi:
        if isi.read(len(MAGIC)) != MAGIC:
            raise ValidationError("Berkas ini bukan salinan backup terenkripsi.")
        (panjang,) = struct.unpack(">I", isi.read(4))
        if not 0 < panjang <= _BATAS_KEPALA:
            raise ValidationError("Kepala salinan backup rusak.")
        mentah = isi.read(panjang)
    try:
        kepala = json.loads(mentah)
        nama = Path(str(kepala["nama"])).name
        if not nama or nama != kepala["nama"]:
            raise ValueError("nama")
    except (ValueError, KeyError, TypeError) as exc:
        raise ValidationError("Kepala salinan backup rusak.") from exc
    return kepala, len(MAGIC) + 4 + panjang


def dekripsi(sumber: Path, tujuan: Path, sandi: str) -> str:
    """
    Buka salinan terenkripsi ke `tujuan`; kembalikan SHA-256 isinya.

    Sandi salah dan berkas rusak sama-sama ditolak tanpa meninggalkan
    berkas separuh jadi.
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    kepala, mulai = _baca_kepala(sumber)
    with sumber.open("rb") as isi:
        isi.seek(len(MAGIC) + 4)
        sidik = hashlib.sha256(isi.read(mulai - len(MAGIC) - 4)).digest()
    try:
        garam = base64.b64decode(kepala["garam"])
        n = int(kepala["n"])
        publik_sementara = base64.b64decode(kepala["sementara"])
        awalan_nonce = base64.b64decode(kepala["nonce"])
        if n not in (2**14, 2**15, 2**16, 2**17) or len(awalan_nonce) != 8:
            raise ValueError("parameter")
        rahasia = _turunkan_rahasia(sandi or "", garam, n)
        aes = AESGCM(
            _kunci_simetris(
                rahasia.exchange(X25519PublicKey.from_public_bytes(publik_sementara)),
                publik_sementara,
            )
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ValidationError("Kepala salinan backup rusak.") from exc

    ringkasan = hashlib.sha256()
    sementara = tujuan.with_name(tujuan.name + ".tmp")
    try:
        with sumber.open("rb") as isi, sementara.open("wb") as keluar:
            isi.seek(mulai)
            nomor = 0
            selesai = False
            while not selesai:
                kepala_blok = isi.read(4)
                if len(kepala_blok) < 4:
                    raise ValidationError("Salinan backup terpotong.")
                (panjang,) = struct.unpack(">I", kepala_blok)
                if panjang > UKURAN_POTONGAN + _TAMBAHAN_GCM:
                    raise ValidationError("Salinan backup rusak.")
                sandi_blok = isi.read(panjang)
                nonce = awalan_nonce + struct.pack(">I", nomor)
                for akhir in (False, True):
                    try:
                        blok = aes.decrypt(nonce, sandi_blok, _aad(sidik, nomor, akhir))
                    except InvalidTag:
                        continue
                    selesai = akhir
                    break
                else:
                    if nomor == 0:
                        raise ValidationError(
                            "Kata sandi salah, atau salinan backup rusak."
                        )
                    raise ValidationError("Salinan backup rusak.")
                ringkasan.update(blok)
                keluar.write(blok)
                nomor += 1
            if isi.read(1):
                raise ValidationError("Salinan backup memuat data tambahan yang tidak sah.")
        hasil = ringkasan.hexdigest()
        if hasil != kepala.get("sha256"):
            raise ValidationError("Isi salinan backup tidak cocok dengan sidiknya.")
        sementara.replace(tujuan)
        return hasil
    except BaseException:
        sementara.unlink(missing_ok=True)
        raise
