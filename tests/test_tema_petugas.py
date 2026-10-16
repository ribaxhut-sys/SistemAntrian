"""Tema tampilan layar petugas: pengubahan warna, penyimpanan, tab Tampilan."""

from __future__ import annotations

import colorsys

import pytest

from app.ui import tema_petugas as tp
from app.ui.tema_petugas import (
    TEMA,
    baca_tema,
    simpan_tema,
    ubah_html,
    ubah_qss,
    ubah_warna,
)


def _rona(hexa: str) -> float:
    r, g, b = (int(hexa.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[0]


def _terang(hexa: str) -> float:
    r, g, b = (int(hexa.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[1]


@pytest.fixture(autouse=True)
def _kembalikan_tema():
    """Tema dan stylesheet aplikasi tidak boleh bocor ke tes lain."""
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    awal = app.styleSheet() if app is not None else ""
    palet = QPalette(app.palette()) if app is not None else None
    yield
    app = QApplication.instance()
    if app is not None:
        tp.terapkan_tema(app, tp.TEMA_BAWAAN)
        app.setStyleSheet(awal)
        if palet is not None:
            app.setPalette(palet)


def test_ada_tema_pink_dan_kemerdekaan():
    assert {"indigo", "sakura", "merdeka", "malam"} <= set(TEMA)
    assert len(TEMA) >= 8


def test_bawaan_tidak_mengubah_apa_pun():
    qss = "QPushButton { background: #FFFFFF; color: #172033; border: 1px solid #E1E7EF; }"
    assert ubah_qss(qss, TEMA["indigo"]) == qss


@pytest.mark.parametrize("kunci", ["samudra", "zamrud", "pasir", "sakura", "merdeka"])
def test_tema_berwarna_menggeser_rona_aksen_saja(kunci):
    tema = TEMA[kunci]
    baru = ubah_warna("#4F46E5", tema, teks=False)
    assert abs(_rona(baru) - tema.rona) < 0.02
    # Terang tidak berubah banyak: tombol tetap terbaca.
    assert abs(_terang(baru) - _terang("#4F46E5")) < 0.03
    # Teks slate netral tidak ikut diwarnai ulang (kecuali tema hangat).
    if not tema.hangat:
        assert ubah_warna("#172033", tema, teks=True) == "#172033"


def test_tema_gelap_membalik_teks_dan_latar_menurut_fungsinya():
    malam = TEMA["malam"]
    assert _terang(ubah_warna("#172033", malam, teks=True)) > 0.7
    assert _terang(ubah_warna("#FFFFFF", malam, teks=False)) < 0.2
    # Putih sebagai TEKS (pada tombol berwarna) tetap putih.
    assert ubah_warna("#FFFFFF", malam, teks=True) == "#FFFFFF"
    # Kepala/tombol gelap sebagai latar tetap gelap.
    assert ubah_warna("#3730A3", malam, teks=False) == "#3730A3"


def test_ubah_qss_hanya_menyentuh_properti_warna():
    qss = (
        'QPushButton:hover { background: #FFFFFF; border: 1px solid #E1E7EF;'
        " color: #172033; width: 10px; }"
    )
    hasil = ubah_qss(qss, TEMA["malam"])
    assert "QPushButton:hover" in hasil
    assert "width: 10px" in hasil
    assert "#FFFFFF" not in hasil.split("background:")[1].split(";")[0]


def test_ubah_html_mengubah_warna_teks_di_dalam_label():
    html = "<b style='color:#172033'>Layanan</b>"
    assert "#172033" not in ubah_html(html, TEMA["malam"])
    assert ubah_html(html, TEMA["indigo"]) == html


def test_simpan_dan_baca_tema(tmp_path):
    berkas = tmp_path / "tampilan.json"
    assert baca_tema(berkas) == "indigo"  # belum ada berkas
    assert simpan_tema("sakura", berkas) is True
    assert baca_tema(berkas) == "sakura"


def test_berkas_rusak_atau_tema_asing_kembali_ke_bawaan(tmp_path):
    berkas = tmp_path / "tampilan.json"
    berkas.write_text("bukan json", encoding="utf-8")
    assert baca_tema(berkas) == "indigo"
    berkas.write_text('{"tema": "tidak-ada"}', encoding="utf-8")
    assert baca_tema(berkas) == "indigo"
    with pytest.raises(ValueError):
        simpan_tema("tidak-ada", berkas)


def test_tab_tampilan_menyimpan_dan_menerapkan_langsung(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from app.ui.tampilan_page import TampilanPage

    berkas = tmp_path / "tampilan.json"
    monkeypatch.setenv("ANTRIAN_TAMPILAN_PATH", str(berkas))
    halaman = TampilanPage()
    qtbot.addWidget(halaman)

    assert set(halaman.kartu) == set(TEMA)
    halaman.pilih("malam")

    assert baca_tema(berkas) == "malam"
    assert tp.tema_aktif().kunci == "malam"
    assert "✓" in halaman.kartu["malam"].label_nama.text()
    assert "✓" not in halaman.kartu["indigo"].label_nama.text()
    assert "background" in QApplication.instance().styleSheet()


def test_widget_lama_ikut_berganti_dan_kembali_ke_aslinya(qtbot):
    from PySide6.QtWidgets import QApplication, QLabel

    app = QApplication.instance()
    tp.terapkan_tema(app, "indigo")  # memasang penyaring
    label = QLabel("x")
    qtbot.addWidget(label)
    label.setStyleSheet("background: #EEF2FF; color: #4F46E5;")
    asli = label.styleSheet()

    tp.terapkan_tema(app, "sakura")
    assert label.styleSheet() != asli

    tp.terapkan_tema(app, "indigo")
    assert label.styleSheet() == asli


# ---------------------------------------------------------------------
# Kontras
# ---------------------------------------------------------------------


def test_rasio_kontras_hitam_putih_dua_puluh_satu():
    assert round(tp.rasio_kontras("#000000", "#FFFFFF"), 1) == 21.0


def test_pastikan_kontras_memperbaiki_teks_pucat_di_latar_terang():
    hasil = tp.pastikan_kontras("#A3AEC0", "#F2F4F7", 4.5)
    assert tp.rasio_kontras(hasil, "#F2F4F7") >= 4.5
    # Warna yang sudah cukup tidak diubah.
    assert tp.pastikan_kontras("#172033", "#FFFFFF", 4.5) == "#172033"


def test_pastikan_kontras_memperbaiki_teks_gelap_di_latar_gelap():
    hasil = tp.pastikan_kontras("#172033", "#1E293B", 4.5)
    assert tp.rasio_kontras(hasil, "#1E293B") >= 4.5


@pytest.mark.parametrize("kunci", list(TEMA))
def test_setiap_aturan_stylesheet_terbaca_pada_semua_tema(kunci):
    """Pada tiap aturan ber-latar solid, teksnya cukup kontras."""
    import re

    from app.ui.style import STYLESHEET

    qss = ubah_qss(STYLESHEET, TEMA[kunci])
    minimum = tp.KONTRAS_MIN_TINGGI if TEMA[kunci].kontras else tp.KONTRAS_MIN
    gagal = []
    for m in re.finditer(r"(?P<sel>[^{}]*)\{(?P<isi>[^{}]*)\}", qss):
        bg = tp._BG.search(m.group("isi"))
        teks = tp._TEKS.search(m.group("isi"))
        if not bg or not teks:
            continue
        batas = tp.KONTRAS_MIN_NONAKTIF if ":disabled" in m.group("sel") else minimum
        r = tp.rasio_kontras(teks.group(1), bg.group(1))
        if r < batas - 0.05:
            gagal.append((m.group("sel").strip(), teks.group(1), bg.group(1), round(r, 2)))
    assert gagal == []


def test_nama_warna_white_ikut_dibalik_pada_tema_gelap():
    qss = "QFrame#k { background: white; border: 1px solid #E1E7EF; }"
    hasil = ubah_qss(qss, TEMA["malam"])
    assert "white" not in hasil
    latar = hasil.split("background:")[1].split(";")[0].strip()
    assert _terang(latar) < 0.2


def test_warna_tema_untuk_kode_yang_menggambar_sendiri(monkeypatch):
    monkeypatch.setattr(tp, "_aktif", TEMA["malam"])
    assert _terang(tp.warna_tema("#172033", teks=True)) > 0.7
    monkeypatch.setattr(tp, "_aktif", TEMA["indigo"])
    assert tp.warna_tema("#172033", teks=True) == "#172033"


def test_simpan_tema_atomik_tidak_meninggalkan_berkas_sementara(tmp_path):
    berkas = tmp_path / "tampilan.json"
    assert simpan_tema("zamrud", berkas) is True
    assert baca_tema(berkas) == "zamrud"
    assert [p.name for p in tmp_path.iterdir()] == ["tampilan.json"]
