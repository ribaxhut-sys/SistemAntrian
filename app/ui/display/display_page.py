"""Layar antrian untuk pengunjung."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core import clock
from app.core.logger import get_logger
from app.models import QueueStatus
from app.services.queue_service import DisplayCounterState, DisplayState, LABEL_STATUS, QueueService
from app.services.settings_service import SettingsService
from app.services.sound_service import SoundPlayer, suara_diaktifkan
from app.ui.common import jalankan_aman
from app.ui.display.tema import (
    BENTO,
    FOKUS,
    KISI,
    SOROTAN,
    SPLIT,
    TABEL,
    TEMA_BAWAAN,
    Palet,
    palet_untuk,
)
from app.ui.kiosk.sambutan import PanelSambutanKios

logger = get_logger("ui.display")

#: Selang penyegaran. Layar ini menghadap pengunjung yang sedang menunggu,
#: sehingga jeda beberapa detik sudah terasa lama.
SELANG_SEGAR_MS = 2_000

#: Jam berdetik sendiri, terpisah dari penyegaran data. Menyatukan keduanya
#: berarti memilih antara jam yang melompat dua detik sekali atau membebani
#: database sekali per detik.
SELANG_JAM_MS = 1_000

#: Lama satu arah transisi pudar saat panel informasi papan kios berganti
#: isi — baik karena pengunjung menyentuh sebuah layanan maupun karena
#: kembali ke teks sambutan. Berpindah begitu saja terbaca sebagai kedipan;
#: pudar-keluar lalu pudar-masuk terasa sebagai pergantian yang disengaja.
DURASI_FADE_INFO_KIOS_MS = 300

#: Teks panel informasi papan kios sebelum pengunjung menyentuh layanan
#: apa pun, dan sesudah ia kembali ke kisi pilihan.
TEKS_SAMBUTAN_KIOS = "Sentuh salah satu layanan di bawah untuk mengambil nomor."

#: Halaman terbanyak yang ikut diputar pada daftar menunggu.
#:
#: Hari ramai meninggalkan ratusan orang menunggu, dan memutar dua puluh
#: halaman berarti satu siklus lebih dari semenit — pengunjung yang mencari
#: nomornya sudah menyerah jauh sebelum halamannya kembali. Sisanya disebut
#: sebagai jumlah ("dan 47 lainnya"), yang lebih jujur daripada rotasi yang
#: tidak pernah sampai kepadanya.
MAKS_HALAMAN = 5

#: Kolom terbanyak pada kisi daftar menunggu, untuk panel yang melintang
#: selebar layar. Lebih dari ini, nomor lima huruf mulai berdempetan pada
#: televisi 1080p.
KOLOM_DAFTAR = 5

#: Kolom untuk tema yang menaruh panel ini di kolom kanan yang sempit.
#: Sorotan dan Split hanya menyisakan sekitar 40% lebar layar untuknya,
#: dan lima kolom nomor di ruang selebar itu saling menempel.
KOLOM_DAFTAR_SEMPIT = 2

#: Kolom nomor untuk SETIAP jenis layanan.
#:
#: Panel ini lebar dan pendek — sekitar 1800x400 pada televisi 1080p —
#: sehingga menumpuk nomor ke bawah menghabiskan sisi yang langka dan
#: menyia-nyiakan sisi yang berlimpah. Dua kolom memakai lebarnya, dan
#: barisnya tetap cukup tinggi untuk memuat hurufnya utuh.
#:
#: Tiga, dengan tiga jenis layanan, berarti sembilan kolom pada 1800px:
#: 200px per kolom, sedangkan nomor lima huruf sudah memakan 160px.
KOLOM_PER_LAYANAN = 2

#: Kolom nomor per jenis layanan pada papan yang panelnya sempit.
#:
#: Tema Sorotan dan Split hanya menyisakan sekitar 40% lebar layar untuk
#: panel ini. Tiga jenis layanan kali dua kolom berarti enam kolom pada
#: lebar itu — sekitar 120px per kolom, sedangkan nomor lima huruf sudah
#: memakan lebih dari itu, dan huruf terakhirnya terpotong.
KOLOM_PER_LAYANAN_SEMPIT = 1

#: Padding dan tepi kartu nomor, dipakai bersama oleh stylesheet dan
#: perhitungan tinggi barisnya. Keduanya WAJIB memakai angka yang sama;
#: berbeda sedikit saja, huruf terpotong tanpa ada yang tahu sebabnya.
PADDING_NOMOR_Y = 8
TEPI_NOMOR = 2

#: Font terkecil yang masih pantas dibaca dari seberang ruangan. Di bawah
#: ini, papan berhenti mengecilkan huruf dan mulai mengurangi barisnya —
#: lebih baik satu halaman lagi daripada nomor yang tidak terbaca.
FONT_DAFTAR_MIN = 18

#: Jenis layanan terbanyak yang masih dapat dijadikan kolom sendiri-sendiri.
#:
#: Di atas ini kolomnya terlalu sempit untuk memuat nomor lima huruf, dan
#: daftar gabungan yang berhalaman justru lebih terbaca daripada tujuh
#: kolom yang semuanya terpotong. Kantor dengan sebanyak itu jenis layanan
#: memang tidak dapat menampilkan semuanya berdampingan pada satu televisi.
MAKS_KOLOM_LAYANAN = 6

#: Kolom kisi bento. Empat, supaya sel besar (2x2) tepat setengah lebar
#: papan dan sisanya masih terbagi rata menjadi sel-sel kecil.
KOLOM_BENTO = 4

#: Pengecilan huruf kartu untuk setiap baris kartu tambahan, dan batas
#: bawahnya.
#:
#: Ukuran huruf papan diturunkan dari besar LAYAR, sedangkan tinggi yang
#: dimiliki satu kartu ditentukan oleh berapa baris kartu yang berbagi
#: layar itu. Pada satu baris keduanya sama saja; pada dua baris, kartu
#: menuntut tinggi dua kali lipat dan yang mengalah adalah daftar menunggu
#: di bawahnya — panel itu menyusut sampai hanya memuat satu baris nomor,
#: dan pertanyaan "kapan giliran saya" tidak lagi terjawab.
#:
#: Karena itu huruf kartu ikut mengecil mengikuti banyaknya baris. Nomor
#: yang sedang dipanggil tetap yang terbesar di layar; yang berkurang
#: hanya kelebihannya.
SUSUT_PER_BARIS = 0.35
SUSUT_MIN = 0.45
#: Baris kartu ringkas — baris tabel dan kartu melebar di kolom samping —
#: yang masih dibiarkan seukuran penuh.
BARIS_BEBAS_RINGKAS = 2

#: Ukuran kartu loket pada pita tema Fokus, terhadap ukuran penuhnya.
#:
#: Pitanya hanya mendapat seperlima tinggi papan — seluruh sisanya milik
#: nomor raksasa di atasnya — sehingga kartunya tidak dapat dihitung dari
#: banyaknya baris seperti tema lain: barisnya memang cuma satu, tetapi
#: tingginya seperlima.
FAKTOR_PITA_FOKUS = 0.4

#: Bagian tinggi papan yang boleh dipakai panel daftar menunggu, per tata
#: letak.
#:
#: Panel ini menghitung sendiri berapa baris nomor yang muat, dari tinggi
#: yang SEDANG dimilikinya — dan tanpa batas atas, angka itu melingkar:
#: panel yang kebetulan tinggi menyimpulkan barisnya banyak, meminta tinggi
#: lebih banyak lagi, dan kartu loket di atasnya menyusut sampai nomornya
#: terpotong. Batas ini memutus lingkaran itu; sisanya pasti milik kartu.
BAGIAN_PANEL: dict[str, float] = {
    KISI: 0.5,
    BENTO: 0.5,
    TABEL: 0.42,
    SOROTAN: 0.45,
    SPLIT: 0.45,
    FOKUS: 0.3,
}

#: Sudut panel daftar menunggu. Padding dalamnya harus sekurang-kurangnya
#: sebesar ini: kartu nomor yang menindih lengkungannya membuat tepi bawah
#: panel tampak terpotong lurus, bukan membulat.
RADIUS_PANEL_TUNGGU = 20

#: Tinggi minimum satu baris kartu loket tegak, pada skala 1. Dipakai
#: membatasi panel menunggu supaya kartu dua baris (bento) tidak mendorong
#: panel itu keluar tepi bawah layar.
TINGGI_BARIS_KARTU_MIN = 180

#: Ukuran panel sorotan tema Fokus, terhadap ukuran penuhnya.
#:
#: Tema Sorotan memberi panel ini hampir seluruh tinggi papan; tema Fokus
#: hanya sekitar setengahnya, karena harus berbagi dengan pita loket dan
#: daftar menunggu. Pada ukuran penuh, nomornya terpotong di kedua ujung.
FAKTOR_SOROT_FOKUS = 0.8

#: Perbandingan lebar kolom pada tata letak TABEL: nomor, loket, status.
#: Dipakai bersama oleh baris kartunya dan baris judul di atasnya —
#: berbeda sedikit saja, judul kolom tidak lagi berdiri di atas isinya.
REGANG_TABEL = (4, 5, 3)

LABEL_STATUS_LOKET: dict[QueueStatus, str] = {
    QueueStatus.CALLED: "DIPANGGIL",
    QueueStatus.SERVING: "DILAYANI",
    QueueStatus.PAUSED: "DITUNDA",
}

#: Ukuran huruf dasar layar televisi ruang tunggu. Dibaca dari seberang
#: ruangan, sehingga nomor antrian sengaja jauh lebih besar daripada apa pun
#: yang lain di layar.
#:
#: Batas atas nomor ditentukan oleh lebar kartu, bukan selera: tiga kartu
#: pada layar 1100px memberi sekitar 325px per kartu, dan nomor lima huruf
#: pada 132px masih muat di dalamnya setelah dikurangi padding (skala
#: turun otomatis di layar yang lebih sempit lewat hitung_skala()).
UKURAN_TV: dict[str, int] = {
    "judul": 36,
    "jam": 24,
    "nama": 32,
    "status": 22,
    "nomor": 132,
    "layanan": 26,
    "berikutnya_judul": 20,
    # Nama jenis layanan di atas kolom daftar menunggu. Terpisah dari judul
    # panel "MENUNGGU GILIRAN": yang dibaca dari jauh adalah kolom mana
    # milik nomornya, bukan hitungan halamannya.
    "berikutnya_kolom": 28,
    "berikutnya": 46,
    # Varian baris: kartu melebar, nomornya di kanan nama loket.
    "nama_baris": 26,
    "status_baris": 20,
    "nomor_baris": 84,
    # Varian tabel: nomor di kolom kiri, seperti papan keberangkatan.
    # Nomornya lebih besar daripada varian baris — di sini nomor adalah
    # kolom pertama yang dibaca, bukan angka di ujung kanan kartu.
    "nama_tabel": 38,
    "status_tabel": 24,
    "nomor_tabel": 96,
    # Panel sorotan.
    "sorot_pil": 22,
    "sorot_nomor": 224,
    "sorot_nama": 62,
    "sorot_layanan": 28,
    # Panel pengumuman tema split.
    "info_judul": 32,
    "info": 26,
    # Panel informasi berputar papan kios, menggantikan kartu ringkasan.
    "kios_info": 26,
    # Kartu nomor yang baru terbit di panel kios. Tidak pernah terpakai di
    # televisi — kartunya hanya dibangun pada mode kompak — tetapi tetap
    # didaftarkan supaya kedua tabel punya kunci yang sama persis.
    "kios_kartu_judul": 22,
    "kios_kartu_nomor": 150,
    "kios_kartu_layanan": 34,
    "kios_kartu_sisa": 24,
    "kios_kartu_arahan": 22,
}

#: Ukuran huruf papan di dalam kios. Layar kios dibaca dari jarak satu
#: lengan dan harus berbagi tempat dengan panel ambil nomor, jadi papannya
#: tetap kompak berapa pun besar layarnya.
UKURAN_KIOS: dict[str, int] = {
    "judul": 34,
    "jam": 15,
    "nama": 16,
    "status": 13,
    "nomor": 64,
    "layanan": 15,
    "berikutnya_judul": 15,
    "berikutnya_kolom": 15,
    "berikutnya": 28,
    "nama_baris": 15,
    "status_baris": 12,
    "nomor_baris": 40,
    "nama_tabel": 20,
    "status_tabel": 13,
    "nomor_tabel": 46,
    "sorot_pil": 12,
    "sorot_nomor": 100,
    "sorot_nama": 28,
    "sorot_layanan": 15,
    "info_judul": 18,
    "info": 14,
    "kios_info": 20,
    # Nomor dibuat jauh lebih besar daripada teks papan kios lainnya
    # dengan sengaja: saat printer kehabisan kertas, kartu inilah
    # satu-satunya catatan nomor yang dipegang pengunjung, dan harus
    # cukup besar untuk difoto dengan ponsel dari jarak berdiri.
    "kios_kartu_judul": 16,
    "kios_kartu_nomor": 112,
    "kios_kartu_layanan": 26,
    "kios_kartu_sisa": 18,
    "kios_kartu_arahan": 16,
}

#: Tinggi layar tempat UKURAN_TV berlaku apa adanya. Di atasnya huruf
#: membesar, di bawahnya mengecil — televisi 1080p mendapat huruf lebih
#: besar daripada jendela pengembang tanpa perlu dua kumpulan angka.
TINGGI_ACUAN_TV = 900
#: Lebar tempat UKURAN_TV berlaku apa adanya. Ikut dihitung karena kartu
#: berjajar: jendela yang lebar-pendek boleh saja punya tinggi cukup,
#: sementara nomornya tidak muat pada lebar kartu.
LEBAR_ACUAN_TV = 1600
SKALA_MIN = 0.7
SKALA_MAKS = 1.5

HARI = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
BULAN = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)


def teks_waktu(saat: datetime | None = None) -> str:
    """
    Tanggal dan jam dalam bahasa Indonesia.

    Nama hari dan bulan ditulis sendiri, tidak diambil dari locale sistem.
    Komputer layar sering dipasang dengan Windows berbahasa Inggris, dan
    papan yang menghadap publik tidak boleh berbunyi "Wednesday".
    """
    saat = saat or clock.now()
    tanggal = f"{HARI[saat.weekday()]}, {saat.day} {BULAN[saat.month - 1]} {saat.year}"
    return f"{tanggal}  ·  {saat:%H:%M:%S}"


def _teks_status(antrian, *, unggulan: bool) -> str:
    """Status satu loket sebagaimana dibaca pengunjung."""
    status = LABEL_STATUS_LOKET.get(
        antrian.status, LABEL_STATUS.get(antrian.status, "").upper()
    )
    if unggulan and antrian.status is QueueStatus.CALLED:
        return "SEDANG DIPANGGIL"
    return status


def faktor_kartu(baris: int, *, ringkas: bool = False) -> float:
    """
    Pengecilan huruf kartu untuk papan yang kartunya bertumpuk `baris`.

    Baris pertama tidak pernah dikecilkan — itulah ukuran yang dirancang
    untuk dibaca dari seberang ruangan. Lihat `SUSUT_PER_BARIS`.

    `ringkas` untuk kartu yang memang sudah pendek: baris tabel dan kartu
    melebar di kolom samping tingginya sekitar sepertiga kartu tegak,
    sehingga tiga barisnya masih memakan ruang yang sama dengan satu kartu
    tegak. Mengecilkannya sejak baris kedua berarti mengecilkan papan yang
    sebenarnya tidak sesak sama sekali.
    """
    bebas = BARIS_BEBAS_RINGKAS if ringkas else 1
    if baris <= bebas:
        return 1.0
    return max(SUSUT_MIN, 1.0 - SUSUT_PER_BARIS * (baris - bebas))


def _bagi_baris(baris: int, jumlah: int) -> list[tuple[int, int, int, int]]:
    """
    Sebaris penuh kisi bento dibagi rata untuk `jumlah` kartu.

    Kembaliannya (baris, kolom, rentang_baris, rentang_kolom) per kartu,
    selalu menghabiskan keempat kolomnya. Sisa kolom yang tidak terpakai
    akan terbaca sebagai bagian layar yang gagal termuat, bukan sebagai
    ruang kosong yang disengaja.
    """
    if jumlah <= 1:
        return [(baris, 0, 1, KOLOM_BENTO)]
    if jumlah == 2:
        return [(baris, 0, 1, 2), (baris, 2, 1, 2)]
    if jumlah == 3:
        # Yang pertama dilebarkan, bukan yang terakhir: urutan loket dibaca
        # dari kiri, dan kartu terlebar di awal baris terbaca sebagai
        # permulaan yang disengaja.
        return [(baris, 0, 1, 2), (baris, 2, 1, 1), (baris, 3, 1, 1)]
    return [(baris, kolom, 1, 1) for kolom in range(KOLOM_BENTO)]


def _peta_bento(jumlah: int) -> list[tuple[int, int, int, int]]:
    """
    Tempat setiap kartu pada kisi bento, sel besar lebih dahulu.

    Sel pertama adalah sel besar (dua kolom kali dua baris) — jatah loket
    yang sedang memanggil. Sisanya mengisi dua kolom kanan, lalu baris-baris
    penuh di bawahnya.

    Bentuknya ditulis per jumlah loket, bukan dihitung dengan satu rumus:
    rumus yang sama untuk semua jumlah selalu meninggalkan sel kosong pada
    jumlah tertentu, dan lubang di tengah papan publik terbaca sebagai
    layar rusak.
    """
    if jumlah <= 1:
        return [(0, 0, 1, KOLOM_BENTO)]
    if jumlah == 2:
        return [(0, 0, 2, 2), (0, 2, 2, 2)]

    peta = [(0, 0, 2, 2)]
    sisa = jumlah - 1

    # Blok kanan: dua kolom, dua baris, sejajar dengan sel besar.
    kanan = min(sisa, 4)
    if kanan == 1:
        peta.append((0, 2, 2, 2))
    elif kanan == 2:
        peta += [(0, 2, 1, 2), (1, 2, 1, 2)]
    elif kanan == 3:
        peta += [(0, 2, 1, 2), (1, 2, 1, 1), (1, 3, 1, 1)]
    else:
        peta += [(0, 2, 1, 1), (0, 3, 1, 1), (1, 2, 1, 1), (1, 3, 1, 1)]

    # Loket berikutnya turun menjadi baris-baris penuh di bawah keduanya.
    sisa -= kanan
    baris = 2
    while sisa > 0:
        di_baris = min(KOLOM_BENTO, sisa)
        peta += _bagi_baris(baris, di_baris)
        sisa -= di_baris
        baris += 1
    return peta


def _sel_bento(jumlah: int, unggulan: int) -> list[tuple[int, int, int, int]]:
    """
    Posisi kisi untuk setiap kartu, sesuai urutan loket.

    Loket yang sedang memanggil mendapat sel besar; loket lain mengisi sel
    kecil dengan urutan aslinya tetap terjaga. Papan yang mengurutkan ulang
    seluruh loketnya setiap panggilan memaksa pengunjung mencari nama loket
    dari awal setiap kali.
    """
    peta = _peta_bento(jumlah)
    unggulan = unggulan if 0 <= unggulan < jumlah else 0
    lain = iter(peta[1:])
    return [
        peta[0] if indeks == unggulan else next(lain) for indeks in range(jumlah)
    ]


class KartuLoket(QFrame):
    """
    Satu loket: nama, nomor yang sedang ditangani, dan jenis layanan.

    Tiga bentuk, ditentukan `varian`:

    * ``"kisi"`` — kartu tegak, nomor di tengah. Dipakai tema berbentuk kisi
      dan bento.
    * ``"baris"`` — kartu melebar, nama di kiri dan nomor di kanan. Dipakai
      kolom loket pada tema Sorotan dan Split, yang harus memuat semua loket
      dalam satu kolom sempit, dan pita loket tema Fokus.
    * ``"tabel"`` — baris papan keberangkatan: nomor di kolom kiri, nama
      loket di tengah, status di kanan, dipisahkan garis rambut alih-alih
      dijadikan kartu. Dipakai tema Papan LED.
    """

    #: Kunci ukuran yang ikut dikalikan `skala_nomor` — nomor antrian saja,
    #: bukan nama loket atau status, supaya pengaturannya benar-benar hanya
    #: membesarkan angka yang dibaca dari jarak jauh.
    _KUNCI_NOMOR = frozenset({"nomor", "nomor_baris", "nomor_tabel"})

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        kompak: bool = False,
        palet: Palet | None = None,
        varian: str = "kisi",
        skala_nomor: float = 1.0,
    ) -> None:
        super().__init__(parent)
        self.kompak = kompak
        self.palet = palet or palet_untuk(TEMA_BAWAAN)
        self.varian = varian
        #: isVisible() masih False selama papan belum tampil, jadi keberadaan
        #: pita disimpan sebagai penanda sendiri.
        self.pakai_pita = bool(self.palet.pita) and varian == "kisi"
        self.ukuran = UKURAN_KIOS if kompak else UKURAN_TV
        self.skala = 1.0
        #: Faktor tambahan dari pengaturan `display.number_font_scale`,
        #: terpisah dari `skala` (yang mengikuti besar layar).
        self.skala_nomor = skala_nomor
        #: Pengecilan extra bila tinggi kartu tidak muat untuk hurufnya.
        #: Dipakai sel kecil bento: setengah tinggi sel besar, tetapi
        #: huruf televisi 132px masih dipasang utuh dan nomornya terpotong.
        self._faktor_muat = 1.0
        self._unggulan = False
        self._kosong = True

        self.setObjectName("kartuLoket")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.label_nama = QLabel("")
        self.label_status = QLabel("KOSONG")
        self.label_nomor = QLabel("—")
        self.label_layanan = QLabel("")
        for label in self._label():
            label.setWordWrap(label is self.label_layanan)
            # Ukuran huruf tidak boleh menjadi ukuran minimum jendela. Tanpa
            # ini, papan yang sempat dibuka layar penuh menolak mengecil lagi
            # saat Esc ditekan. Ukuran huruf sudah mengikuti besar layar
            # lewat set_skala().
            label.setMinimumSize(1, 1)

        if varian == "baris":
            self._bangun_baris()
        elif varian == "tabel":
            self._bangun_tabel()
        else:
            self._bangun_kisi()
        self._tulis_gaya()

    # -----------------------------------------------------------------

    def _label(self) -> tuple[QLabel, ...]:
        return (self.label_nama, self.label_status, self.label_nomor, self.label_layanan)

    def _bangun_kisi(self) -> None:
        luar = QVBoxLayout(self)
        luar.setContentsMargins(0, 0, 0, 0)
        luar.setSpacing(0)

        self.pita = QFrame()
        self.pita.setVisible(self.pakai_pita)
        luar.addWidget(self.pita)

        isi = QWidget()
        isi.setStyleSheet("background: transparent;")
        self.susunan_isi = QVBoxLayout(isi)

        atas = QHBoxLayout()
        if self.palet.status_berpil:
            # Status sebagai pil di pojok kartu: nama loket dan keadaannya
            # terbaca dalam satu tarikan mata, dan nomor mendapat seluruh
            # tengah kartu.
            self.label_nama.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            atas.addWidget(self.label_nama)
            atas.addStretch()
            self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            atas.addWidget(self.label_status)
            self.susunan_isi.addLayout(atas)
        else:
            self.label_nama.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.label_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.susunan_isi.addWidget(self.label_nama)
            self.susunan_isi.addWidget(self.label_status)

        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.susunan_isi.addWidget(self.label_nomor, stretch=1)

        self.label_layanan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.susunan_isi.addWidget(self.label_layanan)

        luar.addWidget(isi, stretch=1)

    def _bangun_baris(self) -> None:
        self.pita = QFrame()
        self.pita.setVisible(False)

        self.susunan_isi = QHBoxLayout(self)
        kiri = QVBoxLayout()
        kiri.setSpacing(2)
        self.label_nama.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.label_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        kiri.addWidget(self.label_nama)
        kiri.addWidget(self.label_status)
        self.label_layanan.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Nama layanan TIDAK dilipat pada kartu melebar. Kolom kiri kartu
        # ini sempit — sisanya milik nomor di kanan — sehingga "Customer
        # Service" dilipat menjadi dua baris, dan setiap kartu bertambah
        # tinggi. Dikalikan lima loket, tambahan itu menggusur judul papan
        # sampai keluar dari layar.
        self.label_layanan.setWordWrap(False)
        kiri.addWidget(self.label_layanan)
        self.susunan_isi.addLayout(kiri)
        self.susunan_isi.addStretch()
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.susunan_isi.addWidget(self.label_nomor)

    def _bangun_tabel(self) -> None:
        """
        Baris papan keberangkatan: nomor, loket, status.

        Nomor berdiri di kolom paling kiri dan paling besar. Pengunjung
        membaca papan ini dengan satu pertanyaan — "nomor berapa sekarang" —
        dan jawaban itu harus berada di tempat yang sama pada setiap baris,
        bukan di ujung kanan yang berpindah-pindah mengikuti panjang nama
        loket.
        """
        self.pita = QFrame()
        self.pita.setVisible(False)

        self.susunan_isi = QHBoxLayout(self)
        regang_nomor, regang_nama, regang_status = REGANG_TABEL

        self.label_nomor.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.susunan_isi.addWidget(self.label_nomor, stretch=regang_nomor)

        tengah = QVBoxLayout()
        tengah.setSpacing(0)
        for label in (self.label_nama, self.label_layanan):
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            tengah.addWidget(label)
        self.susunan_isi.addLayout(tengah, stretch=regang_nama)

        self.label_status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.susunan_isi.addWidget(self.label_status, stretch=regang_status)

    # -----------------------------------------------------------------

    def px(self, kunci: str) -> int:
        """Ukuran huruf setelah diskalakan terhadap besar layar."""
        dasar = self.ukuran[kunci] * self.skala * self._faktor_muat
        if kunci in self._KUNCI_NOMOR:
            dasar *= self.skala_nomor
        return max(10, round(dasar))

    def set_skala(self, skala: float) -> None:
        """Ubah skala huruf. Diabaikan bila perubahannya tidak berarti."""
        if abs(skala - self.skala) < 0.02:
            return
        self.skala = skala
        self._faktor_muat = 1.0
        self._tulis_gaya()

    def muatkan_huruf(self) -> None:
        """
        Turunkan huruf bila kartunya lebih pendek daripada yang dituntut.

        Minimum size setiap label sengaja 1px agar jendela bisa mengecil.
        Akibatnya Qt meremas label di bawah tinggi hurufnya: A-003 terpotong
        di tepi atas, nama layanan di tepi bawah. Huruf yang muat tetap
        terbaca; huruf yang terpotong tidak.
        """
        if self.varian != "kisi" or self.height() <= 1:
            return
        dalam = max(1, self.height() - 2 * self.palet.tebal_tepi - 8)
        penuh = self._tinggi_butuh(self.skala)
        target = 1.0 if penuh <= dalam else max(0.35, dalam / penuh)
        if abs(target - self._faktor_muat) < 0.02:
            return
        self._faktor_muat = target
        self._tulis_gaya()

    def _tinggi_butuh(self, skala: float) -> int:
        """Tinggi isi kartu pada `skala`, termasuk padding dan pil status."""

        def px(kunci: str) -> int:
            dasar = self.ukuran[kunci] * skala
            if kunci in self._KUNCI_NOMOR:
                dasar *= self.skala_nomor
            return max(10, round(dasar))

        def tinggi_huruf(ukuran: int) -> int:
            font = QFont(self.label_nomor.font())
            font.setPixelSize(ukuran)
            return QFontMetrics(font).height()

        if self.kompak:
            pad_atas, pad_bawah, jarak = 10, 12, 4
        else:
            pad_atas = round(22 * skala)
            pad_bawah = round(26 * skala)
            jarak = round(8 * skala)

        atas = tinggi_huruf(px("nama"))
        if self.palet.status_berpil:
            pad_status = max(4, round(8 * skala))
            atas = max(atas, tinggi_huruf(px("status")) + 2 * pad_status)
        else:
            atas += jarak + tinggi_huruf(px("status"))

        return (
            pad_atas
            + atas
            + jarak
            + tinggi_huruf(px("nomor"))
            + jarak
            + tinggi_huruf(px("layanan"))
            + pad_bawah
        )

    def tampilkan(self, keadaan: DisplayCounterState, *, unggulan: bool) -> None:
        self.label_nama.setText((keadaan.counter_name or "").upper())
        antrian = keadaan.antrian
        self._kosong = antrian is None
        self._unggulan = unggulan

        if antrian is None:
            self.label_status.setText("ISTIRAHAT" if keadaan.istirahat else "KOSONG")
            self.label_nomor.setText("—")
            self.label_layanan.setText(
                "Sedang istirahat" if keadaan.istirahat else "Siap melayani"
            )
        else:
            self.label_status.setText(_teks_status(antrian, unggulan=unggulan))
            self.label_nomor.setText(antrian.queue_number)
            self.label_layanan.setText(antrian.category_name)

        self._tulis_gaya()

    def _tulis_gaya(self) -> None:
        """
        Satu-satunya tempat gaya kartu ditulis.

        Warna datang dari palet tema dan ukuran dari skala layar; keduanya
        berubah saat berjalan, jadi tidak boleh tersebar di dua tempat yang
        bisa berbeda isi.
        """
        p = self.palet
        skala = self.skala * self._faktor_muat
        baris = self.varian == "baris"
        tabel = self.varian == "tabel"

        if self.kompak:
            padding = (14, 10, 14, 12) if self.varian == "kisi" else (14, 10, 14, 10)
            tinggi_pita = 6
            jarak = 4
        elif tabel:
            # Baris tabel dibiarkan lebih rapat daripada kartu: yang
            # memisahkannya adalah garis, bukan jarak, dan jarak yang lebar
            # justru memutus garis-garis itu menjadi potongan yang tidak
            # lagi terbaca sebagai satu tabel.
            padding = tuple(round(n * skala) for n in (26, 14, 26, 14))
            tinggi_pita = 0
            jarak = round(18 * skala)
        elif baris:
            padding = tuple(round(n * skala) for n in (30, 18, 30, 18))
            tinggi_pita = 0
            jarak = round(6 * skala)
        else:
            padding = tuple(round(n * skala) for n in (30, 22, 30, 26))
            tinggi_pita = max(6, round(10 * skala))
            jarak = round(8 * skala)

        self.susunan_isi.setContentsMargins(*padding)
        self.susunan_isi.setSpacing(jarak)
        if self.pakai_pita:
            self.pita.setFixedHeight(tinggi_pita)

        akhiran = "_baris" if baris else ("_tabel" if tabel else "")
        kunci_nama = f"nama{akhiran}"
        kunci_status = f"status{akhiran}"
        kunci_nomor = f"nomor{akhiran}"

        warna_nomor = p.nomor if not self._kosong else p.nomor_kosong
        warna_status = p.status_unggulan if self._unggulan else p.status

        self.label_nama.setStyleSheet(
            f"color: {p.nama}; background: transparent;"
            f" font-size: {self.px(kunci_nama)}px; font-weight: 800; letter-spacing: 3px;"
        )
        if p.status_berpil and self.varian == "kisi":
            latar = p.pil_latar if self._unggulan else p.pil_latar_mati
            teks = p.status_unggulan if self._unggulan else p.status
            self.label_status.setStyleSheet(
                f"color: {teks}; background: {latar};"
                f" border-radius: {max(10, round(16 * skala))}px;"
                f" font-size: {self.px(kunci_status)}px; font-weight: 800;"
                f" letter-spacing: 2px; padding: {max(4, round(8 * skala))}px"
                f" {max(8, round(16 * skala))}px;"
            )
        else:
            self.label_status.setStyleSheet(
                f"color: {warna_status}; background: transparent;"
                f" font-size: {self.px(kunci_status)}px; font-weight: 700;"
                " letter-spacing: 3px;"
            )
        self.label_nomor.setStyleSheet(
            f"color: {warna_nomor}; background: transparent;"
            f" font-size: {self.px(kunci_nomor)}px; font-weight: 800;"
            f" letter-spacing: {p.renggang_nomor}px;"
        )
        self.label_layanan.setStyleSheet(
            f"color: {p.layanan}; background: transparent;"
            f" font-size: {self.px('layanan')}px; font-weight: 600;"
        )

        if self._unggulan and baris:
            # kartu_unggulan dirancang untuk panel sorotan yang besar —
            # biasanya nyaris putih. Dipakai di sini, kartu baris yang
            # ramping berubah nyaris putih juga dan menelan tulisannya
            # sendiri (warna nama/status memang dipilih untuk latar gelap).
            # Baris unggulan cukup ditandai tepinya yang menyala.
            latar, tepi, tebal = p.kartu, p.tepi_unggulan, p.tebal_tepi + 1
        elif self._unggulan:
            latar, tepi, tebal = p.kartu_unggulan, p.tepi_unggulan, p.tebal_tepi + 1
        elif self._kosong:
            latar, tepi, tebal = p.kartu_kosong, p.tepi_kartu, p.tebal_tepi
        else:
            latar, tepi, tebal = p.kartu, p.tepi_kartu, p.tebal_tepi

        radius = p.radius if not self.kompak else max(12, p.radius - 8)
        if tabel:
            # Baris tabel bukan kartu: yang memisahkannya adalah garis
            # rambut di bawahnya, dan yang menandai barisnya adalah balok
            # tebal di tepi kiri — penanda yang tetap terlihat dari jauh
            # walau seluruh baris berwarna sama.
            garis = p.garis or p.tepi_kartu
            aksen = p.tepi_unggulan if self._unggulan else "transparent"
            self.setStyleSheet(
                f"QFrame#kartuLoket {{ background: {latar}; border: none;"
                f" border-bottom: {p.tebal_tepi}px solid {garis};"
                f" border-left: {max(6, round(10 * skala))}px solid {aksen};"
                f" border-radius: {max(2, min(radius, 8))}px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#kartuLoket {{ background: {latar}; border-radius: {radius}px;"
                f" border: {tebal}px solid {tepi}; }}"
            )
        if self.pakai_pita:
            self.pita.setStyleSheet(
                f"background: {p.tepi_unggulan if self._unggulan else p.pita};"
                f" border: none; border-top-left-radius: {radius - 2}px;"
                f" border-top-right-radius: {radius - 2}px;"
            )


class KartuSorot(QFrame):
    """
    Panel besar berisi panggilan terbaru.

    Hanya dipakai tema Sorotan. Yang ditampilkan selalu nomor yang paling
    baru dipanggil, sehingga pengunjung yang mendengar bunyi panggilan
    cukup melihat satu tempat.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        kompak: bool = False,
        palet: Palet | None = None,
        skala_nomor: float = 1.0,
    ) -> None:
        super().__init__(parent)
        self.kompak = kompak
        self.palet = palet or palet_untuk(TEMA_BAWAAN)
        self.ukuran = UKURAN_KIOS if kompak else UKURAN_TV
        self.skala = 1.0
        self.skala_nomor = skala_nomor

        self.setObjectName("kartuSorot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.susunan = QVBoxLayout(self)
        self.label_status = QLabel("MENUNGGU PANGGILAN")
        self.label_nomor = QLabel("—")
        self.label_nama = QLabel("")
        self.label_layanan = QLabel("")
        for label in (self.label_status, self.label_nomor, self.label_nama, self.label_layanan):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(1, 1)

        baris_pil = QHBoxLayout()
        baris_pil.addStretch()
        baris_pil.addWidget(self.label_status)
        baris_pil.addStretch()
        self.susunan.addLayout(baris_pil)
        self.susunan.addWidget(self.label_nomor, stretch=1)
        self.susunan.addWidget(self.label_nama)
        self.susunan.addWidget(self.label_layanan)
        self._tulis_gaya()

    def px(self, kunci: str) -> int:
        dasar = self.ukuran[kunci] * self.skala
        if kunci == "sorot_nomor":
            dasar *= self.skala_nomor
        return max(10, round(dasar))

    def set_skala(self, skala: float) -> None:
        if abs(skala - self.skala) < 0.02:
            return
        self.skala = skala
        self._tulis_gaya()

    def tampilkan(self, antrian) -> None:
        if antrian is None:
            self.label_status.setText("MENUNGGU PANGGILAN")
            self.label_nomor.setText("—")
            self.label_nama.setText("")
            self.label_layanan.setText("Belum ada nomor yang dipanggil")
        else:
            self.label_status.setText(_teks_status(antrian, unggulan=True))
            self.label_nomor.setText(antrian.queue_number)
            self.label_nama.setText((antrian.counter_name or "").upper())
            self.label_layanan.setText(antrian.category_name or "")
        self._tulis_gaya()

    def _tulis_gaya(self) -> None:
        p = self.palet
        skala = self.skala
        self.susunan.setContentsMargins(*(round(n * skala) for n in (56, 44, 56, 48)))
        self.susunan.setSpacing(round(10 * skala))

        # Seluruh warna panel ini datang dari palet, tidak satu pun ditanam
        # di sini. Panelnya boleh berlawanan terang-gelap dengan papannya —
        # kartu putih di atas latar gelap pada tema Sorotan, panel gelap
        # pada tema Fokus — dan warna yang ditanam hanya benar untuk salah
        # satunya.
        self.label_status.setStyleSheet(
            f"color: {p.sorot_pil_teks}; background: {p.pil_latar};"
            f" border-radius: {max(12, round(22 * skala))}px;"
            f" font-size: {self.px('sorot_pil')}px; font-weight: 800;"
            f" letter-spacing: 4px; padding: {round(10 * skala)}px {round(26 * skala)}px;"
        )
        self.label_nomor.setStyleSheet(
            f"color: {p.sorot_nomor}; background: transparent;"
            f" font-size: {self.px('sorot_nomor')}px; font-weight: 800;"
            f" letter-spacing: {p.renggang_nomor}px;"
        )
        self.label_nama.setStyleSheet(
            f"color: {p.pil_latar}; background: transparent;"
            f" font-size: {self.px('sorot_nama')}px; font-weight: 800; letter-spacing: 6px;"
        )
        self.label_layanan.setStyleSheet(
            f"color: {p.sorot_teks}; background: transparent;"
            f" font-size: {self.px('sorot_layanan')}px; font-weight: 600;"
        )
        self.setStyleSheet(
            f"QFrame#kartuSorot {{ background: {p.kartu_unggulan};"
            f" border-radius: {round(36 * skala)}px;"
            f" border: {p.tebal_tepi + 1}px solid {p.tepi_unggulan}; }}"
        )


class DisplayPage(QWidget):
    """
    Papan nomor antrian.

    Sengaja tidak memiliki satu pun fungsi administrasi. Komputer layar
    biasanya menghadap publik dan tidak diawasi, jadi tidak ada tombol yang
    dapat mengubah data.

    Isinya dibuat dengan kontras tinggi dan huruf sangat besar karena dibaca
    dari seberang ruangan, bukan dari depan meja. Setiap loket tampil
    sebagai kartu sendiri supaya pengunjung tidak harus menebak di loket
    mana nomornya dipanggil.

    Satu kelas melayani dua pemasangan, dibedakan `kompak`:

    * ``kompak=False`` — televisi ruang tunggu. Huruf besar dan ikut
      membesar mengikuti tinggi layar, margin lapang, kartu mengisi layar.
    * ``kompak=True`` — papan di dalam kios. Tetap kecil berapa pun layarnya,
      karena harus berbagi tempat dengan panel ambil nomor di bawahnya.

    Tampilannya dipilih administrator lewat pengaturan ``display.theme``.
    Papan kios selalu memakai tata letak kisi apa pun temanya — ruangnya
    hanya separuh layar, dan panel bersusun tidak muat di sana — tetapi
    warnanya tetap mengikuti tema yang dipilih.
    """

    def __init__(
        self,
        queue: QueueService,
        settings: SettingsService,
        sound: SoundPlayer,
        parent: QWidget | None = None,
        *,
        otomatis: bool = True,
        kompak: bool = False,
        tema: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.settings = settings
        self.sound = sound
        self.kompak = kompak
        self.ukuran = UKURAN_KIOS if kompak else UKURAN_TV
        self.skala = 1.0

        self.palet = palet_untuk(
            tema if tema is not None else settings.get("display.theme", TEMA_BAWAAN)
        )
        # Kios selalu berbentuk kisi. Sorotan dan Split menuntut tinggi yang
        # tidak dimiliki separuh layar kios, dan memaksakannya berarti nama
        # layanan di panel ambil nomor yang mengalah.
        self.tata_letak = KISI if kompak else self.palet.tata_letak

        # Papan kios menampilkan sederet nomor saja; televisi menampilkan
        # daftar menunggu selengkapnya, berhalaman, dan berpindah sendiri.
        self.baris_diminta = max(1, settings.get_int("display.list_rows", 5))
        #: Nol berarti huruf menyesuaikan sendiri dengan tinggi papan.
        #: Angka lain diperlakukan sebagai batas ATAS, bukan sebagai
        #: perintah mati: papan tetap memperkecilnya bila barisnya tidak
        #: muat, karena nomor terpotong lebih buruk daripada nomor kecil.
        self.font_diminta = max(0, settings.get_int("display.list_font_size", 0))
        self.jeda_putar_ms = (
            max(0, settings.get_int("display.rotate_seconds", 3)) * 1000
        )
        self.jumlah_berikutnya = (
            settings.get_int("display.next_count", 3)
            if kompak
            else self.baris_diminta * KOLOM_PER_LAYANAN * MAKS_HALAMAN
        )
        #: Halaman daftar menunggu yang sedang tampil. Milik widget, BUKAN
        #: dihitung ulang dari data: penyegaran dua detik sekali akan
        #: mengembalikannya ke halaman satu terus-menerus, dan rotasi tidak
        #: akan pernah sempat terlihat.
        self._halaman = 0
        self._menunggu: list = []
        self._layanan: list = []
        self._total_menunggu = 0
        #: Hasil pengukuran daftar menunggu terhadap tinggi panel yang ADA.
        #: Diisi `_ukur_daftar()`; nilai awalnya sekadar penjaga sebelum
        #: jendela pernah ditampilkan sama sekali.
        self._font_daftar = 0
        self._tinggi_baris = 0
        self._baris_muat = 99
        #: Faktor tambahan khusus nomor antrian, dari pengaturan admin.
        self.skala_nomor = settings.get_int("display.number_font_scale", 100) / 100.0
        # `kompak` berarti papan kecil di dalam anjungan, dan anjungan
        # diam secara bawaan supaya pengunjung tidak mendengar dua
        # pengumuman dari dua mesin sekaligus.
        self.suara_aktif = suara_diaktifkan(settings, anjungan=kompak)
        #: Nomor yang terakhir dibunyikan, supaya nada tidak berulang setiap
        #: penyegaran untuk panggilan yang sama.
        self._terakhir_dibunyikan: tuple[int, int] | None = None
        self._kunci_loket: tuple | None = None
        self.kartu_loket: list[KartuLoket] = []
        self.label_berikutnya: list[QLabel] = []
        #: Hanya ada pada tema Sorotan.
        self.kartu_sorot: KartuSorot | None = None
        #: Hanya ada pada tema Split.
        self.panel_info: QFrame | None = None
        #: Hanya ada pada tata letak kisi dan bento.
        self.kisi_loket: QGridLayout | None = None
        #: Susunan sel yang sedang terpasang pada kisi. Disimpan supaya
        #: kartu hanya dipindahkan ketika petanya benar-benar berubah;
        #: menata ulang kisi dua detik sekali membuat papan berkedip.
        self._sel_terpasang: list[tuple[int, int, int, int]] | None = None
        #: Hanya ada pada tata letak tabel: judul kolom NOMOR/LOKET/STATUS.
        self.label_kolom_tabel: list[QLabel] = []
        #: Berapa baris kartu loket yang bertumpuk di atas daftar menunggu.
        #: Menentukan pengecilan hurufnya — lihat `faktor_kartu`.
        self._baris_kartu = 1
        #: Kartu yang menempati sel besar bento, atau -1 bila tidak ada.
        self._indeks_besar = -1

        #: Hanya ada pada papan kios. Isinya diisi KioskPage lewat
        #: `tampilkan_info_kios()` saat pengunjung menyentuh sebuah
        #: layanan — lihat `_bangun_info_kios`.
        self.label_info_kios: QLabel | None = None
        self.panel_info_kios: PanelSambutanKios | None = None

        self._bangun_tampilan()
        self.muat_ulang()

        self.pewaktu = QTimer(self)
        self.pewaktu.setInterval(SELANG_SEGAR_MS)
        self.pewaktu.timeout.connect(self.muat_ulang)

        # Jam tetap berdetik walau data tidak berubah. Papan yang jamnya
        # berhenti membuat pengunjung mengira layarnya menggantung.
        self.pewaktu_jam = QTimer(self)
        self.pewaktu_jam.setInterval(SELANG_JAM_MS)
        self.pewaktu_jam.timeout.connect(self.perbarui_jam)

        # Rotasi halaman berdiri sendiri, terpisah dari penyegaran data.
        # Disatukan, halaman akan ikut berpindah setiap dua detik — terlalu
        # cepat untuk dibaca — dan justru berhenti berpindah pada saat
        # datanya tidak berubah.
        self.pewaktu_halaman = QTimer(self)
        self.pewaktu_halaman.setInterval(max(1, self.jeda_putar_ms))
        self.pewaktu_halaman.timeout.connect(self.putar_halaman)

        if otomatis:
            self.pewaktu.start()
            self.pewaktu_jam.start()
            if self.berotasi:
                self.pewaktu_halaman.start()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def px(self, kunci: str) -> int:
        """Ukuran huruf setelah diskalakan terhadap besar layar."""
        return max(10, round(self.ukuran[kunci] * self.skala))

    @property
    def skala_kartu(self) -> float:
        """
        Skala huruf kartu loket: skala layar, dikurangi menurut barisnya.

        Terpisah dari `skala` yang dipakai judul, jam, dan daftar menunggu.
        Judul tidak berlipat ganda ketika loket bertambah; kartu loket
        berlipat ganda.
        """
        if self.tata_letak == FOKUS:
            return self.skala * FAKTOR_PITA_FOKUS
        ringkas = self.tata_letak not in (KISI, BENTO)
        return self.skala * faktor_kartu(self._baris_kartu, ringkas=ringkas)

    def _terapkan_skala_kartu(self) -> None:
        """
        Ukuran huruf setiap kartu loket, sesuai besar selnya.

        Sel besar bento menempati tinggi dua baris, sehingga kartunya tidak
        ikut dikecilkan: nomor yang sedang dipanggil harus tetap yang
        terbesar di layar. Sel besar dengan nomor yang lebih kecil daripada
        tetangganya membalik seluruh maksud tata letaknya.
        """
        for indeks, kartu in enumerate(self.kartu_loket):
            besar = indeks == self._indeks_besar
            kartu.set_skala(self.skala if besar else self.skala_kartu)

    def _muatkan_huruf_kartu(self) -> None:
        """Turunkan huruf kartu yang selnya lebih pendek daripada isinya."""
        for kartu in self.kartu_loket:
            kartu.muatkan_huruf()

    def _bangun_tampilan(self) -> None:
        # Selector WAJIB dibatasi dengan objectName. Deklarasi "background"
        # tanpa selector merambat ke seluruh widget anak, sehingga panel
        # putih dan setiap label ikut berlatar gelap dan isinya hilang.
        self.setObjectName("layarAntrian")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#layarAntrian {{ background: {self.palet.latar}; }}"
        )
        # Papan boleh mengecil sampai ukuran berapa pun. Tanpa batas kecil
        # yang ditetapkan sendiri, Qt memasang ukuran minimum dari tata letak
        # saat itu — dan sesudah layar penuh, minimum itu ikut sebesar huruf
        # televisi, sehingga Esc menyisakan jendela yang tetap raksasa.
        self.setMinimumSize(1, 1)

        self.susunan = QVBoxLayout(self)
        if self.tata_letak == SOROTAN:
            self._bangun_sorotan()
        elif self.tata_letak == SPLIT:
            self._bangun_split()
        elif self.tata_letak == TABEL:
            self._bangun_tabel()
        elif self.tata_letak == FOKUS:
            self._bangun_fokus()
        else:
            # KISI dan BENTO memakai kerangka yang sama — kepala, kisi
            # kartu, panel menunggu. Yang membedakan bento hanyalah tempat
            # setiap kartu di dalam kisinya; lihat `_tata_kartu`.
            self._bangun_kisi()
        self._terapkan_ukuran()

    # --- bagian yang dipakai bersama ---------------------------------

    def _bangun_kepala(self) -> QVBoxLayout:
        """
        Judul di tengah, jam tepat di bawahnya.

        Nama instansi Indonesia sering panjang. Ditulis sebaris dengan jam,
        keduanya saling memotong: judul kehilangan huruf terakhir, jam
        kehilangan nama hari. Ditumpuk dan rata tengah, keduanya mendapat
        lebar penuh layar — sama di televisi maupun di papan kios.
        """
        self.kepala = QVBoxLayout()

        self.label_judul = QLabel(self.settings.get("display.title"))
        self.label_judul.setMinimumSize(1, 1)
        self.label_judul.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label_jam = QLabel(teks_waktu())
        self.label_jam.setObjectName("jamPapan")
        self.label_jam.setMinimumSize(1, 1)
        self.label_jam.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.kepala.addWidget(self.label_judul)
        self.kepala.addWidget(self.label_jam)
        return self.kepala

    def _bangun_panel_berikutnya(self) -> QWidget:
        self.panel_berikutnya = QFrame()
        self.panel_berikutnya.setObjectName("panelBerikutnya")
        self.panel_berikutnya.setStyleSheet(
            f"QFrame#panelBerikutnya {{ background: {self.palet.panel};"
            f" border-radius: {RADIUS_PANEL_TUNGGU}px; }}"
        )

        self.susunan_berikutnya = QVBoxLayout(self.panel_berikutnya)
        self.susunan_berikutnya.setContentsMargins(
            20, 12, 20, RADIUS_PANEL_TUNGGU
        )
        self.susunan_berikutnya.setSpacing(8)

        self.label_judul_berikutnya = QLabel("MENUNGGU GILIRAN")
        self.label_judul_berikutnya.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_judul_berikutnya.setMinimumSize(1, 1)
        # Judul ini memuat nomor halaman dan sisa yang tidak termuat, dan
        # pada panel kolom samping kalimatnya lebih panjang daripada
        # lebarnya. Dilipat, bukan dipotong: nomor halaman yang hilang
        # membuat pengunjung menyimpulkan nomornya tidak ada di daftar.
        self.label_judul_berikutnya.setWordWrap(True)
        self.susunan_berikutnya.addWidget(self.label_judul_berikutnya)

        # Kisi, bukan satu baris: daftar menunggu televisi memuat sepuluh
        # nomor atau lebih sekaligus, dan sepuluh nomor sebaris menjadi
        # terlalu kecil untuk dibaca dari seberang ruangan.
        self.baris_berikutnya = QGridLayout()
        self.susunan_berikutnya.addLayout(self.baris_berikutnya, stretch=1)
        return self.panel_berikutnya

    def _bangun_kolom_loket(self, *, mendatar: bool = False) -> QVBoxLayout | QHBoxLayout:
        """
        Deret kartu loket, satu kartu per loket.

        Menurun untuk tema yang menaruhnya di kolom sempit (Sorotan, Split)
        dan untuk baris tabel; mendatar untuk tema Fokus, yang menaruh
        loket sebagai pita tipis di bawah nomor raksasanya.
        """
        self.kolom_loket = QHBoxLayout() if mendatar else QVBoxLayout()
        self.kolom_loket.setSpacing(14)
        return self.kolom_loket

    # --- tata letak per tema -----------------------------------------

    def _bangun_kisi(self) -> None:
        self.susunan.addLayout(self._bangun_kepala())

        if self.kompak:
            # Papan kios TIDAK menampilkan kartu per loket maupun daftar
            # nomor menunggu. Pengunjung yang berdiri di anjungan belum
            # memegang nomor sama sekali, sehingga "loket mana yang kosong"
            # atau "nomor apa saja yang menunggu" bukan pertanyaannya — itu
            # urusan orang yang sudah punya tiket, dan televisi ruang
            # tunggu yang menjawabnya. Seluruh papan kios diserahkan pada
            # informasi/pengumuman yang berputar lewat `_bangun_info_kios`.
            self.susunan.addWidget(self._bangun_info_kios(), stretch=1)
            # Dibangun tetap, TIDAK ditambahkan ke tata letak: kode bersama
            # (_terapkan_ukuran, tampilkan, _ukur_daftar) menulis ke
            # objeknya tanpa syarat kompak, dan membelah metode itu demi
            # satu panel yang sengaja disembunyikan berisiko merusak
            # televisi ruang tunggu yang masih memakainya.
            self._bangun_panel_berikutnya()
            return

        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        self.kisi_loket = QGridLayout(panel)
        self.kisi_loket.setContentsMargins(0, 0, 0, 0)
        # Televisi membagi layarnya rata: kartu loket menjawab "siapa yang
        # sedang dipanggil", daftar menunggu menjawab "kapan giliran saya" —
        # dan pertanyaan kedua ditanyakan jauh lebih sering oleh orang yang
        # sudah duduk menunggu.
        self.susunan.addWidget(panel, stretch=5)
        self.susunan.addWidget(self._bangun_panel_berikutnya(), stretch=5)

    def _bangun_info_kios(self) -> QWidget:
        """
        Panel informasi yang berganti isinya, menggantikan kartu angka.

        Mulai dengan sambutan (teks, gambar, atau video menurut pengaturan);
        berganti ke info sebuah layanan — selalu teks — begitu KioskPage
        memanggil `tampilkan_info_kios()` saat layanan itu disentuh.
        """
        self.panel_info_kios = PanelSambutanKios(
            self.settings,
            self.palet,
            teks_bawaan=TEKS_SAMBUTAN_KIOS,
            durasi_fade_ms=DURASI_FADE_INFO_KIOS_MS,
        )
        self.label_info_kios = self.panel_info_kios.label_teks
        # Bayangan pada panel, pudar pada label teks di dalamnya: satu
        # widget hanya boleh punya satu QGraphicsEffect. Video melepaskan
        # bayangan ini sendiri — QVideoWidget hitam di bawah efek grafis.
        self._bayangan(self.panel_info_kios, 40, 12)
        self.panel_info_kios.muat_pengaturan()
        return self.panel_info_kios

    def tampilkan_info_kios(
        self, teks: str | None, *, berkas: Path | None = None
    ) -> None:
        """
        Ganti isi panel informasi papan kios.

        Dipanggil KioskPage: dengan media dan/atau info sebuah layanan saat
        layanan itu disentuh, dan dengan `None` saat kembali ke kisi
        pilihan. Tidak berlaku pada televisi ruang tunggu — panelnya hanya
        dibangun pada mode kompak.
        """
        if self.panel_info_kios is None:
            return
        self.panel_info_kios.tampilkan_info(teks, berkas=berkas)

    def tampilkan_kartu_kios(
        self, *, nomor: str, layanan: str, sisa: str, arahan: str
    ) -> None:
        """Ganti isi panel dengan kartu nomor yang baru terbit."""
        if self.panel_info_kios is None:
            return
        self.panel_info_kios.tampilkan_kartu(
            nomor=nomor, layanan=layanan, sisa=sisa, arahan=arahan
        )

    def _bangun_sorotan(self) -> None:
        self.susunan.addLayout(self._bangun_kepala())

        isi = QHBoxLayout()
        isi.setSpacing(28)

        self.kartu_sorot = KartuSorot(
            kompak=self.kompak, palet=self.palet, skala_nomor=self.skala_nomor
        )
        self._bayangan(self.kartu_sorot, 60, 16)
        isi.addWidget(self.kartu_sorot, stretch=6)

        kanan = QVBoxLayout()
        kanan.setSpacing(16)
        self.label_judul_loket = QLabel("SELURUH LOKET")
        self.label_judul_loket.setMinimumSize(1, 1)
        kanan.addWidget(self.label_judul_loket)
        kanan.addLayout(self._bangun_kolom_loket(), stretch=1)
        kanan.addWidget(self._bangun_panel_berikutnya())
        isi.addLayout(kanan, stretch=4)

        self.susunan.addLayout(isi, stretch=1)

    def _bangun_split(self) -> None:
        # Header melintang penuh, sama seperti tema Sorotan: judul di
        # tengah, jam tepat di bawahnya.
        self.susunan.addLayout(self._bangun_kepala())

        isi = QHBoxLayout()
        isi.setSpacing(28)

        # --- panel pengumuman
        self.panel_info = QFrame()
        self.panel_info.setObjectName("panelInfo")
        self.panel_info.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.panel_info.setStyleSheet(
            f"QFrame#panelInfo {{ background: {self.palet.info_latar};"
            f" border-radius: {self.palet.radius + 6}px; }}"
        )
        info = QVBoxLayout(self.panel_info)
        info.addStretch()
        self.label_info_judul = QLabel("INFORMASI")
        self.label_info_judul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_info_judul.setMinimumSize(1, 1)
        info.addWidget(self.label_info_judul)

        # Isi panel diambil dari pengaturan, bukan ditanam di kode: yang
        # tahu pengumuman hari itu adalah petugas, bukan pemrogram.
        pesan = (self.settings.get("display.info", "") or "").strip()
        self.label_info = QLabel(
            pesan or "Mohon menunggu hingga nomor Anda dipanggil."
        )
        self.label_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_info.setWordWrap(True)
        self.label_info.setMinimumSize(1, 1)
        info.addWidget(self.label_info)
        info.addStretch()
        isi.addWidget(self.panel_info, stretch=6)

        # --- kolom antrian
        kanan = QVBoxLayout()
        kanan.setSpacing(14)
        kanan.addLayout(self._bangun_kolom_loket(), stretch=1)
        kanan.addWidget(self._bangun_panel_berikutnya())
        isi.addLayout(kanan, stretch=4)

        self.susunan.addLayout(isi, stretch=1)

    def _bangun_tabel(self) -> None:
        """
        Papan keberangkatan: satu baris per loket, dipisah garis rambut.

        Judul kolomnya berdiri sendiri di atas baris pertama, bukan diulang
        pada setiap baris. Papan yang mengulang kata "LOKET" sebanyak jumlah
        loketnya menghabiskan lebar yang seharusnya menjadi milik nomor.
        """
        self.susunan.addLayout(self._bangun_kepala())

        self.kepala_tabel = QHBoxLayout()
        self.label_kolom_tabel = []
        rata_kanan = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        rata_kiri = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        for teks, regang, rata in zip(
            ("NOMOR", "LOKET", "STATUS"),
            REGANG_TABEL,
            (rata_kiri, rata_kiri, rata_kanan),
        ):
            label = QLabel(teks)
            label.setAlignment(rata)
            label.setMinimumSize(1, 1)
            self.label_kolom_tabel.append(label)
            self.kepala_tabel.addWidget(label, stretch=regang)
        self.susunan.addLayout(self.kepala_tabel)

        self.susunan.addLayout(self._bangun_kolom_loket(), stretch=6)
        self.susunan.addWidget(self._bangun_panel_berikutnya(), stretch=4)

    def _bangun_fokus(self) -> None:
        """
        Satu nomor raksasa, loket lain sebagai pita di bawahnya.

        Untuk kantor dengan sedikit loket, dan untuk layar yang dipasang
        jauh. Kartu per loket tetap ada — pengunjung harus tetap tahu ke
        loket mana ia dipanggil — tetapi diperkecil menjadi satu pita,
        karena pertanyaan pertamanya selalu "nomor berapa sekarang".
        """
        self.susunan.addLayout(self._bangun_kepala())

        self.kartu_sorot = KartuSorot(
            kompak=self.kompak, palet=self.palet, skala_nomor=self.skala_nomor
        )
        self._bayangan(self.kartu_sorot, 70, 18)
        self.susunan.addWidget(self.kartu_sorot, stretch=6)

        self.susunan.addLayout(self._bangun_kolom_loket(mendatar=True), stretch=2)
        self.susunan.addWidget(self._bangun_panel_berikutnya(), stretch=3)

    def _bayangan(self, widget: QWidget, radius: int, y: int) -> None:
        """
        Bayangan di bawah sebuah panel, sekuat yang diminta tema.

        Tema datar (Papan LED, Kontras Tinggi) menyetel `bayangan` ke nol
        dan tidak mendapat efek sama sekali — bukan efek beralpha nol.
        QGraphicsDropShadowEffect memaksa widget-nya digambar lewat lapisan
        tersendiri, dan pada papan yang menyegar dua detik sekali itu
        biaya yang tidak dibayar apa-apa.
        """
        alpha = self.palet.bayangan
        if alpha <= 0:
            return
        efek = QGraphicsDropShadowEffect(widget)
        efek.setBlurRadius(radius)
        efek.setOffset(0, y)
        efek.setColor(QColor(0, 0, 0, alpha))
        widget.setGraphicsEffect(efek)

    # -----------------------------------------------------------------
    # Ukuran
    # -----------------------------------------------------------------

    def hitung_skala(self, tinggi: int | None = None, lebar: int | None = None) -> float:
        """
        Faktor pembesaran huruf untuk ukuran layar tertentu.

        Diambil dari sisi yang paling sempit: tinggi menentukan berapa besar
        huruf yang muat ke bawah, lebar menentukan berapa lebar nomor yang
        muat di dalam kartunya.

        Papan kios tidak pernah diskalakan: ia sudah pas pada jendela
        1100x700, dan membesarkannya di layar penuh justru menggilas panel
        ambil nomor di bawahnya.
        """
        if self.kompak:
            return 1.0
        tinggi = self.height() if tinggi is None else tinggi
        lebar = self.width() if lebar is None else lebar
        if tinggi <= 0 or lebar <= 0:
            return 1.0
        kasar = min(tinggi / TINGGI_ACUAN_TV, lebar / LEBAR_ACUAN_TV)
        return min(SKALA_MAKS, max(SKALA_MIN, kasar))

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama dari Qt
        super().resizeEvent(event)
        skala = self.hitung_skala()
        # Ambang perubahan mencegah tulis-ulang gaya pada setiap piksel
        # perubahan tinggi jendela, yang memicu tata letak berulang.
        if abs(skala - self.skala) >= 0.02:
            self.skala = skala
            self._terapkan_ukuran()

        # Ditunda sampai Qt selesai menata isinya. Tinggi panel baru
        # diketahui SETELAH tata letak berjalan, sedangkan resizeEvent tiba
        # sebelum itu; mengukur di sini juga membaca tinggi yang belum
        # final. singleShot dengan `self` sebagai konteks ikut batal
        # sendiri bila layarnya keburu ditutup.
        QTimer.singleShot(0, self, self._sesuaikan_daftar)

    def _sesuaikan_daftar(self) -> None:
        """
        Ukur ulang daftar menunggu, gambar ulang bila hurufnya berubah.

        Penggambaran pertama terjadi sebelum panel punya tinggi yang
        sebenarnya, sehingga hurufnya dihitung dari angka yang belum final
        dan nomornya terpotong beberapa piksel. Tanpa penyesuaian ini,
        pengunjung melihat papan yang salah sampai penyegaran dua detik
        berikutnya memperbaikinya sendiri.
        """
        self._batasi_panel()
        self._muatkan_huruf_kartu()
        sebelum = self._font_daftar
        self._ukur_daftar()
        if self._font_daftar != sebelum:
            self._gambar_halaman()

    def _batasi_panel(self) -> None:
        """
        Batasi tinggi panel daftar menunggu ke jatahnya. Lihat BAGIAN_PANEL.

        Papan kios dilewati: panelnya memang tidak ikut ditampilkan di sana.

        Papan yang belum pernah tampil juga dilewati, sama seperti pada
        `_ukur_daftar`: ukurannya saat itu bukan ukuran layar mana pun,
        melainkan ukuran bawaan Qt untuk widget yang baru dibuat. Memotong
        panel menurut ukuran itu berarti papan terbuka dengan daftar
        menunggu sepanjang satu baris, lalu memperbaikinya sendiri satu
        kedipan kemudian.
        """
        if self.kompak or not self.isVisible() or self.height() <= 0:
            return
        margin = self.susunan.contentsMargins()
        badan = (
            self.height()
            - margin.top()
            - margin.bottom()
            - self.kepala.sizeHint().height()
            - self.susunan.spacing() * 2
        )
        if badan <= 0:
            return
        bagian = BAGIAN_PANEL.get(self.tata_letak, 0.5)
        # Jatahnya dipatok dari dua sisi, bukan dibatasi dari atas saja.
        # Dibatasi dari atas saja, panel pada tema Sorotan dan Split
        # menyusut ke arah sebaliknya: kolom loket di atasnya mengambil
        # semua sisa, panel menyimpulkan hanya satu baris yang muat, lalu
        # meminta tinggi seukuran satu baris itu — dan tidak pernah kembali.
        #
        # Batas bawah yang tetap: papan pada jendela pengembang yang kecil
        # tidak boleh kehilangan daftar menunggunya sama sekali.
        jatah = max(100, round(badan * bagian))
        # Bento (dan kisi banyak baris) menumpuk kartu di atas panel ini.
        # Memaksa panel ke 50% badan saat kartu butuh lebih dari 50%
        # mendorong panel — dan nomor paling bawahnya — keluar tepi layar.
        if self.tata_letak in (KISI, BENTO) and self._baris_kartu >= 2:
            min_kartu = (
                round(TINGGI_BARIS_KARTU_MIN * self.skala) * self._baris_kartu
                + round(24 * self.skala) * (self._baris_kartu - 1)
            )
            jatah = min(jatah, max(100, badan - min_kartu))
        self.panel_berikutnya.setMaximumHeight(jatah)
        self.panel_berikutnya.setMinimumHeight(jatah)

    def _terapkan_ukuran(self) -> None:
        """Tulis ulang margin dan ukuran huruf sesuai skala yang berlaku."""
        p = self.palet
        skala = self.skala
        if self.kompak:
            margin = (24, 16, 24, 16)
            jarak = 12
            jarak_kisi = 12
            tinggi_panel = 88
        else:
            # Margin lapang: televisi dipandang dari jauh, dan isi yang
            # menempel ke tepi layar terbaca sebagai satu blok padat.
            # Bawah lebih dalam daripada atas: bayangan kartu jatuh ke
            # bawah, dan panel menunggu yang menempel ke tepi terbaca
            # sebagai layar yang terpotong.
            margin = tuple(round(n * skala) for n in (56, 32, 56, 44))
            jarak = round(22 * skala)
            jarak_kisi = round(24 * skala)
            tinggi_panel = round(120 * skala)

        self.susunan.setContentsMargins(*margin)
        self.susunan.setSpacing(jarak)
        # Jam menempel di bawah judul sebagai satu blok kepala, bukan
        # baris terpisah yang mengambang. Jarak besar di sini membuat
        # tanggal terbaca sebagai isi halaman, bukan keterangan judul.
        self.kepala.setSpacing(max(2, round(4 * skala)))
        if self.kisi_loket is not None:
            self.kisi_loket.setSpacing(jarak_kisi)
            # Bayangan kartu (blur 40, geser 12) digambar di luar batas
            # kisinya. Tanpa margin, tepi bawah baris kartu terakhir
            # terpotong lurus oleh widget induknya.
            if self.palet.bayangan > 0:
                s = max(8, round(10 * skala))
                self.kisi_loket.setContentsMargins(s, s, s, max(20, round(24 * skala)))
        sisi = max(16, round(20 * skala))
        atas_panel = max(10, round(14 * skala))
        bawah_panel = max(RADIUS_PANEL_TUNGGU, round(24 * skala))
        self.susunan_berikutnya.setContentsMargins(sisi, atas_panel, sisi, bawah_panel)
        self.susunan_berikutnya.setSpacing(max(6, round(8 * skala)))
        self.panel_berikutnya.setMinimumHeight(
            tinggi_panel
            if self.tata_letak in (KISI, BENTO)
            else round(tinggi_panel * 0.8)
        )

        self.label_judul.setStyleSheet(
            f"color: {p.judul}; background: transparent;"
            f" font-size: {self.px('judul')}px; font-weight: 800; letter-spacing: 4px;"
        )
        self.label_jam.setStyleSheet(
            f"color: {p.jam}; background: transparent;"
            f" font-size: {self.px('jam')}px; font-weight: 600; letter-spacing: 2px;"
        )
        # Judul dan jam tidak boleh ikut diperas ketika isi papan menuntut
        # lebih banyak tinggi daripada yang ada. Keduanya berukuran kecil
        # dan yang paling dahulu mengalah — tanpa tinggi minimum sendiri,
        # papan yang sesak menampilkan judul terpotong separuh di baris
        # paling atas, dan pengunjung membaca nama kantor yang terpenggal.
        # Kartu loket yang mengalah tidak terlihat sebagai kerusakan;
        # judul yang terpotong terlihat.
        for label in (self.label_judul, self.label_jam):
            label.setMinimumHeight(label.sizeHint().height())
        self.label_judul_berikutnya.setStyleSheet(
            f"color: {p.panel_judul}; background: transparent;"
            f" font-size: {self.px('berikutnya_judul')}px; font-weight: 700;"
            " letter-spacing: 4px;"
        )
        self.baris_berikutnya.setSpacing(round(12 * skala))

        if self.kompak and self.panel_info_kios is not None:
            self.panel_info_kios.ganti_gaya_teks(
                f"color: {p.panel_judul}; background: transparent;"
                f" font-size: {self.px('kios_info')}px; font-weight: 700;"
            )
            self.panel_info_kios.ganti_gaya_kartu(
                {
                    "judul": (
                        f"color: {p.panel_judul}; background: transparent;"
                        f" font-size: {self.px('kios_kartu_judul')}px;"
                        " font-weight: 700; letter-spacing: 3px;"
                    ),
                    "nomor": (
                        f"color: {p.nomor}; background: transparent;"
                        f" font-size: {self.px('kios_kartu_nomor')}px;"
                        " font-weight: 800;"
                    ),
                    "layanan": (
                        f"color: {p.nama}; background: transparent;"
                        f" font-size: {self.px('kios_kartu_layanan')}px;"
                        " font-weight: 700;"
                    ),
                    "sisa": (
                        f"color: {p.panel_judul}; background: transparent;"
                        f" font-size: {self.px('kios_kartu_sisa')}px;"
                        " font-weight: 600;"
                    ),
                    "arahan": (
                        f"color: {p.panel_judul}; background: transparent;"
                        f" font-size: {self.px('kios_kartu_arahan')}px;"
                        " font-weight: 600;"
                    ),
                }
            )

        if self.tata_letak == SOROTAN:
            self.label_judul_loket.setStyleSheet(
                f"color: {p.panel_judul}; background: transparent;"
                f" font-size: {self.px('berikutnya_judul')}px; font-weight: 700;"
                " letter-spacing: 5px;"
            )
        if self.tata_letak == TABEL:
            # Margin kiri-kanan judul kolom disamakan dengan padding baris
            # kartunya. Judul yang bergeser beberapa piksel dari kolomnya
            # membuat seluruh tabel terbaca miring.
            self.kepala_tabel.setContentsMargins(
                round(26 * skala), 0, round(26 * skala), 0
            )
            self.kepala_tabel.setSpacing(round(18 * skala))
            for label in self.label_kolom_tabel:
                label.setStyleSheet(
                    f"color: {p.panel_judul}; background: transparent;"
                    f" font-size: {self.px('berikutnya_judul')}px; font-weight: 700;"
                    " letter-spacing: 4px;"
                )
        if self.panel_info is not None:
            self.label_info_judul.setStyleSheet(
                f"color: {p.info_judul}; background: transparent;"
                f" font-size: {self.px('info_judul')}px; font-weight: 800;"
                " letter-spacing: 6px;"
            )
            self.label_info.setStyleSheet(
                f"color: {p.info_teks}; background: transparent;"
                f" font-size: {self.px('info')}px; font-weight: 500;"
            )
            self.panel_info.layout().setContentsMargins(
                *(round(n * skala) for n in (48, 48, 48, 48))
            )
            self.panel_info.layout().setSpacing(round(12 * skala))

        if self.kartu_sorot is not None:
            self.kartu_sorot.set_skala(
                skala * (FAKTOR_SOROT_FOKUS if self.tata_letak == FOKUS else 1.0)
            )
        self._terapkan_skala_kartu()
        # Diukur ulang, bukan sekadar digayakan ulang: tinggi panel berubah
        # bersama tinggi jendela, dan huruf yang muat pada layar sebelumnya
        # belum tentu muat pada yang sekarang.
        self._batasi_panel()
        self._ukur_daftar()
        for label in self.label_berikutnya:
            self._gaya_berikutnya(label)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Ambil keadaan terbaru dan perbarui layar."""
        self.perbarui_jam()
        berhasil, keadaan = jalankan_aman(self, lambda: self.queue.display_state(
            self.jumlah_berikutnya,
            # Papan kios tidak berkolom, sehingga pengelompokannya tidak
            # perlu disusun sama sekali.
            0 if self.kompak else self.baris_diminta * KOLOM_PER_LAYANAN * MAKS_HALAMAN,
        ))
        if not berhasil or keadaan is None:
            return
        self.tampilkan(keadaan)
        if self.panel_info_kios is not None:
            self.panel_info_kios.muat_pengaturan()

    def perbarui_jam(self) -> None:
        """Tulis tanggal dan jam terkini di kepala papan."""
        self.label_jam.setText(teks_waktu())

    def tampilkan(self, keadaan: DisplayState) -> None:
        """Perbarui layar dari sebuah keadaan. Dipisah agar mudah diuji."""
        terkini = keadaan.terkini

        if not self.kompak:
            # Papan kios tidak punya kartu loket sama sekali — lihat
            # `_bangun_info_kios`. Isi panel informasinya diganti KioskPage
            # lewat `tampilkan_info_kios()`, lepas dari penyegaran data ini.
            self._susun_kartu(keadaan.loket)
            id_unggulan = terkini.id if terkini is not None else None
            indeks_unggulan = 0
            for indeks, (kartu, loket) in enumerate(
                zip(self.kartu_loket, keadaan.loket, strict=False)
            ):
                unggulan = (
                    loket.antrian is not None and loket.antrian.id == id_unggulan
                )
                if unggulan:
                    indeks_unggulan = indeks
                kartu.tampilkan(loket, unggulan=unggulan)
            if self.tata_letak == BENTO:
                # Sel besar berpindah mengikuti panggilan terbaru. Dilakukan
                # SESUDAH kartu diisi: `_tata_kartu` membandingkan peta sel
                # yang baru dengan yang terpasang dan tidak melakukan apa-apa
                # bila loket yang memanggil masih yang itu juga.
                self._tata_kartu(indeks_unggulan)

        if self.kartu_sorot is not None:
            self.kartu_sorot.tampilkan(terkini)

        if terkini is not None:
            self._bunyikan_bila_baru(terkini)

        # Halaman TIDAK dikembalikan ke satu di sini. Penyegaran terjadi
        # dua detik sekali; mengembalikannya berarti pengunjung tidak pernah
        # melihat halaman kedua sama sekali.
        self._menunggu = keadaan.berikutnya
        self._layanan = keadaan.layanan
        self._total_menunggu = keadaan.total_menunggu
        # Diukur SEBELUM halaman dijepit: banyaknya halaman bergantung pada
        # berapa baris yang benar-benar muat, dan itu baru diketahui setelah
        # tinggi panel diukur.
        self._ukur_daftar()
        if self._halaman >= self.jumlah_halaman:
            self._halaman = 0
        self._gambar_halaman()

    def _susun_kartu(self, loket: list[DisplayCounterState]) -> None:
        """Bangun ulang kartu hanya bila jumlah atau urutan loket berubah."""
        kunci = tuple((item.counter_id, item.counter_name) for item in loket)
        if kunci == self._kunci_loket and self.kartu_loket:
            return

        berkisi = self.tata_letak in (KISI, BENTO)
        wadah = self.kisi_loket if berkisi else self.kolom_loket
        while wadah.count():
            item = wadah.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.kartu_loket = []
        self._kunci_loket = kunci
        self._sel_terpasang = None

        if not loket:
            kosong = QLabel("Belum ada loket yang aktif.")
            kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kosong.setMinimumSize(1, 1)
            kosong.setStyleSheet(
                f"color: {self.palet.panel_judul}; background: transparent;"
                f" font-size: {self.px('layanan')}px;"
            )
            if berkisi:
                wadah.addWidget(kosong, 0, 0)
            else:
                wadah.addWidget(kosong)
            return

        if berkisi or self.tata_letak == FOKUS:
            # Pita Fokus memakai kartu tegak yang diperkecil, bukan kartu
            # melebar: kartu melebar menaruh nomor di ujung kanan, dan pada
            # lebar seperlima layar nomor itu bertabrakan dengan nama
            # loketnya sendiri.
            varian = "kisi"
        elif self.tata_letak == TABEL:
            varian = "tabel"
        else:
            varian = "baris"

        # Tema Fokus menjajarkan loketnya mendatar sebagai satu pita, jadi
        # berapa pun loketnya, yang bertumpuk tetap satu baris.
        self._baris_kartu = 1 if self.tata_letak == FOKUS else len(loket)
        # Sel besar hanya ada pada bento; `_tata_kartu` yang menentukannya.
        self._indeks_besar = -1

        for _item in loket:
            kartu = KartuLoket(
                kompak=self.kompak,
                palet=self.palet,
                varian=varian,
                skala_nomor=self.skala_nomor,
            )
            kartu.set_skala(self.skala_kartu)
            # Baris tabel tidak berbayang. Bayangan di bawah baris yang
            # dipisahkan garis rambut menebalkan garis itu tidak merata,
            # dan tabelnya terbaca seolah tercetak miring.
            if varian != "tabel":
                self._bayangan(kartu, 40, 12)
            self.kartu_loket.append(kartu)
            if not berkisi:
                self.kolom_loket.addWidget(kartu, stretch=1)

        if berkisi:
            self._tata_kartu()

    def _tata_kartu(self, unggulan: int = 0) -> None:
        """
        Tempatkan kartu di dalam kisi.

        Kisi biasa membagi loket menjadi baris bertiga. Bento memberi loket
        yang sedang memanggil satu sel besar dan menyusun sisanya di
        sekelilingnya, sehingga papan menjawab "loket mana" bahkan sebelum
        nomornya dibaca.

        Kartunya dipindahkan, bukan dibuat ulang: membangun ulang kartu
        setiap panggilan berarti bayangan, gaya, dan skalanya dihitung
        ulang dua detik sekali pada papan yang tidak pernah dimatikan.
        """
        if self.kisi_loket is None or not self.kartu_loket:
            return

        jumlah = len(self.kartu_loket)
        if self.tata_letak == BENTO:
            sel = _sel_bento(jumlah, unggulan)
        else:
            kolom = min(3, jumlah)
            sel = [(i // kolom, i % kolom, 1, 1) for i in range(jumlah)]
        if sel == self._sel_terpasang:
            return

        while self.kisi_loket.count():
            # takeAt melepas kartu dari tata letak tanpa menghapusnya;
            # ketiganya langsung dipasang kembali di bawah ini.
            self.kisi_loket.takeAt(0)
        for kartu, (baris, kolom, rentang_baris, rentang_kolom) in zip(
            self.kartu_loket, sel, strict=False
        ):
            self.kisi_loket.addWidget(
                kartu, baris, kolom, rentang_baris, rentang_kolom
            )

        # Regangan disamakan supaya sel besar benar-benar dua kali sel
        # kecil. Tanpa ini Qt membagi ruang menurut isi masing-masing sel,
        # dan kolom berisi nomor terpanjang yang paling melebar.
        #
        # Kolom di luar yang terpakai WAJIB dikembalikan ke nol. QGridLayout
        # tidak pernah menyusutkan jumlah kolomnya sendiri, dan kolom sisa
        # dari susunan sebelumnya yang masih beregangan satu akan memakan
        # lebarnya sendiri — lubang kosong di tepi papan yang tidak berisi
        # apa pun.
        kolom_terpakai = max(kolom + lebar for _, kolom, _, lebar in sel)
        baris_terpakai = max(baris + tinggi for baris, _, tinggi, _ in sel)
        for kolom in range(max(self.kisi_loket.columnCount(), kolom_terpakai)):
            self.kisi_loket.setColumnStretch(kolom, 1 if kolom < kolom_terpakai else 0)
        for baris in range(max(self.kisi_loket.rowCount(), baris_terpakai)):
            self.kisi_loket.setRowStretch(baris, 1 if baris < baris_terpakai else 0)
        self._sel_terpasang = sel

        # Baris kisi, bukan jumlah loket: enam loket bertiga sebaris hanya
        # menumpuk dua baris, dan bento menumpuk dua baris bahkan dengan
        # tiga loket karena sel besarnya setinggi dua sel kecil.
        self._baris_kartu = baris_terpakai
        self._indeks_besar = unggulan if self.tata_letak == BENTO else -1
        self._terapkan_skala_kartu()
        # Ditunda: tinggi sel baru diketahui setelah Qt menata ulang kisi.
        QTimer.singleShot(0, self, self._muatkan_huruf_kartu)

    def _bunyikan_bila_baru(self, terkini) -> None:
        """
        Bunyikan nada hanya untuk panggilan yang benar-benar baru.

        Penandanya adalah pasangan (id antrian, jumlah panggilan), sehingga
        panggilan ULANG pada nomor yang sama tetap berbunyi, sementara
        penyegaran biasa tidak.
        """
        penanda = (terkini.id, terkini.jumlah_panggilan)
        if penanda == self._terakhir_dibunyikan:
            return

        self._terakhir_dibunyikan = penanda
        if self.suara_aktif:
            self.sound.announce(terkini.queue_number, terkini.counter_name)

    def _gaya_berikutnya(self, label: QLabel) -> None:
        # Kartu dan angkanya diambil dari palet tema, dan setiap palet
        # memasangkan latar dengan warna teks yang berlawanan terang-gelap;
        # teks yang senada dengan latarnya hampir tidak terbaca dari jauh.
        # rgba(), bukan #RRGGBBAA. Qt tidak mendukung heksadesimal delapan
        # digit dan akan membacanya sebagai warna yang sama sekali berbeda.
        p = self.palet
        # Tinggi MINIMUM sengaja hanya sebesar huruf terkecil yang masih
        # pantas, bukan setinggi baris yang dihitung.
        #
        # Minimum yang setinggi barisnya membuat kisi menuntut lebih dari
        # jatah panelnya, panel mendorong tepi bawah layar, dan tinggi yang
        # terbaca `_ukur_daftar()` ikut membengkak — pengukuran berikutnya
        # memakai angka yang sudah meluber itu dan meluber lagi. Dengan
        # minimum yang rendah, panel selalu persis sebesar jatahnya, dan
        # kartu memuai sendiri mengisi sisanya lewat SizePolicy Expanding.
        label.setMinimumHeight(self._tinggi_baris_untuk(FONT_DAFTAR_MIN))
        label.setStyleSheet(
            f"color: {p.chip_teks}; background: {p.chip};"
            f" border: {TEPI_NOMOR}px solid {p.chip_tepi};"
            f" border-radius: {p.radius_chip}px;"
            f" font-size: {self._font_daftar}px; font-weight: 800;"
            f" letter-spacing: {p.renggang_nomor}px;"
            f" padding: {PADDING_NOMOR_Y}px 12px;"
        )

    @property
    def berotasi(self) -> bool:
        """
        Daftar menunggu berpindah halaman sendiri.

        Tidak berlaku pada papan kios: pengunjung berdiri di depannya
        beberapa detik untuk mengambil nomor, dan daftar yang berpindah
        sendiri di sana hanya menarik matanya dari tombol layanan.
        """
        return not self.kompak and self.jeda_putar_ms > 0

    @property
    def kolom_daftar(self) -> int:
        """Kolom kisi daftar menunggu, mengikuti lebar panel yang tersedia."""
        return KOLOM_DAFTAR_SEMPIT if self.panel_sempit else KOLOM_DAFTAR

    @property
    def panel_sempit(self) -> bool:
        """
        Panel daftar menunggu berdiri di kolom samping, bukan melintang.

        Sorotan dan Split menaruhnya di kolom kanan yang hanya sekitar 40%
        lebar layar; tema lain memberinya seluruh lebar papan.
        """
        return self.tata_letak in (SOROTAN, SPLIT)

    @property
    def kolom_per_layanan(self) -> int:
        """Kolom nomor untuk setiap jenis layanan, mengikuti lebar panel."""
        return (
            KOLOM_PER_LAYANAN_SEMPIT if self.panel_sempit else KOLOM_PER_LAYANAN
        )

    @property
    def berkolom_layanan(self) -> bool:
        """
        Daftar menunggu dipecah menjadi satu kolom per jenis layanan.

        Tiga jenis layanan berarti tiga kolom. Papan kios tidak pernah
        berkolom — tempatnya hanya sederet nomor — dan kantor dengan jenis
        layanan lebih banyak daripada `MAKS_KOLOM_LAYANAN` kembali ke
        daftar gabungan, yang pada lebar sesempit itu justru lebih terbaca.
        """
        return not self.kompak and 0 < len(self._layanan) <= MAKS_KOLOM_LAYANAN

    @property
    def baris_daftar(self) -> int:
        """
        Baris nomor per kolom, setelah dijepit oleh tinggi papan.

        Pengaturan admin diperlakukan sebagai permintaan, bukan perintah.
        Lima baris yang diminta pada papan yang hanya sanggup tiga akan
        diperas Qt melewati tinggi minimumnya, dan hurufnya terpotong di
        kedua ujung — kegagalan yang tidak terlihat sebagai kesalahan
        pengaturan sama sekali.
        """
        return max(1, min(self.baris_diminta, self._baris_muat))

    @property
    def muat_per_halaman(self) -> int:
        """Nomor yang tampil per jenis layanan dalam satu halaman."""
        return self.baris_daftar * self.kolom_per_layanan

    @property
    def jumlah_halaman(self) -> int:
        """
        Banyaknya halaman daftar menunggu. Minimal satu, walau kosong.

        Pada tampilan berkolom, yang menentukan adalah layanan TERPANJANG:
        halaman berhenti setelah layanan yang paling ramai habis, bukan
        setelah yang paling sepi.
        """
        if self.berkolom_layanan:
            terpanjang = max((len(l.menunggu) for l in self._layanan), default=0)
            return max(1, -(-terpanjang // self.muat_per_halaman))
        if not self._menunggu:
            return 1
        return -(-len(self._menunggu) // self.muat_per_halaman)

    def putar_halaman(self) -> None:
        """
        Pindah ke halaman berikutnya daftar menunggu.

        Diam bila hanya ada satu halaman. Halaman yang "berpindah" ke
        dirinya sendiri terbaca sebagai layar berkedip yang rusak, bukan
        sebagai daftar yang berputar.
        """
        if self.jumlah_halaman <= 1:
            return
        self._halaman = (self._halaman + 1) % self.jumlah_halaman
        self._gambar_halaman()

    def _gambar_halaman(self) -> None:
        """Tulis halaman yang sedang aktif beserta keterangannya."""
        awal = self._halaman * self.muat_per_halaman
        # Papan yang benar-benar kosong mendapat satu kalimat, bukan tiga
        # kolom berisi strip. Pagi hari sebelum pengunjung pertama datang,
        # "Tidak ada antrian menunggu" menjawab pertanyaannya langsung.
        if self.berkolom_layanan and self._total_menunggu:
            self._isi_per_layanan(awal)
        else:
            self._isi_berikutnya(self._menunggu[awal : awal + self.muat_per_halaman])
        self.label_judul_berikutnya.setText(self._judul_daftar())

    def _judul_daftar(self) -> str:
        """
        Judul panel beserta nomor halaman dan sisa yang tidak termuat.

        Nomor halaman wajib terlihat. Tanpanya, pengunjung yang tidak
        menemukan nomornya menyimpulkan nomornya hilang dan bertanya ke
        loket — persis pekerjaan yang papan ini ada untuk mengurangi.
        """
        judul = "MENUNGGU GILIRAN"
        if self.jumlah_halaman > 1:
            judul += f"   {self._halaman + 1} / {self.jumlah_halaman}"

        tampil = (
            sum(len(l.menunggu) for l in self._layanan)
            if self.berkolom_layanan
            else len(self._menunggu)
        )
        sisa = self._total_menunggu - tampil
        if sisa > 0:
            judul += f"   ·   DAN {sisa} LAINNYA"
        return judul

    def _tinggi_baris_untuk(self, px: int) -> int:
        """
        Tinggi yang benar-benar dibutuhkan satu kartu nomor pada font ini.

        Diambil dari metrik huruf, bukan dari konstanta. Konstanta yang
        dahulu dipakai (68px) ditetapkan ketika nomor masih berjejer
        MENDATAR dalam satu baris, dan di sana tinggi tidak pernah menjadi
        kendala. Begitu nomor ditumpuk ke bawah, konstanta itu ternyata
        11px lebih pendek daripada hurufnya sendiri — setiap kartu
        terpotong bahkan sebelum kisinya diperas.
        """
        font = QFont(self.font())
        font.setPixelSize(max(1, px))
        font.setWeight(QFont.Weight.ExtraBold)
        return QFontMetrics(font).height() + PADDING_NOMOR_Y * 2 + TEPI_NOMOR * 2

    def _tinggi_judul_kolom(self) -> int:
        """
        Tinggi baris nama jenis layanan di DALAM kisi.

        Ikut memakan tinggi kisi, terpisah dari judul panel di atasnya.
        Terlewat dari perhitungan, seluruh panel menjadi lebih tinggi
        daripada jatahnya dan meluber keluar tepi bawah layar.
        """
        font = QFont(self.font())
        font.setPixelSize(self.px("berikutnya_kolom"))
        font.setWeight(QFont.Weight.Bold)
        return QFontMetrics(font).height() + 4

    def _tinggi_kisi_tersedia(self) -> int:
        """Tinggi yang tersisa di dalam panel setelah judul dan marginnya."""
        tinggi = self.panel_berikutnya.height()
        if tinggi <= 0:
            return 0
        margin = self.susunan_berikutnya.contentsMargins()
        return (
            tinggi
            - margin.top()
            - margin.bottom()
            - self._tinggi_judul_panel()
            - self.susunan_berikutnya.spacing()
        )

    def _tinggi_judul_panel(self) -> int:
        """
        Tinggi judul panel daftar menunggu pada lebar yang dimilikinya.

        Diukur dengan heightForWidth, bukan sizeHint. Judulnya boleh
        melipat, dan sizeHint sebuah label yang melipat adalah tinggi pada
        lebar yang dikira-kira Qt sendiri — bukan pada lebar panel ini.
        Selisihnya terbaca sebagai tinggi yang hilang, dan seluruh nomor
        menunggu ikut mengecil sampai batas terkecilnya tanpa sebab.
        """
        judul = self.label_judul_berikutnya
        margin = self.susunan_berikutnya.contentsMargins()
        lebar = self.panel_berikutnya.width() - margin.left() - margin.right()
        if judul.wordWrap() and lebar > 0:
            return judul.heightForWidth(lebar)
        return judul.sizeHint().height()

    def _ukur_daftar(self) -> None:
        """
        Sesuaikan huruf dan tinggi baris dengan tinggi panel yang ADA.

        Ukuran huruf papan diturunkan dari ukuran JENDELA lewat `skala`,
        dan itu memadai selama nomor berjejer mendatar. Daftar bertumpuk
        lima baris menjadikan tinggi panel — bukan tinggi jendela — yang
        menentukan, dan keduanya tidak sebanding: papan hanya mendapat
        separuh layar dikurangi kepala dan margin.

        Dua hasilnya: berapa baris yang muat sama sekali (`_baris_muat`,
        dihitung pada huruf terkecil yang masih pantas), dan huruf terbesar
        yang memuat baris sebanyak itu tanpa terpotong.
        """
        nominal = self.font_diminta or self.px("berikutnya")
        tersedia = self._tinggi_kisi_tersedia()
        jarak = round(12 * self.skala)
        if self.berkolom_layanan:
            tersedia -= self._tinggi_judul_kolom() + jarak

        if tersedia <= 0:
            # Jendela belum pernah ditampilkan. Dibiarkan pada ukuran
            # nominal; resizeEvent akan mengukur ulang begitu ada geometri.
            self._baris_muat = 99
            self._font_daftar = nominal
            self._tinggi_baris = self._tinggi_baris_untuk(nominal)
            return

        terkecil = self._tinggi_baris_untuk(FONT_DAFTAR_MIN)
        self._baris_muat = max(1, (tersedia + jarak) // (terkecil + jarak))

        baris = self.baris_daftar
        px = nominal
        while px > FONT_DAFTAR_MIN:
            butuh = baris * self._tinggi_baris_untuk(px) + (baris - 1) * jarak
            if butuh <= tersedia:
                break
            px -= 1

        self._font_daftar = px
        self._tinggi_baris = self._tinggi_baris_untuk(px)

    def _kosongkan_daftar(self) -> None:
        while self.baris_berikutnya.count():
            item = self.baris_berikutnya.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.label_berikutnya = []

        # Regangan kolom TIDAK ikut terhapus bersama widget-nya. Tanpa
        # dikembalikan ke nol, kolom milik jenis layanan yang baru
        # dinonaktifkan tetap memakan lebarnya sendiri dan meninggalkan
        # lubang kosong di tengah papan.
        for kolom in range(self.baris_berikutnya.columnCount()):
            self.baris_berikutnya.setColumnStretch(kolom, 0)

    def _label_kosong(self, teks: str) -> QLabel:
        """Keterangan datar, dipakai saat sebuah kolom atau papan tidak berisi."""
        label = QLabel(teks)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(1, 1)
        label.setStyleSheet(
            f"color: {self.palet.panel_judul}; background: transparent;"
            f" font-size: {self.px('berikutnya_judul')}px;"
        )
        return label

    def _isi_per_layanan(self, awal: int) -> None:
        """
        Satu kolom per jenis layanan, masing-masing menampilkan halaman
        yang sama.

        Baris teratas adalah nama layanannya. Tanpa itu, tiga kolom nomor
        berdampingan tidak memberi tahu pengunjung kolom mana yang miliknya
        — dan huruf depan nomor saja terlalu kecil untuk dipakai menebak
        dari seberang ruangan.
        """
        self._kosongkan_daftar()

        for kolom, layanan in enumerate(self._layanan):
            kiri = kolom * self.kolom_per_layanan
            # Pada kolom sempit hanya awalannya yang ditulis. Nama layanan
            # yang terpotong di tengah kata ("Customer Servi") tidak
            # memberi tahu apa pun, sedangkan awalannya adalah huruf yang
            # persis sama dengan huruf pertama nomor di bawahnya.
            judul = QLabel(
                layanan.category_prefix
                if self.panel_sempit
                else f"{layanan.category_prefix} · {layanan.category_name}"
            )
            judul.setAlignment(Qt.AlignmentFlag.AlignCenter)
            judul.setMinimumSize(1, 1)
            judul.setStyleSheet(
                f"color: {self.palet.panel_judul}; background: transparent;"
                f" font-size: {self.px('berikutnya_kolom')}px; font-weight: 700;"
                " letter-spacing: 2px;"
            )
            # Judul melintang di atas kedua sub-kolom layanan ini.
            self.baris_berikutnya.addWidget(
                judul, 0, kiri, 1, self.kolom_per_layanan
            )

            potongan = layanan.menunggu[awal : awal + self.muat_per_halaman]
            if not potongan:
                # Kolom kosong tetap diberi tanda. Kolom yang benar-benar
                # hampa terbaca sebagai bagian layar yang gagal termuat,
                # bukan sebagai layanan yang memang sedang sepi.
                self.baris_berikutnya.addWidget(
                    self._label_kosong("—"), 1, kiri, 1, self.kolom_per_layanan
                )
                continue

            for indeks, antrian in enumerate(potongan):
                label = QLabel(antrian.queue_number)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setMinimumSize(1, 1)
                label.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
                )
                self._gaya_berikutnya(label)
                self.label_berikutnya.append(label)
                # Menurun dulu, baru pindah ke sub-kolom kanan — urutan
                # baca koran. Nomor antrian punya urutan, dan mengisinya
                # mendatar membuat yang kedua duduk di sebelah kanan yang
                # pertama seolah keduanya sederajat.
                self.baris_berikutnya.addWidget(
                    label,
                    indeks % self.baris_daftar + 1,
                    kiri + indeks // self.baris_daftar,
                )

        for kolom in range(len(self._layanan) * self.kolom_per_layanan):
            self.baris_berikutnya.setColumnStretch(kolom, 1)

    def _isi_berikutnya(self, berikutnya: list) -> None:
        """Daftar gabungan, dipakai papan kios dan saat jenis layanan terlalu banyak."""
        self._kosongkan_daftar()

        if not berikutnya:
            self.baris_berikutnya.addWidget(
                self._label_kosong("Tidak ada antrian menunggu"), 0, 0
            )
            return

        # Kolom dihitung dari isinya, bukan dipatok. Tiga nomor pada kisi
        # lima kolom akan berdesak di sepertiga kiri panel dan menyisakan
        # dua kolom kosong yang terbaca sebagai layar setengah termuat.
        baris = -(-len(berikutnya) // self.kolom_daftar)
        kolom = -(-len(berikutnya) // baris)

        for indeks, antrian in enumerate(berikutnya):
            label = QLabel(antrian.queue_number)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(1, 1)
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self._gaya_berikutnya(label)
            self.label_berikutnya.append(label)
            self.baris_berikutnya.addWidget(label, indeks // kolom, indeks % kolom)

    def hentikan(self) -> None:
        """Hentikan penyegaran berkala. Dipanggil saat layar ditutup."""
        self.pewaktu.stop()
        self.pewaktu_jam.stop()
        self.pewaktu_halaman.stop()
        if self.panel_info_kios is not None:
            self.panel_info_kios.hentikan()
