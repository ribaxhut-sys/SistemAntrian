"""Kilau tombol di halaman Pelayanan menunjuk satu langkah berikutnya."""

from tests import test_ui as _test_ui

# Fixture bersama; ditetapkan sebagai nama modul supaya pytest menemukannya.
halaman_layanan = _test_ui.halaman_layanan


def _siap(qtbot, halaman) -> None:
    halaman.show()
    halaman.muat_ulang()
    qtbot.waitUntil(lambda: halaman.tombol_panggil.isEnabled(), timeout=20_000)


def _berkilau(halaman) -> set[str]:
    return {kunci for kunci, efek in halaman.kilau.items() if efek.berjalan}


def _tunggu_kilau(qtbot, halaman, diharapkan: set[str]) -> None:
    """
    Tunggu sampai kilau mencapai keadaan yang diharapkan.

    Tombol baru menyala setelah aksi dan penyegaran latar selesai, beberapa
    detak sesudah `antrian` terisi. Membaca kilau seketika membuat tes
    bergantung pada kecepatan mesin (gagal di CI yang lebih lambat).
    """
    qtbot.waitUntil(lambda: _berkilau(halaman) == diharapkan, timeout=20_000)


def test_kilau_pada_panggil_berikutnya_saat_loket_kosong(qtbot, halaman_layanan, terbitkan):
    terbitkan("A")
    _siap(qtbot, halaman_layanan)

    _tunggu_kilau(qtbot, halaman_layanan, {"panggil"})


def test_kilau_pindah_ke_panggil_ulang_lalu_ke_lewati(qtbot, halaman_layanan, terbitkan):
    terbitkan("A")
    _siap(qtbot, halaman_layanan)

    halaman_layanan.panggil_berikutnya()
    qtbot.waitUntil(lambda: halaman_layanan.antrian is not None, timeout=20_000)
    _tunggu_kilau(qtbot, halaman_layanan, {"panggil_ulang"})

    halaman_layanan.panggil_ulang()
    qtbot.waitUntil(lambda: halaman_layanan.antrian.jumlah_panggilan == 2, timeout=20_000)
    _tunggu_kilau(qtbot, halaman_layanan, {"panggil_ulang"})

    halaman_layanan.panggil_ulang()  # panggilan ketiga: batas tercapai
    qtbot.waitUntil(lambda: halaman_layanan.antrian.jumlah_panggilan == 3, timeout=20_000)
    _tunggu_kilau(qtbot, halaman_layanan, {"lewati"})


def test_kilau_mati_saat_nomor_sedang_dilayani(qtbot, halaman_layanan, terbitkan):
    terbitkan("A")
    _siap(qtbot, halaman_layanan)
    halaman_layanan.panggil_berikutnya()
    qtbot.waitUntil(lambda: halaman_layanan.antrian is not None, timeout=20_000)
    halaman_layanan.aksi["mulai_layani"].click()
    qtbot.waitUntil(
        lambda: halaman_layanan.antrian.status.name == "SERVING", timeout=20_000
    )

    _tunggu_kilau(qtbot, halaman_layanan, set())


def test_kilau_tidak_menangkap_klik(qtbot, halaman_layanan, terbitkan):
    from PySide6.QtCore import Qt

    terbitkan("A")
    _siap(qtbot, halaman_layanan)
    efek = halaman_layanan.kilau["panggil"]

    assert efek.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
