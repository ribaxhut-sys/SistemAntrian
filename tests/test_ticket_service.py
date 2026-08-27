"""
Test tiket antrian.

Aturan yang paling penting diuji di sini: kegagalan mencetak tidak boleh
membatalkan antrian dan tidak boleh melempar exception.
"""

from __future__ import annotations


import pytest

from app.core.database import session_scope
from app.models import Queue, QueueStatus
from app.services.ticket_service import (
    GagalTicketPrinter,
    NullTicketPrinter,
    PdfTicketPrinter,
    QtTicketPrinter,
    TicketData,
    TicketService,
    buat_printer,
)


# ---------------------------------------------------------------------
# Isi tiket
# ---------------------------------------------------------------------

def test_tiket_memuat_keterangan_yang_dibutuhkan(ticket_pdf, reg_queue, antrian_siap):
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])
    tiket = ticket_pdf.susun(nomor)

    assert tiket.queue_number == "A-001"
    assert tiket.category_name == "Konsultasi"
    assert tiket.office_name == "Kantor Pelayanan"
    assert tiket.footer == "Silakan menunggu hingga nomor Anda dipanggil."


def test_tanggal_tiket_berbahasa_indonesia(ticket_pdf, reg_queue, antrian_siap):
    from app.utils.formatting import BULAN

    tiket = ticket_pdf.susun(reg_queue.create_queue(antrian_siap["kategori"]["A"]))

    assert any(bulan in tiket.tanggal for bulan in BULAN)
    assert ":" in tiket.jam


def test_baris_teks_tiket_memuat_nomor_paling_menonjol():
    """Baris keempat adalah nomor; printer teks mengandalkan urutan ini."""
    from datetime import datetime

    tiket = TicketData(
        queue_number="A-023",
        category_name="Konsultasi",
        office_name="Kantor Pelayanan",
        issued_at=datetime(2026, 8, 26, 20, 7),
        footer="Silakan menunggu.",
    )
    baris = tiket.baris_teks()

    assert baris[0] == "Kantor Pelayanan"
    assert baris[2] == "NOMOR ANTRIAN"
    assert baris[3] == "A-023"
    assert "26 Agustus 2026" in baris
    assert "Silakan menunggu." in baris


def test_tiket_tidak_memuat_data_pribadi(ticket_pdf, reg_queue, antrian_siap):
    """Antrian anonim: tidak ada nama, NIK, maupun nomor telepon."""
    tiket = ticket_pdf.susun(reg_queue.create_queue(antrian_siap["kategori"]["A"]))
    isi = " ".join(tiket.baris_teks()).lower()

    for kata in ("nik", "telepon", "hp", "alamat", "nama pengunjung"):
        assert kata not in isi


# ---------------------------------------------------------------------
# Pencetakan ke PDF
# ---------------------------------------------------------------------

def test_tiket_pdf_benar_benar_terbentuk(ticket_pdf, reg_queue, antrian_siap):
    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])
    hasil = ticket_pdf.cetak(nomor)

    assert hasil.berhasil
    assert hasil.berkas is not None
    assert hasil.berkas.exists()
    assert hasil.berkas.read_bytes().startswith(b"%PDF")


def test_nama_berkas_tiket_memuat_nomor_dan_tanggal(ticket_pdf, reg_queue, antrian_siap):
    hasil = ticket_pdf.cetak(reg_queue.create_queue(antrian_siap["kategori"]["B"]))

    assert "B001" in hasil.berkas.name
    assert hasil.berkas.suffix == ".pdf"


def test_folder_tiket_dibuat_bila_belum_ada(tmp_path, reg_queue, antrian_siap, auth):
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService

    folder = tmp_path / "belum" / "ada"
    assert not folder.exists()

    service = TicketService(
        PdfTicketPrinter(folder), SettingsService(auth), MasterDataService(auth)
    )
    assert service.cetak(reg_queue.create_queue(antrian_siap["kategori"]["A"])).berhasil
    assert folder.is_dir()


# ---------------------------------------------------------------------
# Kegagalan cetak
# ---------------------------------------------------------------------

def test_kegagalan_cetak_tidak_membatalkan_antrian(reg_queue, antrian_siap, auth):
    """
    Aturan mutlak: printer mati tidak boleh menghapus nomor yang sudah
    terbit. Pengunjung tetap memegang nomor yang sah.
    """
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService

    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])
    service = TicketService(
        GagalTicketPrinter(), SettingsService(auth), MasterDataService(auth)
    )

    hasil = service.cetak(nomor)
    assert hasil.gagal

    with session_scope() as s:
        tersimpan = s.get(Queue, nomor.id)
        assert tersimpan is not None
        assert tersimpan.queue_number == "A-001"
        assert tersimpan.status is QueueStatus.WAITING


