"""Papan tunggu mini di halaman Pelayanan."""

from __future__ import annotations

from datetime import timedelta

from app.core import clock
from app.ui.queue.papan_tunggu import PapanTunggu


class _Antrian:
    def __init__(self, nomor, kategori_id, nama, menit):
        self.queue_number = nomor
        self.category_id = kategori_id
        self.category_name = nama
        self.created_at = clock.now() - timedelta(minutes=menit)


def test_kolom_per_layanan_dengan_jumlah(qtbot):
    papan = PapanTunggu(10)
    qtbot.addWidget(papan)

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
    papan = PapanTunggu(10)
    qtbot.addWidget(papan)

    papan.setel([], (), clock.now())

    assert papan.judul_kolom == []
    assert papan.label_kosong.isVisibleTo(papan) or not papan.isVisible()
    assert papan.label_total.text() == ""


def test_layanan_di_luar_loket_ditandai_bagian_loket_lain(qtbot):
    papan = PapanTunggu(10)
    qtbot.addWidget(papan)
    papan.setel(
        [_Antrian("A-001", 1, "Konsultasi", 2), _Antrian("B-001", 2, "Pendaftaran", 2)],
        (1,),
        clock.now(),
    )

    teks = [
        papan.kolom.itemAt(i).widget().text() for i in range(papan.kolom.count())
    ]
    assert any("bagian loket lain" in t and "Pendaftaran" in t for t in teks)
    assert not any("bagian loket lain" in t and "Konsultasi" in t for t in teks)


def test_nomor_lama_diberi_penanda(qtbot):
    papan = PapanTunggu(10)
    qtbot.addWidget(papan)
    papan.setel([_Antrian("A-001", 1, "Konsultasi", 15)], (), clock.now())

    teks = papan.kolom.itemAt(0).widget().text()
    assert "15 mnt" in teks
    assert "●" in teks


def test_batas_kolom_menyisakan_ringkasan(qtbot):
    papan = PapanTunggu(10)
    qtbot.addWidget(papan)
    antrian = [_Antrian(f"{c}-001", i, f"Layanan {c}", i) for i, c in enumerate("ABCDEF", 1)]

    papan.setel(antrian, (), clock.now())

    assert len(papan.judul_kolom) == 4
    teks = [papan.kolom.itemAt(i).widget().text() for i in range(papan.kolom.count())]
    assert any("layanan lain" in t for t in teks)
