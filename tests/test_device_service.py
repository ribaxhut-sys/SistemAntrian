"""Perangkat Android (anjungan dan layar antrian): pasang, kontak, cabut."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import clock
from app.core.errors import AuthorizationError, BusinessRuleError, ValidationError
from app.services import device_service
from app.services.device_service import PerangkatService

TOKEN = "token-bersama-panjang"
DEVICE = "a1b2c3d4-0000-4000-8000-000000000001"


@pytest.fixture
def layanan(admin_auth):
    return PerangkatService(admin_auth)


def test_kode_pasang_ditukar_token_sekali_pakai(layanan):
    kode = layanan.buat_kode()

    token = device_service.pasangkan(kode.kode, DEVICE, "Anjungan Lobi", "anjungan")

    assert len(token) >= 64
    pemilik = device_service.perangkat_dari_token(token)
    assert pemilik.nama == "Anjungan Lobi"
    assert pemilik.label_jenis == "Anjungan"
    assert pemilik.dipasangkan
    with pytest.raises(BusinessRuleError):
        device_service.pasangkan(kode.kode, "perangkat-lain-000", "X", "anjungan")


def test_kode_kedaluwarsa_ditolak(layanan, monkeypatch):
    kode = layanan.buat_kode()
    nanti = clock.now() + timedelta(minutes=11)
    monkeypatch.setattr(device_service.clock, "now", lambda: nanti)

    with pytest.raises(BusinessRuleError):
        device_service.pasangkan(kode.kode, DEVICE, "X", "anjungan")


def test_kode_bukan_enam_angka_ditolak(layanan):
    with pytest.raises(ValidationError):
        device_service.pasangkan("12", DEVICE, "X", "anjungan")


def test_jenis_hanya_anjungan_atau_layar_antrian(layanan):
    token = device_service.pasangkan(layanan.buat_kode().kode, DEVICE, "TV", "papan")
    assert device_service.perangkat_dari_token(token).jenis == "anjungan"

    lain = "a1b2c3d4-0000-4000-8000-000000000002"
    token = device_service.pasangkan(layanan.buat_kode().kode, lain, "TV", "layar_antrian")
    assert device_service.perangkat_dari_token(token).label_jenis == "Layar antrian"


def test_pasang_ulang_menghentikan_token_lama(layanan):
    lama = device_service.pasangkan(layanan.buat_kode().kode, DEVICE, "A", "anjungan")
    baru = device_service.pasangkan(layanan.buat_kode().kode, DEVICE, "A", "anjungan")

    assert device_service.perangkat_dari_token(lama) is None
    assert device_service.perangkat_dari_token(baru) is not None
    assert len(layanan.daftar()) == 1


def test_cabut_lalu_hapus(layanan):
    token = device_service.pasangkan(layanan.buat_kode().kode, DEVICE, "A", "anjungan")
    info = device_service.perangkat_dari_token(token)

    with pytest.raises(BusinessRuleError):
        layanan.hapus(info.id)
    dicabut = layanan.cabut(info.id)

    assert dicabut.dicabut
    assert device_service.perangkat_dari_token(token) is None
    assert device_service.perangkat_dicabut(DEVICE)
    layanan.hapus(info.id)
    assert layanan.daftar() == []


def test_kontak_dan_printer_tercatat(layanan):
    device_service.catat_kontak(
        DEVICE, nama="Tablet", alamat_ip="192.168.1.31", versi_nama="1.4", versi_kode=5
    )
    device_service.catat_printer(DEVICE, False, "Printer USB tidak ditemukan")

    (info,) = layanan.daftar()
    assert info.aktif()
    assert not info.dipasangkan, "token bersama: belum dipasangkan"
    assert info.alamat_ip == "192.168.1.31"
    assert info.versi_nama == "1.4"
    assert info.printer_ok is False
    assert "tidak ditemukan" in info.printer_pesan


def test_ganti_nama(layanan):
    device_service.catat_kontak(DEVICE, nama="Perangkat baru")
    (info,) = layanan.daftar()

    assert layanan.ganti_nama(info.id, "  Anjungan   Lt. 2 ").nama == "Anjungan Lt. 2"
    with pytest.raises(ValidationError):
        layanan.ganti_nama(info.id, "   ")


def test_token_bersama_dapat_dimatikan(layanan):
    assert layanan.token_bersama_aktif()
    layanan.setel_token_bersama(False)
    assert not device_service.token_bersama_aktif()


def test_hanya_admin_mengelola_perangkat(auth, antrian_siap):
    from tests.conftest import TEST_PASSWORD

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    with pytest.raises(AuthorizationError):
        PerangkatService(auth).daftar()


# ---------------------------------------------------------------------
# Lewat API
# ---------------------------------------------------------------------


def _klien():
    from app.kiosk_api import KioskServices, create_app

    return TestClient(create_app(TOKEN, KioskServices()))


def test_api_memasangkan_dan_menerima_token_perangkat(layanan):
    klien = _klien()
    kode = layanan.buat_kode().kode

    jawab = klien.post(
        "/v1/kiosk/pair",
        json={"code": kode, "device_id": DEVICE, "name": "Lobi", "kind": "anjungan"},
    )
    assert jawab.status_code == 200
    token = jawab.json()["token"]

    kategori = klien.get(
        "/v1/kiosk/categories",
        headers={"Authorization": f"Bearer {token}", "X-App-Version-Code": "5"},
    )
    assert kategori.status_code == 200
    (info,) = layanan.daftar()
    assert info.versi_kode == 5
    assert info.alamat_ip


def test_api_menolak_perangkat_yang_dicabut(layanan):
    klien = _klien()
    kode = layanan.buat_kode().kode
    token = klien.post(
        "/v1/kiosk/pair", json={"code": kode, "device_id": DEVICE, "name": "Lobi"}
    ).json()["token"]
    (info,) = layanan.daftar()
    layanan.cabut(info.id)

    assert klien.get(
        "/v1/kiosk/categories", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 401
    # Token bersama dengan device_id yang dicabut juga ditolak.
    assert klien.get(
        "/v1/kiosk/categories",
        headers={"Authorization": f"Bearer {TOKEN}", "X-Device-Id": DEVICE},
    ).status_code == 401


def test_api_token_bersama_dapat_dimatikan(layanan):
    klien = _klien()
    kepala = {"Authorization": f"Bearer {TOKEN}"}
    assert klien.get("/v1/kiosk/categories", headers=kepala).status_code == 200

    layanan.setel_token_bersama(False)

    jawab = klien.get("/v1/kiosk/categories", headers=kepala)
    assert jawab.status_code == 401
    assert "Pasangkan" in jawab.json()["detail"]


def test_api_tebakan_kode_beruntun_menghanguskan_kode(layanan):
    klien = _klien()
    benar = layanan.buat_kode().kode
    salah = "000000" if benar != "000000" else "111111"

    for _ in range(10):
        klien.post("/v1/kiosk/pair", json={"code": salah, "device_id": DEVICE})
    jawab = klien.post("/v1/kiosk/pair", json={"code": benar, "device_id": DEVICE})

    assert jawab.status_code == 429


def test_api_mencatat_hasil_cetak(layanan):
    klien = _klien()
    kepala = {"Authorization": f"Bearer {TOKEN}", "X-Device-Id": DEVICE}

    jawab = klien.post(
        "/v1/kiosk/printer", headers=kepala, json={"ok": True, "message": "Tercetak"}
    )

    assert jawab.status_code == 200
    (info,) = layanan.daftar()
    assert info.printer_ok is True


# ---------------------------------------------------------------------
# Layar antrian (TV Android)
# ---------------------------------------------------------------------


def _pasang(klien, layanan, device_id, kind):
    # Langsung ke tabel: fixture CRO sudah mengganti sesi admin.
    from app.core.database import session_scope
    from app.models import KioskPairingCode

    kode = f"{abs(hash(device_id)) % 1_000_000:06d}"
    with session_scope() as session:
        session.add(
            KioskPairingCode(kode=kode, kedaluwarsa=clock.now() + timedelta(minutes=5))
        )
    return klien.post(
        "/v1/kiosk/pair",
        json={"code": kode, "device_id": device_id, "name": "TV", "kind": kind},
    ).json()["token"]


def test_layar_antrian_hanya_menerima_token_layar(layanan, antrian_siap):
    klien = _klien()
    tv = _pasang(klien, layanan, "tv-0000-0000-0001", "layar_antrian")
    tablet = _pasang(klien, layanan, "tablet-000-0000-01", "anjungan")

    assert klien.get("/v1/layar/state", headers={"Authorization": f"Bearer {tv}"}).status_code == 200
    for token in (tablet, TOKEN):
        jawab = klien.get("/v1/layar/state", headers={"Authorization": f"Bearer {token}"})
        assert jawab.status_code == 401


def test_layar_antrian_menampilkan_loket_dan_berikutnya(layanan, antrian_siap, terbitkan, cro_queue):
    klien = _klien()
    tv = _pasang(klien, layanan, "tv-0000-0000-0002", "layar_antrian")
    terbitkan("A", 3)
    cro_queue.call_next(antrian_siap["loket"][0])

    isi = klien.get("/v1/layar/state", headers={"Authorization": f"Bearer {tv}"}).json()

    nomor = [c["queue_number"] for c in isi["counters"] if c["queue_number"]]
    assert nomor == ["A-001"]
    assert isi["next"][:2] == ["A-002", "A-003"]
    assert isi["total_waiting"] == 2
    assert isi["timezone"] == "Asia/Jakarta"


def test_layar_antrian_tidak_membunyikan_panggilan_lama(layanan, antrian_siap, terbitkan, cro_queue):
    klien = _klien()
    tv = _pasang(klien, layanan, "tv-0000-0000-0003", "layar_antrian")
    kepala = {"Authorization": f"Bearer {tv}"}
    terbitkan("A", 2)
    pertama = cro_queue.call_next(antrian_siap["loket"][0])

    awal = klien.get("/v1/layar/calls", headers=kepala).json()
    assert awal["calls"] == []

    cro_queue.recall(pertama.id)
    baru = klien.get("/v1/layar/calls", params={"after": awal["last_id"]}, headers=kepala).json()

    (panggil,) = baru["calls"]
    assert panggil["queue_number"] == "A-001"
    assert panggil["call_number"] == 2, "panggil ulang tetap dibunyikan"
    assert panggil["text"].startswith("Nomor antrian")
    assert baru["last_id"] == panggil["id"]
    kosong = klien.get("/v1/layar/calls", params={"after": baru["last_id"]}, headers=kepala).json()
    assert kosong["calls"] == []
