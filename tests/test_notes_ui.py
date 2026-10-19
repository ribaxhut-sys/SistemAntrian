"""
Ruang kerja petugas dan layar Pengaduan.

Ruang kerja pengaduan/catatan sekarang menyatu di panel kanan, bukan
dialog: satu QTabWidget berbagi tempat dengan Menunggu Dilayani, dan
berpindah tab sendiri mengikuti status loket. Yang diuji di sini adalah
perilaku yang tidak terlihat dari service — bahwa panel berpindah pada
saat yang tepat, bahwa isian ikut berpindah ketika antriannya berganti,
bahwa menutup pelayanan tidak menelan pengaduan yang gagal tersimpan, dan
bahwa tombol Hapus tidak pernah muncul di layar petugas.
"""

from __future__ import annotations

import pytest

from tests.conftest import TEST_PASSWORD


@pytest.fixture
def halaman_kerja(qtbot, auth, antrian_siap):
    """Panel pelayanan lengkap dengan panel kanannya, sebagai petugas CRO."""
    from app.services.master_data_service import MasterDataService
    from app.services.note_service import NoteService
    from app.services.queue_service import QueueService
    from app.services.settings_service import SettingsService
    from app.services.survey_service import SurveyService
    from app.ui.queue.service_page import ServicePage

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    auth.pindah_loket(antrian_siap["loket"][0])
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


#: Catatan yang cukup panjang dan beragam untuk menyelesaikan pelayanan.
CATATAN_SAH = "Pelanggan menanyakan informasi layanan."


def _panggil(halaman, terbitkan, prefix: str = "A"):
    """Terbitkan satu nomor lalu panggil ke loket halaman ini."""
    terbitkan(prefix)
    halaman.muat_ulang()
    halaman.panggil_berikutnya()


# ---------------------------------------------------------------------
# Panel kanan: Menunggu Dilayani <-> Pengaduan & Catatan
# ---------------------------------------------------------------------

def test_tab_menunggu_terlihat_selagi_loket_kosong(halaman_kerja):
    """Loket kosong berarti petugas sedang memilih siapa berikutnya."""
    assert halaman_kerja.tab_kanan.currentWidget() is halaman_kerja.panel_menunggu


def test_berpindah_ke_pengaduan_otomatis_saat_dipanggil(halaman_kerja, terbitkan):
    """Nomor dipanggil berarti petugas mulai berbicara dengan orangnya."""
    _panggil(halaman_kerja, terbitkan)
    assert halaman_kerja.tab_kanan.currentWidget() is halaman_kerja.panel_pengaduan


def test_kembali_ke_menunggu_otomatis_saat_selesai(halaman_kerja, terbitkan):
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.mulai_melayani()
    halaman_kerja.panel_pengaduan.isian_catatan.setPlainText(CATATAN_SAH)
    halaman_kerja.selesaikan()

    assert halaman_kerja.tab_kanan.currentWidget() is halaman_kerja.panel_menunggu


def test_tab_manual_tidak_dipaksa_kembali_oleh_penyegaran(halaman_kerja, terbitkan):
    """
    Memanggil ulang (F3) tidak mengganti antrian yang dipegang loket, jadi
    tidak boleh menyeret petugas keluar dari tab yang sengaja ia buka
    sendiri untuk melirik daftar tunggu sambil tetap melayani.
    """
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.tab_kanan.setCurrentWidget(halaman_kerja.panel_menunggu)

    halaman_kerja.panggil_ulang()

    assert halaman_kerja.tab_kanan.currentWidget() is halaman_kerja.panel_menunggu


def test_f9_berpindah_tab_dan_fokus_ke_kotak(halaman_kerja, terbitkan):
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.tab_kanan.setCurrentWidget(halaman_kerja.panel_menunggu)

    halaman_kerja.buka_ruang_kerja()

    assert halaman_kerja.tab_kanan.currentWidget() is halaman_kerja.panel_pengaduan


def test_judul_tab_menunggu_menyebut_jumlah_dan_yang_lama(halaman_kerja):
    from app.ui.queue.service_page import TUNGGU_LAMA_MENIT

    halaman_kerja._perbarui_judul_tab_menunggu(5, [3, TUNGGU_LAMA_MENIT, 25])

    assert halaman_kerja.tab_kanan.tabText(1) == "Menunggu Dilayani (5) · 2 lama"


