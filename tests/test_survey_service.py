"""
Test survey kepuasan.

Yang paling penting dikunci di sini: survey tidak boleh mengubah status
antrian, dan satu antrian tidak boleh dinilai dua kali.
"""

from __future__ import annotations

import pytest

from app.core.errors import AuthorizationError, BusinessRuleError, NotFoundError, ValidationError
from app.models import QueueStatus
from app.services.survey_service import SurveyService
from tests.conftest import TEST_PASSWORD


# ---------------------------------------------------------------------
# Alur normal
# ---------------------------------------------------------------------

def test_antrian_selesai_dapat_dinilai(cro_survey, layani_sampai_selesai):
    antrian = layani_sampai_selesai()

    hasil = cro_survey.submit(antrian.id, 5, "Pelayanan cepat dan ramah.")

    assert hasil.queue_id == antrian.id
    assert hasil.queue_number == antrian.queue_number
    assert hasil.rating == 5
    assert hasil.rating_label == "Sangat Puas"
    assert hasil.feedback == "Pelayanan cepat dan ramah."


def test_masukan_boleh_dikosongkan(cro_survey, layani_sampai_selesai):
    antrian = layani_sampai_selesai()

    hasil = cro_survey.submit(antrian.id, 4)

    assert hasil.feedback is None


def test_masukan_berisi_spasi_saja_disimpan_sebagai_kosong(
    cro_survey, layani_sampai_selesai
):
    antrian = layani_sampai_selesai()

    hasil = cro_survey.submit(antrian.id, 3, "   \n  ")

    assert hasil.feedback is None


@pytest.mark.parametrize("nilai", [1, 2, 3, 4, 5])
def test_seluruh_nilai_sah_diterima(cro_survey, layani_sampai_selesai, nilai):
    antrian = layani_sampai_selesai()

    assert cro_survey.submit(antrian.id, nilai).rating == nilai


# ---------------------------------------------------------------------
# Survey tidak mengubah antrian
# ---------------------------------------------------------------------

def test_rating_terburuk_tidak_mengubah_status_antrian(
    cro_survey, cro_queue, layani_sampai_selesai
):
    """Rating mengukur kualitas pelayanan, bukan selesai atau tidaknya."""
    antrian = layani_sampai_selesai()

    cro_survey.submit(antrian.id, 1, "Sangat lama menunggu.")

    assert cro_queue.get_queue(antrian.id).status is QueueStatus.COMPLETED


# ---------------------------------------------------------------------
# Penolakan
# ---------------------------------------------------------------------

@pytest.mark.parametrize("nilai", [0, 6, -1, 100])
def test_nilai_di_luar_rentang_ditolak(cro_survey, layani_sampai_selesai, nilai):
    antrian = layani_sampai_selesai()

    with pytest.raises(ValidationError) as info:
        cro_survey.submit(antrian.id, nilai)

    assert "1 sampai 5" in info.value.user_message


def test_nilai_bukan_angka_ditolak(cro_survey, layani_sampai_selesai):
    antrian = layani_sampai_selesai()

    with pytest.raises(ValidationError):
        cro_survey.submit(antrian.id, "5")


def test_masukan_terlalu_panjang_ditolak(cro_survey, layani_sampai_selesai):
    antrian = layani_sampai_selesai()

    with pytest.raises(ValidationError) as info:
        cro_survey.submit(antrian.id, 5, "x" * 1001)

    assert "terlalu panjang" in info.value.user_message


def test_antrian_yang_belum_selesai_tidak_dapat_dinilai(
    antrian_siap, cro_survey, cro_queue, terbitkan
):
    terbitkan("A")
    antrian = cro_queue.call_next(antrian_siap["loket"][0])

    with pytest.raises(BusinessRuleError) as info:
        cro_survey.submit(antrian.id, 5)

    assert "belum selesai" in info.value.user_message


def test_antrian_dibatalkan_tidak_dapat_dinilai(
    antrian_siap, cro_survey, cro_queue, terbitkan
):
    """Antrian yang dibatalkan tidak pernah menerima pelayanan."""
    antrian = terbitkan("A")[0]
    cro_queue.cancel(antrian.id)

    with pytest.raises(BusinessRuleError):
        cro_survey.submit(antrian.id, 5)


def test_satu_antrian_hanya_boleh_dinilai_sekali(cro_survey, layani_sampai_selesai):
    antrian = layani_sampai_selesai()
    cro_survey.submit(antrian.id, 5)

    with pytest.raises(BusinessRuleError) as info:
        cro_survey.submit(antrian.id, 1)

    assert "sudah pernah dinilai" in info.value.user_message


