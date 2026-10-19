"""Petugas keluar dan pengambilalihan pelayanan oleh petugas lain.

Aturan yang dijaga:
- CALLED dikembalikan ke WAITING saat petugas keluar (dapat dipanggil siapa pun);
- SERVING dan PAUSED tetap aktif, lalu dilaporkan agar petugas diberi tahu;
- petugas lain mengambil alih tanpa QUEUE_REASSIGN, status dan waktu mulai
  dipertahankan, tidak lintas cabang, dan tidak pernah oleh dua orang.
"""

from __future__ import annotations

import json
import threading

import pytest

from app.core.errors import AppError, AuthorizationError, BusinessRuleError
from app.models import QueueStatus
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.queue_service import QueueService
from app.services.user_service import UserService
from tests.conftest import TEST_PASSWORD


def _petugas_baru(username: str, loket_id: int, *, branch_id: int | None = None) -> AuthService:
    """Buat akun CRO dengan loket bawaan, lalu kembalikan sesinya yang sudah masuk."""
    admin = AuthService()
    admin.login("admin", TEST_PASSWORD)
    UserService(admin).create_user(
        username=username,
        full_name=f"Petugas {username}",
        password=TEST_PASSWORD,
        role="CRO",
        must_change_password=False,
        default_counter_id=loket_id,
        branch_id=branch_id,
    )
    admin.logout()
    sesi = AuthService()
    sesi.login(username, TEST_PASSWORD)
    return sesi


def _aksi_audit(aksi: str) -> list:
    return [e for e in audit_service.list_terakhir(batas=50) if e.action == aksi]


# ---------------------------------------------------------------------
# Keluar
# ---------------------------------------------------------------------

def test_keluar_mengembalikan_called_ke_waiting_dan_mencatat_audit(
    cro_queue, terbitkan, antrian_siap
):
    loket = antrian_siap["loket"][0]
    terbitkan("A")
    aktif = cro_queue.call_next(loket)
    assert aktif.status is QueueStatus.CALLED

    masih = cro_queue.siapkan_logout_petugas()

    assert masih == []
    baru = cro_queue.get_queue(aktif.id)
    assert baru.status is QueueStatus.WAITING
    assert baru.counter_id is None
    assert baru.served_by_id is None
    assert aktif.id in {q.id for q in cro_queue.list_waiting()}
    entri = _aksi_audit("RETURN_QUEUE_TO_WAITING")
    assert len(entri) == 1
    assert entri[0].entity_id == aktif.id


def test_nomor_yang_dikembalikan_dapat_dipanggil_petugas_lain(
    cro_queue, terbitkan, antrian_siap
):
    lama, lain = antrian_siap["loket"][:2]
    terbitkan("A")
    aktif = cro_queue.call_next(lama)
    cro_queue.siapkan_logout_petugas()

    petugas_lain = _petugas_baru("cro_lain", lain)
    hasil = QueueService(petugas_lain).call_next(lain)

    assert hasil.id == aktif.id
    assert hasil.status is QueueStatus.CALLED
    assert hasil.counter_id == lain


@pytest.mark.parametrize("jeda", [False, True])
def test_keluar_membiarkan_serving_dan_paused_tetap_aktif(
    cro_queue, terbitkan, antrian_siap, jeda
):
    loket = antrian_siap["loket"][0]
    terbitkan("A")
    aktif = cro_queue.call_next(loket)
    cro_queue.start_service(aktif.id)
    if jeda:
        cro_queue.pause(aktif.id)
    mulai_sebelum = cro_queue.current_for_counter(loket).serving_at

    masih = cro_queue.siapkan_logout_petugas()

    assert masih == [aktif.queue_number]
    sekarang = cro_queue.current_for_counter(loket)
    assert sekarang.id == aktif.id
    assert sekarang.status is (QueueStatus.PAUSED if jeda else QueueStatus.SERVING)
    assert sekarang.serving_at == mulai_sebelum
    assert _aksi_audit("RETURN_QUEUE_TO_WAITING") == []


