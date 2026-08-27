"""Survey kepuasan pelayanan."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import clock
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.branch import Branch
    from app.models.counter import Counter
    from app.models.queue import Queue
    from app.models.service_category import ServiceCategory
    from app.models.user import User

RATING_LABELS: dict[int, str] = {
    1: "Sangat Tidak Puas",
    2: "Tidak Puas",
    3: "Cukup Puas",
    4: "Puas",
    5: "Sangat Puas",
}


class SatisfactionSurvey(Base):
    """
    Penilaian pengunjung atas pelayanan yang diterimanya.

    Survey menempel pada satu antrian dan hanya boleh ada satu per antrian.

    Survey TIDAK mengubah status antrian. Antrian yang sudah COMPLETED tetap
    COMPLETED walaupun ratingnya 1. Rating mengukur kualitas pelayanan,
    bukan menentukan selesai atau tidaknya pelayanan.

    Kolom branch/counter/category/officer sengaja disalin ke sini agar
    laporan kepuasan tetap dapat difilter per loket, per jenis layanan, dan
    per petugas tanpa bergantung pada data antrian yang bisa saja berubah.
    """

    __tablename__ = "satisfaction_survey"
    __table_args__ = (
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # unique: satu antrian hanya boleh punya satu survey.
    queue_id: Mapped[int] = mapped_column(
        sa.ForeignKey("queue.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    branch_id: Mapped[int] = mapped_column(
        sa.ForeignKey("branch.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    counter_id: Mapped[int] = mapped_column(
        sa.ForeignKey("counter.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        sa.ForeignKey("service_category.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    officer_id: Mapped[int] = mapped_column(
        sa.ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    rating: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    feedback: Mapped[str | None] = mapped_column(sa.Text)
    submitted_at: Mapped[datetime] = mapped_column(
        sa.DateTime, nullable=False, default=clock.now, index=True
    )

    queue: Mapped[Queue] = relationship(back_populates="survey")
    branch: Mapped[Branch] = relationship()
    counter: Mapped[Counter] = relationship()
    category: Mapped[ServiceCategory] = relationship()
    officer: Mapped[User] = relationship()

    @property
    def rating_label(self) -> str:
        return RATING_LABELS.get(self.rating, "-")

    def __repr__(self) -> str:
        return f"<SatisfactionSurvey queue={self.queue_id} rating={self.rating}>"
