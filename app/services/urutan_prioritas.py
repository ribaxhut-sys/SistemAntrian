"""
Urutan panggil dengan nomor prioritas (lansia, disabilitas, ibu hamil).

Fungsi murni tanpa database, dipakai service pemanggilan dan pratinjau
"berikutnya" di layar petugas supaya keduanya tidak berselisih.

Aturan otomatis: nomor prioritas dipanggil lebih dulu, tetapi setiap
`rasio` nomor prioritas yang berturut-turut dipanggil, satu nomor biasa
disisipkan bila ada yang menunggu. `rasio` 0 berarti prioritas selalu lebih
dulu. Di dalam tiap kelompok urutannya tetap siapa datang lebih dahulu.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar

MODE_OTOMATIS = "otomatis"
MODE_PRIORITAS = "prioritas"
MODE_BIASA = "biasa"
MODE_SAH = (MODE_OTOMATIS, MODE_PRIORITAS, MODE_BIASA)


class _Berprioritas(Protocol):
    prioritas: str | None


T = TypeVar("T", bound=_Berprioritas)


def susun(
    menunggu: Sequence[T],
    *,
    rasio: int,
    beruntun: int = 0,
    mode: str = MODE_OTOMATIS,
) -> list[T]:
    """
    Urutan calon panggil.

    `menunggu` sudah urut siapa datang lebih dahulu. `beruntun` adalah
    banyaknya nomor prioritas yang baru saja dipanggil berturut-turut.
    Hasilnya memuat semua calon; yang pertama adalah yang dipanggil.
    """
    if mode not in MODE_SAH:
        raise ValueError(f"Mode urutan tidak dikenal: {mode}")
    prioritas = [a for a in menunggu if a.prioritas]
    biasa = [a for a in menunggu if not a.prioritas]
    if mode == MODE_PRIORITAS:
        return prioritas + biasa
    if mode == MODE_BIASA:
        return biasa + prioritas
    if not prioritas or not biasa:
        return list(menunggu)

    hasil: list[T] = []
    p, b = list(prioritas), list(biasa)
    hitung = max(0, beruntun)
    while p or b:
        giliran_biasa = bool(b) and (not p or (rasio > 0 and hitung >= rasio))
        if giliran_biasa:
            hasil.append(b.pop(0))
            hitung = 0
        else:
            hasil.append(p.pop(0))
            hitung += 1
    return hasil
