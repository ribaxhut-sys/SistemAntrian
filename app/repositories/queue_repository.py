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
from datetime import date, datetime, time, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.database import transaksi_tulis
from app.models import (
    KioskTicketRequest,
    Queue,
    QueueCall,
    QueueStatus,
    ServiceCategory,
)

#: Status yang berarti loket sedang menangani seseorang.
STATUS_SIBUK = (QueueStatus.CALLED, QueueStatus.SERVING, QueueStatus.PAUSED)

#: Status yang berarti antrian masih akan dilayani.
STATUS_BELUM_SELESAI = (QueueStatus.WAITING, QueueStatus.SKIPPED, *STATUS_SIBUK)

#: Saat sebuah nomor dianggap hangus, pada tanggalnya sendiri.
#:
#: Bukan waktu sapuannya dijalankan. Nomor kemarin hangus kemarin, dan
#: menuliskan waktu hari ini membuat `rata_rata_durasi` menghitung lama
#: pelayanan berhari-hari untuk nomor yang loketnya sudah pulang.
AKHIR_HARI = time(23, 59, 59)

#: Kunci advisory PostgreSQL yang mengantrekan penulisan baris QueueCall.
#: Angka bebas yang tidak dipakai kunci lain ("ANTRIPGL" dalam heksadesimal).
KUNCI_URUTAN_PANGGILAN = 0x414E54524950474C


#: Umur kunci idempotensi tiket anjungan sebelum boleh dibuang. Tablet
#: mengulang permintaan dalam hitungan detik sampai menit; seminggu sudah
#: jauh melampaui itu dan menjaga tabelnya tetap kecil.
UMUR_KUNCI_TIKET = timedelta(days=7)


@dataclass(frozen=True)
class KunciTiket:
    """Kunci idempotensi permintaan tiket: perangkat pengirim dan UUID-nya."""

    device_id: str
    request_id: str


@dataclass(frozen=True)
class NomorTerbit:
    """Hasil penerbitan satu nomor antrian."""

    queue_id: int
    queue_number: str
    sequence_number: int
    queue_date: date


