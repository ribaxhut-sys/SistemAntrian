"""
Pengaduan dan catatan petugas atas satu nomor antrian.

TABEL INI SATU-SATUNYA TEMPAT DATA PRIBADI PENGUNJUNG di seluruh aplikasi.
Antrian sendiri tetap anonim: nama, nomor pelanggan, telepon, email, dan
alamat hanya ada di sini, dan hanya bila petugas memang mengisikannya.

Dipisahkan dari tabel `queue` bukan karena rapi, melainkan karena hak
akses. User PostgreSQL anjungan ambil nomor memiliki SELECT pada `queue`
(lihat docs/sql/kios-grant.sql) — komputer yang berdiri di ruang publik
tanpa diawasi siapa pun. Kalau isian ini menjadi kolom di sana, seluruh
pengaduan hari itu dapat dibaca dari mesin tersebut. Sebagai tabel
tersendiri, ia cukup TIDAK diberi GRANT dan persoalannya hilang sejak awal.

Satu antrian paling banyak punya satu baris di sini. Pengaduan dan catatan
petugas ditaruh pada baris yang sama karena keduanya lahir dari pelayanan
yang sama, tetapi kolomnya terpisah dan tidak boleh disatukan: `deskripsi`
adalah kata pengunjung, `catatan` adalah penilaian petugas. Bercampur, yang
terjadi adalah penilaian internal ikut terbaca sebagai keluhan pelanggan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.counter import Counter
    from app.models.queue import Queue
    from app.models.user import User


class QueueNote(TimestampMixin, Base):
    """Isian pengaduan beserta catatan petugas untuk satu antrian."""

    __tablename__ = "queue_note"

    id: Mapped[int] = mapped_column(primary_key=True)

    # unique: satu antrian hanya punya satu lembar kerja. Petugas menyunting
    # yang sudah ada, bukan menumpuk lembar baru yang saling bertentangan.
    queue_id: Mapped[int] = mapped_column(
        sa.ForeignKey("queue.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    branch_id: Mapped[int] = mapped_column(
        sa.ForeignKey("branch.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Loket dan petugas yang MENULIS, disalin ke sini seperti pada survey:
    # laporan tetap dapat difilter walau antriannya kemudian berubah.
    counter_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("counter.id", ondelete="RESTRICT"), index=True
    )
    officer_id: Mapped[int] = mapped_column(
        sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ------------------------------------------------------------------
    # Identitas pelapor. Terisi hanya bila ada pengaduan.
    # ------------------------------------------------------------------
    # Diindeks karena inilah dua kolom yang dicari petugas di layar
    # Pengaduan — pengunjung yang kembali menyebut namanya atau nomor
    # pelanggannya, bukan nomor antriannya kemarin.
    nama: Mapped[str | None] = mapped_column(sa.String(120), index=True)
    nomor_pelanggan: Mapped[str | None] = mapped_column(sa.String(40), index=True)
    telepon: Mapped[str | None] = mapped_column(sa.String(30))
    email: Mapped[str | None] = mapped_column(sa.String(120))
    alamat: Mapped[str | None] = mapped_column(sa.Text)

    #: Keluhan menurut pengunjung.
    deskripsi: Mapped[str | None] = mapped_column(sa.Text)
    #: Catatan petugas atas pelayanan ini. Berdiri sendiri: boleh terisi
    #: walaupun tidak ada pengaduan sama sekali.
    catatan: Mapped[str | None] = mapped_column(sa.Text)

    queue: Mapped[Queue] = relationship(back_populates="note")
    branch: Mapped[Branch] = relationship()
    counter: Mapped[Counter | None] = relationship()
    officer: Mapped[User] = relationship()

    @property
    def ada_pengaduan(self) -> bool:
        """
        Apakah lembar ini memuat pengaduan, bukan sekadar catatan petugas.

        Deskripsi yang menentukan, bukan nama: nama tanpa keluhan tidak
        mengadukan apa pun, sedangkan keluhan selalu punya deskripsi.
        """
        return bool((self.deskripsi or "").strip())

    def __repr__(self) -> str:
        return f"<QueueNote queue={self.queue_id} pengaduan={self.ada_pengaduan}>"
