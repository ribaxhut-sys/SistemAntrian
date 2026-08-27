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

    def get_by_id(self, counter_id: int) -> Counter | None:
        return self.session.get(Counter, counter_id)

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
