"""
Pengaturan aplikasi yang tersimpan di database.

Berbeda dari app.core.config yang mengatur lokasi file dan hanya dapat
diubah lewat environment variable. Yang di sini dapat diubah petugas ADMIN
dari dalam aplikasi.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.core.database import session_scope
from app.core.errors import NotFoundError
from app.core.logger import get_logger
from app.models import ApplicationSetting, AuditAction
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission

logger = get_logger("settings")

#: Nilai cadangan bila sebuah pengaturan belum ada di database, misalnya
#: karena database dibuat sebelum pengaturan tersebut diperkenalkan.
BAWAAN: dict[str, str] = {
    "backup.auto_enabled": "true",
    "backup.retention_days": "30",
    "dashboard.refresh_seconds": "30",
    "display.title": "ANTRIAN PELAYANAN CRO",
    "display.next_count": "3",
    "display.sound_enabled": "true",
    "queue.max_call_attempts": "3",
    "survey.enabled": "true",
    "ticket.footer": "Silakan menunggu hingga nomor Anda dipanggil.",
    "ticket.printer": "pdf",
}

_BENAR = {"true", "1", "ya", "yes", "on"}


class SettingsService:
    """Pembacaan dan perubahan pengaturan aplikasi."""

    def __init__(self, auth: AuthService | None = None) -> None:
        self.auth = auth

    # -----------------------------------------------------------------
    # Pembacaan
    # -----------------------------------------------------------------
    #
    # Pembacaan sengaja tidak menuntut hak akses. Judul layar display dan
    # teks penutup tiket dibutuhkan oleh hampir semua peran, dan tidak ada
    # satu pun yang bersifat rahasia.

    def get(self, key: str, default: str | None = None) -> str:
        with session_scope() as session:
            baris = session.scalar(
                sa.select(ApplicationSetting).where(ApplicationSetting.key == key)
            )
            if baris is not None:
                return baris.value
        if default is not None:
            return default
        if key in BAWAAN:
            return BAWAAN[key]
        raise NotFoundError(f"Pengaturan {key!r} tidak dikenal.")

    def get_int(self, key: str, default: int | None = None) -> int:
        """Angka yang rusak diperlakukan seperti tidak ada, bukan menggagalkan layar."""
        try:
            return int(self.get(key, None if default is None else str(default)))
        except (ValueError, NotFoundError):
            if default is not None:
                return default
            return int(BAWAAN.get(key, "0"))

    def get_bool(self, key: str, default: bool = False) -> bool:
        try:
            return self.get(key).strip().lower() in _BENAR
        except NotFoundError:
            return default

    def all(self) -> dict[str, str]:
        with session_scope() as session:
            tersimpan = {
                r.key: r.value for r in session.scalars(sa.select(ApplicationSetting))
            }
        return {**BAWAAN, **tersimpan}

    # -----------------------------------------------------------------
    # Perubahan
    # -----------------------------------------------------------------

    def set(self, key: str, value: str) -> None:
        """Ubah satu pengaturan. Hanya ADMIN yang berhak."""
        if self.auth is None:
            raise NotFoundError("Perubahan pengaturan memerlukan sesi pengguna.")
        sesi = self.auth.require_permission(Permission.CONFIG_MANAGE)

        with session_scope() as session:
            baris = session.scalar(
                sa.select(ApplicationSetting).where(ApplicationSetting.key == key)
            )
            if baris is None:
                baris = ApplicationSetting(key=key, value=value)
                session.add(baris)
            else:
                baris.value = value

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="application_setting",
                pengaturan=key,
                nilai=value,
            )
        logger.info("Pengaturan %s diubah", key)
