"""Test login, sesi, dan penegakan hak akses."""

from __future__ import annotations

import sqlalchemy as sa
import pytest

from app.core.database import session_scope
from app.core.errors import (
    AuthenticationError,
    AuthorizationError,
    ValidationError,
)
from app.models import AuditLog, RecordStatus, User, UserRole
from app.services.permissions import Permission
from tests.conftest import TEST_PASSWORD


# ---------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------

def test_login_dengan_kredensial_benar(auth, users):
    sesi = auth.login("cro", TEST_PASSWORD)

    assert sesi.username == "cro"
    assert sesi.role is UserRole.CRO
    assert sesi.user_id == users["CRO"]
    assert auth.is_authenticated


def test_login_tidak_membedakan_huruf_besar_kecil(auth):
    """Petugas yang mengetik "CRO" atau "Cro" tetap harus bisa masuk."""
    assert auth.login("CRO", TEST_PASSWORD).username == "cro"
    auth.logout()
    assert auth.login("  Cro  ", TEST_PASSWORD).username == "cro"


def test_login_kata_sandi_salah_ditolak(auth):
    with pytest.raises(AuthenticationError):
        auth.login("cro", "salah-sekali")
    assert not auth.is_authenticated


def test_login_nama_pengguna_tidak_terdaftar_ditolak(auth):
    with pytest.raises(AuthenticationError):
        auth.login("tidak-ada", TEST_PASSWORD)
    assert not auth.is_authenticated


def test_pesan_gagal_sama_untuk_user_salah_dan_sandi_salah(auth):
    """
    Pesan yang berbeda akan membocorkan nama pengguna mana yang terdaftar.
    """
    with pytest.raises(AuthenticationError) as user_salah:
        auth.login("tidak-ada", TEST_PASSWORD)
    with pytest.raises(AuthenticationError) as sandi_salah:
        auth.login("cro", "salah-sekali")

    assert user_salah.value.user_message == sandi_salah.value.user_message


def test_login_kata_sandi_kosong_ditolak(auth):
    with pytest.raises(AuthenticationError):
        auth.login("cro", "")


def test_akun_nonaktif_tidak_dapat_masuk(auth, users):
    with session_scope() as s:
        s.get(User, users["CRO"]).status = RecordStatus.INACTIVE

    with pytest.raises(AuthenticationError):
        auth.login("cro", TEST_PASSWORD)
    assert not auth.is_authenticated


def test_last_login_at_tercatat(auth, users):
    with session_scope() as s:
        assert s.get(User, users["CRO"]).last_login_at is None

    auth.login("cro", TEST_PASSWORD)

    with session_scope() as s:
        assert s.get(User, users["CRO"]).last_login_at is not None


# ---------------------------------------------------------------------
# Sesi
# ---------------------------------------------------------------------

def test_belum_login_berarti_belum_ada_sesi(auth):
    assert auth.current_session is None
    assert not auth.is_authenticated
    with pytest.raises(AuthenticationError):
        auth.require_session()


def test_logout_menghapus_sesi(auth):
    auth.login("cro", TEST_PASSWORD)
    auth.logout()

    assert auth.current_session is None
    assert not auth.is_authenticated


def test_logout_tanpa_login_tidak_menimbulkan_error(auth):
    auth.logout()
    assert not auth.is_authenticated


def test_login_ulang_mengganti_sesi_sebelumnya(auth):
    auth.login("cro", TEST_PASSWORD)
    auth.logout()
    sesi = auth.login("supervisor", TEST_PASSWORD)

    assert sesi.role is UserRole.SUPERVISOR


def test_sesi_membawa_daftar_kewenangan(auth):
    sesi = auth.login("cro", TEST_PASSWORD)
    assert Permission.QUEUE_CALL in sesi.permissions
    assert Permission.USER_MANAGE not in sesi.permissions


def test_sesi_tidak_memuat_kata_sandi(auth):
    """Objek sesi bisa saja ikut tercetak saat debugging."""
    sesi = auth.login("cro", TEST_PASSWORD)
    isi = repr(sesi) + str(sesi.__dict__)
    assert TEST_PASSWORD not in isi
    # must_change_password adalah nama field yang sah, jadi yang diperiksa
    # adalah tidak adanya nilai kata sandi maupun hash-nya.
    assert "password_hash" not in isi
    assert "scrypt" not in isi


# ---------------------------------------------------------------------
# Penegakan hak akses
# ---------------------------------------------------------------------

def test_cro_boleh_memanggil_antrian(auth):
    auth.login("cro", TEST_PASSWORD)
    assert auth.has_permission(Permission.QUEUE_CALL)
    assert auth.require_permission(Permission.QUEUE_CALL).username == "cro"


def test_cro_tidak_boleh_mengelola_user(auth):
    auth.login("cro", TEST_PASSWORD)
    assert not auth.has_permission(Permission.USER_MANAGE)
    with pytest.raises(AuthorizationError):
        auth.require_permission(Permission.USER_MANAGE)


def test_registration_tidak_boleh_melayani(auth):
    auth.login("registration", TEST_PASSWORD)
    with pytest.raises(AuthorizationError):
        auth.require_permission(Permission.QUEUE_COMPLETE)


