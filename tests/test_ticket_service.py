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
    assert tiket.footer == "Silakan menunggu nomor Anda dipanggil."
    assert tiket.header == "BAPENDA DKI JAKARTA"
    assert tiket.geser_atas_mm == 0


def test_tanggal_tiket_berbahasa_indonesia(ticket_pdf, reg_queue, antrian_siap):
    from app.utils.formatting import BULAN

    tiket = ticket_pdf.susun(reg_queue.create_queue(antrian_siap["kategori"]["A"]))

    assert any(bulan in tiket.tanggal for bulan in BULAN)
    assert ":" in tiket.jam
    assert tiket.tanggal_jam == f"{tiket.tanggal}, {tiket.jam}"


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
    assert "26 Agustus 2026, 20:07" in baris
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
# Sisa antrian pada tiket
# ---------------------------------------------------------------------

def test_tiket_menyebut_sisa_antrian(ticket_pdf, reg_queue, antrian_siap):
    for _ in range(2):
        reg_queue.create_queue(antrian_siap["kategori"]["A"])
    ketiga = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    tiket = ticket_pdf.susun(ketiga)

    assert tiket.sisa_antrian == 2
    assert tiket.baris_sisa_antrian() == "Sisa antrian: 2"


def test_antrian_pertama_tidak_dikabari_angka_nol(ticket_pdf, reg_queue, antrian_siap):
    """
    "Sisa antrian: 0" adalah kalimat yang harus dipecahkan sendiri oleh
    pembacanya. Pengunjung paling depan berhak diberi tahu dengan kalimat,
    bukan dengan angka nol.
    """
    tiket = ticket_pdf.susun(reg_queue.create_queue(antrian_siap["kategori"]["A"]))

    assert tiket.sisa_antrian == 0
    assert tiket.baris_sisa_antrian() == "Tidak ada sisa antrian"


def test_sisa_antrian_dihitung_lintas_jenis_layanan(
    ticket_pdf, reg_queue, antrian_siap
):
    """
    Pemanggilan berjalan murni menurut waktu pengambilan nomor, lintas jenis
    layanan. Menghitung hanya yang sejenis akan menjanjikan giliran yang
    jauh lebih cepat daripada yang benar-benar dialami pengunjung.
    """
    reg_queue.create_queue(antrian_siap["kategori"]["B"])
    reg_queue.create_queue(antrian_siap["kategori"]["B"])
    nomor_a = reg_queue.create_queue(antrian_siap["kategori"]["A"])

    assert ticket_pdf.susun(nomor_a).sisa_antrian == 2


def test_yang_sudah_dipanggil_tidak_lagi_dihitung_sebagai_sisa(
    ticket_pdf, cro_queue, antrian_siap, terbitkan, auth
):
    from tests.conftest import TEST_PASSWORD

    terbitkan("A", 2)
    cro_queue.call_next(antrian_siap["loket"][0])
    ketiga = terbitkan("A")[0]

    # Tiket disusun oleh mesin yang mencetak, yaitu meja pendaftaran.
    auth.logout()
    auth.login("registration", TEST_PASSWORD)

    assert ticket_pdf.susun(ketiga).sisa_antrian == 1


def test_kios_boleh_membaca_ringkasan_tiketnya_sendiri(auth, antrian_siap):
    """
    Kios punya TICKET_PRINT tetapi TIDAK punya QUEUE_VIEW. Ringkasan tiket
    harus tetap terbaca olehnya, karena kios justru mesin yang paling sering
    mencetak tiket.
    """
    from app.services.queue_service import QueueService

    auth.logout()
    auth.mulai_sesi_kios()
    kios = QueueService(auth)

    nomor = kios.create_queue(antrian_siap["kategori"]["A"])

    assert kios.ringkasan_tiket(nomor).sisa_antrian == 0


def test_ringkasan_tidak_membocorkan_daftar_antrian_ke_kios(auth, antrian_siap):
    """Kios di ruang publik tetap tidak boleh membaca siapa saja yang mengantre."""
    import pytest as _pytest

    from app.core.errors import AuthorizationError
    from app.services.queue_service import QueueService

    auth.logout()
    auth.mulai_sesi_kios()
    kios = QueueService(auth)
    kios.create_queue(antrian_siap["kategori"]["A"])

    with _pytest.raises(AuthorizationError):
        kios.list_waiting()


