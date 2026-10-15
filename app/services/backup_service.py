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

import errno
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from app.core import clock
from app.core.config import get_config, reset_config
from app.core.database import dispose_engine, init_database, session_scope
from app.core.errors import AppError, BusinessRuleError, NotFoundError, ValidationError
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

#: Akhiran berkas checksum di samping setiap backup, berformat sha256sum
#: ("<hex>  <nama>") supaya dapat diperiksa juga dengan perkakas umum.
AKHIRAN_CHECKSUM = ".sha256"

#: Catatan hasil backup terakhir, di folder backup. Bukan di database:
#: backup paling sering gagal justru ketika database bermasalah.
BERKAS_STATUS = ".status-backup.json"

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
    #: Ada berkas .sha256 di sampingnya. Backup lama belum mempunyainya.
    checksum_ada: bool = False

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


@dataclass(frozen=True)
class StatusBackup:
    """Hasil backup terakhir yang berhasil dan yang gagal."""

    terakhir_berhasil: datetime | None = None
    terakhir_gagal: datetime | None = None
    pesan_gagal: str = ""
    #: Percobaan backup paling akhir gagal. Bendera, bukan perbandingan
    #: waktu: gagal dan berhasil dapat terjadi pada detik yang sama.
    gagal_terakhir: bool = False


@dataclass(frozen=True)
class HasilUjiBackup:
    """Hasil pemeriksaan keutuhan satu backup."""

    berhasil: bool
    ringkasan: str
    rincian: tuple[str, ...] = field(default_factory=tuple)


def berkas_checksum(berkas: Path) -> Path:
    return berkas.with_name(berkas.name + AKHIRAN_CHECKSUM)


def hitung_sha256(berkas: Path) -> str:
    h = hashlib.sha256()
    with berkas.open("rb") as f:
        for potongan in iter(lambda: f.read(1024 * 1024), b""):
            h.update(potongan)
    return h.hexdigest()


def tulis_checksum(berkas: Path) -> str:
    nilai = hitung_sha256(berkas)
    berkas_checksum(berkas).write_text(f"{nilai}  {berkas.name}\n", encoding="ascii")
    return nilai


def cocokkan_checksum(berkas: Path) -> bool | None:
    """True cocok, False rusak/berubah, None bila tidak ada checksum."""
    samping = berkas_checksum(berkas)
    if not samping.is_file():
        return None
    try:
        tercatat = samping.read_text(encoding="ascii").split()[0].lower()
    except (OSError, UnicodeDecodeError, IndexError):
        return False
    return tercatat == hitung_sha256(berkas)


