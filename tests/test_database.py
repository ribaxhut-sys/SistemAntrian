"""Test koneksi dan integritas database."""

from __future__ import annotations

import sqlalchemy as sa
import pytest

from app.core.database import (
    begin_immediate,
    dispose_engine,
    get_engine,
    session_scope,
)


def test_wal_mode_aktif(database):
    """Pembaca (layar display) tidak boleh memblokir penulis (petugas)."""
    with get_engine().connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode.lower() == "wal"


def test_foreign_keys_ditegakkan(database):
    """
    SQLite mematikan penegakan foreign key secara default.

    Test ini membuktikan PRAGMA sudah dipasang: menyisipkan baris dengan
    branch_id yang tidak ada harus DITOLAK.
    """
    from app.models import Counter

    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as session:
            session.add(Counter(branch_id=99999, code="X", name="Loket Hantu"))


def test_busy_timeout_terpasang(database):
    with get_engine().connect() as conn:
        timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert timeout >= 5000


def test_integrity_check_bersih(database):
    with get_engine().connect() as conn:
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"


def test_session_scope_commit_saat_sukses(seeded):
    from app.models import ApplicationSetting

    with session_scope() as session:
        session.add(ApplicationSetting(key="uji.commit", value="1"))

    with session_scope() as session:
        found = session.scalar(
            sa.select(ApplicationSetting).where(ApplicationSetting.key == "uji.commit")
        )
        assert found is not None


def test_session_scope_rollback_saat_error(seeded):
    """Kegagalan di tengah unit kerja tidak boleh menyisakan data separuh jadi."""
    from app.models import ApplicationSetting

    with pytest.raises(RuntimeError):
        with session_scope() as session:
            session.add(ApplicationSetting(key="uji.rollback", value="1"))
            session.flush()
            raise RuntimeError("gagal di tengah jalan")

    with session_scope() as session:
        found = session.scalar(
            sa.select(ApplicationSetting).where(
                ApplicationSetting.key == "uji.rollback"
            )
        )
        assert found is None


def test_begin_immediate_menulis_dan_commit(seeded):
    """
    Mekanisme kunci yang dipakai penomoran antrian pada Phase 4.

    Di sini hanya diuji bahwa transaksinya benar-benar commit; uji
    konkurensi penuh dilakukan pada Phase 4.
    """
    from app.models import ApplicationSetting

    with begin_immediate() as conn:
        conn.execute(
            sa.insert(ApplicationSetting).values(key="uji.immediate", value="ok")
        )

    with session_scope() as session:
        found = session.scalar(
            sa.select(ApplicationSetting).where(
                ApplicationSetting.key == "uji.immediate"
            )
        )
        assert found is not None and found.value == "ok"


def test_begin_immediate_rollback_saat_error(seeded):
    from app.models import ApplicationSetting

    with pytest.raises(RuntimeError):
        with begin_immediate() as conn:
            conn.execute(
                sa.insert(ApplicationSetting).values(key="uji.batal", value="x")
            )
            raise RuntimeError("batal")

    with session_scope() as session:
        assert (
            session.scalar(
                sa.select(ApplicationSetting).where(
                    ApplicationSetting.key == "uji.batal"
                )
            )
            is None
        )


def test_dispose_engine_melepas_file_database(database):
    """
    Wajib berfungsi sebelum fitur restore (Phase 8).

    Windows menolak menimpa file yang koneksinya masih terbuka.
    """
    get_engine()
    dispose_engine()

    db_file = database.db_path
    renamed = db_file.with_suffix(".db.lepas")
    db_file.rename(renamed)  # gagal bila file masih terkunci
    assert renamed.exists()
    renamed.rename(db_file)


def test_begin_immediate_benar_benar_mengirim_immediate(seeded):
    """
    Penjaga terhadap regresi diam-diam.

    Tanpa test ini, begin_immediate() yang ternyata hanya mengirim "BEGIN"
    biasa tetap lulus seluruh test lain, padahal kunci baris tidak diambil
    sejak awal dan nomor antrian kembar bisa lolos.
    """
    from sqlalchemy import event

    from app.core.database import get_engine

    statements: list[str] = []
    engine = get_engine()

    def capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement.strip().upper())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with begin_immediate():
            pass
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert "BEGIN IMMEDIATE" in statements, statements


def test_transaksi_biasa_tetap_begin_polos(seeded):
    """Hanya penomoran antrian yang perlu IMMEDIATE; sisanya jangan ikut terkunci."""
    from sqlalchemy import event

    from app.core.database import get_engine

    statements: list[str] = []
    engine = get_engine()

    def capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement.strip().upper())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with session_scope() as session:
            session.execute(sa.select(sa.literal(1)))
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert "BEGIN" in statements
    assert "BEGIN IMMEDIATE" not in statements
