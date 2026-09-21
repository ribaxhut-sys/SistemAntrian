"""Test konfigurasi aplikasi."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import config as config_module
from app.core.config import TIMEZONE, load_config, teks_status_database


def test_default_paths_berada_di_bawah_base_dir(monkeypatch: pytest.MonkeyPatch):
    for var in ("ANTRIAN_DB_PATH", "ANTRIAN_BACKUP_DIR", "ANTRIAN_LOG_DIR"):
        monkeypatch.delenv(var, raising=False)
    config_module.reset_config()

    cfg = load_config()
    assert cfg.db_path == cfg.base_dir / "data" / "queue.db"
    assert cfg.backup_dir == cfg.base_dir / "backup"
    assert cfg.log_dir == cfg.base_dir / "logs"


def test_path_database_dapat_diubah_tanpa_mengubah_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Syarat operasional: lokasi database diatur lewat environment variable."""
    target = tmp_path / "lokasi-lain" / "antrian.db"
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(target))
    # Yang diuji di sini adalah jalur cadangan ke SQLite, sehingga URL penuh
    # harus dikosongkan — bila diisi, ia memang seharusnya menang.
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)
    config_module.reset_config()

    cfg = load_config()
    assert cfg.db_path == target.resolve()
    assert cfg.database_url == f"sqlite:///{target.resolve()}"
    assert cfg.memakai_sqlite


def test_url_database_menang_atas_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Beberapa loket yang melayani bersamaan wajib memakai PostgreSQL.

    ANTRIAN_DB_URL sengaja mengalahkan ANTRIAN_DB_PATH: komputer yang sudah
    diarahkan ke server tidak boleh diam-diam kembali memakai berkas SQLite
    lokal hanya karena variabel lama tertinggal.
    """
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(tmp_path / "antrian.db"))
    monkeypatch.setenv(
        "ANTRIAN_DB_URL", "postgresql+psycopg://petugas:sandi@server:5432/antrian"
    )
    config_module.reset_config()

    cfg = load_config()
    assert cfg.dialect == "postgresql"
    assert not cfg.memakai_sqlite
    assert cfg.url_database.host == "server"
    assert cfg.url_database.database == "antrian"
    assert cfg.teks_lokasi == "PostgreSQL @ server:5432/antrian"
    assert "sandi" not in cfg.teks_lokasi
    assert "petugas" not in cfg.teks_lokasi


def test_teks_status_postgres_mati_tetap_menunjuk_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    Server yang mati bukan alasan menampilkan path SQLite lokal.

    Petugas harus tetap melihat host yang dituju, supaya yang diperiksa
    adalah komputer server — bukan berkas queue.db yang kebetulan ada di
    mesin loket.
    """
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(tmp_path / "queue.db"))
    monkeypatch.setenv(
        "ANTRIAN_DB_URL",
        "postgresql+psycopg://antrian:rahasia@192.168.1.10:5432/antrian",
    )
    config_module.reset_config()
    cfg = load_config()

    teks = teks_status_database(False, cfg)
    assert teks == (
        "Database tidak terjangkau (PostgreSQL @ 192.168.1.10:5432/antrian) "
        "— cek komputer server"
    )
    assert "rahasia" not in teks
    assert "queue.db" not in teks


def test_teks_lokasi_sqlite_adalah_path_berkas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = tmp_path / "lokasi-lain" / "antrian.db"
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(target))
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)
    config_module.reset_config()

    cfg = load_config()
    assert cfg.teks_lokasi == str(target.resolve())
    assert teks_status_database(True, cfg) == f"Database: {cfg.teks_lokasi}"
    assert teks_status_database(False, cfg) == (
        f"Database tidak terjangkau ({cfg.teks_lokasi})"
    )


def test_ensure_directories_membuat_folder_yang_belum_ada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(tmp_path / "db" / "queue.db"))
    monkeypatch.setenv("ANTRIAN_BACKUP_DIR", str(tmp_path / "bk"))
    monkeypatch.setenv("ANTRIAN_LOG_DIR", str(tmp_path / "lg"))
    config_module.reset_config()

    cfg = load_config()
    cfg.ensure_directories()

    assert cfg.db_path.parent.is_dir()
    assert cfg.backup_dir.is_dir()
    assert cfg.log_dir.is_dir()


def test_timezone_terkunci_asia_jakarta():
    assert TIMEZONE == "Asia/Jakarta"


# ---------------------------------------------------------------------
# Setelan per mesin
# ---------------------------------------------------------------------

def test_pencetak_dan_suara_kosong_bila_mesin_tidak_berpendapat(env_mesin):
    """
    Mesin yang tidak menyebut apa-apa mengikuti pengaturan bersama.

    None BUKAN False: mendiamkan seluruh mesin hanya karena variabelnya
    tidak diisi akan membuat sistem yang baru dipasang tampak rusak.
    """
    cfg = env_mesin(ANTRIAN_PRINTER=None, ANTRIAN_SUARA=None)

    assert cfg.printer == ""
    assert cfg.suara is None


