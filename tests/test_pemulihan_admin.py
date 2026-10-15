"""
Pemulihan akun admin lewat kunci pengembang, alat pengembangnya, dan
dialog di layar masuk.

Dikunci: respons hanya sah untuk satu tantangan, satu pemasangan, dan satu
kali pakai; tanda tangan palsu atau kedaluwarsa ditolak; percobaan salah
dibatasi; dan alat pengembang menghasilkan respons yang diterima aplikasi.
"""

from __future__ import annotations

import base64
from datetime import timedelta

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import clock
from app.core.database import session_scope
from app.core.errors import AuthenticationError, ValidationError
from app.models import AuditLog, User
from app.services import pemulihan_admin as pa
from tests.conftest import TEST_PASSWORD

SANDI_BARU = "sandi-baru-123"


@pytest.fixture
def pengembang():
    """Pasangan kunci uji: (kunci rahasia, kunci publik base64)."""
    kunci = Ed25519PrivateKey.generate()
    publik = kunci.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return kunci, base64.b64encode(publik).decode()


def _tanda(kunci, kode_tantangan: str) -> str:
    """Tanda tangan seperti alat pengembang (D:\\sistemantrian kunci)."""
    t = pa.baca_tantangan(kode_tantangan)
    return pa.kode_respons(kunci.sign(pa.data_ditandatangani(t.mentah)))


# ---------------------------------------------------------------------
# Alur normal
# ---------------------------------------------------------------------


def test_pemulihan_berhasil_mengganti_kata_sandi_dan_mewajibkan_ganti(
    auth, users, pengembang
):
    kunci, publik = pengembang
    tantangan = pa.buat_tantangan("admin")

    username = pa.pulihkan(
        tantangan, _tanda(kunci, tantangan), SANDI_BARU, kunci_publik_b64=publik
    )

    assert username == "admin"
    sesi = auth.login("admin", SANDI_BARU)
    assert sesi.must_change_password is True


def test_pemulihan_dicatat_di_audit(auth, users, pengembang):
    kunci, publik = pengembang
    tantangan = pa.buat_tantangan("admin")
    pa.pulihkan(tantangan, _tanda(kunci, tantangan), SANDI_BARU, kunci_publik_b64=publik)

    with session_scope() as s:
        aksi = s.scalars(
            sa.select(AuditLog.action).where(AuditLog.action == pa.AKSI_RESET)
        ).all()
    assert aksi == [pa.AKSI_RESET]


def test_kode_tidak_memuat_kata_sandi_maupun_hash(auth, users):
    tantangan = pa.buat_tantangan("admin")
    t = pa.baca_tantangan(tantangan)

    assert t.username == "admin"
    assert t.kedaluwarsa > clock.now()
    assert tantangan.startswith("ANTR-")


# ---------------------------------------------------------------------
# Penolakan
# ---------------------------------------------------------------------


def test_respons_tidak_dapat_dipakai_dua_kali(auth, users, pengembang):
    kunci, publik = pengembang
    tantangan = pa.buat_tantangan("admin")
    respons = _tanda(kunci, tantangan)
    pa.pulihkan(tantangan, respons, SANDI_BARU, kunci_publik_b64=publik)

    with pytest.raises(ValidationError, match="sudah pernah dipakai"):
        pa.pulihkan(tantangan, respons, "sandi-lain-456", kunci_publik_b64=publik)


def test_respons_untuk_tantangan_lain_ditolak(auth, users, pengembang):
    kunci, publik = pengembang
    satu = pa.buat_tantangan("admin")
    dua = pa.buat_tantangan("admin")

    with pytest.raises(AuthenticationError, match="tidak cocok"):
        pa.pulihkan(dua, _tanda(kunci, satu), SANDI_BARU, kunci_publik_b64=publik)


def test_tanda_tangan_kunci_lain_ditolak(auth, users, pengembang):
    _, publik = pengembang
    penyerang = Ed25519PrivateKey.generate()
    tantangan = pa.buat_tantangan("admin")

    with pytest.raises(AuthenticationError, match="tidak cocok"):
        pa.pulihkan(
            tantangan, _tanda(penyerang, tantangan), SANDI_BARU, kunci_publik_b64=publik
        )
    # Kata sandi lama tetap berlaku.
    assert auth.login("admin", TEST_PASSWORD).username == "admin"


def test_tantangan_kedaluwarsa_ditolak(auth, users, pengembang, monkeypatch):
    kunci, publik = pengembang
    tantangan = pa.buat_tantangan("admin")
    respons = _tanda(kunci, tantangan)
    sekarang = clock.now()
    monkeypatch.setattr(clock, "now", lambda: sekarang + timedelta(hours=25))

    with pytest.raises(ValidationError, match="kedaluwarsa"):
        pa.pulihkan(tantangan, respons, SANDI_BARU, kunci_publik_b64=publik)


