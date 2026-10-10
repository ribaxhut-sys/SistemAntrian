"""Test alur pelayanan antrian dan penegakan perpindahan status."""

from __future__ import annotations

import pytest

from app.core.errors import (
    AuthorizationError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
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


# ---------------------------------------------------------------------
# Batas pemanggilan
# ---------------------------------------------------------------------

def _panggil_berulang(cro_queue, antrian_siap, terbitkan, kali: int):
    """Panggil satu nomor lalu ulangi pemanggilannya beberapa kali."""
    terbitkan("A")
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    for _ in range(kali - 1):
        antrian = cro_queue.recall(antrian.id)
    return antrian


def test_batas_panggilan_diambil_dari_pengaturan(cro_queue):
    assert cro_queue.batas_panggilan() == 3


def test_belum_melewati_batas_saat_baru_dipanggil(
    antrian_siap, cro_queue, terbitkan
):
    antrian = _panggil_berulang(cro_queue, antrian_siap, terbitkan, 1)

    assert antrian.jumlah_panggilan == 1
    assert not antrian.melewati_batas_panggilan


def test_melewati_batas_setelah_dipanggil_sebanyak_batasnya(
    antrian_siap, cro_queue, terbitkan
):
    antrian = _panggil_berulang(cro_queue, antrian_siap, terbitkan, 3)

    assert antrian.jumlah_panggilan == 3
    assert antrian.melewati_batas_panggilan


def test_panggil_ulang_tetap_diizinkan_setelah_melewati_batas(
    antrian_siap, cro_queue, terbitkan
):
    """
    Batas hanya mengingatkan, tidak menghalangi.

    Pengunjung yang lambat sampai ke loket tidak boleh kehilangan nomornya
    hanya karena hitungan, sebab nomor yang sudah terbit tidak dapat
    diterbitkan ulang.
    """
    antrian = _panggil_berulang(cro_queue, antrian_siap, terbitkan, 3)

    lagi = cro_queue.recall(antrian.id)

    assert lagi.jumlah_panggilan == 4
    assert lagi.status is QueueStatus.CALLED


def test_batas_tidak_berlaku_setelah_mulai_dilayani(
    antrian_siap, cro_queue, terbitkan
):
    """Pengunjung sudah di depan meja; hitungan panggilan tidak relevan lagi."""
    antrian = _panggil_berulang(cro_queue, antrian_siap, terbitkan, 3)

    dilayani = cro_queue.start_service(antrian.id)

    assert not dilayani.melewati_batas_panggilan


# ---------------------------------------------------------------------
# Istirahat loket
# ---------------------------------------------------------------------

def test_set_istirahat_menandai_loket_istirahat(cro_queue, antrian_siap, auth):
    loket = antrian_siap["loket"][0]
    cro_queue.set_istirahat(loket, True)

    auth.logout()
    auth.login("display", TEST_PASSWORD)
    state = QueueService(auth).display_state()
    entri = next(b for b in state.loket if b.counter_id == loket)
    assert entri.istirahat is True


def test_set_istirahat_loket_tidak_dapat_memanggil(cro_queue, terbitkan, antrian_siap):
    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]
    cro_queue.set_istirahat(loket, True)

    with pytest.raises(BusinessRuleError) as gagal:
        cro_queue.call_next(loket)

    assert "istirahat" in gagal.value.user_message


def test_set_istirahat_kembali_bertugas_dapat_memanggil_lagi(
    cro_queue, terbitkan, antrian_siap
):
    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]

    cro_queue.set_istirahat(loket, True)
    cro_queue.set_istirahat(loket, False)

    assert cro_queue.call_next(loket).queue_number == "A-001"


def test_set_istirahat_tidak_mengganggu_antrian_yang_sedang_ditangani(
    cro_queue, terbitkan, antrian_siap
):
    """Loket boleh ditandai istirahat setelah menerima antrian; yang sedang
    ditangani tidak ikut terbatalkan atau berubah."""
    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]
    antrian = cro_queue.call_next(loket)

    cro_queue.set_istirahat(loket, True)

    assert cro_queue.current_for_counter(loket).id == antrian.id


@pytest.mark.parametrize("peran", ["registration", "supervisor", "display"])
def test_selain_cro_tidak_dapat_mengubah_istirahat(auth, antrian_siap, peran):
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        QueueService(auth).set_istirahat(antrian_siap["loket"][0], True)


# ---------------------------------------------------------------------
# Tutup hari dan buka kembali
# ---------------------------------------------------------------------

