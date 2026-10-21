"""
Test pengaturan aplikasi.

Yang dikunci di sini terutama validasi: pengaturan yang rusak tidak boleh
sampai tersimpan, karena akibatnya baru terasa jauh kemudian — di layar
yang membacanya, bukan di layar yang mengubahnya.
"""

from __future__ import annotations

import pytest

from app.core.errors import AuthorizationError, NotFoundError, ValidationError
from app.services.settings_service import (
    BAWAAN,
    SKEMA,
    SKEMA_PER_KUNCI,
    SettingsService,
    kelompok_pengaturan,
)
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def settings(admin_auth):
    """SettingsService dengan sesi ADMIN."""
    return SettingsService(admin_auth)


# ---------------------------------------------------------------------
# Skema
# ---------------------------------------------------------------------

def test_skema_mencakup_seluruh_pengaturan_yang_dikenali():
    """Pengaturan tanpa keterangan tidak akan pernah muncul di layar."""
    assert {p.kunci for p in SKEMA} == set(BAWAAN)


def test_nilai_bawaan_lolos_validasinya_sendiri(settings):
    """Bawaan yang ditolak validasinya berarti salah satunya keliru."""
    for kunci, nilai in BAWAAN.items():
        settings.set(kunci, nilai)


def test_setiap_pengaturan_yang_tampil_punya_kelompok():
    kelompok = kelompok_pengaturan()
    tampil = [p for p in SKEMA if p.tampil]

    assert sum(len(b) for b in kelompok.values()) == len(tampil)
    assert all(nama for nama in kelompok)


def test_pengaturan_tersembunyi_tidak_muncul_di_formulir():
    """
    Pasangan buka/tutup pendaftaran WAJIB berubah bersama-sama.

    Formulir Pengaturan hanya menyetel satu kunci sekaligus, sehingga
    mematikan `queue.registration_open` dari sana tidak menutup apa pun —
    `pendaftaran_dibuka()` menganggap penutupan tanpa tanggal hari ini
    sudah kedaluwarsa. Admin akan mengira pendaftaran berhenti padahal
    nomor terus terbit, dan tidak ada pesan apa pun yang memberi tahu.
    """
    tampil = {p.kunci for b in kelompok_pengaturan().values() for p in b}

    assert "queue.registration_open" not in tampil
    assert "queue.registration_closed_date" not in tampil


def test_pengaturan_tersembunyi_tetap_dikenali_service(settings):
    """Disembunyikan dari formulir, bukan dihapus: service tetap memakainya."""
    settings.set("queue.registration_open", "false")

    assert settings.get("queue.registration_open") == "false"


# ---------------------------------------------------------------------
# Pembacaan
# ---------------------------------------------------------------------

def test_membaca_pengaturan_tidak_menuntut_hak_akses(auth, seeded):
    """Teks tiket dibutuhkan hampir semua peran."""
    auth.logout()

    assert SettingsService().get("ticket.footer")


def test_pengaturan_yang_belum_ada_memakai_bawaan(database):
    """Database lama yang dibuat sebelum sebuah pengaturan diperkenalkan."""
    assert SettingsService().get("backup.retention_days") == "30"


def test_pengaturan_tidak_dikenal_ditolak(settings):
    with pytest.raises(NotFoundError):
        settings.get("tidak.pernah.ada")


# ---------------------------------------------------------------------
# Perubahan
# ---------------------------------------------------------------------

def test_perubahan_tersimpan_dan_terbaca(settings):
    settings.set("ticket.footer", "TERIMA KASIH PUSAT")

    assert settings.get("ticket.footer") == "TERIMA KASIH PUSAT"


def test_perubahan_tercatat_di_audit(settings):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    settings.set("ticket.footer", "PENUTUP BARU")

    with session_scope() as session:
        aksi = list(
            session.scalars(
                sa.select(AuditLog.action).where(
                    AuditLog.action == "CHANGE_CONFIGURATION"
                )
            )
        )

    assert aksi == ["CHANGE_CONFIGURATION"]


# ---------------------------------------------------------------------
# Validasi
# ---------------------------------------------------------------------

