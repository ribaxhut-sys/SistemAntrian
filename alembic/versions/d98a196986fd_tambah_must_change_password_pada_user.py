"""tambah must_change_password pada user

Revision ID: d98a196986fd
Revises: 318203edb198
Create Date: 2026-08-26 18:50:49.830094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd98a196986fd'
down_revision: Union[str, Sequence[str], None] = '318203edb198'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default WAJIB ada di sini. Menambah kolom NOT NULL tanpa nilai
    # bawaan akan gagal pada database yang sudah berisi user, yaitu persis
    # kondisi di komputer petugas saat aplikasi di-update.
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.drop_column("must_change_password")
