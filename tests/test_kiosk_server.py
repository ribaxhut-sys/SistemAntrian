"""Test helper pengaturan token dan Firewall API anjungan."""

from __future__ import annotations

import base64
import re
import subprocess

import pytest

from app.services import kiosk_server


def test_token_baru_acak_dan_cukup_panjang():
    pertama = kiosk_server.token_baru()
    kedua = kiosk_server.token_baru()

    assert len(pertama) >= 64
    assert pertama != kedua


def test_api_otomatis_tidak_dimulai_bila_pengaturan_mati(monkeypatch, tmp_path):
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: False)
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("API seharusnya tidak dijalankan"),
    )

    assert not kiosk_server.mulai_api_otomatis(
        tmp_path, tmp_path / "logs", token="token-cukup-panjang"
    )


def test_api_otomatis_memakai_token_tersimpan_dan_proses_detached(
    monkeypatch, tmp_path
):
    panggilan = {}
    monkeypatch.delenv("ANTRIAN_KIOS_API_TOKEN", raising=False)
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: True)
    monkeypatch.setattr(kiosk_server, "api_sudah_berjalan", lambda port: False)
    monkeypatch.setattr(kiosk_server, "_firewall_sudah_siap", lambda: True)
    monkeypatch.setattr(kiosk_server, "muat_token_pengguna", lambda: "token-stored")

    def mulai(args, **kwargs):
        panggilan.update(args=args, kwargs=kwargs)

    monkeypatch.setattr(kiosk_server.subprocess, "Popen", mulai)

    assert kiosk_server.mulai_api_otomatis(tmp_path, tmp_path / "logs")
    assert panggilan["args"][-1] == "--kios-api"
    assert panggilan["kwargs"]["env"]["ANTRIAN_KIOS_API_TOKEN"] == "token-stored"
    assert panggilan["kwargs"]["stdin"] == kiosk_server.subprocess.DEVNULL
    assert panggilan["kwargs"]["stdout"].name.endswith("kiosk-api.log")


def test_api_otomatis_menghindari_proses_ganda(monkeypatch, tmp_path):
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: True)
    monkeypatch.setattr(kiosk_server, "api_sudah_berjalan", lambda port: True)
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("API sudah berjalan"),
    )

    assert kiosk_server.mulai_api_otomatis(
        tmp_path, tmp_path / "logs", token="token-cukup-panjang"
    )


def test_siapkan_firewall_meminta_elevasi_dan_membatasi_ke_private(monkeypatch):
    panggilan = []

    def jalankan(args, **kwargs):
        panggilan.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(kiosk_server.subprocess, "run", jalankan)

    kiosk_server.siapkan_firewall()

    args, kwargs = panggilan[-1]
    perintah = args[-1]
    cocok = re.search(r"-EncodedCommand', '([^']+)'", perintah)
    assert cocok is not None
    script = base64.b64decode(cocok.group(1)).decode("utf-16le")
    assert "-Verb RunAs" in perintah
    assert "8765" in script
    assert "8766" in script
    assert "-Profile Private" in script
    assert kwargs["timeout"] == 120
    assert len(panggilan) == 2


def test_firewall_yang_sudah_sesuai_tidak_meminta_elevasi(monkeypatch):
    panggilan = []

    def jalankan(args, **kwargs):
        panggilan.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="OK\n")

    monkeypatch.setattr(kiosk_server.subprocess, "run", jalankan)

    kiosk_server.siapkan_firewall()

    assert len(panggilan) == 1
    assert "-Verb RunAs" not in panggilan[0]


def test_kegagalan_siapkan_firewall_dilaporkan_ke_pemanggil(monkeypatch):
    panggilan = []

    def gagal(args, **kwargs):
        panggilan.append(args)
        if len(panggilan) == 1:
            return subprocess.CompletedProcess(args, 0, stdout="")
        return subprocess.CompletedProcess(args, 1, stderr="Izin dibatalkan")

    monkeypatch.setattr(kiosk_server.subprocess, "run", gagal)

    with pytest.raises(RuntimeError, match="Izin dibatalkan"):
        kiosk_server.siapkan_firewall()
