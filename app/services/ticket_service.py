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

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.core import clock
from app.core.config import get_config
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


@dataclass(frozen=True)
class TicketData:
    """Isi satu tiket antrian."""

    queue_number: str
    category_name: str
    office_name: str
    issued_at: datetime
    footer: str = ""
    counter_name: str | None = None
    #: Banyaknya nomor yang masih menunggu di depan pemegang tiket, lintas
    #: seluruh jenis layanan. None berarti angkanya tidak berhasil dibaca —
    #: barisnya dihilangkan, bukan dicetak sebagai nol yang menyesatkan.
    sisa_antrian: int | None = None

    @property
    def tanggal(self) -> str:
        return tanggal_panjang(self.issued_at.date())

    @property
    def jam(self) -> str:
        return f"{self.issued_at:%H:%M}"

    def baris_teks(self) -> list[str]:
        """
        Tiket dalam bentuk baris teks polos.

        Dipakai printer teks/thermal sederhana, dan sekaligus membuat isi
        tiket dapat diperiksa test tanpa membuka PDF.
        """
        baris = [
            self.office_name,
            "",
            "NOMOR ANTRIAN",
            self.queue_number,
            "",
            self.category_name,
        ]
        if self.counter_name:
            baris.append(self.counter_name)
        baris += ["", self.tanggal, self.jam]
        sisa = self.baris_sisa_antrian()
        if sisa:
            baris += ["", sisa]
        if self.footer:
            baris += ["", self.footer]
        return baris

    def baris_sisa_antrian(self) -> str:
        """Baris sisa antrian tiket ini. Lihat `baris_sisa_antrian()`."""
        return baris_sisa_antrian(self.sisa_antrian)


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
        from reportlab.pdfgen import canvas

        lebar = self.LEBAR_MM * mm
        tinggi = self.TINGGI_MM * mm
        tengah = lebar / 2

        c = canvas.Canvas(str(berkas), pagesize=(lebar, tinggi))
        y = tinggi - 12 * mm

        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(tengah, y, data.office_name[:34])
        y -= 8 * mm

        c.setFont("Helvetica", 9)
        c.drawCentredString(tengah, y, "NOMOR ANTRIAN")
        y -= 18 * mm

        # Nomor dibuat sebesar mungkin: inilah satu-satunya bagian tiket
        # yang benar-benar dibaca pengunjung.
        c.setFont("Helvetica-Bold", 54)
        c.drawCentredString(tengah, y, data.queue_number)
        y -= 13 * mm

        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(tengah, y, data.category_name[:28])
        y -= 6 * mm

        if data.counter_name:
            c.setFont("Helvetica", 11)
            c.drawCentredString(tengah, y, data.counter_name)
            y -= 6 * mm

        c.setFont("Helvetica", 10)
        c.drawCentredString(tengah, y, data.tanggal)
        y -= 5 * mm
        c.drawCentredString(tengah, y, data.jam)
        y -= 7 * mm

        sisa = data.baris_sisa_antrian()
        if sisa:
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(tengah, y, sisa)
            y -= 6 * mm
        else:
            y -= 3 * mm

        if data.footer:
            c.setFont("Helvetica", 9)
            for potongan in _bungkus(data.footer, 38):
                c.drawCentredString(tengah, y, potongan)
                y -= 4.5 * mm

        c.showPage()
        c.save()


class QtTicketPrinter:
    """
    Mencetak ke printer Windows lewat Qt.

    Import Qt sengaja ditunda sampai benar-benar mencetak, supaya modul ini
    tetap dapat dipakai dan diuji tanpa antarmuka grafis.

    Ukuran halaman dan susunan baris SENGAJA disamakan dengan PdfTicketPrinter
    (80 x 88 mm, urutan baris yang sama) agar tiket terlihat identik apa pun
    cara mencetaknya yang dipilih admin.
    """

    nama = "Printer Sistem"

    def __init__(self, nama_printer: str | None = None) -> None:
        self.nama_printer = nama_printer

    def cetak(self, data: TicketData) -> PrintResult:
        try:
            from PySide6.QtCore import QSizeF
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

            printer.setPageSize(
                QPageSize(
                    QSizeF(PdfTicketPrinter.LEBAR_MM, PdfTicketPrinter.TINGGI_MM),
                    QPageSize.Unit.Millimeter,
                )
            )
            printer.setFullPage(True)

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
        from PySide6.QtGui import QFont
        from PySide6.QtPrintSupport import QPrinter

        titik_per_mm = printer.resolution() / 25.4
        lebar = printer.pageRect(QPrinter.Unit.DevicePixel).width()

        def teks_tengah(mm: float, isi: str, ukuran: int, tebal: bool) -> None:
            painter.setFont(
                QFont(
                    "Arial",
                    ukuran,
                    QFont.Weight.Bold if tebal else QFont.Weight.Normal,
                )
            )
            lebar_teks = painter.fontMetrics().horizontalAdvance(isi)
            painter.drawText(int((lebar - lebar_teks) / 2), int(mm * titik_per_mm), isi)

        teks_tengah(12, data.office_name[:34], 11, True)
        teks_tengah(20, "NOMOR ANTRIAN", 9, False)
        teks_tengah(38, data.queue_number, 44, True)
        teks_tengah(51, data.category_name[:28], 14, True)

        y = 57.0
        if data.counter_name:
            teks_tengah(y, data.counter_name, 11, False)
            y += 6

        teks_tengah(y, data.tanggal, 10, False)
        teks_tengah(y + 5, data.jam, 10, False)
        y += 12

        sisa = data.baris_sisa_antrian()
        if sisa:
            teks_tengah(y, sisa, 12, True)
            y += 6
        else:
            y += 3

        if data.footer:
            for potongan in _bungkus(data.footer, 38):
                teks_tengah(y, potongan, 9, False)
                y += 4.5


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
            category_name=antrian.category_name,
            office_name=nama_kantor,
            issued_at=antrian.created_at or clock.now(),
            footer=self.settings.get("ticket.footer", ""),
            counter_name=antrian.counter_name,
            sisa_antrian=ringkasan.sisa_antrian if ringkasan else None,
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
