"""
Layar pengaturan aplikasi untuk administrator.

Kontrol yang ditampilkan mengikuti SKEMA di settings_service: kotak centang
untuk boleh/tidak, daftar pilihan untuk yang pilihannya terbatas, dan kotak
angka dengan batas atas-bawah. Dengan begitu nilai yang tidak masuk akal
tidak mungkin diketik sejak awal — bukan sekadar ditolak setelah disimpan.

Penegakan sesungguhnya tetap di service layer. Layar ini hanya membuat
kesalahan lebih sulit dilakukan.

Susunannya tiga bagian, dan ketiganya menjawab pertanyaan yang berbeda:

* **Daftar kelompok di kiri** menjawab "ada pengaturan apa saja" — dua
  puluh dua pengaturan yang ditumpuk pada satu halaman gulung hanya dapat
  ditemukan dengan menggulung sampai ketemu.
* **Kotak cari di atasnya** menjawab "di mana yang saya cari" bagi orang
  yang sudah tahu namanya tetapi tidak tahu kelompoknya.
* **Bar di bawah** menjawab "apa yang sudah saya ubah tetapi belum
  disimpan" — pertanyaan yang paling mahal bila jawabannya baru diketahui
  setelah menutup layar.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import clock
from app.core.logger import get_logger
from app.services import daftar_putar
from app.services.settings_service import (
    ANGKA,
    BERKAS,
    BOOLEAN,
    DAFTAR_PUTAR,
    TEKS_BANYAK,
    PILIHAN,
    Pengaturan,
    SettingsService,
    kelompok_pengaturan,
)
from app.ui.common import (
    jalankan_aman,
    judul,
    keterangan,
    konfirmasi,
    tampilkan_peringatan,
    tombol,
)
from app.ui.settings.dialogs import JadwalIklanDialog, PemilihMediaLayanan
from app.ui.kiosk.sambutan import (
    EKSTENSI_VIDEO,
    FILTER_BERKAS_ANJUNGAN,
    daftar_media_kios,
    folder_media_kios,
    jenis_sambutan_dari_berkas,
    salin_ke_media_kios,
)
from app.ui.style import BORDER, SUCCESS, TEXT_MUTED, WARNING

logger = get_logger("ui.settings")

#: Lama pesan hasil penyimpanan tampil, dalam milidetik.
JEDA_PESAN = 4000

#: Lebar kolom kelompok di kiri, termasuk padding kartu. Cukup untuk
#: "Ringkasan Harian" pada satu baris — nama kelompok yang terlipat dua
#: baris membuat daftarnya terbaca sebagai paragraf, bukan sebagai daftar.
LEBAR_RAIL = 220

#: Lebar kotak isian di kanan setiap baris.
#:
#: Dibatasi, bukan dibiarkan selebar layar. Kotak angka selebar 1400 piksel
#: untuk menampung angka "3" memaksa mata berjalan jauh dari nama
#: pengaturannya ke nilainya, dan itu satu-satunya pasangan yang benar-benar
#: perlu dibaca bersamaan di layar ini.
#:
#: Kolomnya selebar tetap, dan seluruh sisa lebar baris menjadi milik
#: penjelasan. Pembagian 3:2 sebelumnya menyisakan ruang kosong di kiri
#: kotak isian sementara penjelasan terlipat sampai delapan baris, sehingga
#: kelompok berisi lima pengaturan tidak muat satu layar 1366 x 768.
LEBAR_KONTROL = 340

#: Kalimat pengantar tiap kelompok. Tinggal di sini, bukan di SKEMA:
#: yang dijelaskan adalah letaknya di layar, dan itu urusan tampilan.
KETERANGAN_KELOMPOK: dict[str, str] = {
    "Tiket": "Cara nomor dicetak dan apa yang tertulis pada tiketnya.",
    "Layar Antrian": "Papan yang menghadap pengunjung di ruang tunggu.",
    "Nomor Layar Antrian": (
        "Nomor berikutnya dan nomor menunggu di layar antrian, juga papan "
        "kecil di dalam anjungan."
    ),
    "Suara Panggilan": "Bunyi dan suara saat nomor dipanggil di layar antrian.",
    "Antrian": "Aturan pemanggilan dan jeda ambil nomor.",
    "Anjungan": "Judul, tema, dan letak baris loket di tablet ambil nomor.",
    "Panel Anjungan": "Isi panel besar di atas tombol layanan: teks atau media.",
    "Iklan Anjungan": "Urutan, jadwal, dan cara iklan diputar di tablet.",
    "Perilaku Iklan": (
        "Berapa putaran iklan layar penuh, gerak panel anjungan, dan apa yang "
        "terjadi pada iklan saat petugas memanggil."
    ),
    "Survey": "Penilaian kepuasan yang diminta setelah pelayanan selesai.",
    "Pengaduan": "Berapa lama identitas pelapor pengaduan disimpan.",
    "Ringkasan Harian": "Layar rekap yang dibaca penyelia sepanjang hari.",
    "Backup": "Salinan database dan berapa lama salinan itu disimpan.",
    "Keamanan": "Kunci layar petugas ketika komputer ditinggalkan.",
}

#: Kelompok tambahan yang isinya bukan pengaturan database, melainkan
#: berkas media per jenis layanan. Ikut sebagai kelompok tersendiri supaya
#: letaknya dapat ditebak, bukan tersembunyi di ujung halaman gulung.
KELOMPOK_MEDIA = "Media Anjungan"


class _PemilihBerkas(QWidget):
    """Kotak path plus tombol untuk memilih berkas di komputer ini."""

    berkasDipilih = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        susunan = QHBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)

        self.isian = QLineEdit()
        self.isian.setPlaceholderText("ditambah ke folder media/kiosk")
        susunan.addWidget(self.isian, stretch=1)

        pilih = tombol("Pilih berkas…")
        pilih.setObjectName("tombolPilihBerkas")
        pilih.clicked.connect(self._pilih)
        susunan.addWidget(pilih)

    def text(self) -> str:
        return self.isian.text()

    def setText(self, nilai: str) -> None:  # noqa: N802 - menyamai QLineEdit
        self.isian.setText(nilai)

    def _pilih(self) -> None:
        folder = folder_media_kios()
        awal = str(folder) if folder.is_dir() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih gambar atau video anjungan",
            awal,
            FILTER_BERKAS_ANJUNGAN,
        )
        if not path:
            return
        tujuan = salin_ke_media_kios(Path(path))
        self.isian.setText(tujuan.name)
        self.berkasDipilih.emit(tujuan.name)
        ext = tujuan.suffix.lower()
        if ext in EKSTENSI_VIDEO_BERISIKO:
            tampilkan_peringatan(
                self,
                PERINGATAN_FORMAT.format(ext=ext.lstrip(".").upper()),
                "Format video berisiko",
            )


#: Video yang sering gagal di pemutar bawaan Android. MP4 (H.264) dan WebM
#: didukung semua tablet; MKV dan AVI tergantung isi dan pabrikan tabletnya.
EKSTENSI_VIDEO_BERISIKO = {".mkv", ".avi"}

PERINGATAN_FORMAT = (
    "Format {ext} sering gagal diputar di tablet. Ubah ke MP4 (H.264) "
    "supaya pasti tayang."
)

_BULAN = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
          "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def _tanggal_pendek(nilai) -> str:
    return f"{nilai.day} {_BULAN[nilai.month - 1]} {nilai.year}"


def teks_jadwal(butir: daftar_putar.Butir) -> str:
    """Jadwal tayang sebuah butir dalam kalimat pendek; kosong bila tanpa jadwal."""
    if butir.mulai and butir.selesai:
        return f"{_tanggal_pendek(butir.mulai)} – {_tanggal_pendek(butir.selesai)}"
    if butir.mulai:
        return f"mulai {_tanggal_pendek(butir.mulai)}"
    if butir.selesai:
        return f"sampai {_tanggal_pendek(butir.selesai)}"
    return ""


def teks_tempat(butir: daftar_putar.Butir) -> str:
    """Tempat tampil bila dibatasi; kosong bila keduanya (bawaan)."""
    if butir.tampil == daftar_putar.TAMPIL_KEDUANYA:
        return ""
    return daftar_putar.LABEL_TAMPIL[butir.tampil]


class _KotakBanyakBaris(QPlainTextEdit):
    """Kotak teks beberapa baris dengan antarmuka yang sama seperti QLineEdit."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(110)

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, nilai: str) -> None:  # noqa: N802 - menyamai QLineEdit
        self.setPlainText(nilai)


