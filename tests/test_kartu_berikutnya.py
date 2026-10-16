"""Kartu "Berikutnya & hari ini" di halaman Pelayanan."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from app.core import clock
from app.models import QueueStatus
from app.ui.queue.kartu_berikutnya import KartuBerikutnya


class _Antrian:
    def __init__(self, nomor, kategori_id, nama, menit, prioritas=None):
        self.prioritas = prioritas
        self.queue_number = nomor
        self.category_id = kategori_id
        self.category_name = nama
        self.created_at = clock.now() - timedelta(minutes=menit)


def _ringkasan(selesai=14, rata="6 mnt", riwayat=()):
    return SimpleNamespace(
        selesai=selesai, label_rata_layanan=rata, riwayat=list(riwayat)
    )


def _kartu(qtbot, lebar=420, tinggi=200):
    kartu = KartuBerikutnya(10)
    qtbot.addWidget(kartu)
    kartu.resize(lebar, tinggi)
    kartu.show()
    return kartu


def test_menampilkan_tiga_nomor_berikutnya_sesuai_urutan_panggil(qtbot):
    kartu = _kartu(qtbot, tinggi=240)
    kartu.setel(
        [
            _Antrian("A-001", 1, "Konsultasi", 12),
            _Antrian("B-001", 2, "Pengaduan", 8),
            _Antrian("A-003", 1, "Konsultasi", 2),
            _Antrian("A-004", 1, "Konsultasi", 1),
        ],
        (),
        clock.now(),
        _ringkasan(),
    )

    teks = "\n".join(kartu.baris_tampil)
    assert teks.index("A-001") < teks.index("B-001") < teks.index("A-003")
    assert "A-004" not in teks
    assert "+1 lagi menunggu" in teks


def test_hanya_layanan_milik_loket_ini(qtbot):
    kartu = _kartu(qtbot, tinggi=240)
    kartu.setel(
        [_Antrian("A-001", 1, "Konsultasi", 5), _Antrian("B-001", 2, "Pengaduan", 9)],
        (2,),
        clock.now(),
        None,
    )

    teks = "\n".join(kartu.baris_tampil)
    assert "B-001" in teks
    assert "A-001" not in teks


def test_ringkasan_hari_ini_dan_terakhir_selesai(qtbot):
    kartu = _kartu(qtbot, tinggi=300)
    waktu = clock.now().replace(hour=8, minute=52, second=0, microsecond=0)
    riwayat = [
        SimpleNamespace(nomor="A-004", status=QueueStatus.COMPLETED, waktu=waktu),
        SimpleNamespace(
            nomor="A-002",
            status=QueueStatus.COMPLETED,
            waktu=waktu - timedelta(minutes=30),
        ),
    ]
    kartu.setel([], (), clock.now(), _ringkasan(14, "6 mnt", riwayat))

    teks = "\n".join(kartu.baris_tampil)
    assert "dilayani 14" in teks
    assert "rata-rata 6 mnt" in teks
    assert "A-004 · 08:52" in teks
    assert "Tidak ada nomor menunggu" in teks


def test_ruang_sempit_menyisakan_yang_terpenting(qtbot):
    kartu = _kartu(qtbot, tinggi=44 + 40)  # dua baris
    kartu.setel(
        [_Antrian("A-001", 1, "Konsultasi", 5), _Antrian("A-002", 1, "Konsultasi", 3)],
        (),
        clock.now(),
        _ringkasan(),
    )

    assert len(kartu.baris_tampil) == 2
    # Nomor berikutnya pertama dan ringkasan hari ini didahulukan.
    assert "A-001" in kartu.baris_tampil[0]
    assert "dilayani" in kartu.baris_tampil[1]


def test_terlalu_sempit_kartu_tidak_digambar(qtbot):
    kartu = _kartu(qtbot, tinggi=30)
    kartu.setel([_Antrian("A-001", 1, "Konsultasi", 5)], (), clock.now(), _ringkasan())

    assert kartu.kecil is True
    assert kartu.label.text() == ""


def test_nomor_lama_diberi_penanda(qtbot):
    kartu = _kartu(qtbot, tinggi=240)
    kartu.setel([_Antrian("A-001", 1, "Konsultasi", 15)], (), clock.now(), None)

    assert "●" in kartu.baris_tampil[0]
    assert "15 mnt" in kartu.baris_tampil[0]


def test_nomor_prioritas_ditandai_bintang(qtbot):
    kartu = _kartu(qtbot, tinggi=240)
    kartu.setel(
        [
            _Antrian("A-002", 1, "Konsultasi", 3, prioritas="LANSIA"),
            _Antrian("A-001", 1, "Konsultasi", 9),
        ],
        (),
        clock.now(),
        None,
    )

    assert "★ A-002" in kartu.baris_tampil[0]
    assert "★" not in kartu.baris_tampil[1]
