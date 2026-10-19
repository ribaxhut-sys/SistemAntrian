"""status salinan media di perangkat

Revision ID: e9c3b5a7d281
Revises: d6a1f3b8c704
Create Date: 2026-10-16 12:00:00.000000

Berapa berkas media server yang sudah tersalin di tiap anjungan, dan
penanda permintaan "segarkan media sekarang". Semua kolom boleh kosong.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9c3b5a7d281'
down_revision: Union[str, Sequence[str], None] = 'd6a1f3b8c704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("kiosk_device", schema=None) as batch_op:
        batch_op.add_column(sa.Column("media_total", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("media_tersalin", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("media_byte", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("media_waktu", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("media_segarkan", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("kiosk_device", schema=None) as batch_op:
        batch_op.drop_column("media_segarkan")
        batch_op.drop_column("media_waktu")
        batch_op.drop_column("media_byte")
        batch_op.drop_column("media_tersalin")
        batch_op.drop_column("media_total")
