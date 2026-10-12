"""loket bawaan petugas dan layanan per loket

Revision ID: a1c7f2b40913
Revises: 5c64e15625f1
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7f2b40913'
down_revision: Union[str, Sequence[str], None] = '5c64e15625f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Loket bawaan petugas. Nullable tanpa server_default: akun yang sudah
    # ada memang belum punya loket, dan itu keadaan yang sah — peran selain
    # CRO tidak duduk di loket mana pun.
    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("default_counter_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_app_user_default_counter_id", ["default_counter_id"], unique=False
        )
        # Dinamai eksplisit supaya downgrade dapat menghapusnya di SQLite,
        # yang tidak memberi nama otomatis pada constraint tanpa nama.
        batch_op.create_foreign_key(
            "fk_app_user_default_counter_id",
            "counter",
            ["default_counter_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Jenis layanan yang boleh dipanggil tiap loket. Sengaja dibiarkan
    # KOSONG untuk seluruh loket yang sudah ada: tidak ada baris berarti
    # "boleh memanggil semua", sehingga pemasangan yang sedang berjalan
    # tidak berubah perilakunya sedikit pun setelah upgrade ini.
    op.create_table(
        "counter_category",
        sa.Column("counter_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["counter_id"], ["counter.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["service_category.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("counter_id", "category_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("counter_category")

    with op.batch_alter_table("app_user", schema=None) as batch_op:
        batch_op.drop_constraint("fk_app_user_default_counter_id", type_="foreignkey")
        batch_op.drop_index("ix_app_user_default_counter_id")
        batch_op.drop_column("default_counter_id")
