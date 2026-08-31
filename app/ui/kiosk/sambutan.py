"""
Panel sambutan anjungan: teks, atau isi folder media/kiosk.

Berkas hidup di mesin anjungan, bukan di database. Pengaturan bersama
hanya menyimpan jenis tampilan; semua gambar dan video di folder
diputar bergiliran menurut nama file, lalu diulang dari awal.
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

EKSTENSI_GAMBAR = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}
EKSTENSI_VIDEO = {".mp4", ".mkv", ".webm", ".avi"}
EKSTENSI_MEDIA = EKSTENSI_GAMBAR | EKSTENSI_VIDEO

DURASI_SLIDE_BAWAAN_DETIK = 10

#: Tebal tepi panel di sekeliling gambar/video, dalam piksel. Naikkan bila
#: ingin bingkainya lebih tebal; 0 membuat media mepet ke tepi panel (dan
#: sudut membulatnya ikut terlihat terpotong).
MARGIN_PANEL = 4


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
    Satu panel: teks, atau putaran berkas di folder media.

    Info jenis layanan (setelah A/B/C disentuh) selalu teks, berapa pun
    jenis sambutannya: video tidak sempat selesai dalam jeda konfirmasi.
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

        # Pudar hanya pada label teks. QVideoWidget adalah jendela native:
        # QGraphicsOpacityEffect pada tumpukan membuat videonya hitam.
        self._efek = QGraphicsOpacityEffect(self.label_teks)
        self.label_teks.setGraphicsEffect(self._efek)

        # muat_pengaturan() dipanggil DisplayPage SETELAH bayangan dipasang
        # pada panel ini. Memuat video di sini, sebelum bayangan ada,
        # lalu bayangan ditambahkan di atasnya, membuat video hitam.

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
    # Info layanan (selalu teks)
    # -----------------------------------------------------------------

    def tampilkan_info(self, teks: str | None) -> None:
        """
        Ganti isi lewat pudar. `None` atau string kosong kembali ke sambutan.
        """
        menuju_sambutan = not (teks or "").strip()
        baru = self.teks_sambutan() if menuju_sambutan else (teks or "").strip()
        if baru == self._teks_tampil and (
            menuju_sambutan == (not self._menampilkan_info_layanan)
        ):
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

    def _setelah_pudar(self, teks: str, menuju_sambutan: bool) -> None:
        if menuju_sambutan:
            self._menampilkan_info_layanan = False
            self._lanjutkan_sambutan()
        else:
            self.label_teks.setText(teks)
            self._tampilkan_halaman(HALAMAN_TEKS)

        self._hentikan_animasi()
        self._animasi = QPropertyAnimation(self._efek, b"opacity", self)
        self._animasi.setDuration(self._durasi_fade_ms)
        self._animasi.setStartValue(0.0)
        self._animasi.setEndValue(1.0)
        self._animasi.start()

    def hentikan(self) -> None:
        self._hentikan_animasi()
        self._dijeda_sengaja = True
        self._jeda_putaran()
        self._lepaskan_berkas_video()

    def ganti_gaya_teks(self, stylesheet: str) -> None:
        self.label_teks.setStyleSheet(stylesheet)

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

    def _tampilkan_item(self, berkas: Path, *, lanjut: bool = False) -> bool:
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
            if not self._pasang_video(berkas, lanjut=lanjut):
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
        """
        if (
            self._menampilkan_info_layanan
            or self._dijeda_sengaja
            or self._sedang_ganti_item
            or not self._daftar
            or not self._jam_item.isValid()
        ):
            return
        halaman = self.tumpukan.currentIndex()
        if halaman == HALAMAN_GAMBAR:
            if self._jam_item.elapsed() >= self._durasi_slide_ms():
                self._item_berikutnya()
            return
        if halaman != HALAMAN_VIDEO or self._pemutar is None:
            return

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
        posisi_macet = self._tick_macet * self._jantung.interval() >= 2_000

        if selesai_posisi or lewat_batas or posisi_macet:
            self._item_berikutnya()

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
            efek.setEnabled(True)
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

    def _pasang_video(self, berkas: Path | None, *, lanjut: bool = False) -> bool:
        if berkas is None or self._pemutar is None:
            return False

        if lanjut and self.berkas_tampil == berkas:
            self._dijeda_sengaja = False
            self._pemutar.play()
            return True

        # Selalu sekali putar. Habis itu detak (_jaga_putaran) atau sinyal
        # Qt memaju ke item berikutnya lewat _video_selesai(). setSource
        # ke URL yang sama diabaikan Qt, jadi sumber dikosongkan dulu —
        # stop()/setSource() itu sendiri bisa memancarkan sinyal "selesai"
        # palsu, karena itu diabaikan sampai _timer_izinkan_selesai lewat.
        self._dijeda_sengaja = False
        self._abaikan_selesai_video = True
        self._pemutar.setLoops(1)
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
        if self._dijeda_sengaja or self._menampilkan_info_layanan or not self._daftar:
            return
        if self.tumpukan.currentIndex() != HALAMAN_VIDEO:
            return
        if len(self._daftar) > 1:
            self._item_berikutnya()
            return
        self._cadangan_teks()
