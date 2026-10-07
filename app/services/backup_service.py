"""
Backup dan pemulihan database.

Cara membuat backup berbeda per dialect dan tidak dapat disatukan; yang
mengerjakannya adalah mesin di app/services/backup_engines.py. Modul ini
mengurus hal-hal yang sama pada keduanya: penamaan berkas, retensi, hak
akses, audit, dan cadangan pengaman sebelum pemulihan.

Kegagalan backup tidak boleh menghentikan pelayanan. Backup otomatis saat
aplikasi dibuka mengembalikan objek hasil, bukan melempar exception —
antrian tetap harus bisa berjalan walau folder backup penuh atau tidak
dapat ditulis.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core import clock
from app.core.config import get_config, reset_config
from app.core.database import dispose_engine, init_database, session_scope
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import AuditAction
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.backup_engines import MesinBackup, buat_mesin
from app.services.permissions import Permission
from app.services.settings_service import SettingsService

logger = get_logger("backup")


def _boleh_backup_di_sini() -> bool:
    """
    Backup otomatis hanya dibuat oleh komputer pemilik database.

    SQLite selalu lokal. Untuk PostgreSQL, komputer loket tidak membuatnya:
    pg_dump biasanya tidak terpasang di sana, sehingga backup gagal setiap
    hari di setiap loket dan lognya penuh galat yang tidak berarti apa-apa.
    """
    config = get_config()
    if config.memakai_sqlite:
        return True
    from app.core.mesin import SERVER, muat_pengaturan

    if muat_pengaturan(config.db_path).peran == SERVER:
        return True
    host = (config.url_database.host or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}

#: Pola nama berkas backup, tanpa akhiran. Waktu ikut di nama supaya beberapa
#: backup dalam satu hari tidak saling menimpa, dan urutannya terbaca tanpa
#: membuka folder. Akhirannya ditentukan mesin: .db untuk SQLite, .dump untuk
#: PostgreSQL.
POLA_NAMA = "queue-%Y%m%d-%H%M%S"
AWALAN = "queue-"

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


def _nama_bebas(folder: Path, waktu: datetime, akhiran: str) -> Path:
    """
    Nama berkas backup yang dijamin belum terpakai.

    Nama hanya beresolusi detik, sedangkan backup pengaman sebelum restore
    dibuat pada detik yang sama dengan backup manual yang mendahuluinya.
    Tanpa penanda pembeda, salah satunya akan menimpa yang lain — dan yang
    tertimpa justru salinan pengaman yang dibutuhkan bila restore keliru.
    """
    inti = waktu.strftime(POLA_NAMA)
    dasar = folder / f"{inti}{akhiran}"
    if not dasar.exists():
        return dasar

    urutan = 2
    while True:
        calon = folder / f"{inti}-{urutan}{akhiran}"
        if not calon.exists():
            return calon
        urutan += 1


def _bagian_nama(berkas: Path, akhiran: str) -> tuple[datetime, int]:
    """
    Waktu pembuatan dan nomor urut menurut nama berkas.

    Nama berkas lebih dipercaya daripada mtime karena mtime berubah bila
    berkas disalin antar folder atau antar komputer. Nomor urut memisahkan
    beberapa backup pada detik yang sama; tanpa itu urutannya bergantung
    pada perbandingan teks, dan "…-2.db" justru terbaca lebih tua daripada
    "….db".
    """
    inti = berkas.name[len(AWALAN) : -len(akhiran)]
    urutan = 1
    if inti.count("-") == 2:
        inti, _, penanda = inti.rpartition("-")
        if penanda.isdigit():
            urutan = int(penanda)

    try:
        return datetime.strptime(inti, "%Y%m%d-%H%M%S"), urutan
    except ValueError:
        return datetime.fromtimestamp(berkas.stat().st_mtime), urutan


def _sebagai_info(berkas: Path, akhiran: str) -> BackupInfo:
    waktu, urutan = _bagian_nama(berkas, akhiran)
    return BackupInfo(
        berkas=berkas,
        dibuat_pada=waktu,
        urutan=urutan,
        ukuran_byte=berkas.stat().st_size,
    )


class BackupService:
    """Pembuatan, penghapusan, dan pemulihan backup database."""

    def __init__(
        self,
        auth: AuthService,
        settings: SettingsService | None = None,
        mesin: MesinBackup | None = None,
    ) -> None:
        self.auth = auth
        self.settings = settings or SettingsService(auth)
        self._mesin = mesin

    @property
    def mesin(self) -> MesinBackup:
        """
        Mesin backup sesuai dialect database.

        Dibuat saat pertama dibutuhkan, bukan di konstruktor: pengaturan
        letak perkakas PostgreSQL dibaca dari database, sedangkan service
        ini dibentuk sebelum ada yang masuk.
        """
        if self._mesin is None:
            self._mesin = buat_mesin(
                get_config(), self.settings.get("backup.pg_dump_path", "")
            )
        return self._mesin

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

    @property
    def folder_salinan(self) -> Path | None:
        """Folder salinan kedua, misalnya disk lain atau flashdisk. None bila kosong."""
        teks = (self.settings.get("backup.salinan_folder", "") or "").strip()
        return Path(teks).expanduser() if teks else None

    def _daftar_berkas(self, folder: Path | None = None) -> list[BackupInfo]:
        folder = self.folder if folder is None else folder
        if not folder.exists():
            return []

        akhiran = self.mesin.akhiran
        berkas = [
            p
            for p in folder.glob(f"{AWALAN}*{akhiran}")
            # Berkas sampingan SQLite ikut terjaring pola di atas, padahal
            # bukan backup dan tidak dapat dipulihkan.
            if p.is_file() and not p.name.endswith(("-wal.db", "-shm.db"))
        ]
        return sorted(
            (_sebagai_info(p, akhiran) for p in berkas),
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
            if not _boleh_backup_di_sini():
                return HasilBackup(
                    False,
                    "Backup otomatis dilewati: database berada di komputer "
                    "server, dan backup dibuat di sana.",
                )

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
        config.backup_dir.mkdir(parents=True, exist_ok=True)
        tujuan = _nama_bebas(config.backup_dir, clock.now(), self.mesin.akhiran)

        try:
            self.mesin.salin(tujuan)
        except Exception:
            # Berkas separuh jadi tidak boleh tertinggal di daftar backup:
            # ia tampak sah sampai ada yang mencoba memulihkannya.
            tujuan.unlink(missing_ok=True)
            raise

        info = _sebagai_info(tujuan, self.mesin.akhiran)
        logger.info("Backup %s dibuat: %s (%s)", alasan, info.nama, info.label_ukuran)
        self._salin_kedua(info)
        return info

    def _salin_kedua(self, info: BackupInfo) -> None:
        """
        Salin backup ke folder kedua.

        Backup di disk yang sama dengan database ikut hilang bila disk itu
        rusak, padahal itulah alasan utama backup dibuat. Kegagalannya
        (flashdisk dicabut, disk penuh) hanya dicatat: backup utama sudah
        jadi dan tetap sah.
        """
        folder = self.folder_salinan
        if folder is None:
            return
        try:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(info.berkas, folder / info.nama)
        except OSError as exc:
            logger.warning("Salinan kedua backup %s gagal ke %s: %s", info.nama, folder, exc)
            return
        logger.info("Salinan kedua backup dibuat: %s", folder / info.nama)

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
        kedaluwarsa = list(self._daftar_berkas())
        salinan = self.folder_salinan
        if salinan is not None:
            try:
                kedaluwarsa += self._daftar_berkas(salinan)
            except OSError:
                logger.warning("Folder salinan backup %s tidak terbaca", salinan)
        for info in kedaluwarsa:
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

        config = get_config()
        if config.memakai_sqlite and sumber.resolve() == config.db_path.resolve():
            raise BusinessRuleError(
                "Berkas yang dipilih adalah database yang sedang dipakai."
            )
        if not self.mesin.sah(sumber):
            raise ValidationError(
                "Berkas yang dipilih bukan database antrian yang sah."
            )

        pengaman = self._salin(alasan="sebelum-restore")

        # Koneksi wajib ditutup lebih dahulu. Pada SQLite karena Windows
        # menolak menimpa berkas yang masih terbuka; pada PostgreSQL supaya
        # koneksi menganggur tidak menghalangi pg_restore membuang tabel.
        dispose_engine()
        try:
            self.mesin.pulihkan(sumber)
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


