r"""
PHASE 0 — ENVIRONMENT LOCK: smoke test.

Tujuan file ini BUKAN menguji business logic (belum ada pada Phase 0),
melainkan membuktikan bahwa environment development sudah benar dan
reproducible sebelum Phase 1 dimulai.

Yang diverifikasi:
  1. Interpreter adalah Python 3.13 dan berjalan dari .venv
  2. PySide6 dapat diimpor dan QApplication dapat dibuat
  3. SQLite mendukung WAL, foreign keys, dan backup API
  4. SQLAlchemy dapat membuat engine, tabel, insert, dan select
  5. Timezone Asia/Jakarta tersedia (tzdata ter-bundle)
  6. ReportLab dapat menghasilkan PDF
  7. Alembic tersedia untuk schema migration
  8. PyInstaller tersedia untuk packaging

Jalankan:
    .\.venv\Scripts\python.exe -m pytest tests -v
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

# QApplication harus dapat dibuat tanpa display fisik agar test dapat
# berjalan pada CI / terminal tanpa GUI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------
# 1. Interpreter
# ---------------------------------------------------------------------

def test_python_version_is_3_13():
    """Project ini dikunci pada Python 3.13 (bukan 3.11, bukan 3.14)."""
    assert sys.version_info[:2] == (3, 13), (
        f"Interpreter aktif adalah {sys.version_info.major}."
        f"{sys.version_info.minor}, seharusnya 3.13"
    )


def test_running_inside_project_venv():
    """Test harus dijalankan dari .venv project, bukan Python global."""
    assert sys.prefix != sys.base_prefix, "Tidak berjalan di dalam virtualenv"

    venv_dir = Path(sys.prefix).resolve()
    project_venv = (Path(__file__).resolve().parent.parent / ".venv").resolve()
    assert venv_dir == project_venv, (
        f"Berjalan di venv {venv_dir}, seharusnya {project_venv}"
    )


# ---------------------------------------------------------------------
# 2. PySide6
# ---------------------------------------------------------------------

def test_pyside6_import_and_version():
    import PySide6
    from PySide6 import QtCore

    assert PySide6.__version__.startswith("6."), PySide6.__version__
    assert QtCore.qVersion().startswith("6."), QtCore.qVersion()


def test_pyside6_qapplication_and_widget():
    """Membuktikan Qt runtime benar-benar dapat dijalankan, bukan sekadar import."""
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication.instance() or QApplication([])
    label = QLabel("Sistem Antrian Pengaduan Wajib Pajak")

    assert label.text() == "Sistem Antrian Pengaduan Wajib Pajak"
    assert app is not None

    label.deleteLater()


def test_pyside6_modules_needed_later_are_available():
    """Modul Qt yang dibutuhkan phase berikutnya harus ada di dalam wheel."""
    from PySide6 import QtPrintSupport  # Phase 5 — cetak tiket
    from PySide6 import QtMultimedia    # Phase 5 — suara panggilan

    assert QtPrintSupport is not None
    assert QtMultimedia is not None


# ---------------------------------------------------------------------
# 3. SQLite
# ---------------------------------------------------------------------

def test_sqlite_version_supports_required_features():
    """
    Penomoran antrian membutuhkan RETURNING dan ON CONFLICT.

    RETURNING ada sejak SQLite 3.35, ON CONFLICT sejak 3.24. Keduanya
    dipakai dalam satu pernyataan upsert yang menjadi satu-satunya penjamin
    tidak adanya nomor kembar.
    """
    parts = tuple(int(x) for x in sqlite3.sqlite_version.split("."))
    assert parts >= (3, 35, 0), f"SQLite terlalu lama: {sqlite3.sqlite_version}"


def test_driver_postgresql_tersedia():
    """
    Kantor dengan beberapa loket memakai PostgreSQL.

    Tanpa driver ini, ANTRIAN_DB_URL yang menunjuk PostgreSQL akan gagal
    saat aplikasi dibuka, bukan saat dibangun.
    """
    import psycopg

    assert psycopg.__version__


def test_sqlite_wal_and_foreign_keys(tmp_path: Path):
    """WAL mode dan foreign key enforcement wajib bisa diaktifkan."""
    db = tmp_path / "smoke.db"
    conn = sqlite3.connect(db)
    try:
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        assert mode.lower() == "wal", f"journal_mode = {mode}"

        conn.execute("PRAGMA foreign_keys=ON")
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_sqlite_online_backup_api(tmp_path: Path):
    """
    Backup (Phase 8) wajib memakai SQLite backup API, bukan copy file.
    Test ini membuktikan API tersebut tersedia dan menghasilkan data identik.
    """
    src_path = tmp_path / "source.db"
    dst_path = tmp_path / "backup.db"

    src = sqlite3.connect(src_path)
    src.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    src.execute("INSERT INTO t (v) VALUES ('A-023')")
    src.commit()

    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)  # online backup API
        assert dst.execute("SELECT v FROM t").fetchone()[0] == "A-023"
    finally:
        src.close()
        dst.close()


# ---------------------------------------------------------------------
# 4. SQLAlchemy
# ---------------------------------------------------------------------

def test_sqlalchemy_end_to_end(tmp_path: Path):
    """Engine -> DDL -> INSERT -> SELECT pada file SQLite nyata."""
    assert sa.__version__.startswith("2."), sa.__version__

    class Base(DeclarativeBase):
        pass

    class SmokeRow(Base):
        __tablename__ = "smoke_row"
        id: Mapped[int] = mapped_column(primary_key=True)
        label: Mapped[str] = mapped_column(sa.String(32))

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'orm.db'}")
    try:
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            session.add(SmokeRow(label="A-023"))
            session.commit()

        with Session(engine) as session:
            row = session.scalars(sa.select(SmokeRow)).one()
            assert row.label == "A-023"
    finally:
        engine.dispose()


# ---------------------------------------------------------------------
# 5. Timezone
# ---------------------------------------------------------------------

def test_asia_jakarta_timezone_available():
    """
    Windows tidak punya tz database sistem; paket tzdata harus ter-install.
    WIB adalah UTC+7 tanpa DST.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Jakarta")
    now = datetime.now(tz)

    assert now.utcoffset().total_seconds() == 7 * 3600
    assert now.tzinfo is not None


