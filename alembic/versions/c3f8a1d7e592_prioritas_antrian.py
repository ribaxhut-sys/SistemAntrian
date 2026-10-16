"""prioritas antrian

Revision ID: c3f8a1d7e592
Revises: b7e2d4f6a8c1
Create Date: 2026-10-16 10:00:00.000000

Alasan prioritas pada nomor antrian (lansia, disabilitas, ibu hamil). Kolom
boleh kosong: kosong berarti nomor biasa, sehingga data lama tidak berubah.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f8a1d7e592'
down_revision: Union[str, Sequence[str], None] = 'b7e2d4f6a8c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("queue", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prioritas", sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("queue", schema=None) as batch_op:
        batch_op.drop_column("prioritas")
