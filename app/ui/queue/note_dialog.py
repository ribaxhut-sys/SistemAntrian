"""
Ruang kerja petugas: keluhan pengunjung dan catatan petugas.

DUA KOTAK SAJA. Identitas pelapor tinggal di layar pelayanan (lihat
`pelapor_form.py`) karena ditulis sambil BERTANYA kepada orang di depan
meja — nama, nomor pelanggan, telepon — sedangkan keluhannya ditulis
sambil MENDENGARKAN. Isian pendek yang selalu terlihat dapat diisi
seketika; kotak panjang yang butuh ruang mendapat dialognya sendiri.

DESKRIPSI DAN CATATAN TETAP DUA KOTAK TERPISAH. Deskripsi adalah kata
pengunjung; catatan adalah penilaian petugas. Disatukan menjadi satu kotak,
penilaian internal ikut terbaca sebagai keluhan pelanggan oleh siapa pun
yang membuka lembar itu kemudian.

Dialog inilah yang menyimpan seluruh lembar — kedua kotak ini beserta
identitas yang dibacanya dari layar pelayanan. Lembar tetap satu baris di
database, dan identitas tanpa keluhan maupun catatan tidak pernah tersimpan
sendirian: itu hanya akan menjadi nama pengunjung tanpa satu pun alasan.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.note_service import (
    PANJANG_CATATAN,
    PANJANG_DESKRIPSI,
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

#: Peringatan tetap di atas kotak keluhan.
#:
#: Lembar ini satu-satunya tempat data pribadi di aplikasi ini, dan petugas
#: yang sedang terburu-buru tidak akan mengingat itu. Kalimatnya menyebut
#: apa yang TIDAK perlu ditulis, bukan sekadar mengimbau berhati-hati —
#: imbauan tanpa isi tidak mengubah apa pun.
PERINGATAN = (
    "Isi seperlunya. Jangan menyalin NIK, nomor rekening, atau data lain "
    "yang tidak dibutuhkan untuk menindaklanjuti pengaduan ini."
)

#: Tinggi terkecil kedua kotak.
#:
#: Kotak setinggi satu baris membuat petugas mengetik keluhan panjang lewat
#: lubang intip: yang sudah diketik menggulung ke atas dan tidak terbaca
#: lagi saat hendak diperiksa ulang sebelum disimpan.
TINGGI_DESKRIPSI = 150
TINGGI_CATATAN = 110

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
    """Kotak keluhan dan catatan untuk satu nomor antrian."""

    def __init__(
        self,
        note: NoteService,
        antrian: QueueInfo,
        identitas: Callable[[], dict[str, str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.note = note
        self.antrian = antrian
        # Dibaca pada saat Simpan ditekan, bukan disalin saat dialog dibuka:
        # yang berlaku adalah isian terakhir di layar pelayanan.
        self.identitas = identitas or (lambda: {})
        #: Lembar yang tersimpan di database, atau None bila belum ada.
        self.lembar: NoteInfo | None = None
        #: Benar bila ada yang tersimpan selama dialog ini terbuka. Dipakai
        #: panel pelayanan untuk menyegarkan baris ringkasnya.
        self.tersimpan = False

        self.setWindowTitle(f"Pengaduan & Catatan — {antrian.queue_number}")
        self.setMinimumSize(680, 560)

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

        isi = QWidget()
        isi.setStyleSheet(f"background: {SURFACE_ALT};")
        badan = QVBoxLayout(isi)
        badan.setContentsMargins(22, 16, 22, 16)
        badan.setSpacing(12)

        badan.addWidget(self._bangun_peringatan())
        badan.addWidget(self._bangun_bagian_pengaduan(), stretch=3)
        badan.addWidget(self._bangun_bagian_catatan(), stretch=2)

        susunan.addWidget(isi, stretch=1)
        susunan.addWidget(self._bangun_kaki())

    def _bangun_kepala(self) -> QWidget:
        """
        Kepala dialog: nomor antrian, pelapornya, dan kapsul keadaan.

        Nomor dibuat besar karena satu-satunya kekeliruan yang benar-benar
        merugikan di formulir ini adalah menuliskan keluhan seseorang pada
        nomor milik orang lain. Nama pelapor ikut disebut di sini — ia
        diketik di layar yang sekarang tertutup dialog ini, dan tanpa
        disebutkan tidak ada cara memastikannya tanpa menutup dialog.
        """
        kepala = QFrame()
        kepala.setObjectName("kepalaLembar")
        kepala.setStyleSheet(
            f"QFrame#kepalaLembar {{ background: {SURFACE};"
            f" border-bottom: 1px solid {BORDER}; }}"
        )

        baris = QHBoxLayout(kepala)
        baris.setContentsMargins(22, 14, 22, 14)
        baris.setSpacing(14)

        teks = QVBoxLayout()
        teks.setSpacing(2)

        rincian = [self.antrian.category_name, self.antrian.counter_name]
        nomor = QLabel(
            f"{self.antrian.queue_number}"
            f"<span style='font-size:{FONT_SIZE_SMALL}px; color:{TEXT_MUTED};'>"
            f"   {' · '.join(r for r in rincian if r)}</span>"
        )
        nomor.setStyleSheet(
            f"color: {TEXT}; font-size: {FONT_SIZE_XL}px; font-weight: 800;"
        )
        teks.addWidget(nomor)

        self.label_pelapor = QLabel("")
        self.label_pelapor.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )
        teks.addWidget(self.label_pelapor)
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
            f" border-radius: {RADIUS_SM}px; padding: 8px 12px;"
            f" font-size: {FONT_SIZE_SMALL}px;"
        )
        return peringatan

    def _bangun_bagian_pengaduan(self) -> QWidget:
        kartu, badan = self._kartu("PENGADUAN", "Kata pengunjung")

        self.isian_deskripsi = QPlainTextEdit()
        self.isian_deskripsi.setPlaceholderText(
            "Keluhan menurut pengunjung, dengan kata-katanya sendiri"
        )
        self.isian_deskripsi.setMinimumHeight(TINGGI_DESKRIPSI)
        badan.addWidget(self.isian_deskripsi, stretch=1)

        self.hitung_deskripsi = self._penghitung()
        badan.addWidget(self.hitung_deskripsi, alignment=Qt.AlignmentFlag.AlignRight)
        return kartu

    def _bangun_bagian_catatan(self) -> QWidget:
        kartu, badan = self._kartu("CATATAN PETUGAS", "Tidak dibacakan ke pengunjung")

        self.isian_catatan = QPlainTextEdit()
        self.isian_catatan.setPlaceholderText(
            "Misalnya: berkas belum lengkap, diminta kembali membawa fotokopi."
        )
        self.isian_catatan.setMinimumHeight(TINGGI_CATATAN)
        badan.addWidget(self.isian_catatan, stretch=1)

        self.hitung_catatan = self._penghitung()
        badan.addWidget(self.hitung_catatan, alignment=Qt.AlignmentFlag.AlignRight)
        return kartu

    def _bangun_kaki(self) -> QWidget:
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
        susunan.setContentsMargins(16, 12, 16, 12)
        susunan.setSpacing(8)

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

    @property
    def ada_pengaduan(self) -> bool:
        return bool(self.isian_deskripsi.toPlainText().strip())

    @property
    def ada_isian(self) -> bool:
        """Benar bila ada sesuatu yang layak disimpan."""
        return self.ada_pengaduan or bool(self.isian_catatan.toPlainText().strip())

    @property
    def kurang(self) -> list[str]:
        """
        Isian identitas yang wajib tetapi masih kosong di layar pelayanan.

        Kosong bila tidak ada deskripsi: catatan petugas boleh berdiri
        sendiri tanpa identitas siapa pun.
        """
        if not self.ada_pengaduan:
            return []
        nilai = self.identitas()
        hasil = []
        if not (nilai.get("nama") or "").strip():
            hasil.append("Nama")
        if not (nilai.get("nomor_pelanggan") or "").strip():
            hasil.append("No. Pelanggan")
        return hasil

    def _perbarui_dinamis(self) -> None:
        """
        Selaraskan kapsul, penghitung, dan tombol dengan isian.

        Dijalankan pada setiap ketikan, dan karena itu tidak menyentuh
        database sama sekali — seluruhnya dihitung dari isi layar.
        """
        self._perbarui_kapsul()
        self._perbarui_penghitung()
        self._perbarui_pelapor()
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

    def _perbarui_pelapor(self) -> None:
        """
        Sebutkan pelapor yang terbaca dari layar pelayanan.

        Kekurangannya disebut di sini, bukan hanya saat Simpan ditolak:
        isiannya berada di layar yang sedang tertutup dialog ini, sehingga
        petugas tidak dapat melihat sendiri apa yang belum diisi.
        """
        kurang = self.kurang
        if kurang:
            self.label_pelapor.setText(
                "Belum diisi di layar pelayanan: " + ", ".join(kurang)
            )
            self.label_pelapor.setStyleSheet(
                f"color: {WARNING}; font-size: {FONT_SIZE_SMALL}px; font-weight: 600;"
            )
            return

        nilai = self.identitas()
        bagian = [
            (nilai.get("nama") or "").strip(),
            (nilai.get("nomor_pelanggan") or "").strip(),
        ]
        terisi = " · ".join(b for b in bagian if b)
        self.label_pelapor.setText(terisi or "Tanpa data pelapor")
        self.label_pelapor.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )

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
            self.lembar = lembar
            self.isian_deskripsi.setPlainText(lembar.deskripsi or "")
            self.isian_catatan.setPlainText(lembar.catatan or "")
        self._perbarui_dinamis()

    def _perbarui_keadaan(self, pesan: str = "", warna: str = "") -> None:
        gaya_kapsul = ""
        if pesan:
            teks = pesan
            warna = warna or TEXT_MUTED
            tebal = " font-weight: 700;"
        elif self.berubah:
            teks, warna, tebal = "Ada perubahan yang belum disimpan.", WARNING, ""
        elif self.lembar is not None:
            teks = (
                f"Tersimpan {self.lembar.updated_at.strftime('%H:%M')} · "
                f"{self.lembar.officer_name or '-'}"
            )
            warna, tebal = TEXT_MUTED, ""
        else:
            teks, warna, tebal = "Belum pernah disimpan.", TEXT_MUTED, ""

        self.label_keadaan.setText(teks)
        self.label_keadaan.setStyleSheet(
            f"color: {warna}; font-size: {FONT_SIZE_SMALL}px;{tebal}{gaya_kapsul}"
        )

    @property
    def _isi_layar(self) -> tuple[str, str]:
        return (
            self.isian_deskripsi.toPlainText().strip(),
            self.isian_catatan.toPlainText().strip(),
        )

    @property
    def berubah(self) -> bool:
        """
        Benar bila kedua kotak berbeda dari yang tersimpan.

        Identitas TIDAK ikut dihitung: isiannya tetap ada di layar pelayanan
        setelah dialog ini ditutup, sehingga menutup dialog tidak
        menghilangkannya. Menanyakannya di sini hanya akan menjadi
        pertanyaan yang muncul tanpa ada yang benar-benar dibuang.
        """
        if self.lembar is None:
            return any(self._isi_layar)
        return self._isi_layar != (
            (self.lembar.deskripsi or "").strip(),
            (self.lembar.catatan or "").strip(),
        )

    # =================================================================
    # Tindakan
    # =================================================================

    def simpan(self) -> bool:
        """
        Simpan lembar beserta identitas yang dibaca dari layar pelayanan.

        Dialog TIDAK ditutup sendiri setelah menyimpan. Petugas sering
        menyimpan di tengah pembicaraan lalu meneruskan mengetik; dialog
        yang menghilang begitu Ctrl+S ditekan memaksanya membuka lagi.
        """
        if not self.ada_isian:
            self._perbarui_keadaan(
                "Isi keluhan pengunjung atau catatan petugas lebih dahulu.", WARNING
            )
            return False

        # Diperiksa di sini, bukan dibiarkan ditolak service: isian yang
        # kurang berada di layar yang sedang tertutup dialog ini, dan
        # petugas perlu diberi tahu HARUS MENUTUP dialog untuk mengisinya.
        kurang = self.kurang
        if kurang:
            self._perbarui_keadaan(
                "Lengkapi " + ", ".join(kurang) + " pada Data Pelapor di layar "
                "pelayanan, lalu simpan lagi.",
                WARNING,
            )
            self._perbarui_pelapor()
            return False

        nilai = self.identitas()
        berhasil, lembar = jalankan_aman(
            self,
            lambda: self.note.simpan(
                self.antrian.id,
                nama=nilai.get("nama", ""),
                nomor_pelanggan=nilai.get("nomor_pelanggan", ""),
                telepon=nilai.get("telepon", ""),
                email=nilai.get("email", ""),
                alamat=nilai.get("alamat", ""),
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