def test_tantangan_pemasangan_lain_ditolak(auth, users, pengembang):
    kunci, publik = pengembang
    asing = pa._kodekan(
        pa.AWALAN_TANTANGAN,
        pa.kemas_tantangan(
            "ab" * 16, "admin", b"\x01" * 8, clock.now() + timedelta(hours=1)
        ),
    )

    with pytest.raises(ValidationError, match="pemasangan yang lain"):
        pa.pulihkan(asing, _tanda(kunci, asing), SANDI_BARU, kunci_publik_b64=publik)


def test_hanya_akun_admin_dapat_dipulihkan(auth, users):
    with pytest.raises(ValidationError, match="Akun admin"):
        pa.buat_tantangan("cro")


def test_tanpa_kunci_terpasang_dinyatakan_terus_terang(auth, users):
    assert pa.kunci_terpasang("") is False
    tantangan = pa.buat_tantangan("admin")

    with pytest.raises(ValidationError, match="belum diaktifkan"):
        pa.pulihkan(tantangan, "RESP-AAAA", SANDI_BARU, kunci_publik_b64="")


def test_percobaan_salah_dibatasi(auth, users, pengembang):
    _, publik = pengembang
    tantangan = pa.buat_tantangan("admin")
    for _ in range(pa.BATAS_GAGAL):
        with pytest.raises(ValidationError):
            pa.pulihkan(tantangan, "RESP-AAAA", SANDI_BARU, kunci_publik_b64=publik)

    with pytest.raises(AuthenticationError, match="Terlalu banyak"):
        pa.pulihkan(tantangan, "RESP-AAAA", SANDI_BARU, kunci_publik_b64=publik)


def test_kata_sandi_baru_lemah_ditolak_dan_nonce_tidak_terpakai(auth, users, pengembang):
    kunci, publik = pengembang
    tantangan = pa.buat_tantangan("admin")
    respons = _tanda(kunci, tantangan)

    with pytest.raises(ValidationError):
        pa.pulihkan(tantangan, respons, "pendek", kunci_publik_b64=publik)

    # Respons yang sama masih dapat dipakai dengan kata sandi yang sah.
    assert pa.pulihkan(tantangan, respons, SANDI_BARU, kunci_publik_b64=publik) == "admin"


def test_pemulihan_menghapus_penundaan_login(auth, users, pengembang):
    kunci, publik = pengembang
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            auth.login("admin", "salah-sekali")
    with pytest.raises(AuthenticationError, match="Terlalu banyak"):
        auth.login("admin", TEST_PASSWORD)

    tantangan = pa.buat_tantangan("admin")
    pa.pulihkan(tantangan, _tanda(kunci, tantangan), SANDI_BARU, kunci_publik_b64=publik)

    assert auth.login("admin", SANDI_BARU).username == "admin"


# ---------------------------------------------------------------------
# Dialog di layar masuk
# ---------------------------------------------------------------------


def test_dialog_dinonaktifkan_bila_kunci_belum_terpasang(qtbot, auth, users):
    from app.ui.login.pemulihan_admin_dialog import PemulihanAdminDialog

    dialog = PemulihanAdminDialog(kunci_publik_b64="")
    qtbot.addWidget(dialog)

    assert dialog.label_nonaktif.isVisibleTo(dialog)
    assert not dialog.tombol_pulihkan.isEnabled()
    assert not dialog.tombol_buat.isEnabled()


def test_dialog_memulihkan_admin(qtbot, auth, users, pengembang):
    from app.ui.login.pemulihan_admin_dialog import PemulihanAdminDialog

    kunci, publik = pengembang
    dialog = PemulihanAdminDialog(kunci_publik_b64=publik)
    qtbot.addWidget(dialog)

    dialog.buat_tantangan()
    kode = dialog.kotak_tantangan.toPlainText()
    assert kode.startswith("ANTR-")
    dialog.kotak_respons.setPlainText(_tanda(kunci, kode))
    dialog.input_sandi.setText(SANDI_BARU)
    dialog.input_ulang.setText(SANDI_BARU)
    dialog.pulihkan()

    assert dialog.username_dipulihkan == "admin"
    with session_scope() as s:
        user = s.scalar(sa.select(User).where(User.username == "admin"))
        assert user.must_change_password is True


def test_dialog_menolak_kata_sandi_tidak_sama(qtbot, auth, users, pengembang):
    from app.ui.login.pemulihan_admin_dialog import PemulihanAdminDialog

    _, publik = pengembang
    dialog = PemulihanAdminDialog(kunci_publik_b64=publik)
    qtbot.addWidget(dialog)
    dialog.buat_tantangan()
    dialog.input_sandi.setText(SANDI_BARU)
    dialog.input_ulang.setText("beda-sandi-1")

    dialog.pulihkan()

    assert "tidak sama" in dialog.pesan.text()
    assert dialog.username_dipulihkan is None


def test_kunci_publik_tanpa_padding_tetap_dibaca(auth, users, pengembang):
    kunci, publik = pengembang
    tanpa_padding = publik.rstrip("=")
    tantangan = pa.buat_tantangan("admin")

    assert (
        pa.pulihkan(
            tantangan, _tanda(kunci, tantangan), SANDI_BARU, kunci_publik_b64=tanpa_padding
        )
        == "admin"
    )
