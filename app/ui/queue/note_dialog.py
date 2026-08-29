"""
Ruang kerja petugas: pengaduan pengunjung dan catatan petugas.

DIALOG, bukan panel yang menempel di layar pelayanan. Tujuh isian tidak
muat pada kolom kiri panel pelayanan — kolom itu sudah memuat kartu antrian
dan seluruh tombol tindakan. Dipaksa muat, baris formulirnya tergencet
sampai label dan isian saling menimpa.

SATU HALAMAN, bukan dua tab. Tab menyembunyikan separuh formulir di balik
klik, dan yang tersembunyi itu justru catatan petugas — bagian yang paling
sering lupa diisi. Keduanya kini terlihat sekaligus, dipisahkan judul
bagian, dan seluruh formulir dapat digulir sehingga tidak pernah ada baris
yang diperas ketika jendelanya diperkecil.

DESKRIPSI DAN CATATAN TETAP DUA KOTAK TERPISAH. Deskripsi adalah kata
pengunjung; catatan adalah penilaian petugas. Disatukan menjadi satu kotak,
penilaian internal ikut terbaca sebagai keluhan pelanggan oleh siapa pun
yang membuka lembar itu kemudian.

Formulirnya menanggapi apa yang sedang diketik: begitu deskripsi terisi,
lembar ini berubah menjadi pengaduan, dan isian identitas yang tadinya
opsional berubah menjadi wajib — ditandai pada saat itu juga, bukan
sesudah petugas menekan Simpan dan menerima penolakan.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.note_service import (
    PANJANG_ALAMAT,
    PANJANG_CATATAN,
    PANJANG_DESKRIPSI,
    PANJANG_EMAIL,
    PANJANG_NAMA,
    PANJANG_NOMOR_PELANGGAN,
    PANJANG_TELEPON,
    NoteInfo,
    NoteService,
)
from app.services.queue_service import QueueInfo
from app.ui.common import jalankan_aman, konfirmasi, tombol
from app.ui.style import (
    BORDER,
    DANGER,
    FONT_SIZE_SMALL,
    FONT_SIZE_XL,
    PRIMARY,
    PRIMARY_SOFT,
    RADIUS,
    RADIUS_SM,
    SUCCESS,
    SUCCESS_SOFT,
    SURFACE,
    SURFACE_ALT,
    TEXT,
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
TINGGI_DESKRIPSI = 130
TINGGI_CATATAN = 90

#: Penghitung huruf mulai memperingatkan pada porsi ini dari batasnya.
#:
#: Diperingatkan sebelum mentok, bukan sesudah. Petugas yang baru tahu
#: batasnya ketika penolakan muncul harus memotong kalimat orang lain
#: sambil orangnya menunggu.
AMBANG_PERINGATAN = 0.9


def _gaya_kapsul(warna: str, latar: str) -> str:
    """Label berbentuk kapsul, dipakai menandai keadaan lembar."""
    return (
        f"background: {latar}; color: {warna}; border-radius: 11px;"
        f" padding: 4px 12px; font-size: {FONT_SIZE_SMALL}px; font-weight: 700;"
    )


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
        self.setMinimumSize(720, 640)

        self._bangun_tampilan()
        self._sambungkan()
        self._muat()

        # Ctrl+S sama seperti di mana pun. Petugas yang terbiasa menekannya
        # tidak boleh menemukan dialog ini sebagai pengecualian.
        QShortcut(QKeySequence("Ctrl+S"), self, self.simpan)

    # =================================================================
    # Tampilan
    # =================================================================

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(0)

        susunan.addWidget(self._bangun_kepala())

        # Seluruh formulir dapat digulir. Jendela yang diperkecil lalu
        # memeras baris formulirnya sampai label dan isian saling menimpa
        # sudah pernah terjadi sekali; area gulir membuatnya mustahil.
        gulir = QScrollArea()
        gulir.setWidgetResizable(True)
        gulir.setFrameShape(QFrame.Shape.NoFrame)
        gulir.setStyleSheet(f"QScrollArea {{ background: {SURFACE_ALT}; }}")

        isi = QWidget()
        isi.setStyleSheet(f"background: {SURFACE_ALT};")
        badan = QVBoxLayout(isi)
        badan.setContentsMargins(22, 18, 22, 18)
        badan.setSpacing(14)

        badan.addWidget(self._bangun_peringatan())
        badan.addWidget(self._bangun_bagian_pelapor())
        badan.addWidget(self._bangun_bagian_pengaduan())
        badan.addWidget(self._bangun_bagian_catatan())
        badan.addStretch()

        gulir.setWidget(isi)
        susunan.addWidget(gulir, stretch=1)
        susunan.addWidget(self._bangun_kaki())

    def _bangun_kepala(self) -> QWidget:
        """
        Kepala dialog: nomor antrian besar, keterangan, dan kapsul keadaan.

        Nomor dibuat besar karena satu-satunya kekeliruan yang benar-benar
        merugikan di formulir ini adalah menuliskan keluhan seseorang pada
        nomor milik orang lain.
        """
        kepala = QFrame()
        kepala.setObjectName("kepalaLembar")
        kepala.setStyleSheet(
            f"QFrame#kepalaLembar {{ background: {SURFACE};"
            f" border-bottom: 1px solid {BORDER}; }}"
        )

        baris = QHBoxLayout(kepala)
        baris.setContentsMargins(22, 16, 22, 16)
        baris.setSpacing(14)

        teks = QVBoxLayout()
        teks.setSpacing(2)

        nomor = QLabel(self.antrian.queue_number)
        nomor.setStyleSheet(
            f"color: {TEXT}; font-size: {FONT_SIZE_XL}px; font-weight: 800;"
        )
        teks.addWidget(nomor)

        rincian = [self.antrian.category_name, self.antrian.counter_name]
        keterangan_atas = QLabel(" · ".join(r for r in rincian if r))
        keterangan_atas.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )
        teks.addWidget(keterangan_atas)
        baris.addLayout(teks)
        baris.addStretch()

        self.kapsul = QLabel("")
        self.kapsul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        baris.addWidget(self.kapsul)
        return kepala

    def _bangun_peringatan(self) -> QWidget:
        peringatan = QLabel(PERINGATAN)
        peringatan.setWordWrap(True)
        peringatan.setStyleSheet(
            f"background: {WARNING_SOFT}; color: {WARNING};"
            f" border-radius: {RADIUS_SM}px; padding: 9px 12px;"
            f" font-size: {FONT_SIZE_SMALL}px;"
        )
        return peringatan

    def _bangun_bagian_pelapor(self) -> QWidget:
        kartu, badan = self._kartu("DATA PELAPOR")

        self.isian_nama = self._isian(PANJANG_NAMA, "Nama pelapor")
        self.isian_nomor_pelanggan = self._isian(
            PANJANG_NOMOR_PELANGGAN, "Nomor pelanggan"
        )
        self.isian_telepon = self._isian(PANJANG_TELEPON, "Boleh dikosongkan")
        self.isian_email = self._isian(PANJANG_EMAIL, "Boleh dikosongkan")
        self.isian_alamat = self._isian(PANJANG_ALAMAT, "Boleh dikosongkan")

        # Dua isian per baris, bukan lima baris menurun. Dialog ini lebih
        # lebar daripada tinggi, dan tinggi itulah yang dibutuhkan kotak
        # keluhan di bawahnya.
        kisi = QGridLayout()
        kisi.setHorizontalSpacing(18)
        kisi.setVerticalSpacing(10)
        kisi.setColumnStretch(0, 1)
        kisi.setColumnStretch(1, 1)

        self.label_nama = self._label_isian("Nama")
        self.label_nomor_pelanggan = self._label_isian("No. Pelanggan")

        kisi.addLayout(self._kolom(self.label_nama, self.isian_nama), 0, 0)
        kisi.addLayout(
            self._kolom(self.label_nomor_pelanggan, self.isian_nomor_pelanggan), 0, 1
        )
        kisi.addLayout(
            self._kolom(self._label_isian("Telepon"), self.isian_telepon), 1, 0
        )
        kisi.addLayout(self._kolom(self._label_isian("Email"), self.isian_email), 1, 1)
        kisi.addLayout(
            self._kolom(self._label_isian("Alamat"), self.isian_alamat), 2, 0, 1, 2
        )
        badan.addLayout(kisi)

        self.label_pelapor = QLabel("")
        self.label_pelapor.setWordWrap(True)
        badan.addWidget(self.label_pelapor)
        return kartu

    def _bangun_bagian_pengaduan(self) -> QWidget:
        kartu, badan = self._kartu("PENGADUAN", "Kata pengunjung")

        self.isian_deskripsi = QPlainTextEdit()
        self.isian_deskripsi.setPlaceholderText(
            "Keluhan menurut pengunjung, dengan kata-katanya sendiri"
        )
        self.isian_deskripsi.setMinimumHeight(TINGGI_DESKRIPSI)
        badan.addWidget(self.isian_deskripsi)

        self.hitung_deskripsi = self._penghitung()
        badan.addWidget(
            self.hitung_deskripsi, alignment=Qt.AlignmentFlag.AlignRight
        )
        return kartu

    def _bangun_bagian_catatan(self) -> QWidget:
        kartu, badan = self._kartu("CATATAN PETUGAS", "Tidak dibacakan ke pengunjung")

        self.isian_catatan = QPlainTextEdit()
        self.isian_catatan.setPlaceholderText(
            "Misalnya: berkas belum lengkap, diminta kembali membawa fotokopi."
        )
        self.isian_catatan.setMinimumHeight(TINGGI_CATATAN)
        badan.addWidget(self.isian_catatan)

        self.hitung_catatan = self._penghitung()
        badan.addWidget(self.hitung_catatan, alignment=Qt.AlignmentFlag.AlignRight)
        return kartu

    def _bangun_kaki(self) -> QWidget:
        """
        Kaki yang selalu terlihat, di luar area gulir.

        Tombol Simpan yang ikut tergulir keluar layar adalah tombol yang
        tidak ditemukan petugas ketika formulirnya panjang.
        """
        kaki = QFrame()
        kaki.setObjectName("kakiLembar")
        kaki.setStyleSheet(
            f"QFrame#kakiLembar {{ background: {SURFACE};"
            f" border-top: 1px solid {BORDER}; }}"
        )

        baris = QHBoxLayout(kaki)
        baris.setContentsMargins(22, 14, 22, 14)
        baris.setSpacing(10)

        self.label_keadaan = QLabel("")
        self.label_keadaan.setWordWrap(True)
        baris.addWidget(self.label_keadaan, stretch=1)

        self.tombol_tutup = tombol("Tutup")
        self.tombol_tutup.clicked.connect(self.reject)
        baris.addWidget(self.tombol_tutup)

        self.tombol_simpan = tombol("Simpan (Ctrl+S)", variant="primary", default=True)
        self.tombol_simpan.setMinimumHeight(38)
        self.tombol_simpan.clicked.connect(self.simpan)
        baris.addWidget(self.tombol_simpan)
        return kaki

    # -----------------------------------------------------------------
    # Potongan tampilan yang dipakai berulang
    # -----------------------------------------------------------------

    @staticmethod
    def _kartu(judul_bagian: str, petunjuk: str = "") -> tuple[QFrame, QVBoxLayout]:
        """Kartu berjudul; mengembalikan kartunya beserta susunan isinya."""
        kartu = QFrame()
        kartu.setObjectName("kartuBagian")
        kartu.setStyleSheet(
            f"QFrame#kartuBagian {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )

        susunan = QVBoxLayout(kartu)
        susunan.setContentsMargins(18, 14, 18, 14)
        susunan.setSpacing(10)

        kepala = QHBoxLayout()
        kepala.setSpacing(8)

        judul_label = QLabel(judul_bagian)
        judul_label.setProperty("kapsi", "true")
        kepala.addWidget(judul_label)

        if petunjuk:
            catatan = QLabel(f"· {petunjuk}")
            catatan.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
            )
            kepala.addWidget(catatan)

        kepala.addStretch()
        susunan.addLayout(kepala)
        return kartu, susunan

    @staticmethod
    def _kolom(label: QLabel, isian: QWidget) -> QVBoxLayout:
        """Label di ATAS isiannya, bukan di sampingnya.

        Label bersebelahan memaksa satu kolom selebar label terpanjang, dan
        pada dua isian per baris kolom itu memakan lebar yang dibutuhkan
        isiannya sendiri.
        """
        susunan = QVBoxLayout()
        susunan.setSpacing(4)
        susunan.addWidget(label)
        susunan.addWidget(isian)
        return susunan

    @staticmethod
    def _isian(batas: int, petunjuk: str) -> QLineEdit:
        isian = QLineEdit()
        isian.setMaxLength(batas)
        isian.setPlaceholderText(petunjuk)
        return isian

    @staticmethod
    def _label_isian(teks: str) -> QLabel:
        label = QLabel(teks)
        label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px; font-weight: 600;"
        )
        return label

    @staticmethod
    def _penghitung() -> QLabel:
        label = QLabel("")
        label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;")
        return label

    # =================================================================
    # Perilaku yang mengikuti isian
    # =================================================================

    def _sambungkan(self) -> None:
        for kotak in (self.isian_deskripsi, self.isian_catatan):
            kotak.textChanged.connect(self._perbarui_dinamis)
        for isian in (
            self.isian_nama,
            self.isian_nomor_pelanggan,
            self.isian_telepon,
            self.isian_email,
            self.isian_alamat,
        ):
            isian.textChanged.connect(self._perbarui_dinamis)

    @property
    def ada_pengaduan(self) -> bool:
        return bool(self.isian_deskripsi.toPlainText().strip())

    @property
    def ada_isian(self) -> bool:
        """Benar bila ada sesuatu yang layak disimpan."""
        return self.ada_pengaduan or bool(self.isian_catatan.toPlainText().strip())

    def _perbarui_dinamis(self) -> None:
        """
        Selaraskan kapsul, penanda wajib, dan penghitung dengan isian.

        Dijalankan pada setiap ketikan, dan karena itu tidak menyentuh
        database sama sekali — seluruhnya dihitung dari isi layar.
        """
        self._perbarui_kapsul()
        self._perbarui_wajib()
        self._perbarui_penghitung()
        self.tombol_simpan.setEnabled(self.ada_isian)
        self._perbarui_keadaan()

    def _perbarui_kapsul(self) -> None:
        if self.ada_pengaduan:
            self.kapsul.setText("PENGADUAN")
            self.kapsul.setStyleSheet(_gaya_kapsul(WARNING, WARNING_SOFT))
        elif self.ada_isian:
            self.kapsul.setText("CATATAN")
            self.kapsul.setStyleSheet(_gaya_kapsul(PRIMARY, PRIMARY_SOFT))
        else:
            self.kapsul.setText("KOSONG")
            self.kapsul.setStyleSheet(_gaya_kapsul(TEXT_MUTED, SURFACE_ALT))

    def _perbarui_wajib(self) -> None:
        """
        Tandai identitas sebagai wajib hanya setelah ada deskripsi.

        Kewajibannya memang bersyarat. Menandainya sejak formulir dibuka
        berarti menyalakan peringatan pada lembar yang mungkin hanya berisi
        catatan petugas — dan peringatan yang menyala tanpa sebab cepat
        berhenti dibaca.
        """
        wajib = self.ada_pengaduan
        pasangan = (
            (self.label_nama, self.isian_nama, "Nama"),
            (
                self.label_nomor_pelanggan,
                self.isian_nomor_pelanggan,
                "No. Pelanggan",
            ),
        )
        kurang: list[str] = []
        for label, isian, nama in pasangan:
            kosong = not isian.text().strip()
            label.setText(f"{nama} *" if wajib else nama)
            self._setel_wajib(isian, wajib and kosong)
            if wajib and kosong:
                kurang.append(nama)

        if kurang:
            self.label_pelapor.setText(
                "Wajib diisi untuk pengaduan: " + ", ".join(kurang) + "."
            )
            self.label_pelapor.setStyleSheet(
                f"color: {WARNING}; font-size: {FONT_SIZE_SMALL}px; font-weight: 600;"
            )
        else:
            self.label_pelapor.setText(
                "Telepon, email, dan alamat boleh dikosongkan."
                if wajib
                else "Seluruhnya boleh dikosongkan bila hanya menulis catatan petugas."
            )
            self.label_pelapor.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
            )

    @staticmethod
    def _setel_wajib(widget: QWidget, wajib: bool) -> None:
        """
        Nyalakan gaya "wajib" pada sebuah isian.

        unpolish/polish wajib: Qt sudah menghitung gaya widget ketika
        pertama digambar dan tidak menghitungnya ulang dengan sendirinya —
        property yang berubah tanpa ini tidak mengubah apa pun di layar.
        """
        if widget.property("wajib") == ("true" if wajib else None):
            return
        widget.setProperty("wajib", "true" if wajib else None)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _perbarui_penghitung(self) -> None:
        for kotak, label, batas in (
            (self.isian_deskripsi, self.hitung_deskripsi, PANJANG_DESKRIPSI),
            (self.isian_catatan, self.hitung_catatan, PANJANG_CATATAN),
        ):
            panjang = len(kotak.toPlainText().strip())
            label.setText(f"{panjang} / {batas}")
            if panjang > batas:
                warna, tebal = DANGER, "font-weight: 700;"
            elif panjang >= batas * AMBANG_PERINGATAN:
                warna, tebal = WARNING, "font-weight: 700;"
            else:
                warna, tebal = TEXT_MUTED, ""
            label.setStyleSheet(
                f"color: {warna}; font-size: {FONT_SIZE_SMALL}px; {tebal}"
            )

    # =================================================================
    # Isi
    # =================================================================

    def _muat(self) -> None:
        """Baca lembar yang sudah ada, bila antrian ini pernah ditulisi."""
        berhasil, lembar = jalankan_aman(
            self, lambda: self.note.ambil(self.antrian.id), "Gagal membaca catatan"
        )
        if berhasil and lembar is not None:
            self._tampilkan(lembar)
        self._perbarui_dinamis()

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

        if self.berubah:
            teks, warna = "Ada perubahan yang belum disimpan.", WARNING
        elif self.lembar is not None:
            teks = (
                f"Tersimpan {self.lembar.updated_at.strftime('%H:%M')} · "
                f"{self.lembar.officer_name or '-'}"
            )
            warna = TEXT_MUTED
        else:
            teks, warna = "Belum pernah disimpan.", TEXT_MUTED

        self.label_keadaan.setText(teks)
        self.label_keadaan.setStyleSheet(
            f"color: {warna}; font-size: {FONT_SIZE_SMALL}px;"
        )

    @property
    def _isi_layar(self) -> tuple[str, ...]:
        return (
            self.isian_nama.text().strip(),
            self.isian_nomor_pelanggan.text().strip(),
            self.isian_telepon.text().strip(),
            self.isian_email.text().strip(),
            self.isian_alamat.text().strip(),
            self.isian_deskripsi.toPlainText().strip(),
            self.isian_catatan.toPlainText().strip(),
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
        if tersimpan is None:
            return any(self._isi_layar)
        return self._isi_layar != (
            (tersimpan.nama or "").strip(),
            (tersimpan.nomor_pelanggan or "").strip(),
            (tersimpan.telepon or "").strip(),
            (tersimpan.email or "").strip(),
            (tersimpan.alamat or "").strip(),
            (tersimpan.deskripsi or "").strip(),
            (tersimpan.catatan or "").strip(),
        )

    # =================================================================
    # Tindakan
    # =================================================================

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
        self.label_keadaan.setStyleSheet(
            f"background: {SUCCESS_SOFT}; color: {SUCCESS};"
            f" border-radius: {RADIUS_SM}px; padding: 5px 10px;"
            f" font-size: {FONT_SIZE_SMALL}px; font-weight: 700;"
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
