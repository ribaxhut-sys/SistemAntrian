"""
Test suara panggilan.

Suara bukan bagian penting sistem. Yang diuji terutama adalah bahwa
ketiadaan atau kerusakan perangkat audio tidak pernah menggagalkan
apa pun.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from app.services.sound_service import (
    DURASI_NADA,
    LAJU_SAMPEL,
    NADA_HZ,
    ChimeSoundPlayer,
    NullSoundPlayer,
    buat_nada_panggilan,
    buat_pemutar,
    folder_suara,
)


# ---------------------------------------------------------------------
# Pembangkitan nada
# ---------------------------------------------------------------------

def test_nada_panggilan_dihasilkan_tanpa_berkas_bawaan(tmp_path: Path):
    """
    Nada dibangkitkan sendiri, sehingga aplikasi tidak bergantung pada
    berkas audio yang harus ikut dipaketkan ke dalam .exe.
    """
    berkas = buat_nada_panggilan(tmp_path / "panggilan.wav")

    assert berkas.exists()
    assert berkas.stat().st_size > 1000


def test_berkas_nada_adalah_wav_yang_sah(tmp_path: Path):
    berkas = buat_nada_panggilan(tmp_path / "panggilan.wav")

    with wave.open(str(berkas), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == LAJU_SAMPEL

        durasi = w.getnframes() / w.getframerate()
        harapan = len(NADA_HZ) * DURASI_NADA
        assert abs(durasi - harapan) < 0.01


def test_folder_nada_dibuat_bila_belum_ada(tmp_path: Path):
    tujuan = tmp_path / "belum" / "ada" / "panggilan.wav"
    assert buat_nada_panggilan(tujuan).exists()


def test_folder_suara_dapat_ditulisi():
    folder = folder_suara()
    assert folder.is_dir()

    uji = folder / ".uji-tulis"
    uji.touch()
    assert uji.exists()
    uji.unlink()


# ---------------------------------------------------------------------
# Pemutar diam
# ---------------------------------------------------------------------

def test_pemutar_diam_mencatat_pengumuman():
    pemutar = NullSoundPlayer()

    assert pemutar.announce("A-023", "Loket 2") is False
    assert pemutar.diumumkan == [("A-023", "Loket 2")]


def test_pemutar_diam_tidak_pernah_gagal():
    pemutar = NullSoundPlayer()
    for nomor in ("A-001", "B-999", "", "nomor aneh sekali"):
        pemutar.announce(nomor)
    assert len(pemutar.diumumkan) == 4


def test_suara_dimatikan_menghasilkan_pemutar_diam():
    assert isinstance(buat_pemutar(False), NullSoundPlayer)


# ---------------------------------------------------------------------
# Ketahanan
# ---------------------------------------------------------------------

def test_pemutar_selalu_dapat_dibuat(qapp):
    """
    Komputer tanpa kartu suara harus tetap mendapat pemutar yang aman
    dipanggil, bukan exception saat aplikasi dinyalakan.
    """
    pemutar = buat_pemutar(True)

    assert hasattr(pemutar, "announce")
    assert pemutar.announce("A-001", "Loket 1") in (True, False)


def test_pengumuman_tidak_pernah_melempar_exception(qapp):
    pemutar = buat_pemutar(True)
    for nomor, loket in [("A-001", "Loket 1"), ("B-002", None), ("", "")]:
        assert pemutar.announce(nomor, loket) in (True, False)


def test_perangkat_audio_rusak_diturunkan_ke_pemutar_diam(monkeypatch, qapp):
    """
    Bila penyiapan audio gagal, aplikasi harus berjalan tanpa suara —
    bukan berjalan dengan pemutar yang setiap kali dipanggil meledak.
    """
    monkeypatch.setattr(ChimeSoundPlayer, "_siapkan_nada", lambda self: False)
    assert isinstance(buat_pemutar(True), NullSoundPlayer)


def test_kegagalan_saat_memutar_ditelan(monkeypatch, qapp, tmp_path):
    pemutar = ChimeSoundPlayer(tmp_path)
    if not pemutar._siap:
        pytest.skip("perangkat audio tidak tersedia di lingkungan ini")

    class EfekRusak:
        def play(self):
            raise RuntimeError("perangkat audio dicabut")

    pemutar._efek = EfekRusak()
    assert pemutar.announce("A-001", "Loket 1") is False


# ---------------------------------------------------------------------
# Pengumuman lisan (text-to-speech)
# ---------------------------------------------------------------------

def test_susunan_kalimat_pengumuman():
    from app.services.sound_service import _teks_pengumuman

    assert (
        _teks_pengumuman("A-023", "Loket 2")
        == "Nomor antrian A, dua puluh tiga, silakan menuju Loket 2."
    )


def test_kalimat_tanpa_loket_tetap_wajar():
    """Sebelum antrian dipanggil ke loket mana pun, kalimat tetap masuk akal."""
    from app.services.sound_service import _teks_pengumuman

    assert _teks_pengumuman("B-005", None) == "Nomor antrian B, lima."


def test_prefix_dua_huruf_dieja_terpisah():
    from app.services.sound_service import _teks_pengumuman

    kalimat = _teks_pengumuman("AB-001", "Loket 1")
    assert kalimat.startswith("Nomor antrian A B, satu,")


def test_angka_ratusan_terdengar_wajar():
    from app.services.sound_service import _teks_pengumuman

    assert "seratus dua puluh tiga" in _teks_pengumuman("C-123", None)


def test_tts_disiapkan_saat_pemutar_dibuat(qapp):
    pemutar = ChimeSoundPlayer()
    assert pemutar._tts is not None


def test_suara_indonesia_dipilih_bila_tersedia(qapp):
    """
    Tanpa pemilihan eksplisit, mesin TTS dapat memakai suara bahasa lain
    sebagai bawaan, dan pengumuman tidak akan terdengar sebagai Indonesia.
    """
    pemutar = ChimeSoundPlayer()
    if pemutar._tts is None:
        pytest.skip("text-to-speech tidak tersedia di lingkungan ini")

    tersedia = pemutar._tts.availableVoices()
    ada_suara_indonesia = any(v.locale().name().startswith("id") for v in tersedia)

    if ada_suara_indonesia:
        assert pemutar._tts.voice().locale().name().startswith("id")


def test_announce_tidak_melempar_walau_tts_rusak(monkeypatch, qapp, tmp_path):
    """Kegagalan mengucapkan tidak boleh menggagalkan nada yang sudah berbunyi."""
    pemutar = ChimeSoundPlayer(tmp_path)
    if not pemutar._siap:
        pytest.skip("perangkat audio tidak tersedia di lingkungan ini")

    class TtsRusak:
        def say(self, teks):
            raise RuntimeError("mesin TTS mogok")

    pemutar._tts = TtsRusak()
    assert pemutar.announce("A-001", "Loket 1") is True  # nada tetap berhasil


def test_penyiapan_tts_gagal_tidak_menggagalkan_nada(monkeypatch, qapp, tmp_path):
    """
    Komputer tanpa mesin TTS terpasang (jarang di Windows, tetapi mungkin
    pada instalasi minimal) tetap harus bisa memanggil dengan nada.

    Kegagalan disimulasikan pada konstruktor QTextToSpeech itu sendiri,
    bukan dengan mengganti seluruh _siapkan_tts — mengganti seluruh method
    juga akan membuang try/except di dalamnya dan pengujian jadi tidak
    membuktikan apa pun soal ketahanan kode produksi.
    """
    from PySide6.QtTextToSpeech import QTextToSpeech

    def meledak(self, *args, **kwargs):
        raise RuntimeError("mesin text-to-speech tidak tersedia")

    monkeypatch.setattr(QTextToSpeech, "__init__", meledak)

    pemutar = ChimeSoundPlayer(tmp_path)  # tidak boleh melempar

    assert pemutar._tts is None
    assert pemutar._siap  # nada tetap tersedia walau TTS gagal disiapkan
    assert pemutar.announce("A-001", "Loket 1") is True
