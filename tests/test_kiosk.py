"""
Test dua mesin publik: anjungan ambil nomor dan layar antrian.

Keduanya berjalan TANPA login di komputer yang menghadap publik dan tidak
diawasi. Yang dikunci di sini terutama batas kewenangannya: anjungan boleh
menampilkan papan nomor dan menerbitkan nomor, layar antrian hanya boleh
melihat, dan keduanya tidak boleh apa pun selain itu.
"""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QFrame, QStatusBar

from app.core.errors import AuthorizationError, BusinessRuleError
from app.models import UserRole
from app.services.permissions import Permission, permissions_for
from app.services.queue_service import QueueService
from app.services.settings_service import SettingsService


@pytest.fixture
def kios(auth, antrian_siap):
    """QueueService dengan sesi kios, tanpa login."""
    auth.logout()
    auth.mulai_sesi_kios()
    return QueueService(auth)


# ---------------------------------------------------------------------
# Sesi tanpa login
# ---------------------------------------------------------------------

def test_kios_berjalan_tanpa_login(auth, antrian_siap):
    """Kata sandi tidak boleh perlu disimpan di komputer publik."""
    auth.logout()

    sesi = auth.mulai_sesi_kios()

    assert auth.is_authenticated
    assert sesi.kios
    assert sesi.role is UserRole.KIOSK


def test_sesi_kios_bukan_milik_orang(auth, antrian_siap):
    """
    Tidak ada akun di baliknya, sehingga audit mencatatnya sebagai NULL.

    Kolom user_id pada audit_log memang dirancang boleh kosong untuk
    aktivitas yang tidak berpemilik.
    """
    auth.logout()

    sesi = auth.mulai_sesi_kios()

    assert sesi.user_id is None


def test_sesi_petugas_tetap_punya_pemilik(cro_queue, auth):
    """Penjaga agar user_id yang boleh kosong tidak diam-diam merembet."""
    assert auth.require_session().user_id is not None
    assert not auth.require_session().kios


# ---------------------------------------------------------------------
# Batas kewenangan
# ---------------------------------------------------------------------

def test_kios_boleh_menerbitkan_nomor(kios, antrian_siap):
    nomor = kios.create_queue(antrian_siap["kategori"]["A"])

    assert nomor.queue_number == "A-001"


def test_kios_boleh_melihat_papan_nomor(kios):
    keadaan = kios.display_state()

    assert keadaan.terkini is None


@pytest.mark.parametrize(
    "permission",
    [
        Permission.QUEUE_CALL,
        Permission.QUEUE_SERVE,
        Permission.QUEUE_COMPLETE,
        Permission.QUEUE_CANCEL,
        Permission.QUEUE_NO_SHOW,
        Permission.QUEUE_VIEW,
        Permission.USER_MANAGE,
        Permission.MASTER_MANAGE,
        Permission.CONFIG_MANAGE,
        Permission.BACKUP_MANAGE,
        Permission.REPORT_VIEW,
        Permission.SURVEY_VIEW,
        Permission.SURVEY_SUBMIT,
    ],
)
def test_kios_tidak_berwenang_atas_hal_lain(permission):
    """
    Komputernya berdiri di ruang publik tanpa diawasi.

    Yang boleh hanya dua hal yang memang dikerjakan pengunjung sendiri.
    """
    assert permission not in permissions_for(UserRole.KIOSK)


def test_kios_hanya_punya_tiga_kewenangan():
    assert permissions_for(UserRole.KIOSK) == frozenset(
        {
            Permission.DISPLAY_VIEW,
            Permission.QUEUE_CREATE,
            Permission.TICKET_PRINT,
        }
    )


def test_kios_tidak_dapat_memanggil_antrian(kios, antrian_siap):
    kios.create_queue(antrian_siap["kategori"]["A"])

    with pytest.raises(AuthorizationError):
        kios.call_next(antrian_siap["loket"][0])


def test_kios_tidak_dapat_melihat_daftar_antrian(kios, antrian_siap):
    """Papan nomor cukup; daftar penuh bukan urusan pengunjung."""
    kios.create_queue(antrian_siap["kategori"]["A"])

    with pytest.raises(AuthorizationError):
        kios.list_today()


# ---------------------------------------------------------------------
# Jeda antar-pengambilan
# ---------------------------------------------------------------------

def test_nomor_kedua_ditahan_sejenak(kios, antrian_siap):
    """Satu orang menekan tombol berulang kali tidak boleh memenuhi antrian."""
    kios.create_queue(antrian_siap["kategori"]["A"])

    with pytest.raises(BusinessRuleError) as info:
        kios.create_queue(antrian_siap["kategori"]["A"])

    assert "tunggu" in info.value.user_message.lower()


def test_jeda_dapat_dimatikan_administrator(antrian_siap, admin_auth, auth):
    """Kantor yang ramai boleh mematikannya tanpa mengubah kode."""
    SettingsService(admin_auth).set("kiosk.cooldown_seconds", "0")

    auth.logout()
    auth.mulai_sesi_kios()
    layanan = QueueService(auth)

    a = layanan.create_queue(antrian_siap["kategori"]["A"])
    b = layanan.create_queue(antrian_siap["kategori"]["A"])

    assert (a.queue_number, b.queue_number) == ("A-001", "A-002")


def test_sisa_jeda_menyusut_setelah_nomor_terbit(kios, antrian_siap):
    assert kios.sisa_jeda_kios() == 0

    kios.create_queue(antrian_siap["kategori"]["A"])

    assert 0 < kios.sisa_jeda_kios() <= kios.jeda_kios_detik()


def test_petugas_pendaftaran_tidak_ikut_diperlambat(reg_queue, antrian_siap):
    """
    Meja pendaftaran melayani rombongan yang datang bersamaan.

    Jeda kios sengaja tidak berlaku bagi petugas; memperlambat meja resmi
    adalah akibat yang tidak diinginkan dari aturan yang ditujukan kepada
    pengunjung.
    """
    nomor = [
        reg_queue.create_queue(antrian_siap["kategori"]["A"]).queue_number
        for _ in range(3)
    ]

    assert nomor == ["A-001", "A-002", "A-003"]


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def test_nomor_dari_kios_tercatat_tanpa_pelaku(kios, antrian_siap):
    """
    Terbaca berbeda dari nomor yang diterbitkan petugas.

    Supervisor jadi dapat membedakan mana yang diambil pengunjung sendiri
    dan mana yang diterbitkan di meja pendaftaran.
    """
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    kios.create_queue(antrian_siap["kategori"]["A"])

    with session_scope() as session:
        baris = session.scalars(
            sa.select(AuditLog).where(AuditLog.action == "CREATE_QUEUE")
        ).all()

    assert len(baris) == 1
    assert baris[0].user_id is None


