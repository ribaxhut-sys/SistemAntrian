"""
Ruang kerja petugas: pengaduan pengunjung dan catatan petugas.

Dua tab pada satu panel, bukan dua panel bersebelahan. Panel pelayanan
sudah terbagi dua kolom, dan membelahnya lagi menghasilkan empat kotak
sempit yang tidak satu pun cukup lebar untuk mengetik kalimat. Petugas juga
tidak mengisi keduanya sekaligus: pengaduan ditulis sambil mendengarkan
pengunjung, catatan ditulis setelah orangnya pergi.

DESKRIPSI DAN CATATAN SENGAJA TIDAK DISATUKAN. Deskripsi adalah kata
pengunjung; catatan adalah penilaian petugas. Bercampur dalam satu kotak,
penilaian internal ikut terbaca sebagai keluhan pelanggan oleh siapa pun
yang membuka lembar itu kemudian.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.note_service import (
    PANJANG_EMAIL,
    PANJANG_NAMA,
    PANJANG_NOMOR_PELANGGAN,
    PANJANG_TELEPON,
    NoteInfo,
    NoteService,
)
from app.services.queue_service import QueueInfo
from app.ui.common import jalankan_aman, tombol
from app.ui.style import (
    BORDER,
    FONT_SIZE_SMALL,
    RADIUS,
    SUCCESS,
    SURFACE,
    TEXT_MUTED,
    WARNING,
    WARNING_SOFT,
)

#: Peringatan tetap di atas formulir.
#:
#: Satu-satunya tempat data pribadi disimpan di aplikasi ini adalah lembar
#: ini, dan petugas yang sedang terburu-buru tidak akan mengingat itu.
#: Kalimatnya sengaja menyebut apa yang TIDAK perlu ditulis, bukan sekadar
#: mengimbau berhati-hati — imbauan tanpa isi tidak mengubah apa pun.
PERINGATAN = (
    "Isi seperlunya. Jangan menyalin NIK, nomor rekening, atau data lain "
    "yang tidak dibutuhkan untuk menindaklanjuti pengaduan ini."
)


class NotePanel(QWidget):
    """
    Formulir pengaduan dan catatan untuk antrian yang sedang ditangani.

    Seluruh isian DINONAKTIFKAN ketika tidak ada antrian aktif, bukan
    disembunyikan — sama seperti tombol tindakan di sebelahnya. Panel yang
    muncul dan hilang membuat seluruh kolom melompat setiap kali status
    berubah, dan petugas kehilangan tempat matanya beberapa kali semenit.
    """

    def __init__(self, note: NoteService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.note = note
        self.antrian: QueueInfo | None = None
        #: Lembar yang sedang dibuka, bila antrian ini sudah pernah ditulisi.
        self.lembar: NoteInfo | None = None

        self._bangun_tampilan()
        self.set_antrian(None)

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)

        self.tab = QTabWidget()
        self.tab.addTab(self._bangun_tab_pengaduan(), "Pengaduan")
        self.tab.addTab(self._bangun_tab_catatan(), "Catatan Petugas")
        susunan.addWidget(self.tab, stretch=1)

        baris = QHBoxLayout()
        baris.setSpacing(10)

        self.label_keadaan = QLabel("")
        self.label_keadaan.setWordWrap(True)
        self.label_keadaan.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )
        baris.addWidget(self.label_keadaan, stretch=1)

        self.tombol_simpan = tombol("Simpan (Ctrl+S)", variant="primary")
        self.tombol_simpan.clicked.connect(self.simpan)
        baris.addWidget(self.tombol_simpan)
        susunan.addLayout(baris)

    def _bangun_tab_pengaduan(self) -> QWidget:
        halaman = QWidget()
        susunan = QVBoxLayout(halaman)
        susunan.setContentsMargins(14, 12, 14, 12)
        susunan.setSpacing(8)

        peringatan = QLabel(PERINGATAN)
        peringatan.setWordWrap(True)
        peringatan.setStyleSheet(
            f"background: {WARNING_SOFT}; color: {WARNING};"
            f" border-radius: 6px; padding: 7px 10px;"
            f" font-size: {FONT_SIZE_SMALL}px;"
        )
        susunan.addWidget(peringatan)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.isian_nama = QLineEdit()
        self.isian_nama.setMaxLength(PANJANG_NAMA)
        self.isian_nama.setPlaceholderText("Nama pelapor")

        self.isian_nomor_pelanggan = QLineEdit()
        self.isian_nomor_pelanggan.setMaxLength(PANJANG_NOMOR_PELANGGAN)
        self.isian_nomor_pelanggan.setPlaceholderText("Nomor pelanggan")

        self.isian_telepon = QLineEdit()
        self.isian_telepon.setMaxLength(PANJANG_TELEPON)
        self.isian_telepon.setPlaceholderText("Boleh dikosongkan")

        self.isian_email = QLineEdit()
        self.isian_email.setMaxLength(PANJANG_EMAIL)
        self.isian_email.setPlaceholderText("Boleh dikosongkan")

        self.isian_alamat = QPlainTextEdit()
        self.isian_alamat.setPlaceholderText("Boleh dikosongkan")
        self.isian_alamat.setFixedHeight(52)

        self.isian_deskripsi = QPlainTextEdit()
        self.isian_deskripsi.setPlaceholderText(
            "Keluhan menurut pengunjung, dengan kata-katanya sendiri"
        )

        # Bintang pada dua isian yang wajib. Wajibnya BERSYARAT — hanya
        # ketika ada deskripsi pengaduan — dan itu dijelaskan pada label
        # keadaan di bawah, bukan lewat tanda yang berubah-ubah sendiri.
        form.addRow("Nama *", self.isian_nama)
        form.addRow("No. Pelanggan *", self.isian_nomor_pelanggan)
        form.addRow("Telepon", self.isian_telepon)
        form.addRow("Email", self.isian_email)
        form.addRow("Alamat", self.isian_alamat)
        susunan.addLayout(form)

        label = QLabel("Deskripsi Pengaduan *")
        label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;")
        susunan.addWidget(label)
        susunan.addWidget(self.isian_deskripsi, stretch=1)

        return halaman

    def _bangun_tab_catatan(self) -> QWidget:
        halaman = QWidget()
        susunan = QVBoxLayout(halaman)
        susunan.setContentsMargins(14, 12, 14, 12)
        susunan.setSpacing(8)

        keterangan_teks = QLabel(
            "Catatan internal atas pelayanan ini. Dapat diisi tanpa pengaduan, "
            "dan tidak pernah dibacakan kepada pengunjung."
        )
        keterangan_teks.setWordWrap(True)
        keterangan_teks.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )
        susunan.addWidget(keterangan_teks)

        self.isian_catatan = QPlainTextEdit()
        self.isian_catatan.setPlaceholderText(
            "Misalnya: berkas belum lengkap, diminta kembali membawa fotokopi."
        )
        susunan.addWidget(self.isian_catatan, stretch=1)
        return halaman

    # -----------------------------------------------------------------
    # Isi
    # -----------------------------------------------------------------

    @property
    def _isian(self) -> tuple[QWidget, ...]:
        return (
            self.isian_nama,
            self.isian_nomor_pelanggan,
            self.isian_telepon,
            self.isian_email,
            self.isian_alamat,
            self.isian_deskripsi,
            self.isian_catatan,
        )

    def kosongkan(self) -> None:
        for kotak in self._isian:
            if isinstance(kotak, QLineEdit):
                kotak.clear()
            else:
                kotak.setPlainText("")

    def set_antrian(self, antrian: QueueInfo | None) -> None:
        """
        Pindahkan panel ke antrian lain, memuat lembarnya bila sudah ada.

        Isian dikosongkan lebih dahulu SEBELUM lembar baru dibaca. Kegagalan
        membaca akan meninggalkan isian antrian sebelumnya di layar, dan
        petugas yang menekan Simpan setelah itu menuliskan keluhan orang
        lain ke nomor yang sedang ditangani.
        """
        pindah = antrian is None or self.antrian is None or antrian.id != self.antrian.id
        self.antrian = antrian

        if pindah:
            self.kosongkan()
            self.lembar = None

        aktif = antrian is not None
        for kotak in self._isian:
            kotak.setEnabled(aktif)
        self.tombol_simpan.setEnabled(aktif)

        if aktif and pindah:
            berhasil, lembar = jalankan_aman(
                self, lambda: self.note.ambil(antrian.id), "Gagal membaca catatan"
            )
            if berhasil and lembar is not None:
                self._tampilkan(lembar)

        self._perbarui_keadaan()

    def _tampilkan(self, lembar: NoteInfo) -> None:
        self.lembar = lembar
        self.isian_nama.setText(lembar.nama or "")
        self.isian_nomor_pelanggan.setText(lembar.nomor_pelanggan or "")
        self.isian_telepon.setText(lembar.telepon or "")
        self.isian_email.setText(lembar.email or "")
        self.isian_alamat.setPlainText(lembar.alamat or "")
        self.isian_deskripsi.setPlainText(lembar.deskripsi or "")
        self.isian_catatan.setPlainText(lembar.catatan or "")

    def _perbarui_keadaan(self, pesan: str = "", warna: str = "") -> None:
        if pesan:
            self.label_keadaan.setText(pesan)
            self.label_keadaan.setStyleSheet(
                f"color: {warna or TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
                " font-weight: 700;"
            )
            return

        if self.antrian is None:
            teks = "Panggil sebuah nomor lebih dahulu."
        elif self.lembar is not None:
            waktu = self.lembar.updated_at.strftime("%H:%M")
            teks = f"Tersimpan {waktu} · {self.lembar.officer_name or '-'}"
        else:
            teks = "Nama dan nomor pelanggan wajib diisi bila ada pengaduan."

        self.label_keadaan.setText(teks)
        self.label_keadaan.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )

    # -----------------------------------------------------------------
    # Penyimpanan
    # -----------------------------------------------------------------

    @property
    def ada_isian(self) -> bool:
        """Benar bila ada sesuatu yang layak disimpan."""
        return bool(
            self.isian_deskripsi.toPlainText().strip()
            or self.isian_catatan.toPlainText().strip()
        )

    def simpan(self) -> bool:
        """
        Simpan lembar antrian yang sedang ditangani.

        Mengembalikan True bila tersimpan. Nilainya dipakai `selesaikan()`
        di panel pelayanan: pelayanan tidak boleh ditutup diam-diam sambil
        meninggalkan pengaduan yang gagal disimpan.
        """
        if self.antrian is None or not self.ada_isian:
            return False

        antrian = self.antrian
        berhasil, lembar = jalankan_aman(
            self,
            lambda: self.note.simpan(
                antrian.id,
                nama=self.isian_nama.text(),
                nomor_pelanggan=self.isian_nomor_pelanggan.text(),
                telepon=self.isian_telepon.text(),
                email=self.isian_email.text(),
                alamat=self.isian_alamat.toPlainText(),
                deskripsi=self.isian_deskripsi.toPlainText(),
                catatan=self.isian_catatan.toPlainText(),
            ),
            "Gagal menyimpan catatan",
        )
        if not berhasil or lembar is None:
            return False

        self.lembar = lembar
        self._perbarui_keadaan(
            f"Tersimpan {lembar.updated_at.strftime('%H:%M:%S')}", SUCCESS
        )
        return True


def bingkai_ruang_kerja(isi: QWidget) -> QFrame:
    """
    Bungkus panel dengan bingkai berjudul, senada dengan panel lain.

    Dipisahkan dari NotePanel supaya panelnya sendiri tetap dapat diuji
    tanpa ikut membawa hiasan.
    """
    bingkai = QFrame()
    bingkai.setObjectName("panelKerja")
    bingkai.setStyleSheet(
        f"QFrame#panelKerja {{ background: {SURFACE};"
        f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
    )
    susunan = QVBoxLayout(bingkai)
    susunan.setContentsMargins(14, 12, 14, 12)
    susunan.setSpacing(8)

    judul_panel = QLabel("RUANG KERJA")
    judul_panel.setProperty("kapsi", "true")
    susunan.addWidget(judul_panel)
    susunan.addWidget(isi, stretch=1)
    return bingkai
