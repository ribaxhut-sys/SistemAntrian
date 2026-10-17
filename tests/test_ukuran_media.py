"""Ukuran media anjungan dan peringatan rasio di dialog jadwal."""

from __future__ import annotations

import struct

from app.services import daftar_putar
from app.services.ukuran_media import Ukuran, keterangan_rasio, ukuran_media


def _kotak(jenis: bytes, isi: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(isi), jenis) + isi


def _tkhd(lebar: int, tinggi: int, *, versi: int = 0, putar: bool = False) -> bytes:
    """Kotak tkhd minimal: hanya matriks dan ukuran yang dibaca."""
    awal = bytes([versi, 0, 0, 0]) + bytes(20 if versi == 0 else 32) + bytes(16)
    if putar:  # 90°: a=0, b=1, c=-1, d=0
        matriks = struct.pack(">9i", 0, 0x10000, 0, -0x10000, 0, 0, 0, 0, 0x40000000)
    else:
        matriks = struct.pack(">9i", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)
    return _kotak(b"tkhd", awal + matriks + struct.pack(">II", lebar << 16, tinggi << 16))


def _mp4(tmp_path, *trek: bytes, nama="v.mp4"):
    isi = _kotak(b"ftyp", b"isom" + bytes(4)) + _kotak(b"mdat", bytes(64))
    isi += _kotak(b"moov", _kotak(b"mvhd", bytes(100)) + b"".join(
        _kotak(b"trak", t) for t in trek
    ))
    path = tmp_path / nama
    path.write_bytes(isi)
    return path


def test_ukuran_video_dari_tkhd_melewati_trek_suara(tmp_path):
    path = _mp4(tmp_path, _tkhd(0, 0), _tkhd(1920, 1080))
    assert ukuran_media(path) == Ukuran(1920, 1080)


def test_ukuran_video_tkhd_versi_1(tmp_path):
    assert ukuran_media(_mp4(tmp_path, _tkhd(1280, 720, versi=1))) == Ukuran(1280, 720)


def test_video_ponsel_yang_diputar_dibaca_tegak(tmp_path):
    path = _mp4(tmp_path, _tkhd(1920, 1080, putar=True))
    assert ukuran_media(path) == Ukuran(1080, 1920)


def test_berkas_rusak_atau_format_lain_tidak_diketahui(tmp_path):
    rusak = tmp_path / "rusak.mp4"
    rusak.write_bytes(b"\x00\x00\x00\x02xx")
    mkv = tmp_path / "a.mkv"
    mkv.write_bytes(b"\x1a\x45\xdf\xa3")

    assert ukuran_media(rusak) is None
    assert ukuran_media(mkv) is None
    assert ukuran_media(tmp_path / "tidak-ada.mp4") is None


def test_ukuran_gambar(tmp_path):
    from PIL import Image

    path = tmp_path / "a.png"
    Image.new("RGB", (800, 600)).save(path)
    assert ukuran_media(path) == Ukuran(800, 600)


def test_label_rasio():
    assert Ukuran(1920, 1080).label_rasio == "16:9"
    assert Ukuran(1080, 1920).label_rasio == "9:16"
    assert Ukuran(1366, 768).label_rasio == "±16:9"


def test_berkas_tegak_di_panel_atas_diberi_peringatan():
    tegak = Ukuran(1080, 1920)

    keterangan, peringatan = keterangan_rasio(tegak, daftar_putar.TAMPIL_PANEL)
    assert "1080 × 1920" in keterangan and "tegak" in keterangan
    assert "panel atas" in peringatan
    assert keterangan_rasio(tegak, daftar_putar.TAMPIL_KEDUANYA)[1]
    # Bentuk layar tablet tidak diketahui: layar penuh tanpa peringatan.
    assert keterangan_rasio(tegak, daftar_putar.TAMPIL_PENUH)[1] == ""
    assert keterangan_rasio(Ukuran(1920, 1080), daftar_putar.TAMPIL_PANEL)[1] == ""
    assert "tidak terbaca" in keterangan_rasio(None, daftar_putar.TAMPIL_PANEL)[0]


def test_dialog_jadwal_memperbarui_peringatan_mengikuti_tampil_di(qtbot, tmp_path):
    from app.ui.settings.dialogs import JadwalIklanDialog

    path = _mp4(tmp_path, _tkhd(1080, 1920))
    dialog = JadwalIklanDialog(
        None, daftar_putar.Butir(path.name), gambar=False, berkas=path
    )
    qtbot.addWidget(dialog)

    assert "9:16" in dialog.label_ukuran.text()
    assert not dialog.peringatan_rasio.isHidden()
    dialog.tampil.setCurrentIndex(dialog.tampil.findData(daftar_putar.TAMPIL_PENUH))
    assert dialog.peringatan_rasio.isHidden()
