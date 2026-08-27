"""Test konfigurasi aplikasi."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import config as config_module
from app.core.config import TIMEZONE, load_config


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
