"""
Antrian dan alur pelayanan.

Seluruh perpindahan status antrian melewati modul ini. Tidak ada satu pun
tempat lain yang boleh mengubah `Queue.status` secara langsung — bila ada,
tabel transisi di bawah kehilangan artinya dan status tidak sah bisa lolos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime

from app.core import clock
from app.core.database import session_scope
from app.core.errors import BusinessRuleError, NotFoundError
from app.core.logger import get_logger
from app.models import AuditAction, Counter, Queue, QueueStatus, RecordStatus, User
from app.repositories.master_repository import (
    CounterRepository,
    ServiceCategoryRepository,
)
from app.repositories.queue_repository import (
    STATUS_BELUM_SELESAI,
    QueueRepository,
    terbitkan_nomor,
)
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission
from app.services.settings_service import SettingsService

logger = get_logger("queue")


#: Perpindahan status yang sah.
#:
#: Sumber kebenaran tunggal untuk pertanyaan "boleh tidak antrian ini
#: berpindah ke status itu". Yang tidak tercantum di sini ditolak.
#:
#:     WAITING -> CALLED -> SERVING -> COMPLETED
#:
#: Jalur lain: CALLED -> NO_SHOW, WAITING/CALLED -> CANCELLED,
#: dan SERVING <-> PAUSED.
TRANSISI_SAH: dict[QueueStatus, frozenset[QueueStatus]] = {
    QueueStatus.WAITING: frozenset({QueueStatus.CALLED, QueueStatus.CANCELLED}),
    QueueStatus.CALLED: frozenset(
        {QueueStatus.SERVING, QueueStatus.NO_SHOW, QueueStatus.CANCELLED}
    ),
    QueueStatus.SERVING: frozenset({QueueStatus.PAUSED, QueueStatus.COMPLETED}),
    QueueStatus.PAUSED: frozenset({QueueStatus.SERVING}),
    # Status akhir. Tidak ada jalan keluar dari sini.
    QueueStatus.COMPLETED: frozenset(),
    QueueStatus.CANCELLED: frozenset(),
    QueueStatus.NO_SHOW: frozenset(),
}

#: Nama status dalam bahasa yang dipakai petugas sehari-hari.
LABEL_STATUS: dict[QueueStatus, str] = {
    QueueStatus.WAITING: "Menunggu",
    QueueStatus.CALLED: "Dipanggil",
    QueueStatus.SERVING: "Dilayani",
    QueueStatus.PAUSED: "Ditunda",
    QueueStatus.COMPLETED: "Selesai",
    QueueStatus.CANCELLED: "Dibatalkan",
    QueueStatus.NO_SHOW: "Tidak Hadir",
}


def transisi_sah(dari: QueueStatus, ke: QueueStatus) -> bool:
    return ke in TRANSISI_SAH.get(dari, frozenset())


@dataclass(frozen=True)
class QueueInfo:
    """Data antrian yang aman dibawa ke UI, lepas dari session database."""

    id: int
    queue_number: str
    sequence_number: int
    queue_date: date
    status: QueueStatus
    category_id: int
    category_name: str
    category_prefix: str
    counter_id: int | None
    counter_name: str | None
    served_by_id: int | None
    served_by_name: str | None
    created_at: datetime
    called_at: datetime | None
    serving_at: datetime | None
    completed_at: datetime | None
    jumlah_panggilan: int = 0
    #: Batas pemanggilan yang berlaku, dari pengaturan queue.max_call_attempts.
    #: Nol berarti batasnya tidak diketahui pada data ini.
    batas_panggilan: int = 0

    @property
    def label_status(self) -> str:
        return LABEL_STATUS.get(self.status, self.status.value)

    @property
    def melewati_batas_panggilan(self) -> bool:
        """
        Sudah dipanggil sebanyak batas yang ditetapkan tanpa hadir.

        Sengaja hanya menjadi PENGINGAT, bukan penghalang. Memblokir
        panggilan ulang akan menelantarkan pengunjung yang sebenarnya hadir
        tetapi lambat sampai ke loket, sedangkan nomor yang sudah terbit
        tidak dapat diterbitkan ulang. Keputusan menyatakan seseorang tidak
        hadir tetap milik petugas yang melihat ruangannya.
        """
        return (
            self.status is QueueStatus.CALLED
            and self.batas_panggilan > 0
            and self.jumlah_panggilan >= self.batas_panggilan
        )

    @property
    def menunggu_detik(self) -> float | None:
        """Lama menunggu sampai dipanggil; None bila belum dipanggil."""
        if self.called_at is None:
            return None
        return (self.called_at - self.created_at).total_seconds()

    @property
    def layanan_detik(self) -> float | None:
        """Lama pelayanan; None bila belum selesai."""
        if self.completed_at is None or self.serving_at is None:
            return None
        return (self.completed_at - self.serving_at).total_seconds()

    def aksi_tersedia(self) -> list[str]:
        """
        Tindakan yang sah untuk status saat ini.

        Dipakai UI untuk menyalakan tombol yang tepat. Penegakan
        sesungguhnya tetap pada masing-masing metode service.
        """
        if self.status is QueueStatus.WAITING:
            return ["panggil", "batal"]
        if self.status is QueueStatus.CALLED:
            return ["panggil_ulang", "mulai_layani", "tidak_hadir", "batal"]
        if self.status is QueueStatus.SERVING:
            return ["selesai", "tunda"]
        if self.status is QueueStatus.PAUSED:
            return ["lanjutkan"]
        return []


def _as_info(
    row: Queue, jumlah_panggilan: int = 0, batas_panggilan: int = 0
) -> QueueInfo:
    return QueueInfo(
        id=row.id,
        queue_number=row.queue_number,
        sequence_number=row.sequence_number,
        queue_date=row.queue_date,
        status=row.status,
        category_id=row.category_id,
        category_name=row.category.name,
        category_prefix=row.category.prefix,
        counter_id=row.counter_id,
        counter_name=row.counter.name if row.counter else None,
        served_by_id=row.served_by_user_id,
        served_by_name=row.served_by.full_name if row.served_by else None,
        created_at=row.created_at,
        called_at=row.called_at,
        serving_at=row.serving_at,
        completed_at=row.completed_at,
        jumlah_panggilan=jumlah_panggilan,
        batas_panggilan=batas_panggilan,
    )


@dataclass(frozen=True)
class DisplayCounterState:
    """Keadaan satu loket pada layar antrian."""

    counter_id: int
    counter_name: str
    antrian: QueueInfo | None
    istirahat: bool = False


@dataclass(frozen=True)
class DisplayState:
    """
    Keadaan yang ditampilkan pada layar antrian.

    Disusun sebagai satu objek agar layar mengambil seluruh isinya dalam
    sekali panggil, bukan beberapa panggilan yang bisa saling tidak cocok
    ketika data berubah di tengah penyegaran.
    """

    terkini: QueueInfo | None
    berikutnya: list[QueueInfo]
    loket: list[DisplayCounterState] = field(default_factory=list)
    judul: str = ""


class QueueService:
    """Penerbitan nomor antrian dan seluruh alur pelayanannya."""

    def __init__(self, auth: AuthService, settings: SettingsService | None = None) -> None:
        self.auth = auth
        # Tanpa sesi: pembacaan pengaturan memang tidak menuntut hak akses,
        # dan batas pemanggilan dibutuhkan setiap kali antrian dibaca.
        self.settings = settings or SettingsService(auth)
        #: Waktu nomor terakhir terbit dari mesin ini. Disimpan di memori,
        #: bukan di database: yang perlu ditahan adalah satu orang menekan
        #: tombol berulang kali di satu kios, bukan lalu lintas antar mesin.
        self._nomor_kios_terakhir: datetime | None = None

    def batas_panggilan(self) -> int:
        """
        Batas pemanggilan yang berlaku saat ini.

        Dibaca setiap kali dipakai, bukan disimpan saat service dibuat.
        Administrator dapat mengubahnya sementara aplikasi berjalan, dan
        petugas tidak perlu membuka ulang aplikasinya.
        """
        return self.settings.get_int("queue.max_call_attempts", 3)

    # =================================================================
    # Penerbitan nomor
    # =================================================================

    def create_queue(self, category_id: int) -> QueueInfo:
        """
        Terbitkan nomor antrian baru untuk sebuah jenis layanan.

        Antrian bersifat anonim: tidak ada nama, NIK, maupun nomor telepon
        pengunjung yang disimpan.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CREATE)
        if not self.pendaftaran_dibuka():
            raise BusinessRuleError(
                "Pendaftaran antrian baru sedang ditutup sementara. "
                "Nomor yang sudah terbit tetap dapat dilayani."
            )
        if sesi.kios:
            self._pastikan_jeda_kios()

        with session_scope() as session:
            kategori = ServiceCategoryRepository(session).get_by_id(category_id)
            if kategori is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")
            if kategori.status is not RecordStatus.ACTIVE:
                raise BusinessRuleError(
                    f"Jenis layanan {kategori.name!r} sedang tidak aktif."
                )
            prefix = kategori.prefix
            branch_id = kategori.branch_id

        # Di luar session_scope: penomoran memakai transaksinya sendiri agar
        # kunci tulis dipegang sesingkat mungkin.
        terbit = terbitkan_nomor(
            branch_id=branch_id, category_id=category_id, prefix=prefix
        )

        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.CREATE_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=terbit.queue_id,
                nomor=terbit.queue_number,
            )
            info = _as_info(QueueRepository(session).get_by_id(terbit.queue_id))

        self._nomor_kios_terakhir = clock.now()
        logger.info("Nomor antrian terbit: %s", terbit.queue_number)
        return info

    def pendaftaran_dibuka(self) -> bool:
        """
        Apakah loket dan kios sedang menerima pengambilan nomor baru.

        Penutupan otomatis kedaluwarsa begitu tanggal berganti: petugas
        yang menutup pendaftaran sore hari dan lupa membukanya lagi tidak
        boleh diam-diam membuat kantor tampak tutup keesokan paginya. Hari
        baru dianggap dibuka lagi dari awal, sama seperti penomoran yang
        juga otomatis mulai dari 1 setiap tanggal baru.

        Pembacaan tidak menuntut hak akses — kios berjalan tanpa login dan
        tetap harus tahu kapan tombolnya wajib nonaktif.
        """
        if self.settings.get_bool("queue.registration_open", True):
            return True
        tanggal_tutup = self.settings.get("queue.registration_closed_date", "")
        return tanggal_tutup != str(clock.today())

    def tutup_pendaftaran(self) -> None:
        """
        Hentikan sementara penerbitan nomor baru dari seluruh loket dan kios.

        Berlaku HANYA untuk hari ini — lihat `pendaftaran_dibuka()`.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_TOGGLE_INTAKE)
        self.settings.set(
            "queue.registration_open", "false", permission=Permission.QUEUE_TOGGLE_INTAKE
        )
        self.settings.set(
            "queue.registration_closed_date",
            str(clock.today()),
            permission=Permission.QUEUE_TOGGLE_INTAKE,
        )
        logger.info("Pendaftaran antrian ditutup oleh %s", sesi.username)

    def buka_pendaftaran(self) -> None:
        """
        Buka kembali penerbitan nomor baru, memulai antrian hari ini dari awal.

        Tanggal penutupan ikut dikosongkan supaya kedua nilai itu tidak
        pernah bercerita berbeda: menutup selalu menyetel keduanya, membuka
        selalu membersihkan keduanya.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_TOGGLE_INTAKE)
        self.settings.set(
            "queue.registration_open", "true", permission=Permission.QUEUE_TOGGLE_INTAKE
        )
        self.settings.set(
            "queue.registration_closed_date",
            "",
            permission=Permission.QUEUE_TOGGLE_INTAKE,
        )
        logger.info("Pendaftaran antrian dibuka oleh %s", sesi.username)

    def jeda_kios_detik(self) -> int:
        """Jeda wajib antar-pengambilan nomor di mesin kios."""
        return self.settings.get_int("kiosk.cooldown_seconds", 10)

    def sisa_jeda_kios(self) -> float:
        """Detik yang masih harus ditunggu sebelum nomor berikutnya boleh diambil."""
        if self._nomor_kios_terakhir is None:
            return 0.0
        berlalu = (clock.now() - self._nomor_kios_terakhir).total_seconds()
        return max(0.0, self.jeda_kios_detik() - berlalu)

    def _pastikan_jeda_kios(self) -> None:
        """
        Tahan pengambilan nomor beruntun pada mesin kios.

        Kios swalayan berarti siapa pun dapat menekan tombol berkali-kali
        dan memenuhi antrian dengan nomor yang tidak ada orangnya. Jeda ini
        tidak menghapus masalahnya — orang yang sabar tetap bisa — tetapi
        menghentikan yang paling merepotkan, yaitu satu orang menekan
        berulang kali dalam hitungan detik.

        Sengaja HANYA berlaku pada sesi kios. Petugas pendaftaran melayani
        rombongan yang datang bersamaan dan tidak boleh ikut diperlambat.
        """
        sisa = self.sisa_jeda_kios()
        if sisa <= 0:
            return
        raise BusinessRuleError(
            f"Mohon tunggu {int(sisa) + 1} detik sebelum mengambil nomor berikutnya."
        )

    # =================================================================
    # Pembacaan
    # =================================================================

    def list_waiting(self, *, category_id: int | None = None) -> list[QueueInfo]:
        sesi = self.auth.require_permission(Permission.QUEUE_VIEW)
        with session_scope() as session:
            rows = QueueRepository(session).list_menunggu(
                sesi.branch_id, clock.today(), category_id=category_id
            )
            return [_as_info(r) for r in rows]

    def list_today(self, *, status: tuple[QueueStatus, ...] | None = None) -> list[QueueInfo]:
        sesi = self.auth.require_permission(Permission.QUEUE_VIEW)
        with session_scope() as session:
            rows = QueueRepository(session).list_hari_ini(
                sesi.branch_id, clock.today(), status=status
            )
            return [_as_info(r) for r in rows]

    def get_queue(self, queue_id: int) -> QueueInfo:
        self.auth.require_permission(Permission.QUEUE_VIEW)
        with session_scope() as session:
            repo = QueueRepository(session)
            row = repo.get_by_id(queue_id)
            if row is None:
                raise NotFoundError("Antrian tidak ditemukan.")
            return _as_info(
                row, repo.jumlah_pemanggilan(queue_id), self.batas_panggilan()
            )

    def current_for_counter(self, counter_id: int) -> QueueInfo | None:
        """Antrian yang sedang dipegang sebuah loket, bila ada."""
        self.auth.require_permission(Permission.QUEUE_VIEW)
        with session_scope() as session:
            repo = QueueRepository(session)
            row = repo.sedang_ditangani_loket(counter_id, clock.today())
            if row is None:
                return None
            return _as_info(
                row, repo.jumlah_pemanggilan(row.id), self.batas_panggilan()
            )

    def display_state(self, jumlah_berikutnya: int = 3) -> DisplayState:
        """
        Keadaan layar antrian untuk pengunjung.

        Memakai hak DISPLAY_VIEW, bukan QUEUE_VIEW. Komputer layar biasanya
        menghadap publik dan tidak diawasi, sehingga akun yang menjalankannya
        sengaja tidak diberi kemampuan melihat daftar antrian secara penuh
        maupun mengubah apa pun.
        """
        sesi = self.auth.require_permission(Permission.DISPLAY_VIEW)
        hari = clock.today()

        with session_scope() as session:
            repo = QueueRepository(session)

            terakhir = repo.terakhir_dipanggil(sesi.branch_id, hari, batas=1)
            # Jumlah pemanggilan wajib ikut. Layar memakainya untuk
            # membedakan panggilan ULANG dari penyegaran biasa; tanpa itu
            # nada tidak akan berbunyi lagi saat nomor dipanggil ulang.
            terkini = (
                _as_info(terakhir[0], repo.jumlah_pemanggilan(terakhir[0].id))
                if terakhir
                else None
            )

            menunggu = repo.list_menunggu(sesi.branch_id, hari)
            berikutnya = [_as_info(q) for q in menunggu[:jumlah_berikutnya]]

            counters = CounterRepository(session).list_for_branch(
                sesi.branch_id, only_active=True
            )
            per_loket: dict[int, Queue] = {}
            for antrian in repo.list_sedang_ditangani(sesi.branch_id, hari):
                if antrian.counter_id is not None and antrian.counter_id not in per_loket:
                    per_loket[antrian.counter_id] = antrian

            loket = []
            for counter in counters:
                row = per_loket.get(counter.id)
                loket.append(
                    DisplayCounterState(
                        counter_id=counter.id,
                        counter_name=counter.name,
                        antrian=(
                            _as_info(row, repo.jumlah_pemanggilan(row.id))
                            if row is not None
                            else None
                        ),
                        istirahat=counter.on_break,
                    )
                )

        return DisplayState(terkini=terkini, berikutnya=berikutnya, loket=loket)

    def counts_today(self) -> dict[QueueStatus, int]:
        sesi = self.auth.require_permission(Permission.QUEUE_VIEW)
        with session_scope() as session:
            return QueueRepository(session).hitung_per_status(
                sesi.branch_id, clock.today()
            )

    def call_history(self, queue_id: int) -> list[datetime]:
        """Waktu setiap kali nomor ini dipanggil, urut dari yang pertama."""
        self.auth.require_permission(Permission.QUEUE_VIEW)
        with session_scope() as session:
            return [c.called_at for c in QueueRepository(session).list_pemanggilan(queue_id)]

    # =================================================================
    # Alur pelayanan
    # =================================================================

    def set_istirahat(self, counter_id: int, istirahat: bool) -> None:
        """
        Tandai loket sedang istirahat, atau kembali bertugas.

        Sengaja terpisah dari `status` ACTIVE/INACTIVE loket (kewenangan
        admin di Data Master): istirahat berulang beberapa kali sehari dan
        petugas yang duduk di loket itu sendiri harus bisa mengubahnya
        tanpa memanggil admin setiap kali. Loket yang sedang istirahat
        tetap tampil di layar antrian — hanya statusnya berubah menjadi
        "ISTIRAHAT" — supaya pengunjung tidak mendatangi loket kosong yang
        sebenarnya tidak ditinggal petugas selamanya.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)

        with session_scope() as session:
            loket = self._pastikan_loket_aktif(session, counter_id, sesi.branch_id)
            if loket.on_break is istirahat:
                return
            loket.on_break = istirahat

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="counter",
                entity_id=counter_id,
                istirahat=istirahat,
            )
            logger.info(
                "Loket %s %s", loket.code, "mulai istirahat" if istirahat else "aktif kembali"
            )

    def call_next(self, counter_id: int, *, category_id: int | None = None) -> QueueInfo:
        """
        Panggil antrian paling depan ke sebuah loket.

        Loket yang masih memegang antrian belum boleh memanggil berikutnya;
        selesaikan, tunda, atau tandai tidak hadir terlebih dahulu. Tanpa
        aturan ini, pengunjung yang sedang dilayani bisa terlantar begitu
        saja saat petugas menekan "Panggil Berikutnya".
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)
        hari = clock.today()

        with session_scope() as session:
            loket = self._pastikan_loket_aktif(session, counter_id, sesi.branch_id)
            if loket.on_break:
                raise BusinessRuleError(
                    f"Loket {loket.name!r} sedang istirahat. Akhiri istirahat "
                    "terlebih dahulu sebelum memanggil antrian."
                )
            repo = QueueRepository(session)

            sedang = repo.sedang_ditangani_loket(counter_id, hari)
            if sedang is not None:
                raise BusinessRuleError(
                    f"Loket ini masih menangani {sedang.queue_number}. "
                    "Selesaikan, tunda, atau tandai tidak hadir terlebih dahulu."
                )

            # Daftar kosong berarti loket ini boleh memanggil semua jenis
            # layanan; lihat `counter_category` pada model.
            diizinkan = [kategori.id for kategori in loket.categories]
            if diizinkan and category_id is not None and category_id not in diizinkan:
                raise BusinessRuleError(
                    f"Loket {loket.name!r} tidak melayani jenis layanan itu."
                )

            antrian = repo.berikutnya_untuk_dipanggil(
                sesi.branch_id,
                hari,
                category_id=category_id,
                category_ids=diizinkan or None,
            )
            if antrian is None:
                # Pesannya membedakan "memang sepi" dari "ada yang menunggu
                # tetapi bukan bagian loket ini". Tanpa pembedaan itu petugas
                # melihat "tidak ada antrian" sementara layar di depannya
                # menampilkan sepuluh orang menunggu, lalu menyimpulkan
                # aplikasinya rusak.
                if diizinkan and repo.berikutnya_untuk_dipanggil(
                    sesi.branch_id, hari
                ) is not None:
                    raise BusinessRuleError(
                        "Tidak ada antrian untuk jenis layanan yang dilayani "
                        f"loket {loket.name!r}. Antrian yang menunggu saat ini "
                        "adalah bagian loket lain."
                    )
                raise BusinessRuleError("Tidak ada antrian yang menunggu.")

            self._pindah_status(antrian, QueueStatus.CALLED)
            # Objek relasinya ikut dipasang, bukan hanya kolom counter_id.
            # Relasi sudah terlanjur dimuat sebagai None oleh selectinload,
            # sehingga mengisi kolomnya saja membuat nama loket tetap kosong
            # pada data yang dikembalikan ke UI.
            antrian.counter = loket
            antrian.called_at = clock.now()

            repo.catat_pemanggilan(
                queue_id=antrian.id, counter_id=counter_id, user_id=sesi.user_id
            )
            audit_service.record(
                session,
                AuditAction.CALL_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
                loket=counter_id,
            )
            logger.info("Antrian %s dipanggil ke loket %s", antrian.queue_number, counter_id)
            return _as_info(
                antrian, repo.jumlah_pemanggilan(antrian.id), self.batas_panggilan()
            )

    def recall(self, queue_id: int) -> QueueInfo:
        """
        Panggil ulang nomor yang sudah dipanggil.

        Status TIDAK berubah — nomor ini memang sudah CALLED. Yang bertambah
        hanyalah satu baris riwayat pemanggilan, sehingga terlihat berapa
        kali pengunjung dipanggil sebelum dinyatakan tidak hadir.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = self._ambil(repo, queue_id)

            if antrian.status is not QueueStatus.CALLED:
                raise BusinessRuleError(
                    f"Antrian {antrian.queue_number} berstatus "
                    f"{LABEL_STATUS[antrian.status]} sehingga tidak dapat "
                    "dipanggil ulang."
                )
            if antrian.counter_id is None:
                raise BusinessRuleError("Antrian ini belum terhubung ke loket mana pun.")

            antrian.called_at = clock.now()
            repo.catat_pemanggilan(
                queue_id=antrian.id,
                counter_id=antrian.counter_id,
                user_id=sesi.user_id,
            )
            audit_service.record(
                session,
                AuditAction.CALL_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
                tindakan="panggil ulang",
            )
            jumlah = repo.jumlah_pemanggilan(antrian.id)
            logger.info("Antrian %s dipanggil ulang (ke-%d)", antrian.queue_number, jumlah)
            return _as_info(antrian, jumlah, self.batas_panggilan())

    def start_service(self, queue_id: int) -> QueueInfo:
        """Mulai melayani pengunjung yang sudah dipanggil."""
        sesi = self.auth.require_permission(Permission.QUEUE_SERVE)

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = self._ambil(repo, queue_id)

            self._pindah_status(antrian, QueueStatus.SERVING)
            antrian.serving_at = clock.now()
            # Petugas yang benar-benar melayani, bukan yang memanggil.
            # Pemanggilan ulang bisa dilakukan orang lain.
            antrian.served_by = session.get(User, sesi.user_id)

            audit_service.record(
                session,
                AuditAction.START_SERVICE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
            )
            logger.info("Pelayanan %s dimulai", antrian.queue_number)
            return _as_info(antrian, repo.jumlah_pemanggilan(antrian.id))

    def pause(self, queue_id: int) -> QueueInfo:
        """Tunda pelayanan sementara, misalnya menunggu berkas."""
        return self._ubah_sederhana(
            queue_id,
            QueueStatus.PAUSED,
            Permission.QUEUE_SERVE,
            AuditAction.PAUSE_QUEUE,
            "ditunda",
        )

    def resume(self, queue_id: int) -> QueueInfo:
        """
        Lanjutkan pelayanan yang tertunda.

        serving_at TIDAK disetel ulang. Bila disetel ulang, lama penundaan
        akan hilang dari perhitungan dan waktu layanan tampak lebih singkat
        daripada kenyataannya.
        """
        return self._ubah_sederhana(
            queue_id,
            QueueStatus.SERVING,
            Permission.QUEUE_SERVE,
            AuditAction.RESUME_QUEUE,
            "dilanjutkan",
        )

    def complete(self, queue_id: int) -> QueueInfo:
        """Selesaikan pelayanan."""
        sesi = self.auth.require_permission(Permission.QUEUE_COMPLETE)

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = self._ambil(repo, queue_id)

            self._pindah_status(antrian, QueueStatus.COMPLETED)
            antrian.completed_at = clock.now()

            audit_service.record(
                session,
                AuditAction.COMPLETE_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
            )
            logger.info("Pelayanan %s selesai", antrian.queue_number)
            return _as_info(antrian, repo.jumlah_pemanggilan(antrian.id))

    def no_show(self, queue_id: int) -> QueueInfo:
        """Tandai pengunjung tidak hadir setelah dipanggil."""
        return self._ubah_sederhana(
            queue_id,
            QueueStatus.NO_SHOW,
            Permission.QUEUE_NO_SHOW,
            AuditAction.NO_SHOW,
            "tidak hadir",
            selesai=True,
        )

    def cancel(self, queue_id: int) -> QueueInfo:
        """Batalkan antrian yang belum dilayani."""
        return self._ubah_sederhana(
            queue_id,
            QueueStatus.CANCELLED,
            Permission.QUEUE_CANCEL,
            AuditAction.CANCEL_QUEUE,
            "dibatalkan",
            selesai=True,
        )

    def ringkasan_tutup_hari(self) -> dict[QueueStatus, int]:
        """
        Jumlah antrian yang masih akan dibatalkan bila Tutup Hari dijalankan.

        Dipakai untuk memperlihatkan kepada admin apa yang akan terjadi
        sebelum tombolnya benar-benar ditekan.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CLOSE_DAY)
        with session_scope() as session:
            repo = QueueRepository(session)
            daftar = repo.list_belum_selesai(sesi.branch_id, clock.today())
            hasil = {status: 0 for status in STATUS_BELUM_SELESAI}
            for antrian in daftar:
                hasil[antrian.status] += 1
            return hasil

    def tutup_hari(self) -> int:
        """
        Batalkan seluruh antrian yang belum selesai hari ini (dan sisa hari
        sebelumnya yang belum sempat ditutup).

        Ini BUKAN pembatalan satu per satu lewat `cancel()`: nomor yang
        sedang dipanggil, dilayani, atau ditunda tidak boleh dibatalkan
        pengunjungnya sendiri (lihat TRANSISI_SAH), tetapi wajib bisa
        ditutup paksa oleh admin di akhir hari — mesin tidak pernah tahu
        kapan loket sungguh-sungguh berhenti bekerja. Karena itu perubahan
        statusnya menulis langsung, melewati `_pindah_status`, dan dicatat
        sebagai SATU audit CLOSE_DAY berisi jumlahnya, bukan satu audit per
        nomor yang bisa mencapai ratusan baris.

        Antrian yang sudah COMPLETED/CANCELLED/NO_SHOW tidak tersentuh:
        riwayat pelayanan yang sungguh terjadi tidak boleh ikut berubah.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CLOSE_DAY)
        sekarang = clock.now()

        with session_scope() as session:
            repo = QueueRepository(session)
            daftar = repo.list_belum_selesai(sesi.branch_id, clock.today())
            id_antrian = [antrian.id for antrian in daftar]
            for antrian in daftar:
                antrian.status = QueueStatus.CANCELLED
                antrian.completed_at = sekarang

            jumlah = len(daftar)
            audit_service.record(
                session,
                AuditAction.CLOSE_DAY,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=None,
                jumlah=jumlah,
                branch_id=sesi.branch_id,
                # Disimpan supaya bisa dipulihkan lewat `buka_kembali_hari()`
                # bila tombolnya tertekan tidak sengaja.
                queue_ids=id_antrian,
            )
            logger.info("Tutup hari: %d antrian dibatalkan", jumlah)
            return jumlah

    def ringkasan_buka_kembali_hari(self) -> int:
        """
        Banyaknya antrian yang masih dapat dipulihkan dari Tutup Hari
        terakhir, bila tombolnya ternyata tertekan tidak sengaja.

        Nol berarti tidak ada Tutup Hari yang baru saja terjadi, atau
        seluruh antrian yang dibatalkannya sudah disentuh lagi sejak itu
        (misalnya sudah ditutup ulang secara manual).
        """
        self.auth.require_permission(Permission.QUEUE_CLOSE_DAY)
        ids = self._id_tutup_hari_terakhir()
        if not ids:
            return 0
        with session_scope() as session:
            daftar = QueueRepository(session).list_by_ids(ids)
            return sum(1 for antrian in daftar if antrian.status is QueueStatus.CANCELLED)

    def buka_kembali_hari(self) -> int:
        """
        Batalkan efek Tutup Hari yang PALING BARU, mengembalikan antrian
        yang tersentuh menjadi WAITING seolah belum pernah dipanggil.

        Sengaja hanya mengembalikan ke WAITING, bukan ke status persisnya
        semula (CALLED/SERVING/PAUSED): pengunjung yang tadinya sedang
        dilayani bisa saja sudah pergi begitu tombol Tutup Hari tertekan,
        dan loket yang tercatat menanganinya belum tentu masih relevan.
        Nomor cukup kembali antre dan dipanggil ulang dari awal.

        Hanya menyentuh baris yang statusnya MASIH CANCELLED sejak Tutup
        Hari tadi — bila petugas sudah membatalkannya lagi secara manual
        untuk alasan lain, baris itu dilewati begitu saja.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CLOSE_DAY)
        ids = self._id_tutup_hari_terakhir()
        if not ids:
            return 0

        with session_scope() as session:
            repo = QueueRepository(session)
            daftar = [q for q in repo.list_by_ids(ids) if q.status is QueueStatus.CANCELLED]
            for antrian in daftar:
                antrian.status = QueueStatus.WAITING
                antrian.counter_id = None
                antrian.served_by_user_id = None
                antrian.called_at = None
                antrian.serving_at = None
                antrian.completed_at = None

            jumlah = len(daftar)
            audit_service.record(
                session,
                AuditAction.REOPEN_DAY,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=None,
                jumlah=jumlah,
            )
            logger.info("Buka kembali hari: %d antrian dikembalikan menunggu", jumlah)
            return jumlah

    def _id_tutup_hari_terakhir(self) -> list[int]:
        """
        Id antrian dari Tutup Hari terakhir milik cabang sesi ini, bila ada.

        Dibatasi hanya beberapa baris audit paling baru: Tutup Hari bukan
        aktivitas yang sering terjadi, dan mengembalikan sesuatu dari
        berhari-hari lalu tidak pernah dimaksudkan pengguna yang menekan
        tombol "Buka Kembali".
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CLOSE_DAY)
        for entri in audit_service.list_terakhir(batas=5, aksi=AuditAction.CLOSE_DAY.value):
            if not entri.meta:
                continue
            try:
                meta = json.loads(entri.meta)
            except ValueError:
                continue
            if meta.get("branch_id") != sesi.branch_id:
                continue
            ids = meta.get("queue_ids")
            return list(ids) if isinstance(ids, list) else []
        return []

    # =================================================================
    # Bagian dalam
    # =================================================================

    @staticmethod
    def _ambil(repo: QueueRepository, queue_id: int) -> Queue:
        antrian = repo.get_by_id(queue_id)
        if antrian is None:
            raise NotFoundError("Antrian tidak ditemukan.")
        return antrian

    @staticmethod
    def _pastikan_loket_aktif(session, counter_id: int, branch_id: int) -> Counter:
        loket = CounterRepository(session).get_by_id(counter_id)
        if loket is None or loket.branch_id != branch_id:
            raise NotFoundError("Loket tidak ditemukan.")
        if loket.status is not RecordStatus.ACTIVE:
            raise BusinessRuleError(f"Loket {loket.name!r} sedang tidak aktif.")
        return loket

    @staticmethod
    def _pindah_status(antrian: Queue, tujuan: QueueStatus) -> None:
        """
        Pindahkan status antrian, tolak bila tidak sah.

        Satu-satunya pintu perubahan status. Pesannya menyebut status
        sekarang supaya petugas paham mengapa tombolnya tidak berfungsi.
        """
        asal = antrian.status
        if asal is tujuan:
            raise BusinessRuleError(
                f"Antrian {antrian.queue_number} sudah berstatus "
                f"{LABEL_STATUS[tujuan]}."
            )
        if not transisi_sah(asal, tujuan):
            raise BusinessRuleError(
                f"Antrian {antrian.queue_number} berstatus "
                f"{LABEL_STATUS[asal]} sehingga tidak dapat diubah menjadi "
                f"{LABEL_STATUS[tujuan]}."
            )
        antrian.status = tujuan

    def _ubah_sederhana(
        self,
        queue_id: int,
        tujuan: QueueStatus,
        permission: Permission,
        aksi: AuditAction,
        keterangan: str,
        *,
        selesai: bool = False,
    ) -> QueueInfo:
        """Perpindahan status yang tidak butuh perlakuan khusus."""
        sesi = self.auth.require_permission(permission)

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = self._ambil(repo, queue_id)

            self._pindah_status(antrian, tujuan)
            if selesai:
                antrian.completed_at = clock.now()

            audit_service.record(
                session,
                aksi,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
            )
            logger.info("Antrian %s %s", antrian.queue_number, keterangan)
            return _as_info(antrian, repo.jumlah_pemanggilan(antrian.id))
