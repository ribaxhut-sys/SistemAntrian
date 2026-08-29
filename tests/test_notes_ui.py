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
    """
    Dialog ruang kerja untuk antrian yang sedang ditangani.

    Identitas dibaca dari formulir Data Pelapor di layar pelayanan, persis
    seperti yang dilakukan `ServicePage.buka_ruang_kerja`.
    """
    from app.ui.queue.note_dialog import NoteDialog

    dialog = NoteDialog(
        halaman.note, halaman.antrian, lambda: halaman.pelapor.nilai, halaman
    )
    qtbot.addWidget(dialog)
    return dialog


def _panggil(halaman, terbitkan, prefix: str = "A"):
    """Terbitkan satu nomor lalu panggil ke loket halaman ini."""
    terbitkan(prefix)
    halaman.muat_ulang()
    halaman.panggil_berikutnya()


def test_tombol_ruang_kerja_mati_tanpa_antrian(halaman_kerja):
    assert not halaman_kerja.tombol_kerja.isEnabled()
    assert "setelah nomor dipanggil" in halaman_kerja.label_kerja.text()


def test_tombol_ruang_kerja_hidup_setelah_memanggil(halaman_kerja, terbitkan):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    assert halaman_kerja.tombol_kerja.isEnabled()
    assert "Belum ada" in halaman_kerja.label_kerja.text()


def test_isian_pelapor_tidak_saling_menimpa(halaman_kerja, terbitkan, qtbot):
    """
    Formulir tujuh isian pernah diperas di kolom kiri sampai label dan
    isian saling menimpa. Setelah dipecah — identitas di layar, kotak
    keluhan di dialog — test ini yang menjaga sisa di layarnya tetap muat.
    """
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.show()
    qtbot.waitExposed(halaman_kerja)

    pelapor = halaman_kerja.pelapor
    kotak = (pelapor.isian_nama, pelapor.isian_telepon, pelapor.isian_alamat)
    for atas, bawah in zip(kotak, kotak[1:]):
        sisi_atas = atas.mapTo(pelapor, atas.rect().bottomLeft()).y()
        sisi_bawah = bawah.mapTo(pelapor, bawah.rect().topLeft()).y()
        assert sisi_atas <= sisi_bawah, "isian pelapor menimpa isian di bawahnya"

    for isian in kotak:
        assert isian.height() >= isian.fontMetrics().height()


def test_kotak_dialog_tidak_saling_menimpa(halaman_kerja, terbitkan, qtbot):
    _panggil(halaman_kerja, terbitkan)

    dialog = _buka(halaman_kerja, qtbot)
    dialog.show()
    qtbot.waitExposed(dialog)

    atas, bawah = dialog.isian_deskripsi, dialog.isian_catatan
    assert (
        atas.mapTo(dialog, atas.rect().bottomLeft()).y()
        <= bawah.mapTo(dialog, bawah.rect().topLeft()).y()
    )
    for kotak in (atas, bawah):
        assert kotak.height() >= kotak.fontMetrics().height()


def test_identitas_ada_di_layar_bukan_di_dialog(halaman_kerja, terbitkan, qtbot):
    """
    Identitas ditulis sambil bertanya kepada orang di depan meja; keluhan
    ditulis sambil mendengarkan. Dua kegiatan, dua tempat.
    """
    _panggil(halaman_kerja, terbitkan)

    dialog = _buka(halaman_kerja, qtbot)
    assert not hasattr(dialog, "isian_nama")
    assert halaman_kerja.pelapor.isian_nama.isEnabled()


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


def test_pengaduan_tanpa_identitas_ditahan_sebelum_menyentuh_database(
    halaman_kerja, terbitkan, qtbot, bisu
):
    """
    Ditahan di dialog, bukan dibiarkan ditolak service: petugas perlu tahu
    bahwa yang kurang ada di LAYAR PELAYANAN, bukan di dialog ini. Keluhan
    yang sudah tertulis tidak boleh ikut hilang bersama pesan gagalnya.
    """
    _panggil(halaman_kerja, terbitkan)

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_deskripsi.setPlainText("Air mati tiga hari.")

    assert not dialog.simpan()
    assert not bisu, "tidak perlu kotak dialog; cukup keterangan di kakinya"
    assert "Lengkapi" in dialog.label_keadaan.text()
    assert "layar" in dialog.label_keadaan.text()
    assert dialog.isian_deskripsi.toPlainText() == "Air mati tiga hari."


