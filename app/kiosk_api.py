"""LAN API for the Android ticket-taking kiosk."""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Annotated
from uuid import UUID

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.core.config import TIMEZONE, base_dir, get_config
from app.core.database import dispose_engine
from app.core.errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)
from app.core.logger import get_logger, setup_logging
from app.core.migrations import current_revision
from app.core.seed import seed_initial_data
from app.services.apk_anjungan import (
    TIPE_APK,
    VERSI_MINIMAL,
    VERSI_MINIMAL_LAYAR,
    folder_apk,
    info_apk,
)
from app.services.auth_service import AuthService
from app.services.master_data_service import MasterDataService
from app.services.paket_suara import folder_paket, info_paket, token_pengumuman
from app.services.queue_service import QueueService
from app.services.settings_service import SettingsService
from app.services.ticket_service import (
    NullTicketPrinter,
    TicketService,
    tata_letak_tiket_anjungan,
)

_MEDIA_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".gif",
    ".mp4",
    ".mkv",
    ".webm",
    ".avi",
}
_MEDIA_KINDS = {"media", "gambar", "video"}
MIN_TOKEN_LENGTH = 8
DISCOVERY_REQUEST = b"SISTEMANTRIAN_KIOSK_DISCOVER_V1"
DISCOVERY_RESPONSE = "SISTEMANTRIAN_KIOSK_SERVER_V1"
DISCOVERY_PORT = 8766

logger = get_logger("kiosk_api")
_bearer = HTTPBearer(auto_error=False)


def _serve_discovery(
    discovery_socket: socket.socket,
    api_port: int,
    stop_event: threading.Event,
) -> None:
    """Answer local UDP discovery broadcasts with the API TCP port."""
    while not stop_event.is_set():
        try:
            payload, address = discovery_socket.recvfrom(1024)
        except socket.timeout:
            continue
        except OSError:
            if not stop_event.is_set():
                logger.exception("Listener pencarian server anjungan berhenti")
            return
        if payload != DISCOVERY_REQUEST:
            continue
        response = json.dumps(
            {"service": DISCOVERY_RESPONSE, "api_port": api_port}
        ).encode("utf-8")
        try:
            discovery_socket.sendto(response, address)
        except OSError:
            if not stop_event.is_set():
                logger.exception("Jawaban pencarian server anjungan gagal dikirim")


class TicketRequest(BaseModel):
    category_id: int = Field(gt=0)
    request_id: UUID


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    device_id: str = Field(min_length=8, max_length=64)
    name: str = Field(default="", max_length=80)
    kind: str = Field(default="anjungan", max_length=20)


class PrinterReport(BaseModel):
    ok: bool
    message: str = Field(default="", max_length=200)


class PerangkatDb:
    """Penghubung API dengan tabel perangkat (app.services.device_service)."""

    def __getattr__(self, nama):
        from app.services import device_service

        return getattr(device_service, nama)


#: Tebakan kode pasang yang salah sebelum semua kode aktif dihanguskan.
BATAS_TEBAKAN_KODE = 10
SELANG_TEBAKAN_DETIK = 600
SELANG_TULIS_KONTAK_DETIK = 30


class KioskServices:
    def __init__(self) -> None:
        self.auth = AuthService()
        self.auth.mulai_sesi_kios()
        self.settings = SettingsService(self.auth)
        self.master = MasterDataService(self.auth)
        self.queue = QueueService(self.auth, self.settings)
        self.ticket = TicketService(
            NullTicketPrinter(), self.settings, self.master, self.queue
        )
        self.perangkat = PerangkatDb()