def test_judul_tab_tanpa_keterangan_lama_bila_tidak_ada(halaman_kerja):
    halaman_kerja._perbarui_judul_tab_menunggu(3, [1, 2, 5])
    assert halaman_kerja.tab_kanan.tabText(1) == "Menunggu Dilayani (3)"


# ---------------------------------------------------------------------
# Panel Pengaduan & Catatan
# ---------------------------------------------------------------------

def test_panel_pelayanan_tidak_menampilkan_label_penjelas_berulang(
    halaman_kerja,
):
    from PySide6.QtWidgets import QLabel

    teks = {label.text() for label in halaman_kerja.findChildren(QLabel)}

    assert "F2 panggil · F3 ulangi · F4 mulai · F8 selesai" not in teks
    assert "ALUR PELAYANAN" not in teks
    assert "BILA PENGUNJUNG TIDAK DATANG" not in teks
    assert "Kata pengunjung" not in teks
    assert "Tidak dibacakan ke pengunjung" not in teks
    assert not any("Jangan menyalin NIK" in isi for isi in teks)


def test_panel_pengaduan_mati_tanpa_antrian(halaman_kerja):
    """Dinonaktifkan, bukan disembunyikan — sama seperti tombol tindakan."""
    panel = halaman_kerja.panel_pengaduan

    assert panel is not None
    assert not panel.isEnabled()
    assert not halaman_kerja.pelapor.isian_nama.isEnabled()
    assert not halaman_kerja.pelapor.tombol_tempel.isEnabled()


def test_panel_pengaduan_hidup_setelah_memanggil(halaman_kerja, terbitkan):
    _panggil(halaman_kerja, terbitkan)

    panel = halaman_kerja.panel_pengaduan
    assert panel.isEnabled()
    assert halaman_kerja.pelapor.isian_nama.isEnabled()
    assert halaman_kerja.pelapor.tombol_tempel.isEnabled()


def test_isian_pelapor_tidak_saling_menimpa(halaman_kerja, terbitkan, qtbot):
    """
    Formulir tujuh isian pernah diperas di kolom kiri sampai label dan
    isian saling menimpa. Setelah dipecah — identitas di layar, kotak
    keluhan di panel kanan — test ini yang menjaga sisa di layarnya
    tetap muat.
    """
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.show()
    qtbot.waitExposed(halaman_kerja)

    pelapor = halaman_kerja.pelapor
    # Tata letak dua baris: nama, no. pelanggan, telepon di atas; email dan
    # alamat di bawah. Yang dijaga: baris atas tidak menimpa baris bawah.
    kotak = (
        pelapor.isian_nama,
        pelapor.isian_nomor_pelanggan,
        pelapor.isian_telepon,
        pelapor.isian_email,
        pelapor.isian_alamat,
    )
    pasangan = [(a, b) for a in kotak[:3] for b in kotak[3:]]
    for atas, bawah in pasangan:
        sisi_atas = atas.mapTo(pelapor, atas.rect().bottomLeft()).y()
        sisi_bawah = bawah.mapTo(pelapor, bawah.rect().topLeft()).y()
        assert sisi_atas <= sisi_bawah, "isian pelapor menimpa isian di bawahnya"

    for isian in kotak:
        assert isian.height() >= isian.fontMetrics().height()


def test_kotak_pengaduan_tidak_saling_menimpa(halaman_kerja, terbitkan, qtbot):
    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    halaman_kerja.tab_kanan.setCurrentWidget(panel)
    halaman_kerja.show()
    qtbot.waitExposed(halaman_kerja)

    atas, bawah = panel.isian_deskripsi, panel.isian_catatan
    assert (
        atas.mapTo(panel, atas.rect().bottomLeft()).y()
        <= bawah.mapTo(panel, bawah.rect().topLeft()).y()
    )
    for kotak in (atas, bawah):
        assert kotak.height() >= kotak.fontMetrics().height()


def test_identitas_ada_di_layar_bukan_di_panel_kanan(halaman_kerja, terbitkan):
    """
    Identitas ditulis sambil bertanya kepada orang di depan meja; keluhan
    ditulis sambil mendengarkan. Dua kegiatan, dua tempat.
    """
    _panggil(halaman_kerja, terbitkan)

    assert not hasattr(halaman_kerja.panel_pengaduan, "isian_nama")
    assert halaman_kerja.pelapor.isian_nama.isEnabled()


