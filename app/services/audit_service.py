"""
Pencatatan aktivitas penting.

JANGAN PERNAH memasukkan kata sandi, hash kata sandi, atau kredensial
apa pun ke parameter meta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session, selectinload

from app.core.database import session_scope
from app.core.logger import get_logger
from app.models import AuditAction, AuditLog, User

logger = get_logger("audit")

#: Kunci yang isinya tidak boleh masuk audit log walau tidak sengaja dikirim.
_KUNCI_TERLARANG = {
    "password",
    "password_hash",
    "old_password",
    "new_password",
    "token",
    "secret",
}


def _bersihkan(meta: dict[str, Any]) -> dict[str, Any]:
    """Buang nilai sensitif sebelum disimpan."""
    return {
        k: ("***" if k.lower() in _KUNCI_TERLARANG else v) for k, v in meta.items()
    }


def record(
    session: Session,
    action: AuditAction | str,
    *,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    **meta: Any,
) -> AuditLog:
    """
    Catat satu aktivitas.

    Memakai session yang sedang berjalan supaya pencatatan ikut commit
    atau ikut rollback bersama tindakan yang dicatat. Audit tidak boleh
    mencatat sesuatu yang ternyata batal terjadi.
    """
    nama_aksi = action.value if isinstance(action, AuditAction) else str(action)
    entry = AuditLog(
        user_id=user_id,
        action=nama_aksi,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=json.dumps(_bersihkan(meta), ensure_ascii=False) if meta else None,
    )
    session.add(entry)
    logger.debug("Audit: %s user=%s entity=%s/%s", nama_aksi, user_id, entity_type, entity_id)
    return entry


@dataclass(frozen=True)
class AuditEntry:
    """Satu baris audit yang aman dibawa ke UI, lepas dari session database."""

    id: int
    action: str
    entity_type: str | None
    entity_id: int | None
    username: str | None
    meta: str | None
    created_at: datetime

    @property
    def pelaku(self) -> str:
        """Sistem, untuk aktivitas yang berjalan tanpa sesi pengguna."""
        return self.username or "sistem"


def list_terakhir(
    *,
    batas: int = 100,
    aksi: str | None = None,
    pelaku: str | None = None,
    sejak: date | None = None,
    sampai: date | None = None,
) -> list[AuditEntry]:
    """
    Aktivitas terakhir, terbaru lebih dahulu.

    Tidak menuntut hak akses di sini karena audit log tidak pernah memuat
    kredensial — `record()` sudah menyaringnya. Pembatasan siapa yang boleh
    melihatnya dilakukan pemanggil, yaitu layar administrasi.

    `pelaku` mencocokkan nama pengguna (tanpa membedakan huruf besar-kecil;
    "sistem" berarti aktivitas tanpa pengguna). `sejak` dan `sampai` adalah
    tanggal, keduanya termasuk.
    """
    with session_scope() as session:
        stmt = (
            sa.select(AuditLog)
            .options(selectinload(AuditLog.user))
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(batas)
        )
        if aksi is not None:
            stmt = stmt.where(AuditLog.action == aksi)
        if pelaku:
            nama = pelaku.strip().lower()
            if nama == "sistem":
                stmt = stmt.where(AuditLog.user_id.is_(None))
            else:
                stmt = stmt.where(
                    AuditLog.user_id.in_(
                        sa.select(User.id).where(sa.func.lower(User.username) == nama)
                    )
                )
        if sejak is not None:
            stmt = stmt.where(AuditLog.created_at >= datetime.combine(sejak, time.min))
        if sampai is not None:
            stmt = stmt.where(
                AuditLog.created_at < datetime.combine(sampai + timedelta(days=1), time.min)
            )

        return [
            AuditEntry(
                id=row.id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                username=row.user.username if row.user else None,
                meta=row.meta,
                created_at=row.created_at,
            )
            for row in session.scalars(stmt)
        ]


def daftar_aksi() -> list[str]:
    """Nama tindakan yang pernah tercatat, untuk pilihan filter."""
    with session_scope() as session:
        return list(
            session.scalars(
                sa.select(AuditLog.action).distinct().order_by(AuditLog.action)
            )
        )