def test_tanpa_queue_service_tiket_tetap_terbit_tanpa_ringkasan(
    reg_queue, antrian_siap, auth
):
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService

    printer = NullTicketPrinter()
    service = TicketService(printer, SettingsService(auth), MasterDataService(auth))

    assert service.cetak(reg_queue.create_queue(antrian_siap["kategori"]["A"])).berhasil
    assert printer.tercetak[0].sisa_antrian is None
    assert printer.tercetak[0].baris_sisa_antrian() == ""


def test_ringkasan_yang_gagal_dibaca_tidak_menahan_tiket(
    reg_queue, antrian_siap, auth
):
    """
    Nomor antrian adalah alasan pengunjung berdiri di depan mesin; sisa
    antrian hanya bonus. Database yang tersendat tidak boleh membuat
    tiketnya batal tercetak.
    """
    from app.services.master_data_service import MasterDataService
    from app.services.settings_service import SettingsService

    class QueueRusak:
        def ringkasan_tiket(self, antrian):
            raise RuntimeError("database sedang tidak dapat dihubungi")

    printer = NullTicketPrinter()
    service = TicketService(
        printer, SettingsService(auth), MasterDataService(auth), QueueRusak()
    )

    hasil = service.cetak(reg_queue.create_queue(antrian_siap["kategori"]["A"]))

    assert hasil.berhasil
    assert printer.tercetak[0].queue_number == "A-001"
    assert printer.tercetak[0].baris_sisa_antrian() == ""


def test_sisa_antrian_muat_di_tinggi_struk_yang_tetap(
    ticket_pdf, reg_queue, antrian_siap
):
    """
    Tinggi kertas TIDAK boleh ikut tumbuh: kantor memakai kertas potong
    88 mm. Baris sisa antrian ditambah dua baris catatan kaki karena itu
    harus muat pada tinggi itu juga — baris yang jatuh di luar halaman
    hilang tanpa jejak, jadi tingginya diuji, bukan diandaikan.
    """
    from dataclasses import replace

    from app.services.ticket_service import ATAS_MM, _tata_letak

    assert PdfTicketPrinter.TINGGI_MM == 88

    tiket = ticket_pdf.susun(reg_queue.create_queue(antrian_siap["kategori"]["A"]))
    assert tiket.baris_sisa_antrian()

    # Tiket terpanjang: judul, nama kantor dua baris, loket (tiket cetak
    # ulang yang loketnya sudah diketahui), dan catatan kaki dua baris.
    terpanjang = replace(
        tiket,
        header="BAPENDA DKI JAKARTA",
        office_name="UNIT PELAYANAN PEMUNGUTAN PAJAK DAERAH",
        counter_name="Loket 2",
        footer=" ".join(["Terima kasih atas kesabaran Anda"] * 5),
    )
    baris = _tata_letak(terpanjang, _pas_helvetica, ukuran_nomor=54)
    tulisan = [b for b in baris if not b.garis]

    assert [b.teks for b in tulisan[:3]] == [
        "BAPENDA DKI JAKARTA",
        "UNIT PELAYANAN PEMUNGUTAN",
        "PAJAK DAERAH",
    ]
    assert baris[0].teks == "BAPENDA DKI JAKARTA"
    assert baris[1].garis
    assert baris[1].y_mm > baris[0].y_mm
    assert baris[1].y_mm < tulisan[1].y_mm
    assert tulisan[1].ukuran <= 10
    assert baris[-1].teks.endswith("…"), "catatan kaki harus dua baris penuh"
    assert [b.y_mm for b in baris] == sorted(b.y_mm for b in baris)

    # Baris pertama rapat ke tepi atas: 3,5 mm adalah batas huruf 12 pt.
    assert baris[0].y_mm == ATAS_MM == 3.5

    # IWare makan beberapa mm di kepala kertas. Judul tidak boleh digeser
    # ke zona itu; yang dinaikkan adalah isi di bawahnya, supaya catatan
    # kaki tidak mepet ke tepi potong.
    assert PdfTicketPrinter.TINGGI_MM - baris[-1].y_mm >= 12


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

    from PySide6.QtGui import QPainter
    from PySide6.QtPrintSupport import QPrinter

    from app.services.ticket_service import _pasang_halaman_tiket

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    berkas = tmp_path / "hasil.pdf"
    printer.setOutputFileName(str(berkas))
    _pasang_halaman_tiket(printer, PdfTicketPrinter.LEBAR_MM)

    data = TicketData(
        queue_number="A-023",
        category_name="Konsultasi",
        office_name="Kantor Pelayanan",
        issued_at=datetime(2026, 8, 26, 20, 7),
        footer="Silakan menunggu nomor Anda dipanggil.",
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

    from PySide6.QtGui import QPageLayout
    from PySide6.QtPrintSupport import QPrinter

    from app.services.ticket_service import _pasang_halaman_tiket

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(tmp_path / "ukuran.pdf"))
    _pasang_halaman_tiket(printer, PdfTicketPrinter.LEBAR_MM)

    tata = printer.pageLayout()
    assert tata.mode() == QPageLayout.Mode.FullPageMode
    margin = tata.margins(QPageLayout.Unit.Millimeter)
    assert margin.top() == 0
    assert margin.left() == 0
    assert margin.right() == 0
    assert margin.bottom() == 0

    ukuran_mm = printer.paperRect(QPrinter.Unit.Millimeter)
    assert abs(ukuran_mm.width() - PdfTicketPrinter.LEBAR_MM) < 1
    assert abs(ukuran_mm.height() - PdfTicketPrinter.TINGGI_MM) < 1


