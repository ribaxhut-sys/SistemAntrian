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
from app.services.queue_service import QueueService

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


# ---------------------------------------------------------------------
# Anjungan
# ---------------------------------------------------------------------

@pytest.fixture
def kios_bertingkat(auth, antrian_siap):
    auth.logout()
    auth.mulai_sesi_kios()
    return QueueService(auth)


@pytest.fixture
def anjungan(qtbot, kios_bertingkat, auth):
    """Anjungan tanpa timer, supaya test mengendalikan waktunya sendiri."""
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.services.sound_service import NullSoundPlayer
    from app.ui.kiosk.kiosk_page import KioskPage

    halaman = KioskPage(
        kios_bertingkat,
        MasterDataService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
    )
    qtbot.addWidget(halaman)
    halaman.papan.hentikan()
    halaman._penghitung.stop()
    halaman._pemeriksa_layanan.stop()
    return halaman


def _nama_kartu(halaman) -> list[str]:
    from PySide6.QtWidgets import QLabel

    return [
        btn.findChild(QLabel, "namaLayanan").text() for btn in halaman.kartu_kisi
    ]


def _kembali_tampak(halaman) -> bool:
    """
    Apakah tombol kembali sedang dipasang.

    `isVisible()` tidak dipakai: halaman uji tidak pernah ditampilkan,
    sehingga seluruh anaknya "tidak terlihat" tanpa peduli disembunyikan
    atau tidak. `isHidden()` menjawab yang benar-benar ditanya — apakah
    widget-nya sendiri yang disembunyikan.
    """
    return not halaman.tombol_kembali.isHidden()


def _kartu(halaman, nama: str):
    from PySide6.QtWidgets import QLabel

    for btn in halaman.kartu_kisi:
        if btn.findChild(QLabel, "namaLayanan").text() == nama:
            return btn
    raise AssertionError(f"kartu {nama!r} tidak ada di layar: {_nama_kartu(halaman)}")


def test_menu_utama_hanya_tingkat_teratas(anjungan):
    """PBB tidak boleh ikut berjajar di menu utama bersama Konsultasi."""
    assert _nama_kartu(anjungan) == ["Konsultasi", "Pengaduan", "Informasi"]


def test_menu_utama_tanpa_tombol_kembali(anjungan):
    """Tidak ada tempat untuk pulang dari menu utama."""
    assert not _kembali_tampak(anjungan)


def test_menyentuh_konsultasi_membuka_isinya(anjungan):
    _kartu(anjungan, "Konsultasi").click()
    assert _nama_kartu(anjungan) == ["PBB", "PKB", "PAT", "Reklame", "PBJT", "KEMBALI"]
    assert _kembali_tampak(anjungan)


def test_menyentuh_pbjt_membuka_tingkat_ketiga(anjungan):
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBJT").click()
    assert _nama_kartu(anjungan) == ["Restoran", "Parkir", "Hotel", "Hiburan", "KEMBALI"]
    assert _kembali_tampak(anjungan)


def test_kembali_berdiri_di_kisi_seukuran_submenu(anjungan, qtbot):
    """
    KEMBALI adalah kartu, bukan pil di baris petunjuk.

    Lima anak plus kembali = enam kartu: 3+3 seukuran menu utama, bukan
    enam kolom sempit. Warnanya abu, bukan toska, supaya tidak tertukar
    sebagai jenis layanan.
    """
    from app.ui.kiosk.kiosk_page import LEBAR_TOMBOL_MAKS
    from app.ui.style import DISPLAY_KIOS_KEMBALI

    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()
    lebar_utama = {btn.width() for btn in anjungan.kartu_kisi}

    _kartu(anjungan, "Konsultasi").click()
    anjungan.kisi.activate()

    assert "KEMBALI" in _nama_kartu(anjungan)
    kembali = _kartu(anjungan, "KEMBALI")
    assert kembali is anjungan.tombol_kembali
    assert kembali.objectName() == "tombolKembaliKios"
    assert DISPLAY_KIOS_KEMBALI in kembali.styleSheet()
    assert anjungan._kolom_terpakai == 3
    assert len(anjungan.kartu_kisi) == 6
    atas = sorted(anjungan.kartu_kisi, key=lambda b: (b.y(), b.x()))[:3]
    assert {btn.width() for btn in atas} == lebar_utama
    assert kembali.width() == next(iter(lebar_utama))
    assert {btn.height() for btn in anjungan.kartu_kisi} == {kembali.height()}


