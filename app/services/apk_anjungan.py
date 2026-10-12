"""
APK anjungan Android yang dibagikan server ke tablet.

Tablet tidak diperbarui lewat Play Store; ia mengunduh APK dari server di
jaringan kantor. Supaya itu mungkin, server perlu tahu dua hal:

* VERSI MINIMAL yang masih cocok dengan API ini. Ditulis di kode, bukan di
  pengaturan: yang menentukannya adalah bentuk API, dan bentuk itu berubah
  bersama kode server. Tablet di bawah versi ini berhenti menerbitkan nomor
  sampai diperbarui, karena tablet yang salah membaca jawaban server lebih
  berbahaya daripada tablet yang diam.
* APK TERBARU yang tersedia, dibaca dari folder ``apk`` di sebelah aplikasi.
  build-android-kiosk.ps1 menaruh ``anjungan.apk`` beserta
  ``anjungan.json`` (versi) di sana.

Versi diambil dari berkas JSON, bukan dibaca dari dalam APK. Membongkar
manifest biner Android hanya untuk satu angka adalah kerumitan yang tidak
sebanding; skrip build yang menulis keduanya sekaligus.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("antrian.apk_anjungan")

#: versionCode terendah yang cocok dengan API sekarang. Naikkan setiap kali
#: jawaban API berubah dengan cara yang tidak dipahami APK lama.
#: 5 = 1.4: /v1/kiosk/display tidak lagi mengirim data loket.
#: 49 = 2.4.33: layar Ulangi pada APK lama bertahan selamanya, dan
#: pengunjung berikutnya bisa menerima nomor milik orang sebelumnya.
VERSI_MINIMAL = 49
#: Sama, untuk APK layar antrian (id.sistemantrian.layar).
VERSI_MINIMAL_LAYAR = 1

#: Dua APK yang dibagikan server: tablet anjungan dan layar antrian.
JENIS_APK = ("anjungan", "layar")

NAMA_FOLDER = "apk"
TIPE_APK = "application/vnd.android.package-archive"


@dataclass(frozen=True)
class InfoApk:
    kode_versi: int
    nama_versi: str
    berkas: Path
    ukuran_byte: int


def folder_apk(base: Path) -> Path:
    return Path(base) / NAMA_FOLDER


def info_apk(folder: Path, jenis: str = "anjungan") -> InfoApk | None:
    """APK yang siap dibagikan, atau None bila belum ada atau tidak lengkap."""
    if jenis not in JENIS_APK:
        raise ValueError(f"Jenis APK tidak dikenal: {jenis}")
    berkas = Path(folder) / f"{jenis}.apk"
    try:
        data = json.loads((Path(folder) / f"{jenis}.json").read_text(encoding="utf-8-sig"))
        kode = int(data["version_code"])
        nama = str(data.get("version_name") or kode)
        ukuran = berkas.stat().st_size
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Keterangan APK %s di %s tidak terbaca: %s", jenis, folder, exc)
        return None
    if ukuran <= 0:
        return None
    return InfoApk(kode_versi=kode, nama_versi=nama, berkas=berkas, ukuran_byte=ukuran)
