"""Test peran komputer terhadap pengunjung: dipakai sebagai apa."""

from __future__ import annotations

import json

import pytest

from app.core.peran import (
    ADMIN,
    BAWAAN,
    PAPAN_MEMANJANG,
    PERAN_SAH,
    PETUGAS,
    TELEVISI,
    TIDAK_MENCETAK,
    PeranKomputer,
    baca_peran,
    dari_dict,
    path_berkas_peran,
    tulis_peran,
)


# ---------------------------------------------------------------------
# Tabel simpulan
# ---------------------------------------------------------------------

def test_mode_setiap_peran_sama_dengan_yang_dikenali_dialog():
    """
    Nama mode ditulis ulang di app.core.peran, terpisah dari
    app.ui.login.mode_dialog, karena lapisan core tidak boleh bergantung
    pada lapisan tampilan. Keduanya wajib berisi kata yang sama persis —
    peran yang menunjuk mode tidak dikenali akan membuka dialog
    pilih-mode di depan pengunjung, justru yang hendak dihindari.
    """
    from app.ui.login.mode_dialog import LAYAR_ADMIN, LAYAR_ANTRIAN, LAYAR_PETUGAS

    sah = {LAYAR_PETUGAS, LAYAR_ADMIN, LAYAR_ANTRIAN}

    assert {b.mode for b in BAWAAN.values()} <= sah


@pytest.mark.parametrize("kode", sorted(PERAN_SAH))
def test_setiap_peran_menunjuk_mode_yang_terisi(kode):
    assert BAWAAN[kode].mode


def test_loket_tidak_mencetak():
    """Tidak ada pencetak yang menempel pada komputer petugas."""
    for kode in (PETUGAS, ADMIN):
        assert PeranKomputer(peran=kode).printer_efektif == TIDAK_MENCETAK


def test_anjungan_bukan_peran_komputer_windows():
    """
    Anjungan adalah tablet Android (docs/istilah.md). Berkas lama yang masih
    menyebutnya diperlakukan seperti belum ditetapkan.
    """
    assert "anjungan" not in PERAN_SAH
    assert "anjungan-totem" not in PERAN_SAH
    assert dari_dict({"peran": "anjungan"}).peran == ""
    assert dari_dict({"peran": "anjungan-totem"}).peran == ""


@pytest.mark.parametrize("kode", [PAPAN_MEMANJANG])
def test_papan_memanjang_diam(kode):
    """
    Dua pengeras suara yang memanggil nomor yang sama dengan selisih
    setengah detik terdengar seperti kerusakan, bukan seperti pengumuman.
    """
    assert PeranKomputer(peran=kode).suara_efektif is False


@pytest.mark.parametrize("kode", [PETUGAS, ADMIN, TELEVISI])
def test_selebihnya_mengikuti_pengaturan_bersama(kode):
    """None BUKAN False: mesin yang tidak berpendapat ikut pengaturan."""
    assert PeranKomputer(peran=kode).suara_efektif is None


def test_hanya_papan_memanjang_yang_menyebut_bentuk_layarnya():
    """
    Bentuk layar adalah sifat benda yang tergantung di dinding, dan papan
    sudah mengukurnya sendiri. Peran yang ikut menebak hanya akan
    mengalahkan pengukuran yang lebih tahu.
    """
    menyebut = {k for k in PERAN_SAH if PeranKomputer(peran=k).bentuk_efektif}

    assert menyebut == {PAPAN_MEMANJANG}
    assert PeranKomputer(peran=PAPAN_MEMANJANG).bentuk_efektif == "memanjang"


# ---------------------------------------------------------------------
# Pilihan yang disimpan, bukan hasil simpulannya
# ---------------------------------------------------------------------

def test_belum_ditetapkan_tidak_menuntut_apa_pun():
    """
    Komputer tanpa berkas berperilaku persis seperti sebelum berkas ini
    ada: mode kosong, sehingga dialog pilih-mode tetap muncul.
    """
    kosong = PeranKomputer()

    assert not kosong.ditetapkan
    assert kosong.mode == ""
    assert kosong.printer_efektif == ""
    assert kosong.suara_efektif is None
    assert kosong.bentuk_efektif == ""
    assert not kosong.disesuaikan


