"""
Ruang kerja petugas dan layar Pengaduan.

Yang diuji di sini adalah perilaku yang tidak dapat dilihat dari service:
bahwa isian ikut berpindah ketika antriannya berganti, bahwa menutup
pelayanan tidak menelan pengaduan yang gagal tersimpan, dan bahwa tombol
Hapus tidak pernah muncul di layar petugas.
"""

from __future__ import annotations

import pytest

from tests.conftest import TEST_PASSWORD


@pytest.fixture
def halaman_kerja(qtbot, auth, antrian_siap):
    """Panel pelayanan lengkap dengan ruang kerjanya, sebagai petugas CRO."""
    from app.services.master_data_service import MasterDataService
    from app.services.note_service import NoteService
    from app.services.queue_service import QueueService
    from app.services.settings_service import SettingsService
    from app.services.survey_service import SurveyService
    from app.ui.queue.service_page import ServicePage

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = ServicePage(
        QueueService(auth),
        MasterDataService(auth),
        SurveyService(auth),
        SettingsService(auth),
        auth,
        note=NoteService(auth),
    )
    qtbot.addWidget(halaman)
    return halaman


@pytest.fixture
def bisu(monkeypatch):
    """
    Tahan kotak dialog kegagalan.

    QMessageBox.exec() membuat test suite menggantung tanpa pesan apa pun —
    tidak ada seorang pun yang menekan tombolnya.
    """
    dicatat: list[str] = []
    monkeypatch.setattr(
        "app.ui.common.tampilkan_error",
        lambda parent, exc, judul="Gagal": dicatat.append(str(exc)),
    )
    return dicatat


# ---------------------------------------------------------------------
# Ruang kerja di panel pelayanan
# ---------------------------------------------------------------------

def test_ruang_kerja_mati_tanpa_antrian(halaman_kerja):
    """Dinonaktifkan, bukan disembunyikan — kolomnya tidak boleh melompat."""
    panel = halaman_kerja.panel_kerja

    assert panel is not None
    assert panel.isVisible() or not panel.isHidden()
    assert not panel.isian_deskripsi.isEnabled()
    assert not panel.tombol_simpan.isEnabled()


def test_ruang_kerja_hidup_setelah_memanggil(halaman_kerja, terbitkan):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    panel = halaman_kerja.panel_kerja
    assert panel.isian_deskripsi.isEnabled()
    assert panel.tombol_simpan.isEnabled()


def test_catatan_tersimpan_lewat_panel(halaman_kerja, terbitkan, auth):
    from app.services.note_service import NoteService

    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    panel = halaman_kerja.panel_kerja
    panel.isian_catatan.setPlainText("Berkas belum lengkap.")
    assert halaman_kerja.simpan_catatan()

    lembar = NoteService(auth).ambil(halaman_kerja.antrian.id)
    assert lembar.catatan == "Berkas belum lengkap."


def test_berpindah_antrian_mengosongkan_isian(halaman_kerja, terbitkan):
    """
    Isian antrian sebelumnya yang tertinggal berarti keluhan orang lain
    ikut tersimpan ke nomor yang sedang ditangani.
    """
    terbitkan("A", 2)
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    panel = halaman_kerja.panel_kerja
    panel.isian_catatan.setPlainText("Catatan nomor pertama.")
    halaman_kerja.simpan_catatan()
    halaman_kerja.mulai_melayani()
    halaman_kerja.selesaikan()

    halaman_kerja.panggil_berikutnya()
    assert panel.isian_catatan.toPlainText() == ""


def test_lembar_yang_sudah_ada_dimuat_kembali(halaman_kerja, terbitkan, auth):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    panel = halaman_kerja.panel_kerja
    panel.isian_catatan.setPlainText("Sudah dijelaskan jadwalnya.")
    halaman_kerja.simpan_catatan()

    # Paksa panel membaca ulang seolah antrian baru saja dipilih lagi.
    antrian = halaman_kerja.antrian
    panel.set_antrian(None)
    panel.set_antrian(antrian)

    assert panel.isian_catatan.toPlainText() == "Sudah dijelaskan jadwalnya."


def test_selesai_menyimpan_ruang_kerja_lebih_dahulu(halaman_kerja, terbitkan, auth):
    """F8 menutup pelayanan; catatannya tidak boleh ikut hilang bersamanya."""
    from app.models import QueueStatus
    from app.services.note_service import NoteService

    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()
    antrian_id = halaman_kerja.antrian.id

    halaman_kerja.panel_kerja.isian_catatan.setPlainText("Selesai dilayani.")
    halaman_kerja.mulai_melayani()
    halaman_kerja.selesaikan()

    lembar = NoteService(auth).ambil(antrian_id)
    assert lembar is not None
    assert lembar.catatan == "Selesai dilayani."
    assert halaman_kerja.queue.get_queue(antrian_id).status is QueueStatus.COMPLETED


