"""
Pengaturan aplikasi yang tersimpan di database.

Berbeda dari app.core.config yang mengatur lokasi file dan hanya dapat
diubah lewat environment variable. Yang di sini dapat diubah petugas ADMIN
dari dalam aplikasi.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlalchemy as sa

from app.core.database import session_scope
from app.core.errors import NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import ApplicationSetting, AuditAction
from app.services import audit_service
from app.services.auth_service import AuthService
from app.services.permissions import Permission

logger = get_logger("settings")

#: Nilai cadangan bila sebuah pengaturan belum ada di database, misalnya
#: karena database dibuat sebelum pengaturan tersebut diperkenalkan.
BAWAAN: dict[str, str] = {
    "backup.auto_enabled": "true",
    "backup.pg_dump_path": "",
    "backup.retention_days": "30",
    "dashboard.refresh_seconds": "30",
    "kiosk.cooldown_seconds": "10",
    "display.theme": "gelap",
    "display.title": "ANTRIAN PELAYANAN CRO",
    "display.info": "",
    "display.next_count": "3",
    "display.number_font_scale": "100",
    "display.sound_enabled": "true",
    "queue.max_call_attempts": "3",
    "queue.registration_open": "true",
    "queue.registration_closed_date": "",
    "survey.enabled": "true",
    "ticket.footer": "Silakan menunggu hingga nomor Anda dipanggil.",
    "ticket.printer": "pdf",
}

_BENAR = {"true", "1", "ya", "yes", "on"}


TEKS = "teks"
ANGKA = "angka"
BOOLEAN = "boolean"
PILIHAN = "pilihan"


@dataclass(frozen=True)
class Pengaturan:
    """
    Keterangan satu pengaturan: jenisnya, batasnya, dan namanya di layar.

    Dipakai dua arah. Layar administrasi memakainya untuk menampilkan
    kontrol yang tepat — kotak centang untuk boolean, daftar pilihan untuk
    yang pilihannya terbatas — dan `set()` memakainya untuk menolak nilai
    yang tidak masuk akal. UI dapat dilewati, service tidak, sehingga
    keduanya wajib bersandar pada keterangan yang sama.
    """

    kunci: str
    label: str
    keterangan: str
    jenis: str = TEKS
    #: Pasangan (nilai tersimpan, tulisan di layar) untuk jenis PILIHAN.
    pilihan: tuple[tuple[str, str], ...] = ()
    minimum: int | None = None
    maksimum: int | None = None
    #: Teks yang boleh dikosongkan. Bawaannya tidak boleh, karena judul layar
    #: maupun teks tiket yang kosong hanya membingungkan pembacanya.
    boleh_kosong: bool = False
    kelompok: str = "Umum"
    #: Tampil di layar Pengaturan. Dimatikan untuk nilai yang ditulis dan
    #: dibaca sistem sendiri: mengubahnya lewat formulir umum melewati
    #: aturan yang menyertainya, sehingga hasilnya tidak seperti yang
    #: dikira pengubahnya. Nilainya tetap sah dan tetap divalidasi — yang
    #: hilang hanya kotak isiannya.
    tampil: bool = True


#: Seluruh pengaturan yang dikenali aplikasi.
#:
#: Urutannya menentukan urutan tampil di layar, karena itu dikelompokkan
#: menurut layar yang dipengaruhinya, bukan menurut abjad.
SKEMA: tuple[Pengaturan, ...] = (
    Pengaturan(
        "ticket.printer",
        "Cara mencetak tiket",
        "Kegagalan mencetak tidak pernah membatalkan antrian; nomor sudah "
        "terbit sebelum tiket dicetak.",
        PILIHAN,
        pilihan=(
            ("pdf", "Simpan sebagai PDF di folder tiket"),
            ("system", "Cetak ke printer Windows"),
            ("none", "Tidak mencetak, nomor cukup disebutkan"),
        ),
        kelompok="Tiket",
    ),
    Pengaturan(
        "ticket.footer",
        "Teks penutup tiket",
        "Kalimat di bagian bawah tiket antrian.",
        TEKS,
        kelompok="Tiket",
    ),
    Pengaturan(
        "display.theme",
        "Tampilan layar antrian",
        "Bentuk papan yang menghadap pengunjung. Isinya sama pada semua pilihan — "
        "seluruh loket tetap tampil; yang berbeda hanya tata letak dan warnanya.",
        PILIHAN,
        # Daftar ini sengaja ditulis ulang di sini, tidak diimpor dari
        # app.ui: service tidak boleh bergantung pada lapisan tampilan.
        # Agar keduanya tidak diam-diam berbeda, ada test yang membandingkan
        # daftar ini dengan tema yang benar-benar ada.
        pilihan=(
            ("gelap", "Kartu Gelap (bawaan)"),
            ("terang", "Terang Minimal"),
            ("sorotan", "Sorotan"),
            ("split", "Split Informasi"),
            ("led", "Papan LED"),
        ),
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.title",
        "Judul layar antrian",
        "Tulisan besar di bagian atas layar yang menghadap pengunjung.",
        TEKS,
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.info",
        "Pengumuman layar antrian",
        "Tulisan pada panel kiri tema Split Informasi, misalnya jam layanan atau "
        "berkas yang perlu dibawa. Kosongkan bila tidak ada pengumuman.",
        TEKS,
        boleh_kosong=True,
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.next_count",
        "Jumlah nomor berikutnya",
        "Banyaknya nomor menunggu yang ikut ditampilkan di layar antrian.",
        ANGKA,
        minimum=0,
        maksimum=10,
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.number_font_scale",
        "Ukuran huruf nomor antrian (%)",
        "Membesarkan atau mengecilkan khusus nomor antrian di layar, tanpa "
        "mengubah ukuran tulisan lain. 100 adalah ukuran bawaan.",
        ANGKA,
        minimum=50,
        maksimum=200,
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.sound_enabled",
        "Bunyikan panggilan",
        "Komputer tanpa perangkat suara tetap berjalan normal, hanya tanpa bunyi.",
        BOOLEAN,
        kelompok="Layar Antrian",
    ),
    # Dua pengaturan berikut sengaja TIDAK tampil di layar Pengaturan.
    #
    # Keduanya wajib berubah bersama-sama: menutup pendaftaran berarti
    # menyetel "open" ke false SEKALIGUS menanggali penutupannya, karena
    # `pendaftaran_dibuka()` menganggap penutupan tanpa tanggal hari ini
    # sudah kedaluwarsa. Formulir umum hanya menyetel satu kunci, sehingga
    # mematikan "open" dari sana tidak menutup apa pun — admin mengira
    # pendaftaran berhenti padahal nomor terus terbit.
    #
    # Jalan yang benar sudah ada dan memakai keduanya sekaligus: tombol
    # pada layar Terbitkan Nomor, dan layar Tutup Hari.
    Pengaturan(
        "queue.registration_open",
        "Terima pendaftaran antrian baru",
        "Diubah lewat tombol pada layar Terbitkan Nomor atau layar Tutup "
        "Hari, bukan dari sini.",
        BOOLEAN,
        kelompok="Antrian",
        tampil=False,
    ),
    Pengaturan(
        "queue.registration_closed_date",
        "Tanggal pendaftaran terakhir ditutup",
        "Diisi dan dibaca otomatis oleh sistem. Begitu tanggal berganti, "
        "pendaftaran otomatis terbuka kembali walau lupa dibuka, supaya "
        "penutupan kemarin tidak diam-diam terbawa ke hari ini.",
        TEKS,
        boleh_kosong=True,
        kelompok="Antrian",
        tampil=False,
    ),
    Pengaturan(
        "queue.max_call_attempts",
        "Batas pemanggilan",
        "Setelah dipanggil sebanyak ini tanpa hadir, petugas diingatkan untuk "
        "menandainya tidak hadir.",
        ANGKA,
        minimum=1,
        maksimum=10,
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.cooldown_seconds",
        "Jeda ambil nomor di kios (detik)",
        "Menahan satu orang menekan tombol berulang kali dan memenuhi antrian "
        "dengan nomor kosong. Tidak berlaku bagi petugas pendaftaran, yang "
        "melayani rombongan datang bersamaan.",
        ANGKA,
        minimum=0,
        maksimum=300,
        kelompok="Antrian",
    ),
    Pengaturan(
        "survey.enabled",
        "Aktifkan survey kepuasan",
        "Bila dimatikan, layar survey dan tombol Minta Survey ikut padam.",
        BOOLEAN,
        kelompok="Survey",
    ),
    Pengaturan(
        "dashboard.refresh_seconds",
        "Jeda penyegaran ringkasan",
        "Dalam detik. Semakin kecil semakin sering database dibaca.",
        ANGKA,
        minimum=5,
        maksimum=3600,
        kelompok="Ringkasan Harian",
    ),
    Pengaturan(
        "backup.auto_enabled",
        "Backup otomatis harian",
        "Dibuat satu kali setiap hari saat aplikasi dibuka. Kegagalannya tidak "
        "pernah menghentikan aplikasi.",
        BOOLEAN,
        kelompok="Backup",
    ),
    Pengaturan(
        "backup.pg_dump_path",
        "Folder perkakas PostgreSQL",
        "Hanya dibutuhkan bila memakai PostgreSQL dan foldernya tidak ada di "
        r"PATH, misalnya C:\Program Files\PostgreSQL\17\bin. Kosongkan untuk "
        "SQLite.",
        TEKS,
        boleh_kosong=True,
        kelompok="Backup",
    ),
    Pengaturan(
        "backup.retention_days",
        "Lama backup disimpan (hari)",
        "Backup yang lebih tua akan dihapus otomatis. Nilai 0 mematikan "
        "penghapusan otomatis.",
        ANGKA,
        minimum=0,
        maksimum=3650,
        kelompok="Backup",
    ),
)

SKEMA_PER_KUNCI: dict[str, Pengaturan] = {p.kunci: p for p in SKEMA}


def kelompok_pengaturan() -> dict[str, list[Pengaturan]]:
    """
    Pengaturan dikelompokkan menurut layar yang dipengaruhinya.

    Yang `tampil=False` tidak ikut: nilainya dikelola sistem sendiri dan
    tidak boleh diubah lewat formulir umum.
    """
    hasil: dict[str, list[Pengaturan]] = {}
    for butir in SKEMA:
        if not butir.tampil:
            continue
        hasil.setdefault(butir.kelompok, []).append(butir)
    return hasil


def _validasi(kunci: str, nilai: str) -> str:
    """
    Pastikan nilai layak disimpan, dan kembalikan bentuk bakunya.

    Nilai yang salah ditolak di sini, bukan dibiarkan tersimpan lalu
    menggagalkan layar yang membacanya. `ticket.printer` bernilai "xyz"
    misalnya, baru akan terasa akibatnya saat tiket pertama gagal dicetak.
    """
    butir = SKEMA_PER_KUNCI.get(kunci)
    if butir is None:
        raise NotFoundError(f"Pengaturan {kunci!r} tidak dikenal.")

    nilai = nilai.strip()

    if butir.jenis == BOOLEAN:
        return "true" if nilai.lower() in _BENAR else "false"

    if butir.jenis == PILIHAN:
        sah = {v for v, _ in butir.pilihan}
        if nilai not in sah:
            raise ValidationError(
                f"{butir.label} hanya boleh bernilai: {', '.join(sorted(sah))}."
            )
        return nilai

    if butir.jenis == ANGKA:
        try:
            angka = int(nilai)
        except ValueError:
            raise ValidationError(f"{butir.label} harus berupa angka.") from None
        if butir.minimum is not None and angka < butir.minimum:
            raise ValidationError(
                f"{butir.label} tidak boleh kurang dari {butir.minimum}."
            )
        if butir.maksimum is not None and angka > butir.maksimum:
            raise ValidationError(
                f"{butir.label} tidak boleh lebih dari {butir.maksimum}."
            )
        return str(angka)

    if not nilai and not butir.boleh_kosong:
        raise ValidationError(f"{butir.label} tidak boleh dikosongkan.")
    return nilai


class SettingsService:
    """Pembacaan dan perubahan pengaturan aplikasi."""

    def __init__(self, auth: AuthService | None = None) -> None:
        self.auth = auth

    # -----------------------------------------------------------------
    # Pembacaan
    # -----------------------------------------------------------------
    #
    # Pembacaan sengaja tidak menuntut hak akses. Judul layar display dan
    # teks penutup tiket dibutuhkan oleh hampir semua peran, dan tidak ada
    # satu pun yang bersifat rahasia.

    def get(self, key: str, default: str | None = None) -> str:
        with session_scope() as session:
            baris = session.scalar(
                sa.select(ApplicationSetting).where(ApplicationSetting.key == key)
            )
            if baris is not None:
                return baris.value
        if default is not None:
            return default
        if key in BAWAAN:
            return BAWAAN[key]
        raise NotFoundError(f"Pengaturan {key!r} tidak dikenal.")

    def get_int(self, key: str, default: int | None = None) -> int:
        """Angka yang rusak diperlakukan seperti tidak ada, bukan menggagalkan layar."""
        try:
            return int(self.get(key, None if default is None else str(default)))
        except (ValueError, NotFoundError):
            if default is not None:
                return default
            return int(BAWAAN.get(key, "0"))

    def get_bool(self, key: str, default: bool = False) -> bool:
        try:
            return self.get(key).strip().lower() in _BENAR
        except NotFoundError:
            return default

    def all(self) -> dict[str, str]:
        with session_scope() as session:
            tersimpan = {
                r.key: r.value for r in session.scalars(sa.select(ApplicationSetting))
            }
        return {**BAWAAN, **tersimpan}

    # -----------------------------------------------------------------
    # Perubahan
    # -----------------------------------------------------------------

    def set(
        self, key: str, value: str, *, permission: Permission = Permission.CONFIG_MANAGE
    ) -> None:
        """
        Ubah satu pengaturan. Hanya ADMIN yang berhak, kecuali dipanggil
        lewat service lain yang sengaja memberi wewenang lebih sempit pada
        satu kunci tertentu (mis. `queue.registration_open`, yang juga
        boleh diubah petugas pendaftaran lewat `QueueService`).

        Nilainya divalidasi dan dibakukan lebih dahulu sesuai SKEMA, supaya
        pengaturan yang rusak tidak pernah sampai tersimpan.
        """
        if self.auth is None:
            raise NotFoundError("Perubahan pengaturan memerlukan sesi pengguna.")
        sesi = self.auth.require_permission(permission)
        value = _validasi(key, value)

        with session_scope() as session:
            baris = session.scalar(
                sa.select(ApplicationSetting).where(ApplicationSetting.key == key)
            )
            if baris is None:
                baris = ApplicationSetting(key=key, value=value)
                session.add(baris)
            else:
                baris.value = value

            audit_service.record(
                session,
                AuditAction.CHANGE_CONFIGURATION,
                user_id=sesi.user_id,
                entity_type="application_setting",
                pengaturan=key,
                nilai=value,
            )
        logger.info("Pengaturan %s diubah", key)