def test_geser_printer_tidak_memakan_judul():
    """
    Regresi: geseran −14 mm menaruh judul di zona umpan IWare yang tidak
    tercetak, sehingga "BAPENDA…" hilang dari kertas. Zona itu tidak boleh
    diisi software.
    """
    from app.services.ticket_service import GESER_PRINTER_MM

    assert GESER_PRINTER_MM == 0


def test_offset_gdi_tidak_membatalkan_cetak_tanpa_handle():
    """
    Regresi: QPrinter PySide6 tidak punya handle(). AttributeError di situ
    dulu menelan seluruh cetak — nomor terbit, kertas tidak keluar.
    """
    from app.services.ticket_service import _offset_fisik_gdi

    class TanpaHandle:
        pass

    class HandleRusak:
        def handle(self):
            raise AttributeError("handle")

    assert _offset_fisik_gdi(TanpaHandle()) == (0, 0)
    assert _offset_fisik_gdi(HandleRusak()) == (0, 0)


def test_gambar_pdf_qt_tidak_ikut_geseran_printer_asli(qt_available, tmp_path):
    """Berkas PDF lewat Qt harus tetap rapat ke tepi, seperti tiket ReportLab."""
    from PySide6.QtGui import QPainter
    from PySide6.QtPrintSupport import QPrinter

    from app.services.ticket_service import _geser_atas_printer_px, _pasang_halaman_tiket

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(tmp_path / "tanpa_geser.pdf"))
    _pasang_halaman_tiket(printer, PdfTicketPrinter.LEBAR_MM)

    painter = QPainter()
    assert painter.begin(printer)
    try:
        titik_per_mm = printer.resolution() / 25.4
        assert _geser_atas_printer_px(printer, titik_per_mm, geser_mm=3) == 0
    finally:
        painter.end()


# ---------------------------------------------------------------------
# Catatan kaki dibatasi tinggi struk
# ---------------------------------------------------------------------

def test_footer_bawaan_muat_tanpa_dipotong():
    from app.services.settings_service import BAWAAN
    from app.services.ticket_service import _bungkus

    baris = _bungkus(BAWAAN["ticket.footer"], 38)

    assert baris == ["Silakan menunggu nomor Anda dipanggil."]
    assert len(baris) == 1
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


# ---------------------------------------------------------------------
# Lebar struk
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    ("lebar_printer", "harapan"),
    [(72.0, 72.0), (48.0, 48.0), (80.0, 80.0), (210.0, 80.0), (0.0, 80.0), (-1.0, 80.0)],
)
def test_lebar_halaman_mengikuti_printer_struk_yang_lebih_sempit(lebar_printer, harapan):
    """
    Regresi IWare IW-J200 II: driver POS80 melaporkan kertas 72 mm. Halaman
    80 mm yang dipaksakan membuat seluruh tiket bergeser 4 mm ke kanan dan
    tepi kanannya terpotong.
    """
    from app.services.ticket_service import _lebar_halaman_mm

    assert _lebar_halaman_mm(lebar_printer) == harapan


