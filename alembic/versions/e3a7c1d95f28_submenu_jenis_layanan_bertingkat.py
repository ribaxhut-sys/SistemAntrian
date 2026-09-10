"""submenu jenis layanan bertingkat

Revision ID: e3a7c1d95f28
Revises: c2f5a91d7b3e
Create Date: 2026-09-10 09:20:00.000000

Membuat jenis layanan dapat bertingkat, lalu memasang susunan konsultasi
perpajakan di bawah "Konsultasi" yang sudah ada.

Bagian data sengaja ikut di sini, bukan diserahkan ke seed: seed hanya
berjalan pada database yang masih kosong, sedangkan yang perlu berubah
adalah database yang sudah berisi antrian dan loket.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core import clock


# revision identifiers, used by Alembic.
revision: str = 'e3a7c1d95f28'
down_revision: Union[str, Sequence[str], None] = 'c2f5a91d7b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: (code, name, prefix pilihan pertama, urutan)
_ANAK_KONSULTASI: list[tuple[str, str, str, int]] = [
    ("PBB", "PBB", "PB", 1),
    ("PKB", "PKB", "KB", 2),
    ("PAT", "PAT", "AT", 3),
    ("REKLAME", "Reklame", "RK", 4),
    ("PBJT", "PBJT", "PJ", 5),
]

#: PBJT sendiri tidak menerbitkan nomor; keempat inilah daunnya.
_ANAK_PBJT: list[tuple[str, str, str, int]] = [
    ("RESTORAN", "Restoran", "RS", 1),
    ("PARKIR", "Parkir", "PR", 2),
    ("HOTEL", "Hotel", "HT", 3),
    ("HIBURAN", "Hiburan", "HB", 4),
]

_HURUF = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _prefix_bebas(conn, branch_id: int, pilihan: str) -> str:
    """
    Prefix yang belum dipakai cabang ini, sedekat mungkin dengan pilihan.

    Prefix wajib unik per cabang. Pemasangan yang sudah pernah menambah
    jenis layanan sendiri bisa saja sudah memakai "PB" atau "RS", dan
    migration tidak boleh gagal — apalagi menggagalkan seluruh pembukaan
    aplikasi — hanya karena satu prefix bentrok. Yang bentrok diberi
    prefix lain, dan admin dapat merapikannya belakangan lewat menu
    Jenis Layanan.
    """
    terpakai = {
        (baris[0] or "").upper()
        for baris in conn.execute(
            sa.text("SELECT prefix FROM service_category WHERE branch_id = :b"),
            {"b": branch_id},
        )
    }
    if pilihan not in terpakai:
        return pilihan
    for pertama in _HURUF:
        for kedua in _HURUF:
            calon = pertama + kedua
            if calon not in terpakai:
                return calon
    raise RuntimeError("Seluruh kombinasi prefix dua huruf sudah terpakai.")


def _sisipkan(conn, *, branch_id: int, parent_id: int, baris: list) -> dict[str, int]:
    """Tambah jenis layanan anak; yang kodenya sudah ada dilewati."""
    hasil: dict[str, int] = {}
    for code, name, prefix, urutan in baris:
        ada = conn.execute(
            sa.text(
                "SELECT id FROM service_category "
                "WHERE branch_id = :b AND code = :c"
            ),
            {"b": branch_id, "c": code},
        ).scalar()
        if ada is not None:
            hasil[code] = ada
            continue

        conn.execute(
            sa.text(
                """
                INSERT INTO service_category
                    (branch_id, parent_id, code, name, prefix, display_order,
                     info_text, status, created_at, updated_at)
                VALUES
                    (:branch_id, :parent_id, :code, :name, :prefix, :urutan,
                     '', 'ACTIVE', :now, :now)
                """
            ),
            {
                "branch_id": branch_id,
                "parent_id": parent_id,
                "code": code,
                "name": name,
                "prefix": _prefix_bebas(conn, branch_id, prefix),
                "urutan": urutan,
                # Waktu diambil dari clock aplikasi (WIB), sama seperti
                # baris yang dibuat lewat model, supaya created_at seluruh
                # jenis layanan berada pada zona waktu yang sama.
                "now": clock.now(),
            },
        )
        hasil[code] = conn.execute(
            sa.text(
                "SELECT id FROM service_category "
                "WHERE branch_id = :b AND code = :c"
            ),
            {"b": branch_id, "c": code},
        ).scalar_one()
    return hasil


def _wariskan_loket(conn, *, induk_id: int, anak_ids: list[int]) -> None:
    """
    Loket yang boleh memanggil kelompoknya boleh memanggil anaknya.

    Tanpa ini, seluruh jenis layanan baru tidak dilayani loket mana pun:
    anjungan tetap menerbitkan nomornya, pengunjung tetap duduk menunggu,
    dan tidak ada satu loket pun yang dapat memanggilnya. Loket yang
    daftarnya KOSONG sudah berarti "semua" dan karena itu tidak perlu —
    dan tidak boleh — ikut diisi di sini.
    """
    loket = [
        baris[0]
        for baris in conn.execute(
            sa.text(
                "SELECT counter_id FROM counter_category WHERE category_id = :k"
            ),
            {"k": induk_id},
        )
    ]
    for counter_id in loket:
        for category_id in anak_ids:
            sudah = conn.execute(
                sa.text(
                    "SELECT 1 FROM counter_category "
                    "WHERE counter_id = :l AND category_id = :k"
                ),
                {"l": counter_id, "k": category_id},
            ).scalar()
            if sudah is None:
                conn.execute(
                    sa.text(
                        "INSERT INTO counter_category (counter_id, category_id) "
                        "VALUES (:l, :k)"
                    ),
                    {"l": counter_id, "k": category_id},
                )


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("service_category", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_service_category_parent_id", ["parent_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_service_category_parent_id_service_category",
            "service_category",
            ["parent_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    conn = op.get_bind()
    konsultasi = conn.execute(
        sa.text(
            "SELECT id, branch_id FROM service_category WHERE code = 'KONSULTASI'"
        )
    ).all()

    for induk_id, branch_id in konsultasi:
        anak = _sisipkan(
            conn, branch_id=branch_id, parent_id=induk_id, baris=_ANAK_KONSULTASI
        )
        cucu = _sisipkan(
            conn,
            branch_id=branch_id,
            parent_id=anak["PBJT"],
            baris=_ANAK_PBJT,
        )
        # Konsultasi dan PBJT kini kelompok dan berhenti menerbitkan nomor.
        # Yang mewarisi hak loketnya adalah DAUN-nya: PBB, PKB, PAT,
        # Reklame, dan keempat anak PBJT.
        daun = [anak[code] for code in ("PBB", "PKB", "PAT", "REKLAME")]
        daun += list(cucu.values())
        _wariskan_loket(conn, induk_id=induk_id, anak_ids=daun)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    # Cucu lebih dahulu: PBJT tidak dapat pergi selama anaknya masih ada.
    kode = [baris[0] for baris in _ANAK_PBJT + _ANAK_KONSULTASI]

    # Hanya yang belum pernah dipakai sama sekali yang dihapus. Sisanya
    # cukup dilepas dari induknya: menghapus jenis layanan yang sudah
    # memiliki nomor akan memutus riwayat antrian yang masih dipegang
    # laporan.
    #
    # queue_sequence ikut diperiksa, bukan hanya queue. Nomor yang sudah
    # terbit lalu seluruh antriannya terhapus pada penutupan hari tetap
    # meninggalkan baris urutan yang merujuk ke jenis layanan ini, dan
    # RESTRICT di sana akan menolak penghapusannya.
    for code in kode:
        conn.execute(
            sa.text(
                """
                DELETE FROM counter_category
                 WHERE category_id IN (
                       SELECT id FROM service_category
                        WHERE code = :c
                          AND id NOT IN (SELECT DISTINCT category_id FROM queue)
                          AND id NOT IN (
                              SELECT DISTINCT category_id FROM queue_sequence
                          )
                 )
                """
            ),
            {"c": code},
        )
        conn.execute(
            sa.text(
                """
                DELETE FROM service_category
                 WHERE code = :c
                   AND id NOT IN (SELECT DISTINCT category_id FROM queue)
                   AND id NOT IN (
                       SELECT DISTINCT category_id FROM queue_sequence
                   )
                   AND id NOT IN (
                       SELECT parent_id FROM service_category
                        WHERE parent_id IS NOT NULL
                   )
                """
            ),
            {"c": code},
        )

    with op.batch_alter_table("service_category", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_service_category_parent_id_service_category", type_="foreignkey"
        )
        batch_op.drop_index("ix_service_category_parent_id")
        batch_op.drop_column("parent_id")
