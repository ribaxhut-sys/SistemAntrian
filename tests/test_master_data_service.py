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


# ---------------------------------------------------------------------
# Jenis layanan yang dilayani sebuah loket
# ---------------------------------------------------------------------

def test_loket_baru_melayani_semua_jenis_layanan(master_service):
    """
    Kosong berarti SEMUA, bukan tidak ada.

    Kalau terbalik, pemasangan baru dan loket yang belum sempat diatur akan
    berdiri diam tanpa pernah bisa memanggil siapa pun.
    """
    loket = master_service.list_counters()[0]

    assert loket.category_ids == ()
    assert loket.melayani_semua


def test_atur_jenis_layanan_loket(master_service):
    loket = master_service.list_counters()[0]
    kategori = master_service.list_categories()

    hasil = master_service.set_counter_categories(loket.id, [kategori[0].id])

    assert hasil.category_ids == (kategori[0].id,)
    assert not hasil.melayani_semua
    assert master_service.get_counter(loket.id).category_ids == (kategori[0].id,)


def test_daftar_kosong_mengembalikan_loket_ke_semua_layanan(master_service):
    loket = master_service.list_counters()[0]
    kategori = master_service.list_categories()
    master_service.set_counter_categories(loket.id, [kategori[0].id])

    hasil = master_service.set_counter_categories(loket.id, [])

    assert hasil.category_ids == ()
    assert hasil.melayani_semua


def test_jenis_layanan_ganda_pada_satu_loket(master_service):
    loket = master_service.list_counters()[0]
    kategori = master_service.list_categories()

    hasil = master_service.set_counter_categories(
        loket.id, [kategori[0].id, kategori[1].id]
    )

    assert set(hasil.category_ids) == {kategori[0].id, kategori[1].id}


def test_jenis_layanan_kembar_tidak_menggandakan_baris(master_service):
    loket = master_service.list_counters()[0]
    kategori = master_service.list_categories()[0]

    hasil = master_service.set_counter_categories(
        loket.id, [kategori.id, kategori.id]
    )

    assert hasil.category_ids == (kategori.id,)


def test_jenis_layanan_tidak_dikenal_ditolak(master_service):
    loket = master_service.list_counters()[0]

    with pytest.raises(NotFoundError):
        master_service.set_counter_categories(loket.id, [999999])


def test_selain_admin_tidak_dapat_mengatur_layanan_loket(auth, master_service):
    loket = master_service.list_counters()[0]
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        MasterDataService(auth).set_counter_categories(loket.id, [])


# ---------------------------------------------------------------------
# Layanan tanpa loket
# ---------------------------------------------------------------------

def test_semua_layanan_terlayani_saat_ada_loket_tanpa_batasan(master_service):
    """Satu loket yang dibiarkan "Semua" sudah cukup menutup seluruhnya."""
    kategori = master_service.list_categories()
    loket = master_service.list_counters()
    master_service.set_counter_categories(loket[0].id, [kategori[0].id])

    assert master_service.layanan_tanpa_loket() == []


def test_layanan_tanpa_loket_disebutkan(master_service):
    """
    Keadaan ini sah tersimpan tetapi keliru: anjungan tetap menerbitkan
    nomornya dan tidak ada loket yang bisa memanggilnya.
    """
    kategori = master_service.list_categories()
    for loket in master_service.list_counters():
        master_service.set_counter_categories(loket.id, [kategori[0].id])

    yatim = master_service.layanan_tanpa_loket()

    assert [k.prefix for k in yatim] == ["B", "C"]


def test_loket_nonaktif_tidak_dihitung_melayani(master_service):
    kategori = master_service.list_categories()
    loket = master_service.list_counters()
    master_service.set_counter_categories(loket[0].id, [kategori[1].id])
    for lain in loket[1:]:
        master_service.set_counter_categories(lain.id, [kategori[0].id])
    master_service.set_counter_status(loket[0].id, False)

    assert [k.prefix for k in master_service.layanan_tanpa_loket()] == ["B", "C"]