def test_kegagalan_cetak_tidak_melempar_exception(reg_queue, antrian_siap, auth):
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService

    nomor = reg_queue.create_queue(antrian_siap["kategori"]["A"])
    service = TicketService(
        GagalTicketPrinter("Kertas habis."),
        SettingsService(auth),
        MasterDataService(auth),
    )

    hasil = service.cetak(nomor)  # tidak boleh raise
    assert hasil.gagal
    assert hasil.pesan == "Kertas habis."


def test_folder_tiket_tidak_dapat_ditulisi_dilaporkan_bukan_dilempar(
    reg_queue, antrian_siap, auth, tmp_path
):
    """Folder tiket yang ternyata sebuah berkas tidak boleh meruntuhkan aplikasi."""
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService

    penghalang = tmp_path / "bukan-folder"
    penghalang.write_text("saya berkas, bukan folder", encoding="utf-8")

    service = TicketService(
        PdfTicketPrinter(penghalang), SettingsService(auth), MasterDataService(auth)
    )
    hasil = service.cetak(reg_queue.create_queue(antrian_siap["kategori"]["A"]))

    assert hasil.gagal
    assert hasil.pesan


def test_pesan_kegagalan_menenangkan_bukan_teknis(reg_queue, antrian_siap, auth):
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService

    service = TicketService(
        QtTicketPrinter("printer-yang-tidak-ada"),
        SettingsService(auth),
        MasterDataService(auth),
    )
    hasil = service.cetak(reg_queue.create_queue(antrian_siap["kategori"]["A"]))

    if hasil.gagal:
        assert "tetap tersimpan" in hasil.pesan
        assert "Traceback" not in hasil.pesan


# ---------------------------------------------------------------------
# Mode tanpa printer
# ---------------------------------------------------------------------

def test_mode_tanpa_printer_dianggap_berhasil(reg_queue, antrian_siap, auth):
    """Kantor yang memang tidak memakai tiket cetak tidak boleh melihat error."""
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService

    printer = NullTicketPrinter()
    service = TicketService(printer, SettingsService(auth), MasterDataService(auth))

    hasil = service.cetak(reg_queue.create_queue(antrian_siap["kategori"]["A"]))
    assert hasil.berhasil
    assert printer.tercetak[0].queue_number == "A-001"


# ---------------------------------------------------------------------
# Pemilihan pencetak
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("mode", "kelas"),
    [
        ("pdf", PdfTicketPrinter),
        ("PDF", PdfTicketPrinter),
        ("none", NullTicketPrinter),
        ("system", QtTicketPrinter),
    ],
)
def test_pemilihan_pencetak(tmp_path, mode, kelas):
    assert isinstance(buat_printer(mode, tmp_path), kelas)


@pytest.mark.parametrize("ngawur", ["", "  ", "thermal", "epson"])
def test_mode_printer_tidak_dikenal_jatuh_ke_pdf(tmp_path, ngawur):
    """Salah ketik pada pengaturan tidak boleh membuat tiket berhenti terbit."""
    assert isinstance(buat_printer(ngawur, tmp_path), PdfTicketPrinter)


# ---------------------------------------------------------------------
# QtTicketPrinter — jalur nyata lewat pipeline Qt
# ---------------------------------------------------------------------
#
# Test di bawah memakai QPrinter/QPainter Qt yang sesungguhnya (bukan mock),
# dialihkan ke berkas alih-alih spooler, supaya benar-benar menembus kode
# yang sama dipakai saat mencetak ke printer fisik tanpa memicu dialog
# interaktif "Simpan Sebagai" pada printer virtual seperti
# "Microsoft Print to PDF".

@pytest.fixture
def qt_available(qapp):
    """QtTicketPrinter butuh QApplication; qapp dari pytest-qt menyediakannya."""
    return qapp


def test_nama_printer_yang_tidak_ada_ditolak(qt_available):
    """
    Regresi: QPrinter.isValid() diam-diam jatuh ke printer default OS untuk
    nama yang tidak dikenal, sehingga kesalahan ketik pada pengaturan
    printer tidak pernah terdeteksi dan tiket tercetak ke printer yang salah
    tanpa peringatan apa pun.
    """
    from datetime import datetime

    printer = QtTicketPrinter("Printer-Yang-Tidak-Pernah-Ada-XYZ")
    hasil = printer.cetak(
        TicketData(
            queue_number="A-001",
            category_name="Konsultasi",
            office_name="Kantor Pelayanan",
            issued_at=datetime.now(),
        )
    )

    assert hasil.gagal
    assert "tidak ditemukan" in hasil.pesan
    assert "tetap tersimpan" in hasil.pesan


