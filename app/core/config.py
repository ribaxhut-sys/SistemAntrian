"""
Konfigurasi aplikasi.

Path database, backup, dan log dapat diubah TANPA mengubah source code,
yaitu lewat environment variable. Ini penting karena aplikasi didistribusikan
sebagai .exe dan lokasi penyimpanan bisa berbeda di tiap komputer.

Environment variable yang dikenali:
    ANTRIAN_DB_PATH      lokasi file database SQLite
    ANTRIAN_BACKUP_DIR   folder hasil backup
    ANTRIAN_LOG_DIR      folder file log
    ANTRIAN_LOG_LEVEL    DEBUG | INFO | WARNING | ERROR
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Sistem Antrian CRO"
APP_SLUG = "antrian-cro"

# Timezone operasional. Seluruh timestamp transaksi memakai zona ini,
# bukan zona komputer, agar konsisten di mesin mana pun.
TIMEZONE = "Asia/Jakarta"


def base_dir() -> Path:
    """
    Folder acuan aplikasi.

    Saat dijalankan sebagai .exe hasil PyInstaller, __file__ menunjuk ke
    folder temporary yang isinya terhapus setiap aplikasi ditutup. Karena itu
    lokasi .exe yang dipakai sebagai acuan, bukan __file__.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def resource_dir() -> Path:
    """
    Folder berkas bawaan yang hanya dibaca, yaitu alembic.ini dan alembic/.

    Berbeda dari `base_dir()` dan wajib dibedakan. PyInstaller membongkar
    berkas bundelnya ke folder temporary (`sys._MEIPASS`), sedangkan database,
    backup, dan log harus tetap berada di sebelah .exe agar tidak ikut
    terhapus setiap aplikasi ditutup.

    Saat dijalankan dari source, keduanya menunjuk folder yang sama.
    """
    bundel = getattr(sys, "_MEIPASS", None)
    return Path(bundel) if bundel else base_dir()


def _path_from_env(var: str, default: Path) -> Path:
    raw = os.environ.get(var, "").strip()
    return Path(raw).expanduser().resolve() if raw else default


@dataclass(frozen=True)
class AppConfig:
    """Konfigurasi runtime yang sudah di-resolve menjadi path absolut."""

    base_dir: Path
    db_path: Path
    backup_dir: Path
    log_dir: Path
    log_level: str
    timezone: str = TIMEZONE

    @property
    def database_url(self) -> str:
        """URL SQLAlchemy untuk SQLite."""
        return f"sqlite:///{self.db_path}"

    def ensure_directories(self) -> None:
        """Buat folder yang dibutuhkan bila belum ada."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    """Bangun konfigurasi dari environment variable dengan default yang aman."""
    root = base_dir()
    return AppConfig(
        base_dir=root,
        db_path=_path_from_env("ANTRIAN_DB_PATH", root / "data" / "queue.db"),
        backup_dir=_path_from_env("ANTRIAN_BACKUP_DIR", root / "backup"),
        log_dir=_path_from_env("ANTRIAN_LOG_DIR", root / "logs"),
        log_level=os.environ.get("ANTRIAN_LOG_LEVEL", "INFO").upper(),
    )


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Konfigurasi aktif (dibuat sekali, lalu dipakai ulang)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Paksa konfigurasi dibaca ulang. Dipakai oleh test dan fitur restore."""
    global _config
    _config = None
