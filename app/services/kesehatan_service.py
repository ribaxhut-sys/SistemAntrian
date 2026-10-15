"""
Kesehatan sistem, untuk ADMIN.

Masalah operasional biasanya baru ketahuan dari keluhan: backup yang tidak
terbentuk sejak minggu lalu, disk server penuh, tablet yang memakai APK
lama, atau API anjungan yang menyala tetapi tidak dapat membaca database.
Modul ini mengumpulkan fakta-fakta itu di satu tempat supaya ADMIN dapat
memeriksanya sekali pandang sebelum pelayanan dimulai.

Setiap pemeriksaan berdiri sendiri: satu yang gagal (misalnya database
tidak terjangkau) tidak boleh membuat pemeriksaan lain ikut hilang. Semua
lambat (database, HTTP, PowerShell) dan harus dipanggil di luar utas UI.

Yang TIDAK pernah keluar dari sini: kata sandi, hash, token perangkat,
token API, maupun isi pengaduan. Potongan log yang ditampilkan disamarkan
lebih dahulu (`samarkan`), karena pesan exception pihak ketiga dapat saja
memuat URL koneksi lengkap.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from app import __version__
from app.core import clock
from app.core.config import base_dir, get_config
from app.core.logger import get_logger
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService, _boleh_backup_di_sini
from app.services.permissions import Permission
from app.services.status_anjungan import BATAS_TERPUTUS, MASALAH, NORMAL, PERINGATAN

logger = get_logger("kesehatan")

#: Pemeriksaan yang tidak berlaku di pemasangan ini, misalnya anjungan pada
#: pemasangan SQLite satu komputer. Bukan masalah, hanya keterangan.
INFO = "info"

#: Urutan keparahan, untuk ringkasan keseluruhan.
_BOBOT = {INFO: 0, NORMAL: 0, PERINGATAN: 1, MASALAH: 2}

#: Backup otomatis dibuat saat aplikasi dibuka, sekali sehari. Tiga hari
#: memberi ruang akhir pekan tanpa membuat peringatan menyala tiap Senin.
BATAS_UMUR_BACKUP = timedelta(days=3)

#: Sisa ruang disk. Backup PostgreSQL dan log terus bertambah; di bawah
#: batas ini backup berikutnya bisa gagal di tengah jalan.
BATAS_DISK_PERINGATAN = 1024**3  # 1 GB
BATAS_DISK_MASALAH = 200 * 1024**2  # 200 MB

#: Galat yang dihitung hanya dari jendela ini, supaya galat minggu lalu yang
#: sudah tertangani tidak membuat panel merah selamanya.
JENDELA_GALAT = timedelta(hours=24)
#: Banyaknya pesan galat terakhir yang ditampilkan.
BATAS_RINCIAN_GALAT = 5
#: Bagian akhir app.log yang dibaca. RotatingFileHandler membatasi berkas
#: 2 MB; ekornya sudah cukup untuk jendela 24 jam.
_EKOR_LOG_BYTE = 512 * 1024

_BARIS_GALAT = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (ERROR|CRITICAL)\s* \| (\S+) \| (.*)$"
)

_POLA_RAHASIA = (
    # postgresql+psycopg://antrian:rahasia@host → antrian:***@host
    (re.compile(r"(\w[\w+.-]*://[^:/\s@]+:)[^@\s]+@"), r"\1***@"),
    # password=..., token: ..., Authorization: Bearer ...
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|kata[ _]?sandi|token|secret|rahasia"
            r"|authorization|bearer)\b([\"'\s:=]+)(bearer\s+)?[^\s,;\"']+"
        ),
        r"\1\2\3***",
    ),
    # Untaian panjang mirip token (token_urlsafe, sha256 hex).
    (re.compile(r"[A-Za-z0-9_\-]{32,}"), "***"),
)


@dataclass(frozen=True)
class Pemeriksaan:
    """Satu baris di panel Kesehatan Sistem."""

    nama: str
    tingkat: str
    ringkasan: str
    saran: tuple[str, ...] = field(default_factory=tuple)
    #: Keterangan tambahan, misalnya pesan galat terakhir.
    rincian: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LaporanKesehatan:
    diperiksa_pada: datetime
    butir: tuple[Pemeriksaan, ...]

    @property
    def tingkat(self) -> str:
        """Tingkat terburuk dari semua pemeriksaan."""
        terburuk = NORMAL
        for p in self.butir:
            if _BOBOT.get(p.tingkat, 0) > _BOBOT[terburuk]:
                terburuk = p.tingkat
        return terburuk


def samarkan(teks: str) -> str:
    """Hapus kata sandi, token, dan untaian mirip rahasia dari teks log."""
    for pola, ganti in _POLA_RAHASIA:
        teks = pola.sub(ganti, teks)
    return teks


def _ukuran(byte: int) -> str:
    if byte >= 1024**3:
        return f"{byte / 1024**3:.1f} GB"
    return f"{byte / 1024**2:.0f} MB"


def _waktu(w: datetime | None, sekarang: datetime) -> str:
    if w is None:
        return "belum pernah"
    if w.date() == sekarang.date():
        return f"hari ini {w:%H:%M}"
    return f"{w:%d-%m-%Y %H:%M}"


# =====================================================================
# Penilaian murni (tanpa I/O), supaya setiap kombinasi dapat diuji
# =====================================================================


def nilai_disk(nama: str, folder: Path, total: int, bebas: int) -> Pemeriksaan:
    ringkasan = f"Sisa {_ukuran(bebas)} dari {_ukuran(total)} ({folder})"
    saran = (
        "Kosongkan disk: pindahkan backup lama ke media lain atau hapus berkas "
        "yang tidak dipakai. Jangan menghapus folder data.",
    )
    if bebas < BATAS_DISK_MASALAH:
        return Pemeriksaan(nama, MASALAH, ringkasan, saran)
    if bebas < BATAS_DISK_PERINGATAN:
        return Pemeriksaan(nama, PERINGATAN, ringkasan, saran)
    return Pemeriksaan(nama, NORMAL, ringkasan)


def nilai_backup(
    *,
    terakhir: datetime | None,
    nama_berkas: str = "",
    ukuran: str = "",
    jumlah: int = 0,
    dibuat_di_sini: bool = True,
    otomatis_aktif: bool = True,
    folder_salinan: Path | None = None,
    salinan_ada: bool | None = None,
    gagal_pada: datetime | None = None,
    pesan_gagal: str = "",
    sekarang: datetime | None = None,
) -> Pemeriksaan:
    sekarang = sekarang or clock.now()
    nama = "Backup terakhir"
    if terakhir is None:
        if not dibuat_di_sini:
            return Pemeriksaan(
                nama,
                INFO,
                "Backup database dibuat di komputer server, bukan di komputer ini.",
            )
        gagal = f" Percobaan terakhir gagal: {pesan_gagal}" if gagal_pada else ""
        return Pemeriksaan(
            nama,
            MASALAH,
            "Belum ada backup yang berhasil dibuat." + gagal,
            ("Buka menu Backup, lalu tekan Backup Sekarang.",),
        )

    ringkasan = (
        f"{_waktu(terakhir, sekarang)} · {nama_berkas} ({ukuran}) · {jumlah} berkas tersimpan"
    )
    saran: list[str] = []
    tingkat = NORMAL
    if sekarang - terakhir > BATAS_UMUR_BACKUP:
        tingkat = PERINGATAN
        hari = (sekarang - terakhir).days
        ringkasan = f"Sudah {hari} hari tanpa backup baru. " + ringkasan
        saran.append(
            "Buka menu Backup, lalu tekan Backup Sekarang. Bila gagal, lihat "
            "logs\\app.log baris 'antrian.backup'."
        )
    if not otomatis_aktif:
        tingkat = PERINGATAN
        saran.append("Backup otomatis dimatikan. Nyalakan di Pengaturan › Backup.")
    if gagal_pada is not None:
        tingkat = MASALAH
        ringkasan = (
            f"Backup terakhir GAGAL ({_waktu(gagal_pada, sekarang)}): {pesan_gagal} "
            f"Yang terakhir berhasil: {ringkasan}"
        )
        saran.append("Buka menu Backup, perbaiki penyebabnya, lalu tekan Backup Sekarang.")
    if folder_salinan is not None and salinan_ada is not True:
        tingkat = MASALAH if tingkat == MASALAH else PERINGATAN
        if salinan_ada is None:
            saran.append(
                f"Folder salinan kedua {folder_salinan} tidak terjangkau. Pastikan "
                "disk atau flashdisk tersambung."
            )
        else:
            saran.append(
                f"Backup terakhir belum tersalin ke folder kedua {folder_salinan}."
            )
    return Pemeriksaan(nama, tingkat, ringkasan, tuple(saran))


def nilai_migrasi(terpasang: str | None, terbaru: str | None, dikenal: bool) -> Pemeriksaan:
    nama = "Revisi migrasi"
    if terpasang == terbaru:
        return Pemeriksaan(nama, NORMAL, f"Skema terbaru ({terpasang})")
    if terpasang is not None and not dikenal:
        return Pemeriksaan(
            nama,
            PERINGATAN,
            f"Database memakai skema {terpasang} yang lebih baru dari aplikasi ini.",
            ("Perbarui aplikasi di komputer ini ke versi yang sama dengan server.",),
        )
    return Pemeriksaan(
        nama,
        MASALAH,
        f"Skema database {terpasang or 'kosong'}, aplikasi mengharapkan {terbaru}.",
        ("Tutup lalu buka kembali aplikasi di komputer server agar migrasi berjalan.",),
    )


def nilai_perangkat(
    p, apk_terbaru: dict[str, int], sekarang: datetime | None = None
) -> Pemeriksaan:
    """Satu tablet. `p` adalah PerangkatInfo; token tidak pernah dibaca."""
    sekarang = sekarang or clock.now()
    nama = p.nama or "tanpa nama"
    # Nama bawaan tablet sudah diawali jenisnya ("Anjungan SM-S908E").
    if not nama.lower().startswith(p.label_jenis.lower()):
        nama = f"{p.label_jenis}: {nama}"
    bagian = [f"Terakhir terhubung {_waktu(p.terakhir_terlihat, sekarang)}"]
    if p.versi_nama or p.versi_kode:
        bagian.append(f"APK {p.versi_nama or p.versi_kode}")
    if p.printer_ok is not None:
        bagian.append("printer normal" if p.printer_ok else "printer bermasalah")
    ringkasan = " · ".join(bagian)

    saran: list[str] = []
    rincian: list[str] = []
    tingkat = NORMAL
    if p.terakhir_terlihat is None:
        tingkat = INFO
    elif sekarang - p.terakhir_terlihat > BATAS_TERPUTUS:
        # Tablet cadangan yang tidak menyala hari ini bukan masalah.
        if p.terakhir_terlihat.date() == sekarang.date():
            tingkat = PERINGATAN
            saran.append(
                "Tablet terputus. Pastikan tablet menyala, aplikasinya terbuka, "
                "dan tersambung ke Wi-Fi yang sama dengan komputer server."
            )
        else:
            tingkat = INFO

    terbaru = apk_terbaru.get(p.jenis)
    if terbaru and p.versi_kode and p.versi_kode < terbaru:
        tingkat = PERINGATAN if tingkat != MASALAH else tingkat
        saran.append(
            "APK di tablet lebih lama dari APK di server. Perbarui dari layar "
            "pengaturan aplikasi di tablet."
        )
    if p.printer_ok is False:
        if p.printer_pesan:
            rincian.append(f"Printer: {samarkan(p.printer_pesan)}")
        # Laporan cetak kemarin dari tablet yang belum menyala lagi hari ini
        # belum tentu masih benar; cukup tampil sebagai keterangan.
        waktu = getattr(p, "printer_waktu", None)
        if waktu is None or waktu.date() == sekarang.date():
            tingkat = PERINGATAN if tingkat != MASALAH else tingkat
            saran.append(
                "Periksa kabel USB/OTG, daya, dan kertas printer. Kegagalan cetak "
                "tidak membatalkan nomor."
            )
    return Pemeriksaan(nama, tingkat, ringkasan, tuple(saran), tuple(rincian))


def nilai_token_bersama(aktif: bool, terpasang: int) -> Pemeriksaan:
    """
    Token bersama lama melemahkan pencabutan perangkat.

    Selama token bersama diterima, tablet yang dicabut tetap dapat masuk
    memakai token itu (tanpa menyebut device_id-nya). Begitu semua tablet
    dipasangkan dengan kode, token bersama sebaiknya dimatikan.
    """
    nama = "Token bersama"
    if not aktif:
        return Pemeriksaan(
            nama, NORMAL, "Dimatikan: hanya perangkat yang dipasangkan yang diterima."
        )
    langkah = (
        "Pasangkan setiap tablet dengan kode dari Pengaturan › Layanan Anjungan, "
        "lalu matikan token bersama di halaman yang sama."
    )
    if terpasang:
        return Pemeriksaan(
            nama,
            PERINGATAN,
            "Masih diterima, padahal sudah ada tablet yang dipasangkan. Perangkat "
            "yang dicabut masih dapat masuk dengan token bersama.",
            (langkah,),
        )
    return Pemeriksaan(
        nama,
        INFO,
        "Masih diterima untuk tablet lama yang belum dipasangkan.",
        (langkah,),
    )


def nilai_hash_kata_sandi(tidak_sah: int, total: int) -> Pemeriksaan:
    """
    Kata sandi harus tersimpan sebagai hash scrypt, tidak pernah teks biasa.

    Akun dengan nilai yang bukan format `scrypt$...` (data impor lama atau
    isian manual di database) tidak dapat dipakai masuk dan menandakan ada
    jalur penulisan yang melewati aplikasi.
    """
    nama = "Penyimpanan kata sandi"
    if tidak_sah:
        return Pemeriksaan(
            nama,
            PERINGATAN,
            f"{tidak_sah} dari {total} akun tidak memakai hash kata sandi yang sah.",
            (
                "Setel ulang kata sandi akun itu lewat Data Master › Setel Ulang "
                "Kata Sandi.",
            ),
        )
    return Pemeriksaan(
        nama, NORMAL, f"Seluruh {total} akun memakai hash scrypt bergaram."
    )


def _periksa_kata_sandi() -> Pemeriksaan:
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import User

    with session_scope() as session:
        total = session.scalar(sa.select(sa.func.count()).select_from(User)) or 0
        tidak_sah = (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(User)
                .where(~User.password_hash.like("scrypt$%"))
            )
            or 0
        )
    return nilai_hash_kata_sandi(tidak_sah, total)


def ringkas_galat(baris: list[str], sekarang: datetime | None = None) -> Pemeriksaan:
    """Hitung galat penting pada `JENDELA_GALAT` dari baris-baris app.log."""
    sekarang = sekarang or clock.now()
    batas = sekarang - JENDELA_GALAT
    temuan: list[tuple[datetime, str, str]] = []
    for teks in baris:
        cocok = _BARIS_GALAT.match(teks.rstrip("\r\n"))
        if not cocok:
            continue
        try:
            waktu = datetime.strptime(cocok.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if waktu >= batas:
            temuan.append((waktu, cocok.group(3), cocok.group(4)))

    nama = "Galat penting (24 jam)"
    if not temuan:
        return Pemeriksaan(nama, NORMAL, "Tidak ada galat tercatat.")
    terakhir = temuan[-1][0]
    rincian = tuple(
        f"{w:%H:%M} {sumber}: {samarkan(pesan)[:160]}"
        for w, sumber, pesan in reversed(temuan[-BATAS_RINCIAN_GALAT:])
    )
    return Pemeriksaan(
        nama,
        PERINGATAN,
        f"{len(temuan)} galat tercatat, terakhir {_waktu(terakhir, sekarang)}.",
        ("Detail teknis ada di logs\\app.log pada jam yang sama.",),
        rincian,
    )


# =====================================================================
# Pengumpulan fakta
# =====================================================================


def _periksa_database() -> Pemeriksaan:
    from app.core.database import periksa_koneksi

    config = get_config()
    mulai = time.perf_counter()
    terhubung = periksa_koneksi()
    lama = (time.perf_counter() - mulai) * 1000
    jenis = "SQLite (satu komputer)" if config.memakai_sqlite else "PostgreSQL"
    # teks_lokasi tidak pernah memuat kata sandi.
    lokasi = config.teks_lokasi
    if not terhubung:
        return Pemeriksaan(
            "Database",
            MASALAH,
            f"{jenis} tidak terjangkau: {lokasi}",
            (
                "Pastikan komputer server menyala dan layanan PostgreSQL berjalan.",
                "Periksa jaringan, Firewall TCP 5432, dan pg_hba.conf.",
            ),
        )
    return Pemeriksaan(
        "Database",
        NORMAL,
        f"{jenis} terhubung ({lama:.0f} ms) · {lokasi} · aplikasi v{__version__}",
    )


def _periksa_migrasi() -> Pemeriksaan:
    from alembic.script import ScriptDirectory

    from app.core.migrations import alembic_config, current_revision

    skrip = ScriptDirectory.from_config(alembic_config())
    terpasang = current_revision()
    terbaru = skrip.get_current_head()
    dikenal = True
    if terpasang is not None:
        try:
            dikenal = skrip.get_revision(terpasang) is not None
        except Exception:  # noqa: BLE001 - revisi asing melempar beragam galat
            dikenal = False
    return nilai_migrasi(terpasang, terbaru, dikenal)


def _periksa_api() -> Pemeriksaan:
    from app.services.status_anjungan import api_siap, periksa_status_anjungan

    status = periksa_status_anjungan()
    nama = "API anjungan"
    if status is None:
        return Pemeriksaan(
            nama,
            INFO,
            "Tidak dipakai: anjungan Android hanya ada pada pemasangan PostgreSQL.",
        )
    if status.tingkat == MASALAH or "berjalan" not in status.ringkas:
        return Pemeriksaan(
            nama, status.tingkat, status.judul or status.ringkas, status.saran
        )

    # API menjawab /health, tetapi belum tentu dapat membaca database.
    from app.services.kiosk_server import komputer_server, port_api

    config = get_config()
    host = "127.0.0.1" if komputer_server() else (config.url_database.host or "127.0.0.1")
    siap = api_siap(host, port_api())
    if siap is False:
        return Pemeriksaan(
            nama,
            MASALAH,
            "API menyala, tetapi tidak dapat membaca database — tablet tidak "
            "dapat mengambil nomor.",
            (
                "Buka Pengaturan › Layanan Anjungan, lalu tekan Pasang ulang & "
                "nyalakan ulang.",
                "Lihat logs\\kiosk-api-stderr.log di komputer server.",
            ),
        )
    teks = status.ringkas.removeprefix("API anjungan: ").replace("●", "").strip()
    teks = status.judul or (teks[:1].upper() + teks[1:])
    return Pemeriksaan(nama, status.tingkat, teks, status.saran)


def _apk_terbaru() -> dict[str, int]:
    from app.services.apk_anjungan import folder_apk, info_apk

    hasil: dict[str, int] = {}
    for jenis in ("anjungan", "layar"):
        info = info_apk(folder_apk(base_dir()), jenis)
        if info is not None:
            # Jenis perangkat di database memakai "layar_antrian".
            hasil["layar_antrian" if jenis == "layar" else jenis] = info.kode_versi
    return hasil


def _periksa_perangkat(auth: AuthService) -> list[Pemeriksaan]:
    from app.services.device_service import PerangkatService, token_bersama_aktif

    if get_config().memakai_sqlite:
        return []
    daftar = PerangkatService(auth).daftar()
    jumlah_terpasang = sum(1 for p in daftar if p.dipasangkan and not p.dicabut)
    token = nilai_token_bersama(token_bersama_aktif(), jumlah_terpasang)
    aktif = [p for p in daftar if not p.dicabut and p.dipasangkan]
    dicabut = [p for p in daftar if p.dicabut]
    if not aktif and not dicabut:
        return [
            Pemeriksaan(
                "Perangkat Android",
                INFO,
                "Belum ada tablet yang dipasangkan.",
            ),
            token,
        ]
    apk = _apk_terbaru()
    sekarang = clock.now()
    hasil = [nilai_perangkat(p, apk, sekarang) for p in aktif]
    if dicabut:
        hasil.append(
            Pemeriksaan(
                "Perangkat dicabut",
                INFO,
                f"{len(dicabut)} perangkat dicabut dan tidak dapat mengakses API.",
            )
        )
    hasil.append(token)
    return hasil


def _periksa_printer(settings) -> Pemeriksaan:
    from app.services.ticket_service import mode_pencetak

    mode = (mode_pencetak(settings) or "pdf").strip().lower()
    nama = "Printer tiket (komputer ini)"
    if mode == "none":
        return Pemeriksaan(nama, INFO, "Komputer ini tidak mencetak tiket.")
    if mode != "system":
        return Pemeriksaan(nama, INFO, "Tiket disimpan sebagai PDF, tidak dicetak.")
    from PySide6.QtPrintSupport import QPrinterInfo

    bawaan = QPrinterInfo.defaultPrinter()
    if bawaan.isNull():
        return Pemeriksaan(
            nama,
            MASALAH,
            "Tidak ada printer bawaan Windows.",
            ("Jadikan printer tiket sebagai printer bawaan di Pengaturan Windows.",),
        )
    return Pemeriksaan(nama, NORMAL, f"Printer bawaan: {bawaan.printerName()}")


def _periksa_backup(backup: BackupService) -> Pemeriksaan:
    daftar = backup.list_backup()
    status = backup.status_backup()
    terakhir = daftar[0] if daftar else None
    folder_salinan = backup.folder_salinan
    salinan_ada: bool | None = None
    if folder_salinan is not None and terakhir is not None:
        try:
            if folder_salinan.is_dir():
                salinan_ada = (folder_salinan / terakhir.nama).is_file()
        except OSError:
            salinan_ada = None
    return nilai_backup(
        terakhir=terakhir.dibuat_pada if terakhir else None,
        nama_berkas=terakhir.nama if terakhir else "",
        ukuran=terakhir.label_ukuran if terakhir else "",
        jumlah=len(daftar),
        dibuat_di_sini=_boleh_backup_di_sini(),
        otomatis_aktif=backup.settings.get_bool("backup.auto_enabled", True),
        folder_salinan=folder_salinan,
        salinan_ada=salinan_ada,
        gagal_pada=status.terakhir_gagal if status.gagal_terakhir else None,
        pesan_gagal=status.pesan_gagal,
    )


def _periksa_disk() -> list[Pemeriksaan]:
    config = get_config()
    folder = {
        "Disk data": config.db_path.parent if config.memakai_sqlite else config.log_dir,
        "Disk backup": config.backup_dir,
    }
    hasil: list[Pemeriksaan] = []
    sudah: set[str] = set()
    for nama, path in folder.items():
        path = path if path.exists() else path.parent
        pakai = shutil.disk_usage(path)
        # Data dan backup pada disk yang sama cukup dilaporkan sekali.
        kunci = path.resolve().anchor.lower()
        if kunci in sudah:
            continue
        sudah.add(kunci)
        hasil.append(nilai_disk(nama, path, pakai.total, pakai.free))
    return hasil


def _baca_ekor_log() -> list[str]:
    berkas = get_config().log_dir / "app.log"
    if not berkas.exists():
        return []
    with berkas.open("rb") as f:
        ukuran = f.seek(0, 2)
        f.seek(max(0, ukuran - _EKOR_LOG_BYTE))
        return f.read().decode("utf-8", errors="replace").splitlines()


def _periksa_galat() -> Pemeriksaan:
    return ringkas_galat(_baca_ekor_log())


class KesehatanService:
    """Pemeriksaan kesehatan sistem; hanya ADMIN (CONFIG_MANAGE)."""

    def __init__(self, auth: AuthService, backup: BackupService) -> None:
        self.auth = auth
        self.backup = backup

    def periksa(self) -> LaporanKesehatan:
        self.auth.require_permission(Permission.CONFIG_MANAGE)
        butir: list[Pemeriksaan] = []

        def jalankan(nama: str, aksi) -> None:
            try:
                hasil = aksi()
            except Exception:
                logger.exception("Pemeriksaan kesehatan '%s' gagal", nama)
                butir.append(
                    Pemeriksaan(
                        nama,
                        PERINGATAN,
                        "Tidak dapat diperiksa. Detailnya tersimpan di file log.",
                    )
                )
                return
            butir.extend(hasil if isinstance(hasil, list) else [hasil])

        jalankan("Database", _periksa_database)
        jalankan("Revisi migrasi", _periksa_migrasi)
        jalankan("Penyimpanan kata sandi", _periksa_kata_sandi)
        jalankan("API anjungan", _periksa_api)
        jalankan("Perangkat Android", lambda: _periksa_perangkat(self.auth))
        jalankan("Printer tiket (komputer ini)", lambda: _periksa_printer(self.backup.settings))
        jalankan("Backup terakhir", lambda: _periksa_backup(self.backup))
        jalankan("Kapasitas disk", _periksa_disk)
        jalankan("Galat penting (24 jam)", _periksa_galat)
        return LaporanKesehatan(clock.now(), tuple(butir))
