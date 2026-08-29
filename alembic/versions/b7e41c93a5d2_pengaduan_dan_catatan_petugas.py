"""pengaduan dan catatan petugas per antrian

Revision ID: b7e41c93a5d2
Revises: a1c7f2b40913
Create Date: 2026-08-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e41c93a5d2'
down_revision: Union[str, Sequence[str], None] = 'a1c7f2b40913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Tabel TERSENDIRI, bukan kolom tambahan pada `queue`. User PostgreSQL
    # anjungan ambil nomor punya SELECT pada `queue` (docs/sql/kios-grant.sql)
    # dan komputernya berdiri di ruang publik tanpa diawasi; sebagai tabel
    # sendiri, tabel ini cukup tidak diberi GRANT kepada siapa pun selain
    # user petugas.
    #
    # Seluruh kolom identitas nullable: catatan petugas boleh berdiri
    # sendiri tanpa pengaduan, dan pengaduan tanpa telepon/email/alamat
    # tetap sah. Kewajiban "nama dan nomor pelanggan wajib bila ada
    # deskripsi" ditegakkan di service layer, bukan di sini — aturan
    # bersyarat semacam itu tidak dapat dinyatakan sebagai NOT NULL.
    op.create_table(
        "queue_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("queue_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("counter_id", sa.Integer(), nullable=True),
        sa.Column("officer_id", sa.Integer(), nullable=False),
        sa.Column("nama", sa.String(length=120), nullable=True),
        sa.Column("nomor_pelanggan", sa.String(length=40), nullable=True),
        sa.Column("telepon", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=120), nullable=True),
        sa.Column("alamat", sa.Text(), nullable=True),
        sa.Column("deskripsi", sa.Text(), nullable=True),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["queue_id"],
            ["queue.id"],
            name="fk_queue_note_queue_id_queue",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branch.id"],
            name="fk_queue_note_branch_id_branch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["counter_id"],
            ["counter.id"],
            name="fk_queue_note_counter_id_counter",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["officer_id"],
            ["app_user.id"],
            name="fk_queue_note_officer_id_app_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_queue_note"),
        # Satu antrian satu lembar. Petugas kedua menyunting yang sudah ada,
        # bukan menumpuk lembar tandingan.
        sa.UniqueConstraint("queue_id", name="uq_queue_note_queue_id"),
    )
    op.create_index("ix_queue_note_branch_id", "queue_note", ["branch_id"])
    op.create_index("ix_queue_note_counter_id", "queue_note", ["counter_id"])
    op.create_index("ix_queue_note_officer_id", "queue_note", ["officer_id"])
    # Dua kolom inilah yang dicari petugas di layar Pengaduan: pengunjung
    # yang kembali menyebut namanya atau nomor pelanggannya, bukan nomor
    # antriannya kemarin.
    op.create_index("ix_queue_note_nama", "queue_note", ["nama"])
    op.create_index("ix_queue_note_nomor_pelanggan", "queue_note", ["nomor_pelanggan"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_queue_note_nomor_pelanggan", table_name="queue_note")
    op.drop_index("ix_queue_note_nama", table_name="queue_note")
    op.drop_index("ix_queue_note_officer_id", table_name="queue_note")
    op.drop_index("ix_queue_note_counter_id", table_name="queue_note")
    op.drop_index("ix_queue_note_branch_id", table_name="queue_note")
    op.drop_table("queue_note")
