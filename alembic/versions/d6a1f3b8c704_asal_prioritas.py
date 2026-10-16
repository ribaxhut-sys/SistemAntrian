"""asal prioritas antrian

Revision ID: d6a1f3b8c704
Revises: c3f8a1d7e592
Create Date: 2026-10-16 11:00:00.000000

Siapa yang menandai nomor sebagai prioritas: PENDAFTARAN, MANDIRI
(pengunjung di anjungan), atau PETUGAS (petugas pelayanan). Kolom boleh
kosong; nomor lama dan nomor biasa tidak berubah.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6a1f3b8c704'
down_revision: Union[str, Sequence[str], None] = 'c3f8a1d7e592'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("queue", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("prioritas_asal", sa.String(length=12), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("queue", schema=None) as batch_op:
        batch_op.drop_column("prioritas_asal")
