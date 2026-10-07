"""
Test backup dan pemulihan database.

Yang paling penting dikunci di sini: backup harus berisi data yang benar
walau aplikasi sedang berjalan (mode WAL), restore harus mengembalikan
keadaan lama, dan kegagalan backup otomatis tidak boleh melempar exception
ke pemanggil.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.core.errors import AuthorizationError, NotFoundError, ValidationError
from app.services.backup_service import BackupService
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def backup(admin_auth, antrian_siap, mesin_backup_tersedia):
    """BackupService dengan sesi ADMIN."""
    return BackupService(admin_auth)


@pytest.fixture
def akhiran(backup) -> str:
    """Akhiran berkas backup pada dialect yang sedang diuji."""
    return backup.mesin.akhiran


def _jumlah_antrian(berkas) -> int:
    """Baca langsung dari berkas backup SQLite, tanpa lewat aplikasi."""
    koneksi = sqlite3.connect(f"file:{berkas}?mode=ro", uri=True)
    try:
        return koneksi.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    finally:
        koneksi.close()


def _jumlah_antrian_aktif() -> int:
    """Jumlah antrian pada database yang sedang dipakai, apa pun dialectnya."""
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import Queue

    with session_scope() as session:
        return session.scalar(sa.select(sa.func.count()).select_from(Queue))


# ---------------------------------------------------------------------
# Pembuatan
# ---------------------------------------------------------------------

def test_backup_menghasilkan_berkas(backup, akhiran):
    info = backup.backup()

    assert info.berkas.exists()
    assert info.nama.startswith("queue-")
    assert info.nama.endswith(akhiran)
    assert info.ukuran_byte > 0


def test_backup_memuat_data_terbaru(sqlite_saja, backup, terbitkan):
    """Mode WAL tidak boleh membuat transaksi terbaru tertinggal."""
    terbitkan("A", 3)

    info = backup.backup()

    assert _jumlah_antrian(info.berkas) == 3


def test_backup_berturut_turut_tidak_saling_menimpa(backup):
    pertama = backup.backup()
    kedua = backup.backup()

    assert pertama.nama != kedua.nama
    assert len(backup.list_backup()) == 2


def test_daftar_backup_terbaru_lebih_dahulu(backup):
    backup.backup()
    terbaru = backup.backup()

    assert backup.list_backup()[0].nama == terbaru.nama


def test_backup_tercatat_di_audit(backup):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    backup.backup()

    with session_scope() as session:
        aksi = list(
            session.scalars(sa.select(AuditLog.action).where(AuditLog.action == "BACKUP"))
        )

    assert aksi == ["BACKUP"]


# ---------------------------------------------------------------------
# Backup otomatis
# ---------------------------------------------------------------------

def test_backup_otomatis_membuat_satu_berkas(backup):
    hasil = backup.backup_otomatis_bila_perlu()

    assert hasil.berhasil
    assert hasil.info is not None
    assert hasil.info.berkas.exists()


def test_backup_otomatis_hanya_sekali_sehari(backup):
    backup.backup_otomatis_bila_perlu()

    kedua = backup.backup_otomatis_bila_perlu()

    assert not kedua.berhasil
    assert "sudah ada" in kedua.pesan
    assert len(backup.list_backup()) == 1


def test_backup_otomatis_dapat_dinonaktifkan(backup, admin_auth):
    from app.services.settings_service import SettingsService

    SettingsService(admin_auth).set("backup.auto_enabled", "false")

    hasil = backup.backup_otomatis_bila_perlu()

    assert not hasil.berhasil
    assert "dinonaktifkan" in hasil.pesan
    assert backup.list_backup() == []


def test_backup_otomatis_tidak_melempar_saat_gagal(backup, monkeypatch):
    """Kegagalan backup tidak boleh menghentikan aplikasi saat dibuka."""

    def _meledak(**_kwargs):
        raise OSError("folder penuh")

    monkeypatch.setattr(backup, "_salin", _meledak)

    hasil = backup.backup_otomatis_bila_perlu()

    assert not hasil.berhasil
    assert "gagal" in hasil.pesan.lower()


def test_backup_otomatis_tidak_menuntut_sesi(auth, antrian_siap, mesin_backup_tersedia):
    """Dijalankan sebelum siapa pun masuk, sehingga tidak boleh menolak."""
    auth.logout()

    hasil = BackupService(auth).backup_otomatis_bila_perlu()

    assert hasil.berhasil


# ---------------------------------------------------------------------
# Retensi
# ---------------------------------------------------------------------

def test_backup_baru_tidak_ikut_terhapus(backup):
    backup.backup()

    assert backup.hapus_kedaluwarsa() == []
    assert len(backup.list_backup()) == 1


def test_backup_lama_dihapus(backup, admin_auth, akhiran):
    from app.services.settings_service import SettingsService

    SettingsService(admin_auth).set("backup.retention_days", "1")
    lama = backup.folder / f"queue-20200101-080000{akhiran}"
    lama.write_bytes(b"berkas lama")

    dihapus = backup.hapus_kedaluwarsa()

    assert dihapus == [lama.name]
    assert not lama.exists()


def test_retensi_nol_diabaikan_agar_backup_baru_selamat(backup, admin_auth):
    """Salah konfigurasi tidak boleh menghapus satu-satunya salinan yang ada."""
    from app.services.settings_service import SettingsService

    SettingsService(admin_auth).set("backup.retention_days", "0")
    backup.backup()

    assert backup.hapus_kedaluwarsa() == []
    assert len(backup.list_backup()) == 1


# ---------------------------------------------------------------------
# Pemulihan
# ---------------------------------------------------------------------

def test_restore_mengembalikan_keadaan_lama(backup, terbitkan):
    """Antrian yang terbit setelah titik simpan hilang setelah dipulihkan."""
    terbitkan("A", 2)
    titik_simpan = backup.backup()
    terbitkan("A", 3)
    assert _jumlah_antrian_aktif() == 5

    backup.restore(titik_simpan.berkas)

    assert _jumlah_antrian_aktif() == 2


def test_restore_membuat_pengaman_lebih_dahulu(backup, terbitkan):
    """Salah pilih berkas tidak boleh menghilangkan data hari ini tanpa jalan kembali."""
    terbitkan("A", 2)
    titik_simpan = backup.backup()

    backup.restore(titik_simpan.berkas)

    assert len(backup.list_backup()) == 2


def test_restore_menerima_nama_berkas_saja(backup, terbitkan):
    terbitkan("A")
    titik_simpan = backup.backup()

    backup.restore(titik_simpan.nama)

    assert True  # tidak melempar


def test_restore_tercatat_di_audit(backup):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    titik_simpan = backup.backup()
    backup.restore(titik_simpan.berkas)

    with session_scope() as session:
        aksi = list(
            session.scalars(sa.select(AuditLog.action).where(AuditLog.action == "RESTORE"))
        )

    assert aksi == ["RESTORE"]


def test_restore_menolak_berkas_yang_tidak_ada(backup):
    with pytest.raises(NotFoundError):
        backup.restore("queue-19700101-000000.db")


def test_restore_menolak_berkas_bukan_database(backup, akhiran):
    palsu = backup.folder / f"queue-20990101-000000{akhiran}"
    palsu.write_text("ini bukan database")

    with pytest.raises(ValidationError):
        backup.restore(palsu)


def test_restore_menolak_database_yang_sedang_dipakai(sqlite_saja, backup):
    from app.core.config import get_config

    with pytest.raises(Exception) as info:
        backup.restore(get_config().db_path)

    assert "sedang dipakai" in str(info.value)


# ---------------------------------------------------------------------
# Hak akses
# ---------------------------------------------------------------------

@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration", "display"])
def test_hanya_admin_yang_boleh_backup(auth, antrian_siap, peran):
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        BackupService(auth).backup()


def test_peran_lain_tidak_boleh_memulihkan(auth, antrian_siap):
    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        BackupService(auth).restore("apa pun.db")


# ---------------------------------------------------------------------
# Tahap 1: backup benar-benar jalan di server
# ---------------------------------------------------------------------


def test_pg_dump_dicari_di_program_files_versi_tertinggi(tmp_path):
    from app.services.backup_engines import folder_postgresql_terpasang

    akar = tmp_path / "PostgreSQL"
    for versi in ("15", "17", "16", "bukan-versi"):
        (akar / versi / "bin").mkdir(parents=True)
    (akar / "18").mkdir()  # tanpa bin: bukan pemasangan lengkap

    hasil = folder_postgresql_terpasang([akar])

    assert [p.parent.name for p in hasil] == ["17", "16", "15"]


def test_pg_dump_ditemukan_tanpa_pengaturan(tmp_path, monkeypatch, app_config):
    from app.services import backup_engines

    bin_pg = tmp_path / "PostgreSQL" / "17" / "bin"
    bin_pg.mkdir(parents=True)
    (bin_pg / "pg_dump.exe").write_bytes(b"")
    monkeypatch.setattr(backup_engines.shutil, "which", lambda nama: None)
    monkeypatch.setattr(
        backup_engines, "folder_postgresql_terpasang", lambda: [bin_pg]
    )

    mesin = backup_engines.PostgresBackup(app_config, "")

    assert mesin._alat("pg_dump") == str(bin_pg / "pg_dump.exe")


def test_backup_otomatis_dilewati_di_komputer_loket(backup, monkeypatch):
    monkeypatch.setattr(
        "app.services.backup_service._boleh_backup_di_sini", lambda: False
    )

    hasil = backup.backup_otomatis_bila_perlu()

    assert not hasil.berhasil
    assert "komputer server" in hasil.pesan
    assert backup._daftar_berkas() == []


def test_backup_disalin_ke_folder_kedua(backup, admin_auth, tmp_path):
    from app.services.settings_service import SettingsService

    kedua = tmp_path / "flashdisk" / "backup-antrian"
    SettingsService(admin_auth).set("backup.salinan_folder", str(kedua))

    info = backup.backup()

    assert (kedua / info.nama).is_file()
    assert (kedua / info.nama).stat().st_size == info.ukuran_byte


def test_folder_kedua_yang_gagal_tidak_membatalkan_backup(
    backup, admin_auth, tmp_path, monkeypatch
):
    from app.services import backup_service as modul
    from app.services.settings_service import SettingsService

    SettingsService(admin_auth).set("backup.salinan_folder", str(tmp_path / "x"))

    def gagal(*args, **kwargs):
        raise OSError("flashdisk dicabut")

    monkeypatch.setattr(modul.shutil, "copy2", gagal)

    info = backup.backup()

    assert info.berkas.is_file()
