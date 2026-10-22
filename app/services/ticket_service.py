"""
Tiket antrian.

Aturan terpenting di sini: KEGAGALAN MENCETAK TIDAK BOLEH MEMBATALKAN
ANTRIAN. Nomor sudah terbit dan sudah tersimpan sebelum tiket dicetak.
Bila printer mati, kehabisan kertas, atau belum terpasang, pengunjung tetap
memegang nomor yang sah — petugas cukup menyebutkan nomornya.

Karena itu seluruh fungsi cetak di modul ini mengembalikan hasil, bukan
melempar exception.

Pencetakan dipisahkan ke belakang antarmuka `TicketPrinter` supaya alurnya
dapat diuji tanpa printer fisik.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.core import clock
from app.core.config import get_config
from app.core.identitas import JUDUL_TIKET
from app.core.logger import get_logger
from app.services.queue_service import QueueInfo
from app.utils.formatting import tanggal_panjang

logger = get_logger("ticket")

#: Banyaknya baris catatan kaki yang benar-benar muat di tinggi struk.
#:
#: Diturunkan dari tata letak kedua pencetak: setelah nomor, jenis layanan,
#: loket, tanggal, dan jam, sisa ruangnya hanya cukup untuk dua baris.
#: Baris ketiga jatuh di luar halaman — pada PDF melewati tepi bawah, pada
#: pencetak Qt melewati tinggi kertas — jadi lebih baik dipotong sadar di
#: satu tempat daripada hilang diam-diam di dua tempat.
MAKS_BARIS_FOOTER = 2

#: Jarak aman dari tepi kiri dan kanan kertas. Huruf yang menempel tepi
#: kepala cetak thermal terbaca terpotong walaupun secara hitungan muat.
TEPI_MM = 3

#: Huruf terkecil yang masih dipakai untuk memuatkan baris yang kepanjangan.
#: Di bawah ini tulisan struk thermal 203 DPI sudah sulit dibaca.
UKURAN_HURUF_MIN = 7

#: Jarak antarbaris nama kantor yang dibungkus menjadi dua baris.
JARAK_BARIS_KANTOR_MM = 4.0

#: Ukuran huruf nama kantor. Lebih kecil dari judul instansi supaya
#: "BAPENDA DKI JAKARTA" tetap yang dibaca pertama.
UKURAN_KANTOR = 10

#: Garis dasar baris pertama tiket, diukur dari tepi atas kertas.
#:
#: Ini jarak ke garis dasar huruf, bukan ke puncaknya. Kapital 12 pt
#: setinggi ±3 mm, jadi 3,5 mm adalah batas: puncak judul hampir di tepi
#: halaman. Lebih rapat dari ini memotong "BAPENDA…". Zona kosong di
#: kertas IWare di atas itu tidak tercetak — jangan diisi geseran.
ATAS_MM = 3.5

#: Geser tambahan pencetak Windows asli. Nol dengan sengaja.
#:
#: Percobaan −14 mm menaruh judul di zona kosong kepala kertas IWare
#: — zona itu tidak tercetak, jadi judul hilang. Ruang kosong di atas
#: judul adalah umpan mekanik printer, bukan margin yang bisa diisi.
GESER_PRINTER_MM = 0

#: Jarak antarbaris dari nama layanan sampai catatan kaki. Satu angka
#: supaya ruang kosongnya terasa sama di sepanjang blok itu.
JARAK_BLOK_BAWAH_MM = 5.5


def baris_sisa_antrian(sisa: int | None) -> str:
    """
    Sisa antrian sebagai satu baris siap tampil.

    Disusun di satu tempat lalu dipakai SEMUA yang menyebutkannya: tiket
    PDF, tiket printer sistem, tiket teks, dan kartu nomor di layar
    anjungan. Empat tempat yang menjawab pertanyaan yang sama tidak boleh
    menyebut kalimat yang berbeda.

    Angkanya dihitung lintas seluruh jenis layanan (lihat
    `QueueService.ringkasan_tiket`), jadi kalimatnya sengaja tidak
    menyebut jenis layanan mana pun.

    Kosong berarti barisnya memang tidak ditampilkan — di struk 88 mm
    hanya sepanjang itu ruang yang tersisa setelah nomor, jenis layanan,
    loket, tanggal, jam, dan dua baris catatan kaki.
    """
    if sisa is None:
        return ""
    if sisa <= 0:
        return "Tidak ada sisa antrian"
    return f"Sisa antrian: {sisa}"


def baris_perkiraan_tunggu(detik: float | None) -> str:
    """
    Perkiraan waktu tunggu sebagai satu baris tiket, atau kosong.

    Dibulatkan KE ATAS per 5 menit dan ditulis sebagai rentang: angka
    menit yang tepat terbaca sebagai janji, padahal ini hanya perkiraan
    dari median lama layanan (lihat `QueueService.perkiraan_tunggu`).
    Pengunjung yang dipanggil lebih cepat dari perkiraan tidak kecewa;
    yang menunggu lebih lama dari angka "pasti" merasa dibohongi.

    Kosong bila tidak ada perkiraan, atau tidak ada orang di depan —
    baris "Tidak ada sisa antrian" sudah mengatakannya.
    """
    if detik is None or detik <= 0:
        return ""
    menit = max(5, math.ceil(detik / 60 / 5) * 5)
    if menit > 180:
        return "Perkiraan tunggu: lebih dari 3 jam"
    if menit == 5:
        return "Perkiraan tunggu: ±5 menit"
    return f"Perkiraan tunggu: ±{menit - 5}–{menit} menit"


@dataclass(frozen=True)
class TicketData:
    """Isi satu tiket antrian."""

    queue_number: str
    category_name: str
    office_name: str
    issued_at: datetime
    footer: str = ""
    #: Judul di baris paling atas, di atas nama kantor (mis. nama instansi).
    #: Kosong berarti tiket tanpa judul.
    header: str = ""
    counter_name: str | None = None
    #: Banyaknya nomor yang masih menunggu di depan pemegang tiket, lintas
    #: seluruh jenis layanan. None berarti angkanya tidak berhasil dibaca —
    #: barisnya dihilangkan, bukan dicetak sebagai nol yang menyesatkan.
    sisa_antrian: int | None = None
    #: Perkiraan lama menunggu, dalam detik. None: tidak ada perkiraan
    #: yang jujur, barisnya dihilangkan.
    perkiraan_tunggu_detik: float | None = None
    #: Geseran ke atas pada pencetak Windows asli, dalam milimeter.
    #: 0 berarti tidak digeser. PDF mengabaikannya.
    geser_atas_mm: int = 0
    #: Turunkan isi tiket anjungan Android, dalam milimeter. Tablet mencetak
    #: tanpa driver, jadi tidak mendapat ruang kosong di kepala kertas.
    turun_anjungan_mm: int = 0

    @property
    def tanggal(self) -> str:
        return tanggal_panjang(self.issued_at.date())

    @property
    def jam(self) -> str:
        return f"{self.issued_at:%H:%M}"

    @property
    def tanggal_jam(self) -> str:
        """Tanggal dan jam sebaris, seperti struk: '26 Agustus 2026, 20:07'."""
        return f"{self.tanggal}, {self.jam}"

    def baris_teks(self) -> list[str]:
        """
        Tiket dalam bentuk baris teks polos.

        Dipakai printer teks/thermal sederhana, dan sekaligus membuat isi
        tiket dapat diperiksa test tanpa membuka PDF.
        """
        baris = [self.header] if self.header else []
        baris += [
            self.office_name,
            "",
            "NOMOR ANTRIAN",
            self.queue_number,
            "",
            self.category_name,
        ]
        if self.counter_name:
            baris.append(self.counter_name)
        baris += ["", self.tanggal_jam]
        sisa = self.baris_sisa_antrian()
        if sisa:
            baris += ["", sisa]
        perkiraan = self.baris_perkiraan_tunggu()
        if perkiraan:
            baris.append(perkiraan)
        if self.footer:
            baris += ["", self.footer]
        return baris

    def baris_sisa_antrian(self) -> str:
        """Baris sisa antrian tiket ini. Lihat `baris_sisa_antrian()`."""
        return baris_sisa_antrian(self.sisa_antrian)

    def baris_perkiraan_tunggu(self) -> str:
        """Baris perkiraan tunggu tiket ini. Lihat `baris_perkiraan_tunggu()`."""
        return baris_perkiraan_tunggu(self.perkiraan_tunggu_detik)


@dataclass(frozen=True)
class PrintResult:
    """Hasil percobaan mencetak. Tidak pernah berupa exception."""

    berhasil: bool
    pesan: str = ""
    berkas: Path | None = None

    @property
    def gagal(self) -> bool:
        return not self.berhasil


class TicketPrinter(Protocol):
    """Kontrak pencetak tiket."""

    nama: str

    def cetak(self, data: TicketData) -> PrintResult: ...


# ---------------------------------------------------------------------
# Pencetak
# ---------------------------------------------------------------------


class NullTicketPrinter:
    """
    Tidak mencetak apa pun, tetapi melaporkan keberhasilan.

    Dipakai ketika kantor memang tidak memakai printer tiket: nomor tetap
    diumumkan lisan dan tampil di layar. Riwayat pemanggilannya disimpan
    supaya alurnya tetap dapat diperiksa.
    """

    nama = "Tanpa Printer"

    def __init__(self) -> None:
        self.tercetak: list[TicketData] = []

    def cetak(self, data: TicketData) -> PrintResult:
        self.tercetak.append(data)
        logger.info("Tiket %s tidak dicetak (mode tanpa printer)", data.queue_number)
        return PrintResult(True, "Printer tidak digunakan.")


class GagalTicketPrinter:
    """Selalu gagal. Dipakai test untuk memastikan kegagalan cetak tertangani."""

    nama = "Printer Rusak"

    def __init__(self, pesan: str = "Printer tidak dapat dihubungi.") -> None:
        self.pesan = pesan

    def cetak(self, data: TicketData) -> PrintResult:
        return PrintResult(False, self.pesan)


class PdfTicketPrinter:
    """
    Menyimpan tiket sebagai PDF berukuran struk 80 mm.

    Berguna di dua keadaan: printer thermal yang menerima PDF, dan komputer
    tanpa printer sama sekali — tiketnya tetap dapat dibuka dan dicetak
    belakangan.
    """

    nama = "Berkas PDF"
    LEBAR_MM = 80
    # Tinggi dipas dengan isinya. Kertas struk terpakai setiap pengunjung,
    # jadi ruang kosong di bawah tiket adalah pemborosan harian.
    #
    # Ukurannya TETAP: kertas potong yang dipakai kantor memang setinggi ini.
    # Baris sisa antrian karena itu dimuat dengan merapatkan jarak antarbaris
    # di tengah tiket, bukan dengan menambah tinggi kertas. Menambah satu
    # baris lagi di sini berarti catatan kaki jatuh di luar halaman dan
    # hilang tanpa jejak — lihat MAKS_BARIS_FOOTER.
    TINGGI_MM = 88

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def cetak(self, data: TicketData) -> PrintResult:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            berkas = self.folder / (
                f"tiket_{data.issued_at:%Y%m%d}_{data.queue_number.replace('-', '')}.pdf"
            )
            self._gambar(data, berkas)
        except Exception as exc:  # noqa: BLE001 - kegagalan cetak tidak boleh menyebar
            logger.exception("Gagal membuat berkas tiket %s", data.queue_number)
            return PrintResult(False, f"Tiket tidak dapat dibuat: {exc.__class__.__name__}")

        logger.info("Tiket %s disimpan ke %s", data.queue_number, berkas.name)
        return PrintResult(True, "Tiket tersimpan.", berkas)

    def _gambar(self, data: TicketData, berkas: Path) -> None:
        from reportlab.lib.units import mm
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas

        lebar = self.LEBAR_MM * mm
        tinggi = self.TINGGI_MM * mm
        tengah = lebar / 2
        lebar_isi = lebar - 2 * TEPI_MM * mm

        c = canvas.Canvas(str(berkas), pagesize=(lebar, tinggi))

        def huruf(tebal: bool) -> str:
            return "Helvetica-Bold" if tebal else "Helvetica"

        def pas(isi: str, ukuran: int, tebal: bool, maks_baris: int = 1):
            def muat(teks: str, pt: int) -> bool:
                return stringWidth(teks, huruf(tebal), pt) <= lebar_isi

            return _pas_lebar(isi, muat, ukuran, maks_baris)

        for baris in _tata_letak(data, pas, ukuran_nomor=54):
            if baris.garis:
                c.setStrokeColorRGB(0, 0, 0)
                c.setLineWidth(0.35 * mm)
                y_garis = tinggi - baris.y_mm * mm
                c.line(TEPI_MM * mm, y_garis, lebar - TEPI_MM * mm, y_garis)
                continue
            c.setFont(huruf(baris.tebal), baris.ukuran)
            c.drawCentredString(tengah, tinggi - baris.y_mm * mm, baris.teks)

        c.showPage()
        c.save()


def tata_letak_tiket_anjungan(data: TicketData) -> dict:
    """Susun format raster Android memakai geometri tiket printer Windows."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lebar = 72.0
    # stringWidth mengukur dalam point, bukan mm. Membandingkannya dengan
    # 66 "mm" membuat semua baris dianggap kelebaran hampir tiga kali lipat:
    # judul dan catatan kaki terpotong "…" dan nomor mengecil ke 24 pt.
    lebar_isi = (lebar - 2 * TEPI_MM) * 72 / 25.4

    def pas(isi: str, ukuran: int, tebal: bool, maks_baris: int = 1):
        nama_huruf = "Helvetica-Bold" if tebal else "Helvetica"
        return _pas_lebar(
            isi,
            lambda teks, pt: stringWidth(teks, nama_huruf, pt) <= lebar_isi,
            ukuran,
            maks_baris,
        )

    rows = _tata_letak(data, pas, ukuran_nomor=44)
    # Geseran yang sama dengan raster_tiket_anjungan: tanpa ini tiket dari
    # tata letak cadangan mengabaikan pengaturan "Turunkan isi tiket anjungan".
    geser_mm = max(0, data.turun_anjungan_mm) - max(0, data.geser_atas_mm)
    return {
        "width_mm": lebar,
        "height_mm": PdfTicketPrinter.TINGGI_MM,
        "rows": [
            {
                "y_mm": row.y_mm + geser_mm,
                "text": row.teks,
                "size": row.ukuran,
                "bold": row.tebal,
                "line": row.garis,
            }
            for row in rows
        ],
    }


