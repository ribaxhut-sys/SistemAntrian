"""
Tempel profil WP dari clipboard ECMP ke kartu Data Pelapor.

Parser diuji terpisah dari Qt supaya kontraknya tidak bergantung pada
papan klip mesin penguji. UI hanya diuji pada tombol, pemetaan isian,
konfirmasi, dan bahwa Alamat tidak tersentuh.
"""

from __future__ import annotations

import pytest

from app.utils.profil_wp import (
    JENIS_ID_WP,
    JENIS_INVALID,
    JENIS_PROFIL,
    parse_clipboard_wp,
)

BLOK_PROFIL = (
    "ECMP-WP-1\n"
    "Nama: Ayu Santoso\n"
    "ID WP: 3200000000000034\n"
    "Telepon: 081212345678\n"
    "Email: ayu@example.com\n"
)

BLOK_EMAIL_KOSONG = (
    "ECMP-WP-1\n"
    "Nama: Ayu Santoso\n"
    "ID WP: 3200000000000034\n"
    "Telepon: 081212345678\n"
    "Email:\n"
)

BLOK_TANPA_TELEPON = (
    "ECMP-WP-1\n"
    "Nama: Ayu Santoso\n"
    "ID WP: 3200000000000034\n"
    "Telepon:\n"
    "Email: ayu@example.com\n"
)


# ---------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------

def test_blok_profil_lengkap():
    hasil = parse_clipboard_wp(BLOK_PROFIL)
    assert hasil.jenis == JENIS_PROFIL
    assert hasil.nama == "Ayu Santoso"
    assert hasil.id_wp == "3200000000000034"
    assert hasil.telepon == "081212345678"
    assert hasil.email == "ayu@example.com"


def test_blok_profil_email_kosong_tetap_sah():
    hasil = parse_clipboard_wp(BLOK_EMAIL_KOSONG)
    assert hasil.jenis == JENIS_PROFIL
    assert hasil.nama == "Ayu Santoso"
    assert hasil.id_wp == "3200000000000034"
    assert hasil.telepon == "081212345678"
    assert hasil.email == ""


def test_blok_profil_bom_crlf_dan_baris_kosong():
    teks = (
        "\ufeffECMP-WP-1\r\n"
        "\r\n"
        "Nama: Ayu Santoso\r\n"
        "ID WP: 3200 0000 0000 0034\r\n"
        "\r\n"
        "Telepon: 081212345678\r\n"
        "Email: \r\n"
    )
    hasil = parse_clipboard_wp(teks)
    assert hasil.jenis == JENIS_PROFIL
    assert hasil.nama == "Ayu Santoso"
    assert hasil.id_wp == "3200000000000034"
    assert hasil.telepon == "081212345678"
    assert hasil.email == ""


def test_label_profil_tidak_peka_huruf_besar():
    teks = (
        "ECMP-WP-1\n"
        "nama: Ayu Santoso\n"
        "id wp: 3200000000000034\n"
        "TELEPON: 081212345678\n"
        "Email: ayu@example.com\n"
    )
    hasil = parse_clipboard_wp(teks)
    assert hasil.jenis == JENIS_PROFIL
    assert hasil.telepon == "081212345678"


@pytest.mark.parametrize(
    "teks",
    [
        "ECMP-WP-1\nNama:\nID WP: 3200000000000034\nTelepon: 081212345678\nEmail:\n",
        "ECMP-WP-1\nNama: Ayu Santoso\nID WP:\nTelepon: 081212345678\nEmail:\n",
        BLOK_TANPA_TELEPON,
        "ECMP-WP-1\nNama:\nID WP:\nTelepon:\nEmail:\n",
    ],
)
def test_profil_tanpa_nama_nomor_atau_telepon_invalid(teks):
    assert parse_clipboard_wp(teks).jenis == JENIS_INVALID


def test_id_wp_berkelompok_jadi_digit():
    hasil = parse_clipboard_wp("3200 0000 0000 0034")
    assert hasil.jenis == JENIS_ID_WP
    assert hasil.id_wp == "3200000000000034"
    assert hasil.nama == ""


def test_id_wp_dengan_strip():
    hasil = parse_clipboard_wp("3200-0000-0000-0034")
    assert hasil.jenis == JENIS_ID_WP
    assert hasil.id_wp == "3200000000000034"


def test_id_wp_alfanumerik_tidak_dipaksa_digit():
    hasil = parse_clipboard_wp("CN-10000001")
    assert hasil.jenis == JENIS_ID_WP
    assert hasil.id_wp == "CN-10000001"


def test_nama_orang_ditolak():
    hasil = parse_clipboard_wp("Ayu Santoso")
    assert hasil.jenis == JENIS_INVALID
    assert hasil.nama == ""
    assert hasil.id_wp == ""


@pytest.mark.parametrize(
    "teks",
    [
        "Silakan mengisi formulir pengaduan",
        "<p>Ayu Santoso</p>",
        '{"nama":"Ayu Santoso"}',
        "1234567",
        "",
        "   ",
    ],
)
def test_teks_bebas_ditolak(teks):
    assert parse_clipboard_wp(teks).jenis == JENIS_INVALID


# ---------------------------------------------------------------------
# Tombol Tempel profil
# ---------------------------------------------------------------------