def test_ringkasan_tutup_hari_menghitung_yang_belum_selesai(
    cro_queue, terbitkan, antrian_siap, auth
):
    terbitkan("A", 3)
    loket = antrian_siap["loket"]

    dipanggil = cro_queue.call_next(loket[0])
    cro_queue.start_service(dipanggil.id)
    cro_queue.call_next(loket[1])
    # Nomor ketiga tetap WAITING.

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    ringkasan = QueueService(auth).ringkasan_tutup_hari()

    assert ringkasan[QueueStatus.WAITING] == 1
    assert ringkasan[QueueStatus.CALLED] == 1
    assert ringkasan[QueueStatus.SERVING] == 1


def test_tutup_hari_membatalkan_yang_belum_selesai(
    cro_queue, terbitkan, antrian_siap, auth
):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import Queue

    terbitkan("A", 2)
    loket = antrian_siap["loket"]
    cro_queue.call_next(loket[0])
    # Nomor kedua tetap WAITING.

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    jumlah = QueueService(auth).tutup_hari()

    assert jumlah == 2
    with session_scope() as s:
        statuses = {q.status for q in s.scalars(sa.select(Queue))}
    assert statuses == {QueueStatus.CANCELLED}


def test_tutup_hari_tidak_menyentuh_yang_sudah_selesai(
    cro_queue, terbitkan, antrian_siap, auth
):
    terbitkan("A", 2)
    loket = antrian_siap["loket"]
    selesai = cro_queue.call_next(loket[0])
    cro_queue.start_service(selesai.id)
    cro_queue.complete(selesai.id)
    # Nomor kedua tetap WAITING dan seharusnya dibatalkan.

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    admin_queue = QueueService(auth)
    jumlah = admin_queue.tutup_hari()

    assert jumlah == 1

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    rekap = QueueService(auth).counts_today()
    assert rekap[QueueStatus.COMPLETED] == 1


def test_tutup_hari_hanya_untuk_admin(cro_queue, terbitkan, antrian_siap, auth):
    terbitkan("A", 1)

    with pytest.raises(AuthorizationError):
        cro_queue.tutup_hari()


def test_buka_kembali_hari_mengembalikan_ke_menunggu(
    cro_queue, terbitkan, antrian_siap, auth
):
    terbitkan("A", 1)
    loket = antrian_siap["loket"]
    dipanggil = cro_queue.call_next(loket[0])

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    admin_queue = QueueService(auth)
    admin_queue.tutup_hari()

    jumlah = admin_queue.buka_kembali_hari()
    assert jumlah == 1

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    kembali = QueueService(auth).list_waiting()
    assert [q.id for q in kembali] == [dipanggil.id]
    assert kembali[0].status is QueueStatus.WAITING


def test_ringkasan_buka_kembali_hari_nol_tanpa_tutup_hari(antrian_siap, auth):
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    admin_queue = QueueService(auth)

    assert admin_queue.ringkasan_buka_kembali_hari() == 0
    assert admin_queue.buka_kembali_hari() == 0


def test_tutup_hari_dan_buka_kembali_tercatat_di_audit(
    cro_queue, terbitkan, antrian_siap, auth
):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    terbitkan("A", 1)

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    admin_queue = QueueService(auth)
    admin_queue.tutup_hari()
    admin_queue.buka_kembali_hari()

    with session_scope() as s:
        aksi = {r.action for r in s.scalars(sa.select(AuditLog))}

    assert {"CLOSE_DAY", "REOPEN_DAY"} <= aksi


def test_batas_mengikuti_pengaturan_yang_diubah(
    antrian_siap, cro_queue, terbitkan, auth
):
    """Administrator mengubahnya saat aplikasi berjalan, tanpa buka ulang."""
    from app.services.settings_service import SettingsService

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("queue.max_call_attempts", "2")

    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    antrian = _panggil_berulang(cro_queue, antrian_siap, terbitkan, 2)

    assert cro_queue.batas_panggilan() == 2
    assert antrian.melewati_batas_panggilan



# ---------------------------------------------------------------------
# Nomor hangus saat tanggal berganti
# ---------------------------------------------------------------------

def _terbitkan_pada(antrian_siap, hari, prefix: str = "A"):
    """Terbitkan satu nomor pada tanggal tertentu, langsung lewat repository."""
    from app.repositories.queue_repository import terbitkan_nomor

    return terbitkan_nomor(
        branch_id=antrian_siap["branch_id"],
        category_id=antrian_siap["kategori"][prefix],
        prefix=prefix,
        tanggal=hari,
    )


