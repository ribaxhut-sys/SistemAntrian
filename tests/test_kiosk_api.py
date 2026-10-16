from dataclasses import replace
from datetime import datetime
import json
import time
import socket
import threading
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.core.errors import BusinessRuleError
from app.models.enums import QueueStatus
from app.services.apk_anjungan import VERSI_MINIMAL
from app.services.master_data_service import CategoryInfo
from app.services.queue_service import QueueInfo
from app.services.ticket_service import TicketData

VERSI_APK = {"X-App-Version-Code": str(VERSI_MINIMAL)}


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
        self.terbit: dict[tuple[str, str | None], QueueInfo] = {}

    def create_queue(
        self,
        category_id: int,
        *,
        perangkat="",
        request_id=None,
        kunci_jeda=None,
        prioritas_mandiri=False,
    ):
        self.prioritas_mandiri_terakhir = prioritas_mandiri
        if category_id != 10:
            raise BusinessRuleError("Layanan tidak tersedia.")
        if (perangkat, request_id) in self.terbit:
            return self.terbit[(perangkat, request_id)]
        self.created += 1
        info = self._info()
        self.terbit[(perangkat, request_id)] = info
        return info

    def _info(self):
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
                        queue_number="A-001",
                        category_name="Pajak Kendaraan",
                        label_status="DIPANGGIL",
                        jumlah_panggilan=2,
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

    def sisa_jeda_kios(self, perangkat=""):
        return 0

    def nomor_menunggu_untuk_layar(self):
        return ["A-002", "A-003"]

    def ringkasan_tiket(self, queue_info):
        return SimpleNamespace(sisa_antrian=2)


class _Settings:
    welcome_kind = "teks"
    suara_video = False

    def get_bool(self, key, default):
        return {
            "kiosk.suara_video": self.suara_video,
            "kiosk.tema_agustus": self.tema_agustus,
        }.get(key, default)
    posisi_loket = "otomatis"
    tema = "biru"
    judul = ""
    subjudul = ""
    tema_agustus = False
    daftar_putar = ""

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
            "kiosk.posisi_loket": self.posisi_loket,
            "kiosk.tema": self.tema,
            "kiosk.judul": self.judul,
            "kiosk.subjudul": self.subjudul,
            "kiosk.daftar_putar": self.daftar_putar,
        }
        return values.get(key, default)


class _Ticket:
    def susun(self, queue_info):
        return TicketData(
            queue_number=queue_info.queue_number,
            category_name=queue_info.category_name,
            office_name="Kantor Pelayanan",
            issued_at=queue_info.created_at,
            sisa_antrian=2,
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


@pytest.fixture(autouse=True)
def _tanpa_pin_di_database(monkeypatch):
    """API diuji dengan layanan palsu; PIN tidak boleh dibaca dari database sungguhan."""
    from app.services import pin_anjungan

    monkeypatch.setattr(pin_anjungan, "baca", lambda: None)


def test_api_returns_active_categories_and_ticket_lines():
    from app.kiosk_api import create_app

    client = TestClient(create_app(TOKEN, _Services()))
    headers = {"Authorization": f"Bearer {TOKEN}", **VERSI_APK}

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
    # Anjungan Android tidak menyebut jumlah yang menunggu, di layar maupun di struk.
    assert "ahead_count" not in ticket.json()
    assert not any("sisa antrian" in baris.lower() for baris in ticket.json()["ticket_lines"])
    assert not any(
        "sisa antrian" in row["text"].lower() for row in ticket.json()["ticket_layout"]["rows"]
    )
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


def test_api_display_hanya_berisi_keperluan_ambil_nomor(tmp_path, monkeypatch):
    from app.kiosk_api import create_app

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)

    client = TestClient(create_app(TOKEN, _Services()))
    response = client.get(
        "/v1/kiosk/display", headers={"Authorization": f"Bearer {TOKEN}"}
    )

    assert response.status_code == 200
    isi = response.json()
    assert isi.pop("timezone") == "Asia/Jakarta"
    assert abs(isi.pop("server_time_ms") - time.time() * 1000) < 5000
    assert len(isi.pop("categories_version")) == 16
    assert isi == {
        "title": "KANTOR PELAYANAN",
        "subtitle": "",
        "welcome_text": "Selamat datang",
        "welcome_kind": "teks",
        "welcome_slide_seconds": 10,
        "welcome_media": [],
        "welcome_media_files": [],
        "fullscreen_ad_idle_seconds": 60,
        "fullscreen_ad_loops": 2,
        "return_animation": True,
        "return_animation_lead_seconds": 2,
        "waiting_animation": True,
        "call_interrupts_ad": True,
        "registration_open": True,
        "priority_enabled": True,
        "settings_pin": {"enabled": False},
        "media_refresh": 0,
        "cooldown_remaining_seconds": 0,
        "waiting_queue_numbers": ["A-002", "A-003"],
        "counters": [
            {
                "name": "Loket 1",
                "queue_number": "A-001",
                "category": "Pajak Kendaraan",
                "call_count": 2,
                "status": "DIPANGGIL",
            },
            {
                "name": "Loket 2",
                "queue_number": None,
                "category": None,
                "call_count": 0,
                "status": "ISTIRAHAT",
            },
        ],
        "counter_position": "otomatis",
        "theme": "biru",
        "video_sound": False,
        "call_sound": False,
        "sound_pack_version": None,
        "app_min_version_code": VERSI_MINIMAL,
        "app_latest_version_code": None,
        "app_latest_version_name": None,
    }


