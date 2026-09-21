"""
Tangkap layar halaman Pengaturan. Perkakas, bukan test sungguhan.

Tidak meng-assert apa pun — yang dihasilkannya adalah lima berkas PNG
untuk dilihat manusia. Karena itu ia DILEWATI kecuali diminta secara
eksplisit, lewat folder tujuannya sendiri:

    $env:PRATINJAU_DIR = "C:\\tmp\\pratinjau"
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_zz_pratinjau.py -q

Tanpa penjagaan itu ia ikut berjalan pada seluruh 1300 tes harian dan
menulis lima berkas yang tidak diperiksa siapa pun, setiap kali.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_DIMINTA = os.environ.get("PRATINJAU_DIR", "").strip()
KELUARAN = Path(_DIMINTA or ".")


@pytest.mark.skipif(
    not _DIMINTA,
    reason="Perkakas tangkapan layar; setel PRATINJAU_DIR untuk menjalankannya.",
)
def test_pratinjau_pengaturan(qtbot, admin_auth, seeded, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService
    from app.ui.kiosk import sambutan as modul
    from app.ui.settings.settings_page import SettingsPage
    from app.ui.style import STYLESHEET

    folder = tmp_path / "kiosk"
    folder.mkdir()
    monkeypatch.setattr(modul, "folder_media_kios", lambda: folder)

    QApplication.instance().setStyleSheet(STYLESHEET)

    halaman = SettingsPage(
        SettingsService(admin_auth), MasterDataService(admin_auth)
    )
    qtbot.addWidget(halaman)
    halaman.resize(1280, 860)
    halaman.show()
    qtbot.waitExposed(halaman)
    KELUARAN.mkdir(parents=True, exist_ok=True)

    def potret(nama: str) -> None:
        QApplication.processEvents()
        halaman.grab().save(str(KELUARAN / f"{nama}.png"))

    potret("pengaturan-tiket")

    # Kelompok terpanjang, lengkap dengan angka bersatuan.
    halaman.rail.setCurrentRow(1)
    potret("pengaturan-layar")

    # Keadaan "ada yang belum disimpan".
    halaman.baris["display.list_rows"].kontrol.setValue(7)
    halaman.baris["display.title"].kontrol.setText("ANTRIAN PELAYANAN PAJAK")
    potret("pengaturan-berubah")

    halaman.muat_ulang()

    # Pencarian lintas kelompok.
    halaman.cari.setText("backup")
    potret("pengaturan-cari")

    halaman.cari.setText("")
    halaman.rail.setCurrentRow(halaman.rail.count() - 1)
    potret("pengaturan-media")
