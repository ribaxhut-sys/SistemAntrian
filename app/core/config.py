"""
Konfigurasi aplikasi.

Path database, backup, dan log dapat diubah TANPA mengubah source code,
yaitu lewat environment variable. Ini penting karena aplikasi didistribusikan
sebagai .exe dan lokasi penyimpanan bisa berbeda di tiap komputer.

Environment variable yang dikenali:
    ANTRIAN_DB_URL       URL SQLAlchemy lengkap. Dipakai bila diisi.
                         Contoh: postgresql+psycopg://user:sandi@server/antrian
    ANTRIAN_DB_PATH      lokasi file database SQLite, dipakai bila DB_URL kosong
    ANTRIAN_BACKUP_DIR   folder hasil backup
    ANTRIAN_LOG_DIR      folder file log
    ANTRIAN_LOG_LEVEL    DEBUG | INFO | WARNING | ERROR
    ANTRIAN_PRINTER      pencetak tiket mesin ini: pdf | system | none
    ANTRIAN_SUARA        1/0 — mesin ini membunyikan panggilan atau tidak

Dua yang terakhir menimpa pengaturan bersama di database, dan memang harus
bisa begitu: pencetak tiket menempel pada satu mesin dan pengeras suara
pada mesin lain, sedangkan `ticket.printer` dan `display.sound_enabled` di
database bernilai satu untuk seluruh sistem. Tanpa penimpaan per mesin,
menyalakan pencetak di anjungan berarti kelima komputer loket ikut mencoba
mencetak ke pencetak yang tidak ada padanya.

Beberapa loket yang melayani bersamaan WAJIB memakai PostgreSQL lewat
ANTRIAN_DB_URL. SQLite hanya sanggup melayani satu komputer: mode WAL
memakai shared memory yang tidak berfungsi di filesystem jaringan, dan
akibatnya bukan sekadar lambat melainkan nomor antrian kembar.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

APP_NAME = "Sistem Antrian CRO"
APP_SLUG = "antrian-cro"

# Timezone operasional. Seluruh timestamp transaksi memakai zona ini,
# bukan zona komputer, agar konsisten di mesin mana pun.
TIMEZONE = "Asia/Jakarta"


def base_dir() -> Path:
    """
    Folder acuan aplikasi.

    Saat dijalankan sebagai .exe hasil PyInstaller, __file__ menunjuk ke
    folder temporary yang isinya terhapus setiap aplikasi ditutup. Karena itu
    lokasi .exe yang dipakai sebagai acuan, bukan __file__.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def resource_dir() -> Path:
    """
    Folder berkas bawaan yang hanya dibaca, yaitu alembic.ini dan alembic/.

    Berbeda dari `base_dir()` dan wajib dibedakan. PyInstaller membongkar
    berkas bundelnya ke folder temporary (`sys._MEIPASS`), sedangkan database,
    backup, dan log harus tetap berada di sebelah .exe agar tidak ikut
    terhapus setiap aplikasi ditutup.

    Saat dijalankan dari source, keduanya menunjuk folder yang sama.
    """
    bundel = getattr(sys, "_MEIPASS", None)
    return Path(bundel) if bundel else base_dir()


#: Nilai yang dibaca sebagai "ya" pada environment variable boolean.
#: Sama persis dengan yang diterima pengaturan database, supaya admin tidak
#: perlu mengingat dua daftar kata yang berbeda.
_BENAR = {"true", "1", "ya", "yes", "on"}
_SALAH = {"false", "0", "tidak", "no", "off"}


def _path_from_env(var: str, default: Path) -> Path:
    raw = os.environ.get(var, "").strip()
    return Path(raw).expanduser().resolve() if raw else default


def _bool_from_env(var: str) -> bool | None:
    """
    Baca environment variable boolean, atau None bila mesin ini tidak
    berpendapat.

    None BUKAN sama dengan False. Mesin yang tidak menyebut apa-apa
    mengikuti pengaturan bersama; hanya mesin yang menyebut secara
    eksplisit yang menimpanya. Nilai yang tidak dikenali diperlakukan
    seperti tidak diisi — salah ketik di satu komputer tidak boleh
    mendiamkan panggilan tanpa jejak.
    """
    raw = os.environ.get(var, "").strip().lower()
    if raw in _BENAR:
        return True
    if raw in _SALAH:
        return False
    return None


@dataclass(frozen=True)
class AppConfig:
    """Konfigurasi runtime yang sudah di-resolve menjadi path absolut."""

    base_dir: Path
    db_path: Path
    backup_dir: Path
    log_dir: Path
    log_level: str
    #: URL SQLAlchemy lengkap. Kosong berarti memakai SQLite pada db_path.
    db_url: str = ""
    #: Pencetak tiket mesin ini. Kosong berarti mengikuti `ticket.printer`
    #: yang berlaku untuk seluruh sistem.
    printer: str = ""
    #: Mesin ini membunyikan panggilan atau tidak. None berarti mengikuti
    #: pengaturan bersama dan bawaan modenya.
    suara: bool | None = None
    timezone: str = TIMEZONE

    @property
    def database_url(self) -> str:
        """
        URL SQLAlchemy untuk database aktif.

        Bila ANTRIAN_DB_URL tidak diisi, jatuh ke SQLite pada db_path —
        bentuk yang dipakai pemasangan satu komputer dan seluruh test.
        """
        return self.db_url or f"sqlite:///{self.db_path}"

    @property
    def url_database(self):
        """
        URL yang sudah terurai menjadi host, port, user, dan nama database.

        Dibutuhkan perkakas luar seperti pg_dump yang menerima potongan itu
        sebagai argumen terpisah, bukan sebagai satu URL.
        """
        return make_url(self.database_url)

    @property
    def dialect(self) -> str:
        """
        Nama dialect database: "sqlite", "postgresql", dan seterusnya.

        Beberapa hal memang harus berbeda per dialect — PRAGMA, cara
        menghitung selisih waktu di SQL, dan cara membuat backup. Diambil
        dari sini supaya tidak ada yang mengurai URL sendiri-sendiri.
        """
        return self.url_database.get_backend_name()

    @property
    def memakai_sqlite(self) -> bool:
        return self.dialect == "sqlite"

    def ensure_directories(self) -> None:
        """Buat folder yang dibutuhkan bila belum ada."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    """Bangun konfigurasi dari environment variable dengan default yang aman."""
    root = base_dir()
    return AppConfig(
        base_dir=root,
        db_path=_path_from_env("ANTRIAN_DB_PATH", root / "data" / "queue.db"),
        db_url=os.environ.get("ANTRIAN_DB_URL", "").strip(),
        backup_dir=_path_from_env("ANTRIAN_BACKUP_DIR", root / "backup"),
        log_dir=_path_from_env("ANTRIAN_LOG_DIR", root / "logs"),
        log_level=os.environ.get("ANTRIAN_LOG_LEVEL", "INFO").upper(),
        printer=os.environ.get("ANTRIAN_PRINTER", "").strip(),
        suara=_bool_from_env("ANTRIAN_SUARA"),
    )


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Konfigurasi aktif (dibuat sekali, lalu dipakai ulang)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Paksa konfigurasi dibaca ulang. Dipakai oleh test dan fitur restore."""
    global _config
    _config = None