def test_catatan_tersimpan_lewat_panel(halaman_kerja, terbitkan, auth):
    from app.services.note_service import NoteService

    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    panel.isian_catatan.setPlainText("Berkas belum lengkap.")

    assert panel.simpan()

    lembar = NoteService(auth).ambil(halaman_kerja.antrian.id)
    assert lembar.catatan == "Berkas belum lengkap."


def test_menyimpan_tidak_mengosongkan_isian(halaman_kerja, terbitkan):
    """
    Petugas sering menyimpan di tengah pembicaraan lalu meneruskan
    mengetik — isian yang lenyap begitu Simpan ditekan memaksanya
    mengetik ulang.
    """
    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    panel.isian_catatan.setPlainText("Catatan sementara.")
    panel.simpan()

    assert panel.isian_catatan.toPlainText() == "Catatan sementara."
    assert not panel.berubah


def test_lembar_yang_sudah_ada_dimuat_kembali(halaman_kerja, terbitkan):
    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    panel.isian_catatan.setPlainText("Sudah dijelaskan jadwalnya.")
    panel.simpan()

    # Paksa panel membaca ulang seolah nomornya baru saja dipanggil lagi.
    antrian = halaman_kerja.antrian
    panel.set_antrian(None)
    panel.set_antrian(antrian)

    assert panel.isian_catatan.toPlainText() == "Sudah dijelaskan jadwalnya."
    assert not panel.berubah


def test_pengaduan_tanpa_identitas_ditahan_sebelum_menyentuh_database(
    halaman_kerja, terbitkan, bisu
):
    """
    Ditahan di panel, bukan dibiarkan ditolak service: keluhan yang sudah
    tertulis tidak boleh ikut hilang bersama pesan gagalnya.
    """
    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    panel.isian_deskripsi.setPlainText("Air mati tiga hari.")

    assert not panel.simpan()
    assert not bisu, "tidak perlu kotak dialog; cukup keterangan di panelnya"
    assert "Lengkapi" in panel.label_keadaan.text()
    assert panel.isian_deskripsi.toPlainText() == "Air mati tiga hari."


def test_pengaduan_tersimpan_bersama_identitas_dari_layar(
    halaman_kerja, terbitkan, auth
):
    from app.services.note_service import NoteService

    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.pelapor.isian_nama.setText("Budi Santoso")
    halaman_kerja.pelapor.isian_nomor_pelanggan.setText("1234567")
    halaman_kerja.pelapor.isian_telepon.setText("081234567890")

    panel = halaman_kerja.panel_pengaduan
    panel.isian_deskripsi.setPlainText("Air mati tiga hari.")
    assert panel.simpan()

    lembar = NoteService(auth).ambil(halaman_kerja.antrian.id)
    assert lembar.nama == "Budi Santoso"
    assert lembar.nomor_pelanggan == "1234567"
    assert lembar.telepon == "081234567890"
    assert lembar.deskripsi == "Air mati tiga hari."


def test_berpindah_nomor_mengosongkan_data_pelapor_dan_isian(
    halaman_kerja, terbitkan
):
    """
    Identitas maupun keluhan yang tertinggal dari nomor sebelumnya berarti
    keluhan orang ini tersimpan atas nama orang lain.
    """
    terbitkan("A", 2)
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()
    halaman_kerja.pelapor.isian_nama.setText("Budi Santoso")
    halaman_kerja.panel_pengaduan.isian_catatan.setPlainText("Catatan pertama.")

    halaman_kerja.mulai_melayani()
    halaman_kerja.selesaikan()
    halaman_kerja.panggil_berikutnya()

    assert halaman_kerja.pelapor.isian_nama.text() == ""
    assert halaman_kerja.panel_pengaduan.isian_catatan.toPlainText() == ""


def test_kapsul_mengikuti_isi_lembar(halaman_kerja, terbitkan):
    """Petugas tahu lembar ini menjadi apa tanpa membuka apa pun."""
    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    assert panel.kapsul.text() == "KOSONG"

    panel.isian_catatan.setPlainText("Berkas belum lengkap.")
    assert panel.kapsul.text() == "CATATAN"

    panel.isian_deskripsi.setPlainText("Air mati tiga hari.")
    assert panel.kapsul.text() == "PENGADUAN"