def test_isian_yang_diisi_mengalahkan_bawaan_perannya():
    pilihan = PeranKomputer(peran=TELEVISI, suara=True)

    assert pilihan.suara_efektif is True
    assert pilihan.disesuaikan


def test_menyimpang_ke_nilai_yang_kebetulan_sama_tetap_terbaca_menyimpang():
    """
    Orang yang memilih "diam" untuk papan memanjang sedang menyatakan kehendak,
    bukan sekadar menyetujui bawaannya. Kehendak itu tidak boleh hilang
    hanya karena tabel simpulan kebetulan setuju hari ini.
    """
    pilihan = PeranKomputer(peran=PAPAN_MEMANJANG, suara=False)

    assert pilihan.suara_efektif is False
    assert pilihan.disesuaikan


def test_yang_ikut_peran_disimpan_sebagai_null():
    """
    Menyimpan hasil simpulannya akan membekukan mesin pada nilai saat
    pemasangan, dan perbaikan tabel simpulan di versi berikutnya tidak
    pernah sampai ke sana.
    """
    isi = PeranKomputer(peran=TELEVISI, bentuk_layar="memanjang").ke_dict()

    assert isi == {
        "peran": "televisi",
        "printer": None,
        "suara": None,
        "bentuk_layar": "memanjang",
    }


# ---------------------------------------------------------------------
# Berkas
# ---------------------------------------------------------------------

def test_berkas_pulang_pergi_utuh(tmp_path):
    path = tmp_path / "peran.json"
    asli = PeranKomputer(peran=PETUGAS, suara=False, bentuk_layar="tegak")

    tulis_peran(path, asli)

    assert baca_peran(path) == asli


def test_berkas_ditulis_dalam_bentuk_yang_enak_disunting(tmp_path):
    """Lima komputer loket disalin lewat Notepad; berkasnya harus terbaca."""
    path = tmp_path / "peran.json"
    tulis_peran(path, PeranKomputer(peran=PAPAN_MEMANJANG))

    teks = path.read_text(encoding="utf-8")

    assert '"peran": "papan-memanjang"' in teks
    assert teks.endswith("\n")
    assert json.loads(teks)["printer"] is None


def test_berkas_sementara_tidak_ditinggalkan(tmp_path):
    """Komputer publik sering dimatikan lewat tombol, bukan lewat menu."""
    path = tmp_path / "peran.json"
    tulis_peran(path, PeranKomputer(peran=TELEVISI))

    assert [p.name for p in tmp_path.iterdir()] == ["peran.json"]


def test_berkas_hilang_bukan_galat(tmp_path):
    assert baca_peran(tmp_path / "belum-ada.json") == PeranKomputer()


@pytest.mark.parametrize(
    "isi",
    [
        "{ bukan json",
        "",
        "[]",
        '"televisi"',
        "null",
    ],
)
def test_berkas_rusak_tidak_menjatuhkan_aplikasi(tmp_path, isi):
    """
    Komputer yang berkasnya rusak tetap harus bisa dibuka. Yang hilang
    hanya kenyamanannya — dialog pilih-mode kembali muncul.
    """
    path = tmp_path / "peran.json"
    path.write_text(isi, encoding="utf-8")

    assert baca_peran(path) == PeranKomputer()


def test_peran_salah_ketik_diperlakukan_belum_ditetapkan():
    assert dari_dict({"peran": "televisii"}) == PeranKomputer()


def test_isian_boolean_menerima_tulisan_manusia():
    """Berkas ini disunting di Notepad; "tidak" bukan sebuah kesalahan."""
    assert dari_dict({"peran": "televisi", "suara": "tidak"}).suara is False
    assert dari_dict({"peran": "televisi", "suara": "ya"}).suara is True
    assert dari_dict({"peran": "televisi", "suara": "entah"}).suara is None


def test_huruf_besar_kecil_tidak_menjadi_soal():
    assert dari_dict({"peran": "  Papan-Memanjang "}).peran == PAPAN_MEMANJANG


# ---------------------------------------------------------------------
# Letak berkas
# ---------------------------------------------------------------------

