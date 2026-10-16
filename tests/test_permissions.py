"""
Test matriks hak akses.

Test di sini mengunci pembagian kewenangan sesuai spesifikasi. Bila salah
satu gagal, artinya matriks berubah — dan itu perubahan aturan bisnis yang
harus disengaja, bukan efek samping.
"""

from __future__ import annotations

import pytest

from app.models import UserRole
from app.services.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    permissions_for,
    role_has_permission,
)


def test_setiap_peran_punya_definisi_hak_akses():
    """Peran tanpa definisi akan diam-diam kehilangan seluruh kewenangan."""
    assert set(ROLE_PERMISSIONS) == set(UserRole)


# ---------------------------------------------------------------------
# Kewenangan yang harus dimiliki
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("role", "permission"),
    [
        (UserRole.REGISTRATION, Permission.QUEUE_CREATE),
        (UserRole.REGISTRATION, Permission.TICKET_PRINT),
        (UserRole.CRO, Permission.QUEUE_CALL),
        (UserRole.CRO, Permission.QUEUE_SERVE),
        (UserRole.CRO, Permission.QUEUE_COMPLETE),
        (UserRole.CRO, Permission.QUEUE_NO_SHOW),
        (UserRole.CRO, Permission.QUEUE_CANCEL),
        (UserRole.SUPERVISOR, Permission.DASHBOARD_VIEW),
        (UserRole.SUPERVISOR, Permission.REPORT_VIEW),
        (UserRole.SUPERVISOR, Permission.SURVEY_VIEW),
        (UserRole.ADMIN, Permission.USER_MANAGE),
        (UserRole.ADMIN, Permission.MASTER_MANAGE),
        (UserRole.ADMIN, Permission.CONFIG_MANAGE),
        (UserRole.ADMIN, Permission.REPORT_VIEW),
        (UserRole.DISPLAY, Permission.DISPLAY_VIEW),
    ],
)
def test_peran_memiliki_kewenangannya(role, permission):
    assert role_has_permission(role, permission)


# ---------------------------------------------------------------------
# Kewenangan yang harus DITOLAK
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("role", "permission"),
    [
        # Pendaftaran menerbitkan nomor, tidak melayani.
        (UserRole.REGISTRATION, Permission.QUEUE_CALL),
        (UserRole.REGISTRATION, Permission.QUEUE_COMPLETE),
        (UserRole.REGISTRATION, Permission.USER_MANAGE),
        # CRO melayani, tidak menerbitkan nomor dan tidak mengelola user.
        (UserRole.CRO, Permission.QUEUE_CREATE),
        (UserRole.CRO, Permission.USER_MANAGE),
        (UserRole.CRO, Permission.CONFIG_MANAGE),
        # Supervisor memantau, tidak mengubah antrian.
        (UserRole.SUPERVISOR, Permission.QUEUE_CALL),
        (UserRole.SUPERVISOR, Permission.QUEUE_COMPLETE),
        (UserRole.SUPERVISOR, Permission.USER_MANAGE),
        # Admin mengelola sistem, tidak melayani antrian.
        (UserRole.ADMIN, Permission.QUEUE_CALL),
        (UserRole.ADMIN, Permission.QUEUE_CREATE),
    ],
)
def test_peran_tidak_memiliki_kewenangan_di_luar_tugasnya(role, permission):
    assert not role_has_permission(role, permission)


def test_display_hanya_boleh_melihat_layar():
    """
    Aturan tegas: layar antrian tidak boleh punya fungsi administrasi.

    Komputer display biasanya menghadap publik dan tidak diawasi.
    """
    assert permissions_for(UserRole.DISPLAY) == frozenset({Permission.DISPLAY_VIEW})


def test_display_tidak_dapat_menyentuh_antrian():
    for permission in (
        Permission.QUEUE_CREATE,
        Permission.QUEUE_CALL,
        Permission.QUEUE_SERVE,
        Permission.QUEUE_COMPLETE,
        Permission.QUEUE_CANCEL,
        Permission.USER_MANAGE,
        Permission.REPORT_VIEW,
    ):
        assert not role_has_permission(UserRole.DISPLAY, permission)


def test_tidak_ada_peran_yang_memiliki_semua_kewenangan():
    """Pemisahan tugas: tidak ada satu akun pun yang bisa melakukan segalanya."""
    semua = set(Permission)
    for role in UserRole:
        assert permissions_for(role) != semua
