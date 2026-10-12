"""
Data pelapor, di layar pelayanan.

Identitas ditulis SAMBIL bertanya kepada orang yang duduk di depan meja —
nama, nomor pelanggan, nomor telepon — sedangkan keluhannya ditulis sambil
mendengarkan. Dua kegiatan yang berbeda, dan karena itu dua tempat: isian
pendek ini tetap di layar sehingga dapat diisi seketika, sementara kotak
keluhan yang panjang mendapat tempatnya sendiri di panel kanan
(`note_panel.py`), yang berbagi tab dengan Menunggu Dilayani.

Lembar tetap SATU baris di database. Formulir ini tidak menyimpan apa pun
sendiri: nilainya dibaca NotePanel pada saat Simpan ditekan, karena
identitas tanpa keluhan maupun catatan bukan lembar yang layak disimpan —
ia hanya akan menjadi nama pengunjung yang tersimpan tanpa satu pun alasan.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
)
from app.ui.common import konfirmasi, tombol
from app.ui.style import (
    BORDER,
    FONT_SIZE_SMALL,
    RADIUS,
    SUCCESS,
    SURFACE,
    TEXT_MUTED,
    WARNING,
)
from app.utils.profil_wp import (
    JENIS_ID_WP,
    JENIS_INVALID,
    JENIS_PROFIL,
    HasilClipboardWp,
    parse_clipboard_wp,
)

PESAN_BUKAN_PROFIL = "Clipboard bukan profil WP"
PESAN_PROFIL_DITEMPEL = "Profil ditempel"
PESAN_ID_DITEMPEL = "ID WP ditempel"
PESAN_GANTI = "Ganti data pelapor?"


class PelaporForm(QFrame):
    """Isian identitas pelapor untuk antrian yang sedang ditangani."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panelPelapor")
        self.setStyleSheet(
            f"QFrame#panelPelapor {{ background: {SURFACE};"
            f" border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )

        #: Kewajiban terakhir yang diminta lewat `tandai_wajib`. Disimpan
        #: supaya isian Nama/No. Pelanggan dapat melepas tandanya SENDIRI
        #: begitu diisi, tanpa menunggu NotePanel memanggil `tandai_wajib`
        #: lagi — panel itu hanya bereaksi pada ketikan di kotak keluhan,
        #: bukan pada ketikan di sini.
        self._wajib_aktif = False

        self._bangun_tampilan()
        self.isian_nama.textChanged.connect(self._perbarui_diri)
        self.isian_nomor_pelanggan.textChanged.connect(self._perbarui_diri)
        self.set_aktif(False)

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(14, 10, 14, 10)
        susunan.setSpacing(8)

        kepala = QHBoxLayout()
        kepala.setSpacing(8)
        judul = QLabel("DATA PELAPOR")
        judul.setProperty("kapsi", "true")
        kepala.addWidget(judul)
        kepala.addStretch()
        self.tombol_tempel = tombol("Tempel profil")
        self.tombol_tempel.setStyleSheet(
            f"padding: 4px 10px; min-height: 18px; font-size: {FONT_SIZE_SMALL}px;"
        )
        self.tombol_tempel.clicked.connect(self._saat_tempel)
        kepala.addWidget(self.tombol_tempel)
        susunan.addLayout(kepala)

        self.isian_nama = self._isian(PANJANG_NAMA, "Nama pelapor")
        self.isian_nomor_pelanggan = self._isian(
            PANJANG_NOMOR_PELANGGAN, "Nomor pelanggan"
        )
        self.isian_telepon = self._isian(PANJANG_TELEPON, "Boleh dikosongkan")
        self.isian_email = self._isian(PANJANG_EMAIL, "Boleh dikosongkan")
        self.isian_alamat = self._isian(PANJANG_ALAMAT, "Boleh dikosongkan")

        # Dua isian per baris. Kolom kiri panel pelayanan lebih lebar
        # daripada tinggi, dan tinggi itulah yang paling langka di sana.
        kisi = QGridLayout()
        kisi.setHorizontalSpacing(14)
        kisi.setVerticalSpacing(6)
        kisi.setColumnStretch(0, 1)
        kisi.setColumnStretch(1, 1)

        self.label_nama = self._label("Nama")
        self.label_nomor_pelanggan = self._label("No. Pelanggan")

        kisi.addLayout(self._kolom(self.label_nama, self.isian_nama), 0, 0)
        kisi.addLayout(
            self._kolom(self.label_nomor_pelanggan, self.isian_nomor_pelanggan), 0, 1
        )
        kisi.addLayout(self._kolom(self._label("Telepon"), self.isian_telepon), 1, 0)
        kisi.addLayout(self._kolom(self._label("Email"), self.isian_email), 1, 1)
        kisi.addLayout(
            self._kolom(self._label("Alamat"), self.isian_alamat), 2, 0, 1, 2
        )
        susunan.addLayout(kisi)

        self.label_petunjuk = QLabel("")
        self.label_petunjuk.setWordWrap(True)
        susunan.addWidget(self.label_petunjuk)
        self.tandai_wajib(False)

    @staticmethod
    def _kolom(label: QLabel, isian: QWidget) -> QVBoxLayout:
        """
        Label di ATAS isiannya.

        Label bersebelahan memaksa satu kolom selebar label terpanjang, dan
        pada dua isian per baris kolom itu memakan lebar yang dibutuhkan
        isiannya sendiri.
        """
        susunan = QVBoxLayout()
        susunan.setSpacing(2)
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
    def _label(teks: str) -> QLabel:
        label = QLabel(teks)
        label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px; font-weight: 600;"
        )
        return label

    # -----------------------------------------------------------------
    # Isi
    # -----------------------------------------------------------------

    @property
    def _isian_semua(self) -> tuple[QLineEdit, ...]:
        return (
            self.isian_nama,
            self.isian_nomor_pelanggan,
            self.isian_telepon,
            self.isian_email,
            self.isian_alamat,
        )

    @property
    def nilai(self) -> dict[str, str]:
        """Isian saat ini, siap diteruskan ke service."""
        return {
            "nama": self.isian_nama.text(),
            "nomor_pelanggan": self.isian_nomor_pelanggan.text(),
            "telepon": self.isian_telepon.text(),
            "email": self.isian_email.text(),
            "alamat": self.isian_alamat.text(),
        }

    @property
    def terisi(self) -> bool:
        return any(isian.text().strip() for isian in self._isian_semua)

    @property
    def kurang(self) -> list[str]:
        """Isian wajib pengaduan yang masih kosong, sebagai nama bacanya."""
        hasil = []
        if not self.isian_nama.text().strip():
            hasil.append("Nama")
        if not self.isian_nomor_pelanggan.text().strip():
            hasil.append("No. Pelanggan")
        return hasil

    def kosongkan(self) -> None:
        for isian in self._isian_semua:
            isian.clear()
        self.tandai_wajib(False)

    def isi(self, lembar: NoteInfo) -> None:
        self.isian_nama.setText(lembar.nama or "")
        self.isian_nomor_pelanggan.setText(lembar.nomor_pelanggan or "")
        self.isian_telepon.setText(lembar.telepon or "")
        self.isian_email.setText(lembar.email or "")
        self.isian_alamat.setText(lembar.alamat or "")

    def set_aktif(self, aktif: bool) -> None:
        """
        Hidupkan atau matikan seluruh isian.

        Dinonaktifkan, bukan disembunyikan — sama seperti tombol tindakan di
        atasnya. Panel yang muncul dan hilang membuat seluruh kolom melompat
        setiap kali status antrian berubah.
        """
        for isian in self._isian_semua:
            isian.setEnabled(aktif)
        self.tombol_tempel.setEnabled(aktif)

    # -----------------------------------------------------------------
    # Penanda wajib
    # -----------------------------------------------------------------

    def tandai_wajib(self, wajib: bool) -> None:
        """
        Tandai Nama dan No. Pelanggan sebagai wajib.

        Dinyalakan hanya ketika lembar ini memang memuat pengaduan.
        Kewajibannya bersyarat, dan peringatan yang menyala pada lembar yang
        cuma berisi catatan petugas cepat berhenti dibaca.
        """
        self._wajib_aktif = wajib
        self._terapkan_wajib()

    # -----------------------------------------------------------------
    # Tempel dari ECMP
    # -----------------------------------------------------------------

    def _saat_tempel(self) -> None:
        """Hanya atas klik. Fokus jendela tidak menempelkan apa pun."""
        self.tempel_teks(self._teks_clipboard())

    @staticmethod
    def _teks_clipboard() -> str:
        """
        Ambil text/plain dari papan klip Windows.

        html() dan MIME lain sengaja tidak dibaca: yang tersalin dari ECMP
        adalah teks, dan markup yang kebetulan menempel di papan tidak
        boleh ikut terisi ke Nama.
        """
        aplikasi = QApplication.instance()
        if aplikasi is None:
            return ""
        papan = aplikasi.clipboard()
        if papan is None:
            return ""
        return papan.text() or ""

    def tempel_teks(self, teks: str) -> None:
        """Isi isian dari teks clipboard yang sudah dipegang pemanggil."""
        if not self.tombol_tempel.isEnabled():
            return
        hasil = parse_clipboard_wp(teks)
        if hasil.jenis == JENIS_INVALID:
            self._setel_umpan(PESAN_BUKAN_PROFIL, gagal=True)
            return
        if self._bentrok(hasil) and not konfirmasi(self, PESAN_GANTI):
            return
        if hasil.jenis == JENIS_PROFIL:
            self._terapkan_profil(hasil)
            self._setel_umpan(PESAN_PROFIL_DITEMPEL)
        elif hasil.jenis == JENIS_ID_WP:
            self._isi_jika_ada(self.isian_nomor_pelanggan, hasil.id_wp)
            self._setel_umpan(PESAN_ID_DITEMPEL)

    def _bentrok(self, hasil: HasilClipboardWp) -> bool:
        """Nama atau No. Pelanggan terisi nilai lain dari yang akan ditempel."""
        if hasil.jenis == JENIS_PROFIL:
            return self._berbeda(self.isian_nama, hasil.nama) or self._berbeda(
                self.isian_nomor_pelanggan, hasil.id_wp
            )
        return self._berbeda(self.isian_nomor_pelanggan, hasil.id_wp)

    @staticmethod
    def _berbeda(isian: QLineEdit, baru: str) -> bool:
        if not baru:
            return False
        sekarang = isian.text().strip()
        return bool(sekarang) and sekarang != baru

    def _terapkan_profil(self, hasil: HasilClipboardWp) -> None:
        self._isi_jika_ada(self.isian_nama, hasil.nama)
        self._isi_jika_ada(self.isian_nomor_pelanggan, hasil.id_wp)
        self._isi_jika_ada(self.isian_telepon, hasil.telepon)
        self._isi_jika_ada(self.isian_email, hasil.email)

    @staticmethod
    def _isi_jika_ada(isian: QLineEdit, nilai: str) -> None:
        if nilai:
            isian.setText(nilai)

    def _setel_umpan(self, pesan: str, *, gagal: bool = False) -> None:
        """Umpan balik singkat; sengaja tanpa mengulang isi yang ditempel."""
        self.label_petunjuk.setText(pesan)
        warna = WARNING if gagal else SUCCESS
        self.label_petunjuk.setStyleSheet(
            f"color: {warna}; font-size: {FONT_SIZE_SMALL}px; font-weight: 600;"
        )

    def _perbarui_diri(self) -> None:
        """
        Lepas tanda wajib begitu isiannya sendiri terisi.

        Mengetik di sini tidak memicu `tandai_wajib` dari luar — panel
        keluhan hanya mendengarkan ketikan di kotaknya sendiri. Tanpa
        pengait ini, bingkai kuning pada Nama tetap menyala walau
        petugas sudah selesai mengisinya, sampai keluhannya diketik ulang.
        """
        if self._wajib_aktif:
            self._terapkan_wajib()

    def _terapkan_wajib(self) -> None:
        wajib = self._wajib_aktif
        pasangan = (
            (self.label_nama, self.isian_nama, "Nama"),
            (self.label_nomor_pelanggan, self.isian_nomor_pelanggan, "No. Pelanggan"),
        )
        for label, isian, nama in pasangan:
            kosong = not isian.text().strip()
            label.setText(f"{nama} *" if wajib else nama)
            self._setel_wajib(isian, wajib and kosong)

        kurang = self.kurang if wajib else []
        if kurang:
            self.label_petunjuk.setText(
                "Wajib diisi untuk pengaduan: " + ", ".join(kurang) + "."
            )
            self.label_petunjuk.setStyleSheet(
                f"color: {WARNING}; font-size: {FONT_SIZE_SMALL}px; font-weight: 600;"
            )
        else:
            self.label_petunjuk.setText(
                "Tersimpan bersama pengaduan atau catatan, bukan sendirian."
            )
            self.label_petunjuk.setStyleSheet(
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
        nilai = "true" if wajib else None
        if widget.property("wajib") == nilai:
            return
        widget.setProperty("wajib", nilai)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
