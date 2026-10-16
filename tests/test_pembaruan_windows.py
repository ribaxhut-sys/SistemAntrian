import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.services.pembaruan_windows import (
    InfoPembaruan,
    NAMA_INSTALLER,
    NAMA_VERSI,
    PembaruanError,
    info_pembaruan,
    lebih_baru,
    periksa_pembaruan,
    unduh_pembaruan,
)


class _Jawaban(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_perbandingan_versi_angka():
    assert lebih_baru("1.0.9", "1.0.8")
    assert lebih_baru("1.1", "1.0.99")
    assert not lebih_baru("1.0.8.0", "1.0.8")
    assert not lebih_baru("1.0.7", "1.0.8")


def test_info_pembaruan_membaca_installer_dan_checksum(tmp_path):
    isi = b"installer-yang-ditandatangani"
    (tmp_path / NAMA_INSTALLER).write_bytes(isi)
    (tmp_path / NAMA_VERSI).write_text("1.2.3\n", encoding="utf-8")

    info = info_pembaruan(tmp_path)

    assert info is not None
    assert info.versi == "1.2.3"
    assert info.ukuran_byte == len(isi)
    assert info.sha256 == hashlib.sha256(isi).hexdigest()


def test_periksa_pembaruan_hanya_menerima_versi_lebih_baru(monkeypatch):
    sha = "a" * 64

    def buka(*_, **__):
        return _Jawaban(
            json.dumps(
                {"latest_version": "1.0.9", "size": 123, "sha256": sha}
            ).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", buka)
    info = periksa_pembaruan("http://server:8765", versi_terpasang="1.0.8")
    assert info is not None and info.versi == "1.0.9"
    assert periksa_pembaruan(
        "http://server:8765", versi_terpasang="1.0.9"
    ) is None


def test_unduhan_ditolak_bila_checksum_berbeda(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_, **__: _Jawaban(b"isi-berubah")
    )
    info = InfoPembaruan("1.0.9", tmp_path / NAMA_INSTALLER, 11, "0" * 64)

    with pytest.raises(PembaruanError, match="keamanan"):
        unduh_pembaruan(info, "http://server:8765")


def test_api_membagikan_installer_windows(monkeypatch, tmp_path):
    from app import kiosk_api

    folder = tmp_path / "pembaruan"
    folder.mkdir()
    isi = b"installer-rilis"
    (folder / NAMA_INSTALLER).write_bytes(isi)
    (folder / NAMA_VERSI).write_text("1.0.9", encoding="utf-8")
    monkeypatch.setattr(kiosk_api, "base_dir", lambda: tmp_path)

    client = TestClient(kiosk_api.create_app("token-rilis-panjang", object()))
    metadata = client.get("/v1/windows/update")
    unduhan = client.get("/v1/windows/update/download")

    assert metadata.status_code == 200
    assert metadata.json() == {
        "latest_version": "1.0.9",
        "size": len(isi),
        "sha256": hashlib.sha256(isi).hexdigest(),
    }
    assert unduhan.status_code == 200
    assert unduhan.content == isi


def test_pita_menampilkan_versi_dan_keadaan_unduh(qtbot, tmp_path):
    from app.ui.pita_pembaruan import PitaPembaruan

    pita = PitaPembaruan(lambda: None)
    qtbot.addWidget(pita)
    info = InfoPembaruan("1.1.0", tmp_path / NAMA_INSTALLER, 123, "a" * 64)

    pita.tampilkan(info)

    assert not pita.isHidden()
    assert "1.1.0" in pita.pesan.text()
    assert pita.tombol.isEnabled()
    pita.sedang_mengunduh()
    assert not pita.tombol.isEnabled()