def pesan_kegagalan(exc: BaseException, folder: Path | None = None) -> str:
    """
    Kalimat untuk petugas dari exception backup.

    Detail teknisnya tetap masuk log oleh pemanggil; yang tampil di layar
    hanya penyebab yang dapat ditindaklanjuti.
    """
    if isinstance(exc, AppError):
        return exc.user_message
    if isinstance(exc, subprocess.TimeoutExpired):
        return (
            "Backup terlalu lama dan dihentikan. Periksa koneksi ke server "
            "database, lalu coba lagi."
        )
    if isinstance(exc, PermissionError):
        tempat = f" {folder}" if folder else ""
        return f"Folder backup{tempat} tidak dapat ditulis. Periksa izin foldernya."
    if isinstance(exc, OSError) and (
        exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) in (39, 112)
    ):
        return "Disk penuh: backup tidak dapat ditulis. Kosongkan ruang disk lalu coba lagi."
    return "Backup gagal karena kesalahan tak terduga. Detailnya tersimpan pada file log."


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
        checksum_ada=berkas_checksum(berkas).is_file(),
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

    def status_backup(self) -> StatusBackup:
        """Waktu backup terakhir yang berhasil, dan kegagalan sesudahnya."""
        self.auth.require_permission(Permission.BACKUP_MANAGE)
        return self._baca_status()

    def _baca_status(self) -> StatusBackup:
        def waktu(teks) -> datetime | None:
            try:
                return datetime.fromisoformat(teks) if teks else None
            except (TypeError, ValueError):
                return None

        data: dict = {}
        try:
            data = json.loads((self.folder / BERKAS_STATUS).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        berhasil = waktu(data.get("terakhir_berhasil"))
        # Backup yang dibuat sebelum catatan ini ada tetap terhitung.
        if berhasil is None:
            daftar = self._daftar_berkas()
            berhasil = daftar[0].dibuat_pada if daftar else None
        return StatusBackup(
            terakhir_berhasil=berhasil,
            terakhir_gagal=waktu(data.get("terakhir_gagal")),
            pesan_gagal=str(data.get("pesan_gagal") or ""),
            gagal_terakhir=bool(data.get("gagal_terakhir")),
        )

    def _catat_status(self, **ubah) -> None:
        """Catat hasil backup; kegagalan mencatat tidak boleh menggagalkan backup."""
        berkas = self.folder / BERKAS_STATUS
        try:
            data = json.loads(berkas.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.update(ubah)
        try:
            berkas.parent.mkdir(parents=True, exist_ok=True)
            berkas.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.warning("Catatan status backup tidak dapat ditulis", exc_info=True)

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
        except Exception as exc:
            logger.exception("Backup otomatis gagal")
            return HasilBackup(
                False,
                f"Backup otomatis gagal. {pesan_kegagalan(exc, get_config().backup_dir)}",
            )

    def _salin(self, *, alasan: str) -> BackupInfo:
        config = get_config()
        config.backup_dir.mkdir(parents=True, exist_ok=True)
        tujuan = _nama_bebas(config.backup_dir, clock.now(), self.mesin.akhiran)

        try:
            self.mesin.salin(tujuan)
            # Checksum dihitung segera, selagi berkasnya pasti utuh. Rusak
            # sesudahnya (disk, salinan ke flashdisk) akan tampak saat diuji.
            tulis_checksum(tujuan)
        except Exception as exc:
            # Berkas separuh jadi tidak boleh tertinggal di daftar backup:
            # ia tampak sah sampai ada yang mencoba memulihkannya.
            tujuan.unlink(missing_ok=True)
            berkas_checksum(tujuan).unlink(missing_ok=True)
            self._catat_status(
                terakhir_gagal=clock.now().isoformat(timespec="seconds"),
                pesan_gagal=pesan_kegagalan(exc, config.backup_dir),
                gagal_terakhir=True,
            )
            raise

        info = _sebagai_info(tujuan, self.mesin.akhiran)
        self._catat_status(
            terakhir_berhasil=clock.now().isoformat(timespec="seconds"),
            gagal_terakhir=False,
        )
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
            samping = berkas_checksum(info.berkas)
            if samping.is_file():
                shutil.copy2(samping, folder / samping.name)
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
                berkas_checksum(info.berkas).unlink(missing_ok=True)
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

        sumber = self._sumber(berkas)

        config = get_config()
        if config.memakai_sqlite and sumber.resolve() == config.db_path.resolve():
            raise BusinessRuleError(
                "Berkas yang dipilih adalah database yang sedang dipakai."
            )
        if cocokkan_checksum(sumber) is False:
            raise ValidationError(_PESAN_CHECKSUM_RUSAK)
        if not self.mesin.sah(sumber):
            raise ValidationError(
                "Berkas yang dipilih bukan database antrian yang sah."
            )

        masih_aktif = self._loket_masih_aktif(sesi.user_id)
        if masih_aktif:
            raise BusinessRuleError(
                "Masih ada loket yang aktif: "
                + ", ".join(masih_aktif)
                + ". Minta petugasnya keluar dari aplikasi (Keluar), tunggu "
                "sebentar, lalu ulangi pemulihan. Memulihkan database selagi "
                "loket bekerja dapat merusak nomor yang sedang dilayani."
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

    @staticmethod
    def _loket_masih_aktif(user_id: int | None) -> list[str]:
        """
        Nama loket yang petugasnya masih memberi tanda hadir segar.

        Tanda hadir dikirim setiap 30 detik oleh jendela petugas dan hilang
        saat logout; yang lebih tua dari BATAS_HADIR_PETUGAS_DETIK dianggap
        sudah tidak ada orangnya. Milik sesi yang sedang memulihkan sendiri
        tidak dihitung.
        """
        import sqlalchemy as sa

        from app.models import Counter
        from app.services.queue_service import BATAS_HADIR_PETUGAS_DETIK

        batas = clock.now() - timedelta(seconds=BATAS_HADIR_PETUGAS_DETIK)
        with session_scope() as session:
            kondisi = [
                Counter.petugas_user_id.is_not(None),
                Counter.petugas_terlihat_pada.is_not(None),
                Counter.petugas_terlihat_pada >= batas,
            ]
            if user_id is not None:
                kondisi.append(Counter.petugas_user_id != user_id)
            return list(
                session.scalars(sa.select(Counter.name).where(*kondisi).order_by(Counter.code))
            )

    def _sumber(self, berkas: Path | str) -> Path:
        sumber = Path(berkas)
        if not sumber.is_absolute():
            sumber = self.folder / sumber
        if not sumber.exists():
            raise NotFoundError("Berkas backup tidak ditemukan.")
        return sumber

    # =================================================================
    # Uji keutuhan
    # =================================================================

    def uji_backup(self, berkas: Path | str) -> HasilUjiBackup:
        """
        Periksa sebuah backup benar-benar dapat dipulihkan, tanpa memulihkannya.

        Backup yang rusak biasanya baru ketahuan saat dibutuhkan, dan pada
        saat itu sudah terlambat. Urutannya: checksum (berkas tidak berubah
        sejak dibuat), lalu isi (database antrian yang sah), lalu pemulihan
        uji oleh mesin dialect-nya. Database aktif tidak disentuh.
        """
        self.auth.require_permission(Permission.BACKUP_MANAGE)
        sumber = self._sumber(berkas)
        rincian: list[str] = []

        cocok = cocokkan_checksum(sumber)
        if cocok is False:
            logger.error("Uji backup %s: checksum tidak cocok", sumber.name)
            return HasilUjiBackup(False, _PESAN_CHECKSUM_RUSAK)
        rincian.append(
            "Checksum cocok dengan saat backup dibuat."
            if cocok
            else "Tidak ada checksum (backup dibuat sebelum fitur ini ada)."
        )

        try:
            if not self.mesin.sah(sumber):
                return HasilUjiBackup(
                    False, "Berkas ini bukan database antrian yang sah.", tuple(rincian)
                )
            rincian.append(self.mesin.uji_pulih(sumber))
        except AppError as exc:
            return HasilUjiBackup(False, exc.user_message, tuple(rincian))
        except Exception:
            logger.exception("Uji backup %s gagal", sumber.name)
            return HasilUjiBackup(
                False,
                "Uji backup gagal karena kesalahan tak terduga. Detailnya "
                "tersimpan pada file log.",
                tuple(rincian),
            )

        logger.info("Uji backup %s berhasil", sumber.name)
        return HasilUjiBackup(True, "Backup utuh dan dapat dipulihkan.", tuple(rincian))


_PESAN_CHECKSUM_RUSAK = (
    "Berkas backup rusak atau berubah sejak dibuat (checksum tidak cocok). "
    "Pilih backup lain."
)
