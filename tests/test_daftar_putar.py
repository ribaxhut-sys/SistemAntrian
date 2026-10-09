"""
Daftar putar media anjungan.

Yang dikunci: nilai kosong tetap berarti "putar semua menurut nama" seperti
sebelum fitur ini ada, larik kosong berarti tidak ada media, dan nama
berkas tidak dapat dipakai untuk menunjuk ke luar folder media/kiosk.
"""

from __future__ import annotations

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
