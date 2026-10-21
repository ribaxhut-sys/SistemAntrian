"""cetak ulang tiket di anjungan

Revision ID: b8d4e1f6a923
Revises: a7e3c9d5b214
Create Date: 2026-10-21 14:00:00.000000

Antrean perintah cetak ulang tiket dari petugas ke tablet anjungan asal
nomor. Tabel baru; tidak ada data lama yang berubah.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d4e1f6a923'
down_revision: Union[str, Sequence[str], None] = 'a7e3c9d5b214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "kiosk_cetak_ulang",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("queue_id", sa.Integer(), nullable=False),
        sa.Column("diminta_oleh_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("diambil_pada", sa.DateTime(), nullable=True),
        sa.Column("selesai_pada", sa.DateTime(), nullable=True),
        sa.Column("pesan", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["queue_id"], ["queue.id"],
            name=op.f("fk_kiosk_cetak_ulang_queue_id_queue"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["diminta_oleh_user_id"], ["app_user.id"],
            name=op.f("fk_kiosk_cetak_ulang_diminta_oleh_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kiosk_cetak_ulang")),
    )
    op.create_index(
        op.f("ix_kiosk_cetak_ulang_device_id"), "kiosk_cetak_ulang", ["device_id"]
    )
    op.create_index(
        op.f("ix_kiosk_cetak_ulang_queue_id"), "kiosk_cetak_ulang", ["queue_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_kiosk_cetak_ulang_queue_id"), table_name="kiosk_cetak_ulang")
    op.drop_index(op.f("ix_kiosk_cetak_ulang_device_id"), table_name="kiosk_cetak_ulang")
    op.drop_table("kiosk_cetak_ulang")
