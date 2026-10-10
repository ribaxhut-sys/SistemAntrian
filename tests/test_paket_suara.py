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

    skrip = panggilan["args"][-1]
    assert skrip.index("Windows.Media.SpeechSynthesis") < skrip.index("System.Speech.Synthesis"), (
        "Andika (OneCore) hanya terlihat lewat WinRT; System.Speech cadangan"
    )
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


def test_hening_panjang_di_awal_dan_akhir_klip_dipangkas(tmp_path):
    import array
    import wave

    laju = 16000
    sampel = array.array("h", [0] * int(laju * 0.2) + [8000, -8000] * 2000 + [0] * int(laju * 0.8))
    berkas = tmp_path / "angka_1.wav"
    with wave.open(str(berkas), "wb") as keluar:
        keluar.setnchannels(1)
        keluar.setsampwidth(2)
        keluar.setframerate(laju)
        keluar.writeframes(sampel.tobytes())

    paket_suara.pangkas_hening(berkas)

    with wave.open(str(berkas), "rb") as masuk:
        detik = masuk.getnframes() / masuk.getframerate()
    assert abs(detik - (0.25 + paket_suara.SISA_HENING_DEPAN + paket_suara.SISA_HENING_BELAKANG)) < 0.01

