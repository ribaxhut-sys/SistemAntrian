"""Layar antrian untuk pengunjung."""

from __future__ import annotations

from datetime import datetime

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
from app.ui.display.tema import KISI, SOROTAN, SPLIT, TEMA_BAWAAN, Palet, palet_untuk

logger = get_logger("ui.display")

#: Selang penyegaran. Layar ini menghadap pengunjung yang sedang menunggu,
#: sehingga jeda beberapa detik sudah terasa lama.
SELANG_SEGAR_MS = 2_000

#: Jam berdetik sendiri, terpisah dari penyegaran data. Menyatukan keduanya
#: berarti memilih antara jam yang melompat dua detik sekali atau membebani
#: database sekali per detik.
SELANG_JAM_MS = 1_000

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
    "berikutnya": 46,
    # Varian baris: kartu melebar, nomornya di kanan nama loket.
    "nama_baris": 26,
    "status_baris": 20,
    "nomor_baris": 84,
    # Panel sorotan.
    "sorot_pil": 22,
    "sorot_nomor": 224,
    "sorot_nama": 62,
    "sorot_layanan": 28,
    # Panel pengumuman tema split.
    "info_judul": 32,
    "info": 26,
}

#: Ukuran huruf papan di dalam kios. Layar kios dibaca dari jarak satu
#: lengan dan harus berbagi tempat dengan panel ambil nomor, jadi papannya
#: tetap kompak berapa pun besar layarnya.
UKURAN_KIOS: dict[str, int] = {
    "judul": 22,
    "jam": 15,
    "nama": 16,
    "status": 13,
    "nomor": 64,
    "layanan": 15,
    "berikutnya_judul": 15,
    "berikutnya": 28,
    "nama_baris": 15,
    "status_baris": 12,
    "nomor_baris": 40,
    "sorot_pil": 12,
    "sorot_nomor": 100,
    "sorot_nama": 28,
    "sorot_layanan": 15,
    "info_judul": 18,
    "info": 14,
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


class KartuLoket(QFrame):
    """
    Satu loket: nama, nomor yang sedang ditangani, dan jenis layanan.

    Dua bentuk, ditentukan `varian`:

    * ``"kisi"`` — kartu tegak, nomor di tengah. Dipakai tema berbentuk kisi.
    * ``"baris"`` — kartu melebar, nama di kiri dan nomor di kanan. Dipakai
      kolom loket pada tema Sorotan dan Split, yang harus memuat semua loket
      dalam satu kolom sempit.
    """

    #: Kunci ukuran yang ikut dikalikan `skala_nomor` — nomor antrian saja,
    #: bukan nama loket atau status, supaya pengaturannya benar-benar hanya
    #: membesarkan angka yang dibaca dari jarak jauh.
    _KUNCI_NOMOR = frozenset({"nomor", "nomor_baris"})

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
        self.pakai_pita = bool(self.palet.pita) and varian != "baris"
        self.ukuran = UKURAN_KIOS if kompak else UKURAN_TV
        self.skala = 1.0
        #: Faktor tambahan dari pengaturan `display.number_font_scale`,
        #: terpisah dari `skala` (yang mengikuti besar layar).
        self.skala_nomor = skala_nomor
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
        kiri.addWidget(self.label_layanan)
        self.susunan_isi.addLayout(kiri)
        self.susunan_isi.addStretch()
        self.label_nomor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.susunan_isi.addWidget(self.label_nomor)

    # -----------------------------------------------------------------

    def px(self, kunci: str) -> int:
        """Ukuran huruf setelah diskalakan terhadap besar layar."""
        dasar = self.ukuran[kunci] * self.skala
        if kunci in self._KUNCI_NOMOR:
            dasar *= self.skala_nomor
        return max(10, round(dasar))

    def set_skala(self, skala: float) -> None:
        """Ubah skala huruf. Diabaikan bila perubahannya tidak berarti."""
        if abs(skala - self.skala) < 0.02:
            return
        self.skala = skala
        self._tulis_gaya()

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
        skala = self.skala
        baris = self.varian == "baris"

        if self.kompak:
            padding = (14, 10, 14, 12) if not baris else (14, 10, 14, 10)
            tinggi_pita = 6
            jarak = 4
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

        kunci_nama = "nama_baris" if baris else "nama"
        kunci_status = "status_baris" if baris else "status"
        kunci_nomor = "nomor_baris" if baris else "nomor"

        warna_nomor = p.nomor if not self._kosong else p.nomor_kosong
        warna_status = p.status_unggulan if self._unggulan else p.status

        self.label_nama.setStyleSheet(
            f"color: {p.nama}; background: transparent;"
            f" font-size: {self.px(kunci_nama)}px; font-weight: 800; letter-spacing: 3px;"
        )
        if p.status_berpil and not baris:
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
            latar, tepi, tebal = p.kartu, p.tepi_unggulan, 3
        elif self._unggulan:
            latar, tepi, tebal = p.kartu_unggulan, p.tepi_unggulan, 3
        elif self._kosong:
            latar, tepi, tebal = p.kartu_kosong, p.tepi_kartu, 2
        else:
            latar, tepi, tebal = p.kartu, p.tepi_kartu, 2

        radius = p.radius if not self.kompak else max(12, p.radius - 8)
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

        self.label_status.setStyleSheet(
            f"color: #FFFFFF; background: {p.pil_latar};"
            f" border-radius: {max(12, round(22 * skala))}px;"
            f" font-size: {self.px('sorot_pil')}px; font-weight: 800;"
            f" letter-spacing: 4px; padding: {round(10 * skala)}px {round(26 * skala)}px;"
        )
        self.label_nomor.setStyleSheet(
            f"color: #0B1220; background: transparent;"
            f" font-size: {self.px('sorot_nomor')}px; font-weight: 800;"
        )
        self.label_nama.setStyleSheet(
            f"color: {p.pil_latar}; background: transparent;"
            f" font-size: {self.px('sorot_nama')}px; font-weight: 800; letter-spacing: 6px;"
        )
        self.label_layanan.setStyleSheet(
            "color: #475569; background: transparent;"
            f" font-size: {self.px('sorot_layanan')}px; font-weight: 600;"
        )
        self.setStyleSheet(
            f"QFrame#kartuSorot {{ background: {p.kartu_unggulan};"
            f" border-radius: {round(36 * skala)}px;"
            f" border: 3px solid {p.tepi_unggulan}; }}"
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
        #: Hanya ada pada tata letak kisi.
        self.kisi_loket: QGridLayout | None = None

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
        else:
            self._bangun_kisi()
        self._terapkan_ukuran()

    # --- bagian yang dipakai bersama ---------------------------------

    def _bangun_kepala(self) -> QHBoxLayout:
        """Judul di kiri, tanggal dan jam di kanan."""
        self.kepala = QHBoxLayout()

        self.label_judul = QLabel(self.settings.get("display.title"))
        self.label_judul.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.label_judul.setMinimumSize(1, 1)
        self.kepala.addWidget(self.label_judul)
        self.kepala.addStretch()

        # Jam sengaja lebih kecil daripada nomor loket. Yang dicari
        # pengunjung dari seberang ruangan adalah nomornya, bukan jamnya.
        self.label_jam = QLabel(teks_waktu())
        self.label_jam.setObjectName("jamPapan")
        self.label_jam.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.label_jam.setMinimumSize(1, 1)
        self.kepala.addWidget(self.label_jam)
        return self.kepala

    def _bangun_panel_berikutnya(self) -> QWidget:
        self.panel_berikutnya = QFrame()
        self.panel_berikutnya.setObjectName("panelBerikutnya")
        self.panel_berikutnya.setStyleSheet(
            f"QFrame#panelBerikutnya {{ background: {self.palet.panel};"
            " border-radius: 20px; }"
        )

        self.susunan_berikutnya = QVBoxLayout(self.panel_berikutnya)
        self.susunan_berikutnya.setContentsMargins(20, 12, 20, 14)
        self.susunan_berikutnya.setSpacing(8)

        self.label_judul_berikutnya = QLabel("MENUNGGU GILIRAN")
        self.label_judul_berikutnya.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_judul_berikutnya.setMinimumSize(1, 1)
        self.susunan_berikutnya.addWidget(self.label_judul_berikutnya)

        # Kisi, bukan satu baris: daftar menunggu televisi memuat sepuluh
        # nomor atau lebih sekaligus, dan sepuluh nomor sebaris menjadi
        # terlalu kecil untuk dibaca dari seberang ruangan.
        self.baris_berikutnya = QGridLayout()
        self.susunan_berikutnya.addLayout(self.baris_berikutnya, stretch=1)
        return self.panel_berikutnya

    def _bangun_kolom_loket(self) -> QVBoxLayout:
        """Kolom kartu melebar, satu baris per loket."""
        self.kolom_loket = QVBoxLayout()
        self.kolom_loket.setSpacing(14)
        return self.kolom_loket

    # --- tata letak per tema -----------------------------------------

    def _bangun_kisi(self) -> None:
        self.susunan.addLayout(self._bangun_kepala())

        if self.kompak:
            # Papan kios TIDAK menampilkan kartu per loket. Pengunjung yang
            # berdiri di anjungan belum memegang nomor sama sekali, sehingga
            # "loket mana yang kosong" bukan pertanyaannya — itu urusan
            # orang yang sudah punya tiket, dan televisi ruang tunggu yang
            # menjawabnya. Yang berguna baginya sekadar seberapa ramai
            # kantor ini sekarang, lewat `_bangun_ringkasan_kios`.
            self.susunan.addWidget(self._bangun_ringkasan_kios(), stretch=1)
            self.susunan.addWidget(self._bangun_panel_berikutnya(), stretch=4)
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

    def _bangun_ringkasan_kios(self) -> QWidget:
        """Angka tunggal: berapa banyak antrian yang sedang berlangsung."""
        panel = QFrame()
        panel.setObjectName("panelRingkasKios")
        panel.setStyleSheet(
            f"QFrame#panelRingkasKios {{ background: {self.palet.panel};"
            " border-radius: 20px; }"
        )

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(16, 8, 16, 8)
        susunan.setSpacing(0)
        susunan.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label_ringkas_angka = QLabel("0")
        self.label_ringkas_angka.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_ringkas_angka.setMinimumSize(1, 1)
        susunan.addWidget(self.label_ringkas_angka)

        self.label_ringkas_caption = QLabel("ANTRIAN SEDANG BERLANGSUNG")
        self.label_ringkas_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_ringkas_caption.setMinimumSize(1, 1)
        susunan.addWidget(self.label_ringkas_caption)

        return panel

    def _bangun_sorotan(self) -> None:
        self.susunan.addLayout(self._bangun_kepala())

        isi = QHBoxLayout()
        isi.setSpacing(28)

        self.kartu_sorot = KartuSorot(
            kompak=self.kompak, palet=self.palet, skala_nomor=self.skala_nomor
        )
        self._bayangan(self.kartu_sorot, 60, 16, 120)
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
        # Header melintang penuh, sama seperti tema Sorotan. Ditaruh di
        # dalam kolom kanan yang hanya ~40% lebar layar, judul dan jam
        # bertumpuk karena keduanya menuntut ruang yang tidak dimiliki
        # kolom sesempit itu.
        self.susunan.addLayout(self._bangun_kepala())

        isi = QHBoxLayout()
        isi.setSpacing(28)

        # --- panel pengumuman
        self.panel_info = QFrame()
        self.panel_info.setObjectName("panelInfo")
        self.panel_info.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.panel_info.setStyleSheet(
            "QFrame#panelInfo { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #123A52, stop:1 #0F766E); border-radius: 32px; }"
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

    @staticmethod
    def _bayangan(widget: QWidget, radius: int, y: int, alpha: int) -> None:
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
        sebelum = self._font_daftar
        self._ukur_daftar()
        if self._font_daftar != sebelum:
            self._gambar_halaman()

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
            margin = tuple(round(n * skala) for n in (56, 32, 56, 32))
            jarak = round(22 * skala)
            jarak_kisi = round(24 * skala)
            tinggi_panel = round(120 * skala)

        self.susunan.setContentsMargins(*margin)
        self.susunan.setSpacing(jarak)
        self.kepala.setSpacing(round(16 * skala))
        if self.kisi_loket is not None:
            self.kisi_loket.setSpacing(jarak_kisi)
        self.panel_berikutnya.setMinimumHeight(
            tinggi_panel if self.tata_letak == KISI else round(tinggi_panel * 0.8)
        )

        self.label_judul.setStyleSheet(
            f"color: {p.judul}; background: transparent;"
            f" font-size: {self.px('judul')}px; font-weight: 800; letter-spacing: 4px;"
        )
        self.label_jam.setStyleSheet(
            f"color: {p.jam}; background: transparent;"
            f" font-size: {self.px('jam')}px; font-weight: 600; letter-spacing: 2px;"
        )
        self.label_judul_berikutnya.setStyleSheet(
            f"color: {p.panel_judul}; background: transparent;"
            f" font-size: {self.px('berikutnya_judul')}px; font-weight: 700;"
            " letter-spacing: 4px;"
        )
        self.baris_berikutnya.setSpacing(round(12 * skala))

        if self.kompak:
            self.label_ringkas_angka.setStyleSheet(
                f"color: {p.nomor}; background: transparent;"
                f" font-size: {self.px('nomor_baris')}px; font-weight: 800;"
            )
            self.label_ringkas_caption.setStyleSheet(
                f"color: {p.panel_judul}; background: transparent;"
                f" font-size: {self.px('status_baris')}px; font-weight: 700;"
                " letter-spacing: 3px;"
            )

        if self.tata_letak == SOROTAN:
            self.label_judul_loket.setStyleSheet(
                f"color: {p.panel_judul}; background: transparent;"
                f" font-size: {self.px('berikutnya_judul')}px; font-weight: 700;"
                " letter-spacing: 5px;"
            )
        if self.panel_info is not None:
            self.label_info_judul.setStyleSheet(
                "color: #CFFAFE; background: transparent;"
                f" font-size: {self.px('info_judul')}px; font-weight: 800;"
                " letter-spacing: 6px;"
            )
            self.label_info.setStyleSheet(
                "color: #E0F2FE; background: transparent;"
                f" font-size: {self.px('info')}px; font-weight: 500;"
            )
            self.panel_info.layout().setContentsMargins(
                *(round(n * skala) for n in (48, 48, 48, 48))
            )
            self.panel_info.layout().setSpacing(round(12 * skala))

        if self.kartu_sorot is not None:
            self.kartu_sorot.set_skala(skala)
        for kartu in self.kartu_loket:
            kartu.set_skala(skala)
        # Diukur ulang, bukan sekadar digayakan ulang: tinggi panel berubah
        # bersama tinggi jendela, dan huruf yang muat pada layar sebelumnya
        # belum tentu muat pada yang sekarang.
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

    def perbarui_jam(self) -> None:
        """Tulis tanggal dan jam terkini di kepala papan."""
        self.label_jam.setText(teks_waktu())

    def tampilkan(self, keadaan: DisplayState) -> None:
        """Perbarui layar dari sebuah keadaan. Dipisah agar mudah diuji."""
        terkini = keadaan.terkini

        if self.kompak:
            # Papan kios tidak punya kartu loket sama sekali — lihat
            # `_bangun_ringkasan_kios`. Ganti dengan angka tunggal.
            self._perbarui_ringkasan_kios(keadaan)
        else:
            self._susun_kartu(keadaan.loket)
            id_unggulan = terkini.id if terkini is not None else None
            for kartu, loket in zip(self.kartu_loket, keadaan.loket, strict=False):
                unggulan = (
                    loket.antrian is not None and loket.antrian.id == id_unggulan
                )
                kartu.tampilkan(loket, unggulan=unggulan)

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

    def _perbarui_ringkasan_kios(self, keadaan: DisplayState) -> None:
        """
        Hitung berapa antrian yang sedang berlangsung SEKARANG.

        Bukan sekadar `total_menunggu`: nomor yang sudah dipanggil dan
        sedang dilayani juga masih "berlangsung", belum selesai — hanya
        yang sudah COMPLETED/CANCELLED/NO_SHOW yang tidak lagi dihitung.
        """
        sedang_dilayani = sum(1 for l in keadaan.loket if l.antrian is not None)
        berlangsung = keadaan.total_menunggu + sedang_dilayani
        self.label_ringkas_angka.setText(str(berlangsung))

    def _susun_kartu(self, loket: list[DisplayCounterState]) -> None:
        """Bangun ulang kartu hanya bila jumlah atau urutan loket berubah."""
        kunci = tuple((item.counter_id, item.counter_name) for item in loket)
        if kunci == self._kunci_loket and self.kartu_loket:
            return

        wadah = self.kisi_loket if self.tata_letak == KISI else self.kolom_loket
        while wadah.count():
            item = wadah.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.kartu_loket = []
        self._kunci_loket = kunci

        if not loket:
            kosong = QLabel("Belum ada loket yang aktif.")
            kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kosong.setMinimumSize(1, 1)
            kosong.setStyleSheet(
                f"color: {self.palet.panel_judul}; background: transparent;"
                f" font-size: {self.px('layanan')}px;"
            )
            if self.tata_letak == KISI:
                wadah.addWidget(kosong, 0, 0)
            else:
                wadah.addWidget(kosong)
            return

        varian = "kisi" if self.tata_letak == KISI else "baris"
        kolom = min(3, len(loket))
        for indeks, _item in enumerate(loket):
            kartu = KartuLoket(
                kompak=self.kompak,
                palet=self.palet,
                varian=varian,
                skala_nomor=self.skala_nomor,
            )
            kartu.set_skala(self.skala)
            self._bayangan(kartu, 40, 12, 110)
            self.kartu_loket.append(kartu)
            if self.tata_letak == KISI:
                self.kisi_loket.addWidget(kartu, indeks // kolom, indeks % kolom)
            else:
                self.kolom_loket.addWidget(kartu, stretch=1)

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
            f" border: {TEPI_NOMOR}px solid {p.chip_tepi}; border-radius: 14px;"
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
        return KOLOM_DAFTAR if self.tata_letak == KISI else KOLOM_DAFTAR_SEMPIT

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
        return self.baris_daftar * KOLOM_PER_LAYANAN

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
        font.setPixelSize(self.px("berikutnya_judul"))
        font.setWeight(QFont.Weight.Bold)
        return QFontMetrics(font).height()

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
            - self.label_judul_berikutnya.sizeHint().height()
            - self.susunan_berikutnya.spacing()
        )

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
            kiri = kolom * KOLOM_PER_LAYANAN
            judul = QLabel(f"{layanan.category_prefix} · {layanan.category_name}")
            judul.setAlignment(Qt.AlignmentFlag.AlignCenter)
            judul.setMinimumSize(1, 1)
            judul.setStyleSheet(
                f"color: {self.palet.panel_judul}; background: transparent;"
                f" font-size: {self.px('berikutnya_judul')}px; font-weight: 700;"
                " letter-spacing: 2px;"
            )
            # Judul melintang di atas kedua sub-kolom layanan ini.
            self.baris_berikutnya.addWidget(judul, 0, kiri, 1, KOLOM_PER_LAYANAN)

            potongan = layanan.menunggu[awal : awal + self.muat_per_halaman]
            if not potongan:
                # Kolom kosong tetap diberi tanda. Kolom yang benar-benar
                # hampa terbaca sebagai bagian layar yang gagal termuat,
                # bukan sebagai layanan yang memang sedang sepi.
                self.baris_berikutnya.addWidget(
                    self._label_kosong("—"), 1, kiri, 1, KOLOM_PER_LAYANAN
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

        for kolom in range(len(self._layanan) * KOLOM_PER_LAYANAN):
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
