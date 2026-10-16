"""Papan tunggu mini di halaman Pelayanan."""

from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import Qt

from app.core import clock
from app.ui.queue.papan_tunggu import PapanTunggu


class _Antrian:
    def __init__(self, nomor, kategori_id, nama, menit):
        self.queue_number = nomor
        self.category_id = kategori_id
        self.category_name = nama
        self.created_at = clock.now() - timedelta(minutes=menit)


def _papan(qtbot, lebar=520, tinggi=260):
    papan = PapanTunggu(10)
    qtbot.addWidget(papan)
    papan.resize(lebar, tinggi)
    papan.show()
    return papan


def _kartu(papan):
    return [papan.grid.itemAt(i).widget() for i in range(papan.grid.count())]


def test_kartu_per_layanan_dengan_jumlah(qtbot):
    papan = _papan(qtbot)

    papan.setel(
        [
            _Antrian("A-001", 1, "Konsultasi", 12),
            _Antrian("A-002", 1, "Konsultasi", 5),
            _Antrian("B-001", 2, "Pendaftaran", 1),
        ],
        (),
        clock.now(),
    )

    assert papan.judul_kolom == ["Konsultasi (2)", "Pendaftaran (1)"]
    assert papan.label_total.text() == "3 menunggu"
    assert not papan.label_kosong.isVisibleTo(papan)


def test_papan_kosong_menyatakan_terus_terang(qtbot):
    papan = _papan(qtbot)

    papan.setel([], (), clock.now())

    assert papan.judul_kolom == []
    assert papan.label_kosong.isVisibleTo(papan)
    assert papan.label_total.text() == ""


def test_layanan_di_luar_loket_ditandai_dan_diurutkan_belakangan(qtbot):
    papan = _papan(qtbot)
    papan.setel(
        [_Antrian("B-001", 2, "Pendaftaran", 30), _Antrian("A-001", 1, "Konsultasi", 2)],
        (1,),
        clock.now(),
    )

    # Layanan milik loket ini lebih dulu, walau yang lain menunggu lebih lama.
    assert papan.judul_kolom == ["Konsultasi (1)", "Pendaftaran (1)"]
    assert "loket lain" in papan.teks_kartu[1]
    assert "loket lain" not in papan.teks_kartu[0]


def test_nomor_lama_diberi_penanda(qtbot):
    papan = _papan(qtbot)
    papan.setel([_Antrian("A-001", 1, "Konsultasi", 15)], (), clock.now())

    assert "15 mnt" in papan.teks_kartu[0]
    assert "●" in papan.teks_kartu[0]


def test_semua_layanan_ada_antrian_tampil_bukan_empat_saja(qtbot):
    papan = _papan(qtbot, lebar=720, tinggi=260)
    antrian = [
        _Antrian(f"L{i}-001", i, f"Layanan {i}", i) for i in range(1, 11)
    ]

    papan.setel(antrian, (), clock.now())
    qtbot.wait(30)

    assert len(papan.judul_kolom) == 10
    assert "layanan lain" not in papan.label_total.text()
    # Tidak ada kartu yang keluar dari papan.
    for kartu in _kartu(papan):
        assert papan.rect().contains(kartu.geometry())


def test_isi_kartu_meringkas_saat_ruang_sempit(qtbot):
    papan = _papan(qtbot, lebar=720, tinggi=130)
    antrian = [
        _Antrian(f"L{i}-001", i, f"Layanan {i}", i) for i in range(1, 8)
    ]

    papan.setel(antrian, (), clock.now())

    assert len(papan.judul_kolom) == 7
    assert all("<br>" not in teks for teks in papan.teks_kartu)


def test_kelebihan_kapasitas_disebut_di_kepala(qtbot):
    papan = _papan(qtbot, lebar=340, tinggi=110)
    antrian = [
        _Antrian(f"L{i}-001", i, f"Layanan {i}", i) for i in range(1, 13)
    ]

    papan.setel(antrian, (), clock.now())

    assert len(papan.judul_kolom) < 12
    assert "layanan lain" in papan.label_total.text()


def test_nomor_berikutnya_tampil_saat_kartu_tinggi(qtbot):
    papan = _papan(qtbot, lebar=520, tinggi=300)
    papan.setel(
        [_Antrian("A-001", 1, "Konsultasi", 9), _Antrian("A-002", 1, "Konsultasi", 3)],
        (),
        clock.now(),
    )

    assert "A-002" in papan.teks_kartu[0]


def test_kartu_semua_selalu_ada_dan_terpilih_bawaan(qtbot):
    papan = _papan(qtbot)
    papan.setel(
        [_Antrian("A-001", 1, "Konsultasi", 4), _Antrian("B-001", 2, "Pengaduan", 9)],
        (),
        clock.now(),
    )

    assert papan.kartu_semua is not None
    assert papan.pilihan is None
    assert "Semua" in papan.kartu_semua.text()
    assert "(2)" in papan.kartu_semua.text()
    assert "B-001" in papan.kartu_semua.text()  # terlama dari semua layanan
    # Kartu "Semua" bukan layanan: tidak ikut daftar judul layanan.
    assert papan.judul_kolom == ["Pengaduan (1)", "Konsultasi (1)"]


def test_klik_kartu_memilih_layanan_dan_klik_semua_mencabutnya(qtbot):
    papan = _papan(qtbot)
    papan.setel(
        [_Antrian("A-001", 1, "Konsultasi", 4), _Antrian("B-001", 2, "Pengaduan", 9)],
        (),
        clock.now(),
    )
    qtbot.wait(30)

    dengan_sinyal = []
    papan.layananDipilih.connect(dengan_sinyal.append)

    qtbot.mouseClick(papan.kartu_layanan[2], Qt.MouseButton.LeftButton)
    assert papan.pilihan == 2
    assert dengan_sinyal == [2]

    qtbot.mouseClick(papan.kartu_semua, Qt.MouseButton.LeftButton)
    assert papan.pilihan is None
    assert dengan_sinyal == [2, None]


def test_pilihan_kembali_ke_semua_bila_layanan_sudah_kosong(qtbot):
    papan = _papan(qtbot)
    papan.setel(
        [_Antrian("A-001", 1, "Konsultasi", 4), _Antrian("B-001", 2, "Pengaduan", 9)],
        (),
        clock.now(),
    )
    papan.pilih(2)

    papan.setel([_Antrian("A-001", 1, "Konsultasi", 5)], (), clock.now())

    assert papan.pilihan is None


def test_pilihan_bertahan_saat_data_disegarkan(qtbot):
    papan = _papan(qtbot)
    data = [_Antrian("A-001", 1, "Konsultasi", 4), _Antrian("B-001", 2, "Pengaduan", 9)]
    papan.setel(data, (), clock.now())
    papan.pilih(1)

    papan.setel(data, (), clock.now())

    assert papan.pilihan == 1
    assert papan.kartu_layanan[1].property("terpilih") is True
