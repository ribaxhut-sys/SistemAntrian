"""
Test masa simpan identitas pelapor pengaduan.

Yang dijaga: sesudah masa simpannya, identitas pelapor hilang dari
database, sedangkan isi pengaduan dan catatan petugas tetap ada — dan
audit sapuannya tidak menyalin satu pun isi lembar.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.models import AuditLog, Queue, QueueNote
from app.services.note_service import NoteService, batas_retensi
from tests.conftest import TEST_PASSWORD


@pytest.fixture
def note(auth, antrian_siap):
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    return NoteService(auth)


def _lembar(note, terbitkan, hari_lalu: int) -> int:
    """Lembar pengaduan lengkap, lalu antriannya dimundurkan `hari_lalu` hari."""
    antrian = terbitkan("A")[0]
    lembar = note.simpan(
        antrian.id,
        nama="Budi Santoso",
        nomor_pelanggan="1234567",
        telepon="081234567890",
        email="budi@contoh.id",
        alamat="Jl. Melati 5",
        deskripsi="Tagihan ganda bulan Juli.",
        catatan="Sudah diteruskan ke bagian penagihan.",
    )
    with session_scope() as session:
        baris = session.get(Queue, antrian.id)
        baris.queue_date = clock.today() - timedelta(days=hari_lalu)
    return lembar.id


def _baca(note_id: int) -> QueueNote:
    with session_scope() as session:
        baris = session.get(QueueNote, note_id)
        session.expunge(baris)
        return baris


@pytest.mark.parametrize(
    ("hari_ini", "bulan", "batas"),
    [
        (date(2026, 10, 12), 24, date(2024, 10, 12)),
        (date(2026, 10, 12), 12, date(2025, 10, 12)),
        (date(2026, 1, 15), 1, date(2025, 12, 15)),
        (date(2026, 5, 31), 3, date(2026, 2, 28)),
        (date(2026, 3, 31), 1, date(2026, 2, 28)),
        (date(2026, 12, 31), 12, date(2025, 12, 31)),
    ],
)
def test_batas_retensi_mundur_bulan_kalender(hari_ini, bulan, batas):
    assert batas_retensi(hari_ini, bulan) == batas


def test_identitas_lewat_masa_simpan_dikosongkan_isi_tetap(note, terbitkan):
    lama = _lembar(note, terbitkan, hari_lalu=800)
    baru = _lembar(note, terbitkan, hari_lalu=700)

    assert note.anonimkan_kedaluwarsa() == 1

    hasil = _baca(lama)
    assert (hasil.nama, hasil.nomor_pelanggan, hasil.telepon, hasil.email, hasil.alamat) == (
        None, None, None, None, None,
    )
    assert hasil.deskripsi == "Tagihan ganda bulan Juli."
    assert hasil.catatan == "Sudah diteruskan ke bagian penagihan."

    tetap = _baca(baru)
    assert tetap.nama == "Budi Santoso"
    assert tetap.telepon == "081234567890"


def test_sapuan_kedua_tidak_menghitung_ulang(note, terbitkan):
    _lembar(note, terbitkan, hari_lalu=800)
    assert note.anonimkan_kedaluwarsa() == 1
    assert note.anonimkan_kedaluwarsa() == 0


def test_audit_sapuan_tidak_memuat_isi_lembar(note, terbitkan):
    _lembar(note, terbitkan, hari_lalu=800)
    note.anonimkan_kedaluwarsa()

    with session_scope() as session:
        audit = session.scalars(
            sa.select(AuditLog).where(AuditLog.action == "ANONYMIZE_NOTE")
        ).all()
        assert len(audit) == 1
        assert audit[0].user_id is None
        teks = repr(audit[0].__dict__)
    for rahasia in ("Budi", "1234567", "0812", "budi@", "Melati", "Tagihan"):
        assert rahasia not in teks


def test_retensi_nol_berarti_disimpan_selamanya(note, terbitkan, auth):
    from app.services.settings_service import SettingsService

    lama = _lembar(note, terbitkan, hari_lalu=3000)
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("privasi.retensi_pengaduan_bulan", "0")

    assert note.anonimkan_kedaluwarsa() == 0
    assert _baca(lama).nama == "Budi Santoso"


def test_retensi_dapat_diperpendek(note, terbitkan, auth):
    from app.services.settings_service import SettingsService

    lembar = _lembar(note, terbitkan, hari_lalu=400)
    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("privasi.retensi_pengaduan_bulan", "12")

    assert note.anonimkan_kedaluwarsa() == 1
    assert _baca(lembar).nama is None


def test_sapuan_tidak_menuntut_login(note, terbitkan, auth):
    """Berjalan saat aplikasi mulai, sebelum siapa pun masuk."""
    lembar = _lembar(note, terbitkan, hari_lalu=800)
    auth.logout()

    assert NoteService(auth).anonimkan_kedaluwarsa() == 1
    assert _baca(lembar).nama is None


def test_penyapu_harian_ikut_menganonimkan(monkeypatch):
    import app.main as main_module

    dipanggil = []
    monkeypatch.setattr(main_module, "hanguskan_antrian_hari_lalu", lambda: 0)
    monkeypatch.setattr(
        main_module, "anonimkan_pengaduan_lama", lambda: dipanggil.append(1) or 0
    )
    penyapu = main_module.PenyapuHarian(hari_awal=clock.today() - timedelta(days=1))
    penyapu.periksa()

    assert dipanggil == [1]
