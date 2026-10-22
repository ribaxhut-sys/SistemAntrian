"""LAN API for the Android ticket-taking kiosk."""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import socket
import threading
import time
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app import __version__
from app.core import clock
from app.core.config import TIMEZONE, base_dir, get_config
from app.core.database import dispose_engine, periksa_koneksi
from app.core.identitas import NAMA_TAMPIL
from app.core.errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)
from app.core.logger import get_logger, setup_logging
from app.core.migrations import current_revision, head_revision
from app.core.seed import seed_initial_data
from app.services.apk_anjungan import (
    TIPE_APK,
    VERSI_MINIMAL,
    VERSI_MINIMAL_LAYAR,
    folder_apk,
    info_apk,
)
from app.services.device_service import KUNCI_ANJUNGAN_BERSUARA
from app.services.pembaruan_windows import (
    catat_denyut_pc,
    folder_pembaruan,
    info_pembaruan,
)
from app.services import cetak_ulang_anjungan, daftar_putar, pin_anjungan
from app.services.auth_service import AuthService
from app.services.master_data_service import MasterDataService
from app.services.paket_suara import folder_paket, info_paket, token_pengumuman
from app.services.queue_service import QueueService
from app.services.settings_service import CuplikanPengaturan, SettingsService
from app.services.ticket_service import (
    NullTicketPrinter,
    TicketService,
    raster_tiket_anjungan,
    tata_letak_tiket_anjungan,
)

_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".3gp"}
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
#: Letak baris loket di anjungan; nilai lain dibaca sebagai "otomatis".
POSISI_LOKET = ("otomatis", "atas", "bawah", "sembunyi")
#: Tema warna anjungan Android; nilai lain dibaca sebagai "biru".
TEMA_ANJUNGAN = ("biru", "hijau", "kontras", "gelap", "merah_putih")
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
    #: Pengunjung mencentang "Saya lansia / disabilitas / ibu hamil".
    #: Opsional: APK lama tidak mengirimnya dan tetap mendapat nomor biasa.
    priority: bool = False


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    device_id: str = Field(min_length=8, max_length=64)
    name: str = Field(default="", max_length=80)
    kind: str = Field(default="anjungan", max_length=20)


class PrinterReport(BaseModel):
    ok: bool
    message: str = Field(default="", max_length=200)


class HasilCetakUlang(BaseModel):
    ok: bool
    message: str = Field(default="", max_length=200)


class BateraiReport(BaseModel):
    percent: int = Field(ge=0, le=100)
    charging: bool = False


class MediaReportItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plays: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    error: str = Field(default="", max_length=500)
    #: Percobaan terakhir berkas ini di tablet gagal.
    last_failed: bool = False


class PinRequest(BaseModel):
    pin: str = Field(min_length=1, max_length=12)


class MediaStatus(BaseModel):
    """Status salinan media di tablet: tersalin dari total berkas."""

    total: int = Field(ge=0, le=10_000)
    copied: int = Field(ge=0, le=10_000)
    bytes: int = Field(default=0, ge=0)


class MediaReport(BaseModel):
    items: list[MediaReportItem] = Field(default_factory=list, max_length=100)


class PerangkatDb:
    """Penghubung API dengan tabel perangkat (app.services.device_service)."""

    def __getattr__(self, nama):
        from app.services import device_service

        return getattr(device_service, nama)


class MediaTayangDb:
    """Penghubung API dengan catatan tayang iklan (app.services.media_tayang)."""

    def __getattr__(self, nama):
        from app.services import media_tayang

        return getattr(media_tayang, nama)


#: Tebakan kode pasang yang salah sebelum semua kode aktif dihanguskan.
BATAS_TEBAKAN_KODE = 10
#: Tebakan salah gabungan semua IP sebelum semua kode aktif dihanguskan.
BATAS_TEBAKAN_GLOBAL = 30
SELANG_TEBAKAN_DETIK = 600
SELANG_TULIS_KONTAK_DETIK = 30

#: Jarak minimal antar-restart API yang diminta tablet, juga umur minimal
#: proses API sebelum boleh di-restart dari tablet.
JEDA_RESTART_API_DETIK = 60


@lru_cache(maxsize=1)
def _revisi_terbaru() -> str | None:
    """Revisi migrasi milik program ini; tidak berubah selama proses hidup."""
    return head_revision()


def periksa_kesiapan() -> dict[str, str]:
    """
    Fakta untuk /health/siap: database terjangkau dan skemanya sesuai.

    Hanya kata keadaan yang keluar. Endpoint ini tanpa token, jadi alamat
    database, versi, maupun pesan galat tidak boleh ikut; detailnya masuk
    log (periksa_koneksi mencatatnya sendiri).
    """
    if not periksa_koneksi():
        return {"database": "gagal", "skema": "tidak_diketahui"}
    try:
        skema = "ok" if current_revision() == _revisi_terbaru() else "tidak_sesuai"
    except Exception:
        logger.exception("Revisi skema tidak terbaca untuk /health/siap")
        skema = "gagal"
    return {"database": "ok", "skema": skema}


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
        self.media_tayang = MediaTayangDb()


