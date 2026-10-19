"""Penjaga: halaman Pelayanan yang tampil tidak boleh mati saat memanggil nomor."""

from __future__ import annotations

import pytest

from tests.conftest import TEST_PASSWORD
from tests.test_notes_ui import bisu, halaman_kerja  # noqa: F401


@pytest.mark.parametrize("ukuran", [(1366, 768), (800, 600), (1920, 1080), (1093, 614)])
def test_halaman_tampil_lalu_panggil_berikutnya_tidak_mematikan_proses(
    qtbot, halaman_kerja, bisu, monkeypatch, terbitkan, auth, ukuran  # noqa: F811
):
    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman_kerja.muat_ulang()
    dicatat: list[str] = []
    monkeypatch.setattr(
        "app.ui.queue.service_page.tampilkan_error",
        lambda parent, exc, judul="Gagal": dicatat.append(repr(exc)),
    )
    halaman_kerja.resize(*ukuran)
    halaman_kerja.show()
    qtbot.waitExposed(halaman_kerja)
    halaman_kerja.panggil_berikutnya()
    qtbot.wait(300)
    assert not dicatat, dicatat
    assert halaman_kerja.label_nomor.text() == "A-001"
    assert halaman_kerja.isVisible()
