"""
Exception aplikasi.

Aturan §47: user tidak boleh melihat traceback, nama exception Python,
atau pesan error SQLite. Karena itu setiap exception di sini membawa
user_message, yaitu kalimat yang aman dan masuk akal untuk ditampilkan
di layar. Detail teknis tetap masuk log.
"""

from __future__ import annotations


class AppError(Exception):
    """Induk seluruh error yang sudah diperhitungkan aplikasi."""

    default_message = "Terjadi kesalahan. Silakan coba kembali."

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.user_message = message or self.default_message
        self.detail = detail
        super().__init__(self.user_message)


class ValidationError(AppError):
    """Input tidak memenuhi syarat."""

    default_message = "Data yang dimasukkan belum benar."


class AuthenticationError(AppError):
    """Identitas gagal dibuktikan."""

    default_message = "Nama pengguna atau kata sandi salah."


class AuthorizationError(AppError):
    """Identitas terbukti, tetapi tidak berhak melakukan tindakan ini."""

    default_message = "Anda tidak memiliki hak akses untuk tindakan ini."


class NotFoundError(AppError):
    """Data yang dicari tidak ada."""

    default_message = "Data tidak ditemukan."


class BusinessRuleError(AppError):
    """Tindakan melanggar aturan bisnis, misalnya perpindahan status ilegal."""

    default_message = "Tindakan ini tidak dapat dilakukan pada kondisi saat ini."
