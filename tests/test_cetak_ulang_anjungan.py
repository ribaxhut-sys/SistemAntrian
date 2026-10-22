"""Cetak ulang tiket di anjungan tempat nomor diambil (antrean perintah ke tablet)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core import clock
from app.core.database import session_scope
from app.core.errors import BusinessRuleError
from app.models import AuditLog, KioskCetakUlang
from app.models.enums import AuditAction
from app.services import cetak_ulang_anjungan
from app.services.apk_anjungan import VERSI_MINIMAL
from app.services.device_service import PerangkatService
from app.services.queue_service import QueueService
from tests.conftest import TEST_PASSWORD

TOKEN = "token-bersama-panjang"
DEVICE = "c1d2e3f4-0000-4000-8000-0000000000aa"
LAIN = "c1d2e3f4-0000-4000-8000-0000000000bb"


def _klien():
    from app.kiosk_api import KioskServices, create_app

    return TestClient(create_app(TOKEN, KioskServices()))


def _pasang(klien, admin_auth, device_id, nama):
    kode = PerangkatService(admin_auth).buat_kode().kode
    jawab = klien.post(
        "/v1/kiosk/pair",
        json={"code": kode, "device_id": device_id, "name": nama, "kind": "anjungan"},
    )
    assert jawab.status_code == 200
    return {
        "Authorization": f"Bearer {jawab.json()['token']}",
        "X-Device-Id": device_id,
        "X-App-Version-Code": str(VERSI_MINIMAL),
    }


def _ambil_nomor(klien, kepala, kategori, prioritas=True):
    jawab = klien.post(
        "/v1/kiosk/tickets",
        headers=kepala,
        json={"category_id": kategori, "request_id": str(uuid4()), "priority": prioritas},
    )
    assert jawab.status_code == 200, jawab.text
    return jawab.json()["data"]["queue_number"] if "data" in jawab.json() else jawab.json()["queue_number"]


def _petugas(auth):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    return QueueService(auth)


@pytest.fixture
def skenario(admin_auth, antrian_siap):
    klien = _klien()
    kepala = _pasang(klien, admin_auth, DEVICE, "Anjungan Lobi")
    kepala_lain = _pasang(klien, admin_auth, LAIN, "Anjungan Teras")
    nomor = _ambil_nomor(klien, kepala, antrian_siap["kategori"]["A"])
    layanan = _petugas(admin_auth)
    dipanggil = layanan.call_next(antrian_siap["loket"][0])
    assert dipanggil.queue_number == nomor
    return klien, kepala, kepala_lain, layanan, dipanggil


def test_cabut_lalu_cetak_ulang_sampai_ke_tablet_asal(skenario):
    klien, kepala, kepala_lain, layanan, antrian = skenario

    assert layanan.anjungan_penerbit(antrian.id) == "Anjungan Lobi"
    layanan.cabut_prioritas(antrian.id, kembalikan=True, alasan="TIDAK_MEMENUHI_SYARAT")
    assert layanan.minta_cetak_ulang_anjungan(antrian.id) == "Anjungan Lobi"

    # Tablet lain tidak menerimanya.
    assert klien.get("/v1/kiosk/cetak-ulang", headers=kepala_lain).json() == {"jobs": []}

    tugas = klien.get("/v1/kiosk/cetak-ulang", headers=kepala).json()["jobs"]
    assert len(tugas) == 1
    assert tugas[0]["queue_number"] == antrian.queue_number
    # Tiket disusun dari keadaan sekarang: tanda prioritas sudah hilang.
    assert not any("Prioritas" in baris for baris in tugas[0]["ticket_lines"])
    assert tugas[0]["ticket_layout"] is not None
    # Tiket pengganti bertanda cetak ulang; nomornya tetap yang asli.
    assert any(b.startswith("*** CETAK ULANG ") for b in tugas[0]["ticket_lines"])

    # Sekali kirim: penyegaran berikutnya tidak mencetak dua kali.
    assert klien.get("/v1/kiosk/cetak-ulang", headers=kepala).json() == {"jobs": []}

    jawab = klien.post(
        f"/v1/kiosk/cetak-ulang/{tugas[0]['id']}/hasil",
        headers=kepala,
        json={"ok": True, "message": "Tiket tercetak."},
    )
    assert jawab.status_code == 200
    with session_scope() as session:
        baris = session.scalar(sa.select(KioskCetakUlang))
        assert baris.status == cetak_ulang_anjungan.SELESAI
        aksi = session.scalar(
            sa.select(AuditLog).where(
                AuditLog.action == AuditAction.REPRINT_TICKET_KIOSK.value
            )
        )
        assert aksi is not None


def test_hasil_dari_tablet_lain_ditolak(skenario):
    klien, kepala, kepala_lain, layanan, antrian = skenario
    layanan.minta_cetak_ulang_anjungan(antrian.id)
    (tugas,) = klien.get("/v1/kiosk/cetak-ulang", headers=kepala).json()["jobs"]

    jawab = klien.post(
        f"/v1/kiosk/cetak-ulang/{tugas['id']}/hasil",
        headers=kepala_lain,
        json={"ok": True, "message": "x"},
    )

    assert jawab.status_code == 404


def test_permintaan_kembar_yang_masih_menunggu_dijadikan_satu(skenario):
    klien, kepala, _, layanan, antrian = skenario
    layanan.minta_cetak_ulang_anjungan(antrian.id)
    layanan.minta_cetak_ulang_anjungan(antrian.id)

    assert len(klien.get("/v1/kiosk/cetak-ulang", headers=kepala).json()["jobs"]) == 1


def test_perintah_terlalu_lama_tidak_dikirim(skenario):
    klien, kepala, _, layanan, antrian = skenario
    layanan.minta_cetak_ulang_anjungan(antrian.id)
    with session_scope() as session:
        session.execute(
            sa.update(KioskCetakUlang).values(
                created_at=clock.now()
                - timedelta(minutes=cetak_ulang_anjungan.UMUR_MAKS_MENIT + 1)
            )
        )

    assert klien.get("/v1/kiosk/cetak-ulang", headers=kepala).json() == {"jobs": []}
    with session_scope() as session:
        assert session.scalar(sa.select(KioskCetakUlang.status)) == "KEDALUWARSA"


def test_token_bersama_tidak_mengambil_perintah_tablet(skenario):
    klien, _, _, layanan, antrian = skenario
    layanan.minta_cetak_ulang_anjungan(antrian.id)
    bersama = {"Authorization": f"Bearer {TOKEN}", "X-Device-Id": DEVICE}

    assert klien.get("/v1/kiosk/cetak-ulang", headers=bersama).json() == {"jobs": []}


def test_nomor_dari_windows_tidak_punya_anjungan_penerbit(auth, antrian_siap):
    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    nomor = QueueService(auth).create_queue(antrian_siap["kategori"]["A"])
    layanan = _petugas(auth)

    assert layanan.anjungan_penerbit(nomor.id) is None
    with pytest.raises(BusinessRuleError, match="anjungan"):
        layanan.minta_cetak_ulang_anjungan(nomor.id)


def test_nomor_selesai_tidak_dicetak_ulang(skenario):
    _, _, _, layanan, antrian = skenario
    layanan.start_service(antrian.id)
    layanan.complete(antrian.id)

    with pytest.raises(BusinessRuleError, match="selesai"):
        layanan.minta_cetak_ulang_anjungan(antrian.id)


def test_saran_bila_cetak_di_anjungan_gagal_atau_tidak_dijawab(skenario):
    klien, kepala, _, layanan, antrian = skenario
    assert layanan.saran_cetak_ulang_anjungan(antrian.id) is None

    layanan.minta_cetak_ulang_anjungan(antrian.id)
    assert "belum menjawab" in layanan.saran_cetak_ulang_anjungan(antrian.id)

    (tugas,) = klien.get("/v1/kiosk/cetak-ulang", headers=kepala).json()["jobs"]
    klien.post(
        f"/v1/kiosk/cetak-ulang/{tugas['id']}/hasil",
        headers=kepala,
        json={"ok": False, "message": "Kertas habis"},
    )
    saran = layanan.saran_cetak_ulang_anjungan(antrian.id)
    assert "Kertas habis" in saran and "printer PC" in saran

    layanan.minta_cetak_ulang_anjungan(antrian.id)
    (tugas,) = klien.get("/v1/kiosk/cetak-ulang", headers=kepala).json()["jobs"]
    klien.post(
        f"/v1/kiosk/cetak-ulang/{tugas['id']}/hasil",
        headers=kepala,
        json={"ok": True, "message": "Tiket tercetak."},
    )
    assert layanan.saran_cetak_ulang_anjungan(antrian.id) is None


# ---------------------------------------------------------------------
# Tujuan cetak ulang: penerbit bila aktif, kalau tidak anjungan aktif lain
# ---------------------------------------------------------------------

def _terlihat(device_id: str, menit_lalu: float) -> None:
    from app.models import KioskDevice

    with session_scope() as session:
        session.execute(
            sa.update(KioskDevice)
            .where(KioskDevice.device_id == device_id)
            .values(terakhir_terlihat=clock.now() - timedelta(minutes=menit_lalu))
        )


def _nomor_dari_windows(auth, antrian_siap):
    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    return QueueService(auth).create_queue(antrian_siap["kategori"]["A"])


def test_nomor_dari_windows_dicetak_ulang_di_anjungan_aktif(
    admin_auth, auth, antrian_siap
):
    klien = _klien()
    _pasang(klien, admin_auth, DEVICE, "Anjungan Lobi")
    _terlihat(DEVICE, 0)
    nomor = _nomor_dari_windows(auth, antrian_siap)
    layanan = _petugas(auth)

    assert layanan.anjungan_penerbit(nomor.id) == "Anjungan Lobi"
    assert layanan.minta_cetak_ulang_anjungan(nomor.id) == "Anjungan Lobi"


def _id_nomor(nomor: str) -> int:
    from app.models import Queue

    with session_scope() as session:
        return session.scalar(sa.select(Queue.id).where(Queue.queue_number == nomor))


def test_penerbit_aktif_didahulukan_walau_anjungan_lain_lebih_baru(
    admin_auth, auth, antrian_siap
):
    klien = _klien()
    kepala = _pasang(klien, admin_auth, DEVICE, "Anjungan Lobi")
    _pasang(klien, admin_auth, LAIN, "Anjungan Teras")
    nomor = _ambil_nomor(klien, kepala, antrian_siap["kategori"]["A"], prioritas=False)
    _terlihat(DEVICE, 2)
    _terlihat(LAIN, 0)
    layanan = _petugas(auth)

    assert layanan.minta_cetak_ulang_anjungan(_id_nomor(nomor)) == "Anjungan Lobi"


def test_penerbit_mati_dialihkan_ke_anjungan_lain_yang_aktif(
    admin_auth, auth, antrian_siap
):
    klien = _klien()
    kepala = _pasang(klien, admin_auth, DEVICE, "Anjungan Lobi")
    _pasang(klien, admin_auth, LAIN, "Anjungan Teras")
    nomor = _ambil_nomor(klien, kepala, antrian_siap["kategori"]["A"], prioritas=False)
    _terlihat(DEVICE, cetak_ulang_anjungan.AKTIF_MENIT + 5)
    _terlihat(LAIN, 0)
    layanan = _petugas(auth)

    assert layanan.minta_cetak_ulang_anjungan(_id_nomor(nomor)) == "Anjungan Teras"


def test_tanpa_anjungan_aktif_penerbit_tetap_dipakai_agar_ada_saran(
    admin_auth, auth, antrian_siap
):
    klien = _klien()
    kepala = _pasang(klien, admin_auth, DEVICE, "Anjungan Lobi")
    nomor = _ambil_nomor(klien, kepala, antrian_siap["kategori"]["A"], prioritas=False)
    _terlihat(DEVICE, cetak_ulang_anjungan.AKTIF_MENIT + 5)
    layanan = _petugas(auth)

    assert layanan.minta_cetak_ulang_anjungan(_id_nomor(nomor)) == "Anjungan Lobi"


def test_nomor_dari_windows_tanpa_anjungan_aktif_ditolak(
    admin_auth, auth, antrian_siap
):
    klien = _klien()
    _pasang(klien, admin_auth, DEVICE, "Anjungan Lobi")
    _terlihat(DEVICE, cetak_ulang_anjungan.AKTIF_MENIT + 5)
    nomor = _nomor_dari_windows(auth, antrian_siap)
    layanan = _petugas(auth)

    # Tidak ada penerbit dan satu-satunya anjungan mati: tidak ada tujuan.
    assert layanan.anjungan_penerbit(nomor.id) is None
    with pytest.raises(BusinessRuleError, match="anjungan"):
        layanan.minta_cetak_ulang_anjungan(nomor.id)
