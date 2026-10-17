"""PIN pengaturan anjungan: hash, penundaan, API, dan pengaturan oleh admin."""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from app.core.errors import AuthorizationError, ValidationError
from app.services import pin_anjungan
from app.services.device_service import PerangkatService
from tests.conftest import TEST_PASSWORD
from tests.test_kiosk_api import TOKEN, VERSI_APK, _Services


def test_hash_berbumbu_dan_tidak_memuat_pin():
    a = pin_anjungan.buat("123456")
    b = pin_anjungan.buat("123456")

    assert a.salt != b.salt and a.hash != b.hash
    assert "123456" not in a.ke_json()
    assert pin_anjungan.cocok("123456", a)
    assert not pin_anjungan.cocok("654321", a)


@pytest.mark.parametrize("pin", ["", "12345", "1234567", "12345a", "abcdef", " 12345"])
def test_pin_harus_enam_angka(pin):
    with pytest.raises(ValidationError):
        pin_anjungan.buat(pin)
    assert not pin_anjungan.pin_sah(pin)


def test_hash_dapat_dihitung_ulang_android_dengan_pbkdf2_sha1():
    import hashlib

    data = pin_anjungan.buat("246810")
    langsung = hashlib.pbkdf2_hmac(
        "sha1", b"246810", bytes.fromhex(data.salt), data.iterations
    ).hex()
    assert langsung == data.hash


def test_penundaan_bertingkat_setelah_salah_berulang():
    batas = pin_anjungan.BatasPercobaan()
    for _ in range(4):
        assert batas.catat_gagal("t1", sekarang=0.0) == 0
    assert batas.catat_gagal("t1", sekarang=0.0) == 60
    assert batas.sisa_tunda("t1", sekarang=10.0) == 51
    assert batas.sisa_tunda("t1", sekarang=61.0) == 0
    for _ in range(4):
        batas.catat_gagal("t1", sekarang=100.0)
    assert batas.catat_gagal("t1", sekarang=100.0) == 300
    assert batas.sisa_tunda("tablet-lain", sekarang=100.0) == 0
    batas.catat_berhasil("t1")
    assert batas.sisa_tunda("t1", sekarang=100.0) == 0


def test_admin_mengatur_dan_menghapus_pin(auth):
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    layanan = PerangkatService(auth)
    assert layanan.pin_diatur() is False

    layanan.atur_pin("135790")

    assert layanan.pin_diatur() is True
    assert pin_anjungan.cocok("135790", pin_anjungan.baca())
    layanan.hapus_pin()
    assert layanan.pin_diatur() is False


def test_petugas_biasa_tidak_boleh_mengatur_pin(auth):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        PerangkatService(auth).atur_pin("135790")


def _klien(monkeypatch, data):
    from app.kiosk_api import create_app

    monkeypatch.setattr(pin_anjungan, "baca", lambda: data)
    return TestClient(create_app(TOKEN, _Services()))


def _verifikasi(klien, pin):
    return klien.post(
        "/v1/kiosk/pin/verifikasi",
        headers={"Authorization": f"Bearer {TOKEN}", **VERSI_APK},
        json={"pin": pin},
    ).json()


def test_api_verifikasi_pin_benar_dan_salah(monkeypatch):
    klien = _klien(monkeypatch, pin_anjungan.buat("112233"))

    assert _verifikasi(klien, "112233") == {"ok": True, "locked_seconds": 0}
    assert _verifikasi(klien, "000000") == {"ok": False, "locked_seconds": 0}


def test_api_menunda_tablet_setelah_lima_salah_dan_tidak_menebak_lagi(monkeypatch):
    klien = _klien(monkeypatch, pin_anjungan.buat("112233"))
    for _ in range(4):
        _verifikasi(klien, "000000")

    kelima = _verifikasi(klien, "000000")
    assert kelima["ok"] is False and kelima["locked_seconds"] == 60
    # Selama ditunda, PIN yang BENAR pun tidak diperiksa.
    benar = _verifikasi(klien, "112233")
    assert benar["ok"] is False and benar["locked_seconds"] > 0


def test_api_penundaan_tidak_lolos_dengan_mengganti_device_id(monkeypatch):
    """X-Device-Id token bersama diisi pengirim; penundaan mengikuti IP-nya."""
    klien = _klien(monkeypatch, pin_anjungan.buat("112233"))

    def tebak(pin, perangkat):
        return klien.post(
            "/v1/kiosk/pin/verifikasi",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "X-Device-Id": perangkat,
                **VERSI_APK,
            },
            json={"pin": pin},
        ).json()

    for i in range(5):
        tebak("000000", f"tablet-palsu-{i:04d}")

    benar = tebak("112233", "tablet-palsu-baru")
    assert benar["ok"] is False and benar["locked_seconds"] > 0


def test_api_tanpa_pin_tersimpan_pengaturan_terbuka(monkeypatch):
    klien = _klien(monkeypatch, None)

    assert _verifikasi(klien, "123456")["ok"] is True


TOKEN_TABLET = "token-tablet-terpasang-panjang"


class _PerangkatPalsu:
    """Satu tablet terpasang; cukup untuk require_token dan /display."""

    def perangkat_dari_token(self, token):
        from types import SimpleNamespace

        if token != TOKEN_TABLET:
            return None
        return SimpleNamespace(device_id="tablet-lobi-01", dicabut=False, jenis="anjungan")

    def token_bersama_aktif(self):
        return True

    def keadaan_perangkat(self, device_id):
        return False, False

    def catat_kontak(self, *args, **kwargs):
        pass

    def anjungan_bersuara(self):
        return ""

    def permintaan_segarkan_media(self, device_id):
        return 0


def _klien_terpasang(monkeypatch, data):
    from app.kiosk_api import create_app

    monkeypatch.setattr(pin_anjungan, "baca", lambda: data)
    layanan = _Services()
    layanan.perangkat = _PerangkatPalsu()
    return TestClient(create_app(TOKEN, layanan))


def test_display_mengirim_hash_bukan_pin_ke_tablet_terpasang(monkeypatch):
    data = pin_anjungan.buat("112233")
    klien = _klien_terpasang(monkeypatch, data)

    isi = klien.get(
        "/v1/kiosk/display", headers={"Authorization": f"Bearer {TOKEN_TABLET}"}
    ).json()

    assert isi["settings_pin"] == {
        "enabled": True,
        "salt": data.salt,
        "hash": data.hash,
        "iterations": data.iterations,
    }
    assert "112233" not in str(isi)


def test_display_tidak_mengirim_hash_pin_ke_token_bersama(monkeypatch):
    """Hash PIN 6 angka dapat ditebak habis; pemegang token bersama tidak mendapatnya."""
    klien = _klien_terpasang(monkeypatch, pin_anjungan.buat("112233"))

    isi = klien.get(
        "/v1/kiosk/display",
        headers={"Authorization": f"Bearer {TOKEN}", "X-Device-Id": "tablet-lobi-01"},
    ).json()

    assert "settings_pin" not in isi


def test_display_tanpa_pin_menyatakan_tidak_aktif(monkeypatch):
    klien = _klien_terpasang(monkeypatch, None)

    isi = klien.get(
        "/v1/kiosk/display", headers={"Authorization": f"Bearer {TOKEN_TABLET}"}
    ).json()

    assert isi["settings_pin"] == {"enabled": False}

