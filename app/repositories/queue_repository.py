"""
Akses data antrian.

Bagian terpenting modul ini adalah `terbitkan_nomor`. Penomoran antrian
adalah satu-satunya tempat di sistem ini yang benar-benar rawan balapan
antar penulis, dan nomor kembar berarti dua pengunjung dipanggil dengan
nomor yang sama.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.database import transaksi_tulis
from app.models import Queue, QueueCall, QueueStatus, ServiceCategory

#: Status yang berarti loket sedang menangani seseorang.
STATUS_SIBUK = (QueueStatus.CALLED, QueueStatus.SERVING, QueueStatus.PAUSED)

#: Status yang berarti antrian masih akan dilayani.
STATUS_BELUM_SELESAI = (QueueStatus.WAITING, *STATUS_SIBUK)


@dataclass(frozen=True)
class NomorTerbit:
    """Hasil penerbitan satu nomor antrian."""

    queue_id: int
    queue_number: str
    sequence_number: int
    queue_date: date


def terbitkan_nomor(
    *, branch_id: int, category_id: int, prefix: str, tanggal: date | None = None
) -> NomorTerbit:
    """
    Terbitkan satu nomor antrian baru.

    Penomoran dilakukan oleh SATU pernyataan upsert atomik. Baris sequence
    dibuat bila belum ada, dinaikkan bila sudah ada, dan nilai barunya
    dikembalikan — semuanya dalam satu langkah yang tidak dapat disela.
    Dua permintaan bersamaan karena itu pasti menerima dua nilai berbeda.

    Bentuk sebelumnya — UPDATE dahulu, INSERT bila tidak ada barisnya —
    menyimpan celah: dua penulis dapat sama-sama menemukan barisnya belum
    ada lalu sama-sama menyisipkan. Pada SQLite celah itu tidak pernah
    terlihat karena BEGIN IMMEDIATE mengunci seluruh database sejak awal
    transaksi, tetapi pada PostgreSQL celah itu nyata dan berujung nomor
    kembar. Upsert menutupnya tanpa bergantung pada perilaku satu dialect.

    Penambahan nomor dan penyimpanan antrian berada di transaksi yang sama.
    Bila salah satunya gagal, keduanya dibatalkan, sehingga tidak pernah ada
    nomor yang terpakai tanpa barisan antriannya.

    Nomor dihitung per cabang, per tanggal, per jenis layanan, sehingga
    otomatis mulai dari 1 lagi setiap hari dan A-001 dapat hidup
    berdampingan dengan B-001.
    """
    hari = tanggal or clock.today()
    sekarang = clock.now()

    with transaksi_tulis() as conn:
        # ON CONFLICT menyebut kolom primary key gabungan tabel sequence.
        # EXCLUDED tidak dipakai: nilai barunya dihitung dari baris yang
        # sudah tersimpan, bukan dari baris yang gagal disisipkan.
        urutan = conn.execute(
            sa.text(
                """
                INSERT INTO queue_sequence
                    (branch_id, queue_date, category_id, last_number)
                VALUES (:branch_id, :queue_date, :category_id, 1)
                ON CONFLICT (branch_id, queue_date, category_id)
                DO UPDATE SET last_number = queue_sequence.last_number + 1
             RETURNING last_number
                """
            ).bindparams(sa.bindparam("queue_date", type_=sa.Date)),
            {"branch_id": branch_id, "queue_date": hari, "category_id": category_id},
        ).scalar_one()

        nomor = f"{prefix}-{urutan:03d}"

        queue_id = conn.execute(
            sa.text(
                """
                INSERT INTO queue
                    (branch_id, category_id, queue_date, queue_number,
                     sequence_number, status, created_at, updated_at)
                VALUES
                    (:branch_id, :category_id, :queue_date, :queue_number,
                     :sequence_number, :status, :created_at, :updated_at)
             RETURNING id
                """
            ).bindparams(
                # Konversi tanggal/waktu diserahkan ke SQLAlchemy, bukan ke
                # adapter bawaan sqlite3 yang sudah deprecated sejak Python
                # 3.12 dan akan dihapus. Sekaligus menjamin formatnya sama
                # persis dengan yang ditulis ORM, sehingga perbandingan
                # tanggal pada query lain tetap cocok.
                sa.bindparam("queue_date", type_=sa.Date),
                sa.bindparam("created_at", type_=sa.DateTime),
                sa.bindparam("updated_at", type_=sa.DateTime),
            ),
            {
                "branch_id": branch_id,
                "category_id": category_id,
                "queue_date": hari,
                "queue_number": nomor,
                "sequence_number": urutan,
                "status": QueueStatus.WAITING.value,
                "created_at": sekarang,
                "updated_at": sekarang,
            },
        ).scalar_one()

    return NomorTerbit(
        queue_id=queue_id, queue_number=nomor, sequence_number=urutan, queue_date=hari
    )


class QueueRepository:
    """Pembacaan dan penyimpanan antrian."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -----------------------------------------------------------------
    # Pembacaan
    # -----------------------------------------------------------------

    def _dengan_relasi(self, stmt):
        return stmt.options(
            selectinload(Queue.category),
            selectinload(Queue.counter),
            selectinload(Queue.served_by),
        )

    def get_by_id(self, queue_id: int) -> Queue | None:
        return self.session.scalar(
            self._dengan_relasi(sa.select(Queue).where(Queue.id == queue_id))
        )

    def list_menunggu(
        self,
        branch_id: int,
        tanggal: date,
        *,
        category_id: int | None = None,
        category_ids: Sequence[int] | None = None,
    ) -> list[Queue]:
        """
        Antrian yang belum dipanggil, urut sesuai waktu pengambilan nomor.

        `category_id` adalah penyaringan yang dipilih petugas saat itu;
        `category_ids` adalah batas jenis layanan yang boleh dipanggil
        loketnya. None pada `category_ids` berarti tidak dibatasi.
        """
        stmt = (
            sa.select(Queue)
            .where(
                Queue.branch_id == branch_id,
                Queue.queue_date == tanggal,
                Queue.status == QueueStatus.WAITING,
            )
            .order_by(Queue.created_at, Queue.id)
        )
        if category_id is not None:
            stmt = stmt.where(Queue.category_id == category_id)
        if category_ids is not None:
            stmt = stmt.where(Queue.category_id.in_(list(category_ids)))
        return list(self.session.scalars(self._dengan_relasi(stmt)))

    def berikutnya_untuk_dipanggil(
        self,
        branch_id: int,
        tanggal: date,
        *,
        category_id: int | None = None,
        category_ids: Sequence[int] | None = None,
    ) -> Queue | None:
        """
        Antrian paling depan yang menunggu.

        Urutannya murni siapa datang lebih dahulu, lintas jenis layanan.
        Prefix hanya membedakan penomoran, bukan menentukan prioritas.
        """
        daftar = self.list_menunggu(
            branch_id, tanggal, category_id=category_id, category_ids=category_ids
        )
        return daftar[0] if daftar else None

    def sedang_ditangani_loket(self, counter_id: int, tanggal: date) -> Queue | None:
        """Antrian yang sedang dipegang sebuah loket, bila ada."""
        return self.session.scalar(
            self._dengan_relasi(
                sa.select(Queue)
                .where(
                    Queue.counter_id == counter_id,
                    Queue.queue_date == tanggal,
                    Queue.status.in_(STATUS_SIBUK),
                )
                .order_by(Queue.called_at.desc())
            )
        )

    def list_sedang_ditangani(self, branch_id: int, tanggal: date) -> list[Queue]:
        """
        Antrian yang sedang dipegang seluruh loket cabang, hari ini.

        Diurutkan dari panggilan terbaru supaya pemanggil dapat mengambil
        satu baris pertama per loket tanpa query tambahan.
        """
        return list(
            self.session.scalars(
                self._dengan_relasi(
                    sa.select(Queue)
                    .where(
                        Queue.branch_id == branch_id,
                        Queue.queue_date == tanggal,
                        Queue.status.in_(STATUS_SIBUK),
                        Queue.counter_id.is_not(None),
                    )
                    .order_by(Queue.called_at.desc())
                )
            )
        )

    def list_hari_ini(
        self, branch_id: int, tanggal: date, *, status: tuple[QueueStatus, ...] | None = None
    ) -> list[Queue]:
        stmt = (
            sa.select(Queue)
            .where(Queue.branch_id == branch_id, Queue.queue_date == tanggal)
            .order_by(Queue.created_at.desc(), Queue.id.desc())
        )
        if status:
            stmt = stmt.where(Queue.status.in_(status))
        return list(self.session.scalars(self._dengan_relasi(stmt)))

    def terakhir_dipanggil(self, branch_id: int, tanggal: date, batas: int = 1) -> list[Queue]:
        """Antrian yang paling baru dipanggil, untuk layar display."""
        return list(
            self.session.scalars(
                self._dengan_relasi(
                    sa.select(Queue)
                    .where(
                        Queue.branch_id == branch_id,
                        Queue.queue_date == tanggal,
                        Queue.called_at.is_not(None),
                    )
                    .order_by(Queue.called_at.desc())
                    .limit(batas)
                )
            )
        )

    def list_by_ids(self, ids: list[int]) -> list[Queue]:
        """Antrian dari sekumpulan id, tanpa urutan tertentu."""
        if not ids:
            return []
        return list(
            self.session.scalars(
                self._dengan_relasi(sa.select(Queue).where(Queue.id.in_(ids)))
            )
        )

    def list_belum_selesai(self, branch_id: int, sampai: date) -> list[Queue]:
        """
        Antrian yang belum mencapai status akhir, pada tanggal itu atau
        sebelumnya.

        Dipakai oleh "Tutup Hari": mengumpulkan nomor yang masih menunggu,
        dipanggil, dilayani, atau ditunda, termasuk sisa hari-hari
        sebelumnya yang tidak sempat ditutup.
        """
        stmt = (
            sa.select(Queue)
            .where(
                Queue.branch_id == branch_id,
                Queue.queue_date <= sampai,
                Queue.status.in_(STATUS_BELUM_SELESAI),
            )
            .order_by(Queue.queue_date, Queue.created_at)
        )
        return list(self.session.scalars(self._dengan_relasi(stmt)))

    def hitung_per_status(self, branch_id: int, tanggal: date) -> dict[QueueStatus, int]:
        """Jumlah antrian per status untuk satu hari."""
        baris = self.session.execute(
            sa.select(Queue.status, sa.func.count())
            .where(Queue.branch_id == branch_id, Queue.queue_date == tanggal)
            .group_by(Queue.status)
        ).all()
        hasil = {status: 0 for status in QueueStatus}
        for status, jumlah in baris:
            hasil[status] = jumlah
        return hasil

    def hitung_per_kategori(self, branch_id: int, tanggal: date) -> dict[str, int]:
        """
        Jumlah antrian per jenis layanan untuk satu hari.

        Jenis layanan yang belum menerbitkan nomor sama sekali tetap muncul
        dengan nilai nol, supaya layar ringkasan tidak berubah-ubah
        susunannya sepanjang hari.
        """
        baris = self.session.execute(
            sa.select(ServiceCategory.name, sa.func.count(Queue.id))
            .select_from(ServiceCategory)
            .outerjoin(
                Queue,
                sa.and_(
                    Queue.category_id == ServiceCategory.id,
                    Queue.queue_date == tanggal,
                ),
            )
            .where(ServiceCategory.branch_id == branch_id)
            .group_by(ServiceCategory.id)
            .order_by(ServiceCategory.prefix)
        ).all()
        return {nama: jumlah for nama, jumlah in baris}

    def rata_rata_durasi(self, branch_id: int, tanggal: date) -> tuple[float | None, float | None]:
        """
        Rata-rata lama menunggu dan lama pelayanan, dalam detik.

        Dihitung di SQL, bukan dengan menarik seluruh baris ke Python.
        Nilai None berarti belum ada satu pun antrian yang mencapai tahap
        tersebut hari ini.

        Yang dihitung hanya antrian yang benar-benar sampai ke tahapnya:
        nomor yang dibatalkan sebelum dipanggil tidak pernah "menunggu
        sampai dipanggil", dan memasukkannya akan menurunkan angka secara
        keliru.
        """
        menunggu = sa.func.avg(self._selisih_detik(Queue.created_at, Queue.called_at))
        layanan = sa.func.avg(self._selisih_detik(Queue.serving_at, Queue.completed_at))

        dasar = (Queue.branch_id == branch_id, Queue.queue_date == tanggal)
        rata_menunggu = self.session.scalar(
            sa.select(menunggu).where(*dasar, Queue.called_at.is_not(None))
        )
        rata_layanan = self.session.scalar(
            sa.select(layanan).where(
                *dasar,
                Queue.serving_at.is_not(None),
                Queue.completed_at.is_not(None),
            )
        )
        return (
            None if rata_menunggu is None else float(rata_menunggu),
            None if rata_layanan is None else float(rata_layanan),
        )

    def _selisih_detik(self, awal, akhir):
        """
        Selisih dua kolom waktu dalam detik, sesuai dialect yang dipakai.

        Tidak ada cara yang berlaku di kedua dialect. SQLite tidak mengenal
        tipe interval dan menghitungnya lewat julianday() yang bersatuan
        hari; PostgreSQL mengurangkan timestamp menjadi interval yang lalu
        diambil detiknya dengan EXTRACT.
        """
        if self.session.get_bind().dialect.name == "sqlite":
            detik_per_hari = 86400.0
            return (sa.func.julianday(akhir) - sa.func.julianday(awal)) * detik_per_hari
        return sa.extract("epoch", akhir - awal)

    def get_category(self, category_id: int) -> ServiceCategory | None:
        return self.session.get(ServiceCategory, category_id)

    # -----------------------------------------------------------------
    # Pemanggilan
    # -----------------------------------------------------------------

    def jumlah_pemanggilan(self, queue_id: int) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count())
                .select_from(QueueCall)
                .where(QueueCall.queue_id == queue_id)
            )
            or 0
        )

    def catat_pemanggilan(
        self, *, queue_id: int, counter_id: int, user_id: int
    ) -> QueueCall:
        """
        Tambahkan satu baris riwayat pemanggilan.

        Baris lama tidak pernah ditimpa, sehingga terlihat berapa kali
        sebuah nomor dipanggil sebelum dilayani atau dinyatakan tidak hadir.
        """
        panggilan = QueueCall(
            queue_id=queue_id,
            counter_id=counter_id,
            user_id=user_id,
            call_number=self.jumlah_pemanggilan(queue_id) + 1,
            called_at=clock.now(),
        )
        self.session.add(panggilan)
        self.session.flush()
        return panggilan

    def list_pemanggilan(self, queue_id: int) -> list[QueueCall]:
        return list(
            self.session.scalars(
                sa.select(QueueCall)
                .where(QueueCall.queue_id == queue_id)
                .order_by(QueueCall.call_number)
            )
        )