def test_keluar_tanpa_nomor_aktif_tidak_melakukan_apa_apa(cro_queue, antrian_siap):
    assert cro_queue.siapkan_logout_petugas() == []
    assert _aksi_audit("RETURN_QUEUE_TO_WAITING") == []


def test_keluar_tidak_menyentuh_nomor_milik_petugas_lain(
    cro_queue, terbitkan, antrian_siap
):
    lama, lain = antrian_siap["loket"][:2]
    terbitkan("A", 2)
    milik_lain = QueueService(_petugas_baru("cro_lain", lain)).call_next(lain)
    milik_sendiri = cro_queue.call_next(lama)

    cro_queue.siapkan_logout_petugas()

    assert cro_queue.get_queue(milik_lain.id).status is QueueStatus.CALLED
    assert cro_queue.get_queue(milik_sendiri.id).status is QueueStatus.WAITING
    waiting_id = {q.id for q in cro_queue.list_waiting()}
    assert milik_sendiri.id in waiting_id
    assert milik_lain.id not in waiting_id


# ---------------------------------------------------------------------
# Ambil alih
# ---------------------------------------------------------------------

def _serving_ditinggal(cro_queue, terbitkan, loket, *, jeda=False):
    terbitkan("A")
    aktif = cro_queue.call_next(loket)
    cro_queue.start_service(aktif.id)
    if jeda:
        cro_queue.pause(aktif.id)
    aktif = cro_queue.current_for_counter(loket)
    cro_queue.siapkan_logout_petugas()
    cro_queue.auth.logout()  # sesudah logout tanda hadir loket dilepas
    return aktif


def _masuk_ulang(cro_queue):
    cro_queue.auth.login("cro", TEST_PASSWORD)


@pytest.mark.parametrize("jeda", [False, True])
def test_petugas_lain_mengambil_alih_tanpa_queue_reassign(
    cro_queue, terbitkan, antrian_siap, jeda
):
    lama, baru = antrian_siap["loket"][:2]
    aktif = _serving_ditinggal(cro_queue, terbitkan, lama, jeda=jeda)
    sebelum = aktif
    pengganti = _petugas_baru("cro_pengganti", baru)
    layanan = QueueService(pengganti)
    from app.services.permissions import Permission

    assert not pengganti.has_permission(Permission.QUEUE_REASSIGN)

    hasil = layanan.ambil_alih_pelayanan(aktif.id)

    assert hasil.status is sebelum.status
    assert hasil.serving_at == sebelum.serving_at
    assert hasil.counter_id == baru
    assert hasil.served_by_name == "Petugas cro_pengganti"
    assert layanan.current_for_counter(baru).id == aktif.id
    entri = _aksi_audit("REASSIGN_QUEUE")
    assert len(entri) == 1
    meta = json.loads(entri[0].meta)
    assert meta["petugas_baru_id"] == hasil.served_by_id
    assert meta["petugas_lama"]


def test_pemilik_lama_tidak_dapat_lagi_menyelesaikan_nomor_setelah_diambil_alih(
    cro_queue, terbitkan, antrian_siap
):
    lama, baru = antrian_siap["loket"][:2]
    aktif = _serving_ditinggal(cro_queue, terbitkan, lama)
    QueueService(_petugas_baru("cro_pengganti", baru)).ambil_alih_pelayanan(aktif.id)

    _masuk_ulang(cro_queue)
    with pytest.raises(AppError):
        cro_queue.complete(aktif.id)


def test_ambil_alih_ditolak_untuk_nomor_called_waiting_atau_selesai(
    cro_queue, terbitkan, antrian_siap
):
    lama, baru = antrian_siap["loket"][:2]
    terbitkan("A", 2)
    called = cro_queue.call_next(lama)
    pengganti = QueueService(_petugas_baru("cro_pengganti", baru))

    with pytest.raises(BusinessRuleError):
        pengganti.ambil_alih_pelayanan(called.id)

    cro_queue.start_service(called.id)
    cro_queue.complete(called.id)
    with pytest.raises(BusinessRuleError):
        pengganti.ambil_alih_pelayanan(called.id)


