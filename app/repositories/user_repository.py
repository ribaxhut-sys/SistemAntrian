"""Akses data user."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import RecordStatus, User, UserRole


def normalize_username(username: str) -> str:
    """
    Bentuk baku nama pengguna.

    Nama pengguna tidak dibedakan huruf besar/kecil supaya petugas yang
    mengetik "Admin" tetap dapat masuk. Penyimpanannya selalu huruf kecil.
    """
    return (username or "").strip().lower()


class UserRepository:
    """Pengambilan dan penyimpanan data user."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        return self.session.scalar(
            sa.select(User).where(User.username == normalize_username(username))
        )

    def exists_username(self, username: str) -> bool:
        return self.get_by_username(username) is not None

    def list_all(self, *, only_active: bool = False) -> list[User]:
        stmt = sa.select(User).order_by(User.username)
        if only_active:
            stmt = stmt.where(User.status == RecordStatus.ACTIVE)
        return list(self.session.scalars(stmt))

    def list_by_role(self, role: UserRole) -> list[User]:
        return list(
            self.session.scalars(
                sa.select(User).where(User.role == role).order_by(User.username)
            )
        )

    def count(self) -> int:
        return self.session.scalar(sa.select(sa.func.count()).select_from(User)) or 0

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user