#: Kepala cetak printer struk 80 mm: 576 titik pada 203 DPI (8 titik/mm).
TITIK_PER_MM_ANJUNGAN = 8.0
LEBAR_TITIK_ANJUNGAN = 576


def _huruf_arial(tebal: bool) -> Path | None:
    """Berkas Arial yang juga dipakai QtTicketPrinter di Windows."""
    import os

    folder = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    calon = [folder / ("arialbd.ttf" if tebal else "arial.ttf")]
    try:
        import reportlab

        # Cadangan di luar Windows (mis. test di Linux): Vera ikut reportlab.
        fonts = Path(reportlab.__file__).parent / "fonts"
        calon.append(fonts / ("VeraBd.ttf" if tebal else "Vera.ttf"))
    except ImportError:
        pass
    return next((path for path in calon if path.is_file()), None)


def raster_tiket_anjungan(data: TicketData) -> dict | None:
    """
    Gambar tiket anjungan Android sebagai bitmap 1-bit siap kirim ke printer.

    Dulu tablet menggambar sendiri dari `tata_letak_tiket_anjungan` dengan
    huruf Roboto dan tepi huruf yang dibuang saat dijadikan hitam-putih,
    tanpa `geser_atas_mm` — hasilnya lebih kecil, lebih tipis, dan lebih
    turun daripada tiket Windows. Di sini tiket digambar seperti
    QtTicketPrinter: Arial, ukuran pt pada 203 DPI, ditengahkan menurut
    lebar huruf sungguhan, tanpa anti-alias, dan diangkat sebesar
    `geser_atas_mm`.

    Mengembalikan None bila Arial atau Pillow tidak tersedia; tablet lalu
    memakai tata letak lama.
    """
    import base64

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None
    berkas_biasa, berkas_tebal = _huruf_arial(False), _huruf_arial(True)
    if berkas_biasa is None or berkas_tebal is None:
        return None

    titik_per_mm = TITIK_PER_MM_ANJUNGAN
    lebar = LEBAR_TITIK_ANJUNGAN
    tinggi = round(PdfTicketPrinter.TINGGI_MM * titik_per_mm)
    lebar_isi = lebar - 2 * TEPI_MM * titik_per_mm
    simpanan: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}

    def huruf(pt: int, tebal: bool) -> ImageFont.FreeTypeFont:
        kunci = (pt, tebal)
        if kunci not in simpanan:
            # Ukuran pt seperti QFont di printer: pt / 72 inci pada 203,2 DPI.
            piksel = round(pt * titik_per_mm * 25.4 / 72)
            simpanan[kunci] = ImageFont.truetype(
                str(berkas_tebal if tebal else berkas_biasa), piksel
            )
        return simpanan[kunci]

    def pas(isi: str, ukuran: int, tebal: bool, maks_baris: int = 1):
        return _pas_lebar(
            isi,
            lambda teks, pt: huruf(pt, tebal).getlength(teks) <= lebar_isi,
            ukuran,
            maks_baris,
        )

    gambar = Image.new("L", (lebar, tinggi), 255)
    pena = ImageDraw.Draw(gambar)
    pena.fontmode = "1"  # tanpa anti-alias: tepi huruf tegas seperti driver
    geser = (max(0, data.geser_atas_mm) - max(0, data.turun_anjungan_mm)) * titik_per_mm
    for baris in _tata_letak(data, pas, ukuran_nomor=44):
        y = baris.y_mm * titik_per_mm - geser
        if baris.garis:
            tebal_garis = max(1, round(0.35 * titik_per_mm))
            tepi = TEPI_MM * titik_per_mm
            pena.line([(tepi, y), (lebar - tepi, y)], fill=0, width=tebal_garis)
            continue
        pena.text(
            (lebar / 2, y), baris.teks, fill=0,
            font=huruf(baris.ukuran, baris.tebal), anchor="ms",
        )

    # ESC/POS GS v 0: bit 1 = titik hitam, bit tertinggi di kiri.
    hitam = gambar.point(lambda v: 255 if v < 128 else 0, mode="1")
    return {
        "width_px": lebar,
        "height_px": tinggi,
        "data": base64.b64encode(hitam.tobytes()).decode("ascii"),
    }


