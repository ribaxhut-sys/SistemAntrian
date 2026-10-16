"""Nomor prioritas (lansia, disabilitas, ibu hamil) dan urutan panggilnya."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import BusinessRuleError, ValidationError
from app.services.queue_service import QueueService
from app.services.urutan_prioritas import (
    MODE_BIASA,
    MODE_OTOMATIS,
    MODE_PRIORITAS,
    susun,
)
from tests.conftest import TEST_PASSWORD


def _n(nomor, prioritas=None):
    return SimpleNamespace(nomor=nomor, prioritas=prioritas)


def _urut(daftar):
    return [a.nomor for a in daftar]


# ---------------------------------------------------------------------
# Fungsi urutan (murni)
# ---------------------------------------------------------------------


def test_tanpa_prioritas_urutan_tidak_berubah():
    daftar = [_n("A1"), _n("A2"), _n("A3")]
    assert _urut(susun(daftar, rasio=3)) == ["A1", "A2", "A3"]


def test_rasio_tiga_prioritas_disusul_satu_biasa():
    daftar = [
        _n("B1"),
        _n("P1", "LANSIA"),
        _n("P2", "LANSIA"),
        _n("P3", "IBU_HAMIL"),
        _n("P4", "DISABILITAS"),
        _n("B2"),
    ]
    assert _urut(susun(daftar, rasio=3)) == ["P1", "P2", "P3", "B1", "P4", "B2"]


def test_rasio_nol_prioritas_selalu_lebih_dulu():
    daftar = [_n("B1"), _n("P1", "LANSIA"), _n("P2", "LANSIA"), _n("B2")]
    assert _urut(susun(daftar, rasio=0)) == ["P1", "P2", "B1", "B2"]


def test_beruntun_yang_sudah_terpanggil_diperhitungkan():
    daftar = [_n("B1"), _n("P1", "LANSIA")]
    # Tiga prioritas baru saja dipanggil: giliran nomor biasa.
    assert _urut(susun(daftar, rasio=3, beruntun=3)) == ["B1", "P1"]
    assert _urut(susun(daftar, rasio=3, beruntun=2)) == ["P1", "B1"]


def test_mode_manual_mengalahkan_otomatis():
    daftar = [_n("B1"), _n("P1", "LANSIA")]
    assert _urut(susun(daftar, rasio=3, mode=MODE_BIASA)) == ["B1", "P1"]
    assert _urut(susun(daftar, rasio=3, mode=MODE_PRIORITAS)) == ["P1", "B1"]
    assert _urut(susun(daftar, rasio=3, mode=MODE_OTOMATIS)) == ["P1", "B1"]


def test_mode_tidak_dikenal_ditolak():
    with pytest.raises(ValueError):
        susun([], rasio=3, mode="acak")


# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------


def _terbit(auth, antrian_siap, daftar):
    """daftar: [(prefix, prioritas|None), ...] diterbitkan oleh pendaftaran."""
    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    layanan = QueueService(auth)
    return [
        layanan.create_queue(antrian_siap["kategori"][prefix], prioritas=prioritas)
        for prefix, prioritas in daftar
    ]


def _panggil_semua(auth, antrian_siap, jumlah, **kw):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    layanan = QueueService(auth)
    loket = antrian_siap["loket"][0]
    urutan = []
    for _ in range(jumlah):
        info = layanan.call_next(loket, **kw)
        urutan.append(info.queue_number)
        layanan.start_service(info.id)
        layanan.complete(info.id)
    return urutan


def test_pendaftaran_menandai_prioritas_dan_tersimpan(auth, antrian_siap):
    biasa, lansia = _terbit(auth, antrian_siap, [("A", None), ("A", "LANSIA")])

    assert biasa.prioritas is None
    assert lansia.prioritas == "LANSIA"
    assert lansia.label_prioritas == "Lansia"


def test_hanya_pendaftaran_yang_boleh_menandai(auth, antrian_siap):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    # CRO tidak punya hak menerbitkan sama sekali; yang penting ditolak.
    with pytest.raises(Exception):  # noqa: B017 - AuthorizationError
        QueueService(auth).create_queue(
            antrian_siap["kategori"]["A"], prioritas="LANSIA"
        )


def test_anjungan_tidak_boleh_menandai_prioritas(auth, antrian_siap):
    auth.logout()
    auth.mulai_sesi_kios()
    with pytest.raises(BusinessRuleError, match="petugas pendaftaran"):
        QueueService(auth).create_queue(
            antrian_siap["kategori"]["A"], prioritas="LANSIA", perangkat="tab-1"
        )


def test_alasan_tidak_dikenal_ditolak(auth, antrian_siap):
    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    with pytest.raises(ValidationError):
        QueueService(auth).create_queue(
            antrian_siap["kategori"]["A"], prioritas="VIP"
        )


def test_urutan_panggil_tiga_prioritas_satu_biasa(auth, antrian_siap):
    _terbit(
        auth,
        antrian_siap,
        [
            ("A", None),       # A-001 biasa
            ("A", "LANSIA"),   # A-002
            ("A", "LANSIA"),   # A-003
            ("A", "IBU_HAMIL"),  # A-004
            ("A", "DISABILITAS"),  # A-005
            ("A", None),       # A-006 biasa
        ],
    )

    assert _panggil_semua(auth, antrian_siap, 6) == [
        "A-002", "A-003", "A-004", "A-001", "A-005", "A-006",
    ]


def test_petugas_dapat_memilih_biasa_dulu(auth, antrian_siap):
    _terbit(auth, antrian_siap, [("A", "LANSIA"), ("A", None)])

    assert _panggil_semua(auth, antrian_siap, 1, urutan=MODE_BIASA) == ["A-002"]


def test_petugas_dapat_memilih_prioritas_dulu(auth, antrian_siap):
    _terbit(auth, antrian_siap, [("A", None), ("A", "LANSIA")])

    assert _panggil_semua(auth, antrian_siap, 1, urutan=MODE_PRIORITAS) == ["A-002"]


def test_urutan_manual_tidak_dikenal_ditolak(auth, antrian_siap):
    _terbit(auth, antrian_siap, [("A", None)])
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(ValidationError):
        QueueService(auth).call_next(antrian_siap["loket"][0], urutan="acak")


def test_daftar_menunggu_mengikuti_urutan_panggil(auth, antrian_siap):
    _terbit(
        auth, antrian_siap, [("A", None), ("A", "LANSIA"), ("A", None)]
    )
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    nomor = [q.queue_number for q in QueueService(auth).list_waiting()]

    assert nomor == ["A-002", "A-001", "A-003"]


def test_rasio_dari_pengaturan_dipakai(auth, antrian_siap):
    from app.services.settings_service import SettingsService

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("queue.rasio_prioritas", "1")
    _terbit(
        auth,
        antrian_siap,
        [("A", None), ("A", "LANSIA"), ("A", "LANSIA"), ("A", None)],
    )

    # Rasio 1: prioritas, biasa, prioritas, biasa.
    assert _panggil_semua(auth, antrian_siap, 4) == [
        "A-002", "A-001", "A-003", "A-004",
    ]


def test_layar_dan_anjungan_memakai_urutan_panggil(auth, antrian_siap):
    _terbit(auth, antrian_siap, [("A", None), ("A", "LANSIA")])
    auth.logout()
    auth.login("display", TEST_PASSWORD)
    layanan = QueueService(auth)

    keadaan = layanan.display_state(3)

    assert [q.queue_number for q in keadaan.berikutnya] == ["A-002", "A-001"]
    assert layanan.nomor_menunggu_untuk_layar() == ["A-002", "A-001"]
