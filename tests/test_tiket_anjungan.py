"""
Penerbitan tiket anjungan Android lewat API, di atas database sungguhan.

Test di tests/test_kiosk_api.py memakai layanan tiruan dan karena itu tidak
dapat membuktikan apa pun tentang database. Di sini yang diuji adalah
janji yang harus tetap benar sesudah API dinyalakan ulang: satu request_id
dari satu perangkat menghasilkan tepat satu nomor.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.database import session_scope
from app.models import KioskTicketRequest, Queue
from app.services.apk_anjungan import VERSI_MINIMAL

TOKEN = "bapendacro"


def _klien() -> TestClient:
    """API baru dengan layanan baru — setara proses API yang baru dinyalakan."""
    from app.kiosk_api import KioskServices, create_app

    return TestClient(create_app(TOKEN, KioskServices()))


def _header(perangkat: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "X-App-Version-Code": str(VERSI_MINIMAL),
        "X-Device-Id": perangkat,
    }


def _pasang(device_id: str) -> dict[str, str]:
    """Pasangkan perangkat dan kembalikan header dengan token miliknya."""
    from datetime import timedelta

    from app.core import clock
    from app.models import KioskPairingCode
    from app.services import device_service

    kode = f"{abs(hash(device_id)) % 1_000_000:06d}"
    with session_scope() as session:
        session.add(
            KioskPairingCode(kode=kode, kedaluwarsa=clock.now() + timedelta(minutes=5))
        )
    token = device_service.pasangkan(kode, device_id, device_id, "anjungan")
    return {
        "Authorization": f"Bearer {token}",
        "X-App-Version-Code": str(VERSI_MINIMAL),
        "X-Device-Id": device_id,
    }


def _jumlah(model) -> int:
    with session_scope() as s:
        return s.scalar(sa.select(sa.func.count()).select_from(model))


@pytest.fixture
def kategori(antrian_siap) -> dict[str, int]:
    return antrian_siap["kategori"]


# ---------------------------------------------------------------------
# Idempotensi
# ---------------------------------------------------------------------

def test_permintaan_ulang_menerima_tiket_yang_sama(kategori):
    """Ulangan biasa: jawaban pertama tidak sampai ke tablet, tablet mengulang."""
    klien = _klien()
    isi = {"category_id": kategori["A"], "request_id": str(uuid4())}

    pertama = klien.post("/v1/kiosk/tickets", headers=_header("tablet-aaa"), json=isi)
    ulang = klien.post("/v1/kiosk/tickets", headers=_header("tablet-aaa"), json=isi)

    assert pertama.status_code == 200
    # Ulangan datang di tengah jeda perangkat itu sendiri dan tetap dijawab.
    assert ulang.status_code == 200
    assert ulang.json() == pertama.json()
    assert _jumlah(Queue) == 1


def test_permintaan_ulang_sesudah_api_dinyalakan_ulang(kategori):
    """
    Celah lama: kunci hanya di memori, hilang bersama prosesnya.

    Nomor terbit, jawabannya hilang, API dinyalakan ulang, tablet mengulang
    dengan UUID yang sama. Tidak boleh ada nomor kedua.
    """
    isi = {"category_id": kategori["A"], "request_id": str(uuid4())}

    pertama = _klien().post("/v1/kiosk/tickets", headers=_header("tablet-aaa"), json=isi)
    ulang = _klien().post("/v1/kiosk/tickets", headers=_header("tablet-aaa"), json=isi)

    assert pertama.status_code == ulang.status_code == 200
    assert ulang.json()["queue_number"] == pertama.json()["queue_number"] == "A-001"
    assert ulang.json()["issued_at"] == pertama.json()["issued_at"]
    assert _jumlah(Queue) == 1
    assert _jumlah(KioskTicketRequest) == 1


def test_permintaan_ulang_tetap_dijawab_sesudah_pendaftaran_ditutup(
    kategori, auth
):
    """Nomornya sudah terbit; menutup pendaftaran tidak boleh menghilangkannya."""
    from app.services.queue_service import QueueService
    from tests.conftest import TEST_PASSWORD

    klien = _klien()
    isi = {"category_id": kategori["A"], "request_id": str(uuid4())}
    pertama = klien.post("/v1/kiosk/tickets", headers=_header("tablet-aaa"), json=isi)

    auth.logout()
    auth.login("registration", TEST_PASSWORD)
    QueueService(auth).tutup_pendaftaran()

    ulang = klien.post("/v1/kiosk/tickets", headers=_header("tablet-aaa"), json=isi)
    assert ulang.status_code == 200
    assert ulang.json() == pertama.json()


def test_request_id_sama_dari_dua_perangkat_adalah_dua_permintaan(kategori):
    """UUID hanya unik di perangkat pembuatnya; kuncinya pasangan keduanya."""
    klien = _klien()
    isi = {"category_id": kategori["A"], "request_id": str(uuid4())}

    a = klien.post("/v1/kiosk/tickets", headers=_pasang("tablet-aaa-0001"), json=isi)
    b = klien.post("/v1/kiosk/tickets", headers=_pasang("tablet-bbb-0001"), json=isi)

    assert a.status_code == b.status_code == 200
    assert {a.json()["queue_number"], b.json()["queue_number"]} == {"A-001", "A-002"}
    assert _jumlah(Queue) == 2


def test_request_id_sama_untuk_layanan_lain_ditolak(kategori):
    """
    Bukan permintaan ulang: tablet yang benar membuat UUID baru per pilihan.

    Ditolak dengan 409 dan pesan yang jelas — tidak menerbitkan nomor baru,
    dan tidak mengembalikan nomor layanan yang tidak dipilih pengunjung.
    """
    klien = _klien()
    request_id = str(uuid4())
    klien.post(
        "/v1/kiosk/tickets",
        headers=_header("tablet-aaa"),
        json={"category_id": kategori["A"], "request_id": request_id},
    )

    lain = _klien().post(
        "/v1/kiosk/tickets",
        headers=_header("tablet-aaa"),
        json={"category_id": kategori["B"], "request_id": request_id},
    )

    assert lain.status_code == 409
    assert "jenis layanan lain" in lain.json()["detail"]
    assert _jumlah(Queue) == 1


def test_permintaan_kembar_bersamaan_hanya_menerbitkan_satu_nomor(kategori):
    """
    Tanpa kunci di proses API: yang menahan hanyalah constraint database.

    Beberapa utas memanggil layanan langsung — melewati kunci tiket di API —
    dengan kunci yang sama pada saat bersamaan, masing-masing dengan
    instance layanan sendiri seperti beberapa proses API.
    """
    from app.kiosk_api import KioskServices

    utas = 6
    request_id = str(uuid4())
    layanan = [KioskServices().queue for _ in range(utas)]
    serentak = threading.Barrier(utas)

    def terbitkan(queue_service):
        serentak.wait()
        return queue_service.create_queue(
            kategori["A"], perangkat="tablet-aaa", request_id=request_id
        )

    with ThreadPoolExecutor(max_workers=utas) as pool:
        hasil = list(pool.map(terbitkan, layanan))

    assert {info.id for info in hasil} == {hasil[0].id}
    assert _jumlah(Queue) == 1
    assert _jumlah(KioskTicketRequest) == 1
    # Transaksi yang kalah batal seluruhnya, termasuk kenaikan nomor urut.
    lanjut = layanan[0].create_queue(kategori["A"], perangkat="tablet-bbb")
    assert lanjut.queue_number == "A-002"


def test_constraint_database_yang_menolak_kembaran(kategori, monkeypatch):
    """
    Pemeriksaan awal dilewati, seperti kembaran yang membacanya sebelum
    yang pertama commit. Yang tersisa hanyalah constraint unik — dan itu
    harus cukup: transaksinya batal, tiket yang sudah ada dikembalikan.
    """
    from app.kiosk_api import KioskServices
    from app.services.queue_service import QueueService

    request_id = str(uuid4())
    pertama = KioskServices().queue.create_queue(
        kategori["A"], perangkat="tablet-aaa", request_id=request_id
    )

    asli = QueueService._tiket_anjungan_terbit
    dilewati = []

    def belum_terlihat(self, kunci, category_id):
        if not dilewati:
            dilewati.append(True)
            return None
        return asli(self, kunci, category_id)

    monkeypatch.setattr(QueueService, "_tiket_anjungan_terbit", belum_terlihat)

    kembar = KioskServices().queue.create_queue(
        kategori["A"], perangkat="tablet-aaa", request_id=request_id
    )

    assert dilewati
    assert kembar.id == pertama.id
    assert _jumlah(Queue) == 1
    with session_scope() as s:
        urut = s.scalar(sa.text("SELECT last_number FROM queue_sequence"))
    assert urut == 1, "kenaikan nomor urut milik transaksi yang batal ikut tersimpan"


# ---------------------------------------------------------------------
# Jeda per perangkat
# ---------------------------------------------------------------------

def test_jeda_menahan_perangkat_yang_sama_saja(kategori):
    klien = _klien()
    tablet_a = _pasang("tablet-aaa-0001")
    tablet_b = _pasang("tablet-bbb-0001")

    def ambil(header: dict[str, str]):
        return klien.post(
            "/v1/kiosk/tickets",
            headers=header,
            json={"category_id": kategori["A"], "request_id": str(uuid4())},
        )

    assert ambil(tablet_a).status_code == 200

    ditahan = ambil(tablet_a)
    assert ditahan.status_code == 409
    assert "tunggu" in ditahan.json()["detail"].lower()

    assert ambil(tablet_b).status_code == 200


def test_sisa_jeda_di_layar_anjungan_per_perangkat(kategori):
    klien = _klien()
    tablet_a = _pasang("tablet-aaa-0001")
    tablet_b = _pasang("tablet-bbb-0001")
    klien.post(
        "/v1/kiosk/tickets",
        headers=tablet_a,
        json={"category_id": kategori["A"], "request_id": str(uuid4())},
    )

    def sisa(header: dict[str, str]) -> float:
        jawab = klien.get("/v1/kiosk/display", headers=header)
        return jawab.json()["cooldown_remaining_seconds"]

    assert sisa(tablet_a) > 0
    assert sisa(tablet_b) == 0


def test_token_bersama_tidak_lolos_jeda_dengan_mengganti_device_id(kategori):
    """X-Device-Id pada token bersama diisi pengirim sendiri; tidak dipercaya."""
    klien = _klien()

    def ambil(perangkat: str):
        return klien.post(
            "/v1/kiosk/tickets",
            headers=_header(perangkat),
            json={"category_id": kategori["A"], "request_id": str(uuid4())},
        )

    assert ambil("tablet-aaa").status_code == 200
    assert ambil("tablet-palsu").status_code == 409
    assert _jumlah(Queue) == 1


def test_permintaan_ulang_dari_hari_lain_ditolak(kategori, monkeypatch):
    """Kunci disimpan seminggu, tetapi nomor kemarin tidak boleh dicetak lagi."""
    from datetime import timedelta

    from app.core import clock

    isi = {"category_id": kategori["A"], "request_id": str(uuid4())}
    assert _klien().post(
        "/v1/kiosk/tickets", headers=_header("tablet-aaa"), json=isi
    ).status_code == 200

    besok = clock.now() + timedelta(days=1)
    monkeypatch.setattr(clock, "now", lambda: besok)
    monkeypatch.setattr(clock, "today", lambda: besok.date())

    ulang = _klien().post("/v1/kiosk/tickets", headers=_header("tablet-aaa"), json=isi)
    assert ulang.status_code == 409
    assert "kedaluwarsa" in ulang.json()["detail"]
    assert _jumlah(Queue) == 1


def test_layar_anjungan_memuat_nomor_menunggu(kategori):
    klien = _klien()
    for perangkat in ("tablet-aaa-0001", "tablet-bbb-0001"):
        klien.post(
            "/v1/kiosk/tickets",
            headers=_pasang(perangkat),
            json={"category_id": kategori["A"], "request_id": str(uuid4())},
        )
    jawab = klien.get("/v1/kiosk/display", headers=_header("tablet-aaa"))
    assert jawab.json()["waiting_queue_numbers"] == ["A-001", "A-002"]


def test_polling_layar_anjungan_tidak_mengulang_query_yang_sama(kategori):
    """Polling satu detik harus tetap ringan meski tablet sudah dipasangkan."""
    from app.core.database import get_engine

    klien = _klien()
    header = _pasang("tablet-hitung-query")
    # Kontak pertama memang mencatat versi/IP perangkat. Ukur polling rutin
    # sesudahnya; pencatatan kontak dibatasi sekali tiap 30 detik.
    assert klien.get("/v1/kiosk/display", headers=header).status_code == 200
    perintah: list[str] = []

    def hitung(_conn, _cursor, statement, *_args):
        perintah.append(" ".join(statement.split()))

    mesin = get_engine()
    sa.event.listen(mesin, "before_cursor_execute", hitung)
    try:
        jawab = klien.get("/v1/kiosk/display", headers=header)
    finally:
        sa.event.remove(mesin, "before_cursor_execute", hitung)

    assert jawab.status_code == 200
    assert len(perintah) <= 10, (
        f"polling anjungan menjalankan {len(perintah)} pernyataan SQL: {perintah}"
    )


# ---------------------------------------------------------------------
# Restart API dari tablet
# ---------------------------------------------------------------------

def test_restart_api_ditolak_untuk_token_bersama(kategori, monkeypatch):
    from app.services import kiosk_server

    dipanggil = []
    monkeypatch.setattr(
        kiosk_server, "jadwalkan_mulai_ulang_layanan_api", lambda: dipanggil.append(1)
    )
    jawab = _klien().post("/v1/kiosk/restart-api", headers=_header("tablet-aaa"))
    assert jawab.status_code == 403
    assert dipanggil == []


def test_restart_api_dibatasi_sekali_per_jeda(kategori, monkeypatch):
    import app.kiosk_api as kiosk_api
    from app.services import kiosk_server

    dipanggil = []
    monkeypatch.setattr(
        kiosk_server, "jadwalkan_mulai_ulang_layanan_api", lambda: dipanggil.append(1)
    )
    sekarang = [1000.0]
    monkeypatch.setattr(kiosk_api.time, "monotonic", lambda: sekarang[0])
    klien = _klien()
    tablet = _pasang("tablet-aaa-0001")

    # API yang baru menyala belum boleh di-restart lagi dari tablet.
    assert klien.post("/v1/kiosk/restart-api", headers=tablet).status_code == 429

    sekarang[0] += kiosk_api.JEDA_RESTART_API_DETIK
    assert klien.post("/v1/kiosk/restart-api", headers=tablet).status_code == 200
    assert klien.post("/v1/kiosk/restart-api", headers=tablet).status_code == 429
    assert dipanggil == [1]