class QtTicketPrinter:
    """
    Mencetak ke printer Windows lewat Qt.

    Import Qt sengaja ditunda sampai benar-benar mencetak, supaya modul ini
    tetap dapat dipakai dan diuji tanpa antarmuka grafis.

    Ukuran halaman dan susunan baris SENGAJA disamakan dengan PdfTicketPrinter
    (80 x 88 mm, urutan baris yang sama) agar tiket terlihat identik apa pun
    cara mencetaknya yang dipilih admin. Satu-satunya pengecualian adalah
    lebar: printer struk yang kertasnya lebih sempit dari 80 mm memakai lebar
    kertasnya sendiri — lihat `_lebar_halaman_mm`.
    """

    nama = "Printer Sistem"

    def __init__(self, nama_printer: str | None = None) -> None:
        self.nama_printer = nama_printer

    def cetak(self, data: TicketData) -> PrintResult:
        try:
            from PySide6.QtGui import QPageSize, QPainter
            from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

            if self.nama_printer:
                # QPrinter.isValid() TIDAK BOLEH dipakai untuk memeriksa nama
                # printer. Nama yang tidak dikenal diam-diam jatuh ke printer
                # default OS dan isValid() tetap mengembalikan True, sehingga
                # kesalahan ketik pada pengaturan printer tidak pernah
                # terdeteksi dan tiket tercetak ke printer yang salah tanpa
                # peringatan apa pun. QPrinterInfo benar-benar memeriksa nama.
                if QPrinterInfo.printerInfo(self.nama_printer).isNull():
                    return PrintResult(
                        False,
                        f"Printer {self.nama_printer!r} tidak ditemukan. "
                        "Nomor antrian tetap tersimpan.",
                    )

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            if self.nama_printer:
                printer.setPrinterName(self.nama_printer)

            if not printer.isValid():
                return PrintResult(
                    False,
                    "Printer tidak tersedia. Nomor antrian tetap tersimpan.",
                )

            # Lebar mengikuti kertas printer bila lebih sempit dari 80 mm —
            # lihat _lebar_halaman_mm. Tingginya tetap 88 mm.
            info = QPrinterInfo(printer)
            lebar_kertas = (
                0.0
                if info.isNull()
                else info.defaultPageSize().size(QPageSize.Unit.Millimeter).width()
            )
            _pasang_halaman_tiket(printer, _lebar_halaman_mm(lebar_kertas))

            painter = QPainter()
            if not painter.begin(printer):
                return PrintResult(
                    False,
                    "Printer tidak dapat dibuka. Nomor antrian tetap tersimpan.",
                )
            try:
                self._gambar(painter, printer, data)
            finally:
                painter.end()
        except Exception as exc:  # noqa: BLE001 - kegagalan cetak tidak boleh menyebar
            logger.exception("Gagal mencetak tiket %s", data.queue_number)
            return PrintResult(
                False,
                f"Tiket gagal dicetak ({exc.__class__.__name__}). "
                "Nomor antrian tetap tersimpan.",
            )

        logger.info("Tiket %s dicetak", data.queue_number)
        return PrintResult(True, "Tiket dicetak.")

    @staticmethod
    def _gambar(painter, printer, data: TicketData) -> None:
        """
        Gambar isi tiket dalam satuan milimeter, bukan piksel tetap.

        WAJIB dihitung dari printer.resolution() (DPI printer sesungguhnya).
        Mode HighResolution dapat memakai DPI native printer yang jauh lebih
        tinggi dari layar (ratusan hingga ribuan DPI); offset piksel tetap
        yang masuk akal di 96 DPI akan membuat seluruh baris bertumpuk hanya
        dalam beberapa milimeter pertama pada DPI setinggi itu.
        """
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor, QFont, QPen
        from PySide6.QtPrintSupport import QPrinter

        titik_per_mm = printer.resolution() / 25.4
        # paperRect, bukan pageRect: bila driver Windows masih menyisakan
        # margin, pageRect sudah bergeser ke bawah dan menggambar dari situ
        # justru menambah ruang kosong di atas judul. Asal kertas adalah
        # tepi fisik, lalu digeser lagi oleh _geser_atas_printer_px.
        kertas = printer.paperRect(QPrinter.Unit.DevicePixel)
        lebar = kertas.width()
        lebar_isi = lebar - 2 * TEPI_MM * titik_per_mm
        painter.setClipping(False)
        geser_px = _geser_atas_printer_px(
            printer, titik_per_mm, data.geser_atas_mm
        )

        def huruf(ukuran: int, tebal: bool) -> QFont:
            return QFont(
                "Arial",
                ukuran,
                QFont.Weight.Bold if tebal else QFont.Weight.Normal,
            )

        def lebar_teks(isi: str, ukuran: int, tebal: bool) -> int:
            # Diukur lewat painter yang juga menggambarnya, supaya ukuran
            # "muat" dan posisi tengahnya dihitung dengan metrik yang sama.
            painter.setFont(huruf(ukuran, tebal))
            return painter.fontMetrics().horizontalAdvance(isi)

        def pas(isi: str, ukuran: int, tebal: bool, maks_baris: int = 1):
            def muat(teks: str, pt: int) -> bool:
                return lebar_teks(teks, pt, tebal) <= lebar_isi

            return _pas_lebar(isi, muat, ukuran, maks_baris)

        def tulis(mm: float, isi: str, ukuran: int, tebal: bool) -> None:
            lebar_isi_teks = lebar_teks(isi, ukuran, tebal)
            painter.drawText(
                int(kertas.left() + (lebar - lebar_isi_teks) / 2),
                int(kertas.top() + mm * titik_per_mm) + geser_px,
                isi,
            )

        def garis(mm: float) -> None:
            y = kertas.top() + mm * titik_per_mm + geser_px
            x1 = kertas.left() + TEPI_MM * titik_per_mm
            x2 = kertas.left() + lebar - TEPI_MM * titik_per_mm
            painter.setPen(QPen(QColor(0, 0, 0), max(1, round(0.35 * titik_per_mm))))
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))

        for baris in _tata_letak(data, pas, ukuran_nomor=44):
            if baris.garis:
                garis(baris.y_mm)
                continue
            tulis(baris.y_mm, baris.teks, baris.ukuran, baris.tebal)


