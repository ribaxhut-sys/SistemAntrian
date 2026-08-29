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
    assert PdfTicketPrinter.TINGGI_MM == 88

    tiket = ticket_pdf.susun(reg_queue.create_queue(antrian_siap["kategori"]["A"]))
    assert tiket.baris_sisa_antrian()

    # Jarak antarbaris persis seperti pada PdfTicketPrinter._gambar, dihitung
    # dari tepi atas kertas sampai baris catatan kaki yang paling bawah, pada
    # tiket terpanjang: tiket cetak ulang yang loketnya sudah diketahui.
    jarak = [
        12,  # margin atas -> nama kantor
        8,  # -> "NOMOR ANTRIAN"
        18,  # -> nomor antrian
        13,  # -> jenis layanan
        6,  # -> nama loket
        6,  # -> tanggal
        5,  # -> jam
        7,  # -> sisa antrian
        6,  # -> catatan kaki baris pertama
        4.5,  # -> catatan kaki baris kedua
    ]
    assert sum(jarak) <= PdfTicketPrinter.TINGGI_MM


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