def _kemarin():
    from datetime import timedelta

    from app.core import clock

    return clock.today() - timedelta(days=1)


def _status(queue_id: int):
    from app.core.database import session_scope
    from app.models import Queue

    with session_scope() as s:
        antrian = s.get(Queue, queue_id)
        return antrian.status, antrian.completed_at


def test_nomor_hari_lalu_hangus(antrian_siap, auth):
    """
    Pergantian hari mengakhiri antrian, tanpa menunggu ada yang menekan
    tombol Tutup Hari.
    """
    kemarin = _kemarin()
    sisa = _terbitkan_pada(antrian_siap, kemarin)

    jumlah = QueueService(auth).hanguskan_hari_lalu()

    status, selesai_pada = _status(sisa.queue_id)
    assert jumlah == 1
    assert status is QueueStatus.CANCELLED
    # Hangus pada tanggalnya sendiri, bukan pada saat sapuannya berjalan:
    # `rata_rata_durasi` menghitung dari kolom ini.
    assert selesai_pada.date() == kemarin


def test_nomor_hari_ini_tidak_ikut_hangus(antrian_siap, terbitkan, auth):
    """Mesin tidak pernah tahu kapan loket sungguh berhenti bekerja."""
    hari_ini = terbitkan("A", 1)[0]

    jumlah = QueueService(auth).hanguskan_hari_lalu()

    status, _ = _status(hari_ini.id)
    assert jumlah == 0
    assert status is QueueStatus.WAITING


def test_nomor_hari_lalu_yang_sudah_selesai_tidak_tersentuh(antrian_siap, auth):
    """Riwayat pelayanan yang sungguh terjadi tidak boleh ikut berubah."""
    from app.core.database import session_scope
    from app.models import Queue

    kemarin = _kemarin()
    selesai = _terbitkan_pada(antrian_siap, kemarin)
    with session_scope() as s:
        s.get(Queue, selesai.queue_id).status = QueueStatus.COMPLETED

    jumlah = QueueService(auth).hanguskan_hari_lalu()

    status, _ = _status(selesai.queue_id)
    assert jumlah == 0
    assert status is QueueStatus.COMPLETED


def test_hangus_tidak_menuntut_login(antrian_siap, auth):
    """
    Sapuan berjalan saat aplikasi mulai, sebelum ada yang masuk.

    Menuntut hak akses berarti sapuan ini tidak pernah berjalan sama
    sekali di komputer anjungan, yang memang tidak pernah login.
    """
    _terbitkan_pada(antrian_siap, _kemarin())
    auth.logout()

    assert QueueService(auth).hanguskan_hari_lalu() == 1


def test_sapuan_kedua_tidak_mencatat_audit_lagi(antrian_siap, auth):
    """
    Lima komputer loket menyala berbarengan menyapu daftar yang sama.

    Hanya yang pertama benar-benar mengubah baris; sisanya tidak boleh
    meninggalkan audit untuk pekerjaan yang tidak mereka lakukan.
    """
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditAction, AuditLog

    _terbitkan_pada(antrian_siap, _kemarin())
    antrian = QueueService(auth)

    assert antrian.hanguskan_hari_lalu() == 1
    assert antrian.hanguskan_hari_lalu() == 0

    with session_scope() as s:
        jumlah = s.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.EXPIRE_QUEUE.value)
        )
    assert jumlah == 1


def test_hangus_tidak_dapat_dipulihkan_buka_kembali_hari(antrian_siap, auth):
    """
    "Buka Kembali" ada untuk tombol Tutup Hari yang tertekan tidak sengaja.

    Sapuan otomatis tidak pernah tertekan tidak sengaja, dan mengembalikan
    nomor kemarin menjadi menunggu hari ini tidak pernah benar.
    """
    sisa = _terbitkan_pada(antrian_siap, _kemarin())
    QueueService(auth).hanguskan_hari_lalu()

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    admin_queue = QueueService(auth)

    assert admin_queue.ringkasan_buka_kembali_hari() == 0
    assert admin_queue.buka_kembali_hari() == 0
    assert _status(sisa.queue_id)[0] is QueueStatus.CANCELLED


# ---------------------------------------------------------------------
# Jenis layanan yang dilayani sebuah loket
# ---------------------------------------------------------------------

def _batasi_loket(auth, loket_id: int, kategori_ids: list[int]) -> None:
    """Tetapkan jenis layanan sebuah loket sebagai admin, lalu kembali ke CRO."""
    from app.services.master_data_service import MasterDataService

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    MasterDataService(auth).set_counter_categories(loket_id, kategori_ids)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)


