"""
Ruang kerja petugas: pengaduan pengunjung dan catatan petugas.

DIALOG, bukan panel yang menempel di layar pelayanan. Tujuh isian tidak
muat pada kolom kiri panel pelayanan — kolom itu sudah memuat kartu antrian
dan seluruh tombol tindakan, dan sisanya hanya beberapa ratus piksel.
Dipaksa muat, baris formulirnya tergencet sampai label dan isian saling
menimpa. Dialog mendapat ruangnya sendiri, dan ruang itulah yang dibutuhkan
untuk mengetik keluhan orang.

Pengorbanannya disadari: petugas harus membukanya lebih dahulu. Karena itu
baris ringkas di panel pelayanan menyebutkan keadaan lembar tanpa perlu
dibuka — sudah terisi atau belum, dan kapan terakhir disimpan.

DESKRIPSI DAN CATATAN SENGAJA TIDAK DISATUKAN. Deskripsi adalah kata
pengunjung; catatan adalah penilaian petugas. Bercampur dalam satu kotak,
penilaian internal ikut terbaca sebagai keluhan pelanggan oleh siapa pun
yang membuka lembar itu kemudian.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.note_service import (
    PANJANG_ALAMAT,
    PANJANG_EMAIL,
    PANJANG_NAMA,
    PANJANG_NOMOR_PELANGGAN,
    PANJANG_TELEPON,
    NoteInfo,
    NoteService,
)
from app.services.queue_service import QueueInfo
from app.ui.common import jalankan_aman, judul, konfirmasi, tombol
from app.ui.style import (
    FONT_SIZE_SMALL,
    SUCCESS,
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

#: Tinggi terkecil kotak keluhan dan catatan.
#:
#: Kotak setinggi satu baris membuat petugas mengetik keluhan panjang lewat
#: lubang intip: yang sudah diketik menggulung ke atas dan tidak terbaca
#: lagi saat hendak diperiksa ulang sebelum disimpan.
TINGGI_KOTAK_MINIMUM = 110


class NoteDialog(QDialog):
    """Formulir pengaduan dan catatan untuk satu nomor antrian."""

    def __init__(
        self,
        note: NoteService,
        antrian: QueueInfo,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.note = note
        self.antrian = antrian
        #: Lembar yang tersimpan di database, atau None bila belum ada.
        self.lembar: NoteInfo | None = None
        #: Benar bila ada yang tersimpan selama dialog ini terbuka. Dipakai
        #: panel pelayanan untuk menyegarkan baris ringkasnya.
        self.tersimpan = False

        self.setWindowTitle(f"Pengaduan & Catatan — {antrian.queue_number}")
        self.setMinimumSize(660, 600)

        self._bangun_tampilan()
        self._muat()

        # Ctrl+S sama seperti di mana pun. Petugas yang terbiasa menekannya
        # tidak boleh menemukan dialog ini sebagai pengecualian.
        QShortcut(QKeySequence("Ctrl+S"), self, self.simpan)

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(12)

        susunan.addWidget(judul(f"Lembar Antrian {self.antrian.queue_number}"))

        rincian = [self.antrian.category_name]
        if self.antrian.counter_name:
            rincian.append(self.antrian.counter_name)
        keterangan_atas = QLabel(" · ".join(r for r in rincian if r))
        keterangan_atas.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )
        susunan.addWidget(keterangan_atas)

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

        self.tombol_tutup = tombol("Tutup")
        self.tombol_tutup.clicked.connect(self.reject)
        baris.addWidget(self.tombol_tutup)

        self.tombol_simpan = tombol("Simpan (Ctrl+S)", variant="primary", default=True)
        self.tombol_simpan.clicked.connect(self.simpan)
        baris.addWidget(self.tombol_simpan)
        susunan.addLayout(baris)

    def _bangun_tab_pengaduan(self) -> QWidget:
        halaman = QWidget()
        susunan = QVBoxLayout(halaman)
        susunan.setContentsMargins(16, 14, 16, 14)
        susunan.setSpacing(10)

        peringatan = QLabel(PERINGATAN)
        peringatan.setWordWrap(True)
        peringatan.setStyleSheet(
            f"background: {WARNING_SOFT}; color: {WARNING};"
            " border-radius: 6px; padding: 8px 10px;"
            f" font-size: {FONT_SIZE_SMALL}px;"
        )
        susunan.addWidget(peringatan)

        self.isian_nama = self._isian_singkat(PANJANG_NAMA, "Nama pelapor")
        self.isian_nomor_pelanggan = self._isian_singkat(
            PANJANG_NOMOR_PELANGGAN, "Nomor pelanggan"
        )
        self.isian_telepon = self._isian_singkat(PANJANG_TELEPON, "Boleh dikosongkan")
        self.isian_email = self._isian_singkat(PANJANG_EMAIL, "Boleh dikosongkan")
        self.isian_alamat = self._isian_singkat(PANJANG_ALAMAT, "Boleh dikosongkan")

        # Dua isian per baris, bukan tujuh baris menurun. Dialog ini lebih
        # lebar daripada tinggi, dan tinggi itulah yang dibutuhkan kotak
        # keluhan di bawahnya.
        kisi = QGridLayout()
        kisi.setHorizontalSpacing(16)
        kisi.setVerticalSpacing(8)
        kisi.setColumnStretch(1, 1)
        kisi.setColumnStretch(3, 1)

        for baris, kiri, kanan in (
            (0, ("Nama *", self.isian_nama), ("No. Pelanggan *", self.isian_nomor_pelanggan)),
            (1, ("Telepon", self.isian_telepon), ("Email", self.isian_email)),
        ):
            kisi.addWidget(self._label(kiri[0]), baris, 0)
            kisi.addWidget(kiri[1], baris, 1)
            kisi.addWidget(self._label(kanan[0]), baris, 2)
            kisi.addWidget(kanan[1], baris, 3)

        kisi.addWidget(self._label("Alamat"), 2, 0)
        kisi.addWidget(self.isian_alamat, 2, 1, 1, 3)
        susunan.addLayout(kisi)

        susunan.addWidget(self._label("Deskripsi Pengaduan *"))
        self.isian_deskripsi = QPlainTextEdit()
        self.isian_deskripsi.setPlaceholderText(
            "Keluhan menurut pengunjung, dengan kata-katanya sendiri"
        )
        self.isian_deskripsi.setMinimumHeight(TINGGI_KOTAK_MINIMUM)
        susunan.addWidget(self.isian_deskripsi, stretch=1)

        wajib = QLabel(
            "Bertanda * wajib diisi bila ada pengaduan. Catatan petugas boleh "
            "diisi tanpa pengaduan sama sekali."
        )
        wajib.setWordWrap(True)
        wajib.setStyleSheet(f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;")
        susunan.addWidget(wajib)
        return halaman

    def _bangun_tab_catatan(self) -> QWidget:
        halaman = QWidget()
        susunan = QVBoxLayout(halaman)
        susunan.setContentsMargins(16, 14, 16, 14)
        susunan.setSpacing(10)

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
        self.isian_catatan.setMinimumHeight(TINGGI_KOTAK_MINIMUM)
        susunan.addWidget(self.isian_catatan, stretch=1)
        return halaman

    @staticmethod
    def _isian_singkat(batas: int, petunjuk: str) -> QLineEdit:
        isian = QLineEdit()
        isian.setMaxLength(batas)
        isian.setPlaceholderText(petunjuk)
        return isian

    @staticmethod
    def _label(teks: str) -> QLabel:
        label = QLabel(teks)
        label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;")
        return label

    # -----------------------------------------------------------------
    # Isi
    # -----------------------------------------------------------------

    def _muat(self) -> None:
        """Baca lembar yang sudah ada, bila antrian ini pernah ditulisi."""
        berhasil, lembar = jalankan_aman(
            self, lambda: self.note.ambil(self.antrian.id), "Gagal membaca catatan"
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
        self.isian_alamat.setText(lembar.alamat or "")
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

        if self.lembar is None:
            teks = "Belum pernah disimpan."
        else:
            teks = (
                f"Tersimpan {self.lembar.updated_at.strftime('%H:%M')} · "
                f"{self.lembar.officer_name or '-'}"
            )
        self.label_keadaan.setText(teks)
        self.label_keadaan.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )

    @property
    def ada_isian(self) -> bool:
        """Benar bila ada sesuatu yang layak disimpan."""
        return bool(
            self.isian_deskripsi.toPlainText().strip()
            or self.isian_catatan.toPlainText().strip()
        )

    @property
    def berubah(self) -> bool:
        """
        Benar bila isian di layar berbeda dari yang tersimpan.

        Dipakai saat dialog ditutup. Menutup dengan perubahan yang belum
        disimpan berarti keluhan yang barusan diceritakan hilang tanpa
        jejak, dan orangnya sudah meninggalkan meja.
        """
        tersimpan = self.lembar
        sekarang = (
            self.isian_nama.text().strip(),
            self.isian_nomor_pelanggan.text().strip(),
            self.isian_telepon.text().strip(),
            self.isian_email.text().strip(),
            self.isian_alamat.text().strip(),
            self.isian_deskripsi.toPlainText().strip(),
            self.isian_catatan.toPlainText().strip(),
        )
        if tersimpan is None:
            return any(sekarang)
        return sekarang != (
            (tersimpan.nama or "").strip(),
            (tersimpan.nomor_pelanggan or "").strip(),
            (tersimpan.telepon or "").strip(),
            (tersimpan.email or "").strip(),
            (tersimpan.alamat or "").strip(),
            (tersimpan.deskripsi or "").strip(),
            (tersimpan.catatan or "").strip(),
        )

    # -----------------------------------------------------------------
    # Tindakan
    # -----------------------------------------------------------------

    def simpan(self) -> bool:
        """
        Simpan lembar. Mengembalikan True bila tersimpan.

        Dialog TIDAK ditutup sendiri setelah menyimpan. Petugas sering
        menyimpan di tengah pembicaraan lalu meneruskan mengetik; dialog
        yang menghilang begitu Ctrl+S ditekan memaksanya membuka lagi.
        """
        if not self.ada_isian:
            self._perbarui_keadaan(
                "Isi deskripsi pengaduan atau catatan petugas lebih dahulu.", WARNING
            )
            return False

        berhasil, lembar = jalankan_aman(
            self,
            lambda: self.note.simpan(
                self.antrian.id,
                nama=self.isian_nama.text(),
                nomor_pelanggan=self.isian_nomor_pelanggan.text(),
                telepon=self.isian_telepon.text(),
                email=self.isian_email.text(),
                alamat=self.isian_alamat.text(),
                deskripsi=self.isian_deskripsi.toPlainText(),
                catatan=self.isian_catatan.toPlainText(),
            ),
            "Gagal menyimpan catatan",
        )
        if not berhasil or lembar is None:
            return False

        self.lembar = lembar
        self.tersimpan = True
        self._perbarui_keadaan(
            f"Tersimpan {lembar.updated_at.strftime('%H:%M:%S')}", SUCCESS
        )
        return True

    def reject(self) -> None:  # noqa: D102 - perilaku Qt, dijelaskan di bawah
        """
        Tutup dialog, menanyakan lebih dahulu bila ada yang belum tersimpan.

        Termasuk saat ditutup lewat tombol X maupun tombol Esc — Qt
        mengarahkan ketiganya ke sini.
        """
        if self.berubah and not konfirmasi(
            self,
            "Ada isian yang belum disimpan. Tutup dan buang perubahannya?",
            "Tutup Lembar",
        ):
            return
        super().reject()
