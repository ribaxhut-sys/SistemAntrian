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

#: Posisi panel anjungan. Iklan di atas adalah bawaan: kartu layanan
#: setinggi tangan orang berdiri, iklan di atas kepala untuk antrean.
URUTAN_PANEL_IKLAN_ATAS = "iklan-atas"
URUTAN_PANEL_LAYANAN_ATAS = "layanan-atas"

#: Bentuk layar yang menghadap pengunjung. Yang dipilih adalah RUPA layar,
#: bukan resolusinya: orang yang memasang televisi mengenali layarnya dari
#: bentuknya, dan tidak seorang pun menghafal rasio aspek perangkat yang
#: baru saja digantung di dinding.
#:
#: "auto" adalah bawaan dan seharusnya cukup untuk hampir semua pemasangan
#: — papan mengukur layarnya sendiri. Pilihan lainnya ada untuk satu kasus
#: yang tidak dapat ditebak: panel LED yang menerima HDMI 1920x1080 lalu
#: memotong sepetak kecil darinya. Windows tetap melaporkan layar 16:9,
#: sementara yang benar-benar menyala berbentuk pita memanjang.
BENTUK_LAYAR_OTOMATIS = "auto"
BENTUK_LAYAR_LEBAR = "lebar"
BENTUK_LAYAR_MEMANJANG = "memanjang"
BENTUK_LAYAR_TEGAK = "tegak"

#: Bentuk yang sah sebagai penimpaan per mesin. "auto" tidak ikut: mesin
#: yang tidak berpendapat cukup tidak menyebut apa-apa, sama seperti
#: ANTRIAN_PRINTER yang kosong.
BENTUK_LAYAR_MANUAL = (
    BENTUK_LAYAR_LEBAR,
    BENTUK_LAYAR_MEMANJANG,
    BENTUK_LAYAR_TEGAK,
)

#: Nilai cadangan bila sebuah pengaturan belum ada di database, misalnya
#: karena database dibuat sebelum pengaturan tersebut diperkenalkan.
BAWAAN: dict[str, str] = {
    "backup.auto_enabled": "true",
    "backup.pg_dump_path": "",
    "backup.retention_days": "30",
    "backup.salinan_folder": "",
    "dashboard.refresh_seconds": "30",
    "kiosk.cooldown_seconds": "10",
    "kiosk.welcome_kind": "teks",
    "kiosk.welcome_text": "",
    "kiosk.welcome_file": "",
    "kiosk.welcome_slide_seconds": "10",
    "kiosk.info_ratio": "3",
    "kiosk.panel_order": "iklan-atas",
    "display.screen_shape": "auto",
    "display.theme": "kaca",
    "display.title": "ANTRIAN PELAYANAN CRO",
    "display.info": "",
    "display.next_count": "3",
    "display.list_rows": "5",
    "display.list_font_size": "0",
    "display.rotate_seconds": "3",
    "display.number_font_scale": "100",
    "display.sound_enabled": "true",
    "queue.max_call_attempts": "3",
    "queue.registration_open": "true",
    "queue.registration_closed_date": "",
    "survey.enabled": "true",
    "ticket.header": "BAPENDA DKI JAKARTA",
    "ticket.footer": "Silakan menunggu nomor Anda dipanggil.",
    "ticket.printer": "pdf",
    "ticket.geser_atas_mm": "0",
}

_BENAR = {"true", "1", "ya", "yes", "on"}


TEKS = "teks"
ANGKA = "angka"
BOOLEAN = "boolean"
PILIHAN = "pilihan"
BERKAS = "berkas"


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
    #: Satuan angka, ditulis DI DALAM kotak isiannya: "3 detik", bukan
    #: "Jeda pergantian halaman (detik)" pada namanya. Satuan yang menempel
    #: pada angkanya terbaca bersama angka itu — pada namanya, ia terbaca
    #: beberapa detik sebelumnya lalu terlupakan.
    satuan: str = ""
    #: Tulisan pengganti untuk nilai TERKECIL, ketika nilai itu berarti
    #: sesuatu dan bukan sekadar nol. "Otomatis" jauh lebih jelas daripada
    #: angka 0 yang artinya harus dicari dulu di keterangannya.
    nilai_khusus: str = ""


