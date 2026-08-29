"""
Fixture bersama untuk test.

Setiap test mendapat database SQLite sendiri di folder temporary, dibangun
lewat migration Alembic yang sama dengan yang dipakai aplikasi. Dengan begitu
yang diuji adalah skema sungguhan, bukan skema tiruan hasil create_all().
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Widget Qt harus dapat dibuat tanpa layar fisik agar test dapat berjalan
# di terminal maupun pada mesin build. Harus diset sebelum Qt diimpor.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from sqlalchemy.orm import Session

from app.core import config as config_module
from app.core import database as database_module


def _pakai_sqlite() -> bool:
    """Benar bila test dijalankan di atas SQLite (bawaan)."""
    from app.core.config import get_config

    return get_config().memakai_sqlite


@pytest.fixture
def sqlite_saja(app_config):
    """
    Lewati test yang memang hanya bermakna pada SQLite.

    PRAGMA, integrity_check, dan penguncian berkas tidak punya padanan di
    PostgreSQL. Yang diuji test semacam itu adalah cara SQLite dipasang,
    bukan perilaku aplikasi.
    """
    if not _pakai_sqlite():
        pytest.skip("khusus SQLite")


@pytest.fixture
def mesin_backup_tersedia(app_config):
    """
    Lewati test backup bila perkakas dialect ini tidak terpasang.

    Backup PostgreSQL membutuhkan pg_dump dan pg_restore, yang ikut dalam
    pemasangan PostgreSQL. Komputer pengembang boleh saja tidak memilikinya
    — tetapi komputer server WAJIB, dan bila test ini terlewat berarti
    backup PostgreSQL belum terbukti sama sekali.
    """
    import shutil

    if app_config.memakai_sqlite:
        return
    if not (shutil.which("pg_dump") and shutil.which("pg_restore")):
        pytest.skip(
            "pg_dump/pg_restore tidak terpasang; backup PostgreSQL TIDAK teruji"
        )


@pytest.fixture
def app_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Arahkan seluruh path aplikasi ke folder temporary milik test ini."""
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(tmp_path / "queue.db"))
    monkeypatch.setenv("ANTRIAN_BACKUP_DIR", str(tmp_path / "backup"))
    monkeypatch.setenv("ANTRIAN_LOG_DIR", str(tmp_path / "logs"))

    config_module.reset_config()
    database_module.dispose_engine()

    cfg = config_module.get_config()
    cfg.ensure_directories()
    yield cfg

    database_module.dispose_engine()
    config_module.reset_config()


@pytest.fixture
def env_mesin(monkeypatch: pytest.MonkeyPatch):
    """
    Setel environment variable per-mesin lalu bangun ulang konfigurasi.

    Pencetak dan pengeras suara adalah sifat MESIN, sehingga jalur yang
    diuji memang jalur environment variable — bukan pengaturan database.
    Konfigurasi dikembalikan setelah test supaya nilainya tidak bocor ke
    test berikutnya lewat cache `get_config()`.
    """

    def setel(**nilai: str | None):
        for kunci, isi in nilai.items():
            if isi is None:
                monkeypatch.delenv(kunci, raising=False)
            else:
                monkeypatch.setenv(kunci, isi)
        config_module.reset_config()
        return config_module.get_config()

    yield setel
    config_module.reset_config()


def _kosongkan_schema() -> None:
    """
    Kembalikan database PostgreSQL ke keadaan benar-benar kosong.

    SQLite mendapat berkas baru di folder temporary untuk setiap test,
    sedangkan PostgreSQL dipakai bersama seluruh test. Tanpa pengosongan
    ini, data satu test bocor ke test berikutnya dan kegagalannya bergantung
    pada urutan — jenis kegagalan yang paling sulit ditelusuri.
    """

    from app.core.database import get_engine

    with get_engine().begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")
    database_module.dispose_engine()


@pytest.fixture
def database(app_config):
    """Database kosong yang skemanya sudah dinaikkan ke revisi terbaru."""
    from app.core.database import init_database

    if not app_config.memakai_sqlite:
        _kosongkan_schema()

    init_database()
    return app_config


@pytest.fixture
def session(database) -> Iterator[Session]:
    """Session yang otomatis di-commit bila blok test selesai tanpa error."""
    from app.core.database import session_scope

    with session_scope() as s:
        yield s


@pytest.fixture
def seeded(database):
    """Database yang sudah berisi data master awal."""
    from app.core.seed import seed_initial_data

    seed_initial_data()
    return database


@pytest.fixture
def master(seeded):
    """
    Data master siap pakai beserta satu user CRO.

    User dibuat langsung di sini karena hashing password baru ada pada
    Phase 2; nilai password_hash di bawah hanyalah penanda, bukan hash asli.
    """
    from sqlalchemy import select

    from app.core.database import session_scope
    from app.models import Branch, Counter, ServiceCategory, User, UserRole

    with session_scope() as s:
        branch = s.scalar(select(Branch).where(Branch.code == "PUSAT"))
        counter = s.scalar(select(Counter).where(Counter.code == "LOKET-1"))
        category = s.scalar(select(ServiceCategory).where(ServiceCategory.prefix == "A"))
        user = User(
            branch_id=branch.id,
            username="cro1",
            full_name="Petugas CRO Satu",
            password_hash="phase-2-placeholder",
            role=UserRole.CRO,
        )
        s.add(user)
        s.flush()
        return {
            "branch_id": branch.id,
            "counter_id": counter.id,
            "category_id": category.id,
            "user_id": user.id,
        }


# ---------------------------------------------------------------------
# Fixture autentikasi (Phase 2)
# ---------------------------------------------------------------------

TEST_PASSWORD = "rahasia123"


