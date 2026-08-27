"""
Hak akses per peran.

Matriks di bawah adalah satu-satunya sumber kebenaran soal siapa boleh
melakukan apa. UI hanya boleh memakainya untuk menyembunyikan tombol;
penegakan sesungguhnya tetap dilakukan service layer, karena UI dapat
dilewati sedangkan service tidak.
"""

from __future__ import annotations

from enum import Enum

from app.models import UserRole


class Permission(str, Enum):
    """Tindakan yang dapat dikendalikan hak aksesnya."""

    # Penerbitan antrian
    QUEUE_CREATE = "QUEUE_CREATE"
    TICKET_PRINT = "TICKET_PRINT"

    # Pelayanan
    QUEUE_VIEW = "QUEUE_VIEW"
    QUEUE_CALL = "QUEUE_CALL"
    QUEUE_SERVE = "QUEUE_SERVE"
    QUEUE_COMPLETE = "QUEUE_COMPLETE"
    QUEUE_CANCEL = "QUEUE_CANCEL"
    QUEUE_NO_SHOW = "QUEUE_NO_SHOW"
    QUEUE_CLOSE_DAY = "QUEUE_CLOSE_DAY"
    QUEUE_TOGGLE_INTAKE = "QUEUE_TOGGLE_INTAKE"

    # Layar antrian
    DISPLAY_VIEW = "DISPLAY_VIEW"

    # Survey
    SURVEY_SUBMIT = "SURVEY_SUBMIT"
    SURVEY_VIEW = "SURVEY_VIEW"

    # Pemantauan
    DASHBOARD_VIEW = "DASHBOARD_VIEW"
    REPORT_VIEW = "REPORT_VIEW"

    # Administrasi
    MASTER_MANAGE = "MASTER_MANAGE"
    USER_MANAGE = "USER_MANAGE"
    CONFIG_MANAGE = "CONFIG_MANAGE"
    BACKUP_MANAGE = "BACKUP_MANAGE"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    # Menerbitkan nomor antrian dan mencetak tiket.
    UserRole.REGISTRATION: frozenset(
        {
            Permission.QUEUE_CREATE,
            Permission.TICKET_PRINT,
            Permission.QUEUE_VIEW,
            Permission.QUEUE_TOGGLE_INTAKE,
        }
    ),
    # Petugas yang memanggil dan melayani pengunjung.
    UserRole.CRO: frozenset(
        {
            Permission.QUEUE_VIEW,
            Permission.QUEUE_CALL,
            Permission.QUEUE_SERVE,
            Permission.QUEUE_COMPLETE,
            Permission.QUEUE_CANCEL,
            Permission.QUEUE_NO_SHOW,
            Permission.SURVEY_SUBMIT,
        }
    ),
    # Pemantauan dan pelaporan, tanpa kewenangan mengubah antrian.
    UserRole.SUPERVISOR: frozenset(
        {
            Permission.QUEUE_VIEW,
            Permission.DASHBOARD_VIEW,
            Permission.REPORT_VIEW,
            Permission.SURVEY_VIEW,
        }
    ),
    # Pengelolaan data master, user, konfigurasi, dan backup.
    UserRole.ADMIN: frozenset(
        {
            Permission.MASTER_MANAGE,
            Permission.USER_MANAGE,
            Permission.CONFIG_MANAGE,
            Permission.BACKUP_MANAGE,
            Permission.QUEUE_CLOSE_DAY,
            Permission.QUEUE_TOGGLE_INTAKE,
        }
    ),
    # Hanya layar antrian, tanpa fungsi administrasi apa pun.
    UserRole.DISPLAY: frozenset({Permission.DISPLAY_VIEW}),
    # Mesin kios yang menghadap pengunjung. Berjalan tanpa login, sehingga
    # kewenangannya sengaja dibatasi pada dua hal yang memang dikerjakan
    # pengunjung sendiri: melihat papan nomor dan mengambil nomornya.
    #
    # Perhatikan yang TIDAK ada di sini: kios tidak dapat memanggil,
    # melayani, membatalkan, maupun melihat daftar antrian secara penuh.
    # Komputernya berdiri di ruang publik tanpa diawasi.
    UserRole.KIOSK: frozenset(
        {
            Permission.DISPLAY_VIEW,
            Permission.QUEUE_CREATE,
            Permission.TICKET_PRINT,
        }
    ),
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    """Hak akses yang dimiliki sebuah peran."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in permissions_for(role)