def test_identitas_ditandai_wajib_hanya_setelah_ada_pengaduan(
    halaman_kerja, terbitkan
):
    """
    Kewajibannya bersyarat. Peringatan yang menyala pada lembar yang hanya
    berisi catatan petugas akan cepat berhenti dibaca.
    """
    _panggil(halaman_kerja, terbitkan)
    pelapor = halaman_kerja.pelapor
    panel = halaman_kerja.panel_pengaduan

    assert pelapor.isian_nama.property("wajib") is None
    assert "*" not in pelapor.label_nama.text()

    panel.isian_deskripsi.setPlainText("Air mati tiga hari.")

    assert pelapor.isian_nama.property("wajib") == "true"
    assert pelapor.label_nama.text().endswith("*")
    assert "Nama" in pelapor.label_petunjuk.text()

    pelapor.isian_nama.setText("Budi")
    pelapor.isian_nomor_pelanggan.setText("1234567")

    assert pelapor.isian_nama.property("wajib") is None
    assert "Wajib diisi" not in pelapor.label_petunjuk.text()


def test_data_pelapor_dimuat_kembali_dari_lembar_tersimpan(halaman_kerja, terbitkan):
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.pelapor.isian_nama.setText("Budi Santoso")
    halaman_kerja.pelapor.isian_nomor_pelanggan.setText("1234567")

    panel = halaman_kerja.panel_pengaduan
    panel.isian_deskripsi.setPlainText("Air mati tiga hari.")
    panel.simpan()

    # Paksa panel membaca ulang seolah nomornya baru saja dipanggil lagi.
    halaman_kerja.pelapor.kosongkan()
    antrian = halaman_kerja.antrian
    panel.set_antrian(None)
    panel.set_antrian(antrian)

    assert halaman_kerja.pelapor.isian_nama.text() == "Budi Santoso"
    assert halaman_kerja.pelapor.isian_nama.property("wajib") is None


def test_tombol_selesai_menyala_hanya_bila_catatan_memadai(halaman_kerja, terbitkan):
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.mulai_melayani()
    panel = halaman_kerja.panel_pengaduan
    assert halaman_kerja.aksi["selesai"] is panel.tombol_selesai
    assert not panel.tombol_selesai.isEnabled()

    # Identitas saja bukan isi: tidak ada keluhan maupun catatan di sana.
    halaman_kerja.pelapor.isian_nama.setText("Budi")
    assert not panel.tombol_selesai.isEnabled()

    # Pengaduan tanpa catatan petugas tetap belum cukup.
    panel.isian_deskripsi.setPlainText("Air mati tiga hari.")
    assert not panel.tombol_selesai.isEnabled()

    for kurang in ("-", "ok", "Berkas.", "aaaaaaaaaaaaaaa", "1234567890 -- 12"):
        panel.isian_catatan.setPlainText(kurang)
        assert not panel.tombol_selesai.isEnabled(), kurang

    panel.isian_catatan.setPlainText("Berkas belum lengkap.")
    assert panel.tombol_selesai.isEnabled()


def test_tombol_selesai_mati_bila_belum_dilayani_walau_catatan_ada(
    halaman_kerja, terbitkan
):
    """Dua syarat: nomor sedang dilayani DAN catatan memadai."""
    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    panel.isian_catatan.setPlainText(CATATAN_SAH)
    assert not panel.tombol_selesai.isEnabled()  # baru dipanggil

    halaman_kerja.mulai_melayani()
    assert panel.tombol_selesai.isEnabled()

    halaman_kerja.tunda()
    assert not panel.tombol_selesai.isEnabled()


def test_f8_tanpa_catatan_tidak_menyelesaikan_dan_memfokuskan_kotak(
    halaman_kerja, terbitkan
):
    from app.models import QueueStatus

    _panggil(halaman_kerja, terbitkan)
    antrian_id = halaman_kerja.antrian.id
    halaman_kerja.mulai_melayani()
    halaman_kerja.tab_kanan.setCurrentWidget(halaman_kerja.panel_menunggu)

    halaman_kerja.selesaikan()

    assert halaman_kerja.queue.get_queue(antrian_id).status is QueueStatus.SERVING
    assert halaman_kerja.tab_kanan.currentWidget() is halaman_kerja.panel_pengaduan
    assert "catatan" in halaman_kerja.panel_pengaduan.label_keadaan.text().lower()


def test_kalimat_cepat_menyisipkan_ke_catatan(halaman_kerja, terbitkan):
    from app.services.note_service import FRASA_BAWAAN

    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    assert len(panel._tombol_frasa) == len(FRASA_BAWAAN)

    panel._tombol_frasa[0].click()
    assert panel.isian_catatan.toPlainText() == FRASA_BAWAAN[0]
    panel._tombol_frasa[1].click()
    assert panel.isian_catatan.toPlainText() == f"{FRASA_BAWAAN[0]}\n{FRASA_BAWAAN[1]}"

    halaman_kerja.mulai_melayani()
    assert panel.tombol_selesai.isEnabled()  # kalimat cepat dihitung sebagai catatan


