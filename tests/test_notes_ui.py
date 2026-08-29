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
# Ruang kerja (dialog) dan baris ringkasnya
# ---------------------------------------------------------------------

def _buka(halaman, qtbot):
    """Dialog ruang kerja untuk antrian yang sedang ditangani."""
    from app.ui.queue.note_dialog import NoteDialog

    dialog = NoteDialog(halaman.note, halaman.antrian, halaman)
    qtbot.addWidget(dialog)
    return dialog


def test_tombol_ruang_kerja_mati_tanpa_antrian(halaman_kerja):
    assert not halaman_kerja.tombol_kerja.isEnabled()
    assert "setelah nomor dipanggil" in halaman_kerja.label_kerja.text()


def test_tombol_ruang_kerja_hidup_setelah_memanggil(halaman_kerja, terbitkan):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    assert halaman_kerja.tombol_kerja.isEnabled()
    assert "Belum ada" in halaman_kerja.label_kerja.text()


def test_isian_formulir_tidak_saling_menimpa(halaman_kerja, terbitkan, qtbot):
    """
    Bentuk sebelumnya menempelkan formulir ini ke kolom kiri panel
    pelayanan, dan tujuh isian tidak muat di sana: barisnya tergencet
    sampai label dan isian saling menimpa. Dialog punya ruangnya sendiri,
    dan test ini yang menjaganya tetap begitu.
    """
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    dialog.show()
    qtbot.waitExposed(dialog)

    kotak = (
        dialog.isian_nama,
        dialog.isian_telepon,
        dialog.isian_alamat,
        dialog.isian_deskripsi,
    )
    for atas, bawah in zip(kotak, kotak[1:]):
        sisi_atas = atas.mapTo(dialog, atas.rect().bottomLeft()).y()
        sisi_bawah = bawah.mapTo(dialog, bawah.rect().topLeft()).y()
        assert sisi_atas <= sisi_bawah, (
            f"{atas.objectName() or atas} menimpa isian di bawahnya"
        )

    # Setiap isian harus setinggi hurufnya sendiri, bukan tergencet
    # menjadi beberapa piksel.
    for isian in kotak:
        assert isian.height() >= isian.fontMetrics().height()


def test_catatan_tersimpan_lewat_dialog(halaman_kerja, terbitkan, auth, qtbot):
    from app.services.note_service import NoteService

    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_catatan.setPlainText("Berkas belum lengkap.")
    assert dialog.simpan()

    lembar = NoteService(auth).ambil(halaman_kerja.antrian.id)
    assert lembar.catatan == "Berkas belum lengkap."


def test_dialog_tetap_terbuka_setelah_menyimpan(halaman_kerja, terbitkan, qtbot):
    """Petugas sering menyimpan di tengah pembicaraan lalu meneruskan."""
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    dialog.show()
    dialog.isian_catatan.setPlainText("Catatan sementara.")
    dialog.simpan()

    assert dialog.isVisible()
    assert not dialog.berubah


def test_lembar_yang_sudah_ada_dimuat_kembali(halaman_kerja, terbitkan, qtbot):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    pertama = _buka(halaman_kerja, qtbot)
    pertama.isian_catatan.setPlainText("Sudah dijelaskan jadwalnya.")
    pertama.simpan()

    kedua = _buka(halaman_kerja, qtbot)
    assert kedua.isian_catatan.toPlainText() == "Sudah dijelaskan jadwalnya."
    assert not kedua.berubah


def test_pengaduan_tanpa_nama_ditolak_dan_isian_tetap_ada(
    halaman_kerja, terbitkan, qtbot, bisu
):
    """
    Isian TIDAK boleh ikut hilang bersama pesan gagalnya: yang
    menceritakan keluhannya sudah selesai berbicara.
    """
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_deskripsi.setPlainText("Air mati tiga hari.")

    assert not dialog.simpan()
    assert bisu, "petugas wajib diberi tahu alasannya"
    assert dialog.isian_deskripsi.toPlainText() == "Air mati tiga hari."


def test_menutup_dengan_isian_belum_tersimpan_dikonfirmasi(
    halaman_kerja, terbitkan, qtbot, monkeypatch
):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_catatan.setPlainText("Belum sempat disimpan.")

    ditanya: list[str] = []
    monkeypatch.setattr(
        "app.ui.queue.note_dialog.konfirmasi",
        lambda parent, pertanyaan, judul="Konfirmasi": ditanya.append(pertanyaan)
        and False,
    )
    dialog.reject()

    assert ditanya, "menutup tanpa menyimpan wajib ditanyakan"
    assert dialog.result() != dialog.DialogCode.Accepted