def test_loket_khusus_hanya_memanggil_layanannya(auth, antrian_siap, terbitkan):
    terbitkan("A", 1)
    terbitkan("B", 1)
    loket = antrian_siap["loket"][0]
    _batasi_loket(auth, loket, [antrian_siap["kategori"]["B"]])

    assert QueueService(auth).call_next(loket).queue_number == "B-001"


def test_loket_khusus_melewati_antrian_yang_bukan_bagiannya(
    auth, antrian_siap, terbitkan
):
    """A-001 datang lebih dulu, tetapi bukan bagian loket ini."""
    terbitkan("A", 2)
    terbitkan("B", 1)
    loket = antrian_siap["loket"][0]
    _batasi_loket(auth, loket, [antrian_siap["kategori"]["B"]])

    assert QueueService(auth).call_next(loket).queue_number == "B-001"


def test_loket_tanpa_batasan_memanggil_semua_layanan(auth, antrian_siap, terbitkan):
    """Daftar kosong berarti semua, sehingga perilakunya seperti sebelumnya."""
    terbitkan("B", 1)
    loket = antrian_siap["loket"][0]
    _batasi_loket(auth, loket, [])

    assert QueueService(auth).call_next(loket).queue_number == "B-001"


def test_loket_khusus_boleh_melayani_beberapa_jenis(auth, antrian_siap, terbitkan):
    terbitkan("C", 1)
    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]
    _batasi_loket(
        auth, loket, [antrian_siap["kategori"]["A"], antrian_siap["kategori"]["C"]]
    )

    assert QueueService(auth).call_next(loket).queue_number == "C-001"


def test_pesan_membedakan_sepi_dari_bukan_bagian_loket_ini(
    auth, antrian_siap, terbitkan
):
    """
    Petugas melihat sepuluh orang menunggu di layar. Bila pesannya hanya
    "tidak ada antrian", dia akan menyimpulkan aplikasinya rusak.
    """
    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]
    _batasi_loket(auth, loket, [antrian_siap["kategori"]["B"]])

    with pytest.raises(BusinessRuleError) as gagal:
        QueueService(auth).call_next(loket)

    assert "loket lain" in gagal.value.user_message


def test_pesan_sepi_tetap_apa_adanya_saat_memang_kosong(auth, antrian_siap):
    loket = antrian_siap["loket"][0]
    _batasi_loket(auth, loket, [antrian_siap["kategori"]["B"]])

    with pytest.raises(BusinessRuleError) as gagal:
        QueueService(auth).call_next(loket)

    assert gagal.value.user_message == "Tidak ada antrian yang menunggu."


def test_saringan_petugas_di_luar_layanan_loket_ditolak(auth, antrian_siap, terbitkan):
    terbitkan("A", 1)
    loket = antrian_siap["loket"][0]
    _batasi_loket(auth, loket, [antrian_siap["kategori"]["B"]])

    with pytest.raises(BusinessRuleError) as gagal:
        QueueService(auth).call_next(loket, category_id=antrian_siap["kategori"]["A"])

    assert "tidak melayani" in gagal.value.user_message


def test_daftar_menunggu_tetap_utuh_walau_loket_dibatasi(auth, antrian_siap, terbitkan):
    """
    Batasan hanya berlaku saat memanggil.

    Petugas tetap perlu melihat keseluruhan antrian untuk tahu keadaan
    ruangan, dan supervisor membaca daftar yang sama.
    """
    terbitkan("A", 1)
    terbitkan("B", 1)
    loket = antrian_siap["loket"][0]
    _batasi_loket(auth, loket, [antrian_siap["kategori"]["B"]])

    assert len(QueueService(auth).list_waiting()) == 2


# ---------------------------------------------------------------------
# Loket bawaan petugas
# ---------------------------------------------------------------------

def test_sesi_membawa_loket_bawaan_petugas(auth, antrian_siap, users):
    """Layar pelayanan memakainya untuk memilih loket sendiri saat masuk."""
    from app.services.user_service import UserService

    loket = antrian_siap["loket"][1]
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    UserService(auth).update_user(
        users["CRO"], full_name="Petugas Cro", role="CRO", default_counter_id=loket
    )

    auth.logout()
    sesi = auth.login("cro", TEST_PASSWORD)

    assert sesi.default_counter_id == loket


def test_loket_bawaan_kosong_bila_belum_ditetapkan(auth):
    auth.logout()
    sesi = auth.login("cro", TEST_PASSWORD)

    assert sesi.default_counter_id is None


