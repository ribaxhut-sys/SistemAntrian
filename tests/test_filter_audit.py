"""Filter jejak aktivitas: tindakan, pelaku, dan rentang tanggal."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.core.database import session_scope
from app.models import AuditLog, User
from app.services import audit_service
from sqlalchemy import select


@pytest.fixture
def jejak(admin_auth):
    """Tiga entri dengan pelaku dan tanggal berbeda, dikenali lewat tindakan UJI_*."""
    with session_scope() as s:
        admin = s.scalar(select(User).where(User.username == "admin"))
        sekarang = datetime.now().replace(microsecond=0)
        s.add_all(
            [
                AuditLog(user_id=admin.id, action="UJI_A", created_at=sekarang),
                AuditLog(user_id=None, action="UJI_B", created_at=sekarang),
                AuditLog(
                    user_id=admin.id,
                    action="UJI_C",
                    created_at=sekarang - timedelta(days=10),
                ),
            ]
        )
    return sekarang


def _aksi(**filter_) -> set[str]:
    return {
        e.action
        for e in audit_service.list_terakhir(batas=500, **filter_)
        if e.action.startswith("UJI_")
    }


def test_filter_menurut_tindakan(jejak):
    assert _aksi(aksi="UJI_B") == {"UJI_B"}


def test_filter_pelaku_nama_pengguna_tanpa_membedakan_huruf(jejak):
    assert _aksi(pelaku="ADMIN") == {"UJI_A", "UJI_C"}


def test_filter_pelaku_sistem_untuk_aktivitas_tanpa_pengguna(jejak):
    assert _aksi(pelaku="sistem") == {"UJI_B"}


def test_filter_rentang_tanggal_termasuk_kedua_ujung(jejak):
    hari_ini = jejak.date()
    assert _aksi(sejak=hari_ini, sampai=hari_ini) == {"UJI_A", "UJI_B"}
    assert _aksi(sampai=hari_ini - timedelta(days=5)) == {"UJI_C"}
    assert _aksi(sejak=hari_ini - timedelta(days=10), sampai=hari_ini - timedelta(days=10)) == {
        "UJI_C"
    }


def test_filter_digabung(jejak):
    assert _aksi(pelaku="admin", sejak=jejak.date()) == {"UJI_A"}


def test_daftar_aksi_memuat_yang_pernah_tercatat(jejak):
    assert {"UJI_A", "UJI_B", "UJI_C"} <= set(audit_service.daftar_aksi())


def test_layar_menyaring_jejak_aktivitas(qtbot, admin_auth, jejak):
    from app.services.backup_service import BackupService
    from app.ui.settings.backup_page import BackupPage

    halaman = BackupPage(BackupService(admin_auth))
    qtbot.addWidget(halaman)

    def tindakan() -> set[str]:
        tabel = halaman.tabel_audit
        return {tabel.item(b, 2).text() for b in range(tabel.rowCount())}

    assert {"UJI_A", "UJI_B"} <= tindakan()

    halaman.pilih_aksi_audit.setCurrentIndex(halaman.pilih_aksi_audit.findData("UJI_B"))
    halaman.tombol_filter_audit.click()
    assert tindakan() == {"UJI_B"}

    halaman.pilih_aksi_audit.setCurrentIndex(0)
    halaman.isian_pelaku_audit.setText("sistem")
    halaman.tombol_filter_audit.click()
    assert tindakan() == {"UJI_B"}

    halaman.isian_pelaku_audit.clear()
    halaman.centang_tanggal_audit.setChecked(True)
    halaman.tanggal_dari_audit.setDate(date(2000, 1, 1))
    halaman.tanggal_sampai_audit.setDate(jejak.date() - timedelta(days=5))
    halaman.tombol_filter_audit.click()
    assert "UJI_C" in tindakan() and "UJI_A" not in tindakan()
