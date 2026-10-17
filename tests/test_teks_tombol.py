"""
Teks tombol aplikasi Windows tidak boleh terpotong.

Menelusuri setiap menu, tab, dan rail per peran pada beberapa ukuran jendela
serta skala tampilan, lalu membandingkan lebar tombol dengan `sizeHint()`.
Pengukurnya ada di `tests/ukuran_tombol.py` agar bisa dipakai tes lain.

Tentang skala Windows: Qt membagi ukuran fisik dengan skala, jadi layar 1366
px pada 125% / 150% hanya memberi jendela ±1093 / ±911 px logis dengan huruf
yang sama. Skala itu diwakili ukuran jendela logis. "Teks lebih besar"
diwakili `skala_huruf`, yang mengalikan font-size px pada stylesheet.
"""

from __future__ import annotations

import re

import pytest
from PySide6.QtWidgets import QApplication

from tests.conftest import TEST_PASSWORD
from tests.ukuran_tombol import (
    jelajahi,
    periksa_semua_label,
    tombol_bertulisan,
    tombol_terpotong,
)

UKURAN_DASAR = [(800, 600), (1280, 720), (1366, 768)]
# Windows 125% dan 150% pada layar 1366 x 768 (ukuran logis, dibulatkan).
UKURAN_SKALA_WINDOWS = [(1093, 614), (911, 512)]
PERAN = ["admin", "supervisor", "cro", "registration"]


@pytest.fixture
def gaya_aplikasi(request):
    """Stylesheet aplikasi sungguhan, dikembalikan setelah tes."""
    from app.ui.style import STYLESHEET

    aplikasi = QApplication.instance()
    sebelumnya = aplikasi.styleSheet()
    aplikasi.setStyleSheet(STYLESHEET)
    request.addfinalizer(lambda: aplikasi.setStyleSheet(sebelumnya))
    return aplikasi


def skala_huruf(faktor: float) -> None:
    """Perbesar semua font-size px pada stylesheet aplikasi."""
    aplikasi = QApplication.instance()
    aplikasi.setStyleSheet(
        re.sub(
            r"(font-size:\s*)(\d+(?:\.\d+)?)px",
            lambda m: f"{m.group(1)}{round(float(m.group(2)) * faktor)}px",
            aplikasi.styleSheet(),
        )
    )


def _masuk(auth, peran: str) -> None:
    auth.logout()
    auth.login(peran, TEST_PASSWORD)


def _jendela(qtbot, auth, peran, ukuran, monkeypatch):
    from app.ui import main_window
    from app.ui.main_window import MainWindow

    # Menu Layanan Anjungan hanya ada di komputer server; ikut diperiksa.
    monkeypatch.setattr(main_window, "_komputer_server", lambda: True)
    _masuk(auth, peran)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)
    jendela.resize(*ukuran)
    jendela.show()
    qtbot.waitExposed(jendela)
    return jendela


def _periksa_jendela(qtbot, jendela, dilihat: set[str]) -> list[str]:
    masalah: list[str] = []

    def periksa(akar):
        dilihat.update(t.text() for t in tombol_bertulisan(jendela))
        masalah.extend(tombol_terpotong(jendela))
        masalah.extend(periksa_semua_label(jendela))

    # Kepala jendela (pil menu, Ganti Kata Sandi, Keluar) ikut terukur di
    # setiap menu karena yang diukur seluruh jendela.
    for indeks, menu in enumerate(jendela.menu_aktif):
        jendela.navigasi.setCurrentRow(indeks)
        qtbot.wait(60)
        jelajahi(jendela.halaman.currentWidget(), periksa)
    # Hilangkan duplikat tanpa mengubah urutan.
    return list(dict.fromkeys(masalah))


def _kumpulkan(qtbot, auth, peran, ukuran, monkeypatch, faktor=1.0):
    """Daftar tombol terpotong; juga memastikan penelusuran tidak kosong."""
    if faktor != 1.0:
        skala_huruf(faktor)
    jendela = _jendela(qtbot, auth, peran, ukuran, monkeypatch)
    dilihat: set[str] = set()
    masalah = _periksa_jendela(qtbot, jendela, dilihat)
    assert "Keluar" in dilihat, "penelusuran tidak mencapai kepala jendela"
    assert len(dilihat) >= 5, f"penelusuran terlalu dangkal: {len(dilihat)} tombol"
    return masalah


@pytest.mark.parametrize("ukuran", UKURAN_DASAR, ids=lambda u: f"{u[0]}x{u[1]}")
@pytest.mark.parametrize("peran", PERAN)
def test_teks_tombol_tidak_terpotong(
    qtbot, auth, antrian_siap, terbitkan, gaya_aplikasi, monkeypatch, peran, ukuran
):
    terbitkan("A", 3)
    assert _kumpulkan(qtbot, auth, peran, ukuran, monkeypatch) == []


