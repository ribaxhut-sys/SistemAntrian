"""
Catatan tayang iklan anjungan.

Yang dikunci: laporan beruntun dijumlah per hari per tablet, tanda gagal
padam begitu berkasnya berhasil diputar lagi di tablet yang sama, dan
nama tablet yang tampil adalah nama yang diberikan admin.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services import device_service, media_tayang
from app.services.media_tayang import LaporanBerkas

LOBI = "a1b2c3d4-0000-4000-8000-0000000000aa"
PINTU = "a1b2c3d4-0000-4000-8000-0000000000bb"


@pytest.fixture
def jam(database, monkeypatch):
    """Jam yang dapat dimajukan, dipakai bersama oleh pencatat dan ringkasan."""
    sekarang = [datetime(2026, 11, 2, 9, 0)]
    monkeypatch.setattr(media_tayang.clock, "now", lambda: sekarang[0])
    monkeypatch.setattr(media_tayang.clock, "today", lambda: sekarang[0].date())
    return sekarang


def test_laporan_dijumlah_per_hari(jam):
    media_tayang.catat(LOBI, [LaporanBerkas("promo.jpg", tayang=3)])
    media_tayang.catat(LOBI, [LaporanBerkas("promo.jpg", tayang=2)])
    media_tayang.catat(PINTU, [LaporanBerkas("promo.jpg", tayang=4)])
    jam[0] += timedelta(days=1)
    media_tayang.catat(LOBI, [LaporanBerkas("promo.jpg", tayang=1)])

    info = media_tayang.ringkasan()["promo.jpg"]

    assert info.tayang_hari_ini == 1
    assert info.tayang_rentang == 10
    assert info.gagal == []


def test_angka_di_luar_tiga_puluh_hari_tidak_dihitung(jam):
    media_tayang.catat(LOBI, [LaporanBerkas("promo.jpg", tayang=5)])
    jam[0] += timedelta(days=media_tayang.RENTANG_HARI)

    assert "promo.jpg" not in media_tayang.ringkasan()


def test_tanda_gagal_menyebut_nama_tablet_dan_padam_setelah_berhasil(jam):
    device_service.catat_kontak(LOBI, nama="Tablet Lobi")
    media_tayang.catat(
        LOBI,
        [LaporanBerkas("iklan.avi", gagal=2, galat="video what=1", terakhir_gagal=True)],
    )

    (gagal,) = media_tayang.ringkasan()["iklan.avi"].gagal
    assert gagal.tablet == "Tablet Lobi"
    assert gagal.pesan == "video what=1"

    jam[0] += timedelta(minutes=1)
    media_tayang.catat(LOBI, [LaporanBerkas("iklan.avi", tayang=1)])

    assert media_tayang.ringkasan()["iklan.avi"].gagal == []


def test_tayang_dan_gagal_dalam_satu_laporan_mengikuti_percobaan_terakhir(jam):
    media_tayang.catat(
        LOBI, [LaporanBerkas("a.mp4", tayang=1, gagal=1, galat="x", terakhir_gagal=True)]
    )
    media_tayang.catat(
        PINTU, [LaporanBerkas("a.mp4", tayang=1, gagal=1, galat="x", terakhir_gagal=False)]
    )

    (gagal,) = media_tayang.ringkasan()["a.mp4"].gagal
    assert gagal.tablet == LOBI[:8], "tablet tanpa nama memakai awal device_id"


def test_galat_kemarin_lusa_tidak_lagi_ditandai(jam):
    media_tayang.catat(LOBI, [LaporanBerkas("a.mp4", gagal=1, terakhir_gagal=True)])
    jam[0] += timedelta(days=2)

    assert media_tayang.ringkasan()["a.mp4"].gagal == []


def test_laporan_kosong_atau_tanpa_perangkat_diabaikan(jam):
    media_tayang.catat("", [LaporanBerkas("a.jpg", tayang=1)])
    media_tayang.catat(LOBI, [LaporanBerkas("a.jpg"), LaporanBerkas("  ", tayang=3)])

    assert media_tayang.ringkasan() == {}


def test_ringkasan_tidak_mengelompokkan_ekspresi_berparameter(jam):
    """
    Regresi: GROUP BY "tanggal = :hari" lolos di SQLite tetapi ditolak
    PostgreSQL (database produksi), karena parameter di SELECT dan di
    GROUP BY dianggap ekspresi berbeda. Halaman Pengaturan menelan galatnya,
    jadi angka tayang hilang tanpa pesan apa pun.
    """
    import sqlalchemy as sa

    from app.core.database import get_engine

    media_tayang.catat(LOBI, [LaporanBerkas("promo.jpg", tayang=1)])
    perintah = []

    def rekam(_conn, _cursor, statement, *_args):
        perintah.append(statement)

    mesin = get_engine()
    sa.event.listen(mesin, "before_cursor_execute", rekam)
    try:
        media_tayang.ringkasan()
    finally:
        sa.event.remove(mesin, "before_cursor_execute", rekam)

    kelompok = [p.split("GROUP BY", 1)[1] for p in perintah if "GROUP BY" in p]
    assert kelompok, "query jumlah tayang tidak terekam"
    for isi in kelompok:
        assert "?" not in isi and "%(" not in isi