def test_gambar_tidak_melempar_dan_menghasilkan_berkas_valid(qt_available, tmp_path):
    """
    Regresi ganda:
    1. QtTicketPrinter._gambar memakai QPrinter.Unit.DevicePixel tanpa
       mengimpor QPrinter di scope method-nya sendiri — NameError setiap
       kali dipanggil.
    2. Offset piksel tetap (mis. y += 90) diasumsikan DPI rendah, padahal
       mode HighResolution memakai DPI native printer yang bisa ribuan;
       akibatnya seluruh baris tiket saling tumpang tindih.

    Dibuktikan dengan benar-benar menggambar lewat QPainter+QPrinter nyata
    (dialihkan ke berkas PDF, bukan mock), lalu memeriksa hasilnya.
    """
    from datetime import datetime

    from PySide6.QtCore import QSizeF
    from PySide6.QtGui import QPageSize, QPainter
    from PySide6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    berkas = tmp_path / "hasil.pdf"
    printer.setOutputFileName(str(berkas))
    printer.setPageSize(
        QPageSize(
            QSizeF(PdfTicketPrinter.LEBAR_MM, PdfTicketPrinter.TINGGI_MM),
            QPageSize.Unit.Millimeter,
        )
    )
    printer.setFullPage(True)

    data = TicketData(
        queue_number="A-023",
        category_name="Konsultasi",
        office_name="Kantor Pelayanan",
        issued_at=datetime(2026, 8, 26, 20, 7),
        footer="Silakan menunggu hingga nomor Anda dipanggil.",
        counter_name="Loket 2",
    )

    painter = QPainter()
    assert painter.begin(printer)
    QtTicketPrinter._gambar(painter, printer, data)  # tidak boleh melempar
    painter.end()

    assert berkas.exists()
    assert berkas.stat().st_size > 1000
    assert berkas.read_bytes().startswith(b"%PDF")


def test_ukuran_halaman_sama_dengan_tiket_pdf(qt_available, tmp_path):
    """Kedua mode cetak harus menghasilkan ukuran tiket yang identik."""

    from PySide6.QtCore import QSizeF
    from PySide6.QtGui import QPageSize
    from PySide6.QtPrintSupport import QPrinter

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(tmp_path / "ukuran.pdf"))
    printer.setPageSize(
        QPageSize(
            QSizeF(PdfTicketPrinter.LEBAR_MM, PdfTicketPrinter.TINGGI_MM),
            QPageSize.Unit.Millimeter,
        )
    )
    printer.setFullPage(True)

    ukuran_mm = printer.pageRect(QPrinter.Unit.Millimeter)
    assert abs(ukuran_mm.width() - PdfTicketPrinter.LEBAR_MM) < 1
    assert abs(ukuran_mm.height() - PdfTicketPrinter.TINGGI_MM) < 1


# ---------------------------------------------------------------------
# Catatan kaki dibatasi tinggi struk
# ---------------------------------------------------------------------

def test_footer_bawaan_muat_tanpa_dipotong():
    from app.services.settings_service import BAWAAN
    from app.services.ticket_service import MAKS_BARIS_FOOTER, _bungkus

    baris = _bungkus(BAWAAN["ticket.footer"], 38)

    assert len(baris) <= MAKS_BARIS_FOOTER
    assert not baris[-1].endswith("…"), "footer bawaan tidak boleh terpotong"


def test_footer_panjang_dipotong_bukan_jatuh_di_luar_halaman():
    """
    Tinggi struk tetap, jadi baris ketiga tidak akan tercetak sama sekali.

    Dipotong dengan "…" supaya yang menulis catatan kaki tahu tulisannya
    kepanjangan, bukan hilang diam-diam tanpa jejak.
    """
    from app.services.ticket_service import MAKS_BARIS_FOOTER, _bungkus

    panjang = " ".join(["Terima kasih atas kesabaran Anda"] * 5)
    baris = _bungkus(panjang, 38)

    assert len(baris) == MAKS_BARIS_FOOTER
    assert baris[-1].endswith("…")
    assert all(len(b) <= 38 for b in baris)


def test_footer_pendek_tidak_disentuh():
    from app.services.ticket_service import _bungkus

    assert _bungkus("Singkat.", 38) == ["Singkat."]
