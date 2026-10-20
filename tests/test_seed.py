"""Test data awal."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.core.database import session_scope
from app.core.seed import seed_initial_data
from app.models import (
    ApplicationSetting,
    Branch,
    Counter,
    RecordStatus,
    ServiceCategory,
)


def test_seed_membuat_data_master(database):
    """
    Seed pertama membuat seluruh data awal.

    Jumlah pengaturan dihitung dari daftarnya sendiri, bukan angka tetap.
    Angka tetap basi setiap kali satu pengaturan ditambahkan, dan test yang
    gagal karena hal itu tidak menandakan apa pun selain dirinya sendiri
    ketinggalan.
    """
    from app.core.seed import _CATEGORIES, _SETTINGS

    hasil = seed_initial_data()
    assert hasil == {
        "counters": 3,
        "categories": len(_CATEGORIES),
        "settings": len(_SETTINGS),
        "users": 1,
    }

    with session_scope() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(Branch)) == 1
        assert s.scalar(sa.select(sa.func.count()).select_from(Counter)) == 3
        assert s.scalar(
            sa.select(sa.func.count()).select_from(ServiceCategory)
        ) == len(_CATEGORIES)
        assert s.scalar(
            sa.select(sa.func.count()).select_from(ApplicationSetting)
        ) == len(_SETTINGS)


def test_seed_idempotent(database):
    """Aplikasi menjalankan seed setiap start; tidak boleh menumpuk data."""
    seed_initial_data()
    kedua = seed_initial_data()
    ketiga = seed_initial_data()

    kosong = {"counters": 0, "categories": 0, "settings": 0, "users": 0}
    assert kedua == kosong
    assert ketiga == kosong

    with session_scope() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(Counter)) == 3


@pytest.mark.layanan_bertingkat
def test_prefix_jenis_layanan_sesuai_rancangan(seeded):
    """
    Prefix seluruh jenis layanan bawaan, beserta induknya.

    Prefix wajib unik dalam satu cabang; dua yang sama membuat nomor
    antrian keduanya bertabrakan. Daftar ini karena itu dikunci utuh,
    bukan hanya tiga yang teratas.
    """
    with session_scope() as s:
        kategori = s.scalars(
            sa.select(ServiceCategory).order_by(ServiceCategory.id)
        ).all()
        nama_per_id = {c.id: c.name for c in kategori}
        assert [
            (c.prefix, c.name, nama_per_id.get(c.parent_id)) for c in kategori
        ] == [
            ("A", "Konsultasi", None),
            ("PB", "PBB", "Konsultasi"),
            ("KB", "PKB", "Konsultasi"),
            ("AT", "PAT", "Konsultasi"),
            ("RK", "Reklame", "Konsultasi"),
            ("PJ", "PBJT", "Konsultasi"),
            ("RS", "Restoran", "PBJT"),
            ("PR", "Parkir", "PBJT"),
            ("HT", "Hotel", "PBJT"),
            ("HB", "Hiburan", "PBJT"),
            ("B", "Pengaduan", None),
            ("C", "Informasi", None),
        ]


def test_data_master_berstatus_aktif(seeded):
    with session_scope() as s:
        assert all(
            c.status is RecordStatus.ACTIVE for c in s.scalars(sa.select(Counter))
        )
        assert all(
            c.status is RecordStatus.ACTIVE
            for c in s.scalars(sa.select(ServiceCategory))
        )


def test_seed_membuat_admin_bawaan_yang_wajib_ganti_sandi(database):
    """
    Aplikasi harus bisa dipakai saat pertama dipasang, tetapi kata sandi
    bawaan tidak boleh dibiarkan terpakai terus.
    """
    from app.core.seed import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME
    from app.core.security import verify_password
    from app.models import User, UserRole

    seed_initial_data()
    with session_scope() as s:
        admin = s.scalar(sa.select(User).where(User.username == DEFAULT_ADMIN_USERNAME))
        assert admin is not None
        assert admin.role is UserRole.ADMIN
        assert admin.must_change_password is True
        assert verify_password(DEFAULT_ADMIN_PASSWORD, admin.password_hash)
        # Kata sandi tidak boleh tersimpan apa adanya.
        assert DEFAULT_ADMIN_PASSWORD not in admin.password_hash


def test_admin_bawaan_tidak_dibuat_ulang_bila_sudah_ada_user(database):
    """Admin yang sengaja dihapus setelah ada akun lain tidak boleh muncul lagi."""
    from app.models import User

    seed_initial_data()
    with session_scope() as s:
        jumlah_awal = s.scalar(sa.select(sa.func.count()).select_from(User))

    seed_initial_data()
    with session_scope() as s:
        assert s.scalar(sa.select(sa.func.count()).select_from(User)) == jumlah_awal


def test_pengaturan_penting_tersedia(seeded):
    with session_scope() as s:
        keys = {row.key for row in s.scalars(sa.select(ApplicationSetting))}
    assert {
        "ticket.footer",
        "survey.enabled",
        "queue.max_call_attempts",
        "kiosk.cooldown_seconds",
        "dashboard.refresh_seconds",
        "backup.auto_enabled",
        "backup.retention_days",
    } <= keys


def test_seluruh_bawaan_ikut_di_seed():
    """
    Setiap pengaturan yang dikenali aplikasi harus punya baris di database.

    Tanpa ini, pengaturan baru hanya hidup sebagai nilai bawaan di kode dan
    tidak pernah muncul di layar administrasi untuk diubah.
    """
    from app.core.seed import _SETTINGS
    from app.services.settings_service import BAWAAN

    assert {kunci for kunci, _, _ in _SETTINGS} == set(BAWAAN)