def _bungkus(teks: str, lebar: int, maks_baris: int = MAKS_BARIS_FOOTER) -> list[str]:
    """
    Pecah teks menjadi beberapa baris agar muat di lebar struk.

    Dipotong pada `maks_baris` karena tinggi struk tetap: baris berikutnya
    tidak akan tercetak di kertas, melainkan jatuh di luar halaman tanpa
    jejak apa pun. Lebih baik terlihat terpotong dengan "…" daripada
    hilang diam-diam — yang menulis catatan kaki itu perlu tahu bahwa
    tulisannya kepanjangan.
    """
    kata = teks.split()
    baris: list[str] = []
    sekarang = ""
    for k in kata:
        calon = f"{sekarang} {k}".strip()
        if len(calon) <= lebar:
            sekarang = calon
        else:
            if sekarang:
                baris.append(sekarang)
            sekarang = k
    if sekarang:
        baris.append(sekarang)

    if len(baris) > maks_baris:
        baris = baris[:maks_baris]
        baris[-1] = baris[-1][: lebar - 1].rstrip() + "…"
    return baris


def _bungkus_ukur(teks: str, muat: Callable[[str, int], bool], ukuran: int) -> list[str]:
    """Bungkus per kata menurut lebar huruf sungguhan, bukan jumlah karakter."""
    baris: list[str] = []
    sekarang = ""
    for k in teks.split():
        calon = f"{sekarang} {k}".strip()
        if not sekarang or muat(calon, ukuran):
            sekarang = calon
        else:
            baris.append(sekarang)
            sekarang = k
    if sekarang:
        baris.append(sekarang)
    return baris or [""]


