"""
Test perkiraan waktu tunggu di tiket.

Yang paling penting: tiket DIAM bila tidak ada perkiraan yang jujur —
tanpa loket berpetugas atau tanpa riwayat pelayanan — dan angka yang
dicetak berupa rentang yang dibulatkan ke atas, bukan janji menit.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core import clock
from app.core.database import session_scope
from app.models import Counter, Queue, QueueStatus
from app.services.queue_service import _lama_layanan_tipikal
from app.services.ticket_service import baris_perkiraan_tunggu


def _riwayat(antrian_siap, prefix: str, menit: list[float], hari_lalu: int = 0) -> None:
    """Sisipkan pelayanan SELESAI dengan lama layanan tertentu."""
    tanggal = clock.today() - timedelta(days=hari_lalu)
    awal = datetime.combine(tanggal, datetime.min.time()).replace(hour=8)
    with session_scope() as session:
        for i, lama in enumerate(menit):
            mulai = awal + timedelta(minutes=10 * i)
            session.add(
                Queue(
                    branch_id=antrian_siap["branch_id"],
                    category_id=antrian_siap["kategori"][prefix],
                    queue_date=tanggal,
                    queue_number=f"{prefix}-9{hari_lalu}{i:02d}",
                    sequence_number=900 + i,
                    status=QueueStatus.COMPLETED,
                    created_at=mulai,
                    called_at=mulai,
                    serving_at=mulai,
                    completed_at=mulai + timedelta(minutes=lama),
                )
            )


def _loket(antrian_siap, jumlah: int, layanan: list[str] | None = None, **ubah) -> None:
    """Tandai `jumlah` loket pertama berpetugas; sisanya kosong."""
    from app.models import ServiceCategory

    with session_scope() as session:
        for urutan, counter_id in enumerate(antrian_siap["loket"]):
            counter = session.get(Counter, counter_id)
            counter.on_break = False
            counter.petugas_terlihat_pada = clock.now() if urutan < jumlah else None
            counter.categories = [
                session.get(ServiceCategory, antrian_siap["kategori"][p])
                for p in (layanan or [])
            ]
            for kunci, nilai in ubah.items():
                setattr(counter, kunci, nilai)


@pytest.fixture
def cukup_loket(antrian_siap):
    if len(antrian_siap["loket"]) < 2:
        pytest.skip("butuh dua loket dari data awal")


# ---------------------------------------------------------------------
# Kalimat di tiket
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("detik", "kalimat"),
    [
        (None, ""),
        (0, ""),
        (60, "Perkiraan tunggu: ±5 menit"),
        (24 * 60, "Perkiraan tunggu: ±20–25 menit"),
        (25 * 60, "Perkiraan tunggu: ±20–25 menit"),
        (25 * 60 + 1, "Perkiraan tunggu: ±25–30 menit"),
        (4 * 3600, "Perkiraan tunggu: lebih dari 3 jam"),
    ],
)
def test_kalimat_perkiraan_dibulatkan_ke_atas_per_lima_menit(detik, kalimat):
    assert baris_perkiraan_tunggu(detik) == kalimat


def test_median_tidak_terseret_satu_pelayanan_yang_sangat_lama():
    hari = clock.today()
    sampel = [(1, hari, 300.0)] * 6 + [(1, hari, 5400.0)]
    tipikal, gabungan = _lama_layanan_tipikal(sampel, hari)
    assert tipikal[1] == 300.0
    assert gabungan == 300.0


def test_riwayat_lama_dipakai_bila_hari_ini_belum_cukup():
    hari = clock.today()
    kemarin = hari - timedelta(days=1)
    sampel = [(1, hari, 600.0)] * 2 + [(1, kemarin, 300.0)] * 5
    tipikal, _ = _lama_layanan_tipikal(sampel, hari)
    assert tipikal[1] == 300.0


def test_tanpa_cukup_sampel_tidak_ada_perkiraan():
    hari = clock.today()
    tipikal, gabungan = _lama_layanan_tipikal([(1, hari, 300.0)] * 4, hari)
    assert tipikal == {}
    assert gabungan is None


# ---------------------------------------------------------------------
# Perhitungan dari database
# ---------------------------------------------------------------------

def test_perkiraan_dibagi_banyaknya_loket_berpetugas(
    ticket_pdf, reg_queue, antrian_siap, cukup_loket
):
    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 2)
    for _ in range(4):
        reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    # 4 orang × 6 menit ÷ 2 loket = 12 menit.
    assert reg_queue.perkiraan_tunggu(nomor) == pytest.approx(12 * 60)
    tiket = ticket_pdf.susun(nomor)
    assert tiket.baris_perkiraan_tunggu() == "Perkiraan tunggu: ±10–15 menit"
    assert "Perkiraan tunggu: ±10–15 menit" in tiket.baris_teks()


def test_orang_di_depan_memakai_lama_layanan_jenisnya_sendiri(
    reg_queue, antrian_siap
):
    _riwayat(antrian_siap, "A", [4] * 5)
    _riwayat(antrian_siap, "B", [20] * 5)
    _loket(antrian_siap, 1)
    reg_queue.create_queue(antrian_siap["kategori"]["B"])
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert reg_queue.perkiraan_tunggu(nomor) == pytest.approx(24 * 60)


def test_loket_istirahat_atau_tanpa_petugas_tidak_dihitung(reg_queue, antrian_siap):
    _riwayat(antrian_siap, "A", [6] * 5)
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    _loket(antrian_siap, 0)
    assert reg_queue.perkiraan_tunggu(nomor) is None

    _loket(antrian_siap, 1, on_break=True)
    assert reg_queue.perkiraan_tunggu(nomor) is None


def test_loket_yang_tidak_melayani_jenisnya_tidak_dihitung(reg_queue, antrian_siap):
    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1, layanan=["B"])
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert reg_queue.perkiraan_tunggu(nomor) is None


def test_antrian_jenis_lain_yang_tidak_terjangkau_loket_tidak_menambah(
    reg_queue, antrian_siap
):
    _riwayat(antrian_siap, "A", [6] * 5)
    _riwayat(antrian_siap, "B", [30] * 5)
    _loket(antrian_siap, 1, layanan=["A"])
    reg_queue.create_queue(antrian_siap["kategori"]["B"])
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert reg_queue.perkiraan_tunggu(nomor) == pytest.approx(6 * 60)


def test_tanpa_riwayat_tiket_tidak_mencetak_perkiraan(
    ticket_pdf, reg_queue, antrian_siap
):
    _loket(antrian_siap, 1)
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    tiket = ticket_pdf.susun(nomor)
    assert tiket.perkiraan_tunggu_detik is None
    assert not any(b.startswith("Perkiraan") for b in tiket.baris_teks())


def test_pemegang_tiket_terdepan_tidak_mendapat_baris_perkiraan(
    ticket_pdf, reg_queue, antrian_siap
):
    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1)
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert reg_queue.perkiraan_tunggu(nomor) == 0
    assert ticket_pdf.susun(nomor).baris_perkiraan_tunggu() == ""


def test_pengaturan_dapat_mematikan_perkiraan(
    ticket_pdf, reg_queue, antrian_siap, auth
):
    from app.services.settings_service import SettingsService
    from tests.conftest import TEST_PASSWORD

    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1)
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    SettingsService(auth).set("ticket.perkiraan_tunggu", "false")
    auth.logout()
    auth.login("registration", TEST_PASSWORD)

    assert ticket_pdf.susun(nomor).perkiraan_tunggu_detik is None


def test_kios_boleh_membaca_perkiraan(auth, reg_queue, antrian_siap):
    from app.services.queue_service import QueueService

    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1)
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    auth.logout()
    auth.mulai_sesi_kios()
    kios = QueueService(auth)
    nomor = kios.create_queue(antrian_siap["kategori"]["A"])

    assert kios.perkiraan_tunggu(nomor) == pytest.approx(6 * 60)


def test_perkiraan_gagal_tidak_menghapus_sisa_antrian(
    ticket_pdf, reg_queue, antrian_siap, monkeypatch
):
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    def rusak(_):
        raise RuntimeError("database tersendat")

    monkeypatch.setattr(ticket_pdf.queue, "perkiraan_tunggu", rusak)
    tiket = ticket_pdf.susun(nomor)
    assert tiket.sisa_antrian == 1
    assert tiket.perkiraan_tunggu_detik is None


def test_tiket_terpanjang_dengan_perkiraan_tetap_muat_88_mm(
    ticket_pdf, reg_queue, antrian_siap
):
    from dataclasses import replace

    from app.services.ticket_service import PdfTicketPrinter, _tata_letak
    from tests.test_ticket_service import _pas_helvetica

    tiket = replace(
        ticket_pdf.susun(reg_queue.create_queue(antrian_siap["kategori"]["A"])),
        header="BAPENDA DKI JAKARTA",
        office_name="UNIT PELAYANAN PEMUNGUTAN PAJAK DAERAH",
        counter_name="Loket 2",
        footer=" ".join(["Terima kasih atas kesabaran Anda"] * 5),
        sisa_antrian=12,
        perkiraan_tunggu_detik=95 * 60,
    )
    baris = _tata_letak(tiket, _pas_helvetica, ukuran_nomor=54)
    teks = [b.teks for b in baris]

    assert "Perkiraan tunggu: ±90–95 menit" in teks
    assert teks.index("Sisa antrian: 12") + 1 == teks.index("Perkiraan tunggu: ±90–95 menit")
    assert [b.y_mm for b in baris] == sorted(b.y_mm for b in baris)
    assert PdfTicketPrinter.TINGGI_MM - baris[-1].y_mm >= 12


def test_cetak_ulang_tiket_yang_sudah_dipanggil(
    ticket_pdf, cro_queue, terbitkan, antrian_siap, auth
):
    """Tiket sudah dipanggil: tidak ada yang di depannya lagi."""
    from tests.conftest import TEST_PASSWORD

    _riwayat(antrian_siap, "A", [6] * 5)
    pertama = terbitkan("A")[0]
    terbitkan("A", 3)
    cro_queue.call_next(antrian_siap["loket"][0])
    _loket(antrian_siap, 1)

    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    tiket = ticket_pdf.susun(pertama)
    assert tiket.perkiraan_tunggu_detik is None
    assert tiket.sisa_antrian == 0


def test_tiket_anjungan_tanpa_sisa_tetap_mencetak_perkiraan(
    ticket_pdf, reg_queue, antrian_siap
):
    """kiosk_api membuang sisa antrian; perkiraan harus tetap tergambar."""
    from dataclasses import replace

    from app.services.ticket_service import tata_letak_tiket_anjungan

    _riwayat(antrian_siap, "A", [6] * 5)
    _loket(antrian_siap, 1)
    reg_queue.create_queue(antrian_siap["kategori"]["A"])
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    tiket = replace(ticket_pdf.susun(nomor), sisa_antrian=None)
    teks = [b["text"] for b in tata_letak_tiket_anjungan(tiket)["rows"]]
    assert "Perkiraan tunggu: ±5–10 menit" in teks
    assert not any(t.startswith("Sisa antrian") for t in teks)
    assert "Perkiraan tunggu: ±5–10 menit" in tiket.baris_teks()


def test_tiket_contoh_tidak_menghitung_perkiraan(ticket_pdf, monkeypatch):
    from types import SimpleNamespace

    def jangan(_):
        raise AssertionError("tiket contoh tidak boleh dihitung")

    monkeypatch.setattr(ticket_pdf.queue, "perkiraan_tunggu", jangan)
    contoh = SimpleNamespace(
        queue_number="UJI-000", category_name="Uji", created_at=clock.now(),
        counter_name=None,
    )
    assert ticket_pdf._perkiraan(contoh) is None
