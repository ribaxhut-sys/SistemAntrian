"""
Autentikasi dan otorisasi.

Aplikasi ini berjalan lokal dan hanya dipakai satu petugas pada satu waktu
di satu komputer, sehingga sesi cukup disimpan di memori. Tidak ada token,
tidak ada cookie, dan tidak ada yang ditulis ke disk. Menutup aplikasi
otomatis mengakhiri sesi.

Seluruh pemeriksaan hak akses berada di lapisan ini. UI boleh
menyembunyikan tombol, tetapi tidak boleh menjadi satu-satunya penjaga.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

import json

import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import (
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)
from app.core.logger import get_logger
from app.core.security import hash_password, needs_rehash, validate_password_strength, verify_password
from app.models import AuditAction, AuditLog, Counter, RecordStatus, UserRole
from app.repositories.master_repository import CounterRepository
from app.repositories.queue_repository import QueueRepository
from app.repositories.user_repository import UserRepository, normalize_username
from app.services import audit_service
from app.services.permissions import Permission, permissions_for

logger = get_logger("auth")

#: Jendela waktu penghitung percobaan masuk yang gagal, per nama pengguna.
JENDELA_LOGIN_GAGAL_MENIT = 15

#: Penundaan bertingkat: (gagal dalam jendela, menit ditunda), dari yang
#: terberat. Penundaan dihitung dari percobaan gagal terakhir, sehingga
#: setiap kegagalan sesudah ambang memulai penundaan baru. Pemulihan
#: admin dan masuk yang berhasil mengosongkan hitungan.
TINGKAT_PENUNDAAN: tuple[tuple[int, int], ...] = ((10, 15), (8, 5), (5, 1))

#: Percobaan gagal pertama yang memicu penundaan.
BATAS_LOGIN_GAGAL = TINGKAT_PENUNDAAN[-1][0]


def _menit_penundaan(jumlah_gagal: int) -> int:
    for ambang, menit in TINGKAT_PENUNDAAN:
        if jumlah_gagal >= ambang:
            return menit
    return 0


def _label_sisa(sisa: timedelta) -> str:
    """Sisa waktu untuk dibaca orang: "3 menit 20 detik" atau "45 detik"."""
    detik = max(1, int(sisa.total_seconds() + 0.999))
    menit, rest = divmod(detik, 60)
    if menit and rest:
        return f"{menit} menit {rest} detik"
    if menit:
        return f"{menit} menit"
    return f"{rest} detik"


@dataclass(frozen=True)
class AuthSession:
    """Sesi yang sedang aktif. Objek nilai, bukan model database."""

    #: None hanya untuk sesi kios, yang memang tidak mewakili orang tertentu.
    #: Audit log menyimpannya sebagai NULL — kolomnya memang dirancang boleh
    #: kosong untuk aktivitas yang tidak berpemilik.
    user_id: int | None
    username: str
    full_name: str
    role: UserRole
    branch_id: int
    login_at: datetime
    must_change_password: bool = False
    #: Loket bawaan petugas ini, dipakai layar pelayanan untuk memilih
    #: loketnya sendiri begitu masuk. Kosong berarti belum ditetapkan —
    #: petugas memilih sendiri seperti sebelumnya.
    default_counter_id: int | None = None

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role)

    @property
    def kios(self) -> bool:
        """Sesi mesin kios yang berjalan tanpa login."""
        return self.role is UserRole.KIOSK

    def __repr__(self) -> str:
        return f"<AuthSession {self.username} {self.role.value}>"


class AuthService:
    """Login, logout, dan pemeriksaan hak akses."""

    def __init__(self) -> None:
        self._session: AuthSession | None = None

    # -----------------------------------------------------------------
    # Keadaan sesi
    # -----------------------------------------------------------------

    @property
    def current_session(self) -> AuthSession | None:
        return self._session

    @property
    def is_authenticated(self) -> bool:
        return self._session is not None

    def require_session(self) -> AuthSession:
        if self._session is None:
            raise AuthenticationError("Anda belum masuk. Silakan login terlebih dahulu.")
        return self._session

    # -----------------------------------------------------------------
    # Login / logout
    # -----------------------------------------------------------------

    def _catat_login_gagal(
        self, *, user_id: int | None, username: str, alasan: str
    ) -> None:
        """
        Catat percobaan login yang gagal pada transaksi tersendiri.

        Harus terpisah dari transaksi pemeriksaan kredensial. Bila dicatat
        di dalam transaksi yang sama, exception yang menyusul akan
        me-rollback catatannya, dan justru percobaan masuk yang gagal —
        yang paling perlu terlihat — tidak akan pernah tersimpan.
        """
        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.LOGIN_FAILED,
                user_id=user_id,
                entity_type="app_user",
                entity_id=user_id,
                username=username,
                alasan=alasan,
            )

    def login(self, username: str, password: str) -> AuthSession:
        """
        Masuk ke aplikasi.

        Pesan kegagalan sengaja dibuat sama untuk nama pengguna yang tidak
        ada maupun kata sandi yang salah, supaya tidak ada cara menebak
        nama pengguna mana yang terdaftar.
        """
        nama = normalize_username(username)
        gagal: tuple[int | None, str, str] | None = None
        ditunda: timedelta | None = None

        with session_scope() as session:
            repo = UserRepository(session)
            user = repo.get_by_username(nama)

            # Dihitung per NAMA yang diketik, bukan per akun yang ada: nama
            # yang tidak terdaftar ditunda dengan cara dan pesan yang sama,
            # sehingga penundaan tidak membocorkan akun mana yang ada.
            sisa_tunda = self._sisa_penundaan(
                session, nama, user.id if user is not None else None
            )
            if sisa_tunda is not None:
                # Ditolak sebelum kata sandi diperiksa dan TIDAK dicatat
                # sebagai percobaan gagal baru: jendela penundaan yang
                # diperpanjang oleh penolakannya sendiri akan mengunci
                # pemilik akun selama penyerang terus mencoba.
                ditunda = sisa_tunda
            elif user is None or not verify_password(password, user.password_hash):
                gagal = (
                    user.id if user else None,
                    "kredensial salah",
                    AuthenticationError.default_message,
                )
            elif user.status is not RecordStatus.ACTIVE:
                gagal = (
                    user.id,
                    "akun nonaktif",
                    "Akun Anda tidak aktif. Hubungi administrator.",
                )
            else:
                # Perkuat hash secara diam-diam bila parameternya sudah lama.
                if needs_rehash(user.password_hash):
                    user.password_hash = hash_password(password)
                    logger.info("Hash kata sandi %r diperbarui", nama)

                user.last_login_at = clock.now()

                audit_service.record(
                    session,
                    AuditAction.LOGIN,
                    user_id=user.id,
                    entity_type="app_user",
                    entity_id=user.id,
                    role=user.role.value,
                )

                self._session = AuthSession(
                    user_id=user.id,
                    username=user.username,
                    full_name=user.full_name,
                    role=user.role,
                    branch_id=user.branch_id,
                    login_at=clock.now(),
                    must_change_password=user.must_change_password,
                    default_counter_id=user.default_counter_id,
                )

        if ditunda is not None:
            logger.warning("Login %r ditunda: terlalu banyak percobaan gagal", nama)
            raise AuthenticationError(
                "Terlalu banyak percobaan masuk yang gagal. Coba lagi dalam "
                f"{_label_sisa(ditunda)}."
            )

        if gagal is not None:
            user_id, alasan, pesan = gagal
            self._catat_login_gagal(user_id=user_id, username=nama, alasan=alasan)
            pesan = self._beri_tahu_bila_terkunci(user_id, nama, pesan)
            logger.warning("Login gagal untuk %r: %s", nama, alasan)
            raise AuthenticationError(pesan)

        logger.info("Login berhasil: %s (%s)", nama, self._session.role.value)
        return self._session

    @staticmethod
    def _sisa_penundaan(
        session, username: str, user_id: int | None = None
    ) -> timedelta | None:
        """
        Sisa waktu penundaan untuk nama ini, atau None bila tidak ditunda.

        Ditunda bila ada BATAS_LOGIN_GAGAL percobaan gagal dengan nama itu
        dalam JENDELA_LOGIN_GAGAL_MENIT menit terakhir; lamanya mengikuti
        TINGKAT_PENUNDAAN dan dihitung dari percobaan gagal terakhir.
        Percobaan sebelum pemulihan admin (`RESET_ADMIN_KEY`) atau masuk
        berhasil terakhir tidak dihitung.

        Dihitung dari audit log, bukan memori: percobaan dari komputer
        loket mana pun ikut terhitung, dan tidak hilang saat aplikasi
        dibuka ulang. Pencocokan memakai nama yang tercatat di `meta`
        sehingga nama yang tidak terdaftar diperlakukan sama.
        """
        jendela = timedelta(minutes=JENDELA_LOGIN_GAGAL_MENIT)
        sekarang = clock.now()
        sejak = sekarang - jendela
        if user_id is not None:
            # Hitungan dimulai ulang oleh pemulihan admin dan oleh masuk
            # yang berhasil terakhir.
            titik_awal = session.scalar(
                sa.select(sa.func.max(AuditLog.created_at)).where(
                    AuditLog.action.in_(
                        (
                            AuditAction.RESET_ADMIN_KEY.value,
                            AuditAction.LOGIN.value,
                        )
                    ),
                    AuditLog.user_id == user_id,
                )
            )
            if titik_awal is not None and titik_awal > sejak:
                sejak = titik_awal
        penanda = f'"username": {json.dumps(username, ensure_ascii=False)}'
        waktu = list(
            session.scalars(
                sa.select(AuditLog.created_at)
                .where(
                    AuditLog.action == AuditAction.LOGIN_FAILED.value,
                    AuditLog.meta.contains(penanda, autoescape=True),
                    AuditLog.created_at > sejak,
                )
                .order_by(AuditLog.created_at.desc())
                .limit(TINGKAT_PENUNDAAN[0][0])
            )
        )
        menit = _menit_penundaan(len(waktu))
        if not menit:
            return None
        sisa = (waktu[0] + timedelta(minutes=menit)) - sekarang
        return sisa if sisa > timedelta(0) else None

    def _beri_tahu_bila_terkunci(
        self, user_id: int | None, username: str, pesan: str
    ) -> str:
        """
        Percobaan gagal yang baru saja mencapai batas: catat `LOGIN_LOCKED`
        (sekali, karena percobaan berikutnya ditolak tanpa dicatat) dan
        beri tahu pengguna bahwa akunnya ditunda.
        """
        with session_scope() as session:
            sisa = self._sisa_penundaan(session, username, user_id)
            if sisa is None:
                return pesan
            audit_service.record(
                session,
                AuditAction.LOGIN_LOCKED,
                user_id=user_id,
                entity_type="app_user",
                entity_id=user_id,
                username=username,
                menit=round(sisa.total_seconds() / 60, 1),
            )
        logger.warning("Akun %r ditunda %s", username, _label_sisa(sisa))
        return (
            "Kata sandi salah. Karena terlalu banyak percobaan, akun ditunda "
            f"{_label_sisa(sisa)}."
        )

    def verifikasi_kata_sandi(self, password: str) -> bool:
        """
        Benar bila `password` milik akun yang sedang masuk.

        Untuk membuka kunci layar. Tidak mengubah sesi. Jawaban salah
        dicatat sebagai percobaan gagal dan ikut dihitung batas percobaan
        login, sehingga kunci layar tidak dapat ditebak tanpa batas.
        """
        sesi = self.require_session()
        if sesi.user_id is None:
            return False
        with session_scope() as session:
            user = UserRepository(session).get_by_id(sesi.user_id)
            if user is None:
                return False
            sisa = self._sisa_penundaan(session, sesi.username, user.id)
            if sisa is not None:
                raise AuthenticationError(
                    "Terlalu banyak percobaan yang gagal. Coba lagi dalam "
                    f"{_label_sisa(sisa)}."
                )
            sah = verify_password(password, user.password_hash)
        if not sah:
            self._catat_login_gagal(
                user_id=sesi.user_id, username=sesi.username, alasan="kunci layar"
            )
        return sah

    def logout(self) -> None:
        """Keluar dari aplikasi. Aman dipanggil walau belum login."""
        if self._session is None:
            return

        sesi = self._session
        if sesi.user_id is not None:
            try:
                self._lepas_hadir_loket(sesi.user_id)
            except Exception:
                # Logout tidak boleh gagal karena ini; tanda hadir yang
                # tertinggal basi sendiri dalam BATAS_HADIR_PETUGAS_DETIK.
                logger.warning("Tanda hadir %s tidak terhapus", sesi.username, exc_info=True)
        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.LOGOUT,
                user_id=sesi.user_id,
                entity_type="app_user",
                entity_id=sesi.user_id,
            )
        self._session = None
        logger.info("Logout: %s", sesi.username)

    # -----------------------------------------------------------------
    # Sesi mesin publik (tanpa login)
    # -----------------------------------------------------------------

    def mulai_sesi_kios(self) -> AuthSession:
        """
        Buka sesi mesin kios tanpa login.

        Mesin ini adalah anjungan ambil nomor: pengunjung memilih jenis
        layanan dan mencetak tiketnya sendiri.

        Komputer kios menghadap publik dan tidak diawasi. Menyimpan kata
        sandi petugas di mesin seperti itu — atau menempelkannya di bawah
        keyboard agar petugas pagi bisa masuk — justru menciptakan kebocoran
        yang tidak perlu. Kios hanya menampilkan papan nomor dan menerbitkan
        nomor, keduanya hal yang memang dikerjakan pengunjung sendiri.

        Pembatasan sesungguhnya ada pada dua lapis: hak akses peran KIOSK di
        sini, dan hak user PostgreSQL mesin itu di database. Lapis kedua
        yang membuat mesin publik tidak dapat membaca tabel app_user sama
        sekali.
        """
        cabang = self._cabang_pertama()
        sesi = AuthSession(
            user_id=None,
            username="kios",
            full_name="Anjungan Ambil Nomor",
            role=UserRole.KIOSK,
            branch_id=cabang,
            login_at=clock.now(),
        )
        self._session = sesi
        logger.info("Sesi anjungan dimulai untuk cabang %s", cabang)
        return sesi

    def mulai_sesi_layar(self) -> AuthSession:
        """
        Buka sesi layar antrian ruang tunggu tanpa login.

        Televisi ruang tunggu berdiri di tempat yang sama publiknya dengan
        anjungan, dan alasan untuk tidak menyimpan kata sandi di sana persis
        sama. Sebelumnya layar itu hanya dapat dibuka lewat akun berperan
        DISPLAY, sehingga setiap mati listrik meninggalkan papan kosong
        sampai ada yang datang mengetikkan sandi — dan sandi yang harus
        diketik setiap pagi di ruang tunggu berakhir tertempel di bawah
        keyboard.

        Kewenangannya paling sempit di seluruh sistem: peran DISPLAY hanya
        boleh MELIHAT papan. Ia tidak dapat menerbitkan nomor sekalipun,
        berbeda dari anjungan.
        """
        cabang = self._cabang_pertama()
        sesi = AuthSession(
            user_id=None,
            username="layar",
            full_name="Layar Antrian",
            role=UserRole.DISPLAY,
            branch_id=cabang,
            login_at=clock.now(),
        )
        self._session = sesi
        logger.info("Sesi layar antrian dimulai untuk cabang %s", cabang)
        return sesi

    def mulai_sesi_pengembang(self) -> AuthSession:
        """Masuk sebagai administrator tanpa nama dan sandi, hanya dari source."""
        return self._mulai_sesi_uji(UserRole.ADMIN)

    def mulai_sesi_petugas(self) -> AuthSession:
        """Masuk sebagai petugas CRO tanpa nama dan sandi, hanya dari source."""
        return self._mulai_sesi_uji(UserRole.CRO)

    def _mulai_sesi_uji(self, peran: UserRole) -> AuthSession:
        """
        Pintasan uji tampilan: jangan minta nama/sandi, dan jangan paksa
        ganti sandi bawaan. Pada .exe ditolak, karena komputer petugas
        tidak boleh terbuka tanpa kunci.
        """
        from app.core.config import lewati_login_pengembang
        from app.core.seed import DEFAULT_ADMIN_USERNAME

        if not lewati_login_pengembang():
            raise BusinessRuleError(
                "Pintasan masuk pengembang hanya untuk uji dari source."
            )

        with session_scope() as session:
            repo = UserRepository(session)
            user = None
            if peran is UserRole.ADMIN:
                user = repo.get_by_username(DEFAULT_ADMIN_USERNAME)
            if user is None:
                kandidat = [
                    u
                    for u in repo.list_by_role(peran)
                    if u.status is RecordStatus.ACTIVE
                ]
                terikat = [u for u in kandidat if u.default_counter_id is not None]
                user = (terikat or kandidat or [None])[0]
            if user is None or user.status is not RecordStatus.ACTIVE:
                if peran is UserRole.ADMIN:
                    raise NotFoundError(
                        "Akun administrator belum ada. Jalankan aplikasi sekali "
                        "terlebih dahulu agar data awal terbentuk."
                    )
                raise NotFoundError(
                    "Akun petugas CRO belum ada. Buat akun petugas di Data Master "
                    "sebelum membuka layar petugas."
                )

            user.last_login_at = clock.now()
            audit_service.record(
                session,
                AuditAction.LOGIN,
                user_id=user.id,
                entity_type="app_user",
                entity_id=user.id,
                role=user.role.value,
                alasan="pintasan pengembang tanpa sandi",
            )
            self._session = AuthSession(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                branch_id=user.branch_id,
                login_at=clock.now(),
                must_change_password=False,
                default_counter_id=user.default_counter_id,
            )

        logger.warning(
            "Masuk sebagai %s tanpa sandi (pintasan pengembang)",
            self._session.username,
        )
        return self._session

    @staticmethod
    def _cabang_pertama() -> int:
        """
        Cabang yang dilayani mesin ini.

        Sistem ini melayani satu kantor, sehingga cabangnya tunggal dan
        tidak perlu dipilih petugas saat kios dinyalakan.
        """
        import sqlalchemy as sa

        from app.models import Branch

        with session_scope() as session:
            cabang = session.scalar(sa.select(Branch.id).order_by(Branch.id))
        if cabang is None:
            raise NotFoundError(
                "Data cabang belum ada. Jalankan aplikasi sebagai petugas "
                "terlebih dahulu agar data awal terbentuk."
            )
        return cabang

    # -----------------------------------------------------------------
    # Hak akses
    # -----------------------------------------------------------------

    def has_permission(self, permission: Permission) -> bool:
        """
        True bila sesi saat ini berhak melakukan tindakan tersebut.

        User yang wajib mengganti kata sandi dianggap belum berhak apa pun
        sampai kata sandinya diganti.
        """
        if self._session is None or self._session.must_change_password:
            return False
        return permission in self._session.permissions

    def require_permission(self, permission: Permission) -> AuthSession:
        """Pastikan sesi berhak; bila tidak, hentikan dengan pesan yang jelas."""
        sesi = self.require_session()

        if sesi.must_change_password:
            raise AuthorizationError(
                "Kata sandi Anda harus diganti terlebih dahulu sebelum "
                "menggunakan aplikasi."
            )

        if permission not in sesi.permissions:
            logger.warning(
                "Akses ditolak: %s (%s) mencoba %s",
                sesi.username,
                sesi.role.value,
                permission.value,
            )
            raise AuthorizationError()

        return sesi

    # -----------------------------------------------------------------
    # Pengelolaan kata sandi dan user
    # -----------------------------------------------------------------

    def change_password(self, old_password: str, new_password: str) -> None:
        """
        Ganti kata sandi sendiri.

        Sengaja tidak memerlukan hak akses khusus: setiap user berhak
        mengganti kata sandinya sendiri, termasuk user yang sedang
        diwajibkan menggantinya.
        """
        sesi = self.require_session()
        validate_password_strength(new_password)

        if old_password == new_password:
            raise ValidationError("Kata sandi baru harus berbeda dari yang lama.")

        with session_scope() as session:
            user = UserRepository(session).get_by_id(sesi.user_id)
            if user is None:
                raise NotFoundError("Akun Anda tidak ditemukan.")

            if not verify_password(old_password, user.password_hash):
                logger.warning("Ganti kata sandi gagal untuk %s", sesi.username)
                raise AuthenticationError("Kata sandi lama salah.")

            user.password_hash = hash_password(new_password)
            user.must_change_password = False

            audit_service.record(
                session,
                AuditAction.CHANGE_PASSWORD,
                user_id=user.id,
                entity_type="app_user",
                entity_id=user.id,
            )

        # Sesi diperbarui agar kewajiban ganti kata sandi tidak menempel lagi.
        self._session = AuthSession(
            user_id=sesi.user_id,
            username=sesi.username,
            full_name=sesi.full_name,
            role=sesi.role,
            branch_id=sesi.branch_id,
            login_at=sesi.login_at,
            must_change_password=False,
            default_counter_id=sesi.default_counter_id,
        )
        logger.info("Kata sandi diganti: %s", sesi.username)

    def pindah_loket(self, counter_id: int | None) -> AuthSession:
        """
        Pindahkan petugas yang sedang masuk ke loket lain, dan ingat itu.

        Pindah meja terjadi tanpa rencana — petugas menggantikan rekannya,
        atau loketnya rusak — dan tidak masuk akal menunggu admin untuk hal
        sesederhana itu. Karena itu petugas boleh mengubah loketnya sendiri,
        dan pilihannya disimpan sebagai loket bawaan supaya besok tidak
        perlu diulang.

        Menyimpannya juga mencegah petugas harus memilih ulang setiap kali
        masuk. Layar pelayanan tidak pernah memilih loket pertama secara
        diam-diam ketika akun belum memiliki loket bawaan.
        """
        sesi = self.require_permission(Permission.QUEUE_CALL)
        if sesi.user_id is None:
            raise BusinessRuleError("Sesi kios tidak memiliki loket.")

        with session_scope() as session:
            user = UserRepository(session).get_by_id(sesi.user_id)
            if user is None:
                raise NotFoundError("Akun tidak ditemukan.")

            tujuan = None
            if counter_id is not None:
                tujuan = CounterRepository(session).get_by_id(counter_id)
                if tujuan is None or tujuan.branch_id != sesi.branch_id:
                    raise NotFoundError("Loket tidak ditemukan.")
                if tujuan.status is not RecordStatus.ACTIVE:
                    raise BusinessRuleError(
                        f"Loket {tujuan.name!r} sedang tidak aktif."
                    )

            loket_semula = user.default_counter_id
            if counter_id != loket_semula:
                antrean = QueueRepository(session)
                if loket_semula is not None:
                    sedang = antrean.sedang_ditangani_loket(
                        loket_semula, clock.today()
                    )
                    if (
                        sedang is not None
                        and sedang.served_by_user_id in (None, sesi.user_id)
                    ):
                        raise BusinessRuleError(
                            f"Selesaikan antrian {sedang.queue_number} di "
                            "loket saat ini sebelum berpindah."
                        )

                if counter_id is not None:
                    sedang = antrean.sedang_ditangani_loket(
                        counter_id, clock.today()
                    )
                    if (
                        sedang is not None
                        and sedang.served_by_user_id != sesi.user_id
                    ):
                        nama = tujuan.name if tujuan is not None else "tersebut"
                        raise BusinessRuleError(
                            f"Loket {nama!r} masih menangani antrian "
                            f"{sedang.queue_number}. Pilih loket lain."
                        )

            user.default_counter_id = counter_id
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="app_user",
                entity_id=sesi.user_id,
                tindakan="pindah loket",
                default_counter_id=counter_id,
            )

        self._session = replace(sesi, default_counter_id=counter_id)
        logger.info("Petugas %s pindah ke loket %s", sesi.username, counter_id)
        try:
            # Papan langsung mengikuti, tidak menunggu tanda hidup berikutnya.
            self.tanda_hadir_loket()
        except Exception:
            logger.warning("Tanda hadir sesudah pindah loket gagal", exc_info=True)
        return self._session

    # -----------------------------------------------------------------
    # Tanda hadir petugas di loket
    # -----------------------------------------------------------------

    def tanda_hadir_loket(self) -> int | None:
        """
        Catat bahwa petugas ini sedang login di loketnya; kembalikan loketnya.

        Dipanggil berkala oleh jendela petugas (MainWindow). Loket dibaca
        dari database, bukan dari sesi, supaya penugasan ulang oleh admin
        ikut terbawa; tanda di loket lain milik petugas yang sama dihapus.
        `updated_at` loket sengaja tidak disentuh: ini keadaan, bukan
        perubahan data master.
        """
        sesi = self.require_session()
        if sesi.user_id is None:
            return None
        with session_scope() as session:
            user = UserRepository(session).get_by_id(sesi.user_id)
            if user is None:
                return None
            loket_id = user.default_counter_id
            lepas = sa.update(Counter).where(Counter.petugas_user_id == sesi.user_id)
            if loket_id is not None:
                lepas = lepas.where(Counter.id != loket_id)
            session.execute(
                lepas.values(
                    petugas_user_id=None,
                    petugas_terlihat_pada=None,
                    updated_at=Counter.updated_at,
                )
            )
            if loket_id is not None:
                session.execute(
                    sa.update(Counter)
                    .where(Counter.id == loket_id)
                    .values(
                        petugas_user_id=sesi.user_id,
                        petugas_terlihat_pada=clock.now(),
                        updated_at=Counter.updated_at,
                    )
                )
        return loket_id

    @staticmethod
    def _lepas_hadir_loket(user_id: int) -> None:
        with session_scope() as session:
            session.execute(
                sa.update(Counter)
                .where(Counter.petugas_user_id == user_id)
                .values(
                    petugas_user_id=None,
                    petugas_terlihat_pada=None,
                    updated_at=Counter.updated_at,
                )
            )

    def sinkronkan_loket(self) -> AuthSession:
        """Segarkan loket sesi dari database tanpa mengubah penugasannya."""
        sesi = self.require_permission(Permission.QUEUE_CALL)
        if sesi.user_id is None:
            return sesi

        with session_scope() as session:
            user = UserRepository(session).get_by_id(sesi.user_id)
            if user is None:
                raise NotFoundError("Akun tidak ditemukan.")
            loket_terbaru = user.default_counter_id

        if loket_terbaru != sesi.default_counter_id:
            self._session = replace(sesi, default_counter_id=loket_terbaru)
            logger.info(
                "Loket sesi %s disinkronkan ke %s", sesi.username, loket_terbaru
            )
        return self.current_session


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """Sesi tunggal milik aplikasi."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


def reset_auth_service() -> None:
    """Buang sesi yang tersimpan. Dipakai test dan saat restore database."""
    global _auth_service
    _auth_service = None