def test_tulisan_kembali_berwarna_merah(anjungan, qtbot):
    """
    Tulisan KEMBALI merah, juga bila kartunya lebih pendek dari 120 px.

    Stylesheet global `QWidget { color }` mengalahkan warna pada tombol.
    Yang diuji adalah warna di label nama, tempat huruf itu digambar.
    """
    from PySide6.QtWidgets import QLabel

    from app.ui.style import DISPLAY_KIOS_KEMBALI_TEKS

    anjungan.resize(1280, 720)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()

    _kartu(anjungan, "Konsultasi").click()
    anjungan.kisi.activate()
    qtbot.wait(50)

    kembali = _kartu(anjungan, "KEMBALI")
    css_tombol = kembali.styleSheet()
    css_nama = kembali.findChild(QLabel, "namaLayanan").styleSheet()
    assert DISPLAY_KIOS_KEMBALI_TEKS in css_tombol
    assert DISPLAY_KIOS_KEMBALI_TEKS in css_nama


def test_submenu_mengisi_kisi_pada_jendela_biasa(anjungan, qtbot):
    """
    Di jendela 1280×720, dua baris mengisi kisi, bukan pil di tengah.

    Panel informasi tidak ikut memanjang; sisa ruang di dalam kisi
    itulah yang harus dipakai kartu.
    """
    from app.ui.kiosk.kiosk_page import CELAH_BARIS_KELOMPOK, MARGIN_KISI

    anjungan.resize(1280, 720)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()
    qtbot.wait(50)
    panel_ambil = anjungan.panel_ambil.height()

    _kartu(anjungan, "Konsultasi").click()
    anjungan.kisi.activate()
    qtbot.wait(50)

    assert anjungan.panel_ambil.height() == panel_ambil
    tinggi = next(btn.height() for btn in anjungan.kartu_kisi)
    assert {btn.height() for btn in anjungan.kartu_kisi} == {tinggi}
    assert anjungan._kolom_terpakai == 3
    sisa = anjungan.halaman_pilihan.height() - 2 * tinggi
    assert sisa <= 2 * MARGIN_KISI + CELAH_BARIS_KELOMPOK + 24


def test_kembali_naik_satu_tingkat_saja(anjungan):
    """Dari PBJT pulangnya ke Konsultasi, bukan langsung ke menu utama."""
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBJT").click()
    anjungan.tombol_kembali.click()
    assert "PBB" in _nama_kartu(anjungan)

    anjungan.tombol_kembali.click()
    assert _nama_kartu(anjungan) == ["Konsultasi", "Pengaduan", "Informasi"]
    assert not _kembali_tampak(anjungan)


def test_layar_konfirmasi_menyembunyikan_tombol_kembali(anjungan):
    """
    Dua jalan mundur berdampingan membingungkan, dan yang satu menipu.

    Baris pil berdiri di LUAR tumpukan, jadi tombol kembali tetap tampak
    di sebelah BATAL bila tidak disembunyikan — dan menekannya memulangkan
    menu di belakang layar konfirmasi yang masih menunggu jawaban.
    """
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBB").click()
    assert not _kembali_tampak(anjungan)

    anjungan._batal_konfirmasi()
    assert _kembali_tampak(anjungan)


