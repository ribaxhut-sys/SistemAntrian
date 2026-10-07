"""
Test menu jenis layanan bertingkat.

Anjungan tidak lagi memajang seluruh jenis layanan sekaligus. "Konsultasi"
kini KELOMPOK: menyentuhnya membuka PBB, PKB, PAT, Reklame, dan PBJT — dan
PBJT sendiri membuka Restoran, Parkir, Hotel, dan Hiburan. Yang dikunci di
sini terutama dua hal yang paling mudah rusak diam-diam: kelompok tidak
boleh menerbitkan nomor, dan pengunjung tidak boleh terkurung di dalam
sebuah kelompok tanpa jalan keluar.

Seluruh berkas ini memakai marker `layanan_bertingkat` supaya pohon bawaan
dari seed tidak diratakan fixture — lihat `layanan_bawaan_datar` di
conftest.
"""

from __future__ import annotations

import pytest

from app.core.errors import BusinessRuleError, ValidationError

pytestmark = pytest.mark.layanan_bertingkat

#: Kata sandi seluruh user uji; sama dengan yang dipakai conftest.
TEST_PASSWORD = "rahasia123"


@pytest.fixture
def admin_lain(users):
    """
    MasterDataService dengan AuthService-nya SENDIRI.

    Fixture `auth` dipakai bersama seluruh layar dalam satu test, dan
    login sebagai admin di tengah test akan menggusur sesi kios yang
    sedang dipegang anjungan. Sesi tersimpan per-instance AuthService,
    sehingga instance kedua memberi admin tempat berdiri sendiri.
    """
    from app.services.auth_service import AuthService
    from app.services.master_data_service import MasterDataService

    lain = AuthService()
    lain.login("admin", TEST_PASSWORD)
    return MasterDataService(lain)


# ---------------------------------------------------------------------
# Susunan bawaan
# ---------------------------------------------------------------------

def test_seed_memasang_konsultasi_perpajakan(master_service):
    """Pemasangan baru langsung mendapat susunan yang sama dengan kantornya."""
    semua = master_service.list_categories()
    per_kode = {k.code: k for k in semua}

    konsultasi = per_kode["KONSULTASI"]
    assert konsultasi.parent_id is None
    assert konsultasi.punya_anak

    anak = [k.code for k in semua if k.parent_id == konsultasi.id]
    assert anak == ["PBB", "PKB", "PAT", "REKLAME", "PBJT"]

    pbjt = per_kode["PBJT"]
    assert pbjt.punya_anak
    cucu = [k.code for k in semua if k.parent_id == pbjt.id]
    assert cucu == ["RESTORAN", "PARKIR", "HOTEL", "HIBURAN"]


def test_daftar_tersusun_induk_lalu_anak(master_service):
    """
    Urutannya menelusuri pohon, bukan sekadar display_order mentah.

    Anak Konsultasi bernomor urut 1..5 dan anak PBJT 1..4, sehingga daftar
    yang diurutkan angka saja akan mencampur ketiga tingkat.
    """
    urutan = [(k.code, k.level) for k in master_service.list_categories()]
    assert urutan[:11] == [
        ("KONSULTASI", 0),
        ("PBB", 1),
        ("PKB", 1),
        ("PAT", 1),
        ("REKLAME", 1),
        ("PBJT", 1),
        ("RESTORAN", 2),
        ("PARKIR", 2),
        ("HOTEL", 2),
        ("HIBURAN", 2),
        ("PENGADUAN", 0),
    ]


def test_only_leaf_membuang_kelompok(master_service):
    """Layar petugas hanya boleh ditawari yang benar-benar punya nomor."""
    kode = {k.code for k in master_service.list_categories(only_leaf=True)}
    assert "KONSULTASI" not in kode
    assert "PBJT" not in kode
    assert {"PBB", "RESTORAN", "PENGADUAN"} <= kode


def test_kelompok_tidak_menjanjikan_contoh_nomor(master_service):
    """"PJ-001" pada kartu PBJT adalah nomor yang tidak akan pernah ada."""
    per_kode = {k.code: k for k in master_service.list_categories()}
    assert per_kode["PBJT"].contoh_nomor == "—"
    assert per_kode["RESTORAN"].contoh_nomor == "RS-001"


# ---------------------------------------------------------------------
# Aturan kelompok
# ---------------------------------------------------------------------

def test_kelompok_menolak_menerbitkan_nomor(reg_queue, master_service):
    """
    Inti aturannya: nomor terbit atas nama daun, bukan atas nama kelompok.

    Ditolak di service, bukan sekadar disembunyikan di layar — anjungan
    memegang daftar layanan di memori dan bisa saja masih memegang daftar
    lama beberapa detik sesudah admin menambahkan anak pertama.
    """
    konsultasi = next(
        k for k in master_service.list_categories() if k.code == "KONSULTASI"
    )
    with pytest.raises(BusinessRuleError, match="kelompok"):
        reg_queue.create_queue(konsultasi.id)


def test_daun_menerbitkan_nomor_dengan_prefixnya_sendiri(reg_queue, master_service):
    restoran = next(
        k for k in master_service.list_categories() if k.code == "RESTORAN"
    )
    nomor = reg_queue.create_queue(restoran.id)
    assert nomor.queue_number == "RS-001"