class _DaftarPutar(QWidget):
    """
    Berkas di folder media/kiosk dengan centang (diputar) dan urutannya.

    Nilainya larik JSON nama berkas yang dicentang, berurutan, beserta
    jadwal dan lama tampil bila diatur (lihat app.services.daftar_putar).
    Selama pengguna belum menyentuhnya, nilai kosong dipertahankan: artinya
    "belum diatur, putar semua menurut nama" — membuka halaman pengaturan
    saja tidak boleh membuat baris ini tampak berubah.
    """

    diubah = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._belum_diatur = True
        self._sedang_mengisi = False
        #: Jadwal dan lama tampil per nama berkas. Ikut diingat untuk berkas
        #: yang tidak dicentang, supaya mencentangnya kembali tidak membuang
        #: jadwal yang sudah diatur — sampai halaman dimuat ulang.
        self._aturan: dict[str, daftar_putar.Butir] = {}
        #: Hasil media_tayang.ringkasan(): angka tayang dan tanda gagal.
        self._ringkasan: dict = {}

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(6)

        self.peringatan = QLabel()
        self.peringatan.setObjectName("peringatanDaftarPutar")
        self.peringatan.setWordWrap(True)
        self.peringatan.setStyleSheet(f"color: {WARNING}; font-weight: 600;")
        self.peringatan.setVisible(False)
        susunan.addWidget(self.peringatan)

        self.daftar = QListWidget()
        self.daftar.setObjectName("daftarPutarMedia")
        self.daftar.setMinimumHeight(160)
        self.daftar.setWordWrap(True)
        self.daftar.itemChanged.connect(self._pada_centang)
        self.daftar.itemDoubleClicked.connect(lambda _item: self.atur_jadwal())
        susunan.addWidget(self.daftar)

        # Dua baris, bukan satu: empat tombol berdampingan butuh ~400px,
        # sedangkan kolom kontrol hanya LEBAR_KONTROL — "Atur jadwal…" dan
        # "Muat ulang" terpotong menjadi "r jadwa" dan "uat ular".
        tombol_baris = QGridLayout()
        tombol_baris.setSpacing(6)
        naik = tombol("Naik")
        naik.clicked.connect(lambda: self._geser(-1))
        turun = tombol("Turun")
        turun.clicked.connect(lambda: self._geser(1))
        jadwal = tombol("Atur jadwal…")
        jadwal.setObjectName("tombolJadwalIklan")
        jadwal.setToolTip("Tanggal tayang dan lama tampil berkas yang dipilih")
        jadwal.clicked.connect(self.atur_jadwal)
        muat = tombol("Muat ulang")
        muat.setToolTip("Baca ulang isi folder media/kiosk")
        muat.clicked.connect(self.muat_ulang_folder)
        for indeks, item in enumerate((naik, turun, jadwal, muat)):
            tombol_baris.addWidget(item, indeks // 2, indeks % 2)
        susunan.addLayout(tombol_baris)

    # -- antarmuka seperti QLineEdit, dipakai _BarisPengaturan ----------

    def text(self) -> str:
        if self._belum_diatur:
            return ""
        return daftar_putar.tulis([self._butir(nama) for nama in self._tercentang()])

    def setText(self, nilai: str) -> None:  # noqa: N802 - menyamai QLineEdit
        butir = daftar_putar.baca_butir(nilai)
        self._belum_diatur = butir is None
        self._aturan = {b.nama: b for b in butir or []}
        self._isi(None if butir is None else [b.nama for b in butir])

    # -------------------------------------------------------------------

    def ada_yang_diputar(self) -> bool:
        return bool(self._tercentang())

    def tampilkan_peringatan(self, teks: str) -> None:
        self.peringatan.setText(teks)
        self.peringatan.setVisible(bool(teks))

    def tampilkan_ringkasan(self, ringkasan: dict) -> None:
        """Angka tayang dan tanda gagal dari laporan tablet."""
        self._ringkasan = ringkasan or {}
        self.muat_ulang_folder()

    def muat_ulang_folder(self) -> None:
        """Baca ulang folder tanpa membuang centang dan urutan yang ada."""
        self._isi(None if self._belum_diatur else self._tercentang())

    def tambah(self, nama: str) -> None:
        """Berkas yang baru disalin langsung ikut diputar di ujung daftar."""
        if self._belum_diatur:
            self.muat_ulang_folder()
            return
        urutan = [n for n in self._tercentang() if n != nama] + [nama]
        self._isi(urutan)
        self.diubah.emit()

    def atur_jadwal(self) -> None:
        """Buka jadwal tayang berkas yang sedang dipilih."""
        item = self.daftar.currentItem()
        nama = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if nama is None:
            return
        dialog = JadwalIklanDialog(
            self,
            self._butir(nama),
            gambar=Path(nama).suffix.lower() not in EKSTENSI_VIDEO,
            berkas=folder_media_kios() / nama,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.terapkan_jadwal(dialog.butir)

    def terapkan_jadwal(self, baru: daftar_putar.Butir) -> None:
        """Pasang jadwal dan lama tampil satu berkas, lalu tandai berubah."""
        if baru == self._butir(baru.nama):
            return
        self._aturan[baru.nama] = baru
        # Mengatur jadwal berarti mulai mengatur daftar putarnya juga.
        tercentang = None if self._belum_diatur else self._tercentang()
        self._belum_diatur = False
        baris = self.daftar.currentRow()
        self._isi(tercentang)
        self.daftar.setCurrentRow(baris)
        self.diubah.emit()

    def _butir(self, nama: str) -> daftar_putar.Butir:
        return self._aturan.get(nama) or daftar_putar.Butir(nama)

    def _tercentang(self) -> list[str]:
        hasil = []
        for baris in range(self.daftar.count()):
            item = self.daftar.item(baris)
            if item.checkState() == Qt.CheckState.Checked:
                hasil.append(item.data(Qt.ItemDataRole.UserRole))
        return hasil

    def _teks_butir(self, nama: str) -> tuple[str, str, bool]:
        """Teks baris daftar, isi tooltip, dan apakah perlu diperhatikan."""
        ext = Path(nama).suffix.lower()
        video = ext in EKSTENSI_VIDEO
        butir = self._butir(nama)
        bagian = [nama, "video" if video else "gambar"]
        if not video and butir.detik:
            bagian.append(f"{butir.detik} dtk")
        tempat = teks_tempat(butir)
        if tempat:
            bagian.append(f"hanya {tempat.lower()}")
        jadwal = teks_jadwal(butir)
        if jadwal:
            bagian.append(jadwal)
            if not butir.tayang_pada(clock.today()):
                bagian.append("di luar jadwal")
        baris = ["  ·  ".join(bagian)]
        tip = []

        info = self._ringkasan.get(nama)
        if info is not None and (info.tayang_rentang or info.tayang_hari_ini):
            baris.append(
                f"Tayang hari ini {_angka(info.tayang_hari_ini)}×  ·  "
                f"30 hari {_angka(info.tayang_rentang)}×"
            )
        perhatian = False
        if info is not None and info.gagal:
            perhatian = True
            baris.append(
                "⚠ Gagal diputar di " + ", ".join(g.tablet for g in info.gagal)
            )
            tip += [
                f"{g.tablet} ({g.waktu:%d/%m %H:%M}): {g.pesan or 'tanpa keterangan'}"
                for g in info.gagal
            ]
        if ext in EKSTENSI_VIDEO_BERISIKO:
            perhatian = True
            baris.append("⚠ " + PERINGATAN_FORMAT.format(ext=ext.lstrip(".").upper()))
        return "\n".join(baris), "\n".join(tip), perhatian

    def _isi(self, urutan: list[str] | None) -> None:
        semua = [path.name for path in daftar_media_kios()]
        if urutan is None:
            tampil = [(nama, True) for nama in semua]
        else:
            ada = [nama for nama in urutan if nama in semua]
            tampil = [(nama, True) for nama in ada]
            tampil += [(nama, False) for nama in semua if nama not in ada]
        self._sedang_mengisi = True
        try:
            self.daftar.clear()
            for nama, aktif in tampil:
                teks, tip, perhatian = self._teks_butir(nama)
                item = QListWidgetItem(teks)
                item.setData(Qt.ItemDataRole.UserRole, nama)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if aktif else Qt.CheckState.Unchecked
                )
                if tip:
                    item.setToolTip(tip)
                if perhatian:
                    item.setForeground(QColor(WARNING))
                self.daftar.addItem(item)
            if not tampil:
                kosong = QListWidgetItem("Folder media/kiosk masih kosong.")
                kosong.setFlags(Qt.ItemFlag.NoItemFlags)
                self.daftar.addItem(kosong)
        finally:
            self._sedang_mengisi = False

    def _pada_centang(self, _item: QListWidgetItem) -> None:
        if self._sedang_mengisi:
            return
        self._belum_diatur = False
        self.diubah.emit()

    def _geser(self, arah: int) -> None:
        baris = self.daftar.currentRow()
        tujuan = baris + arah
        if baris < 0 or not 0 <= tujuan < self.daftar.count():
            return
        if self.daftar.item(baris).data(Qt.ItemDataRole.UserRole) is None:
            return
        self._sedang_mengisi = True
        try:
            item = self.daftar.takeItem(baris)
            self.daftar.insertItem(tujuan, item)
            self.daftar.setCurrentRow(tujuan)
        finally:
            self._sedang_mengisi = False
        self._belum_diatur = False
        self.diubah.emit()


def _angka(nilai: int) -> str:
    """Angka dengan titik ribuan: 12.345."""
    return f"{nilai:,}".replace(",", ".")


def _garis() -> QFrame:
    """Garis pemisah setipis mungkin antara dua baris pengaturan."""
    garis = QFrame()
    garis.setFixedHeight(1)
    garis.setStyleSheet(f"background: {BORDER}; border: none;")
    return garis


class _BarisPengaturan(QFrame):
    """
    Satu pengaturan: nama dan penjelasannya di kiri, kontrolnya di kanan.

    Nama dan penjelasan disatukan dalam satu kolom, bukan nama di kiri dan
    penjelasan melintang di bawah keduanya. Penjelasan yang melintang penuh
    memisahkan sebuah baris dari baris berikutnya sejauh ia memisahkan
    dirinya sendiri dari namanya, sehingga daftar pengaturan terbaca sebagai
    paragraf beruntun alih-alih sebagai daftar.

    Baris yang nilainya sudah diubah tetapi belum disimpan menandai dirinya
    sendiri (property ``berubah``), supaya "apa saja yang tadi saya ubah"
    dapat dijawab dengan melihat, bukan dengan mengingat.
    """

    nilaiBerubah = Signal()

    def __init__(self, butir: Pengaturan, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.butir = butir
        #: Nilai yang terakhir dibaca dari database. Pembanding untuk
        #: menentukan baris ini berubah atau tidak.
        self._tersimpan = ""
        #: Garis pemisah di ATAS baris ini, milik halaman kelompoknya.
        #: Disimpan di sini supaya ikut tersembunyi ketika barisnya
        #: disaring oleh pencarian — garis yang tertinggal sendirian
        #: terbaca sebagai baris kosong.
        self.pemisah: QFrame | None = None

        self.setObjectName("barisPengaturan")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        susunan = QHBoxLayout(self)
        # Form admin harus muat pada layar penuh 1366x768. Jarak 14 px di
        # atas DAN bawah tiap baris menumpuk menjadi lebih dari satu baris
        # kontrol pada kelompok berisi lima pengaturan.
        susunan.setContentsMargins(18, 8, 18, 8)
        susunan.setSpacing(18)

        kiri = QVBoxLayout()
        kiri.setSpacing(3)
        self.label = QLabel(butir.label)
        self.label.setWordWrap(True)
        self.label.setProperty("namaPengaturan", "true")
        kiri.addWidget(self.label)

        self.penjelasan = QLabel(butir.keterangan)
        self.penjelasan.setWordWrap(True)
        self.penjelasan.setProperty("muted", "true")
        kiri.addWidget(self.penjelasan)
        # Baris yang kontrolnya tinggi (daftar putar) tidak boleh membuat
        # nama dan penjelasannya melayang terpisah di tengah dan di bawah.
        kiri.addStretch()
        susunan.addLayout(kiri, stretch=1)

        self.kontrol = self._bangun_kontrol()
        susunan.addWidget(self._bungkus(self.kontrol))
        self._hubungkan()

    # -----------------------------------------------------------------

    def _bangun_kontrol(self) -> QWidget:
        if self.butir.jenis == BOOLEAN:
            return QCheckBox()

        if self.butir.jenis == PILIHAN:
            kotak = QComboBox()
            for nilai, teks in self.butir.pilihan:
                kotak.addItem(teks, nilai)
            return kotak

        if self.butir.jenis == ANGKA:
            angka = QSpinBox()
            # Batasnya diambil dari SKEMA yang sama dengan yang dipakai
            # service, sehingga tidak mungkin berbeda diam-diam.
            angka.setMinimum(self.butir.minimum if self.butir.minimum is not None else 0)
            angka.setMaximum(
                self.butir.maksimum if self.butir.maksimum is not None else 999_999
            )
            if self.butir.satuan:
                angka.setSuffix(f" {self.butir.satuan}")
            if self.butir.nilai_khusus:
                # Berlaku tepat pada nilai terkecil. Angka 0 yang artinya
                # "otomatis" tidak dapat ditebak dari angkanya sendiri.
                angka.setSpecialValueText(self.butir.nilai_khusus)
            return angka

        if self.butir.jenis == BERKAS:
            return _PemilihBerkas()

        if self.butir.jenis == DAFTAR_PUTAR:
            return _DaftarPutar()

        if self.butir.jenis == TEKS_BANYAK:
            return _KotakBanyakBaris()

        return QLineEdit()

    def _bungkus(self, kontrol: QWidget) -> QWidget:
        """Kontrol dirapatkan ke kanan pada lebar yang seragam."""
        kotak = QWidget()
        kotak.setFixedWidth(LEBAR_KONTROL)
        tata = QHBoxLayout(kotak)
        tata.setContentsMargins(0, 0, 0, 0)
        tata.addStretch()
        if self.butir.jenis != BOOLEAN:
            kontrol.setFixedWidth(LEBAR_KONTROL)
        tata.addWidget(kontrol, alignment=Qt.AlignmentFlag.AlignTop)
        return kotak

    def _hubungkan(self) -> None:
        """Sambungkan sinyal perubahan kontrol, apa pun jenis kontrolnya."""
        if self.butir.jenis == BOOLEAN:
            self.kontrol.toggled.connect(self._pada_ubah)
        elif self.butir.jenis == PILIHAN:
            self.kontrol.currentIndexChanged.connect(self._pada_ubah)
        elif self.butir.jenis == ANGKA:
            self.kontrol.valueChanged.connect(self._pada_ubah)
        elif self.butir.jenis == BERKAS:
            self.kontrol.isian.textChanged.connect(self._pada_ubah)
        elif self.butir.jenis == DAFTAR_PUTAR:
            self.kontrol.diubah.connect(self._pada_ubah)
        else:
            self.kontrol.textChanged.connect(self._pada_ubah)

    def _pada_ubah(self, *_args) -> None:
        self.tandai(self.sudah_berubah())
        self.nilaiBerubah.emit()

    # -----------------------------------------------------------------

    def tampilkan(self, nilai: str) -> None:
        """Isi kontrol dari nilai yang tersimpan, dan jadikan itu acuannya."""
        self._tersimpan = nilai
        self.tulis(nilai)
        self.tandai(False)

    def tulis(self, nilai: str) -> None:
        """
        Isi kontrol TANPA mengubah acuan "sudah tersimpan".

        Dipakai ketika layar sendiri yang mengubah sebuah nilai — memilih
        berkas media ikut mengganti jenis tampilan panel. Perubahan itu
        tetap perubahan yang harus disimpan; menganggapnya sebagai nilai
        tersimpan berarti tombol Simpan diam saja dan pilihannya hilang.
        """
        if self.butir.jenis == BOOLEAN:
            self.kontrol.setChecked(nilai.strip().lower() == "true")
        elif self.butir.jenis == PILIHAN:
            tampil = nilai
            if self.butir.kunci == "kiosk.welcome_kind" and nilai in (
                "gambar",
                "video",
            ):
                tampil = "media"
            indeks = self.kontrol.findData(tampil)
            # Nilai yang tidak dikenal (misalnya dari database lama) tidak
            # boleh membuat pilihan tampak kosong tanpa sebab.
            self.kontrol.setCurrentIndex(indeks if indeks >= 0 else 0)
        elif self.butir.jenis == ANGKA:
            try:
                self.kontrol.setValue(int(nilai))
            except ValueError:
                self.kontrol.setValue(self.kontrol.minimum())
        else:
            self.kontrol.setText(nilai)
            if isinstance(self.kontrol, QLineEdit):
                # Kotak isian menggulung sendiri ke ujung teks setelah diisi,
                # sehingga kalimat yang lebih panjang daripada kotaknya
                # tampil terpenggal di awal — bagian yang justru dibaca
                # lebih dulu untuk mengenali isinya.
                self.kontrol.setCursorPosition(0)

    def nilai(self) -> str:
        if self.butir.jenis == BOOLEAN:
            return "true" if self.kontrol.isChecked() else "false"
        if self.butir.jenis == PILIHAN:
            return self.kontrol.currentData()
        if self.butir.jenis == ANGKA:
            return str(self.kontrol.value())
        return self.kontrol.text().strip()

    def sudah_berubah(self) -> bool:
        return self.nilai() != self._tersimpan

    def tandai(self, berubah: bool) -> None:
        """Nyalakan atau padamkan penanda "belum disimpan" pada baris ini."""
        if self.property("berubah") == ("true" if berubah else "false"):
            return
        self.setProperty("berubah", "true" if berubah else "false")
        # Qt tidak menghitung ulang gaya sebuah widget hanya karena
        # propertinya berubah; tanpa unpolish/polish penandanya tidak
        # pernah muncul.
        self.style().unpolish(self)
        self.style().polish(self)

    def cocok(self, kata: str) -> bool:
        """Baris ini termasuk hasil pencarian `kata`."""
        ladang = f"{self.butir.label} {self.butir.keterangan} {self.butir.kunci}"
        return kata in ladang.lower()


class SettingsPage(QWidget):
    """Pengelolaan pengaturan aplikasi."""

    def __init__(
        self,
        settings: SettingsService,
        master=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        #: MasterDataService, dipakai HANYA untuk mendaftar jenis layanan
        #: pada kartu media anjungan. Boleh None — halaman pengaturan tetap
        #: berguna tanpanya, dan kelompoknya sekadar tidak ikut dibangun.
        self.master = master
        self.baris: dict[str, _BarisPengaturan] = {}
        #: Urutan kelompok beserta barisnya, sejajar dengan urutan item di
        #: daftar kiri dan urutan halaman di tumpukan kanan.
        self._kelompok: list[tuple[str, list[_BarisPengaturan]]] = []
        #: Nama jenis layanan pada kelompok Media Anjungan, supaya pencarian
        #: "konsultasi" menemukannya walau kata itu tidak ada di judul kelompok.
        self._ladang_media = ""

        # Timer dimiliki widget ini, bukan QTimer.singleShot yang statis.
        # singleShot tidak terikat pada apa pun sehingga tetap menyala
        # setelah halamannya dihapus, lalu menyentuh label yang sudah tidak
        # ada — aplikasi berhenti bila ditutup tepat setelah menyimpan.
        self._penghapus_pesan = QTimer(self)
        self._penghapus_pesan.setSingleShot(True)

        self._bangun_tampilan()
        self.muat_ulang()
        pemilih = self.baris.get("kiosk.welcome_file")
        if pemilih is not None and isinstance(pemilih.kontrol, _PemilihBerkas):
            pemilih.kontrol.berkasDipilih.connect(self._sesuaikan_jenis_sambutan)
            daftar = self.baris.get(daftar_putar.KUNCI)
            if daftar is not None and isinstance(daftar.kontrol, _DaftarPutar):
                pemilih.kontrol.berkasDipilih.connect(daftar.kontrol.tambah)
        daftar = self.baris.get(daftar_putar.KUNCI)
        jenis = self.baris.get("kiosk.welcome_kind")
        if daftar is not None and jenis is not None:
            daftar.kontrol.diubah.connect(self._aktifkan_media_bila_perlu)
            jenis.kontrol.currentIndexChanged.connect(
                lambda *_: self._perbarui_peringatan_daftar()
            )
            self._perbarui_peringatan_daftar()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        luar = QVBoxLayout(self)
        luar.setContentsMargins(24, 16, 24, 0)
        luar.setSpacing(10)

        luar.addWidget(judul("Pengaturan Aplikasi"))
        luar.addWidget(
            keterangan(
                "Perubahan berlaku setelah layar yang bersangkutan dimuat ulang "
                "atau aplikasi dibuka kembali."
            )
        )

        badan = QHBoxLayout()
        badan.setSpacing(20)
        badan.addWidget(self._bangun_rail())
        badan.addWidget(self._bangun_isi(), stretch=1)
        luar.addLayout(badan, stretch=1)

        luar.addWidget(self._bangun_bar())

        # Ctrl+S: administrator yang mengubah beberapa pengaturan
        # berturut-turut tidak perlu berpindah ke tombol setiap kali.
        simpan = QShortcut(QKeySequence.StandardKey.Save, self)
        simpan.activated.connect(self.simpan)

        temukan = QShortcut(QKeySequence.StandardKey.Find, self)
        temukan.activated.connect(self._fokus_cari)
        lepas = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.cari)
        lepas.setContext(Qt.ShortcutContext.WidgetShortcut)
        lepas.activated.connect(self.cari.clear)

    def _bangun_rail(self) -> QWidget:
        kotak = QWidget()
        kotak.setObjectName("panelRailPengaturan")
        kotak.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        kotak.setFixedWidth(LEBAR_RAIL)
        susunan = QVBoxLayout(kotak)
        susunan.setContentsMargins(10, 10, 10, 10)
        susunan.setSpacing(10)

        self.cari = QLineEdit()
        self.cari.setObjectName("cariPengaturan")
        self.cari.setPlaceholderText("Cari pengaturan…")
        self.cari.setClearButtonEnabled(True)
        self.cari.textChanged.connect(self._saring)
        susunan.addWidget(self.cari)

        self.rail = QListWidget()
        self.rail.setObjectName("railPengaturan")
        self.rail.currentRowChanged.connect(self._pilih_kelompok)
        susunan.addWidget(self.rail, stretch=1)
        return kotak

    def _bangun_isi(self) -> QWidget:
        self.tumpukan = QStackedWidget()

        for nama, butir_butir in kelompok_pengaturan().items():
            baris_baris = []
            for butir in butir_butir:
                baris = _BarisPengaturan(butir)
                baris.nilaiBerubah.connect(self._perbarui_status)
                self.baris[butir.kunci] = baris
                baris_baris.append(baris)
            self._kelompok.append((nama, baris_baris))
            self.tumpukan.addWidget(self._bangun_halaman(nama, baris_baris))

        kartu_media = self._bangun_media_layanan()
        if kartu_media is not None:
            self._kelompok.append((KELOMPOK_MEDIA, []))
            self.tumpukan.addWidget(kartu_media)

        # Halaman terakhir: pencarian yang tidak menemukan apa pun. Layar
        # kosong tanpa keterangan terbaca sebagai layar yang gagal termuat.
        self._halaman_kosong = QWidget()
        kosong = QVBoxLayout(self._halaman_kosong)
        kosong.addStretch()
        self.label_kosong = QLabel("")
        self.label_kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_kosong.setProperty("muted", "true")
        self.label_kosong.setWordWrap(True)
        kosong.addWidget(self.label_kosong)
        kosong.addStretch()
        self.tumpukan.addWidget(self._halaman_kosong)

        for nama, _ in self._kelompok:
            self.rail.addItem(nama)
        self.rail.setCurrentRow(0)
        return self.tumpukan

    def _bangun_halaman(self, nama: str, baris_baris: list[_BarisPengaturan]) -> QWidget:
        """Satu kelompok: judulnya, pengantarnya, lalu kartu berisi barisnya."""
        gulung = QScrollArea()
        gulung.setWidgetResizable(True)
        gulung.setFrameShape(QFrame.Shape.NoFrame)

        isi = QWidget()
        susunan = QVBoxLayout(isi)
        susunan.setContentsMargins(0, 0, 10, 8)
        susunan.setSpacing(6)

        susunan.addWidget(judul(nama))
        pengantar = KETERANGAN_KELOMPOK.get(nama)
        if pengantar:
            susunan.addWidget(keterangan(pengantar))

        kartu = QFrame()
        kartu.setObjectName("kartuPengaturan")
        kartu_susunan = QVBoxLayout(kartu)
        kartu_susunan.setContentsMargins(0, 4, 0, 4)
        kartu_susunan.setSpacing(0)
        for indeks, baris in enumerate(baris_baris):
            if indeks:
                baris.pemisah = _garis()
                kartu_susunan.addWidget(baris.pemisah)
            kartu_susunan.addWidget(baris)

        susunan.addSpacing(6)
        susunan.addWidget(kartu)
        susunan.addStretch()

        gulung.setWidget(isi)
        return gulung

    def _bangun_media_layanan(self) -> QWidget | None:
        """
        Pemilih media anjungan untuk SETIAP jenis layanan, satu halaman.

        Ada juga di dialog Ubah Jenis Layanan, memakai widget yang sama
        persis sehingga keduanya mustahil berbeda perilaku. Di sini
        semuanya berjajar dalam satu layar — cara yang jauh lebih enak
        saat memasang media A, B, dan C sekaligus.

        Berkasnya hidup di mesin ini, bukan di database (aturan yang sama
        dengan media sambutan), jadi tidak ada yang ikut tersimpan lewat
        tombol Simpan halaman ini.
        """
        if self.master is None:
            return None

        gulung = QScrollArea()
        gulung.setWidgetResizable(True)
        gulung.setFrameShape(QFrame.Shape.NoFrame)

        isi = QWidget()
        susunan = QVBoxLayout(isi)
        susunan.setContentsMargins(0, 0, 10, 16)
        susunan.setSpacing(6)

        susunan.addWidget(judul(KELOMPOK_MEDIA))
        susunan.addWidget(
            keterangan(
                "Tampil di panel anjungan begitu pengunjung menyentuh layanan "
                "itu, menggantikan sambutan sampai nomornya terbit. Bila "
                "kosong, anjungan memakai Info Anjungan berupa teks."
            )
        )
        susunan.addWidget(
            keterangan(
                "Berkas langsung dipasang tanpa menunggu tombol Simpan, dan "
                "menggantikan berkas sebelumnya. Video diulang terus sampai "
                "pengunjung menekan YA atau BATAL, jadi klip pendek 5-10 detik "
                "justru paling baik — usahakan frame awal dan akhirnya mirip "
                "supaya sambungannya tidak berkedip. Suara tidak diputar."
            )
        )
        susunan.addSpacing(6)

        kartu = QFrame()
        kartu.setObjectName("kartuPengaturan")
        kartu_susunan = QVBoxLayout(kartu)
        kartu_susunan.setContentsMargins(18, 14, 18, 14)
        kartu_susunan.setSpacing(14)
        susunan.addWidget(kartu)
        susunan.addStretch()
        gulung.setWidget(isi)

        try:
            kategori = self.master.list_categories(only_active=True)
        except Exception:  # noqa: BLE001 - halaman pengaturan tidak boleh mati
            logger.exception("Jenis layanan tidak terbaca; kartu media dilewati")
            kartu_susunan.addWidget(
                keterangan("Daftar jenis layanan tidak dapat dibaca saat ini.")
            )
            return gulung

        if not kategori:
            kartu_susunan.addWidget(keterangan("Belum ada jenis layanan."))
            return gulung

        self._ladang_media = " ".join(
            f"{layanan.prefix} {layanan.name} {layanan.code}" for layanan in kategori
        ).lower()
        self.media_layanan: dict[str, PemilihMediaLayanan] = {}
        for indeks, layanan in enumerate(kategori):
            if indeks:
                kartu_susunan.addWidget(_garis())
            label = QLabel(f"{layanan.prefix} — {layanan.name}")
            label.setProperty("namaPengaturan", "true")
            kartu_susunan.addWidget(label)
            pemilih = PemilihMediaLayanan(layanan.code, ringkas=True)
            self.media_layanan[layanan.code] = pemilih
            kartu_susunan.addWidget(pemilih)

        return gulung

    def _bangun_bar(self) -> QWidget:
        """
        Bar tetap di bawah layar: keadaan perubahan, lalu tombolnya.

        Pesan hasil ditaruh sebaris dengan tombolnya, bukan sebagai kotak
        dialog. Administrator sering mengubah beberapa pengaturan
        berturut-turut, dan kotak yang harus ditutup setiap kali hanya
        menambah pekerjaan.
        """
        bar = QFrame()
        bar.setObjectName("barPengaturan")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        susunan = QHBoxLayout(bar)
        susunan.setContentsMargins(0, 8, 0, 8)
        susunan.setSpacing(12)

        self.pesan = QLabel("")
        self._penghapus_pesan.timeout.connect(self._perbarui_status)
        susunan.addWidget(self.pesan)
        susunan.addStretch()

        self.tombol_batal = tombol("Batalkan Perubahan")
        self.tombol_batal.clicked.connect(self._batalkan)
        susunan.addWidget(self.tombol_batal)

        self.tombol_simpan = tombol("Simpan", variant="primary")
        self.tombol_simpan.clicked.connect(self.simpan)
        susunan.addWidget(self.tombol_simpan)
        return bar

    # -----------------------------------------------------------------
    # Navigasi dan pencarian
    # -----------------------------------------------------------------

    def _pilih_kelompok(self, baris: int) -> None:
        if 0 <= baris < len(self._kelompok):
            self.tumpukan.setCurrentIndex(baris)

    def _saring(self, teks: str) -> None:
        """
        Sembunyikan baris yang tidak cocok, dan kelompok yang habis isinya.

        Daftar kelompok di kiri berubah peran ketika ada kata pencarian: ia
        menjadi daftar hasil, lengkap dengan berapa yang cocok di masing-
        masing kelompok. Tanpa itu, pencarian yang hasilnya berada di
        kelompok lain tampak seperti pencarian yang tidak menemukan apa-apa.
        """
        kata = teks.strip().lower()
        ada_hasil = False

        for indeks, (nama, baris_baris) in enumerate(self._kelompok):
            if nama == KELOMPOK_MEDIA:
                ladang = f"{nama} {self._ladang_media}".lower()
                cocok = 1 if not kata or kata in ladang else 0
            else:
                cocok = 0
                pertama = True
                for baris in baris_baris:
                    tampil = not kata or baris.cocok(kata)
                    baris.setVisible(tampil)
                    if baris.pemisah is not None:
                        baris.pemisah.setVisible(tampil and not pertama)
                    if tampil:
                        cocok += 1
                        pertama = False

            item = self.rail.item(indeks)
            item.setText(nama if not kata else f"{nama}  ·  {cocok}")
            item.setHidden(bool(kata) and cocok == 0)
            ada_hasil = ada_hasil or cocok > 0

        if not ada_hasil:
            self.label_kosong.setText(
                f'Tidak ada pengaturan yang cocok dengan "{teks.strip()}".'
            )
            self.tumpukan.setCurrentWidget(self._halaman_kosong)
            return

        # Kelompok yang sedang terbuka boleh saja tidak punya hasil sama
        # sekali; pindahkan ke kelompok pertama yang punya.
        sekarang = self.rail.currentRow()
        if sekarang < 0 or self.rail.item(sekarang).isHidden():
            for indeks in range(self.rail.count()):
                if not self.rail.item(indeks).isHidden():
                    self.rail.setCurrentRow(indeks)
                    break
        else:
            self.tumpukan.setCurrentIndex(sekarang)

    def _fokus_cari(self) -> None:
        self.cari.setFocus()
        self.cari.selectAll()

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def _batalkan(self) -> None:
        """Kembalikan nilai tersimpan, setelah dipastikan bukan ketukan salah."""
        if not self.berubah():
            return
        if not konfirmasi(
            self,
            "Buang perubahan yang belum disimpan?",
            "Batalkan perubahan",
        ):
            return
        self.muat_ulang()

    def muat_ulang(self) -> None:
        """Isi seluruh kontrol dari nilai yang tersimpan."""
        berhasil, tersimpan = jalankan_aman(
            self, self.settings.all, "Gagal membaca pengaturan"
        )
        if not berhasil or tersimpan is None:
            return
        for kunci, baris in self.baris.items():
            baris.tampilkan(tersimpan.get(kunci, ""))
        self._muat_ringkasan_tayang()
        self._perbarui_peringatan_daftar()
        self._perbarui_status()

    def _muat_ringkasan_tayang(self) -> None:
        """Angka tayang dan tanda gagal yang dilaporkan tablet anjungan."""
        daftar = self.baris.get(daftar_putar.KUNCI)
        if daftar is None:
            return
        from app.services import media_tayang

        try:
            ringkasan = media_tayang.ringkasan()
        except Exception:
            # Angka tayang hanya pelengkap; halaman pengaturan tetap harus
            # terbuka walau tabelnya belum ada atau database sedang sibuk.
            logger.warning("Ringkasan tayang iklan gagal dibaca", exc_info=True)
            return
        daftar.kontrol.tampilkan_ringkasan(ringkasan)

    def _aktifkan_media_bila_perlu(self) -> None:
        """
        Mencentang iklan sementara panel masih "Teks sambutan" berarti iklan
        itu tidak pernah tayang. Jenis tampilan ikut dipindah ke folder media,
        sebagai perubahan yang belum disimpan seperti perubahan lainnya.
        """
        daftar = self.baris.get(daftar_putar.KUNCI)
        jenis = self.baris.get("kiosk.welcome_kind")
        if daftar is None or jenis is None:
            return
        if daftar.kontrol.ada_yang_diputar() and jenis.nilai() == "teks":
            jenis.tulis("media")
            self._beritahu(
                "Tampilan panel anjungan dipindah ke Folder media supaya "
                "iklan yang dicentang tayang. Simpan untuk menerapkannya.",
                WARNING,
            )
        self._perbarui_peringatan_daftar()

    def _perbarui_peringatan_daftar(self) -> None:
        daftar = self.baris.get(daftar_putar.KUNCI)
        jenis = self.baris.get("kiosk.welcome_kind")
        if daftar is None or jenis is None:
            return
        tidak_tayang = jenis.nilai() == "teks" and daftar.kontrol.ada_yang_diputar()
        daftar.kontrol.tampilkan_peringatan(
            "Belum tayang: Panel Anjungan masih memakai Teks sambutan."
            if tidak_tayang
            else ""
        )

    def berubah(self) -> dict[str, str]:
        """Pengaturan yang nilainya di layar berbeda dari yang tersimpan."""
        return {
            kunci: baris.nilai()
            for kunci, baris in self.baris.items()
            if baris.sudah_berubah()
        }

    def simpan(self) -> None:
        """
        Simpan hanya pengaturan yang benar-benar berubah.

        Menulis semuanya akan memenuhi audit log dengan baris perubahan
        untuk nilai yang sebenarnya tidak disentuh, sehingga jejak perubahan
        yang sungguhan justru tenggelam.
        """
        berubah = self.berubah()
        if not berubah:
            self._beritahu("Tidak ada pengaturan yang berubah.", TEXT_MUTED)
            return

        for kunci, nilai in berubah.items():
            sukses, _ = jalankan_aman(
                self,
                lambda k=kunci, v=nilai: self.settings.set(k, v),
                "Gagal menyimpan pengaturan",
            )
            if not sukses:
                # Berhenti pada kegagalan pertama lalu muat ulang, supaya
                # yang tampil di layar sama dengan yang benar-benar tersimpan.
                self.muat_ulang()
                return

        self.muat_ulang()
        jumlah = len(berubah)
        self._beritahu(f"{jumlah} pengaturan tersimpan.", SUCCESS)

    def _sesuaikan_jenis_sambutan(self, nama: str) -> None:
        """Pilih berkas gambar/video ikut mengganti jenis tampilan panel."""
        jenis = jenis_sambutan_dari_berkas(nama)
        if jenis is None or "kiosk.welcome_kind" not in self.baris:
            return
        self.baris["kiosk.welcome_kind"].tulis(jenis)

    # -----------------------------------------------------------------
    # Keadaan
    # -----------------------------------------------------------------

    def _perbarui_status(self) -> None:
        """
        Tulis ulang bar bawah menurut ada-tidaknya perubahan.

        Tombol Simpan yang selalu menyala tidak memberi tahu apa pun.
        Tombol yang menyala hanya ketika ada yang berubah sekaligus
        menjawab "apakah tadi saya sudah menyimpan".
        """
        jumlah = len(self.berubah())
        self.tombol_simpan.setEnabled(bool(jumlah))
        self.tombol_batal.setEnabled(bool(jumlah))
        if jumlah:
            self._tulis_pesan(f"{jumlah} pengaturan belum disimpan", WARNING)
        else:
            self._tulis_pesan("Semua perubahan tersimpan", TEXT_MUTED)

    def _beritahu(self, teks: str, warna: str) -> None:
        self._tulis_pesan(teks, warna)
        self._penghapus_pesan.start(JEDA_PESAN)

    def _tulis_pesan(self, teks: str, warna: str) -> None:
        self.pesan.setText(teks)
        self.pesan.setStyleSheet(f"color: {warna}; font-weight: 600;")
