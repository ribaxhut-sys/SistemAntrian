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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.logger import get_logger
from app.services.note_service import (
    MIN_HURUF_CATATAN,
    PANJANG_CATATAN,
    PANJANG_DESKRIPSI,
    PESAN_CATATAN_KURANG,
    NoteService,
    catatan_memadai,
    catatan_sama_dengan,
    jumlah_huruf_catatan,
    samakan_catatan,
)
from app.services.queue_service import QueueInfo
from app.ui.common import jalankan_aman
from app.ui.queue.pelapor_form import PelaporForm
from app.ui.daftar_frasa import DaftarFrasa
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
TINGGI_CATATAN = 72

#: Penghitung huruf mulai memperingatkan pada porsi ini dari batasnya.
#:
#: Diperingatkan sebelum mentok, bukan sesudah. Petugas yang baru tahu
#: batasnya ketika penolakan muncul harus memotong kalimat orang lain
#: sambil orangnya menunggu.
AMBANG_PERINGATAN = 0.9

#: Jeda simpan draf otomatis, dalam milidetik. Tombol Simpan sendiri sudah
#: menjadi Simpan & Selesai, jadi tulisan yang belum rampung dijaga di sini.
JEDA_SIMPAN_OTOMATIS = 15_000

#: Peringatan bila catatan persis sama dengan catatan nomor sebelumnya.
PESAN_CATATAN_SAMA = (
    "Catatan sama dengan nomor sebelumnya. Sesuaikan dengan pelanggan ini."
)

logger = get_logger("catatan.panel")


def _tanpa_titik_akhir(teks: str) -> str:
    """Kalimat tanpa titik penutupnya, supaya cocok di tengah rangkaian."""
    return teks.rstrip(". ")