def test_supervisor_tidak_boleh_mengubah_antrian(auth):
    auth.login("supervisor", TEST_PASSWORD)
    assert auth.has_permission(Permission.REPORT_VIEW)
    with pytest.raises(AuthorizationError):
        auth.require_permission(Permission.QUEUE_CALL)


def test_display_tidak_boleh_apa_pun_selain_display(auth):
    auth.login("display", TEST_PASSWORD)
    assert auth.has_permission(Permission.DISPLAY_VIEW)
    for permission in (
        Permission.QUEUE_CREATE,
        Permission.QUEUE_CALL,
        Permission.REPORT_VIEW,
        Permission.USER_MANAGE,
    ):
        with pytest.raises(AuthorizationError):
            auth.require_permission(permission)


def test_tanpa_login_seluruh_kewenangan_ditolak(auth):
    assert not auth.has_permission(Permission.QUEUE_CALL)
    with pytest.raises(AuthenticationError):
        auth.require_permission(Permission.QUEUE_CALL)


# ---------------------------------------------------------------------
# Wajib ganti kata sandi
# ---------------------------------------------------------------------

def test_user_wajib_ganti_sandi_tidak_dapat_bekerja(auth, users):
    """Akun bawaan tidak boleh dipakai bekerja sebelum sandinya diganti."""
    with session_scope() as s:
        s.get(User, users["CRO"]).must_change_password = True

    sesi = auth.login("cro", TEST_PASSWORD)
    assert sesi.must_change_password is True
    assert not auth.has_permission(Permission.QUEUE_CALL)
    with pytest.raises(AuthorizationError):
        auth.require_permission(Permission.QUEUE_CALL)


def test_setelah_ganti_sandi_kewenangan_pulih(auth, users):
    with session_scope() as s:
        s.get(User, users["CRO"]).must_change_password = True

    auth.login("cro", TEST_PASSWORD)
    auth.change_password(TEST_PASSWORD, "sandibaru123")

    assert auth.current_session.must_change_password is False
    assert auth.has_permission(Permission.QUEUE_CALL)


# ---------------------------------------------------------------------
# Ganti kata sandi
# ---------------------------------------------------------------------

def test_ganti_sandi_berhasil_dan_sandi_lama_tidak_berlaku(auth):
    auth.login("cro", TEST_PASSWORD)
    auth.change_password(TEST_PASSWORD, "sandibaru123")
    auth.logout()

    with pytest.raises(AuthenticationError):
        auth.login("cro", TEST_PASSWORD)
    assert auth.login("cro", "sandibaru123").username == "cro"


def test_ganti_sandi_dengan_sandi_lama_yang_salah_ditolak(auth):
    auth.login("cro", TEST_PASSWORD)
    with pytest.raises(AuthenticationError):
        auth.change_password("bukan-sandi-saya", "sandibaru123")


def test_sandi_baru_harus_berbeda(auth):
    auth.login("cro", TEST_PASSWORD)
    with pytest.raises(ValidationError):
        auth.change_password(TEST_PASSWORD, TEST_PASSWORD)


def test_sandi_baru_harus_memenuhi_syarat(auth):
    auth.login("cro", TEST_PASSWORD)
    with pytest.raises(ValidationError):
        auth.change_password(TEST_PASSWORD, "123")


def test_ganti_sandi_tanpa_login_ditolak(auth):
    with pytest.raises(AuthenticationError):
        auth.change_password(TEST_PASSWORD, "sandibaru123")


# ---------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------

def _aksi_tercatat() -> list[str]:
    with session_scope() as s:
        return [row.action for row in s.scalars(sa.select(AuditLog))]


def test_login_berhasil_tercatat(auth):
    auth.login("cro", TEST_PASSWORD)
    assert "LOGIN" in _aksi_tercatat()


def test_login_gagal_tercatat(auth):
    """Percobaan masuk yang gagal justru yang paling perlu terlihat."""
    with pytest.raises(AuthenticationError):
        auth.login("cro", "salah-sekali")
    assert "LOGIN_FAILED" in _aksi_tercatat()


def test_logout_tercatat(auth):
    auth.login("cro", TEST_PASSWORD)
    auth.logout()
    assert "LOGOUT" in _aksi_tercatat()


def test_ganti_sandi_tercatat(auth):
    auth.login("cro", TEST_PASSWORD)
    auth.change_password(TEST_PASSWORD, "sandibaru123")
    assert "CHANGE_PASSWORD" in _aksi_tercatat()


def test_audit_log_tidak_memuat_kata_sandi(auth):
    """Aturan mutlak: kredensial tidak boleh masuk audit log."""
    auth.login("cro", TEST_PASSWORD)
    auth.change_password(TEST_PASSWORD, "sandibaru123")
    auth.logout()
    with pytest.raises(AuthenticationError):
        auth.login("cro", "tebakan-sandi")

    with session_scope() as s:
        isi = " ".join(row.meta or "" for row in s.scalars(sa.select(AuditLog)))

    assert TEST_PASSWORD not in isi
    assert "sandibaru123" not in isi
    assert "tebakan-sandi" not in isi