def test_layanan_nonaktif_tidak_dianggap_yatim(master_service):
    """Layanan yang sudah dimatikan tidak menerbitkan nomor apa pun."""
    kategori = master_service.list_categories()
    for loket in master_service.list_counters():
        master_service.set_counter_categories(loket.id, [kategori[0].id])
    master_service.set_category_status(kategori[1].id, False)

    assert [k.prefix for k in master_service.layanan_tanpa_loket()] == ["C"]


def test_loket_istirahat_tetap_dihitung_melayani(master_service):
    """
    Istirahat itu sementara dan diakhiri sendiri oleh petugasnya.

    Bila istirahat ikut dihitung, peringatan "tanpa loket" akan menyala
    setiap jam makan siang lalu berhenti dibaca.
    """
    from app.core.database import session_scope
    from app.models import Counter

    kategori = master_service.list_categories()
    loket = master_service.list_counters()
    for baris in loket:
        master_service.set_counter_categories(baris.id, [kategori[0].id])
    master_service.set_counter_categories(loket[0].id, [kategori[1].id])

    with session_scope() as session:
        session.get(Counter, loket[0].id).on_break = True

    assert [k.prefix for k in master_service.layanan_tanpa_loket()] == ["C"]


def test_petugas_biasa_boleh_membaca_layanan_tanpa_loket(auth, master_service):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    assert MasterDataService(auth).layanan_tanpa_loket() == []


# ---------------------------------------------------------------------
# Urutan tampil jenis layanan
# ---------------------------------------------------------------------

def test_jenis_layanan_dapat_digeser_turun(master_service):
    """Urutan ini yang menyusun tombol di anjungan."""
    kategori = master_service.list_categories()

    hasil = master_service.pindahkan_category(kategori[0].id, naik=False)

    assert [k.prefix for k in hasil] == ["B", "A", "C"]
    assert [k.prefix for k in master_service.list_categories()] == ["B", "A", "C"]


def test_jenis_layanan_dapat_digeser_naik(master_service):
    kategori = master_service.list_categories()

    hasil = master_service.pindahkan_category(kategori[2].id, naik=True)

    assert [k.prefix for k in hasil] == ["A", "C", "B"]


def test_jenis_layanan_teratas_tidak_dapat_naik(master_service):
    kategori = master_service.list_categories()

    with pytest.raises(BusinessRuleError):
        master_service.pindahkan_category(kategori[0].id, naik=True)


def test_jenis_layanan_terbawah_tidak_dapat_turun(master_service):
    kategori = master_service.list_categories()

    with pytest.raises(BusinessRuleError):
        master_service.pindahkan_category(kategori[-1].id, naik=False)


def test_urutan_kembar_dinomori_ulang_sebelum_ditukar(master_service):
    """
    Pada display_order yang kembar, tukar-menukar tidak mengubah apa pun.

    Data lama boleh punya urutan kembar atau berlubang; tanpa penomoran
    ulang, tombol Naik/Turun akan tampak tidak berfungsi.
    """
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import ServiceCategory

    with session_scope() as session:
        session.execute(sa.update(ServiceCategory).values(display_order=0))

    kategori = master_service.list_categories()
    hasil = master_service.pindahkan_category(kategori[0].id, naik=False)

    assert [k.prefix for k in hasil] == ["B", "A", "C"]
    assert [k.display_order for k in hasil] == [1, 2, 3]


def test_jenis_layanan_nonaktif_tetap_menempati_urutan(master_service):
    """
    Tempatnya harus terjaga supaya urutannya kembali seperti semula
    begitu jenis layanan itu diaktifkan lagi.
    """
    kategori = master_service.list_categories()
    master_service.set_category_status(kategori[1].id, False)

    hasil = master_service.pindahkan_category(kategori[2].id, naik=True)

    assert [k.prefix for k in hasil] == ["A", "C", "B"]


def test_selain_admin_tidak_dapat_memindah_urutan(auth, master_service):
    kategori = master_service.list_categories()
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        MasterDataService(auth).pindahkan_category(kategori[0].id, naik=False)


# ---------------------------------------------------------------------
# Nonaktifkan loket yang sedang melayani
# ---------------------------------------------------------------------

