"""Test pengelolaan data master."""

from __future__ import annotations

import pytest

from app.core.errors import (
    AuthorizationError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)
from app.models import RecordStatus
from app.services.master_data_service import MasterDataService
from tests.conftest import TEST_PASSWORD


# ---------------------------------------------------------------------
# Pembacaan
# ---------------------------------------------------------------------

def test_daftar_loket_dari_seed(master_service):
    loket = master_service.list_counters()
    assert [c.code for c in loket] == ["LOKET-1", "LOKET-2", "LOKET-3"]


def test_daftar_jenis_layanan_terurut(master_service):
    layanan = master_service.list_categories()
    assert [c.prefix for c in layanan] == ["A", "B", "C"]
    assert layanan[0].contoh_nomor == "A-001"


def test_petugas_biasa_boleh_membaca_data_master(auth):
    """
    Petugas pendaftaran perlu daftar jenis layanan untuk menerbitkan nomor,
    padahal ia tidak berhak mengubah data master.
    """
    auth.login("registration", TEST_PASSWORD)
    service = MasterDataService(auth)

    assert len(service.list_categories(only_active=True)) == 3
    assert len(service.list_counters(only_active=True)) == 3


def test_membaca_data_master_tanpa_login_ditolak(auth):
    from app.core.errors import AuthenticationError

    service = MasterDataService(auth)
    with pytest.raises(AuthenticationError):
        service.list_counters()


# ---------------------------------------------------------------------
# Loket
# ---------------------------------------------------------------------

def test_admin_dapat_menambah_loket(master_service):
    counter_id = master_service.create_counter(code="loket-4", name="Loket 4")

    dibuat = master_service.get_counter(counter_id)
    assert dibuat.code == "LOKET-4"  # kode dinormalkan menjadi huruf besar
    assert dibuat.name == "Loket 4"
    assert dibuat.is_active


def test_kode_loket_dinormalkan(master_service):
    """Kode dengan spasi dan huruf kecil tidak boleh lolos menjadi duplikat tersamar."""
    counter_id = master_service.create_counter(code="  loket 9 ", name="Loket 9")
    assert master_service.get_counter(counter_id).code == "LOKET-9"


def test_kode_loket_ganda_ditolak(master_service):
    with pytest.raises(ValidationError):
        master_service.create_counter(code="LOKET-1", name="Duplikat")


def test_kode_loket_ganda_beda_huruf_besar_kecil_juga_ditolak(master_service):
    with pytest.raises(ValidationError):
        master_service.create_counter(code="loket-1", name="Duplikat")


@pytest.mark.parametrize("kosong", ["", "   ", None])
def test_nama_loket_wajib(master_service, kosong):
    with pytest.raises(ValidationError):
        master_service.create_counter(code="LOKET-8", name=kosong)


def test_nama_loket_dapat_diubah(master_service):
    loket = master_service.list_counters()[0]
    diubah = master_service.update_counter(loket.id, name="Loket Utama")
    assert diubah.name == "Loket Utama"
    assert diubah.code == loket.code  # kode tidak berubah


def test_loket_dapat_dinonaktifkan_dan_diaktifkan(master_service):
    loket = master_service.list_counters()[0]

    assert not master_service.set_counter_status(loket.id, False).is_active
    assert len(master_service.list_counters(only_active=True)) == 2

    assert master_service.set_counter_status(loket.id, True).is_active
    assert len(master_service.list_counters(only_active=True)) == 3


def test_loket_aktif_terakhir_tidak_boleh_dinonaktifkan(master_service):
    """Tanpa loket aktif, tidak ada antrian yang dapat dipanggil."""
    loket = master_service.list_counters()
    master_service.set_counter_status(loket[0].id, False)
    master_service.set_counter_status(loket[1].id, False)

    with pytest.raises(BusinessRuleError):
        master_service.set_counter_status(loket[2].id, False)

    assert len(master_service.list_counters(only_active=True)) == 1


def test_loket_tidak_dikenal_ditolak(master_service):
    with pytest.raises(NotFoundError):
        master_service.get_counter(999999)
    with pytest.raises(NotFoundError):
        master_service.update_counter(999999, name="Hantu")


# ---------------------------------------------------------------------
# Jenis layanan
# ---------------------------------------------------------------------

def test_admin_dapat_menambah_jenis_layanan(master_service):
    category_id = master_service.create_category(
        code="pengembalian", name="Pengembalian", prefix="d"
    )

    dibuat = master_service.get_category(category_id)
    assert dibuat.code == "PENGEMBALIAN"
    assert dibuat.prefix == "D"  # prefix dinormalkan menjadi huruf besar
    assert dibuat.contoh_nomor == "D-001"
    assert dibuat.display_order == 4


def test_prefix_ganda_ditolak_dengan_penjelasan(master_service):
    """
    Prefix yang sama membuat nomor antrian bertabrakan, jadi pesannya harus
    menjelaskan sebabnya, bukan sekadar "gagal".
    """
    with pytest.raises(ValidationError) as gagal:
        master_service.create_category(code="LAIN", name="Layanan Lain", prefix="A")

    pesan = gagal.value.user_message
    assert "Konsultasi" in pesan
    assert "bertabrakan" in pesan


