"""Format tampilan berbahasa Indonesia."""

from __future__ import annotations

from datetime import date, datetime

BULAN = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

HARI = (
    "Senin",
    "Selasa",
    "Rabu",
    "Kamis",
    "Jumat",
    "Sabtu",
    "Minggu",
)


def tanggal_panjang(nilai: date) -> str:
    """26 Agustus 2026."""
    return f"{nilai.day} {BULAN[nilai.month - 1]} {nilai.year}"


def tanggal_pendek(nilai: date) -> str:
    """3 Okt — untuk kolom tabel yang sempit."""
    return f"{nilai.day} {BULAN[nilai.month - 1][:3]}"


def hari_dan_tanggal(nilai: date) -> str:
    """Rabu, 26 Agustus 2026."""
    return f"{HARI[nilai.weekday()]}, {tanggal_panjang(nilai)}"


def jam(nilai: datetime) -> str:
    """20:07 WIB."""
    return f"{nilai:%H:%M} WIB"


def durasi_singkat(detik: float | None) -> str:
    """
    Lama waktu dalam bentuk yang mudah dibaca sekilas.

    Dipakai pada daftar tunggu dan laporan, sehingga satuannya menyesuaikan
    besarannya: detik untuk yang baru saja, jam untuk yang lama menunggu.
    """
    if detik is None:
        return "—"
    detik = int(detik)
    if detik < 60:
        return f"{detik} detik"
    if detik < 3600:
        return f"{detik // 60} menit"
    return f"{detik // 3600} jam {(detik % 3600) // 60} menit"


_SATUAN = (
    "", "satu", "dua", "tiga", "empat", "lima",
    "enam", "tujuh", "delapan", "sembilan",
)
_BELASAN = (
    "sepuluh", "sebelas", "dua belas", "tiga belas", "empat belas",
    "lima belas", "enam belas", "tujuh belas", "delapan belas", "sembilan belas",
)
_PULUHAN = (
    "", "", "dua puluh", "tiga puluh", "empat puluh", "lima puluh",
    "enam puluh", "tujuh puluh", "delapan puluh", "sembilan puluh",
)


def angka_ke_kata(n: int) -> str:
    """
    Ubah bilangan bulat menjadi kata bahasa Indonesia.

    Dipakai suara panggilan agar nomor antrian terdengar wajar ("dua puluh
    tiga"), bukan dieja per digit. Mendukung 0 sampai jutaan — jauh lebih
    dari cukup untuk nomor antrian harian, tetapi tidak dibatasi secara
    sengaja supaya tidak diam-diam salah bila suatu saat dipakai di tempat
    lain (mis. nominal pada laporan).
    """
    if n < 0:
        return f"minus {angka_ke_kata(-n)}"
    if n == 0:
        return "nol"

    if n < 10:
        return _SATUAN[n]
    if n < 20:
        return _BELASAN[n - 10]
    if n < 100:
        puluh, sisa = divmod(n, 10)
        inti = _PULUHAN[puluh]
        return f"{inti} {_SATUAN[sisa]}".strip() if sisa else inti
    if n < 1000:
        ratus, sisa = divmod(n, 100)
        depan = "seratus" if ratus == 1 else f"{_SATUAN[ratus]} ratus"
        return f"{depan} {angka_ke_kata(sisa)}".strip() if sisa else depan
    if n < 1_000_000:
        ribu, sisa = divmod(n, 1000)
        depan = "seribu" if ribu == 1 else f"{angka_ke_kata(ribu)} ribu"
        return f"{depan} {angka_ke_kata(sisa)}".strip() if sisa else depan

    juta, sisa = divmod(n, 1_000_000)
    depan = f"{angka_ke_kata(juta)} juta"
    return f"{depan} {angka_ke_kata(sisa)}".strip() if sisa else depan


def eja_prefix(prefix: str) -> str:
    """
    Eja huruf prefix satu per satu, dipisah spasi.

    Diucapkan sebagai huruf lepas ("A", "B") agar tidak salah dibaca mesin
    TTS sebagai singkatan atau kata.
    """
    return " ".join(prefix.upper())