@pytest.fixture
def pelapor(qtbot):
    from app.ui.queue.pelapor_form import PelaporForm

    form = PelaporForm()
    qtbot.addWidget(form)
    form.set_aktif(True)
    return form


@pytest.fixture
def tanpa_konfirmasi(monkeypatch):
    """
    Gagal cepat bila dialog konfirmasi muncul tanpa sengaja.

    konfirmasi() memakai QMessageBox.exec(); tanpa ini, test suite
    menggantung menunggu tombol yang tidak pernah ditekan.
    """

    def jangan(*_a, **_k):
        raise AssertionError("konfirmasi tidak seharusnya dipanggil")

    monkeypatch.setattr("app.ui.queue.pelapor_form.konfirmasi", jangan)


def test_tombol_tempel_ada_di_header(pelapor):
    assert pelapor.tombol_tempel.text() == "Tempel profil"


def test_round_trip_profil_email_boleh_kosong(pelapor, tanpa_konfirmasi):
    pelapor.tempel_teks(BLOK_EMAIL_KOSONG)

    assert pelapor.isian_nama.text() == "Ayu Santoso"
    assert pelapor.isian_nomor_pelanggan.text() == "3200000000000034"
    assert pelapor.isian_telepon.text() == "081212345678"
    assert pelapor.isian_email.text() == ""
    assert pelapor.label_petunjuk.text() == "Profil ditempel"


def test_email_kosong_di_clipboard_tidak_menimpa_isian(pelapor, tanpa_konfirmasi):
    pelapor.isian_email.setText("lama@example.com")
    pelapor.tempel_teks(BLOK_EMAIL_KOSONG)

    assert pelapor.isian_email.text() == "lama@example.com"
    assert pelapor.isian_telepon.text() == "081212345678"


def test_profil_tanpa_telepon_ditolak(pelapor, tanpa_konfirmasi):
    pelapor.tempel_teks(BLOK_TANPA_TELEPON)

    assert pelapor.isian_nama.text() == ""
    assert pelapor.isian_nomor_pelanggan.text() == ""
    assert pelapor.label_petunjuk.text() == "Clipboard bukan profil WP"


def test_id_wp_berkelompok_hanya_mengisi_nomor(pelapor, tanpa_konfirmasi):
    pelapor.isian_nama.setText("Sudah ada")
    pelapor.tempel_teks("3200 0000 0000 0034")

    assert pelapor.isian_nomor_pelanggan.text() == "3200000000000034"
    assert pelapor.isian_nama.text() == "Sudah ada"
    assert pelapor.label_petunjuk.text() == "ID WP ditempel"


def test_nama_orang_tidak_mengisi_nama(pelapor, tanpa_konfirmasi):
    pelapor.tempel_teks("Ayu Santoso")

    assert pelapor.isian_nama.text() == ""
    assert pelapor.isian_nomor_pelanggan.text() == ""
    assert pelapor.label_petunjuk.text() == "Clipboard bukan profil WP"


def test_alamat_tidak_berubah(pelapor, tanpa_konfirmasi):
    pelapor.isian_alamat.setText("Jl. Melati No. 1")
    pelapor.tempel_teks(BLOK_PROFIL)

    assert pelapor.isian_alamat.text() == "Jl. Melati No. 1"
    assert pelapor.isian_nama.text() == "Ayu Santoso"


def test_nama_berbeda_minta_konfirmasi_sebelum_menimpa(pelapor, monkeypatch):
    pelapor.isian_nama.setText("Budi Santoso")
    pelapor.isian_alamat.setText("Jl. Melati No. 1")

    monkeypatch.setattr("app.ui.queue.pelapor_form.konfirmasi", lambda *a, **k: False)
    pelapor.tempel_teks(BLOK_PROFIL)

    assert pelapor.isian_nama.text() == "Budi Santoso"
    assert pelapor.isian_nomor_pelanggan.text() == ""
    assert pelapor.isian_alamat.text() == "Jl. Melati No. 1"

    pertanyaan: list[str] = []

    def ya(_parent, teks, _judul="Konfirmasi"):
        pertanyaan.append(teks)
        return True

    monkeypatch.setattr("app.ui.queue.pelapor_form.konfirmasi", ya)
    pelapor.tempel_teks(BLOK_PROFIL)

    assert pertanyaan == ["Ganti data pelapor?"]
    assert pelapor.isian_nama.text() == "Ayu Santoso"
    assert pelapor.isian_nomor_pelanggan.text() == "3200000000000034"
    assert pelapor.isian_alamat.text() == "Jl. Melati No. 1"


def test_nama_sama_tidak_minta_konfirmasi(pelapor, tanpa_konfirmasi):
    pelapor.isian_nama.setText("Ayu Santoso")
    pelapor.tempel_teks(BLOK_PROFIL)

    assert pelapor.isian_nomor_pelanggan.text() == "3200000000000034"
    assert pelapor.label_petunjuk.text() == "Profil ditempel"


def test_tombol_membaca_clipboard_bukan_html(pelapor, monkeypatch, tanpa_konfirmasi):
    monkeypatch.setattr(pelapor, "_teks_clipboard", lambda: BLOK_PROFIL)
    pelapor.tombol_tempel.click()

    assert pelapor.isian_nama.text() == "Ayu Santoso"
    assert pelapor.isian_nomor_pelanggan.text() == "3200000000000034"
