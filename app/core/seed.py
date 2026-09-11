"""
Data awal aplikasi.

Bersifat idempotent: aman dijalankan berkali-kali, data yang sudah ada
tidak diduplikasi dan tidak ditimpa.

Seed membuat satu akun ADMIN bawaan agar aplikasi dapat dipakai pertama
kali. Akun tersebut WAJIB mengganti kata sandinya saat login pertama,
karena kata sandi bawaan bersifat umum dan tidak rahasia.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import session_scope
from app.core.logger import get_logger
from app.core.security import hash_password
from app.models import (
    ApplicationSetting,
    Branch,
    Counter,
    RecordStatus,
    ServiceCategory,
    User,
    UserRole,
)

logger = get_logger("seed")

DEFAULT_BRANCH_CODE = "PUSAT"

# Akun bawaan untuk login pertama kali. Kata sandinya sengaja mudah ditebak
# dan karena itu WAJIB diganti pada login pertama (must_change_password).
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"

_COUNTERS: list[tuple[str, str]] = [
    ("LOKET-1", "Loket 1"),
    ("LOKET-2", "Loket 2"),
    ("LOKET-3", "Loket 3"),
]

# (code, name, prefix, display_order, kode induk)
# prefix menentukan nomor antrian: A-001, B-001, C-001.
#
# Induk disebut dengan KODE, bukan id, karena id-nya belum ada saat daftar
# ini ditulis. Urutan daftar sekaligus urutan penyisipan: induk selalu
# berada di atas anaknya, sehingga id induk pasti sudah terbit saat
# anaknya menyusul.
#
# Jenis layanan yang punya anak berubah menjadi KELOMPOK dan berhenti
# menerbitkan nomor. Prefix-nya tetap diisi supaya tetap unik dan tetap
# sah bila kelak anaknya dilepas kembali.
_CATEGORIES: list[tuple[str, str, str, int, str | None]] = [
    ("KONSULTASI", "Konsultasi", "A", 1, None),
    ("PBB", "PBB", "PB", 1, "KONSULTASI"),
    ("PKB", "PKB", "KB", 2, "KONSULTASI"),
    ("PAT", "PAT", "AT", 3, "KONSULTASI"),
    ("REKLAME", "Reklame", "RK", 4, "KONSULTASI"),
    ("PBJT", "PBJT", "PJ", 5, "KONSULTASI"),
    ("RESTORAN", "Restoran", "RS", 1, "PBJT"),
    ("PARKIR", "Parkir", "PR", 2, "PBJT"),
    ("HOTEL", "Hotel", "HT", 3, "PBJT"),
    ("HIBURAN", "Hiburan", "HB", 4, "PBJT"),
    ("PENGADUAN", "Pengaduan", "B", 2, None),
    ("INFORMASI", "Informasi", "C", 3, None),
]

# (key, value, description)
_SETTINGS: list[tuple[str, str, str]] = [
    ("backup.auto_enabled", "true",
     "Buat backup otomatis satu kali setiap hari saat aplikasi dibuka"),
    ("backup.pg_dump_path", "",
     "Folder perkakas PostgreSQL bila tidak ada di PATH; kosongkan untuk SQLite"),
    ("backup.retention_days", "30",
     "Lama backup disimpan sebelum dihapus, dalam hari"),
    ("dashboard.refresh_seconds", "30",
     "Jeda penyegaran layar ringkasan harian, dalam detik"),
    ("display.theme", "kaca", "Tampilan layar antrian"),
    ("display.title", "ANTRIAN PELAYANAN CRO", "Judul pada layar display"),
    ("display.info", "", "Pengumuman pada tema Split Informasi"),
    ("display.next_count", "3", "Jumlah nomor berikutnya pada papan kios"),
    ("display.list_rows", "5", "Baris nomor per kolom pada daftar menunggu"),
    ("display.list_font_size", "0", "Ukuran huruf nomor menunggu; 0 = otomatis"),
    ("display.rotate_seconds", "3", "Jeda pergantian halaman daftar menunggu, detik"),
    ("display.number_font_scale", "100", "Ukuran huruf nomor antrian di layar, dalam persen"),
    ("display.sound_enabled", "true", "Suara saat nomor dipanggil"),
    ("queue.max_call_attempts", "3", "Batas pemanggilan sebelum dianggap tidak hadir"),
    ("queue.registration_open", "true", "Loket dan kios sedang menerima nomor baru"),
    ("queue.registration_closed_date", "",
     "Tanggal pendaftaran terakhir ditutup; dikelola otomatis oleh sistem"),
    ("kiosk.cooldown_seconds", "10",
     "Jeda antar-pengambilan nomor di mesin kios, dalam detik"),
    ("kiosk.welcome_kind", "teks",
     "Jenis isi panel sambutan anjungan: teks atau folder media"),
    ("kiosk.welcome_text", "",
     "Teks sambutan anjungan; kosong berarti memakai teks bawaan"),
    ("kiosk.welcome_file", "",
     "Berkas terakhir yang ditambahkan ke folder media/kiosk"),
    ("kiosk.welcome_slide_seconds", "10",
     "Lama tiap gambar di folder media anjungan, dalam detik"),
    ("kiosk.info_ratio", "3",
     "Perbandingan lebar:tinggi panel informasi anjungan"),
    ("kiosk.panel_order", "iklan-atas",
     "Iklan di atas kartu layanan, atau sebaliknya"),
    ("survey.enabled", "true", "Tampilkan survey setelah pelayanan selesai"),
    ("ticket.footer", "Silakan menunggu hingga nomor Anda dipanggil.",
     "Teks penutup pada tiket antrian"),
    ("ticket.printer", "pdf",
     "Cara mencetak tiket: pdf, system, atau none"),
]


def _seed_branch(session: Session) -> Branch:
    branch = session.scalar(select(Branch).where(Branch.code == DEFAULT_BRANCH_CODE))
    if branch is None:
        branch = Branch(
            code=DEFAULT_BRANCH_CODE,
            name="Kantor Pelayanan",
            status=RecordStatus.ACTIVE,
        )
        session.add(branch)
        session.flush()
        logger.info("Seed: cabang %s dibuat", DEFAULT_BRANCH_CODE)
    return branch


def _seed_counters(session: Session, branch: Branch) -> int:
    created = 0
    for code, name in _COUNTERS:
        exists = session.scalar(
            select(Counter).where(Counter.branch_id == branch.id, Counter.code == code)
        )
        if exists is None:
            session.add(
                Counter(
                    branch_id=branch.id,
                    code=code,
                    name=name,
                    status=RecordStatus.ACTIVE,
                )
            )
            created += 1
    if created:
        logger.info("Seed: %d loket dibuat", created)
    return created


def _seed_categories(session: Session, branch: Branch) -> int:
    created = 0
    #: kode -> id, terisi sambil berjalan supaya anak menemukan induknya.
    #: Ikut memuat jenis layanan yang sudah ada agar seed yang diulang
    #: pada database lama tetap dapat memasang anak di bawah induk yang
    #: sudah tersimpan lebih dahulu.
    id_kode: dict[str, int] = {}

    for code, name, prefix, order, kode_induk in _CATEGORIES:
        exists = session.scalar(
            select(ServiceCategory).where(
                ServiceCategory.branch_id == branch.id, ServiceCategory.code == code
            )
        )
        if exists is not None:
            id_kode[code] = exists.id
            continue

        category = ServiceCategory(
            branch_id=branch.id,
            parent_id=id_kode.get(kode_induk) if kode_induk else None,
            code=code,
            name=name,
            prefix=prefix,
            display_order=order,
            status=RecordStatus.ACTIVE,
        )
        session.add(category)
        # id induk harus sudah nyata sebelum anaknya disusun; tanpa flush,
        # seluruh baris baru menunggu di memori tanpa id sampai commit.
        session.flush()
        id_kode[code] = category.id
        created += 1

    if created:
        logger.info("Seed: %d jenis layanan dibuat", created)
    return created


def _seed_settings(session: Session) -> int:
    created = 0
    for key, value, description in _SETTINGS:
        exists = session.scalar(
            select(ApplicationSetting).where(ApplicationSetting.key == key)
        )
        if exists is None:
            session.add(
                ApplicationSetting(key=key, value=value, description=description)
            )
            created += 1
    if created:
        logger.info("Seed: %d pengaturan dibuat", created)
    return created


def _seed_admin(session: Session, branch: Branch) -> int:
    """
    Buat akun ADMIN bawaan bila belum ada user sama sekali.

    Pemeriksaannya adalah "belum ada user mana pun", bukan "belum ada admin".
    Dengan begitu administrator yang sengaja menghapus akun bawaan setelah
    membuat akun sendiri tidak akan mendapatkannya kembali setiap start.
    """
    sudah_ada_user = session.scalar(select(User).limit(1))
    if sudah_ada_user is not None:
        return 0

    session.add(
        User(
            branch_id=branch.id,
            username=DEFAULT_ADMIN_USERNAME,
            full_name="Administrator",
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            status=RecordStatus.ACTIVE,
            must_change_password=True,
        )
    )
    logger.warning(
        "Seed: akun admin bawaan dibuat dengan kata sandi bawaan. "
        "Kata sandi WAJIB diganti pada login pertama."
    )
    return 1


def seed_initial_data() -> dict[str, int]:
    """
    Isi data master awal bila belum ada.

    Mengembalikan jumlah baris yang benar-benar dibuat, sehingga pemanggilan
    kedua menghasilkan angka nol semua.
    """
    with session_scope() as session:
        branch = _seed_branch(session)
        return {
            "counters": _seed_counters(session, branch),
            "categories": _seed_categories(session, branch),
            "settings": _seed_settings(session),
            "users": _seed_admin(session, branch),
        }
