"""
Pengaduan dan catatan petugas.

Test di berkas ini mengunci aturan yang menjaga satu-satunya tempat data
pribadi di aplikasi ini. Yang paling penting bukan bahwa lembarnya
tersimpan, melainkan bahwa isinya TIDAK bocor ke audit log dan bahwa
penulisnya tidak dapat menghapus tulisannya sendiri.
"""

from __future__ import annotations

import pytest

from app.core.errors import (
    AuthorizationError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def note(auth, antrian_siap):
    """NoteService dengan sesi CRO, yang berhak menulis maupun membaca."""
    from app.services.note_service import NoteService

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    return NoteService(auth)


@pytest.fixture
def antrian(terbitkan):
    """Satu nomor antrian yang siap ditulisi lembarnya."""
    return terbitkan("A")[0]


# ---------------------------------------------------------------------
# Penyimpanan
# ---------------------------------------------------------------------

def test_catatan_petugas_boleh_berdiri_sendiri(note, antrian):
    """Tidak setiap pelayanan melahirkan pengaduan."""
    lembar = note.simpan(antrian.id, catatan="Berkas belum lengkap.")

    assert lembar.catatan == "Berkas belum lengkap."
    assert lembar.deskripsi is None
    assert not lembar.ada_pengaduan


def test_pengaduan_wajib_menyebut_nama_dan_nomor_pelanggan(note, antrian):
    """
    Pengaduan tanpa identitas tidak dapat ditindaklanjuti siapa pun.

    Aturan ini bersyarat — hanya berlaku begitu ada deskripsi — sehingga
    tidak dapat dinyatakan sebagai NOT NULL di tabelnya.
    """
    with pytest.raises(ValidationError):
        note.simpan(antrian.id, deskripsi="Air mati tiga hari.")

    with pytest.raises(ValidationError):
        note.simpan(antrian.id, deskripsi="Air mati tiga hari.", nama="Budi")

    lembar = note.simpan(
        antrian.id,
        deskripsi="Air mati tiga hari.",
        nama="Budi",
        nomor_pelanggan="1234567",
    )
    assert lembar.ada_pengaduan


def test_lembar_kosong_ditolak(note, antrian):
    with pytest.raises(ValidationError):
        note.simpan(antrian.id, nama="Budi", nomor_pelanggan="1234567")


def test_menyimpan_dua_kali_menyunting_lembar_yang_sama(note, antrian):
    """Satu antrian satu lembar — bukan tumpukan lembar yang bertentangan."""
    pertama = note.simpan(antrian.id, catatan="Catatan awal.")
    kedua = note.simpan(antrian.id, catatan="Catatan yang diperbaiki.")

    assert kedua.id == pertama.id
    assert note.ambil(antrian.id).catatan == "Catatan yang diperbaiki."


def test_email_dan_telepon_yang_jelas_keliru_ditolak(note, antrian):
    with pytest.raises(ValidationError):
        note.simpan(antrian.id, catatan="x", email="budi.example.com")
    with pytest.raises(ValidationError):
        note.simpan(antrian.id, catatan="x", telepon="0812")


def test_email_tidak_biasa_tetap_diterima(note, antrian):
    """
    Pemeriksaan sengaja longgar. Menolak alamat yang sebenarnya sah
    membuat petugas berhenti mengisinya sama sekali.
    """
    lembar = note.simpan(
        antrian.id, catatan="x", email="budi+tagihan@kantor-pelayanan.co.id"
    )
    assert lembar.email == "budi+tagihan@kantor-pelayanan.co.id"


def test_isian_terlalu_panjang_ditolak_dengan_pesan_indonesia(note, antrian):
    from app.services.note_service import PANJANG_DESKRIPSI

    with pytest.raises(ValidationError) as galat:
        note.simpan(
            antrian.id,
            nama="Budi",
            nomor_pelanggan="1234567",
            deskripsi="a" * (PANJANG_DESKRIPSI + 1),
        )
    assert "maksimum" in galat.value.user_message.lower()


def test_lembar_antrian_kemarin_tidak_dapat_diubah(note, antrian, monkeypatch):
    """
    Pengaduan yang masih bisa diubah berhari-hari kemudian tidak berguna
    sebagai bukti apa pun.
    """
    from datetime import timedelta

    from app.core import clock

    note.simpan(antrian.id, catatan="Ditulis hari ini.")

    besok = clock.today() + timedelta(days=1)
    monkeypatch.setattr(clock, "today", lambda: besok)

    with pytest.raises(BusinessRuleError):
        note.simpan(antrian.id, catatan="Disunting keesokan harinya.")


# ---------------------------------------------------------------------
# Data pribadi tidak boleh menyebar
# ---------------------------------------------------------------------

def test_isi_lembar_tidak_pernah_masuk_audit_log(note, antrian):
    """
    Audit log dibaca ADMIN dan ikut ke setiap berkas backup. Menyalin nama
    dan nomor telepon ke sana berarti menggandakan data pribadi ke tempat
    yang tidak pernah ditinjau siapa pun.
    """
    from app.services import audit_service

    note.simpan(
        antrian.id,
        nama="Budi Santoso",
        nomor_pelanggan="1234567",
        telepon="081234567890",
        email="budi@contoh.id",
        alamat="Jalan Melati Nomor 7",
        deskripsi="Air mati tiga hari berturut-turut.",
        catatan="Sudah dijelaskan jadwal perbaikannya.",
    )

    jejak = audit_service.list_terakhir(batas=50)
    catatan_audit = [e for e in jejak if e.action == "SAVE_NOTE"]
    assert catatan_audit, "penyimpanan lembar wajib tercatat"

    seluruh_teks = " ".join(str(e.meta) for e in jejak)
    for rahasia in (
        "Budi Santoso",
        "1234567",
        "081234567890",
        "budi@contoh.id",
        "Jalan Melati",
        "Air mati tiga hari",
        "jadwal perbaikannya",
    ):
        assert rahasia not in seluruh_teks


# ---------------------------------------------------------------------
# Hak akses
# ---------------------------------------------------------------------

def test_petugas_pendaftaran_tidak_boleh_menulis_lembar(auth, antrian_siap, antrian):
    from app.services.note_service import NoteService

    auth.logout()
    auth.login("registration", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        NoteService(auth).simpan(antrian.id, catatan="x")


def test_supervisor_membaca_tetapi_tidak_menulis(auth, antrian_siap, antrian, note):
    from app.services.note_service import NoteService

    note.simpan(antrian.id, catatan="Catatan petugas.")

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    supervisor = NoteService(auth)

    assert supervisor.ambil(antrian.id).catatan == "Catatan petugas."
    with pytest.raises(AuthorizationError):
        supervisor.simpan(antrian.id, catatan="Disunting supervisor.")


def test_penulis_tidak_boleh_menghapus_tulisannya_sendiri(note, antrian):
    """
    Penulis yang sekaligus dapat menghilangkan tulisannya membuat catatan
    itu tidak berguna sebagai bukti apa pun.
    """
    lembar = note.simpan(antrian.id, catatan="Catatan petugas.")

    with pytest.raises(AuthorizationError):
        note.hapus(lembar.id)


def test_admin_menghapus_dan_tercatat_di_audit(auth, antrian, note):
    from app.services import audit_service
    from app.services.note_service import NoteService

    lembar = note.simpan(antrian.id, catatan="Catatan petugas.")

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    NoteService(auth).hapus(lembar.id)

    assert NoteService(auth).ambil(antrian.id) is None
    aksi = [e.action for e in audit_service.list_terakhir(batas=20)]
    assert "DELETE_NOTE" in aksi


def test_menghapus_lembar_yang_tidak_ada_ditolak_dengan_jelas(auth, antrian_siap):
    from app.services.note_service import NoteService

    auth.logout()
    auth.login("admin", TEST_PASSWORD)

    with pytest.raises(NotFoundError):
        NoteService(auth).hapus(9999)


def test_anjungan_kios_tidak_dapat_membaca_lembar(auth, antrian_siap, antrian, note):
    """
    Anjungan berdiri di ruang publik tanpa diawasi. Ia tidak boleh membaca
    satu pun lembar, dan itu ditegakkan di service — bukan hanya lewat
    GRANT PostgreSQL yang tidak berlaku pada pemasangan SQLite.
    """
    from app.services.note_service import NoteService

    note.simpan(antrian.id, catatan="Catatan petugas.")

    auth.logout()
    auth.mulai_sesi_kios()

    with pytest.raises(AuthorizationError):
        NoteService(auth).ambil(antrian.id)


# ---------------------------------------------------------------------
# Pencarian
# ---------------------------------------------------------------------

def test_pencarian_menemukan_lewat_nama_nomor_pelanggan_dan_isi(note, terbitkan):
    satu, dua = terbitkan("A", 2)
    note.simpan(
        satu.id,
        nama="Budi Santoso",
        nomor_pelanggan="1234567",
        deskripsi="Air mati tiga hari.",
    )
    note.simpan(
        dua.id,
        nama="Siti Aminah",
        nomor_pelanggan="7654321",
        deskripsi="Tagihan tidak sesuai.",
    )

    assert [n.queue_number for n in note.cari("budi")] == [satu.queue_number]
    assert [n.queue_number for n in note.cari("7654321")] == [dua.queue_number]
    assert [n.queue_number for n in note.cari("tagihan")] == [dua.queue_number]
    assert [n.queue_number for n in note.cari(satu.queue_number)] == [
        satu.queue_number
    ]


def test_pencarian_tidak_membedakan_huruf_besar_kecil(note, antrian):
    note.simpan(
        antrian.id,
        nama="Budi Santoso",
        nomor_pelanggan="1234567",
        deskripsi="Air mati.",
    )
    assert len(note.cari("BUDI SANTOSO")) == 1


def test_hanya_pengaduan_menyaring_catatan_petugas(note, terbitkan):
    satu, dua = terbitkan("A", 2)
    note.simpan(satu.id, catatan="Hanya catatan petugas.")
    note.simpan(
        dua.id,
        nama="Budi",
        nomor_pelanggan="1234567",
        deskripsi="Air mati.",
    )

    seluruhnya = note.cari()
    pengaduan = note.cari(hanya_pengaduan=True)

    assert len(seluruhnya) == 2
    assert [n.queue_number for n in pengaduan] == [dua.queue_number]


def test_pencarian_dibatasi_rentang_tanggal(note, antrian):
    from datetime import timedelta

    from app.core import clock

    note.simpan(antrian.id, catatan="Catatan hari ini.")
    kemarin = clock.today() - timedelta(days=1)

    assert note.cari(dari=clock.today()) != []
    assert note.cari(sampai=kemarin) == []