@pytest.mark.parametrize(
    ("tersimpan", "dikirim"),
    [
        ("atas", "atas"),
        ("bawah", "bawah"),
        ("otomatis", "otomatis"),
        ("sembunyi", "sembunyi"),
        ("ngawur", "otomatis"),
    ],
)
def test_display_sends_counter_position(tersimpan, dikirim):
    from app.kiosk_api import create_app

    services = _Services()
    services.settings.posisi_loket = tersimpan
    client = TestClient(create_app(TOKEN, services))
    isi = client.get(
        "/v1/kiosk/display", headers={"Authorization": f"Bearer {TOKEN}"}
    ).json()

    assert isi["counter_position"] == dikirim


def test_display_memakai_judul_anjungan_sendiri():
    from app.kiosk_api import create_app

    services = _Services()
    services.settings.judul = "  Selamat datang di Bapenda  "
    services.settings.subjudul = " UPPRD Menteng · 08.00–15.00 "
    client = TestClient(create_app(TOKEN, services))
    isi = client.get(
        "/v1/kiosk/display", headers={"Authorization": f"Bearer {TOKEN}"}
    ).json()

    assert isi["title"] == "Selamat datang di Bapenda"
    assert isi["subtitle"] == "UPPRD Menteng · 08.00–15.00"


@pytest.mark.parametrize(
    ("tersimpan", "agustus", "bulan", "dikirim"),
    [
        ("gelap", False, 10, "gelap"),
        ("ngawur", False, 10, "biru"),
        ("hijau", True, 10, "hijau"),
        ("hijau", True, 8, "merah_putih"),
        ("hijau", False, 8, "hijau"),
    ],
)
def test_display_sends_theme(monkeypatch, tersimpan, agustus, bulan, dikirim):
    from app.kiosk_api import create_app

    monkeypatch.setattr(
        "app.kiosk_api.clock.today", lambda: datetime(2026, bulan, 15).date()
    )
    services = _Services()
    services.settings.tema = tersimpan
    services.settings.tema_agustus = agustus
    client = TestClient(create_app(TOKEN, services))
    isi = client.get(
        "/v1/kiosk/display", headers={"Authorization": f"Bearer {TOKEN}"}
    ).json()

    assert isi["theme"] == dikirim