def create_app(token: str, services: KioskServices | None = None) -> FastAPI:
    """Build an API application that can issue tickets only for a kiosk session."""
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(
            f"ANTRIAN_KIOS_API_TOKEN must contain at least {MIN_TOKEN_LENGTH} characters."
        )

    services = services or KioskServices()
    ticket_lock = threading.Lock()
    ticket_responses: dict[UUID, dict] = {}
    app = FastAPI(
        title="Sistem Antrian CRO Kiosk API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Tanpa `perangkat` (test lama, atau API yang dijalankan tanpa database
    # perangkat) hanya token bersama yang dikenal.
    perangkat = getattr(services, "perangkat", None)
    kontak_terakhir: dict[str, float] = {}
    tebakan_salah: list[float] = []

    def tolak() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token anjungan tidak sah.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def catat_kontak(request: Request, device_id: str) -> None:
        sekarang = time.monotonic()
        if sekarang - kontak_terakhir.get(device_id, -1e9) < SELANG_TULIS_KONTAK_DETIK:
            return
        kontak_terakhir[device_id] = sekarang
        try:
            versi_kode = int(request.headers.get("x-app-version-code") or 0)
        except ValueError:
            versi_kode = 0
        try:
            perangkat.catat_kontak(
                device_id,
                nama=request.headers.get("x-device-name", ""),
                jenis=request.headers.get("x-device-kind", "anjungan"),
                alamat_ip=request.client.host if request.client else "",
                versi_nama=request.headers.get("x-app-version-name", ""),
                versi_kode=versi_kode,
            )
        except Exception:
            # Daftar perangkat adalah keterangan, bukan syarat pelayanan.
            logger.warning("Kontak perangkat %s gagal dicatat", device_id, exc_info=True)

    def require_token(
        request: Request,
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(_bearer)
        ],
    ) -> str:
        """
        Token perangkat (hasil pasang) atau token bersama lama.

        Mengembalikan device_id yang dipakai mencatat kontak; kosong bila
        perangkat tidak menyebutkannya.
        """
        if credentials is None:
            raise tolak()
        diberikan = credentials.credentials
        device_id = (request.headers.get("x-device-id") or "").strip()[:64]

        if perangkat is not None:
            pemilik = perangkat.perangkat_dari_token(diberikan)
            if pemilik is not None:
                if pemilik.dicabut:
                    raise tolak()
                catat_kontak(request, pemilik.device_id)
                return pemilik.device_id

        if not hmac.compare_digest(diberikan, token):
            raise tolak()
        if perangkat is not None:
            if not perangkat.token_bersama_aktif():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "Token bersama sudah dimatikan. Pasangkan perangkat ini "
                        "dengan kode dari Layanan Anjungan."
                    ),
                )
            if device_id:
                if perangkat.perangkat_dicabut(device_id):
                    raise tolak()
                catat_kontak(request, device_id)
        return device_id

    def welcome_media_paths() -> list[Path]:
        kind = services.settings.get("kiosk.welcome_kind", "teks")
        if kind not in _MEDIA_KINDS:
            return []
        folder = (base_dir() / "media" / "kiosk").resolve()
        files = []
        if folder.is_dir():
            for item in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
                if not item.is_file() or item.name.startswith("."):
                    continue
                if item.suffix.lower() not in _MEDIA_EXTENSIONS:
                    continue
                resolved = item.resolve()
                try:
                    resolved.relative_to(folder)
                except ValueError:
                    continue
                files.append(resolved)
        if files:
            return files
        fallback_value = services.settings.get("kiosk.welcome_file", "").strip()
        fallback = Path(fallback_value) if fallback_value else None
        if fallback is not None and not fallback.is_absolute():
            fallback = (folder / fallback).resolve()
            try:
                fallback.relative_to(folder)
            except ValueError:
                fallback = None
        return (
            [fallback]
            if fallback is not None
            and fallback.is_file()
            and fallback.suffix.lower() in _MEDIA_EXTENSIONS
            else []
        )

    @app.exception_handler(AppError)
    async def handle_app_error(_, exc: AppError):
        if isinstance(exc, AuthenticationError):
            code = status.HTTP_401_UNAUTHORIZED
        elif isinstance(exc, AuthorizationError):
            code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, NotFoundError):
            code = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, ValidationError):
            code = status.HTTP_422_UNPROCESSABLE_ENTITY
        elif isinstance(exc, BusinessRuleError):
            code = status.HTTP_409_CONFLICT
        else:
            code = status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=code, content={"detail": exc.user_message})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    def require_layar(
        request: Request,
        credentials: Annotated[
            HTTPAuthorizationCredentials | None, Depends(_bearer)
        ],
    ) -> str:
        """
        Hanya token perangkat berjenis layar antrian.

        Token bersama tidak diterima di sini: layar antrian baru, jadi tidak
        ada TV lama yang perlu dilindungi masa peralihannya. Token anjungan
        juga ditolak; satu perangkat, satu tugas (docs/istilah.md).
        """
        if perangkat is None or credentials is None:
            raise tolak()
        pemilik = perangkat.perangkat_dari_token(credentials.credentials)
        if pemilik is None or pemilik.dicabut or pemilik.jenis != "layar_antrian":
            raise tolak()
        catat_kontak(request, pemilik.device_id)
        return pemilik.device_id

    @app.get("/v1/layar/state", dependencies=[Depends(require_layar)])
    def layar_state(next: int | None = None):
        """
        Isi papan: nomor tiap loket, nomor berikutnya, dan yang menunggu.

        `next` (paling banyak 12): layar meminta lebih banyak nomor
        berikutnya supaya daftarnya dapat memanjang saat antrian ramai;
        `display.next_count` tetap menjadi jumlah paling sedikit.
        """
        jumlah = max(1, services.settings.get_int("display.next_count", 3))
        if next is not None:
            jumlah = max(jumlah, min(int(next), 12))
        state = services.queue.display_state(jumlah_berikutnya=jumlah)
        apk = info_apk(folder_apk(base_dir()), "layar")
        paket = info_paket(folder_paket(base_dir()))
        return {
            "title": services.settings.get("display.title", "ANTRIAN PELAYANAN CRO"),
            "sound_enabled": services.settings.get_bool("display.sound_enabled", True),
            "counters": [
                {
                    "name": loket.counter_name,
                    "queue_number": loket.antrian.queue_number if loket.antrian else None,
                    "category": loket.antrian.category_name if loket.antrian else None,
                    "status": (
                        loket.antrian.label_status
                        if loket.antrian is not None
                        else ("ISTIRAHAT" if loket.istirahat else "KOSONG")
                    ),
                }
                for loket in state.loket
            ],
            "next": [q.queue_number for q in state.berikutnya],
            "total_waiting": state.total_menunggu,
            "server_time_ms": int(time.time() * 1000),
            "timezone": TIMEZONE,
            "app_min_version_code": VERSI_MINIMAL_LAYAR,
            "app_latest_version_code": apk.kode_versi if apk else None,
            "app_latest_version_name": apk.nama_versi if apk else None,
            # Layar mengunduh ulang paket suara bila versinya berubah.
            "sound_pack_version": paket.versi if paket else None,
        }

    @app.get(
        "/v1/layar/app/apk",
        dependencies=[Depends(require_layar)],
        response_class=FileResponse,
    )
    def layar_apk():
        apk = info_apk(folder_apk(base_dir()), "layar")
        if apk is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="APK layar antrian belum tersedia di server.",
            )
        return FileResponse(
            apk.berkas, media_type=TIPE_APK, filename=f"AntrianLayar-{apk.nama_versi}.apk"
        )

    @app.get("/v1/layar/sound", dependencies=[Depends(require_layar)])
    def layar_sound_index():
        """Daftar klip paket suara: kunci → nama berkas."""
        paket = info_paket(folder_paket(base_dir()))
        if paket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Paket suara belum dibuat di Layanan Anjungan.",
            )
        return {"version": paket.versi, "voice": paket.suara, "clips": paket.klip}

    @app.get(
        "/v1/layar/sound/{filename}",
        dependencies=[Depends(require_layar)],
        response_class=FileResponse,
    )
    def layar_sound_clip(filename: str):
        """Satu klip; hanya berkas yang tercantum di indeks paket."""
        paket = info_paket(folder_paket(base_dir()))
        if paket is None or filename not in set(paket.klip.values()):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Klip tidak ada.")
        return FileResponse(folder_paket(base_dir()) / filename, media_type="audio/wav")

    @app.get("/v1/layar/calls", dependencies=[Depends(require_layar)])
    def layar_calls(after: int | None = None):
        """
        Panggilan sesudah id `after`, beserta kalimat yang diucapkan.

        Tanpa `after`, hanya id terakhir yang dikembalikan: TV yang baru
        menyala tidak membunyikan ulang panggilan yang sudah lewat.
        """
        from app.services.sound_service import teks_pengumuman

        terakhir, panggilan = services.queue.panggilan_sejak(after)
        return {
            "last_id": terakhir,
            "calls": [
                {
                    "id": p.id,
                    "queue_number": p.queue_number,
                    "counter_name": p.counter_name,
                    "call_number": p.call_number,
                    "text": teks_pengumuman(p.queue_number, p.counter_name),
                    # Urutan klip paket suara, untuk layar tanpa TTS Indonesia.
                    "tokens": token_pengumuman(p.queue_number, p.counter_name),
                }
                for p in panggilan
            ],
        }

    @app.post("/v1/kiosk/pair")
    def pair(request: PairRequest):
        """Tukar kode 6 angka dari Layanan Anjungan dengan token perangkat."""
        if perangkat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pemasangan perangkat tidak tersedia.",
            )
        sekarang = time.monotonic()
        tebakan_salah[:] = [t for t in tebakan_salah if sekarang - t < SELANG_TEBAKAN_DETIK]
        if len(tebakan_salah) >= BATAS_TEBAKAN_KODE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Terlalu banyak kode salah. Buat kode baru di Layanan Anjungan.",
            )
        try:
            device_token = perangkat.pasangkan(
                request.code, request.device_id, request.name, request.kind
            )
        except AppError:
            tebakan_salah.append(sekarang)
            if len(tebakan_salah) >= BATAS_TEBAKAN_KODE:
                # Tebakan beruntun: hanguskan semua kode yang masih terbuka.
                perangkat.batalkan_kode_aktif()
                logger.warning("Kode pasang dihanguskan setelah %s tebakan salah", len(tebakan_salah))
            raise
        return {"token": device_token}

    @app.post("/v1/kiosk/printer")
    def printer_report(
        report: PrinterReport,
        # Bentuk `= Depends(...)`, bukan Annotated: require_token adalah
        # fungsi lokal yang tidak terbaca FastAPI dari anotasi bertunda.
        device_id: str = Depends(require_token),  # noqa: B008
    ):
        """Hasil cetak terakhir, untuk kolom Printer di daftar perangkat."""
        if perangkat is not None and device_id:
            try:
                perangkat.catat_printer(device_id, report.ok, report.message)
            except Exception:
                logger.warning("Status printer %s gagal dicatat", device_id, exc_info=True)
        return {"status": "ok"}

    @app.get("/v1/kiosk/categories", dependencies=[Depends(require_token)])
    def categories():
        return [
            {
                "id": item.id,
                "name": item.name,
                "prefix": item.prefix,
                "parent_id": item.parent_id,
                "is_group": item.punya_anak,
                "info": item.info_text,
            }
            for item in services.master.list_categories(only_active=True)
        ]

    @app.get("/v1/kiosk/display", dependencies=[Depends(require_token)])
    def display():
        """
        Keadaan yang dibutuhkan anjungan untuk menerbitkan tiket, tidak lebih.

        Anjungan Android hanya mengambil nomor. Nomor yang sedang dilayani
        tiap loket dan jumlah yang menunggu adalah urusan papan antrian,
        sehingga sengaja tidak dikirim ke sini.
        """
        media = welcome_media_paths()
        apk = info_apk(folder_apk(base_dir()))
        return {
            "title": services.settings.get("display.title", "ANTRIAN PELAYANAN CRO"),
            "welcome_text": services.settings.get(
                "kiosk.welcome_text",
                "Sentuh salah satu layanan di bawah untuk mengambil nomor.",
            )
            or "Sentuh salah satu layanan di bawah untuk mengambil nomor.",
            "welcome_kind": services.settings.get("kiosk.welcome_kind", "teks"),
            "welcome_slide_seconds": services.settings.get_int(
                "kiosk.welcome_slide_seconds", 10
            ),
            "welcome_media": [item.name for item in media],
            "registration_open": services.queue.pendaftaran_dibuka(),
            "cooldown_remaining_seconds": services.queue.sisa_jeda_kios(),
            # Jam di layar anjungan memakai jam dan zona waktu SERVER, bukan
            # setelan tablet: tablet tanpa internet sering salah jam, dan
            # zona waktunya bisa terpasang di luar Indonesia.
            "server_time_ms": int(time.time() * 1000),
            "timezone": TIMEZONE,
            # Pembaruan APK dari server. Di bawah versi minimal, tablet
            # berhenti menerbitkan nomor dan menawarkan pembaruan.
            "app_min_version_code": VERSI_MINIMAL,
            "app_latest_version_code": apk.kode_versi if apk else None,
            "app_latest_version_name": apk.nama_versi if apk else None,
        }

    @app.get(
        "/v1/kiosk/media/{filename}",
        dependencies=[Depends(require_token)],
        response_class=FileResponse,
    )
    def welcome_media(filename: str):
        """Serve only configured kiosk welcome media files."""
        if not filename or filename != Path(filename).name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media sambutan tidak ditemukan.",
            )
        media = next(
            (item for item in welcome_media_paths() if item.name == filename),
            None,
        )
        if media is None or media.suffix.lower() not in _MEDIA_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media sambutan tidak ditemukan.",
            )
        media_type = mimetypes.guess_type(media.name)[0] or "application/octet-stream"
        return FileResponse(media, media_type=media_type)

    @app.get(
        "/v1/kiosk/app/apk",
        dependencies=[Depends(require_token)],
        response_class=FileResponse,
    )
    def download_apk():
        """APK anjungan terbaru untuk pembaruan dari server."""
        apk = info_apk(folder_apk(base_dir()))
        if apk is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="APK anjungan belum tersedia di server.",
            )
        return FileResponse(
            apk.berkas,
            media_type=TIPE_APK,
            filename=f"AntrianKiosk-{apk.nama_versi}.apk",
        )

    @app.post("/v1/kiosk/tickets", dependencies=[Depends(require_token)])
    def issue_ticket(
        request: TicketRequest,
        x_app_version_code: Annotated[int | None, Header()] = None,
    ):
        # APK lama salah membaca jawaban API sekarang. Lebih baik nomor
        # tidak terbit sama sekali daripada terbit tanpa tercetak benar.
        if x_app_version_code is None or x_app_version_code < VERSI_MINIMAL:
            raise HTTPException(
                status_code=status.HTTP_426_UPGRADE_REQUIRED,
                detail=(
                    "Aplikasi anjungan perlu diperbarui sebelum dapat "
                    "menerbitkan nomor."
                ),
            )
        with ticket_lock:
            cached = ticket_responses.get(request.request_id)
            if cached is not None:
                return cached

            queue_info = services.queue.create_queue(request.category_id)
            ticket_warning = None
            ticket_layout = None
            try:
                # Anjungan Android hanya mengambil nomor: tiketnya tidak
                # menyebut berapa yang menunggu. Baris itu tetap ada pada
                # tiket yang dicetak dari Windows.
                ticket = replace(services.ticket.susun(queue_info), sisa_antrian=None)
                ticket_lines = ticket.baris_teks()
                ticket_layout = tata_letak_tiket_anjungan(ticket)
                issued_at = ticket.issued_at.isoformat()
            except Exception:
                logger.exception(
                    "Tiket %s terbit, tetapi isi struk gagal disusun",
                    queue_info.queue_number,
                )
                ticket_lines = [
                    "NOMOR ANTRIAN",
                    queue_info.queue_number,
                    queue_info.category_name,
                ]
                issued_at = queue_info.created_at.isoformat()
                ticket_warning = "Nomor terbit; rincian tiket tidak lengkap."
            response = {
                "request_id": str(request.request_id),
                "queue_number": queue_info.queue_number,
                "category_name": queue_info.category_name,
                "issued_at": issued_at,
                "ticket_lines": ticket_lines,
                "ticket_layout": ticket_layout,
                "ticket_warning": ticket_warning,
                "cooldown_seconds": services.settings.get_int(
                    "kiosk.cooldown_seconds", 10
                ),
            }
            ticket_responses[request.request_id] = response
            if len(ticket_responses) > 1000:
                ticket_responses.pop(next(iter(ticket_responses)))
            return response

    return app


