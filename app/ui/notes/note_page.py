"""
Layar Pengaduan: mencari dan membaca lembar yang pernah ditulis petugas.

Tanpa layar ini, "semua petugas boleh membaca" tidak berarti apa-apa —
tidak ada satu pun jalan untuk membuka lembar milik antrian yang sudah
lewat, dan pengunjung yang kembali esok hari ke loket lain akan diminta
menceritakan keluhannya dari awal.

Layar ini MEMBACA. Satu-satunya tindakan yang mengubah sesuatu di sini
adalah Hapus, dan tombolnya hanya hidup bagi ADMIN. Menyunting pengaduan
lama dilakukan di panel pelayanan pada hari yang sama, bukan dari sini:
pengaduan yang masih bisa diubah berhari-hari kemudian tidak berguna
sebagai bukti apa pun.

Menyegar sendiri secara berkala, seperti Ringkasan Harian — petugas lain
terus menulis lembar baru sepanjang hari, dan layar yang dibuka lalu
dibiarkan terbuka tidak boleh menyiratkan bahwa lembar seseorang tidak
pernah masuk. Penyegaran berkala memakai kriteria pencarian TERAKHIR
YANG DISUBMIT, bukan apa pun yang sedang diketik di kotak pencarian:
pencarian sengaja hanya berjalan saat Enter/Cari ditekan (lihat komentar
pada `isian_cari`), dan penyegaran diam-diam tidak boleh mendahului
petugas yang belum selesai mengetik kata kuncinya.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import clock
from app.services.auth_service import AuthService
from app.services.note_service import NoteInfo, NoteService
from app.services.permissions import Permission
from app.ui.common import jalankan_aman, judul, keterangan, konfirmasi, tombol
from app.ui.style import (
    BORDER,
    FONT_SIZE_LARGE,
    FONT_SIZE_SMALL,
    RADIUS,
    SURFACE,
    TEXT,
    TEXT_MUTED,
)
from app.utils.formatting import hari_dan_tanggal, jam

#: Rentang tanggal bawaan saat penyaringan tanggal dinyalakan.
#:
#: Sebulan ke belakang, bukan hari ini saja: yang dicari petugas hampir
#: selalu kejadian beberapa hari lalu — pengunjung yang mengadu hari ini
#: tidak perlu dicari, orangnya sedang berdiri di depan meja.
HARI_BAWAAN = 30

#: Jeda penyegaran otomatis, dalam milidetik.
#:
#: Sama dengan bawaan Ringkasan Harian. Layar ini dibaca berkali-kali
#: sehari oleh lebih dari satu orang; 30 detik cukup segar tanpa membebani
#: database dengan query beruntun.
SELANG_PENYEGARAN_MS = 30_000


class NotePage(QWidget):
    """Pencarian pengaduan dan catatan pada cabang yang sedang aktif."""

    def __init__(
        self,
        note: NoteService,
        auth: AuthService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.note = note
        self.auth = auth
        self.hasil: list[NoteInfo] = []
        #: Kriteria pencarian yang TERAKHIR DISUBMIT (Cari/Enter/centang),
        #: dipakai ulang oleh penyegaran otomatis — lihat `_segarkan_otomatis`.
        self._kata_terakhir = ""
        self._dari_terakhir: date | None = None
        self._sampai_terakhir: date | None = None
        self._hanya_pengaduan_terakhir = False

        self._bangun_tampilan()
        self.muat_ulang()
        self._pasang_penyegar()

    def _pasang_penyegar(self) -> None:
        """
        Segarkan berkala supaya lembar baru dari petugas lain ikut terlihat.

        Bukan `muat_ulang()` yang disambungkan, melainkan `_segarkan_otomatis`:
        yang belakangan memakai kriteria TERAKHIR DISUBMIT, bukan apa pun
        yang sedang diketik di kotak pencarian saat timer kebetulan berbunyi.
        """
        self.penyegar = QTimer(self)
        self.penyegar.timeout.connect(self._segarkan_otomatis)
        self.penyegar.start(SELANG_PENYEGARAN_MS)

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    @property
    def boleh_hapus(self) -> bool:
        """Hanya ADMIN. Penegakannya tetap di service; ini sekadar tombol."""
        if self.auth is None:
            return False
        sesi = self.auth.current_session
        return sesi is not None and Permission.NOTE_DELETE in sesi.permissions

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(12)

        susunan.addWidget(judul("Pengaduan & Catatan"))
        susunan.addWidget(
            keterangan(
                "Berisi data pribadi pelapor. Buka seperlunya, dan jangan "
                "menyalinnya ke luar aplikasi."
            )
        )
        susunan.addLayout(self._bangun_penyaring())

        isi = QHBoxLayout()
        isi.setSpacing(16)
        isi.addWidget(self._bangun_tabel(), stretch=5)
        isi.addWidget(self._bangun_rincian(), stretch=4)
        susunan.addLayout(isi, stretch=1)

        self.label_kosong = QLabel("")
        self.label_kosong.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(self.label_kosong)

    def _bangun_penyaring(self) -> QHBoxLayout:
        baris = QHBoxLayout()
        baris.setSpacing(10)

        self.isian_cari = QLineEdit()
        self.isian_cari.setPlaceholderText(
            "Cari nama, nomor pelanggan, isi pengaduan, atau nomor antrian"
        )
        # returnPressed, bukan textChanged: setiap huruf yang diketik
        # berarti satu query ke database, dan pencarian LIKE tanpa awalan
        # tetap memindai seluruh tabel yang tidak pernah dibersihkan.
        self.isian_cari.returnPressed.connect(self.muat_ulang)
        baris.addWidget(self.isian_cari, stretch=1)

        self.centang_tanggal = QCheckBox("Batasi tanggal")
        self.centang_tanggal.toggled.connect(self._tanggal_dialihkan)
        baris.addWidget(self.centang_tanggal)

        hari_ini = clock.today()
        self.tanggal_dari = QDateEdit()
        self.tanggal_dari.setCalendarPopup(True)
        self.tanggal_dari.setDisplayFormat("dd/MM/yyyy")
        self.tanggal_dari.setDate(
            QDate(*(hari_ini - timedelta(days=HARI_BAWAAN)).timetuple()[:3])
        )
        baris.addWidget(self.tanggal_dari)

        baris.addWidget(QLabel("s.d."))

        self.tanggal_sampai = QDateEdit()
        self.tanggal_sampai.setCalendarPopup(True)
        self.tanggal_sampai.setDisplayFormat("dd/MM/yyyy")
        self.tanggal_sampai.setDate(QDate(*hari_ini.timetuple()[:3]))
        baris.addWidget(self.tanggal_sampai)

        self.centang_pengaduan = QCheckBox("Hanya pengaduan")
        self.centang_pengaduan.toggled.connect(self.muat_ulang)
        baris.addWidget(self.centang_pengaduan)

        self.tombol_cari = tombol("Cari", variant="primary")
        self.tombol_cari.clicked.connect(self.muat_ulang)
        baris.addWidget(self.tombol_cari)

        self._tanggal_dialihkan(False)
        return baris

    def _bangun_tabel(self) -> QWidget:
        self.tabel = QTableWidget(0, 5)
        self.tabel.setHorizontalHeaderLabels(
            ["Tanggal", "Nomor", "Nama", "No. Pelanggan", "Isi"]
        )
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.currentCellChanged.connect(lambda *_: self._pilih_baris())

        kepala = self.tabel.horizontalHeader()
        kepala.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        kepala.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        return self.tabel

    def _bangun_rincian(self) -> QWidget:
        bingkai = QFrame()
        bingkai.setObjectName("panelRincian")
        bingkai.setStyleSheet(
            f"QFrame#panelRincian {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )

        susunan = QVBoxLayout(bingkai)
        susunan.setContentsMargins(18, 14, 18, 14)
        susunan.setSpacing(8)

        self.label_nomor = QLabel("—")
        self.label_nomor.setStyleSheet(
            f"color: {TEXT}; font-size: {FONT_SIZE_LARGE}px; font-weight: 800;"
        )
        susunan.addWidget(self.label_nomor)

        self.label_meta = QLabel("")
        self.label_meta.setWordWrap(True)
        self.label_meta.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
        )
        susunan.addWidget(self.label_meta)

        # Rincian dibungkus area bergulir: alamat dan deskripsi panjangnya
        # tidak terbatas, dan panel yang ikut memanjang mendorong tombol
        # Hapus keluar dari layar.
        gulir = QScrollArea()
        gulir.setWidgetResizable(True)
        gulir.setFrameShape(QFrame.Shape.NoFrame)

        isi = QWidget()
        self.susunan_rincian = QVBoxLayout(isi)
        self.susunan_rincian.setContentsMargins(0, 0, 0, 0)
        self.susunan_rincian.setSpacing(10)
        self.susunan_rincian.addStretch()
        gulir.setWidget(isi)
        susunan.addWidget(gulir, stretch=1)

        self.tombol_hapus = tombol("Hapus Lembar", variant="danger")
        self.tombol_hapus.clicked.connect(self.hapus)
        self.tombol_hapus.setVisible(self.boleh_hapus)
        susunan.addWidget(self.tombol_hapus)

        return bingkai

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def _tanggal_dialihkan(self, aktif: bool) -> None:
        self.tanggal_dari.setEnabled(aktif)
        self.tanggal_sampai.setEnabled(aktif)
        # Dipanggil sekali saat penyaring dibangun, ketika tabelnya belum
        # ada. Memuat ulang di saat itu berarti mengisi tabel yang belum
        # dibuat.
        if hasattr(self, "tabel"):
            self.muat_ulang()

    def muat_ulang(self) -> None:
        """
        Cari ulang memakai kriteria yang SEDANG TERTULIS di layar.

        Dipanggil oleh interaksi eksplisit — tombol Cari, Enter di kotak
        pencarian, kedua kotak tanggal, kedua kotak centang — maupun oleh
        `F5`. Kriterianya disimpan sebagai "terakhir disubmit" supaya
        penyegaran OTOMATIS berikutnya memakainya kembali tanpa membaca
        ulang kotak pencarian, yang boleh jadi sedang diketik separuh
        jalan.
        """
        self._kata_terakhir = self.isian_cari.text()
        if self.centang_tanggal.isChecked():
            self._dari_terakhir = self.tanggal_dari.date().toPython()
            self._sampai_terakhir = self.tanggal_sampai.date().toPython()
        else:
            self._dari_terakhir = None
            self._sampai_terakhir = None
        self._hanya_pengaduan_terakhir = self.centang_pengaduan.isChecked()
        self._cari_dan_tampilkan()

    def _segarkan_otomatis(self) -> None:
        """
        Segarkan diam-diam setiap `SELANG_PENYEGARAN_MS`.

        Memakai kriteria TERAKHIR DISUBMIT, bukan `muat_ulang()` — timer
        ini dapat berbunyi kapan saja, termasuk saat petugas baru mengetik
        separuh kata kunci dan belum menekan Enter. Mencari memakai kata
        yang belum selesai diketik sama saja mendahului petugas yang
        belum meminta apa pun.
        """
        self._cari_dan_tampilkan()

    def _cari_dan_tampilkan(self) -> None:
        berhasil, data = jalankan_aman(
            self,
            lambda: self.note.cari(
                self._kata_terakhir,
                dari=self._dari_terakhir,
                sampai=self._sampai_terakhir,
                hanya_pengaduan=self._hanya_pengaduan_terakhir,
            ),
            "Gagal membaca pengaduan",
        )
        if not berhasil:
            return

        # Baris yang sedang dibaca petugas TIDAK BOLEH melompat ke baris
        # lain hanya karena penyegaran berkala kebetulan berbunyi —
        # dicatat di sini, sebelum `self.hasil` ditimpa hasil yang baru.
        dipilih_sebelumnya = self.terpilih.id if self.terpilih else None
        self.hasil = data or []
        self._isi_tabel(pilih_id=dipilih_sebelumnya)

    def _isi_tabel(self, pilih_id: int | None = None) -> None:
        self.tabel.setRowCount(len(self.hasil))
        for baris, lembar in enumerate(self.hasil):
            nilai = (
                hari_dan_tanggal(lembar.queue_date),
                lembar.queue_number,
                lembar.nama or "-",
                lembar.nomor_pelanggan or "-",
                lembar.ringkas or "-",
            )
            for kolom, teks in enumerate(nilai):
                item = QTableWidgetItem(teks)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tabel.setItem(baris, kolom, item)

        self.label_kosong.setText(
            "Belum ada pengaduan maupun catatan yang cocok."
            if not self.hasil
            else f"{len(self.hasil)} lembar ditemukan."
        )
        if not self.hasil:
            self._tampilkan_rincian(None)
            return

        # Lembar yang sama dipilih lagi bila masih ada di hasil baru;
        # baris pertama hanya dipakai untuk pencarian yang benar-benar
        # baru, ketika belum ada satu pun yang dipilih sebelumnya.
        baris_dipilih = next(
            (i for i, lembar in enumerate(self.hasil) if lembar.id == pilih_id), 0
        )
        self.tabel.selectRow(baris_dipilih)
        # Dipanggil eksplisit, bukan mengandalkan sinyal `currentCellChanged`
        # semata: sinyal itu tidak berbunyi bila baris yang dipilih ulang
        # kebetulan berindeks sama seperti sebelumnya, dan rincian akan
        # menampilkan data yang sudah basi walau tabelnya sendiri sudah
        # segar.
        self._tampilkan_rincian(self.hasil[baris_dipilih])

    @property
    def terpilih(self) -> NoteInfo | None:
        baris = self.tabel.currentRow()
        if 0 <= baris < len(self.hasil):
            return self.hasil[baris]
        return None

    def _pilih_baris(self) -> None:
        self._tampilkan_rincian(self.terpilih)

    def _tampilkan_rincian(self, lembar: NoteInfo | None) -> None:
        while self.susunan_rincian.count():
            item = self.susunan_rincian.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.tombol_hapus.setEnabled(lembar is not None and self.boleh_hapus)

        if lembar is None:
            self.label_nomor.setText("—")
            self.label_meta.setText("Pilih satu baris untuk membacanya.")
            self.susunan_rincian.addStretch()
            return

        self.label_nomor.setText(f"{lembar.queue_number} · {lembar.category_name or '-'}")
        self.label_meta.setText(
            f"{hari_dan_tanggal(lembar.queue_date)} · "
            f"{lembar.counter_name or 'Tanpa loket'} · "
            f"{lembar.officer_name or '-'} · "
            f"diperbarui {jam(lembar.updated_at)}"
        )

        for kapsi, isi in (
            ("Nama", lembar.nama),
            ("No. Pelanggan", lembar.nomor_pelanggan),
            ("Telepon", lembar.telepon),
            ("Email", lembar.email),
            ("Alamat", lembar.alamat),
            ("Deskripsi Pengaduan", lembar.deskripsi),
            ("Catatan Petugas", lembar.catatan),
        ):
            # Isian kosong TIDAK ditampilkan sebagai baris berisi "-".
            # Tujuh baris strip membuat yang benar-benar tertulis tenggelam
            # di antara yang memang tidak diisi.
            if not (isi or "").strip():
                continue
            self.susunan_rincian.addWidget(self._blok(kapsi, isi or ""))

        self.susunan_rincian.addStretch()

    @staticmethod
    def _blok(kapsi: str, isi: str) -> QWidget:
        kotak = QWidget()
        susunan = QVBoxLayout(kotak)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(2)

        label = QLabel(kapsi.upper())
        label.setProperty("kapsi", "true")
        susunan.addWidget(label)

        nilai = QLabel(isi)
        nilai.setWordWrap(True)
        nilai.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        nilai.setStyleSheet(f"color: {TEXT};")
        susunan.addWidget(nilai)
        return kotak

    # -----------------------------------------------------------------
    # Tindakan
    # -----------------------------------------------------------------

    def hapus(self) -> None:
        """
        Hapus lembar terpilih beserta data pribadi di dalamnya.

        Dikonfirmasi karena tidak dapat dibatalkan: tidak ada tempat sampah
        dan tidak ada salinan selain berkas backup, yang belum tentu masih
        memuat hari itu.
        """
        lembar = self.terpilih
        if lembar is None or not self.boleh_hapus:
            return
        if not konfirmasi(
            self,
            f"Hapus lembar antrian {lembar.queue_number} beserta seluruh isinya? "
            "Tindakan ini tidak dapat dibatalkan.",
            "Hapus Lembar",
        ):
            return

        berhasil, _ = jalankan_aman(
            self, lambda: self.note.hapus(lembar.id), "Gagal menghapus lembar"
        )
        if berhasil:
            self.muat_ulang()