@pytest.mark.parametrize("nilai", ["1", "true", "TRUE", "ya", "yes", "on"])
def test_suara_dinyalakan_dari_environment(env_mesin, nilai: str):
    assert env_mesin(ANTRIAN_SUARA=nilai).suara is True


@pytest.mark.parametrize("nilai", ["0", "false", "FALSE", "tidak", "no", "off"])
def test_suara_dimatikan_dari_environment(env_mesin, nilai: str):
    assert env_mesin(ANTRIAN_SUARA=nilai).suara is False


@pytest.mark.parametrize("nilai", ["mungkin", "-", "2", " "])
def test_nilai_suara_yang_tidak_dikenal_dianggap_tidak_diisi(env_mesin, nilai: str):
    """
    Salah ketik di satu komputer tidak boleh mendiamkan panggilan tanpa
    jejak. Lebih baik jatuh ke pengaturan bersama yang terlihat di layar
    Pengaturan daripada diam karena sebuah variabel yang tak seorang pun
    ingat pernah diisi.
    """
    assert env_mesin(ANTRIAN_SUARA=nilai).suara is None


def test_pencetak_mesin_dibaca_apa_adanya(env_mesin):
    assert env_mesin(ANTRIAN_PRINTER="system").printer == "system"


def test_lewati_login_menyala_dari_source(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTRIAN_LEWATI_LOGIN", raising=False)
    monkeypatch.setattr(config_module.sys, "frozen", False, raising=False)
    from app.core.config import lewati_login_pengembang

    assert lewati_login_pengembang() is True


def test_lewati_login_mati_pada_exe(monkeypatch: pytest.MonkeyPatch):
    """Lupa mencabut pintasan tidak boleh membuka .exe petugas tanpa kunci."""
    monkeypatch.setenv("ANTRIAN_LEWATI_LOGIN", "1")
    monkeypatch.setattr(config_module.sys, "frozen", True, raising=False)
    from app.core.config import lewati_login_pengembang

    assert lewati_login_pengembang() is False


def test_lewati_login_dapat_dimatikan_dari_environment(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("ANTRIAN_LEWATI_LOGIN", "0")
    monkeypatch.setattr(config_module.sys, "frozen", False, raising=False)
    from app.core.config import lewati_login_pengembang

    assert lewati_login_pengembang() is False


# ---------------------------------------------------------------------
# Peran mesin mengisi yang tidak disebut environment
# ---------------------------------------------------------------------

@pytest.fixture
def mesin_berperan(tmp_path, monkeypatch):
    """Sebuah komputer dengan peran.json, tanpa environment apa pun."""
    from app.core.config import reset_config
    from app.core.peran import PeranKomputer, tulis_peran

    folder = tmp_path / "data"
    folder.mkdir(parents=True)
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(folder / "queue.db"))
    for nama in ("ANTRIAN_PRINTER", "ANTRIAN_SUARA", "ANTRIAN_BENTUK_LAYAR"):
        monkeypatch.delenv(nama, raising=False)
    monkeypatch.delenv("ANTRIAN_PERAN_PATH", raising=False)

    def pasang(**isian):
        tulis_peran(folder / "peran.json", PeranKomputer(**isian))
        reset_config()
        from app.core.config import load_config

        return load_config()

    yield pasang
    reset_config()


def test_peran_televisi_mematikan_pencetak(mesin_berperan):
    """Tidak ada pencetak yang menempel pada komputer televisi."""
    cfg = mesin_berperan(peran="televisi")

    assert cfg.printer == "none"
    assert cfg.suara is None
    assert cfg.bentuk_layar == ""


def test_peran_anjungan_mendiamkan_mesinnya(mesin_berperan):
    cfg = mesin_berperan(peran="anjungan")

    assert cfg.suara is False
    # Anjungan memang mencetak, tetapi caranya keputusan seluruh kantor.
    assert cfg.printer == ""


def test_peran_papan_memanjang_membawa_bentuk_layarnya(mesin_berperan):
    cfg = mesin_berperan(peran="papan-memanjang")

    assert cfg.bentuk_layar == "memanjang"
    assert cfg.suara is False


def test_environment_tetap_mengalahkan_berkas_peran(mesin_berperan, monkeypatch):
    """
    Pemasangan yang sudah memakai `setx` jauh sebelum berkas peran ada
    harus berperilaku sama persis sesudahnya.
    """
    monkeypatch.setenv("ANTRIAN_PRINTER", "system")
    monkeypatch.setenv("ANTRIAN_SUARA", "1")
    monkeypatch.setenv("ANTRIAN_BENTUK_LAYAR", "tegak")

    cfg = mesin_berperan(peran="papan-memanjang")

    assert cfg.printer == "system"
    assert cfg.suara is True
    assert cfg.bentuk_layar == "tegak"


def test_tanpa_berkas_peran_tidak_ada_yang_berubah(mesin_berperan, tmp_path):
    """Komputer yang belum ditetapkan berperilaku seperti sebelum fitur ini."""
    from app.core.config import load_config, reset_config

    reset_config()
    cfg = load_config()

    assert cfg.printer == ""
    assert cfg.suara is None
    assert cfg.bentuk_layar == ""
