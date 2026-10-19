"""Catatan petugas wajib untuk menyelesaikan pelayanan, beserta jalur adminnya."""

from __future__ import annotations

import pytest

from app.core.errors import AuthorizationError, BusinessRuleError, ValidationError
from app.models import QueueStatus
from app.services.note_service import (
    FRASA_BAWAAN,
    FRASA_MAKS,
    PANJANG_FRASA,
    NoteService,
    catatan_memadai,
    daftar_frasa,
)
from app.services.queue_service import QueueService
from tests.conftest import TEST_PASSWORD
from tests.test_queue_service import _buat_target_pengalihan


@pytest.mark.parametrize(
    ("catatan", "memadai"),
    [
        (None, False),
        ("", False),
        ("-", False),
        ("ok", False),
        ("Sudah.", False),
        ("1234567890 12345", False),
        ("aaaaaaaaaaaaaaaa", False),
        ("abababababababab", False),
        ("Berkas belum lengkap.", True),
        ("Tanya informasi", True),
        ("  Pelanggan menanyakan tagihan.  ", True),
    ],
)
def test_aturan_catatan_memadai(catatan, memadai):
    assert catatan_memadai(catatan) is memadai


def test_daftar_frasa_rapi_dan_dibatasi():
    teks = "  Berkas   diterima.  \n\nBerkas diterima.\n" + "\n".join(
        f"Kalimat {chr(97 + i) * 3}" for i in range(12)
    )
    daftar = daftar_frasa(teks)
    assert daftar[0] == "Berkas diterima."
    assert len(daftar) == FRASA_MAKS
    assert daftar_frasa(None) == [] and daftar_frasa("  \n ") == []
    assert len(daftar_frasa("x" * 500)[0]) <= 200


def _layani(cro_queue, terbitkan, antrian_siap):
    terbitkan("A")
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    return cro_queue.start_service(antrian.id)


def test_complete_wajib_catatan_menolak_tanpa_lembar(
    auth, cro_queue, terbitkan, antrian_siap
):
    antrian = _layani(cro_queue, terbitkan, antrian_siap)

    with pytest.raises(BusinessRuleError, match="catatan petugas"):
        cro_queue.complete(antrian.id, wajib_catatan=True)

    assert cro_queue.get_queue(antrian.id).status is QueueStatus.SERVING


def test_complete_wajib_catatan_menolak_pengaduan_tanpa_catatan(
    auth, cro_queue, terbitkan, antrian_siap
):
    antrian = _layani(cro_queue, terbitkan, antrian_siap)
    NoteService(auth).simpan(
        antrian.id,
        nama="Budi",
        nomor_pelanggan="123456",
        deskripsi="Air mati tiga hari.",
    )

    with pytest.raises(BusinessRuleError):
        cro_queue.complete(antrian.id, wajib_catatan=True)


def test_complete_wajib_catatan_menolak_catatan_asal(
    auth, cro_queue, terbitkan, antrian_siap
):
    antrian = _layani(cro_queue, terbitkan, antrian_siap)
    NoteService(auth).simpan(antrian.id, catatan="ok")

    with pytest.raises(BusinessRuleError):
        cro_queue.complete(antrian.id, wajib_catatan=True)


def test_complete_wajib_catatan_lolos_dengan_catatan_memadai(
    auth, cro_queue, terbitkan, antrian_siap
):
    antrian = _layani(cro_queue, terbitkan, antrian_siap)
    NoteService(auth).simpan(antrian.id, catatan="Pelanggan menanyakan tagihan.")

    hasil = cro_queue.complete(antrian.id, wajib_catatan=True)

    assert hasil.status is QueueStatus.COMPLETED


def test_complete_tanpa_syarat_tetap_bisa_untuk_pemanggil_lain(
    cro_queue, terbitkan, antrian_siap
):
    antrian = _layani(cro_queue, terbitkan, antrian_siap)
    assert cro_queue.complete(antrian.id).status is QueueStatus.COMPLETED


def test_admin_menyelesaikan_paksa_pelayanan_tertinggal(
    cro_queue, terbitkan, antrian_siap
):
    antrian = _layani(cro_queue, terbitkan, antrian_siap)
    admin, _ = _buat_target_pengalihan(antrian_siap["loket"][1])

    hasil = QueueService(admin).selesaikan_paksa(
        antrian.id, "Petugas pulang sebelum menutup"
    )

    assert hasil.status is QueueStatus.COMPLETED
    assert hasil.completed_at is not None
    assert QueueService(admin).list_pelayanan_aktif() == []


def test_admin_menyelesaikan_paksa_pelayanan_ditunda(
    cro_queue, terbitkan, antrian_siap
):
    antrian = _layani(cro_queue, terbitkan, antrian_siap)
    cro_queue.pause(antrian.id)
    admin, _ = _buat_target_pengalihan(antrian_siap["loket"][1])

    hasil = QueueService(admin).selesaikan_paksa(antrian.id, "Berkas sudah lengkap")

    assert hasil.status is QueueStatus.COMPLETED


