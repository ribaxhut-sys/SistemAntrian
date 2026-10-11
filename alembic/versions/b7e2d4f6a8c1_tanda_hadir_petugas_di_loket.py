"""tanda hadir petugas di loket

Revision ID: b7e2d4f6a8c1
Revises: d4b8e2a61f39
Create Date: 2026-10-11 16:00:00.000000

Petugas yang sedang login di tiap loket dan tanda hidup terakhirnya, supaya
layar antrian hanya menampilkan loket yang ada petugasnya. Dua kolom boleh
kosong; tidak ada data lama yang berubah.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2d4f6a8c1'
down_revision: Union[str, Sequence[str], None] = 'd4b8e2a61f39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("counter", schema=None) as batch_op:
        batch_op.add_column(sa.Column("petugas_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("petugas_terlihat_pada", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("counter", schema=None) as batch_op:
        batch_op.drop_column("petugas_terlihat_pada")
        batch_op.drop_column("petugas_user_id")
