"""kalimat cepat catatan petugas pada jenis layanan

Revision ID: f1b4c8d2a6e9
Revises: e9c3b5a7d281
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1b4c8d2a6e9'
down_revision: Union[str, Sequence[str], None] = 'e9c3b5a7d281'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default WAJIB ada: jenis layanan yang sudah tersimpan dianggap
    # belum punya kalimat cepat sendiri dan memakai daftar bawaan.
    with op.batch_alter_table("service_category", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "frasa_catatan",
                sa.Text(),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("service_category", schema=None) as batch_op:
        batch_op.drop_column("frasa_catatan")
