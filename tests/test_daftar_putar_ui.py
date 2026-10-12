"""
Daftar putar iklan di halaman Pengaturan.

Yang dikunci: iklan yang dicentang tidak boleh diam-diam tidak tayang
karena panel masih "Teks sambutan", jadwal dan lama tampil ikut tersimpan,
dan admin melihat angka tayang serta tanda gagal dari tablet.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from PySide6.QtCore import Qt

from app.services import daftar_putar
from app.services.media_tayang import GagalDiTablet, RingkasanBerkas
from app.services.settings_service import SettingsService


@pytest.fixture
def folder(tmp_path, monkeypatch):
    from app.ui.kiosk import sambutan as modul

    folder = tmp_path / "kiosk"
    folder.mkdir()
    for nama in ("a.jpg", "b.mp4", "lama.avi"):
        (folder / nama).write_bytes(b"isi")
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)
    return folder


@pytest.fixture
def halaman(qtbot, admin_auth, seeded, folder):
    from app.ui.settings.settings_page import SettingsPage

    halaman = SettingsPage(SettingsService(admin_auth))
    qtbot.addWidget(halaman)
    return halaman


def _daftar(halaman):
    return halaman.baris[daftar_putar.KUNCI].kontrol


def _item(daftar, nama):
    for baris in range(daftar.daftar.count()):
        item = daftar.daftar.item(baris)
        if item.data(Qt.ItemDataRole.UserRole) == nama:
            return baris, item
    raise AssertionError(nama)


def test_mencentang_iklan_memindah_panel_ke_folder_media(halaman):
    jenis = halaman.baris["kiosk.welcome_kind"]
    assert jenis.nilai() == "teks"
    daftar = _daftar(halaman)

    _, item = _item(daftar, "b.mp4")
    item.setCheckState(Qt.CheckState.Unchecked)

    assert jenis.nilai() == "media"
    assert "kiosk.welcome_kind" in halaman.berubah(), "harus disimpan seperti perubahan lain"
    assert "Folder media" in halaman.pesan.text()


def test_peringatan_bila_panel_dikembalikan_ke_teks(halaman):
    jenis = halaman.baris["kiosk.welcome_kind"]
    daftar = _daftar(halaman)
    _, item = _item(daftar, "b.mp4")
    item.setCheckState(Qt.CheckState.Unchecked)
    assert daftar.peringatan.isHidden()

    jenis.tulis("teks")

    assert not daftar.peringatan.isHidden()
    assert "Belum tayang" in daftar.peringatan.text()


def test_peringatan_untuk_pengaturan_lama_yang_tersimpan(qtbot, admin_auth, seeded, folder):
    from app.ui.settings.settings_page import SettingsPage

    SettingsService(admin_auth).set(daftar_putar.KUNCI, '["a.jpg"]')
    halaman = SettingsPage(SettingsService(admin_auth))
    qtbot.addWidget(halaman)

    assert "Belum tayang" in _daftar(halaman).peringatan.text()
    assert not halaman.berubah(), "membuka halaman saja tidak mengubah apa pun"


def test_jadwal_dan_lama_tampil_ikut_tersimpan(halaman, admin_auth):
    daftar = _daftar(halaman)
    baris, _ = _item(daftar, "a.jpg")
    daftar.daftar.setCurrentRow(baris)

    daftar.terapkan_jadwal(
        daftar_putar.Butir("a.jpg", date(2026, 11, 1), date(2026, 11, 30), 20)
    )
    halaman.simpan()

    tersimpan = json.loads(SettingsService(admin_auth).get(daftar_putar.KUNCI))
    assert {"nama": "a.jpg", "mulai": "2026-11-01", "selesai": "2026-11-30", "detik": 20} in tersimpan
    _, item = _item(_daftar(halaman), "a.jpg")
    assert "1 Nov 2026 – 30 Nov 2026" in item.text()
    assert "20 dtk" in item.text()


def test_dialog_jadwal_menolak_tanggal_terbalik(qtbot):
    from PySide6.QtCore import QDate

    from app.ui.settings.dialogs import JadwalIklanDialog

    dialog = JadwalIklanDialog(None, daftar_putar.Butir("a.jpg"), gambar=True)
    qtbot.addWidget(dialog)
    dialog.pakai_mulai.setChecked(True)
    dialog.pakai_selesai.setChecked(True)
    dialog.tanggal_mulai.setDate(QDate(2026, 11, 30))
    dialog.tanggal_selesai.setDate(QDate(2026, 11, 1))

    dialog.simpan()

    assert dialog.result() != dialog.DialogCode.Accepted
    assert "lebih awal" in dialog.pesan_kesalahan.text()


def test_dialog_jadwal_kosong_berarti_tanpa_aturan(qtbot):
    from app.ui.settings.dialogs import JadwalIklanDialog

    dialog = JadwalIklanDialog(None, daftar_putar.Butir("b.mp4"), gambar=False)
    qtbot.addWidget(dialog)

    assert dialog.butir == daftar_putar.Butir("b.mp4")


def test_video_berformat_berisiko_ditandai(halaman):
    _, item = _item(_daftar(halaman), "lama.avi")

    assert "MP4" in item.text()
    _, aman = _item(_daftar(halaman), "b.mp4")
    assert "MP4" not in aman.text()


def test_angka_tayang_dan_tablet_yang_gagal_tampil(halaman):
    daftar = _daftar(halaman)

    daftar.tampilkan_ringkasan(
        {
            "a.jpg": RingkasanBerkas(tayang_hari_ini=12, tayang_rentang=3400),
            "b.mp4": RingkasanBerkas(
                gagal=[GagalDiTablet("Tablet Lobi", "video what=1", datetime(2026, 11, 2, 9))]
            ),
        }
    )

    _, a = _item(daftar, "a.jpg")
    assert "hari ini 12×" in a.text()
    assert "30 hari 3.400×" in a.text()
    _, b = _item(daftar, "b.mp4")
    assert "Gagal diputar di Tablet Lobi" in b.text()
    assert "video what=1" in b.toolTip()


def test_tombol_daftar_putar_muat_di_kolom_kontrol(qtbot, halaman, request):
    """Empat tombol sebaris memotong "Atur jadwal…" dan "Muat ulang"."""
    from PySide6.QtWidgets import QApplication, QPushButton

    from app.ui.style import STYLESHEET

    # Stylesheet berlaku untuk seluruh QApplication yang dipakai bersama
    # semua test. Tanpa dikembalikan, test sesudahnya (test_display,
    # test_ui) ikut memakai huruf aplikasi dan gagal karena meluap.
    aplikasi = QApplication.instance()
    sebelumnya = aplikasi.styleSheet()
    aplikasi.setStyleSheet(STYLESHEET)
    request.addfinalizer(lambda: aplikasi.setStyleSheet(sebelumnya))
    halaman.resize(1366, 768)
    halaman.show()
    qtbot.waitExposed(halaman)
    (butir,) = halaman.rail.findItems("Iklan Anjungan", Qt.MatchFlag.MatchExactly)
    halaman.rail.setCurrentItem(butir)
    daftar = _daftar(halaman)
    QApplication.processEvents()
    assert daftar.isVisible()

    for tombol in daftar.findChildren(QPushButton):
        assert tombol.width() >= tombol.sizeHint().width(), tombol.text()
