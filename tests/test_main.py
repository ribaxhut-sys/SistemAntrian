"""Test titik masuk aplikasi."""

from __future__ import annotations

from pathlib import Path

from app.core import config as config_module
from app.core import database as database_module
from app.core import logger as logger_module
from app.main import main


def test_init_only_mencatat_fondasi_siap_ke_log(
    tmp_path: Path, monkeypatch
) -> None:
    """
    A3b: komputer baru menjalankan --init-only lalu membaca app.log.

    fileConfig Alembic pernah menimpa logging sehingga baris itu hilang
    tepat pada pemasangan pertama — satu-satunya saat pemeriksaan ini
    benar-benar dibutuhkan.
    """
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(tmp_path / "queue.db"))
    monkeypatch.setenv("ANTRIAN_BACKUP_DIR", str(tmp_path / "backup"))
    monkeypatch.setenv("ANTRIAN_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)

    config_module.reset_config()
    database_module.dispose_engine()
    logger_module._configured = False

    assert main(["--init-only"]) == 0

    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "Fondasi siap" in log
    assert "Migrasi selesai" in log
    assert "admin123" not in log.lower()


# ---------------------------------------------------------------------
# Mode mesin dari baris perintah
# ---------------------------------------------------------------------

def test_tanpa_argumen_mode_ditanyakan() -> None:
    """None berarti dialog pilihan yang menentukan, bukan mode bawaan."""
    from app.main import mode_dari_argumen

    assert mode_dari_argumen([]) is None
    assert mode_dari_argumen(["--init-only"]) is None


def test_argumen_membuka_mesin_yang_sesuai() -> None:
    from app.main import mode_dari_argumen
    from app.ui.login.mode_dialog import ANJUNGAN, LAYAR_ANTRIAN

    assert mode_dari_argumen(["--tv"]) == LAYAR_ANTRIAN
    assert mode_dari_argumen(["--kios"]) == ANJUNGAN


def test_pintasan_lama_layar_tetap_membuka_anjungan() -> None:
    """
    `--layar` sudah terpasang pada shortcut Startup komputer anjungan.

    Memutusnya saat aplikasi diperbarui berarti mesin itu berhenti di
    dialog pilihan setiap mati listrik — tepat keadaan yang argumen ini
    diciptakan untuk mencegah.
    """
    from app.main import mode_dari_argumen
    from app.ui.login.mode_dialog import ANJUNGAN

    assert mode_dari_argumen(["--layar"]) == ANJUNGAN


def test_layar_antrian_didahulukan_bila_dua_argumen_tertulis() -> None:
    """
    Papan kosong terlihat seluruh ruang tunggu, sedangkan anjungan yang
    keliru masih bisa digantikan petugas yang menerbitkan nomor dari
    mejanya.
    """
    from app.main import mode_dari_argumen
    from app.ui.login.mode_dialog import LAYAR_ANTRIAN

    assert mode_dari_argumen(["--kios", "--tv"]) == LAYAR_ANTRIAN
