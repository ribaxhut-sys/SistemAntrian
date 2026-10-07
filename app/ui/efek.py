"""
Sakelar efek grafis — bayangan dan pudar — untuk seluruh aplikasi.

Dahulu dimatikan untuk pratinjau totem anjungan Windows, yang membungkus
halamannya dalam QGraphicsProxyWidget — dan Qt tidak menggambar
QGraphicsEffect dengan benar di dalam proxy. Anjungan Windows sudah
dihapus (docs/istilah.md), jadi sakelarnya kini selalu menyala; titik
pemasangan tunggal `pasang_efek` tetap dipertahankan.

Efeknya tetap DIPASANG, hanya dinonaktifkan. Kode lain memegang efek itu:
animasi pudar menganimasikan opacity-nya, dan panel sambutan melepas lalu
memulihkan bayangannya setiap kali video diputar. Efek yang tidak pernah
dipasang akan membuat semua itu menunjuk None; efek yang nonaktif tetap
hidup, hanya tidak digambar.

Modul ini sengaja tidak mengimpor Qt, supaya `--init-only` dan test
non-UI tetap tidak menyentuh PySide6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QGraphicsEffect, QWidget

_aktif = True


def efek_grafis_aktif() -> bool:
    """True bila bayangan dan efek pudar boleh digambar."""
    return _aktif


def setel_efek_grafis(aktif: bool) -> None:
    """Nyalakan atau matikan efek grafis untuk widget yang dibuat sesudahnya."""
    global _aktif
    _aktif = aktif


def pasang_efek(widget: QWidget, efek: QGraphicsEffect) -> QGraphicsEffect:
    """
    Pasang `efek` pada `widget`, dan nonaktifkan bila sakelarnya mati.

    Satu-satunya jalan memasang efek grafis di aplikasi ini. Efek yang
    dipasang langsung dengan `setGraphicsEffect` lolos dari sakelar.
    """
    widget.setGraphicsEffect(efek)
    efek.setEnabled(_aktif)
    return efek
