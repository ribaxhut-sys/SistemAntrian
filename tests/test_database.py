"""Test koneksi dan integritas database."""

from __future__ import annotations

import sqlalchemy as sa
import pytest

from app.core.database import (
    dispose_engine,
    get_engine,
    periksa_koneksi,
    session_scope,
    transaksi_tulis,
)


# ---------------------------------------------------------------------
# Pemasangan SQLite
#
# Yang diuji di bagian ini adalah cara SQLite dipasang, bukan perilaku
# aplikasi, sehingga tidak punya padanan di PostgreSQL.
# ---------------------------------------------------------------------

def test_wal_mode_aktif(sqlite_saja, database):
    """Pembaca (layar display) tidak boleh memblokir penulis (petugas)."""
    with get_engine().connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode.lower() == "wal"


def test_busy_timeout_terpasang(sqlite_saja, database):
    with get_engine().connect() as conn:
        timeout = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert timeout >= 5000


def test_integrity_check_bersih(sqlite_saja, database):
    with get_engine().connect() as conn:
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"


def test_dispose_engine_melepas_file_database(sqlite_saja, database):
    """
    Wajib berfungsi sebelum fitur restore.

    Windows menolak menimpa file yang koneksinya masih terbuka.
    """
    get_engine()
    dispose_engine()

    db_file = database.db_path
    renamed = db_file.with_suffix(".db.lepas")
    db_file.rename(renamed)  # gagal bila file masih terkunci
    assert renamed.exists()
    renamed.rename(db_file)


# ---------------------------------------------------------------------
# Integritas, berlaku di kedua dialect
# ---------------------------------------------------------------------

def test_foreign_keys_ditegakkan(database):
    """
    Relasi antar tabel wajib dijaga database, bukan hanya oleh kode.

    SQLite mematikan penegakan foreign key secara default sehingga
    membutuhkan PRAGMA; PostgreSQL selalu menegakkannya. Test ini
    membuktikan hasil akhirnya sama pada keduanya: menyisipkan baris dengan
    branch_id yang tidak ada harus DITOLAK.
    """
    from app.models import Counter

    with pytest.raises(sa.exc.IntegrityError):
        with session_scope() as session:
            session.add(Counter(branch_id=99999, code="X", name="Loket Hantu"))


# ---------------------------------------------------------------------
# Unit kerja
# ---------------------------------------------------------------------

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


def test_transaksi_tulis_menulis_dan_commit(seeded):
    """Transaksi mentah yang dipakai penomoran antrian."""
    from app.models import ApplicationSetting

    with transaksi_tulis() as conn:
        conn.execute(
            sa.insert(ApplicationSetting).values(key="uji.tulis", value="ok")
        )

    with session_scope() as session:
        found = session.scalar(
            sa.select(ApplicationSetting).where(ApplicationSetting.key == "uji.tulis")
        )
        assert found is not None and found.value == "ok"


def test_transaksi_tulis_rollback_saat_error(seeded):
    from app.models import ApplicationSetting

    with pytest.raises(RuntimeError):
        with transaksi_tulis() as conn:
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


def test_periksa_koneksi_sukses(database):
    """Bilah status hanya boleh bilang terhubung bila SELECT 1 berhasil."""
    assert periksa_koneksi() is True


def test_periksa_koneksi_gagal_tanpa_mengangkat():
    """
    Kegagalan harus menjadi False, bukan exception ke UI.

    Petugas tidak boleh melihat traceback; yang ditampilkan hanya status
    "tidak terjangkau" di bilah.
    """

    class Palsu:
        def connect(self):
            raise RuntimeError("server mati")

    assert periksa_koneksi(Palsu()) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Penjaga mekanisme penomoran
# ---------------------------------------------------------------------

def test_penomoran_memakai_satu_pernyataan_atomik(seeded, antrian_siap):
    """
    Penjaga terhadap regresi diam-diam.

    Keamanan penomoran terhadap penulis bersamaan bersandar sepenuhnya pada
    SATU pernyataan upsert. Bila suatu saat dipecah kembali menjadi UPDATE
    lalu INSERT, seluruh test lain tetap lulus — sementara dua loket yang
    menerbitkan nomor pada saat yang sama dapat menerima nomor kembar.

    Karena itu bentuk pernyataannya ikut dikunci, bukan hanya hasilnya.
    """
    from sqlalchemy import event

    from app.repositories.queue_repository import terbitkan_nomor

    perintah: list[str] = []
    engine = get_engine()

    def catat(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        perintah.append(" ".join(statement.split()).upper())

    event.listen(engine, "before_cursor_execute", catat)
    try:
        terbitkan_nomor(
            branch_id=antrian_siap["branch_id"],
            category_id=antrian_siap["kategori"]["A"],
            prefix="A",
        )
    finally:
        event.remove(engine, "before_cursor_execute", catat)

    sequence = [p for p in perintah if "QUEUE_SEQUENCE" in p]

    assert len(sequence) == 1, f"penomoran harus satu pernyataan, bukan {len(sequence)}"
    assert "ON CONFLICT" in sequence[0]
    assert "RETURNING LAST_NUMBER" in sequence[0]