# ---------------------------------------------------------------------
# UI kios
# ---------------------------------------------------------------------

@pytest.fixture
def halaman_kios(qtbot, kios, auth):
    """Layar kios tanpa timer, supaya test mengendalikan waktunya."""
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.services.sound_service import NullSoundPlayer
    from app.ui.kiosk.kiosk_page import KioskPage

    halaman = KioskPage(
        kios,
        MasterDataService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
    )
    qtbot.addWidget(halaman)
    halaman.papan.hentikan()
    halaman._penghitung.stop()
    return halaman


def test_halaman_kios_membuat_tombol_jenis_layanan(halaman_kios):
    assert len(halaman_kios.tombol_layanan) == 3
    assert [c.prefix for c in halaman_kios.kategori] == ["A", "B", "C"]


def test_tulisan_tombol_layanan_berwarna_terang(halaman_kios):
    """Huruf A/B/C harus putih di atas tombol teal, bukan gelap dari stylesheet global."""
    from PySide6.QtWidgets import QLabel

    from app.ui.style import DISPLAY_KIOS_TOMBOL_TEKS

    for btn in halaman_kios.tombol_layanan:
        prefix = btn.findChild(QLabel, "prefixLayanan")
        nama = btn.findChild(QLabel, "namaLayanan")
        assert prefix is not None
        assert nama is not None
        assert DISPLAY_KIOS_TOMBOL_TEKS in prefix.styleSheet()
        assert DISPLAY_KIOS_TOMBOL_TEKS in nama.styleSheet()


def test_nama_layanan_tetap_tampil_pada_jendela_biasa(qtbot, halaman_kios):
    """
    Papan nomor huruf besar merebut tinggi jendela. Nama di bawah A/B/C
    tidak boleh ikut terpotong saat petugas menekan F11.
    """
    from PySide6.QtWidgets import QLabel

    halaman_kios.resize(1100, 700)
    halaman_kios.show()
    qtbot.waitExposed(halaman_kios)

    nama_tampil = []
    for btn in halaman_kios.tombol_layanan:
        label = btn.findChild(QLabel, "namaLayanan")
        assert label is not None
        assert label.text()
        assert btn.height() >= 80
        nama_tampil.append(label.text())

    assert nama_tampil == ["Konsultasi", "Pengaduan", "Informasi"]


def test_nama_layanan_tetap_tampil_pada_layar_penuh(qtbot, halaman_kios):
    """
    Kios dipasang layar penuh di monitor 1080p.

    Papan nomor tidak boleh ikut membesar sampai menelan panel ambil nomor;
    nama layanan di bawah A/B/C harus tetap muat seluruhnya.
    """
    from PySide6.QtWidgets import QLabel

    from app.ui.kiosk.kiosk_page import TINGGI_PANEL_AMBIL_MIN, TINGGI_TOMBOL_MIN

    halaman_kios.resize(1920, 1080)
    halaman_kios.show()
    qtbot.waitExposed(halaman_kios)

    panel = halaman_kios.findChild(QFrame, "panelAmbil")
    assert panel is not None
    assert panel.height() >= TINGGI_PANEL_AMBIL_MIN

    for btn in halaman_kios.tombol_layanan:
        label = btn.findChild(QLabel, "namaLayanan")
        assert label is not None
        assert btn.height() >= TINGGI_TOMBOL_MIN
        # QLabel memotong teksnya diam-diam bila tingginya kurang; yang
        # dijaga di sini adalah tinggi yang dibutuhkan pada lebar sekarang.
        assert label.height() >= label.heightForWidth(label.width())


def test_tombol_layanan_proporsional_pada_layar_penuh(qtbot, halaman_kios):
    """
    Tiga tombol A/B/C tidak boleh meregang jadi batang pipih selebar panel.

    Pada 1080p, Expanding tanpa batas lebar membuat tiap kartu ~600px
    lebar pada tinggi ~120px — terbaca sebagai pita, bukan tombol sentuh.
    """
    from app.ui.kiosk.kiosk_page import (
        CELAH_TOMBOL,
        LEBAR_TOMBOL_MAKS,
        TINGGI_TOMBOL_MAKS,
        TINGGI_TOMBOL_MIN,
    )

    halaman_kios.resize(1920, 1080)
    halaman_kios.show()
    qtbot.waitExposed(halaman_kios)
    halaman_kios._sesuaikan_ukuran_tombol()

    ukuran = {(btn.width(), btn.height()) for btn in halaman_kios.tombol_layanan}
    assert len(ukuran) == 1

    lebar, tinggi = next(iter(ukuran))
    assert TINGGI_TOMBOL_MIN <= tinggi <= TINGGI_TOMBOL_MAKS
    # Pada 1080p ruangnya cukup: lebar harus tepat angka yang diminta.
    assert lebar == LEBAR_TOMBOL_MAKS

    kotak = [btn.geometry() for btn in halaman_kios.tombol_layanan]
    for i, a in enumerate(kotak):
        for b in kotak[i + 1 :]:
            assert not a.intersects(b)

    urut = sorted(halaman_kios.tombol_layanan, key=lambda btn: btn.x())
    for kiri, kanan in zip(urut, urut[1:]):
        jarak = kanan.x() - (kiri.x() + kiri.width())
        assert jarak >= CELAH_TOMBOL


# ---------------------------------------------------------------------
# Kisi kartu menyesuaikan banyaknya layanan
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "jumlah, harapan",
    [
        (1, [1]),
        (2, [2]),
        (3, [3]),
        (4, [2, 2]),
        (5, [3, 2]),
        (6, [3, 3]),
        (7, [3, 2, 2]),
        (8, [3, 3, 2]),
        (9, [3, 3, 3]),
    ],
)
def test_baris_kisi_membagi_kartu_serata_mungkin(jumlah, harapan):
    """
    Empat layanan disusun 2×2 dan tujuh layanan 3+2+2, bukan 3+1 dan 3+3+1.

    Kartu yang sendirian di baris bawah terbaca sebagai kartu yang berbeda
    derajat, padahal semua jenis layanan setara.
    """
    from app.ui.kiosk.kiosk_page import baris_kisi

    assert baris_kisi(jumlah) == harapan


