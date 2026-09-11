"""
Panel sambutan anjungan: teks, atau isi folder media/kiosk.

Berkas hidup di mesin anjungan, bukan di database. Pengaturan bersama
hanya menyimpan jenis tampilan; semua gambar dan video di folder
diputar bergiliran menurut nama file, lalu diulang dari awal.

Panel yang sama diambil alih sementara oleh KioskPage untuk dua hal,
lalu dikembalikan ke putaran sambutan:

* media (atau teks) satu jenis layanan, selama layar konfirmasi tampil;
* kartu nomor yang baru terbit, selama layar hasil tampil.

Media per jenis layanan mengikuti aturan yang sama seperti sambutan —
berkasnya di mesin anjungan, bukan di database — dan dialamatkan lewat
konvensi folder `media/kiosk/layanan/<code>/`, sehingga tidak perlu
kolom baru maupun migrasi.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QElapsedTimer,
    QFileSystemWatcher,
    QTimer,
    QUrl,
    QPropertyAnimation,
)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.config import base_dir
from app.core.logger import get_logger
from app.services.settings_service import SettingsService
from app.ui.display.tema import Palet
from app.ui.efek import efek_grafis_aktif, pasang_efek

logger = get_logger("ui.kiosk.sambutan")

JENIS_TEKS = "teks"
JENIS_MEDIA = "media"
#: Nilai lama di database, diperlakukan sama dengan folder media.
JENIS_GAMBAR = "gambar"
JENIS_VIDEO = "video"

JENIS_FOLDER = frozenset({JENIS_MEDIA, JENIS_GAMBAR, JENIS_VIDEO})

HALAMAN_TEKS = 0
HALAMAN_GAMBAR = 1
HALAMAN_VIDEO = 2
#: Kartu nomor yang baru terbit. Halaman teks biasa tidak dipakai untuk
#: ini karena kartunya butuh empat ukuran huruf yang berbeda sekaligus,
#: sedangkan halaman teks sengaja satu label bergaya seragam.
HALAMAN_KARTU = 3

EKSTENSI_GAMBAR = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}
EKSTENSI_VIDEO = {".mp4", ".mkv", ".webm", ".avi"}
EKSTENSI_MEDIA = EKSTENSI_GAMBAR | EKSTENSI_VIDEO


def _pola(ekstensi: set[str]) -> str:
    return " ".join(f"*{e}" for e in sorted(ekstensi))


#: Filter QFileDialog, diturunkan dari daftar ekstensi di atas supaya
#: berkas yang boleh dipilih admin dan berkas yang benar-benar dapat
#: diputar panel tidak pernah berbeda.
FILTER_BERKAS_ANJUNGAN = (
    f"Gambar dan video ({_pola(EKSTENSI_MEDIA)});;"
    f"Gambar ({_pola(EKSTENSI_GAMBAR)});;"
    f"Video ({_pola(EKSTENSI_VIDEO)});;"
    "Semua berkas (*)"
)

DURASI_SLIDE_BAWAAN_DETIK = 10

#: Lama posisi video boleh diam di tempat sebelum dianggap tersendat.
#:
#: Putaran sambutan memakai ambang pendek: item berikutnya tetap tampil,
#: jadi salah menduga pun tidak merugikan. Media layanan memakai ambang
#: jauh lebih panjang karena kesimpulannya berbeda — ia MENYERAH ke teks,
#: dan menyerah terlalu cepat berarti membuang video yang sebenarnya
#: cuma tersendat sesaat saat mulai diputar.
MACET_PUTARAN_MS = 2_000
MACET_LAYANAN_MS = 5_000

#: Tebal tepi panel di sekeliling gambar/video, dalam piksel. Naikkan bila
#: ingin bingkainya lebih tebal; 0 membuat media mepet ke tepi panel (dan
#: sudut membulatnya ikut terlihat terpotong).
MARGIN_PANEL = 4

#: Subfolder di dalam media/kiosk tempat media per jenis layanan disimpan.
#: `daftar_media_kios()` hanya mengambil `path.is_file()`, sehingga folder
#: ini otomatis tidak ikut terputar sebagai sambutan.
NAMA_FOLDER_LAYANAN = "layanan"


def jenis_sambutan_dari_berkas(nama: str) -> str | None:
    """Folder media bila ekstensinya dikenali, atau None."""
    if Path(nama).suffix.lower() in EKSTENSI_MEDIA:
        return JENIS_MEDIA
    return None


def folder_media_kios() -> Path:
    """Folder berkas sambutan pada mesin ini, di sebelah aplikasi."""
    return base_dir() / "media" / "kiosk"


def daftar_media_kios() -> list[Path]:
    """
    Gambar dan video di folder media/kiosk, urut nama file.

    Nama yang diawali titik (mis. .gitkeep) diabaikan. Urutan nama
    adalah urutan putar: `01_sambutan.mp4` lalu `02_edukasi.jpg`.
    """
    folder = folder_media_kios()
    if not folder.is_dir():
        return []
    hasil: list[Path] = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() in EKSTENSI_MEDIA:
            hasil.append(path)
    return hasil


def jejak_media(daftar: list[Path]) -> tuple[tuple[str, int, int], ...]:
    """Nama, waktu ubah, dan ukuran — berubah bila berkas diganti isinya."""
    jejak: list[tuple[str, int, int]] = []
    for path in daftar:
        try:
            st = path.stat()
            jejak.append((path.name, int(st.st_mtime_ns), int(st.st_size)))
        except OSError:
            jejak.append((path.name, 0, 0))
    return tuple(jejak)


def path_media_kios(nama: str) -> Path | None:
    """
    Temukan berkas sambutan, atau None bila tidak ada.

    Nama relatif hanya boleh berada di dalam folder media/kiosk — path
    yang merayap ke luar (`../...`) ditolak. Path absolut dipakai apa
    adanya, untuk mesin yang menyimpan medianya di folder lain.
    """
    nama = (nama or "").strip()
    if not nama:
        return None
    kandidat = Path(nama)
    if kandidat.is_absolute():
        return kandidat if kandidat.is_file() else None
    folder = folder_media_kios().resolve()
    gabung = (folder / nama).resolve()
    try:
        gabung.relative_to(folder)
    except ValueError:
        return None
    return gabung if gabung.is_file() else None


def salin_ke_media_kios(sumber: Path) -> Path:
    """
    Salin berkas ke folder media/kiosk, lalu kembalikan path tujuannya.

    Bila sumbernya sudah berada di folder itu, tidak disalin ulang.
    """
    folder = folder_media_kios()
    folder.mkdir(parents=True, exist_ok=True)
    sumber = sumber.resolve()
    tujuan = (folder / sumber.name).resolve()
    if sumber != tujuan:
        shutil.copy2(sumber, tujuan)
    return tujuan


def folder_media_layanan(code: str) -> Path | None:
    """
    Folder media satu jenis layanan, atau None bila `code` tidak aman.

    Foldernya dinamai `code`, bukan prefix: prefix masih boleh diubah admin
    selama jenis layanannya belum dipakai antrian, sedangkan code dikunci
    sejak dibuat — sehingga foldernya tidak pernah jadi yatim karena
    namanya berganti.

    `code` datang dari isian admin, jadi diperlakukan sebagai nama yang
    tidak dipercaya: wajib satu segmen nama saja, dan hasilnya wajib tetap
    berada di dalam media/kiosk/layanan. Penjagaan yang sama dengan
    `path_media_kios`, dengan alasan yang sama.
    """
    bersih = (code or "").strip()
    if not bersih or bersih != Path(bersih).name:
        return None
    induk = (folder_media_kios() / NAMA_FOLDER_LAYANAN).resolve()
    calon = (induk / bersih).resolve()
    if calon == induk:
        return None
    try:
        calon.relative_to(induk)
    except ValueError:
        return None
    return calon


def media_layanan(code: str) -> Path | None:
    """
    SATU berkas media untuk jenis layanan ini, atau None.

    Sengaja satu, bukan daftar. Panel layanan hanya tampil selama layar
    konfirmasi dan layar hasil — terlalu singkat untuk sebuah putaran —
    dan putaran kedua akan bertabrakan dengan mesin putar sambutan yang
    dijaga `_jaga_putaran`. Bila foldernya berisi lebih dari satu berkas,
    yang pertama menurut nama yang dipakai.
    """
    folder = folder_media_layanan(code)
    if folder is None or not folder.is_dir():
        return None
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() in EKSTENSI_MEDIA:
            return path
    return None


def salin_ke_media_layanan(code: str, sumber: Path) -> Path | None:
    """
    Pasang satu berkas media untuk sebuah jenis layanan.

    Berkas lain di folder itu DIHAPUS. Hanya satu berkas yang pernah
    dipakai (lihat `media_layanan`), jadi membiarkan yang lama menumpuk
    berarti menyimpan berkas yang tidak akan pernah tampil — dan lebih
    buruk lagi, memilih berkas baru yang namanya jatuh setelah nama lama
    secara alfabet akan tampak seperti tidak terjadi apa-apa.

    Hanya menyentuh isi media/kiosk/layanan/<code>/, folder yang memang
    tidak dipakai untuk apa pun selain ini.
    """
    folder = folder_media_layanan(code)
    if folder is None:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    sumber = sumber.resolve()
    tujuan = (folder / sumber.name).resolve()
    for lama in folder.iterdir():
        if not lama.is_file() or lama.resolve() == tujuan:
            continue
        try:
            lama.unlink()
        except OSError:
            logger.warning(
                "Media layanan lama %s tidak dapat dihapus; "
                "berkas baru mungkin tidak terpilih",
                lama.name,
            )
    if sumber != tujuan:
        shutil.copy2(sumber, tujuan)
    return tujuan


def hapus_media_layanan(code: str) -> None:
    """Kosongkan folder media sebuah jenis layanan."""
    folder = folder_media_layanan(code)
    if folder is None or not folder.is_dir():
        return
    for berkas in folder.iterdir():
        if not berkas.is_file():
            continue
        try:
            berkas.unlink()
        except OSError:
            logger.warning("Media layanan %s tidak dapat dihapus", berkas.name)


class _LabelGambar(QLabel):
    """Gambar yang selalu muat di panel, tanpa dipotong atau diregang."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._asli: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

    def set_gambar(self, pixmap: QPixmap | None) -> None:
        self._asli = pixmap if pixmap is not None and not pixmap.isNull() else None
        if self._asli is None:
            self.setPixmap(QPixmap())
            return
        self._sesuaikan()

    def resizeEvent(self, event) -> None:  # noqa: N802 - nama API Qt
        super().resizeEvent(event)
        self._sesuaikan()

    def _sesuaikan(self) -> None:
        if self._asli is None:
            return
        # Halaman tumpukan yang sedang tersembunyi sering berukuran 0.
        # Mengosongkan pixmap di sini membuat gambar hilang saat halaman
        # itu ditampilkan lagi tanpa peristiwa resize baru.
        if self.width() < 2 or self.height() < 2:
            return
        self.setPixmap(
            self._asli.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class PanelSambutanKios(QFrame):
    """
    Satu panel dengan empat isi yang bergantian.

    Keadaan bakunya adalah sambutan: teks, atau putaran berkas di folder
    media. KioskPage mengambil alih panel ini dua kali per pengunjung —
    dengan media/teks jenis layanan saat A/B/C disentuh, lalu dengan kartu
    nomor saat nomornya terbit — dan `_kembali_ke_sambutan()` yang
    mengembalikannya.

    Selama diambil alih, `_menampilkan_info_layanan` bernilai True. Flag
    itu MENAHAN seluruh mesin putar sambutan: detak `_jaga_putaran`,
    penyegaran `muat_pengaturan` yang datang dua detik sekali dari papan,
    dan sinyal selesai/gagal pemutar video. Setiap jalan masuk ke keadaan
    "diambil alih" wajib menyalakannya sebelum menyentuh pemutar.
    """

    def __init__(
        self,
        settings: SettingsService,
        palet: Palet,
        *,
        teks_bawaan: str,
        durasi_fade_ms: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.palet = palet
        self._teks_bawaan = teks_bawaan
        self._durasi_fade_ms = durasi_fade_ms
        self._kunci_aktif = None
        self._menampilkan_info_layanan = False
        self._teks_tampil = teks_bawaan
        self._pemutar = None
        self._audio = None
        self._widget_video = None
        self._animasi: QPropertyAnimation | None = None
        self._bayangan_tersimpan = None
        self._daftar: list[Path] = []
        self._indeks = 0
        self.berkas_tampil: Path | None = None
        #: Media jenis layanan yang sedang mengambil alih panel, bila ada.
        self._berkas_layanan: Path | None = None
        #: Teks yang dipakai bila media layanan itu ternyata gagal diputar.
        self._teks_cadangan_layanan = ""
        #: True bila pengambilalihan sempat mengganti SUMBER pemutar, bukan
        #: sekadar menjedanya. Menentukan jalan pulang: sumber yang masih
        #: utuh boleh disambung, sumber yang sudah tergantikan tidak —
        #: lihat `_kembali_ke_sambutan`.
        self._pemutar_disentuh = False
        #: Perubahan folder media yang tiba selagi panel diambil alih.
        #: Ditunda, bukan dibuang: timer debounce-nya sudah terlanjur
        #: meletus dan tidak akan mencoba lagi sampai ada perubahan
        #: berikutnya, sehingga berkas yang baru disalin admin bisa
        #: tertinggal tidak tampil entah sampai kapan.
        self._perlu_muat_ulang = False
        # Mesin putar: SATU detak berkala yang memutuskan kapan lanjut ke
        # item berikutnya. Sinyal "selesai" Qt (EndOfMedia/StoppedState)
        # dipakai sebagai jalan cepat opsional saja — di Windows dengan
        # FFmpeg sinyal itu sering absen di item terakhir, jadi detak ini
        # adalah satu-satunya yang WAJIB benar. Jangan tambah timer lain
        # untuk mendeteksi "video selesai": cukup baca posisi/durasi di
        # sini setiap detak.
        self._jantung = QTimer(self)
        self._jantung.setInterval(250)
        self._jantung.timeout.connect(self._jaga_putaran)
        self._jam_item = QElapsedTimer()
        self._posisi_tick_lalu = -1
        self._tick_macet = 0
        # Menahan sinyal "selesai" Qt yang muncul akibat panggilan kita
        # sendiri (stop()/setSource() saat ganti atau lepas berkas), bukan
        # akibat video sungguh-sungguh selesai.
        self._timer_izinkan_selesai = QTimer(self)
        self._timer_izinkan_selesai.setSingleShot(True)
        self._timer_izinkan_selesai.timeout.connect(self._izinkan_selesai_video)
        self._timer_folder = QTimer(self)
        self._timer_folder.setSingleShot(True)
        self._timer_folder.timeout.connect(self._muat_ulang_dari_folder)
        self._pantau_folder = QFileSystemWatcher(self)
        self._pantau_folder.directoryChanged.connect(self._folder_media_berubah)
        self._pantau_folder.fileChanged.connect(self._folder_media_berubah)
        self._abaikan_selesai_video = False
        self._dijeda_sengaja = False
        # Dikunci SELAMA _item_berikutnya() berjalan (termasuk semua
        # pemanggilan bersarang yang dipicu olehnya, mis. sinyal Qt dari
        # stop()/setSource() saat menyiapkan item berikutnya). Tanpa kunci
        # ini, sinyal yang muncul di tengah pergantian item bisa memicu
        # _item_berikutnya() lagi secara bersarang dan merusak indeks.
        self._sedang_ganti_item = False

        self.setObjectName("panelInfoKios")
        self.setStyleSheet(
            f"QFrame#panelInfoKios {{ background: {palet.panel};"
            " border-radius: 20px; }}"
        )

        luar = QVBoxLayout(self)
        # Tepi tipis saja. Margin di sinilah yang tampak sebagai "bingkai"
        # di sekeliling gambar/video, karena warna panel menyembul di
        # baliknya. Tidak dinolkan supaya sudut membulat panel (20px) tetap
        # rapi — gambar bersudut siku yang mepet ke tepi akan terlihat
        # terpotong di keempat sudutnya.
        luar.setContentsMargins(MARGIN_PANEL, MARGIN_PANEL, MARGIN_PANEL, MARGIN_PANEL)

        self.tumpukan = QStackedWidget()
        luar.addWidget(self.tumpukan, stretch=1)

        self._halaman_teks = QWidget()
        isi_teks = QVBoxLayout(self._halaman_teks)
        # Teks tetap punya jarak baca seperti sebelumnya; yang dirampingkan
        # hanya tepi di sekeliling gambar/video.
        isi_teks.setContentsMargins(12, 4, 12, 4)
        self.label_teks = QLabel(teks_bawaan)
        self.label_teks.setObjectName("labelInfoKios")
        self.label_teks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_teks.setWordWrap(True)
        self.label_teks.setMinimumSize(1, 1)
        self.label_teks.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        isi_teks.addStretch()
        isi_teks.addWidget(self.label_teks)
        isi_teks.addStretch()
        self.tumpukan.addWidget(self._halaman_teks)

        self.label_gambar = _LabelGambar()
        self.tumpukan.addWidget(self.label_gambar)

        self._halaman_video = QWidget()
        isi_video = QVBoxLayout(self._halaman_video)
        isi_video.setContentsMargins(0, 0, 0, 0)
        isi_video.addWidget(self._siapkan_video() or QWidget(), stretch=1)
        self.tumpukan.addWidget(self._halaman_video)
        if self._widget_video is not None:
            self._widget_video.hide()

        self.tumpukan.addWidget(self._bangun_halaman_kartu())

        # Pudar hanya pada label teks. QVideoWidget adalah jendela native:
        # QGraphicsOpacityEffect pada tumpukan membuat videonya hitam.
        self._efek = QGraphicsOpacityEffect(self.label_teks)
        pasang_efek(self.label_teks, self._efek)

        # muat_pengaturan() dipanggil DisplayPage SETELAH bayangan dipasang
        # pada panel ini. Memuat video di sini, sebelum bayangan ada,
        # lalu bayangan ditambahkan di atasnya, membuat video hitam.

    def _bangun_halaman_kartu(self) -> QWidget:
        """
        Kartu nomor yang baru terbit: nomor, layanan, sisa antrian.

        Nomornya dibuat sebesar mungkin dengan sengaja. `_cetak()` di
        KioskPage tidak pernah menggagalkan pengambilan nomor — printer
        yang kehabisan kertas tetap meninggalkan nomor yang sah — dan pada
        saat itu layar inilah SATU-SATUNYA catatan nomor yang dipegang
        pengunjung. Cukup besar untuk difoto dengan ponsel dari jarak
        berdiri, bukan sekadar terbaca.

        Kalimat arahannya TIDAK ada di sini. Kartu ini yang difoto, dan
        yang perlu terbawa dalam foto hanyalah nomornya; apa yang harus
        dilakukan pengunjung dikatakan sekali saja, oleh pil petunjuk di
        panel bawah yang berada tepat di depan tangannya.

        Kartunya berlatar sendiri (`kartuKios`), bukan menumpang latar
        panel. Warna latar dan warna tulisannya lalu boleh diambil dari
        pasangan `kartu`/`nomor` milik tema — satu-satunya pasangan yang
        sudah dijamin terbaca di ketujuh tema, karena itulah pasangan yang
        dipakai kartu loket di papan.
        """
        halaman = QFrame()
        halaman.setObjectName("kartuKios")
        isi = QVBoxLayout(halaman)
        isi.setContentsMargins(12, 4, 12, 4)
        isi.setSpacing(2)

        self.label_kartu_judul = QLabel("NOMOR ANDA")
        self.label_kartu_nomor = QLabel("")
        self.label_kartu_layanan = QLabel("")
        self.label_kartu_sisa = QLabel("")

        isi.addStretch(1)
        for label in (
            self.label_kartu_judul,
            self.label_kartu_nomor,
            self.label_kartu_layanan,
            self.label_kartu_sisa,
        ):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setMinimumSize(1, 1)
            isi.addWidget(label)
        isi.addStretch(1)
        self.kartu_kios = halaman
        return halaman

    # -----------------------------------------------------------------
    # Pengaturan
    # -----------------------------------------------------------------

    def teks_sambutan(self) -> str:
        kustom = (self.settings.get("kiosk.welcome_text", "") or "").strip()
        return kustom or self._teks_bawaan

    def muat_pengaturan(self) -> None:
        """
        Terapkan jenis tampilan dari pengaturan, tanpa menyentuh info layanan.

        Dipanggil berkala dari papan. Bila kuncinya sama, tidak melakukan
        apa-apa — memuat ulang video tiap dua detik akan membuatnya
        berkedip dari awal.
        """
        if self._menampilkan_info_layanan:
            return
        jenis = self.settings.get("kiosk.welcome_kind", JENIS_TEKS)
        teks = self.teks_sambutan()
        daftar = self._kumpulkan_daftar() if jenis in JENIS_FOLDER else []
        durasi = str(self._durasi_slide_ms())
        kunci = (jenis, teks, jejak_media(daftar), durasi)
        if kunci == self._kunci_aktif:
            return
        self._kunci_aktif = kunci
        self._teks_tampil = teks
        self.label_teks.setText(teks)
        self._pasang_pantau_folder(daftar)
        self._terapkan(jenis, daftar)

    # -----------------------------------------------------------------
    # Pengambilalihan panel oleh KioskPage
    # -----------------------------------------------------------------

    def tampilkan_info(self, teks: str | None, *, berkas: Path | None = None) -> None:
        """
        Tampilkan info sebuah jenis layanan, atau kembali ke sambutan.

        `berkas` diutamakan atas `teks`: panel ini kecil dan nama layanan
        sudah tampil besar di panel konfirmasi di bawahnya, jadi menumpuk
        gambar dan tulisan hanya membuat dua-duanya sulit dibaca. `teks`
        tetap dipakai sebagai cadangan bila berkasnya gagal dimuat.

        `None` pada keduanya berarti kembali ke sambutan.
        """
        if berkas is not None and self._ambil_alih_media(berkas, teks or ""):
            return

        menuju_sambutan = not (teks or "").strip()
        baru = self.teks_sambutan() if menuju_sambutan else (teks or "").strip()
        # Perbandingan teks saja tidak cukup lagi sejak panel bisa dipegang
        # media atau kartu nomor: teksnya mungkin sama persis dengan yang
        # terakhir tampil, sedangkan yang kelihatan di layar bukan teks.
        if (
            not self._sedang_dipegang()
            and baru == self._teks_tampil
            and menuju_sambutan == (not self._menampilkan_info_layanan)
        ):
            return

        if menuju_sambutan and self._sedang_dipegang():
            # Memudarkan media tidak mungkin: efek opacity hanya terpasang
            # pada label teks, dan QGraphicsOpacityEffect di atas
            # QVideoWidget membuat videonya hitam (lihat _lepas_bayangan).
            self._teks_tampil = baru
            self._hentikan_animasi()
            self._efek.setOpacity(1.0)
            self._kembali_ke_sambutan()
            return

        self._teks_tampil = baru
        # Kunci sejak awal fade, supaya penyegaran papan dua detik sekali
        # tidak mengembalikan video di tengah transisi ke info layanan.
        self._menampilkan_info_layanan = not menuju_sambutan
        if not menuju_sambutan:
            self._jeda_putaran()

        self._hentikan_animasi()

        self._animasi = QPropertyAnimation(self._efek, b"opacity", self)
        self._animasi.setDuration(self._durasi_fade_ms)
        self._animasi.setStartValue(1.0)
        self._animasi.setEndValue(0.0)
        self._animasi.finished.connect(
            lambda baru=baru, sambutan=menuju_sambutan: self._setelah_pudar(
                baru, sambutan
            )
        )
        self._animasi.start()

    def tampilkan_kartu(self, *, nomor: str, layanan: str, sisa: str) -> None:
        """
        Ganti isi panel dengan kartu nomor yang baru terbit.

        Seketika, tanpa pudar: yang tergantikan hampir selalu media
        layanan, dan media tidak bisa dipudarkan.

        Pemutar hanya DIJEDA, tidak dilepas. Bila layanan tadi tidak punya
        media, sumber pemutar masih memegang klip sambutan pada posisi
        terakhirnya, dan `_kembali_ke_sambutan()` bisa menyambungnya.
        """
        self._hentikan_animasi()
        self._efek.setOpacity(1.0)
        # Dinyalakan SEBELUM menyentuh apa pun: inilah yang menahan detak
        # putaran dan penyegaran papan selama kartu tampil.
        self._menampilkan_info_layanan = True
        self._jeda_putaran()
        self._berkas_layanan = None
        self._teks_cadangan_layanan = ""

        self.label_kartu_nomor.setText(nomor)
        self.label_kartu_layanan.setText(layanan)
        self.label_kartu_sisa.setText(sisa)
        self.label_kartu_sisa.setVisible(bool(sisa))

        self._tampilkan_halaman(HALAMAN_KARTU)
        self._pulihkan_bayangan()

    def _sedang_dipegang(self) -> bool:
        """True bila panel sedang menampilkan media layanan atau kartu."""
        return (
            self._berkas_layanan is not None
            or self.tumpukan.currentIndex() == HALAMAN_KARTU
        )

    def _ambil_alih_media(self, berkas: Path, teks_cadangan: str) -> bool:
        """
        Tampilkan media satu jenis layanan. False bila berkasnya tak terpakai.

        Seketika, tanpa pudar — alasannya sama dengan `tampilkan_kartu`.
        """
        if self._berkas_layanan == berkas:
            return True

        self._hentikan_animasi()
        self._efek.setOpacity(1.0)
        # Dinyalakan SEBELUM menyentuh pemutar. stop()/setSource() di dalam
        # _tampilkan_item memancarkan sinyal "selesai" dan "error" palsu,
        # dan flag inilah yang menahan keduanya supaya tidak memajukan
        # putaran sambutan di tengah pengambilalihan.
        self._menampilkan_info_layanan = True
        self._jeda_putaran()
        self._teks_cadangan_layanan = teks_cadangan
        # Berlaku untuk gambar JUGA, bukan video saja: jalur gambar di
        # _tampilkan_item() memanggil _lepaskan_berkas_video(), sehingga
        # klip sambutan yang sedang berjalan tetap kehilangan sumbernya.
        # Hanya info layanan yang murni teks — yang tidak pernah masuk ke
        # sini — meninggalkan pemutar sekadar terjeda.
        self._pemutar_disentuh = True

        if self._tampilkan_item(berkas, ulang=True):
            self._berkas_layanan = berkas
            return True

        logger.warning("Media layanan %s gagal dimuat, memakai teks", berkas.name)
        self._berkas_layanan = None
        return False

    def _kembali_ke_sambutan(self) -> None:
        """
        Lepaskan panel dari pengambilalihan, kembali ke putaran sambutan.

        Dua jalan pulang, dipilih dari apakah SUMBER pemutar sempat
        tergantikan. Bila tidak — info layanan hanya teks, atau hanya
        gambar — klip sambutan cuma dijeda dan posisinya masih utuh, jadi
        disambung seperti sebelumnya. Bila iya, posisinya sudah hilang dan
        tidak ada gunanya memaksa mengulang klip yang sama dari nol: orang
        yang tadi menontonnya sudah pergi membawa nomornya, dan yang
        berdiri berikutnya lebih baik disambut item berikutnya dari awal.
        """
        self._berkas_layanan = None
        self._teks_cadangan_layanan = ""
        # Dibersihkan lebih dulu: _item_berikutnya() dan _jaga_putaran()
        # sama-sama menolak berjalan selama flag ini menyala. Tidak ada
        # celah balapan — seluruh sisa fungsi ini berjalan sinkron, jadi
        # tidak ada detak pewaktu maupun penyegaran papan yang bisa
        # menyelip di antaranya.
        self._menampilkan_info_layanan = False

        if self._pemutar_disentuh and self._daftar:
            self._pemutar_disentuh = False
            self._dijeda_sengaja = False
            self._item_berikutnya()
        else:
            self._pemutar_disentuh = False
            self._lanjutkan_sambutan()

        if self._perlu_muat_ulang:
            self._perlu_muat_ulang = False
            self.muat_pengaturan()

    def _setelah_pudar(self, teks: str, menuju_sambutan: bool) -> None:
        if menuju_sambutan:
            self._kembali_ke_sambutan()
        else:
            self.label_teks.setText(teks)
            self._tampilkan_halaman(HALAMAN_TEKS)
            self._pulihkan_bayangan()

        self._hentikan_animasi()
        self._animasi = QPropertyAnimation(self._efek, b"opacity", self)
        self._animasi.setDuration(self._durasi_fade_ms)
        self._animasi.setStartValue(0.0)
        self._animasi.setEndValue(1.0)
        self._animasi.start()

    def hentikan(self) -> None:
        self._hentikan_animasi()
        self._dijeda_sengaja = True
        self._berkas_layanan = None
        self._jeda_putaran()
        self._lepaskan_berkas_video()

    def ganti_gaya_teks(self, stylesheet: str) -> None:
        self.label_teks.setStyleSheet(stylesheet)

    def ganti_gaya_kartu(self, gaya: dict[str, str]) -> None:
        """Gaya tiap baris kartu nomor, dikirim papan bersama ukurannya."""
        for nama, stylesheet in gaya.items():
            label = getattr(self, f"label_kartu_{nama}", None)
            if label is not None:
                label.setStyleSheet(stylesheet)

    def ganti_latar_kartu(self, stylesheet: str) -> None:
        """
        Latar kartu nomor, dikirim papan bersama warna tulisannya.

        Terpisah dari `ganti_gaya_kartu` karena yang dilukis bukan label
        melainkan bingkainya, dan keduanya harus datang dari tema yang
        sama: warna tulisan tanpa latarnya adalah persis cara nomor
        pernah menjadi hitam di atas papan hitam.
        """
        self.kartu_kios.setStyleSheet(stylesheet)

    def showEvent(self, event) -> None:  # noqa: N802 - nama API Qt
        super().showEvent(event)
        if self.tumpukan.currentIndex() == HALAMAN_GAMBAR:
            self.label_gambar._sesuaikan()

    def _hentikan_animasi(self) -> None:
        if self._animasi is None:
            return
        # stop() tidak memancarkan finished — itu hanya terjadi saat
        # animasi mencapai nilai akhir sendiri. Jangan disconnect():
        # PySide6 memperingatkan bila slotnya sudah tidak terpasang.
        self._animasi.stop()
        self._animasi = None

    # -----------------------------------------------------------------
    # Isi sambutan
    # -----------------------------------------------------------------

    def _kumpulkan_daftar(self) -> list[Path]:
        daftar = daftar_media_kios()
        if daftar:
            return daftar
        # Cadangan: satu berkas yang disebut pengaturan, termasuk path
        # absolut di luar folder, supaya mesin lama tetap menampilkan.
        satu = path_media_kios(self.settings.get("kiosk.welcome_file", ""))
        return [satu] if satu else []

    def _durasi_slide_ms(self) -> int:
        detik = self.settings.get_int(
            "kiosk.welcome_slide_seconds", DURASI_SLIDE_BAWAAN_DETIK
        )
        return max(1, detik) * 1000

    def _terapkan(self, jenis: str, daftar: list[Path]) -> None:
        # Jangan memakai _jeda_putaran(): flag "dijeda sengaja" menahan
        # pengawas video, dan pause() tetap mengunci berkas di Windows.
        self._jantung.stop()
        self._lepaskan_berkas_video()
        self._dijeda_sengaja = False
        self._sedang_ganti_item = False
        self._abaikan_selesai_video = False
        self._daftar = daftar
        self._indeks = 0
        self.berkas_tampil = None

        if jenis in JENIS_FOLDER and daftar:
            for i, berkas in enumerate(daftar):
                self._indeks = i
                if self._tampilkan_item(berkas):
                    logger.info(
                        "Sambutan anjungan mulai dari %s (%d/%d berkas)",
                        berkas.name, i + 1, len(daftar),
                    )
                    return
            logger.warning(
                "Tidak ada berkas sambutan anjungan yang dapat dibuka di %s",
                folder_media_kios(),
            )

        self._cadangan_teks()

    def _folder_media_berubah(self, _path: str = "") -> None:
        """Debounce: salin berkas bisa memicu banyak peristiwa sekaligus."""
        self._timer_folder.start(400)

    def _muat_ulang_dari_folder(self) -> None:
        """
        QFileSystemWatcher Windows sering memancarkan directoryChanged/
        fileChanged untuk hal yang tidak sungguh mengubah isi (waktu akses
        yang disentuh antivirus/pengindeks, proses lain yang sekadar
        membuka folder). JANGAN paksa _kunci_aktif=None di sini — itu
        membuat muat_pengaturan() selalu menganggap "berubah" dan me-reset
        putaran ke item pertama pada setiap sinyal basi, sehingga gambar
        (atau video) yang sedang tampil terpotong sebelum durasinya lewat.
        Cukup panggil muat_pengaturan(): perbandingan jejak_media() di
        dalamnya sudah benar mendeteksi perubahan SUNGGUHAN saja.
        """
        if self._menampilkan_info_layanan:
            # Ditunda, bukan dibuang. Timer debounce sudah meletus dan
            # tidak akan mencoba lagi sampai ada perubahan folder
            # BERIKUTNYA, sehingga berkas yang baru saja disalin admin
            # bisa tertinggal tidak tampil entah sampai kapan.
            self._perlu_muat_ulang = True
            return
        self.muat_pengaturan()

    def _pasang_pantau_folder(self, daftar: list[Path]) -> None:
        folder = folder_media_kios()
        target: set[str] = set()
        if folder.is_dir():
            target.add(str(folder.resolve()))
        target.update(str(p) for p in daftar)
        terpasang = set(self._pantau_folder.directories() + self._pantau_folder.files())
        for path in terpasang - target:
            self._pantau_folder.removePath(path)
        for path in target - terpasang:
            self._pantau_folder.addPath(path)

    def _cadangan_teks(self) -> None:
        self._jantung.stop()
        self._lepaskan_berkas_video()
        self._daftar = []
        self.berkas_tampil = None
        self.label_gambar.set_gambar(None)
        # Sembunyikan widget video (jendela native) SEBELUM memasang balik
        # efek bayangan pada panel — memasangnya lebih dulu membuat video
        # sempat dirender lewat jalur compositing berbeda sesaat sebelum
        # disembunyikan, dan di sebagian driver GPU malah tetap menembus.
        self._tampilkan_halaman(HALAMAN_TEKS)
        self._pulihkan_bayangan()

    def _lanjutkan_sambutan(self) -> None:
        """Kembali dari info layanan tanpa mengulang daftar dari awal."""
        if self._daftar:
            berkas = self._daftar[self._indeks]
            if self._tampilkan_item(berkas, lanjut=True):
                return
            # Berkas yang sedang ditampilkan hilang/rusak selagi dijeda.
            self._cadangan_teks()
            return
        self.label_teks.setText(self.teks_sambutan())
        self._teks_tampil = self.teks_sambutan()
        self._tampilkan_halaman(HALAMAN_TEKS)
        # Media layanan boleh berupa video walaupun sambutannya cuma teks,
        # dan video mematikan bayangan panel. Tanpa baris ini panel pulang
        # ke sambutan tanpa bayangannya.
        self._pulihkan_bayangan()

    def _item_berikutnya(self) -> None:
        """
        Lanjut ke item berikutnya, modulo panjang daftar — TIDAK ADA
        cabang "item terakhir, berhenti". Dikunci lewat _sedang_ganti_item
        selama fungsi ini berjalan (termasuk semua panggilan bersarang
        yang dipicunya, misalnya sinyal Qt dari stop()/setSource() saat
        _tampilkan_item() menyiapkan item berikutnya) supaya sinyal itu
        tidak memicu pergantian item kedua kalinya secara bersarang.
        """
        if (
            self._menampilkan_info_layanan
            or self._sedang_ganti_item
            or not self._daftar
        ):
            return
        self._sedang_ganti_item = True
        try:
            total = len(self._daftar)
            for _ in range(total):
                self._indeks = (self._indeks + 1) % total
                berkas = self._daftar[self._indeks]
                if self._tampilkan_item(berkas):
                    if self._indeks == 0:
                        logger.info(
                            "Sambutan anjungan mengulang dari awal: %s", berkas.name
                        )
                    else:
                        logger.info(
                            "Sambutan anjungan lanjut ke %s (%d/%d)",
                            berkas.name, self._indeks + 1, total,
                        )
                    return
            # Semua berkas gagal dibuka: jangan kosongkan panel, tetap di
            # item yang tampil dan coba lagi di detak berikutnya.
            self._mulai_jam_item()
        finally:
            self._sedang_ganti_item = False

    def _tampilkan_item(
        self, berkas: Path, *, lanjut: bool = False, ulang: bool = False
    ) -> bool:
        ekstensi = berkas.suffix.lower()
        if ekstensi in EKSTENSI_GAMBAR:
            if not self._pasang_gambar(berkas):
                logger.warning(
                    "Sambutan anjungan: gambar %s gagal dimuat, dilewati", berkas.name
                )
                return False
            self._dijeda_sengaja = False
            self._lepaskan_berkas_video()
            # Sembunyikan widget video SEBELUM memasang balik efek bayangan
            # (lihat catatan di _cadangan_teks): urutan ini mencegah video
            # native sempat "menembus" ke atas gambar sesaat.
            self._tampilkan_halaman(HALAMAN_GAMBAR)
            self._pulihkan_bayangan()
            self.berkas_tampil = berkas
            self._mulai_jam_item()
            return True

        if ekstensi in EKSTENSI_VIDEO:
            if not self._pasang_video(berkas, lanjut=lanjut, ulang=ulang):
                logger.warning(
                    "Sambutan anjungan: video %s gagal dimuat, dilewati", berkas.name
                )
                return False
            self._lepas_bayangan()
            self._tampilkan_halaman(HALAMAN_VIDEO)
            self.berkas_tampil = berkas
            self._mulai_jam_item()
            return True

        return False

    def _mulai_jam_item(self) -> None:
        self._jam_item.start()
        self._posisi_tick_lalu = -1
        self._tick_macet = 0
        if not self._jantung.isActive():
            self._jantung.start()

    def _jaga_putaran(self) -> None:
        """
        Detak berkala: satu-satunya pemicu yang WAJIB benar, termasuk di
        item terakhir. Timer/sinyal video Qt di Windows sering absen —
        jangan andalkan mereka, baca posisi/durasi langsung di sini.

        Melayani DUA pemakai dengan kesimpulan berbeda dari pembacaan yang
        sama: putaran sambutan maju ke item berikutnya, media jenis layanan
        mengulang dirinya sendiri sampai pengunjung memilih.
        """
        if self._sedang_ganti_item or not self._jam_item.isValid():
            return

        # Didahulukan atas penjagaan di bawahnya: selama media layanan
        # tampil, `_menampilkan_info_layanan` menyala dan `_daftar` tidak
        # relevan — keduanya akan memulangkan fungsi ini terlalu awal.
        if self._berkas_layanan is not None:
            self._jaga_ulangan_layanan()
            return

        if (
            self._menampilkan_info_layanan
            or self._dijeda_sengaja
            or not self._daftar
        ):
            return
        halaman = self.tumpukan.currentIndex()
        if halaman == HALAMAN_GAMBAR:
            if self._jam_item.elapsed() >= self._durasi_slide_ms():
                self._item_berikutnya()
            return
        if halaman != HALAMAN_VIDEO or self._pemutar is None:
            return

        selesai, macet_ms = self._periksa_ujung_video()
        if selesai or macet_ms >= MACET_PUTARAN_MS:
            self._item_berikutnya()

    def _periksa_ujung_video(self) -> tuple[bool, int]:
        """
        Baca sendiri apakah video sudah di ujung, dan berapa lama ia diam.

        Satu pembacaan untuk dua pemakai, karena kesalahannya sama:
        `EndOfMedia`/`StoppedState` sering tidak terpancar di Windows
        dengan backend FFmpeg, jadi posisi dan durasi dibaca langsung di
        sini alih-alih dipercayakan pada sinyal.

        Yang dikembalikan sengaja mentah — "sudah di ujung" dan "berapa
        milidetik posisinya tidak bergerak" — supaya tiap pemakai memilih
        ambang macetnya sendiri.
        """
        durasi = self._pemutar.duration()
        posisi = self._pemutar.position()
        selesai_posisi = durasi > 0 and posisi > 0 and posisi >= max(0, durasi - 250)
        elapsed = self._jam_item.elapsed()
        lewat_batas = elapsed >= (durasi + 1_000 if durasi > 0 else 8_000)

        if posisi == self._posisi_tick_lalu:
            self._tick_macet += 1
        else:
            self._tick_macet = 0
        self._posisi_tick_lalu = posisi

        return (
            selesai_posisi or lewat_batas,
            self._tick_macet * self._jantung.interval(),
        )

    def _jaga_ulangan_layanan(self) -> None:
        """
        Ulang video jenis layanan sampai pengunjung menekan YA atau BATAL.

        Video yang membeku di frame terakhir salah untuk panel ini:
        pengunjung menontonnya SAMBIL memutuskan, dan yang datang di
        tengah putaran hanya akan melihat gambar diam.
        """
        if self._dijeda_sengaja or self._pemutar is None:
            return
        if self.tumpukan.currentIndex() != HALAMAN_VIDEO:
            return

        selesai, macet_ms = self._periksa_ujung_video()
        if selesai:
            self._ulang_video_layanan()
            return
        if macet_ms >= MACET_LAYANAN_MS:
            # SENGAJA tidak diulang. Berkas yang rusak akan tersendat lagi
            # seketika, dan mengulangnya tiap detak menghasilkan kedutan
            # berulang di layar publik — jauh lebih buruk daripada teks.
            self._jatuhkan_media_layanan("tersendat")

    def _ulang_video_layanan(self) -> None:
        """
        Kembali ke detik nol.

        `setLoops(Infinite)` sudah dipasang sebagai jalan cepat, tetapi
        pengulangan internal Qt bertumpu pada deteksi akhir-media yang
        sama dengan sinyal yang sering absen itu. Jalur inilah yang WAJIB
        benar; yang di atas hanya bonus bila kebetulan bekerja.
        """
        if self._pemutar is None:
            return
        self._pemutar.setPosition(0)
        self._pemutar.play()
        # WAJIB. `lewat_batas` di _periksa_ujung_video dihitung dari jam
        # ini; tanpa direstart ia langsung benar lagi pada detak berikutnya
        # dan videonya diulang setiap 250 milidetik.
        self._mulai_jam_item()

    def _jatuhkan_media_layanan(self, alasan: str) -> None:
        """Lepas media layanan yang tidak dapat diputar, ganti dengan teks."""
        berkas = self._berkas_layanan
        if berkas is None:
            return
        self._berkas_layanan = None
        teks = self._teks_cadangan_layanan or self.teks_sambutan()
        self._teks_tampil = teks
        self.label_teks.setText(teks)
        self._lepaskan_berkas_video()
        self._tampilkan_halaman(HALAMAN_TEKS)
        self._pulihkan_bayangan()
        logger.warning("Media layanan %s %s; memakai teks", berkas.name, alasan)

    def _jeda_putaran(self) -> None:
        self._jantung.stop()
        self._dijeda_sengaja = True
        self._jeda_video()

    def _tampilkan_halaman(self, indeks: int) -> None:
        self.tumpukan.setCurrentIndex(indeks)
        if self._widget_video is not None:
            # QVideoWidget jendela native: halaman tumpukan yang "tersembunyi"
            # tetap menembus ke atas teks/gambar bila widgetnya tidak di-hide.
            # setVisible(False) saja kadang tak cukup di sebagian driver GPU
            # Windows — lower() + hide() eksplisit sebagai lapis kedua.
            tampilkan_video = indeks == HALAMAN_VIDEO
            self._widget_video.setVisible(tampilkan_video)
            if not tampilkan_video:
                self._widget_video.lower()
                self._widget_video.hide()
        if indeks == HALAMAN_GAMBAR:
            # Setelah halaman berganti, ukuran label baru pasti. Tanpa
            # panggilan ini, pixmap yang ditahan saat ukuran masih 0
            # tetap kosong sampai peristiwa resize berikutnya.
            self.label_gambar._sesuaikan()

    def _lepas_bayangan(self) -> None:
        """
        QVideoWidget tidak tampil di bawah QGraphicsDropShadowEffect.

        JANGAN memakai setGraphicsEffect(None) di sini: QWidget MEMILIKI
        efeknya, dan mengganti/mengosongkan efek MENGHAPUS objek C++-nya.
        Referensi Python di _bayangan_tersimpan jadi menunjuk objek mati,
        sehingga _pulihkan_bayangan() melempar RuntimeError persis di
        tengah pergantian item — sebelum berkas_tampil dan _mulai_jam_item()
        sempat dijalankan. Akibatnya gambar tidak pernah tercatat tampil,
        jam itemnya tidak di-restart, dan detak berikutnya langsung
        melompat balik ke video. Cukup NONAKTIFKAN efeknya: objeknya tetap
        hidup dan bisa dinyalakan lagi.
        """
        efek = self.graphicsEffect()
        if efek is not None:
            self._bayangan_tersimpan = efek
            try:
                efek.setEnabled(False)
            except RuntimeError:
                self._bayangan_tersimpan = None

    def _pulihkan_bayangan(self) -> None:
        efek = self._bayangan_tersimpan
        if efek is None:
            return
        try:
            # Pratinjau totem mematikan seluruh efek grafis — lihat
            # app/ui/efek.py. Memulihkan bayangan ke True di sini akan
            # menyalakannya lagi, dan panel informasinya kembali salah
            # gambar begitu video pertama selesai diputar.
            efek.setEnabled(efek_grafis_aktif())
        except RuntimeError:
            # Efeknya sudah dihapus Qt (mis. diganti dari luar panel ini).
            # Bukan alasan untuk menggagalkan pergantian item.
            self._bayangan_tersimpan = None

    def _pasang_gambar(self, berkas: Path | None) -> bool:
        if berkas is None or berkas.suffix.lower() not in EKSTENSI_GAMBAR:
            return False
        # Baca dari bytes, bukan path: Qt meng-cache QPixmap menurut nama
        # file, sehingga ganti isi dengan nama yang sama tampak "macet".
        try:
            data = berkas.read_bytes()
        except OSError:
            return False
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return False
        self.label_gambar.set_gambar(pixmap)
        return True

    def _siapkan_video(self) -> QWidget | None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget
        except ImportError:
            logger.warning("QtMultimedia tidak tersedia; panel video dimatikan")
            return None

        self._widget_video = QVideoWidget()
        self._widget_video.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._audio = QAudioOutput()
        self._audio.setMuted(True)
        self._pemutar = QMediaPlayer()
        self._pemutar.setAudioOutput(self._audio)
        self._pemutar.setVideoOutput(self._widget_video)
        self._pemutar.errorOccurred.connect(self._gagal_video)
        self._pemutar.mediaStatusChanged.connect(self._status_video)
        self._pemutar.playbackStateChanged.connect(self._keadaan_putar)
        return self._widget_video

    def _pasang_video(
        self, berkas: Path | None, *, lanjut: bool = False, ulang: bool = False
    ) -> bool:
        from PySide6.QtMultimedia import QMediaPlayer

        if berkas is None or self._pemutar is None:
            return False

        # Ditentukan di SATU baris dari argumen, bukan disimpulkan dari
        # keadaan di tempat lain: sambutan sekali putar lalu maju ke item
        # berikutnya, media jenis layanan mengulang sampai pengunjung
        # memilih. Dipasang sebelum jalan pintas `lanjut` supaya jalur
        # mana pun tidak pernah mewarisi nilai pemakai sebelumnya.
        self._pemutar.setLoops(
            QMediaPlayer.Loops.Infinite if ulang else QMediaPlayer.Loops.Once
        )

        if lanjut and self.berkas_tampil == berkas:
            self._dijeda_sengaja = False
            self._pemutar.play()
            return True

        # setSource ke URL yang sama diabaikan Qt, jadi sumber dikosongkan
        # dulu — stop()/setSource() itu sendiri bisa memancarkan sinyal
        # "selesai" palsu, karena itu diabaikan sampai
        # _timer_izinkan_selesai lewat.
        self._dijeda_sengaja = False
        self._abaikan_selesai_video = True
        self._pemutar.stop()
        self._pemutar.setSource(QUrl())
        self._pemutar.setSource(QUrl.fromLocalFile(str(berkas)))
        self._pemutar.play()
        self._timer_izinkan_selesai.start(200)
        return True

    def _izinkan_selesai_video(self) -> None:
        self._abaikan_selesai_video = False

    def _jeda_video(self) -> None:
        """Jeda putar; berkas tetap terbuka — untuk konfirmasi A/B/C."""
        if self._pemutar is not None:
            self._pemutar.pause()

    def _lepaskan_berkas_video(self) -> None:
        """Tutup sumber video agar file di Windows bisa diganti."""
        if self._pemutar is not None:
            # stop()/setSource(kosong) memancarkan sinyal "selesai" palsu;
            # abaikan supaya tidak memicu pergantian item kedua kalinya.
            self._abaikan_selesai_video = True
            self._pemutar.stop()
            self._pemutar.setSource(QUrl())
            self._timer_izinkan_selesai.start(200)

    def _status_video(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._video_selesai()

    def _keadaan_putar(self, keadaan) -> None:
        from PySide6.QtMultimedia import QMediaPlayer

        if keadaan == QMediaPlayer.PlaybackState.StoppedState:
            self._video_selesai()

    def _video_selesai(self) -> None:
        """
        Jalan cepat opsional saat sinyal Qt memang terpancar. Deteksi
        yang WAJIB benar ada di _jaga_putaran() (detak berkala), bukan
        di sini — sinyal ini absen di banyak mesin Windows.
        """
        if self._abaikan_selesai_video:
            return
        if self._dijeda_sengaja or self._menampilkan_info_layanan or not self._daftar:
            return
        if self.tumpukan.currentIndex() != HALAMAN_VIDEO:
            return
        self._item_berikutnya()

    def _gagal_video(self, _error, pesan: str) -> None:
        """
        Sinyal errorOccurred Qt. setSource(QUrl()) saat melepas/mengganti
        berkas (_lepaskan_berkas_video/_pasang_video) sendiri bisa memicu
        error palsu ("no media"/"immediate exit requested") — tanpa
        penjagaan yang sama seperti _video_selesai(), error basi itu bisa
        muncul BELAKANGAN saat panel sudah pindah ke gambar dan memotong
        durasi tampil gambar sebelum 5 detiknya lewat.
        """
        logger.warning("Pemutar video sambutan gagal: %s", pesan)
        if self._abaikan_selesai_video:
            return
        if self._berkas_layanan is not None:
            # Video jenis layanan yang rusak. Qt baru melaporkannya jauh
            # setelah _tampilkan_item() mengaku berhasil, jadi ini salah
            # satu dari dua tempat kegagalannya dapat ditangkap — yang
            # lain adalah ambang macet di _jaga_ulangan_layanan, untuk
            # berkas yang gagal tanpa memancarkan error sama sekali.
            self._jatuhkan_media_layanan("tidak dapat diputar")
            return
        if self._dijeda_sengaja or self._menampilkan_info_layanan or not self._daftar:
            return
        if self.tumpukan.currentIndex() != HALAMAN_VIDEO:
            return
        if len(self._daftar) > 1:
            self._item_berikutnya()
            return
        self._cadangan_teks()