def create_app(token: str, services: KioskServices | None = None) -> FastAPI:
    """Build an API application that can issue tickets only for a kiosk session."""
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(
            f"ANTRIAN_KIOS_API_TOKEN must contain at least {MIN_TOKEN_LENGTH} characters."
        )

    services = services or KioskServices()
    # Pengaman tambahan saja: menerbitkan satu tiket pada satu waktu di
    # proses ini, sehingga dua sentuhan beruntun dari tablet yang sama
    # tidak lolos jeda bersamaan. Perlindungan dari nomor ganda ada di
    # database (constraint unik device_id + request_id), yang tetap
    # berlaku walau proses API dinyalakan ulang.
    ticket_lock = threading.Lock()
    # Kunci restart terpisah: pemeriksaan tugas lewat PowerShell makan 1–3
    # detik, dan selama itu penerbitan tiket tidak boleh ikut tertahan.
    restart_lock = threading.Lock()
    #: Waktu (monotonic) API ini mulai, lalu restart terakhir yang diterima.
    #: Diisi sejak awal: restart mematikan proses ini, sehingga catatan
    #: restart ikut hilang — yang tersisa sebagai pembatas adalah umur
    #: proses yang baru menyala.
    restart_terakhir: list[float] = [time.monotonic()]
    app = FastAPI(
        title="Sistem Antrian CRO Kiosk API",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Tanpa `perangkat` (test lama, atau API yang dijalankan tanpa database
    # perangkat) hanya token bersama yang dikenal.
    perangkat = getattr(services, "perangkat", None)
    kontak_terakhir: dict[str, float] = {}
    #: Waktu tebakan kode pasang yang salah, per IP pengirim.
    tebakan_salah: dict[str, list[float]] = {}
    #: Endpoint sinkron FastAPI berjalan di thread pool; pembatas tebakan
    #: (kode pasang dan PIN) dibaca-ubah di bawah kunci ini.
    lock_tebakan = threading.Lock()

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
                # Token perangkat tidak dapat dipindahkan antar-tugas.
                # Layar antrian mempunyai endpoint baca sendiri di /v1/layar;
                # ia tidak boleh menerbitkan nomor atau mengubah keadaan kios.
                if pemilik.dicabut or pemilik.jenis != "anjungan":
                    raise tolak()
                catat_kontak(request, pemilik.device_id)
                request.state.perangkat_terpasang = True
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
                dicabut, dipasangkan = perangkat.keadaan_perangkat(device_id)
                if dicabut:
                    raise tolak()
                if dipasangkan:
                    # Tablet itu punya token sendiri; token bersama tidak
                    # boleh berbicara atas namanya (status printer, media,
                    # jatah tebakan PIN). Diperlakukan tanpa ID.
                    return ""
                catat_kontak(request, device_id)
        return device_id

    def perangkat_terpercaya(
        request: Request, device_id: str = Depends(require_token)  # noqa: B008
    ) -> str:
        """
        device_id yang dapat dipercaya, untuk jeda kios dan restart API.

        Hanya device_id perangkat yang DIPASANGKAN yang dapat dipercaya:
        token perangkat itu sendiri yang menyebut pemiliknya. Pada token
        bersama, X-Device-Id diisi pengirim sendiri — memakainya sebagai
        kunci jeda berarti cukup mengganti header untuk lolos dari jeda.
        Karena itu semua pengguna token bersama berbagi satu kunci kosong.

        Kunci idempotensi tiket tetap memakai X-Device-Id: mengubahnya hanya
        memisahkan permintaan pengirim itu sendiri, tidak melonggarkan apa pun.
        """
        if getattr(request.state, "perangkat_terpasang", False):
            return device_id
        return ""

    def anjungan_ini_bersuara(device_id: str, pengaturan=None) -> bool:
        if not device_id or perangkat is None:
            return False
        if pengaturan is not None:
            return pengaturan.get(KUNCI_ANJUNGAN_BERSUARA, "") == device_id
        try:
            return perangkat.anjungan_bersuara() == device_id
        except Exception:
            # Suara bukan syarat pelayanan; anjungan tetap menerbitkan nomor.
            logger.warning("Pengaturan anjungan bersuara tidak terbaca", exc_info=True)
            return False

    def posisi_loket(pengaturan=None) -> str:
        nilai = (pengaturan or services.settings).get(
            "kiosk.posisi_loket", "otomatis"
        )
        return nilai if nilai in POSISI_LOKET else "otomatis"

    def tema_anjungan(pengaturan=None) -> str:
        """Tema yang berlaku hari ini; Agustus boleh otomatis merah putih."""
        sumber = pengaturan or services.settings
        if (
            sumber.get_bool("kiosk.tema_agustus", True)
            and clock.today().month == 8
        ):
            return "merah_putih"
        nilai = sumber.get("kiosk.tema", "biru")
        return nilai if nilai in TEMA_ANJUNGAN else "biru"

    def isi_loket(state) -> list[dict]:
        """Nomor tiap loket, sama untuk layar antrian dan anjungan."""
        return [
            {
                "name": loket.counter_name,
                "queue_number": loket.antrian.queue_number if loket.antrian else None,
                "category": loket.antrian.category_name if loket.antrian else None,
                # Bertambah tiap panggilan DAN panggilan ulang: anjungan
                # mengenali panggilan baru dari perubahan angka ini.
                "call_count": (
                    loket.antrian.jumlah_panggilan if loket.antrian else 0
                ),
                "status": (
                    loket.antrian.label_status
                    if loket.antrian is not None
                    else ("ISTIRAHAT" if loket.istirahat else "KOSONG")
                ),
            }
            for loket in state.loket
        ]

    def isi_pin(pengaturan=None) -> dict:
        try:
            data = (
                pin_anjungan.dari_nilai(pengaturan.get(pin_anjungan.KUNCI, ""))
                if isinstance(pengaturan, CuplikanPengaturan)
                else pin_anjungan.baca()
            )
        except Exception:
            logger.warning("PIN anjungan gagal dibaca", exc_info=True)
            data = None
        if data is None:
            return {"enabled": False}
        return {
            "enabled": True,
            "salt": data.salt,
            "hash": data.hash,
            "iterations": data.iterations,
        }

    def permintaan_segarkan(device_id: str) -> int:
        if perangkat is None or not device_id:
            return 0
        try:
            return int(perangkat.permintaan_segarkan_media(device_id))
        except Exception:
            return 0

    def pustaka_media() -> list[Path]:
        """SEMUA gambar/video di folder media server, bukan hanya daftar putar."""
        folder = (base_dir() / "media" / "kiosk").resolve()
        if not folder.is_dir():
            return []
        hasil = []
        for item in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
            if not item.is_file() or item.name.startswith("."):
                continue
            if item.suffix.lower() not in _MEDIA_EXTENSIONS:
                continue
            try:
                item.resolve().relative_to(folder)
            except ValueError:
                continue
            hasil.append(item.resolve())
        return hasil

    def welcome_media_paths(pengaturan=None) -> list[Path]:
        sumber = pengaturan or services.settings
        kind = sumber.get("kiosk.welcome_kind", "teks")
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
        nilai_daftar = sumber.get(daftar_putar.KUNCI, "")
        if daftar_putar.baca(nilai_daftar) is not None:
            # Daftar putar yang sudah diatur berlaku apa adanya, juga bila
            # semua berkas sengaja dimatikan: tidak ada media, bukan cadangan.
            # Iklan di luar tanggal tayangnya dilewati menurut tanggal SERVER.
            return daftar_putar.terapkan(files, nilai_daftar, clock.today())
        if files:
            return files
        fallback_value = sumber.get("kiosk.welcome_file", "").strip()
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
        # Isi ini dibandingkan byte demi byte oleh api_sudah_berjalan dan
        # api_terjangkau, termasuk di komputer loket versi lama. Jangan
        # ditambah; pemeriksaan sungguhan ada di /health/siap.
        return {"status": "ok"}

    @app.get("/health/siap")
    def health_siap():
        """
        Siap melayani tablet: 200 bila ya, 503 bila tidak.

        /health hanya membuktikan proses menyala. API yang kehilangan
        database tetap menjawab /health, padahal tablet tidak dapat
        mengambil nomor — itulah kegagalan yang ditangkap di sini.
        """
        fakta = periksa_kesiapan()
        siap = fakta["database"] == "ok" and fakta["skema"] == "ok"
        return JSONResponse(
            status_code=status.HTTP_200_OK if siap else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ok" if siap else "gagal", **fakta},
        )

    @app.get("/v1/windows/update")
    def windows_update_info(request: Request):
        """Metadata installer Windows terbaru untuk PC jaringan kantor."""
        catat_denyut_pc(
            request.headers.get("X-Komputer", ""),
            request.headers.get("X-Versi-App", ""),
            request.client.host if request.client else "",
        )
        info = info_pembaruan(folder_pembaruan(base_dir()))
        if info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pembaruan Windows belum tersedia di server.",
            )
        return {
            "latest_version": info.versi,
            "size": info.ukuran_byte,
            "sha256": info.sha256,
            # Tanda tangan pengembang atas tiga nilai di atas; klien
            # memverifikasinya dengan kunci publik tertanam.
            "signature": info.tanda,
            # Teks biasa "apa yang baru"; tidak ditandatangani.
            "release_notes": info.catatan,
        }

    @app.get("/v1/windows/update/download")
    def windows_update_download():
        """Installer Windows; klien wajib memeriksa checksum-nya."""
        info = info_pembaruan(folder_pembaruan(base_dir()))
        if info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pembaruan Windows belum tersedia di server.",
            )
        return FileResponse(
            info.berkas,
            media_type="application/vnd.microsoft.portable-executable",
            filename=info.berkas.name,
        )

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

        `next` (paling banyak 300): layar meminta lebih banyak nomor
        berikutnya supaya daftarnya dapat memanjang saat antrian ramai;
        `display.next_count` tetap menjadi jumlah paling sedikit.
        """
        jumlah = max(1, services.settings.get_int("display.next_count", 3))
        if next is not None:
            jumlah = max(jumlah, min(int(next), 300))
        state = services.queue.display_state(
            jumlah_berikutnya=jumlah, jumlah_per_layanan=1, riwayat_dipanggil=300
        )
        apk = info_apk(folder_apk(base_dir()), "layar")
        paket = info_paket(folder_paket(base_dir()))
        return {
            "title": NAMA_TAMPIL,
            "sound_enabled": services.settings.get_bool("display.sound_enabled", True),
            "counters": isi_loket(state),
            "next": [q.queue_number for q in state.berikutnya],
            # Subset "next" yang prioritas (hanya nomor; tanpa alasan).
            "next_priority": [
                q.queue_number for q in state.berikutnya if q.prioritas
            ],
            "total_waiting": state.total_menunggu,
            # Semua nomor yang sudah dipanggil hari ini (terbaru dulu): hanya nomor
            # dan label status, untuk dinding nomor.
            "called": [{"n": n, "s": st} for n, st in state.dipanggil],
            # Prefiks nomor -> nama layanan, untuk judul kelompok di layar.
            "service_labels": {
                k.category_prefix: k.category_name for k in state.layanan
            },
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

    def indeks_paket_suara() -> dict:
        """Daftar klip paket suara: kunci → nama berkas."""
        paket = info_paket(folder_paket(base_dir()))
        if paket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Paket suara belum dibuat di Layanan Anjungan.",
            )
        return {"version": paket.versi, "voice": paket.suara, "clips": paket.klip}

    def klip_paket_suara(filename: str) -> FileResponse:
        """Satu klip; hanya berkas yang tercantum di indeks paket."""
        paket = info_paket(folder_paket(base_dir()))
        if paket is None or filename not in set(paket.klip.values()):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Klip tidak ada.")
        return FileResponse(folder_paket(base_dir()) / filename, media_type="audio/wav")

    def panggilan_sejak(after: int | None) -> dict:
        """
        Panggilan sesudah id `after`, beserta kalimat yang diucapkan.

        Tanpa `after`, hanya id terakhir yang dikembalikan: perangkat yang
        baru menyala tidak membunyikan ulang panggilan yang sudah lewat.
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
                    # Umur menurut jam server; jam tablet sering salah.
                    "age_seconds": round(p.umur_detik, 1),
                    "text": teks_pengumuman(p.queue_number, p.counter_name),
                    # Urutan klip paket suara, untuk perangkat tanpa TTS Indonesia.
                    "tokens": token_pengumuman(p.queue_number, p.counter_name),
                }
                for p in panggilan
            ],
        }

    @app.get("/v1/layar/sound", dependencies=[Depends(require_layar)])
    def layar_sound_index():
        return indeks_paket_suara()

    @app.get(
        "/v1/layar/sound/{filename}",
        dependencies=[Depends(require_layar)],
        response_class=FileResponse,
    )
    def layar_sound_clip(filename: str):
        return klip_paket_suara(filename)

    @app.get("/v1/layar/calls", dependencies=[Depends(require_layar)])
    def layar_calls(after: int | None = None):
        return panggilan_sejak(after)

    # Anjungan yang dipilih admin merangkap pengeras suara panggilan selama
    # layar antrian belum terpasang. Isinya sama dengan milik layar antrian,
    # tetapi lewat token anjungan: satu token tetap untuk satu jenis perangkat.

    @app.get("/v1/kiosk/sound", dependencies=[Depends(require_token)])
    def kiosk_sound_index():
        return indeks_paket_suara()

    @app.get(
        "/v1/kiosk/sound/{filename}",
        dependencies=[Depends(require_token)],
        response_class=FileResponse,
    )
    def kiosk_sound_clip(filename: str):
        return klip_paket_suara(filename)

    @app.get("/v1/kiosk/calls", dependencies=[Depends(require_token)])
    def kiosk_calls(after: int | None = None):
        return panggilan_sejak(after)

    def kunci_pembatas(request: Request, device_id: str) -> str:
        """
        Kunci pembatas tebakan: tablet terpasang, atau IP pengirim.

        X-Device-Id token bersama diisi pengirim sendiri, jadi tidak dipakai;
        alamat IP koneksi TCP tidak dapat dipilih semaunya oleh pengirim.
        """
        if getattr(request.state, "perangkat_terpasang", False) and device_id:
            return device_id
        return "ip:" + (request.client.host if request.client else "")

    @app.post("/v1/kiosk/pair")
    def pair(permintaan: PairRequest, request: Request):
        """
        Tukar kode 6 angka dari Layanan Anjungan dengan token perangkat.

        Tebakan salah dibatasi per IP pengirim (BATAS_TEBAKAN_KODE), supaya
        satu pengganggu tidak dapat menghalangi pemasangan tablet lain.
        Jumlah gabungan semua IP tetap dijaga (BATAS_TEBAKAN_GLOBAL): bila
        terlampaui, semua kode terbuka dihanguskan, karena tebakan dari
        banyak alamat sekaligus adalah tanda penebakan terencana.
        """
        if perangkat is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pemasangan perangkat tidak tersedia.",
            )
        ip = request.client.host if request.client else ""
        with lock_tebakan:
            sekarang = time.monotonic()
            for kunci in list(tebakan_salah):
                segar = [t for t in tebakan_salah[kunci] if sekarang - t < SELANG_TEBAKAN_DETIK]
                if segar:
                    tebakan_salah[kunci] = segar
                else:
                    del tebakan_salah[kunci]
            if len(tebakan_salah.get(ip, ())) >= BATAS_TEBAKAN_KODE:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Terlalu banyak kode salah. Buat kode baru di Layanan Anjungan.",
                )
            try:
                device_token = perangkat.pasangkan(
                    permintaan.code, permintaan.device_id, permintaan.name, permintaan.kind
                )
            except AppError:
                tebakan_salah.setdefault(ip, []).append(sekarang)
                jumlah = sum(len(v) for v in tebakan_salah.values())
                if (
                    len(tebakan_salah[ip]) >= BATAS_TEBAKAN_KODE
                    or jumlah >= BATAS_TEBAKAN_GLOBAL
                ):
                    # Tebakan beruntun: hanguskan semua kode yang masih terbuka.
                    perangkat.batalkan_kode_aktif()
                    logger.warning(
                        "Kode pasang dihanguskan setelah tebakan salah (%s dari %s, %s total)",
                        len(tebakan_salah[ip]),
                        ip,
                        jumlah,
                    )
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

    batas_pin = pin_anjungan.BatasPercobaan()

    @app.post("/v1/kiosk/pin/verifikasi")
    def pin_verifikasi(
        permintaan: PinRequest,
        request: Request,
        device_id: str = Depends(require_token),  # noqa: B008
    ):
        """
        Periksa PIN pengaturan anjungan. Salah berulang menunda tablet itu
        1 / 5 / 15 menit; selama ditunda jawabannya `locked_seconds` tanpa
        memeriksa PIN, supaya penundaan tidak dapat ditembus dengan menebak.

        Kuncinya `kunci_pembatas`: dengan X-Device-Id sebagai kunci, cukup
        mengganti header tiap tebakan untuk lolos dari penundaan.
        """
        kunci = kunci_pembatas(request, device_id)
        # Dikunci: dua tebakan bersamaan tidak boleh sama-sama lolos
        # sebelum hitungan gagal bertambah.
        with lock_tebakan:
            sisa = batas_pin.sisa_tunda(kunci)
            if sisa:
                return {"ok": False, "locked_seconds": sisa}
            data = pin_anjungan.baca()
            if data is None:
                # Tidak ada PIN yang perlu diperiksa: pengaturan terbuka.
                return {"ok": True, "locked_seconds": 0}
            if pin_anjungan.cocok(permintaan.pin, data):
                batas_pin.catat_berhasil(kunci)
                return {"ok": True, "locked_seconds": 0}
            tunda = batas_pin.catat_gagal(kunci)
        logger.warning("PIN pengaturan salah dari anjungan %s", kunci)
        return {"ok": False, "locked_seconds": tunda}

    @app.post("/v1/kiosk/baterai")
    def baterai_report(
        laporan: BateraiReport,
        device_id: str = Depends(require_token),  # noqa: B008
    ):
        """Tingkat baterai tablet, untuk Kesehatan Sistem."""
        if perangkat is not None and device_id:
            try:
                perangkat.catat_baterai(device_id, laporan.percent, laporan.charging)
            except Exception:
                logger.warning(
                    "Status baterai %s gagal dicatat", device_id, exc_info=True
                )
        return {"status": "ok"}

    @app.post("/v1/kiosk/media-status")
    def media_status(
        laporan: MediaStatus,
        device_id: str = Depends(require_token),  # noqa: B008
    ):
        """Berapa berkas daftar putar yang sudah tersalin utuh di tablet."""
        if perangkat is not None and device_id:
            try:
                perangkat.catat_media(
                    device_id, laporan.total, laporan.copied, laporan.bytes
                )
            except Exception:
                logger.warning(
                    "Status media %s gagal dicatat", device_id, exc_info=True
                )
        return {"status": "ok"}

    @app.post("/v1/kiosk/media-report")
    def media_report(
        report: MediaReport,
        device_id: str = Depends(require_token),  # noqa: B008
    ):
        """
        Jumlah tayang dan gagal iklan sejak laporan sebelumnya.

        Gagal mencatat tidak boleh membuat tablet mengulang laporan yang
        sama selamanya; jawabannya tetap "ok" dan kesalahannya masuk log.
        """
        catatan = getattr(services, "media_tayang", None)
        if catatan is not None and device_id and report.items:
            from app.services.media_tayang import LaporanBerkas

            try:
                catatan.catat(
                    device_id,
                    [
                        LaporanBerkas(
                            nama=item.name,
                            tayang=item.plays,
                            gagal=item.failures,
                            galat=item.error,
                            terakhir_gagal=item.last_failed,
                        )
                        for item in report.items
                    ],
                )
            except Exception:
                logger.warning("Laporan tayang %s gagal dicatat", device_id, exc_info=True)
        return {"status": "ok"}

    def isi_layanan() -> list[dict]:
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

    def versi_layanan(isi: list[dict]) -> str:
        """Sidik daftar layanan; tablet memuat ulang daftarnya bila berubah."""
        mentah = json.dumps(isi, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(mentah.encode("utf-8")).hexdigest()[:16]

    @app.get("/v1/kiosk/categories", dependencies=[Depends(require_token)])
    def categories():
        return isi_layanan()

    @app.get("/v1/kiosk/display")
    def display(device_id: str = Depends(perangkat_terpercaya)):  # noqa: B008
        """
        Keadaan ringkas anjungan: daftar nomor yang masih menunggu dan nomor
        yang sedang dilayani tiap loket.

        Keduanya hanya nomor anonim pada hari ini. Anjungan menampilkannya
        sebagai satu baris ringkas "NOMOR DI LOKET"; papan loket besar tetap
        urusan layar antrian. Panggilan bersuara juga, kecuali admin memilih
        anjungan ini sebagai pengganti sementara (`call_sound`).
        """
        pengaturan = services.settings.cuplikan()
        media = welcome_media_paths(pengaturan)
        detik_khusus = daftar_putar.detik_per_berkas(
            pengaturan.get(daftar_putar.KUNCI, "")
        )
        tampil_berkas = daftar_putar.tampil_per_berkas(
            pengaturan.get(daftar_putar.KUNCI, "")
        )
        apk = info_apk(folder_apk(base_dir()))
        paket = info_paket(folder_paket(base_dir()))
        keadaan = services.queue.display_state(
            jumlah_berikutnya=0,
            rasio_prioritas=max(0, pengaturan.get_int("queue.rasio_prioritas", 3)),
            loket_tampil=pengaturan.get("display.loket_tampil", "berpetugas"),
            sertakan_terkini=False,
        )
        return {
            # Identitas tetap (app/core/identitas.py); tidak dapat diubah admin.
            "title": NAMA_TAMPIL,
            "subtitle": (pengaturan.get("kiosk.subjudul", "") or "").strip(),
            "welcome_text": pengaturan.get(
                "kiosk.welcome_text",
                "Sentuh salah satu layanan di bawah untuk mengambil nomor.",
            )
            or "Sentuh salah satu layanan di bawah untuk mengambil nomor.",
            "welcome_kind": pengaturan.get("kiosk.welcome_kind", "teks"),
            "welcome_slide_seconds": pengaturan.get_int(
                "kiosk.welcome_slide_seconds", 10
            ),
            "welcome_media": [item.name for item in media],
            # Ukuran dan waktu ubah tiap berkas: tablet menyimpan salinan
            # media dan baru mengunduh ulang bila salah satunya berubah.
            "welcome_media_files": [
                {
                    "name": item.name,
                    "size": item.stat().st_size,
                    "modified_ms": int(item.stat().st_mtime * 1000),
                    # Lama tampil gambar ini; null = welcome_slide_seconds.
                    "seconds": detik_khusus.get(item.name),
                    # Di mana berkas ini tampil: panel (strip atas), penuh
                    # (layar penuh saat menganggur), atau keduanya. APK lama
                    # mengabaikannya dan memutar semuanya seperti dulu.
                    "show": tampil_berkas.get(
                        item.name, daftar_putar.TAMPIL_KEDUANYA
                    ),
                }
                for item in media
            ],
            # Setelah sekian detik tanpa sentuhan iklan memenuhi layar;
            # 0 = tidak pernah.
            "fullscreen_ad_idle_seconds": pengaturan.get_int(
                "kiosk.iklan_layar_penuh_detik", 60
            ),
            # Berapa putaran iklan layar penuh sebelum kembali ke tampilan
            # antrian; 0 = berputar terus sampai disentuh.
            "fullscreen_ad_loops": pengaturan.get_int(
                "kiosk.iklan_putaran", 2
            ),
            # Animasi tiga panel masuk dari arah acak saat kembali ke antrian.
            "return_animation": pengaturan.get_bool(
                "kiosk.animasi_kembali", True
            ),
            # Tiga panel keluar sebelum iklan layar penuh muncul.
            "ad_entry_animation": pengaturan.get_bool(
                "kiosk.animasi_iklan_muncul", True
            ),
            # Panggilan petugas mengalahkan iklan layar penuh.
            "call_interrupts_ad": pengaturan.get_bool(
                "kiosk.panggilan_hentikan_iklan", True
            ),
            # Nomor menunggu muncul berurutan dengan gaya acak.
            "waiting_animation": pengaturan.get_bool(
                "kiosk.animasi_nomor_menunggu", True
            ),
            # Detik sebelum iklan terakhir berakhir saat animasi mulai; 0 =
            # sesudah iklan selesai.
            "return_animation_lead_seconds": pengaturan.get_int(
                "kiosk.animasi_mulai_detik", 2
            ),
            "registration_open": services.queue.pendaftaran_dibuka(pengaturan),
            # PIN pengaturan anjungan. Hash (bukan PIN) ikut dikirim supaya
            # tablet yang terputus tetap dapat memeriksa PIN untuk jalan pulih.
            # Hash PIN 6 angka dapat ditebak habis di luar server, jadi hanya
            # tablet TERPASANG yang menerimanya; pemegang token bersama tidak.
            # Tanpa kunci ini tablet memakai salinan yang sudah ia simpan.
            **({"settings_pin": isi_pin(pengaturan)} if device_id else {}),
            # Berubah bila admin menekan "Segarkan media" untuk tablet ini;
            # tablet menyegarkan salinannya segera bila nilainya baru.
            "media_refresh": permintaan_segarkan(device_id),
            # Tablet menampilkan kotak prioritas hanya bila true.
            "priority_enabled": pengaturan.get_bool(
                "kiosk.prioritas_aktif", True
            ),
            # Tablet hanya memuat /categories saat menyala. Tanpa sidik ini
            # layanan yang ditambah, diganti nama, atau dinonaktifkan di
            # Data Master baru terlihat sesudah tablet dibuka ulang.
            "categories_version": versi_layanan(isi_layanan()),
            "cooldown_remaining_seconds": services.queue.sisa_jeda_kios(
                device_id, pengaturan
            ),
            "waiting_queue_numbers": keadaan.nomor_menunggu,
            # Nomor yang diberi tanda bintang; tanpa alasan prioritasnya.
            "waiting_priority_numbers": keadaan.nomor_prioritas,
            # Baris "NOMOR DI LOKET". Posisinya (otomatis/atas/bawah) dipilih
            # di server supaya semua tablet seragam; tablet sendiri yang
            # memutuskan "otomatis", karena hanya tablet yang tahu apakah
            # media iklannya benar-benar dapat diputar.
            "counters": isi_loket(keadaan),
            "counter_position": posisi_loket(pengaturan),
            "theme": tema_anjungan(pengaturan),
            "video_sound": pengaturan.get_bool("kiosk.suara_video", False),
            # Hanya anjungan pilihan admin yang membunyikan panggilan, dan
            # hanya yang dipasangkan: device_id token bersama tidak dapat
            # dipercaya (lihat perangkat_terpercaya).
            "call_sound": anjungan_ini_bersuara(device_id, pengaturan),
            # Tablet mengunduh ulang paket suara bila versinya berubah.
            "sound_pack_version": paket.versi if paket else None,
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

    @app.get("/v1/kiosk/ticket-sample", dependencies=[Depends(require_token)])
    def ticket_sample():
        """
        Tiket contoh untuk tombol Uji cetak di tablet.

        Digambar dengan pengaturan tiket yang sama dengan tiket sungguhan
        (judul, nama kantor, catatan kaki tidak, geseran ya), supaya uji
        cetak menunjukkan hasil yang benar-benar akan keluar. Nomornya
        sengaja tidak menyerupai nomor sungguhan.
        """
        contoh = SimpleNamespace(
            queue_number="UJI-000",
            category_name="Uji Cetak",
            created_at=clock.now(),
            counter_name=None,
        )
        ticket = replace(
            services.ticket.susun(contoh),
            sisa_antrian=None,
            footer="Tiket contoh untuk menguji pencetak. Bukan nomor antrian.",
        )
        return {
            "ticket_layout": tata_letak_tiket_anjungan(ticket),
            "ticket_raster": raster_tiket_anjungan(ticket),
        }

    @app.get("/v1/kiosk/cetak-ulang")
    def cetak_ulang_menunggu(
        device_id: str = Depends(perangkat_terpercaya),  # noqa: B008
    ):
        """
        Tiket yang diminta petugas dicetak ulang di tablet ini.

        Hanya tablet berpasangan: token bersama mengisi X-Device-Id sendiri,
        sehingga tidak boleh mengambil perintah milik tablet lain. Isi tiket
        disusun sekarang dari keadaan nomor (prioritas yang sudah dicabut
        tidak tercetak lagi). Perintah yang diambil tidak dikirim dua kali.
        """
        if not device_id:
            return {"jobs": []}
        tugas = []
        for perintah_id, queue_id in cetak_ulang_anjungan.ambil_untuk_perangkat(device_id):
            try:
                info = services.queue.nomor_untuk_cetak_ulang(queue_id)
                ticket = replace(
                    services.ticket.susun(info, cetak_ulang=True), sisa_antrian=None
                )
                raster = None
                try:
                    raster = raster_tiket_anjungan(ticket)
                except Exception:
                    logger.exception("Gambar tiket cetak ulang %s gagal", info.queue_number)
                tugas.append(
                    {
                        "id": perintah_id,
                        "queue_number": info.queue_number,
                        "ticket_lines": ticket.baris_teks(),
                        "ticket_layout": tata_letak_tiket_anjungan(ticket),
                        "ticket_raster": raster,
                    }
                )
            except Exception:
                logger.exception("Perintah cetak ulang %s gagal disusun", perintah_id)
                cetak_ulang_anjungan.catat_hasil(
                    perintah_id, device_id, False, "Isi tiket gagal disusun di server."
                )
        return {"jobs": tugas}

    @app.post("/v1/kiosk/cetak-ulang/{perintah_id}/hasil")
    def cetak_ulang_hasil(
        perintah_id: int,
        hasil: HasilCetakUlang,
        device_id: str = Depends(perangkat_terpercaya),  # noqa: B008
    ):
        """Hasil cetak satu perintah, dilaporkan tablet sesudah mencoba mencetak."""
        if not device_id or not cetak_ulang_anjungan.catat_hasil(
            perintah_id, device_id, hasil.ok, hasil.message
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Perintah tidak ditemukan."
            )
        if perangkat is not None:
            try:
                perangkat.catat_printer(device_id, hasil.ok, hasil.message)
            except Exception:
                logger.warning("Status printer %s gagal dicatat", device_id, exc_info=True)
        return {"status": "ok"}

    @app.post("/v1/kiosk/restart-api")
    def restart_api(device_id: str = Depends(perangkat_terpercaya)):  # noqa: B008
        """
        Minta restart layanan API dari tablet yang sudah dipasangkan.

        Token bersama ditolak: siapa pun yang memegangnya dapat menyebut
        dirinya perangkat apa saja. Restart juga dibatasi sekali per
        JEDA_RESTART_API_DETIK, supaya tablet yang macet — atau orang iseng
        di depan tablet — tidak dapat membuat API terus-menerus mati.
        """
        from app.services.kiosk_server import jadwalkan_mulai_ulang_layanan_api

        if not device_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Restart API hanya untuk tablet yang dipasangkan dengan kode "
                    "dari Layanan Anjungan."
                ),
            )
        with restart_lock:
            sekarang = time.monotonic()
            if sekarang - restart_terakhir[0] < JEDA_RESTART_API_DETIK:
                sisa = int(JEDA_RESTART_API_DETIK - (sekarang - restart_terakhir[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"API baru saja dinyalakan. Coba lagi {sisa} detik lagi.",
                    headers={"Retry-After": str(sisa)},
                )
            try:
                jadwalkan_mulai_ulang_layanan_api()
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
                ) from exc
            restart_terakhir[:] = [sekarang]
        logger.warning("Restart API diminta oleh anjungan %s", device_id)
        return {"status": "restarting", "retry_after_seconds": 5}

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

    @app.get("/v1/kiosk/media-library", dependencies=[Depends(require_token)])
    def media_library():
        """
        Semua berkas media di server beserta ukuran dan waktu ubahnya, untuk
        "Salin dari server" di tablet. Berbeda dengan daftar putar: yang
        tidak dicentang pun terdaftar.
        """
        return [
            {
                "name": item.name,
                "size": item.stat().st_size,
                "modified_ms": int(item.stat().st_mtime * 1000),
                "video": item.suffix.lower() in _VIDEO_EXTENSIONS,
            }
            for item in pustaka_media()
        ]

    @app.get(
        "/v1/kiosk/media-library/{filename}",
        dependencies=[Depends(require_token)],
        response_class=FileResponse,
    )
    def media_library_file(filename: str):
        """Satu berkas dari pustaka media server (untuk disalin ke tablet)."""
        if not filename or filename != Path(filename).name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media tidak ditemukan.",
            )
        media = next((item for item in pustaka_media() if item.name == filename), None)
        if media is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media tidak ditemukan.",
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
            filename=f"antrianCRO-{apk.nama_versi}.apk",
        )

    @app.post("/v1/kiosk/tickets")
    def issue_ticket(
        request: TicketRequest,
        device_id: str = Depends(require_token),  # noqa: B008
        kunci_jeda: str = Depends(perangkat_terpercaya),  # noqa: B008
        x_app_version_code: Annotated[int | None, Header()] = None,
    ):
        """
        Terbitkan satu tiket, idempoten per (device_id, request_id).

        Permintaan ulang dengan pasangan yang sama menerima nomor yang sama
        — juga sesudah API dinyalakan ulang — dan tidak tertahan jeda
        maupun penutupan pendaftaran, karena nomornya sudah terbit. Pasangan
        yang sama dengan category_id lain ditolak 409. Lihat
        `QueueService.create_queue`.
        """
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
            queue_info = services.queue.create_queue(
                request.category_id,
                perangkat=device_id,
                kunci_jeda=kunci_jeda,
                request_id=str(request.request_id),
                prioritas_mandiri=request.priority,
            )
            ticket_warning = None
            ticket_layout = None
            ticket_raster = None
            try:
                # Anjungan Android hanya mengambil nomor: tiketnya tidak
                # menyebut berapa yang menunggu. Baris itu tetap ada pada
                # tiket yang dicetak dari Windows.
                ticket = replace(services.ticket.susun(queue_info), sisa_antrian=None)
                ticket_lines = ticket.baris_teks()
                ticket_layout = tata_letak_tiket_anjungan(ticket)
                issued_at = ticket.issued_at.isoformat()
                try:
                    # Tiket yang sudah digambar seperti di Windows; APK lama
                    # mengabaikannya dan tetap memakai ticket_layout.
                    ticket_raster = raster_tiket_anjungan(ticket)
                except Exception:
                    logger.exception("Gambar tiket %s gagal disusun", queue_info.queue_number)
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
                "ticket_raster": ticket_raster,
                "ticket_warning": ticket_warning,
                "cooldown_seconds": services.settings.get_int(
                    "kiosk.cooldown_seconds", 10
                ),
            }
            return response

    return app


