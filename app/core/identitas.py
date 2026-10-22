"""Identitas tetap aplikasi: produk dan instansi pemiliknya.

Sengaja konstanta di kode, bukan pengaturan di database: admin kantor tidak
boleh mengubahnya dari menu mana pun. Ubah hanya di sini, lalu bangun ulang.

`APP_NAME` di `config.py` tetap nama produk teknis (nama aplikasi Qt, jalur
data, tugas terjadwal); jangan diganti agar pembaruan di PC yang sudah
terpasang tidak putus. Yang tampil kepada orang memakai `NAMA_TAMPIL`.
"""

from __future__ import annotations

PRODUK = "Sistem Antrian CRO"
INSTANSI = "CRO"

#: Judul jendela, layar masuk, dan kepala aplikasi.
NAMA_TAMPIL = PRODUK

#: Baris paling atas tiket dan kop laporan.
JUDUL_TIKET = INSTANSI.upper()