def test_tzdata_package_is_bundled():
    """Dependency eksplisit — dibutuhkan agar .exe hasil PyInstaller tetap benar."""
    import tzdata

    assert tzdata is not None


# ---------------------------------------------------------------------
# 6. ReportLab
# ---------------------------------------------------------------------

def test_reportlab_generates_pdf(tmp_path: Path):
    """Dipakai Phase 5 (tiket) dan Phase 7 (laporan cetak)."""
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "ticket.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(100, 750, "A-023")
    c.save()

    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")


# ---------------------------------------------------------------------
# 7. LAN API
# ---------------------------------------------------------------------

def test_android_kiosk_api_dependencies_available():
    """The authenticated kiosk API is included in the Windows runtime bundle."""
    import fastapi
    import uvicorn

    assert fastapi.__version__
    assert uvicorn.__version__


def test_versi_rilis_desktop_seragam():
    """Versi paket, API, installer, skrip build, dan panduan harus sama."""
    from app import __version__
    from app.kiosk_api import create_app

    root = Path(__file__).resolve().parent.parent
    installer = (root / "installer.iss").read_text(encoding="utf-8")
    build = (root / "build-installer.ps1").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert f'#define MyAppVersion "{__version__}"' in installer
    assert f"AntrianCRO-Setup-{__version__}" in installer
    assert f"AntrianCRO-Setup-{__version__}.exe" in build
    assert f"AntrianCRO-Setup-{__version__}.exe" in readme
    assert create_app("token-rilis-panjang", object()).version == __version__


# ---------------------------------------------------------------------
# 8. Alembic
# ---------------------------------------------------------------------

def test_alembic_available_with_cli():
    """
    Migration dipakai sejak Phase 1. Alembic adalah runtime dependency:
    .exe di komputer petugas harus mampu meng-upgrade skema tanpa
    menghapus data antrian & survey yang sudah ada.
    """
    import alembic
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    assert alembic.__version__.startswith("1."), alembic.__version__
    assert Config is not None
    assert ScriptDirectory is not None

    cli = Path(sys.prefix) / "Scripts" / "alembic.exe"
    assert cli.exists(), f"CLI alembic tidak ditemukan di {cli}"


# ---------------------------------------------------------------------
# 9. PyInstaller
# ---------------------------------------------------------------------

def test_pyinstaller_available():
    """Packaging tool untuk Phase 9. Build nyata diuji terpisah (lambat)."""
    import PyInstaller

    assert PyInstaller.__version__.startswith("6."), PyInstaller.__version__