def test_ambil_alih_ditolak_bila_petugas_masih_memegang_nomor_lain(
    cro_queue, terbitkan, antrian_siap
):
    lama, baru = antrian_siap["loket"][:2]
    aktif = _serving_ditinggal(cro_queue, terbitkan, lama)
    pengganti_auth = _petugas_baru("cro_pengganti", baru)
    pengganti = QueueService(pengganti_auth)
    terbitkan("A")
    pengganti.call_next(baru)

    with pytest.raises(BusinessRuleError):
        pengganti.ambil_alih_pelayanan(aktif.id)
    _masuk_ulang(cro_queue)
    assert cro_queue.current_for_counter(lama).id == aktif.id


def test_ambil_alih_ditolak_tanpa_loket_bawaan(cro_queue, terbitkan, antrian_siap):
    lama = antrian_siap["loket"][0]
    aktif = _serving_ditinggal(cro_queue, terbitkan, lama)
    admin = AuthService()
    admin.login("admin", TEST_PASSWORD)
    UserService(admin).create_user(
        username="cro_tanpa_loket", full_name="Tanpa Loket",
        password=TEST_PASSWORD, role="CRO", must_change_password=False,
    )
    tanpa = AuthService()
    tanpa.login("cro_tanpa_loket", TEST_PASSWORD)

    with pytest.raises(BusinessRuleError, match="loket bawaan"):
        QueueService(tanpa).ambil_alih_pelayanan(aktif.id)


@pytest.mark.parametrize("peran", ["registration", "supervisor"])
def test_peran_tanpa_hak_memanggil_tidak_dapat_mengambil_alih(
    cro_queue, terbitkan, antrian_siap, auth, peran
):
    aktif = _serving_ditinggal(cro_queue, terbitkan, antrian_siap["loket"][0])
    asing = AuthService()
    asing.login(peran, TEST_PASSWORD)

    with pytest.raises(AuthorizationError):
        QueueService(asing).ambil_alih_pelayanan(aktif.id)


def test_ambil_alih_tidak_dapat_menjangkau_nomor_cabang_lain(
    cro_queue, terbitkan, antrian_siap
):
    from app.core.database import session_scope
    from app.models import Branch, Counter, RecordStatus

    aktif = _serving_ditinggal(cro_queue, terbitkan, antrian_siap["loket"][0])
    with session_scope() as s:
        cabang = Branch(code="CAB2", name="Cabang Dua", status=RecordStatus.ACTIVE)
        s.add(cabang)
        s.flush()
        loket = Counter(
            branch_id=cabang.id, code="X1", name="Loket Cabang Dua",
            status=RecordStatus.ACTIVE,
        )
        s.add(loket)
        s.flush()
        cabang_id, loket_id = cabang.id, loket.id
    asing = _petugas_baru("cro_cab2", loket_id, branch_id=cabang_id)

    with pytest.raises(BusinessRuleError, match="tidak lagi dapat diambil alih"):
        QueueService(asing).ambil_alih_pelayanan(aktif.id)
    _masuk_ulang(cro_queue)
    assert cro_queue.current_for_counter(antrian_siap["loket"][0]).id == aktif.id


def test_dua_petugas_berebut_nomor_yang_sama_hanya_satu_menang(
    cro_queue, terbitkan, antrian_siap
):
    lama, a, b = antrian_siap["loket"][:3]
    aktif = _serving_ditinggal(cro_queue, terbitkan, lama)
    layanan = [
        QueueService(_petugas_baru("cro_a", a)),
        QueueService(_petugas_baru("cro_b", b)),
    ]
    gerbang = threading.Barrier(2)
    hasil: list[object] = []

    def rebut(svc: QueueService) -> None:
        gerbang.wait()
        try:
            hasil.append(svc.ambil_alih_pelayanan(aktif.id))
        except AppError as exc:
            hasil.append(exc)

    utas = [threading.Thread(target=rebut, args=(s,)) for s in layanan]
    for t in utas:
        t.start()
    for t in utas:
        t.join(timeout=30)

    menang = [h for h in hasil if not isinstance(h, Exception)]
    assert len(hasil) == 2
    # Yang kedua melihat pemilik baru: ia boleh mengambil alih lagi (nomor
    # memang masih SERVING), tetapi tidak pernah ada dua pemilik sekaligus.
    pemilik = {
        QueueService(layanan[i].auth).current_for_counter(c)
        for i, c in enumerate((a, b))
    }
    pemilik_ada = [p for p in pemilik if p is not None]
    assert len(pemilik_ada) == 1
    assert len(menang) >= 1
    assert len(_aksi_audit("REASSIGN_QUEUE")) == len(menang)