def test_kalimat_cepat_mengikuti_jenis_layanan(halaman_kerja, terbitkan, auth, antrian_siap):
    from app.services.master_data_service import MasterDataService

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    MasterDataService(auth).update_category(
        antrian_siap["kategori"]["A"],
        name="Layanan A",
        frasa_catatan="Berkas diterima.\nBerkas dikembalikan.\nBerkas diterima.",
    )
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    auth.pindah_loket(antrian_siap["loket"][0])

    _panggil(halaman_kerja, terbitkan)
    teks = [btn.toolTip() for btn in halaman_kerja.panel_pengaduan._tombol_frasa]
    assert teks == ["Berkas diterima.", "Berkas dikembalikan."]


def test_simpan_otomatis_menyimpan_draf_tanpa_dialog(halaman_kerja, terbitkan, bisu, auth):
    from app.services.note_service import NoteService

    _panggil(halaman_kerja, terbitkan)
    antrian_id = halaman_kerja.antrian.id
    panel = halaman_kerja.panel_pengaduan
    panel.isian_catatan.setPlainText("Draf catatan yang belum rampung")

    panel.simpan_otomatis()

    assert not bisu
    assert NoteService(auth).ambil(antrian_id).catatan == "Draf catatan yang belum rampung"
    assert not panel.berubah


def test_simpan_otomatis_menunggu_identitas_pengaduan(halaman_kerja, terbitkan, bisu, auth):
    from app.services.note_service import NoteService

    _panggil(halaman_kerja, terbitkan)
    antrian_id = halaman_kerja.antrian.id
    panel = halaman_kerja.panel_pengaduan
    panel.isian_deskripsi.setPlainText("Air mati tiga hari.")

    panel.simpan_otomatis()  # nama dan nomor pelanggan belum ada

    assert not bisu
    assert NoteService(auth).ambil(antrian_id) is None


def test_penghitung_huruf_memperingatkan_sebelum_batas(halaman_kerja, terbitkan):
    """
    Petugas yang baru tahu batasnya ketika penolakan muncul harus memotong
    kalimat orang lain sambil orangnya menunggu.
    """
    from app.services.note_service import PANJANG_CATATAN
    from app.ui.style import TEXT_MUTED

    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    panel.isian_catatan.setPlainText("abc")
    assert "Minimal 10 huruf (3/10)" in panel.hitung_catatan.text()
    assert TEXT_MUTED not in panel.hitung_catatan.styleSheet()

    panel.isian_catatan.setPlainText("Berkas belum lengkap.")
    assert panel.hitung_catatan.text() == f"21 / {PANJANG_CATATAN}"
    assert TEXT_MUTED in panel.hitung_catatan.styleSheet()

    panel.isian_catatan.setPlainText(("abc " * PANJANG_CATATAN)[: PANJANG_CATATAN - 1])
    assert TEXT_MUTED not in panel.hitung_catatan.styleSheet()


def test_keadaan_menyebut_perubahan_yang_belum_disimpan(halaman_kerja, terbitkan):
    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    assert "Belum pernah disimpan" in panel.label_keadaan.text()

    panel.isian_catatan.setPlainText("Belum sempat disimpan.")
    assert "belum disimpan" in panel.label_keadaan.text()

    panel.simpan()
    assert "Tersimpan" in panel.label_keadaan.text()


def test_selesai_menyimpan_otomatis_sebelum_menutup(halaman_kerja, terbitkan, auth):
    """F8 menutup pelayanan; catatannya tidak boleh ikut hilang bersamanya."""
    from app.models import QueueStatus
    from app.services.note_service import NoteService

    _panggil(halaman_kerja, terbitkan)
    antrian_id = halaman_kerja.antrian.id
    halaman_kerja.panel_pengaduan.isian_catatan.setPlainText("Selesai dilayani.")

    halaman_kerja.mulai_melayani()
    halaman_kerja.selesaikan()

    lembar = NoteService(auth).ambil(antrian_id)
    assert lembar is not None
    assert lembar.catatan == "Selesai dilayani."
    assert halaman_kerja.queue.get_queue(antrian_id).status is QueueStatus.COMPLETED


