"""Catatan rilis ("Apa yang baru?") pada pembaruan Windows."""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from app.services.pembaruan_windows import (
    BATAS_CATATAN,
    NAMA_CATATAN,
    NAMA_INSTALLER,
    NAMA_VERSI,
    InfoPembaruan,
    bersihkan_catatan,
    info_pembaruan,
    periksa_pembaruan,
)
from tests.test_pembaruan_windows import _pasangan_kunci, _server, _tandatangani


def test_catatan_dibersihkan_dari_karakter_kendali_dan_dipotong():
    teks = "  Baru:\r\n- Laporan\x07 Saya  \n\x1b[31mmerah\n"
    assert bersihkan_catatan(teks) == "Baru:\n- Laporan Saya\n[31mmerah"
    panjang = bersihkan_catatan("a" * (BATAS_CATATAN + 50))
    assert len(panjang) == BATAS_CATATAN and panjang.endswith("…")
    assert bersihkan_catatan(None) == ""


def test_server_membagikan_catatan_bila_ada(monkeypatch, tmp_path):
    from app import kiosk_api

    folder = tmp_path / "pembaruan"
    folder.mkdir()
    isi = b"installer-rilis"
    (folder / NAMA_INSTALLER).write_bytes(isi)
    (folder / NAMA_VERSI).write_text("1.0.9", encoding="utf-8")
    assert info_pembaruan(folder).catatan == ""

    (folder / NAMA_CATATAN).write_text("- Laporan Saya untuk CRO\n", encoding="utf-8")
    monkeypatch.setattr(kiosk_api, "base_dir", lambda: tmp_path)
    klien = TestClient(kiosk_api.create_app("token-rilis-panjang", object()))

    data = klien.get("/v1/windows/update").json()
    assert data["release_notes"] == "- Laporan Saya untuk CRO"
    assert data["sha256"] == hashlib.sha256(isi).hexdigest()


def test_klien_membaca_catatan_tanpa_memengaruhi_tanda_tangan(monkeypatch):
    rahasia, publik = _pasangan_kunci()
    sha = "b" * 64
    _server(monkeypatch, {
        "latest_version": "1.0.9", "size": 123, "sha256": sha,
        "signature": _tandatangani(rahasia, "1.0.9", 123, sha),
        "release_notes": "Perbaikan\x00 cetak tiket",
    })

    info = periksa_pembaruan(
        "http://server:8765", versi_terpasang="1.0.8", kunci_publik_b64=publik
    )

    assert info is not None
    assert info.catatan == "Perbaikan cetak tiket"


def test_server_lama_tanpa_catatan_tetap_diterima(monkeypatch):
    sha = "c" * 64
    _server(monkeypatch, {"latest_version": "1.0.9", "size": 1, "sha256": sha})
    info = periksa_pembaruan("http://server:8765", versi_terpasang="1.0.8", kunci_publik_b64="")
    assert info is not None and info.catatan == ""


def test_tombol_apa_yang_baru_hanya_bila_ada_catatan(qtbot, tmp_path):
    from app.ui.pita_pembaruan import PitaPembaruan

    pita = PitaPembaruan(lambda: None)
    qtbot.addWidget(pita)
    tanpa = InfoPembaruan("1.1.0", tmp_path / NAMA_INSTALLER, 10, "a" * 64)
    dengan = InfoPembaruan(
        "1.1.0", tmp_path / NAMA_INSTALLER, 10, "a" * 64, catatan="<b>tebal</b>"
    )

    pita.tampilkan(tanpa)
    assert pita.tombol_catatan.isHidden()
    pita.tampilkan(dengan)
    assert not pita.tombol_catatan.isHidden()
