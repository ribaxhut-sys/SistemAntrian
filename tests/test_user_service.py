"""Test administrasi user."""

from __future__ import annotations

import pytest

from app.core.errors import (
    AuthorizationError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)
from app.models import UserRole
from app.services.user_service import UserService
from tests.conftest import TEST_PASSWORD


# ---------------------------------------------------------------------
# Pembacaan
# ---------------------------------------------------------------------

def test_admin_dapat_melihat_daftar_user(user_service):
    daftar = user_service.list_users()
    assert {u.username for u in daftar} >= {"admin", "cro", "supervisor", "display"}


def test_daftar_user_tidak_memuat_hash_kata_sandi(user_service):
    """UserInfo bisa saja ikut tercetak saat debugging atau masuk log."""
    daftar = user_service.list_users()
    isi = " ".join(repr(u) for u in daftar)

    assert "password_hash" not in isi
    assert "scrypt" not in isi


@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration", "display"])
def test_selain_admin_tidak_dapat_melihat_daftar_user(auth, peran):
    auth.login(peran, TEST_PASSWORD)
    with pytest.raises(AuthorizationError):
        UserService(auth).list_users()


# ---------------------------------------------------------------------
# Pembuatan
# ---------------------------------------------------------------------

def test_admin_dapat_membuat_user(user_service):
    user_id = user_service.create_user(
        username="cro2",
        full_name="Petugas CRO Dua",
        password="sandibaru123",
        role=UserRole.CRO,
    )

    dibuat = user_service.get_user(user_id)
    assert dibuat.username == "cro2"
    assert dibuat.role is UserRole.CRO
    assert dibuat.is_active
    assert dibuat.must_change_password is True


def test_user_baru_wajib_ganti_sandi_secara_bawaan(user_service, auth):
    """Admin tidak boleh terus mengetahui kata sandi petugas."""
    user_service.create_user(
        username="cro2",
        full_name="Petugas CRO Dua",
        password="sandibaru123",
        role=UserRole.CRO,
    )
    auth.logout()

    sesi = auth.login("cro2", "sandibaru123")
    assert sesi.must_change_password is True


def test_user_baru_dapat_langsung_bekerja_bila_diminta(user_service, auth):
    user_service.create_user(
        username="cro2",
        full_name="Petugas CRO Dua",
        password="sandibaru123",
        role=UserRole.CRO,
        must_change_password=False,
    )
    auth.logout()

    assert auth.login("cro2", "sandibaru123").must_change_password is False


def test_nama_pengguna_dinormalkan(user_service, auth):
    user_service.create_user(
        username="  CRO2  ",
        full_name="Petugas CRO Dua",
        password="sandibaru123",
        role=UserRole.CRO,
        must_change_password=False,
    )
    auth.logout()
    assert auth.login("cro2", "sandibaru123").username == "cro2"


def test_nama_pengguna_ganda_ditolak(user_service):
    with pytest.raises(ValidationError):
        user_service.create_user(
            username="CRO",  # sudah ada sebagai "cro"
            full_name="Kembar",
            password="sandibaru123",
            role=UserRole.CRO,
        )


@pytest.mark.parametrize("kosong", ["", "   "])
def test_nama_pengguna_dan_nama_lengkap_wajib(user_service, kosong):
    with pytest.raises(ValidationError):
        user_service.create_user(
            username=kosong,
            full_name="Seseorang",
            password="sandibaru123",
            role=UserRole.CRO,
        )
    with pytest.raises(ValidationError):
        user_service.create_user(
            username="baru",
            full_name=kosong,
            password="sandibaru123",
            role=UserRole.CRO,
        )


def test_kata_sandi_lemah_ditolak(user_service):
    with pytest.raises(ValidationError):
        user_service.create_user(
            username="baru",
            full_name="Petugas Baru",
            password="123",
            role=UserRole.CRO,
        )


@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration", "display"])
def test_selain_admin_tidak_dapat_membuat_user(auth, peran):
    auth.login(peran, TEST_PASSWORD)
    with pytest.raises(AuthorizationError):
        UserService(auth).create_user(
            username="penyusup",
            full_name="Penyusup",
            password="sandibaru123",
            role=UserRole.ADMIN,
        )


def test_membuat_user_tanpa_login_ditolak(auth):
    from app.core.errors import AuthenticationError

    auth.logout()
    with pytest.raises(AuthenticationError):
        UserService(auth).create_user(
            username="siapa",
            full_name="Siapa Saja",
            password="sandibaru123",
            role=UserRole.ADMIN,
        )


# ---------------------------------------------------------------------
# Perubahan
# ---------------------------------------------------------------------

def test_nama_dan_peran_dapat_diubah(user_service, users):
    diubah = user_service.update_user(
        users["CRO"], full_name="Petugas CRO Senior", role=UserRole.SUPERVISOR
    )

    assert diubah.full_name == "Petugas CRO Senior"
    assert diubah.role is UserRole.SUPERVISOR


def test_admin_tidak_dapat_mengubah_perannya_sendiri(user_service, users):
    """Satu klik keliru bisa membuat sistem kehilangan seluruh admin."""
    with pytest.raises(BusinessRuleError) as gagal:
        user_service.update_user(
            users["ADMIN"], full_name="Administrator", role=UserRole.CRO
        )

    assert "akun Anda sendiri" in gagal.value.user_message


