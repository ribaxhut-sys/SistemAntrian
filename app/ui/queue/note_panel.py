"""
Ruang kerja petugas: keluhan pengunjung dan catatan petugas.

PANEL TETAP, bukan dialog. Menunggu Dilayani dan ruang kerja ini berbagi
satu tab di kolom kanan (lihat `service_page._bangun_panel_kanan`), dan
kolom kanan berpindah tab sendiri mengikuti status loket: Menunggu Dilayani
selagi loket kosong — saat petugas memilih siapa berikutnya — lalu ruang
kerja ini begitu nomor dipanggil, saat petugas mulai berbicara dengan
orangnya. Sebelumnya ruang kerja ini berupa dialog; dua isian saja tidak
lagi butuh jendela sendiri, dan modal justru satu langkah tambahan untuk
sesuatu yang ditulis di hampir setiap pelayanan.

DUA KOTAK SAJA. Identitas pelapor tetap di kartu Data Pelapor pada kolom
kiri (lihat `pelapor_form.py`), ditulis sambil BERTANYA kepada orang di
depan meja, sedangkan keluhan dan catatan ditulis sambil MENDENGARKAN.
Panel ini membaca dan menulis identitas itu lewat referensi `pelapor`
langsung — tidak menyalinnya — karena isian pelapor tetap terlihat dan
dapat disunting kapan pun selagi panel ini terbuka.

DESKRIPSI DAN CATATAN TETAP DUA KOTAK TERPISAH. Deskripsi adalah kata
pengunjung; catatan adalah penilaian petugas. Disatukan menjadi satu kotak,
penilaian internal ikut terbaca sebagai keluhan pelanggan oleh siapa pun
yang membuka lembar itu kemudian.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.note_service import PANJANG_CATATAN, PANJANG_DESKRIPSI, NoteService
from app.services.queue_service import QueueInfo
from app.ui.common import jalankan_aman, tombol
from app.ui.queue.pelapor_form import PelaporForm
from app.ui.style import (
    BORDER,
    DANGER,
    FONT_SIZE_SMALL,
    PRIMARY,
    PRIMARY_SOFT,
    RADIUS,
    RADIUS_SM,
    SUCCESS,
    SUCCESS_SOFT,
    SURFACE,
    SURFACE_ALT,
    TEXT_MUTED,
    WARNING,
    WARNING_SOFT,
)

#: Tinggi terkecil kedua kotak.
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


class NotePanel(QWidget):
    """Kotak keluhan dan catatan untuk antrian yang sedang ditangani."""

    def __init__(
        self,
        note: NoteService,
        pelapor: PelaporForm,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.note = note
        self.pelapor = pelapor
        self.antrian: QueueInfo | None = None
        #: Lembar yang tersimpan di database, atau None bila belum ada.
        self.lembar = None

        self._bangun_tampilan()
        self._sambungkan()
        self.set_antrian(None)

        # Ctrl+S sama seperti di mana pun. Petugas yang terbiasa menekannya
        # tidak boleh menemukan panel ini sebagai pengecualian.
        QShortcut(QKeySequence("Ctrl+S"), self, self.simpan)

    # =================================================================
    # Tampilan
    # =================================================================

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(0)

        # Kedua kartu dapat digulir. Kaki berisi tombol Simpan tetap di
        # tempatnya — tombol yang ikut tergulir keluar layar adalah tombol
        # yang tidak ditemukan petugas.
        gulir = QScrollArea()
        gulir.setWidgetResizable(True)
        gulir.setFrameShape(QFrame.Shape.NoFrame)
        gulir.setStyleSheet(f"QScrollArea {{ background: {SURFACE_ALT}; }}")

        isi = QWidget()
        isi.setStyleSheet(f"background: {SURFACE_ALT};")
        badan = QVBoxLayout(isi)
        badan.setContentsMargins(2, 2, 2, 2)
        badan.setSpacing(12)

        badan.addLayout(self._bangun_kepala())
        badan.addWidget(self._bangun_bagian_pengaduan(), stretch=3)
        badan.addWidget(self._bangun_bagian_catatan(), stretch=2)

        gulir.setWidget(isi)
        susunan.addWidget(gulir, stretch=1)
        susunan.addWidget(self._bangun_kaki())

    def _bangun_kepala(self) -> QHBoxLayout:
        """Baris tipis berisi kapsul keadaan lembar, rata kanan."""
        baris = QHBoxLayout()
        baris.addStretch()
        self.kapsul = QLabel("")
        self.kapsul.setAlignment(Qt.AlignmentFlag.AlignCenter)
        baris.addWidget(self.kapsul)
        return baris

    def _bangun_bagian_pengaduan(self) -> QWidget:
        kartu, badan = self._kartu("PENGADUAN")

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
        kartu, badan = self._kartu("CATATAN PETUGAS")

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
        baris.setContentsMargins(4, 10, 4, 2)
        baris.setSpacing(10)

        self.label_keadaan = QLabel("")
        self.label_keadaan.setWordWrap(True)
        baris.addWidget(self.label_keadaan, stretch=1)

        self.tombol_simpan = tombol("Simpan (Ctrl+S)", variant="primary")
        self.tombol_simpan.setMinimumHeight(36)
        self.tombol_simpan.clicked.connect(self.simpan)
        baris.addWidget(self.tombol_simpan)
        return kaki

    @staticmethod
    def _kartu(judul_bagian: str) -> tuple[QFrame, QVBoxLayout]:
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

    def _perbarui_dinamis(self) -> None:
        """
        Selaraskan kapsul, penghitung, tombol, dan Data Pelapor dengan isian.

        Dijalankan pada setiap ketikan, dan karena itu tidak menyentuh
        database sama sekali — seluruhnya dihitung dari isi layar.
        """
        self._perbarui_kapsul()
        self._perbarui_penghitung()
        self.pelapor.tandai_wajib(self.ada_pengaduan)
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

    # =================================================================
    # Isi
    # =================================================================

    def set_antrian(self, antrian: QueueInfo | None) -> None:
        """
        Pindahkan panel ke antrian lain, membaca lembarnya bila ada.

        Dijaga dengan nomor antrian, bukan dipanggil buta setiap
        `muat_ulang()`: memanggil ulang (F3) atau menunda (F4) tidak
        mengganti ANTRIAN-nya, dan membaca ulang dari database pada momen
        itu akan menimpa keluhan yang sedang diketik petugas.

        Berganti nomor WAJIB mengosongkan isian lebih dahulu. Identitas
        maupun keluhan yang tertinggal dari nomor sebelumnya berarti
        keluhan orang ini tersimpan atas nama orang lain.
        """
        nomor_baru = antrian.id if antrian is not None else None
        nomor_lama = self.antrian.id if self.antrian is not None else None
        self.antrian = antrian

        aktif = antrian is not None
        self.setEnabled(aktif)
        self.pelapor.set_aktif(aktif)

        if nomor_baru == nomor_lama:
            return

        self.lembar = None
        self.isian_deskripsi.blockSignals(True)
        self.isian_catatan.blockSignals(True)
        self.isian_deskripsi.setPlainText("")
        self.isian_catatan.setPlainText("")
        self.isian_deskripsi.blockSignals(False)
        self.isian_catatan.blockSignals(False)
        self.pelapor.kosongkan()

        if aktif:
            berhasil, lembar = jalankan_aman(
                self, lambda: self.note.ambil(antrian.id), "Gagal membaca catatan"
            )
            if berhasil and lembar is not None:
                self.lembar = lembar
                self.isian_deskripsi.setPlainText(lembar.deskripsi or "")
                self.isian_catatan.setPlainText(lembar.catatan or "")
                self.pelapor.isi(lembar)

        self._perbarui_dinamis()

    @property
    def _isi_layar(self) -> tuple[str, str]:
        return (
            self.isian_deskripsi.toPlainText().strip(),
            self.isian_catatan.toPlainText().strip(),
        )

    @property
    def berubah(self) -> bool:
        """Benar bila kedua kotak berbeda dari yang tersimpan."""
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
        Simpan lembar beserta identitas yang dibaca dari Data Pelapor.

        Mengembalikan True bila tersimpan. Dipakai baik oleh tombol/Ctrl+S
        maupun oleh `ServicePage.selesaikan()` sebelum menutup pelayanan —
        pelayanan yang ditutup dengan keluhan yang belum tersimpan berarti
        keluhan itu hilang tanpa dapat diketik ulang, karena yang
        menceritakannya sudah berdiri meninggalkan meja.
        """
        if self.antrian is None or not self.ada_isian:
            self._perbarui_keadaan(
                "Isi keluhan pengunjung atau catatan petugas lebih dahulu.", WARNING
            )
            return False

        kurang = self.pelapor.kurang if self.ada_pengaduan else []
        if kurang:
            self._perbarui_keadaan(
                "Lengkapi " + ", ".join(kurang) + " pada Data Pelapor.", WARNING
            )
            return False

        nilai = self.pelapor.nilai
        antrian = self.antrian
        berhasil, lembar = jalankan_aman(
            self,
            lambda: self.note.simpan(
                antrian.id,
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
        self._perbarui_keadaan(
            f"Tersimpan {lembar.updated_at.strftime('%H:%M:%S')}", SUCCESS
        )
        self.label_keadaan.setStyleSheet(
            f"background: {SUCCESS_SOFT}; color: {SUCCESS};"
            f" border-radius: {RADIUS_SM}px; padding: 5px 10px;"
            f" font-size: {FONT_SIZE_SMALL}px; font-weight: 700;"
        )
        return True