def test_petugas_pindah_loket_sendiri(auth, antrian_siap):
    """Pindah meja terjadi tanpa rencana dan tidak menunggu admin."""
    loket = antrian_siap["loket"][2]
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    sesi = auth.pindah_loket(loket)

    assert sesi.default_counter_id == loket


def test_pindah_loket_diingat_sampai_login_berikutnya(auth, antrian_siap):
    loket = antrian_siap["loket"][2]
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    auth.pindah_loket(loket)

    auth.logout()
    sesi = auth.login("cro", TEST_PASSWORD)

    assert sesi.default_counter_id == loket


def test_tidak_dapat_pindah_sebelum_antrian_loket_lama_selesai(
    auth, cro_queue, terbitkan, antrian_siap
):
    lama, baru = antrian_siap["loket"][:2]
    auth.pindah_loket(lama)
    terbitkan("A")
    cro_queue.call_next(lama)

    with pytest.raises(BusinessRuleError, match="Selesaikan antrian"):
        auth.pindah_loket(baru)

    assert auth.current_session.default_counter_id == lama


def test_dapat_memilih_loket_yang_sedang_ditangani_sendiri(
    auth, cro_queue, terbitkan, antrian_siap
):
    tujuan = antrian_siap["loket"][1]
    terbitkan("A")
    cro_queue.call_next(tujuan)

    sesi = auth.pindah_loket(tujuan)

    assert sesi.default_counter_id == tujuan


def test_petugas_lama_dapat_pindah_setelah_pengalihan_di_loket_yang_sama(
    auth, cro_queue, terbitkan, antrian_siap
):
    lama, baru = antrian_siap["loket"][:2]
    auth.pindah_loket(lama)
    terbitkan("A")
    aktif = cro_queue.call_next(lama)
    admin, target_id = _buat_target_pengalihan(lama)
    QueueService(admin).alihkan_pelayanan(
        aktif.id, target_id, "Pergantian petugas pada loket yang sama"
    )

    sesi = auth.pindah_loket(baru)

    assert sesi.default_counter_id == baru


def test_pindah_ke_loket_nonaktif_ditolak(auth, antrian_siap, master_service):
    loket = antrian_siap["loket"][0]
    master_service.set_counter_status(loket, False)

    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(BusinessRuleError):
        auth.pindah_loket(loket)


def test_pindah_ke_loket_tidak_dikenal_ditolak(auth, antrian_siap):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    with pytest.raises(NotFoundError):
        auth.pindah_loket(999999)


def test_petugas_dapat_melepas_ikatan_loketnya(auth, antrian_siap):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    auth.pindah_loket(antrian_siap["loket"][0])

    sesi = auth.pindah_loket(None)

    assert sesi.default_counter_id is None


@pytest.mark.parametrize("peran", ["registration", "supervisor", "display"])
def test_selain_cro_tidak_dapat_pindah_loket(auth, antrian_siap, peran):
    """Hanya yang memanggil antrian yang duduk di loket."""
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        auth.pindah_loket(antrian_siap["loket"][0])


# ---------------------------------------------------------------------
# Pengalihan pelayanan oleh admin
# ---------------------------------------------------------------------

def _buat_target_pengalihan(loket_id: int):
    from app.services.auth_service import AuthService
    from app.services.user_service import UserService

    admin = AuthService()
    admin.login("admin", TEST_PASSWORD)
    target_id = UserService(admin).create_user(
        username="cro_pengganti",
        full_name="Petugas Pengganti",
        password=TEST_PASSWORD,
        role="CRO",
        must_change_password=False,
        default_counter_id=loket_id,
    )
    return admin, target_id


def test_admin_mengalihkan_pelayanan_berjalan_dalam_keadaan_ditunda(
    auth, cro_queue, terbitkan, antrian_siap
):
    lama, tujuan = antrian_siap["loket"][:2]
    terbitkan("A")
    aktif = cro_queue.call_next(lama)
    cro_queue.start_service(aktif.id)
    admin, target_id = _buat_target_pengalihan(tujuan)

    hasil = QueueService(admin).alihkan_pelayanan(
        aktif.id, target_id, "Petugas sebelumnya pulang mendadak"
    )

    assert hasil.status is QueueStatus.PAUSED
    assert hasil.counter_id == tujuan
    assert hasil.served_by_id == target_id
    assert hasil.served_by_name == "Petugas Pengganti"

    with pytest.raises(BusinessRuleError, match="telah dialihkan"):
        cro_queue.complete(aktif.id)

    from app.services.auth_service import AuthService

    pengganti = AuthService()
    sesi_pengganti = pengganti.login("cro_pengganti", TEST_PASSWORD)
    assert sesi_pengganti.default_counter_id == tujuan
    layanan_pengganti = QueueService(pengganti)
    assert layanan_pengganti.current_for_counter(tujuan).id == aktif.id
    layanan_pengganti.resume(aktif.id)
    assert layanan_pengganti.complete(aktif.id).status is QueueStatus.COMPLETED


