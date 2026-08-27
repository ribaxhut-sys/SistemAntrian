"""
Mesin backup per dialect database.

Mengikuti pola TicketPrinter di app/services/ticket_service.py: satu
Protocol dengan beberapa implementasi, dipilih saat aplikasi berjalan.
Alasannya sama — cara mencetak tiket dan cara membuat backup sama-sama
bergantung pada hal di luar aplikasi, dan keduanya harus dapat diganti
tanpa menyentuh logika yang memanggilnya.

SQLite dan PostgreSQL tidak punya cara backup yang sama, dan tidak ada
gunanya dipaksakan:

* SQLite  satu berkas, disalin dengan Online Backup API bawaan. Penyalinan
          berkas biasa TIDAK aman karena mode WAL menyimpan sebagian
          transaksi terbaru di berkas terpisah.
* PostgreSQL  database dilayani server, sehingga harus diminta lewat
          pg_dump. Tidak ada berkas yang bisa disalin begitu saja.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Protocol

from app.core.config import AppConfig
from app.core.database import get_engine
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.logger import get_logger

logger = get_logger("backup")

#: Batas waktu pg_dump dan pg_restore, dalam detik. Database antrian satu
#: kantor berukuran kecil; kalau sampai selama ini belum selesai, yang
#: terjadi hampir pasti bukan proses yang lambat melainkan yang menggantung.
BATAS_DETIK = 600

#: Tabel yang wajib ada agar sebuah berkas diakui sebagai database antrian.
TABEL_PENANDA = {"queue", "app_user", "alembic_version"}


class MesinBackup(Protocol):
    """Cara membuat dan memulihkan backup untuk satu jenis database."""

    #: Akhiran nama berkas hasil backup, termasuk titiknya.
    akhiran: str

    def salin(self, tujuan: Path) -> None:
        """Tulis backup database aktif ke `tujuan`."""

    def pulihkan(self, sumber: Path) -> None:
        """Ganti isi database aktif dengan isi `sumber`."""

    def sah(self, berkas: Path) -> bool:
        """Benar bila berkas benar-benar backup database antrian."""


class SqliteBackup:
    """Backup satu berkas SQLite."""

    akhiran = ".db"

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def salin(self, tujuan: Path) -> None:
        if not self.config.db_path.exists():
            raise NotFoundError("File database tidak ditemukan.")

        # Backup diambil lewat koneksi engine yang sedang berjalan supaya
        # isi WAL yang belum ter-checkpoint ikut tersalin.
        with get_engine().raw_connection() as mentah:
            sumber: sqlite3.Connection = mentah.driver_connection
            salinan = sqlite3.connect(tujuan)
            try:
                sumber.backup(salinan)
            finally:
                salinan.close()

    def pulihkan(self, sumber: Path) -> None:
        """
        Timpa berkas database dengan isi backup.

        Berkas -wal dan -shm milik database lama wajib ikut dibuang. Bila
        tertinggal, SQLite akan memutar ulang transaksi database LAMA di
        atas berkas yang baru dipulihkan.

        Pemanggil wajib menutup engine lebih dahulu; Windows menolak menimpa
        berkas yang koneksinya masih terbuka.
        """
        tujuan = self.config.db_path
        if sumber.resolve() == tujuan.resolve():
            raise BusinessRuleError(
                "Berkas yang dipilih adalah database yang sedang dipakai."
            )

        for tambahan in (
            tujuan.with_name(tujuan.name + "-wal"),
            tujuan.with_name(tujuan.name + "-shm"),
        ):
            tambahan.unlink(missing_ok=True)
        tujuan.write_bytes(sumber.read_bytes())

    def sah(self, berkas: Path) -> bool:
        try:
            koneksi = sqlite3.connect(f"file:{berkas}?mode=ro", uri=True)
            try:
                nama = {
                    baris[0]
                    for baris in koneksi.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                koneksi.close()
        except sqlite3.Error:
            return False
        return TABEL_PENANDA <= nama


class PostgresBackup:
    """
    Backup PostgreSQL lewat pg_dump dan pg_restore.

    Format custom (-Fc) dipilih, bukan SQL polos: hasilnya terkompresi,
    dapat dipulihkan sebagian, dan pg_restore mengurutkan sendiri
    pembuatan tabel beserta foreign key-nya.
    """

    akhiran = ".dump"

    def __init__(self, config: AppConfig, folder_alat: str = "") -> None:
        self.config = config
        self.folder_alat = folder_alat

    # -----------------------------------------------------------------

    def _alat(self, nama: str) -> str:
        """
        Cari pg_dump atau pg_restore.

        Dicari di PATH lebih dahulu; pengaturan backup.pg_dump_path dipakai
        bila PostgreSQL dipasang tanpa memasukkan foldernya ke PATH, yang
        merupakan keadaan bawaan installer Windows.
        """
        if self.folder_alat:
            calon = Path(self.folder_alat) / f"{nama}.exe"
            if calon.exists():
                return str(calon)
            calon = Path(self.folder_alat) / nama
            if calon.exists():
                return str(calon)

        ditemukan = shutil.which(nama)
        if ditemukan:
            return ditemukan

        raise NotFoundError(
            f"{nama} tidak ditemukan. Backup PostgreSQL membutuhkan perkakas "
            "bawaan PostgreSQL. Isi pengaturan 'backup.pg_dump_path' dengan "
            "folder bin PostgreSQL, misalnya "
            r"C:\Program Files\PostgreSQL\17\bin."
        )

    def _lingkungan(self) -> dict[str, str]:
        """
        Kirim kata sandi lewat environment, bukan lewat argumen perintah.

        Argumen perintah terlihat oleh seluruh proses di komputer yang sama.
        """
        url = self.config.url_database
        env = dict(os.environ)
        if url.password:
            env["PGPASSWORD"] = str(url.password)
        return env

    def _sambungan(self) -> list[str]:
        url = self.config.url_database
        argumen = ["--host", url.host or "localhost", "--port", str(url.port or 5432)]
        if url.username:
            argumen += ["--username", str(url.username)]
        return argumen + ["--no-password"]

    def _jalankan(self, perintah: list[str]) -> None:
        hasil = subprocess.run(
            perintah,
            env=self._lingkungan(),
            capture_output=True,
            text=True,
            timeout=BATAS_DETIK,
            # Jendela konsol tidak boleh berkedip di depan petugas; aplikasi
            # ini berjalan tanpa terminal.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if hasil.returncode != 0:
            logger.error(
                "%s gagal (kode %s): %s",
                Path(perintah[0]).name,
                hasil.returncode,
                hasil.stderr.strip(),
            )
            raise BusinessRuleError(
                f"{Path(perintah[0]).name} gagal. Detailnya tersimpan pada file log."
            )

    # -----------------------------------------------------------------

    def salin(self, tujuan: Path) -> None:
        url = self.config.url_database
        self._jalankan(
            [self._alat("pg_dump"), *self._sambungan(),
             "--format", "custom", "--file", str(tujuan), url.database or ""]
        )

    def pulihkan(self, sumber: Path) -> None:
        """
        Kembalikan isi database dari sebuah dump.

        --clean --if-exists membuang objek lama lebih dahulu, sehingga
        pemulihan tidak menumpuk di atas data yang sekarang. --single-
        transaction membuat kegagalan di tengah jalan membatalkan
        seluruhnya, bukan meninggalkan database separuh terpulihkan.
        """
        url = self.config.url_database
        self._jalankan(
            [self._alat("pg_restore"), *self._sambungan(),
             "--dbname", url.database or "",
             "--clean", "--if-exists", "--single-transaction",
             "--no-owner", "--no-privileges", str(sumber)]
        )

    def sah(self, berkas: Path) -> bool:
        """
        Periksa isi dump tanpa memulihkannya.

        pg_restore --list membaca daftar objek di dalamnya; berkas yang
        bukan dump PostgreSQL akan ditolak di langkah ini.
        """
        # NotFoundError sengaja TIDAK ditangkap. Perkakas yang belum
        # terpasang bukan berarti berkasnya tidak sah, dan pesan "bukan
        # database antrian yang sah" akan menyesatkan petugas yang
        # sebenarnya hanya perlu mengisi letak pg_restore.
        alat = self._alat("pg_restore")
        try:
            hasil = subprocess.run(
                [alat, "--list", str(berkas)],
                capture_output=True,
                text=True,
                timeout=BATAS_DETIK,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (subprocess.SubprocessError, OSError):
            return False
        if hasil.returncode != 0:
            return False

        isi = hasil.stdout.upper()
        return all(tabel.upper() in isi for tabel in TABEL_PENANDA)


def buat_mesin(config: AppConfig, folder_alat: str = "") -> MesinBackup:
    """Mesin backup yang sesuai dengan database yang sedang dipakai."""
    if config.memakai_sqlite:
        return SqliteBackup(config)
    return PostgresBackup(config, folder_alat)
