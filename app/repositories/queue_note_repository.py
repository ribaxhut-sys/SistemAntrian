"""
Akses data pengaduan dan catatan petugas.

Pencarian dikerjakan di SQL dan selalu dibatasi jumlahnya. Tabel ini tidak
pernah dibersihkan otomatis — pemilik memilih menyimpannya selamanya dan
menghapus sendiri bila perlu — sehingga isinya hanya bertambah, dan sebuah
layar yang menarik seluruh baris akan menjadi lambat justru setelah
setahun dipakai, ketika tidak ada lagi yang ingat mengapa.
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Session, selectinload

from app.models import Queue, QueueNote

#: Batas bawaan hasil pencarian. Petugas mencari satu pelapor, bukan
#: membaca arsip; hasil yang lebih panjang dari ini berarti kata kuncinya
#: yang perlu dipersempit, bukan layarnya yang perlu diperpanjang.
BATAS_PENCARIAN = 200


def _muat_relasi():
    """Relasi yang selalu ikut dibaca agar UI tidak menyentuh session."""
    return (
        selectinload(QueueNote.queue).selectinload(Queue.category),
        selectinload(QueueNote.counter),
        selectinload(QueueNote.officer),
    )


class QueueNoteRepository:
    """Pembacaan dan penyimpanan lembar pengaduan/catatan."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -----------------------------------------------------------------
    # Pembacaan
    # -----------------------------------------------------------------

    def get_by_id(self, note_id: int) -> QueueNote | None:
        return self.session.scalar(
            sa.select(QueueNote).options(*_muat_relasi()).where(QueueNote.id == note_id)
        )

    def get_by_queue(self, queue_id: int) -> QueueNote | None:
        return self.session.scalar(
            sa.select(QueueNote)
            .options(*_muat_relasi())
            .where(QueueNote.queue_id == queue_id)
        )

    def cari(
        self,
        branch_id: int,
        *,
        kata: str = "",
        dari: date | None = None,
        sampai: date | None = None,
        hanya_pengaduan: bool = False,
        batas: int = BATAS_PENCARIAN,
    ) -> list[QueueNote]:
        """
        Cari lembar menurut kata kunci dan rentang tanggal.

        Kata kunci dicocokkan pada nama, nomor pelanggan, deskripsi,
        catatan petugas, dan nomor antrian. Catatan ikut dicari walaupun
        bukan kata pengunjung: lembar yang HANYA berisi catatan tidak punya
        nama maupun deskripsi, sehingga tanpa ini ia hanya dapat ditemukan
        oleh orang yang kebetulan masih ingat nomor antriannya.

        Pencocokan memakai `lower()` di kedua sisi, bukan ILIKE: ILIKE
        hanya ada di PostgreSQL, sedangkan pemasangan satu komputer memakai
        SQLite.

        Tanggal diambil dari antriannya, bukan dari `created_at` lembar ini.
        Yang diingat pengunjung adalah hari ia datang.
        """
        query = (
            sa.select(QueueNote)
            .join(Queue, QueueNote.queue_id == Queue.id)
            .options(*_muat_relasi())
            .where(QueueNote.branch_id == branch_id)
        )

        bersih = (kata or "").strip().lower()
        if bersih:
            pola = f"%{bersih}%"
            query = query.where(
                sa.or_(
                    sa.func.lower(QueueNote.nama).like(pola),
                    sa.func.lower(QueueNote.nomor_pelanggan).like(pola),
                    sa.func.lower(QueueNote.deskripsi).like(pola),
                    sa.func.lower(QueueNote.catatan).like(pola),
                    sa.func.lower(Queue.queue_number).like(pola),
                )
            )

        if dari is not None:
            query = query.where(Queue.queue_date >= dari)
        if sampai is not None:
            query = query.where(Queue.queue_date <= sampai)

        if hanya_pengaduan:
            # Deskripsi yang menentukan ada tidaknya pengaduan. Baris yang
            # hanya berisi catatan petugas bukan pengaduan siapa pun.
            query = query.where(
                QueueNote.deskripsi.is_not(None),
                sa.func.trim(QueueNote.deskripsi) != "",
            )

        # Terbaru lebih dahulu: yang dicari hampir selalu kejadian kemarin,
        # bukan kejadian tahun lalu.
        query = query.order_by(Queue.queue_date.desc(), QueueNote.id.desc()).limit(
            batas
        )
        return list(self.session.scalars(query))

    # -----------------------------------------------------------------
    # Penulisan
    # -----------------------------------------------------------------

    def simpan(self, note: QueueNote) -> QueueNote:
        self.session.add(note)
        self.session.flush()
        return note

    def hapus(self, note: QueueNote) -> None:
        self.session.delete(note)
        self.session.flush()
