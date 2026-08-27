"""
Koneksi database.

Mendukung dua dialect. SQLite untuk pemasangan satu komputer dan untuk
seluruh test; PostgreSQL untuk kantor dengan beberapa loket yang melayani
bersamaan — SQLite tidak sanggup melayani beberapa komputer sekaligus.

PRAGMA khusus SQLite yang ditegakkan di sini:

* foreign_keys = ON     SQLite mematikan penegakan foreign key secara default.
                        Tanpa ini, relasi antar tabel tidak dijaga sama sekali.
* journal_mode = WAL    Pembaca tidak memblokir penulis. Penting karena layar
                        display membaca terus-menerus sementara petugas menulis.
* busy_timeout          Menunggu kunci alih-alih langsung gagal.

PostgreSQL tidak membutuhkan satu pun dari itu: foreign key selalu
ditegakkan, pembaca memang tidak pernah memblokir penulis, dan antrian
kunci ditangani server.
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
    """Pasang PRAGMA pada setiap koneksi SQLite baru."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def create_engine(config: AppConfig | None = None) -> Engine:
    """Buat engine baru sesuai dialect database yang dipakai."""
    config = config or get_config()
    config.ensure_directories()

    if config.memakai_sqlite:
        engine = sa.create_engine(
            config.database_url,
            future=True,
            # check_same_thread=False dibutuhkan karena UI Qt dapat mengakses
            # database dari thread selain thread utama.
            connect_args={"check_same_thread": False},
        )
        event.listen(engine, "connect", _configure_connection)
        return engine

    return sa.create_engine(
        config.database_url,
        future=True,
        # pool_pre_ping wajib untuk koneksi lewat jaringan. Koneksi yang
        # sudah putus — server sempat restart, kabel tercabut, switch
        # memutus sesi menganggur — tidak memberi tahu klien. Tanpa ini,
        # kegagalannya baru terasa saat petugas menekan tombol.
        pool_pre_ping=True,
        # Loket yang menganggur tidak perlu menggenggam koneksi semalaman.
        pool_recycle=1800,
    )


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
def transaksi_tulis() -> Iterator[sa.Connection]:
    """
    Satu transaksi tulis pada Connection mentah, di luar ORM.

    Dipakai penomoran antrian, yang memerlukan SQL apa adanya dan tidak
    boleh ikut menunggu unit kerja lain. Keamanan terhadap penulis
    bersamaan TIDAK bergantung pada mode transaksi di sini, melainkan pada
    satu pernyataan upsert atomik di dalamnya — lihat `terbitkan_nomor`.
    """
    conn = get_engine().connect()
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
