"""catatan tayang iklan anjungan

Revision ID: d4b8e2a61f39
Revises: c91f2a4d7e60
Create Date: 2026-10-10 10:30:00.000000

Jumlah tayang dan gagal tiap berkas iklan per tablet per hari, dilaporkan
oleh anjungan Android. Hanya menambah tabel; tidak ada data lama berubah.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4b8e2a61f39'
down_revision: Union[str, Sequence[str], None] = 'c91f2a4d7e60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "kiosk_media_tayang",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tanggal", sa.Date(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("nama_berkas", sa.String(length=255), nullable=False),
        sa.Column("jumlah_tayang", sa.Integer(), nullable=False),
        sa.Column("jumlah_gagal", sa.Integer(), nullable=False),
        sa.Column("galat_terakhir", sa.String(length=200), nullable=False),
        sa.Column("tayang_terakhir_pada", sa.DateTime(), nullable=True),
        sa.Column("gagal_terakhir_pada", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kiosk_media_tayang")),
        sa.UniqueConstraint(
            "tanggal",
            "device_id",
            "nama_berkas",
            name=op.f("uq_kiosk_media_tayang_tanggal"),
        ),
    )
    with op.batch_alter_table("kiosk_media_tayang", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_kiosk_media_tayang_tanggal"), ["tanggal"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("kiosk_media_tayang", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_kiosk_media_tayang_tanggal"))
    op.drop_table("kiosk_media_tayang")