def _pas_lebar(
    teks: str,
    muat: Callable[[str, int], bool],
    ukuran: int,
    maks_baris: int = 1,
) -> tuple[list[str], int]:
    """
    Susun teks agar muat di lebar struk; kembalikan baris dan ukuran hurufnya.

    Dibungkus per kata sampai `maks_baris`, lalu hurufnya dikecilkan satu
    poin demi satu poin bila masih kelebaran. Lebarnya diukur dengan huruf
    sungguhan lewat `muat`, bukan jumlah karakter: "UNIT PELAYANAN
    PEMUNGUTAN PAJAK DAERAH" hanya 38 karakter tetapi selebar ±95 mm pada
    11 pt tebal, dan potongan [:34] yang dulu dipakai pun masih ±84 mm —
    tetap keluar dari kertas 72 mm.

    Bila pada UKURAN_HURUF_MIN pun masih kelebaran, baris dipotong dengan
    "…" — sama seperti `_bungkus`, lebih baik terlihat terpotong daripada
    hilang diam-diam di luar tepi kertas.
    """
    for pt in range(ukuran, UKURAN_HURUF_MIN - 1, -1):
        baris = _bungkus_ukur(teks, muat, pt)
        if len(baris) <= maks_baris and all(muat(b, pt) for b in baris):
            return baris, pt

    pt = min(ukuran, UKURAN_HURUF_MIN)
    baris = _bungkus_ukur(teks, muat, pt)
    hasil: list[str] = []
    for i, b in enumerate(baris[:maks_baris]):
        terakhir = i == maks_baris - 1
        if muat(b, pt) and not (terakhir and len(baris) > maks_baris):
            hasil.append(b)
            continue
        while b and not muat(f"{b}…", pt):
            b = b[:-1]
        hasil.append(f"{b.rstrip()}…")
    return hasil, pt


