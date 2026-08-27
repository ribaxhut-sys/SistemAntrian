"""Layar antrian untuk pengunjung."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
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
from app.services.sound_service import SoundPlayer
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
#: pada 112px masih muat di dalamnya setelah dikurangi padding.
UKURAN_TV: dict[str, int] = {
    "judul": 36,
    "jam": 24,
    "nama": 32,
    "status": 22,
    "nomor": 112,
    "layanan": 26,
    "berikutnya_judul": 20,
    "berikutnya": 46,
    # Varian baris: kartu melebar, nomornya di kanan nama loket.
    "nama_baris": 26,
    "status_baris": 20,
    "nomor_baris": 72,
    # Panel sorotan.
    "sorot_pil": 22,
    "sorot_nomor": 200,
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
    "nomor": 56,
    "layanan": 15,
    "berikutnya_judul": 15,
    "berikutnya": 28,
    "nama_baris": 15,
    "status_baris": 12,
    "nomor_baris": 34,
    "sorot_pil": 12,
    "sorot_nomor": 90,
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

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        kompak: bool = False,
        palet: Palet | None = None,
        varian: str = "kisi",
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
        return max(10, round(self.ukuran[kunci] * self.skala))

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
            self.label_status.setText("KOSONG")
            self.label_nomor.setText("—")
            self.label_layanan.setText("Siap melayani")
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
        self, parent: QWidget | None = None, *, kompak: bool = False, palet: Palet | None = None
    ) -> None:
        super().__init__(parent)
        self.kompak = kompak
        self.palet = palet or palet_untuk(TEMA_BAWAAN)
        self.ukuran = UKURAN_KIOS if kompak else UKURAN_TV
        self.skala = 1.0

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
        return max(10, round(self.ukuran[kunci] * self.skala))

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

        self.jumlah_berikutnya = settings.get_int("display.next_count", 3)
        self.suara_aktif = settings.get_bool("display.sound_enabled", True)
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
        if otomatis:
            self.pewaktu.start()
            self.pewaktu_jam.start()

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

        self.baris_berikutnya = QHBoxLayout()
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

        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        self.kisi_loket = QGridLayout(panel)
        self.kisi_loket.setContentsMargins(0, 0, 0, 0)
        # Kartu loket mendapat porsi jauh lebih besar pada layar televisi.
        # Di kios papan memang tidak boleh mendominasi, jadi panel
        # "menunggu giliran" relatif lebih tinggi di sana.
        self.susunan.addWidget(panel, stretch=5 if self.kompak else 8)
        self.susunan.addWidget(self._bangun_panel_berikutnya(), stretch=2)

    def _bangun_sorotan(self) -> None:
        self.susunan.addLayout(self._bangun_kepala())

        isi = QHBoxLayout()
        isi.setSpacing(28)

        self.kartu_sorot = KartuSorot(kompak=self.kompak, palet=self.palet)
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
        if abs(skala - self.skala) < 0.02:
            return
        self.skala = skala
        self._terapkan_ukuran()

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
        for label in self.label_berikutnya:
            self._gaya_berikutnya(label)

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Ambil keadaan terbaru dan perbarui layar."""
        self.perbarui_jam()
        berhasil, keadaan = jalankan_aman(self, lambda: self.queue.display_state(
            self.jumlah_berikutnya
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
        self._susun_kartu(keadaan.loket)

        id_unggulan = terkini.id if terkini is not None else None
        for kartu, loket in zip(self.kartu_loket, keadaan.loket, strict=False):
            unggulan = loket.antrian is not None and loket.antrian.id == id_unggulan
            kartu.tampilkan(loket, unggulan=unggulan)

        if self.kartu_sorot is not None:
            self.kartu_sorot.tampilkan(terkini)

        if terkini is not None:
            self._bunyikan_bila_baru(terkini)

        self._isi_berikutnya(keadaan.berikutnya)

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
            kartu = KartuLoket(kompak=self.kompak, palet=self.palet, varian=varian)
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
        label.setMinimumHeight(round((52 if self.kompak else 68) * self.skala))
        label.setStyleSheet(
            f"color: {p.chip_teks}; background: {p.chip};"
            f" border: 2px solid {p.chip_tepi}; border-radius: 14px;"
            f" font-size: {self.px('berikutnya')}px; font-weight: 800;"
            f" letter-spacing: {p.renggang_nomor}px; padding: 8px 12px;"
        )

    def _isi_berikutnya(self, berikutnya: list) -> None:
        while self.baris_berikutnya.count():
            item = self.baris_berikutnya.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.label_berikutnya = []

        if not berikutnya:
            kosong = QLabel("Tidak ada antrian menunggu")
            kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kosong.setMinimumSize(1, 1)
            kosong.setStyleSheet(
                f"color: {self.palet.panel_judul}; background: transparent;"
                f" font-size: {self.px('berikutnya_judul')}px;"
            )
            self.baris_berikutnya.addWidget(kosong)
            return

        for antrian in berikutnya:
            label = QLabel(antrian.queue_number)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(1, 1)
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self._gaya_berikutnya(label)
            self.label_berikutnya.append(label)
            self.baris_berikutnya.addWidget(label)

    def hentikan(self) -> None:
        """Hentikan penyegaran berkala. Dipanggil saat layar ditutup."""
        self.pewaktu.stop()
        self.pewaktu_jam.stop()
