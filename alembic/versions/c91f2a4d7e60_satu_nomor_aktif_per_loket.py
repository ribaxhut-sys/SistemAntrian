"""satu nomor aktif per loket

Revision ID: c91f2a4d7e60
Revises: a8e3d6f19c42
Create Date: 2026-10-09 10:30:00.000000

Satu loket hanya boleh memegang satu nomor berstatus CALLED, SERVING, atau
PAUSED pada tanggal yang sama. Indeks parsial berlaku pada SQLite dan
PostgreSQL tanpa menghalangi riwayat nomor yang sudah selesai.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91f2a4d7e60"
down_revision: Union[str, Sequence[str], None] = "a8e3d6f19c42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AKTIF = sa.text(
    "counter_id IS NOT NULL AND status IN ('CALLED', 'SERVING', 'PAUSED')"
)


def upgrade() -> None:
    """Tambahkan pertahanan basis data terhadap pemanggilan loket ganda."""
    op.create_index(
        "uq_queue_active_counter_date",
        "queue",
        ["counter_id", "queue_date"],
        unique=True,
        sqlite_where=_AKTIF,
        postgresql_where=_AKTIF,
    )


def downgrade() -> None:
    """Hapus pertahanan satu nomor aktif per loket."""
    op.drop_index("uq_queue_active_counter_date", table_name="queue")