def test_kartu_kelompok_memakai_tanda_submenu(anjungan):
    """
    Kartu anjungan tidak memajang A/B/C. Yang membuka submenu memakai ">".

    Prefix tiket tetap ada di data dan di layar konfirmasi; di kartu
    sentuh ia hanya mengulang nama (PB di atas PBB) atau menjanjikan
    nomor pada kelompok yang tidak pernah menerbitkannya.
    """
    from PySide6.QtWidgets import QLabel

    from app.ui.kiosk.kiosk_page import TANDA_KELOMPOK

    konsultasi = _kartu(anjungan, "Konsultasi")
    assert konsultasi.findChild(QLabel, "prefixLayanan") is None
    tanda = konsultasi.findChild(QLabel, "tandaSubmenu")
    assert tanda is not None
    assert tanda.text() == TANDA_KELOMPOK

    pengaduan = _kartu(anjungan, "Pengaduan")
    assert pengaduan.findChild(QLabel, "tandaSubmenu") is None
    assert pengaduan.findChild(QLabel, "prefixLayanan") is None

    _kartu(anjungan, "Konsultasi").click()
    pbb = _kartu(anjungan, "PBB")
    assert pbb.findChild(QLabel, "tandaSubmenu") is None
    assert pbb.findChild(QLabel, "namaLayanan").text() == "PBB"

    pbjt = _kartu(anjungan, "PBJT")
    assert pbjt.findChild(QLabel, "tandaSubmenu").text() == TANDA_KELOMPOK


def test_kelompok_tidak_membuka_layar_konfirmasi(anjungan):
    _kartu(anjungan, "Konsultasi").click()
    assert anjungan.tumpukan.currentWidget() is anjungan.halaman_pilihan
    assert anjungan._kategori_terpilih is None


def test_daun_membuka_layar_konfirmasi(anjungan):
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBB").click()
    assert anjungan.tumpukan.currentWidget() is anjungan.halaman_konfirmasi
    assert anjungan.label_konfirmasi_kode.text() == "PB"
    assert anjungan.label_konfirmasi_layanan.text() == "PBB"


def test_batal_kembali_ke_daftar_kelompok(anjungan):
    """Yang membatalkan biasanya hendak memilih yang di sebelahnya."""
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBB").click()
    anjungan._batal_konfirmasi()
    assert "PKB" in _nama_kartu(anjungan)


def test_anjungan_pulang_sendiri_setelah_ditinggal(anjungan):
    """
    Pengunjung yang berbalik pergi tidak boleh meninggalkan anjungan
    tersangkut di dalam menu untuk orang berikutnya.
    """
    _kartu(anjungan, "Konsultasi").click()
    assert anjungan._pemulang.isActive()

    anjungan._pulang()
    assert _nama_kartu(anjungan) == ["Konsultasi", "Pengaduan", "Informasi"]
    assert not anjungan._pemulang.isActive()


def test_nomor_terbit_mengembalikan_anjungan_ke_menu_utama(anjungan):
    """
    Orang berikutnya harus menemukan layar seperti semula.

    Kisinya pulang begitu nomornya terbit, BUKAN menunggu kartu nomor
    hilang dari papan sepuluh detik kemudian. Sepanjang sepuluh detik itu
    orang berikutnya sudah berdiri di depan mesin, dan menu yang dilihatnya
    bukan menu utama.
    """
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBB").click()
    anjungan._konfirmasi_ambil()

    assert _nama_kartu(anjungan) == ["Konsultasi", "Pengaduan", "Informasi"]


def test_pulang_seketika_tidak_menghapus_kartu_nomor(anjungan):
    """
    Kepulangan kisi tidak boleh menyeret papan ikut dibersihkan.

    `_pulang()` membebaskan panel papan ke sambutan bila tidak ada kartu
    nomor yang sedang tampil. Dipanggil terlalu dini — sebelum kartu nomor
    dipasang — sambutan itu menyembul sekejap di antara keduanya, dan
    kedipannya terlihat oleh orang yang sedang menunggu nomornya muncul.
    """
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBB").click()

    dibebaskan: list = []
    asli = anjungan.papan.tampilkan_info_kios
    anjungan.papan.tampilkan_info_kios = lambda *a, **k: dibebaskan.append(a)
    try:
        anjungan._konfirmasi_ambil()
    finally:
        anjungan.papan.tampilkan_info_kios = asli

    assert dibebaskan == [], "papan dibebaskan padahal kartu nomor baru terbit"
    assert anjungan._penghapus_hasil.isActive()


