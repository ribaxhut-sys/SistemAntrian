"""
Konfigurasi environment Alembic.

URL database TIDAK diambil dari alembic.ini melainkan dari app.core.config,
supaya migration selalu menunjuk database yang sama dengan yang dipakai
aplikasi, termasuk ketika lokasinya diubah lewat environment variable.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Pastikan package app dapat diimpor saat alembic dijalankan dari CLI.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_config  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_config().database_url)

target_metadata = Base.metadata


def _configure(**kwargs) -> None:
    """
    Opsi yang berlaku untuk mode offline maupun online.

    render_as_batch WAJIB untuk SQLite. SQLite hampir tidak mendukung
    ALTER TABLE, sehingga Alembic perlu membuat tabel baru, menyalin data,
    lalu menukarnya. Tanpa opsi ini, perubahan kolom di kemudian hari akan
    gagal total.
    """
    context.configure(
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # JANGAN menjalankan PRAGMA di sini. Statement apa pun sebelum
        # context.configure() akan membuka transaksi implisit, sehingga baris
        # alembic_version ikut ter-rollback saat koneksi ditutup: skema
        # terbentuk tetapi versinya tidak tercatat, dan migration akan
        # dijalankan ulang terus-menerus.
        #
        # foreign_keys sengaja dibiarkan OFF selama migration. Mode batch
        # SQLite membangun ulang tabel lalu menukarnya, dan penegakan foreign
        # key selama proses itu justru menggagalkan perubahan skema.
        # Penegakan foreign key tetap aktif pada engine aplikasi.
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