def test_pengaduan_tanpa_nama_membatalkan_penyelesaian(halaman_kerja, terbitkan, bisu):
    """
    Antrian TIDAK boleh tertutup ketika pengaduannya gagal disimpan.
    Kartu berganti kosong begitu selesai, dan yang menceritakan keluhannya
    sudah berdiri meninggalkan meja.
    """
    from app.models import QueueStatus

    _panggil(halaman_kerja, terbitkan)
    antrian_id = halaman_kerja.antrian.id
    halaman_kerja.panel_pengaduan.isian_deskripsi.setPlainText("Air mati tiga hari.")
    halaman_kerja.panel_pengaduan.isian_catatan.setPlainText(CATATAN_SAH)

    halaman_kerja.mulai_melayani()
    halaman_kerja.selesaikan()

    assert not bisu, "tidak perlu kotak dialog; cukup keterangan di panelnya"
    assert halaman_kerja.queue.get_queue(antrian_id).status is not QueueStatus.COMPLETED
    assert halaman_kerja.panel_pengaduan.isian_deskripsi.toPlainText() == (
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


def test_layar_pengaduan_tanpa_pengantar_privasi_berulang(
    qtbot, auth, lembar_terisi
):
    from PySide6.QtWidgets import QLabel

    halaman = _halaman_pengaduan(qtbot, auth)
    teks = {label.text() for label in halaman.findChildren(QLabel)}

    assert not any("Berisi data pribadi pelapor" in isi for isi in teks)


def test_pencarian_menyaring_daftar(qtbot, auth, lembar_terisi):
    halaman = _halaman_pengaduan(qtbot, auth)

    halaman.isian_cari.setText("budi")
    halaman.muat_ulang()

    assert halaman.tabel.rowCount() == 1
    assert halaman.terpilih.nama == "Budi Santoso"


def test_hanya_pengaduan_menyembunyikan_catatan_petugas(qtbot, auth, lembar_terisi):
    halaman = _halaman_pengaduan(qtbot, auth)

    halaman.centang_pengaduan.setChecked(True)

    qtbot.waitUntil(lambda: halaman.tabel.rowCount() == 1, timeout=5000)
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


# ---------------------------------------------------------------------
# Penyegaran otomatis
# ---------------------------------------------------------------------

def test_penyegaran_otomatis_menemukan_lembar_baru(qtbot, auth, antrian_siap, terbitkan):
    """Petugas lain terus menulis lembar baru sepanjang hari."""
    from app.services.note_service import NoteService

    satu = terbitkan("A")[0]
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    halaman = _halaman_pengaduan(qtbot, auth)
    assert halaman.tabel.rowCount() == 0

    NoteService(auth).simpan(satu.id, catatan="Ditulis setelah layar dibuka.")
    halaman._segarkan_otomatis()

    assert halaman.tabel.rowCount() == 1


def test_penyegaran_otomatis_tidak_memakai_ketikan_belum_disubmit(
    qtbot, auth, lembar_terisi
):
    """
    Pencarian sengaja hanya berjalan saat Enter/Cari ditekan. Penyegaran
    diam-diam yang membaca kotak pencarian secara langsung akan mendahului
    petugas yang belum selesai mengetik kata kuncinya.
    """
    halaman = _halaman_pengaduan(qtbot, auth)
    sebelum = halaman.tabel.rowCount()

    # Diketik, TIDAK ditekan Enter maupun tombol Cari.
    halaman.isian_cari.setText("kata yang tidak akan pernah cocok")
    halaman._segarkan_otomatis()

    assert halaman.tabel.rowCount() == sebelum


def test_penyegaran_otomatis_mempertahankan_baris_terpilih(
    qtbot, auth, antrian_siap, terbitkan
):
    """
    Baris yang sedang dibaca petugas tidak boleh melompat ke baris lain
    hanya karena penyegaran berkala kebetulan berbunyi.
    """
    from app.services.note_service import NoteService

    satu, dua = terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    note = NoteService(auth)
    note.simpan(satu.id, catatan="Lembar pertama.")
    note.simpan(dua.id, catatan="Lembar kedua.")

    halaman = _halaman_pengaduan(qtbot, auth)
    halaman.tabel.selectRow(1)
    dipilih = halaman.terpilih.id

    halaman._segarkan_otomatis()

    assert halaman.terpilih.id == dipilih


def test_f5_tetap_memakai_ketikan_saat_ini(qtbot, auth, lembar_terisi):
    """
    `muat_ulang()` — dipanggil F5 maupun tombol Cari — tetap membaca kotak
    pencarian secara langsung. Hanya penyegaran BERKALA yang menahan diri.
    """
    halaman = _halaman_pengaduan(qtbot, auth)

    halaman.isian_cari.setText("budi")
    halaman.muat_ulang()

    assert halaman.tabel.rowCount() == 1
    assert halaman.terpilih.nama == "Budi Santoso"


# ---------------------------------------------------------------------
# Urutan tab, pemicu mulai-layani, dan penanda isian belum disimpan
# ---------------------------------------------------------------------

def test_tab_pengaduan_selalu_di_awal(halaman_kerja):
    tab = halaman_kerja.tab_kanan
    assert tab.widget(0) is halaman_kerja.panel_pengaduan
    assert tab.tabText(0).startswith("Pengaduan && Catatan")


def test_mulai_melayani_membuka_pengaduan_walau_tab_lain_dibuka(
    halaman_kerja, terbitkan
):
    _panggil(halaman_kerja, terbitkan)
    halaman_kerja.tab_kanan.setCurrentWidget(halaman_kerja.panel_menunggu)

    halaman_kerja.mulai_melayani()

    assert halaman_kerja.tab_kanan.currentWidget() is halaman_kerja.panel_pengaduan


def test_judul_pengaduan_bertanda_bila_ada_isian_belum_disimpan(
    halaman_kerja, terbitkan
):
    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    assert halaman_kerja.tab_kanan.tabText(0) == "Pengaduan && Catatan"

    panel.isian_catatan.setPlainText("ditulis tetapi belum disimpan")

    assert halaman_kerja.tab_kanan.tabText(0).endswith("●")


# ---------------------------------------------------------------------
# Kalimat cepat tidak terpotong, tidak diulang, dan catatan tidak disalin
# ---------------------------------------------------------------------


def test_kalimat_cepat_yang_sudah_dipakai_dimatikan(halaman_kerja, terbitkan):
    from app.services.note_service import FRASA_BAWAAN

    _panggil(halaman_kerja, terbitkan)
    panel = halaman_kerja.panel_pengaduan
    pertama, kedua = panel._tombol_frasa[0], panel._tombol_frasa[1]

    pertama.click()
    assert not pertama.isEnabled() and pertama.terpakai
    assert pertama.label.text().startswith("✓ ")
    assert pertama.toolTip() == "Sudah ada di catatan"
    assert kedua.isEnabled()

    # Klik pada tombol mati tidak menambah apa pun.
    pertama.click()
    assert panel.isian_catatan.toPlainText() == FRASA_BAWAAN[0]

    # Dihapus dari catatan: tombolnya hidup lagi.
    panel.isian_catatan.setPlainText("")
    assert pertama.isEnabled() and not pertama.terpakai
    assert pertama.label.text() == FRASA_BAWAAN[0]


def test_kalimat_cepat_panjang_tampil_utuh_membungkus(qtbot):
    """
    Tombol sendiri, bukan seluruh layar pelayanan: menampilkan ServicePage
    di test menghentikan proses Qt tanpa pesan di mesin ini.
    """
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from app.services.note_service import PANJANG_FRASA
    from app.ui.tombol_frasa import TombolFrasa

    panjang = "Pelanggan menanyakan persyaratan pengajuan sambungan baru beserta biayanya"
    assert len(panjang) <= PANJANG_FRASA
    wadah = QWidget()
    tata = QVBoxLayout(wadah)
    tombol = TombolFrasa(panjang)
    tata.addWidget(tombol)
    qtbot.addWidget(wadah)
    wadah.resize(260, 300)
    wadah.show()
    qtbot.wait(30)

    assert tombol.label.text() == panjang  # tanpa elipsis
    assert tombol.label.wordWrap()
    butuh = tombol.label.heightForWidth(tombol.label.width())
    assert tombol.label.height() >= butuh, "tinggi label kurang: teks terpotong"
    assert tombol.height() >= butuh
    # Sempit memang lebih tinggi daripada lebar: teks membungkus, bukan terpotong.
    assert butuh > tombol.label.fontMetrics().height() * 1.5


def test_peringatan_catatan_sama_dengan_nomor_sebelumnya(
    halaman_kerja, terbitkan, auth
):
    from app.ui.queue.note_panel import PESAN_CATATAN_SAMA

    terbitkan("A", 2)
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()
    halaman_kerja.mulai_melayani()
    halaman_kerja.panel_pengaduan.isian_catatan.setPlainText(
        "Berkas belum lengkap, diminta kembali besok."
    )
    halaman_kerja.selesaikan()

    halaman_kerja.panggil_berikutnya()
    panel = halaman_kerja.panel_pengaduan
    assert not panel.catatan_sama_dengan_sebelumnya

    # Persis sama (huruf besar-kecil dan spasi tidak dihitung): diperingatkan.
    panel.isian_catatan.setPlainText("  berkas BELUM lengkap,  diminta kembali besok. ")
    assert panel.catatan_sama_dengan_sebelumnya
    assert PESAN_CATATAN_SAMA in panel.label_keadaan.text()

    # Disesuaikan sedikit: tidak lagi diperingatkan.
    panel.isian_catatan.setPlainText("Berkas belum lengkap, diminta kembali Senin.")
    assert not panel.catatan_sama_dengan_sebelumnya
    assert PESAN_CATATAN_SAMA not in panel.label_keadaan.text()


def test_peringatan_tidak_berlaku_untuk_kalimat_cepat(halaman_kerja, terbitkan):
    terbitkan("A", 2)
    halaman_kerja.muat_ulang()
    halaman_kerja.panggil_berikutnya()
    halaman_kerja.mulai_melayani()
    halaman_kerja.panel_pengaduan._tombol_frasa[0].click()
    halaman_kerja.selesaikan()

    halaman_kerja.panggil_berikutnya()
    panel = halaman_kerja.panel_pengaduan
    panel._tombol_frasa[0].click()  # kalimat cepat yang sama untuk pelayanan yang sama

    assert panel.isian_catatan.toPlainText() == panel._tombol_frasa[0].kalimat
    assert not panel.catatan_sama_dengan_sebelumnya


def test_detak_simpan_otomatis_diam_bila_jendela_tidak_tampil(
    halaman_kerja, terbitkan, auth
):
    """
    Panel yang sudah ditutup tidak boleh menulis ke database sesudahnya:
    detak 15 detiknya dulu menulis catatan basi ke data tes berikutnya.
    """
    from app.services.note_service import NoteService

    _panggil(halaman_kerja, terbitkan)
    antrian_id = halaman_kerja.antrian.id
    panel = halaman_kerja.panel_pengaduan
    panel.isian_catatan.setPlainText("Catatan yang belum tersimpan sama sekali")
    assert not panel.window().isVisible()

    panel._saat_pewaktu_otomatis()

    assert NoteService(auth).ambil(antrian_id) is None


# ---------------------------------------------------------------------
# Pekerja latar layar pelayanan
# ---------------------------------------------------------------------


def test_pekerja_lama_selesai_tidak_membuang_pekerja_baru(halaman_kerja):
    """
    `finished` pekerja lama bisa tiba sesudah penyegaran berikutnya mulai.
    Dulu handlernya menghapus `_pekerja_data` yang kini dipegang, sehingga
    Qt mematikan proses: "QThread: Destroyed while thread is still running".
    """
    from app.ui.common import PekerjaLatar

    lama = PekerjaLatar(lambda: None, halaman_kerja)
    baru = PekerjaLatar(lambda: None, halaman_kerja)
    halaman_kerja._pekerja_data = baru
    halaman_kerja._bersihkan_pekerja_data(lama)
    assert halaman_kerja._pekerja_data is baru

    halaman_kerja._bersihkan_pekerja_data(baru)
    assert halaman_kerja._pekerja_data is None

    lama_aksi = PekerjaLatar(lambda: None, halaman_kerja)
    baru_aksi = PekerjaLatar(lambda: None, halaman_kerja)
    halaman_kerja._pekerja_aksi = baru_aksi
    halaman_kerja._bersihkan_pekerja_aksi(lama_aksi)
    assert halaman_kerja._pekerja_aksi is baru_aksi

    halaman_kerja._bersihkan_pekerja_aksi(baru_aksi)
    assert halaman_kerja._pekerja_aksi is None


def test_layar_pelayanan_tampil_lalu_memanggil_nomor_tanpa_mematikan_proses(
    qtbot, halaman_kerja, terbitkan
):
    """Regresi: tampil + panggil nomor + beberapa detak event loop mematikan Qt."""
    from PySide6.QtWidgets import QApplication

    halaman_kerja.resize(1100, 800)
    halaman_kerja.show()
    QApplication.processEvents()
    _panggil(halaman_kerja, terbitkan)
    for _ in range(20):
        qtbot.wait(10)

    assert halaman_kerja.antrian is not None