def test_selesaikan_paksa_menolak_nomor_yang_belum_dilayani(
    cro_queue, terbitkan, antrian_siap
):
    terbitkan("A")
    dipanggil = cro_queue.call_next(antrian_siap["loket"][0])
    admin, _ = _buat_target_pengalihan(antrian_siap["loket"][1])

    with pytest.raises(BusinessRuleError):
        QueueService(admin).selesaikan_paksa(dipanggil.id, "Alasan apa pun")


def test_selesaikan_paksa_wajib_alasan_dan_hak_admin(
    cro_queue, terbitkan, antrian_siap
):
    antrian = _layani(cro_queue, terbitkan, antrian_siap)
    admin, _ = _buat_target_pengalihan(antrian_siap["loket"][1])

    with pytest.raises(ValidationError):
        QueueService(admin).selesaikan_paksa(antrian.id, "   ")
    with pytest.raises(AuthorizationError):
        cro_queue.selesaikan_paksa(antrian.id, "Mencoba sendiri")


def test_frasa_cepat_bawaan_dan_milik_layanan(
    auth, master_service, antrian_siap, cro_queue
):
    kategori = antrian_siap["kategori"]["A"]

    def baca(id_kategori) -> list[str]:
        # Kalimat cepat dibaca petugas; pengaturannya oleh admin.
        auth.logout()
        auth.login("cro", TEST_PASSWORD)
        hasil = NoteService(auth).frasa_cepat(id_kategori)
        auth.logout()
        auth.login("admin", TEST_PASSWORD)
        return hasil

    assert baca(kategori) == list(FRASA_BAWAAN)
    assert baca(None) == list(FRASA_BAWAAN)

    master_service.update_category(
        kategori, name="Layanan A", frasa_catatan="Berkas diterima.\nBerkas ditolak."
    )
    assert baca(kategori) == ["Berkas diterima.", "Berkas ditolak."]

    # Mengubah nama tanpa menyebut kalimat cepat tidak boleh menghapusnya.
    master_service.update_category(kategori, name="Layanan A baru")
    assert baca(kategori) == ["Berkas diterima.", "Berkas ditolak."]

    # Dikosongkan sengaja: kembali ke daftar bawaan.
    master_service.update_category(kategori, name="Layanan A", frasa_catatan="")
    assert baca(kategori) == list(FRASA_BAWAAN)


def test_periksa_frasa_menolak_terlalu_panjang_atau_banyak():
    from app.services.note_service import periksa_frasa

    periksa_frasa(None)
    periksa_frasa("Berkas diterima.\nBerkas ditolak.")
    periksa_frasa("x" * PANJANG_FRASA)
    with pytest.raises(ValidationError, match="maksimal"):
        periksa_frasa("x" * (PANJANG_FRASA + 1))
    with pytest.raises(ValidationError, match="paling banyak"):
        periksa_frasa("\n".join(f"Kalimat nomor {i}" for i in range(FRASA_MAKS + 1)))


def test_master_menolak_kalimat_cepat_terlalu_panjang(
    master_service, antrian_siap
):
    kategori = antrian_siap["kategori"]["A"]
    with pytest.raises(ValidationError):
        master_service.update_category(
            kategori, name="Layanan A", frasa_catatan="y" * (PANJANG_FRASA + 1)
        )
    with pytest.raises(ValidationError):
        master_service.create_category(
            code="ZZ", name="Baru", prefix="Z", frasa_catatan="y" * (PANJANG_FRASA + 1)
        )


def test_catatan_sama_dengan_mengabaikan_spasi_dan_huruf_besar():
    from app.services.note_service import catatan_sama_dengan

    sebelumnya = ["Berkas belum lengkap.", "Tanya tagihan bulan ini"]
    assert catatan_sama_dengan("  BERKAS  belum lengkap. ", sebelumnya)
    assert not catatan_sama_dengan("Berkas belum lengkap, kembali besok.", sebelumnya)
    assert not catatan_sama_dengan("", sebelumnya)
    assert not catatan_sama_dengan("Berkas belum lengkap.", [])


def test_catatan_terakhir_saya_hanya_milik_petugas_dan_hari_ini(
    auth, cro_queue, terbitkan, antrian_siap
):
    catatan = NoteService(auth)
    nomor = []
    for isi in ("Catatan satu lengkap.", "Catatan dua lengkap."):
        terbitkan("A")
        antrian = cro_queue.call_next(antrian_siap["loket"][0])
        cro_queue.start_service(antrian.id)
        catatan.simpan(antrian.id, catatan=isi)
        cro_queue.complete(antrian.id)
        nomor.append(antrian.id)

    # Terbaru lebih dulu; nomor yang sedang dikerjakan dikecualikan.
    assert catatan.catatan_terakhir_saya() == ["Catatan dua lengkap.", "Catatan satu lengkap."]
    assert catatan.catatan_terakhir_saya(kecuali_queue_id=nomor[1]) == ["Catatan satu lengkap."]
