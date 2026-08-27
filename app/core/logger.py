"""
Logging aplikasi.

Aturan (lihat §47 spesifikasi): user TIDAK PERNAH melihat traceback.
Detail teknis masuk ke file log, user hanya menerima pesan yang manusiawi.

Jangan pernah menuliskan password, hash password, atau kredensial apa pun
ke dalam log.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.core import clock
from app.core.config import AppConfig, get_config

APP_LOGGER = "antrian"
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB per file
_BACKUP_COUNT = 5

_configured = False


class _WibFormatter(logging.Formatter):
    """Formatter yang mencetak waktu WIB, bukan waktu lokal komputer."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        moment = clock.now()
        return moment.strftime(datefmt) if datefmt else moment.strftime("%Y-%m-%d %H:%M:%S")


def setup_logging(config: AppConfig | None = None, *, force: bool = False) -> logging.Logger:
    """
    Pasang handler file (rotating) dan console pada root logger.

    Aman dipanggil berkali-kali; pemasangan hanya terjadi sekali kecuali
    force=True.
    """
    global _configured
    if _configured and not force:
        return logging.getLogger(APP_LOGGER)

    config = config or get_config()
    config.ensure_directories()

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    level = getattr(logging, config.log_level, logging.INFO)
    root.setLevel(level)

    formatter = _WibFormatter(_LOG_FORMAT)

    file_handler = RotatingFileHandler(
        config.log_dir / "app.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    # SQLAlchemy sangat berisik pada level INFO.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Hidupkan kembali logger aplikasi yang mungkin telah dimatikan.
    #
    # `fileConfig` milik Alembic berjalan dengan disable_existing_loggers
    # bawaannya, yang menyetel `disabled = True` pada setiap logger yang
    # sudah terlanjur dibuat. Memasang ulang handler saja TIDAK memulihkan
    # keadaan itu: pesannya berhenti di logger yang mati, jauh sebelum
    # sampai ke handler mana pun, sehingga app.log hanya berisi baris
    # milik Alembic sendiri. Pada kios yang berdiri tanpa penjaga, log
    # adalah satu-satunya keterangan yang tertinggal ketika ada yang
    # salah — kehilangannya diam-diam jauh lebih mahal daripada
    # pemeriksaan singkat ini.
    for nama, butir in logging.Logger.manager.loggerDict.items():
        if isinstance(butir, logging.Logger) and nama.startswith(APP_LOGGER):
            butir.disabled = False

    _configured = True
    return logging.getLogger(APP_LOGGER)


def get_logger(name: str | None = None) -> logging.Logger:
    """Logger bernama, selalu berada di bawah namespace aplikasi."""
    return logging.getLogger(APP_LOGGER if name is None else f"{APP_LOGGER}.{name}")