@pytest.mark.parametrize("buruk", ["1", "A1", "ABC", "-", " ", "a b"])
def test_prefix_harus_satu_atau_dua_huruf(master_service, buruk):
    with pytest.raises(ValidationError):
        master_service.create_category(code="UJI", name="Uji", prefix=buruk)


def test_prefix_dua_huruf_diterima(master_service):
    category_id = master_service.create_category(
        code="KHUSUS", name="Layanan Khusus", prefix="AB"
    )
    assert master_service.get_category(category_id).contoh_nomor == "AB-001"


def test_kode_jenis_layanan_ganda_ditolak(master_service):
    with pytest.raises(ValidationError):
        master_service.create_category(code="KONSULTASI", name="Lain", prefix="Z")


def test_nama_jenis_layanan_dapat_diubah(master_service):
    layanan = master_service.list_categories()[0]
    diubah = master_service.update_category(layanan.id, name="Konsultasi Perpajakan")

    assert diubah.name == "Konsultasi Perpajakan"
    assert diubah.prefix == "A"


def test_prefix_dapat_diubah_selama_belum_terpakai(master_service):
    layanan = master_service.list_categories()[0]
    diubah = master_service.update_category(layanan.id, name="Konsultasi", prefix="K")
    assert diubah.prefix == "K"


def test_prefix_tidak_dapat_diubah_bila_sudah_ada_antrian(master_service, master):
    """
    Setelah nomor A-023 terbit, mengubah prefix akan membuat nomor lama
    tidak lagi cocok dengan jenis layanannya.
    """
    from app.core import clock
    from app.core.database import session_scope
    from app.models import Queue

    layanan = master_service.list_categories()[0]
    with session_scope() as s:
        s.add(
            Queue(
                branch_id=layanan.branch_id,
                category_id=layanan.id,
                queue_date=clock.today(),
                queue_number="A-001",
                sequence_number=1,
            )
        )

    with pytest.raises(BusinessRuleError) as gagal:
        master_service.update_category(layanan.id, name="Konsultasi", prefix="K")

    assert "sudah dipakai antrian" in gagal.value.user_message
    # Nama tetap boleh diubah.
    assert master_service.update_category(layanan.id, name="Konsultasi Pajak").prefix == "A"


def test_prefix_ganda_saat_mengubah_ditolak(master_service):
    layanan = master_service.list_categories()[0]
    with pytest.raises(ValidationError):
        master_service.update_category(layanan.id, name="Konsultasi", prefix="B")


def test_jenis_layanan_dapat_dinonaktifkan(master_service):
    layanan = master_service.list_categories()[0]

    assert not master_service.set_category_status(layanan.id, False).is_active
    assert len(master_service.list_categories(only_active=True)) == 2


def test_jenis_layanan_aktif_terakhir_tidak_boleh_dinonaktifkan(master_service):
    """Tanpa jenis layanan aktif, tidak ada nomor antrian yang bisa diterbitkan."""
    layanan = master_service.list_categories()
    master_service.set_category_status(layanan[0].id, False)
    master_service.set_category_status(layanan[1].id, False)

    with pytest.raises(BusinessRuleError):
        master_service.set_category_status(layanan[2].id, False)


# ---------------------------------------------------------------------
# Cabang
# ---------------------------------------------------------------------

def test_nama_cabang_dapat_diubah(master_service):
    cabang = master_service.list_branches()[0]
    diubah = master_service.update_branch(
        cabang.id, name="KPP Pratama", address="Jl. Merdeka 1"
    )

    assert diubah.name == "KPP Pratama"
    assert diubah.address == "Jl. Merdeka 1"
    assert diubah.code == cabang.code  # kode cabang tidak dapat diubah


def test_alamat_kosong_disimpan_sebagai_kosong(master_service):
    cabang = master_service.list_branches()[0]
    assert master_service.update_branch(cabang.id, name="KPP", address="   ").address is None


# ---------------------------------------------------------------------
# Hak akses
# ---------------------------------------------------------------------

@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration", "display"])
def test_selain_admin_tidak_dapat_mengubah_data_master(auth, peran):
    auth.login(peran, TEST_PASSWORD)
    service = MasterDataService(auth)

    with pytest.raises(AuthorizationError):
        service.create_counter(code="LOKET-X", name="Loket Nakal")
    with pytest.raises(AuthorizationError):
        service.create_category(code="X", name="Layanan Nakal", prefix="X")


def test_selain_admin_tidak_dapat_menonaktifkan_loket(auth, master_service):
    loket = master_service.list_counters()[0]
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        MasterDataService(auth).set_counter_status(loket.id, False)


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def test_perubahan_data_master_tercatat_di_audit(master_service):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    master_service.create_counter(code="LOKET-7", name="Loket 7")

    with session_scope() as s:
        entri = [
            r
            for r in s.scalars(sa.select(AuditLog))
            if r.entity_type == "counter" and r.action == "CHANGE_CONFIGURATION"
        ]

    assert entri, "perubahan data master harus tercatat"
    assert "LOKET-7" in (entri[-1].meta or "")


def test_status_awal_data_master_aktif(master_service):
    counter_id = master_service.create_counter(code="LOKET-5", name="Loket 5")
    category_id = master_service.create_category(code="BARU", name="Baru", prefix="E")

    assert master_service.get_counter(counter_id).status is RecordStatus.ACTIVE
    assert master_service.get_category(category_id).status is RecordStatus.ACTIVE