def test_admin_tidak_dapat_mengalihkan_ke_loket_yang_tidak_melayani_kategori(
    auth, cro_queue, terbitkan, antrian_siap
):
    lama, tujuan = antrian_siap["loket"][:2]
    terbitkan("A")
    aktif = cro_queue.call_next(lama)
    _batasi_loket(auth, tujuan, [antrian_siap["kategori"]["B"]])
    admin, target_id = _buat_target_pengalihan(tujuan)

    with pytest.raises(BusinessRuleError, match="tidak melayani"):
        QueueService(admin).alihkan_pelayanan(
            aktif.id, target_id, "Petugas lama pulang"
        )


def test_petugas_tidak_dapat_memanggil_dari_loket_selain_penugasannya(
    auth, cro_queue, terbitkan, antrian_siap
):
    pertama, kedua = antrian_siap["loket"][:2]
    auth.pindah_loket(pertama)
    terbitkan("A", 2)
    aktif = cro_queue.call_next(pertama)

    with pytest.raises(BusinessRuleError, match="ditugaskan ke loket lain"):
        cro_queue.call_next(kedua)

    assert cro_queue.current_for_counter(pertama).id == aktif.id
    assert cro_queue.current_for_counter(kedua) is None


def test_pengalihan_nomor_yang_baru_dipanggil_mempertahankan_status(
    cro_queue, terbitkan, antrian_siap
):
    lama, tujuan = antrian_siap["loket"][:2]
    terbitkan("A")
    aktif = cro_queue.call_next(lama)
    admin, target_id = _buat_target_pengalihan(tujuan)

    hasil = QueueService(admin).alihkan_pelayanan(
        aktif.id, target_id, "Pergantian petugas"
    )

    assert hasil.status is QueueStatus.CALLED
    assert hasil.counter_id == tujuan
    assert hasil.served_by_id == target_id


def test_pengalihan_mencatat_asal_tujuan_dan_alasan(
    cro_queue, terbitkan, antrian_siap
):
    import json

    from app.services import audit_service

    lama, tujuan = antrian_siap["loket"][:2]
    terbitkan("A")
    aktif = cro_queue.call_next(lama)
    admin, target_id = _buat_target_pengalihan(tujuan)

    QueueService(admin).alihkan_pelayanan(
        aktif.id, target_id, "Petugas lama sudah pulang"
    )

    entri = audit_service.list_terakhir(batas=1)[0]
    meta = json.loads(entri.meta)
    assert entri.action == "REASSIGN_QUEUE"
    assert meta["alasan"] == "Petugas lama sudah pulang"
    assert meta["loket_lama_id"] == lama
    assert meta["loket_baru_id"] == tujuan
    assert meta["petugas_baru_id"] == target_id


def test_tidak_dapat_mengalihkan_ke_loket_yang_sedang_sibuk(
    cro_queue, terbitkan, antrian_siap
):
    lama, tujuan = antrian_siap["loket"][:2]
    terbitkan("A", 2)
    pertama = cro_queue.call_next(lama)
    cro_queue.call_next(tujuan)
    admin, target_id = _buat_target_pengalihan(tujuan)

    with pytest.raises(BusinessRuleError, match="masih menangani"):
        QueueService(admin).alihkan_pelayanan(
            pertama.id, target_id, "Petugas lama pulang"
        )


def test_alasan_pengalihan_dan_pembatalan_paksa_wajib_diisi(
    cro_queue, terbitkan, antrian_siap
):
    terbitkan("A")
    aktif = cro_queue.call_next(antrian_siap["loket"][0])
    admin, target_id = _buat_target_pengalihan(antrian_siap["loket"][1])
    layanan_admin = QueueService(admin)

    with pytest.raises(ValidationError, match="wajib diisi"):
        layanan_admin.alihkan_pelayanan(aktif.id, target_id, "   ")
    with pytest.raises(ValidationError, match="wajib diisi"):
        layanan_admin.batalkan_paksa(aktif.id, "")


