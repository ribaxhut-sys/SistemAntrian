"""Laporan mingguan otomatis: kapan dibuat, kapan dilewati."""

from __future__ import annotations

from datetime import date

import pytest

from app.models import AuditAction, AuditLog
from app.services import laporan_terjadwal as lt
from app.services.settings_service import SettingsService
from app.core.database import session_scope
from sqlalchemy import select

# Rabu 21 Oktober 2026 -> minggu lalu Senin 12 s.d. Minggu 18 Oktober.
HARI = date(2026, 10, 21)


@pytest.fixture
def folder(admin_auth, tmp_path):
    pengaturan = SettingsService(admin_auth)
    pengaturan.set(lt.KUNCI_FOLDER, str(tmp_path / "laporan"))
    return tmp_path / "laporan"


def _aktifkan(auth):
    SettingsService(auth).set(lt.KUNCI_AKTIF, "true")


def test_minggu_lalu_senin_sampai_minggu():
    assert lt.minggu_lalu(HARI) == (date(2026, 10, 12), date(2026, 10, 18))
    # Senin pun mengambil minggu penuh sebelumnya, bukan minggu berjalan.
    assert lt.minggu_lalu(date(2026, 10, 19)) == (date(2026, 10, 12), date(2026, 10, 18))
    assert lt.minggu_lalu(date(2026, 10, 18)) == (date(2026, 10, 5), date(2026, 10, 11))


def test_tidak_membuat_bila_tidak_diaktifkan(admin_auth, folder):
    assert lt.buat_laporan_mingguan_bila_perlu(admin_auth, hari=HARI) is None
    assert not folder.exists()


def test_membuat_pdf_sekali_dan_tidak_menggandakan(admin_auth, folder):
    _aktifkan(admin_auth)
    hasil = lt.buat_laporan_mingguan_bila_perlu(admin_auth, hari=HARI)

    assert hasil == folder / "laporan-mingguan-20261012-20261018.pdf"
    assert hasil.read_bytes().startswith(b"%PDF")
    assert not list(folder.glob(".*sementara"))
    # Dibuka lagi pada hari yang sama atau esok harinya: tidak dibuat ulang.
    assert lt.buat_laporan_mingguan_bila_perlu(admin_auth, hari=HARI) is None
    assert len(list(folder.glob("*.pdf"))) == 1


def test_pembuatan_tercatat_di_audit(admin_auth, folder):
    _aktifkan(admin_auth)
    lt.buat_laporan_mingguan_bila_perlu(admin_auth, hari=HARI)
    with session_scope() as s:
        jumlah = len(
            s.scalars(
                select(AuditLog).where(AuditLog.action == AuditAction.EXPORT_REPORT.value)
            ).all()
        )
    assert jumlah == 1


@pytest.mark.parametrize("peran", ["cro", "display"])
def test_peran_tanpa_hak_laporan_dilewati(auth, folder, admin_auth, peran):
    _aktifkan(admin_auth)
    auth.logout()
    from tests.conftest import TEST_PASSWORD

    auth.login(peran, TEST_PASSWORD)
    assert lt.buat_laporan_mingguan_bila_perlu(auth, hari=HARI) is None
    assert not folder.exists()


def test_kegagalan_tidak_dilempar(admin_auth, folder, monkeypatch):
    _aktifkan(admin_auth)

    def rusak(*a, **k):
        raise OSError("disk penuh")

    monkeypatch.setattr(lt, "ekspor_pdf", rusak)
    assert lt.buat_laporan_mingguan_bila_perlu(admin_auth, hari=HARI) is None
    assert not list(folder.glob("*.pdf"))
    assert not list(folder.glob(".*sementara"))


def test_jendela_utama_menjadwalkan_hanya_untuk_pemegang_hak(qtbot, admin_auth, antrian_siap):
    from app.ui.main_window import MainWindow

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    assert jendela._pewaktu_laporan_awal.isActive()
    jendela.close()
    assert not jendela._pewaktu_laporan_awal.isActive()