def test_kartu_kembali_tetap_hidup_selama_jeda(anjungan):
    """
    Jeda pengambilan nomor tidak boleh mengurung pengunjung di dalam menu.

    Kartu layanan memang dimatikan — nomornya belum boleh terbit — tetapi
    jalan pulangnya harus tetap dapat disentuh.

    Jeda di sini milik pengunjung SEBELUMNYA: sejak nomor terbit kisinya
    langsung pulang ke menu utama, sehingga yang masuk ke dalam kelompok
    selagi jeda berjalan adalah orang berikutnya.
    """
    _kartu(anjungan, "Pengaduan").click()
    anjungan._konfirmasi_ambil()

    _kartu(anjungan, "Konsultasi").click()
    anjungan._perbarui_jeda()

    assert not _kartu(anjungan, "PBB").isEnabled()
    assert anjungan.tombol_kembali.isEnabled()
    assert _kembali_tampak(anjungan)


def test_jalur_dipangkas_bila_kelompoknya_hilang(anjungan, admin_lain):
    """
    Admin boleh menonaktifkan kelompok tepat saat ada orang di dalamnya.

    Tanpa pemangkasan, layarnya menjadi benar-benar kosong: tidak ada satu
    kartu pun, dan tidak ada jalan keluar.
    """
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBJT").click()
    assert len(anjungan._jalur) == 2

    pbjt = next(k for k in admin_lain.list_categories() if k.code == "PBJT")
    admin_lain.set_category_status(pbjt.id, False)
    anjungan.muat_ulang()

    assert [langkah.code for langkah in anjungan._jalur] == ["KONSULTASI"]
    assert "PBB" in _nama_kartu(anjungan)


def test_kelompok_kosong_tetap_menyisakan_jalan_keluar(anjungan, admin_lain):
    """Kartu kembali harus ada bahkan saat isinya habis dinonaktifkan."""
    semua = admin_lain.list_categories()
    pbjt = next(k for k in semua if k.code == "PBJT")
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBJT").click()

    for anak in [k for k in semua if k.parent_id == pbjt.id]:
        admin_lain.set_category_status(anak.id, False)
    # Jalur SENGAJA tidak dipangkas lewat muat_ulang di sini: yang diuji
    # adalah keadaan kisi yang isinya kosong, bukan pemangkasan jalurnya.
    anjungan.kategori = [
        k for k in admin_lain.list_categories(only_active=True)
    ]
    anjungan._susun_tombol()

    assert _kembali_tampak(anjungan)


def test_menu_utama_memakai_kartu_terbesar(anjungan, qtbot):
    """
    Menu utama tidak boleh membayar apa pun untuk menu di bawahnya.

    Kartunya sudah mentok pada batas lebar kartu, dan batas itulah yang
    harus tetap didapatnya berapa pun padatnya isi kelompok — pengunjung
    yang berdiri di depan mesin pertama kali melihat layar INI.
    """
    from app.ui.kiosk.kiosk_page import LEBAR_TOMBOL_MAKS

    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()

    assert {btn.width() for btn in anjungan.kartu_kisi} == {LEBAR_TOMBOL_MAKS}


