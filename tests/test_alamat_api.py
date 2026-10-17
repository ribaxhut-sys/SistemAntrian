"""Alamat tempat API anjungan mendengarkan (pilihan admin di Layanan Anjungan)."""

from __future__ import annotations

import socket
import threading
import time
import urllib.request

import pytest

from app.core.errors import AuthorizationError, ValidationError
from app.kiosk_api import _jalankan_uvicorn, pilih_alamat_dengar
from app.services import device_service
from app.services.device_service import PerangkatService
from tests.conftest import TEST_PASSWORD


def test_bawaan_semua_antarmuka():
    assert pilih_alamat_dengar(None, "", ["192.168.1.10"]) == ["0.0.0.0"]


def test_alamat_pilihan_admin_ditambah_loopback():
    assert pilih_alamat_dengar(None, "192.168.1.10", ["192.168.1.10", "10.0.0.5"]) == [
        "192.168.1.10",
        "127.0.0.1",
    ]


def test_alamat_yang_hilang_kembali_ke_semua_antarmuka(caplog):
    assert pilih_alamat_dengar(None, "192.168.1.10", ["192.168.1.77"]) == ["0.0.0.0"]
    assert "tidak ada di komputer ini" in caplog.text


def test_env_pengembang_menang():
    assert pilih_alamat_dengar("127.0.0.1", "192.168.1.10", ["192.168.1.10"]) == [
        "127.0.0.1"
    ]


@pytest.mark.parametrize(
    "alamat, sah",
    [
        ("", True),
        ("192.168.1.10", True),
        ("10.1.2.3", True),
        ("127.0.0.1", False),
        ("0.0.0.0", False),
        ("8.8.8.8", False),
        ("server-kantor", False),
    ],
)
def test_alamat_api_sah(alamat, sah):
    assert device_service.alamat_api_sah(alamat) is sah


def test_admin_menyimpan_alamat_api(admin_auth):
    layanan = PerangkatService(admin_auth)
    assert layanan.alamat_api() == ""

    layanan.setel_alamat_api("192.168.1.10")
    assert device_service.alamat_api_tersimpan() == "192.168.1.10"

    with pytest.raises(ValidationError):
        layanan.setel_alamat_api("8.8.8.8")
    layanan.setel_alamat_api("")
    assert device_service.alamat_api_tersimpan() == ""


def test_petugas_tidak_boleh_mengubah_alamat_api(auth, antrian_siap):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    with pytest.raises(AuthorizationError):
        PerangkatService(auth).setel_alamat_api("192.168.1.10")


def _port_bebas() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_satu_server_mendengar_di_dua_alamat(monkeypatch):
    """Pola soket ganda uvicorn benar-benar menjawab di kedua alamat (Windows)."""
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    server_dibuat: list[uvicorn.Server] = []
    asli = uvicorn.Server.__init__

    def catat(self, config):
        asli(self, config)
        server_dibuat.append(self)

    monkeypatch.setattr(uvicorn.Server, "__init__", catat)
    port = _port_bebas()
    # 127.0.0.2 adalah loopback juga di Windows; mewakili alamat LAN.
    alamat = ["127.0.0.1", "127.0.0.2"]
    benang = threading.Thread(target=_jalankan_uvicorn, args=(app, alamat, port), daemon=True)
    benang.start()
    try:
        for _ in range(100):
            if server_dibuat and server_dibuat[0].started:
                break
            time.sleep(0.05)
        for host in alamat:
            with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=3) as r:
                assert r.read() == b'{"status":"ok"}'
    finally:
        if server_dibuat:
            server_dibuat[0].should_exit = True
        benang.join(timeout=5)


class _PerangkatPalsu:
    def __init__(self):
        self.tersimpan = ""

    def alamat_api(self):
        return self.tersimpan

    def setel_alamat_api(self, alamat):
        self.tersimpan = alamat


def test_layar_layanan_anjungan_memilih_alamat(qtbot, monkeypatch, app_config):
    from app.ui.settings import layanan_anjungan_page as halaman_modul

    monkeypatch.setattr(halaman_modul, "alamat_ipv4_lan", lambda: ["192.168.1.10"])
    monkeypatch.setattr(halaman_modul.LayananAnjunganPage, "muat_ulang", lambda self: None)
    # Kartu Perangkat butuh PerangkatService sungguhan; di sini cukup wadah kosong.
    monkeypatch.setattr(
        "app.ui.settings.kartu_perangkat.KartuPerangkat",
        lambda *a, **k: halaman_modul.QWidget(),
    )
    palsu = _PerangkatPalsu()
    halaman = halaman_modul.LayananAnjunganPage(palsu)
    qtbot.addWidget(halaman)

    kotak = halaman.alamat_api
    assert [kotak.itemData(i) for i in range(kotak.count())] == ["", "192.168.1.10"]
    kotak.setCurrentIndex(1)

    assert palsu.tersimpan == "192.168.1.10"
    assert "Pasang ulang" in halaman.catatan.text()
