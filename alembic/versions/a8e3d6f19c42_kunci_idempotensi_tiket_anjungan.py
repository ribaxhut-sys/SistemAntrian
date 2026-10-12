"""kunci idempotensi tiket anjungan

Revision ID: a8e3d6f19c42
Revises: f6d2a8c41b07
Create Date: 2026-10-08 09:30:00.000000

Sebelumnya `request_id` dari anjungan Android hanya diingat di memori API.
Bila nomor terbit, jawabannya gagal sampai, lalu API dinyalakan ulang,
permintaan ulang tablet menerbitkan nomor kedua. Tabel ini menyimpan kunci
itu di database, disisipkan bersama baris antriannya. Hanya menambah tabel.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8e3d6f19c42'
down_revision: Union[str, Sequence[str], None] = 'f6d2a8c41b07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "kiosk_ticket_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("queue_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["queue_id"],
            ["queue.id"],
            name=op.f("fk_kiosk_ticket_request_queue_id_queue"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kiosk_ticket_request")),
        sa.UniqueConstraint(
            "device_id",
            "request_id",
            name=op.f("uq_kiosk_ticket_request_device_id"),
        ),
    )
    with op.batch_alter_table("kiosk_ticket_request", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_kiosk_ticket_request_queue_id"), ["queue_id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("kiosk_ticket_request", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_kiosk_ticket_request_queue_id"))
    op.drop_table("kiosk_ticket_request")
