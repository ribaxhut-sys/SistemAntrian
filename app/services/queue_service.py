"""
Antrian dan alur pelayanan.

Seluruh perpindahan status antrian melewati modul ini. Tidak ada satu pun
tempat lain yang boleh mengubah `Queue.status` secara langsung — bila ada,
tabel transisi di bawah kehilangan artinya dan status tidak sah bisa lolos.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import (
    AuditAction,
    Counter,
    Queue,
    QueueStatus,
    RecordStatus,
    User,
    UserRole,
)
from app.repositories.master_repository import (
    CounterRepository,
    ServiceCategoryRepository,
)
from app.repositories.queue_repository import (
    STATUS_BELUM_SELESAI,
    STATUS_SIBUK,
    KunciTiket,
    QueueRepository,
    terbitkan_nomor,
)
from app.repositories.queue_note_repository import QueueNoteRepository
from app.repositories.user_repository import UserRepository
from app.models.enums import (
    ASAL_MANDIRI,
    ASAL_PENDAFTARAN,
    LABEL_PRIORITAS,
    AlasanPrioritas,
)
from app.services import audit_service, cetak_ulang_anjungan
from app.services.urutan_prioritas import MODE_OTOMATIS, MODE_SAH, susun
from app.services.auth_service import AuthService
from app.services.note_service import PESAN_CATATAN_KURANG, catatan_memadai
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
#: Jalur lain: CALLED -> SKIPPED -> CALLED, CALLED/SKIPPED -> NO_SHOW,
#: WAITING/CALLED/SKIPPED -> CANCELLED, dan SERVING <-> PAUSED.
TRANSISI_SAH: dict[QueueStatus, frozenset[QueueStatus]] = {
    QueueStatus.WAITING: frozenset({QueueStatus.CALLED, QueueStatus.CANCELLED}),
    QueueStatus.CALLED: frozenset(
        {
            QueueStatus.SKIPPED,
            QueueStatus.SERVING,
            QueueStatus.NO_SHOW,
            QueueStatus.CANCELLED,
        }
    ),
    QueueStatus.SKIPPED: frozenset(
        {QueueStatus.CALLED, QueueStatus.NO_SHOW, QueueStatus.CANCELLED}
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
    QueueStatus.SKIPPED: "Dilewati",
    QueueStatus.SERVING: "Dilayani",
    QueueStatus.PAUSED: "Ditunda",
    QueueStatus.COMPLETED: "Selesai",
    QueueStatus.CANCELLED: "Dibatalkan",
    QueueStatus.NO_SHOW: "Tidak Hadir",
}


def transisi_sah(dari: QueueStatus, ke: QueueStatus) -> bool:
    return ke in TRANSISI_SAH.get(dari, frozenset())


#: Alasan petugas mencabut prioritas, dicatat di audit.
ALASAN_CABUT_PRIORITAS: dict[str, str] = {
    "TIDAK_MEMENUHI_SYARAT": "Tidak memenuhi syarat",
    "SALAH_PILIH": "Salah pilih di anjungan",
    "LAINNYA": "Lainnya",
}


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
    #: Alasan prioritas (AlasanPrioritas.value); None untuk nomor biasa.
    prioritas: str | None = None
    #: PENDAFTARAN, MANDIRI, atau PETUGAS; None bila nomor biasa.
    prioritas_asal: str | None = None

    @property
    def prioritas_mandiri(self) -> bool:
        """Ditandai pengunjung sendiri di anjungan: perlu diperiksa petugas."""
        return self.prioritas is not None and self.prioritas_asal == ASAL_MANDIRI

    @property
    def label_prioritas(self) -> str:
        return LABEL_PRIORITAS.get(self.prioritas or "", "")

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
        hadir atau melewatinya sementara tetap milik petugas yang melihat
        ruangannya.
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
            return [
                "panggil_ulang",
                "mulai_layani",
                "lewati",
                "tidak_hadir",
                "batal",
            ]
        if self.status is QueueStatus.SKIPPED:
            return ["panggil_kembali", "tidak_hadir", "batal"]
        if self.status is QueueStatus.SERVING:
            return ["selesai", "tunda"]
        if self.status is QueueStatus.PAUSED:
            return ["lanjutkan"]
        return []


@dataclass(frozen=True)
class TransferTargetInfo:
    """Petugas CRO beserta loket bawaannya yang dapat menjadi tujuan."""

    user_id: int
    full_name: str
    counter_id: int
    counter_name: str


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
        prioritas=row.prioritas,
        prioritas_asal=row.prioritas_asal,
    )


@dataclass(frozen=True)
class DisplayCounterState:
    """Keadaan satu loket pada layar antrian."""

    counter_id: int
    counter_name: str
    antrian: QueueInfo | None
    istirahat: bool = False


#: Pengaturan loket mana yang tampil di layar antrian dan anjungan.
KUNCI_LOKET_TAMPIL = "display.loket_tampil"
LOKET_TAMPIL_PETUGAS = "petugas"
LOKET_TAMPIL_SEMUA = "semua"
#: Tanda hidup petugas lebih tua dari ini dianggap tidak ada orangnya: PC
#: loket yang mati listrik hilang sendiri dari papan. Tiga kali selang
#: tanda hidup (SELANG_TANDA_HADIR_MS di main_window), supaya satu atau dua
#: tanda yang terlambat tidak membuat loketnya berkedip.
BATAS_HADIR_PETUGAS_DETIK = 90


#: Sampel paling sedikit sebelum median dianggap mewakili. Di bawah ini
#: satu pelayanan yang kebetulan lama atau singkat menentukan angkanya.
SAMPEL_MINIMUM_LAMA_LAYANAN = 5
#: Hanya sekian pelayanan terbaru hari ini yang dipakai: ritme pagi tidak
#: selalu sama dengan ritme siang.
SAMPEL_TERBARU_LAMA_LAYANAN = 20


def _median_terbaru(sampel: list[tuple[date, float]], hari_ini: date) -> float | None:
    """
    Median dari pelayanan hari ini; bila terlalu sedikit, ditambah riwayat.

    Median, bukan rata-rata: satu pengaduan 90 menit tidak boleh membuat
    semua pengunjung berikutnya tampak harus menunggu sejam lebih.
    `sampel` sudah terurut dari yang terbaru.
    """
    hari_ini_saja = [lama for tanggal, lama in sampel if tanggal == hari_ini]
    if len(hari_ini_saja) >= SAMPEL_MINIMUM_LAMA_LAYANAN:
        return statistics.median(hari_ini_saja[:SAMPEL_TERBARU_LAMA_LAYANAN])
    if len(sampel) >= SAMPEL_MINIMUM_LAMA_LAYANAN:
        return statistics.median(lama for _, lama in sampel)
    return None


#: Jendela pengamatan laju kedatangan nomor prioritas untuk perkiraan tunggu.
JENDELA_LAJU_PRIORITAS = timedelta(minutes=60)


def sisipan_prioritas(
    dasar_detik: float,
    *,
    laju_per_detik: float,
    lama_per_orang: float,
    loket: int,
    rasio: int,
    biasa_di_depan: int,
) -> float:
    """
    Tambahan tunggu nomor BIASA karena nomor prioritas yang datang nanti.

    Urutan saat tiket dicetak sudah memperhitungkan prioritas yang SEDANG
    menunggu. Prioritas yang datang selama pemegang tiket menunggu juga
    menyalip (3 prioritas : 1 biasa), sehingga perkiraan polos terlalu
    rendah bila banyak lansia/disabilitas datang. Banyaknya penyalip
    diperkirakan dari laju kedatangan prioritas satu jam terakhir dikali
    lama menunggu, dan dibatasi rasio: sebelum giliran tiket ini paling
    banyak `rasio` prioritas per nomor biasa di depannya (ditambah satu
    giliran untuk tiket ini sendiri). Dua putaran cukup: tunggu yang
    bertambah mendatangkan sedikit penyalip lagi, bukan deret tak berujung.
    """
    if laju_per_detik <= 0 or lama_per_orang <= 0 or loket <= 0:
        return 0.0
    batas = rasio * (biasa_di_depan + 1) if rasio > 0 else None
    tunggu = dasar_detik
    tambahan = 0.0
    for _ in range(2):
        penyalip = laju_per_detik * tunggu
        if batas is not None:
            penyalip = min(penyalip, float(batas))
        tambahan = penyalip * lama_per_orang / loket
        tunggu = dasar_detik + tambahan
    return tambahan


def _lama_layanan_tipikal(
    sampel: list[tuple[int, date, float]], hari_ini: date
) -> tuple[dict[int, float], float | None]:
    """Lama layanan tipikal per jenis layanan, beserta median gabungannya."""
    per_kategori: dict[int, list[tuple[date, float]]] = {}
    for kategori, tanggal, lama in sampel:
        per_kategori.setdefault(kategori, []).append((tanggal, lama))
    tipikal = {}
    for kategori, isi in per_kategori.items():
        median = _median_terbaru(isi, hari_ini)
        if median is not None:
            tipikal[kategori] = median
    gabungan = _median_terbaru([(t, lama) for _, t, lama in sampel], hari_ini)
    return tipikal, gabungan


@dataclass(frozen=True)
class DisplayServiceQueue:
    """
    Antrian menunggu pada satu jenis layanan.

    Layar antrian menampilkan satu kolom per jenis layanan, bukan satu
    antrean gabungan. Loket dapat dibatasi jenis layanan yang boleh
    dipanggilnya (tabel counter_category), sehingga urutan panggil memang
    berjalan per layanan — daftar gabungan justru menyiratkan urutan yang
    tidak pernah terjadi.
    """

    category_id: int
    category_name: str
    category_prefix: str
    #: Sebanyak yang diminta layar, urut waktu pengambilan nomor.
    menunggu: list[QueueInfo]
    #: Seluruh yang menunggu pada layanan ini, termasuk yang tidak termuat.
    total: int


@dataclass(frozen=True)
class Panggilan:
    """Satu pemanggilan (termasuk panggil ulang), untuk dibunyikan layar antrian."""

    id: int
    queue_number: str
    counter_name: str
    call_number: int
    #: Detik sejak panggilan, menurut jam server. Perangkat yang sempat
    #: putus melewati panggilan yang sudah basi alih-alih mengucapkannya.
    umur_detik: float = 0.0


@dataclass(frozen=True)
class DisplayState:
    """
    Keadaan yang ditampilkan pada layar antrian.

    Disusun sebagai satu objek agar layar mengambil seluruh isinya dalam
    sekali panggil, bukan beberapa panggilan yang bisa saling tidak cocok
    ketika data berubah di tengah penyegaran.
    """

    terkini: QueueInfo | None
    #: Antrian menunggu, sebanyak yang diminta layar. Televisi meminta
    #: berhalaman-halaman; papan kios meminta sederet saja.
    berikutnya: list[QueueInfo]
    loket: list[DisplayCounterState] = field(default_factory=list)
    judul: str = ""
    #: SELURUH antrian menunggu hari ini, termasuk yang tidak ikut terbawa
    #: di `berikutnya`. Layar memakainya untuk menyebut sisanya sebagai
    #: jumlah — pengunjung yang tidak menemukan nomornya perlu tahu bahwa
    #: daftarnya terpotong, bukan bahwa nomornya hilang.
    total_menunggu: int = 0
    #: Antrian menunggu dikelompokkan per jenis layanan, satu butir per
    #: kolom di layar. Kosong bila layar tidak memintanya (papan kios).
    layanan: list[DisplayServiceQueue] = field(default_factory=list)
    #: Daftar lengkap nomor publik dibawa bersama keadaan loket supaya anjungan
    #: tidak mengulang query antrian yang sama dua kali pada setiap polling.
    nomor_menunggu: list[str] = field(default_factory=list)
    nomor_prioritas: list[str] = field(default_factory=list)
    #: Nomor yang sudah dipanggil hari ini (yang terbaru lebih dulu) beserta
    #: label statusnya. Hanya nomor dan status; kosong bila layar tidak memintanya.
    dipanggil: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RingkasanTiket:
    """
    Angka yang dicetak di tiket selain nomor antriannya sendiri.

    FOTO SESAAT pada detik tiket dicetak, bukan janji. Antrian bergerak,
    nomor dibatalkan, loket istirahat — angka ini sudah berubah sebelum
    pengunjung selesai membacanya.
    """

    #: Banyaknya nomor yang masih menunggu dan terbit lebih dahulu, lintas
    #: seluruh jenis layanan. Nol berarti pemegang tiket paling depan.
    sisa_antrian: int = 0


class QueueService:
    """Penerbitan nomor antrian dan seluruh alur pelayanannya."""

    def __init__(self, auth: AuthService, settings: SettingsService | None = None) -> None:
        self.auth = auth
        # Tanpa sesi: pembacaan pengaturan memang tidak menuntut hak akses,
        # dan batas pemanggilan dibutuhkan setiap kali antrian dibaca.
        self.settings = settings or SettingsService(auth)
        #: Waktu nomor terakhir terbit, per perangkat anjungan (device_id;
        #: kosong = perangkat yang tidak menyebut dirinya). Satu tablet yang
        #: baru menerbitkan nomor tidak boleh menahan tablet lain.
        #:
        #: Sengaja di memori, bukan di database. Jeda ini hanya beberapa
        #: detik dan ditujukan pada satu orang yang menekan tombol berulang
        #: kali; API yang dinyalakan ulang butuh waktu lebih lama dari jeda
        #: itu, sehingga tidak ada yang hilang bila catatannya ikut hilang.
        #: Hanya ada satu proses API, jadi tidak ada salinan lain yang perlu
        #: diselaraskan. Perlindungan dari nomor ganda ada di database (lihat
        #: KioskTicketRequest), bukan di sini.
        self._nomor_kios_terakhir: dict[str, datetime] = {}

    def batas_panggilan(self) -> int:
        """
        Batas pemanggilan yang berlaku saat ini.

        Dibaca setiap kali dipakai, bukan disimpan saat service dibuat.
        Administrator dapat mengubahnya sementara aplikasi berjalan, dan
        petugas tidak perlu membuka ulang aplikasinya.
        """
        return self.settings.get_int("queue.max_call_attempts", 3)

    def rasio_prioritas(self) -> int:
        """Nomor prioritas beruntun sebelum satu nomor biasa; 0 = tanpa batas."""
        return max(0, self.settings.get_int("queue.rasio_prioritas", 3))

    # =================================================================
    # Penerbitan nomor
    # =================================================================

    def create_queue(
        self,
        category_id: int,
        *,
        perangkat: str = "",
        request_id: str | None = None,
        kunci_jeda: str | None = None,
        prioritas: str | None = None,
        prioritas_mandiri: bool = False,
    ) -> QueueInfo:
        """
        Terbitkan nomor antrian baru untuk sebuah jenis layanan.

        Antrian bersifat anonim: tidak ada nama, NIK, maupun nomor telepon
        pengunjung yang disimpan.

        `perangkat` adalah device_id anjungan pengirim. Jeda kios dihitung
        per `kunci_jeda` (bawaannya `perangkat`); API mengisinya kosong bila
        device_id tidak dapat dipercaya, yaitu pada token bersama yang
        X-Device-Id-nya diisi pengirim sendiri. `request_id` membuat penerbitan idempoten: permintaan
        ulang dengan pasangan (perangkat, request_id) yang sama menerima
        nomor yang SAMA, bahkan sesudah API dinyalakan ulang. Permintaan
        ulang diperiksa paling awal — sebelum pendaftaran ditutup dan
        sebelum jeda — karena nomornya memang sudah terbit; menolaknya
        membuat tablet kehilangan nomor yang sudah tercatat di antrian.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CREATE)
        if prioritas is not None:
            # Hanya petugas pendaftaran yang melihat pengunjungnya langsung.
            # Anjungan dan akun lain tidak boleh menandai prioritas sendiri.
            if sesi.role is not UserRole.REGISTRATION:
                raise BusinessRuleError(
                    "Hanya petugas pendaftaran yang dapat menandai nomor prioritas."
                )
            if prioritas not in {a.value for a in AlasanPrioritas}:
                raise ValidationError("Alasan prioritas tidak dikenal.")
        asal = None
        if prioritas is not None:
            asal = ASAL_PENDAFTARAN
        elif prioritas_mandiri:
            # Pilihan pengunjung di anjungan. Bila saklarnya dimatikan admin,
            # tablet yang masih menampilkannya tetap mendapat nomor biasa:
            # menolak penerbitan lebih merugikan daripada mengabaikannya.
            if not sesi.kios:
                raise BusinessRuleError(
                    "Pilihan prioritas mandiri hanya tersedia di anjungan."
                )
            if self.settings.get_bool("kiosk.prioritas_aktif", True):
                prioritas = AlasanPrioritas.PRIORITAS.value
                asal = ASAL_MANDIRI
        kunci = None if request_id is None else KunciTiket(perangkat, request_id)
        if kunci_jeda is None:
            kunci_jeda = perangkat
        if kunci is not None:
            sudah_terbit = self._tiket_anjungan_terbit(kunci, category_id)
            if sudah_terbit is not None:
                return sudah_terbit

        if not self.pendaftaran_dibuka():
            raise BusinessRuleError(
                "Pendaftaran antrian baru sedang ditutup sementara. "
                "Nomor yang sudah terbit tetap dapat dilayani."
            )
        if sesi.kios:
            try:
                self._pastikan_jeda_kios(kunci_jeda)
            except BusinessRuleError:
                # Kembaran permintaan ini bisa saja commit di antara
                # pemeriksaan di atas dan di sini, lalu memulai jedanya.
                # Itu permintaan ulang, bukan pengambilan beruntun.
                if kunci is not None:
                    sudah_terbit = self._tiket_anjungan_terbit(kunci, category_id)
                    if sudah_terbit is not None:
                        return sudah_terbit
                raise

        with session_scope() as session:
            repo_kategori = ServiceCategoryRepository(session)
            kategori = repo_kategori.get_by_id(category_id)
            if kategori is None:
                raise NotFoundError("Jenis layanan tidak ditemukan.")
            if kategori.status is not RecordStatus.ACTIVE:
                raise BusinessRuleError(
                    f"Jenis layanan {kategori.name!r} sedang tidak aktif."
                )
            # KELOMPOK hanya membuka daftar isinya di anjungan; nomornya
            # terbit atas nama salah satu anaknya. Ditolak di sini, bukan
            # hanya disembunyikan di layar: anjungan menyimpan daftar
            # jenis layanan di memori dan bisa saja masih memegang daftar
            # lama beberapa detik sesudah admin menambahkan anak pertama
            # ke sebuah jenis layanan.
            if repo_kategori.has_active_children(category_id):
                raise BusinessRuleError(
                    f"{kategori.name!r} adalah kelompok layanan. Pilih salah "
                    "satu layanan di dalamnya untuk mengambil nomor."
                )
            prefix = kategori.prefix
            branch_id = kategori.branch_id

        # Di luar session_scope: penomoran memakai transaksinya sendiri agar
        # kunci tulis dipegang sesingkat mungkin.
        try:
            terbit = terbitkan_nomor(
                branch_id=branch_id, category_id=category_id, prefix=prefix, kunci=kunci
            )
        except sa.exc.IntegrityError:
            # Permintaan kembar yang tiba bersamaan: yang lain sudah commit
            # lebih dulu, constraint unik membatalkan transaksi ini
            # seluruhnya (termasuk kenaikan nomor urutnya). Bila itu memang
            # sebabnya, kembalikan tiket milik yang menang.
            if kunci is None:
                raise
            sudah_terbit = self._tiket_anjungan_terbit(kunci, category_id)
            if sudah_terbit is None:
                raise
            return sudah_terbit

        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.CREATE_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=terbit.queue_id,
                nomor=terbit.queue_number,
                prioritas=prioritas,
                asal=asal,
            )
            baris = QueueRepository(session).get_by_id(terbit.queue_id)
            if prioritas is not None:
                baris.prioritas = prioritas
                baris.prioritas_asal = asal
            info = _as_info(baris)

        if sesi.kios:
            self._catat_jeda_kios(kunci_jeda)
        logger.info("Nomor antrian terbit: %s", terbit.queue_number)
        return info

    def _tiket_anjungan_terbit(
        self, kunci: KunciTiket, category_id: int
    ) -> QueueInfo | None:
        """
        Tiket yang sudah terbit untuk kunci ini, bila ada.

        request_id yang sama dengan jenis layanan BERBEDA ditolak, bukan
        dianggap permintaan ulang: tablet yang benar membuat UUID baru
        untuk setiap pilihan layanan, jadi hal ini hanya terjadi karena
        kesalahan di tablet. Menerbitkan nomor baru akan membuat satu UUID
        mewakili dua nomor; mengembalikan nomor lama akan mencetak layanan
        yang tidak dipilih pengunjung.
        """
        with session_scope() as session:
            repo = QueueRepository(session)
            baris = repo.tiket_anjungan(kunci)
            if baris is None:
                return None
            if baris.category_id != category_id:
                raise BusinessRuleError(
                    "Permintaan tiket ini sudah dipakai untuk jenis layanan "
                    "lain. Ulangi pemilihan layanan dari awal."
                )
            # Kunci disimpan seminggu, tetapi nomor hanya berlaku pada hari
            # terbitnya. Mengembalikan tiket kemarin berarti mencetak nomor
            # yang tidak akan pernah dipanggil — dan melewati penutupan
            # pendaftaran hari ini.
            if baris.created_at.date() != clock.today():
                raise BusinessRuleError(
                    "Permintaan tiket ini sudah kedaluwarsa. Ulangi pemilihan "
                    "layanan dari awal."
                )
            return _as_info(repo.get_by_id(baris.queue_id))

    def pendaftaran_dibuka(self, pengaturan=None) -> bool:
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
        sumber = pengaturan or self.settings
        if sumber.get_bool("queue.registration_open", True):
            return True
        tanggal_tutup = sumber.get("queue.registration_closed_date", "")
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

    def jeda_kios_detik(self, pengaturan=None) -> int:
        """Jeda wajib antar-pengambilan nomor di mesin kios."""
        return (pengaturan or self.settings).get_int("kiosk.cooldown_seconds", 10)

    def sisa_jeda_kios(self, perangkat: str = "", pengaturan=None) -> float:
        """
        Detik yang masih harus ditunggu perangkat ini sebelum nomor berikutnya.

        `perangkat` adalah device_id anjungan; perangkat lain tidak ikut
        tertahan oleh nomor yang baru terbit di sini.
        """
        terakhir = self._nomor_kios_terakhir.get(perangkat)
        if terakhir is None:
            return 0.0
        berlalu = (clock.now() - terakhir).total_seconds()
        return max(0.0, self.jeda_kios_detik(pengaturan) - berlalu)

    def _catat_jeda_kios(self, perangkat: str) -> None:
        sekarang = clock.now()
        # Catatan yang jedanya sudah lama lewat tidak berarti apa-apa lagi.
        # Dibuang sesekali supaya device_id tablet yang sudah dicabut tidak
        # menumpuk selama API berjalan berbulan-bulan.
        if len(self._nomor_kios_terakhir) > 256:
            self._nomor_kios_terakhir = {
                kunci: waktu
                for kunci, waktu in self._nomor_kios_terakhir.items()
                if (sekarang - waktu).total_seconds() < 3600
            }
        self._nomor_kios_terakhir[perangkat] = sekarang

    def _pastikan_jeda_kios(self, perangkat: str = "") -> None:
        """
        Tahan pengambilan nomor beruntun pada mesin kios.

        Kios swalayan berarti siapa pun dapat menekan tombol berkali-kali
        dan memenuhi antrian dengan nomor yang tidak ada orangnya. Jeda ini
        tidak menghapus masalahnya — orang yang sabar tetap bisa — tetapi
        menghentikan yang paling merepotkan, yaitu satu orang menekan
        berulang kali dalam hitungan detik.

        Sengaja HANYA berlaku pada sesi kios. Petugas pendaftaran melayani
        rombongan yang datang bersamaan dan tidak boleh ikut diperlambat.

        Berlaku per perangkat: antrean di depan Tablet A tidak boleh
        tertahan karena seseorang baru saja mengambil nomor di Tablet B.
        """
        sisa = self.sisa_jeda_kios(perangkat)
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
            rows = QueueRepository(session).list_menunggu_berurutan(
                sesi.branch_id,
                clock.today(),
                rasio=self.rasio_prioritas(),
                category_id=category_id,
            )
            return [_as_info(r) for r in rows]

    def nomor_menunggu_untuk_layar(self) -> list[str]:
        """Nomor hari ini yang aman ditampilkan pada perangkat publik."""
        sesi = self.auth.require_permission(Permission.DISPLAY_VIEW)
        with session_scope() as session:
            # Urutan panggil (prioritas dan rasio), supaya daftar di layar
            # dan anjungan sama dengan yang benar-benar akan terpanggil.
            return [
                q.queue_number
                for q in QueueRepository(session).list_menunggu_berurutan(
                    sesi.branch_id, clock.today(), rasio=self.rasio_prioritas()
                )
            ]

    def nomor_prioritas_menunggu_untuk_layar(self) -> list[str]:
        """
        Nomor menunggu hari ini yang berstatus prioritas. HANYA nomornya: alasan
        (lansia, disabilitas, ibu hamil) tidak boleh sampai ke perangkat publik.
        """
        sesi = self.auth.require_permission(Permission.DISPLAY_VIEW)
        with session_scope() as session:
            return [
                q.queue_number
                for q in QueueRepository(session).list_menunggu_berurutan(
                    sesi.branch_id, clock.today(), rasio=self.rasio_prioritas()
                )
                if q.prioritas
            ]

    def list_today(self, *, status: tuple[QueueStatus, ...] | None = None) -> list[QueueInfo]:
        sesi = self.auth.require_permission(Permission.QUEUE_VIEW)
        with session_scope() as session:
            rows = QueueRepository(session).list_hari_ini(
                sesi.branch_id, clock.today(), status=status
            )
            return [_as_info(r) for r in rows]

    def list_skipped(self) -> list[QueueInfo]:
        """Nomor hari ini yang dilewati sementara dan masih menunggu kembali."""
        sesi = self.auth.require_permission(Permission.QUEUE_VIEW)
        with session_scope() as session:
            repo = QueueRepository(session)
            return [
                _as_info(row, repo.jumlah_pemanggilan(row.id))
                for row in repo.list_dilewati(sesi.branch_id, clock.today())
            ]

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

    def _sesi_ringkasan_tiket(self):
        """
        Sesi yang berhak membaca ringkasan sebuah tiket.

        Penerbit tiket (kios, pendaftaran) memakai TICKET_PRINT. Petugas
        loket mencetak ULANG tiket nomor yang ia pegang dan tidak punya
        TICKET_PRINT, tetapi berhak QUEUE_VIEW; tanpa jalur ini penolakannya
        tercatat sebagai peringatan palsu di log dan tiketnya kehilangan
        baris sisa antrian.
        """
        if self.auth.has_permission(Permission.TICKET_PRINT):
            return self.auth.require_permission(Permission.TICKET_PRINT)
        return self.auth.require_permission(Permission.QUEUE_VIEW)

    def ringkasan_tiket(self, antrian: QueueInfo) -> RingkasanTiket:
        """
        Keadaan antrian pada detik sebuah tiket dicetak.

        Memakai hak TICKET_PRINT (atau QUEUE_VIEW bagi petugas loket yang
        mencetak ulang), bukan DISPLAY_VIEW.
        Tiket terbit dari dua tempat dengan kewenangan yang berbeda —
        anjungan kios (DISPLAY_VIEW, tanpa QUEUE_VIEW) dan meja pendaftaran
        (QUEUE_VIEW, tanpa DISPLAY_VIEW) — sehingga hak yang benar untuk
        pertanyaan ini adalah hak yang keduanya sama-sama punya: hak
        mencetak tiket itu sendiri.

        Yang dikembalikan hanya satu angka ringkas, bukan daftar antrian,
        sehingga kios di ruang publik tetap tidak dapat membaca siapa saja
        yang sedang mengantre.
        """
        sesi = self._sesi_ringkasan_tiket()

        with session_scope() as session:
            repo = QueueRepository(session)

            # Lintas seluruh jenis layanan, karena pemanggilan pun begitu:
            # `berikutnya_untuk_dipanggil` mengurutkan murni dengan waktu
            # pengambilan nomor. Menghitung hanya yang sejenis akan
            # menghasilkan angka yang jauh lebih kecil daripada kenyataan
            # yang dirasakan pengunjung di ruang tunggu.
            menunggu = repo.list_menunggu_berurutan(
                sesi.branch_id, antrian.queue_date, rasio=self.rasio_prioritas()
            )
            sisa = 0
            for antre in menunggu:
                if antre.id == antrian.id:
                    break
                sisa += 1
            else:
                # Cetak ulang tiket yang sudah dipanggil: tidak ada lagi
                # yang di depannya. Tanpa ini seluruh yang menunggu
                # terhitung sebagai "di depan".
                sisa = 0

        return RingkasanTiket(sisa_antrian=sisa)

    def perkiraan_tunggu(self, antrian: QueueInfo) -> float | None:
        """
        Perkiraan lama menunggu pemegang tiket, dalam detik.

        Rumusnya: jumlah lama layanan tipikal setiap orang di depan, dibagi
        banyaknya loket yang sanggup melayani tiket ini. "Orang di depan"
        lintas jenis layanan, karena loket memanggil lintas jenis layanan
        (lihat `berikutnya_untuk_dipanggil`), tetapi hanya jenis layanan
        yang memang dapat dipanggil loket-loket tersebut.

        None berarti TIDAK ADA perkiraan yang jujur: tidak ada loket yang
        sedang berpetugas untuk layanan ini, atau belum cukup riwayat
        pelayanan. Tiket lebih baik diam daripada mencetak angka karangan.

        Memakai hak TICKET_PRINT dengan alasan yang sama seperti
        `ringkasan_tiket`, dan hanya mengembalikan satu angka.
        """
        sesi = self.auth.require_permission(Permission.TICKET_PRINT)
        batas_hadir = clock.now() - timedelta(seconds=BATAS_HADIR_PETUGAS_DETIK)

        with session_scope() as session:
            repo = QueueRepository(session)
            melayani = [
                counter
                for counter in CounterRepository(session).list_for_branch(
                    sesi.branch_id, only_active=True
                )
                if not counter.on_break
                and counter.petugas_terlihat_pada is not None
                and counter.petugas_terlihat_pada >= batas_hadir
                and (
                    not counter.categories
                    or antrian.category_id in {c.id for c in counter.categories}
                )
            ]
            if not melayani:
                return None

            # Loket tanpa daftar layanan boleh memanggil semuanya.
            jangkauan: set[int] | None = set()
            for counter in melayani:
                if not counter.categories:
                    jangkauan = None
                    break
                jangkauan.update(c.id for c in counter.categories)

            rasio = self.rasio_prioritas()
            di_depan: list[int] = []
            biasa_di_depan = 0
            for antre in repo.list_menunggu_berurutan(
                sesi.branch_id,
                antrian.queue_date,
                rasio=rasio,
                category_ids=jangkauan,
            ):
                if antre.id == antrian.id:
                    break
                di_depan.append(antre.category_id)
                if not antre.prioritas:
                    biasa_di_depan += 1
            else:
                # Tidak lagi menunggu — cetak ulang tiket yang sudah
                # dipanggil. Tanpa ini SEMUA yang menunggu terhitung di depan.
                return None
            if not di_depan:
                return 0.0

            tipikal, gabungan = _lama_layanan_tipikal(
                repo.sampel_lama_layanan(sesi.branch_id, antrian.queue_date),
                antrian.queue_date,
            )
            # Nomor prioritas mengikuti urutan datang di kelompoknya sendiri;
            # yang datang belakangan tidak menyalipnya.
            prioritas_baru = 0
            if not antrian.prioritas and gabungan is not None:
                prioritas_baru = repo.jumlah_prioritas_terbit_sejak(
                    sesi.branch_id,
                    antrian.queue_date,
                    clock.now() - JENDELA_LAJU_PRIORITAS,
                    category_ids=jangkauan,
                )

        total = 0.0
        for kategori in di_depan:
            lama = tipikal.get(kategori, gabungan)
            if lama is None:
                return None
            total += lama
        dasar = total / len(melayani)
        if not prioritas_baru:
            return dasar
        return dasar + sisipan_prioritas(
            dasar,
            laju_per_detik=prioritas_baru / JENDELA_LAJU_PRIORITAS.total_seconds(),
            lama_per_orang=gabungan,
            loket=len(melayani),
            rasio=rasio,
            biasa_di_depan=biasa_di_depan,
        )

    def display_state(
        self,
        jumlah_berikutnya: int = 3,
        jumlah_per_layanan: int = 0,
        *,
        rasio_prioritas: int | None = None,
        loket_tampil: str | None = None,
        sertakan_terkini: bool = True,
        riwayat_dipanggil: int = 0,
    ) -> DisplayState:
        """
        Keadaan layar antrian untuk pengunjung.

        Memakai hak DISPLAY_VIEW, bukan QUEUE_VIEW. Komputer layar biasanya
        menghadap publik dan tidak diawasi, sehingga akun yang menjalankannya
        sengaja tidak diberi kemampuan melihat daftar antrian secara penuh
        maupun mengubah apa pun.

        `jumlah_per_layanan` nol berarti pengelompokan per jenis layanan
        tidak disusun sama sekali — dipakai papan kios, yang hanya memuat
        sederet nomor dan tidak punya tempat untuk berkolom.
        """
        sesi = self.auth.require_permission(Permission.DISPLAY_VIEW)
        hari = clock.today()

        with session_scope() as session:
            repo = QueueRepository(session)

            terakhir = (
                repo.terakhir_dipanggil(sesi.branch_id, hari, batas=1)
                if sertakan_terkini
                else []
            )
            # Jumlah pemanggilan wajib ikut. Layar memakainya untuk
            # membedakan panggilan ULANG dari penyegaran biasa; tanpa itu
            # nada tidak akan berbunyi lagi saat nomor dipanggil ulang.
            terkini = (
                _as_info(terakhir[0], repo.jumlah_pemanggilan(terakhir[0].id))
                if terakhir
                else None
            )

            rasio = self.rasio_prioritas() if rasio_prioritas is None else rasio_prioritas
            menunggu = repo.list_menunggu_berurutan(sesi.branch_id, hari, rasio=rasio)
            berikutnya = [_as_info(q) for q in menunggu[:jumlah_berikutnya]]
            layanan = (
                self._kelompokkan_per_layanan(
                    session, sesi.branch_id, menunggu, jumlah_per_layanan
                )
                if jumlah_per_layanan > 0
                else []
            )

            counters = CounterRepository(session).list_for_branch(
                sesi.branch_id, only_active=True
            )
            per_loket: dict[int, Queue] = {}
            for antrian in repo.list_sedang_ditangani(sesi.branch_id, hari):
                if antrian.counter_id is not None and antrian.counter_id not in per_loket:
                    per_loket[antrian.counter_id] = antrian

            dipanggil = (
                [
                    (q.queue_number, LABEL_STATUS.get(q.status, q.status.value))
                    for q in repo.terakhir_dipanggil(
                        sesi.branch_id, hari, batas=riwayat_dipanggil
                    )
                ]
                if riwayat_dipanggil > 0
                else []
            )

            nilai_loket = loket_tampil
            if nilai_loket is None:
                nilai_loket = self.settings.get(
                    KUNCI_LOKET_TAMPIL, LOKET_TAMPIL_PETUGAS
                )
            hanya_berpetugas = nilai_loket != LOKET_TAMPIL_SEMUA
            batas_hadir = clock.now() - timedelta(seconds=BATAS_HADIR_PETUGAS_DETIK)

            loket = []
            for counter in counters:
                row = per_loket.get(counter.id)
                # Loket yang masih memanggil atau melayani nomor tetap tampil
                # walau petugasnya baru keluar: pengunjung yang sudah
                # dipanggil tidak boleh kehilangan nomornya dari papan.
                if (
                    hanya_berpetugas
                    and row is None
                    and not (
                        counter.petugas_terlihat_pada is not None
                        and counter.petugas_terlihat_pada >= batas_hadir
                    )
                ):
                    continue
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

        return DisplayState(
            terkini=terkini,
            berikutnya=berikutnya,
            loket=loket,
            total_menunggu=len(menunggu),
            layanan=layanan,
            nomor_menunggu=[q.queue_number for q in menunggu],
            nomor_prioritas=[q.queue_number for q in menunggu if q.prioritas],
            dipanggil=dipanggil,
        )

    def panggilan_sejak(self, setelah_id: int | None, batas: int = 20) -> tuple[int, list[Panggilan]]:
        """
        Panggilan hari ini sesudah `setelah_id`, untuk layar antrian Android.

        Setiap pemanggilan — termasuk panggil ULANG — adalah satu baris
        QueueCall dengan id yang naik, sehingga TV cukup mengingat id
        terakhir yang sudah dibunyikannya. `setelah_id` None berarti TV baru
        tersambung: yang dikembalikan hanya id terakhir, tanpa panggilan,
        supaya TV yang baru menyala tidak membunyikan ulang panggilan lama.
        """
        sesi = self.auth.require_permission(Permission.DISPLAY_VIEW)
        hari = clock.today()
        from app.models import QueueCall

        with session_scope() as session:
            dasar = (
                sa.select(
                    QueueCall.id,
                    Queue.queue_number,
                    Counter.name,
                    QueueCall.call_number,
                    QueueCall.called_at,
                )
                .join(Queue, Queue.id == QueueCall.queue_id)
                .join(Counter, Counter.id == QueueCall.counter_id)
                .where(Queue.branch_id == sesi.branch_id, Queue.queue_date == hari)
            )
            terakhir = session.scalar(
                sa.select(sa.func.max(QueueCall.id))
                .join(Queue, Queue.id == QueueCall.queue_id)
                .where(Queue.branch_id == sesi.branch_id, Queue.queue_date == hari)
            ) or 0
            # `setelah_id` di atas id terakhir hari ini: tanggal baru belum
            # punya panggilan, atau id panggilan turun karena database
            # dipulihkan dari backup. Perangkat diarahkan ke id terakhir yang
            # sebenarnya; mengembalikan `setelah_id` membuatnya menunggu id
            # yang tidak akan datang dan diam selamanya.
            if setelah_id is None or setelah_id > terakhir:
                return terakhir, []
            baris = session.execute(
                dasar.where(QueueCall.id > setelah_id).order_by(QueueCall.id).limit(batas)
            ).all()
        sekarang = clock.now()
        hasil = [
            Panggilan(
                id=i,
                queue_number=nomor,
                counter_name=loket,
                call_number=ke,
                umur_detik=max(0.0, (sekarang - waktu).total_seconds()),
            )
            for i, nomor, loket, ke, waktu in baris
        ]
        return (hasil[-1].id if hasil else terakhir), hasil

    @staticmethod
    def _kelompokkan_per_layanan(
        session, branch_id: int, menunggu: list[Queue], batas: int
    ) -> list[DisplayServiceQueue]:
        """
        Susun satu kolom per jenis layanan, urut sesuai urutan tampilnya.

        Jenis layanan yang sedang KOSONG tetap mendapat kolomnya. Kolom yang
        muncul dan hilang mengikuti isinya membuat lebar seluruh papan
        berubah beberapa detik sekali, dan pengunjung yang sedang membaca
        kehilangan tempat matanya.

        Kolomnya mengikuti pengaturan layanan yang AKTIF, sama persis
        dengan kartu di anjungan. Satu layanan di anjungan berarti satu
        layanan di layar; dua daftar yang bersumber pada aturan berbeda
        akan berselisih tanpa ada yang tahu mana yang benar.

        Nomor pada layanan yang ditutup di tengah hari karena itu tidak
        lagi mendapat kolom. Orangnya tetap terhitung pada
        `total_menunggu`, sehingga papan masih menyebut mereka sebagai
        "dan N lainnya" — dan pemanggilannya sendiri tidak terpengaruh
        sama sekali.
        """
        per_kategori: dict[int, list[Queue]] = {}
        for antrian in menunggu:
            per_kategori.setdefault(antrian.category_id, []).append(antrian)

        hasil: list[DisplayServiceQueue] = []
        for kategori in ServiceCategoryRepository(session).list_for_branch(
            branch_id, only_active=True
        ):
            antre = per_kategori.get(kategori.id, [])
            hasil.append(
                DisplayServiceQueue(
                    category_id=kategori.id,
                    category_name=kategori.name,
                    category_prefix=kategori.prefix,
                    menunggu=[_as_info(q) for q in antre[:batas]],
                    total=len(antre),
                )
            )
        return hasil

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
            loket = self._pastikan_loket_aktif(
                session, counter_id, sesi.branch_id, kunci=True
            )
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

    def call_next(
        self,
        counter_id: int,
        *,
        category_id: int | None = None,
        urutan: str = MODE_OTOMATIS,
    ) -> QueueInfo:
        """
        Panggil antrian paling depan ke sebuah loket.

        Loket yang masih memegang antrian belum boleh memanggil berikutnya;
        selesaikan, lewati sementara, tunda, atau tandai tidak hadir terlebih
        dahulu. Tanpa aturan ini, pengunjung yang sedang dilayani bisa
        terlantar begitu saja saat petugas menekan "Panggil Berikutnya".
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)
        hari = clock.today()

        with session_scope() as session:
            # Kunci akun lebih dulu supaya perubahan loket dan pengalihan
            # admin tidak beradu dengan panggilan dari sesi yang masih basi.
            petugas = session.get(User, sesi.user_id, with_for_update=True)
            if petugas is None:
                raise NotFoundError("Akun petugas tidak ditemukan.")
            if (
                petugas.default_counter_id is not None
                and petugas.default_counter_id != counter_id
            ):
                raise BusinessRuleError(
                    "Akun Anda telah ditugaskan ke loket lain. Muat ulang "
                    "halaman pelayanan sebelum memanggil antrian."
                )
            repo = QueueRepository(session)

            # Kunci loket sebelum memeriksa apakah ia sedang menangani nomor.
            # Tanpa ini dua komputer dapat sama-sama melihat loket kosong,
            # lalu masing-masing mengklaim nomor yang berbeda.
            loket = self._pastikan_loket_aktif(
                session, counter_id, sesi.branch_id, kunci=True
            )
            if loket.on_break:
                raise BusinessRuleError(
                    f"Loket {loket.name!r} sedang istirahat. Akhiri istirahat "
                    "terlebih dahulu sebelum memanggil antrian."
                )
            sedang = repo.sedang_ditangani_loket(counter_id, hari)
            if sedang is not None:
                raise BusinessRuleError(
                    f"Loket ini masih menangani {sedang.queue_number}. "
                    "Selesaikan, lewati sementara, tunda, atau tandai tidak hadir "
                    "terlebih dahulu."
                )

            # Daftar kosong berarti loket ini boleh memanggil semua jenis
            # layanan; lihat `counter_category` pada model.
            diizinkan = [kategori.id for kategori in loket.categories]
            if diizinkan and category_id is not None and category_id not in diizinkan:
                raise BusinessRuleError(
                    f"Loket {loket.name!r} tidak melayani jenis layanan itu."
                )

            # Calon dibaca tanpa kunci, lalu diklaim satu per satu dengan
            # UPDATE bersyarat. Loket lain bisa saja mengambil calon pertama
            # di antara pembacaan dan klaim; klaim itu gagal dan calon
            # berikutnya dicoba. Nomor yang sudah diambil satu loket karena
            # itu tidak pernah ikut dipanggil loket lain.
            if urutan not in MODE_SAH:
                raise ValidationError("Urutan panggil tidak dikenal.")
            daftar = repo.list_menunggu(
                sesi.branch_id,
                hari,
                category_id=category_id,
                category_ids=diizinkan or None,
            )
            rasio = self.rasio_prioritas()
            daftar = susun(
                daftar,
                rasio=rasio,
                beruntun=(
                    repo.prioritas_beruntun(sesi.branch_id, hari, rasio or 1)
                    if rasio
                    else 0
                ),
                mode=urutan,
            )
            antrian = None
            for calon in daftar:
                if repo.klaim_untuk_dipanggil(calon.id):
                    antrian = calon
                    break
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
            # Sejak dipanggil nomor sudah menjadi tanggung jawab petugas ini.
            # Ini memungkinkan sesi lama ditolak segera setelah admin
            # mengalihkannya, termasuk sebelum pelayanan sempat dimulai.
            antrian.served_by = petugas
            antrian.called_at = clock.now()

            try:
                # Memaksa indeks unik loket aktif diperiksa sebelum riwayat
                # dan audit ditambahkan. Bila proses lain menang lebih dulu,
                # seluruh klaim transaksi ini dibatalkan oleh session_scope.
                session.flush()
            except sa.exc.IntegrityError as exc:
                raise BusinessRuleError(
                    f"Loket {loket.name!r} baru saja memanggil nomor dari "
                    "komputer lain. Muat ulang sebelum mencoba lagi."
                ) from exc

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

    def cabut_prioritas(
        self,
        queue_id: int,
        *,
        kembalikan: bool = False,
        alasan: str | None = None,
    ) -> QueueInfo:
        """
        Cabut prioritas dari nomor yang belum selesai.

        Penandaan hanya terjadi di anjungan (pilihan pengunjung) atau saat
        petugas pendaftaran menerbitkan nomor. Petugas pelayanan hanya boleh
        MENCABUT: pengunjung yang mencentang tetapi ternyata tidak berhak
        kembali ke antrian biasa, dengan urutan datangnya tetap.

        `kembalikan`: nomor yang baru DIPANGGIL (belum mulai dilayani) ikut
        dikembalikan ke daftar menunggu dengan urutan datang semula, dan
        loketnya bebas memanggil nomor berikutnya. Pengunjungnya duduk
        kembali dan dipanggil pada gilirannya. Nomor yang sudah dilayani
        tidak dapat dikembalikan; hanya prioritasnya yang dicabut.

        `alasan` (kunci ALASAN_CABUT_PRIORITAS) dicatat di audit.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)
        if alasan is not None and alasan not in ALASAN_CABUT_PRIORITAS:
            raise ValidationError("Alasan pencabutan prioritas tidak dikenal.")

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = self._ambil(repo, queue_id, for_update=True)
            if antrian.branch_id != sesi.branch_id:
                raise NotFoundError("Antrian tidak ditemukan.")
            if antrian.status.is_final:
                raise BusinessRuleError(
                    f"{antrian.queue_number} sudah selesai; prioritasnya tidak "
                    "dapat diubah."
                )
            if antrian.prioritas is None:
                return _as_info(antrian, repo.jumlah_pemanggilan(antrian.id))
            if kembalikan:
                self._pastikan_penanggung_jawab(antrian, sesi.user_id)
                if antrian.status is not QueueStatus.CALLED:
                    raise BusinessRuleError(
                        f"{antrian.queue_number} berstatus "
                        f"{LABEL_STATUS[antrian.status]}. Hanya nomor yang baru "
                        "dipanggil dan belum dilayani yang dapat dikembalikan "
                        "ke antrian."
                    )
            lama = antrian.prioritas
            asal = antrian.prioritas_asal
            antrian.prioritas = None
            antrian.prioritas_asal = None
            if kembalikan:
                # Bukan perpindahan status biasa (tidak ada di TRANSISI_SAH):
                # nomor kembali ke daftar menunggu seperti belum pernah dipanggil
                # oleh loket ini. Riwayat pemanggilannya (queue_call) tetap.
                antrian.status = QueueStatus.WAITING
                antrian.counter_id = None
                antrian.served_by_user_id = None
                antrian.called_at = None
            audit_service.record(
                session,
                AuditAction.CLEAR_PRIORITY,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
                alasan=lama,
                asal=asal,
                alasan_cabut=alasan,
                dikembalikan=kembalikan,
            )
            logger.info(
                "Prioritas %s dicabut (%s)%s",
                antrian.queue_number,
                lama,
                ", dikembalikan ke antrian" if kembalikan else "",
            )
            return _as_info(antrian, repo.jumlah_pemanggilan(antrian.id))

    def nomor_untuk_cetak_ulang(self, queue_id: int) -> QueueInfo:
        """
        Keadaan nomor untuk tiket yang dicetak ulang tablet anjungan.

        Dipakai sesi kios (hak TICKET_PRINT), yang sengaja tidak boleh
        membaca antrian secara umum; hanya satu nomor yang diminta petugas.
        """
        self.auth.require_permission(Permission.TICKET_PRINT)
        with session_scope() as session:
            repo = QueueRepository(session)
            return _as_info(
                self._ambil(repo, queue_id),
                0,
                self.batas_panggilan(),
            )

    def anjungan_penerbit(self, queue_id: int) -> str | None:
        """
        Nama anjungan tempat cetak ulang nomor ini dikeluarkan, None bila tidak ada.

        Penerbit nomor bila ia aktif; kalau tidak (nomor dari pendaftaran atau
        penerbitnya mati), anjungan lain yang aktif.
        """
        self.auth.require_permission(Permission.QUEUE_VIEW)
        tujuan = cetak_ulang_anjungan.perangkat_tujuan(queue_id)
        return (tujuan[1] or "Anjungan") if tujuan else None

    def saran_cetak_ulang_anjungan(self, queue_id: int) -> str | None:
        """
        Saran untuk petugas bila cetak ulang di anjungan belum berhasil.

        None bila tiket sudah tercetak atau tidak ada permintaan. Dibaca
        petugas beberapa detik sesudah meminta, ketika tablet sudah (atau
        belum) menjawab.
        """
        self.auth.require_permission(Permission.QUEUE_VIEW)
        keadaan = cetak_ulang_anjungan.status_terakhir(queue_id)
        if keadaan is None or keadaan[0] == cetak_ulang_anjungan.SELESAI:
            return None
        status, pesan = keadaan
        if status == cetak_ulang_anjungan.GAGAL:
            return (
                f"Tiket gagal dicetak di anjungan ({pesan or 'sebab tidak diketahui'}). "
                "Periksa kertas dan kabel printer anjungan, atau gunakan "
                "'Cetak ulang tiket' untuk mencetak di printer PC ini."
            )
        if status == cetak_ulang_anjungan.KEDALUWARSA:
            return (
                "Anjungan tidak mengambil perintah cetak. Pastikan tablet menyala "
                "dan tersambung ke jaringan, atau cetak di printer PC ini."
            )
        return (
            "Anjungan belum menjawab. Bila tiket tidak keluar, periksa tablet "
            "dan printernya, atau cetak di printer PC ini."
        )

    def minta_cetak_ulang_anjungan(self, queue_id: int) -> str:
        """
        Minta tiket nomor ini dicetak ulang di anjungan tempat ia diambil.

        Perintah diantrikan; tablet mengambilnya pada penyegaran berikutnya
        (beberapa detik) dan mencetak tiket dari keadaan nomor SAAT ITU.
        Mengembalikan nama anjungan tujuan.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)
        tujuan = cetak_ulang_anjungan.perangkat_tujuan(queue_id)
        if tujuan is None:
            raise BusinessRuleError(
                "Tidak ada anjungan berpasangan yang dapat dihubungi untuk "
                "mencetak ulang tiket ini."
            )
        device_id, nama = tujuan
        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = self._ambil(repo, queue_id)
            if antrian.branch_id != sesi.branch_id:
                raise NotFoundError("Antrian tidak ditemukan.")
            if antrian.status.is_final:
                raise BusinessRuleError(
                    f"{antrian.queue_number} sudah selesai; tiketnya tidak "
                    "perlu dicetak ulang."
                )
            perintah = cetak_ulang_anjungan.antrikan(
                session, queue_id, device_id, sesi.user_id
            )
            audit_service.record(
                session,
                AuditAction.REPRINT_TICKET_KIOSK,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
                perangkat=nama,
                perintah_id=perintah.id,
            )
            logger.info("Cetak ulang %s diminta ke anjungan %s", antrian.queue_number, nama)
        return nama or "Anjungan"

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
            self._pastikan_penanggung_jawab(antrian, sesi.user_id)

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

    def skip(self, queue_id: int) -> QueueInfo:
        """Lewati nomor yang sudah dipanggil tanpa mengakhiri antreannya."""
        return self._ubah_sederhana(
            queue_id,
            QueueStatus.SKIPPED,
            Permission.QUEUE_CALL,
            AuditAction.SKIP_QUEUE,
            "dilewati sementara",
        )

    def recall_skipped(self, queue_id: int, counter_id: int) -> QueueInfo:
        """Panggil kembali nomor yang dilewati ke loket yang sedang dipakai."""
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)
        hari = clock.today()

        with session_scope() as session:
            petugas = session.get(User, sesi.user_id, with_for_update=True)
            if petugas is None:
                raise NotFoundError("Akun petugas tidak ditemukan.")
            if (
                petugas.default_counter_id is not None
                and petugas.default_counter_id != counter_id
            ):
                raise BusinessRuleError(
                    "Akun Anda telah ditugaskan ke loket lain. Muat ulang "
                    "halaman pelayanan sebelum memanggil antrian."
                )

            repo = QueueRepository(session)
            loket = self._pastikan_loket_aktif(
                session, counter_id, sesi.branch_id, kunci=True
            )
            if loket.on_break:
                raise BusinessRuleError(
                    f"Loket {loket.name!r} sedang istirahat. Akhiri istirahat "
                    "terlebih dahulu sebelum memanggil antrian."
                )
            sedang = repo.sedang_ditangani_loket(counter_id, hari)
            if sedang is not None:
                raise BusinessRuleError(
                    f"Loket ini masih menangani {sedang.queue_number}. "
                    "Selesaikan terlebih dahulu sebelum memanggil kembali "
                    "nomor yang dilewati."
                )

            antrian = repo.get_by_id(queue_id, for_update=True)
            if (
                antrian is None
                or antrian.branch_id != sesi.branch_id
                or antrian.queue_date != hari
            ):
                raise BusinessRuleError(
                    "Antrian yang dilewati tidak ditemukan untuk hari ini."
                )
            if antrian.status is not QueueStatus.SKIPPED:
                raise BusinessRuleError(
                    f"Antrian {antrian.queue_number} berstatus "
                    f"{LABEL_STATUS[antrian.status]} sehingga tidak dapat "
                    "dipanggil kembali dari daftar dilewati."
                )

            diizinkan = [kategori.id for kategori in loket.categories]
            if diizinkan and antrian.category_id not in diizinkan:
                raise BusinessRuleError(
                    f"Loket {loket.name!r} tidak melayani jenis layanan "
                    f"{antrian.category.name!r}."
                )

            self._pindah_status(antrian, QueueStatus.CALLED)
            antrian.counter = loket
            antrian.served_by = petugas
            antrian.called_at = clock.now()
            try:
                session.flush()
            except sa.exc.IntegrityError as exc:
                raise BusinessRuleError(
                    f"Loket {loket.name!r} baru saja memanggil nomor dari "
                    "komputer lain. Muat ulang sebelum mencoba lagi."
                ) from exc

            repo.catat_pemanggilan(
                queue_id=antrian.id,
                counter_id=counter_id,
                user_id=sesi.user_id,
            )
            audit_service.record(
                session,
                AuditAction.CALL_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
                tindakan="panggil kembali setelah dilewati",
                loket=counter_id,
            )
            jumlah = repo.jumlah_pemanggilan(antrian.id)
            logger.info(
                "Antrian %s dipanggil kembali setelah dilewati (ke-%d)",
                antrian.queue_number,
                jumlah,
            )
            return _as_info(antrian, jumlah, self.batas_panggilan())

    def start_service(self, queue_id: int) -> QueueInfo:
        """Mulai melayani pengunjung yang sudah dipanggil."""
        sesi = self.auth.require_permission(Permission.QUEUE_SERVE)

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = self._ambil(repo, queue_id)
            self._pastikan_penanggung_jawab(antrian, sesi.user_id)

            self._pindah_status(antrian, QueueStatus.SERVING)
            antrian.serving_at = clock.now()
            # Tegaskan kembali pemilik pelayanan saat pengunjung tiba.
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

    def siapkan_logout_petugas(self) -> list[str]:
        """Kembalikan panggilan yang belum dimulai sebelum sesi petugas berakhir.

        Nomor yang sudah mulai dilayani tetap aktif agar petugas lain dapat
        mengambil alih. Sebaliknya, nomor yang baru dipanggil aman
        dikembalikan ke antrean agar dapat dipanggil petugas lain.
        """
        sesi = self.auth.require_session()
        if not self.auth.has_permission(Permission.QUEUE_CALL):
            # Admin, supervisor, dan pendaftaran tidak memegang nomor; tidak
            # ada yang perlu dikembalikan, dan keluar tidak boleh tertahan
            # hanya karena perannya tidak memanggil.
            return []
        with session_scope() as session:
            repo = QueueRepository(session)
            aktif = [
                row
                for row in repo.list_sedang_ditangani(
                    sesi.branch_id, clock.today(), for_update=True
                )
                if row.served_by_user_id == sesi.user_id
            ]
            masih_dilayani = [
                row.queue_number
                for row in aktif
                if row.status in (QueueStatus.SERVING, QueueStatus.PAUSED)
            ]
            for antrian in aktif:
                if antrian.status is not QueueStatus.CALLED:
                    continue
                nomor = antrian.queue_number
                antrian.status = QueueStatus.WAITING
                antrian.counter_id = None
                antrian.served_by_user_id = None
                antrian.called_at = None
                audit_service.record(
                    session,
                    AuditAction.RETURN_QUEUE_TO_WAITING,
                    user_id=sesi.user_id,
                    entity_type="queue",
                    entity_id=antrian.id,
                    nomor=nomor,
                    tindakan="dikembalikan ke antrean saat petugas keluar",
                )
                logger.info("Antrian %s dikembalikan saat petugas keluar", nomor)
            return masih_dilayani

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

    def complete(self, queue_id: int, *, wajib_catatan: bool = False) -> QueueInfo:
        """
        Selesaikan pelayanan.

        Layar pelayanan petugas memanggilnya dengan `wajib_catatan=True`:
        pelayanan hanya boleh ditutup bila lembarnya sudah memuat catatan
        petugas yang memadai (lihat `catatan_memadai`). Diperiksa di sini,
        dari lembar yang TERSIMPAN, bukan dari isi layar, sehingga tidak
        ada jalan menyelesaikan nomor tanpa jejak lewat kode UI yang lain.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_COMPLETE)

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = self._ambil(repo, queue_id)
            self._pastikan_penanggung_jawab(antrian, sesi.user_id)

            if wajib_catatan:
                lembar = QueueNoteRepository(session).get_by_queue(antrian.id)
                if lembar is None or not catatan_memadai(lembar.catatan):
                    raise BusinessRuleError(PESAN_CATATAN_KURANG)

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

    # -----------------------------------------------------------------
    # Pengambilalihan oleh administrator
    # -----------------------------------------------------------------

    def list_pelayanan_aktif(self) -> list[QueueInfo]:
        """
        Daftar pelayanan aktif di cabang sesi.

        Dilihat petugas pelayanan (untuk mengambil alih nomor yang ditinggal)
        dan admin (untuk mengalihkan, membatalkan, atau menyelesaikan paksa).
        Admin tidak memegang QUEUE_CALL, jadi salah satu hak sudah cukup.
        """
        sesi = (
            self.auth.require_permission(Permission.QUEUE_CALL)
            if self.auth.has_permission(Permission.QUEUE_CALL)
            else self.auth.require_permission(Permission.QUEUE_REASSIGN)
        )
        with session_scope() as session:
            repo = QueueRepository(session)
            return [
                _as_info(row, repo.jumlah_pemanggilan(row.id))
                for row in repo.list_sedang_ditangani(
                    sesi.branch_id, clock.today()
                )
            ]

    def list_tujuan_pengalihan(self) -> list[TransferTargetInfo]:
        """CRO aktif yang sudah memiliki loket bawaan aktif."""
        sesi = self.auth.require_permission(Permission.QUEUE_REASSIGN)
        with session_scope() as session:
            loket_repo = CounterRepository(session)
            hasil = []
            for user in UserRepository(session).list_by_role(UserRole.CRO):
                if (
                    user.branch_id != sesi.branch_id
                    or user.status is not RecordStatus.ACTIVE
                    or user.default_counter_id is None
                ):
                    continue
                loket = loket_repo.get_by_id(user.default_counter_id)
                if loket is None or loket.status is not RecordStatus.ACTIVE:
                    continue
                hasil.append(
                    TransferTargetInfo(
                        user_id=user.id,
                        full_name=user.full_name,
                        counter_id=loket.id,
                        counter_name=loket.name,
                    )
                )
            return sorted(hasil, key=lambda item: item.full_name.casefold())

    def ambil_alih_pelayanan(self, queue_id: int) -> QueueInfo:
        """Pindahkan pelayanan aktif ke petugas yang sedang masuk.

        Status dan waktu mulai dipertahankan agar durasi pelayanan tidak
        hilang; penguncian baris mencegah dua petugas mengambil nomor sama.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_CALL)
        with session_scope() as session:
            repo = QueueRepository(session)
            petugas = session.get(User, sesi.user_id, with_for_update=True)
            if petugas is None or petugas.default_counter_id is None:
                raise BusinessRuleError("Akun Anda belum memiliki loket bawaan.")
            antrian = repo.get_by_id(queue_id, for_update=True)
            if (antrian is None or antrian.branch_id != sesi.branch_id
                    or antrian.queue_date != clock.today()
                    or antrian.status not in (QueueStatus.SERVING, QueueStatus.PAUSED)):
                raise BusinessRuleError("Nomor itu tidak lagi dapat diambil alih.")
            # Pengambilalihan untuk nomor yang ditinggal, bukan untuk merebut
            # dari rekan yang sedang melayani. Pemilik dianggap pergi bila ia
            # sudah keluar (tanda hadir loket dilepas) atau komputernya mati
            # sehingga tanda hadirnya basi.
            if antrian.served_by_user_id not in (None, sesi.user_id):
                batas_hadir = clock.now() - timedelta(seconds=BATAS_HADIR_PETUGAS_DETIK)
                masih_hadir = session.scalar(
                    sa.select(Counter.id).where(
                        Counter.petugas_user_id == antrian.served_by_user_id,
                        Counter.petugas_terlihat_pada.is_not(None),
                        Counter.petugas_terlihat_pada >= batas_hadir,
                    )
                )
                if masih_hadir is not None:
                    nama = antrian.served_by.full_name if antrian.served_by else "Petugas"
                    raise BusinessRuleError(
                        f"{nama} masih hadir dan melayani nomor ini. "
                        "Minta admin mengalihkannya bila perlu."
                    )
            loket = self._pastikan_loket_aktif(
                session, petugas.default_counter_id, sesi.branch_id, kunci=True
            )
            aktif = repo.list_sedang_ditangani(sesi.branch_id, clock.today(), for_update=True)
            if any(row.id != queue_id and row.counter_id == loket.id for row in aktif):
                raise BusinessRuleError(f"Loket {loket.name!r} masih menangani nomor lain.")
            if any(row.id != queue_id and row.served_by_user_id == sesi.user_id for row in aktif):
                raise BusinessRuleError("Anda masih menangani nomor lain.")
            lama_id = antrian.served_by_user_id
            lama_nama = antrian.served_by.full_name if antrian.served_by else None
            antrian.counter = loket
            antrian.served_by = petugas
            audit_service.record(
                session, AuditAction.REASSIGN_QUEUE, user_id=sesi.user_id,
                entity_type="queue", entity_id=antrian.id, nomor=antrian.queue_number,
                tindakan="ambil alih pelayanan tanpa izin khusus",
                petugas_lama_id=lama_id, petugas_lama=lama_nama,
                petugas_baru_id=petugas.id, petugas_baru=petugas.full_name,
                loket_baru=loket.name,
            )
            return _as_info(antrian, repo.jumlah_pemanggilan(antrian.id))

    def alihkan_pelayanan(
        self, queue_id: int, target_user_id: int, alasan: str
    ) -> QueueInfo:
        """
        Alihkan nomor aktif kepada CRO dan loket bawaannya.

        Loket bawaan akun tidak diubah. Bila pelayanan sudah berjalan,
        status menjadi PAUSED agar petugas baru meninjau keadaan sebelum
        melanjutkannya.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_REASSIGN)
        alasan_bersih = self._alasan_admin(alasan)

        with session_scope() as session:
            repo = QueueRepository(session)
            # Urutan kuncinya sama dengan call_next(): akun, antrean, lalu
            # loket. Dengan begitu panggilan bersamaan tidak dapat lolos di
            # sela pemeriksaan bahwa target masih kosong.
            target = session.get(User, target_user_id, with_for_update=True)
            if (
                target is None
                or target.branch_id != sesi.branch_id
                or target.role is not UserRole.CRO
                or target.status is not RecordStatus.ACTIVE
            ):
                raise BusinessRuleError("Petugas tujuan tidak aktif atau bukan CRO.")
            if target.default_counter_id is None:
                raise BusinessRuleError(
                    f"Petugas {target.full_name!r} belum memiliki loket bawaan."
                )

            aktif = repo.list_sedang_ditangani(
                sesi.branch_id, clock.today(), for_update=True
            )
            antrian = next((row for row in aktif if row.id == queue_id), None)
            if antrian is None:
                raise BusinessRuleError(
                    "Antrian tidak lagi aktif hari ini. Muat ulang daftar."
                )

            tujuan = self._pastikan_loket_aktif(
                session, target.default_counter_id, sesi.branch_id, kunci=True
            )
            kategori_tujuan = {kategori.id for kategori in tujuan.categories}
            if kategori_tujuan and antrian.category_id not in kategori_tujuan:
                raise BusinessRuleError(
                    f"Loket {tujuan.name!r} tidak melayani "
                    f"{antrian.category.name!r}. Pilih petugas di loket lain."
                )
            if (
                antrian.served_by_user_id == target.id
                and antrian.counter_id == tujuan.id
            ):
                raise BusinessRuleError(
                    f"Antrian {antrian.queue_number} sudah ditangani "
                    f"{target.full_name} di {tujuan.name}."
                )

            for lain in aktif:
                if lain.id == antrian.id:
                    continue
                if lain.counter_id == tujuan.id:
                    raise BusinessRuleError(
                        f"Loket {tujuan.name!r} masih menangani "
                        f"{lain.queue_number}."
                    )
                if lain.served_by_user_id == target.id:
                    raise BusinessRuleError(
                        f"Petugas {target.full_name!r} masih menangani "
                        f"{lain.queue_number}."
                    )

            counter_lama_id = antrian.counter_id
            counter_lama_nama = antrian.counter.name if antrian.counter else None
            petugas_lama_id = antrian.served_by_user_id
            petugas_lama_nama = (
                antrian.served_by.full_name if antrian.served_by else None
            )
            status_lama = antrian.status

            if antrian.status is QueueStatus.SERVING:
                antrian.status = QueueStatus.PAUSED
            antrian.counter = tujuan
            antrian.served_by = target

            try:
                session.flush()
            except sa.exc.IntegrityError as exc:
                raise BusinessRuleError(
                    f"Loket {tujuan.name!r} baru saja menerima antrian lain. "
                    "Muat ulang sebelum mencoba lagi."
                ) from exc

            audit_service.record(
                session,
                AuditAction.REASSIGN_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
                alasan=alasan_bersih,
                petugas_lama_id=petugas_lama_id,
                petugas_lama=petugas_lama_nama,
                petugas_baru_id=target.id,
                petugas_baru=target.full_name,
                loket_lama_id=counter_lama_id,
                loket_lama=counter_lama_nama,
                loket_baru_id=tujuan.id,
                loket_baru=tujuan.name,
                status_lama=status_lama.value,
                status_baru=antrian.status.value,
            )
            logger.info(
                "Antrian %s dialihkan admin ke %s di %s",
                antrian.queue_number,
                target.full_name,
                tujuan.name,
            )
            return _as_info(
                antrian, repo.jumlah_pemanggilan(antrian.id), self.batas_panggilan()
            )

    def batalkan_paksa(self, queue_id: int, alasan: str) -> QueueInfo:
        """Batalkan nomor aktif oleh admin ketika pelayanan tidak dilanjutkan."""
        sesi = self.auth.require_permission(Permission.QUEUE_REASSIGN)
        alasan_bersih = self._alasan_admin(alasan)

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = repo.get_by_id(queue_id, for_update=True)
            if (
                antrian is None
                or antrian.branch_id != sesi.branch_id
                or antrian.queue_date != clock.today()
                or antrian.status not in (*STATUS_SIBUK, QueueStatus.SKIPPED)
            ):
                raise BusinessRuleError(
                    "Antrian tidak lagi aktif hari ini. Muat ulang daftar."
                )

            status_lama = antrian.status
            antrian.status = QueueStatus.CANCELLED
            antrian.completed_at = clock.now()
            audit_service.record(
                session,
                AuditAction.FORCE_CANCEL_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
                alasan=alasan_bersih,
                status_lama=status_lama.value,
                loket_id=antrian.counter_id,
                petugas_id=antrian.served_by_user_id,
            )
            logger.info("Antrian %s dibatalkan paksa admin", antrian.queue_number)
            return _as_info(
                antrian, repo.jumlah_pemanggilan(antrian.id), self.batas_panggilan()
            )

    def selesaikan_paksa(self, queue_id: int, alasan: str) -> QueueInfo:
        """
        Selesaikan nomor yang tertinggal di loket, oleh admin.

        Untuk pelayanan yang sebenarnya sudah rampung tetapi petugasnya
        pergi tanpa menutupnya. Tidak menuntut catatan petugas, tetapi
        alasannya wajib dan tercatat di audit bersama petugas aslinya.
        Hanya nomor yang sedang dilayani atau ditunda yang dapat ditutup
        begini; nomor yang baru dipanggil belum pernah dilayani.
        """
        sesi = self.auth.require_permission(Permission.QUEUE_REASSIGN)
        alasan_bersih = self._alasan_admin(alasan)

        with session_scope() as session:
            repo = QueueRepository(session)
            antrian = repo.get_by_id(queue_id, for_update=True)
            if (
                antrian is None
                or antrian.branch_id != sesi.branch_id
                or antrian.queue_date != clock.today()
                or antrian.status not in (QueueStatus.SERVING, QueueStatus.PAUSED)
            ):
                raise BusinessRuleError(
                    "Hanya nomor yang sedang dilayani atau ditunda hari ini "
                    "yang dapat diselesaikan. Muat ulang daftar."
                )

            status_lama = antrian.status
            antrian.status = QueueStatus.COMPLETED
            antrian.completed_at = clock.now()
            audit_service.record(
                session,
                AuditAction.COMPLETE_QUEUE,
                user_id=sesi.user_id,
                entity_type="queue",
                entity_id=antrian.id,
                nomor=antrian.queue_number,
                paksa=True,
                alasan=alasan_bersih,
                status_lama=status_lama.value,
                loket_id=antrian.counter_id,
                petugas_id=antrian.served_by_user_id,
            )
            logger.info("Antrian %s diselesaikan paksa admin", antrian.queue_number)
            return _as_info(
                antrian, repo.jumlah_pemanggilan(antrian.id), self.batas_panggilan()
            )

    def hanguskan_hari_lalu(self) -> int:
        """
        Hanguskan seluruh nomor sisa hari-hari SEBELUM hari ini.

        Pergantian hari mengakhiri antrian, sama seperti ia mengembalikan
        penomoran ke 1 dan membuka kembali pendaftaran yang ditutup sore
        kemarin (lihat `pendaftaran_dibuka`). Sebelum ini, satu-satunya
        yang mengubah statusnya adalah Tutup Hari yang harus ditekan orang;
        bila tidak ada yang menekan, laporan tanggal itu selamanya menyebut
        ada N orang menunggu di kantor yang sudah tutup.

        Hari INI tidak disentuh. Mesin tidak pernah tahu kapan loket
        sungguh-sungguh berhenti bekerja — itu sebabnya Tutup Hari tetap
        manual, dan alasannya sudah ditulis di `tutup_hari()`.

        Tidak menuntut hak akses apa pun, dan auditnya tidak beratas nama
        siapa-siapa. Sapuan ini berjalan saat aplikasi mulai, sebelum ada
        yang masuk; mencatatnya atas nama petugas yang kebetulan login
        pertama pagi itu akan menuduhkan kepadanya pekerjaan yang tidak
        pernah ia lakukan.

        Auditnya memakai EXPIRE_QUEUE, bukan CLOSE_DAY: `buka_kembali_hari()`
        mencari CLOSE_DAY terakhir untuk dipulihkan, dan mengembalikan nomor
        kemarin menjadi WAITING hari ini tidak pernah benar.
        """
        with session_scope() as session:
            tersapu = QueueRepository(session).batalkan_sisa_sebelum(clock.today())
            jumlah = 0
            for branch_id, hari, banyak in tersapu:
                jumlah += banyak
                audit_service.record(
                    session,
                    AuditAction.EXPIRE_QUEUE,
                    user_id=None,
                    entity_type="queue",
                    entity_id=None,
                    jumlah=banyak,
                    branch_id=branch_id,
                    tanggal=str(hari),
                )
                logger.info(
                    "Nomor antrian %s hangus: %d nomor dibatalkan", hari, banyak
                )
            return jumlah

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
    def _alasan_admin(alasan: str) -> str:
        bersih = " ".join((alasan or "").split())
        if not bersih:
            raise ValidationError("Alasan tindakan admin wajib diisi.")
        if len(bersih) > 300:
            raise ValidationError("Alasan tindakan admin maksimal 300 karakter.")
        return bersih

    @staticmethod
    def _pastikan_penanggung_jawab(antrian: Queue, user_id: int | None) -> None:
        """Tolak sesi lama setelah admin mengalihkan sebuah pelayanan."""
        if (
            antrian.served_by_user_id is not None
            and antrian.served_by_user_id != user_id
        ):
            nama = antrian.served_by.full_name if antrian.served_by else "petugas lain"
            raise BusinessRuleError(
                f"Antrian {antrian.queue_number} telah dialihkan kepada {nama}. "
                "Muat ulang halaman pelayanan."
            )

    @staticmethod
    def _ambil(
        repo: QueueRepository, queue_id: int, *, for_update: bool = False
    ) -> Queue:
        antrian = repo.get_by_id(queue_id, for_update=for_update)
        if antrian is None:
            raise NotFoundError("Antrian tidak ditemukan.")
        return antrian

    @staticmethod
    def _pastikan_loket_aktif(
        session, counter_id: int, branch_id: int, *, kunci: bool = False
    ) -> Counter:
        loket = CounterRepository(session).get_by_id(
            counter_id, for_update=kunci
        )
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
            # Dikunci: nomor dilewati dapat dipanggil kembali loket lain pada
            # saat yang sama, dan perubahan ini tidak boleh menimpanya.
            antrian = self._ambil(repo, queue_id, for_update=True)
            if antrian.status is QueueStatus.SKIPPED:
                # Nomor dilewati tidak lagi memegang loket mana pun dan boleh
                # dipanggil kembali oleh loket mana saja; menutupnya juga.
                if antrian.branch_id != sesi.branch_id:
                    raise NotFoundError("Antrian tidak ditemukan.")
            else:
                self._pastikan_penanggung_jawab(antrian, sesi.user_id)

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
