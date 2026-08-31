"""tambah info anjungan pada jenis layanan

Revision ID: c2f5a91d7b3e
Revises: b7e41c93a5d2
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2f5a91d7b3e'
down_revision: Union[str, Sequence[str], None] = 'b7e41c93a5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default WAJIB ada: jenis layanan yang sudah tersimpan harus
    # otomatis dianggap belum punya info anjungan, bukan gagal di-upgrade.
    with op.batch_alter_table("service_category", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "info_text",
                sa.Text(),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("service_category", schema=None) as batch_op:
        batch_op.drop_column("info_text")
