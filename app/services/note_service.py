"""
Pengaduan dan catatan petugas atas satu antrian.

MODUL INI SATU-SATUNYA YANG MENYENTUH DATA PRIBADI PENGUNJUNG. Nama, nomor
pelanggan, telepon, email, dan alamat hanya ada di tabel `queue_note`, dan
hanya bila petugas mengisikannya. Antrian itu sendiri tetap anonim.

Dua akibatnya yang harus dijaga di sini, bukan di UI:

1. **Isinya tidak pernah masuk audit log.** Audit mencatat BAHWA sebuah
   lembar disimpan atau dihapus, oleh siapa, untuk nomor antrian mana —
   tidak pernah apa yang tertulis di dalamnya. Audit log dibaca ADMIN dan
   ikut terbawa setiap backup; menyalin nama dan nomor telepon ke sana
   berarti menggandakan data pribadi ke tempat yang tidak pernah ditinjau.
2. **Menghapus bukan hak penulisnya.** Petugas menulis, ADMIN menghapus.
   Penulis yang sekaligus dapat menghilangkan tulisannya membuat catatan
   itu tidak berguna sebagai bukti apa pun.
3. **Identitas pelapor punya masa simpan.** Sesudah
   `privasi.retensi_pengaduan_bulan` (bawaan 24 bulan) identitasnya
   dikosongkan otomatis — lihat `anonimkan_kedaluwarsa`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core import clock
from app.core.database import session_scope
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import AuditAction, QueueNote
from app.repositories.queue_note_repository import (
    BATAS_PENCARIAN,
    QueueNoteRepository,
)
from app.repositories.queue_repository import QueueRepository
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission

logger = get_logger("note")

#: Batas panjang tiap isian. Kolom Text tidak membatasi apa pun, dan tanpa
#: batas di sini satu tempelan tak sengaja dari dokumen lain masuk utuh ke
#: database lalu ikut ke setiap berkas backup.
PANJANG_NAMA = 120
PANJANG_NOMOR_PELANGGAN = 40
PANJANG_TELEPON = 30
PANJANG_EMAIL = 120
PANJANG_ALAMAT = 500
PANJANG_DESKRIPSI = 4000
PANJANG_CATATAN = 2000

#: Angka minimum yang masih masuk akal untuk sebuah nomor telepon.
#: Pemeriksaannya sengaja longgar: petugas sedang berhadapan dengan orang
#: yang menunggu, dan menolak nomor yang bentuknya tidak biasa lebih
#: merugikan daripada menyimpan nomor yang kurang rapi.
DIGIT_TELEPON_MINIMUM = 6

#: Pengaturan masa simpan identitas pelapor, dalam bulan. 0 = selamanya.
KUNCI_RETENSI = "privasi.retensi_pengaduan_bulan"


def batas_retensi(hari_ini: date, bulan: int) -> date:
    """
    Tanggal antrian paling awal yang identitas pelapornya masih disimpan.

    Mundur `bulan` bulan kalender, dengan tanggal dipangkas ke akhir bulan
    tujuan (31 Mei mundur 3 bulan = 28/29 Februari). Bukan 30 hari per
    bulan: dua tahun yang dijanjikan kepada pelapor adalah dua tahun
    kalender, bukan 720 hari.
    """
    indeks = hari_ini.year * 12 + hari_ini.month - 1 - bulan
    tahun, bulan_ke = divmod(indeks, 12)
    berikut = indeks + 1
    awal_bulan_berikut = date(berikut // 12, berikut % 12 + 1, 1)
    hari_terakhir = (awal_bulan_berikut - timedelta(days=1)).day
    return date(tahun, bulan_ke + 1, min(hari_ini.day, hari_terakhir))


@dataclass(frozen=True)
class NoteInfo:
    """Lembar pengaduan/catatan yang aman dibawa ke UI, lepas dari session."""

    id: int
    queue_id: int
    queue_number: str
    queue_date: date
    nama: str | None
    nomor_pelanggan: str | None
    telepon: str | None
    email: str | None
    alamat: str | None
    deskripsi: str | None
    catatan: str | None
    counter_name: str | None
    officer_name: str | None
    category_name: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def ada_pengaduan(self) -> bool:
        return bool((self.deskripsi or "").strip())

    @property
    def ringkas(self) -> str:
        """Satu baris untuk kolom daftar, dipotong bila kepanjangan."""
        isi = (self.deskripsi or self.catatan or "").strip().replace("\n", " ")
        return isi if len(isi) <= 80 else isi[:77] + "..."


def _as_note_info(row: QueueNote) -> NoteInfo:
    return NoteInfo(
        id=row.id,
        queue_id=row.queue_id,
        queue_number=row.queue.queue_number,
        queue_date=row.queue.queue_date,
        nama=row.nama,
        nomor_pelanggan=row.nomor_pelanggan,
        telepon=row.telepon,
        email=row.email,
        alamat=row.alamat,
        deskripsi=row.deskripsi,
        catatan=row.catatan,
        counter_name=row.counter.name if row.counter else None,
        officer_name=row.officer.full_name if row.officer else None,
        category_name=row.queue.category.name if row.queue.category else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _bersih(nilai: str | None, batas: int, kapsi: str) -> str | None:
    """Rapikan satu isian, atau tolak bila melebihi batasnya."""
    teks = (nilai or "").strip()
    if not teks:
        return None
    if len(teks) > batas:
        raise ValidationError(f"{kapsi} terlalu panjang, maksimum {batas} karakter.")
    return teks


def _periksa_email(email: str | None) -> str | None:
    """
    Periksa bentuk email seadanya.

    Sengaja TIDAK memakai pola ketat. Alamat email yang sah bentuknya jauh
    lebih beragam daripada yang biasa dikira, dan menolak alamat yang
    sebenarnya benar membuat petugas berhenti mengisinya sama sekali. Yang
    ditolak hanya yang pasti keliru: tanpa "@", atau mengandung spasi.
    """
    if email is None:
        return None
    if " " in email or email.count("@") != 1 or email.startswith("@") or email.endswith("@"):
        raise ValidationError("Alamat email tidak sesuai bentuknya.")
    return email


def _periksa_telepon(telepon: str | None) -> str | None:
    """Pastikan nomor telepon setidaknya berisi angka yang cukup."""
    if telepon is None:
        return None
    if sum(huruf.isdigit() for huruf in telepon) < DIGIT_TELEPON_MINIMUM:
        raise ValidationError("Nomor telepon terlalu pendek.")
    return telepon


class NoteService:
    """Penulisan dan pembacaan pengaduan serta catatan petugas."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    # =================================================================
    # Penulisan
    # =================================================================

    def simpan(
        self,
        queue_id: int,
        *,
        nama: str | None = None,
        nomor_pelanggan: str | None = None,
        telepon: str | None = None,
        email: str | None = None,
        alamat: str | None = None,
        deskripsi: str | None = None,
        catatan: str | None = None,
    ) -> NoteInfo:
        """
        Simpan atau perbarui lembar milik satu antrian.

        Satu antrian punya paling banyak satu lembar; pemanggilan berikutnya
        menyunting yang sudah ada. Petugas kedua yang menambahkan sesuatu
        pada pelayanan yang sama menulis di lembar yang sama, bukan membuat
        lembar tandingan yang isinya saling bertentangan.

        Lembar hanya dapat disunting pada HARI yang sama dengan antriannya.
        Pengaduan yang masih bisa diubah berhari-hari kemudian tidak berguna
        sebagai bukti apa pun, dan tidak ada seorang pun yang dapat
        mengetahui versi mana yang pernah dibaca supervisor.

        Isian identitas menjadi WAJIB begitu ada deskripsi pengaduan:
        pengaduan tanpa nama dan nomor pelanggan tidak dapat ditindaklanjuti
        siapa pun, dan hanya akan menumpuk. Catatan petugas boleh berdiri
        sendiri tanpa identitas apa pun.
        """
        sesi = self.auth.require_permission(Permission.NOTE_WRITE)
        if sesi.user_id is None:
            raise BusinessRuleError(
                "Sesi ini tidak mewakili petugas tertentu sehingga tidak dapat "
                "menulis pengaduan."
            )

        nama = _bersih(nama, PANJANG_NAMA, "Nama")
        nomor_pelanggan = _bersih(
            nomor_pelanggan, PANJANG_NOMOR_PELANGGAN, "Nomor pelanggan"
        )
        telepon = _periksa_telepon(_bersih(telepon, PANJANG_TELEPON, "Nomor telepon"))
        email = _periksa_email(_bersih(email, PANJANG_EMAIL, "Alamat email"))
        alamat = _bersih(alamat, PANJANG_ALAMAT, "Alamat")
        deskripsi = _bersih(deskripsi, PANJANG_DESKRIPSI, "Deskripsi pengaduan")
        catatan = _bersih(catatan, PANJANG_CATATAN, "Catatan petugas")

        if deskripsi is None and catatan is None:
            raise ValidationError(
                "Isi deskripsi pengaduan atau catatan petugas lebih dahulu."
            )
        if deskripsi is not None:
            if nama is None:
                raise ValidationError("Nama pelapor wajib diisi untuk pengaduan.")
            if nomor_pelanggan is None:
                raise ValidationError(
                    "Nomor pelanggan wajib diisi untuk pengaduan."
                )

        with session_scope() as session:
            antrian = QueueRepository(session).get_by_id(queue_id)
            if antrian is None or antrian.branch_id != sesi.branch_id:
                raise NotFoundError("Antrian tidak ditemukan.")
            if antrian.queue_date != clock.today():
                raise BusinessRuleError(
                    f"Antrian {antrian.queue_number} bukan antrian hari ini "
                    "sehingga lembarnya tidak dapat diubah lagi."
                )

            repo = QueueNoteRepository(session)
            lembar = repo.get_by_queue(queue_id)
            baru = lembar is None

            if lembar is None:
                lembar = QueueNote(
                    queue_id=antrian.id,
                    branch_id=antrian.branch_id,
                    counter_id=antrian.counter_id,
                    # Penulis PERTAMA, dan tidak berubah walau disunting
                    # petugas lain. Siapa yang menyunting terbaca di audit
                    # log; kolom ini menjawab pertanyaan yang berbeda —
                    # pelayanan siapa yang melahirkan lembar ini.
                    officer_id=sesi.user_id,
                )

            lembar.nama = nama
            lembar.nomor_pelanggan = nomor_pelanggan
            lembar.telepon = telepon
            lembar.email = email
            lembar.alamat = alamat
            lembar.deskripsi = deskripsi
            lembar.catatan = catatan

            if baru:
                repo.simpan(lembar)
            else:
                session.flush()

            # Isi lembar TIDAK ikut dicatat — lihat docstring modul.
            audit_service.record(
                session,
                AuditAction.SAVE_NOTE,
                user_id=sesi.user_id,
                entity_type="queue_note",
                entity_id=lembar.id,
                nomor=antrian.queue_number,
                baru=baru,
                pengaduan=deskripsi is not None,
            )
            logger.info(
                "Lembar antrian %s %s oleh %s",
                antrian.queue_number,
                "dibuat" if baru else "diperbarui",
                sesi.username,
            )
            return _as_note_info(repo.get_by_queue(queue_id))

    def hapus(self, note_id: int) -> None:
        """
        Hapus satu lembar beserta seluruh data pribadi di dalamnya.

        Sapuan otomatis hanya mengosongkan identitas pelapor (lihat
        `anonimkan_kedaluwarsa`); lembarnya sendiri disimpan sampai ada
        yang menghapusnya. Karena itu penghapusan
        harus benar-benar menghilangkan barisnya, bukan menandainya
        nonaktif — baris yang "dihapus" tetapi masih tersimpan hanya
        memindahkan data pribadi ke tempat yang tidak lagi diperiksa siapa
        pun, dan tetap ikut ke setiap berkas backup.
        """
        sesi = self.auth.require_permission(Permission.NOTE_DELETE)

        with session_scope() as session:
            repo = QueueNoteRepository(session)
            lembar = repo.get_by_id(note_id)
            if lembar is None or lembar.branch_id != sesi.branch_id:
                raise NotFoundError("Lembar pengaduan tidak ditemukan.")

            nomor = lembar.queue.queue_number
            ada_pengaduan = lembar.ada_pengaduan
            repo.hapus(lembar)

            audit_service.record(
                session,
                AuditAction.DELETE_NOTE,
                user_id=sesi.user_id,
                entity_type="queue_note",
                entity_id=note_id,
                nomor=nomor,
                pengaduan=ada_pengaduan,
            )
            logger.info("Lembar antrian %s dihapus oleh %s", nomor, sesi.username)

    def anonimkan_kedaluwarsa(self) -> int:
        """
        Kosongkan identitas pelapor yang sudah melewati masa simpannya.

        Mengapa dianonimkan, bukan dihapus: isi pengaduan tetap dibutuhkan
        untuk laporan dan untuk melihat keluhan yang berulang, sedangkan
        nama, nomor pelanggan, telepon, email, dan alamat tidak lagi punya
        kegunaan sesudah tindak lanjutnya lama selesai — menyimpannya
        terus hanya memperpanjang risiko bocornya lewat backup.

        Tidak menuntut hak akses dan auditnya tidak beratas nama siapa pun,
        dengan alasan yang sama seperti `QueueService.hanguskan_hari_lalu`:
        ini sapuan yang berjalan saat aplikasi mulai dan saat tanggal
        berganti, bukan perbuatan petugas yang kebetulan login.

        Kata-kata pelapor di kolom deskripsi tidak disentuh. Bila pelapor
        menulis nomor teleponnya di sana, nomor itu tetap tersimpan —
        mesin tidak dapat memilah kalimat bebas dengan aman.
        """
        from app.services.settings_service import SettingsService

        bulan = SettingsService(self.auth).get_int(KUNCI_RETENSI, 24)
        if bulan <= 0:
            return 0
        batas = batas_retensi(clock.today(), bulan)

        with session_scope() as session:
            per_cabang = QueueNoteRepository(session).anonimkan_sebelum(batas)
            for branch_id, jumlah in per_cabang.items():
                # Hanya jumlah dan tanggal batas, tidak satu pun isi lembar
                # (aturan nomor 1 di atas berlaku juga untuk sapuan ini).
                audit_service.record(
                    session,
                    AuditAction.ANONYMIZE_NOTE,
                    user_id=None,
                    entity_type="queue_note",
                    entity_id=None,
                    jumlah=jumlah,
                    branch_id=branch_id,
                    sebelum=str(batas),
                )
        total = sum(per_cabang.values())
        if total:
            logger.info(
                "Identitas pelapor dianonimkan: %d lembar sebelum %s", total, batas
            )
        return total

    # =================================================================
    # Pembacaan
    # =================================================================

    def ambil(self, queue_id: int) -> NoteInfo | None:
        """Lembar milik satu antrian, atau None bila belum pernah ditulis."""
        self.auth.require_permission(Permission.NOTE_VIEW)

        with session_scope() as session:
            lembar = QueueNoteRepository(session).get_by_queue(queue_id)
            return _as_note_info(lembar) if lembar else None

    def cari(
        self,
        kata: str = "",
        *,
        dari: date | None = None,
        sampai: date | None = None,
        hanya_pengaduan: bool = False,
        batas: int = BATAS_PENCARIAN,
    ) -> list[NoteInfo]:
        """
        Cari lembar pada cabang sesi ini.

        Dibatasi cabang sesi, bukan loket maupun petugas: pengunjung yang
        sama kembali pada hari berikutnya ke loket yang berbeda, dan petugas
        di sana perlu tahu apa yang sudah pernah diadukan supaya orangnya
        tidak diminta menceritakan keluhannya dari awal.
        """
        sesi = self.auth.require_permission(Permission.NOTE_VIEW)

        with session_scope() as session:
            baris = QueueNoteRepository(session).cari(
                sesi.branch_id,
                kata=kata,
                dari=dari,
                sampai=sampai,
                hanya_pengaduan=hanya_pengaduan,
                batas=batas,
            )
            return [_as_note_info(row) for row in baris]
