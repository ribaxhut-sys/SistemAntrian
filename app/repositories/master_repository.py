"""Akses data master: cabang, loket, dan jenis layanan."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import Branch, Counter, Queue, RecordStatus, ServiceCategory


class BranchRepository:
    """Pengambilan dan penyimpanan data cabang."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, branch_id: int) -> Branch | None:
        return self.session.get(Branch, branch_id)

    def get_by_code(self, code: str) -> Branch | None:
        return self.session.scalar(sa.select(Branch).where(Branch.code == code))

    def list_all(self, *, only_active: bool = False) -> list[Branch]:
        stmt = sa.select(Branch).order_by(Branch.code)
        if only_active:
            stmt = stmt.where(Branch.status == RecordStatus.ACTIVE)
        return list(self.session.scalars(stmt))

    def add(self, branch: Branch) -> Branch:
        self.session.add(branch)
        self.session.flush()
        return branch


class CounterRepository:
    """Pengambilan dan penyimpanan data loket."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(
        self, counter_id: int, *, for_update: bool = False
    ) -> Counter | None:
        """
        Ambil loket, dan bila diminta kunci barisnya sampai transaksi selesai.

        Kunci dipakai saat memanggil nomor: dua komputer dapat memilih loket
        yang sama, tetapi hanya satu yang boleh memutuskan loket itu masih
        kosong. SQLite mengabaikan ``FOR UPDATE`` dan memang hanya didukung
        untuk satu komputer; indeks unik pada tabel antrian tetap menjadi
        pertahanan terakhir pada kedua dialect.
        """
        stmt = sa.select(Counter).where(Counter.id == counter_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self.session.scalar(stmt)

    def get_by_code(self, branch_id: int, code: str) -> Counter | None:
        return self.session.scalar(
            sa.select(Counter).where(
                Counter.branch_id == branch_id, Counter.code == code
            )
        )

    def list_for_branch(
        self, branch_id: int, *, only_active: bool = False
    ) -> list[Counter]:
        stmt = (
            sa.select(Counter)
            .where(Counter.branch_id == branch_id)
            .order_by(Counter.code)
        )
        if only_active:
            stmt = stmt.where(Counter.status == RecordStatus.ACTIVE)
        return list(self.session.scalars(stmt))

    def count_active(self, branch_id: int) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count())
                .select_from(Counter)
                .where(
                    Counter.branch_id == branch_id,
                    Counter.status == RecordStatus.ACTIVE,
                )
            )
            or 0
        )

    def add(self, counter: Counter) -> Counter:
        self.session.add(counter)
        self.session.flush()
        return counter


class ServiceCategoryRepository:
    """Pengambilan dan penyimpanan data jenis layanan."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, category_id: int) -> ServiceCategory | None:
        return self.session.get(ServiceCategory, category_id)

    def get_by_code(self, branch_id: int, code: str) -> ServiceCategory | None:
        return self.session.scalar(
            sa.select(ServiceCategory).where(
                ServiceCategory.branch_id == branch_id, ServiceCategory.code == code
            )
        )

    def get_by_prefix(self, branch_id: int, prefix: str) -> ServiceCategory | None:
        return self.session.scalar(
            sa.select(ServiceCategory).where(
                ServiceCategory.branch_id == branch_id,
                ServiceCategory.prefix == prefix,
            )
        )

    def list_for_branch(
        self, branch_id: int, *, only_active: bool = False
    ) -> list[ServiceCategory]:
        stmt = (
            sa.select(ServiceCategory)
            .where(ServiceCategory.branch_id == branch_id)
            .order_by(ServiceCategory.display_order, ServiceCategory.prefix)
        )
        if only_active:
            stmt = stmt.where(ServiceCategory.status == RecordStatus.ACTIVE)
        return list(self.session.scalars(stmt))

    def count_active(self, branch_id: int) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count())
                .select_from(ServiceCategory)
                .where(
                    ServiceCategory.branch_id == branch_id,
                    ServiceCategory.status == RecordStatus.ACTIVE,
                )
            )
            or 0
        )

    def next_display_order(self, branch_id: int) -> int:
        tertinggi = self.session.scalar(
            sa.select(sa.func.max(ServiceCategory.display_order)).where(
                ServiceCategory.branch_id == branch_id
            )
        )
        return (tertinggi or 0) + 1

    def has_active_children(self, category_id: int) -> bool:
        """
        True bila jenis layanan ini punya anak yang masih aktif.

        Inilah yang membuatnya menjadi KELOMPOK: di anjungan ia membuka
        daftar anaknya alih-alih menerbitkan nomor. Anak yang dinonaktifkan
        tidak dihitung — kelompok yang seluruh anaknya dimatikan akan
        menjadi jenis layanan biasa lagi, bukan kartu yang membuka daftar
        kosong di depan pengunjung.
        """
        return (
            self.session.scalar(
                sa.select(sa.func.count())
                .select_from(ServiceCategory)
                .where(
                    ServiceCategory.parent_id == category_id,
                    ServiceCategory.status == RecordStatus.ACTIVE,
                )
            )
            or 0
        ) > 0

    def children_of(self, category_id: int) -> list[ServiceCategory]:
        """Anak langsung, aktif maupun tidak, menurut urutan tampilnya."""
        return list(
            self.session.scalars(
                sa.select(ServiceCategory)
                .where(ServiceCategory.parent_id == category_id)
                .order_by(ServiceCategory.display_order, ServiceCategory.prefix)
            )
        )

    def siblings_of(
        self, branch_id: int, parent_id: int | None
    ) -> list[ServiceCategory]:
        """
        Seluruh jenis layanan yang berbagi induk yang sama.

        Inilah kelompok tempat urutan tampil berlaku: menggeser PBB ke
        atas hanya berarti sesuatu di antara sesama anak Konsultasi, tidak
        di antara seluruh jenis layanan se-cabang.
        """
        return list(
            self.session.scalars(
                sa.select(ServiceCategory)
                .where(
                    ServiceCategory.branch_id == branch_id,
                    ServiceCategory.parent_id.is_(None)
                    if parent_id is None
                    else ServiceCategory.parent_id == parent_id,
                )
                .order_by(ServiceCategory.display_order, ServiceCategory.prefix)
            )
        )

    def has_children(self, category_id: int) -> bool:
        """True bila ada anak, termasuk yang sedang nonaktif."""
        return (
            self.session.scalar(
                sa.select(sa.func.count())
                .select_from(ServiceCategory)
                .where(ServiceCategory.parent_id == category_id)
            )
            or 0
        ) > 0

    def next_display_order_dalam(self, branch_id: int, parent_id: int | None) -> int:
        """Urutan berikutnya DI ANTARA SAUDARA, bukan di seluruh cabang."""
        tertinggi = self.session.scalar(
            sa.select(sa.func.max(ServiceCategory.display_order)).where(
                ServiceCategory.branch_id == branch_id,
                ServiceCategory.parent_id.is_(None)
                if parent_id is None
                else ServiceCategory.parent_id == parent_id,
            )
        )
        return (tertinggi or 0) + 1

    def has_queues(self, category_id: int) -> bool:
        """True bila jenis layanan ini sudah pernah dipakai antrian."""
        return (
            self.session.scalar(
                sa.select(sa.func.count())
                .select_from(Queue)
                .where(Queue.category_id == category_id)
            )
            or 0
        ) > 0

    def add(self, category: ServiceCategory) -> ServiceCategory:
        self.session.add(category)
        self.session.flush()
        return category
