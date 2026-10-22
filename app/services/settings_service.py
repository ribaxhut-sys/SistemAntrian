"""
Pengaturan aplikasi yang tersimpan di database.

Berbeda dari app.core.config yang mengatur lokasi file dan hanya dapat
diubah lewat environment variable. Yang di sini dapat diubah petugas ADMIN
dari dalam aplikasi.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import sqlalchemy as sa

from app.core.database import session_scope
from app.core.errors import NotFoundError, ValidationError
from app.core.logger import get_logger
from app.models import ApplicationSetting, AuditAction
from app.services import audit_service, daftar_putar
from app.services.auth_service import AuthService
from app.services.permissions import Permission

logger = get_logger("settings")

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
    "laporan.mingguan_aktif": "false",
    "laporan.mingguan_folder": "",
    "dashboard.refresh_seconds": "30",
    "sesi.idle_menit": "15",
    "kiosk.cooldown_seconds": "10",
    "kiosk.welcome_kind": "teks",
    "kiosk.welcome_text": "",
    "kiosk.subjudul": "",
    "kiosk.welcome_file": "",
    "kiosk.welcome_slide_seconds": "10",
    "kiosk.posisi_loket": "otomatis",
    "kiosk.daftar_putar": "",
    "kiosk.suara_video": "false",
    "kiosk.iklan_layar_penuh_detik": "60",
    "kiosk.iklan_putaran": "2",
    "kiosk.animasi_kembali": "true",
    "kiosk.animasi_mulai_detik": "2",
    "kiosk.animasi_nomor_menunggu": "true",
    "kiosk.panggilan_hentikan_iklan": "true",
    "kiosk.animasi_iklan_muncul": "true",
    "kiosk.tema": "biru",
    "kiosk.tema_agustus": "true",
    "display.screen_shape": "auto",
    "display.theme": "kaca",
    "display.info": "",
    "display.next_count": "3",
    "display.list_rows": "5",
    "display.list_font_size": "0",
    "display.rotate_seconds": "3",
    "display.number_font_scale": "100",
    "display.sound_enabled": "true",
    "display.loket_tampil": "petugas",
    "queue.max_call_attempts": "3",
    "queue.rasio_prioritas": "3",
    "kiosk.prioritas_aktif": "true",
    "queue.registration_open": "true",
    "queue.registration_closed_date": "",
    "survey.enabled": "true",
    "privasi.retensi_pengaduan_bulan": "24",
    "catatan.frasa_bawaan": "",
    "ticket.footer": "Silakan menunggu nomor Anda dipanggil.",
    "ticket.printer": "pdf",
    "ticket.geser_atas_mm": "0",
    "ticket.turun_anjungan_mm": "4",
}

_BENAR = {"true", "1", "ya", "yes", "on"}


TEKS = "teks"
ANGKA = "angka"
BOOLEAN = "boolean"
PILIHAN = "pilihan"
BERKAS = "berkas"
DAFTAR_PUTAR = "daftar_putar"
#: Teks beberapa baris (satu butir per baris).
TEKS_BANYAK = "teks_banyak"


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
        "ticket.turun_anjungan_mm",
        "Turunkan isi tiket anjungan",
        "Hanya untuk tiket dari tablet anjungan Android. Tablet mencetak "
        "langsung tanpa driver POS80, jadi tidak mendapat ruang kosong di "
        "kepala kertas seperti tiket Windows. Naikkan bila judul terlalu "
        "mepet ke atas.",
        ANGKA,
        minimum=0,
        maksimum=15,
        satuan="mm",
        nilai_khusus="Tidak diturunkan",
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
        "display.loket_tampil",
        "Loket yang ditampilkan",
        "Loket tanpa petugas login disembunyikan dari layar antrian dan "
        "anjungan; yang masih memanggil nomor tetap tampil.",
        PILIHAN,
        pilihan=(
            ("petugas", "Hanya yang ada petugasnya (disarankan)"),
            ("semua", "Semua loket aktif"),
        ),
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
        kelompok="Nomor Layar Antrian",
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
        kelompok="Nomor Layar Antrian",
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
        kelompok="Nomor Layar Antrian",
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
        kelompok="Nomor Layar Antrian",
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
        kelompok="Nomor Layar Antrian",
    ),
    Pengaturan(
        "display.sound_enabled",
        "Bunyikan panggilan",
        "Berlaku untuk komputer layar antrian dan loket. Anjungan ambil "
        "nomor tetap diam agar tidak berbunyi bersahutan dengan televisi, "
        "kecuali satu anjungan yang dipilih di Layanan Anjungan → Perangkat "
        "sebagai pengganti sementara; satu mesin dapat menyimpang dari pengaturan ini lewat "
        "ANTRIAN_SUARA. Komputer tanpa perangkat suara tetap berjalan "
        "normal, hanya tanpa bunyi.",
        BOOLEAN,
        kelompok="Suara Panggilan",
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
        "queue.rasio_prioritas",
        "Rasio nomor prioritas",
        "Setiap sekian nomor prioritas (lansia, disabilitas, ibu hamil) yang "
        "dipanggil beruntun, satu nomor biasa disisipkan supaya tidak menunggu "
        "tanpa batas. Isi 0 bila prioritas selalu didahulukan.",
        ANGKA,
        minimum=0,
        maksimum=20,
        satuan="nomor",
        nilai_khusus="Prioritas selalu lebih dulu",
        kelompok="Antrian",
    ),
    Pengaturan(
        "kiosk.prioritas_aktif",
        "Pilihan prioritas di anjungan",
        "Menampilkan kotak \"Saya lansia / disabilitas / ibu hamil\" di anjungan. "
        "Nomor yang ditandai pengunjung diperiksa petugas di loket dan dapat "
        "dicabut.",
        BOOLEAN,
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
        "kiosk.subjudul",
        "Subjudul anjungan",
        "Satu baris kecil di bawah judul, misalnya nama kantor atau jam "
        "layanan. Kosongkan bila tidak perlu.",
        TEKS,
        boleh_kosong=True,
        kelompok="Anjungan",
    ),
    Pengaturan(
        "kiosk.welcome_kind",
        "Tampilan panel anjungan",
        "Isi panel besar di atas tombol A/B/C sebelum pengunjung memilih "
        "layanan. Folder media memutar gambar dan video yang dicentang di "
        "Daftar putar media, bergiliran. Bila tidak ada yang dapat diputar, "
        "panel kembali ke teks.",
        PILIHAN,
        pilihan=(
            ("teks", "Teks sambutan"),
            ("media", "Folder media (gambar & video bergantian)"),
        ),
        kelompok="Panel Anjungan",
    ),
    Pengaturan(
        "kiosk.welcome_text",
        "Teks sambutan anjungan",
        "Ditampilkan bila jenisnya teks, dan sebagai cadangan bila folder "
        "media kosong atau gagal. Kosongkan untuk memakai teks bawaan.",
        TEKS,
        boleh_kosong=True,
        kelompok="Panel Anjungan",
    ),
    Pengaturan(
        "kiosk.welcome_file",
        "Tambah berkas ke folder anjungan",
        "Berkas disalin ke media/kiosk dan masuk ke ujung Daftar putar "
        "media dalam keadaan dicentang. Memilih berkas juga mengganti "
        "tampilan panel ke folder media. Tetap klik Simpan.",
        BERKAS,
        boleh_kosong=True,
        kelompok="Panel Anjungan",
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
        kelompok="Panel Anjungan",
    ),
    Pengaturan(
        "kiosk.daftar_putar",
        "Daftar putar media",
        "Centang gambar atau video yang diputar di anjungan, lalu atur "
        "urutannya dengan Naik/Turun. Video diputar sampai selesai; satu "
        "video saja diulang terus. Yang tidak dicentang tetap "
        "tersimpan di folder dan dapat dinyalakan lagi kapan saja. "
        "Atur jadwal… membatasi tanggal tayang, lama tampil tiap gambar, dan "
        "tempat tampilnya: panel atas, layar penuh, atau keduanya.",
        DAFTAR_PUTAR,
        boleh_kosong=True,
        kelompok="Iklan Anjungan",
    ),
    Pengaturan(
        "kiosk.suara_video",
        "Suara video anjungan",
        "Bila dimatikan, video di anjungan diputar tanpa suara. Sebaiknya "
        "tetap mati bila anjungan dekat layar antrian, supaya suara iklan "
        "tidak menutupi panggilan nomor. Selama pengunjung sedang memilih "
        "layanan sampai tiketnya keluar, video selalu dibisukan.",
        BOOLEAN,
        kelompok="Iklan Anjungan",
    ),
    Pengaturan(
        "kiosk.animasi_kembali",
        "Animasi saat kembali ke antrian",
        "Setelah iklan layar penuh, tiga panel anjungan masuk dari arah acak. "
        "Dilewati otomatis bila animasi dimatikan di pengaturan Android tablet.",
        BOOLEAN,
        kelompok="Perilaku Iklan",
    ),
    Pengaturan(
        "kiosk.animasi_iklan_muncul",
        "Animasi saat iklan akan muncul",
        "Sekitar 1,5 detik sebelum iklan layar penuh mulai, tiga panel "
        "(judul dan loket, pilihan layanan, hasil nomor) keluar ke arah acak "
        "lalu iklan muncul. Disentuh pada saat itu, panel kembali dan iklan "
        "dibatalkan. Dilewati bila animasi dimatikan di Android tablet atau "
        "waktu menganggur kurang dari 5 detik.",
        BOOLEAN,
        kelompok="Perilaku Iklan",
    ),
    Pengaturan(
        "kiosk.panggilan_hentikan_iklan",
        "Panggilan menghentikan iklan",
        "Saat petugas memanggil atau memanggil ulang sebuah nomor, iklan layar "
        "penuh langsung berhenti, tampilan antrian muncul, dan nomor itu "
        "ditampilkan besar selama beberapa detik. Waktu menganggur dihitung "
        "ulang dari nol sesudahnya.",
        BOOLEAN,
        kelompok="Perilaku Iklan",
    ),
    Pengaturan(
        "kiosk.animasi_nomor_menunggu",
        "Animasi nomor menunggu",
        "Nomor menunggu muncul satu per satu: baris demi baris, dan tiap nomor "
        "dengan gaya acak (naik, mekar, atau geser dari samping). Berlaku saat "
        "panel muncul, saat halaman berganti, dan saat kembali dari iklan. "
        "Dilewati otomatis bila animasi dimatikan di pengaturan Android tablet.",
        BOOLEAN,
        kelompok="Perilaku Iklan",
    ),
    Pengaturan(
        "kiosk.animasi_mulai_detik",
        "Animasi mulai sebelum iklan berakhir",
        "Pada putaran iklan yang terakhir, iklan meredup dan tiga panel mulai "
        "masuk sekian detik sebelum berkas terakhir selesai, jadi bagian akhir "
        "iklan bertumpuk dengan animasi. Isi 0 agar animasi baru mulai setelah "
        "iklan selesai.",
        ANGKA,
        minimum=0,
        maksimum=5,
        satuan="detik",
        nilai_khusus="Setelah iklan selesai",
        kelompok="Perilaku Iklan",
    ),
    Pengaturan(
        "kiosk.iklan_putaran",
        "Putaran iklan layar penuh",
        "Iklan layar penuh berputar sebanyak ini (satu putaran = seluruh daftar "
        "putar layar penuh diputar sekali), lalu kembali ke tampilan antrian dan "
        "menunggu waktu menganggur lagi sebelum muncul kembali. Isi 0 agar "
        "berputar terus sampai disentuh.",
        ANGKA,
        minimum=0,
        maksimum=10,
        satuan="putaran",
        nilai_khusus="Berputar terus",
        kelompok="Perilaku Iklan",
    ),
    Pengaturan(
        "kiosk.iklan_layar_penuh_detik",
        "Iklan layar penuh saat menganggur",
        "Bila tablet tidak disentuh selama ini, iklan diperbesar memenuhi "
        "layar. Sentuhan apa pun mengembalikan pilihan layanan. Hanya "
        "berlaku bila daftar putar media sedang berputar.",
        ANGKA,
        minimum=0,
        maksimum=600,
        satuan="detik",
        nilai_khusus="Mati",
        kelompok="Iklan Anjungan",
    ),
    Pengaturan(
        "kiosk.posisi_loket",
        "Posisi baris loket di anjungan",
        "Letak baris NOMOR DI LOKET (nomor tiap loket) pada tablet "
        "anjungan. Otomatis: pindah ke panel bawah bila panel atas memutar "
        "iklan, kembali ke panel atas bila tidak ada iklan atau iklannya "
        "gagal diputar. Sembunyikan bila layar antrian TV sudah terlihat "
        "dari depan anjungan. Tablet dapat menimpa pilihan ini di "
        "Pengaturan tablet.",
        PILIHAN,
        pilihan=(
            ("otomatis", "Otomatis mengikuti iklan (bawah bila ada iklan)"),
            ("bawah", "Pindahkan loket ke panel bawah"),
            ("atas", "Pindahkan loket ke panel atas"),
            ("sembunyi", "Sembunyikan baris loket"),
        ),
        kelompok="Anjungan",
    ),
    Pengaturan(
        "kiosk.tema",
        "Tema anjungan",
        "Warna tampilan tablet anjungan. Kontras tinggi memakai hitam-kuning "
        "dan huruf lebih besar untuk pengunjung lansia atau lobi yang silau. "
        "Tablet dapat menimpa pilihan ini di Pengaturan tablet.",
        PILIHAN,
        pilihan=(
            ("biru", "Biru instansi"),
            ("hijau", "Hijau segar"),
            ("kontras", "Kontras tinggi"),
            ("gelap", "Gelap elegan"),
            ("merah_putih", "Merah putih (perayaan)"),
        ),
        kelompok="Anjungan",
    ),
    Pengaturan(
        "kiosk.tema_agustus",
        "Merah putih otomatis setiap Agustus",
        "Selama bulan Agustus anjungan memakai tema merah putih, lalu "
        "kembali ke tema di atas pada 1 September tanpa perlu diubah.",
        BOOLEAN,
        kelompok="Anjungan",
    ),
    Pengaturan(
        "survey.enabled",
        "Aktifkan survey kepuasan",
        "Bila dimatikan, layar survey dan tombol Minta Survey ikut padam.",
        BOOLEAN,
        kelompok="Survey",
    ),
    Pengaturan(
        "privasi.retensi_pengaduan_bulan",
        "Masa simpan identitas pelapor",
        "Sesudah masa ini, nama, nomor pelanggan, telepon, email, dan alamat "
        "pada lembar pengaduan dikosongkan otomatis. Isi pengaduan dan catatan "
        "petugas tetap disimpan untuk laporan. Dihitung dari tanggal "
        "antriannya, diperiksa saat aplikasi dibuka dan saat tanggal berganti.",
        ANGKA,
        minimum=0,
        maksimum=120,
        satuan="bulan",
        nilai_khusus="Disimpan selamanya",
        kelompok="Pengaduan",
    ),
    Pengaturan(
        "catatan.frasa_bawaan",
        "Kalimat cepat bawaan catatan petugas",
        "Satu kalimat per baris (maksimal 8, masing-masing 80 karakter). "
        "Dipakai jenis layanan yang kolom \"Kalimat Cepat Catatan\"-nya "
        "dikosongkan. Kosongkan untuk memakai daftar bawaan aplikasi.",
        TEKS_BANYAK,
        boleh_kosong=True,
        kelompok="Pengaduan",
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
        "sesi.idle_menit",
        "Kunci layar setelah menganggur",
        "Layar petugas dikunci dan meminta kata sandi bila tidak ada aktivitas "
        "selama ini. Isi 0 untuk mematikan.",
        ANGKA,
        minimum=0,
        maksimum=480,
        satuan="menit",
        kelompok="Keamanan",
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
        "laporan.mingguan_aktif",
        "Laporan mingguan otomatis",
        "Saat admin atau supervisor membuka aplikasi, PDF laporan minggu lalu "
        "(Senin sampai Minggu) dibuat sekali bila belum ada.",
        BOOLEAN,
        kelompok="Laporan",
    ),
    Pengaturan(
        "laporan.mingguan_folder",
        "Folder laporan mingguan",
        "Tempat PDF laporan mingguan disimpan, di komputer yang membukanya. "
        "Kosongkan untuk folder laporan-mingguan di samping data aplikasi.",
        TEKS,
        boleh_kosong=True,
        kelompok="Laporan",
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

    if butir.jenis == DAFTAR_PUTAR:
        return daftar_putar.baku(nilai)

    if butir.jenis == TEKS_BANYAK:
        if kunci == "catatan.frasa_bawaan":
            from app.services.note_service import daftar_frasa, periksa_frasa

            periksa_frasa(nilai)
            return "\n".join(daftar_frasa(nilai))
        return nilai

    if not nilai and not butir.boleh_kosong:
        raise ValidationError(f"{butir.label} tidak boleh dikosongkan.")
    return nilai


@dataclass(frozen=True)
class CuplikanPengaturan:
    """Satu hasil baca konsisten agar endpoint cepat tidak membuat query per kunci."""

    nilai: Mapping[str, str]

    def get(self, key: str, default: str | None = None) -> str:
        if key in self.nilai:
            return self.nilai[key]
        if default is not None:
            return default
        raise NotFoundError(f"Pengaturan {key!r} tidak dikenal.")

    def get_int(self, key: str, default: int | None = None) -> int:
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

    def cuplikan(self) -> CuplikanPengaturan:
        """Baca semua kunci sekali agar satu respons memakai keadaan yang sama."""
        return CuplikanPengaturan(self.all())

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