@pytest.fixture
def bikin_halaman_kios(qtbot, auth, master_service):
    """Layar kios dengan sekian jenis layanan aktif."""
    from app.services.master_data_service import MasterDataService
    from app.services.queue_service import QueueService
    from app.services.settings_service import SettingsService
    from app.services.sound_service import NullSoundPlayer
    from app.ui.kiosk.kiosk_page import KioskPage

    def bikin(jumlah: int, lebar: int = 1366, tinggi: int = 768):
        for nomor, huruf in enumerate("DEFG", start=4):
            if len(master_service.list_categories()) >= jumlah:
                break
            master_service.create_category(
                code=f"LAYANAN-{huruf}", name=f"Layanan {huruf}", prefix=huruf
            )
        for kategori in master_service.list_categories()[jumlah:]:
            master_service.set_category_status(kategori.id, False)

        auth.logout()
        auth.mulai_sesi_kios()
        halaman = KioskPage(
            QueueService(auth),
            MasterDataService(auth),
            SettingsService(auth),
            NullSoundPlayer(),
        )
        qtbot.addWidget(halaman)
        halaman.papan.hentikan()
        halaman._penghitung.stop()
        halaman.resize(lebar, tinggi)
        halaman.show()
        qtbot.waitExposed(halaman)
        halaman._sesuaikan_ukuran_tombol()
        return halaman

    return bikin


@pytest.mark.parametrize("jumlah", [1, 2, 3, 4, 5, 6, 7])
def test_kartu_tidak_pernah_meluber_keluar_layar(bikin_halaman_kios, jumlah):
    """
    Baris kartu paling bawah adalah bagian yang harus disentuh.

    Sempat panel meminta tinggi lebih daripada sisa layar, dan yang keluar
    dari tepi bawah justru baris itu — kartunya tidak mengecil, tetapi
    terpotong beserta nama layanannya.
    """
    halaman = bikin_halaman_kios(jumlah)

    for btn in halaman.tombol_layanan:
        bawah = btn.mapTo(halaman, btn.rect().bottomLeft()).y()
        assert bawah <= halaman.height()


@pytest.mark.parametrize("jumlah", [4, 5, 6, 7])
def test_kartu_tidak_saling_menindih(bikin_halaman_kios, jumlah):
    """
    Baris kartu tidak boleh bertumpuk pada jendela yang pendek.

    Kartu punya ukuran tetap; begitu jumlah tinggi seluruh barisnya
    melebihi panel, layout menumpuk baris kedua di atas baris pertama dan
    nama layanan yang tertimbun hilang sama sekali. Tingginya harus
    mengalah, bukan barisnya.
    """
    halaman = bikin_halaman_kios(jumlah)

    kotak = [btn.geometry() for btn in halaman.tombol_layanan]
    for indeks, satu in enumerate(kotak):
        for lain in kotak[indeks + 1 :]:
            assert not satu.intersects(lain)


def test_lima_layanan_tersusun_tiga_di_atas_dua_di_bawah(bikin_halaman_kios):
    halaman = bikin_halaman_kios(5)

    per_baris: dict[int, list] = {}
    for btn in halaman.tombol_layanan:
        per_baris.setdefault(btn.y(), []).append(btn)

    assert sorted(len(isi) for isi in per_baris.values()) == [2, 3]


def test_kartu_baris_terakhir_dilebarkan_secukupnya(bikin_halaman_kios):
    """
    Dua kartu terakhir mengisi barisnya, tetapi tidak sampai jauh lebih
    besar daripada kartu di atasnya — ukuran yang berbeda terbaca sebagai
    derajat yang berbeda.
    """
    from app.ui.kiosk.kiosk_page import PEMBESAR_BARIS_AKHIR

    halaman = bikin_halaman_kios(5)
    atas, bawah = halaman.tombol_layanan[:3], halaman.tombol_layanan[3:]

    assert bawah[0].width() > atas[0].width()
    assert bawah[0].width() <= round(atas[0].width() * PEMBESAR_BARIS_AKHIR)
    assert bawah[0].height() == atas[0].height()


def test_empat_layanan_dua_baris_dua_kolom(bikin_halaman_kios):
    halaman = bikin_halaman_kios(4)

    per_baris: dict[int, list] = {}
    for btn in halaman.tombol_layanan:
        per_baris.setdefault(btn.y(), []).append(btn)

    assert sorted(len(isi) for isi in per_baris.values()) == [2, 2]
    ukuran = {(btn.width(), btn.height()) for btn in halaman.tombol_layanan}
    assert len(ukuran) == 1


def test_kartu_melebar_saat_layanannya_sedikit(bikin_halaman_kios):
    """
    Kantor berlayanan tunggal tidak seharusnya mendapat kartu seukuran
    kantor berlayanan tiga, lalu menyisakan separuh panel kosong.
    """
    from app.ui.kiosk.kiosk_page import LEBAR_TOMBOL_MAKS

    halaman = bikin_halaman_kios(1, lebar=1920, tinggi=1080)

    assert halaman.tombol_layanan[0].width() > LEBAR_TOMBOL_MAKS


def test_petunjuk_tidak_menyuruh_memilih_saat_layanannya_satu(bikin_halaman_kios):
    """
    "Jenis layanan yang Anda butuhkan" mengandaikan ada yang perlu
    dipilih, dan membuat pengunjung mencari tombol lain yang tidak ada.
    """
    halaman = bikin_halaman_kios(1)

    assert halaman.label_petunjuk.text() == (
        "Sentuh tombol di bawah untuk mengambil nomor"
    )


def test_pesan_kosong_saat_tidak_ada_jenis_layanan(halaman_kios):
    """
    Jalur yang jarang terjadi tetapi harus tetap sehat.

    Aturan service menjaga selalu ada satu jenis layanan aktif, sehingga
    layar ini nyaris tidak pernah terlihat — dan justru karena itu
    kesalahannya bisa lama tidak ketahuan. Ia sempat melempar NameError,
    dan yang menemukannya bukan test melainkan pewaktu penyegaran yang
    kebetulan berdetak setelah databasenya dibongkar.
    """
    from PySide6.QtWidgets import QLabel

    halaman_kios.kategori = []
    halaman_kios._susun_tombol()

    teks = [
        label.text()
        for label in halaman_kios.halaman_pilihan.findChildren(QLabel)
    ]
    assert "Belum ada jenis layanan yang dibuka." in teks
    assert halaman_kios.tombol_layanan == []


def test_kartu_berubah_warna_saat_ditekan(halaman_kios):
    """
    Layar sentuh resistif tidak terasa ditekan.

    Kartu yang warnanya tidak berubah apa pun saat disentuh membuat
    pengunjung menekannya dua kali — dan tekanan kedua mendarat di layar
    konfirmasi yang baru saja muncul.
    """
    from app.ui.style import DISPLAY_KIOS_TOMBOL, DISPLAY_KIOS_TOMBOL_TEKAN

    assert DISPLAY_KIOS_TOMBOL_TEKAN != DISPLAY_KIOS_TOMBOL
    gaya = halaman_kios.tombol_layanan[0].styleSheet()
    assert f"QPushButton:pressed {{ background: {DISPLAY_KIOS_TOMBOL_TEKAN}" in gaya


# ---------------------------------------------------------------------
# Daftar layanan menyusul perubahan admin
# ---------------------------------------------------------------------

