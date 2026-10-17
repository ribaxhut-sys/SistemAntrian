"""
Ukuran gambar/video anjungan dan keterangan rasionya untuk admin.

Anjungan memutar media dengan rasio terjaga: *Pas* menyisakan pita hitam,
*Isi* memotong tepi. Admin perlu tahu bentuk berkasnya sebelum memilih
"Tampil di" — video tegak di strip panel atas yang mendatar tampak kecil
sekali (Pas) atau hampir habis terpotong (Isi).

Hanya membaca kepala berkas, tanpa ffprobe: gambar lewat Pillow, video
MP4/MOV/3GP/M4V dari kotak `tkhd` ISO BMFF. Format lain (MKV, WebM, AVI)
dilaporkan "tidak diketahui"; itu bukan galat.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from math import gcd
from pathlib import Path

from app.services import daftar_putar

EKSTENSI_BMFF = {".mp4", ".mov", ".3gp", ".m4v"}
EKSTENSI_GAMBAR = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}
#: Kotak yang dimasuki untuk mencari `tkhd`; kotak lain dilompati.
_KOTAK_WADAH = {b"moov", b"trak"}
#: Berkas rusak atau sangat besar tidak dibaca tanpa batas.
_BATAS_KOTAK = 4096

#: Panel atas berupa strip mendatar; berkas lebih tegak dari ini tampak buruk.
RASIO_MIN_PANEL = 1.2


@dataclass(frozen=True)
class Ukuran:
    lebar: int
    tinggi: int

    @property
    def rasio(self) -> float:
        return self.lebar / self.tinggi

    @property
    def label_rasio(self) -> str:
        """16:9, 9:16, 4:3 ... atau desimal bila tidak sederhana."""
        pembagi = gcd(self.lebar, self.tinggi)
        a, b = self.lebar // pembagi, self.tinggi // pembagi
        if a <= 32 and b <= 32:
            return f"{a}:{b}"
        for umum_a, umum_b in ((16, 9), (9, 16), (4, 3), (3, 4), (21, 9), (1, 1)):
            if abs(self.rasio - umum_a / umum_b) < 0.02:
                return f"±{umum_a}:{umum_b}"
        return f"{self.rasio:.2f}:1"


def _ukuran_bmff(berkas) -> Ukuran | None:
    """Lebar × tinggi trek video pertama yang berukuran dari kotak `tkhd`."""
    langkah = 0

    def jelajah(akhir: int | None) -> Ukuran | None:
        nonlocal langkah
        while akhir is None or berkas.tell() < akhir:
            langkah += 1
            if langkah > _BATAS_KOTAK:
                return None
            awal = berkas.tell()
            kepala = berkas.read(8)
            if len(kepala) < 8:
                return None
            panjang, jenis = struct.unpack(">I4s", kepala)
            isi_awal = awal + 8
            if panjang == 1:
                besar = berkas.read(8)
                if len(besar) < 8:
                    return None
                panjang = struct.unpack(">Q", besar)[0]
                isi_awal += 8
            elif panjang == 0:
                return None  # sampai akhir berkas; tidak ada lagi yang dicari
            if panjang < isi_awal - awal:
                return None
            ujung = awal + panjang
            if jenis in _KOTAK_WADAH:
                hasil = jelajah(ujung)
                if hasil is not None:
                    return hasil
            elif jenis == b"tkhd":
                isi = berkas.read(min(panjang - (isi_awal - awal), 128))
                if len(isi) >= 4:
                    versi = isi[0]
                    posisi = 76 if versi == 0 else 88
                    if len(isi) >= posisi + 8:
                        lebar, tinggi = struct.unpack(">II", isi[posisi : posisi + 8])
                        lebar, tinggi = lebar >> 16, tinggi >> 16
                        # Trek suara juga punya tkhd, dengan ukuran 0.
                        if lebar and tinggi:
                            # Matriks rotasi 90°/270° (video ponsel tegak).
                            a, b = struct.unpack(">ii", isi[posisi - 36 : posisi - 28])
                            if a == 0 and b != 0:
                                lebar, tinggi = tinggi, lebar
                            return Ukuran(lebar, tinggi)
            berkas.seek(ujung)
        return None

    return jelajah(None)


def ukuran_media(path: Path) -> Ukuran | None:
    """Ukuran berkas media, atau None bila formatnya tidak terbaca di sini."""
    path = Path(path)
    akhiran = path.suffix.lower()
    try:
        if akhiran in EKSTENSI_GAMBAR:
            from PIL import Image

            with Image.open(path) as gambar:
                lebar, tinggi = gambar.size
            return Ukuran(lebar, tinggi) if lebar and tinggi else None
        if akhiran in EKSTENSI_BMFF:
            with path.open("rb") as berkas:
                return _ukuran_bmff(berkas)
    except (OSError, ValueError, struct.error):
        return None
    return None


def keterangan_rasio(ukuran: Ukuran | None, tampil: str) -> tuple[str, str]:
    """
    (keterangan, peringatan) untuk dialog jadwal; peringatan "" bila aman.

    Bentuk layar tablet tidak diketahui server, jadi layar penuh hanya
    diberi keterangan, bukan peringatan.
    """
    if ukuran is None:
        return (
            "Ukuran berkas tidak terbaca (format ini tidak diperiksa).",
            "",
        )
    arah = "mendatar" if ukuran.rasio > 1.05 else "tegak" if ukuran.rasio < 0.95 else "persegi"
    keterangan = f"{ukuran.lebar} × {ukuran.tinggi} px · {ukuran.label_rasio} ({arah})"
    if tampil in (daftar_putar.TAMPIL_PANEL, daftar_putar.TAMPIL_KEDUANYA) and (
        ukuran.rasio < RASIO_MIN_PANEL
    ):
        return (
            keterangan,
            f"Berkas {arah} di strip panel atas yang mendatar akan tampak kecil "
            "dengan pita lebar (Pas) atau terpotong banyak (Isi). Pertimbangkan "
            "\"Layar penuh\" saja, atau berkas mendatar seperti 16:9.",
        )
    return keterangan, ""