def test_pengaturan_tidak_dikenal_tidak_dapat_disimpan(settings):
    with pytest.raises(NotFoundError):
        settings.set("tidak.pernah.ada", "apa pun")


@pytest.mark.parametrize("nilai", ["xyz", "PDF ", "", "printer"])
def test_cara_cetak_di_luar_pilihan_ditolak(settings, nilai):
    """ticket.printer bernilai asal baru terasa saat tiket pertama gagal dicetak."""
    with pytest.raises(ValidationError) as info:
        settings.set("ticket.printer", nilai)

    assert "hanya boleh bernilai" in info.value.user_message


def test_cara_cetak_yang_sah_diterima(settings):
    for nilai in ("pdf", "system", "none"):
        settings.set("ticket.printer", nilai)
        assert settings.get("ticket.printer") == nilai


def test_geser_atas_tiket_dibatasi(settings):
    with pytest.raises(ValidationError):
        settings.set("ticket.geser_atas_mm", "7")
    settings.set("ticket.geser_atas_mm", "0")
    assert settings.get("ticket.geser_atas_mm") == "0"


def test_jenis_sambutan_anjungan_yang_tidak_dikenal_ditolak(settings):
    with pytest.raises(ValidationError):
        settings.set("kiosk.welcome_kind", "youtube")

    settings.set("kiosk.welcome_kind", "gambar")
    assert settings.get("kiosk.welcome_kind") == "media"
    settings.set("kiosk.welcome_kind", "media")
    assert settings.get("kiosk.welcome_kind") == "media"


def test_angka_bukan_bilangan_ditolak(settings):
    with pytest.raises(ValidationError) as info:
        settings.set("dashboard.refresh_seconds", "cepat")

    assert "harus berupa angka" in info.value.user_message


def test_angka_di_bawah_batas_ditolak(settings):
    """Penyegaran tiap 1 detik akan menyiksa database sepanjang hari."""
    with pytest.raises(ValidationError) as info:
        settings.set("dashboard.refresh_seconds", "1")

    assert "kurang dari 5" in info.value.user_message


def test_angka_di_atas_batas_ditolak(settings):
    with pytest.raises(ValidationError) as info:
        settings.set("display.next_count", "999")

    assert "lebih dari 10" in info.value.user_message


def test_retensi_nol_tetap_diterima(settings):
    """Nol berarti mematikan penghapusan otomatis, bukan salah ketik."""
    settings.set("backup.retention_days", "0")

    assert settings.get("backup.retention_days") == "0"


def test_teks_kosong_ditolak(settings):
    with pytest.raises(ValidationError) as info:
        settings.set("ticket.footer", "   ")

    assert "tidak boleh dikosongkan" in info.value.user_message


@pytest.mark.parametrize(
    ("masukan", "tersimpan"),
    [
        ("true", "true"),
        ("ya", "true"),
        ("1", "true"),
        ("ON", "true"),
        ("false", "false"),
        ("tidak", "false"),
        ("apa pun", "false"),
    ],
)
def test_boleh_tidak_dibakukan_saat_disimpan(settings, masukan, tersimpan):
    """Disimpan seragam supaya nilainya terbaca sama oleh siapa pun."""
    settings.set("survey.enabled", masukan)

    assert settings.get("survey.enabled") == tersimpan


def test_angka_dibakukan_saat_disimpan(settings):
    settings.set("display.next_count", " 04 ")

    assert settings.get("display.next_count") == "4"


# ---------------------------------------------------------------------
# Hak akses
# ---------------------------------------------------------------------

@pytest.mark.parametrize("peran", ["cro", "supervisor", "registration", "display"])
def test_hanya_admin_yang_boleh_mengubah_pengaturan(auth, users, peran):
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        SettingsService(auth).set("ticket.footer", "COBA")


def test_tanpa_sesi_tidak_dapat_mengubah_pengaturan(seeded):
    with pytest.raises(NotFoundError):
        SettingsService().set("ticket.footer", "COBA")


def test_batas_angka_konsisten(settings):
    """Batas bawah tidak boleh lebih besar daripada batas atas."""
    for butir in SKEMA_PER_KUNCI.values():
        if butir.minimum is not None and butir.maksimum is not None:
            assert butir.minimum <= butir.maksimum
