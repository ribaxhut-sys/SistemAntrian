"""tambah status istirahat pada loket

Revision ID: 5c64e15625f1
Revises: d98a196986fd
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c64e15625f1'
down_revision: Union[str, Sequence[str], None] = 'd98a196986fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default WAJIB ada: loket yang sudah tersimpan harus otomatis
    # dianggap tidak sedang istirahat, bukan gagal di-upgrade.
    with op.batch_alter_table("counter", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "on_break",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("counter", schema=None) as batch_op:
        batch_op.drop_column("on_break")
