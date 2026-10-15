"""Hapus permanen akun tanpa riwayat, dan arsip akun yang pernah bekerja."""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import AuthorizationError, BusinessRuleError, NotFoundError
from app.core.security import hash_password
from app.models import Counter, RecordStatus, User, UserRole
from app.services.user_service import UserService
from tests.conftest import TEST_PASSWORD


def _buat(users: dict, username: str, peran: UserRole = UserRole.CRO) -> int:
    with session_scope() as s:
        user = User(
            branch_id=users["branch_id"],
            username=username,
            full_name=f"Nama {username}",
            password_hash=hash_password(TEST_PASSWORD),
            role=peran,
        )
        s.add(user)
        s.flush()
        return user.id


def _ada(user_id: int) -> bool:
    with session_scope() as s:
        return s.get(User, user_id) is not None


def test_akun_tanpa_riwayat_dihapus_permanen(admin_auth, users):
    baru = _buat(users, "petugas-baru")
    layanan = UserService(admin_auth)

    assert layanan.jejak_user(baru) == 0
    layanan.hapus_user(baru)

    assert not _ada(baru)


def test_akun_dengan_riwayat_tidak_dapat_dihapus(
    auth, antrian_siap, terbitkan, users, layani_sampai_selesai
):
    layani_sampai_selesai()
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    layanan = UserService(auth)

    assert layanan.jejak_user(users["CRO"]) > 0
    with pytest.raises(BusinessRuleError, match="Arsipkan"):
        layanan.hapus_user(users["CRO"])
    assert _ada(users["CRO"])


def test_arsip_menonaktifkan_dan_mempertahankan_nama(
    auth, antrian_siap, terbitkan, users, layani_sampai_selesai
):
    layani_sampai_selesai()
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    layanan = UserService(auth)

    info = layanan.arsipkan_user(users["CRO"])

    assert info.is_active is False
    assert info.username == "cro"
    assert info.default_counter_id is None


def test_arsip_dapat_menyamarkan_nama(admin_auth, users):
    baru = _buat(users, "petugas-lama")

    info = UserService(admin_auth).arsipkan_user(baru, samarkan_nama=True)

    assert info.username == f"arsip-{baru}"
    assert info.full_name == f"Petugas diarsipkan #{baru}"


def test_arsip_melepas_dari_loket(admin_auth, users, antrian_siap):
    baru = _buat(users, "petugas-loket")
    loket = antrian_siap["loket"][0]
    with session_scope() as s:
        s.execute(
            sa.update(Counter)
            .where(Counter.id == loket)
            .values(
                petugas_user_id=baru,
                petugas_terlihat_pada=clock.now() - timedelta(minutes=30),
            )
        )

    UserService(admin_auth).arsipkan_user(baru)

    with session_scope() as s:
        assert s.get(Counter, loket).petugas_user_id is None


def test_tidak_dapat_menghapus_diri_sendiri(admin_auth, users):
    with pytest.raises(BusinessRuleError, match="sendiri"):
        UserService(admin_auth).hapus_user(users["ADMIN"])


def test_admin_tidak_dapat_dihapus_lewat_jalur_ini(admin_auth, users):
    admin_lain = _buat(users, "admin-dua", UserRole.ADMIN)

    with pytest.raises(BusinessRuleError, match="petugas, pendaftaran"):
        UserService(admin_auth).hapus_user(admin_lain)
    with pytest.raises(BusinessRuleError):
        UserService(admin_auth).arsipkan_user(admin_lain)


def test_petugas_yang_sedang_masuk_ditolak(admin_auth, users, antrian_siap):
    baru = _buat(users, "petugas-aktif")
    with session_scope() as s:
        s.execute(
            sa.update(Counter)
            .where(Counter.id == antrian_siap["loket"][0])
            .values(petugas_user_id=baru, petugas_terlihat_pada=clock.now())
        )

    with pytest.raises(BusinessRuleError, match="sedang masuk"):
        UserService(admin_auth).hapus_user(baru)


def test_akun_tidak_ditemukan(admin_auth):
    with pytest.raises(NotFoundError):
        UserService(admin_auth).hapus_user(999_999)


@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration"])
def test_hanya_admin_boleh_menghapus(auth, users, peran):
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        UserService(auth).hapus_user(users["CRO"])
    with pytest.raises(AuthorizationError):
        UserService(auth).arsipkan_user(users["CRO"])


def test_penghapusan_dicatat_di_audit(admin_auth, users):
    from app.models import AuditLog

    baru = _buat(users, "petugas-audit")
    UserService(admin_auth).hapus_user(baru)

    with session_scope() as s:
        aksi = s.scalars(
            sa.select(AuditLog.action).where(AuditLog.action == "DELETE_USER")
        ).all()
    assert aksi == ["DELETE_USER"]


def test_akun_nonaktif_pun_dapat_dihapus_bila_tanpa_riwayat(admin_auth, users):
    baru = _buat(users, "petugas-nonaktif")
    with session_scope() as s:
        s.execute(
            sa.update(User).where(User.id == baru).values(status=RecordStatus.INACTIVE)
        )

    UserService(admin_auth).hapus_user(baru)

    assert not _ada(baru)


# ---------------------------------------------------------------------
# Tampilan
# ---------------------------------------------------------------------


def test_tombol_hapus_arsip_ada_di_tab_pengguna(qtbot, admin_auth, users):
    from app.services.master_data_service import MasterDataService
    from app.ui.settings.master_data_page import UserTab

    tab = UserTab(UserService(admin_auth), MasterDataService(admin_auth))
    qtbot.addWidget(tab)

    teks = [b.text() for b in tab.findChildren(type(tab.tombol_status))]
    assert "Hapus / Arsipkan" in teks


def test_hapus_lewat_tab_menghapus_akun_tanpa_riwayat(
    qtbot, admin_auth, users, monkeypatch
):
    from app.services.master_data_service import MasterDataService
    from app.ui.settings import master_data_page
    from app.ui.settings.master_data_page import UserTab

    baru = _buat(users, "petugas-ui")
    monkeypatch.setattr(master_data_page, "konfirmasi", lambda *a, **k: True)
    tab = UserTab(UserService(admin_auth), MasterDataService(admin_auth))
    qtbot.addWidget(tab)
    baris = next(i for i, a in enumerate(tab.data) if a.id == baru)
    tab.tabel.selectRow(baris)

    tab.hapus_atau_arsipkan()

    assert not _ada(baru)