def _muat_helvetica_tebal(lebar_mm):
    """Pengukur lebar dengan huruf sungguhan, seperti yang dipakai tiket PDF."""
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth

    return lambda teks, pt: stringWidth(teks, "Helvetica-Bold", pt) <= lebar_mm * mm


def test_nama_kantor_panjang_dibungkus_bukan_dipotong():
    """
    Regresi: "UNIT PELAYANAN PEMUNGUTAN PAJAK DAERAH" dipotong [:34] menjadi
    "... PAJAK DA", dan potongan itu pun masih lebih lebar dari kertas 72 mm.
    """
    from app.services.ticket_service import TEPI_MM, _pas_lebar

    nama = "UNIT PELAYANAN PEMUNGUTAN PAJAK DAERAH"
    muat = _muat_helvetica_tebal(72 - 2 * TEPI_MM)

    baris, pt = _pas_lebar(nama, muat, 10, maks_baris=2)

    assert " ".join(baris) == nama
    assert len(baris) == 2
    assert all(muat(b, pt) for b in baris)


def test_nama_kantor_pendek_tetap_satu_baris_ukuran_asli():
    from app.services.ticket_service import TEPI_MM, _pas_lebar

    muat = _muat_helvetica_tebal(72 - 2 * TEPI_MM)

    assert _pas_lebar("Kantor Pelayanan", muat, 10, maks_baris=2) == (
        ["Kantor Pelayanan"],
        10,
    )


def test_baris_tunggal_kepanjangan_dikecilkan_hurufnya():
    """Jenis layanan tidak punya ruang baris kedua: hurufnya yang mengecil."""
    from app.services.ticket_service import TEPI_MM, _pas_lebar

    muat = _muat_helvetica_tebal(72 - 2 * TEPI_MM)
    nama = "Pelayanan Pajak Kendaraan Bermotor"

    baris, pt = _pas_lebar(nama, muat, 14)

    assert baris == [nama]
    assert pt < 14
    assert muat(nama, pt)


def test_teks_yang_tetap_kelebaran_dipotong_dengan_elipsis():
    from app.services.ticket_service import TEPI_MM, UKURAN_HURUF_MIN, _pas_lebar

    muat = _muat_helvetica_tebal(72 - 2 * TEPI_MM)

    baris, pt = _pas_lebar("PELAYANAN " * 20, muat, 14)

    assert pt == UKURAN_HURUF_MIN
    assert len(baris) == 1
    assert baris[0].endswith("…")
    assert muat(baris[0], pt)


def _pas_helvetica(teks, ukuran, tebal, maks_baris):
    """`pas` untuk _tata_letak dengan huruf sungguhan di kertas 72 mm."""
    from app.services.ticket_service import TEPI_MM, _pas_lebar

    return _pas_lebar(teks, _muat_helvetica_tebal(72 - 2 * TEPI_MM), ukuran, maks_baris)


def test_judul_tiket_di_baris_paling_atas():
    from datetime import datetime

    tiket = TicketData(
        queue_number="A-001",
        category_name="Konsultasi",
        office_name="Kantor Pelayanan",
        issued_at=datetime(2026, 9, 12, 9, 30),
        header="BAPENDA DKI JAKARTA",
    )

    assert tiket.baris_teks()[:4] == [
        "BAPENDA DKI JAKARTA",
        "Kantor Pelayanan",
        "",
        "NOMOR ANTRIAN",
    ]


def test_tanpa_judul_nama_kantor_naik_ke_baris_pertama():
    """Judul boleh dikosongkan; tidak boleh menyisakan baris kosong di atas."""
    from dataclasses import replace

    from app.services.ticket_service import ATAS_MM, _tata_letak

    baris = _tata_letak(
        replace(_tiket_nama_panjang(), header=""), _pas_helvetica, ukuran_nomor=44
    )

    assert baris[0].teks == "UNIT PELAYANAN PEMUNGUTAN"
    assert baris[0].y_mm == ATAS_MM
    assert not any(b.garis for b in baris)


def _tiket_nama_panjang():
    from datetime import datetime

    return TicketData(
        queue_number="A-023",
        category_name="Pelayanan Pajak Kendaraan Bermotor",
        office_name="UNIT PELAYANAN PEMUNGUTAN PAJAK DAERAH",
        header="BAPENDA DKI JAKARTA",
        issued_at=datetime(2026, 9, 12, 9, 30),
        footer="Silakan menunggu nomor Anda dipanggil.",
        counter_name="Loket 2",
        sisa_antrian=3,
    )


