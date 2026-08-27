"""Histori pemanggilan antrian."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import clock
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.counter import Counter
    from app.models.queue import Queue
    from app.models.user import User


class QueueCall(Base):
    """
    Catatan satu kali pemanggilan.

    Baris di tabel ini TIDAK PERNAH ditimpa atau diubah. Pemanggilan ulang
    menghasilkan baris baru dengan call_number berikutnya, sehingga terlihat
    berapa kali sebuah nomor dipanggil sebelum dilayani atau dinyatakan
    tidak hadir.
    """

    __tablename__ = "queue_call"
    __table_args__ = (
        sa.UniqueConstraint("queue_id", "call_number", name="uq_queue_call_number"),
        sa.CheckConstraint("call_number > 0", name="call_number_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    queue_id: Mapped[int] = mapped_column(
        sa.ForeignKey("queue.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counter_id: Mapped[int] = mapped_column(
        sa.ForeignKey("counter.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    call_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    called_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=clock.now
    )

    queue: Mapped[Queue] = relationship(back_populates="calls")
    counter: Mapped[Counter] = relationship()
    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"<QueueCall queue={self.queue_id} #{self.call_number}>"
