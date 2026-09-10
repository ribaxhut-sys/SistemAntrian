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


class _TakDiubah:
    """
    Penanda "argumen ini tidak disebut sama sekali".

    Diperlukan karena None sudah punya arti tersendiri pada `parent_id`:
    pindahkan ke tingkat teratas. Tanpa penanda terpisah, memanggil
    update_category tanpa menyebut induk akan mencabut jenis layanan dari
    kelompoknya — dan seluruh pemanggil lama melakukan tepat itu.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - hanya untuk penelusuran
        return "TAK_DIUBAH"


TAK_DIUBAH = _TakDiubah()


@dataclass(frozen=True)
class CategoryInfo:
    id: int
    branch_id: int
    code: str
    name: str
    prefix: str
    display_order: int
    status: RecordStatus
    #: Ditampilkan di panel informasi anjungan begitu layanan ini disentuh.
    info_text: str = ""
    #: Kelompok induknya; None berarti berdiri di tingkat teratas anjungan.
    parent_id: int | None = None
    #: True bila ada jenis layanan lain di bawahnya. Yang punya anak
    #: menjadi KELOMPOK: di anjungan ia membuka daftar anaknya dan tidak
    #: menerbitkan nomor sendiri.
    punya_anak: bool = False
    #: Kedalaman dari tingkat teratas: 0 untuk induk, 1 untuk anaknya.
    #: Dipakai layar admin untuk menjorokkan barisnya.
    level: int = 0

    @property
    def is_active(self) -> bool:
        return self.status is RecordStatus.ACTIVE

    @property
    def contoh_nomor(self) -> str:
        # Kelompok tidak pernah menerbitkan nomor, dan menampilkan
        # "PJ-001" di sebelahnya hanya menjanjikan nomor yang tidak akan
        # pernah ada.
        if self.punya_anak:
            return "—"
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


def _as_category(
    row: ServiceCategory, *, punya_anak: bool = False, level: int = 0
) -> CategoryInfo:
    return CategoryInfo(
        row.id,
        row.branch_id,
        row.code,
        row.name,
        row.prefix,
        row.display_order,
        row.status,
        row.info_text,
        row.parent_id,
        punya_anak,
        level,
    )


def _susun_hierarki(rows: list[ServiceCategory]) -> list[CategoryInfo]:
    """
    Urutkan jenis layanan induk-lalu-anak, dan tandai mana yang kelompok.

    Hasilnya tetap satu daftar datar — pemanggilnya sudah terbiasa dengan
    bentuk itu — tetapi urutannya kini menelusuri pohon: setiap induk
    langsung diikuti anak-anaknya. Layar admin cukup menjorokkan baris
    menurut `level` untuk memperlihatkan susunannya.

    "Punya anak" dihitung dari BARIS YANG DISARING INI, bukan dari seluruh
    tabel. Saat anjungan meminta yang aktif saja, kelompok yang seluruh
    anaknya dinonaktifkan otomatis kembali menjadi jenis layanan biasa dan
    menerbitkan nomornya sendiri — jauh lebih baik daripada kartu yang
    membuka daftar kosong di depan pengunjung yang sedang berdiri.

    Anak yang induknya tidak ikut tersaring (induk nonaktif, anaknya
    aktif) naik ke tingkat teratas, bukan hilang. Jenis layanan yang masih
    aktif harus selalu dapat dicapai.
    """
    ada = {row.id for row in rows}
    anak_dari: dict[int | None, list[ServiceCategory]] = {}
    for row in rows:
        induk = row.parent_id if row.parent_id in ada else None
        anak_dari.setdefault(induk, []).append(row)

    hasil: list[CategoryInfo] = []

    def telusuri(induk: int | None, level: int) -> None:
        for row in anak_dari.get(induk, []):
            hasil.append(
                _as_category(row, punya_anak=bool(anak_dari.get(row.id)), level=level)
            )
            telusuri(row.id, level + 1)

    telusuri(None, 0)
    return hasil


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


#: Kedalaman menu anjungan yang masih masuk akal untuk pengunjung yang
#: berdiri: tingkat teratas, satu kelompok, dan satu sub-kelompok.
#: Contohnya Konsultasi > PBJT > Restoran. Lebih dalam dari itu dan
#: pengunjung tersesat sebelum sampai ke nomornya.
TINGKAT_MAKS = 3


def _kedalaman_induk(repo: ServiceCategoryRepository, category) -> int:
    """
    Tingkat sebuah jenis layanan; 0 bila ia berdiri di tingkat teratas.

    Ditelusuri ke atas dengan batas langkah, bukan while polos: satu baris
    data yang rusak dan menunjuk dirinya sendiri sebagai induk tidak boleh
    membuat aplikasi menggantung selamanya.
    """
    tingkat = 0
    kini = category
    for _ in range(TINGKAT_MAKS + 1):
        if kini.parent_id is None:
            return tingkat
        kini = repo.get_by_id(kini.parent_id)
        if kini is None:
            return tingkat
        tingkat += 1
    return tingkat


def _kedalaman_anak(repo: ServiceCategoryRepository, category_id: int) -> int:
    """Tinggi sub-pohon; 1 bila jenis layanan ini belum punya anak."""
    anak = repo.children_of(category_id)
    if not anak:
        return 1
    return 1 + max(_kedalaman_anak(repo, baris.id) for baris in anak)


def _keturunan(repo: ServiceCategoryRepository, category_id: int) -> set[int]:
    """Seluruh id di bawah jenis layanan ini, sedalam apa pun."""
    hasil: set[int] = set()
    for baris in repo.children_of(category_id):
        hasil.add(baris.id)
        hasil |= _keturunan(repo, baris.id)
    return hasil


def _periksa_induk(
    repo: ServiceCategoryRepository,
    *,
    parent_id: int | None,
    branch_id: int,
    category=None,
):
    """
    Pastikan sebuah kelompok boleh menjadi induk, lalu kembalikan barisnya.

    Menolak lebih awal, di satu tempat, karena akibat dari induk yang salah
    tidak terlihat di layar admin: menu anjungan-lah yang kemudian menjadi
    terlalu dalam, melingkar, atau menghilang.
    """
    if parent_id is None:
        return None

    induk = repo.get_by_id(parent_id)
    if induk is None:
        raise ValidationError("Kelompok induk tidak ditemukan.")
    if induk.branch_id != branch_id:
        raise ValidationError("Kelompok induk berada di cabang yang berbeda.")

    if category is not None:
        if induk.id == category.id:
            raise ValidationError(
                f"{category.name} tidak dapat menjadi induk bagi dirinya sendiri."
            )
        if induk.id in _keturunan(repo, category.id):
            raise ValidationError(
                f"{induk.name} berada DI BAWAH {category.name}. Memindahkannya "
                "ke sana akan membuat menu anjungan berputar tanpa ujung."
            )

    tingkat_induk = _kedalaman_induk(repo, induk)
    tinggi = _kedalaman_anak(repo, category.id) if category is not None else 1
    if tingkat_induk + 1 + tinggi > TINGKAT_MAKS:
        raise ValidationError(
            f"Menu anjungan paling dalam {TINGKAT_MAKS} tingkat. "
            f"{induk.name} sudah berada di tingkat {tingkat_induk + 1}."
        )
    return induk


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
        self,
        branch_id: int | None = None,
        *,
        only_active: bool = False,
        only_leaf: bool = False,
    ) -> list[CategoryInfo]:
        """
        Daftar jenis layanan, tersusun induk-lalu-anak.

        `only_leaf` membuang KELOMPOK dari hasil dan menyisakan yang
        benar-benar dapat menerbitkan nomor. Dipakai layar yang meminta
        satu jenis layanan sekaligus — pendaftaran oleh petugas, penyaring
        panggilan di loket, pemetaan layanan per loket — karena di sana
        "Konsultasi" sudah tidak berarti apa-apa lagi: yang ada hanyalah
        PBB, PKB, dan seterusnya. Anjungan justru meminta SELURUHNYA,
        sebab kelompoknya-lah yang dipakai menyusun menu bertingkat.
        """
        sesi = self.auth.require_session()
        with session_scope() as session:
            rows = ServiceCategoryRepository(session).list_for_branch(
                branch_id or sesi.branch_id, only_active=only_active
            )
            hasil = _susun_hierarki(rows)
            if only_leaf:
                hasil = [k for k in hasil if not k.punya_anak]
            return hasil

    def layanan_tanpa_loket(self, branch_id: int | None = None) -> list[CategoryInfo]:
        """
        Jenis layanan aktif yang tidak dilayani loket aktif mana pun.

        Keadaan ini tidak ditolak oleh aturan mana pun, dan justru itulah
        bahayanya: anjungan tetap menerbitkan nomornya, pengunjung tetap
        duduk menunggu, dan tidak ada satu loket pun yang bisa memanggilnya.
        Tidak ada yang akan menyadarinya sampai ada orang yang menunggu
        terlalu lama lalu bertanya ke petugas.

        Loket yang daftar layanannya kosong melayani SEMUA jenis layanan
        (lihat `counter_category`), sehingga satu saja loket aktif yang
        dibiarkan "Semua" membuat daftar ini pasti kosong.

        Loket yang sedang istirahat tetap dihitung melayani: istirahat itu
        sementara dan diakhiri sendiri oleh petugasnya, bukan keadaan yang
        perlu diperingatkan kepada admin.
        """
        sesi = self.auth.require_session()
        with session_scope() as session:
            cabang = branch_id or sesi.branch_id
            loket = CounterRepository(session).list_for_branch(
                cabang, only_active=True
            )
            if any(not baris.categories for baris in loket):
                return []

            dilayani = {
                kategori.id for baris in loket for kategori in baris.categories
            }
            # KELOMPOK sengaja dilewati. Ia tidak pernah menerbitkan nomor,
            # jadi tidak ada antrian miliknya yang bisa terlantar — dan
            # memperingatkan admin tentangnya hanya akan mengubur
            # peringatan yang sungguh-sungguh berbahaya.
            repo = ServiceCategoryRepository(session)
            return [
                kategori
                for kategori in _susun_hierarki(
                    repo.list_for_branch(cabang, only_active=True)
                )
                if kategori.id not in dilayani and not kategori.punya_anak
            ]

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
            repo = ServiceCategoryRepository(session)
            row = repo.get_by_id(category_id)
            if row is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")
            return _as_category(row, punya_anak=repo.has_children(category_id))

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
        self,
        *,
        code: str,
        name: str,
        prefix: str,
        branch_id: int | None = None,
        info_text: str = "",
        parent_id: int | None = None,
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

            _periksa_induk(repo, parent_id=parent_id, branch_id=cabang)

            category = repo.add(
                ServiceCategory(
                    branch_id=cabang,
                    parent_id=parent_id,
                    code=kode,
                    name=nama,
                    prefix=awalan,
                    # Urutan dihitung di antara SAUDARA. Memakai nomor
                    # tertinggi se-cabang membuat anak pertama sebuah
                    # kelompok lahir dengan urutan 12 sementara saudara
                    # berikutnya 13 — benar secara relatif, tetapi angkanya
                    # tidak berarti apa-apa dan membingungkan saat dibaca.
                    display_order=repo.next_display_order_dalam(cabang, parent_id),
                    status=RecordStatus.ACTIVE,
                    info_text=_bersihkan(info_text),
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
        self,
        category_id: int,
        *,
        name: str,
        prefix: str | None = None,
        info_text: str = "",
        parent_id: int | None | _TakDiubah = TAK_DIUBAH,
    ) -> CategoryInfo:
        """
        Ubah jenis layanan.

        Prefix hanya boleh diubah selama belum ada antrian yang memakainya.
        Setelah terpakai, mengubah prefix akan membuat nomor lama seperti
        A-023 tidak lagi cocok dengan jenis layanannya.

        `parent_id` memakai penanda TAK_DIUBAH, bukan None, sebagai nilai
        bawaan: None adalah nilai yang SAH — artinya "pindahkan ke tingkat
        teratas" — sehingga pemanggil lama yang tidak menyebut induk sama
        sekali tidak boleh diam-diam mencabut jenis layanan dari
        kelompoknya.
        """
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)
        nama = _wajib(name, "Nama jenis layanan")

        with session_scope() as session:
            repo = ServiceCategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")

            category.name = nama
            category.info_text = _bersihkan(info_text)

            if parent_id is not TAK_DIUBAH and parent_id != category.parent_id:
                _periksa_induk(
                    repo,
                    parent_id=parent_id,
                    branch_id=category.branch_id,
                    category=category,
                )
                category.parent_id = parent_id
                category.display_order = repo.next_display_order_dalam(
                    category.branch_id, parent_id
                )

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
            return _as_category(category, punya_anak=repo.has_children(category.id))

    def pindahkan_category(self, category_id: int, *, naik: bool) -> list[CategoryInfo]:
        """
        Geser satu jenis layanan satu langkah pada urutan tampil.

        Urutan inilah yang dipakai anjungan untuk menyusun kartu A/B/C dan
        layar petugas untuk menyusun pilihannya. Tanpa cara mengubahnya,
        jenis layanan yang ditambahkan belakangan selamanya jadi kartu
        terakhir — walau justru itu yang paling sering disentuh.

        Seluruh baris dinomori ulang 1..N lebih dahulu, bukan hanya dua
        baris yang bertukar. Data lama boleh memiliki `display_order`
        kembar atau berlubang, dan pada nilai yang kembar tukar-menukar
        tidak mengubah urutan apa pun — tombolnya seakan tidak berfungsi.

        Jenis layanan NONAKTIF ikut menempati urutan. Ia memang tidak
        tampil di anjungan, tetapi tempatnya harus tetap terjaga supaya
        urutannya kembali seperti semula begitu diaktifkan lagi.

        Yang bergeser hanyalah kedudukan DI ANTARA SAUDARA SEKELOMPOK.
        PBB tidak pernah bisa naik melewati Konsultasi menjadi kartu di
        tingkat teratas: pindah kelompok adalah perbuatan lain, dilakukan
        lewat kolom Induk pada dialog ubah, dan tidak boleh terjadi tanpa
        sengaja hanya karena tombol Naik ditekan sekali terlalu banyak.
        """
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)

        with session_scope() as session:
            repo = ServiceCategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")

            urutan = repo.siblings_of(category.branch_id, category.parent_id)
            for posisi, baris in enumerate(urutan, start=1):
                baris.display_order = posisi

            indeks = next(
                i for i, baris in enumerate(urutan) if baris.id == category_id
            )
            tetangga = indeks - 1 if naik else indeks + 1
            if not 0 <= tetangga < len(urutan):
                raise BusinessRuleError(
                    f"{category.name} sudah berada di urutan "
                    f"{'teratas' if naik else 'terbawah'}."
                )

            urutan[indeks].display_order, urutan[tetangga].display_order = (
                urutan[tetangga].display_order,
                urutan[indeks].display_order,
            )

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="service_category",
                entity_id=category.id,
                tindakan="pindah urutan",
                urutan_baru=urutan[indeks].display_order,
            )
            logger.info(
                "Jenis layanan %s dipindah ke urutan %s",
                category.code,
                urutan[indeks].display_order,
            )
            # Yang dikembalikan tetap SELURUH cabang dalam susunan
            # pohonnya, bukan sekadar saudara yang barusan bertukar:
            # layar admin menampilkan seluruh daftar dan harus melihat
            # hasilnya utuh.
            session.flush()
            return _susun_hierarki(repo.list_for_branch(category.branch_id))

    def set_category_status(self, category_id: int, active: bool) -> CategoryInfo:
        """
        Aktifkan atau nonaktifkan jenis layanan, BESERTA SELURUH ANAKNYA.

        Jenis layanan terakhir yang aktif tidak boleh dinonaktifkan; tanpa
        itu, tidak ada nomor antrian yang bisa diterbitkan sama sekali.
        Yang dihitung adalah yang benar-benar dapat menerbitkan nomor —
        kelompok tidak ikut, sebab kelompok hanya membuka daftar.

        Anak ikut berubah karena tidak ada tafsir lain yang masuk akal.
        Menonaktifkan "Konsultasi" sementara PBB, PKB, dan PAT dibiarkan
        aktif akan membuat ketiganya naik menjadi kartu tingkat teratas di
        anjungan — persis kebalikan dari yang diminta admin. Menyalakannya
        kembali juga harus mengembalikan anaknya: kelompok yang seluruh
        anaknya mati berubah peran menjadi jenis layanan biasa dan mulai
        menerbitkan nomornya sendiri lagi.
        """
        sesi = self.auth.require_permission(Permission.MASTER_MANAGE)

        with session_scope() as session:
            repo = ServiceCategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")

            ikut = _keturunan(repo, category.id)

            if not active and category.status is RecordStatus.ACTIVE:
                tersisa = [
                    baris
                    for baris in _susun_hierarki(
                        repo.list_for_branch(category.branch_id, only_active=True)
                    )
                    if not baris.punya_anak
                    and baris.id != category.id
                    and baris.id not in ikut
                ]
                if not tersisa:
                    raise BusinessRuleError(
                        "Tidak ada jenis layanan lain yang masih dapat "
                        "menerbitkan nomor. Aktifkan jenis layanan lain "
                        "terlebih dahulu."
                    )

            status = RecordStatus.ACTIVE if active else RecordStatus.INACTIVE
            category.status = status
            for anak_id in ikut:
                anak = repo.get_by_id(anak_id)
                if anak is not None:
                    anak.status = status

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="service_category",
                entity_id=category.id,
                tindakan="aktifkan" if active else "nonaktifkan",
                anak_ikut=len(ikut),
            )
            logger.info(
                "Jenis layanan %s %s bersama %d anaknya",
                category.code,
                "diaktifkan" if active else "dinonaktifkan",
                len(ikut),
            )
            return _as_category(category, punya_anak=bool(ikut))

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

            if repo.has_children(category.id):
                # RESTRICT pada parent_id memang akan menolaknya juga,
                # tetapi yang sampai ke layar admin hanya pesan database
                # yang tidak menjelaskan apa pun. Yang perlu diketahui
                # admin adalah bahwa anaknya harus dipindahkan atau
                # dihapus lebih dahulu.
                raise BusinessRuleError(
                    f"{category.name!r} masih menaungi jenis layanan lain. "
                    "Pindahkan atau hapus isinya terlebih dahulu."
                )

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
