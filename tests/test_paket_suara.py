"""Paket suara layar antrian: urutan klip dan pembuatannya."""

from __future__ import annotations

import json
import subprocess

from app.services import paket_suara


def test_token_mengikuti_kalimat_pengumuman():
    assert paket_suara.token_pengumuman("PB-014", "Loket 1") == [
        "nomor_antrian", "huruf_p", "huruf_b", "_jeda",
        "angka_0", "angka_1", "angka_4",
        "_jeda", "silakan_menuju", "kata_loket", "angka_1",
    ]


def test_nama_loket_bebas_dieja_per_kata_dan_digit():
    token = paket_suara.token_pengumuman("RS-102", "Loket Prioritas 02")
    assert token[-4:] == ["kata_loket", "kata_prioritas", "angka_0", "angka_2"]


def test_kosakata_memuat_huruf_angka_frasa_dan_kata_loket():
    kata = paket_suara.kosakata(["Loket 1", "Loket Prioritas"])
    assert kata["huruf_p"] == "pe"
    assert kata["angka_7"] == "tujuh"
    assert kata["nomor_antrian"] == "Nomor antrian"
    assert kata["kata_prioritas"] == "prioritas"
    # Setiap token yang mungkin muncul punya klip.
    for token in paket_suara.token_pengumuman("ZX-999", "Loket Prioritas 3"):
        assert token == paket_suara.JEDA or token in kata


def test_buat_paket_menulis_indeks_sesudah_klip(tmp_path, monkeypatch):
    panggilan = {}

    def jalankan(args, **kwargs):
        panggilan["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout="Microsoft Andika|id-ID\n")

    monkeypatch.setattr(paket_suara.subprocess, "run", jalankan)

    info = paket_suara.buat_paket(tmp_path, ["Loket 1"])

    assert "System.Speech" in panggilan["args"][-1]
    assert info.suara == "Microsoft Andika (Indonesia)"
    indeks = json.loads((tmp_path / "paket.json").read_text(encoding="utf-8"))
    assert indeks["klip"]["kata_loket"] == "kata_loket.wav"
    assert paket_suara.info_paket(tmp_path).versi == info.versi
    assert info.kurang(["Loket 1", "Loket Prioritas"]) == ["kata_prioritas"]


def test_buat_paket_gagal_dilaporkan(tmp_path, monkeypatch):
    monkeypatch.setattr(
        paket_suara.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(args, 1, stderr="tidak ada suara"),
    )
    try:
        paket_suara.buat_paket(tmp_path, [])
    except RuntimeError as exc:
        assert "tidak ada suara" in str(exc)
    else:
        raise AssertionError("seharusnya gagal")
    assert paket_suara.info_paket(tmp_path) is None
