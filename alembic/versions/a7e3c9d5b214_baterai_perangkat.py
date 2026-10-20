"""baterai perangkat

Revision ID: a7e3c9d5b214
Revises: f1b4c8d2a6e9
Create Date: 2026-10-20 20:00:00.000000

Tingkat baterai tablet dan apakah sedang diisi, untuk Kesehatan Sistem.
Semua kolom boleh kosong; tablet lama yang belum melapor tetap sah.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7e3c9d5b214'
down_revision: Union[str, Sequence[str], None] = 'f1b4c8d2a6e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("kiosk_device", schema=None) as batch_op:
        batch_op.add_column(sa.Column("baterai_persen", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("baterai_mengisi", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("baterai_waktu", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("kiosk_device", schema=None) as batch_op:
        batch_op.drop_column("baterai_waktu")
        batch_op.drop_column("baterai_mengisi")
        batch_op.drop_column("baterai_persen")
