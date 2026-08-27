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

from dataclasses import dataclass
from datetime import datetime

from app.core import clock
from app.core.database import session_scope
from app.core.errors import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from app.core.logger import get_logger
from app.core.security import hash_password, needs_rehash, validate_password_strength, verify_password
from app.models import AuditAction, RecordStatus, UserRole
from app.repositories.user_repository import UserRepository, normalize_username
from app.services import audit_service
from app.services.permissions import Permission, permissions_for

logger = get_logger("auth")


@dataclass(frozen=True)
class AuthSession:
    """Sesi yang sedang aktif. Objek nilai, bukan model database."""

    user_id: int
    username: str
    full_name: str
    role: UserRole
    branch_id: int
    login_at: datetime
    must_change_password: bool = False

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role)

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

        with session_scope() as session:
            repo = UserRepository(session)
            user = repo.get_by_username(nama)

            if user is None or not verify_password(password, user.password_hash):
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
                )

        if gagal is not None:
            user_id, alasan, pesan = gagal
            self._catat_login_gagal(user_id=user_id, username=nama, alasan=alasan)
            logger.warning("Login gagal untuk %r: %s", nama, alasan)
            raise AuthenticationError(pesan)

        logger.info("Login berhasil: %s (%s)", nama, self._session.role.value)
        return self._session

    def logout(self) -> None:
        """Keluar dari aplikasi. Aman dipanggil walau belum login."""
        if self._session is None:
            return

        sesi = self._session
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
        )
        logger.info("Kata sandi diganti: %s", sesi.username)


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