def test_tombol_anjungan_tidak_menerima_fokus(anjungan):
    """
    Sentuhan tidak boleh meninggalkan sorotan native pada kartu berikutnya.

    Tombol KEMBALI disembunyikan di tengah klik. Tanpa NoFocus, Qt
    menyerahkan fokus ke kartu Konsultasi yang baru disusun — dan kartu
    itu tampak berubah tanpa disentuh.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    assert anjungan.tombol_kembali.objectName() == "tombolKembaliKios"
    for btn in anjungan.findChildren(QPushButton):
        assert btn.focusPolicy() == Qt.FocusPolicy.NoFocus, btn.text()
        assert not btn.property("variant")
    for btn in anjungan.kartu_kisi:
        assert btn.objectName() == "kartuKios"


def test_kembali_mengembalikan_ukuran_menu_utama(anjungan, qtbot):
    """
    Pulang dari Konsultasi harus mengembalikan kartu seperti semula.

    Tes ukuran menu utama di atas hanya melihat gambar pertama. Kartu yang
    tetap kecil setelah kisinya disusun ulang terbaca sebagai tombol yang
    berubah.
    """
    from app.ui.kiosk.kiosk_page import LEBAR_TOMBOL_MAKS

    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()
    ukuran_semula = [(btn.width(), btn.height()) for btn in anjungan.kartu_kisi]

    _kartu(anjungan, "Konsultasi").click()
    anjungan.tombol_kembali.click()
    anjungan.kisi.activate()

    assert _nama_kartu(anjungan) == ["Konsultasi", "Pengaduan", "Informasi"]
    assert {btn.width() for btn in anjungan.kartu_kisi} == {LEBAR_TOMBOL_MAKS}
    assert [
        (btn.width(), btn.height()) for btn in anjungan.kartu_kisi
    ] == ukuran_semula
    assert not anjungan.tombol_kembali.isDown()
    assert anjungan.focusWidget() not in anjungan.kartu_kisi


def test_kartu_bukan_pil_pipih_setelah_ganti_menu(anjungan, qtbot):
    """
    Kartu tidak boleh kehilangan tingginya saat kisi disusun ulang.

    Bugnya: tinggi kisi dihitung dari `panel - halaman_pilihan`. Saat
    kartu lama dihapus, halaman itu mengerut, selisihnya membengkak, dan
    kartu baru — menu utama maupun isi Konsultasi — lahir sebagai pil
    pipih di tengah panel yang masih lapang.
    """
    from app.ui.kiosk.kiosk_page import MARGIN_KISI, TINGGI_TOMBOL_MIN

    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()

    def ukuran() -> list[tuple[int, int]]:
        return [(btn.width(), btn.height()) for btn in anjungan.kartu_kisi]

    awal = ukuran()
    assert all(tinggi >= TINGGI_TOMBOL_MIN for _, tinggi in awal)
    # Ruang kosong di sekeliling kartu hanyalah margin kisi, bukan sisa
    # panel yang tidak jadi dipakai.
    assert anjungan.halaman_pilihan.height() - awal[0][1] <= 2 * MARGIN_KISI + 24

    _kartu(anjungan, "Konsultasi").click()
    anjungan.kisi.activate()
    dalam = ukuran()
    # Dua baris di panel yang sama: kartu boleh lebih pendek daripada menu
    # utama, tetapi harus mengisi kisi, bukan pil di tengah bidang kosong.
    assert all(tinggi > 0 for _, tinggi in dalam)
    assert {tinggi for _, tinggi in dalam} == {dalam[0][1]}
    assert (
        anjungan.halaman_pilihan.height() - 2 * dalam[0][1]
        <= 2 * MARGIN_KISI + 16 + 24
    )

    anjungan.tombol_kembali.click()
    anjungan.kisi.activate()
    qtbot.wait(50)
    assert ukuran() == awal


def test_konsultasi_seukuran_menu_utama(anjungan, qtbot):
    """
    Lima anak Konsultasi 3+2: lebar menu utama, tinggi menyesuaikan panel.

    Menyusunnya lima dalam satu baris membuat tiap kartu ~324 px.
    Menyalin tinggi menu utama ke dua baris merampas papan informasi.
    """
    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()
    qtbot.wait(50)
    lebar_utama = {btn.width() for btn in anjungan.kartu_kisi}
    tinggi_utama = next(btn.height() for btn in anjungan.kartu_kisi)
    panel_ambil = anjungan.panel_ambil.height()

    _kartu(anjungan, "Konsultasi").click()
    anjungan.kisi.activate()
    qtbot.wait(50)

    assert anjungan._kolom_terpakai == 3, anjungan._kolom_terpakai
    assert _nama_kartu(anjungan)[:5] == ["PBB", "PKB", "PAT", "Reklame", "PBJT"]
    assert _nama_kartu(anjungan)[-1] == "KEMBALI"
    atas = sorted(anjungan.kartu_kisi, key=lambda b: (b.y(), b.x()))[:3]
    assert {btn.width() for btn in atas} == lebar_utama
    tinggi_dalam = {btn.height() for btn in anjungan.kartu_kisi}
    assert len(tinggi_dalam) == 1
    assert next(iter(tinggi_dalam)) <= tinggi_utama
    assert anjungan.panel_ambil.height() == panel_ambil


def test_kartu_tahan_kisi_mengerut_setelah_video(anjungan, qtbot):
    """
    Kisi yang mengerut (video layanan berganti) tidak boleh mengecilkan kartu.

    Tes lain mengukur segera setelah klik, sebelum putaran tata letak
    berikutnya. Di mesin anjungan, video Konsultasi 1920×540 merampas
    tinggi papan sesudah itu, halaman pilihan sempat 80 px, dan kartu
    dihitung ulang jadi pil. Itulah yang terlihat di layar sungguhan.
    """
    from app.ui.kiosk.kiosk_page import LEBAR_TOMBOL_MIN, TINGGI_TOMBOL_MIN
    from PySide6.QtWidgets import QSizePolicy

    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()
    awal = [(btn.width(), btn.height()) for btn in anjungan.kartu_kisi]
    assert awal[0][0] > LEBAR_TOMBOL_MIN
    assert awal[0][1] > TINGGI_TOMBOL_MIN

    _kartu(anjungan, "Konsultasi").click()
    anjungan.kisi.activate()
    qtbot.wait(0)
    dalam = [(btn.width(), btn.height()) for btn in anjungan.kartu_kisi]

    halaman = anjungan.halaman_pilihan
    kebijakan = halaman.sizePolicy()
    halaman.setFixedHeight(80)
    anjungan._sesuaikan_ukuran_tombol()

    setelah_mengerut = [(btn.width(), btn.height()) for btn in anjungan.kartu_kisi]
    assert setelah_mengerut == dalam
    atas = sorted(anjungan.kartu_kisi, key=lambda b: (b.y(), b.x()))[:3]
    assert {btn.width() for btn in atas} == {awal[0][0]}

    halaman.setMinimumHeight(0)
    halaman.setMaximumHeight((1 << 24) - 1)
    halaman.setSizePolicy(kebijakan)

    anjungan.tombol_kembali.click()
    anjungan.kisi.activate()
    halaman.setFixedHeight(80)
    anjungan._sesuaikan_ukuran_tombol()

    pulang = [(btn.width(), btn.height()) for btn in anjungan.kartu_kisi]
    assert pulang == awal

    halaman.setMinimumHeight(0)
    halaman.setMaximumHeight((1 << 24) - 1)
    halaman.setSizePolicy(kebijakan)


def test_kembali_tidak_mengecilkan_huruf_kartu(anjungan, qtbot):
    """
    Nama menu utama harus sama sebelum dan sesudah masuk kelompok.

    Tes lebar kartu tidak cukup: huruf di dalamnya bisa menyusut diam-diam
    setelah kisi disusun ulang.
    """
    from PySide6.QtWidgets import QLabel

    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()

    def ukuran_nama() -> list[int]:
        import re

        hasil = []
        for btn in anjungan.kartu_kisi:
            css = btn.findChild(QLabel, "namaLayanan").styleSheet()
            hasil.append(int(re.search(r"font-size: (\d+)px", css).group(1)))
        return hasil

    semula = ukuran_nama()

    _kartu(anjungan, "Konsultasi").click()
    anjungan.tombol_kembali.click()
    anjungan.kisi.activate()
    qtbot.wait(300)

    assert ukuran_nama() == semula


def test_fullscreen_restore_mengembalikan_ukuran_kartu(anjungan, qtbot):
    """
    F11 penuh lalu restore tidak boleh meninggalkan kartu dalam ukuran transisi.

    Qt mengirim beberapa Resize dengan kisi yang sempat mengerut.
    Menghitung di setiap langkah membuat huruf dan tinggi kartu tertinggal
    di angka yang salah sesudah jendela kembali ke ukuran semula.
    """
    import re

    from PySide6.QtWidgets import QLabel

    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()
    qtbot.wait(20)

    def snapshot() -> list[tuple[int, int, int]]:
        hasil = []
        for btn in anjungan.kartu_kisi:
            css = btn.findChild(QLabel, "namaLayanan").styleSheet()
            huruf = int(re.search(r"font-size: (\d+)px", css).group(1))
            hasil.append((btn.width(), btn.height(), huruf))
        return hasil

    semula = snapshot()
    assert all(tinggi > 120 for _, tinggi, _ in semula)

    anjungan.resize(1100, 700)
    qtbot.wait(20)
    anjungan._sesuaikan_setelah_ubah_jendela()

    anjungan.resize(1920, 1080)
    qtbot.wait(20)
    anjungan._sesuaikan_setelah_ubah_jendela()
    anjungan.kisi.activate()

    assert snapshot() == semula


def test_tombol_kembali_tidak_memakan_tinggi_kartu(anjungan, qtbot):
    """
    Tempat tombol kembali tidak boleh mengubah tinggi baris pil.

    Baris pil berdiri TEPAT di atas kisi. Tempatnya dipesan di setiap
    tingkat supaya tinggi chrome panel — dan karena itu jatah kartu —
    tidak berubah hanya karena tombol KEMBALI muncul.
    """
    anjungan.resize(1920, 1080)
    anjungan.show()
    qtbot.waitExposed(anjungan)
    anjungan._susun_tombol()
    anjungan.kisi.activate()
    panel_ambil = anjungan.panel_ambil.height()

    _kartu(anjungan, "Konsultasi").click()
    anjungan.kisi.activate()

    assert anjungan.panel_ambil.height() == panel_ambil
    assert (
        anjungan.wadah_kembali.height()
        <= anjungan.label_petunjuk.sizeHint().height()
    )


def test_pulang_otomatis_tidak_menghapus_kartu_nomor(anjungan):
    """
    Hitungan pulang tidak boleh menyapu nomor yang baru saja terbit.

    Pengunjung menyentuh Konsultasi lalu PBB — hitungan 25 detik berjalan.
    Bila nomornya terbit pada detik ke-20, hitungan itu masih akan meletus
    lima detik kemudian, tepat ketika pemilik nomor sedang memfotonya.
    """
    _kartu(anjungan, "Konsultasi").click()
    _kartu(anjungan, "PBB").click()
    anjungan._konfirmasi_ambil()

    assert not anjungan._pemulang.isActive()
    assert anjungan._penghapus_hasil.isActive()

    # Sekalipun hitungannya entah bagaimana tetap meletus, papan tidak
    # boleh ikut dibersihkan selama kartu nomor masih tampil.
    dipanggil: list = []
    asli = anjungan.papan.tampilkan_info_kios
    anjungan.papan.tampilkan_info_kios = lambda *a, **k: dipanggil.append(a)
    try:
        anjungan._jalur = [
            k for k in anjungan.kategori if k.code == "KONSULTASI"
        ]
        anjungan._pulang()
    finally:
        anjungan.papan.tampilkan_info_kios = asli

    assert dipanggil == [], "papan dibersihkan padahal kartu nomor masih tampil"
    assert anjungan.label_ajakan.text() == "NOMOR ANDA SUDAH TERBIT"


def test_totem_sempit_submenu_tidak_keluar_layar(qtbot, kios_bertingkat, auth):
    """
    Submenu totem pada skala Windows 150% tidak boleh terpotong di kanan.

    Di dalam kelompok kisinya tiga kolom. Pada lebar 720 px, tiga kartu
    selebar minimumnya beserta celahnya menuntut 640 px dari 624 yang ada,
    dan kartu ketiga dahulu terpotong di tepi kanan layar.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.services.sound_service import NullSoundPlayer
    from app.ui.kiosk.kiosk_page import KioskPage

    halaman = KioskPage(
        kios_bertingkat,
        MasterDataService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        totem=True,
    )
    qtbot.addWidget(halaman)
    halaman.papan.hentikan()
    halaman._penghitung.stop()
    halaman._pemeriksa_layanan.stop()
    halaman.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    halaman.resize(720, 1280)
    halaman.show()
    for _ in range(3):
        QApplication.processEvents()

    _kartu(halaman, "Konsultasi").click()
    for _ in range(3):
        QApplication.processEvents()

    assert halaman.width() == 720
    kanan = halaman.halaman_pilihan.width()
    assert "PBB" in _nama_kartu(halaman)
    for kartu in halaman.kartu_kisi:
        if kartu.isVisible():
            assert kartu.geometry().right() <= kanan, (kartu.geometry().getRect(), kanan)