class TombolSelesai(QPushButton):
    """
    Tombol Simpan & Selesai: menyala hanya bila DUA syarat terpenuhi.

    Izin datang dari layar pelayanan (nomor sedang dilayani) lewat
    `setEnabled`, seperti tombol aksi lain; syarat isi datang dari panel
    (catatan memadai) lewat `setel_syarat`. Menumpuk keduanya di sini
    membuat loop penyalaan tombol di layar pelayanan tetap berlaku tanpa
    bisa mengabaikan syarat catatan.
    """

    def __init__(self, teks: str, parent: QWidget | None = None) -> None:
        super().__init__(teks, parent)
        self._izin = False
        self._syarat = False
        self.setProperty("variant", "success")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoDefault(False)
        super().setEnabled(False)

    def setEnabled(self, aktif: bool) -> None:  # noqa: N802 - nama Qt
        self._izin = bool(aktif)
        self._terapkan()

    def setel_syarat(self, terpenuhi: bool) -> None:
        self._syarat = bool(terpenuhi)
        self._terapkan()

    def _terapkan(self) -> None:
        super().setEnabled(self._izin and self._syarat)


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

        self._pewaktu_otomatis = QTimer(self)
        self._pewaktu_otomatis.setInterval(JEDA_SIMPAN_OTOMATIS)
        self._pewaktu_otomatis.timeout.connect(self._saat_pewaktu_otomatis)
        self._pewaktu_otomatis.start()

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
        # Tanpa kartu: bingkai dan bantalannya memakan tempat, dan catatan
        # hanyalah isian lanjutan di bawah pengaduan.
        kartu, badan = self._kartu("CATATAN PETUGAS", dengan_kartu=False)

        self.isian_catatan = QPlainTextEdit()
        self.isian_catatan.setPlaceholderText(
            "Misalnya: berkas belum lengkap, diminta kembali membawa fotokopi."
        )
        # Kotak catatan lega (empat baris) dan boleh tumbuh bila ada ruang;
        # lebih tinggi dari ini membuat panel bergulir pada layar pendek.
        self.isian_catatan.setMinimumHeight(
            max(TINGGI_CATATAN, 4 * self.isian_catatan.fontMetrics().lineSpacing() + 16)
        )

        # Kalimat cepat: satu klik menyisipkan kalimat ke catatan, dan
        # petugas tetap bisa menambah atau mengubahnya. Daftarnya milik
        # jenis layanan nomor yang dilayani (lihat `set_antrian`).
        self.daftar_frasa = DaftarFrasa()
        self.daftar_frasa.dipilih.connect(self.sisipkan_frasa)
        badan.addWidget(self.daftar_frasa)
        #: Catatan petugas ini pada nomor lain hari ini (bahan peringatan).
        self._catatan_sebelumnya: list[str] = []
        self._frasa_bawaan_layar: list[str] = []

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

        # Satu tombol untuk menyimpan dan menutup pelayanan. Kliknya
        # disambungkan oleh ServicePage (ia yang memegang antrian dan
        # memanggil `queue.complete`), yang juga mendaftarkannya sebagai
        # aksi "selesai".
        self.tombol_selesai = TombolSelesai("Simpan && Selesai  ·  F8")
        self.tombol_selesai.setMinimumHeight(36)
        baris.addWidget(self.tombol_selesai)
        return kaki

    @staticmethod
    def _kartu(
        judul_bagian: str, *, dengan_kartu: bool = True
    ) -> tuple[QFrame, QVBoxLayout]:
        """
        Bagian berjudul; mengembalikan wadahnya beserta susunan isinya.

        `dengan_kartu=False`: tanpa bingkai, latar, dan bantalan; hanya
        judul kecil di atas isinya.
        """
        kartu = QFrame()
        kartu.setObjectName("kartuBagian")
        susunan = QVBoxLayout(kartu)
        if dengan_kartu:
            kartu.setStyleSheet(
                f"QFrame#kartuBagian {{ background: {SURFACE};"
                f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
            )
            susunan.setContentsMargins(16, 12, 16, 12)
        else:
            kartu.setStyleSheet("QFrame#kartuBagian { background: transparent; border: none; }")
            susunan.setContentsMargins(2, 0, 2, 0)
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

    @property
    def catatan_sama_dengan_sebelumnya(self) -> bool:
        """
        Benar bila catatan persis sama dengan catatan petugas ini pada nomor lain.

        Hanya peringatan, tidak menghalangi. Catatan yang seluruhnya terdiri
        dari kalimat cepat dikecualikan: memakai tombol yang sama untuk
        pelayanan yang sama memang wajar.
        """
        catatan = self.isian_catatan.toPlainText()
        if not catatan_sama_dengan(catatan, self._catatan_sebelumnya):
            return False
        return not self._hanya_kalimat_cepat(catatan)

    def _hanya_kalimat_cepat(self, catatan: str) -> bool:
        """Benar bila isi catatan hanya rangkaian kalimat cepat (koma atau baris baru)."""
        sisa = samakan_catatan(catatan)
        ada = False
        for frasa in sorted(self._frasa_bawaan_layar, key=len, reverse=True):
            potongan = _tanpa_titik_akhir(samakan_catatan(frasa))
            if potongan and potongan in sisa:
                sisa = sisa.replace(potongan, "")
                ada = True
        return ada and not sisa.strip(" ,.;\n")

    @property
    def catatan_memadai(self) -> bool:
        """Benar bila catatan petugas cukup untuk menyelesaikan pelayanan."""
        return catatan_memadai(self.isian_catatan.toPlainText())

    def _perbarui_dinamis(self) -> None:
        """
        Selaraskan kapsul, penghitung, tombol, dan Data Pelapor dengan isian.

        Dijalankan pada setiap ketikan, dan karena itu tidak menyentuh
        database sama sekali — seluruhnya dihitung dari isi layar.
        """
        self._perbarui_kapsul()
        self._perbarui_penghitung()
        self._perbarui_frasa_terpakai()
        self.pelapor.tandai_wajib(self.ada_pengaduan)
        self.tombol_selesai.setel_syarat(self.catatan_memadai)
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
            if kotak is self.isian_catatan and not self.catatan_memadai:
                huruf = jumlah_huruf_catatan(kotak.toPlainText())
                label.setText(
                    f"Minimal {MIN_HURUF_CATATAN} huruf "
                    f"({min(huruf, MIN_HURUF_CATATAN)}/{MIN_HURUF_CATATAN}) · "
                    f"{panjang} / {batas}"
                )
                warna, tebal = WARNING, "font-weight: 700;"
            elif panjang > batas:
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

        if self.catatan_sama_dengan_sebelumnya:
            teks, warna = PESAN_CATATAN_SAMA, WARNING
        elif self.berubah:
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

        self._muat_frasa(antrian.category_id if aktif else None)
        self._muat_catatan_sebelumnya(antrian.id if aktif else None)
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

    # =================================================================
    # Kalimat cepat
    # =================================================================

    def _muat_frasa(self, category_id: int | None) -> None:
        """Pasang kalimat cepat milik jenis layanan nomor ini."""
        self._frasa_bawaan_layar = []
        self.daftar_frasa.set_kalimat([])
        if category_id is None:
            return
        try:
            daftar = self.note.frasa_cepat(category_id)
        except Exception:  # noqa: BLE001 - kalimat cepat hanya pelengkap
            logger.warning("Kalimat cepat gagal dibaca", exc_info=True)
            return
        self._frasa_bawaan_layar = list(daftar)
        self.daftar_frasa.set_kalimat(daftar)
        self._perbarui_frasa_terpakai()

    def _perbarui_frasa_terpakai(self) -> None:
        """Tandai ✓ kalimat yang sudah ada di catatan."""
        isi = samakan_catatan(self.isian_catatan.toPlainText())
        for urutan, butir in enumerate(self.daftar_frasa.item):
            self.daftar_frasa.tandai_terpakai(
                urutan, _tanpa_titik_akhir(samakan_catatan(butir.kalimat)) in isi
            )

    def _muat_catatan_sebelumnya(self, queue_id: int | None) -> None:
        self._catatan_sebelumnya = []
        if queue_id is None:
            return
        try:
            self._catatan_sebelumnya = self.note.catatan_terakhir_saya(queue_id)
        except Exception:  # noqa: BLE001 - peringatan hanya pelengkap
            logger.warning("Catatan sebelumnya gagal dibaca", exc_info=True)

    def sisipkan_frasa(self, kalimat: str) -> None:
        """
        Tambahkan kalimat ke catatan, dirangkai dengan koma bila sudah ada isinya.

        Koma, bukan baris baru, supaya beberapa kalimat cukup di kotak dua
        baris. Titik di ujung catatan lama dibuang agar rangkaiannya
        terbaca "A, B." dan bukan "A., B.".
        """
        sekarang = self.isian_catatan.toPlainText().rstrip()
        if sekarang:
            sekarang = f"{sekarang.rstrip('.').rstrip()}, {kalimat}"
        else:
            sekarang = kalimat
        self.isian_catatan.setPlainText(sekarang)
        kursor = self.isian_catatan.textCursor()
        kursor.movePosition(kursor.MoveOperation.End)
        self.isian_catatan.setTextCursor(kursor)
        self.isian_catatan.setFocus()

    def fokus_catatan(self) -> None:
        """Arahkan petugas ke kotak catatan beserta alasan tombolnya belum menyala."""
        self.isian_catatan.setFocus()
        self._perbarui_keadaan(PESAN_CATATAN_KURANG, WARNING)

    # =================================================================
    # Simpan draf otomatis
    # =================================================================

    def _saat_pewaktu_otomatis(self) -> None:
        """
        Detak simpan otomatis: hanya bila jendelanya sungguh tampil.

        Panel yang sudah ditutup tetapi belum dihancurkan (jendela ditutup,
        atau widget uji yang menunggu dibersihkan) tidak boleh menulis ke
        database lama-lama sesudahnya, atas nama sesi siapa pun yang kini
        masuk. Tab lain pada layar yang sama tetap dihitung tampil.
        """
        if self.window().isVisible():
            self.simpan_otomatis()

    def simpan_otomatis(self) -> None:
        """
        Simpan draf diam-diam bila ada perubahan yang sah disimpan.

        Tidak memunculkan dialog apa pun: gagal pun hanya meninggalkan
        pesan di kaki panel, dan ketikan petugas tidak terganggu. Hanya
        berjalan bila identitas pelapor sudah lengkap, karena pengaduan
        tanpa nama tidak boleh disimpan setengah-setengah.
        """
        if self.antrian is None or not self.ada_isian or not self.berubah:
            return
        if self.ada_pengaduan and self.pelapor.kurang:
            return
        nilai = self.pelapor.nilai
        try:
            lembar = self.note.simpan(
                self.antrian.id,
                nama=nilai.get("nama", ""),
                nomor_pelanggan=nilai.get("nomor_pelanggan", ""),
                telepon=nilai.get("telepon", ""),
                email=nilai.get("email", ""),
                alamat=nilai.get("alamat", ""),
                deskripsi=self.isian_deskripsi.toPlainText(),
                catatan=self.isian_catatan.toPlainText(),
            )
        except Exception:  # noqa: BLE001 - draf otomatis tidak boleh mengganggu
            logger.warning("Simpan draf otomatis gagal", exc_info=True)
            self._perbarui_keadaan("Draf belum tersimpan otomatis.", WARNING)
            return
        self.lembar = lembar
        self._perbarui_keadaan()

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