def test_kelompok_kembali_menerbitkan_nomor_bila_isinya_kosong(
    reg_queue, admin_lain
):
    """
    Kelompok yang seluruh anaknya dinonaktifkan berubah jadi layanan biasa.

    Jauh lebih baik daripada kartu yang membuka daftar kosong di depan
    pengunjung yang sudah berdiri di sana.
    """
    semua = admin_lain.list_categories()
    pbjt = next(k for k in semua if k.code == "PBJT")
    for anak in [k for k in semua if k.parent_id == pbjt.id]:
        admin_lain.set_category_status(anak.id, False)

    nomor = reg_queue.create_queue(pbjt.id)
    assert nomor.queue_number.startswith("PJ-")


def test_menonaktifkan_kelompok_ikut_menonaktifkan_isinya(master_service):
    """
    Kalau tidak, PBB dan PKB naik jadi kartu tingkat teratas di anjungan —
    persis kebalikan dari yang diminta admin saat menutup Konsultasi.
    """
    konsultasi = next(
        k for k in master_service.list_categories() if k.code == "KONSULTASI"
    )
    master_service.set_category_status(konsultasi.id, False)

    aktif = {k.code for k in master_service.list_categories(only_active=True)}
    assert aktif == {"PENGADUAN", "INFORMASI"}

    master_service.set_category_status(konsultasi.id, True)
    aktif = {k.code for k in master_service.list_categories(only_active=True)}
    assert {"PBB", "PBJT", "HIBURAN"} <= aktif


def test_kelompok_tidak_dapat_dihapus_selama_masih_berisi(master_service):
    pbjt = next(k for k in master_service.list_categories() if k.code == "PBJT")
    with pytest.raises(BusinessRuleError, match="menaungi"):
        master_service.delete_category(pbjt.id)


def test_kelompok_tidak_diperingatkan_sebagai_layanan_tanpa_loket(master_service):
    """
    Kelompok tidak pernah punya antrian yang bisa terlantar.

    Memperingatkannya hanya akan mengubur peringatan yang sungguhan.
    """
    loket = master_service.list_counters()[0]
    daun = [k for k in master_service.list_categories(only_leaf=True)]
    master_service.set_counter_categories(loket.id, [daun[0].id])
    for lain in master_service.list_counters()[1:]:
        master_service.set_counter_categories(lain.id, [daun[0].id])

    yatim = {k.code for k in master_service.layanan_tanpa_loket()}
    assert "KONSULTASI" not in yatim
    assert "PBJT" not in yatim


# ---------------------------------------------------------------------
# Perubahan susunan oleh admin
# ---------------------------------------------------------------------

def test_menolak_menu_lebih_dari_tiga_tingkat(master_service):
    """Pengunjung yang berdiri tersesat sebelum sampai ke nomornya."""
    restoran = next(
        k for k in master_service.list_categories() if k.code == "RESTORAN"
    )
    with pytest.raises(ValidationError, match="tingkat"):
        master_service.create_category(
            code="RESTORAN-KECIL",
            name="Restoran Kecil",
            # Prefix yang belum dipakai siapa pun: yang harus ditolak di
            # sini adalah kedalaman menunya, bukan prefix yang kembar.
            prefix="ZX",
            parent_id=restoran.id,
        )


def test_menolak_induk_yang_berputar(master_service):
    """Konsultasi di bawah PBJT membuat menu berputar tanpa ujung."""
    semua = master_service.list_categories()
    konsultasi = next(k for k in semua if k.code == "KONSULTASI")
    pbjt = next(k for k in semua if k.code == "PBJT")

    with pytest.raises(ValidationError, match="DI BAWAH"):
        master_service.update_category(
            konsultasi.id, name=konsultasi.name, parent_id=pbjt.id
        )


def test_induk_tidak_berubah_bila_tidak_disebut(master_service):
    """
    None berarti "pindahkan ke menu utama", jadi tidak boleh jadi bawaan.

    Seluruh pemanggil lama update_category tidak menyebut induk sama
    sekali, dan tidak satu pun bermaksud mencabut PBB dari Konsultasi.
    """
    pbb = next(k for k in master_service.list_categories() if k.code == "PBB")
    sesudah = master_service.update_category(pbb.id, name="PBB P2")
    assert sesudah.parent_id == pbb.parent_id


def test_urutan_bergeser_di_dalam_kelompoknya_saja(master_service):
    """
    PBB tidak boleh naik melewati Konsultasi menjadi kartu tingkat teratas.

    Pindah kelompok adalah perbuatan lain, lewat kolom Induk.
    """
    semua = master_service.list_categories()
    pkb = next(k for k in semua if k.code == "PKB")
    master_service.pindahkan_category(pkb.id, naik=True)

    sesudah = master_service.list_categories()
    anak = [
        k.code
        for k in sesudah
        if k.parent_id == pkb.parent_id
    ]
    assert anak == ["PKB", "PBB", "PAT", "REKLAME", "PBJT"]
    assert [k.code for k in sesudah if k.level == 0] == [
        "KONSULTASI",
        "PENGADUAN",
        "INFORMASI",
    ]


def test_baris_pertama_kelompok_tidak_dapat_naik(master_service):
    pbb = next(k for k in master_service.list_categories() if k.code == "PBB")
    with pytest.raises(BusinessRuleError, match="teratas"):
        master_service.pindahkan_category(pbb.id, naik=True)
