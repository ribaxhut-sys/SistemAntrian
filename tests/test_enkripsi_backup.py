"""
Test enkripsi backup.

Yang dijaga: backup terenkripsi tidak memuat data dalam bentuk terbaca,
pulih utuh dengan kunci yang benar, ditolak — tanpa meninggalkan salinan
polos — dengan kunci yang salah, dan kunci tidak pernah masuk audit.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.core.database import session_scope
from app.core.errors import BusinessRuleError, ValidationError
from app.models import AuditLog, Queue
from app.services import enkripsi_backup
from app.services.backup_service import BackupService


@pytest.fixture
def backup(admin_auth, antrian_siap, mesin_backup_tersedia):
    return BackupService(admin_auth)


def _jumlah_antrian() -> int:
    with session_scope() as session:
        return session.scalar(sa.select(sa.func.count()).select_from(Queue))


def _sisa_sementara(folder) -> list[str]:
    return [p.name for p in folder.iterdir() if p.name.endswith(".sementara")]


# ---------------------------------------------------------------------
# Format berkas
# ---------------------------------------------------------------------

@pytest.mark.parametrize("ukuran", [0, 10, enkripsi_backup.UKURAN_POTONGAN, 2_500_000])
def test_enkripsi_lalu_dekripsi_mengembalikan_isi(tmp_path, ukuran):
    import os

    asli = tmp_path / "asli.bin"
    asli.write_bytes(os.urandom(ukuran))
    terkunci = tmp_path / "x.enc"
    kembali = tmp_path / "kembali.bin"

    enkripsi_backup.enkripsi(asli, terkunci, "KUNCI-RAHASIA-12345")
    assert enkripsi_backup.terenkripsi(terkunci)
    enkripsi_backup.dekripsi(terkunci, kembali, "kunci rahasia 12345".replace(" ", "-"))

    assert kembali.read_bytes() == asli.read_bytes()


def test_isi_terenkripsi_tidak_terbaca(tmp_path):
    asli = tmp_path / "asli.txt"
    asli.write_text("Budi Santoso 081234567890 " * 100, encoding="utf-8")
    terkunci = tmp_path / "x.enc"
    enkripsi_backup.enkripsi(asli, terkunci, "KUNCI-RAHASIA-12345")

    assert b"Budi" not in terkunci.read_bytes()


def test_kunci_salah_ditolak_tanpa_sisa_berkas(tmp_path):
    asli = tmp_path / "asli.bin"
    asli.write_bytes(b"isi" * 1000)
    terkunci = tmp_path / "x.enc"
    enkripsi_backup.enkripsi(asli, terkunci, "KUNCI-RAHASIA-12345")

    with pytest.raises(ValidationError):
        enkripsi_backup.dekripsi(terkunci, tmp_path / "keluar", "KUNCI-LAIN-0000000")
    assert not (tmp_path / "keluar").exists()
    assert not enkripsi_backup.cocok(terkunci, "KUNCI-LAIN-0000000")
    assert enkripsi_backup.cocok(terkunci, "KUNCI-RAHASIA-12345")


def test_berkas_terpotong_ditolak(tmp_path):
    import os

    asli = tmp_path / "asli.bin"
    asli.write_bytes(os.urandom(enkripsi_backup.UKURAN_POTONGAN * 2 + 10))
    terkunci = tmp_path / "x.enc"
    enkripsi_backup.enkripsi(asli, terkunci, "KUNCI-RAHASIA-12345")

    # Buang potongan terakhir: dua potongan pertama tetap utuh dan sah,
    # tetapi tidak satu pun bertanda "terakhir".
    data = terkunci.read_bytes()
    terpotong = tmp_path / "terpotong.enc"
    panjang_potongan = 4 + enkripsi_backup.UKURAN_POTONGAN + 16
    terpotong.write_bytes(data[: len(enkripsi_backup.MAGIC) + 24 + 2 * panjang_potongan])

    with pytest.raises(ValidationError):
        enkripsi_backup.dekripsi(terpotong, tmp_path / "keluar", "KUNCI-RAHASIA-12345")
    assert not (tmp_path / "keluar").exists()


def test_frasa_baru_mudah_disalin_tangan():
    frasa = enkripsi_backup.frasa_baru()
    kelompok = frasa.split("-")
    assert len(kelompok) == 6 and all(len(k) == 5 for k in kelompok)
    assert not set(frasa) & set("01OIL")
    assert frasa != enkripsi_backup.frasa_baru()


# ---------------------------------------------------------------------
# BackupService
# ---------------------------------------------------------------------

def test_tanpa_kunci_backup_tetap_polos(backup):
    assert not backup.enkripsi_aktif
    info = backup.backup()
    assert not info.terenkripsi
    assert not info.nama.endswith(".enc")


def test_backup_terenkripsi_dan_pulih_utuh(backup, terbitkan):
    frasa = backup.buat_kunci_enkripsi()
    assert backup.enkripsi_aktif
    assert enkripsi_backup.path_berkas_kunci().read_text(encoding="utf-8").strip() == frasa

    terbitkan("A", 2)
    info = backup.backup()
    assert info.terenkripsi
    assert info.nama.endswith(backup.mesin.akhiran + ".enc")
    assert enkripsi_backup.terenkripsi(info.berkas)
    assert _sisa_sementara(backup.folder) == []
    assert backup.list_backup()[0].nama == info.nama

    hasil = backup.uji_backup(info.berkas)
    assert hasil.berhasil, hasil.ringkasan
    assert any("Terenkripsi" in r for r in hasil.rincian)

    terbitkan("A", 3)
    assert _jumlah_antrian() == 5
    backup.restore(info.berkas)
    assert _jumlah_antrian() == 2
    assert _sisa_sementara(backup.folder) == []


def test_kunci_berbeda_tidak_dapat_memulihkan(backup, terbitkan):
    backup.buat_kunci_enkripsi()
    info = backup.backup()
    enkripsi_backup.simpan_frasa("KUNCI-LAIN-YANG-SALAH-1")
    terbitkan("A")

    hasil = backup.uji_backup(info.berkas)
    assert not hasil.berhasil
    assert "kunci" in hasil.ringkasan.lower()

    with pytest.raises(ValidationError):
        backup.restore(info.berkas)
    assert _jumlah_antrian() == 1
    assert _sisa_sementara(backup.folder) == []


def test_komputer_tanpa_kunci_menyebut_cara_memasukkannya(backup):
    backup.buat_kunci_enkripsi()
    info = backup.backup()
    enkripsi_backup.path_berkas_kunci().unlink()

    hasil = backup.uji_backup(info.berkas)
    assert not hasil.berhasil
    assert "Masukkan" in hasil.ringkasan


def test_kunci_tidak_dapat_dibuat_dua_kali(backup):
    backup.buat_kunci_enkripsi()
    with pytest.raises(BusinessRuleError):
        backup.buat_kunci_enkripsi()


def test_memasukkan_kunci_diperiksa_terhadap_backup_terbaru(backup):
    frasa = backup.buat_kunci_enkripsi()
    backup.backup()
    enkripsi_backup.path_berkas_kunci().unlink()

    with pytest.raises(ValidationError):
        backup.pasang_kunci_enkripsi("KUNCI-LAIN-YANG-SALAH-1")
    assert not backup.enkripsi_aktif

    # Salinan tangan: huruf kecil dan spasi tetap diterima.
    backup.pasang_kunci_enkripsi(" " + frasa.lower() + " ")
    assert backup.enkripsi_aktif
    assert backup.uji_backup(backup.list_backup()[0].berkas).berhasil


def test_kunci_tidak_masuk_audit(backup):
    frasa = backup.buat_kunci_enkripsi()
    backup.pasang_kunci_enkripsi(frasa)

    with session_scope() as session:
        semua = session.scalars(sa.select(AuditLog)).all()
        teks = " ".join(repr(a.__dict__) for a in semua)
    assert frasa not in teks
    assert frasa.replace("-", "") not in teks


def test_retensi_ikut_menghapus_backup_terenkripsi(backup, admin_auth, monkeypatch):
    from datetime import timedelta

    from app.core import clock
    from app.services.settings_service import SettingsService

    backup.buat_kunci_enkripsi()
    lama = backup.backup()
    SettingsService(admin_auth).set("backup.retention_days", "1")
    sekarang = clock.now()
    monkeypatch.setattr(clock, "now", lambda: sekarang + timedelta(days=3))

    dihapus = backup.hapus_kedaluwarsa()
    assert lama.nama in dihapus
    assert not lama.berkas.exists()


def test_layar_backup_memperingatkan_backup_tanpa_enkripsi(qtbot, backup):
    from app.ui.settings.backup_page import BackupPage

    halaman = BackupPage(backup)
    qtbot.addWidget(halaman)
    assert "TIDAK dienkripsi" in halaman.label_enkripsi.text()
    assert not halaman.tombol_aktifkan_enkripsi.isHidden()

    backup.buat_kunci_enkripsi()
    backup.backup()
    halaman.muat_ulang()

    assert "AKTIF" in halaman.label_enkripsi.text()
    assert halaman.tombol_aktifkan_enkripsi.isHidden()
    assert halaman.tabel_backup.item(0, 4).text() == "terenkripsi"
