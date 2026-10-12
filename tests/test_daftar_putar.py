"""
Daftar putar media anjungan.

Yang dikunci: nilai kosong tetap berarti "putar semua menurut nama" seperti
sebelum fitur ini ada, larik kosong berarti tidak ada media, dan nama
berkas tidak dapat dipakai untuk menunjuk ke luar folder media/kiosk.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.core.errors import ValidationError
from app.services import daftar_putar
from app.services.settings_service import SettingsService


def _berkas(*nama: str) -> list[Path]:
    return [Path("media") / "kiosk" / n for n in nama]


def test_nilai_kosong_memutar_semua_berkas_menurut_urutan_folder():
    berkas = _berkas("a.jpg", "b.mp4")

    assert daftar_putar.terapkan(berkas, "") == berkas


def test_daftar_putar_menyaring_dan_mengurutkan():
    berkas = _berkas("a.jpg", "b.mp4", "c.mp4")

    hasil = daftar_putar.terapkan(berkas, '["c.mp4", "a.jpg"]')

    assert [p.name for p in hasil] == ["c.mp4", "a.jpg"]


def test_berkas_yang_sudah_dihapus_dilewati():
    hasil = daftar_putar.terapkan(_berkas("a.jpg"), '["hilang.mp4", "a.jpg"]')

    assert [p.name for p in hasil] == ["a.jpg"]


def test_larik_kosong_berarti_tidak_ada_media():
    assert daftar_putar.terapkan(_berkas("a.jpg"), "[]") == []


@pytest.mark.parametrize("nilai", ['["../rahasia.mp4"]', '["sub/a.jpg"]', '{"a": 1}', "bukan json"])
def test_nilai_rusak_ditolak(nilai):
    with pytest.raises(ValidationError):
        daftar_putar.baku(nilai)


def test_nilai_dibakukan_tanpa_duplikat():
    assert daftar_putar.baku('[" a.jpg ", "a.jpg", "b.mp4"]') == '["a.jpg", "b.mp4"]'


def test_pengaturan_menyimpan_daftar_putar_yang_dibakukan(admin_auth):
    settings = SettingsService(admin_auth)

    settings.set(daftar_putar.KUNCI, '["b.mp4", "b.mp4", "a.jpg"]')

    assert settings.get(daftar_putar.KUNCI) == '["b.mp4", "a.jpg"]'


# ---------------------------------------------------------------------------
# Jadwal tayang dan lama tampil per berkas
# ---------------------------------------------------------------------------


JADWAL = (
    '["a.jpg", {"nama": "promo.jpg", "mulai": "2026-11-01", '
    '"selesai": "2026-11-30", "detik": 20}]'
)


@pytest.mark.parametrize(
    ("hari", "harapan"),
    [
        (date(2026, 10, 31), ["a.jpg"]),
        (date(2026, 11, 1), ["a.jpg", "promo.jpg"]),
        (date(2026, 11, 30), ["a.jpg", "promo.jpg"]),
        (date(2026, 12, 1), ["a.jpg"]),
    ],
)
def test_iklan_hanya_tayang_dalam_tanggalnya(hari, harapan):
    hasil = daftar_putar.terapkan(_berkas("a.jpg", "promo.jpg"), JADWAL, hari)

    assert [p.name for p in hasil] == harapan


def test_tanpa_tanggal_jadwal_tidak_menyaring():
    """Pemakai lama (tanpa hari) tetap mendapat seluruh daftar."""
    hasil = daftar_putar.terapkan(_berkas("a.jpg", "promo.jpg"), JADWAL)

    assert [p.name for p in hasil] == ["a.jpg", "promo.jpg"]


def test_lama_tampil_per_berkas():
    assert daftar_putar.detik_per_berkas(JADWAL) == {"promo.jpg": 20}
    assert daftar_putar.detik_per_berkas("") == {}


def test_butir_tanpa_aturan_tetap_ditulis_sebagai_nama():
    """Nilai lama dan nilai baru tanpa jadwal tidak berbeda bentuknya."""
    nilai = daftar_putar.tulis(
        [
            daftar_putar.Butir("a.jpg"),
            daftar_putar.Butir("b.jpg", mulai=date(2026, 11, 1), detik=15),
        ]
    )

    assert json.loads(nilai) == ["a.jpg", {"nama": "b.jpg", "mulai": "2026-11-01", "detik": 15}]
    assert daftar_putar.baca(nilai) == ["a.jpg", "b.jpg"]
    assert daftar_putar.baku(nilai) == nilai


@pytest.mark.parametrize(
    "nilai",
    [
        '[{"nama": "a.jpg", "mulai": "kemarin"}]',
        '[{"nama": "a.jpg", "mulai": "2026-11-30", "selesai": "2026-11-01"}]',
        '[{"nama": "a.jpg", "detik": 1}]',
        '[{"nama": "a.jpg", "detik": "lama"}]',
        '[{"nama": "../a.jpg"}]',
        '[{"berkas": "a.jpg"}]',
        "[3]",
    ],
)
def test_aturan_rusak_ditolak(nilai):
    with pytest.raises(ValidationError):
        daftar_putar.baku(nilai)


def test_aturan_rusak_yang_sudah_tersimpan_tidak_menjatuhkan_anjungan():
    """Nilai yang terlanjur rusak dibaca seadanya, bukan melempar galat."""
    butir = daftar_putar.baca_butir(
        '[{"nama": "a.jpg", "mulai": "kemarin", "detik": 999}, 7, "b.jpg"]'
    )

    assert butir == [daftar_putar.Butir("a.jpg"), daftar_putar.Butir("b.jpg")]
