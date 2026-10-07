from datetime import datetime
import json
import socket
import threading
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.core.errors import BusinessRuleError
from app.models.enums import QueueStatus
from app.services.master_data_service import CategoryInfo
from app.services.queue_service import QueueInfo
from app.services.ticket_service import TicketData


TOKEN = "bapendacro"


class _Master:
    def list_categories(self, *, only_active: bool):
        assert only_active
        return [
            CategoryInfo(
                id=10,
                branch_id=1,
                code="A",
                name="Pajak Kendaraan",
                prefix="A",
                display_order=1,
                status=None,
            )
        ]


class _Queue:
    def __init__(self):
        self.created = 0

    def create_queue(self, category_id: int):
        if category_id != 10:
            raise BusinessRuleError("Layanan tidak tersedia.")
        self.created += 1
        return QueueInfo(
            id=1,
            queue_number=f"A-{self.created:03}",
            sequence_number=self.created,
            queue_date=datetime(2026, 10, 6).date(),
            status=QueueStatus.WAITING,
            category_id=10,
            category_name="Pajak Kendaraan",
            category_prefix="A",
            counter_id=None,
            counter_name=None,
            served_by_id=None,
            served_by_name=None,
            created_at=datetime(2026, 10, 6, 9, 0),
            called_at=None,
            serving_at=None,
            completed_at=None,
        )

    def display_state(self, *, jumlah_berikutnya: int):
        assert jumlah_berikutnya == 0
        return SimpleNamespace(
            total_menunggu=2,
            loket=[
                SimpleNamespace(
                    counter_name="Loket 1",
                    antrian=SimpleNamespace(
                        queue_number="A-001", label_status="DIPANGGIL"
                    ),
                    istirahat=False,
                ),
                SimpleNamespace(
                    counter_name="Loket 2", antrian=None, istirahat=True
                ),
            ],
        )

    def pendaftaran_dibuka(self):
        return True

    def sisa_jeda_kios(self):
        return 0

    def ringkasan_tiket(self, queue_info):
        return SimpleNamespace(sisa_antrian=2)


class _Settings:
    welcome_kind = "teks"

    def get_int(self, key, default):
        return {
            "kiosk.cooldown_seconds": 10,
            "kiosk.welcome_slide_seconds": 10,
        }.get(key, default)

    def get(self, key, default=None):
        values = {
            "display.title": "KANTOR PELAYANAN",
            "kiosk.welcome_text": "Selamat datang",
            "kiosk.welcome_kind": self.welcome_kind,
            "kiosk.welcome_file": "",
        }
        return values.get(key, default)


class _Ticket:
    def susun(self, queue_info):
        return TicketData(
            queue_number=queue_info.queue_number,
            category_name=queue_info.category_name,
            office_name="Kantor Pelayanan",
            issued_at=queue_info.created_at,
        )


class _Services:
    def __init__(self):
        self.master = _Master()
        self.queue = _Queue()
        self.settings = _Settings()
        self.ticket = _Ticket()


def test_api_requires_bearer_token():
    from app.kiosk_api import create_app

    client = TestClient(create_app(TOKEN, _Services()))
    assert client.get("/v1/kiosk/categories").status_code == 401
    assert client.get(
        "/v1/kiosk/categories", headers={"Authorization": "Bearer wrong-token"}
    ).status_code == 401


def test_api_rejects_tokens_shorter_than_eight_characters():
    from app.kiosk_api import create_app

    with pytest.raises(ValueError, match="at least 8 characters"):
        create_app("short")


def test_udp_server_discovery_returns_api_port():
    from app.kiosk_api import (
        DISCOVERY_REQUEST,
        DISCOVERY_RESPONSE,
        _serve_discovery,
    )

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(1)
    stop = threading.Event()
    thread = threading.Thread(
        target=_serve_discovery, args=(server, 8765, stop), daemon=True
    )
    thread.start()
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(1)
    try:
        client.sendto(DISCOVERY_REQUEST, server.getsockname())
        payload, _ = client.recvfrom(1024)
        response = json.loads(payload)
        assert response == {
            "service": DISCOVERY_RESPONSE,
            "api_port": 8765,
        }
    finally:
        stop.set()
        server.close()
        client.close()
        thread.join(timeout=1)