def test_berkas_mengikuti_folder_database(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTRIAN_PERAN_PATH", raising=False)

    hasil = path_berkas_peran(tmp_path / "data" / "queue.db")

    assert hasil == (tmp_path / "data" / "peran.json").resolve()


def test_environment_menimpa_letak_berkas(tmp_path, monkeypatch):
    lain = tmp_path / "lain" / "peran.json"
    monkeypatch.setenv("ANTRIAN_PERAN_PATH", str(lain))

    assert path_berkas_peran(tmp_path / "data" / "queue.db") == lain.resolve()


def test_peran_tidak_pernah_bersanding_dengan_mesin_json():
    """
    Berkas peran dirancang untuk DISALIN antar-komputer, sedangkan
    mesin.json memuat kata sandi database dan tidak boleh disalin. Nama
    berkasnya wajib berbeda supaya keduanya tidak pernah tertukar.
    """
    from app.core import mesin, peran

    assert peran.NAMA_BERKAS != mesin.NAMA_BERKAS


# ---------------------------------------------------------------------
# Nilai yang tidak dikenali
# ---------------------------------------------------------------------

def test_pencetak_yang_dikenali_sama_dengan_pilihan_di_pengaturan():
    """
    Ditulis ulang di app.core.peran karena core tidak bergantung pada
    lapisan service. Nilai yang berbeda berarti satu komputer menyimpan
    pencetak yang ditolak sisa sistem.
    """
    from app.core.peran import PENCETAK_SAH
    from app.services.settings_service import SKEMA

    butir = next(p for p in SKEMA if p.kunci == "ticket.printer")

    assert PENCETAK_SAH == {kode for kode, _ in butir.pilihan}


def test_bentuk_yang_dikenali_sama_dengan_pilihan_manual_di_pengaturan():
    from app.core.peran import BENTUK_SAH
    from app.services.settings_service import BENTUK_LAYAR_MANUAL

    assert BENTUK_SAH == set(BENTUK_LAYAR_MANUAL)


@pytest.mark.parametrize(
    ("kunci", "nilai"),
    [
        ("printer", "sistem"),      # salah ketik "system"
        ("printer", "epson"),
        ("bentuk_layar", "panjang"),  # salah ketik "memanjang"
        ("bentuk_layar", "16:9"),
    ],
)
def test_nilai_yang_tidak_dikenali_diperlakukan_seperti_tidak_diisi(kunci, nilai):
    """
    Sikap yang sama sudah dipakai `_bool_from_env` di app.core.config:
    salah ketik di satu komputer tidak boleh mengubah perilakunya tanpa
    jejak, dan tidak boleh pula membuatnya gagal dibuka.
    """
    hasil = dari_dict({"peran": TELEVISI, kunci: nilai})

    assert getattr(hasil, kunci) is None
    assert hasil.peran == TELEVISI


def test_salah_ketik_meninggalkan_jejak_di_log(caplog):
    with caplog.at_level("WARNING", logger="antrian.peran"):
        dari_dict({"peran": TELEVISI, "printer": "sistem"})

    assert "sistem" in caplog.text


# ---------------------------------------------------------------------
# Nama yang tampil
# ---------------------------------------------------------------------

def test_setiap_peran_punya_nama_yang_tampil():
    """
    Peran tanpa nama akan muncul sebagai ruang kosong di bilah status dan
    sebagai baris kosong di kotak pilihan.
    """
    from app.core.peran import LABEL

    assert set(LABEL) == PERAN_SAH
    assert all(LABEL[kode].strip() for kode in PERAN_SAH)


def test_belum_ditetapkan_tidak_punya_nama():
    """Ruang kosong lebih jujur daripada kata "(tidak ada)"."""
    assert PeranKomputer().label == ""


def test_mesin_yang_menyimpang_diberi_tanda():
    """
    Orang yang memasang tujuh komputer perlu melihat bahwa satu di
    antaranya tidak lagi sama dengan saudara-saudaranya.
    """
    biasa = PeranKomputer(peran=TELEVISI)
    menyimpang = PeranKomputer(peran=TELEVISI, suara=False)

    assert biasa.label == "Televisi ruang tunggu"
    assert menyimpang.label == "Televisi ruang tunggu (disesuaikan)"
