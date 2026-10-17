"""
Perangkat Android yang menyambung ke aplikasi server.

Dua kelompok pemanggil dengan aturan berbeda:

* API (proses terpisah, tanpa login): memeriksa token perangkat, mencatat
  kontak dan hasil cetak, dan menukar kode pasang dengan token. Fungsi
  modul di bawah dipanggil langsung; yang menjaganya adalah token itu
  sendiri dan kode pasang yang sekali pakai.
* Layar Layanan Anjungan (ADMIN): daftar, kode pasang baru, ganti nama,
  cabut, hapus. Lewat `PerangkatService` dengan hak CONFIG_MANAGE.

Lihat docs/istilah.md untuk arti anjungan dan layar antrian.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import ApplicationSetting, AuditAction, KioskDevice, KioskPairingCode
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission

logger = get_logger("perangkat")

JENIS_ANJUNGAN = "anjungan"
JENIS_LAYAR_ANTRIAN = "layar_antrian"
JENIS_SAH = (JENIS_ANJUNGAN, JENIS_LAYAR_ANTRIAN)
LABEL_JENIS = {JENIS_ANJUNGAN: "Anjungan", JENIS_LAYAR_ANTRIAN: "Layar antrian"}

UMUR_KODE = timedelta(minutes=10)
#: Perangkat dianggap aktif bila menghubungi server dalam selang ini.
SELANG_AKTIF = timedelta(minutes=1)
#: Kontak yang sama tidak ditulis ulang lebih rapat dari ini: tablet
#: bertanya tiap beberapa detik, database tidak perlu tahu setiap kalinya.
SELANG_TULIS = timedelta(seconds=30)

#: Kunci pengaturan: apakah token bersama lama masih diterima. Bukan bagian
#: SKEMA Pengaturan, karena yang mengubahnya adalah layar Layanan Anjungan.
KUNCI_TOKEN_BERSAMA = "kiosk.token_bersama_aktif"
#: device_id anjungan yang membunyikan panggilan; kosong = semua anjungan diam.
#: Satu nilai, bukan centang per perangkat: dua anjungan yang sama-sama
#: bersuara mengulang pengumuman yang sama dengan selisih setengah detik.
KUNCI_ANJUNGAN_BERSUARA = "kiosk.suara_panggilan_perangkat"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PerangkatInfo:
    id: int
    device_id: str
    nama: str
    jenis: str
    dipasangkan: bool
    dicabut_pada: datetime | None
    terakhir_terlihat: datetime | None
    alamat_ip: str
    versi_nama: str
    versi_kode: int
    printer_ok: bool | None
    printer_pesan: str
    printer_waktu: datetime | None
    media_total: int | None = None
    media_tersalin: int | None = None
    media_byte: int | None = None
    media_waktu: datetime | None = None

    @property
    def teks_media(self) -> str:
        """Ringkasan salinan media untuk daftar perangkat; "" bila belum ada."""
        if self.media_total is None or self.media_tersalin is None:
            return ""
        ukuran = ""
        if self.media_byte:
            ukuran = f" · {self.media_byte / 1_048_576:.0f} MB"
        return f"{self.media_tersalin} dari {self.media_total} tersalin{ukuran}"

    @property
    def media_lengkap(self) -> bool:
        return (
            self.media_total is not None
            and self.media_tersalin is not None
            and self.media_tersalin >= self.media_total
        )

    @property
    def label_jenis(self) -> str:
        return LABEL_JENIS.get(self.jenis, self.jenis)

    @property
    def dicabut(self) -> bool:
        return self.dicabut_pada is not None

    def aktif(self, sekarang: datetime | None = None) -> bool:
        if self.terakhir_terlihat is None or self.dicabut:
            return False
        return (sekarang or clock.now()) - self.terakhir_terlihat <= SELANG_AKTIF


def _info(baris: KioskDevice) -> PerangkatInfo:
    return PerangkatInfo(
        id=baris.id,
        device_id=baris.device_id,
        nama=baris.nama,
        jenis=baris.jenis,
        dipasangkan=baris.token_hash is not None,
        dicabut_pada=baris.dicabut_pada,
        terakhir_terlihat=baris.terakhir_terlihat,
        alamat_ip=baris.alamat_ip,
        versi_nama=baris.versi_nama,
        versi_kode=baris.versi_kode,
        printer_ok=baris.printer_ok,
        printer_pesan=baris.printer_pesan,
        printer_waktu=baris.printer_waktu,
        media_total=baris.media_total,
        media_tersalin=baris.media_tersalin,
        media_byte=baris.media_byte,
        media_waktu=baris.media_waktu,
    )


def _jenis_sah(jenis: str | None) -> str:
    return jenis if jenis in JENIS_SAH else JENIS_ANJUNGAN


def _nama_bersih(nama: str | None, cadangan: str = "") -> str:
    return " ".join((nama or "").split())[:80] or cadangan


# =====================================================================
# Dipanggil API
# =====================================================================


def token_bersama_aktif() -> bool:
    """Bawaannya YA, supaya tablet lama tetap jalan sampai dipasangkan ulang."""
    with session_scope() as session:
        baris = session.scalar(
            sa.select(ApplicationSetting).where(ApplicationSetting.key == KUNCI_TOKEN_BERSAMA)
        )
        return baris is None or baris.value.strip().lower() not in {"false", "0", "tidak"}


def anjungan_bersuara() -> str:
    """device_id anjungan yang membunyikan panggilan, atau kosong."""
    with session_scope() as session:
        baris = session.scalar(
            sa.select(ApplicationSetting).where(
                ApplicationSetting.key == KUNCI_ANJUNGAN_BERSUARA
            )
        )
        return (baris.value or "").strip() if baris is not None else ""


def suara_layar_antrian_menyala() -> bool:
    """Pengaturan "suara layar antrian" (display.sound_enabled); bawaannya YA."""
    with session_scope() as session:
        baris = session.scalar(
            sa.select(ApplicationSetting).where(ApplicationSetting.key == "display.sound_enabled")
        )
        return baris is None or baris.value.strip().lower() not in {"false", "0", "tidak"}


def perangkat_dari_token(token: str) -> PerangkatInfo | None:
    """Perangkat pemilik token ini, termasuk yang sudah dicabut."""
    with session_scope() as session:
        baris = session.scalar(
            sa.select(KioskDevice).where(KioskDevice.token_hash == hash_token(token))
        )
        return _info(baris) if baris is not None else None


def perangkat_dicabut(device_id: str) -> bool:
    with session_scope() as session:
        return (
            session.scalar(
                sa.select(KioskDevice.id).where(
                    KioskDevice.device_id == device_id,
                    KioskDevice.dicabut_pada.is_not(None),
                )
            )
            is not None
        )


def keadaan_perangkat(device_id: str) -> tuple[bool, bool]:
    """
    (dicabut, dipasangkan) untuk device_id yang disebut header token bersama.

    Satu kueri untuk dua pertanyaan API: perangkat yang dicabut ditolak, dan
    perangkat yang sudah punya token sendiri tidak boleh "diwakili" token
    bersama — kalau boleh, siapa pun pemegang token bersama dapat menulis
    status printer/media atas nama tablet itu atau memakai jatah tebakan
    PIN-nya.
    """
    with session_scope() as session:
        baris = session.execute(
            sa.select(KioskDevice.dicabut_pada, KioskDevice.token_hash).where(
                KioskDevice.device_id == device_id
            )
        ).first()
    if baris is None:
        return False, False
    dicabut = baris.dicabut_pada is not None
    return dicabut, (not dicabut and baris.token_hash is not None)


def catat_kontak(
    device_id: str,
    *,
    nama: str = "",
    jenis: str = JENIS_ANJUNGAN,
    alamat_ip: str = "",
    versi_nama: str = "",
    versi_kode: int = 0,
) -> None:
    """
    Catat bahwa perangkat baru saja menghubungi server.

    Perangkat dengan token bersama ikut tercatat walau belum dipasangkan,
    supaya petugas melihat tablet mana yang masih perlu dipasangkan ulang.
    """
    device_id = device_id.strip()[:64]
    if not device_id:
        return
    sekarang = clock.now()
    with session_scope() as session:
        baris = session.scalar(sa.select(KioskDevice).where(KioskDevice.device_id == device_id))
        if baris is None:
            baris = KioskDevice(
                device_id=device_id,
                nama=_nama_bersih(nama, "Perangkat baru"),
                jenis=_jenis_sah(jenis),
            )
            session.add(baris)
        baris.terakhir_terlihat = sekarang
        baris.alamat_ip = (alamat_ip or "")[:45]
        baris.versi_nama = (versi_nama or "")[:20]
        baris.versi_kode = int(versi_kode or 0)


def daftar_anjungan() -> list[PerangkatInfo]:
    """
    Anjungan yang belum dicabut, untuk indikator di jendela petugas.

    Tanpa hak akses: setiap petugas berhak tahu tablet di depan pintu
    sedang tersambung atau tidak. Isinya hanya nama dan waktu terakhir
    terlihat — token tidak pernah ikut keluar dari sini.
    """
    with session_scope() as session:
        return [
            _info(baris)
            for baris in session.scalars(
                sa.select(KioskDevice).where(
                    KioskDevice.jenis == JENIS_ANJUNGAN,
                    KioskDevice.dicabut_pada.is_(None),
                )
            )
        ]


def catat_printer(device_id: str, ok: bool, pesan: str = "") -> None:
    with session_scope() as session:
        baris = session.scalar(sa.select(KioskDevice).where(KioskDevice.device_id == device_id))
        if baris is None:
            return
        baris.printer_ok = bool(ok)
        baris.printer_pesan = (pesan or "")[:200]
        baris.printer_waktu = clock.now()


def catat_media(device_id: str, total: int, tersalin: int, byte: int = 0) -> None:
    """Status salinan media dari tablet (berkas tersalin dari total)."""
    with session_scope() as session:
        baris = session.scalar(sa.select(KioskDevice).where(KioskDevice.device_id == device_id))
        if baris is None:
            return
        baris.media_total = max(0, int(total))
        baris.media_tersalin = max(0, min(int(tersalin), baris.media_total))
        baris.media_byte = max(0, int(byte))
        baris.media_waktu = clock.now()


def permintaan_segarkan_media(device_id: str) -> int:
    """
    Penanda permintaan "segarkan media sekarang" untuk tablet ini, dalam
    milidetik sejak epoch; 0 bila belum pernah diminta. Tablet menyegarkan
    salinannya bila nilainya berbeda dari yang terakhir ia tangani.
    """
    with session_scope() as session:
        baris = session.scalar(sa.select(KioskDevice).where(KioskDevice.device_id == device_id))
        if baris is None or baris.media_segarkan is None:
            return 0
        return int(baris.media_segarkan.timestamp() * 1000)


def pasangkan(kode: str, device_id: str, nama: str, jenis: str) -> str:
    """
    Tukar kode pasang yang masih berlaku dengan token khusus perangkat ini.

    Token asli dikembalikan sekali ini saja; server hanya menyimpan
    hash-nya. Perangkat yang dipasangkan ulang (tablet direset, misalnya)
    mendapat token baru, dan token lamanya berhenti berlaku saat itu juga.
    """
    kode = "".join(ch for ch in (kode or "") if ch.isdigit())
    device_id = (device_id or "").strip()[:64]
    if len(kode) != 6 or not device_id:
        raise ValidationError("Kode pasang harus 6 angka.")
    sekarang = clock.now()
    token = secrets.token_urlsafe(48)
    with session_scope() as session:
        # Pembaruan bersyarat, bukan baca-lalu-tandai: dua permintaan
        # bersamaan dengan kode yang sama hanya satu yang mendapat baris.
        dipakai = session.execute(
            sa.update(KioskPairingCode)
            .where(
                KioskPairingCode.kode == kode,
                KioskPairingCode.dipakai_pada.is_(None),
                KioskPairingCode.kedaluwarsa >= sekarang,
            )
            .values(dipakai_pada=sekarang)
            .execution_options(synchronize_session=False)
        )
        if not dipakai.rowcount:
            raise BusinessRuleError(
                "Kode pasang salah atau sudah kedaluwarsa. Buat kode baru di "
                "Layanan Anjungan pada komputer server."
            )

        baris = session.scalar(sa.select(KioskDevice).where(KioskDevice.device_id == device_id))
        if baris is None:
            baris = KioskDevice(device_id=device_id)
            session.add(baris)
        baris.nama = _nama_bersih(nama, baris.nama or "Perangkat baru")
        baris.jenis = _jenis_sah(jenis)
        baris.token_hash = hash_token(token)
        baris.dicabut_pada = None
        baris.terakhir_terlihat = sekarang
        session.flush()
        audit_service.record(
            session,
            AuditAction.PAIR_DEVICE,
            entity_type="kiosk_device",
            entity_id=baris.id,
            nama=baris.nama,
            jenis=baris.jenis,
        )
        if baris.jenis == JENIS_ANJUNGAN:
            _pilih_anjungan_bersuara_pertama(session, baris)
    logger.info("Perangkat dipasangkan: %s (%s)", nama, device_id)
    return token


def _pilih_anjungan_bersuara_pertama(session, baris: KioskDevice) -> None:
    """
    Pemasangan baru dengan satu anjungan saja langsung bersuara.

    Hanya bila pengaturannya BELUM PERNAH disentuh (barisnya tidak ada) dan
    tidak ada perangkat terpasang lain — anjungan kedua atau layar antrian
    Android. Pilihan admin, termasuk "Tidak ada" (baris berisi kosong),
    tidak pernah ditimpa. Layar antrian Windows tidak terdaftar sebagai
    perangkat; pemasangan yang memakainya mematikan suara layar itu atau
    memilih Tidak ada di kartu Perangkat.
    """
    sudah_diatur = session.scalar(
        sa.select(ApplicationSetting).where(ApplicationSetting.key == KUNCI_ANJUNGAN_BERSUARA)
    )
    if sudah_diatur is not None:
        return
    perangkat_lain = session.scalar(
        sa.select(sa.func.count())
        .select_from(KioskDevice)
        .where(
            KioskDevice.id != baris.id,
            KioskDevice.token_hash.is_not(None),
            KioskDevice.dicabut_pada.is_(None),
        )
    )
    if perangkat_lain:
        return
    session.add(ApplicationSetting(key=KUNCI_ANJUNGAN_BERSUARA, value=baris.device_id))
    audit_service.record(
        session,
        AuditAction.CHANGE_CONFIGURATION,
        entity_type="setting",
        key=KUNCI_ANJUNGAN_BERSUARA,
        value=baris.device_id,
    )
    logger.info("Anjungan pertama %s dipilih membunyikan panggilan", baris.device_id)


def batalkan_kode_aktif() -> int:
    """Hanguskan semua kode yang belum dipakai. Dipakai saat ada tebakan beruntun."""
    with session_scope() as session:
        hasil = session.execute(
            sa.update(KioskPairingCode)
            .where(KioskPairingCode.dipakai_pada.is_(None))
            .values(kedaluwarsa=clock.now() - timedelta(seconds=1))
        )
        return hasil.rowcount or 0


# =====================================================================
# Layar Layanan Anjungan
# =====================================================================


@dataclass(frozen=True)
class KodePasang:
    kode: str
    kedaluwarsa: datetime


class PerangkatService:
    """Pengelolaan perangkat oleh ADMIN di komputer server."""

    def __init__(self, auth: AuthService) -> None:
        self.auth = auth

    def daftar(self) -> list[PerangkatInfo]:
        """Yang aktif dulu, lalu yang terakhir terlihat paling baru."""
        self.auth.require_permission(Permission.CONFIG_MANAGE)
        with session_scope() as session:
            baris = session.scalars(sa.select(KioskDevice)).all()
            hasil = [_info(b) for b in baris]
        return sorted(
            hasil,
            key=lambda p: (p.dicabut, -(p.terakhir_terlihat or datetime.min).timestamp()),
        )

    def pin_diatur(self) -> bool:
        """Apakah PIN pengaturan anjungan sudah ada (isinya tidak pernah dibaca UI)."""
        self.auth.require_permission(Permission.CONFIG_MANAGE)
        from app.services import pin_anjungan

        return pin_anjungan.baca() is not None

    def atur_pin(self, pin: str) -> None:
        """Pasang atau ganti PIN pengaturan anjungan untuk SEMUA tablet."""
        sesi = self.auth.require_permission(Permission.CONFIG_MANAGE)
        from app.services import pin_anjungan

        pin_anjungan.simpan(pin_anjungan.buat(pin))
        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="application_setting",
                pengaturan=pin_anjungan.KUNCI,
                nilai="(PIN diganti)",
            )

    def hapus_pin(self) -> None:
        sesi = self.auth.require_permission(Permission.CONFIG_MANAGE)
        from app.services import pin_anjungan

        pin_anjungan.simpan(None)
        with session_scope() as session:
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="application_setting",
                pengaturan=pin_anjungan.KUNCI,
                nilai="(PIN dihapus)",
            )

    def segarkan_media(self, perangkat_id: int) -> None:
        """Minta satu anjungan menyegarkan salinan medianya sekarang."""
        self.auth.require_permission(Permission.CONFIG_MANAGE)
        with session_scope() as session:
            baris = session.get(KioskDevice, perangkat_id)
            if baris is None:
                raise NotFoundError("Perangkat tidak ditemukan.")
            if baris.dicabut_pada is not None:
                raise BusinessRuleError("Perangkat ini sudah dicabut.")
            baris.media_segarkan = clock.now()

    def buat_kode(self) -> KodePasang:
        sesi = self.auth.require_permission(Permission.CONFIG_MANAGE)
        sekarang = clock.now()
        kode = f"{secrets.randbelow(1_000_000):06d}"
        kedaluwarsa = sekarang + UMUR_KODE
        with session_scope() as session:
            session.add(KioskPairingCode(kode=kode, kedaluwarsa=kedaluwarsa))
            audit_service.record(
                session,
                AuditAction.PAIR_DEVICE,
                user_id=sesi.user_id,
                entity_type="kiosk_pairing_code",
                tahap="kode dibuat",
            )
        return KodePasang(kode=kode, kedaluwarsa=kedaluwarsa)

    def _ubah(self, perangkat_id: int, aksi: AuditAction, ubah) -> PerangkatInfo:
        sesi = self.auth.require_permission(Permission.CONFIG_MANAGE)
        with session_scope() as session:
            baris = session.get(KioskDevice, perangkat_id)
            if baris is None:
                raise NotFoundError("Perangkat tidak ditemukan.")
            ubah(baris)
            audit_service.record(
                session,
                aksi,
                user_id=sesi.user_id,
                entity_type="kiosk_device",
                entity_id=baris.id,
                nama=baris.nama,
            )
            return _info(baris)

    def ganti_nama(self, perangkat_id: int, nama: str) -> PerangkatInfo:
        nama = _nama_bersih(nama)
        if not nama:
            raise ValidationError("Nama perangkat tidak boleh kosong.")

        def ubah(baris: KioskDevice) -> None:
            baris.nama = nama

        return self._ubah(perangkat_id, AuditAction.RENAME_DEVICE, ubah)

    def cabut(self, perangkat_id: int) -> PerangkatInfo:
        """Token perangkat berhenti berlaku; perangkat lain tidak terganggu."""

        def ubah(baris: KioskDevice) -> None:
            baris.dicabut_pada = clock.now()
            baris.token_hash = None

        return self._ubah(perangkat_id, AuditAction.REVOKE_DEVICE, ubah)

    def hapus(self, perangkat_id: int) -> None:
        """Hanya yang sudah dicabut: perangkat aktif dicabut dulu, bukan hilang diam-diam."""
        sesi = self.auth.require_permission(Permission.CONFIG_MANAGE)
        with session_scope() as session:
            baris = session.get(KioskDevice, perangkat_id)
            if baris is None:
                return
            if baris.dicabut_pada is None:
                raise BusinessRuleError("Cabut perangkat ini dulu sebelum menghapusnya.")
            audit_service.record(
                session,
                AuditAction.DELETE_DEVICE,
                user_id=sesi.user_id,
                entity_type="kiosk_device",
                entity_id=baris.id,
                nama=baris.nama,
            )
            session.delete(baris)

    def token_bersama_aktif(self) -> bool:
        self.auth.require_permission(Permission.CONFIG_MANAGE)
        return token_bersama_aktif()

    def setel_token_bersama(self, aktif: bool) -> None:
        sesi = self.auth.require_permission(Permission.CONFIG_MANAGE)
        nilai = "true" if aktif else "false"
        with session_scope() as session:
            baris = session.scalar(
                sa.select(ApplicationSetting).where(ApplicationSetting.key == KUNCI_TOKEN_BERSAMA)
            )
            if baris is None:
                session.add(ApplicationSetting(key=KUNCI_TOKEN_BERSAMA, value=nilai))
            else:
                baris.value = nilai
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="setting",
                key=KUNCI_TOKEN_BERSAMA,
                value=nilai,
            )

    def anjungan_bersuara(self) -> str:
        self.auth.require_permission(Permission.CONFIG_MANAGE)
        return anjungan_bersuara()

    def suara_layar_antrian_menyala(self) -> bool:
        self.auth.require_permission(Permission.CONFIG_MANAGE)
        return suara_layar_antrian_menyala()

    def setel_anjungan_bersuara(self, device_id: str | None) -> None:
        """
        Pilih anjungan yang membunyikan panggilan; None atau kosong = tidak ada.

        Hanya anjungan yang dipasangkan dan belum dicabut: device_id tablet
        bertoken bersama diisi tablet itu sendiri, sehingga API tidak dapat
        memastikan tablet mana yang sebenarnya bertanya.
        """
        sesi = self.auth.require_permission(Permission.CONFIG_MANAGE)
        nilai = (device_id or "").strip()
        with session_scope() as session:
            if nilai:
                perangkat = session.scalar(
                    sa.select(KioskDevice).where(KioskDevice.device_id == nilai)
                )
                if perangkat is None:
                    raise NotFoundError("Perangkat tidak ditemukan.")
                info = _info(perangkat)
                if info.jenis != JENIS_ANJUNGAN or info.dicabut or not info.dipasangkan:
                    raise BusinessRuleError(
                        "Hanya anjungan yang sudah dipasangkan dan belum dicabut "
                        "yang dapat membunyikan panggilan."
                    )
            baris = session.scalar(
                sa.select(ApplicationSetting).where(
                    ApplicationSetting.key == KUNCI_ANJUNGAN_BERSUARA
                )
            )
            if baris is None:
                session.add(ApplicationSetting(key=KUNCI_ANJUNGAN_BERSUARA, value=nilai))
            else:
                baris.value = nilai
            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="setting",
                key=KUNCI_ANJUNGAN_BERSUARA,
                value=nilai,
            )