@pytest.mark.parametrize(
    "ukuran", UKURAN_SKALA_WINDOWS, ids=lambda u: f"windows-{u[0]}x{u[1]}"
)
@pytest.mark.parametrize("peran", PERAN)
def test_teks_tombol_pada_skala_windows_125_dan_150(
    qtbot, auth, antrian_siap, terbitkan, gaya_aplikasi, monkeypatch, peran, ukuran
):
    terbitkan("A", 3)
    assert _kumpulkan(qtbot, auth, peran, ukuran, monkeypatch) == []


@pytest.mark.parametrize("faktor", [1.25, 1.5], ids=["huruf125", "huruf150"])
@pytest.mark.parametrize("peran", ["admin", "cro"])
def test_teks_tombol_dengan_huruf_diperbesar(
    qtbot, auth, antrian_siap, terbitkan, gaya_aplikasi, monkeypatch, peran, faktor
):
    terbitkan("A", 3)
    assert _kumpulkan(qtbot, auth, peran, (1366, 768), monkeypatch, faktor) == []


def test_pengukur_mendeteksi_tombol_terpotong(qtbot, gaya_aplikasi):
    """Pengukur sendiri harus gagal pada tombol yang sengaja dipersempit."""
    from PySide6.QtWidgets import QWidget

    from app.ui.common import tombol

    wadah = QWidget()
    qtbot.addWidget(wadah)
    sempit = tombol("Teks yang cukup panjang untuk dipotong")
    sempit.setParent(wadah)
    sempit.setFixedWidth(40)
    wadah.resize(200, 80)
    wadah.show()
    qtbot.waitExposed(wadah)

    assert len(tombol_bertulisan(wadah)) == 1
    assert tombol_terpotong(wadah)


# ---------------------------------------------------------------------
# Keadaan yang tidak muncul pada jendela baru
# ---------------------------------------------------------------------


@pytest.mark.parametrize("ukuran", [(800, 600), (1366, 768)], ids=lambda u: f"{u[0]}x{u[1]}")
def test_tombol_admin_dengan_pita_dan_perangkat_terpasang(
    qtbot, auth, antrian_siap, gaya_aplikasi, monkeypatch, tmp_path, ukuran
):
    """Pita pembaruan/anjungan/database dan baris perangkat ikut terukur."""
    from app.services import device_service
    from app.services.device_service import PerangkatService
    from app.services.pembaruan_windows import InfoPembaruan
    from app.services.status_anjungan import MASALAH, StatusAnjungan

    _masuk(auth, "admin")
    kode = PerangkatService(auth).buat_kode()
    device_service.pasangkan(kode.kode, "a1b2c3d4-0000-4000-8000-000000000001", "Anjungan Lobi", "anjungan")

    jendela = _jendela(qtbot, auth, "admin", ukuran, monkeypatch)
    jendela.pita_pembaruan.tampilkan(
        InfoPembaruan(versi="9.9.9", berkas=tmp_path / "x.exe", ukuran_byte=1, sha256="0")
    )
    jendela.pita_anjungan.tampilkan(
        StatusAnjungan(MASALAH, "API mati", "API anjungan tidak berjalan", ("Tekan Pasang ulang.",))
    )
    jendela.pita_database.perbarui(False)
    dilihat: set[str] = set()
    masalah = _periksa_jendela(qtbot, jendela, dilihat)
    jendela.pita_pembaruan.sedang_mengunduh()
    masalah += _periksa_jendela(qtbot, jendela, dilihat)

    assert {"Unduh pembaruan", "Periksa lagi", "Segarkan media"} <= dilihat
    assert list(dict.fromkeys(masalah)) == []


@pytest.mark.parametrize("ukuran", [(800, 600), (1366, 768)], ids=lambda u: f"{u[0]}x{u[1]}")
def test_tombol_pelayanan_saat_melayani_nomor(
    qtbot, auth, users, antrian_siap, terbitkan, gaya_aplikasi, monkeypatch, ukuran
):
    """Tombol aksi nomor aktif muncul hanya setelah nomor dipanggil."""
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import User
    from app.services.queue_service import QueueService

    loket = antrian_siap["loket"][0]
    with session_scope() as s:
        s.execute(sa.update(User).where(User.id == users["CRO"]).values(default_counter_id=loket))
    terbitkan("A", 3)
    _masuk(auth, "cro")
    QueueService(auth).call_next(loket)

    jendela = _jendela(qtbot, auth, "cro", ukuran, monkeypatch)
    qtbot.wait(200)
    dilihat: set[str] = set()
    masalah = _periksa_jendela(qtbot, jendela, dilihat)

    assert any(t.startswith("Mulai Melayani") for t in dilihat)
    assert masalah == []


