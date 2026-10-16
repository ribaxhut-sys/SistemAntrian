"""
Kunci publik pemulihan akun admin.

Isinya hanya kunci PUBLIK pengembang (32 byte, base64). Kunci rahasianya
tidak pernah ada di repository maupun installer; ia dibuat dan disimpan oleh
pengembang dengan alat kunci miliknya (di luar repository).

Kosong berarti pemulihan lewat pengembang belum diaktifkan pada pemasangan
ini, dan layar "Lupa kata sandi admin" menyatakannya terus terang.

Cara mengisi: jalankan alat pengembang, tab "Buat kunci", lalu tempel
nilai yang ditampilkan ke `KUNCI_PUBLIK_BASE64` di bawah.
"""

from __future__ import annotations

KUNCI_PUBLIK_BASE64 = "zNm2aTUH54Z+JohyN/gyq6VdyzKMPTvE5MLoO54E4wE"