def pilih_alamat_dengar(
    dari_env: str | None, tersimpan: str, alamat_lokal: list[str]
) -> list[str]:
    """
    Alamat tempat API mendengarkan.

    `ANTRIAN_KIOS_API_HOST` (bila diisi) menang, untuk pengembangan. Alamat
    pilihan admin dipakai bersama 127.0.0.1: pemeriksa kesehatan, status
    bar, dan pencegah proses ganda di komputer server mengetuk 127.0.0.1.
    Alamat yang tidak lagi dimiliki komputer ini (DHCP memberi IP lain)
    TIDAK membuat API mati: kembali ke semua antarmuka dengan peringatan,
    karena tablet yang tidak dapat mengambil nomor lebih buruk daripada
    API yang mendengar di antarmuka lebih banyak dari seharusnya.
    """
    if dari_env:
        return [dari_env]
    if tersimpan:
        if tersimpan in alamat_lokal:
            return [tersimpan, "127.0.0.1"]
        logger.warning(
            "Alamat API %s tidak ada di komputer ini (alamat: %s); "
            "API mendengar di semua antarmuka. Perbarui di Layanan Anjungan.",
            tersimpan,
            ", ".join(alamat_lokal) or "-",
        )
    return ["0.0.0.0"]


def _alamat_ipv4_komputer() -> list[str]:
    try:
        return sorted(
            {
                info[4][0]
                for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
            }
        )
    except OSError:
        return []