def _lebar_halaman_mm(lebar_kertas_printer_mm: float) -> float:
    """
    Lebar halaman tiket untuk printer yang lebar kertasnya diketahui.

    Printer struk "80 mm" hanya mencetak 72 mm: kepala cetaknya 576 titik
    pada 203 DPI, dan drivernya (mis. POS80 untuk IWare IW-J200 II) memang
    melaporkan kertas 72 mm. Halaman 80 mm yang dipaksakan membuat isi tiket
    berpusat di 40 mm padahal pusat kepala cetak di 36 mm — seluruh tiket
    bergeser 4 mm ke kanan dan 8 mm terakhirnya terpotong.

    Printer biasa (A4, Letter) dan printer yang lebarnya tidak diketahui
    tetap memakai 80 mm, sama dengan tiket PDF.
    """
    if lebar_kertas_printer_mm <= 0:
        return PdfTicketPrinter.LEBAR_MM
    return min(PdfTicketPrinter.LEBAR_MM, lebar_kertas_printer_mm)


def _pasang_halaman_tiket(printer, lebar_mm: float) -> None:
    """
    Halaman struk tanpa margin, setinggi tiket PDF.

    Driver Windows (termasuk POS80) sering memakai margin bawaan ±6 mm
    meski offset di properti printer sudah 0. `setFullPage(True)` di Qt 6
    bersifat usang dan pada sebagian driver tidak meniadakan margin itu —
    akibatnya judul turun dan catatan kaki mepet ke tepi potong. Tata letak
    halaman penuh dengan margin 0 mm adalah cara Qt 6 yang menggantikannya.
    """
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize

    tata = QPageLayout(
        QPageSize(
            QSizeF(lebar_mm, PdfTicketPrinter.TINGGI_MM),
            QPageSize.Unit.Millimeter,
        ),
        QPageLayout.Orientation.Portrait,
        QMarginsF(0, 0, 0, 0),
        QPageLayout.Unit.Millimeter,
    )
    tata.setMode(QPageLayout.Mode.FullPageMode)
    printer.setPageLayout(tata)


def _offset_fisik_gdi(printer) -> tuple[int, int]:
    """
    Jarak GDI dari tepi kertas ke area cetak, dalam piksel perangkat.

    Windows menaruh titik (0, 0) di sudut area yang bisa dicetak, bukan di
    sudut kertas. PHYSICALOFFSETY adalah zona kosong di atas judul bila Qt
    tidak menggeser paperRect ke negatif.

    QPrinter PySide6 tidak punya handle(); kegagalan di sini tidak boleh
    membatalkan cetak. Tanpa HDC, geseran tetap memakai GESER_PRINTER_MM.
    """
    if sys.platform != "win32":
        return (0, 0)
    ambil = getattr(printer, "handle", None)
    if not callable(ambil):
        return (0, 0)
    try:
        hdc = int(ambil())
    except (TypeError, ValueError, AttributeError):
        return (0, 0)
    if not hdc:
        return (0, 0)

    try:
        import ctypes

        # winuser.h: PHYSICALOFFSETX = 112, PHYSICALOFFSETY = 113
        gdi32 = ctypes.windll.gdi32
        return (
            int(gdi32.GetDeviceCaps(hdc, 112)),
            int(gdi32.GetDeviceCaps(hdc, 113)),
        )
    except (AttributeError, OSError, ValueError):
        return (0, 0)