def terbitkan_nomor(
    *,
    branch_id: int,
    category_id: int,
    prefix: str,
    tanggal: date | None = None,
    kunci: KunciTiket | None = None,
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

    `kunci` (permintaan dari anjungan Android) ikut disisipkan di transaksi
    yang sama. Bila pasangan (device_id, request_id) itu sudah ada,
    IntegrityError diangkat dan SELURUH transaksi batal — urutan nomor
    tidak ikut naik, dan pemanggil mengembalikan tiket yang sudah terbit.
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

        if kunci is not None:
            tabel = KioskTicketRequest.__table__
            # Kunci kedaluwarsa cukup dibuang sekali sehari, pada nomor
            # pertama jenis layanan ini — bukan di setiap tiket, karena
            # transaksi ini memegang kunci penomoran yang ditunggu loket
            # dan anjungan lain.
            if urutan == 1:
                conn.execute(
                    tabel.delete().where(tabel.c.created_at < sekarang - UMUR_KUNCI_TIKET)
                )
            conn.execute(
                tabel.insert().values(
                    device_id=kunci.device_id,
                    request_id=kunci.request_id,
                    category_id=category_id,
                    queue_id=queue_id,
                    created_at=sekarang,
                    updated_at=sekarang,
                )
            )

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

    def get_by_id(self, queue_id: int, *, for_update: bool = False) -> Queue | None:
        stmt = sa.select(Queue).where(Queue.id == queue_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self.session.scalar(self._dengan_relasi(stmt))

    def tiket_anjungan(self, kunci: KunciTiket) -> KioskTicketRequest | None:
        """Permintaan tiket anjungan yang sudah pernah diterbitkan, bila ada."""
        return self.session.scalar(
            sa.select(KioskTicketRequest).where(
                KioskTicketRequest.device_id == kunci.device_id,
                KioskTicketRequest.request_id == kunci.request_id,
            )
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

    def list_menunggu_berurutan(
        self,
        branch_id: int,
        tanggal: date,
        *,
        rasio: int,
        category_id: int | None = None,
        category_ids: Sequence[int] | None = None,
    ) -> list[Queue]:
        """
        Antrian menunggu menurut URUTAN PANGGIL: nomor prioritas lebih dulu
        dengan rasio yang berlaku (lihat `app.services.urutan_prioritas`).
        Tanpa nomor prioritas hasilnya sama dengan `list_menunggu`.
        """
        from app.services.urutan_prioritas import susun

        daftar = self.list_menunggu(
            branch_id, tanggal, category_id=category_id, category_ids=category_ids
        )
        if not any(a.prioritas for a in daftar):
            return daftar
        beruntun = self.prioritas_beruntun(branch_id, tanggal, rasio) if rasio else 0
        return susun(daftar, rasio=rasio, beruntun=beruntun)

    def list_dilewati(self, branch_id: int, tanggal: date) -> list[Queue]:
        """Nomor yang dilewati sementara, terbaru lebih dulu."""
        stmt = (
            sa.select(Queue)
            .where(
                Queue.branch_id == branch_id,
                Queue.queue_date == tanggal,
                Queue.status == QueueStatus.SKIPPED,
            )
            .order_by(Queue.updated_at.desc(), Queue.id.desc())
        )
        return list(self.session.scalars(self._dengan_relasi(stmt)))

    def nomor_menunggu(self, branch_id: int, tanggal: date) -> list[str]:
        """Nomor antrian yang belum dipanggil, urutan sama dengan `list_menunggu`."""
        return list(
            self.session.scalars(
                sa.select(Queue.queue_number)
                .where(
                    Queue.branch_id == branch_id,
                    Queue.queue_date == tanggal,
                    Queue.status == QueueStatus.WAITING,
                )
                .order_by(Queue.created_at, Queue.id)
            )
        )

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

    def jumlah_prioritas_terbit_sejak(
        self,
        branch_id: int,
        tanggal: date,
        sejak: datetime,
        *,
        category_ids: Sequence[int] | None = None,
    ) -> int:
        """Nomor prioritas yang terbit hari ini sejak `sejak` (apa pun statusnya)."""
        stmt = sa.select(sa.func.count(Queue.id)).where(
            Queue.branch_id == branch_id,
            Queue.queue_date == tanggal,
            Queue.prioritas.is_not(None),
            Queue.created_at >= sejak,
        )
        if category_ids is not None:
            stmt = stmt.where(Queue.category_id.in_(list(category_ids)))
        return int(self.session.scalar(stmt) or 0)

    def prioritas_beruntun(self, branch_id: int, tanggal: date, batas: int) -> int:
        """
        Berapa nomor prioritas yang baru saja dipanggil berturut-turut.

        Dihitung dari pemanggilan terbaru hari ini, lintas loket: yang
        diadilkan adalah antrian, bukan satu loket. Berhenti di nomor biasa
        pertama; `batas` membatasi pembacaan.
        """
        terakhir = self.session.scalars(
            sa.select(Queue.prioritas)
            .where(
                Queue.branch_id == branch_id,
                Queue.queue_date == tanggal,
                Queue.called_at.is_not(None),
            )
            .order_by(Queue.called_at.desc(), Queue.id.desc())
            .limit(max(1, batas))
        )
        hitung = 0
        for alasan in terakhir:
            if not alasan:
                break
            hitung += 1
        return hitung

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

    def list_sedang_ditangani(
        self, branch_id: int, tanggal: date, *, for_update: bool = False
    ) -> list[Queue]:
        """
        Antrian yang sedang dipegang seluruh loket cabang, hari ini.

        Diurutkan dari panggilan terbaru supaya pemanggil dapat mengambil
        satu baris pertama per loket tanpa query tambahan.
        """
        stmt = (
            sa.select(Queue)
            .where(
                Queue.branch_id == branch_id,
                Queue.queue_date == tanggal,
                Queue.status.in_(STATUS_SIBUK),
                Queue.counter_id.is_not(None),
            )
            .order_by(Queue.called_at.desc())
        )
        if for_update:
            stmt = stmt.with_for_update()
        return list(self.session.scalars(self._dengan_relasi(stmt)))

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
        dilewati, dipanggil, dilayani, atau ditunda, termasuk sisa hari-hari
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

    def batalkan_sisa_sebelum(
        self, tanggal: date, *, branch_id: int | None = None
    ) -> list[tuple[int, date, int]]:
        """
        Batalkan antrian belum selesai dari tanggal-tanggal SEBELUM `tanggal`.

        Mengembalikan `(branch_id, queue_date, jumlah)` untuk setiap hari
        yang benar-benar tersapu. `branch_id` None menyapu seluruh cabang —
        sapuan ini berjalan saat aplikasi mulai, sebelum ada yang masuk,
        sehingga belum ada cabang yang dapat dijadikan batas.

        Ditulis sebagai UPDATE per hari, bukan baris demi baris lewat ORM,
        karena dua alasan. `completed_at` harus mengikuti tanggal barisnya
        sendiri (lihat `AKHIR_HARI`), sehingga satu UPDATE untuk semua hari
        tidak mungkin. Dan `rowcount` UPDATE menghitung baris yang SUNGGUH
        berubah: bila lima komputer loket menyala berbarengan dan sama-sama
        menyapu, hanya yang pertama menerima angka bukan nol, sehingga
        auditnya tidak tercatat lima kali untuk pekerjaan yang sama.
        """
        dasar = [Queue.queue_date < tanggal, Queue.status.in_(STATUS_BELUM_SELESAI)]
        if branch_id is not None:
            dasar.append(Queue.branch_id == branch_id)

        kelompok = self.session.execute(
            sa.select(Queue.branch_id, Queue.queue_date).where(*dasar).distinct()
        ).all()

        hasil: list[tuple[int, date, int]] = []
        for cabang, hari in kelompok:
            jumlah = self.session.execute(
                sa.update(Queue)
                .where(
                    Queue.branch_id == cabang,
                    Queue.queue_date == hari,
                    Queue.status.in_(STATUS_BELUM_SELESAI),
                )
                .values(
                    status=QueueStatus.CANCELLED,
                    completed_at=datetime.combine(hari, AKHIR_HARI),
                )
            ).rowcount
            if jumlah:
                hasil.append((cabang, hari, jumlah))
        return hasil

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

    def sampel_lama_layanan(
        self, branch_id: int, sampai: date, *, hari: int = 30, batas: int = 2000
    ) -> list[tuple[int, date, float]]:
        """
        Lama pelayanan (detik) antrian SELESAI, terbaru lebih dulu.

        Bahan perkiraan waktu tunggu di tiket. Hanya COMPLETED: nomor yang
        hangus mendapat `completed_at` akhir hari (lihat AKHIR_HARI) dan
        akan terbaca sebagai pelayanan berjam-jam. Durasi nol atau negatif
        (jam komputer bergeser) dibuang di sini, bukan di pemakainya.
        """
        durasi = self._selisih_detik(Queue.serving_at, Queue.completed_at)
        stmt = (
            sa.select(Queue.category_id, Queue.queue_date, durasi)
            .where(
                Queue.branch_id == branch_id,
                Queue.queue_date > sampai - timedelta(days=hari),
                Queue.queue_date <= sampai,
                Queue.status == QueueStatus.COMPLETED,
                Queue.serving_at.is_not(None),
                Queue.completed_at.is_not(None),
            )
            .order_by(Queue.completed_at.desc())
            .limit(batas)
        )
        return [
            (kategori, tanggal, float(detik))
            for kategori, tanggal, detik in self.session.execute(stmt)
            if detik is not None and float(detik) > 0
        ]

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

    def klaim_untuk_dipanggil(self, queue_id: int) -> bool:
        """
        Ambil satu antrian WAITING untuk loket ini, atau gagal bila sudah diambil.

        Satu UPDATE bersyarat, bukan baca-lalu-tulis. Dua loket dapat sama-
        sama MELIHAT nomor yang sama menunggu, tetapi hanya satu UPDATE yang
        menemukan statusnya masih WAITING:

        * PostgreSQL: UPDATE kedua menunggu kunci baris milik yang pertama,
          lalu menilai ulang WHERE sesudah yang pertama commit — dan tidak
          menemukan apa pun.
        * SQLite: penulis diantrekan oleh kunci tulis database; UPDATE
          kedua berjalan sesudah yang pertama commit dan juga kosong.

        Objek ORM di session sengaja tidak disinkronkan. Pemanggil tetap
        memindahkan statusnya lewat `_pindah_status` supaya aturan transisi
        dan kolom pendampingnya tetap ditulis di satu tempat.
        """
        hasil = self.session.execute(
            sa.update(Queue)
            .where(Queue.id == queue_id, Queue.status == QueueStatus.WAITING)
            .values(status=QueueStatus.CALLED, updated_at=clock.now())
            .execution_options(synchronize_session=False)
        )
        return hasil.rowcount == 1

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

        Di PostgreSQL penulisan panggilan diantrekan dengan advisory lock
        sampai transaksinya selesai. Layar antrian dan anjungan bersuara
        hanya mengingat id panggilan terakhir yang sudah diucapkannya
        (`panggilan_sejak`). Tanpa kunci, id dibagikan saat flush, bukan saat
        commit: Loket 1 mendapat id 37, Loket 2 id 38 dan commit lebih dulu,
        perangkat bertanya tepat di antaranya dan mencatat 38 — panggilan
        Loket 1 tidak pernah diucapkan. Dengan kunci, urutan id sama dengan
        urutan commit. SQLite tidak perlu: penulisnya memang satu per satu.
        """
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(
                sa.select(sa.func.pg_advisory_xact_lock(KUNCI_URUTAN_PANGGILAN))
            )
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
