"""
Koneksi database SQLite.

Yang ditegakkan di sini:

* foreign_keys = ON     SQLite mematikan penegakan foreign key secara default.
                        Tanpa ini, relasi antar tabel tidak dijaga sama sekali.
* journal_mode = WAL    Pembaca tidak memblokir penulis. Penting karena layar
                        display membaca terus-menerus sementara petugas menulis.
* busy_timeout          Menunggu kunci alih-alih langsung gagal.
* BEGIN eksplisit       pysqlite secara default memulai transaksi secara
                        implisit dan tidak memungkinkan BEGIN IMMEDIATE.
                        Perilaku itu dimatikan agar penomoran antrian
                        (Phase 4) dapat mengunci baris sequence dengan benar.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import AppConfig, get_config
from app.core.logger import get_logger

logger = get_logger("database")

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _configure_connection(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """Pasang PRAGMA pada setiap koneksi baru."""
    # Matikan manajemen transaksi implisit milik pysqlite supaya PRAGMA
    # di bawah ini berjalan di luar transaksi dan BEGIN dapat dikendalikan.
    dbapi_connection.isolation_level = None

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


#: Nama execution option untuk memilih mode BEGIN pada SQLite.
BEGIN_MODE_OPTION = "sqlite_begin_mode"


def _emit_begin(conn) -> None:  # noqa: ANN001
    """
    Mulai transaksi secara eksplisit (menggantikan perilaku pysqlite).

    Mode BEGIN harus ditentukan di sini, bukan lewat statement terpisah.
    Statement apa pun yang dijalankan pada Connection akan otomatis membuka
    transaksi terlebih dahulu, sehingga "BEGIN IMMEDIATE" yang dikirim
    belakangan pasti ditolak dengan "cannot start a transaction within a
    transaction".
    """
    mode = conn.get_execution_options().get(BEGIN_MODE_OPTION, "")
    conn.exec_driver_sql(f"BEGIN {mode}".strip())


def create_engine(config: AppConfig | None = None) -> Engine:
    """Buat engine baru lengkap dengan seluruh PRAGMA dan hook transaksi."""
    config = config or get_config()
    config.ensure_directories()

    engine = sa.create_engine(
        config.database_url,
        future=True,
        # check_same_thread=False dibutuhkan karena UI Qt dapat mengakses
        # database dari thread selain thread utama.
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _configure_connection)
    event.listen(engine, "begin", _emit_begin)
    return engine


def get_engine() -> Engine:
    """Engine aktif aplikasi (dibuat sekali, lalu dipakai ulang)."""
    global _engine
    if _engine is None:
        _engine = create_engine()
        logger.info("Engine database dibuat: %s", get_config().db_path)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Pabrik Session yang terikat pada engine aktif."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    Satu unit kerja transaksional.

    Commit bila blok selesai tanpa error, rollback bila terjadi exception.
    Session selalu ditutup.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def begin_immediate() -> Iterator[sa.Connection]:
    """
    Transaksi tulis dengan kunci yang diambil SEJAK AWAL.

    BEGIN IMMEDIATE mencegah dua proses membaca nilai sequence yang sama lalu
    sama-sama menuliskan nomor antrian kembar. Dipakai oleh Phase 4.
    """
    conn = get_engine().connect().execution_options(
        **{BEGIN_MODE_OPTION: "IMMEDIATE"}
    )
    try:
        with conn.begin():
            yield conn
    finally:
        conn.close()


def dispose_engine() -> None:
    """
    Tutup seluruh koneksi dan lepaskan file database.

    Wajib dipanggil sebelum restore database (Phase 8); Windows tidak
    mengizinkan file yang masih terbuka untuk ditimpa.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        logger.info("Engine database ditutup")
    _engine = None
    _session_factory = None


def init_database() -> Engine:
    """
    Siapkan database agar siap dipakai.

    Skema dibuat lewat migration Alembic, bukan create_all(), supaya update
    aplikasi di kemudian hari tidak menghapus data antrian dan survey.
    """
    from app.core.migrations import upgrade_to_head

    engine = get_engine()
    upgrade_to_head()
    logger.info("Database siap digunakan")
    return engine