@pytest.fixture
def ubah_sebagai_admin(auth, master_service):
    """
    Jalankan perubahan data master, lalu kembali ke sesi kios.

    Anjungan berjalan tanpa login; sesinya harus utuh kembali sesudahnya,
    persis seperti keadaan sungguhan ketika admin mengubah data dari
    komputer lain.
    """
    from tests.conftest import TEST_PASSWORD

    def ubah(aksi):
        auth.logout()
        auth.login("admin", TEST_PASSWORD)
        try:
            return aksi(master_service)
        finally:
            auth.logout()
            auth.mulai_sesi_kios()

    return ubah


def test_kartu_menyusul_jenis_layanan_baru(halaman_kios, ubah_sebagai_admin):
    """
    Anjungan berdiri tanpa penjaga; tidak ada yang menekan F5 di sana.

    Sebelum ini, jenis layanan yang baru ditambah admin tidak pernah
    sampai ke layar anjungan sampai aplikasinya ditutup dan dibuka lagi.
    """
    ubah_sebagai_admin(
        lambda master: master.create_category(
            code="LAYANAN-D", name="Legalisir Surat", prefix="D"
        )
    )

    halaman_kios._periksa_perubahan_layanan()

    assert [k.prefix for k in halaman_kios.kategori] == ["A", "B", "C", "D"]
    assert len(halaman_kios.tombol_layanan) == 4


def test_kartu_menyusul_layanan_yang_dinonaktifkan(halaman_kios, ubah_sebagai_admin):
    kategori = halaman_kios.kategori[0]
    ubah_sebagai_admin(
        lambda master: master.set_category_status(kategori.id, False)
    )

    halaman_kios._periksa_perubahan_layanan()

    assert [k.prefix for k in halaman_kios.kategori] == ["B", "C"]


def test_kartu_menyusul_urutan_yang_digeser(halaman_kios, ubah_sebagai_admin):
    """Urutan kartu di anjungan adalah urutan yang diatur di Data Master."""
    kategori = halaman_kios.kategori[0]
    ubah_sebagai_admin(
        lambda master: master.pindahkan_category(kategori.id, naik=False)
    )

    halaman_kios._periksa_perubahan_layanan()

    assert [k.prefix for k in halaman_kios.kategori] == ["B", "A", "C"]


def test_kartu_tidak_disusun_ulang_bila_tidak_ada_yang_berubah(halaman_kios):
    """
    Tombol yang sama tidak boleh dibangun ulang tiap dua puluh detik.

    Membangun ulang menghapus tombol yang lama; bila itu terjadi tepat
    ketika jari pengunjung sedang menyentuhnya, sentuhannya hilang.
    """
    sebelum = list(halaman_kios.tombol_layanan)

    halaman_kios._periksa_perubahan_layanan()

    assert halaman_kios.tombol_layanan == sebelum


def test_kartu_tidak_disusun_ulang_saat_menunggu_konfirmasi(
    halaman_kios, ubah_sebagai_admin
):
    """
    Menyusun ulang kartu saat layar konfirmasi terbuka akan membatalkan
    pilihan pengunjung tanpa ia mengerti mengapa.
    """
    halaman_kios._pilih_layanan(halaman_kios.kategori[0])
    ubah_sebagai_admin(
        lambda master: master.create_category(
            code="LAYANAN-D", name="Legalisir Surat", prefix="D"
        )
    )

    halaman_kios._periksa_perubahan_layanan()

    assert len(halaman_kios.tombol_layanan) == 3
    assert halaman_kios._menunggu_konfirmasi


def test_kartu_tidak_disusun_ulang_saat_kartu_nomor_tampil(
    halaman_kios, ubah_sebagai_admin
):
    """Layar yang sedang dibaca orang tidak boleh direbut."""
    halaman_kios.ambil_nomor(halaman_kios.kategori[0].id)
    ubah_sebagai_admin(
        lambda master: master.create_category(
            code="LAYANAN-D", name="Legalisir Surat", prefix="D"
        )
    )

    halaman_kios._periksa_perubahan_layanan()

    assert len(halaman_kios.tombol_layanan) == 3


def test_kartu_baru_ikut_mati_selama_jeda(halaman_kios, ubah_sebagai_admin):
    """
    Tombol yang baru dibangun selalu lahir hidup.

    Tanpa penyesuaian ulang, kartu yang muncul tepat di tengah jeda bisa
    disentuh padahal jedanya belum habis.
    """
    halaman_kios.ambil_nomor(halaman_kios.kategori[0].id)
    halaman_kios._penghapus_hasil.stop()  # hasil sudah lewat, jeda masih jalan
    ubah_sebagai_admin(
        lambda master: master.create_category(
            code="LAYANAN-D", name="Legalisir Surat", prefix="D"
        )
    )

    halaman_kios._periksa_perubahan_layanan()

    assert len(halaman_kios.tombol_layanan) == 4
    assert all(not btn.isEnabled() for btn in halaman_kios.tombol_layanan)


def test_papan_kios_tetap_kompak_di_layar_penuh(qtbot, halaman_kios):
    """Pembedanya `kompak`, bukan aplikasi yang berbeda."""
    sebelum = halaman_kios.papan.px("nomor")

    halaman_kios.resize(1920, 1080)
    halaman_kios.show()
    qtbot.waitExposed(halaman_kios)

    assert halaman_kios.papan.kompak is True
    assert halaman_kios.papan.skala == 1.0
    assert halaman_kios.papan.px("nomor") == sebelum


def test_papan_kios_juga_memiliki_jam(halaman_kios):
    """Satu DisplayPage: perbaikan pada papan televisi ikut ke kios."""
    assert halaman_kios.papan.label_jam.text()
    assert "·" in halaman_kios.papan.label_jam.text()


def test_mengambil_nomor_menampilkan_hasil_besar(halaman_kios, antrian_siap):
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])

    assert "A-001" in halaman_kios.label_ajakan.text()


def test_tombol_mati_selama_jeda_dan_menyebutkan_alasannya(halaman_kios, antrian_siap):
    """
    Tombol mati tanpa keterangan membuat pengunjung menekannya berulang
    kali dan mengira layarnya rusak.
    """
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])

    assert all(not btn.isEnabled() for btn in halaman_kios.tombol_layanan)

    halaman_kios._penghapus_hasil.stop()
    halaman_kios._perbarui_jeda()

    assert "tunggu" in halaman_kios.label_petunjuk.text().lower()


def test_pengambilan_kedua_tidak_membuka_dialog(halaman_kios, antrian_siap):
    """Dialog modal di layar publik membuat test hang dan layar tersangkut."""
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])

    assert "A-001" in halaman_kios.label_ajakan.text()
    assert "tunggu" in halaman_kios.label_petunjuk.text().lower()