@pytest.fixture
def users(seeded) -> dict:
    """Satu user untuk tiap peran, semuanya dengan kata sandi TEST_PASSWORD."""
    from sqlalchemy import select

    from app.core.database import session_scope
    from app.core.security import hash_password
    from app.models import Branch, RecordStatus, User, UserRole

    dibuat: dict[str, int] = {}
    with session_scope() as s:
        branch = s.scalar(select(Branch).where(Branch.code == "PUSAT"))
        sandi = hash_password(TEST_PASSWORD)
        for role in UserRole:
            if role is UserRole.KIOSK:
                # Bukan akun. Sesi kios dibuat tanpa login, jadi tidak
                # boleh ada baris app_user dengan peran ini — termasuk
                # di data uji.
                continue
            username = role.value.lower()

            # Seed sudah membuat akun "admin". Akun itu dipakai ulang, bukan
            # dibuat lagi, supaya tidak melanggar keunikan nama pengguna.
            user = s.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(
                    branch_id=branch.id,
                    username=username,
                    full_name=f"Petugas {role.value.title()}",
                    role=role,
                )
                s.add(user)

            user.password_hash = sandi
            user.status = RecordStatus.ACTIVE
            user.must_change_password = False
            s.flush()
            dibuat[role.value] = user.id

        dibuat["branch_id"] = branch.id
    return dibuat


@pytest.fixture
def auth(users):
    """AuthService baru untuk tiap test, tanpa sesi yang tertinggal."""
    from app.services.auth_service import AuthService, reset_auth_service

    reset_auth_service()
    service = AuthService()
    yield service
    reset_auth_service()


@pytest.fixture
def admin_auth(auth):
    """Sesi ADMIN yang sudah masuk dan siap mengelola data master."""
    auth.login("admin", TEST_PASSWORD)
    return auth


@pytest.fixture
def master_service(admin_auth):
    from app.services.master_data_service import MasterDataService

    return MasterDataService(admin_auth)


@pytest.fixture
def user_service(admin_auth):
    from app.services.user_service import UserService

    return UserService(admin_auth)


# ---------------------------------------------------------------------
# Fixture antrian (Phase 4)
# ---------------------------------------------------------------------

@pytest.fixture
def antrian_siap(users, master_service):
    """
    Data siap pakai untuk menguji alur antrian.

    Mengembalikan id cabang, loket, dan jenis layanan per prefix.
    """
    return {
        "branch_id": users["branch_id"],
        "loket": [c.id for c in master_service.list_counters()],
        "kategori": {c.prefix: c.id for c in master_service.list_categories()},
    }


@pytest.fixture
def reg_queue(auth, antrian_siap):
    """QueueService dengan sesi petugas PENDAFTARAN (berhak menerbitkan nomor)."""
    from app.services.queue_service import QueueService

    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    return QueueService(auth)


@pytest.fixture
def cro_queue(auth, antrian_siap):
    """QueueService dengan sesi petugas CRO (berhak memanggil dan melayani)."""
    from app.services.queue_service import QueueService

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    return QueueService(auth)


@pytest.fixture
def terbitkan(antrian_siap, auth):
    """
    Fungsi bantu untuk menerbitkan nomor sebagai petugas pendaftaran,
    lalu mengembalikan sesi ke keadaan semula.
    """
    from app.services.queue_service import QueueService

    def _terbit(prefix: str = "A", jumlah: int = 1) -> list:
        sebelumnya = auth.current_session
        auth.logout()
        auth.login("registration", TEST_PASSWORD)
        hasil = [
            QueueService(auth).create_queue(antrian_siap["kategori"][prefix])
            for _ in range(jumlah)
        ]
        auth.logout()
        if sebelumnya is not None:
            auth.login(sebelumnya.username, TEST_PASSWORD)
        return hasil

    return _terbit


# ---------------------------------------------------------------------
# Fixture tiket, suara, dan layar (Phase 5)
# ---------------------------------------------------------------------

@pytest.fixture
def settings_service(auth):
    from app.services.settings_service import SettingsService

    return SettingsService(auth)


@pytest.fixture
def ticket_pdf(tmp_path, auth, seeded):
    """TicketService yang menulis tiket sebagai PDF ke folder sementara."""
    from app.services.master_data_service import MasterDataService
    from app.services.queue_service import QueueService
    from app.services.settings_service import SettingsService
    from app.services.ticket_service import PdfTicketPrinter, TicketService

    folder = tmp_path / "tiket"
    return TicketService(
        PdfTicketPrinter(folder),
        SettingsService(auth),
        MasterDataService(auth),
        QueueService(auth),
    )


@pytest.fixture
def display_queue(auth, antrian_siap):
    """QueueService dengan sesi layar antrian (hanya berhak melihat display)."""
    from app.services.queue_service import QueueService

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    return QueueService(auth)


# ---------------------------------------------------------------------
# Fixture survey kepuasan (Phase 6)
# ---------------------------------------------------------------------

@pytest.fixture
def cro_survey(auth, cro_queue):
    """SurveyService dengan sesi CRO, sesi yang sama dengan `cro_queue`."""
    from app.services.survey_service import SurveyService

    return SurveyService(auth)


@pytest.fixture
def layani_sampai_selesai(antrian_siap, cro_queue, terbitkan):
    """
    Fungsi bantu: terbitkan satu nomor lalu layani sampai COMPLETED.

    Mengembalikan QueueInfo antrian yang sudah selesai, siap dinilai.
    """

    def _layani(prefix: str = "A"):
        terbitkan(prefix)
        loket = antrian_siap["loket"][0]
        antrian = cro_queue.call_next(loket)
        cro_queue.start_service(antrian.id)
        return cro_queue.complete(antrian.id)

    return _layani