@pytest.mark.parametrize("ukuran", [(800, 600), (1366, 768)], ids=lambda u: f"{u[0]}x{u[1]}")
def test_tombol_pendaftaran_dalam_dua_keadaan(
    qtbot, auth, antrian_siap, gaya_aplikasi, monkeypatch, ukuran
):
    """Buka/Tutup Pendaftaran dipasang bergantian di halaman Terbitkan Nomor."""
    jendela = _jendela(qtbot, auth, "registration", ukuran, monkeypatch)
    halaman = jendela.halaman.currentWidget().widget()
    for dibuka in (False, True):
        halaman.pendaftaran_dibuka = dibuka
        halaman.tombol_pendaftaran.setText(
            "Tutup Pendaftaran" if dibuka else "Buka Pendaftaran"
        )
        halaman.tombol_pendaftaran.updateGeometry()
        QApplication.processEvents()
        assert tombol_terpotong(jendela) == []


# ---------------------------------------------------------------------
# Dialog (jendela tersendiri; tidak tercapai lewat MainWindow)
# ---------------------------------------------------------------------


def _dialog_login(auth, **_):
    from app.ui.login.login_window import LoginWindow

    return LoginWindow(auth)


def _dialog_kunci(auth, **_):
    from app.ui.login.kunci_layar import KunciLayarDialog

    return KunciLayarDialog(auth)


def _dialog_mode(**_):
    from app.ui.login.mode_dialog import ModeDialog

    return ModeDialog()


def _dialog_pemulihan(**_):
    from app.ui.login.pemulihan_admin_dialog import PemulihanAdminDialog

    return PemulihanAdminDialog()


def _dialog_sandi(auth, **_):
    from app.ui.login.change_password_dialog import ChangePasswordDialog

    return ChangePasswordDialog(auth)


def _dialog_sandi_wajib(auth, **_):
    from app.ui.login.change_password_dialog import ChangePasswordDialog

    return ChangePasswordDialog(auth, wajib=True)


def _dialog_mesin(**_):
    from app.ui.login.setup_mesin_dialog import SetupMesinDialog

    return SetupMesinDialog()


def _dialog_loket(**_):
    from app.ui.settings.dialogs import CounterDialog

    return CounterDialog()


def _dialog_layanan(**_):
    from app.ui.settings.dialogs import CategoryDialog

    return CategoryDialog()


def _dialog_akun(**_):
    from app.ui.settings.dialogs import UserDialog

    return UserDialog()


def _dialog_reset_sandi(**_):
    from app.ui.settings.dialogs import ResetPasswordDialog

    return ResetPasswordDialog(nama_petugas="Petugas Contoh")


def _dialog_jadwal(**_):
    from datetime import date

    from app.services import daftar_putar
    from app.ui.settings.dialogs import JadwalIklanDialog

    return JadwalIklanDialog(
        None, daftar_putar.Butir("a.jpg", date(2026, 11, 1), date(2026, 11, 30), 20), gambar=True
    )


def _dialog_kode_pasang(**_):
    from datetime import datetime

    from app.ui.settings.kartu_perangkat import DialogKodePasang

    return DialogKodePasang("123456", datetime(2030, 1, 1))


DIALOG = {
    "login": _dialog_login,
    "kunci-layar": _dialog_kunci,
    "mode": _dialog_mode,
    "pemulihan-admin": _dialog_pemulihan,
    "ganti-sandi": _dialog_sandi,
    "ganti-sandi-wajib": _dialog_sandi_wajib,
    "setup-mesin": _dialog_mesin,
    "loket": _dialog_loket,
    "jenis-layanan": _dialog_layanan,
    "akun": _dialog_akun,
    "reset-sandi": _dialog_reset_sandi,
    "jadwal-iklan": _dialog_jadwal,
    "kode-pasang": _dialog_kode_pasang,
}


@pytest.mark.parametrize("faktor", [1.0, 1.5], ids=["huruf100", "huruf150"])
@pytest.mark.parametrize("nama", sorted(DIALOG))
def test_tombol_dialog_tidak_terpotong(
    qtbot, auth, antrian_siap, gaya_aplikasi, monkeypatch, tmp_path, nama, faktor
):
    # Dialog setup mesin menulis konfigurasi komputer; arahkan ke folder sementara.
    monkeypatch.setenv("ANTRIAN_PERAN_PATH", str(tmp_path / "peran.json"))
    _masuk(auth, "admin")
    if faktor != 1.0:
        skala_huruf(faktor)
    dialog = DIALOG[nama](auth=auth)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    assert tombol_bertulisan(dialog), "dialog tanpa tombol bertulisan tidak berguna diuji"
    assert tombol_terpotong(dialog) == []
    assert periksa_semua_label(dialog) == []