def test_admin_dapat_membatalkan_paksa_pelayanan_aktif(
    cro_queue, terbitkan, antrian_siap
):
    terbitkan("A")
    aktif = cro_queue.call_next(antrian_siap["loket"][0])
    admin, _target_id = _buat_target_pengalihan(antrian_siap["loket"][1])

    hasil = QueueService(admin).batalkan_paksa(
        aktif.id, "Pengunjung tidak dapat melanjutkan"
    )

    assert hasil.status is QueueStatus.CANCELLED
    assert QueueService(admin).list_pelayanan_aktif() == []


def test_hanya_admin_dapat_melihat_dan_mengalihkan_pelayanan(cro_queue):
    with pytest.raises(AuthorizationError):
        cro_queue.list_pelayanan_aktif()
    with pytest.raises(AuthorizationError):
        cro_queue.list_tujuan_pengalihan()
    with pytest.raises(AuthorizationError):
        cro_queue.alihkan_pelayanan(1, 1, "uji")
    with pytest.raises(AuthorizationError):
        cro_queue.batalkan_paksa(1, "uji")


# ---------------------------------------------------------------------
# Buka / tutup pendaftaran
# ---------------------------------------------------------------------

def test_pendaftaran_terbuka_secara_bawaan(reg_queue):
    assert reg_queue.pendaftaran_dibuka()


def test_tutup_pendaftaran_menghentikan_nomor_baru(reg_queue, antrian_siap):
    reg_queue.tutup_pendaftaran()

    assert not reg_queue.pendaftaran_dibuka()
    with pytest.raises(BusinessRuleError):
        reg_queue.create_queue(antrian_siap["kategori"]["A"])


def test_buka_pendaftaran_memulihkan_penerbitan(reg_queue, antrian_siap):
    reg_queue.tutup_pendaftaran()
    reg_queue.buka_pendaftaran()

    assert reg_queue.pendaftaran_dibuka()
    assert reg_queue.create_queue(antrian_siap["kategori"]["A"]).queue_number == "A-001"


def test_buka_pendaftaran_membersihkan_tanggal_penutupan(reg_queue, settings_service):
    """
    Kedua nilai itu tidak boleh bercerita berbeda.

    Tanggal yang tertinggal membuat penutupan berikutnya tampak sudah
    kedaluwarsa padahal baru saja terjadi.
    """
    reg_queue.tutup_pendaftaran()
    assert settings_service.get("queue.registration_closed_date") != ""

    reg_queue.buka_pendaftaran()

    assert settings_service.get("queue.registration_closed_date") == ""


def test_penutupan_kedaluwarsa_saat_tanggal_berganti(auth, reg_queue, settings_service):
    """
    Petugas yang menutup sore hari dan lupa membukanya lagi tidak boleh
    diam-diam membuat kantor tampak tutup keesokan paginya.
    """
    from app.services.settings_service import SettingsService

    reg_queue.tutup_pendaftaran()
    assert not reg_queue.pendaftaran_dibuka()

    # Menua-kan tanggal penutupan setara dengan hari berganti. Ditulis
    # sebagai admin karena mengubah pengaturan menuntut CONFIG_MANAGE.
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("queue.registration_closed_date", "2000-01-01")
    auth.logout()
    auth.login("registration", TEST_PASSWORD)

    assert QueueService(auth).pendaftaran_dibuka()


def test_nomor_yang_sudah_terbit_tetap_dapat_dipanggil_saat_pendaftaran_ditutup(
    auth, reg_queue, antrian_siap, terbitkan
):
    """Menutup pendaftaran menghentikan nomor BARU, bukan pelayanan."""
    terbitkan("A", 1)
    reg_queue.tutup_pendaftaran()

    auth.logout()
    auth.login("cro", TEST_PASSWORD)

    assert QueueService(auth).call_next(antrian_siap["loket"][0]).queue_number == "A-001"


@pytest.mark.parametrize("peran", ["cro", "supervisor", "display"])
def test_peran_tanpa_hak_tidak_dapat_menutup_pendaftaran(auth, antrian_siap, peran):
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        QueueService(auth).tutup_pendaftaran()


# ---------------------------------------------------------------------
# Pemanggilan bersamaan dari beberapa loket
# ---------------------------------------------------------------------

def _riwayat_panggilan() -> dict[int, list[int]]:
    """queue_id -> daftar loket yang tercatat memanggilnya."""
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import QueueCall

    riwayat: dict[int, list[int]] = {}
    with session_scope() as s:
        for baris in s.scalars(sa.select(QueueCall)):
            riwayat.setdefault(baris.queue_id, []).append(baris.counter_id)
    return riwayat