def test_gagal_cetak_tidak_membatalkan_nomor_di_kios(qtbot, kios, antrian_siap, auth):
    """Printer kehabisan kertas tidak boleh menghapus giliran pengunjung."""
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import Queue, QueueStatus
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.services.sound_service import NullSoundPlayer
    from app.services.ticket_service import GagalTicketPrinter, TicketService
    from app.ui.kiosk.kiosk_page import KioskPage

    tiket = TicketService(
        GagalTicketPrinter("Kertas habis."),
        SettingsService(auth),
        MasterDataService(auth),
    )
    halaman = KioskPage(
        kios,
        MasterDataService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        tiket,
    )
    qtbot.addWidget(halaman)
    halaman.papan.hentikan()
    halaman._penghitung.stop()

    halaman.ambil_nomor(antrian_siap["kategori"]["A"])

    assert "A-001" in halaman.label_ajakan.text()
    with session_scope() as session:
        tersimpan = session.scalar(sa.select(Queue))
    assert tersimpan is not None
    assert tersimpan.queue_number == "A-001"
    assert tersimpan.status is QueueStatus.WAITING


def test_sesi_anjungan_hanya_menu_anjungan(qtbot, auth, antrian_siap):
    from app.ui.kiosk.kiosk_page import KioskPage
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert menu == ["Anjungan Ambil Nomor"]
    assert jendela.mode_kios
    assert isinstance(jendela.halaman.currentWidget(), KioskPage)
    assert jendela.findChild(QFrame, "panelHeader") is None
    assert jendela.findChild(QStatusBar) is None
    assert jendela.navigasi.parent() is None


