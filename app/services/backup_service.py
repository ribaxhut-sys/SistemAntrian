"""
Backup dan pemulihan database.

Menyalin file database dengan `copy` biasa TIDAK aman di sini. Aplikasi
berjalan dalam mode WAL, sehingga sebagian transaksi terbaru masih berada di
file -wal dan belum masuk ke file utama; salinan mentahnya bisa tertinggal
atau bahkan rusak. Karena itu backup memakai Online Backup API bawaan SQLite,
yang menghasilkan satu file utuh dan konsisten walau aplikasi sedang dipakai.

Kegagalan backup tidak boleh menghentikan pelayanan. Backup otomatis saat
aplikasi dibuka mengembalikan objek hasil, bukan melempar exception —
antrian tetap harus bisa berjalan walau folder backup penuh atau tidak
dapat ditulis.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core import clock
from app.core.config import get_config, reset_config
from app.core.database import dispose_engine, get_engine, init_database, session_scope
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import AuditAction
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission
from app.services.settings_service import SettingsService

logger = get_logger("backup")

#: Pola nama berkas backup. Waktu ikut di nama supaya beberapa backup dalam
#: satu hari tidak saling menimpa, dan urutannya terbaca tanpa membuka folder.
POLA_NAMA = "queue-%Y%m%d-%H%M%S.db"
AWALAN = "queue-"
AKHIRAN = ".db"

#: Batas bawah retensi. Nilai nol atau negatif akan menghapus backup yang
#: baru saja dibuat, sehingga diperlakukan sebagai salah konfigurasi.
RETENSI_MINIMUM = 1


@dataclass(frozen=True)
class BackupInfo:
    """Satu berkas backup beserta keterangannya."""

    berkas: Path
    dibuat_pada: datetime
    ukuran_byte: int
    #: Pembeda antar backup pada detik yang sama, mulai dari 1.
    urutan: int = 1

    @property
    def nama(self) -> str:
        return self.berkas.name

    @property
    def ukuran_mb(self) -> float:
        return self.ukuran_byte / (1024 * 1024)

    @property
    def label_ukuran(self) -> str:
        if self.ukuran_byte < 1024 * 1024:
            return f"{self.ukuran_byte / 1024:.0f} KB"
        return f"{self.ukuran_mb:.1f} MB"


@dataclass(frozen=True)
class HasilBackup:
    """
    Hasil backup otomatis.

    Sengaja berupa objek, bukan exception. Backup yang gagal saat aplikasi
    dibuka tidak boleh membuat petugas tidak dapat bekerja.
    """

    berhasil: bool
    pesan: str
    info: BackupInfo | None = None


def _nama_bebas(folder: Path, waktu: datetime) -> Path:
    """
    Nama berkas backup yang dijamin belum terpakai.

    Nama hanya beresolusi detik, sedangkan backup pengaman sebelum restore
    dibuat pada detik yang sama dengan backup manual yang mendahuluinya.
    Tanpa akhiran pembeda, salah satunya akan menimpa yang lain — dan yang
    tertimpa justru salinan pengaman yang dibutuhkan bila restore keliru.
    """
    dasar = folder / waktu.strftime(POLA_NAMA)
    if not dasar.exists():
        return dasar

    inti = dasar.name[: -len(AKHIRAN)]
    urutan = 2
    while True:
        calon = folder / f"{inti}-{urutan}{AKHIRAN}"
        if not calon.exists():
            return calon
        urutan += 1


def _bagian_nama(berkas: Path) -> tuple[datetime, int]:
    """
    Waktu pembuatan dan nomor urut menurut nama berkas.

    Nama berkas lebih dipercaya daripada mtime karena mtime berubah bila
    berkas disalin antar folder atau antar komputer. Nomor urut memisahkan
    beberapa backup pada detik yang sama; tanpa itu urutannya bergantung
    pada perbandingan teks, dan "…-2.db" justru terbaca lebih tua daripada
    "….db".
    """
    inti = berkas.name[len(AWALAN) : -len(AKHIRAN)]
    urutan = 1
    if inti.count("-") == 2:
        inti, _, akhiran = inti.rpartition("-")
        if akhiran.isdigit():
            urutan = int(akhiran)

    try:
        return datetime.strptime(inti, "%Y%m%d-%H%M%S"), urutan
    except ValueError:
        return datetime.fromtimestamp(berkas.stat().st_mtime), urutan


def _sebagai_info(berkas: Path) -> BackupInfo:
    waktu, urutan = _bagian_nama(berkas)
    return BackupInfo(
        berkas=berkas,
        dibuat_pada=waktu,
        urutan=urutan,
        ukuran_byte=berkas.stat().st_size,
    )


class BackupService:
    """Pembuatan, penghapusan, dan pemulihan backup database."""

    def __init__(self, auth: AuthService, settings: SettingsService | None = None) -> None:
        self.auth = auth
        self.settings = settings or SettingsService(auth)

    # =================================================================
    # Pembacaan
    # =================================================================

    @property
    def folder(self) -> Path:
        return get_config().backup_dir

    def list_backup(self) -> list[BackupInfo]:
        """Seluruh backup yang tersedia, terbaru lebih dahulu."""
        self.auth.require_permission(Permission.BACKUP_MANAGE)
        return self._daftar_berkas()

    def _daftar_berkas(self) -> list[BackupInfo]:
        folder = self.folder
        if not folder.exists():
            return []
        berkas = [
            p
            for p in folder.glob(f"{AWALAN}*{AKHIRAN}")
            if p.is_file() and not p.name.endswith(("-wal.db", "-shm.db"))
        ]
        return sorted(
            (_sebagai_info(p) for p in berkas),
            key=lambda i: (i.dibuat_pada, i.urutan),
            reverse=True,
        )

    # =================================================================
    # Pembuatan
    # =================================================================

    def backup(self, *, alasan: str = "manual") -> BackupInfo:
        """
        Buat satu backup database sekarang juga.

        Memakai Online Backup API sehingga aman dijalankan walau petugas lain
        sedang menerbitkan nomor. Retensi dibersihkan setelah backup baru
        berhasil dibuat, bukan sebelumnya — bila dibalik, kegagalan backup
        akan meninggalkan sistem tanpa salinan sama sekali.
        """
        sesi = self.auth.require_permission(Permission.BACKUP_MANAGE)
        info = self._salin(alasan=alasan)

        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.BACKUP,
                user_id=sesi.user_id,
                entity_type="database",
                berkas=info.nama,
                alasan=alasan,
                ukuran_byte=info.ukuran_byte,
            )

        self._bersihkan_kedaluwarsa()
        return info

    def backup_otomatis_bila_perlu(self) -> HasilBackup:
        """
        Backup harian saat aplikasi dibuka.

        Dipanggil sebelum ada sesi pengguna, sehingga tidak menuntut hak
        akses dan tidak masuk audit log atas nama siapa pun. Jejaknya tetap
        ada berupa berkas backup itu sendiri dan catatan pada file log.

        Apa pun yang gagal di sini tidak boleh menggagalkan aplikasi.
        """
        try:
            if not self.settings.get_bool("backup.auto_enabled", True):
                return HasilBackup(False, "Backup otomatis dinonaktifkan.")

            hari = clock.today()
            if any(i.dibuat_pada.date() == hari for i in self._daftar_berkas()):
                return HasilBackup(False, "Backup hari ini sudah ada.")

            info = self._salin(alasan="otomatis")
            self._bersihkan_kedaluwarsa()
            logger.info("Backup otomatis dibuat: %s", info.nama)
            return HasilBackup(True, f"Backup otomatis dibuat: {info.nama}", info)
        except Exception:
            logger.exception("Backup otomatis gagal")
            return HasilBackup(
                False, "Backup otomatis gagal. Detailnya tersimpan pada file log."
            )

    def _salin(self, *, alasan: str) -> BackupInfo:
        config = get_config()
        if not config.db_path.exists():
            raise NotFoundError("File database tidak ditemukan.")

        config.backup_dir.mkdir(parents=True, exist_ok=True)
        tujuan = _nama_bebas(config.backup_dir, clock.now())

        # Backup diambil lewat koneksi engine yang sedang berjalan supaya
        # isi WAL yang belum ter-checkpoint ikut tersalin.
        with get_engine().raw_connection() as mentah:
            sumber: sqlite3.Connection = mentah.driver_connection
            salinan = sqlite3.connect(tujuan)
            try:
                sumber.backup(salinan)
            finally:
                salinan.close()

        info = _sebagai_info(tujuan)
        logger.info("Backup %s dibuat: %s (%s)", alasan, info.nama, info.label_ukuran)
        return info

    # =================================================================
    # Retensi
    # =================================================================

    def hapus_kedaluwarsa(self) -> list[str]:
        """Hapus backup yang sudah melewati masa simpan. Kembalikan namanya."""
        self.auth.require_permission(Permission.BACKUP_MANAGE)
        return self._bersihkan_kedaluwarsa()

    def _bersihkan_kedaluwarsa(self) -> list[str]:
        hari = self.settings.get_int("backup.retention_days", 30)
        if hari < RETENSI_MINIMUM:
            logger.warning(
                "backup.retention_days bernilai %s; retensi dilewati agar backup "
                "yang baru dibuat tidak ikut terhapus.",
                hari,
            )
            return []

        batas = clock.now().timestamp() - hari * 86400
        dihapus: list[str] = []
        for info in self._daftar_berkas():
            if info.dibuat_pada.timestamp() >= batas:
                continue
            try:
                info.berkas.unlink()
                dihapus.append(info.nama)
            except OSError:
                # Berkas yang sedang dipakai program lain dilewati saja.
                # Backup kedaluwarsa yang tertinggal jauh lebih ringan
                # akibatnya daripada proses backup yang berhenti.
                logger.warning("Backup %s tidak dapat dihapus", info.nama)

        if dihapus:
            logger.info("Backup kedaluwarsa dihapus: %s", ", ".join(dihapus))
        return dihapus

    # =================================================================
    # Pemulihan
    # =================================================================

    def restore(self, berkas: Path | str) -> None:
        """
        Ganti database aktif dengan isi sebuah backup.

        SELURUH data setelah tanggal backup akan hilang. Pemanggil wajib
        memastikan petugas sudah menyetujuinya.

        Sebelum menimpa, database aktif disalin lebih dahulu ke backup baru
        bertanda "sebelum-restore". Tanpa itu, salah pilih berkas berarti data
        hari ini hilang tanpa jalan kembali.
        """
        sesi = self.auth.require_permission(Permission.BACKUP_MANAGE)

        sumber = Path(berkas)
        if not sumber.is_absolute():
            sumber = self.folder / sumber
        if not sumber.exists():
            raise NotFoundError("Berkas backup tidak ditemukan.")
        if not self._sqlite_sah(sumber):
            raise ValidationError(
                "Berkas yang dipilih bukan database antrian yang sah."
            )

        config = get_config()
        if sumber.resolve() == config.db_path.resolve():
            raise BusinessRuleError(
                "Berkas yang dipilih adalah database yang sedang dipakai."
            )

        pengaman = self._salin(alasan="sebelum-restore")

        # Koneksi wajib ditutup lebih dahulu: Windows menolak menimpa file
        # yang masih terbuka.
        dispose_engine()
        try:
            self._timpa(sumber, config.db_path)
        finally:
            reset_config()
            init_database()

        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.RESTORE,
                user_id=sesi.user_id,
                entity_type="database",
                berkas=sumber.name,
                pengaman=pengaman.nama,
            )
        logger.warning(
            "Database dipulihkan dari %s (pengaman: %s)", sumber.name, pengaman.nama
        )

    @staticmethod
    def _timpa(sumber: Path, tujuan: Path) -> None:
        """
        Salin isi backup ke database aktif.

        Berkas -wal dan -shm milik database lama wajib ikut dibuang. Bila
        tertinggal, SQLite akan memutar ulang transaksi database LAMA di atas
        berkas yang baru dipulihkan.
        """
        for tambahan in (
            tujuan.with_name(tujuan.name + "-wal"),
            tujuan.with_name(tujuan.name + "-shm"),
        ):
            tambahan.unlink(missing_ok=True)
        tujuan.write_bytes(sumber.read_bytes())

    @staticmethod
    def _sqlite_sah(berkas: Path) -> bool:
        """Pastikan berkas benar-benar database antrian, bukan file sembarangan."""
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
        return {"queue", "app_user", "alembic_version"} <= nama
