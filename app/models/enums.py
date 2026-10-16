"""Enumerasi domain."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """Peran pengguna. Otorisasi ditegakkan di service layer, bukan di UI."""

    ADMIN = "ADMIN"              # user, cabang, loket, jenis layanan, konfigurasi
    SUPERVISOR = "SUPERVISOR"    # monitoring, dashboard, laporan, survey
    REGISTRATION = "REGISTRATION"  # menerbitkan nomor antrian, cetak tiket
    CRO = "CRO"                  # memanggil dan melayani antrian
    DISPLAY = "DISPLAY"          # hanya layar antrian, tanpa fungsi administrasi

    # Mesin kios yang menghadap pengunjung: menampilkan papan nomor sekaligus
    # melayani pengambilan nomor sendiri. TIDAK ada akun dengan peran ini —
    # sesinya dibuat tanpa login, karena menyimpan kata sandi di komputer
    # publik yang tidak diawasi justru menciptakan kebocoran yang tidak perlu.
    KIOSK = "KIOSK"


class AlasanPrioritas(str, Enum):
    """Alasan sebuah nomor didahulukan. Nomor biasa tidak menyimpan apa pun."""

    LANSIA = "LANSIA"
    DISABILITAS = "DISABILITAS"
    IBU_HAMIL = "IBU_HAMIL"


LABEL_PRIORITAS: dict[str, str] = {
    AlasanPrioritas.LANSIA.value: "Lansia",
    AlasanPrioritas.DISABILITAS.value: "Disabilitas",
    AlasanPrioritas.IBU_HAMIL.value: "Ibu hamil",
}


class RecordStatus(str, Enum):
    """Status aktif/nonaktif untuk data master."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class QueueStatus(str, Enum):
    """
    Status antrian.

    Alur normal:
        WAITING -> CALLED -> SERVING -> COMPLETED

    Alur alternatif:
        CALLED  -> SKIPPED -> CALLED
        CALLED  -> NO_SHOW
        WAITING -> CANCELLED
        CALLED  -> CANCELLED
        SERVING -> PAUSED -> SERVING

    Validasi perpindahan status adalah tanggung jawab QueueService (Phase 4).
    """

    WAITING = "WAITING"
    CALLED = "CALLED"
    SKIPPED = "SKIPPED"
    SERVING = "SERVING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"

    @property
    def is_final(self) -> bool:
        """Status akhir tidak dapat berpindah ke status lain."""
        return self in _FINAL_STATUSES


_FINAL_STATUSES = frozenset(
    {QueueStatus.COMPLETED, QueueStatus.CANCELLED, QueueStatus.NO_SHOW}
)


class AuditAction(str, Enum):
    """Aktivitas yang wajib tercatat pada audit log."""

    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    CHANGE_PASSWORD = "CHANGE_PASSWORD"
    CREATE_USER = "CREATE_USER"
    UPDATE_USER = "UPDATE_USER"
    CREATE_QUEUE = "CREATE_QUEUE"
    CALL_QUEUE = "CALL_QUEUE"
    SKIP_QUEUE = "SKIP_QUEUE"
    START_SERVICE = "START_SERVICE"
    PAUSE_QUEUE = "PAUSE_QUEUE"
    RESUME_QUEUE = "RESUME_QUEUE"
    COMPLETE_QUEUE = "COMPLETE_QUEUE"
    NO_SHOW = "NO_SHOW"
    CANCEL_QUEUE = "CANCEL_QUEUE"
    REASSIGN_QUEUE = "REASSIGN_QUEUE"
    FORCE_CANCEL_QUEUE = "FORCE_CANCEL_QUEUE"
    CLOSE_DAY = "CLOSE_DAY"
    REOPEN_DAY = "REOPEN_DAY"
    #: Sapuan otomatis nomor sisa hari-hari sebelumnya. Sengaja BUKAN
    #: CLOSE_DAY: `buka_kembali_hari()` memulihkan Tutup Hari terakhir, dan
    #: memulihkan nomor kemarin ke hari ini tidak pernah benar.
    EXPIRE_QUEUE = "EXPIRE_QUEUE"
    SUBMIT_SURVEY = "SUBMIT_SURVEY"
    SAVE_NOTE = "SAVE_NOTE"
    DELETE_NOTE = "DELETE_NOTE"
    ANONYMIZE_NOTE = "ANONYMIZE_NOTE"
    BACKUP = "BACKUP"
    RESTORE = "RESTORE"
    CHANGE_CONFIGURATION = "CHANGE_CONFIGURATION"
    PAIR_DEVICE = "PAIR_DEVICE"
    RENAME_DEVICE = "RENAME_DEVICE"
    REVOKE_DEVICE = "REVOKE_DEVICE"
    DELETE_DEVICE = "DELETE_DEVICE"
    LOGIN_LOCKED = "LOGIN_LOCKED"
    RESET_ADMIN_KEY = "RESET_ADMIN_KEY"
    DELETE_USER = "DELETE_USER"
    ARCHIVE_USER = "ARCHIVE_USER"
