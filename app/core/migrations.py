"""
Menjalankan migration Alembic dari dalam aplikasi.

Aplikasi didistribusikan sebagai .exe, dan petugas tidak akan menjalankan
perintah alembic dari terminal. Karena itu migration dijalankan otomatis
saat aplikasi start.
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.core.config import get_config, resource_dir
from app.core.database import get_engine
from app.core.logger import get_logger, setup_logging

logger = get_logger("migrations")


def alembic_config() -> Config:
    """Config Alembic yang menunjuk database aktif aplikasi."""
    root = resource_dir()
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_config().database_url)
    return cfg


def current_revision() -> str | None:
    """Revisi yang sedang terpasang pada database, None bila masih kosong."""
    with get_engine().connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def head_revision() -> str | None:
    """Revisi terbaru yang tersedia pada folder migration."""
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def is_up_to_date() -> bool:
    return current_revision() == head_revision()


def upgrade_to_head() -> None:
    """
    Naikkan skema database ke revisi terbaru.

    Aman dipanggil berulang kali; bila sudah terbaru, tidak ada yang dikerjakan.
    """
    if is_up_to_date():
        logger.debug("Skema database sudah terbaru (%s)", current_revision())
        return

    logger.info("Migrasi skema: %s -> %s", current_revision(), head_revision())
    command.upgrade(alembic_config(), "head")
    # command.upgrade memuat env.py, yang pada CLI Alembic memanggil
    # fileConfig. Pulihkan handler aplikasi supaya jejak setelah migrasi
    # (termasuk --init-only) tetap masuk app.log.
    setup_logging(force=True)
    logger.info("Migrasi selesai")