def test_pengaduan_tersimpan_bersama_identitas_dari_layar(
    halaman_kerja, terbitkan, qtbot, auth
):
    from app.services.note_service import NoteService

    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.pelapor.isian_nama.setText("Budi Santoso")
    halaman_kerja.pelapor.isian_nomor_pelanggan.setText("1234567")
    halaman_kerja.pelapor.isian_telepon.setText("081234567890")

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_deskripsi.setPlainText("Air mati tiga hari.")
    assert dialog.simpan()

    lembar = NoteService(auth).ambil(halaman_kerja.antrian.id)
    assert lembar.nama == "Budi Santoso"
    assert lembar.nomor_pelanggan == "1234567"
    assert lembar.telepon == "081234567890"
    assert lembar.deskripsi == "Air mati tiga hari."


def test_berpindah_nomor_mengosongkan_data_pelapor(halaman_kerja, terbitkan):
    """
    Identitas yang tertinggal dari nomor sebelumnya berarti keluhan orang
    ini tersimpan atas nama orang lain.
    """
    terbitkan("A", 2)
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()
    halaman_kerja.pelapor.isian_nama.setText("Budi Santoso")

    halaman_kerja.mulai_melayani()
    halaman_kerja.selesaikan()
    halaman_kerja.panggil_berikutnya()

    assert halaman_kerja.pelapor.isian_nama.text() == ""


def test_data_pelapor_dimuat_kembali_dari_lembar_tersimpan(
    halaman_kerja, terbitkan, qtbot
):
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.pelapor.isian_nama.setText("Budi Santoso")
    halaman_kerja.pelapor.isian_nomor_pelanggan.setText("1234567")

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_deskripsi.setPlainText("Air mati tiga hari.")
    dialog.simpan()

    # Paksa panel membaca ulang seolah nomornya baru saja dipanggil lagi.
    halaman_kerja.pelapor.kosongkan()
    halaman_kerja._lembar_nomor = None
    halaman_kerja._perbarui_baris_kerja()

    assert halaman_kerja.pelapor.isian_nama.text() == "Budi Santoso"
    assert halaman_kerja.pelapor.isian_nama.property("wajib") is None


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


def test_identitas_ditandai_wajib_hanya_setelah_ada_pengaduan(
    halaman_kerja, terbitkan
):
    """
    Kewajibannya bersyarat. Peringatan yang menyala pada lembar yang hanya
    berisi catatan petugas akan cepat berhenti dibaca.
    """
    _panggil(halaman_kerja, terbitkan)
    pelapor = halaman_kerja.pelapor

    assert pelapor.isian_nama.property("wajib") is None
    assert "*" not in pelapor.label_nama.text()

    pelapor.tandai_wajib(True)

    assert pelapor.isian_nama.property("wajib") == "true"
    assert pelapor.label_nama.text().endswith("*")
    assert "Nama" in pelapor.label_petunjuk.text()

    pelapor.isian_nama.setText("Budi")
    pelapor.isian_nomor_pelanggan.setText("1234567")
    pelapor.tandai_wajib(True)

    assert pelapor.isian_nama.property("wajib") is None
    assert "Wajib diisi" not in pelapor.label_petunjuk.text()


def test_dialog_menyebut_identitas_yang_belum_diisi(halaman_kerja, terbitkan, qtbot):
    """
    Isiannya berada di layar yang sedang tertutup dialog ini; petugas tidak
    dapat melihat sendiri apa yang belum terisi.
    """
    _panggil(halaman_kerja, terbitkan)

    dialog = _buka(halaman_kerja, qtbot)
    dialog.isian_deskripsi.setPlainText("Air mati tiga hari.")

    assert "Nama" in dialog.label_pelapor.text()
    assert "No. Pelanggan" in dialog.label_pelapor.text()

    halaman_kerja.pelapor.isian_nama.setText("Budi")
    halaman_kerja.pelapor.isian_nomor_pelanggan.setText("1234567")
    dialog._perbarui_dinamis()

    assert dialog.label_pelapor.text() == "Budi · 1234567"


def test_tombol_simpan_mati_selama_belum_ada_isi(halaman_kerja, terbitkan, qtbot):
    terbitkan("A")
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()

    dialog = _buka(halaman_kerja, qtbot)
    assert not dialog.tombol_simpan.isEnabled()

    # Identitas saja bukan isi: tidak ada keluhan maupun catatan di sana.
    halaman_kerja.pelapor.isian_nama.setText("Budi")
    dialog._perbarui_dinamis()
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

    halaman_kerja.pelapor.isian_nama.setText("Budi")
    halaman_kerja.pelapor.isian_nomor_pelanggan.setText("1234567")
    dialog = _buka(halaman_kerja, qtbot)
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
