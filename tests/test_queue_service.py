"""Test alur pelayanan antrian dan penegakan perpindahan status."""

from __future__ import annotations

import pytest

from app.core.errors import (
    AuthorizationError,
    BusinessRuleError,
    NotFoundError,
)
from app.models import QueueStatus
from app.services.queue_service import (
    LABEL_STATUS,
    TRANSISI_SAH,
    QueueService,
    transisi_sah,
)
from tests.conftest import TEST_PASSWORD


# ---------------------------------------------------------------------
# Tabel transisi
# ---------------------------------------------------------------------

def test_setiap_status_punya_definisi_transisi():
    """Status tanpa definisi akan diam-diam menolak segalanya."""
    assert set(TRANSISI_SAH) == set(QueueStatus)


def test_setiap_status_punya_label_indonesia():
    assert set(LABEL_STATUS) == set(QueueStatus)


@pytest.mark.parametrize(
    ("dari", "ke"),
    [
        (QueueStatus.WAITING, QueueStatus.CALLED),
        (QueueStatus.CALLED, QueueStatus.SERVING),
        (QueueStatus.SERVING, QueueStatus.COMPLETED),
        (QueueStatus.CALLED, QueueStatus.NO_SHOW),
        (QueueStatus.WAITING, QueueStatus.CANCELLED),
        (QueueStatus.CALLED, QueueStatus.CANCELLED),
        (QueueStatus.SERVING, QueueStatus.PAUSED),
        (QueueStatus.PAUSED, QueueStatus.SERVING),
    ],
)
def test_transisi_yang_diizinkan_spesifikasi(dari, ke):
    assert transisi_sah(dari, ke)


@pytest.mark.parametrize(
    ("dari", "ke"),
    [
        # Tidak boleh melompati pemanggilan.
        (QueueStatus.WAITING, QueueStatus.SERVING),
        (QueueStatus.WAITING, QueueStatus.COMPLETED),
        (QueueStatus.WAITING, QueueStatus.NO_SHOW),
        # Tidak boleh selesai tanpa dilayani.
        (QueueStatus.CALLED, QueueStatus.COMPLETED),
        # Status akhir tidak punya jalan keluar.
        (QueueStatus.COMPLETED, QueueStatus.SERVING),
        (QueueStatus.COMPLETED, QueueStatus.WAITING),
        (QueueStatus.CANCELLED, QueueStatus.WAITING),
        (QueueStatus.NO_SHOW, QueueStatus.CALLED),
        (QueueStatus.NO_SHOW, QueueStatus.SERVING),
    ],
)
def test_transisi_yang_harus_ditolak(dari, ke):
    assert not transisi_sah(dari, ke)


def test_status_akhir_tidak_punya_kelanjutan():
    for status in (QueueStatus.COMPLETED, QueueStatus.CANCELLED, QueueStatus.NO_SHOW):
        assert TRANSISI_SAH[status] == frozenset()
        assert status.is_final


# ---------------------------------------------------------------------
# Alur normal
# ---------------------------------------------------------------------

def test_alur_lengkap_dari_menunggu_sampai_selesai(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]

    dipanggil = cro_queue.call_next(loket)
    assert dipanggil.status is QueueStatus.CALLED
    assert dipanggil.queue_number == "A-001"
    assert dipanggil.counter_name == "Loket 1"
    assert dipanggil.called_at is not None

    dilayani = cro_queue.start_service(dipanggil.id)
    assert dilayani.status is QueueStatus.SERVING
    assert dilayani.serving_at is not None
    assert dilayani.served_by_name == "Petugas Cro"

    selesai = cro_queue.complete(dilayani.id)
    assert selesai.status is QueueStatus.COMPLETED
    assert selesai.completed_at is not None
    assert selesai.menunggu_detik is not None
    assert selesai.layanan_detik is not None


def test_panggil_mengambil_yang_paling_lama_menunggu(cro_queue, terbitkan, antrian_siap):
    """Urutannya siapa datang lebih dulu, lintas jenis layanan."""
    terbitkan("A", 1)
    terbitkan("B", 1)
    terbitkan("A", 1)

    loket = antrian_siap["loket"]
    assert cro_queue.call_next(loket[0]).queue_number == "A-001"
    assert cro_queue.call_next(loket[1]).queue_number == "B-001"
    assert cro_queue.call_next(loket[2]).queue_number == "A-002"


