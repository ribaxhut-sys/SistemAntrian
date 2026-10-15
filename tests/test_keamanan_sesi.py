"""
Batas percobaan login, kata sandi minimal, dan penjagaan restore.

Dikunci di sini: akun yang diserang tidak terkunci selamanya (penolakan tidak
memperpanjang penundaan), akun lain tidak terpengaruh, dan pemulihan database
tidak berjalan selagi ada loket yang masih bekerja.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import AuthenticationError, BusinessRuleError, ValidationError
from app.core.security import MIN_PASSWORD_LENGTH, validate_password_strength
from app.models import AuditAction, AuditLog, Counter
from app.services.auth_service import BATAS_LOGIN_GAGAL
from app.services.backup_service import BackupService
from tests.conftest import TEST_PASSWORD


def _gagal_login(auth, username: str, kali: int) -> None:
    for _ in range(kali):
        with pytest.raises(AuthenticationError):
            auth.login(username, "salah-sekali")


def _jumlah_gagal(username_id: int) -> int:
    with session_scope() as s:
        return s.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == AuditAction.LOGIN_FAILED.value,
                AuditLog.user_id == username_id,
            )
        )


# ---------------------------------------------------------------------
# Batas percobaan login
# ---------------------------------------------------------------------


def test_login_ditunda_setelah_terlalu_banyak_gagal(auth, users):
    _gagal_login(auth, "cro", BATAS_LOGIN_GAGAL)

    with pytest.raises(AuthenticationError, match="Terlalu banyak"):
        auth.login("cro", TEST_PASSWORD)  # kata sandi benar pun ditolak


def test_penolakan_tidak_memperpanjang_penundaan(auth, users):
    _gagal_login(auth, "cro", BATAS_LOGIN_GAGAL)
    sebelum = _jumlah_gagal(users["CRO"])

    for _ in range(3):
        with pytest.raises(AuthenticationError, match="Terlalu banyak"):
            auth.login("cro", "salah-lagi")

    assert _jumlah_gagal(users["CRO"]) == sebelum


def test_penundaan_berakhir_setelah_jendelanya_lewat(auth, users):
    _gagal_login(auth, "cro", BATAS_LOGIN_GAGAL)
    with session_scope() as s:
        s.execute(
            sa.update(AuditLog)
            .where(AuditLog.user_id == users["CRO"])
            .values(created_at=clock.now() - timedelta(minutes=30))
        )

    assert auth.login("cro", TEST_PASSWORD).username == "cro"


def test_akun_lain_tidak_ikut_ditunda(auth, users):
    _gagal_login(auth, "cro", BATAS_LOGIN_GAGAL)

    assert auth.login("supervisor", TEST_PASSWORD).username == "supervisor"


def test_gagal_di_bawah_batas_tidak_menunda(auth, users):
    _gagal_login(auth, "cro", BATAS_LOGIN_GAGAL - 1)

    assert auth.login("cro", TEST_PASSWORD).username == "cro"


# ---------------------------------------------------------------------
# Kata sandi dan kunci layar
# ---------------------------------------------------------------------


def test_kata_sandi_minimal_delapan_karakter():
    assert MIN_PASSWORD_LENGTH == 8
    with pytest.raises(ValidationError):
        validate_password_strength("1234567")
    validate_password_strength("12345678")


def test_verifikasi_kata_sandi_untuk_kunci_layar(auth, users):
    auth.login("cro", TEST_PASSWORD)

    assert auth.verifikasi_kata_sandi(TEST_PASSWORD) is True
    assert auth.verifikasi_kata_sandi("bukan-sandinya") is False


def test_kunci_layar_tidak_dapat_ditebak_tanpa_batas(auth, users):
    auth.login("cro", TEST_PASSWORD)
    for _ in range(BATAS_LOGIN_GAGAL):
        assert auth.verifikasi_kata_sandi("salah") is False

    with pytest.raises(AuthenticationError, match="Terlalu banyak"):
        auth.verifikasi_kata_sandi(TEST_PASSWORD)


# ---------------------------------------------------------------------
# Restore tidak berjalan selagi loket bekerja
# ---------------------------------------------------------------------


@pytest.fixture
def backup(admin_auth, antrian_siap, mesin_backup_tersedia):
    return BackupService(admin_auth)


def _tandai_hadir(counter_id: int, user_id: int, umur: timedelta) -> None:
    with session_scope() as s:
        s.execute(
            sa.update(Counter)
            .where(Counter.id == counter_id)
            .values(petugas_user_id=user_id, petugas_terlihat_pada=clock.now() - umur)
        )


def test_restore_ditolak_bila_ada_loket_aktif(backup, antrian_siap, users):
    titik = backup.backup()
    _tandai_hadir(antrian_siap["loket"][0], users["CRO"], timedelta(seconds=5))

    with pytest.raises(BusinessRuleError, match="loket yang aktif"):
        backup.restore(titik.berkas)


def test_restore_berjalan_bila_tanda_hadir_sudah_basi(backup, antrian_siap, users):
    titik = backup.backup()
    _tandai_hadir(antrian_siap["loket"][0], users["CRO"], timedelta(minutes=10))

    backup.restore(titik.berkas)  # tidak melempar


# ---------------------------------------------------------------------
# Kunci layar setelah menganggur
# ---------------------------------------------------------------------


def _jendela(qtbot, auth, peran: str):
    from app.ui.main_window import MainWindow

    auth.logout()
    auth.login(peran, TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    return jendela


def test_dialog_kunci_dibuka_dengan_kata_sandi_benar(qtbot, auth, users):
    from app.ui.login.kunci_layar import KunciLayarDialog

    auth.login("cro", TEST_PASSWORD)
    dialog = KunciLayarDialog(auth)
    qtbot.addWidget(dialog)
    diterima = []
    dialog.accepted.connect(lambda: diterima.append(True))

    dialog.isian.setText("salah")
    dialog.coba_buka()
    assert dialog.label_galat.text() == "Kata sandi salah."
    assert diterima == []

    dialog.isian.setText(TEST_PASSWORD)
    dialog.coba_buka()
    assert diterima == [True]


def test_esc_tidak_menutup_kunci(qtbot, auth, users):
    from app.ui.login.kunci_layar import KunciLayarDialog

    auth.login("cro", TEST_PASSWORD)
    dialog = KunciLayarDialog(auth)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.reject()

    assert dialog.isVisible()


def test_jendela_terkunci_setelah_menganggur(qtbot, auth, users, monkeypatch):
    from app.ui.login import kunci_layar

    jendela = _jendela(qtbot, auth, "cro")
    assert jendela._pengamat_aktivitas is not None
    dibuka = []
    monkeypatch.setattr(
        kunci_layar.KunciLayarDialog, "exec", lambda self: dibuka.append(True) or 1
    )

    jendela._pengamat_aktivitas.terakhir -= jendela._batas_menganggur + 1
    jendela._periksa_menganggur()

    assert dibuka == [True]
    # Aktivitas dihitung ulang sesudah terbuka: tidak terkunci lagi seketika.
    jendela._periksa_menganggur()
    assert dibuka == [True]


def test_pilih_keluar_dari_kunci_mengakhiri_sesi(qtbot, auth, users, monkeypatch):
    from app.ui.login import kunci_layar

    jendela = _jendela(qtbot, auth, "cro")

    def exec_keluar(self):
        self.keluar = True
        return 0

    monkeypatch.setattr(kunci_layar.KunciLayarDialog, "exec", exec_keluar)

    jendela.kunci_layar()

    assert not auth.is_authenticated


def test_kunci_dimatikan_dengan_nol_menit(qtbot, auth, users):
    from app.services.settings_service import SettingsService

    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("sesi.idle_menit", "0")

    jendela = _jendela(qtbot, auth, "cro")

    assert jendela._pengamat_aktivitas is None


# ---------------------------------------------------------------------
# Notifikasi penundaan
# ---------------------------------------------------------------------


def test_percobaan_kelima_memberi_tahu_akun_ditunda(auth, users):
    for _ in range(BATAS_LOGIN_GAGAL - 1):
        with pytest.raises(AuthenticationError):
            auth.login("cro", "salah-sekali")

    with pytest.raises(AuthenticationError, match="ditunda"):
        auth.login("cro", "salah-sekali")


def test_pesan_penundaan_menyebut_sisa_waktu(auth, users):
    _gagal_login(auth, "cro", BATAS_LOGIN_GAGAL)

    with pytest.raises(AuthenticationError, match=r"menit|detik"):
        auth.login("cro", TEST_PASSWORD)


def test_penundaan_dicatat_sekali_di_audit(auth, users):
    _gagal_login(auth, "cro", BATAS_LOGIN_GAGAL)
    for _ in range(3):
        with pytest.raises(AuthenticationError):
            auth.login("cro", "lagi")

    with session_scope() as s:
        jumlah = s.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.LOGIN_LOCKED.value)
        )
    assert jumlah == 1