def _geser_atas_printer_px(printer, titik_per_mm: float, geser_mm: int = 0) -> int:
    """
    Geseran tegak ke atas untuk pencetak Windows asli, dalam piksel.

    Nol pada PDF. Nilai positif `geser_mm` mengangkat isi tiket; terlalu
    besar menaruh judul di zona umpan IWare yang tidak tercetak.
    """
    from PySide6.QtPrintSupport import QPrinter

    if printer.outputFormat() != QPrinter.OutputFormat.NativeFormat:
        return 0
    if geser_mm <= 0:
        return 0
    return int(round(-geser_mm * titik_per_mm))


@dataclass(frozen=True)
class _Baris:
    """Satu baris tiket yang sudah dipaskan lebarnya, siap digambar."""

    #: Garis dasar baris, atau posisi garis mendatar, dari tepi atas kertas.
    y_mm: float
    teks: str = ""
    ukuran: int = 0
    tebal: bool = False
    #: True: gambar garis mendatar di y_mm, bukan teks.
    garis: bool = False


def _tata_letak(
    data: TicketData,
    pas: Callable[[str, int, bool, int], tuple[list[str], int]],
    ukuran_nomor: int,
) -> list[_Baris]:
    """
    Susunan tegak tiket, dari atas ke bawah, untuk kedua pencetak.

    Satu-satunya tempat jarak antarbaris ditentukan. Dulu PdfTicketPrinter
    dan QtTicketPrinter masing-masing menulis angkanya sendiri dan harus
    diubah berbarengan; sekarang keduanya hanya menggambar hasil susunan
    ini dengan huruf dan pengukur lebarnya masing-masing (`pas`).

    Tinggi kertas tetap 88 mm, jadi tiket terpanjang — judul, nama kantor
    dua baris, loket, sisa antrian, dan catatan kaki dua baris — harus muat
    dengan ruang sisa di bawah. IWare menambah zona kosong di kepala kertas
    yang tidak bisa diisi (judul hilang bila digeser ke sana), jadi ruang
    di tepi potong bawah didapat dengan merapatkan jarak di tengah tiket,
    bukan dengan mengangkat judul. Ada test yang mengukurnya.
    """
    hasil: list[_Baris] = []

    def satu(y: float, teks: str, ukuran: int, tebal: bool) -> None:
        baris, pt = pas(teks, ukuran, tebal, 1)
        hasil.append(_Baris(y, baris[0], pt, tebal))

    y = ATAS_MM
    if data.header:
        satu(y, data.header, 12, True)
        y += 1.8
        hasil.append(_Baris(y, garis=True))
        y += 3.2

    kantor, pt = pas(data.office_name, UKURAN_KANTOR, True, 2)
    for i, baris in enumerate(kantor):
        if i:
            y += JARAK_BARIS_KANTOR_MM
        hasil.append(_Baris(y, baris, pt, True))
    y += 4

    satu(y, "NOMOR ANTRIAN", 9, False)
    y += 17

    # Nomor dibuat sebesar mungkin: inilah satu-satunya bagian tiket
    # yang benar-benar dibaca pengunjung.
    satu(y, data.queue_number, ukuran_nomor, True)
    y += 7.5

    satu(y, data.category_name, 14, True)
    y += JARAK_BLOK_BAWAH_MM

    if data.counter_name:
        satu(y, data.counter_name, 11, False)
        y += JARAK_BLOK_BAWAH_MM

    satu(y, data.tanggal_jam, 10, False)
    y += JARAK_BLOK_BAWAH_MM

    sisa = data.baris_sisa_antrian()
    perkiraan = data.baris_perkiraan_tunggu()
    if sisa:
        satu(y, sisa, 12, True)
        y += JARAK_BLOK_BAWAH_MM
        if perkiraan:
            # Tepat di bawah sisa antrian, lebih kecil: keduanya menjawab
            # "berapa lama lagi", dan sisa antrian adalah angka pastinya.
            satu(y - 0.5, perkiraan, 10, False)
            y += JARAK_BLOK_BAWAH_MM - 0.5
    elif perkiraan:
        # Tiket anjungan Android sengaja tanpa sisa antrian (lihat
        # kiosk_api), tetapi perkiraan tetap dicetak — justru di sanalah
        # sebagian besar tiket terbit. Mengambil tempat baris sisa.
        satu(y, perkiraan, 11, True)
        y += JARAK_BLOK_BAWAH_MM
    else:
        y += JARAK_BLOK_BAWAH_MM

    if data.footer:
        for potongan in _bungkus(data.footer, 38):
            satu(y, potongan, 9, False)
            y += 4.5
    return hasil


# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------