def test_panggil_dapat_dibatasi_pada_satu_jenis_layanan(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    terbitkan("B", 1)

    dipanggil = cro_queue.call_next(
        antrian_siap["loket"][0], category_id=antrian_siap["kategori"]["B"]
    )
    assert dipanggil.queue_number == "B-001"


def test_tidak_ada_antrian_ditolak_dengan_pesan_jelas(cro_queue, antrian_siap):
    with pytest.raises(BusinessRuleError) as gagal:
        cro_queue.call_next(antrian_siap["loket"][0])

    assert "Tidak ada antrian" in gagal.value.user_message


# ---------------------------------------------------------------------
# Panggil ulang
# ---------------------------------------------------------------------

def test_panggil_ulang_menambah_riwayat_tanpa_mengubah_status(
    cro_queue, terbitkan, antrian_siap
):
    """
    Riwayat pemanggilan tidak pernah ditimpa, sehingga terlihat berapa kali
    pengunjung dipanggil sebelum dinyatakan tidak hadir.
    """
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    assert antrian.jumlah_panggilan == 1

    for harapan in (2, 3):
        antrian = cro_queue.recall(antrian.id)
        assert antrian.jumlah_panggilan == harapan
        assert antrian.status is QueueStatus.CALLED

    assert len(cro_queue.call_history(antrian.id)) == 3


def test_panggil_ulang_hanya_untuk_yang_sudah_dipanggil(cro_queue, terbitkan, antrian_siap):
    nomor = terbitkan("A", 1)[0]

    with pytest.raises(BusinessRuleError):
        cro_queue.recall(nomor.id)  # masih WAITING


def test_panggil_ulang_setelah_dilayani_ditolak(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    antrian = cro_queue.start_service(antrian.id)

    with pytest.raises(BusinessRuleError):
        cro_queue.recall(antrian.id)


# ---------------------------------------------------------------------
# Tunda dan lanjutkan
# ---------------------------------------------------------------------

def test_tunda_lalu_lanjutkan(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    antrian = cro_queue.start_service(antrian.id)
    mulai = antrian.serving_at

    ditunda = cro_queue.pause(antrian.id)
    assert ditunda.status is QueueStatus.PAUSED

    dilanjut = cro_queue.resume(antrian.id)
    assert dilanjut.status is QueueStatus.SERVING
    assert dilanjut.serving_at == mulai, (
        "serving_at tidak boleh disetel ulang; lama penundaan akan hilang "
        "dari perhitungan waktu layanan"
    )


def test_tunda_hanya_saat_sedang_dilayani(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])

    with pytest.raises(BusinessRuleError):
        cro_queue.pause(antrian.id)


def test_antrian_tertunda_tidak_dapat_langsung_diselesaikan(
    cro_queue, terbitkan, antrian_siap
):
    """Petugas harus melanjutkan dulu; SERVING -> COMPLETED, bukan dari PAUSED."""
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    antrian = cro_queue.start_service(antrian.id)
    cro_queue.pause(antrian.id)

    with pytest.raises(BusinessRuleError):
        cro_queue.complete(antrian.id)

    cro_queue.resume(antrian.id)
    assert cro_queue.complete(antrian.id).status is QueueStatus.COMPLETED


# ---------------------------------------------------------------------
# Tidak hadir dan batal
# ---------------------------------------------------------------------

def test_tidak_hadir_setelah_dipanggil(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])

    hasil = cro_queue.no_show(antrian.id)
    assert hasil.status is QueueStatus.NO_SHOW
    assert hasil.completed_at is not None


def test_tidak_hadir_sebelum_dipanggil_ditolak(cro_queue, terbitkan):
    nomor = terbitkan("A", 1)[0]

    with pytest.raises(BusinessRuleError):
        cro_queue.no_show(nomor.id)


def test_batal_saat_menunggu(cro_queue, terbitkan):
    nomor = terbitkan("A", 1)[0]
    assert cro_queue.cancel(nomor.id).status is QueueStatus.CANCELLED


def test_batal_setelah_dipanggil(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    assert cro_queue.cancel(antrian.id).status is QueueStatus.CANCELLED


def test_batal_setelah_dilayani_ditolak(cro_queue, terbitkan, antrian_siap):
    """Pelayanan yang sudah berjalan diselesaikan, bukan dibatalkan."""
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    antrian = cro_queue.start_service(antrian.id)

    with pytest.raises(BusinessRuleError):
        cro_queue.cancel(antrian.id)


def test_antrian_selesai_tidak_dapat_diubah_lagi(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    antrian = cro_queue.start_service(antrian.id)
    cro_queue.complete(antrian.id)

    for tindakan in (cro_queue.complete, cro_queue.cancel, cro_queue.no_show, cro_queue.pause):
        with pytest.raises(BusinessRuleError):
            tindakan(antrian.id)


def test_pesan_penolakan_menyebut_status_saat_ini(cro_queue, terbitkan):
    """Petugas harus paham mengapa tombolnya menolak."""
    nomor = terbitkan("A", 1)[0]

    with pytest.raises(BusinessRuleError) as gagal:
        cro_queue.complete(nomor.id)

    pesan = gagal.value.user_message
    assert "A-001" in pesan
    assert "Menunggu" in pesan


# ---------------------------------------------------------------------
# Satu loket satu pengunjung
# ---------------------------------------------------------------------

def test_loket_tidak_boleh_memanggil_saat_masih_menangani(
    cro_queue, terbitkan, antrian_siap
):
    """
    Tanpa aturan ini, pengunjung yang sedang dilayani terlantar begitu saja
    ketika petugas menekan "Panggil Berikutnya".
    """
    terbitkan("A", 2)
    loket = antrian_siap["loket"][0]
    cro_queue.call_next(loket)

    with pytest.raises(BusinessRuleError) as gagal:
        cro_queue.call_next(loket)

    assert "A-001" in gagal.value.user_message


def test_loket_bebas_kembali_setelah_pelayanan_selesai(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 2)
    loket = antrian_siap["loket"][0]

    pertama = cro_queue.call_next(loket)
    cro_queue.start_service(pertama.id)
    cro_queue.complete(pertama.id)

    assert cro_queue.call_next(loket).queue_number == "A-002"


def test_loket_bebas_kembali_setelah_tidak_hadir(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 2)
    loket = antrian_siap["loket"][0]

    pertama = cro_queue.call_next(loket)
    cro_queue.no_show(pertama.id)

    assert cro_queue.call_next(loket).queue_number == "A-002"


def test_antrian_tertunda_masih_menahan_loket(cro_queue, terbitkan, antrian_siap):
    """Pengunjung yang ditunda belum selesai, jadi loket belum bebas."""
    terbitkan("A", 2)
    loket = antrian_siap["loket"][0]
    antrian = cro_queue.call_next(loket)
    cro_queue.start_service(antrian.id)
    cro_queue.pause(antrian.id)

    with pytest.raises(BusinessRuleError):
        cro_queue.call_next(loket)


def test_beberapa_loket_bekerja_bersamaan(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 3)
    loket = antrian_siap["loket"]

    a = cro_queue.call_next(loket[0])
    b = cro_queue.call_next(loket[1])
    c = cro_queue.call_next(loket[2])

    assert [a.queue_number, b.queue_number, c.queue_number] == ["A-001", "A-002", "A-003"]
    assert cro_queue.current_for_counter(loket[1]).queue_number == "A-002"


def test_loket_nonaktif_tidak_dapat_memanggil(cro_queue, terbitkan, antrian_siap, master_service, auth):
    loket = antrian_siap["loket"][0]
    terbitkan("A", 1)

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master_service.set_counter_status(loket, False)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(BusinessRuleError):
        QueueService(auth).call_next(loket)


# ---------------------------------------------------------------------
# Penerbitan nomor: aturan dan hak akses
# ---------------------------------------------------------------------

def test_jenis_layanan_nonaktif_tidak_menerbitkan_nomor(
    reg_queue, antrian_siap, master_service, auth
):
    kategori = antrian_siap["kategori"]["A"]

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    master_service.set_category_status(kategori, False)
    auth.logout()
    auth.login("registration", TEST_PASSWORD)

    with pytest.raises(BusinessRuleError) as gagal:
        QueueService(auth).create_queue(kategori)

    assert "tidak aktif" in gagal.value.user_message


def test_jenis_layanan_tidak_dikenal_ditolak(reg_queue):
    with pytest.raises(NotFoundError):
        reg_queue.create_queue(999999)


@pytest.mark.parametrize("peran", ["cro", "supervisor", "display"])
def test_selain_pendaftaran_tidak_dapat_menerbitkan_nomor(auth, antrian_siap, peran):
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        QueueService(auth).create_queue(antrian_siap["kategori"]["A"])


@pytest.mark.parametrize("peran", ["registration", "supervisor", "display"])
def test_selain_cro_tidak_dapat_memanggil(auth, antrian_siap, terbitkan, peran):
    terbitkan("A", 1)
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        QueueService(auth).call_next(antrian_siap["loket"][0])


def test_layar_antrian_tidak_dapat_melihat_daftar(auth, terbitkan):
    """Komputer display menghadap publik dan tidak diawasi."""
    terbitkan("A", 1)
    auth.logout()
    auth.login("display", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        QueueService(auth).list_waiting()


# ---------------------------------------------------------------------
# Pembacaan dan rekap
# ---------------------------------------------------------------------

def test_daftar_menunggu_terurut_kedatangan(cro_queue, terbitkan):
    terbitkan("A", 2)
    terbitkan("B", 1)

    assert [q.queue_number for q in cro_queue.list_waiting()] == ["A-001", "A-002", "B-001"]


def test_daftar_menunggu_menyusut_setelah_dipanggil(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 3)
    assert len(cro_queue.list_waiting()) == 3

    cro_queue.call_next(antrian_siap["loket"][0])
    assert [q.queue_number for q in cro_queue.list_waiting()] == ["A-002", "A-003"]


def test_rekap_hari_ini(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 5)
    loket = antrian_siap["loket"]

    selesai = cro_queue.call_next(loket[0])
    cro_queue.start_service(selesai.id)
    cro_queue.complete(selesai.id)

    tidak_hadir = cro_queue.call_next(loket[1])
    cro_queue.no_show(tidak_hadir.id)

    cro_queue.call_next(loket[2])

    rekap = cro_queue.counts_today()
    assert rekap[QueueStatus.WAITING] == 2
    assert rekap[QueueStatus.CALLED] == 1
    assert rekap[QueueStatus.COMPLETED] == 1
    assert rekap[QueueStatus.NO_SHOW] == 1


def test_loket_tanpa_antrian_mengembalikan_kosong(cro_queue, antrian_siap):
    assert cro_queue.current_for_counter(antrian_siap["loket"][0]) is None


# ---------------------------------------------------------------------
# Tindakan yang tersedia untuk UI
# ---------------------------------------------------------------------

def test_aksi_tersedia_mengikuti_status(cro_queue, terbitkan, antrian_siap):
    nomor = terbitkan("A", 1)[0]
    assert set(nomor.aksi_tersedia()) == {"panggil", "batal"}

    dipanggil = cro_queue.call_next(antrian_siap["loket"][0])
    assert set(dipanggil.aksi_tersedia()) == {
        "panggil_ulang", "mulai_layani", "tidak_hadir", "batal"
    }

    dilayani = cro_queue.start_service(dipanggil.id)
    assert set(dilayani.aksi_tersedia()) == {"selesai", "tunda"}

    ditunda = cro_queue.pause(dilayani.id)
    assert ditunda.aksi_tersedia() == ["lanjutkan"]

    cro_queue.resume(ditunda.id)
    assert cro_queue.complete(ditunda.id).aksi_tersedia() == []


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def test_seluruh_tindakan_tercatat_di_audit(cro_queue, terbitkan, antrian_siap):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    terbitkan("A", 2)
    loket = antrian_siap["loket"][0]

    antrian = cro_queue.call_next(loket)
    cro_queue.recall(antrian.id)
    cro_queue.start_service(antrian.id)
    cro_queue.pause(antrian.id)
    cro_queue.resume(antrian.id)
    cro_queue.complete(antrian.id)

    kedua = cro_queue.call_next(loket)
    cro_queue.no_show(kedua.id)

    with session_scope() as s:
        aksi = {r.action for r in s.scalars(sa.select(AuditLog))}

    assert {
        "CREATE_QUEUE",
        "CALL_QUEUE",
        "START_SERVICE",
        "PAUSE_QUEUE",
        "RESUME_QUEUE",
        "COMPLETE_QUEUE",
        "NO_SHOW",
    } <= aksi
