"""Test peran komputer ini terhadap database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core import config as config_module
from app.core.mesin import (
    HOST_LOKAL,
    KLIEN,
    SENDIRI,
    SERVER,
    alamat_ipv4_lokal,
    baca_berkas_mesin,
    kesalahan_isian,
    path_berkas_mesin,
    PengaturanMesin,
    pengaturan_dari_url,
    tulis_berkas_mesin,
    uji_koneksi,
    url_dari_berkas_mesin,
)


def test_path_berkas_mengikuti_folder_database(tmp_path: Path):
    """Test tidak boleh membaca mesin.json milik pengembang."""
    db = tmp_path / "data" / "queue.db"
    assert path_berkas_mesin(db) == (tmp_path / "data" / "mesin.json").resolve()


def test_path_berkas_dapat_ditimpa_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    tujuan = tmp_path / "lain" / "peran.json"
    monkeypatch.setenv("ANTRIAN_MESIN_PATH", str(tujuan))
    assert path_berkas_mesin(tmp_path / "queue.db") == tujuan.resolve()


def test_berkas_yang_belum_ada_berarti_belum_ditetapkan(tmp_path: Path):
    assert baca_berkas_mesin(tmp_path / "mesin.json") is None
    assert url_dari_berkas_mesin(tmp_path / "mesin.json") == ""


def test_simpan_dan_baca_server(tmp_path: Path):
    path = tmp_path / "mesin.json"
    tulis_berkas_mesin(
        path,
        PengaturanMesin(
            peran=SERVER,
            port=5432,
            nama_database="antrian",
            pengguna="antrian",
            sandi="rahasia",
        ),
    )
    terbaca = baca_berkas_mesin(path)
    assert terbaca is not None
    assert terbaca.peran == SERVER
    assert terbaca.sandi == "rahasia"
    url = url_dari_berkas_mesin(path)
    assert url.startswith("postgresql+psycopg://")
    assert HOST_LOKAL in url
    assert "rahasia" in url
    assert "192.168" not in url


def test_server_menyambung_ke_localhost_bukan_ip_lan():
    """
    Firewall dan pg_hba sering menolak mesin yang memutar balik lewat
    alamat LAN-nya sendiri. IP jaringan hanya untuk disalin ke klien.
    """
    url = PengaturanMesin(peran=SERVER, host="192.168.1.10", sandi="x").ke_url()
    assert "127.0.0.1" in url
    assert "192.168.1.10" not in url


def test_klien_menulis_alamat_yang_diisi(tmp_path: Path):
    path = tmp_path / "mesin.json"
    tulis_berkas_mesin(
        path,
        PengaturanMesin(
            peran=KLIEN,
            host="192.168.1.10",
            pengguna="antrian_kios",
            sandi="sandi-kios",
        ),
    )
    url = url_dari_berkas_mesin(path)
    assert "192.168.1.10" in url
    assert "antrian_kios" in url


def test_klien_tanpa_alamat_tidak_boleh_disimpan():
    assert kesalahan_isian(PengaturanMesin(peran=KLIEN, host=""))


def test_klien_tanpa_alamat_di_berkas_diabaikan(tmp_path: Path):
    """Berkas rusak tidak boleh diam-diam menyambung ke host kosong."""
    path = tmp_path / "mesin.json"
    path.write_text(
        json.dumps({"peran": "klien", "host": "", "port": 5432}),
        encoding="utf-8",
    )
    assert url_dari_berkas_mesin(path) == ""


def test_sendiri_tidak_menghasilkan_url_postgres(tmp_path: Path):
    path = tmp_path / "mesin.json"
    tulis_berkas_mesin(path, PengaturanMesin(peran=SENDIRI))
    assert url_dari_berkas_mesin(path) == ""


def test_json_rusak_diabaikan(tmp_path: Path):
    path = tmp_path / "mesin.json"
    path.write_text("{bukan json", encoding="utf-8")
    assert baca_berkas_mesin(path) is None
    assert url_dari_berkas_mesin(path) == ""


def test_peran_asing_diabaikan(tmp_path: Path):
    path = tmp_path / "mesin.json"
    path.write_text(json.dumps({"peran": "ketua"}), encoding="utf-8")
    assert baca_berkas_mesin(path) is None


def test_kata_sandi_tidak_masuk_ringkasan():
    teks = PengaturanMesin(peran=KLIEN, host="10.0.0.5", sandi="rahasia-besar").ringkasan()
    assert "rahasia-besar" not in teks
    assert "10.0.0.5" in teks


def test_kata_sandi_berkarakter_khusus_tetap_sah():
    url = PengaturanMesin(
        peran=KLIEN, host="192.168.1.10", sandi="a@b/c:d"
    ).ke_url()
    terurai = pengaturan_dari_url(url)
    assert terurai.sandi == "a@b/c:d"
    assert terurai.host == "192.168.1.10"
    assert terurai.peran == KLIEN


def test_url_localhost_dianggap_server():
    pengaturan = pengaturan_dari_url(
        "postgresql+psycopg://antrian:x@127.0.0.1:5432/antrian"
    )
    assert pengaturan.peran == SERVER
    assert pengaturan.host == ""


def test_url_sqlite_dianggap_sendiri(tmp_path: Path):
    pengaturan = pengaturan_dari_url(f"sqlite:///{tmp_path / 'queue.db'}")
    assert pengaturan.peran == SENDIRI


def test_alamat_lokal_tidak_memuat_loopback():
    for ip in alamat_ipv4_lokal():
        assert not ip.startswith("127.")
        assert not ip.startswith("169.254.")


def test_uji_koneksi_sqlite_berhasil():
    assert uji_koneksi("sqlite:///:memory:") is None


def test_uji_koneksi_yang_gagal_berbahasa_indonesia():
    pesan = uji_koneksi("postgresql+psycopg://x:y@127.0.0.1:1/tidakada")
    assert pesan is not None
    assert "traceback" not in pesan.lower()
    assert "Tidak dapat menghubungi database" in pesan


def test_pesan_sandi_tidak_disalahkan_sebagai_jaringan():
    from app.core.mesin import pesan_kegagalan_koneksi

    pesan = pesan_kegagalan_koneksi(
        Exception('password authentication failed for user "antrian"')
    )

    assert "pengguna antrian" in pesan.lower()
    assert "jaringan yang sama" not in pesan.lower()
    assert "password authentication" not in pesan


def test_pindai_melewati_komputer_ini_dan_tidak_memilih_sendiri():
    """Lebih dari satu jawaban dikembalikan apa adanya, tanpa pemenang."""
    from app.core.mesin import cari_server_jaringan

    dipanggil: list[str] = []

    def periksa(ip: str) -> bool:
        dipanggil.append(ip)
        return ip in {"192.168.1.20", "192.168.1.30"}

    hasil = cari_server_jaringan(alamat=("192.168.1.5",), pemeriksa=periksa)

    assert hasil == ("192.168.1.20", "192.168.1.30")
    assert "192.168.1.5" not in dipanggil
    assert len(dipanggil) == 253


def test_izin_jaringan_hanya_subnet_kantor_dan_tidak_trust(tmp_path: Path):
    from app.core.mesin import tambahan_izin_hba

    isi = "host    all    all    127.0.0.1/32    scram-sha-256\n"
    tambahan = tambahan_izin_hba(isi, ("192.168.1.0/24",))

    assert "192.168.1.0/24" in tambahan
    assert "antrian" in tambahan
    assert "scram-sha-256" in tambahan
    assert "trust" not in tambahan
    assert "0.0.0.0/0" not in tambahan
    assert tambahan_izin_hba(isi + tambahan, ("192.168.1.0/24",)) == ""


def test_siapkan_tanpa_sandi_tidak_menyambung():
    from app.core.mesin import siapkan_database_lokal

    hasil = siapkan_database_lokal("", "sandi-postgres")

    assert hasil.gagal
    assert hasil.peringatan is None


def test_berkas_mesin_dipakai_bila_url_kosong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db = tmp_path / "queue.db"
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(db))
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)
    monkeypatch.delenv("ANTRIAN_MESIN_PATH", raising=False)
    tulis_berkas_mesin(
        path_berkas_mesin(db),
        PengaturanMesin(peran=KLIEN, host="192.168.1.10", sandi="x"),
    )
    config_module.reset_config()
    cfg = config_module.load_config()
    assert cfg.dialect == "postgresql"
    assert cfg.url_database.host == "192.168.1.10"
    assert "x" not in cfg.teks_lokasi
    config_module.reset_config()


def test_url_environment_mengalahkan_berkas_mesin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Pemasangan lama lewat setx tidak boleh berubah diam-diam."""
    db = tmp_path / "queue.db"
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(db))
    monkeypatch.setenv(
        "ANTRIAN_DB_URL",
        "postgresql+psycopg://petugas:sandi@server-lama:5432/antrian",
    )
    tulis_berkas_mesin(
        path_berkas_mesin(db),
        PengaturanMesin(peran=KLIEN, host="192.168.1.10", sandi="x"),
    )
    config_module.reset_config()
    cfg = config_module.load_config()
    assert cfg.url_database.host == "server-lama"
    config_module.reset_config()