def test_menutup_tanpa_perubahan_tidak_bertanya(
    halaman_kerja, terbitkan, qtbot, monkeypatch
):
    """Pertanyaan yang muncul tanpa alasan membuat petugas berhenti membacanya."""
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    ditanya: list[str] = []
    monkeypatch.setattr(
        "app.ui.queue.note_dialog.konfirmasi",
        lambda *a, **k: ditanya.append("x") or True,
    )
    dialog.reject()

    assert not ditanya


def test_kedua_kotak_terlihat_tanpa_berpindah_tab(halaman_kerja, terbitkan, qtbot):
    """
    Tab menyembunyikan separuh formulir di balik klik, dan yang tersembunyi
    justru catatan petugas — bagian yang paling sering lupa diisi.
    """
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    dialog.show()
    qtbot.waitExposed(dialog)

    assert dialog.isian_deskripsi.isVisible()
    assert dialog.isian_catatan.isVisible()


def test_kapsul_mengikuti_isi_lembar(halaman_kerja, terbitkan, qtbot):
    """Petugas tahu lembar ini menjadi apa sebelum menekan Simpan."""
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    assert dialog.kapsul.text() == "KOSONG"

    dialog.isian_catatan.setPlainText("Berkas belum lengkap.")
    assert dialog.kapsul.text() == "CATATAN"

    dialog.isian_deskripsi.setPlainText("Air mati tiga hari.")
    assert dialog.kapsul.text() == "PENGADUAN"


def test_identitas_ditandai_wajib_hanya_setelah_ada_deskripsi(
    halaman_kerja, terbitkan, qtbot
):
    """
    Kewajibannya bersyarat. Peringatan yang menyala pada lembar yang hanya
    berisi catatan petugas akan cepat berhenti dibaca.
    """
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    assert dialog.isian_nama.property("wajib") is None
    assert "*" not in dialog.label_nama.text()

    dialog.isian_deskripsi.setPlainText("Air mati tiga hari.")

    assert dialog.isian_nama.property("wajib") == "true"
    assert dialog.label_nama.text().endswith("*")
    assert "Nama" in dialog.label_pelapor.text()

    dialog.isian_nama.setText("Budi")
    assert dialog.isian_nama.property("wajib") is None
    assert "Nama" not in dialog.label_pelapor.text()


def test_tombol_simpan_mati_selama_belum_ada_isi(halaman_kerja, terbitkan, qtbot):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    assert not dialog.tombol_simpan.isEnabled()

    # Identitas saja bukan isi: tidak ada keluhan maupun catatan di sana.
    dialog.isian_nama.setText("Budi")
    assert not dialog.tombol_simpan.isEnabled()

    dialog.isian_catatan.setPlainText("Berkas belum lengkap.")
    assert dialog.tombol_simpan.isEnabled()


def test_penghitung_huruf_memperingatkan_sebelum_batas(
    halaman_kerja, terbitkan, qtbot
):
    """
    Petugas yang baru tahu batasnya ketika penolakan muncul harus memotong
    kalimat orang lain sambil orangnya menunggu.
    """
    from app.services.note_service import PANJANG_CATATAN
    from app.ui.style import TEXT_MUTED

    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_catatan.setPlainText("abc")
    assert dialog.hitung_catatan.text() == f"3 / {PANJANG_CATATAN}"
    assert TEXT_MUTED in dialog.hitung_catatan.styleSheet()

    dialog.isian_catatan.setPlainText("a" * (PANJANG_CATATAN - 1))
    assert TEXT_MUTED not in dialog.hitung_catatan.styleSheet()


def test_keadaan_menyebut_perubahan_yang_belum_disimpan(
    halaman_kerja, terbitkan, qtbot
):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    assert "Belum pernah disimpan" in dialog.label_keadaan.text()

    dialog.isian_catatan.setPlainText("Belum sempat disimpan.")
    assert "belum disimpan" in dialog.label_keadaan.text()

    dialog.simpan()
    assert "Tersimpan" in dialog.label_keadaan.text()


def test_baris_ringkas_menyebut_keadaan_lembar(halaman_kerja, terbitkan, qtbot):
    """
    Lembar yang tersembunyi di balik dialog mudah terlupakan sama sekali
    bila layarnya tidak menyebut keadaannya.
    """
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_nama.setText("Budi")
    dialog.isian_nomor_pelanggan.setText("1234567")
    dialog.isian_deskripsi.setPlainText("Air mati tiga hari.")
    dialog.simpan()

    halaman_kerja._lembar_nomor = None
    halaman_kerja._perbarui_baris_kerja()

    assert "Pengaduan tersimpan" in halaman_kerja.label_kerja.text()


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