def _petugas_loket_lain(loket_id: int) -> QueueService:
    """
    Petugas kedua yang memanggil di loket B.

    Dua komputer di lapangan adalah dua akun di dua proses. Memanggil
    loket B dengan akun yang sama dari dalam transaksi loket A membuat
    panggilan B menunggu kunci akun milik A selamanya di PostgreSQL;
    SQLite mengabaikan FOR UPDATE sehingga tidak terlihat di sana.
    """
    from app.services.auth_service import AuthService
    from app.services.user_service import UserService

    admin = AuthService()
    admin.login("admin", TEST_PASSWORD)
    UserService(admin).create_user(
        username="cro_loket_b",
        full_name="Petugas Loket B",
        password=TEST_PASSWORD,
        role="CRO",
        must_change_password=False,
        default_counter_id=loket_id,
    )
    petugas = AuthService()
    petugas.login("cro_loket_b", TEST_PASSWORD)
    return QueueService(petugas)


def test_loket_lain_yang_menyela_tidak_membuat_nomor_dipanggil_dua_kali(
    cro_queue, antrian_siap, terbitkan, monkeypatch
):
    """
    Celah yang dulu ada di PostgreSQL, dibuat terjadi dengan pasti.

    Loket A sudah membaca A-001 sebagai calon. Tepat sebelum A mengklaimnya,
    loket B memanggil dan mendapat A-001. Klaim A harus gagal dan jatuh ke
    A-002 — bukan memanggil A-001 untuk kedua kalinya.
    """
    from app.repositories.queue_repository import QueueRepository

    terbitkan("A", 2)
    loket_a, loket_b = antrian_siap["loket"][:2]
    petugas_b = _petugas_loket_lain(loket_b)

    asli = QueueRepository.list_menunggu
    hasil_b = []

    def dibaca_lalu_disela(self, *args, **kwargs):
        calon = asli(self, *args, **kwargs)
        if not hasil_b:
            hasil_b.append(None)
            hasil_b[0] = petugas_b.call_next(loket_b)
        return calon

    monkeypatch.setattr(QueueRepository, "list_menunggu", dibaca_lalu_disela)

    hasil_a = cro_queue.call_next(loket_a)

    assert hasil_b[0].queue_number == "A-001"
    assert hasil_a.queue_number == "A-002"
    assert _riwayat_panggilan() == {hasil_b[0].id: [loket_b], hasil_a.id: [loket_a]}


def test_klaim_kalah_tanpa_calon_lain_menjawab_tidak_ada_antrian(
    cro_queue, antrian_siap, terbitkan, monkeypatch
):
    from app.repositories.queue_repository import QueueRepository

    terbitkan("A", 1)
    loket_a, loket_b = antrian_siap["loket"][:2]
    petugas_b = _petugas_loket_lain(loket_b)

    asli = QueueRepository.list_menunggu
    disela = []

    def dibaca_lalu_disela(self, *args, **kwargs):
        calon = asli(self, *args, **kwargs)
        if not disela:
            disela.append(None)  # dipasang dulu: panggilan B juga lewat sini
            disela[0] = petugas_b.call_next(loket_b)
        return calon

    monkeypatch.setattr(QueueRepository, "list_menunggu", dibaca_lalu_disela)

    with pytest.raises(BusinessRuleError, match="Tidak ada antrian"):
        cro_queue.call_next(loket_a)

    assert _riwayat_panggilan() == {disela[0].id: [loket_b]}


def test_loket_memanggil_bersamaan_mendapat_nomor_berbeda(
    cro_queue, antrian_siap, terbitkan
):
    """Tiga loket menekan "Panggil Berikutnya" pada saat yang sama, berulang kali."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    putaran = 4
    loket = antrian_siap["loket"][:3]
    terbitkan("A", len(loket) * putaran)

    for _ in range(putaran):
        serentak = threading.Barrier(len(loket))

        def panggil(counter_id: int):
            serentak.wait()
            return cro_queue.call_next(counter_id)

        with ThreadPoolExecutor(max_workers=len(loket)) as pool:
            hasil = list(pool.map(panggil, loket))

        assert len({info.id for info in hasil}) == len(loket)
        # Selesaikan supaya loket boleh memanggil lagi di putaran berikutnya.
        for info in hasil:
            cro_queue.start_service(info.id)
            cro_queue.complete(info.id)

    riwayat = _riwayat_panggilan()
    assert len(riwayat) == len(loket) * putaran
    assert all(len(pemanggil) == 1 for pemanggil in riwayat.values())
