"""Perangkat Android (anjungan dan layar antrian): pasang, kontak, cabut."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

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


def test_daftar_anjungan_untuk_indikator_petugas(layanan):
    """Hanya anjungan yang belum dicabut; layar antrian bukan urusannya."""
    device_service.catat_kontak("tablet-pintu-01", nama="Pintu")
    device_service.catat_kontak("tablet-lobi-002", nama="Lobi")
    device_service.catat_kontak("tv-ruang-tunggu", nama="TV", jenis="layar_antrian")
    lobi = next(p for p in layanan.daftar() if p.nama == "Lobi")
    layanan.cabut(lobi.id)

    daftar = device_service.daftar_anjungan()

    assert [p.nama for p in daftar] == ["Pintu"]
    assert daftar[0].terakhir_terlihat is not None


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

    assert klien.get(
        "/v1/layar/state", headers={"Authorization": f"Bearer {tv}"}
    ).status_code == 200
    kepala_tv = {
        "Authorization": f"Bearer {tv}",
        "X-App-Version-Code": "5",
    }
    assert klien.get("/v1/kiosk/categories", headers=kepala_tv).status_code == 401
    assert klien.post(
        "/v1/kiosk/tickets",
        headers=kepala_tv,
        json={
            "category_id": antrian_siap["kategori"]["A"],
            "request_id": str(uuid4()),
        },
    ).status_code == 401
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
    assert panggil["tokens"][0] == "nomor_antrian"
    assert baru["last_id"] == panggil["id"]
    kosong = klien.get("/v1/layar/calls", params={"after": baru["last_id"]}, headers=kepala).json()
    assert kosong["calls"] == []


def test_panggilan_tetap_sampai_sesudah_id_panggilan_turun(
    layanan, antrian_siap, terbitkan, cro_queue
):
    """
    Sesudah database dipulihkan dari backup, id panggilan bisa lebih kecil
    daripada id terakhir yang diingat perangkat. Perangkat diarahkan ke id
    terakhir yang sebenarnya, bukan dibiarkan menunggu id yang tak datang.
    """
    klien = _klien()
    tv = _pasang(klien, layanan, "tv-0000-0000-0010", "layar_antrian")
    kepala = {"Authorization": f"Bearer {tv}"}
    terbitkan("A", 2)
    pertama = cro_queue.call_next(antrian_siap["loket"][0])
    sebenarnya = klien.get("/v1/layar/calls", headers=kepala).json()["last_id"]

    basi = klien.get(
        "/v1/layar/calls", params={"after": sebenarnya + 1000}, headers=kepala
    ).json()
    assert basi == {"last_id": sebenarnya, "calls": []}

    cro_queue.recall(pertama.id)
    baru = klien.get(
        "/v1/layar/calls", params={"after": basi["last_id"]}, headers=kepala
    ).json()
    assert [p["queue_number"] for p in baru["calls"]] == ["A-001"]


def test_layar_mengunduh_paket_suara_dan_apk(layanan, antrian_siap, tmp_path, monkeypatch):
    import json as _json

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    klien = _klien()
    tv = _pasang(klien, layanan, "tv-0000-0000-0009", "layar_antrian")
    kepala = {"Authorization": f"Bearer {tv}"}

    isi = klien.get("/v1/layar/state", headers=kepala).json()
    assert isi["sound_pack_version"] is None
    assert isi["app_latest_version_code"] is None
    assert klien.get("/v1/layar/sound", headers=kepala).status_code == 404

    folder = tmp_path / "media" / "suara-layar"
    folder.mkdir(parents=True)
    (folder / "angka_1.wav").write_bytes(b"RIFF-isi")
    (folder / "paket.json").write_text(
        _json.dumps({"versi": "abc123", "suara": "X", "klip": {"angka_1": "angka_1.wav"}}),
        encoding="utf-8",
    )
    apk = tmp_path / "apk"
    apk.mkdir()
    (apk / "layar.apk").write_bytes(b"PK-layar")
    (apk / "layar.json").write_text('{"version_code": 2, "version_name": "1.1"}')

    isi = klien.get("/v1/layar/state", headers=kepala).json()
    assert isi["sound_pack_version"] == "abc123"
    assert isi["app_latest_version_name"] == "1.1"
    assert klien.get("/v1/layar/sound", headers=kepala).json()["clips"] == {"angka_1": "angka_1.wav"}
    assert klien.get("/v1/layar/sound/angka_1.wav", headers=kepala).content == b"RIFF-isi"
    assert klien.get("/v1/layar/sound/..%2Fpaket.json", headers=kepala).status_code == 404
    assert klien.get("/v1/layar/app/apk", headers=kepala).content == b"PK-layar"


def test_layar_boleh_meminta_sampai_dua_belas_nomor(layanan, antrian_siap, terbitkan):
    klien = _klien()
    tv = _pasang(klien, layanan, "tv-0000-0000-0010", "layar_antrian")
    kepala = {"Authorization": f"Bearer {tv}"}
    terbitkan("A", 15)

    bawaan = klien.get("/v1/layar/state", headers=kepala).json()
    banyak = klien.get("/v1/layar/state", params={"next": 50}, headers=kepala).json()

    assert len(bawaan["next"]) == 3
    assert len(banyak["next"]) == 12
    assert banyak["total_waiting"] == 15


# ---------------------------------------------------------------------
# Anjungan yang membunyikan panggilan
# ---------------------------------------------------------------------


def _setel_bersuara(device_id: str) -> None:
    # Langsung ke tabel: fixture CRO sudah mengganti sesi admin.
    from app.core.database import session_scope
    from app.models import ApplicationSetting

    import sqlalchemy as sa

    with session_scope() as session:
        baris = session.scalar(
            sa.select(ApplicationSetting).where(
                ApplicationSetting.key == device_service.KUNCI_ANJUNGAN_BERSUARA
            )
        )
        if baris is None:
            session.add(
                ApplicationSetting(key=device_service.KUNCI_ANJUNGAN_BERSUARA, value=device_id)
            )
        else:
            baris.value = device_id


def test_hanya_anjungan_terpasang_yang_dapat_bersuara(layanan):
    from app.core.errors import NotFoundError

    klien = _klien()
    for device_id, jenis in ((DEVICE, "anjungan"), ("tv-0000-0000-0020", "layar_antrian")):
        kode = layanan.buat_kode().kode
        klien.post(
            "/v1/kiosk/pair",
            json={"code": kode, "device_id": device_id, "name": "X", "kind": jenis},
        )
    assert layanan.anjungan_bersuara() == DEVICE, "anjungan pertama dipilih otomatis"

    layanan.setel_anjungan_bersuara(None)
    layanan.setel_anjungan_bersuara(DEVICE)
    assert device_service.anjungan_bersuara() == DEVICE

    with pytest.raises(BusinessRuleError):
        layanan.setel_anjungan_bersuara("tv-0000-0000-0020")
    with pytest.raises(NotFoundError):
        layanan.setel_anjungan_bersuara("tidak-ada")
    assert device_service.anjungan_bersuara() == DEVICE, "pilihan lama tetap"

    (anjungan,) = [p for p in layanan.daftar() if p.device_id == DEVICE]
    layanan.cabut(anjungan.id)
    with pytest.raises(BusinessRuleError):
        layanan.setel_anjungan_bersuara(DEVICE)

    layanan.setel_anjungan_bersuara(None)
    assert device_service.anjungan_bersuara() == ""


def test_anjungan_terpilih_membunyikan_panggilan(
    layanan, antrian_siap, terbitkan, cro_queue, tmp_path, monkeypatch
):
    import json as _json

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    klien = _klien()
    bersuara = _pasang(klien, layanan, "kios-0000-0000-0021", "anjungan")
    diam = _pasang(klien, layanan, "kios-0000-0000-0022", "anjungan")
    tv = _pasang(klien, layanan, "tv-0000-0000-0023", "layar_antrian")
    _setel_bersuara("kios-0000-0000-0021")

    def display(token):
        return klien.get(
            "/v1/kiosk/display", headers={"Authorization": f"Bearer {token}"}
        ).json()

    assert display(bersuara)["call_sound"] is True
    assert display(diam)["call_sound"] is False
    assert display(TOKEN)["call_sound"] is False, "token bersama tidak dapat dipercaya"
    assert display(bersuara)["sound_pack_version"] is None

    kepala = {"Authorization": f"Bearer {bersuara}"}
    terbitkan("A", 1)
    awal = klien.get("/v1/kiosk/calls", headers=kepala).json()
    assert awal["calls"] == []
    cro_queue.call_next(antrian_siap["loket"][0])
    (panggil,) = klien.get(
        "/v1/kiosk/calls", params={"after": awal["last_id"]}, headers=kepala
    ).json()["calls"]
    assert panggil["queue_number"] == "A-001"
    assert panggil["text"].startswith("Nomor antrian")
    assert panggil["tokens"][0] == "nomor_antrian"
    assert 0 <= panggil["age_seconds"] < 30, "tablet melewati panggilan basi menurut umur ini"
    tolak = klien.get("/v1/kiosk/calls", headers={"Authorization": f"Bearer {tv}"})
    assert tolak.status_code == 401, "token layar antrian tetap untuk /v1/layar"

    assert klien.get("/v1/kiosk/sound", headers=kepala).status_code == 404
    folder = tmp_path / "media" / "suara-layar"
    folder.mkdir(parents=True)
    (folder / "angka_1.wav").write_bytes(b"RIFF-isi")
    (folder / "paket.json").write_text(
        _json.dumps({"versi": "abc123", "suara": "X", "klip": {"angka_1": "angka_1.wav"}}),
        encoding="utf-8",
    )
    assert display(bersuara)["sound_pack_version"] == "abc123"
    assert klien.get("/v1/kiosk/sound", headers=kepala).json()["clips"] == {
        "angka_1": "angka_1.wav"
    }
    assert klien.get("/v1/kiosk/sound/angka_1.wav", headers=kepala).content == b"RIFF-isi"
    assert klien.get("/v1/kiosk/sound/..%2Fpaket.json", headers=kepala).status_code == 404


def _pasang_lewat_kode(layanan, device_id, jenis):
    return device_service.pasangkan(layanan.buat_kode().kode, device_id, device_id, jenis)


def test_anjungan_pertama_otomatis_bersuara(layanan):
    _pasang_lewat_kode(layanan, "kios-satu", "anjungan")
    assert device_service.anjungan_bersuara() == "kios-satu"

    _pasang_lewat_kode(layanan, "kios-dua", "anjungan")
    assert device_service.anjungan_bersuara() == "kios-satu", "anjungan kedua tidak menimpa"


def test_tidak_otomatis_bila_ada_layar_antrian(layanan):
    _pasang_lewat_kode(layanan, "tv-satu", "layar_antrian")
    _pasang_lewat_kode(layanan, "kios-satu", "anjungan")
    assert device_service.anjungan_bersuara() == ""


def test_pilihan_tidak_ada_dari_admin_tidak_ditimpa(layanan):
    layanan.setel_anjungan_bersuara(None)
    _pasang_lewat_kode(layanan, "kios-satu", "anjungan")
    assert device_service.anjungan_bersuara() == ""


def test_anjungan_dicabut_tidak_menghalangi_pilihan_otomatis(layanan):
    _pasang_lewat_kode(layanan, "kios-lama", "anjungan")
    layanan.setel_anjungan_bersuara(None)
    # Pemasangan ulang dari awal: baris pengaturan dihapus, perangkat lama dicabut.
    from app.core.database import session_scope
    from app.models import ApplicationSetting

    with session_scope() as session:
        session.query(ApplicationSetting).filter_by(
            key=device_service.KUNCI_ANJUNGAN_BERSUARA
        ).delete()
    (lama,) = [p for p in layanan.daftar() if p.device_id == "kios-lama"]
    layanan.cabut(lama.id)

    _pasang_lewat_kode(layanan, "kios-baru", "anjungan")
    assert device_service.anjungan_bersuara() == "kios-baru"



@pytest.mark.parametrize(
    "path",
    [
        "/v1/kiosk/categories",
        "/v1/kiosk/display",
        "/v1/kiosk/calls",
        "/v1/kiosk/sound",
        "/v1/kiosk/sound/klip.ogg",
        "/v1/kiosk/ticket-sample",
        "/v1/kiosk/media/iklan.png",
        "/v1/kiosk/app/apk",
    ],
)
def test_anjungan_dicabut_ditolak_di_semua_endpoint(layanan, path):
    klien = _klien()
    token = _pasang(klien, layanan, DEVICE, "anjungan")
    (info,) = layanan.daftar()
    layanan.cabut(info.id)

    jawab = klien.get(path, headers={"Authorization": f"Bearer {token}"})

    assert jawab.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/v1/layar/state",
        "/v1/layar/calls",
        "/v1/layar/sound",
        "/v1/layar/sound/klip.ogg",
        "/v1/layar/app/apk",
    ],
)
def test_layar_dicabut_ditolak_di_semua_endpoint(layanan, path):
    klien = _klien()
    token = _pasang(klien, layanan, "tv-0000-0000-0099", "layar_antrian")
    (info,) = layanan.daftar()
    layanan.cabut(info.id)

    jawab = klien.get(path, headers={"Authorization": f"Bearer {token}"})

    assert jawab.status_code == 401
