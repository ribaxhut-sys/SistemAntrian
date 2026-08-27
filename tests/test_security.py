"""Test hashing kata sandi."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.core.security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    validate_password_strength,
    verify_password,
)


# ---------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------

def test_kata_sandi_tidak_tersimpan_apa_adanya():
    """Syarat paling dasar: kata sandi asli tidak boleh muncul di hash."""
    sandi = "rahasia123"
    hasil = hash_password(sandi)
    assert sandi not in hasil


def test_hash_memuat_algoritma_dan_parameter():
    """Parameter disimpan agar hash lama tetap bisa diverifikasi."""
    bagian = hash_password("rahasia123").split("$")
    assert len(bagian) == 6
    assert bagian[0] == "scrypt"
    assert int(bagian[1]) >= 16384  # faktor biaya


def test_dua_hash_dari_kata_sandi_sama_selalu_berbeda():
    """
    Salt acak. Tanpa ini, dua petugas berkata sandi sama akan punya hash
    identik dan itu langsung terlihat oleh siapa pun yang membuka database.
    """
    assert hash_password("rahasia123") != hash_password("rahasia123")


def test_kata_sandi_benar_diterima():
    hasil = hash_password("rahasia123")
    assert verify_password("rahasia123", hasil) is True


@pytest.mark.parametrize(
    "salah",
    ["rahasia124", "Rahasia123", "rahasia12", "rahasia1234", "", "   "],
)
def test_kata_sandi_salah_ditolak(salah):
    hasil = hash_password("rahasia123")
    assert verify_password(salah, hasil) is False


def test_hash_yang_diubah_ditolak():
    """Mengutak-atik kolom password_hash di database tidak membuka pintu."""
    hasil = hash_password("rahasia123")
    diubah = hasil[:-4] + "AAAA"
    assert verify_password("rahasia123", diubah) is False


@pytest.mark.parametrize(
    "rusak",
    ["", "bukan-hash", "scrypt$abc", "md5$1$1$1$aa$bb", "$$$$$", "scrypt$0$0$0$$"],
)
def test_hash_rusak_tidak_membuat_aplikasi_gagal(rusak):
    """Data rusak harus menghasilkan False, bukan traceback ke layar user."""
    assert verify_password("rahasia123", rusak) is False


def test_verifikasi_tanpa_kata_sandi_ditolak():
    hasil = hash_password("rahasia123")
    assert verify_password("", hasil) is False


# ---------------------------------------------------------------------
# Syarat kata sandi
# ---------------------------------------------------------------------

@pytest.mark.parametrize("buruk", ["", "   ", "abc", "12345"])
def test_kata_sandi_terlalu_pendek_ditolak(buruk):
    with pytest.raises(ValidationError):
        validate_password_strength(buruk)


def test_kata_sandi_sepanjang_batas_diterima():
    validate_password_strength("a" * MIN_PASSWORD_LENGTH)


def test_hash_menolak_kata_sandi_yang_tidak_memenuhi_syarat():
    with pytest.raises(ValidationError):
        hash_password("123")


# ---------------------------------------------------------------------
# Rehash
# ---------------------------------------------------------------------

def test_hash_baru_tidak_perlu_diperkuat():
    assert needs_rehash(hash_password("rahasia123")) is False


@pytest.mark.parametrize(
    "lama",
    ["scrypt$1024$8$1$aaaa$bbbb", "md5$16384$8$1$aaaa$bbbb", "bukan-hash"],
)
def test_hash_lama_atau_asing_ditandai_perlu_diperkuat(lama):
    assert needs_rehash(lama) is True
