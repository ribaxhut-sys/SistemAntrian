"""Test migration Alembic."""

from __future__ import annotations

import sqlalchemy as sa

from app.core.database import get_engine, init_database
from app.core.migrations import current_revision, head_revision, is_up_to_date
from app.models import Base

EXPECTED_TABLES = {
    "app_user",
    "application_setting",
    "audit_log",
    "branch",
    "counter",
    "queue",
    "queue_call",
    "queue_sequence",
    "satisfaction_survey",
    "service_category",
}


def test_migration_membuat_seluruh_tabel(database):
    tables = set(sa.inspect(get_engine()).get_table_names())
    assert EXPECTED_TABLES <= tables


def test_revisi_tercatat_setelah_migrasi(database):
    """
    Regresi: pernah terjadi skema terbentuk tetapi alembic_version kosong,
    sehingga migration dijalankan berulang dan gagal pada start kedua.
    """
    assert current_revision() is not None
    assert current_revision() == head_revision()
    assert is_up_to_date()


def test_migrasi_ulang_tidak_bermasalah(database):
    """Aplikasi menjalankan migration setiap start; harus aman diulang."""
    init_database()
    init_database()
    assert is_up_to_date()


def test_skema_hasil_migrasi_sama_dengan_model(database):
    """
    Model dan migration tidak boleh menyimpang.

    Bila test ini gagal, artinya model diubah tanpa membuat migration baru.
    """
    inspector = sa.inspect(get_engine())
    for table_name, table in Base.metadata.tables.items():
        actual = {c["name"] for c in inspector.get_columns(table_name)}
        expected = {c.name for c in table.columns}
        assert actual == expected, f"kolom tabel {table_name} tidak cocok"


def test_skema_menjaga_satu_nomor_aktif_per_loket(database):
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        # SQLAlchemy 2.0 belum selalu merefleksikan indeks parsial SQLite,
        # jadi baca katalog aslinya. Perilaku uniknya diuji di test_models.
        with engine.connect() as conn:
            sql = conn.scalar(
                sa.text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'index' AND name = :nama"
                ),
                {"nama": "uq_queue_active_counter_date"},
            )
        assert sql is not None
        assert "UNIQUE INDEX" in sql.upper()
        assert "WHERE" in sql.upper()
        return

    indeks = {item["name"]: item for item in sa.inspect(engine).get_indexes("queue")}
    assert indeks["uq_queue_active_counter_date"]["unique"]
    assert indeks["uq_queue_active_counter_date"]["column_names"] == [
        "counter_id",
        "queue_date",
    ]