def serve() -> int:
    """Serve the authenticated LAN kiosk API using an initialized database."""
    # Task Scheduler menjalankan proses ini tanpa environment petugas, jadi
    # token dibaca dari berkas di folder database bila tidak diberikan.
    from app.services.kiosk_server import muat_token

    token = muat_token()
    if len(token) < MIN_TOKEN_LENGTH:
        logger.error(
            "Token API anjungan belum disiapkan (minimal %s karakter). "
            "Buka Layanan Anjungan pada komputer server.",
            MIN_TOKEN_LENGTH,
        )
        return 2
    discovery_socket = None
    discovery_stop = threading.Event()
    discovery_thread = None
    try:
        services = KioskServices()
        app = create_app(token, services)
        host = os.environ.get("ANTRIAN_KIOS_API_HOST", "0.0.0.0")
        port = int(os.environ.get("ANTRIAN_KIOS_API_PORT", "8765"))
        discovery_port = int(
            os.environ.get("ANTRIAN_KIOS_DISCOVERY_PORT", str(DISCOVERY_PORT))
        )
        discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        discovery_socket.bind(("0.0.0.0", discovery_port))
        discovery_socket.settimeout(0.5)
        discovery_thread = threading.Thread(
            target=_serve_discovery,
            args=(discovery_socket, port, discovery_stop),
            name="kiosk-discovery",
            daemon=True,
        )
        discovery_thread.start()
        logger.info(
            "API anjungan dimulai pada %s:%s; pencarian LAN UDP %s "
            "(revisi database %s)",
            host,
            port,
            discovery_port,
            current_revision(),
        )
        uvicorn.run(app, host=host, port=port, log_config=None)
        return 0
    except Exception:
        logger.exception("API anjungan berhenti karena kesalahan")
        return 1
    finally:
        discovery_stop.set()
        if discovery_socket is not None:
            discovery_socket.close()
        if discovery_thread is not None:
            discovery_thread.join(timeout=1)


def main() -> int:
    """Initialize the database and serve the authenticated LAN kiosk API."""
    config = get_config()
    setup_logging(config)
    try:
        from app.core.database import init_database

        init_database()
        seed_initial_data()
        return serve()
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    except Exception:
        logger.exception("API anjungan gagal dimulai")
        return 1
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