def test_admin_aktif_terakhir_tidak_dapat_diturunkan_perannya(user_service, users, auth):
    """
    Admin kedua menurunkan peran admin pertama; saat tinggal satu admin,
    penurunan terakhir harus ditolak.
    """
    id_admin2 = user_service.create_user(
        username="admin2",
        full_name="Administrator Dua",
        password="sandibaru123",
        role=UserRole.ADMIN,
        must_change_password=False,
    )

    # admin2 menurunkan admin pertama — masih boleh, karena admin2 tetap ada.
    auth.logout()
    auth.login("admin2", "sandibaru123")
    service = UserService(auth)
    service.update_user(users["ADMIN"], full_name="Administrator", role=UserRole.CRO)

    # Kini admin2 satu-satunya admin, dan tidak ada yang berhak menurunkannya.
    with pytest.raises(BusinessRuleError):
        service.update_user(id_admin2, full_name="Administrator Dua", role=UserRole.CRO)


def test_nama_lengkap_kosong_ditolak_saat_mengubah(user_service, users):
    with pytest.raises(ValidationError):
        user_service.update_user(users["CRO"], full_name="   ", role=UserRole.CRO)


def test_user_tidak_dikenal_ditolak(user_service):
    with pytest.raises(NotFoundError):
        user_service.get_user(999999)
    with pytest.raises(NotFoundError):
        user_service.update_user(999999, full_name="Hantu", role=UserRole.CRO)


# ---------------------------------------------------------------------
# Aktif / nonaktif
# ---------------------------------------------------------------------

def test_user_dapat_dinonaktifkan_dan_tidak_dapat_login(user_service, users, auth):
    user_service.set_user_status(users["CRO"], False)
    auth.logout()

    from app.core.errors import AuthenticationError

    with pytest.raises(AuthenticationError):
        auth.login("cro", TEST_PASSWORD)


def test_user_dapat_diaktifkan_kembali(user_service, users, auth):
    user_service.set_user_status(users["CRO"], False)
    assert user_service.set_user_status(users["CRO"], True).is_active

    auth.logout()
    assert auth.login("cro", TEST_PASSWORD).username == "cro"


def test_admin_tidak_dapat_menonaktifkan_dirinya_sendiri(user_service, users):
    """Mengunci diri sendiri keluar dari aplikasi tidak dapat dibatalkan."""
    with pytest.raises(BusinessRuleError) as gagal:
        user_service.set_user_status(users["ADMIN"], False)

    assert "akun Anda sendiri" in gagal.value.user_message


def test_admin_aktif_terakhir_tidak_dapat_dinonaktifkan(user_service, auth):
    id_admin2 = user_service.create_user(
        username="admin2",
        full_name="Administrator Dua",
        password="sandibaru123",
        role=UserRole.ADMIN,
        must_change_password=False,
    )

    auth.logout()
    auth.login("admin2", "sandibaru123")
    service = UserService(auth)

    # Menonaktifkan admin pertama masih boleh — admin2 tetap ada.
    daftar = {u.username: u.id for u in service.list_users()}
    service.set_user_status(daftar["admin"], False)

    # Menonaktifkan diri sendiri tetap ditolak, dan ia satu-satunya admin.
    with pytest.raises(BusinessRuleError):
        service.set_user_status(id_admin2, False)


# ---------------------------------------------------------------------
# Reset kata sandi
# ---------------------------------------------------------------------

def test_admin_dapat_menyetel_ulang_kata_sandi(user_service, users, auth):
    user_service.reset_password(users["CRO"], "sandidarurat1")
    auth.logout()

    sesi = auth.login("cro", "sandidarurat1")
    assert sesi.must_change_password is True, "sandi sementara wajib diganti"


def test_kata_sandi_lama_tidak_berlaku_setelah_disetel_ulang(user_service, users, auth):
    from app.core.errors import AuthenticationError

    user_service.reset_password(users["CRO"], "sandidarurat1")
    auth.logout()

    with pytest.raises(AuthenticationError):
        auth.login("cro", TEST_PASSWORD)


def test_setel_ulang_dengan_kata_sandi_lemah_ditolak(user_service, users):
    with pytest.raises(ValidationError):
        user_service.reset_password(users["CRO"], "12")


@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration", "display"])
def test_selain_admin_tidak_dapat_menyetel_ulang_kata_sandi(auth, users, peran):
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        UserService(auth).reset_password(users["ADMIN"], "sandibaru123")


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def test_perubahan_user_tercatat_tanpa_kata_sandi(user_service, users):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    user_service.create_user(
        username="cro2",
        full_name="Petugas CRO Dua",
        password="sandirahasia9",
        role=UserRole.CRO,
    )
    user_service.set_user_status(users["CRO"], False)
    user_service.reset_password(users["SUPERVISOR"], "sandidarurat1")

    with session_scope() as s:
        semua = list(s.scalars(sa.select(AuditLog)))
        aksi = {r.action for r in semua}
        isi = " ".join(r.meta or "" for r in semua)

    assert {"CREATE_USER", "UPDATE_USER", "CHANGE_PASSWORD"} <= aksi
    assert "sandirahasia9" not in isi
    assert "sandidarurat1" not in isi
