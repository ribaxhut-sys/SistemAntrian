"""
Sakelar efek grafis — bayangan dan pudar — untuk seluruh aplikasi.

Hanya ada satu keadaan yang menuntutnya: pratinjau totem `--jendela`.
Pratinjau itu membungkus halaman anjungan dalam QGraphicsProxyWidget
supaya kaca 1080×1920 dapat diperkecil utuh ke layar laptop, dan Qt tidak
menggambar QGraphicsEffect dengan benar pada widget di dalam proxy:
kartu layanan yang berbayangan tidak tergambar SAMA SEKALI, dan label
berefek pudar tergambar di tempat dan ukuran yang salah. Pratinjau yang
tanpa kartu layanan tidak bisa dipakai menyimulasikan apa pun.

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
    dipasang langsung dengan `setGraphicsEffect` lolos dari sakelar, dan
    kartunya kembali hilang dari pratinjau totem.
    """
    widget.setGraphicsEffect(efek)
    efek.setEnabled(_aktif)
    return efek
