"""
Pengelolaan data master: cabang, loket, dan jenis layanan.

Data master yang SUDAH PERNAH DIPAKAI tidak dapat dihapus, hanya
dinonaktifkan. Menghapusnya akan memutus riwayat antrian dan membuat laporan
lama tidak dapat dibaca lagi — skemanya pun menolak lewat `ondelete=RESTRICT`
pada `queue`. Menonaktifkan membuatnya hilang dari pilihan petugas tanpa
merusak data yang sudah terlanjur ada.

Yang BELUM pernah dipakai sama sekali boleh dihapus bersih, supaya salah
ketik saat pemasangan tidak tertinggal selamanya sebagai baris nonaktif.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import (
    AuditAction,
    Branch,
    Counter,
    Queue,
    QueueSequence,
    RecordStatus,
    ServiceCategory,
)
from app.repositories.master_repository import (
    BranchRepository,
    CounterRepository,
    ServiceCategoryRepository,
)
from app.repositories.queue_repository import QueueRepository
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission

logger = get_logger("master")

#: Prefix nomor antrian: satu atau dua huruf, misalnya "A" atau "AB".
_POLA_PREFIX = re.compile(r"^[A-Z]{1,2}$")


@dataclass(frozen=True)
class BranchInfo:
    """Data cabang yang aman dibawa ke UI, lepas dari session database."""

    id: int
    code: str
    name: str
    address: str | None
    status: RecordStatus

    @property
    def is_active(self) -> bool:
        return self.status is RecordStatus.ACTIVE


@dataclass(frozen=True)
class CounterInfo:
    id: int
    branch_id: int
    code: str
    name: str
    status: RecordStatus
    on_break: bool = False
    #: Jenis layanan yang boleh dipanggil loket ini. KOSONG berarti semua,
    #: bukan tidak ada — lihat `counter_category` pada model.
    category_ids: tuple[int, ...] = ()

    @property
    def is_active(self) -> bool:
        return self.status is RecordStatus.ACTIVE

    @property
    def melayani_semua(self) -> bool:
        return not self.category_ids


@dataclass(frozen=True)
class CategoryInfo:
    id: int
    branch_id: int
    code: str
    name: str
    prefix: str
    display_order: int
    status: RecordStatus

    @property
    def is_active(self) -> bool:
        return self.status is RecordStatus.ACTIVE

    @property
    def contoh_nomor(self) -> str:
        return f"{self.prefix}-001"


def _as_branch(row: Branch) -> BranchInfo:
    return BranchInfo(row.id, row.code, row.name, row.address, row.status)


def _as_counter(row: Counter) -> CounterInfo:
    return CounterInfo(
        row.id,
        row.branch_id,
        row.code,
        row.name,
        row.status,
        row.on_break,
        tuple(kategori.id for kategori in row.categories),
    )


def _as_category(row: ServiceCategory) -> CategoryInfo:
    return CategoryInfo(
        row.id,
        row.branch_id,
        row.code,
        row.name,
        row.prefix,
        row.display_order,
        row.status,
    )


def _bersihkan(nilai: str | None) -> str:
    return (nilai or "").strip()


def _wajib(nilai: str | None, label: str) -> str:
    hasil = _bersihkan(nilai)
    if not hasil:
        raise ValidationError(f"{label} tidak boleh kosong.")
    return hasil


def _kode(nilai: str | None, label: str) -> str:
    """Kode selalu huruf besar tanpa spasi agar tidak ada duplikat tersamar."""
    hasil = _wajib(nilai, label).upper().replace(" ", "-")
    if len(hasil) > 20:
        raise ValidationError(f"{label} maksimal 20 karakter.")
    return hasil


class MasterDataService:
    """Pembacaan dan perubahan data master."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    # =================================================================
    # Pembacaan
    # =================================================================
    #
    # Pembacaan data master tidak memerlukan hak MASTER_MANAGE. Petugas
    # pendaftaran perlu daftar jenis layanan, dan petugas CRO perlu daftar
    # loket, padahal keduanya tidak berhak mengubah data master.

    def list_branches(self, *, only_active: bool = False) -> list[BranchInfo]:
        self.auth.require_session()
        with session_scope() as session:
            return [
                _as_branch(b)
                for b in BranchRepository(session).list_all(only_active=only_active)
            ]

    def list_counters(
        self, branch_id: int | None = None, *, only_active: bool = False
    ) -> list[CounterInfo]:
        sesi = self.auth.require_session()
        with session_scope() as session:
            rows = CounterRepository(session).list_for_branch(
                branch_id or sesi.branch_id, only_active=only_active
            )
            return [_as_counter(c) for c in rows]

    def list_categories(
        self, branch_id: int | None = None, *, only_active: bool = False
    ) -> list[CategoryInfo]:
        sesi = self.auth.require_session()
        with session_scope() as session:
            rows = ServiceCategoryRepository(session).list_for_branch(
                branch_id or sesi.branch_id, only_active=only_active
            )
            return [_as_category(c) for c in rows]

    def get_counter(self, counter_id: int) -> CounterInfo:
        self.auth.require_session()
        with session_scope() as session:
            row = CounterRepository(session).get_by_id(counter_id)
            if row is None:
                raise NotFoundError("Loket tidak ditemukan.")
            return _as_counter(row)

    def get_category(self, category_id: int) -> CategoryInfo:
        self.auth.require_session()
        with session_scope() as session:
            row = ServiceCategoryRepository(session).get_by_id(category_id)
            if row is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")
            return _as_category(row)

    # =================================================================
    # Cabang
    # =================================================================

    def update_branch(
        self, branch_id: int, *, name: str, address: str | None = None
    ) -> BranchInfo:
        """Ubah nama dan alamat cabang. Kode cabang tidak dapat diubah."""
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)
        nama = _wajib(name, "Nama cabang")

        with session_scope() as session:
            branch = BranchRepository(session).get_by_id(branch_id)
            if branch is None:
                raise NotFoundError("Cabang tidak ditemukan.")

            branch.name = nama
            branch.address = _bersihkan(address) or None

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="branch",
                entity_id=branch.id,
                nama=nama,
            )
            logger.info("Cabang %s diperbarui", branch.code)
            return _as_branch(branch)

    # =================================================================
    # Loket
    # =================================================================

    def create_counter(self, *, code: str, name: str, branch_id: int | None = None) -> int:
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)
        kode = _kode(code, "Kode loket")
        nama = _wajib(name, "Nama loket")
        cabang = branch_id or sesi.branch_id

        with session_scope() as session:
            repo = CounterRepository(session)
            if repo.get_by_code(cabang, kode) is not None:
                raise ValidationError(f"Loket dengan kode {kode!r} sudah ada.")

            counter = repo.add(
                Counter(
                    branch_id=cabang,
                    code=kode,
                    name=nama,
                    status=RecordStatus.ACTIVE,
                )
            )
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="counter",
                entity_id=counter.id,
                tindakan="tambah",
                kode=kode,
            )
            logger.info("Loket %s dibuat", kode)
            return counter.id

    def update_counter(self, counter_id: int, *, name: str) -> CounterInfo:
        """Ubah nama loket. Kode tidak dapat diubah karena melekat pada riwayat."""
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)
        nama = _wajib(name, "Nama loket")

        with session_scope() as session:
            counter = CounterRepository(session).get_by_id(counter_id)
            if counter is None:
                raise NotFoundError("Loket tidak ditemukan.")

            counter.name = nama
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="counter",
                entity_id=counter.id,
                tindakan="ubah",
                nama=nama,
            )
            return _as_counter(counter)

    def set_counter_status(self, counter_id: int, active: bool) -> CounterInfo:
        """
        Aktifkan atau nonaktifkan loket.

        Loket terakhir yang masih aktif tidak boleh dinonaktifkan; tanpa
        loket aktif, tidak ada satu pun antrian yang dapat dipanggil.

        Loket yang sedang memegang pengunjung juga tidak boleh dinonaktifkan.
        Kartunya akan hilang dari papan televisi begitu itu terjadi — layar
        hanya menampilkan loket aktif — sehingga pengunjung yang sedang
        duduk di depan meja kehilangan jejak nomornya, dan petugasnya tidak
        lagi dapat menyelesaikan pelayanan yang sudah telanjur berjalan.
        """
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)

        with session_scope() as session:
            repo = CounterRepository(session)
            counter = repo.get_by_id(counter_id)
            if counter is None:
                raise NotFoundError("Loket tidak ditemukan.")

            if (
                not active
                and counter.status is RecordStatus.ACTIVE
                and repo.count_active(counter.branch_id) <= 1
            ):
                raise BusinessRuleError(
                    "Loket ini satu-satunya yang masih aktif. "
                    "Aktifkan loket lain terlebih dahulu."
                )

            if not active and counter.status is RecordStatus.ACTIVE:
                sedang = QueueRepository(session).sedang_ditangani_loket(
                    counter_id, clock.today()
                )
                if sedang is not None:
                    raise BusinessRuleError(
                        f"Loket {counter.name!r} masih menangani "
                        f"{sedang.queue_number}. Selesaikan pelayanannya "
                        "terlebih dahulu."
                    )

            counter.status = RecordStatus.ACTIVE if active else RecordStatus.INACTIVE
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="counter",
                entity_id=counter.id,
                tindakan="aktifkan" if active else "nonaktifkan",
            )
            logger.info(
                "Loket %s %s", counter.code, "diaktifkan" if active else "dinonaktifkan"
            )
            return _as_counter(counter)

    def set_counter_categories(
        self, counter_id: int, category_ids: list[int] | tuple[int, ...]
    ) -> CounterInfo:
        """
        Tetapkan jenis layanan yang boleh dipanggil sebuah loket.

        Daftar KOSONG berarti loket boleh memanggil semua jenis layanan.
        Itu sekaligus keadaan bawaannya, sehingga loket yang belum pernah
        diatur tetap bekerja penuh.

        Jenis layanan yang sudah nonaktif sengaja masih boleh dipilih:
        loket khusus yang layanannya sedang dihentikan sementara tidak
        kehilangan pengaturannya begitu layanan itu diaktifkan lagi.
        """
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)
        diminta = list(dict.fromkeys(category_ids))  # buang duplikat, jaga urutan

        with session_scope() as session:
            counter = CounterRepository(session).get_by_id(counter_id)
            if counter is None:
                raise NotFoundError("Loket tidak ditemukan.")

            kategori: list[ServiceCategory] = []
            repo_kategori = ServiceCategoryRepository(session)
            for category_id in diminta:
                baris = repo_kategori.get_by_id(category_id)
                if baris is None or baris.branch_id != counter.branch_id:
                    raise NotFoundError("Jenis layanan tidak ditemukan.")
                kategori.append(baris)

            counter.categories = kategori

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="counter",
                entity_id=counter.id,
                tindakan="atur layanan",
                category_ids=diminta,
            )
            logger.info(
                "Loket %s melayani %s",
                counter.code,
                "semua jenis layanan" if not kategori else
                ", ".join(k.code for k in kategori),
            )
            return _as_counter(counter)

    # =================================================================
    # Jenis layanan
    # =================================================================

    def create_category(
        self, *, code: str, name: str, prefix: str, branch_id: int | None = None
    ) -> int:
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)
        kode = _kode(code, "Kode jenis layanan")
        nama = _wajib(name, "Nama jenis layanan")
        awalan = _wajib(prefix, "Prefix").upper()
        cabang = branch_id or sesi.branch_id

        if not _POLA_PREFIX.match(awalan):
            raise ValidationError(
                "Prefix harus berupa satu atau dua huruf, misalnya A atau AB."
            )

        with session_scope() as session:
            repo = ServiceCategoryRepository(session)
            if repo.get_by_code(cabang, kode) is not None:
                raise ValidationError(f"Jenis layanan dengan kode {kode!r} sudah ada.")

            bentrok = repo.get_by_prefix(cabang, awalan)
            if bentrok is not None:
                raise ValidationError(
                    f"Prefix {awalan!r} sudah dipakai oleh {bentrok.name!r}. "
                    "Nomor antrian akan bertabrakan bila prefix sama."
                )

            category = repo.add(
                ServiceCategory(
                    branch_id=cabang,
                    code=kode,
                    name=nama,
                    prefix=awalan,
                    display_order=repo.next_display_order(cabang),
                    status=RecordStatus.ACTIVE,
                )
            )
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="service_category",
                entity_id=category.id,
                tindakan="tambah",
                kode=kode,
                prefix=awalan,
            )
            logger.info("Jenis layanan %s (%s) dibuat", kode, awalan)
            return category.id

    def update_category(
        self, category_id: int, *, name: str, prefix: str | None = None
    ) -> CategoryInfo:
        """
        Ubah jenis layanan.

        Prefix hanya boleh diubah selama belum ada antrian yang memakainya.
        Setelah terpakai, mengubah prefix akan membuat nomor lama seperti
        A-023 tidak lagi cocok dengan jenis layanannya.
        """
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)
        nama = _wajib(name, "Nama jenis layanan")

        with session_scope() as session:
            repo = ServiceCategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")

            category.name = nama

            if prefix is not None:
                awalan = _wajib(prefix, "Prefix").upper()
                if awalan != category.prefix:
                    if not _POLA_PREFIX.match(awalan):
                        raise ValidationError(
                            "Prefix harus berupa satu atau dua huruf, "
                            "misalnya A atau AB."
                        )
                    if repo.has_queues(category.id):
                        raise BusinessRuleError(
                            "Prefix tidak dapat diubah karena jenis layanan ini "
                            "sudah dipakai antrian. Nonaktifkan jenis layanan ini "
                            "lalu buat yang baru bila prefix perlu berubah."
                        )
                    bentrok = repo.get_by_prefix(category.branch_id, awalan)
                    if bentrok is not None and bentrok.id != category.id:
                        raise ValidationError(
                            f"Prefix {awalan!r} sudah dipakai oleh {bentrok.name!r}."
                        )
                    category.prefix = awalan

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="service_category",
                entity_id=category.id,
                tindakan="ubah",
                nama=nama,
            )
            return _as_category(category)

    def set_category_status(self, category_id: int, active: bool) -> CategoryInfo:
        """
        Aktifkan atau nonaktifkan jenis layanan.

        Jenis layanan terakhir yang aktif tidak boleh dinonaktifkan; tanpa
        itu, tidak ada nomor antrian yang bisa diterbitkan sama sekali.
        """
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)

        with session_scope() as session:
            repo = ServiceCategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")

            if (
                not active
                and category.status is RecordStatus.ACTIVE
                and repo.count_active(category.branch_id) <= 1
            ):
                raise BusinessRuleError(
                    "Jenis layanan ini satu-satunya yang masih aktif. "
                    "Aktifkan jenis layanan lain terlebih dahulu."
                )

            category.status = RecordStatus.ACTIVE if active else RecordStatus.INACTIVE
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="service_category",
                entity_id=category.id,
                tindakan="aktifkan" if active else "nonaktifkan",
            )
            logger.info(
                "Jenis layanan %s %s",
                category.code,
                "diaktifkan" if active else "dinonaktifkan",
            )
            return _as_category(category)

    def delete_category(self, category_id: int) -> None:
        """
        Hapus jenis layanan yang BELUM PERNAH dipakai sama sekali.

        Gunanya sempit dan disengaja: membereskan salah ketik saat
        pemasangan, supaya tidak tertinggal selamanya sebagai baris nonaktif
        yang membingungkan. Begitu satu nomor saja pernah terbit atas jenis
        layanan ini, penghapusan ditolak dan yang benar adalah menonaktifkan
        — riwayat antrian dan laporan lama merujuk ke baris ini, dan
        `ondelete=RESTRICT` pada `queue` memang akan menolaknya di tingkat
        database sekalipun pemeriksaan di sini terlewat.

        Baris penomoran harian ikut diperiksa, bukan hanya antriannya:
        nomor yang sudah terbit lalu seluruhnya terhapus pada penutupan
        tetap meninggalkan jejak urutan yang tidak boleh hilang diam-diam.
        """
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)

        with session_scope() as session:
            repo = ServiceCategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")

            if (
                category.status is RecordStatus.ACTIVE
                and repo.count_active(category.branch_id) <= 1
            ):
                raise BusinessRuleError(
                    "Jenis layanan ini satu-satunya yang masih aktif. "
                    "Tambahkan jenis layanan lain terlebih dahulu."
                )

            terpakai = session.scalar(
                sa.select(sa.func.count())
                .select_from(Queue)
                .where(Queue.category_id == category_id)
            ) or session.scalar(
                sa.select(sa.func.count())
                .select_from(QueueSequence)
                .where(QueueSequence.category_id == category_id)
            )
            if terpakai:
                raise BusinessRuleError(
                    f"Jenis layanan {category.name!r} sudah pernah dipakai "
                    "sehingga tidak dapat dihapus — riwayat antrian dan "
                    "laporan lama merujuk kepadanya. Nonaktifkan saja: "
                    "nomor baru berhenti terbit dan pilihannya hilang dari "
                    "layar petugas."
                )

            kode, nama = category.code, category.name
            session.delete(category)

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="service_category",
                entity_id=category_id,
                tindakan="hapus",
                code=kode,
                name=nama,
            )
            logger.info("Jenis layanan %s dihapus (belum pernah dipakai)", kode)