def test_pengaduan_tanpa_nama_membatalkan_penyelesaian(
    halaman_kerja, terbitkan, bisu
):
    """
    Antrian TIDAK boleh tertutup ketika pengaduannya gagal disimpan.
    Kartu berganti kosong begitu selesai, dan yang menceritakan keluhannya
    sudah berdiri meninggalkan meja.
    """
    from app.models import QueueStatus

    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()
    antrian_id = halaman_kerja.antrian.id

    halaman_kerja.panel_kerja.isian_deskripsi.setPlainText("Air mati tiga hari.")
    halaman_kerja.mulai_melayani()
    halaman_kerja.selesaikan()

    assert bisu, "petugas wajib diberi tahu alasannya"
    assert halaman_kerja.queue.get_queue(antrian_id).status is not QueueStatus.COMPLETED
    assert halaman_kerja.panel_kerja.isian_deskripsi.toPlainText() == (
        "Air mati tiga hari."
    )


# ---------------------------------------------------------------------
# Layar Pengaduan
# ---------------------------------------------------------------------

@pytest.fixture
def lembar_terisi(auth, antrian_siap, terbitkan):
    """Dua lembar tersimpan: satu pengaduan, satu catatan petugas saja."""
    from app.services.note_service import NoteService

    satu, dua = terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    note = NoteService(auth)
    note.simpan(
        satu.id,
        nama="Budi Santoso",
        nomor_pelanggan="1234567",
        deskripsi="Air mati tiga hari.",
    )
    note.simpan(dua.id, catatan="Berkas belum lengkap.")
    return {"pengaduan": satu, "catatan": dua}


def _halaman_pengaduan(qtbot, auth):
    from app.services.note_service import NoteService
    from app.ui.notes.note_page import NotePage

    halaman = NotePage(NoteService(auth), auth)
    qtbot.addWidget(halaman)
    return halaman


def test_layar_pengaduan_menampilkan_seluruh_lembar(qtbot, auth, lembar_terisi):
    halaman = _halaman_pengaduan(qtbot, auth)
    assert halaman.tabel.rowCount() == 2


def test_pencarian_menyaring_daftar(qtbot, auth, lembar_terisi):
    halaman = _halaman_pengaduan(qtbot, auth)

    halaman.isian_cari.setText("budi")
    halaman.muat_ulang()

    assert halaman.tabel.rowCount() == 1
    assert halaman.terpilih.nama == "Budi Santoso"


def test_hanya_pengaduan_menyembunyikan_catatan_petugas(qtbot, auth, lembar_terisi):
    halaman = _halaman_pengaduan(qtbot, auth)

    halaman.centang_pengaduan.setChecked(True)

    assert halaman.tabel.rowCount() == 1
    assert halaman.terpilih.queue_number == lembar_terisi["pengaduan"].queue_number


def test_rincian_menyembunyikan_isian_yang_kosong(qtbot, auth, lembar_terisi):
    """
    Tujuh baris strip membuat yang benar-benar tertulis tenggelam di antara
    yang memang tidak diisi.
    """
    halaman = _halaman_pengaduan(qtbot, auth)
    halaman.isian_cari.setText("Berkas belum lengkap")
    halaman.muat_ulang()

    teks = _teks_rincian(halaman)
    assert "Berkas belum lengkap." in teks
    assert "TELEPON" not in teks
    assert "ALAMAT" not in teks


def _teks_rincian(halaman) -> str:
    from PySide6.QtWidgets import QLabel

    bagian: list[str] = []
    for i in range(halaman.susunan_rincian.count()):
        widget = halaman.susunan_rincian.itemAt(i).widget()
        if widget is None:
            continue
        bagian += [label.text() for label in widget.findChildren(QLabel)]
    return "\n".join(bagian)


def test_tombol_hapus_tidak_ada_untuk_petugas(qtbot, auth, lembar_terisi):
    """Menghapus data pribadi adalah tindakan administratif, bukan harian."""
    halaman = _halaman_pengaduan(qtbot, auth)

    assert not halaman.boleh_hapus
    assert not halaman.tombol_hapus.isVisible()


def test_admin_dapat_menghapus_lembar(qtbot, auth, lembar_terisi, monkeypatch):
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    halaman = _halaman_pengaduan(qtbot, auth)

    monkeypatch.setattr(
        "app.ui.notes.note_page.konfirmasi", lambda *a, **k: True
    )
    assert halaman.boleh_hapus
    sebelum = halaman.tabel.rowCount()

    halaman.hapus()

    assert halaman.tabel.rowCount() == sebelum - 1