def test_jarak_dari_layanan_sampai_catatan_kaki_seragam():
    """Nama layanan, loket, tanggal-jam, sisa, dan catatan kaki selang-seling sama."""
    from app.services.ticket_service import JARAK_BLOK_BAWAH_MM, _tata_letak

    baris = [
        b
        for b in _tata_letak(_tiket_nama_panjang(), _pas_helvetica, 44)
        if not b.garis
    ]
    bawah = baris[-5:]
    jarak = [round(b.y_mm - a.y_mm, 2) for a, b in zip(bawah, bawah[1:])]

    assert bawah[0].teks.startswith("Pelayanan")
    assert bawah[-1].teks.startswith("Silakan menunggu")
    assert jarak == [JARAK_BLOK_BAWAH_MM] * 4


def test_tiket_pdf_nama_kantor_dua_baris(tmp_path):
    hasil = PdfTicketPrinter(tmp_path).cetak(_tiket_nama_panjang())

    assert hasil.berhasil
    assert hasil.berkas.read_bytes().startswith(b"%PDF")


def test_gambar_qt_nama_kantor_dua_baris_di_kertas_72mm(qt_available, tmp_path):
    """Jalur Qt sungguhan pada lebar kertas printer struk yang sebenarnya."""
    from PySide6.QtGui import QPainter
    from PySide6.QtPrintSupport import QPrinter

    from app.services.ticket_service import _pasang_halaman_tiket

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    berkas = tmp_path / "72mm.pdf"
    printer.setOutputFileName(str(berkas))
    _pasang_halaman_tiket(printer, 72)

    painter = QPainter()
    assert painter.begin(printer)
    QtTicketPrinter._gambar(painter, printer, _tiket_nama_panjang())
    painter.end()

    assert berkas.read_bytes().startswith(b"%PDF")


# ---------------------------------------------------------------------
# Pencetak per mesin
# ---------------------------------------------------------------------

class _SettingsPalsu:
    """Pengaturan bersama, seolah dibaca dari database."""

    def __init__(self, nilai: str) -> None:
        self.nilai = nilai

    def get(self, key: str, default: str | None = None) -> str:
        assert key == "ticket.printer"
        return self.nilai


def test_pencetak_mengikuti_pengaturan_bersama_bila_mesin_diam(env_mesin):
    from app.services.ticket_service import mode_pencetak

    env_mesin(ANTRIAN_PRINTER=None)
    assert mode_pencetak(_SettingsPalsu("system")) == "system"


def test_pencetak_mesin_menang_atas_pengaturan_bersama(env_mesin):
    """
    Pencetak tiket menempel pada satu komputer.

    Tanpa penimpaan per mesin, menyalakan "Cetak ke printer Windows" untuk
    anjungan membuat kelima komputer loket ikut mencoba mencetak ke
    pencetak yang tidak ada padanya — persis baris "Printer tidak dapat
    dibuka" yang memenuhi log.
    """
    from app.services.ticket_service import mode_pencetak

    env_mesin(ANTRIAN_PRINTER="none")
    assert mode_pencetak(_SettingsPalsu("system")) == "none"


def test_tata_letak_anjungan_android_tidak_memotong_tiket_biasa():
    """Lebar diukur dalam point; dulu 66 mm dibaca 66 pt dan semua terpotong."""
    from datetime import datetime

    from app.services.ticket_service import tata_letak_tiket_anjungan

    data = TicketData(
        queue_number="C-002",
        category_name="Informasi",
        office_name="Kantor Pelayanan",
        issued_at=datetime(2026, 10, 12, 10, 0),
        footer="Silakan menunggu nomor Anda dipanggil.",
        header="BAPENDA DKI JAKARTA",
    )
    baris = {
        row["text"]: row["size"]
        for row in tata_letak_tiket_anjungan(data)["rows"]
        if not row["line"]
    }

    assert baris["BAPENDA DKI JAKARTA"] == 12
    assert baris["Kantor Pelayanan"] == 10
    assert baris["C-002"] == 44
    assert baris["Silakan menunggu nomor Anda dipanggil."] == 9
    assert not any("…" in teks for teks in baris)


