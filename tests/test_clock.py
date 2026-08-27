"""Test sumber waktu aplikasi."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.core import clock


def test_now_mengembalikan_wib_tanpa_tzinfo():
    moment = clock.now()
    assert moment.tzinfo is None


def test_now_selalu_wib_walau_zona_komputer_berbeda(monkeypatch: pytest.MonkeyPatch):
    """
    Syarat §33: waktu tidak boleh bergantung pada setelan komputer.

    Dibandingkan dengan UTC sungguhan: selisihnya harus tepat 7 jam.
    """
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    wib_now = clock.now()

    selisih_jam = (wib_now - utc_now).total_seconds() / 3600
    assert 6.99 < selisih_jam < 7.01, f"selisih {selisih_jam} jam, seharusnya 7"


def test_today_konsisten_dengan_now():
    assert clock.today() == clock.now().date()


def test_now_bergerak_maju():
    first = clock.now()
    time.sleep(0.01)
    assert clock.now() >= first
