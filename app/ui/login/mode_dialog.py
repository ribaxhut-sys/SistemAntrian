"""
Pilihan layar saat aplikasi dibuka.

Yang dipilih di sini sebenarnya sifat MESIN, bukan sifat momen: komputer
televisi ruang tunggu selalu menjadi layar antrian, komputer anjungan
selalu melayani pengambilan nomor, komputer loket selalu layar petugas.
Karena itu dialog ini dapat dilewati sepenuhnya lewat argumen baris
perintah, dan itulah yang dipasang pada shortcut kedua mesin publik: mereka
pulih sendiri setelah mati listrik tanpa perlu ada yang mengklik.

Dialog ini untuk mesin yang belum diatur, atau yang sesekali dipakai untuk
lebih dari satu hal.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import APP_NAME, lewati_login_pengembang

#: Hasil pilihan.
#:
#: LAYAR_ANTRIAN dan ANJUNGAN adalah dua mesin publik. LAYAR_ADMIN dan
#: LAYAR_PETUGAS adalah dua peran di komputer loket: admin mengelola data,
#: petugas memanggil antrian. Dahulu keduanya satu tombol, sehingga uji
#: tampilan selalu masuk sebagai admin dan tombol panggil tidak muncul.
LAYAR_ANTRIAN = "antrian"
ANJUNGAN = "anjungan"
LAYAR_ADMIN = "admin"
LAYAR_PETUGAS = "petugas"


class ModeDialog(QDialog):
    """Tanya layar mana yang akan dibuka pada komputer ini."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pilihan: str | None = None
        self._kartu_utama: QPushButton | None = None

        self.setObjectName("dialogMode")
        self.setWindowTitle(APP_NAME)
        #: Lebar dikunci karena penjelasan di dalam kartu dibungkus per
        #: baris. Dialog yang dapat ditarik melebar membuat penjelasan dua
        #: baris berubah menjadi satu baris panjang, dan kartunya lalu
        #: tampak setengah kosong.
        self.setFixedWidth(600)
        self._bangun_tampilan()

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(28, 26, 28, 24)
        susunan.setSpacing(10)

        susunan.addLayout(self._bangun_kepala())
        susunan.addSpacing(12)

        susunan.addWidget(
            self._bangun_pilihan(
                "LAYAR ANTRIAN",
                "Papan nomor untuk televisi ruang tunggu. Menampilkan dan "
                "membunyikan panggilan. Tidak perlu masuk.",
                LAYAR_ANTRIAN,
                ikon="📺",
                aksen="antrian",
            )
        )
        susunan.addWidget(
            self._bangun_pilihan(
                "ANJUNGAN AMBIL NOMOR",
                "Tempat pengunjung memilih jenis layanan dan mencetak tiket "
                "antriannya sendiri. Tidak perlu masuk.",
                ANJUNGAN,
                ikon="🎫",
                aksen="anjungan",
            )
        )
        # Komputer loket punya dua peran. Saat uji dari source keduanya
        # ditawarkan terpisah supaya admin tidak ikut menelan kursi petugas.
        # Di .exe cukup satu tombol: yang membedakan adalah akun yang masuk.
        if lewati_login_pengembang():
            susunan.addWidget(
                self._bangun_pilihan(
                    "LAYAR ADMIN",
                    "Mengelola data, pengaturan, dan backup. Pintasan uji: "
                    "masuk sebagai admin tanpa nama dan sandi.",
                    LAYAR_ADMIN,
                    ikon="⚙",
                    aksen="admin",
                )
            )
            susunan.addWidget(
                self._bangun_pilihan(
                    "LAYAR PETUGAS",
                    "Memanggil dan melayani antrian. Pintasan uji: masuk "
                    "sebagai petugas CRO tanpa nama dan sandi.",
                    LAYAR_PETUGAS,
                    ikon="📣",
                    aksen="petugas",
                    utama=True,
                )
            )
        else:
            susunan.addWidget(
                self._bangun_pilihan(
                    "LAYAR PETUGAS",
                    "Melayani antrian, mengelola data, dan melihat laporan. "
                    "Wajib masuk dengan akun petugas.",
                    LAYAR_PETUGAS,
                    ikon="📣",
                    aksen="petugas",
                    utama=True,
                )
            )

        susunan.addSpacing(8)
        susunan.addWidget(self._bangun_catatan())

        if self._kartu_utama is not None:
            self._kartu_utama.setFocus()

    def _bangun_kepala(self) -> QHBoxLayout:
        """Nama aplikasi, dengan lencana yang membawa warna merek."""
        baris = QHBoxLayout()
        baris.setSpacing(16)

        lencana = QLabel("CRO")
        lencana.setObjectName("lencanaMerek")
        lencana.setFixedSize(56, 56)
        lencana.setAlignment(Qt.AlignmentFlag.AlignCenter)
        baris.addWidget(lencana)

        teks = QVBoxLayout()
        teks.setSpacing(2)
        nama = QLabel(APP_NAME)
        nama.setObjectName("judulMerek")
        teks.addWidget(nama)
        tanya = QLabel("Pilih layar yang akan dibuka di komputer ini")
        tanya.setObjectName("subJudulMerek")
        teks.addWidget(tanya)
        baris.addLayout(teks, 1)

        return baris

    def _bangun_pilihan(
        self,
        teks: str,
        penjelasan: str,
        nilai: str,
        *,
        ikon: str,
        aksen: str,
        utama: bool = False,
    ) -> QWidget:
        """
        Satu kartu pilihan: seluruh kartu adalah tombolnya.

        Judul dan penjelasan digambar sebagai QLabel di dalam tombol supaya
        keduanya dapat berbeda ukuran dan warna. Teks tombol sendiri tetap
        disetel — itulah namanya bagi pembaca layar — lalu dibuat tembus
        pandang lewat stylesheet supaya tidak tergambar dua kali.
        """
        btn = QPushButton(teks)
        btn.setObjectName("kartuMode")
        btn.setProperty("aksen", aksen)
        if utama:
            btn.setProperty("utama", "true")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Tinggi kartu ditetapkan di stylesheet (min-height pada
        # #kartuMode), bukan di sini: setMinimumHeight selalu ditimpa oleh
        # min-height dari stylesheet, dan QPushButton menghitung tingginya
        # dari teksnya sendiri, bukan dari layout yang ada di dalamnya.
        btn.setAutoDefault(False)
        # Enter langsung membuka layar petugas. Di komputer loket itulah
        # pilihan yang hampir selalu dimaksud, dan dua mesin publik lain
        # dijalankan lewat pintasan, bukan lewat papan ketik.
        btn.setDefault(utama)
        btn.clicked.connect(lambda: self._pilih(nilai))

        isi = QGridLayout(btn)
        isi.setContentsMargins(18, 16, 20, 16)
        isi.setHorizontalSpacing(16)
        isi.setVerticalSpacing(3)
        isi.setColumnStretch(1, 1)

        kotak_ikon = QLabel(ikon)
        kotak_ikon.setObjectName("ikonMode")
        kotak_ikon.setProperty("aksen", aksen)
        kotak_ikon.setFixedSize(52, 52)
        kotak_ikon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        isi.addWidget(kotak_ikon, 0, 0, 2, 1)

        label_judul = QLabel(teks)
        label_judul.setObjectName("judulMode")
        isi.addWidget(label_judul, 0, 1)

        label_penjelasan = QLabel(penjelasan)
        label_penjelasan.setObjectName("penjelasanMode")
        label_penjelasan.setWordWrap(True)
        isi.addWidget(label_penjelasan, 1, 1)

        panah = QLabel("›")
        panah.setObjectName("tandaPanah")
        panah.setAlignment(Qt.AlignmentFlag.AlignCenter)
        isi.addWidget(panah, 0, 2, 2, 1)

        # Tanpa ini, melintasi ikon atau tulisan membuat kartu kehilangan
        # keadaan :hover — kartunya berkedip justru ketika ditunjuk.
        for anak in (kotak_ikon, label_judul, label_penjelasan, panah):
            anak.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        if utama:
            self._kartu_utama = btn
        return btn

    def _bangun_catatan(self) -> QFrame:
        """Keterangan pemasangan, bukan pilihan kelima."""
        kotak = QFrame()
        kotak.setObjectName("catatanMode")
        susunan = QHBoxLayout(kotak)
        susunan.setContentsMargins(14, 12, 14, 12)
        susunan.setSpacing(10)

        tanda = QLabel("💡")
        tanda.setObjectName("catatanTeks")
        tanda.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        susunan.addWidget(tanda)

        teks = QLabel(
            "Komputer televisi dan anjungan sebaiknya dijalankan dengan "
            "pintasan AntrianCRO.exe --tv atau --kios. Komputer loket: "
            "--admin atau --petugas."
        )
        teks.setObjectName("catatanTeks")
        teks.setWordWrap(True)
        susunan.addWidget(teks, 1)

        return kotak

    def _pilih(self, nilai: str) -> None:
        self.pilihan = nilai
        self.accept()