def test_tata_letak_anjungan_ikut_turun_seperti_raster():
    """Pengaturan "Turunkan isi tiket anjungan" berlaku di kedua jalur Android."""
    from datetime import datetime

    from app.services.ticket_service import tata_letak_tiket_anjungan

    dasar = dict(
        queue_number="C-002",
        category_name="Informasi",
        office_name="Kantor Pelayanan",
        issued_at=datetime(2026, 10, 12, 10, 0),
    )
    rata = tata_letak_tiket_anjungan(TicketData(**dasar))["rows"]
    turun = tata_letak_tiket_anjungan(
        TicketData(**dasar, turun_anjungan_mm=4, geser_atas_mm=1)
    )["rows"]

    assert [b["y_mm"] - a["y_mm"] for a, b in zip(rata, turun)] == [3] * len(rata)


# ---------------------------------------------------------------------
# Penanda cetak ulang
# ---------------------------------------------------------------------

def _tiket_contoh(**ubah):
    from datetime import datetime

    from app.services.ticket_service import TicketData

    dasar = dict(
        queue_number="PB-004",
        category_name="PBB",
        office_name="Kantor Pelayanan",
        issued_at=datetime(2026, 10, 22, 9, 15),
        sisa_antrian=3,
    )
    return TicketData(**{**dasar, **ubah})


def test_tiket_pertama_tanpa_penanda_cetak_ulang():
    tiket = _tiket_contoh()
    assert tiket.baris_cetak_ulang() == ""
    assert "Sisa antrian: 3" in tiket.baris_teks()


def test_tiket_cetak_ulang_bertanda_jam_dan_menggantikan_sisa_antrian():
    from datetime import datetime

    tiket = _tiket_contoh(cetak_ulang_pada=datetime(2026, 10, 22, 9, 42))
    baris = tiket.baris_teks()

    assert "*** CETAK ULANG 09:42 ***" in baris
    assert not any(b.startswith("Sisa antrian") for b in baris)
    # Nomor dan jam terbit tetap yang asli.
    assert "PB-004" in baris
    assert tiket.jam == "09:15"


def test_tiket_cetak_ulang_tetap_muat_88_mm():
    from dataclasses import replace
    from datetime import datetime

    from app.services.ticket_service import PdfTicketPrinter, _tata_letak

    tiket = replace(
        _tiket_contoh(),
        header="BAPENDA DKI JAKARTA",
        office_name="UNIT PELAYANAN PEMUNGUTAN PAJAK DAERAH",
        counter_name="Loket 2",
        footer=" ".join(["Terima kasih atas kesabaran Anda"] * 5),
        cetak_ulang_pada=datetime(2026, 10, 22, 9, 42),
    )
    baris = _tata_letak(tiket, _pas_helvetica, ukuran_nomor=54)

    assert "*** CETAK ULANG 09:42 ***" in [b.teks for b in baris]
    assert PdfTicketPrinter.TINGGI_MM - baris[-1].y_mm >= 12


def test_petugas_loket_membaca_ringkasan_tiket_tanpa_peringatan_akses(
    auth, antrian_siap, terbitkan, caplog
):
    """CRO mencetak ulang di loket: tidak punya TICKET_PRINT, tetapi berhak QUEUE_VIEW."""
    import logging

    from app.services.queue_service import QueueService
    from tests.conftest import TEST_PASSWORD

    terbitkan("A", 3)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    layanan = QueueService(auth)
    nomor = layanan.call_next(antrian_siap["loket"][0])

    with caplog.at_level(logging.WARNING, logger="antrian.auth"):
        ringkasan = layanan.ringkasan_tiket(nomor)

    assert ringkasan.sisa_antrian == 0
    assert not [r for r in caplog.records if "Akses ditolak" in r.getMessage()]


def test_cetak_ulang_petugas_loket_memuat_ringkasan_tanpa_gagal(
    auth, antrian_siap, terbitkan, ticket_pdf
):
    from app.services.queue_service import QueueService
    from tests.conftest import TEST_PASSWORD

    terbitkan("A", 2)
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    nomor = QueueService(auth).call_next(antrian_siap["loket"][0])

    tiket = ticket_pdf.susun(nomor, cetak_ulang=True)

    assert tiket.sisa_antrian == 0
    assert tiket.baris_cetak_ulang().startswith("*** CETAK ULANG")
