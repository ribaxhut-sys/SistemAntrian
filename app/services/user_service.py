"""
Administrasi user.

Dipisahkan dari AuthService dengan sengaja. AuthService mengurus identitas
pemakai yang sedang berjalan — login, sesi, dan mengganti kata sandi
sendiri. Modul ini mengurus user LAIN, dan seluruhnya menuntut hak
USER_MANAGE yang hanya dimiliki ADMIN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.database import session_scope
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.logger import get_logger
from app.core.security import hash_password, validate_password_strength
from app.models import AuditAction, RecordStatus, User, UserRole
from app.repositories.master_repository import CounterRepository
from app.repositories.user_repository import UserRepository, normalize_username
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission

logger = get_logger("user")


@dataclass(frozen=True)
class UserInfo:
    """Data user yang aman dibawa ke UI. Tidak pernah memuat hash kata sandi."""

    id: int
    branch_id: int
    username: str
    full_name: str
    role: UserRole
    status: RecordStatus
    last_login_at: datetime | None
    must_change_password: bool
    #: Loket yang langsung terpilih saat petugas ini masuk. Kosong berarti
    #: belum ditetapkan — peran selain CRO memang tidak duduk di loket.
    default_counter_id: int | None = None

    @property
    def is_active(self) -> bool:
        return self.status is RecordStatus.ACTIVE


def _normalkan_peran(role: UserRole | str) -> UserRole:
    """
    QComboBox di PySide sering menyimpan str Enum sebagai string biasa.

    Tanpa langkah ini, pemanggilan `role.value` melempar AttributeError
    ('str' tidak punya .value) dan petugas hanya melihat pesan “tidak terduga”.
    """
    if isinstance(role, UserRole):
        return role
    try:
        return UserRole(role)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Peran tidak dikenali.") from exc


def _loket_sah(session, counter_id: int | None, branch_id: int) -> int | None:
    """
    Pastikan loket bawaan benar-benar ada dan sekantor dengan akunnya.

    Loket dari cabang lain ditolak, bukan diam-diam dikosongkan: itu selalu
    salah pilih, dan petugas yang loket bawaannya hilang tanpa kabar akan
    mengira pengaturannya tidak tersimpan.
    """
    if counter_id is None:
        return None

    loket = CounterRepository(session).get_by_id(counter_id)
    if loket is None or loket.branch_id != branch_id:
        raise NotFoundError("Loket tidak ditemukan.")
    return loket.id


def _tolak_peran_kios(role: UserRole) -> None:
    """KIOSK bukan akun. Menyimpannya di app_user hanya menambah kredensial di mesin publik."""
    if role == UserRole.KIOSK:
        raise ValidationError(
            "Peran kios tidak dapat diberikan kepada akun. "
            "Mesin kios berjalan tanpa login."
        )


def _as_info(row: User) -> UserInfo:
    return UserInfo(
        id=row.id,
        branch_id=row.branch_id,
        username=row.username,
        full_name=row.full_name,
        role=row.role,
        status=row.status,
        last_login_at=row.last_login_at,
        must_change_password=row.must_change_password,
        default_counter_id=row.default_counter_id,
    )


class UserService:
    """Pembuatan dan pengelolaan akun petugas."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    # -----------------------------------------------------------------
    # Pembacaan
    # -----------------------------------------------------------------

    def list_users(self, *, only_active: bool = False) -> list[UserInfo]:
        self.auth.require_permission(Permission.USER_MANAGE)
        with session_scope() as session:
            return [
                _as_info(u)
                for u in UserRepository(session).list_all(only_active=only_active)
            ]

    def get_user(self, user_id: int) -> UserInfo:
        self.auth.require_permission(Permission.USER_MANAGE)
        with session_scope() as session:
            row = UserRepository(session).get_by_id(user_id)
            if row is None:
                raise NotFoundError("Akun tidak ditemukan.")
            return _as_info(row)

    # -----------------------------------------------------------------
    # Perubahan
    # -----------------------------------------------------------------

    def create_user(
        self,
        *,
        username: str,
        full_name: str,
        password: str,
        role: UserRole | str,
        branch_id: int | None = None,
        must_change_password: bool = True,
        default_counter_id: int | None = None,
    ) -> int:
        """
        Buat akun petugas baru.

        Kata sandi ditentukan admin, dan secara bawaan petugas diwajibkan
        menggantinya saat login pertama supaya admin tidak ikut mengetahui
        kata sandi petugas selamanya.
        """
        sesi = self.auth.require_permission(Permission.USER_MANAGE)
        peran = _normalkan_peran(role)
        _tolak_peran_kios(peran)

        nama = normalize_username(username)
        if not nama:
            raise ValidationError("Nama pengguna tidak boleh kosong.")
        if len(nama) > 50:
            raise ValidationError("Nama pengguna maksimal 50 karakter.")
        lengkap = (full_name or "").strip()
        if not lengkap:
            raise ValidationError("Nama lengkap tidak boleh kosong.")
        validate_password_strength(password)

        with session_scope() as session:
            repo = UserRepository(session)
            if repo.exists_username(nama):
                raise ValidationError(
                    f"Nama pengguna {nama!r} sudah dipakai. Gunakan nama lain."
                )

            cabang = branch_id or sesi.branch_id
            user = repo.add(
                User(
                    branch_id=cabang,
                    username=nama,
                    full_name=lengkap,
                    password_hash=hash_password(password),
                    role=peran,
                    status=RecordStatus.ACTIVE,
                    must_change_password=must_change_password,
                    default_counter_id=_loket_sah(session, default_counter_id, cabang),
                )
            )
            audit_service.record(
                session,
                AuditAction.CREATE_USER,
                user_id=sesi.user_id,
                entity_type="app_user",
                entity_id=user.id,
                username=nama,
                role=peran.value,
            )
            logger.info("User baru dibuat: %s (%s)", nama, peran.value)
            return user.id

    def update_user(
        self,
        user_id: int,
        *,
        full_name: str,
        role: UserRole | str,
        default_counter_id: int | None = None,
    ) -> UserInfo:
        """
        Ubah nama lengkap, peran, dan loket bawaan.

        Admin tidak dapat mengubah perannya sendiri. Tanpa larangan ini,
        satu klik keliru bisa membuat tidak ada lagi ADMIN di sistem dan
        aplikasi tidak dapat dikelola sama sekali.

        `default_counter_id` None berarti akun ini tidak diikat ke loket
        mana pun — keadaan yang benar untuk peran selain CRO.
        """
        sesi = self.auth.require_permission(Permission.USER_MANAGE)
        peran = _normalkan_peran(role)
        _tolak_peran_kios(peran)
        lengkap = (full_name or "").strip()
        if not lengkap:
            raise ValidationError("Nama lengkap tidak boleh kosong.")

        with session_scope() as session:
            repo = UserRepository(session)
            user = repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError("Akun tidak ditemukan.")

            if user.id == sesi.user_id and peran != user.role:
                raise BusinessRuleError(
                    "Anda tidak dapat mengubah peran akun Anda sendiri."
                )

            if (
                user.role == UserRole.ADMIN
                and peran != UserRole.ADMIN
                and self._jumlah_admin_aktif(repo, kecuali=user.id) == 0
            ):
                raise BusinessRuleError(
                    "Ini satu-satunya akun ADMIN yang aktif. "
                    "Buat admin lain terlebih dahulu sebelum mengubah perannya."
                )

            user.full_name = lengkap
            user.role = peran
            user.default_counter_id = _loket_sah(
                session, default_counter_id, user.branch_id
            )

            audit_service.record(
                session,
                AuditAction.UPDATE_USER,
                user_id=sesi.user_id,
                entity_type="app_user",
                entity_id=user.id,
                username=user.username,
                role=peran.value,
                default_counter_id=user.default_counter_id,
            )
            logger.info("User %s diperbarui", user.username)
            return _as_info(user)

    def set_user_status(self, user_id: int, active: bool) -> UserInfo:
        """
        Aktifkan atau nonaktifkan akun.

        Akun tidak pernah dihapus. Menghapusnya akan memutus riwayat
        pemanggilan antrian dan survey yang menunjuk petugas tersebut.
        """
        sesi = self.auth.require_permission(Permission.USER_MANAGE)

        with session_scope() as session:
            repo = UserRepository(session)
            user = repo.get_by_id(user_id)
            if user is None:
                raise NotFoundError("Akun tidak ditemukan.")

            if not active:
                if user.id == sesi.user_id:
                    raise BusinessRuleError(
                        "Anda tidak dapat menonaktifkan akun Anda sendiri."
                    )
                if (
                    user.role is UserRole.ADMIN
                    and self._jumlah_admin_aktif(repo, kecuali=user.id) == 0
                ):
                    raise BusinessRuleError(
                        "Ini satu-satunya akun ADMIN yang aktif. "
                        "Aplikasi tidak akan dapat dikelola bila dinonaktifkan."
                    )

            user.status = RecordStatus.ACTIVE if active else RecordStatus.INACTIVE

            audit_service.record(
                session,
                AuditAction.UPDATE_USER,
                user_id=sesi.user_id,
                entity_type="app_user",
                entity_id=user.id,
                username=user.username,
                tindakan="aktifkan" if active else "nonaktifkan",
            )
            logger.info(
                "Akun %s %s",
                user.username,
                "diaktifkan" if active else "dinonaktifkan",
            )
            return _as_info(user)

    def reset_password(self, user_id: int, new_password: str) -> None:
        """
        Setel ulang kata sandi petugas yang lupa.

        Petugas WAJIB menggantinya saat login berikutnya, sehingga kata
        sandi sementara yang diketahui admin tidak terus dipakai.
        """
        sesi = self.auth.require_permission(Permission.USER_MANAGE)
        validate_password_strength(new_password)

        with session_scope() as session:
            user = UserRepository(session).get_by_id(user_id)
            if user is None:
                raise NotFoundError("Akun tidak ditemukan.")

            user.password_hash = hash_password(new_password)
            user.must_change_password = True

            audit_service.record(
                session,
                AuditAction.CHANGE_PASSWORD,
                user_id=sesi.user_id,
                entity_type="app_user",
                entity_id=user.id,
                username=user.username,
                tindakan="reset oleh admin",
            )
            logger.info("Kata sandi %s disetel ulang oleh %s", user.username, sesi.username)

    # -----------------------------------------------------------------

    @staticmethod
    def _jumlah_admin_aktif(repo: UserRepository, *, kecuali: int) -> int:
        return sum(
            1
            for u in repo.list_by_role(UserRole.ADMIN)
            if u.status is RecordStatus.ACTIVE and u.id != kecuali
        )