def _jalankan_uvicorn(app: FastAPI, alamat: list[str], port: int) -> None:
    if len(alamat) == 1:
        uvicorn.run(app, host=alamat[0], port=port, log_config=None)
        return
    # Beberapa alamat sekaligus: soket disiapkan sendiri, lalu diserahkan
    # ke satu server uvicorn.
    soket = []
    try:
        for host in alamat:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((host, port))
            soket.append(s)
        server = uvicorn.Server(uvicorn.Config(app, log_config=None))
        server.run(sockets=soket)
    finally:
        for s in soket:
            s.close()


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
        port = int(os.environ.get("ANTRIAN_KIOS_API_PORT", "8765"))
        try:
            from app.services.device_service import alamat_api_tersimpan

            tersimpan = alamat_api_tersimpan()
        except Exception:  # noqa: BLE001 - tanpa pilihan admin: perilaku lama
            logger.warning("Alamat API pilihan admin tidak terbaca", exc_info=True)
            tersimpan = ""
        alamat = pilih_alamat_dengar(
            os.environ.get("ANTRIAN_KIOS_API_HOST", "").strip() or None,
            tersimpan,
            _alamat_ipv4_komputer(),
        )
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
        threading.Thread(
            target=_jaga_paket_suara,
            args=(discovery_stop,),
            name="kiosk-paket-suara",
            daemon=True,
        ).start()
        logger.info(
            "API anjungan dimulai pada %s port %s; pencarian LAN UDP %s "
            "(revisi database %s)",
            ", ".join(alamat),
            port,
            discovery_port,
            current_revision(),
        )
        _jalankan_uvicorn(app, alamat, port)
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


