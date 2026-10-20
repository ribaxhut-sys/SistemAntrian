"""Penjaga: identitas instansi tetap, tidak dapat diubah lewat pengaturan."""

from __future__ import annotations

from pathlib import Path

from app.core import identitas
from app.services.settings_service import SKEMA

RAKIT = Path(__file__).resolve().parent.parent

#: Kunci yang dulu bisa diubah admin dan kini dikunci di kode.
KUNCI_DIKUNCI = ("ticket.header", "display.title", "kiosk.judul")


def test_nama_tampil_memuat_produk_dan_instansi():
    assert identitas.NAMA_TAMPIL == "Sistem Antrian CRO - Bapenda DKI Jakarta"
    assert identitas.JUDUL_TIKET == "BAPENDA DKI JAKARTA"


def test_judul_identitas_tidak_ada_di_pengaturan_admin():
    kunci = {butir.kunci for butir in SKEMA}
    assert not kunci.intersection(KUNCI_DIKUNCI)


def test_judul_tiket_selalu_identitas_tetap(ticket_pdf, antrian_siap, terbitkan):
    nomor = terbitkan("A", 1)[0]
    assert ticket_pdf.susun(nomor).header == identitas.JUDUL_TIKET


def test_android_memakai_nama_instansi_saja():
    """Judul di tablet hanya nama instansi; Windows tetap memakai NAMA_TAMPIL penuh."""
    kiosk = (
        RAKIT / "android-kiosk/app/src/main/java/id/sistemantrian/kiosk/MainActivity.java"
    ).read_text(encoding="utf-8")
    layar = (
        RAKIT / "android-kiosk/layar/src/main/java/id/sistemantrian/layar/MainActivity.java"
    ).read_text(encoding="utf-8")
    assert f'NAMA_TAMPIL = "{identitas.INSTANSI}"' in kiosk
    assert f'NAMA_TAMPIL = "{identitas.INSTANSI}"' in layar
    for manifes in (
        "android-kiosk/app/src/main/AndroidManifest.xml",
        "android-kiosk/layar/src/main/AndroidManifest.xml",
    ):
        assert "Bapenda DKI Jakarta" in (RAKIT / manifes).read_text(encoding="utf-8")