class TicketService:
    """Menyusun dan mencetak tiket antrian."""

    def __init__(self, printer: TicketPrinter, settings, master, queue=None) -> None:
        self.printer = printer
        self.settings = settings
        self.master = master
        # Boleh None: tiket tetap tercetak, hanya tanpa blok ringkasan
        # antrian. Yang tidak boleh terjadi adalah pembacaan tambahan ini
        # menghalangi tercetaknya nomor.
        self.queue = queue

    def susun(self, antrian: QueueInfo) -> TicketData:
        """Susun isi tiket dari sebuah antrian."""
        cabang = self.master.list_branches()
        nama_kantor = cabang[0].name if cabang else "Kantor Pelayanan"
        ringkasan = self._ringkasan(antrian)

        return TicketData(
            queue_number=antrian.queue_number,
            # Nomor prioritas ditandai pada baris layanan supaya terbaca
            # petugas dan pengunjung tanpa mengubah tata letak tiket.
            category_name=antrian.category_name
            + (" · Prioritas" if antrian.prioritas else ""),
            office_name=nama_kantor,
            issued_at=antrian.created_at or clock.now(),
            footer=self.settings.get("ticket.footer", ""),
            header=JUDUL_TIKET,
            counter_name=antrian.counter_name,
            sisa_antrian=ringkasan.sisa_antrian if ringkasan else None,
            perkiraan_tunggu_detik=self._perkiraan(antrian),
            geser_atas_mm=self.settings.get_int("ticket.geser_atas_mm", 0),
            turun_anjungan_mm=self.settings.get_int("ticket.turun_anjungan_mm", 4),
        )

    def _ringkasan(self, antrian: QueueInfo):
        """
        Keadaan antrian saat ini, atau None bila tidak dapat dibaca.

        Kegagalannya sengaja ditelan. Angka sisa antrian adalah tambahan
        yang menyenangkan, sedangkan nomor antriannya adalah alasan
        pengunjung berdiri di depan mesin — database yang sedang tersendat
        tidak boleh menahan tiketnya hanya karena hitungan ini gagal.
        """
        if self.queue is None:
            return None
        try:
            return self.queue.ringkasan_tiket(antrian)
        except Exception:  # noqa: BLE001 - ringkasan tidak boleh menahan tiket
            logger.warning(
                "Sisa antrian untuk tiket %s tidak terbaca; tiket dicetak tanpa baris itu",
                antrian.queue_number,
                exc_info=True,
            )
            return None

    def _perkiraan(self, antrian: QueueInfo) -> float | None:
        """
        Perkiraan waktu tunggu, atau None bila mati atau tidak terbaca.

        Ditelan seperti `_ringkasan`, dan dibaca terpisah darinya: gagalnya
        perkiraan tidak boleh ikut menghapus baris sisa antrian.
        """
        # Tiket contoh (Uji cetak di tablet) bukan antrian sungguhan.
        if getattr(antrian, "id", None) is None:
            return None
        if self.queue is None or not self.settings.get_bool(
            "ticket.perkiraan_tunggu", True
        ):
            return None
        try:
            return self.queue.perkiraan_tunggu(antrian)
        except Exception:  # noqa: BLE001 - perkiraan tidak boleh menahan tiket
            logger.warning(
                "Perkiraan tunggu untuk tiket %s tidak terbaca; tiket dicetak tanpa baris itu",
                antrian.queue_number,
                exc_info=True,
            )
            return None

    def cetak(self, antrian: QueueInfo) -> PrintResult:
        """
        Cetak tiket untuk sebuah antrian.

        Tidak pernah melempar exception. Kegagalan printer dilaporkan
        sebagai hasil, karena antriannya sendiri sudah sah dan tersimpan.
        """
        try:
            data = self.susun(antrian)
        except Exception as exc:  # noqa: BLE001 - batas terluar pencetakan
            logger.exception("Gagal menyusun tiket %s", antrian.queue_number)
            return PrintResult(
                False,
                f"Tiket tidak dapat disusun ({exc.__class__.__name__}). "
                "Nomor antrian tetap tersimpan.",
            )

        return self.printer.cetak(data)


def mode_pencetak(settings) -> str:
    """
    Cara MESIN INI mencetak tiket.

    Pencetak tiket menempel pada satu komputer — anjungan ambil nomor, atau
    meja pendaftaran — sedangkan `ticket.printer` di database berlaku untuk
    seluruh sistem. Tanpa ANTRIAN_PRINTER pada mesin yang bersangkutan,
    menyalakan "Cetak ke printer Windows" untuk anjungan membuat kelima
    komputer loket ikut mencoba mencetak ke pencetak yang tidak ada padanya.
    """
    return get_config().printer or settings.get("ticket.printer", "pdf")


def buat_printer(mode: str, folder: Path) -> TicketPrinter:
    """
    Pilih pencetak sesuai pengaturan `ticket.printer`.

    Mode yang tidak dikenal diperlakukan sebagai "pdf", bukan digagalkan:
    salah ketik pada pengaturan tidak boleh membuat tiket berhenti terbit.
    """
    bersih = (mode or "").strip().lower()
    if bersih == "none":
        return NullTicketPrinter()
    if bersih == "system":
        return QtTicketPrinter()
    if bersih != "pdf":
        logger.warning("Mode printer %r tidak dikenal, memakai PDF", mode)
    return PdfTicketPrinter(folder)
