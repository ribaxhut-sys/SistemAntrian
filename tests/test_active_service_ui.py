"""Halaman admin untuk pelayanan yang ditinggalkan petugas."""

from __future__ import annotations

from app.models import QueueStatus
from app.services.queue_service import QueueService, TransferTargetInfo
from app.services.user_service import UserService
from app.ui.settings.active_service_page import ActiveServicePage
from tests.conftest import TEST_PASSWORD


def test_admin_dapat_mengalihkan_dari_halaman_pelayanan_aktif(
    qtbot, auth, antrian_siap, terbitkan, monkeypatch
):
    lama, tujuan = antrian_siap["loket"][:2]
    target_id = UserService(auth).create_user(
        username="cro_pengganti_ui",
        full_name="Petugas Pengganti UI",
        password=TEST_PASSWORD,
        role="CRO",
        must_change_password=False,
        default_counter_id=tujuan,
    )

    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    terbitkan("A")
    aktif = QueueService(auth).call_next(lama)
    QueueService(auth).start_service(aktif.id)

    auth.logout()
    auth.login("admin", TEST_PASSWORD)
    halaman = ActiveServicePage(QueueService(auth))
    qtbot.addWidget(halaman)
    assert halaman.tabel.rowCount() == 1

    indeks_target = next(
        indeks
        for indeks in range(halaman.pilih_petugas.count())
        if isinstance(
            halaman.pilih_petugas.itemData(indeks), TransferTargetInfo
        )
        and halaman.pilih_petugas.itemData(indeks).user_id == target_id
    )
    halaman.pilih_petugas.setCurrentIndex(indeks_target)
    halaman.input_alasan.setText("Petugas sebelumnya sudah pulang")
    assert halaman.tombol_alihkan.isEnabled()

    monkeypatch.setattr(
        "app.ui.settings.active_service_page.konfirmasi", lambda *_args: True
    )
    monkeypatch.setattr(
        "app.ui.settings.active_service_page.tampilkan_info", lambda *_args: None
    )
    halaman.tombol_alihkan.click()

    hasil = QueueService(auth).list_pelayanan_aktif()
    assert len(hasil) == 1
    assert hasil[0].id == aktif.id
    assert hasil[0].status is QueueStatus.PAUSED
    assert hasil[0].counter_id == tujuan
    assert hasil[0].served_by_id == target_id


def test_tombol_admin_memerlukan_antrian_target_dan_alasan(
    qtbot, admin_auth, antrian_siap
):
    halaman = ActiveServicePage(QueueService(admin_auth))
    qtbot.addWidget(halaman)

    assert not halaman.tombol_alihkan.isEnabled()
    assert not halaman.tombol_batal.isEnabled()


def test_penyegaran_otomatis_tidak_memblokir_thread_ui(
    qtbot, admin_auth, monkeypatch
):
    import threading

    layanan = QueueService(admin_auth)
    halaman = ActiveServicePage(layanan)
    qtbot.addWidget(halaman)
    mulai = threading.Event()
    lanjut = threading.Event()

    def lambat():
        mulai.set()
        lanjut.wait(2)
        return []

    monkeypatch.setattr(layanan, "list_pelayanan_aktif", lambat)
    monkeypatch.setattr(layanan, "list_tujuan_pengalihan", lambda: [])

    halaman.show()
    try:
        qtbot.waitUntil(mulai.is_set, timeout=1_000)
        assert halaman._pekerja is not None
        assert halaman._pekerja.isRunning()
    finally:
        lanjut.set()

    qtbot.waitUntil(lambda: halaman._pekerja is None, timeout=3_000)
