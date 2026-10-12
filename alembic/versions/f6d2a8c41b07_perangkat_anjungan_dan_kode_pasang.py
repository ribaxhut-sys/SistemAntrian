"""perangkat anjungan dan kode pasang

Revision ID: f6d2a8c41b07
Revises: e3a7c1d95f28
Create Date: 2026-10-07 19:20:00.000000

Daftar perangkat Android (anjungan dan layar antrian) yang menyambung ke
API aplikasi server, beserta kode 6 angka untuk memasangkannya. Hanya
menambah tabel; tidak ada data lama yang berubah.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6d2a8c41b07'
down_revision: Union[str, Sequence[str], None] = 'e3a7c1d95f28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "kiosk_device",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("nama", sa.String(length=80), nullable=False),
        sa.Column("jenis", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("dicabut_pada", sa.DateTime(), nullable=True),
        sa.Column("terakhir_terlihat", sa.DateTime(), nullable=True),
        sa.Column("alamat_ip", sa.String(length=45), nullable=False),
        sa.Column("versi_nama", sa.String(length=20), nullable=False),
        sa.Column("versi_kode", sa.Integer(), nullable=False),
        sa.Column("printer_ok", sa.Boolean(), nullable=True),
        sa.Column("printer_pesan", sa.String(length=200), nullable=False),
        sa.Column("printer_waktu", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kiosk_device")),
        sa.UniqueConstraint("device_id", name=op.f("uq_kiosk_device_device_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_kiosk_device_token_hash")),
    )
    op.create_table(
        "kiosk_pairing_code",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kode", sa.String(length=6), nullable=False),
        sa.Column("kedaluwarsa", sa.DateTime(), nullable=False),
        sa.Column("dipakai_pada", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kiosk_pairing_code")),
    )
    with op.batch_alter_table("kiosk_pairing_code", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_kiosk_pairing_code_kode"), ["kode"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("kiosk_pairing_code", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_kiosk_pairing_code_kode"))
    op.drop_table("kiosk_pairing_code")
    op.drop_table("kiosk_device")