@pytest.mark.parametrize(
    ("daftar", "harapan"),
    [
        ("", ["a.jpg", "b.mp4", "c.mp4"]),
        ('["c.mp4", "a.jpg"]', ["c.mp4", "a.jpg"]),
        ("[]", []),
    ],
)
def test_display_follows_media_playlist(tmp_path, monkeypatch, daftar, harapan):
    from app.kiosk_api import create_app

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    folder = tmp_path / "media" / "kiosk"
    folder.mkdir(parents=True)
    for nama in ("a.jpg", "b.mp4", "c.mp4"):
        (folder / nama).write_bytes(b"isi")
    services = _Services()
    services.settings.welcome_kind = "media"
    services.settings.daftar_putar = daftar
    client = TestClient(create_app(TOKEN, services))
    headers = {"Authorization": f"Bearer {TOKEN}", **VERSI_APK}

    isi = client.get("/v1/kiosk/display", headers=headers).json()

    assert isi["welcome_media"] == harapan
    assert [berkas["name"] for berkas in isi["welcome_media_files"]] == harapan
    for berkas in isi["welcome_media_files"]:
        info = (folder / berkas["name"]).stat()
        assert berkas["size"] == 3
        assert berkas["modified_ms"] == int(info.st_mtime * 1000)
    # Berkas yang tidak dicentang juga tidak dilayani.
    for nama in {"a.jpg", "b.mp4", "c.mp4"} - set(harapan):
        assert client.get(f"/v1/kiosk/media/{nama}", headers=headers).status_code == 404


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
    headers = {"Authorization": f"Bearer {TOKEN}", **VERSI_APK}

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
        headers={"Authorization": f"Bearer {TOKEN}", **VERSI_APK},
        json={"category_id": 99, "request_id": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Layanan tidak tersedia."


def test_repeated_request_id_does_not_issue_a_second_number():
    from app.kiosk_api import create_app

    services = _Services()
    client = TestClient(create_app(TOKEN, services))
    headers = {"Authorization": f"Bearer {TOKEN}", **VERSI_APK}
    body = {"category_id": 10, "request_id": str(uuid4())}

    first = client.post("/v1/kiosk/tickets", headers=headers, json=body)
    retry = client.post("/v1/kiosk/tickets", headers=headers, json=body)

    assert first.status_code == 200
    assert retry.json() == first.json()
    assert services.queue.created == 1


def test_apk_lama_tidak_dapat_menerbitkan_nomor():
    """APK tanpa versi atau di bawah minimal salah membaca jawaban API sekarang."""
    from app.kiosk_api import create_app

    client = TestClient(create_app(TOKEN, _Services()))
    body = {"category_id": 10, "request_id": str(uuid4())}
    for versi in ({}, {"X-App-Version-Code": str(VERSI_MINIMAL - 1)}):
        response = client.post(
            "/v1/kiosk/tickets",
            headers={"Authorization": f"Bearer {TOKEN}", **versi},
            json=body,
        )
        assert response.status_code == 426
        assert "diperbarui" in response.json()["detail"]


def test_apk_terbaru_diumumkan_dan_dapat_diunduh(tmp_path, monkeypatch):
    from app.kiosk_api import create_app

    folder = tmp_path / "apk"
    folder.mkdir()
    (folder / "anjungan.apk").write_bytes(b"PK-isi-apk")
    (folder / "anjungan.json").write_text(
        '{"version_code": 6, "version_name": "1.5"}', encoding="utf-8"
    )
    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    client = TestClient(create_app(TOKEN, _Services()))
    headers = {"Authorization": f"Bearer {TOKEN}"}

    isi = client.get("/v1/kiosk/display", headers=headers).json()
    assert isi["app_latest_version_code"] == 6
    assert isi["app_latest_version_name"] == "1.5"

    unduh = client.get("/v1/kiosk/app/apk", headers=headers)
    assert unduh.status_code == 200
    assert unduh.content == b"PK-isi-apk"
    assert unduh.headers["content-type"] == "application/vnd.android.package-archive"
    assert client.get("/v1/kiosk/app/apk").status_code == 401


def test_apk_belum_ada_dijawab_404(tmp_path, monkeypatch):
    from app.kiosk_api import create_app

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    client = TestClient(create_app(TOKEN, _Services()))

    response = client.get(
        "/v1/kiosk/app/apk", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 404


def _baris_hitam_pertama(raster) -> int:
    import base64

    data = base64.b64decode(raster["data"])
    per_baris = raster["width_px"] // 8
    for y in range(raster["height_px"]):
        if any(data[y * per_baris:(y + 1) * per_baris]):
            return y
    return -1


def test_ticket_raster_matches_windows_geometry():
    import base64

    from app.services.ticket_service import raster_tiket_anjungan

    data = TicketData(
        queue_number="A-001",
        category_name="Pajak Kendaraan",
        office_name="Kantor Pelayanan",
        issued_at=datetime(2026, 10, 6, 9, 0),
        header="BAPENDA DKI JAKARTA",
    )
    raster = raster_tiket_anjungan(data)

    assert raster is not None
    # 72 mm x 88 mm pada 8 titik/mm, 1 bit per titik.
    assert (raster["width_px"], raster["height_px"]) == (576, 704)
    assert len(base64.b64decode(raster["data"])) == 576 // 8 * 704
    atas = _baris_hitam_pertama(raster)
    assert atas >= 0

    # geser_atas_mm mengangkat isi tiket seperti di Windows.
    terangkat = raster_tiket_anjungan(replace(data, geser_atas_mm=2))
    assert _baris_hitam_pertama(terangkat) < atas

    # turun_anjungan_mm menurunkan isi tiket anjungan, 8 titik per mm.
    turun = raster_tiket_anjungan(replace(data, turun_anjungan_mm=4))
    assert _baris_hitam_pertama(turun) - atas == 32


def test_api_sends_ticket_raster_and_sample():
    from app.kiosk_api import create_app

    client = TestClient(create_app(TOKEN, _Services()))
    headers = {"Authorization": f"Bearer {TOKEN}", **VERSI_APK}

    ticket = client.post(
        "/v1/kiosk/tickets",
        headers=headers,
        json={"category_id": 10, "request_id": str(uuid4())},
    ).json()
    assert ticket["ticket_raster"]["width_px"] == 576

    contoh = client.get("/v1/kiosk/ticket-sample", headers=headers)
    assert contoh.status_code == 200
    assert contoh.json()["ticket_raster"]["height_px"] == 704
    assert any(
        row["text"] == "UJI-000" for row in contoh.json()["ticket_layout"]["rows"]
    )


class _MediaTayang:
    def __init__(self):
        self.laporan = []

    def catat(self, device_id, laporan):
        self.laporan.append((device_id, laporan))


def test_laporan_tayang_iklan_diteruskan_ke_pencatat():
    from app.kiosk_api import create_app

    services = _Services()
    services.media_tayang = _MediaTayang()
    client = TestClient(create_app(TOKEN, services))
    headers = {"Authorization": f"Bearer {TOKEN}", "X-Device-Id": "tablet-lobi-01"}

    response = client.post(
        "/v1/kiosk/media-report",
        headers=headers,
        json={
            "items": [
                {"name": "promo.jpg", "plays": 4},
                {
                    "name": "iklan.avi",
                    "failures": 2,
                    "error": "video what=1",
                    "last_failed": True,
                },
            ]
        },
    )

    assert response.status_code == 200
    ((device_id, laporan),) = services.media_tayang.laporan
    assert device_id == "tablet-lobi-01"
    assert [(b.nama, b.tayang, b.gagal, b.terakhir_gagal) for b in laporan] == [
        ("promo.jpg", 4, 0, False),
        ("iklan.avi", 0, 2, True),
    ]
    assert laporan[1].galat == "video what=1"


def test_laporan_tayang_butuh_token_dan_angka_wajar():
    from app.kiosk_api import create_app

    services = _Services()
    services.media_tayang = _MediaTayang()
    client = TestClient(create_app(TOKEN, services))
    laporan = {"items": [{"name": "a.jpg", "plays": 1}]}

    assert client.post("/v1/kiosk/media-report", json=laporan).status_code == 401
    assert client.post(
        "/v1/kiosk/media-report",
        headers={"Authorization": f"Bearer {TOKEN}", "X-Device-Id": "tablet-lobi-01"},
        json={"items": [{"name": "a.jpg", "plays": -1}]},
    ).status_code == 422
    assert services.media_tayang.laporan == []


def test_display_menyaring_jadwal_dan_mengirim_lama_tampil(tmp_path, monkeypatch):
    from datetime import date

    from app.kiosk_api import create_app

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    monkeypatch.setattr("app.kiosk_api.clock.today", lambda: date(2026, 11, 5))
    folder = tmp_path / "media" / "kiosk"
    folder.mkdir(parents=True)
    for nama in ("a.jpg", "promo.jpg", "lalu.jpg"):
        (folder / nama).write_bytes(b"isi")
    services = _Services()
    services.settings.welcome_kind = "media"
    services.settings.daftar_putar = json.dumps(
        [
            "a.jpg",
            {"nama": "promo.jpg", "mulai": "2026-11-01", "detik": 25},
            {"nama": "lalu.jpg", "selesai": "2026-10-31"},
        ]
    )
    client = TestClient(create_app(TOKEN, services))
    headers = {"Authorization": f"Bearer {TOKEN}", **VERSI_APK}

    isi = client.get("/v1/kiosk/display", headers=headers).json()

    assert isi["welcome_media"] == ["a.jpg", "promo.jpg"]
    assert [(b["name"], b["seconds"]) for b in isi["welcome_media_files"]] == [
        ("a.jpg", None),
        ("promo.jpg", 25),
    ]
    # Iklan yang jadwalnya lewat juga tidak dilayani lagi.
    assert client.get("/v1/kiosk/media/lalu.jpg", headers=headers).status_code == 404


def test_versi_layanan_berubah_bila_daftar_layanan_berubah(tmp_path, monkeypatch):
    """Tablet memuat ulang /categories hanya bila sidik ini berubah."""
    from app.kiosk_api import create_app

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    layanan = _Services()
    client = TestClient(create_app(TOKEN, layanan))
    headers = {"Authorization": f"Bearer {TOKEN}"}

    def versi() -> str:
        return client.get("/v1/kiosk/display", headers=headers).json()["categories_version"]

    awal = versi()
    assert versi() == awal

    asli = layanan.master.list_categories
    monkeypatch.setattr(
        layanan.master,
        "list_categories",
        lambda *, only_active: [replace(k, name="PKB") for k in asli(only_active=only_active)],
    )
    assert versi() != awal


def test_centang_prioritas_diteruskan_ke_service():
    from app.kiosk_api import create_app

    services = _Services()
    client = TestClient(create_app(TOKEN, services))
    headers = {"Authorization": f"Bearer {TOKEN}", **VERSI_APK}

    biasa = client.post(
        "/v1/kiosk/tickets",
        headers=headers,
        json={"category_id": 10, "request_id": str(uuid4())},
    )
    assert biasa.status_code == 200
    assert services.queue.prioritas_mandiri_terakhir is False

    prioritas = client.post(
        "/v1/kiosk/tickets",
        headers=headers,
        json={"category_id": 10, "request_id": str(uuid4()), "priority": True},
    )
    assert prioritas.status_code == 200
    assert services.queue.prioritas_mandiri_terakhir is True


def test_media_status_diterima_tanpa_mengganggu_tablet():
    from app.kiosk_api import create_app

    client = TestClient(create_app(TOKEN, _Services()))
    headers = {"Authorization": f"Bearer {TOKEN}", **VERSI_APK}

    ok = client.post(
        "/v1/kiosk/media-status",
        headers=headers,
        json={"total": 3, "copied": 2, "bytes": 1234},
    )
    salah = client.post(
        "/v1/kiosk/media-status", headers=headers, json={"total": -1, "copied": 0}
    )

    assert ok.status_code == 200 and ok.json() == {"status": "ok"}
    assert salah.status_code == 422


def test_pustaka_media_memuat_semua_berkas_bukan_hanya_daftar_putar(
    tmp_path, monkeypatch
):
    from app.kiosk_api import create_app

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    folder = tmp_path / "media" / "kiosk"
    folder.mkdir(parents=True)
    (folder / "satu.mp4").write_bytes(b"x" * 10)
    (folder / "dua.jpg").write_bytes(b"y" * 5)
    (folder / "catatan.txt").write_text("bukan media")
    client = TestClient(create_app(TOKEN, _Services()))
    headers = {"Authorization": f"Bearer {TOKEN}"}

    daftar = client.get("/v1/kiosk/media-library", headers=headers)

    assert daftar.status_code == 200
    nama = {item["name"]: item for item in daftar.json()}
    assert set(nama) == {"satu.mp4", "dua.jpg"}
    assert nama["satu.mp4"]["video"] is True and nama["dua.jpg"]["video"] is False
    assert nama["satu.mp4"]["size"] == 10
    unduh = client.get("/v1/kiosk/media-library/satu.mp4", headers=headers)
    assert unduh.status_code == 200 and unduh.content == b"x" * 10
    assert client.get("/v1/kiosk/media-library/catatan.txt", headers=headers).status_code == 404
    assert client.get("/v1/kiosk/media-library/%2e%2e%2fx.mp4", headers=headers).status_code in {
        404,
        307,
    }
    assert client.get("/v1/kiosk/media-library").status_code == 401


def test_display_menyebut_tempat_tampil_tiap_berkas(tmp_path, monkeypatch):
    """APK baru membedakan panel atas dan layar penuh; APK lama mengabaikannya."""
    from app.kiosk_api import create_app
    from app.services import daftar_putar

    monkeypatch.setattr("app.kiosk_api.base_dir", lambda: tmp_path)
    folder = tmp_path / "media" / "kiosk"
    folder.mkdir(parents=True)
    for nama in ("a.mp4", "b.mp4", "c.jpg"):
        (folder / nama).write_bytes(b"x")
    services = _Services()
    daftar = daftar_putar.tulis(
        [
            daftar_putar.Butir("a.mp4", tampil=daftar_putar.TAMPIL_PANEL),
            daftar_putar.Butir("b.mp4", tampil=daftar_putar.TAMPIL_PENUH),
            "c.jpg",
        ]
    )
    nilai_asli = services.settings.get

    def get(kunci, bawaan=None):
        if kunci == daftar_putar.KUNCI:
            return daftar
        if kunci == "kiosk.welcome_kind":
            return "media"
        return nilai_asli(kunci, bawaan)

    services.settings.get = get
    client = TestClient(create_app(TOKEN, services))

    isi = client.get(
        "/v1/kiosk/display", headers={"Authorization": f"Bearer {TOKEN}"}
    ).json()

    tampil = {item["name"]: item["show"] for item in isi["welcome_media_files"]}
    assert tampil == {"a.mp4": "panel", "b.mp4": "penuh", "c.jpg": "keduanya"}
    assert isi["welcome_media"] == ["a.mp4", "b.mp4", "c.jpg"]