def test_loket_yang_sedang_melayani_tidak_dapat_dinonaktifkan(
    auth, master_service, antrian_siap, terbitkan
):
    """
    Kartunya akan hilang dari papan televisi begitu dinonaktifkan, sedangkan
    pengunjungnya masih duduk di depan meja.
    """
    from app.services.queue_service import QueueService

    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    antrian = QueueService(auth).call_next(loket)

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    with pytest.raises(BusinessRuleError) as gagal:
        MasterDataService(auth).set_counter_status(loket, False)

    assert antrian.queue_number in gagal.value.user_message


def test_loket_bebas_dapat_dinonaktifkan(auth, master_service, antrian_siap, terbitkan):
    """Setelah pelayanannya selesai, loket kembali boleh dinonaktifkan."""
    from app.services.queue_service import QueueService

    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    cro = QueueService(auth)
    antrian = cro.call_next(loket)
    cro.start_service(antrian.id)
    cro.complete(antrian.id)

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    hasil = MasterDataService(auth).set_counter_status(loket, False)

    assert hasil.status is RecordStatus.INACTIVE


# ---------------------------------------------------------------------
# Hapus jenis layanan
# ---------------------------------------------------------------------

def test_jenis_layanan_yang_belum_dipakai_dapat_dihapus(master_service):
    """Salah ketik saat pemasangan tidak boleh tertinggal selamanya."""
    category_id = master_service.create_category(
        code="SALAH", name="Salah Ketik", prefix="Z"
    )

    master_service.delete_category(category_id)

    assert category_id not in [c.id for c in master_service.list_categories()]


def test_jenis_layanan_yang_sudah_dipakai_tidak_dapat_dihapus(
    auth, master_service, antrian_siap, terbitkan
):
    """Riwayat antrian dan laporan lama merujuk kepadanya."""
    terbitkan("A", 1)
    kategori = antrian_siap["kategori"]["A"]

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    with pytest.raises(BusinessRuleError) as gagal:
        MasterDataService(auth).delete_category(kategori)

    assert "Nonaktifkan" in gagal.value.user_message


def test_hapus_jenis_layanan_tidak_dikenal_ditolak(master_service):
    with pytest.raises(NotFoundError):
        master_service.delete_category(999999)


def test_jenis_layanan_aktif_terakhir_tidak_dapat_dihapus(master_service):
    """Tanpa satu pun jenis layanan aktif, nomor tidak dapat diterbitkan."""
    kategori = master_service.list_categories()
    for baris in kategori[1:]:
        master_service.set_category_status(baris.id, False)

    with pytest.raises(BusinessRuleError):
        master_service.delete_category(kategori[0].id)


def test_penghapusan_jenis_layanan_tercatat_di_audit(master_service):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    category_id = master_service.create_category(
        code="SALAH", name="Salah Ketik", prefix="Z"
    )
    master_service.delete_category(category_id)

    with session_scope() as s:
        entri = [
            r
            for r in s.scalars(sa.select(AuditLog))
            if r.entity_type == "service_category" and "hapus" in (r.meta or "")
        ]

    assert entri, "penghapusan data master harus tercatat"
    assert "SALAH" in (entri[-1].meta or "")


def test_selain_admin_tidak_dapat_menghapus_jenis_layanan(auth, master_service):
    kategori = master_service.list_categories()[0]
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        MasterDataService(auth).delete_category(kategori.id)
def test_hapus_layanan_membersihkan_ikatan_loket(master_service):
    """
    Ikatan loket-layanan ikut terhapus lewat CASCADE.

    Bila baris ikatannya tertinggal, loket itu akan terlihat "khusus" pada
    jenis layanan yang sudah tidak ada, dan tidak akan pernah bisa
    memanggil siapa pun.
    """
    loket = master_service.list_counters()[0]
    category_id = master_service.create_category(
        code="SALAH", name="Salah Ketik", prefix="Z"
    )
    master_service.set_counter_categories(loket.id, [category_id])
    assert master_service.get_counter(loket.id).category_ids == (category_id,)

    master_service.delete_category(category_id)

    assert master_service.get_counter(loket.id).category_ids == ()