#: Selang pemeriksaan paket suara terhadap nama loket aktif.
SELANG_PERIKSA_PAKET_DETIK = 60


def _jaga_paket_suara(berhenti: threading.Event) -> None:
    """
    Perbarui paket suara bila loket ditambah atau diganti namanya.

    Berjalan di API karena API selalu hidup di komputer server, tempat
    paket disimpan dan dibagikan; nama loket dapat diubah dari PC admin
    mana pun. Kegagalan hanya dicatat: suara bukan syarat pelayanan.
    """
    from app.services.paket_suara import (
        SuaraTurunError,
        nama_loket_aktif,
        perbarui_bila_perlu,
    )

    # Nama loket yang paketnya sudah gagal dibuat: tidak dicoba lagi tiap
    # menit (satu PowerShell penuh) sampai nama loketnya berubah.
    ditolak: list[str] | None = None
    while not berhenti.wait(SELANG_PERIKSA_PAKET_DETIK):
        try:
            nama_loket = sorted(nama_loket_aktif())
            if nama_loket == ditolak:
                continue
            baru = perbarui_bila_perlu(folder_paket(base_dir()), nama_loket)
        except SuaraTurunError as exc:
            ditolak = nama_loket
            logger.warning("Paket suara tidak diperbarui otomatis: %s", exc)
            continue
        except Exception:
            ditolak = nama_loket
            logger.warning("Paket suara gagal diperbarui otomatis", exc_info=True)
            continue
        if baru is not None:
            logger.info("Paket suara diperbarui otomatis: %s klip, %s", baru.jumlah, baru.suara)


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
