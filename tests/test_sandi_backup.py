"""Enkripsi salinan backup di folder kedua (keputusan pemilik Oktober 2026)."""

from __future__ import annotations

import pytest

from app.core.errors import AuthorizationError, BusinessRuleError, ValidationError
from app.services import sandi_backup
from app.services.backup_service import BackupService
from tests.conftest import TEST_PASSWORD

SANDI = "sandi-salinan-panjang"


@pytest.fixture
def kunci():
    return sandi_backup.buat_kunci(SANDI)


@pytest.fixture
def potongan_kecil(monkeypatch):
    """Banyak potongan dari berkas kecil, supaya urutan potongan teruji."""
    monkeypatch.setattr(sandi_backup, "UKURAN_POTONGAN", 1000)


def _isi(tmp_path, ukuran=4500):
    sumber = tmp_path / "queue-20261017-080000.dump"
    sumber.write_bytes(bytes(range(256)) * (ukuran // 256) + b"RAHASIA-NIK-123" + b"x" * 7)
    return sumber


# ---------------------------------------------------------------------
# Format berkas
# ---------------------------------------------------------------------


def test_bolak_balik_banyak_potongan(tmp_path, kunci, potongan_kecil):
    sumber = _isi(tmp_path)
    enc = tmp_path / "salinan.antrianenc"
    sandi_backup.enkripsi(sumber, enc, kunci)

    assert b"RAHASIA-NIK-123" not in enc.read_bytes()
    assert sandi_backup.nama_asli(enc) == sumber.name

    hasil = tmp_path / "buka.dump"
    sandi_backup.dekripsi(enc, hasil, SANDI)
    assert hasil.read_bytes() == sumber.read_bytes()


def test_berkas_kosong(tmp_path, kunci):
    sumber = tmp_path / "kosong.dump"
    sumber.write_bytes(b"")
    enc = tmp_path / "k.antrianenc"
    sandi_backup.enkripsi(sumber, enc, kunci)
    sandi_backup.dekripsi(enc, tmp_path / "k.dump", SANDI)
    assert (tmp_path / "k.dump").read_bytes() == b""


def test_sandi_salah_ditolak_tanpa_berkas_tertinggal(tmp_path, kunci):
    enc = tmp_path / "s.antrianenc"
    sandi_backup.enkripsi(_isi(tmp_path), enc, kunci)
    tujuan = tmp_path / "buka.dump"

    with pytest.raises(ValidationError, match="Kata sandi salah"):
        sandi_backup.dekripsi(enc, tujuan, "bukan-sandinya-sama-sekali")
    assert not tujuan.exists()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("rusak", ["potong_akhir", "ubah_byte", "tambah_data"])
def test_berkas_diubah_ditolak(tmp_path, kunci, potongan_kecil, rusak):
    enc = tmp_path / "r.antrianenc"
    sandi_backup.enkripsi(_isi(tmp_path), enc, kunci)
    data = bytearray(enc.read_bytes())
    if rusak == "potong_akhir":
        # Buang potongan terakhir utuh (4 byte panjang + isi + tag).
        terakhir = 4 + (4500 + 22) % 1000 + 16
        data = data[:-terakhir]
    elif rusak == "ubah_byte":
        data[-5] ^= 0xFF
    else:
        data += b"sisipan"
    enc.write_bytes(bytes(data))

    with pytest.raises(ValidationError):
        sandi_backup.dekripsi(enc, tmp_path / "x.dump", SANDI)
    assert not (tmp_path / "x.dump").exists()


def test_sandi_pendek_ditolak():
    with pytest.raises(ValidationError, match="minimal"):
        sandi_backup.buat_kunci("pendek")


def test_bukan_berkas_terenkripsi(tmp_path):
    lain = tmp_path / "lain.antrianenc"
    lain.write_bytes(b"PGDMP....")
    with pytest.raises(ValidationError, match="bukan salinan"):
        sandi_backup.nama_asli(lain)


# ---------------------------------------------------------------------
# BackupService
# ---------------------------------------------------------------------


@pytest.fixture
def backup(admin_auth, antrian_siap, mesin_backup_tersedia):
    return BackupService(admin_auth)


def _folder_kedua(admin_auth, tmp_path):
    from app.services.settings_service import SettingsService

    kedua = tmp_path / "flashdisk"
    SettingsService(admin_auth).set("backup.salinan_folder", str(kedua))
    return kedua


def test_tanpa_sandi_salinan_kedua_tetap_polos(backup, admin_auth, tmp_path):
    kedua = _folder_kedua(admin_auth, tmp_path)
    info = backup.backup()

    assert not backup.salinan_terenkripsi()
    assert (kedua / info.nama).is_file()


def test_salinan_kedua_terenkripsi_dan_dapat_dibuka_lalu_diuji(
    backup, admin_auth, tmp_path
):
    kedua = _folder_kedua(admin_auth, tmp_path)
    backup.atur_sandi_salinan(SANDI)
    info = backup.backup()

    assert backup.salinan_terenkripsi()
    assert not (kedua / info.nama).exists(), "tidak boleh ada salinan polos"
    enc = kedua / (info.nama + sandi_backup.AKHIRAN)
    assert enc.is_file()
    assert sandi_backup.KUNCI not in enc.read_text(errors="ignore")

    # Backup di server hilang; yang tersisa hanya salinan terenkripsi.
    info.berkas.unlink()
    (info.berkas.parent / (info.nama + ".sha256")).unlink(missing_ok=True)
    dibuka = backup.buka_salinan_terenkripsi(enc, SANDI)

    assert dibuka.nama == info.nama and dibuka.checksum_ada
    assert backup.uji_backup(dibuka.berkas).berhasil
    with pytest.raises(BusinessRuleError, match="sudah ada"):
        backup.buka_salinan_terenkripsi(enc, SANDI)


def test_sandi_tidak_tersimpan_di_database(backup):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import ApplicationSetting, AuditLog

    backup.atur_sandi_salinan(SANDI)

    with session_scope() as s:
        nilai = " ".join(s.scalars(sa.select(ApplicationSetting.value)))
        audit = " ".join(m or "" for m in s.scalars(sa.select(AuditLog.meta)))
    assert SANDI not in nilai and SANDI not in audit


def test_hapus_sandi_kembali_polos(backup, admin_auth, tmp_path):
    kedua = _folder_kedua(admin_auth, tmp_path)
    backup.atur_sandi_salinan(SANDI)
    backup.hapus_sandi_salinan()

    info = backup.backup()
    assert (kedua / info.nama).is_file()


def test_retensi_ikut_menghapus_salinan_terenkripsi_lama(
    backup, admin_auth, tmp_path, kunci
):
    from app.services.settings_service import SettingsService

    kedua = _folder_kedua(admin_auth, tmp_path)
    kedua.mkdir(parents=True)
    akhiran = backup.mesin.akhiran
    lama_polos = tmp_path / f"queue-20200101-080000{akhiran}"
    lama_polos.write_bytes(b"lama")
    lama = kedua / (lama_polos.name + sandi_backup.AKHIRAN)
    sandi_backup.enkripsi(lama_polos, lama, kunci)
    SettingsService(admin_auth).set("backup.retention_days", "1")

    dihapus = backup.hapus_kedaluwarsa()

    assert not lama.exists()
    assert lama.name in dihapus


def test_hanya_admin_mengatur_sandi_salinan(auth, antrian_siap):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    with pytest.raises(AuthorizationError):
        BackupService(auth).atur_sandi_salinan(SANDI)


def test_layar_backup_mengatur_sandi(qtbot, backup, monkeypatch):
    from app.ui.settings import backup_page
    from app.ui.settings.backup_page import BackupPage

    monkeypatch.setattr(backup_page, "konfirmasi", lambda *a, **k: True)
    monkeypatch.setattr(backup_page, "tampilkan_info", lambda *a, **k: None)
    halaman = BackupPage(backup)
    qtbot.addWidget(halaman)
    assert halaman.tombol_sandi.text() == "Atur Sandi Salinan…"

    jawaban = iter([SANDI, SANDI])
    monkeypatch.setattr(halaman, "_minta_sandi", lambda *a: next(jawaban))
    halaman.atur_sandi_salinan()

    assert backup.salinan_terenkripsi()
    assert halaman.tombol_sandi.text() == "Ganti Sandi Salinan…"
