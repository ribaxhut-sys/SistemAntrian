"""
Indikator anjungan di jendela petugas.

Yang diuji terutama `nilai_status`: fakta apa menghasilkan peringatan apa,
dan saran mana yang diberikan. Saran yang salah alamat — menyuruh petugas
loket menekan tombol yang hanya ada di server — sama buruknya dengan tidak
memberi saran sama sekali.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services.status_anjungan import (
    MASALAH,
    NORMAL,
    PERINGATAN,
    StatusAnjungan,
    TabletAnjungan,
    nilai_status,
)

SEKARANG = datetime(2026, 10, 8, 10, 0)


def _nilai(**fakta) -> StatusAnjungan:
    bawaan = dict(di_server=True, host="127.0.0.1", port=8765, sekarang=SEKARANG)
    bawaan.update(fakta)
    return nilai_status(**bawaan)


def _tablet(nama: str, menit_lalu: float | None) -> TabletAnjungan:
    return TabletAnjungan(
        nama, None if menit_lalu is None else SEKARANG - timedelta(minutes=menit_lalu)
    )


# ---------------------------------------------------------------------
# API mati
# ---------------------------------------------------------------------

def test_api_mati_di_server_menyarankan_pasang_ulang():
    status = _nilai(api_hidup=False)

    assert status.tingkat == MASALAH
    assert "mati" in status.judul
    assert any("Pasang ulang" in s for s in status.saran)
    assert not any("Token" in s for s in status.saran)


def test_api_mati_tanpa_berkas_token_menyebut_tokennya_lebih_dulu():
    """Kejadian 2026-10-08: tugas SYSTEM berhenti karena berkas token tidak ada."""
    status = _nilai(api_hidup=False, berkas_token_ada=False)

    assert "Token" in status.saran[0]


def test_api_tidak_terjangkau_dari_loket_tidak_menyuruh_menekan_tombol_server():
    status = _nilai(di_server=False, host="192.168.1.10", api_hidup=False)

    assert status.tingkat == MASALAH
    assert "192.168.1.10:8765" in status.judul
    assert any("komputer server menyala" in s for s in status.saran)
    assert any("jaringan lokal yang sama" in s for s in status.saran)
    assert not any(s.startswith("Buka Pengaturan") for s in status.saran)


# ---------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------

def test_aturan_firewall_lama_minta_pasang_ulang():
    status = _nilai(api_hidup=True, firewall_siap=False)

    assert status.tingkat == MASALAH
    assert "Firewall" in status.ringkas
    assert "Pasang ulang" in status.saran[0]


def test_aturan_firewall_hanya_dinilai_di_server():
    status = _nilai(di_server=False, host="192.168.1.10", api_hidup=True, firewall_siap=False)

    assert status.tingkat == NORMAL


# ---------------------------------------------------------------------
# Tablet
# ---------------------------------------------------------------------

def test_api_berjalan_tanpa_tablet_terdaftar_normal():
    status = _nilai(api_hidup=True)

    assert status.tingkat == NORMAL
    assert not status.bermasalah


def test_tablet_tersambung_dihitung():
    status = _nilai(api_hidup=True, tablet=(_tablet("Pintu", 0.5), _tablet("Lobi", 1)))

    assert status.tingkat == NORMAL
    assert "2 tablet tersambung" in status.ringkas


def test_belum_ada_tablet_yang_tersambung():
    status = _nilai(api_hidup=True, tablet=(_tablet("Pintu", None),))

    assert status.tingkat == PERINGATAN
    assert "belum ada tablet" in status.judul
    assert any("Wi-Fi yang sama" in s for s in status.saran)


def test_tablet_yang_terputus_hari_ini_disebut_namanya():
    status = _nilai(
        api_hidup=True, tablet=(_tablet("Pintu", 0.5), _tablet("Lobi", 15))
    )

    assert status.tingkat == PERINGATAN
    assert "Lobi (terakhir 09:45)" in status.judul
    assert "Pintu" not in status.judul


def test_tablet_cadangan_yang_tidak_dipakai_hari_ini_tidak_mengganggu():
    status = _nilai(
        api_hidup=True,
        tablet=(_tablet("Pintu", 0.5), _tablet("Cadangan", 60 * 24 * 3)),
    )

    assert status.tingkat == NORMAL


# ---------------------------------------------------------------------
# Pita di jendela petugas
# ---------------------------------------------------------------------

def test_pita_tersembunyi_saat_normal_dan_muncul_saat_bermasalah(qtbot):
    from app.ui.indikator_anjungan import PitaAnjungan

    pita = PitaAnjungan(lambda: None)
    qtbot.addWidget(pita)
    pita.show()

    pita.tampilkan(_nilai(api_hidup=True))
    assert pita.isHidden()

    pita.tampilkan(_nilai(api_hidup=False))
    assert not pita.isHidden()
    assert "mati" in pita.judul.text()
    assert "Pasang ulang" in pita.saran.text()


def test_pita_yang_disembunyikan_muncul_lagi_bila_masalahnya_berubah(qtbot):
    from app.ui.indikator_anjungan import PitaAnjungan

    pita = PitaAnjungan(lambda: None)
    qtbot.addWidget(pita)
    mati = _nilai(api_hidup=False)

    pita.tampilkan(mati)
    pita.tombol_tutup.click()
    pita.tampilkan(mati)
    assert pita.isHidden(), "pemeriksaan berkala tidak boleh memunculkannya lagi"

    pita.tampilkan(_nilai(api_hidup=True, firewall_siap=False))
    assert not pita.isHidden()


def test_pita_tidak_menafsirkan_saran_sebagai_html(qtbot):
    from app.ui.indikator_anjungan import PitaAnjungan

    pita = PitaAnjungan(lambda: None)
    qtbot.addWidget(pita)
    pita.tampilkan(StatusAnjungan(MASALAH, "ringkas", "judul", ("<b>wifi</b>",)))

    assert "&lt;b&gt;wifi&lt;/b&gt;" in pita.saran.text()


def test_jendela_petugas_menampilkan_hasil_pemeriksaan(qtbot, admin_auth, monkeypatch):
    """Hasil pemeriksaan di utas sendiri sampai ke bilah status dan pita."""
    monkeypatch.setattr("app.ui.main_window._komputer_server", lambda: True)
    monkeypatch.setattr(
        "app.services.kiosk_server.api_sudah_berjalan", lambda port=8765: True
    )
    status = _nilai(api_hidup=True, firewall_siap=False)
    monkeypatch.setattr(
        "app.services.status_anjungan.periksa_status_anjungan", lambda: status
    )
    from tests.test_ui import _status_palsu

    _status_palsu(monkeypatch, api=True)
    from app.ui.main_window import MainWindow

    jendela = MainWindow(admin_auth)
    qtbot.addWidget(jendela)
    jendela._jadwalkan_periksa_anjungan()
    qtbot.waitUntil(lambda: not jendela.pita_anjungan.isHidden(), timeout=3000)

    assert jendela._label_api.text() == "API anjungan: ● aturan Firewall perlu diperbarui"
    assert "Private" in jendela.pita_anjungan.judul.text()
    assert jendela.pita_anjungan.tombol_layanan is not None

    jendela.pita_anjungan.tombol_layanan.click()
    baris = jendela.navigasi._baris
    assert jendela.menu_aktif[baris].judul == "Layanan Anjungan"
