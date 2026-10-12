"""
Domain model.

Seluruh model diimpor di sini agar metadata Base memuat semua tabel.
Alembic mengandalkan ini untuk mendeteksi perubahan skema.
"""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.branch import Branch
from app.models.counter import Counter
from app.models.enums import AuditAction, QueueStatus, RecordStatus, UserRole
from app.models.kiosk_device import KioskDevice, KioskPairingCode, KioskTicketRequest
from app.models.media_tayang import KioskMediaTayang
from app.models.queue import Queue, QueueSequence
from app.models.queue_call import QueueCall
from app.models.queue_note import QueueNote
from app.models.service_category import ServiceCategory
from app.models.setting import ApplicationSetting
from app.models.survey import RATING_LABELS, SatisfactionSurvey
from app.models.user import User

__all__ = [
    "RATING_LABELS",
    "ApplicationSetting",
    "AuditAction",
    "AuditLog",
    "Base",
    "Branch",
    "Counter",
    "KioskDevice",
    "KioskMediaTayang",
    "KioskPairingCode",
    "KioskTicketRequest",
    "Queue",
    "QueueCall",
    "QueueNote",
    "QueueSequence",
    "QueueStatus",
    "RecordStatus",
    "SatisfactionSurvey",
    "ServiceCategory",
    "User",
    "UserRole",
]