#: Seluruh pengaturan yang dikenali aplikasi.
#:
#: Urutannya menentukan urutan tampil di layar, karena itu dikelompokkan
#: menurut layar yang dipengaruhinya, bukan menurut abjad.
SKEMA: tuple[Pengaturan, ...] = (
    Pengaturan(
        "ticket.printer",
        "Cara mencetak tiket",
        "Berlaku untuk komputer yang tidak menyebut pencetaknya sendiri "
        "lewat ANTRIAN_PRINTER. Kegagalan mencetak tidak pernah membatalkan "
        "antrian; nomor sudah terbit sebelum tiket dicetak.",
        PILIHAN,
        pilihan=(
            ("pdf", "Simpan sebagai PDF di folder tiket"),
            ("system", "Cetak ke printer Windows"),
            ("none", "Tidak mencetak, nomor cukup disebutkan"),
        ),
        kelompok="Tiket",
    ),
    Pengaturan(
        "ticket.header",
        "Judul tiket",
        "Baris paling atas tiket antrian, di atas nama kantor. "
        "Kosongkan bila tiket tidak memerlukan judul.",
        TEKS,
        boleh_kosong=True,
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
        "ticket.geser_atas_mm",
        "Naikkan isi tiket",
        "Hanya untuk pencetak Windows. Pada IWare IW-J200, 1 mm saja sudah "
        "memotong judul — biarkan 0. Ruang kosong di atas judul diatur di "
        "driver POS80 (margin atas / unprintable / begin feed), bukan di sini.",
        ANGKA,
        minimum=0,
        maksimum=6,
        satuan="mm",
        nilai_khusus="Tidak digeser",
        kelompok="Tiket",
    ),
    Pengaturan(
        "display.screen_shape",
        "Bentuk layar antrian",
        "Biarkan Otomatis kecuali papannya terlihat keliru. Papan mengukur "
        "layarnya sendiri dan hampir selalu benar; yang tidak dapat ditebaknya "
        "adalah panel LED yang menerima gambar 16:9 lalu memotong sepetak "
        "memanjang darinya. Pilihan ini berlaku untuk KOMPUTER INI saja bila "
        "mesinnya menyebut ANTRIAN_BENTUK_LAYAR.",
        PILIHAN,
        pilihan=(
            ("auto", "Otomatis (disarankan)"),
            ("lebar", "Televisi biasa, lebih lebar daripada tinggi"),
            ("memanjang", "Papan memanjang, seperti pita di atas pintu"),
            ("tegak", "Layar berdiri, lebih tinggi daripada lebar"),
        ),
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.theme",
        "Tampilan layar antrian",
        "Bentuk papan yang menghadap pengunjung. Isinya sama pada semua pilihan — "
        "seluruh loket tetap tampil; yang berbeda hanya tata letak dan warnanya. "
        "Pada layar memanjang yang terpakai hanya WARNANYA: tata letak mana pun "
        "bersusun ke bawah, dan pita setinggi sejengkal tidak memuat susunan apa "
        "pun, sehingga papan menyusun sendiri kartunya berjajar.",
        PILIHAN,
        # Daftar ini sengaja ditulis ulang di sini, tidak diimpor dari
        # app.ui: service tidak boleh bergantung pada lapisan tampilan.
        # Agar keduanya tidak diam-diam berbeda, ada test yang membandingkan
        # daftar ini dengan tema yang benar-benar ada.
        pilihan=(
            ("kaca", "Kaca Malam (bawaan)"),
            ("bento", "Bento Terang"),
            ("led", "Papan LED"),
            ("fokus", "Fokus Nomor"),
            ("sorotan", "Sorotan"),
            ("split", "Split Informasi"),
            ("kontras", "Kontras Tinggi"),
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
        "Jumlah nomor berikutnya di papan kios",
        "Banyaknya nomor menunggu pada papan kecil di dalam anjungan. "
        "Televisi ruang tunggu memakai dua pengaturan di bawah ini.",
        ANGKA,
        minimum=0,
        maksimum=10,
        satuan="nomor",
        nilai_khusus="Tidak ditampilkan",
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.list_rows",
        "Baris nomor per kolom",
        "Setiap jenis layanan mendapat dua kolom, sehingga 5 baris berarti "
        "10 nomor per layanan pada satu halaman. Sisanya masuk halaman "
        "berikutnya. Baris yang tidak muat di layar otomatis dikurangi — "
        "huruf yang terpotong tidak menolong siapa pun.",
        ANGKA,
        minimum=1,
        maksimum=12,
        satuan="baris",
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.list_font_size",
        "Ukuran huruf nomor menunggu",
        "Isi 0 agar menyesuaikan sendiri dengan tinggi papan — itu yang "
        "disarankan. Angka lain diperlakukan sebagai batas ATAS: papan "
        "tetap memperkecilnya bila barisnya tidak muat, karena nomor yang "
        "terpotong lebih buruk daripada nomor yang sedikit lebih kecil.",
        ANGKA,
        minimum=0,
        maksimum=96,
        satuan="px",
        nilai_khusus="Otomatis",
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.rotate_seconds",
        "Jeda pergantian halaman",
        "Lama satu halaman daftar menunggu tampil sebelum berganti sendiri. "
        "Isi 0 bila halaman tidak boleh berpindah sendiri. Pengunjung "
        "membutuhkan waktu untuk mencari nomornya sendiri dari seberang "
        "ruangan; terlalu cepat membuat daftar ini tidak terbaca sama sekali.",
        ANGKA,
        minimum=0,
        maksimum=60,
        satuan="detik",
        nilai_khusus="Tidak berpindah sendiri",
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.number_font_scale",
        "Ukuran huruf nomor antrian",
        "Membesarkan atau mengecilkan khusus nomor antrian di layar, tanpa "
        "mengubah ukuran tulisan lain. 100 adalah ukuran bawaan.",
        ANGKA,
        minimum=50,
        maksimum=200,
        satuan="%",
        kelompok="Layar Antrian",
    ),
    Pengaturan(
        "display.sound_enabled",
        "Bunyikan panggilan",
        "Berlaku untuk komputer layar antrian dan loket. Anjungan ambil "
        "nomor sengaja tetap diam agar tidak berbunyi bersahutan dengan "
        "televisi; satu mesin dapat menyimpang dari pengaturan ini lewat "
        "ANTRIAN_SUARA. Komputer tanpa perangkat suara tetap berjalan "
        "normal, hanya tanpa bunyi.",
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
        satuan="kali",
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.cooldown_seconds",
        "Jeda ambil nomor di kios",
        "Menahan satu orang menekan tombol berulang kali dan memenuhi antrian "
        "dengan nomor kosong. Tidak berlaku bagi petugas pendaftaran, yang "
        "melayani rombongan datang bersamaan.",
        ANGKA,
        minimum=0,
        maksimum=300,
        satuan="detik",
        nilai_khusus="Tanpa jeda",
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.welcome_kind",
        "Tampilan panel anjungan",
        "Isi panel besar di atas tombol A/B/C sebelum pengunjung memilih "
        "layanan. Folder media memutar semua gambar dan video di "
        "media/kiosk bergiliran menurut nama file. Bila foldernya kosong "
        "atau berkasnya gagal, panel kembali ke teks.",
        PILIHAN,
        pilihan=(
            ("teks", "Teks sambutan"),
            ("media", "Folder media (gambar & video bergantian)"),
        ),
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.welcome_text",
        "Teks sambutan anjungan",
        "Ditampilkan bila jenisnya teks, dan sebagai cadangan bila folder "
        "media kosong atau gagal. Kosongkan untuk memakai teks bawaan.",
        TEKS,
        boleh_kosong=True,
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.welcome_file",
        "Tambah berkas ke folder anjungan",
        "Berkas disalin ke media/kiosk. Semua gambar dan video di folder "
        "itu diputar bergiliran (urut nama: 01_, 02_, …). Memilih berkas "
        "juga mengganti tampilan panel ke folder media. Tetap klik Simpan.",
        BERKAS,
        boleh_kosong=True,
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.welcome_slide_seconds",
        "Lama tampil tiap gambar",
        "Hanya untuk gambar di folder media. Video diputar sampai selesai "
        "lalu ganti ke berkas berikutnya. Satu gambar saja tampil terus.",
        ANGKA,
        minimum=3,
        maksimum=60,
        satuan="detik",
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.info_ratio",
        "Bentuk panel informasi anjungan",
        "Perbandingan lebar dan tinggi panel besar di atas tombol A/B/C. "
        "Gambar atau video sambutan yang perbandingannya sama akan memenuhi "
        "panel tanpa bidang kosong di tepinya. Ditetapkan di sini supaya "
        "bentuknya TIDAK ikut berubah ketika jenis layanan bertambah — yang "
        "mengalah kartu A/B/C, bukan panelnya. "
        "Diambil sedekat yang disanggupi layarnya. Panel tidak akan "
        "memendek melewati ukuran terbesar kartu layanan (sisanya hanya "
        "akan jadi bidang kosong di bawah kartu), dan tidak akan meninggi "
        "sampai kartunya kehabisan tempat. Pada layar 1920x1080 dengan "
        "tiga layanan, yang benar-benar bisa dicapai berkisar 2,6:1 "
        "sampai 3,4:1.",
        PILIHAN,
        pilihan=(
            ("2.5", "2,5 : 1 — panel setinggi mungkin"),
            ("3", "3 : 1 (disarankan)"),
            ("3.5", "3,5 : 1 — kartu layanan selapang mungkin"),
        ),
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.panel_order",
        "Posisi iklan dan kartu layanan",
        "Anjungan berdiri membagi layar dua: panel iklan/informasi dan "
        "kartu ambil nomor. Bawaan menaruh iklan di atas — kartu tetap "
        "setinggi tangan, iklan terbaca antrean di belakang. Tukar bila "
        "layarnya digantung rendah, supaya kartu tidak ada di lutut. "
        "Pintasan Ctrl+Shift+T di anjungan menulis nilai yang sama.",
        PILIHAN,
        pilihan=(
            (URUTAN_PANEL_IKLAN_ATAS, "Iklan di atas, layanan di bawah"),
            (URUTAN_PANEL_LAYANAN_ATAS, "Layanan di atas, iklan di bawah"),
        ),
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
        "Semakin kecil semakin sering database dibaca.",
        ANGKA,
        minimum=5,
        maksimum=3600,
        satuan="detik",
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
        r"PATH dan tidak terpasang di C:\Program Files\PostgreSQL (yang dicari "
        "otomatis). Kosongkan untuk SQLite.",
        TEKS,
        boleh_kosong=True,
        kelompok="Backup",
    ),
    Pengaturan(
        "backup.salinan_folder",
        "Folder salinan kedua",
        "Setiap backup juga disalin ke sini, misalnya disk D: atau flashdisk. "
        "Backup yang hanya ada di disk database ikut hilang bila disk itu "
        "rusak. Masa simpannya sama. Kosongkan bila tidak dipakai.",
        TEKS,
        boleh_kosong=True,
        kelompok="Backup",
    ),
    Pengaturan(
        "backup.retention_days",
        "Lama backup disimpan",
        "Backup yang lebih tua akan dihapus otomatis. Nilai 0 mematikan "
        "penghapusan otomatis.",
        ANGKA,
        minimum=0,
        maksimum=3650,
        satuan="hari",
        nilai_khusus="Tidak dihapus otomatis",
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
        if kunci == "kiosk.welcome_kind" and nilai in {"gambar", "video"}:
            # Nilai lama: gambar atau video terpisah sekarang sama artinya
            # dengan seluruh folder media.
            nilai = "media"
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

    def tukar_urutan_panel_kios(self) -> str:
        """
        Anjungan menukar posisi iklan dan kartu layanan.

        Mesin kios tidak punya CONFIG_MANAGE — komputernya publik — tetapi
        menukar tata letak adalah perbuatan mesin itu sendiri, sama seperti
        mengambil nomor. Hak QUEUE_CREATE cukup, dan nilainya satu untuk
        seluruh sistem: kantor ini punya satu anjungan berdiri.
        """
        sekarang = self.get("kiosk.panel_order", URUTAN_PANEL_IKLAN_ATAS)
        baru = (
            URUTAN_PANEL_LAYANAN_ATAS
            if sekarang != URUTAN_PANEL_LAYANAN_ATAS
            else URUTAN_PANEL_IKLAN_ATAS
        )
        self.set(
            "kiosk.panel_order",
            baru,
            permission=Permission.QUEUE_CREATE,
        )
        return baru