def test_api_returns_active_categories_and_ticket_lines():
    from app.kiosk_api import create_app

    client = TestClient(create_app(TOKEN, _Services()))
    headers = {"Authorization": f"Bearer {TOKEN}"}

    categories = client.get("/v1/kiosk/categories", headers=headers)
    assert categories.status_code == 200
    assert categories.json()[0]["name"] == "Pajak Kendaraan"

    ticket = client.post(
        "/v1/kiosk/tickets",
        headers=headers,
        json={"category_id": 10, "request_id": str(uuid4())},
    )
    assert ticket.status_code == 200
    assert ticket.json()["queue_number"] == "A-001"
    assert ticket.json()["ahead_count"] == 2
    assert "NOMOR ANTRIAN" in ticket.json()["ticket_lines"]
    layout = ticket.json()["ticket_layout"]
    assert layout["width_mm"] == 72
    assert layout["height_mm"] == 88
    assert any(
        row["text"] == ticket.json()["queue_number"]
        and row["bold"]
        for row in layout["rows"]
    )
    assert ticket.json()["cooldown_seconds"] == 10


def test_api_returns_live_kiosk_display_state():
    from app.kiosk_api import create_app

    client = TestClient(create_app(TOKEN, _Services()))
    response = client.get(
        "/v1/kiosk/display", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "title": "KANTOR PELAYANAN",
        "welcome_text": "Selamat datang",
        "welcome_kind": "teks",
        "welcome_slide_seconds": 10,
        "welcome_media": [],
        "total_waiting": 2,
        "registration_open": True,
        "cooldown_remaining_seconds": 0,
        "counters": [
            {
                "name": "Loket 1",
                "queue_number": "A-001",
                "status": "DIPANGGIL",
            },
            {
                "name": "Loket 2",
                "queue_number": None,
                "status": "ISTIRAHAT",
            },
        ],
    }


def test_api_serves_only_configured_kiosk_media(tmp_path, monkeypatch):
    from app.kiosk_api import create_app

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    media_folder = tmp_path / "media" / "kiosk"
    media_folder.mkdir(parents=True)
    image = media_folder / "sambutan.jpg"
    image.write_bytes(b"jpeg test bytes")
    services = _Services()
    services.settings.welcome_kind = "media"
    client = TestClient(create_app(TOKEN, services))
    headers = {"Authorization": f"Bearer {TOKEN}"}

    media = client.get("/v1/kiosk/media/sambutan.jpg", headers=headers)
    assert media.status_code == 200
    assert media.content == b"jpeg test bytes"

    assert client.get(
        "/v1/kiosk/media/unknown.jpg", headers=headers
    ).status_code == 404
    assert client.get(
        "/v1/kiosk/media/../sambutan.jpg", headers=headers
    ).status_code in {404, 307}
    assert client.get("/v1/kiosk/media/unknown.jpg").status_code == 401


def test_api_returns_business_errors_without_creating_a_ticket():
    from app.kiosk_api import create_app

    client = TestClient(create_app(TOKEN, _Services()))
    response = client.post(
        "/v1/kiosk/tickets",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"category_id": 99, "request_id": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Layanan tidak tersedia."


def test_repeated_request_id_does_not_issue_a_second_number():
    from app.kiosk_api import create_app

    services = _Services()
    client = TestClient(create_app(TOKEN, services))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    body = {"category_id": 10, "request_id": str(uuid4())}

    first = client.post("/v1/kiosk/tickets", headers=headers, json=body)
    retry = client.post("/v1/kiosk/tickets", headers=headers, json=body)

    assert first.status_code == 200
    assert retry.json() == first.json()
    assert services.queue.created == 1