# ---------------------------------------------------------------------
# Pemilik lama masih hadir
# ---------------------------------------------------------------------

def test_tidak_dapat_merebut_nomor_dari_petugas_yang_masih_hadir(
    cro_queue, terbitkan, antrian_siap
):
    """Pengambilalihan untuk nomor yang ditinggal, bukan untuk merebut."""
    lama, baru = antrian_siap["loket"][:2]
    cro_queue.auth.pindah_loket(lama)  # loket bawaan memasang tanda hadir
    terbitkan("A")
    aktif = cro_queue.call_next(lama)
    cro_queue.start_service(aktif.id)  # pemilik tetap masuk dan hadir
    cro_queue.auth.tanda_hadir_loket()  # denyut berkala MainWindow
    pengganti = QueueService(_petugas_baru("cro_pengganti", baru))

    with pytest.raises(BusinessRuleError, match="masih hadir"):
        pengganti.ambil_alih_pelayanan(aktif.id)

    assert cro_queue.current_for_counter(lama).id == aktif.id
    assert _aksi_audit("REASSIGN_QUEUE") == []


def test_dapat_mengambil_alih_setelah_tanda_hadir_pemilik_basi(
    cro_queue, terbitkan, antrian_siap
):
    """Komputer pemilik mati mendadak: tanda hadir tidak diperbarui lagi."""
    from datetime import timedelta

    import sqlalchemy as sa

    from app.core import clock
    from app.core.database import session_scope
    from app.models import Counter
    from app.services.queue_service import BATAS_HADIR_PETUGAS_DETIK

    lama, baru = antrian_siap["loket"][:2]
    cro_queue.auth.pindah_loket(lama)
    terbitkan("A")
    aktif = cro_queue.call_next(lama)
    cro_queue.start_service(aktif.id)
    cro_queue.auth.tanda_hadir_loket()
    with session_scope() as s:
        s.execute(
            sa.update(Counter)
            .where(Counter.id == lama)
            .values(
                petugas_terlihat_pada=clock.now()
                - timedelta(seconds=BATAS_HADIR_PETUGAS_DETIK + 5)
            )
        )

    hasil = QueueService(_petugas_baru("cro_pengganti", baru)).ambil_alih_pelayanan(aktif.id)

    assert hasil.counter_id == baru


# ---------------------------------------------------------------------
# Peran tanpa hak memanggil harus tetap bisa keluar
# ---------------------------------------------------------------------

@pytest.mark.parametrize("peran", ["admin", "supervisor", "registration"])
def test_peran_tanpa_hak_memanggil_dapat_keluar_tanpa_galat(
    auth, antrian_siap, peran
):
    """Tidak ada nomor yang perlu dikembalikan; keluar tidak boleh tertahan."""
    auth.logout()
    auth.login(peran, TEST_PASSWORD)

    assert QueueService(auth).siapkan_logout_petugas() == []


@pytest.mark.parametrize("peran", ["admin", "supervisor", "registration"])
def test_jendela_menutup_tanpa_dialog_untuk_peran_tanpa_hak_memanggil(
    qtbot, auth, antrian_siap, monkeypatch, peran
):
    from app.ui.main_window import MainWindow

    dialog: list[str] = []
    monkeypatch.setattr(
        "app.ui.main_window.tampilkan_peringatan",
        lambda parent, pesan, judul="": dialog.append(pesan) or None,
    )
    auth.logout()
    auth.login(peran, TEST_PASSWORD)
    jendela = MainWindow(auth)
    qtbot.addWidget(jendela)

    jendela.close()

    assert dialog == []
    assert jendela._ditutup