@pytest.mark.parametrize(
    "peran", ["cro", "supervisor", "registration", "admin", "display"]
)
def test_petugas_tidak_melihat_menu_anjungan(qtbot, auth, peran):
    from app.ui.main_window import MainWindow
    from tests.conftest import TEST_PASSWORD

    auth.logout()
    auth.login(peran, TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert "Anjungan Ambil Nomor" not in menu


def test_mode_dialog_memilih_anjungan(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QPushButton

    from app.ui.login.mode_dialog import ANJUNGAN, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)
    tombol_anjungan = next(
        b for b in dialog.findChildren(QPushButton) if "ANJUNGAN" in b.text()
    )
    qtbot.mouseClick(tombol_anjungan, Qt.MouseButton.LeftButton)

    assert dialog.pilihan == ANJUNGAN
    assert dialog.result() == int(QDialog.DialogCode.Accepted)


def test_mode_dialog_memilih_layar_antrian(qtbot):
    """
    Televisi ruang tunggu adalah pilihan tersendiri, bukan bagian dari
    anjungan. Sebelumnya keduanya satu tombol bernama "Layar Pengunjung",
    dan mesin televisi terpaksa dibuka lewat login akun DISPLAY.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QPushButton

    from app.ui.login.mode_dialog import LAYAR_ANTRIAN, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)
    tombol_antrian = next(
        b for b in dialog.findChildren(QPushButton) if "LAYAR ANTRIAN" in b.text()
    )
    qtbot.mouseClick(tombol_antrian, Qt.MouseButton.LeftButton)

    assert dialog.pilihan == LAYAR_ANTRIAN
    assert dialog.result() == int(QDialog.DialogCode.Accepted)


def test_mode_dialog_menawarkan_empat_pilihan_saat_uji(qtbot):
    """
    Dari source, admin dan petugas harus dapat dipilih terpisah.

    Satu tombol 'Layar Petugas' yang selalu masuk sebagai admin membuat
    uji panggilan tidak bisa dilakukan tanpa mematikan pintasan login.
    """
    from PySide6.QtWidgets import QPushButton

    from app.ui.login.mode_dialog import (
        ANJUNGAN,
        LAYAR_ADMIN,
        LAYAR_ANTRIAN,
        LAYAR_PETUGAS,
        ModeDialog,
    )

    dialog = ModeDialog()
    qtbot.addWidget(dialog)

    teks = [b.text() for b in dialog.findChildren(QPushButton)]
    assert len(teks) == 4
    assert any("ANTRIAN" in t for t in teks)
    assert any("ANJUNGAN" in t for t in teks)
    assert any("ADMIN" in t for t in teks)
    assert any("PETUGAS" in t for t in teks)
    assert len({LAYAR_ANTRIAN, ANJUNGAN, LAYAR_ADMIN, LAYAR_PETUGAS}) == 4


def test_mode_dialog_satu_tombol_petugas_bila_wajib_login(qtbot, monkeypatch):
    """Pada .exe, peran dipisah oleh akun yang masuk, bukan oleh tombol."""
    monkeypatch.setenv("ANTRIAN_LEWATI_LOGIN", "0")
    from PySide6.QtWidgets import QPushButton

    from app.ui.login.mode_dialog import ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)

    teks = [b.text() for b in dialog.findChildren(QPushButton)]
    assert len(teks) == 3
    assert not any("ADMIN" in t for t in teks)
    assert any("PETUGAS" in t for t in teks)


def test_mode_dialog_memilih_layar_petugas(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QPushButton

    from app.ui.login.mode_dialog import LAYAR_PETUGAS, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)
    tombol_petugas = next(
        b for b in dialog.findChildren(QPushButton) if "PETUGAS" in b.text()
    )
    qtbot.mouseClick(tombol_petugas, Qt.MouseButton.LeftButton)

    assert dialog.pilihan == LAYAR_PETUGAS
    assert dialog.result() == int(QDialog.DialogCode.Accepted)


def test_mode_dialog_memilih_layar_admin(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QPushButton

    from app.ui.login.mode_dialog import LAYAR_ADMIN, ModeDialog

    dialog = ModeDialog()
    qtbot.addWidget(dialog)
    tombol_admin = next(
        b for b in dialog.findChildren(QPushButton) if "ADMIN" in b.text()
    )
    qtbot.mouseClick(tombol_admin, Qt.MouseButton.LeftButton)

    assert dialog.pilihan == LAYAR_ADMIN
    assert dialog.result() == int(QDialog.DialogCode.Accepted)


# ---------------------------------------------------------------------
# Layar antrian sebagai mesin tersendiri
# ---------------------------------------------------------------------

def test_sesi_layar_hanya_menu_layar_antrian(qtbot, auth, antrian_siap):
    """
    Televisi ruang tunggu membuka papan besar, bukan halaman anjungan.

    Menu-nya dibuktikan di sini karena keduanya sama-sama berjalan tanpa
    login: yang membedakan hanyalah peran sesinya, dan tertukarnya berarti
    televisi memunculkan tombol ambil nomor yang tidak ada orang di
    depannya untuk menekan.
    """
    from app.ui.display.display_page import DisplayPage
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_layar()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
    assert menu == ["Layar Antrian"]
    assert isinstance(jendela.halaman.currentWidget(), DisplayPage)


def test_sesi_layar_menyembunyikan_seluruh_perkakas_petugas(qtbot, auth, antrian_siap):
    """
    Sama seperti anjungan: tidak ada bilah atas, navigasi, maupun bilah
    status. Tombol "Keluar" yang terpampang di ruang tunggu hanya
    mengundang orang menutup aplikasi antrian.
    """
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_layar()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.mode_kios
    assert jendela.findChild(QFrame, "panelHeader") is None
    assert jendela.findChild(QStatusBar) is None
    assert jendela.navigasi.parent() is None


def test_papan_televisi_bukan_papan_kompak(qtbot, auth, antrian_siap):
    """
    Televisi dibaca dari seberang ruangan, anjungan dari jarak satu lengan.

    Papan kompak di televisi berarti nomor sebesar papan kios pada layar 50
    inci — terbaca, tetapi membuang seluruh alasan televisi itu dipasang.
    """
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.mulai_sesi_layar()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.halaman.currentWidget().kompak is False


# ---------------------------------------------------------------------
# Pencetak dan pengeras suara menempel pada mesin
# ---------------------------------------------------------------------

def test_anjungan_diam_walau_suara_dinyalakan_di_pengaturan(
    qtbot, auth, antrian_siap, env_mesin
):
    """
    Dua mesin publik dengan pengeras suara masing-masing akan mengumumkan
    nomor yang sama dua kali, saling menyusul, karena keduanya menyegarkan
    sendiri tiap dua detik.

    Yang dibuktikan di sini adalah pemutarnya benar-benar diam — bukan
    sekadar penanda `suara_aktif` di papan, yang masih menyisakan
    kemungkinan bunyi lewat jalur lain.
    """
    from app.services.sound_service import NullSoundPlayer
    from app.ui.main_window import MainWindow

    env_mesin(ANTRIAN_SUARA=None)
    SettingsService(auth).set("display.sound_enabled", "true")

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert isinstance(jendela.sound_player, NullSoundPlayer)
    assert jendela.halaman.currentWidget().papan.suara_aktif is False


def test_anjungan_bersuara_kembali_bila_mesin_memintanya(
    qtbot, auth, antrian_siap, env_mesin
):
    """Pemasangan satu-mesin yang anjungannya merangkap papan nomor."""
    from app.ui.main_window import MainWindow

    env_mesin(ANTRIAN_SUARA="1")
    SettingsService(auth).set("display.sound_enabled", "false")

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert jendela.halaman.currentWidget().papan.suara_aktif is True


def test_pencetak_mesin_dipakai_jendela_utama(qtbot, auth, antrian_siap, env_mesin):
    """
    Komputer loket tanpa pencetak tiket tidak boleh ikut mencoba mencetak
    hanya karena pengaturan bersama menyebut "Cetak ke printer Windows".
    """
    from app.services.ticket_service import NullTicketPrinter
    from app.ui.main_window import MainWindow

    env_mesin(ANTRIAN_PRINTER="none")
    SettingsService(auth).set("ticket.printer", "system")

    auth.logout()
    auth.mulai_sesi_kios()
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    assert isinstance(jendela.ticket_service.printer, NullTicketPrinter)


# ---------------------------------------------------------------------
# Media per jenis layanan
# ---------------------------------------------------------------------

@pytest.fixture
def folder_media(tmp_path, monkeypatch):
    """Alihkan media/kiosk ke folder sementara milik test ini."""
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)
    return folder


def _gambar(path):
    """PNG 1x1 yang benar-benar dapat dimuat QPixmap."""
    from PySide6.QtGui import QImage

    gambar = QImage(1, 1, QImage.Format.Format_RGB32)
    gambar.fill(0)
    assert gambar.save(str(path))
    return path


def test_media_layanan_menolak_kode_yang_merayap_keluar(folder_media):
    """
    `code` datang dari isian admin dan tidak boleh jadi jalan ke luar
    folder media, persis seperti penjagaan pada path_media_kios.
    """
    from app.ui.kiosk.sambutan import folder_media_layanan

    assert folder_media_layanan("..") is None
    assert folder_media_layanan("../rahasia") is None
    assert folder_media_layanan("a/b") is None
    assert folder_media_layanan("") is None
    assert folder_media_layanan("   ") is None
    assert folder_media_layanan("KONSULTASI") is not None


def test_media_layanan_mengambil_berkas_pertama_menurut_nama(folder_media):
    """Satu berkas, bukan playlist — layar konfirmasi terlalu singkat."""
    from app.ui.kiosk.sambutan import folder_media_layanan, media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "02_kedua.png")
    _gambar(folder / "01_pertama.png")

    assert media_layanan("KONSULTASI").name == "01_pertama.png"


def test_media_layanan_kosong_bila_belum_ada_berkas(folder_media):
    from app.ui.kiosk.sambutan import media_layanan

    assert media_layanan("KONSULTASI") is None


def test_folder_layanan_tidak_ikut_diputar_sebagai_sambutan(folder_media):
    """
    Subfolder layanan hidup DI DALAM media/kiosk. Kalau ikut terbaca,
    putaran sambutan akan mencoba memutar sebuah folder.
    """
    from app.ui.kiosk.sambutan import daftar_media_kios, folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "info.png")
    _gambar(folder_media / "sambutan.png")

    assert [p.name for p in daftar_media_kios()] == ["sambutan.png"]


def test_pasang_media_layanan_mengganti_berkas_sebelumnya(folder_media):
    """
    Hanya berkas pertama menurut nama yang pernah tampil. Berkas lama yang
    dibiarkan menumpuk membuat pilihan admin tampak tidak berpengaruh.
    """
    from app.ui.kiosk.sambutan import (
        folder_media_layanan,
        media_layanan,
        salin_ke_media_layanan,
    )

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "01_lama.png")

    sumber = _gambar(folder_media.parent / "99_baru.png")
    salin_ke_media_layanan("KONSULTASI", sumber)

    assert [p.name for p in folder.iterdir()] == ["99_baru.png"]
    assert media_layanan("KONSULTASI").name == "99_baru.png"


def test_hapus_media_layanan_mengosongkan_folder(folder_media):
    from app.ui.kiosk.sambutan import (
        folder_media_layanan,
        hapus_media_layanan,
        media_layanan,
    )

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "info.png")

    hapus_media_layanan("KONSULTASI")

    assert media_layanan("KONSULTASI") is None


# ---------------------------------------------------------------------
# Panel anjungan: media layanan dan kartu nomor
# ---------------------------------------------------------------------

def test_sentuh_layanan_menampilkan_media_bukan_teks(halaman_kios, folder_media):
    """Media mengalahkan info teks bila jenis layanan itu punya berkas."""
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR, folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    berkas = _gambar(folder / "info.png")

    layanan = next(k for k in halaman_kios.kategori if k.code == "KONSULTASI")
    halaman_kios._pilih_layanan(layanan)

    panel = halaman_kios.papan.panel_info_kios
    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR
    assert panel.berkas_tampil == berkas


def test_layanan_tanpa_media_tetap_memakai_info_teks(qtbot, halaman_kios, folder_media):
    """Rantai cadangannya utuh: berkas, lalu info teks, lalu sambutan."""
    from app.ui.display.display_page import DURASI_FADE_INFO_KIOS_MS
    from app.ui.kiosk.sambutan import HALAMAN_TEKS

    layanan = next(k for k in halaman_kios.kategori if k.code == "KONSULTASI")
    halaman_kios._pilih_layanan(layanan)
    qtbot.wait(DURASI_FADE_INFO_KIOS_MS * 2 + 200)

    panel = halaman_kios.papan.panel_info_kios
    assert panel.tumpukan.currentIndex() == HALAMAN_TEKS


def test_batal_mengembalikan_panel_ke_sambutan(halaman_kios, folder_media):
    from app.ui.kiosk.sambutan import HALAMAN_TEKS, folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "info.png")

    layanan = next(k for k in halaman_kios.kategori if k.code == "KONSULTASI")
    halaman_kios._pilih_layanan(layanan)
    halaman_kios._batal_konfirmasi()

    panel = halaman_kios.papan.panel_info_kios
    assert panel.tumpukan.currentIndex() == HALAMAN_TEKS
    assert panel._berkas_layanan is None


def test_sentuh_layanan_tidak_mereset_putaran_sambutan(halaman_kios, folder_media):
    """
    Jebakan yang paling gampang terlewat: menyentuh _kunci_aktif akan
    membuat penyegaran papan menganggap pengaturan berubah dan membangun
    ulang putaran dari berkas pertama pada SETIAP sentuhan pengunjung.
    """
    from app.ui.kiosk.sambutan import folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "info.png")

    panel = halaman_kios.papan.panel_info_kios
    kunci_sebelum = panel._kunci_aktif

    layanan = next(k for k in halaman_kios.kategori if k.code == "KONSULTASI")
    halaman_kios._pilih_layanan(layanan)
    halaman_kios._batal_konfirmasi()

    assert panel._kunci_aktif == kunci_sebelum


def test_kartu_nomor_menyebut_nomor_layanan_dan_sisa_antrian(halaman_kios, antrian_siap):
    """
    Kartu ini yang dibaca pengunjung sambil menunggu tiketnya keluar —
    dan satu-satunya catatan nomornya bila printer kehabisan kertas.
    """
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])

    panel = halaman_kios.papan.panel_info_kios
    assert panel.label_kartu_nomor.text() == "A-001"
    assert panel.label_kartu_layanan.text() == "Konsultasi"
    assert panel.label_kartu_sisa.text() == "Tidak ada sisa antrian"


def test_kartu_nomor_menghitung_antrian_di_depannya(
    halaman_kios, antrian_siap, monkeypatch
):
    """Angkanya lintas jenis layanan, sama seperti yang tercetak di tiket."""
    # Jeda antar-pengambilan dimatikan: yang diuji di sini hitungannya,
    # bukan penahan tombol beruntun yang sudah punya testnya sendiri.
    monkeypatch.setattr(halaman_kios.queue, "jeda_kios_detik", lambda: 0)

    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["B"])
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["C"])

    panel = halaman_kios.papan.panel_info_kios
    assert panel.label_kartu_nomor.text() == "C-001"
    assert panel.label_kartu_sisa.text() == "Sisa antrian: 2"


def test_kartu_nomor_dan_panel_bawah_memakai_kalimat_yang_sama(
    halaman_kios, antrian_siap
):
    """Dua tempat yang menjawab pertanyaan sama tidak boleh berbeda bunyi."""
    halaman_kios.ambil_nomor(antrian_siap["kategori"]["A"])

    panel = halaman_kios.papan.panel_info_kios
    assert panel.label_kartu_arahan.text() == halaman_kios.label_petunjuk.text()


def test_arahan_menyuruh_mencatat_nomor_saat_cetak_gagal(
    qtbot, kios, auth, antrian_siap
):
    """
    Menyuruh "ambil tiket Anda" di depan printer yang tidak mengeluarkan
    apa pun jauh lebih menyesatkan daripada tidak berkata apa-apa.
    """
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.services.sound_service import NullSoundPlayer
    from app.services.ticket_service import GagalTicketPrinter, TicketService
    from app.ui.kiosk.kiosk_page import ARAHAN_CETAK, CETAK_GAGAL, KioskPage

    tiket = TicketService(
        GagalTicketPrinter("Kertas habis."),
        SettingsService(auth),
        MasterDataService(auth),
    )
    halaman = KioskPage(
        kios,
        MasterDataService(auth),
        SettingsService(auth),
        NullSoundPlayer(),
        tiket,
    )
    qtbot.addWidget(halaman)
    halaman._penghitung.stop()

    halaman.ambil_nomor(antrian_siap["kategori"]["A"])

    panel = halaman.papan.panel_info_kios
    assert panel.label_kartu_arahan.text() == ARAHAN_CETAK[CETAK_GAGAL]
    # Nomornya tetap tampil besar: justru inilah saat layar paling perlu
    # dibaca, karena tidak ada kertas yang membawanya pulang.
    assert panel.label_kartu_nomor.text() == "A-001"
    halaman.papan.hentikan()


def test_kartu_nomor_bertahan_sampai_tombol_hidup_lagi(halaman_kios, antrian_siap):
    """
    Tanpa penyelarasan ini ada beberapa detik saat panel sudah kembali ke
    sambutan padahal tombolnya masih mati — layar tampak siap dipakai
    padahal belum.
    """
    from app.ui.kiosk.kiosk_page import JEDA_HASIL

    jeda_ms = halaman_kios.queue.jeda_kios_detik() * 1000

    assert halaman_kios._lama_hasil_ms() >= jeda_ms
    assert halaman_kios._lama_hasil_ms() >= JEDA_HASIL


def test_panel_dibebaskan_saat_nomor_gagal_terbit(halaman_kios, folder_media):
    """
    Kartu nomor tidak akan pernah tampil bila nomornya gagal terbit, jadi
    tidak ada lagi yang akan membebaskan panel dari media layanan.
    """
    from app.core.errors import BusinessRuleError
    from app.ui.kiosk.sambutan import HALAMAN_TEKS, folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "info.png")

    layanan = next(k for k in halaman_kios.kategori if k.code == "KONSULTASI")
    halaman_kios._pilih_layanan(layanan)

    def gagal(_category_id):
        raise BusinessRuleError("Pendaftaran ditutup.")

    halaman_kios.queue.create_queue = gagal
    halaman_kios._konfirmasi_ambil()

    panel = halaman_kios.papan.panel_info_kios
    assert panel.tumpukan.currentIndex() == HALAMAN_TEKS
    assert panel._berkas_layanan is None
    assert not panel._menampilkan_info_layanan


# ---------------------------------------------------------------------
# Video jenis layanan diulang sampai pengunjung memilih
# ---------------------------------------------------------------------

def _panel_dengan_video_layanan(halaman_kios, folder_media):
    """
    Panel anjungan yang sedang memegang video sebuah jenis layanan.

    Berkasnya palsu — yang diuji keputusan detaknya, bukan kemampuan Qt
    memutar berkas. Pola yang sama dipakai test putaran sambutan.
    """
    from app.ui.kiosk.sambutan import HALAMAN_VIDEO, folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    berkas = folder / "info.mp4"
    berkas.write_bytes(b"bukan video sungguhan, cukup ada namanya")

    layanan = next(k for k in halaman_kios.kategori if k.code == "KONSULTASI")
    halaman_kios._pilih_layanan(layanan)

    panel = halaman_kios.papan.panel_info_kios
    panel._berkas_layanan = berkas
    panel.berkas_tampil = berkas
    panel._tampilkan_halaman(HALAMAN_VIDEO)
    panel._dijeda_sengaja = False
    panel._sedang_ganti_item = False
    panel._mulai_jam_item()
    return panel


def test_video_layanan_diulang_dari_awal_saat_habis(
    halaman_kios, folder_media, monkeypatch
):
    """
    Membeku di frame terakhir salah untuk panel ini: pengunjung
    menontonnya SAMBIL memutuskan, dan yang datang di tengah putaran
    hanya akan melihat gambar diam.
    """
    panel = _panel_dengan_video_layanan(halaman_kios, folder_media)

    diulang = []
    monkeypatch.setattr(panel._pemutar, "duration", lambda: 5000)
    monkeypatch.setattr(panel._pemutar, "position", lambda: 5000)
    monkeypatch.setattr(panel._pemutar, "setPosition", lambda ms: diulang.append(ms))

    panel._jaga_putaran()

    assert diulang == [0]


def test_mengulang_video_layanan_tidak_menyentuh_putaran_sambutan(
    halaman_kios, folder_media, monkeypatch
):
    """Media layanan hidup di luar daftar sambutan dan tidak boleh memajukannya."""
    panel = _panel_dengan_video_layanan(halaman_kios, folder_media)
    indeks_sebelum = panel._indeks

    monkeypatch.setattr(panel._pemutar, "duration", lambda: 5000)
    monkeypatch.setattr(panel._pemutar, "position", lambda: 5000)
    monkeypatch.setattr(panel._pemutar, "setPosition", lambda ms: None)

    panel._jaga_putaran()

    assert panel._indeks == indeks_sebelum
    assert panel._berkas_layanan is not None


def test_jam_item_direstart_supaya_tidak_mengulang_tiap_detak(
    halaman_kios, folder_media, monkeypatch
):
    """
    `lewat_batas` dihitung dari jam item. Tanpa restart, ia langsung benar
    lagi pada detak berikutnya dan videonya diulang setiap 250 milidetik.
    """
    panel = _panel_dengan_video_layanan(halaman_kios, folder_media)

    diulang = []
    monkeypatch.setattr(panel._pemutar, "duration", lambda: 5000)
    monkeypatch.setattr(panel._pemutar, "setPosition", lambda ms: diulang.append(ms))

    monkeypatch.setattr(panel._pemutar, "position", lambda: 5000)
    panel._jaga_putaran()

    # Detak berikutnya: video sudah mulai lagi dari awal.
    monkeypatch.setattr(panel._pemutar, "position", lambda: 120)
    panel._jaga_putaran()

    assert diulang == [0]


def test_video_layanan_yang_tersendat_menyerah_ke_teks(
    halaman_kios, folder_media, monkeypatch
):
    """
    Berkas rusak tidak boleh diulang tiap detak — kedutan berulang di
    layar publik lebih buruk daripada teks yang diam.
    """
    from app.ui.kiosk.sambutan import HALAMAN_TEKS, MACET_LAYANAN_MS

    panel = _panel_dengan_video_layanan(halaman_kios, folder_media)

    diulang = []
    monkeypatch.setattr(panel._pemutar, "duration", lambda: 0)
    monkeypatch.setattr(panel._pemutar, "position", lambda: 0)
    monkeypatch.setattr(panel._pemutar, "setPosition", lambda ms: diulang.append(ms))

    detak = MACET_LAYANAN_MS // panel._jantung.interval() + 2
    for _ in range(detak):
        panel._jaga_putaran()

    assert panel._berkas_layanan is None
    assert panel.tumpukan.currentIndex() == HALAMAN_TEKS
    assert diulang == []


def test_sambutan_tetap_sekali_putar_setelah_media_layanan(
    halaman_kios, folder_media, monkeypatch
):
    """
    Penjaga kebocoran: pengaturan Infinite milik media layanan tidak boleh
    tertinggal pada klip sambutan berikutnya, yang harus maju ke item lain
    setelah selesai.
    """
    from PySide6.QtMultimedia import QMediaPlayer
    from app.ui.kiosk.sambutan import folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    berkas_layanan = folder / "info.mp4"
    berkas_layanan.write_bytes(b"palsu")
    berkas_sambutan = folder_media / "01_sambutan.mp4"
    berkas_sambutan.write_bytes(b"palsu")

    panel = halaman_kios.papan.panel_info_kios
    diminta = []
    monkeypatch.setattr(panel._pemutar, "setLoops", lambda n: diminta.append(n))

    panel._pasang_video(berkas_layanan, ulang=True)
    panel._pasang_video(berkas_sambutan)

    assert diminta == [QMediaPlayer.Loops.Infinite, QMediaPlayer.Loops.Once]


def test_gambar_layanan_tidak_ikut_diulang(halaman_kios, folder_media, monkeypatch):
    """Gambar sudah "mengulang" dengan cara tetap diam di layar."""
    from app.ui.kiosk.sambutan import HALAMAN_GAMBAR, folder_media_layanan

    folder = folder_media_layanan("KONSULTASI")
    folder.mkdir(parents=True)
    _gambar(folder / "info.png")

    layanan = next(k for k in halaman_kios.kategori if k.code == "KONSULTASI")
    halaman_kios._pilih_layanan(layanan)

    panel = halaman_kios.papan.panel_info_kios
    diulang = []
    monkeypatch.setattr(panel._pemutar, "setPosition", lambda ms: diulang.append(ms))

    panel._mulai_jam_item()
    panel._jaga_putaran()

    assert panel.tumpukan.currentIndex() == HALAMAN_GAMBAR
    assert diulang == []
    assert panel._berkas_layanan is not None