def test_antrian_tidak_dikenal_ditolak(cro_survey, layani_sampai_selesai):
    layani_sampai_selesai()

    with pytest.raises(NotFoundError):
        cro_survey.submit(999_999, 5)


# ---------------------------------------------------------------------
# Hak akses
# ---------------------------------------------------------------------

def test_pendaftaran_tidak_boleh_mengisi_survey(
    auth, layani_sampai_selesai
):
    antrian = layani_sampai_selesai()
    auth.logout()
    auth.login("registration", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        SurveyService(auth).submit(antrian.id, 5)


def test_cro_tidak_boleh_melihat_ringkasan(cro_survey, layani_sampai_selesai):
    """Ringkasan kepuasan adalah urusan supervisor, bukan petugas loket."""
    layani_sampai_selesai()

    with pytest.raises(AuthorizationError):
        cro_survey.ringkasan()


def test_supervisor_tidak_boleh_mengisi_survey(auth, layani_sampai_selesai):
    antrian = layani_sampai_selesai()
    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        SurveyService(auth).submit(antrian.id, 5)


# ---------------------------------------------------------------------
# Daftar yang belum dinilai
# ---------------------------------------------------------------------

def test_antrian_selesai_muncul_di_daftar_belum_dinilai(
    cro_survey, layani_sampai_selesai
):
    antrian = layani_sampai_selesai()

    assert [q.id for q in cro_survey.list_pending()] == [antrian.id]


def test_antrian_hilang_dari_daftar_setelah_dinilai(
    cro_survey, layani_sampai_selesai
):
    antrian = layani_sampai_selesai()
    cro_survey.submit(antrian.id, 4)

    assert cro_survey.list_pending() == []


def test_antrian_yang_masih_dilayani_tidak_masuk_daftar(
    antrian_siap, cro_survey, cro_queue, terbitkan
):
    terbitkan("A")
    antrian = cro_queue.call_next(antrian_siap["loket"][0])
    cro_queue.start_service(antrian.id)

    assert cro_survey.list_pending() == []


def test_get_by_queue_mengembalikan_none_bila_belum_dinilai(
    cro_survey, layani_sampai_selesai
):
    antrian = layani_sampai_selesai()

    assert cro_survey.get_by_queue(antrian.id) is None


# ---------------------------------------------------------------------
# Ringkasan untuk supervisor
# ---------------------------------------------------------------------

def _ringkasan_supervisor(auth):
    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    return SurveyService(auth).ringkasan()


def test_ringkasan_kosong_saat_belum_ada_survey(auth, users):
    ringkasan = _ringkasan_supervisor(auth)

    assert ringkasan.jumlah == 0
    assert ringkasan.rata_rata is None
    assert ringkasan.label_rata_rata == "-"
    assert ringkasan.distribusi == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}


def test_ringkasan_menghitung_rata_rata_dan_distribusi(
    auth, cro_survey, layani_sampai_selesai
):
    for nilai in (5, 4, 3):
        cro_survey.submit(layani_sampai_selesai().id, nilai)

    ringkasan = _ringkasan_supervisor(auth)

    assert ringkasan.jumlah == 3
    assert ringkasan.rata_rata == pytest.approx(4.0)
    assert ringkasan.distribusi[5] == 1
    assert ringkasan.distribusi[4] == 1
    assert ringkasan.distribusi[3] == 1
    assert ringkasan.distribusi[1] == 0
    assert ringkasan.persentase(5) == pytest.approx(100 / 3)


def test_supervisor_melihat_survey_terakhir(auth, cro_survey, layani_sampai_selesai):
    antrian = layani_sampai_selesai()
    cro_survey.submit(antrian.id, 2, "Perlu diperbaiki.")

    auth.logout()
    auth.login("supervisor", TEST_PASSWORD)
    daftar = SurveyService(auth).list_terakhir()

    assert len(daftar) == 1
    assert daftar[0].queue_number == antrian.queue_number
    assert daftar[0].feedback == "Perlu diperbaiki."


# ---------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------

def test_pengisian_survey_tercatat_di_audit(cro_survey, layani_sampai_selesai):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditLog

    antrian = layani_sampai_selesai()
    cro_survey.submit(antrian.id, 5)

    with session_scope() as session:
        aksi = list(
            session.scalars(
                sa.select(AuditLog.action).where(AuditLog.action == "SUBMIT_SURVEY")
            )
        )

    assert aksi == ["SUBMIT_SURVEY"]
