"""Dialog isian data master."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import ValidationError
from app.core.security import MIN_PASSWORD_LENGTH
from app.models import UserRole
from app.services import daftar_putar
from app.services.note_service import FRASA_MAKS, PANJANG_FRASA, daftar_frasa, periksa_frasa
from app.ui.common import judul, keterangan, label_error, tombol
from app.ui.daftar_frasa import DaftarFrasa
from app.ui.kiosk.sambutan import (
    FILTER_BERKAS_ANJUNGAN,
    folder_media_layanan,
    hapus_media_layanan,
    media_layanan,
    salin_ke_media_layanan,
)

#: Nama peran dalam bahasa yang dipakai sehari-hari di kantor.
LABEL_PERAN: dict[UserRole, str] = {
    UserRole.ADMIN: "Administrator",
    UserRole.SUPERVISOR: "Supervisor",
    UserRole.REGISTRATION: "Petugas Pendaftaran",
    UserRole.CRO: "Petugas CRO",
    UserRole.DISPLAY: "Layar Antrian",
}


class PemilihMediaLayanan(QWidget):
    """
    Berkas gambar/video yang tampil di anjungan saat layanan ini disentuh.

    Berkasnya hidup di mesin anjungan, bukan di database — aturan yang
    sama dengan media sambutan — jadi tidak ada yang perlu ikut disimpan
    bersama form ini. Karena itu tombolnya bekerja SEKETIKA, tidak
    menunggu Simpan, dan penjelasannya mengatakan begitu.

    `ringkas` untuk tempat yang memasang beberapa widget ini berjajar —
    layar Pengaturan memasang satu untuk setiap jenis layanan. Di sana
    penjelasan yang sama terulang tiga kali dan berhenti dibaca pada
    kalinya yang kedua, jadi penjelasannya ditulis sekali di atas
    kelompoknya dan yang di sini hanya menyebut letak foldernya.
    """

    def __init__(
        self, code: str, parent: QWidget | None = None, *, ringkas: bool = False
    ) -> None:
        super().__init__(parent)
        self.code = code
        self.ringkas = ringkas

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(6)

        baris = QHBoxLayout()
        baris.setSpacing(8)
        self.label_berkas = QLabel()
        self.label_berkas.setWordWrap(True)
        baris.addWidget(self.label_berkas, stretch=1)

        self.btn_pilih = tombol("Pilih berkas…")
        self.btn_pilih.clicked.connect(self._pilih)
        baris.addWidget(self.btn_pilih)

        self.btn_hapus = tombol("Hapus")
        self.btn_hapus.clicked.connect(self._hapus)
        baris.addWidget(self.btn_hapus)
        susunan.addLayout(baris)

        folder = folder_media_layanan(code)
        panjang = (
            "Berkas langsung dipasang tanpa menunggu Simpan, dan menggantikan "
            "berkas sebelumnya. Video diulang terus sampai pengunjung menekan "
            "YA atau BATAL, jadi klip pendek 5-10 detik justru paling baik — "
            "usahakan frame awal dan akhirnya mirip supaya sambungannya tidak "
            "berkedip. Suara tidak diputar."
        )
        self.keterangan = keterangan(
            ("" if ringkas else panjang)
            + (f" Folder: {folder}" if folder is not None else "")
        )
        self.keterangan.setWordWrap(True)
        susunan.addWidget(self.keterangan)

        self._perbarui()

    def _perbarui(self) -> None:
        berkas = media_layanan(self.code)
        self.label_berkas.setText(
            berkas.name if berkas is not None else "Belum ada berkas — memakai Info Anjungan."
        )
        self.btn_hapus.setEnabled(berkas is not None)

    def _pilih(self) -> None:
        folder = folder_media_layanan(self.code)
        awal = str(folder) if folder is not None and folder.is_dir() else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih gambar atau video layanan", awal, FILTER_BERKAS_ANJUNGAN
        )
        if not path:
            return
        salin_ke_media_layanan(self.code, Path(path))
        self._perbarui()

    def _hapus(self) -> None:
        hapus_media_layanan(self.code)
        self._perbarui()


class _DialogIsian(QDialog):
    """Kerangka bersama seluruh dialog isian: form, pesan sebaris, dua tombol."""

    def __init__(self, parent: QWidget | None, judul_teks: str, penjelasan: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(judul_teks)

        self._susunan = QVBoxLayout(self)
        self._susunan.setContentsMargins(28, 24, 28, 24)
        self._susunan.setSpacing(14)
        self._susunan.addWidget(judul(judul_teks))
        if penjelasan:
            self._susunan.addWidget(keterangan(penjelasan))

        self._gulir_form = QScrollArea()
        self._gulir_form.setObjectName("gulirFormDialog")
        self._gulir_form.setWidgetResizable(True)
        self._gulir_form.setFrameShape(QFrame.Shape.NoFrame)
        self._gulir_form.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._gulir_form.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self._isi_form = QWidget()
        self.form = QFormLayout(self._isi_form)
        self.form.setContentsMargins(0, 0, 8, 0)
        self.form.setSpacing(12)
        self._gulir_form.setWidget(self._isi_form)
        self._susunan.addWidget(self._gulir_form, stretch=1)

        self.pesan_kesalahan = label_error()
        self._susunan.addWidget(self.pesan_kesalahan)

        baris = QHBoxLayout()
        baris.addStretch()
        batal = tombol("Batal")
        batal.clicked.connect(self.reject)
        baris.addWidget(batal)
        self.tombol_simpan = tombol("SIMPAN", variant="primary", default=True)
        self.tombol_simpan.clicked.connect(self.simpan)
        baris.addWidget(self.tombol_simpan)
        self._susunan.addLayout(baris)

    def showEvent(self, event) -> None:  # noqa: N802 - nama Qt
        """Batasi dialog ke area monitor; isi panjang tetap dapat digulir."""
        super().showEvent(event)
        layar = self.screen()
        if layar is None:
            return
        area = layar.availableGeometry()
        maksimum = QSize(max(1, area.width() - 32), max(1, area.height() - 32))
        self.setMinimumWidth(min(440, maksimum.width()))
        self.setMaximumSize(maksimum)
        ideal = self.sizeHint().boundedTo(maksimum)
        ideal.setWidth(min(maksimum.width(), max(self.minimumWidth(), ideal.width())))
        self.resize(ideal)

    def tampilkan_kesalahan(self, pesan: str, fokus: QWidget | None = None) -> None:
        self.pesan_kesalahan.setText(pesan)
        self.pesan_kesalahan.setVisible(True)
        if fokus is not None:
            fokus.setFocus()

    def simpan(self) -> None:  # pragma: no cover - diisi turunannya
        raise NotImplementedError


class CounterDialog(_DialogIsian):
    """Tambah atau ubah loket."""

    def __init__(self, parent: QWidget | None = None, *, counter=None) -> None:
        self.counter = counter
        ubah = counter is not None
        super().__init__(
            parent,
            "Ubah Loket" if ubah else "Tambah Loket",
            "Kode loket tidak dapat diubah setelah dibuat karena melekat "
            "pada riwayat pemanggilan." if ubah else "",
        )

        self.input_kode = QLineEdit(counter.code if ubah else "")
        self.input_kode.setPlaceholderText("mis. LOKET-4")
        self.input_kode.setMaxLength(20)
        self.input_kode.setEnabled(not ubah)
        self.form.addRow("Kode Loket", self.input_kode)

        self.input_nama = QLineEdit(counter.name if ubah else "")
        self.input_nama.setPlaceholderText("mis. Loket 4")
        self.form.addRow("Nama Loket", self.input_nama)

        (self.input_nama if ubah else self.input_kode).setFocus()

    @property
    def kode(self) -> str:
        return self.input_kode.text().strip()

    @property
    def nama(self) -> str:
        return self.input_nama.text().strip()

    def simpan(self) -> None:
        if self.counter is None and not self.kode:
            self.tampilkan_kesalahan("Kode loket belum diisi.", self.input_kode)
            return
        if not self.nama:
            self.tampilkan_kesalahan("Nama loket belum diisi.", self.input_nama)
            return
        self.accept()


class CounterCategoryDialog(_DialogIsian):
    """
    Pilih jenis layanan yang boleh dipanggil sebuah loket.

    Tidak ada yang dicentang berarti loket melayani SEMUA jenis layanan.
    Itu ditulis terang-terangan di dialognya karena kotak yang semuanya
    kosong biasanya dibaca sebagai "tidak melayani apa pun", padahal
    artinya justru sebaliknya.
    """

    def __init__(
        self, parent: QWidget | None = None, *, counter, categories: list
    ) -> None:
        super().__init__(
            parent,
            f"Jenis Layanan {counter.name}",
            "Centang jenis layanan yang boleh dipanggil loket ini. Bila "
            "tidak ada yang dicentang, loket melayani SEMUA jenis layanan — "
            "itu pilihan yang disarankan kecuali loket ini memang khusus.",
        )
        self.counter = counter
        self.kotak: list[tuple[int, QCheckBox]] = []

        terpilih = set(counter.category_ids)
        for kategori in categories:
            # Jorok mengikuti tingkatnya, sama seperti tabel jenis layanan:
            # "Restoran" sendirian tidak memberi tahu bahwa ia berada di
            # bawah PBJT, di bawah Konsultasi.
            jorok = "    " * getattr(kategori, "level", 0)
            kotak = QCheckBox(f"{jorok}{kategori.name} ({kategori.prefix})")
            kotak.setChecked(kategori.id in terpilih)
            if getattr(kategori, "punya_anak", False):
                # Kelompok tidak pernah menerbitkan nomor, jadi mencentangnya
                # tidak pernah mengubah antrian mana pun yang dapat dipanggil
                # loket ini. Tetap ditampilkan supaya centang lama yang
                # tersimpan tidak lenyap diam-diam saat dialog disimpan.
                kotak.setText(f"{kotak.text()} — kelompok, tanpa nomor")
            if not kategori.is_active:
                # Jenis layanan nonaktif tetap ditampilkan supaya loket
                # khusus tidak kehilangan pengaturannya saat layanannya
                # sedang dihentikan sementara.
                kotak.setText(f"{kotak.text()} — nonaktif")
            self.form.addRow("", kotak)
            self.kotak.append((kategori.id, kotak))

    @property
    def terpilih(self) -> list[int]:
        return [id_ for id_, kotak in self.kotak if kotak.isChecked()]

    def simpan(self) -> None:
        self.accept()


class CategoryDialog(_DialogIsian):
    """Tambah atau ubah jenis layanan."""

    #: Sebanyak tingkat yang dapat dicapai menu anjungan. Sama dengan
    #: TINGKAT_MAKS di master_data_service, yang menegakkannya sungguhan;
    #: di sini hanya dipakai untuk tidak menawarkan induk yang pasti
    #: ditolak, supaya admin tidak menabrak pesan kesalahan tanpa perlu.
    TINGKAT_MAKS = 3

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        category=None,
        prefix_terkunci: bool = False,
        semua: list | None = None,
    ) -> None:
        self.category = category
        ubah = category is not None
        super().__init__(
            parent,
            "Ubah Jenis Layanan" if ubah else "Tambah Jenis Layanan",
            "Prefix menentukan nomor antrian. Prefix A menghasilkan A-001, "
            "A-002, dan seterusnya.",
        )

        self.input_kode = QLineEdit(category.code if ubah else "")
        self.input_kode.setPlaceholderText("mis. PENGEMBALIAN")
        self.input_kode.setMaxLength(20)
        self.input_kode.setEnabled(not ubah)
        self.form.addRow("Kode", self.input_kode)

        self.input_nama = QLineEdit(category.name if ubah else "")
        self.input_nama.setPlaceholderText("mis. Pengembalian")
        self.form.addRow("Nama Layanan", self.input_nama)

        self.pilih_induk = QComboBox()
        self.pilih_induk.addItem("— Menu utama anjungan —", None)
        for pilihan in self._calon_induk(semua or [], category):
            self.pilih_induk.addItem(
                "    " * pilihan.level + pilihan.name, pilihan.id
            )
        if ubah and category.parent_id is not None:
            posisi = self.pilih_induk.findData(category.parent_id)
            if posisi >= 0:
                self.pilih_induk.setCurrentIndex(posisi)
        self.form.addRow("Induk", self.pilih_induk)
        self.form.addRow(
            "",
            keterangan(
                "Jenis layanan yang menaungi jenis layanan lain berubah "
                "menjadi KELOMPOK: di anjungan ia membuka daftar isinya dan "
                "berhenti menerbitkan nomor sendiri."
            ),
        )

        self.input_prefix = QLineEdit(category.prefix if ubah else "")
        self.input_prefix.setPlaceholderText("A")
        self.input_prefix.setMaxLength(2)
        self.input_prefix.setEnabled(not prefix_terkunci)
        self.input_prefix.textChanged.connect(self._perbarui_contoh)
        self.form.addRow("Prefix", self.input_prefix)

        self.contoh = keterangan("")
        self.form.addRow("", self.contoh)
        self._perbarui_contoh(self.input_prefix.text())

        self.input_info = QPlainTextEdit(category.info_text if ubah else "")
        self.input_info.setPlaceholderText(
            "Ditampilkan di panel anjungan begitu pengunjung menyentuh "
            "layanan ini. Kosongkan bila tidak perlu."
        )
        self.input_info.setMaximumHeight(90)
        self.form.addRow("Info Anjungan", self.input_info)

        self.input_frasa = QPlainTextEdit(category.frasa_catatan if ubah else "")
        self.input_frasa.setPlaceholderText(
            "Satu kalimat per baris (maksimal 8). Tampil sebagai tombol cepat "
            "di catatan petugas. Kosongkan untuk memakai daftar bawaan."
        )
        self.input_frasa.setMaximumHeight(110)
        self.form.addRow("Kalimat Cepat Catatan", self.input_frasa)

        # Pratinjau: paragraf persis seperti yang dilihat petugas (kalimat
        # dirangkai koma, tanpa kotak), supaya admin tahu bila daftarnya
        # terlalu panjang untuk dua sampai tiga baris sebelum menyimpan.
        self.peringatan_frasa = keterangan("")
        self.form.addRow("", self.peringatan_frasa)
        self.pratinjau_frasa = DaftarFrasa()
        self.pratinjau_frasa.setMaximumWidth(360)
        self.form.addRow("Pratinjau", self.pratinjau_frasa)
        self.input_frasa.textChanged.connect(self._perbarui_pratinjau_frasa)
        self._perbarui_pratinjau_frasa()

        # Media mengalahkan Info Anjungan bila keduanya diisi: panel
        # anjungan kecil, dan nama layanan sudah tampil besar di panel
        # konfirmasi di bawahnya, jadi menumpuk gambar dan tulisan hanya
        # membuat dua-duanya sulit dibaca.
        #
        # Hanya tersedia saat mengubah. Foldernya dinamai menurut kode
        # layanan, dan kode itu belum ada sampai jenis layanannya
        # tersimpan.
        if ubah:
            self.media = PemilihMediaLayanan(category.code)
            self.form.addRow("Media Anjungan", self.media)
        else:
            self.media = None
            self.form.addRow(
                "Media Anjungan",
                keterangan(
                    "Dapat dipasang setelah jenis layanan ini disimpan."
                ),
            )

        if prefix_terkunci:
            self.form.addRow(
                "",
                keterangan(
                    "Prefix tidak dapat diubah karena jenis layanan ini sudah "
                    "dipakai antrian."
                ),
            )

        (self.input_nama if ubah else self.input_kode).setFocus()

    #: Daftar yang lebih tinggi dari ini tidak lagi "dua sampai tiga baris".
    BARIS_FRASA_MAKS = 3

    def _perbarui_pratinjau_frasa(self) -> None:
        teks = self.input_frasa.toPlainText()
        daftar = daftar_frasa(teks)
        self.pratinjau_frasa.set_kalimat(daftar)
        try:
            periksa_frasa(teks)
        except ValidationError as exc:
            self.peringatan_frasa.setText(str(exc))
            self.peringatan_frasa.setStyleSheet("color: #B45309; font-weight: 600;")
            return
        baris = self._baris_pratinjau()
        if baris > self.BARIS_FRASA_MAKS:
            self.peringatan_frasa.setText(
                f"Daftar ini memakan sekitar {baris} baris di layar petugas. "
                f"Persingkat supaya paling banyak {self.BARIS_FRASA_MAKS} baris."
            )
            self.peringatan_frasa.setStyleSheet("color: #B45309; font-weight: 600;")
            return
        self.peringatan_frasa.setStyleSheet("")
        self.peringatan_frasa.setText(
            f"Maksimal {FRASA_MAKS} kalimat, masing-masing {PANJANG_FRASA} karakter. "
            "Kosongkan untuk memakai daftar bawaan."
        )

    def _baris_pratinjau(self) -> int:
        """Perkiraan banyaknya baris pratinjau pada lebarnya sekarang."""
        daftar = self.pratinjau_frasa
        if not daftar.item:
            return 0
        lebar = min(daftar.maximumWidth(), 360)
        tinggi = daftar.heightForWidth(lebar)
        return max(1, round(tinggi / max(1, daftar.fontMetrics().lineSpacing())))

    def _perbarui_contoh(self, teks: str) -> None:
        bersih = teks.strip().upper()
        self.contoh.setText(
            f"Contoh nomor antrian: {bersih}-001" if bersih else "Contoh nomor antrian: —"
        )

    def _calon_induk(self, semua: list, category) -> list:
        """
        Jenis layanan yang boleh dipilih sebagai induk.

        Yang dibuang tiga macam: dirinya sendiri, seluruh KETURUNANNYA —
        memindahkan Konsultasi ke bawah PBJT akan membuat menu berputar
        tanpa ujung — dan yang sudah berada di tingkat terdalam, karena
        anaknya tidak akan punya tempat lagi di layar.
        """
        buang: set[int] = set()
        if category is not None:
            buang.add(category.id)
            berubah = True
            while berubah:
                berubah = False
                for baris in semua:
                    if baris.parent_id in buang and baris.id not in buang:
                        buang.add(baris.id)
                        berubah = True

        return [
            baris
            for baris in semua
            if baris.id not in buang and baris.level < self.TINGKAT_MAKS - 1
        ]

    @property
    def induk_id(self) -> int | None:
        return self.pilih_induk.currentData()

    @property
    def kode(self) -> str:
        return self.input_kode.text().strip()

    @property
    def nama(self) -> str:
        return self.input_nama.text().strip()

    @property
    def prefix(self) -> str:
        return self.input_prefix.text().strip().upper()

    @property
    def info_text(self) -> str:
        return self.input_info.toPlainText().strip()

    @property
    def frasa_catatan(self) -> str:
        return self.input_frasa.toPlainText().strip()

    def simpan(self) -> None:
        if self.category is None and not self.kode:
            self.tampilkan_kesalahan("Kode belum diisi.", self.input_kode)
            return
        if not self.nama:
            self.tampilkan_kesalahan("Nama layanan belum diisi.", self.input_nama)
            return
        if self.input_prefix.isEnabled() and not self.prefix:
            self.tampilkan_kesalahan("Prefix belum diisi.", self.input_prefix)
            return
        try:
            periksa_frasa(self.frasa_catatan)
        except ValidationError as exc:
            self.tampilkan_kesalahan(str(exc), self.input_frasa)
            return
        self.accept()


class UserDialog(_DialogIsian):
    """Tambah atau ubah akun petugas."""

    def __init__(
        self, parent: QWidget | None = None, *, user=None, counters: list | None = None
    ) -> None:
        self.user = user
        ubah = user is not None
        super().__init__(
            parent,
            "Ubah Akun" if ubah else "Tambah Akun",
            "" if ubah else
            f"Kata sandi minimal {MIN_PASSWORD_LENGTH} karakter. Petugas akan "
            "diminta menggantinya saat pertama kali masuk.",
        )

        self.input_username = QLineEdit(user.username if ubah else "")
        self.input_username.setPlaceholderText("mis. cro2")
        self.input_username.setMaxLength(50)
        self.input_username.setEnabled(not ubah)
        self.form.addRow("Nama Pengguna", self.input_username)

        self.input_nama = QLineEdit(user.full_name if ubah else "")
        self.input_nama.setPlaceholderText("mis. Budi Santoso")
        self.form.addRow("Nama Lengkap", self.input_nama)

        self.pilih_peran = QComboBox()
        for role in UserRole:
            # KIOSK bukan akun petugas. Sesi itu dibuat tanpa login, dan
            # menawarkannya di sini hanya mengundang admin menyimpan kata
            # sandi di komputer publik.
            if role is UserRole.KIOSK:
                continue
            # Simpan nilai string, bukan objek enum. QVariant PySide sering
            # mengubah str Enum menjadi str biasa; service tetap menormalkannya.
            self.pilih_peran.addItem(LABEL_PERAN[role], role.value)
        if ubah:
            nilai = user.role.value if isinstance(user.role, UserRole) else user.role
            self.pilih_peran.setCurrentIndex(self.pilih_peran.findData(nilai))
        self.form.addRow("Peran", self.pilih_peran)

        # Loket bawaan: yang langsung terpilih saat petugas ini masuk,
        # supaya tidak perlu memilihnya lagi setiap hari dan tidak keliru
        # memanggil atas nama loket sebelah. Petugas tetap boleh berpindah
        # sendiri saat pindah meja; yang disimpan di sini titik awalnya.
        self.pilih_loket = QComboBox()
        self.pilih_loket.addItem("— Tidak diikat ke loket —", None)
        for loket in counters or []:
            self.pilih_loket.addItem(loket.name, loket.id)
        if ubah and getattr(user, "default_counter_id", None) is not None:
            baris = self.pilih_loket.findData(user.default_counter_id)
            if baris >= 0:
                self.pilih_loket.setCurrentIndex(baris)
        self.form.addRow("Loket Bawaan", self.pilih_loket)

        if not ubah:
            self.input_password = QLineEdit()
            self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
            self.form.addRow("Kata Sandi", self.input_password)
        else:
            self.input_password = None

        (self.input_nama if ubah else self.input_username).setFocus()

    @property
    def username(self) -> str:
        return self.input_username.text().strip()

    @property
    def nama_lengkap(self) -> str:
        return self.input_nama.text().strip()

    @property
    def peran(self) -> UserRole:
        data = self.pilih_peran.currentData()
        if isinstance(data, UserRole):
            return data
        return UserRole(data)

    @property
    def loket_bawaan(self) -> int | None:
        return self.pilih_loket.currentData()

    @property
    def password(self) -> str:
        return self.input_password.text() if self.input_password else ""

    def simpan(self) -> None:
        if self.user is None and not self.username:
            self.tampilkan_kesalahan("Nama pengguna belum diisi.", self.input_username)
            return
        if not self.nama_lengkap:
            self.tampilkan_kesalahan("Nama lengkap belum diisi.", self.input_nama)
            return
        if self.input_password is not None and not self.password:
            self.tampilkan_kesalahan("Kata sandi belum diisi.", self.input_password)
            return
        self.accept()


class ResetPasswordDialog(_DialogIsian):
    """Setel ulang kata sandi petugas yang lupa."""

    def __init__(self, parent: QWidget | None = None, *, nama_petugas: str = "") -> None:
        super().__init__(
            parent,
            "Setel Ulang Kata Sandi",
            f"Kata sandi sementara untuk {nama_petugas}. Petugas WAJIB "
            "menggantinya saat masuk berikutnya.",
        )

        self.input_baru = QLineEdit()
        self.input_baru.setEchoMode(QLineEdit.EchoMode.Password)
        self.form.addRow("Kata Sandi Sementara", self.input_baru)

        self.input_ulangi = QLineEdit()
        self.input_ulangi.setEchoMode(QLineEdit.EchoMode.Password)
        self.form.addRow("Ulangi", self.input_ulangi)

        self.input_baru.setFocus()

    @property
    def password(self) -> str:
        return self.input_baru.text()

    def simpan(self) -> None:
        if not self.password:
            self.tampilkan_kesalahan("Kata sandi belum diisi.", self.input_baru)
            return
        if self.password != self.input_ulangi.text():
            self.tampilkan_kesalahan("Ulangan kata sandi tidak sama.", self.input_ulangi)
            return
        self.accept()


class JadwalIklanDialog(_DialogIsian):
    """
    Tanggal tayang dan lama tampil satu berkas di daftar putar anjungan.

    Tanggal dibaca menurut jam server, dan keduanya ikut dihitung: iklan
    1–30 November tayang sejak pagi tanggal 1 sampai malam tanggal 30.
    """

    def __init__(
        self,
        parent: QWidget | None,
        butir: daftar_putar.Butir,
        *,
        gambar: bool,
        berkas: Path | None = None,
    ) -> None:
        super().__init__(
            parent,
            "Jadwal Iklan",
            f"{butir.nama}. Di luar tanggalnya berkas ini tidak diputar, "
            "tetapi tetap tercentang di daftar putar.",
        )
        self._nama = butir.nama
        hari_ini = QDate.currentDate()

        self.pakai_mulai = QCheckBox("Mulai tanggal")
        self.tanggal_mulai = self._kotak_tanggal(butir.mulai, hari_ini)
        self.form.addRow(self.pakai_mulai, self.tanggal_mulai)
        self.pakai_selesai = QCheckBox("Sampai tanggal")
        self.tanggal_selesai = self._kotak_tanggal(butir.selesai, hari_ini.addDays(30))
        self.form.addRow(self.pakai_selesai, self.tanggal_selesai)
        for centang, kotak, nilai in (
            (self.pakai_mulai, self.tanggal_mulai, butir.mulai),
            (self.pakai_selesai, self.tanggal_selesai, butir.selesai),
        ):
            centang.toggled.connect(kotak.setEnabled)
            centang.setChecked(nilai is not None)
            kotak.setEnabled(nilai is not None)

        # Video untuk strip panel atas dan video untuk layar penuh berbeda
        # bentuknya (mendatar kecil vs seluruh layar): satu berkas dapat
        # dibatasi pada salah satunya.
        self.tampil = QComboBox()
        for kunci in daftar_putar.TAMPIL_SAH:
            self.tampil.addItem(daftar_putar.LABEL_TAMPIL[kunci], kunci)
        self.tampil.setCurrentIndex(self.tampil.findData(butir.tampil))
        self.tampil.setToolTip(
            "Panel atas: strip di atas kartu layanan. Layar penuh: saat anjungan "
            "menganggur dan iklan memenuhi layar."
        )
        self.form.addRow("Tampil di", self.tampil)

        # Bentuk berkas terhadap tempat tampilnya: dibaca sekali dari kepala
        # berkas, peringatannya mengikuti pilihan "Tampil di".
        from app.services.ukuran_media import ukuran_media

        self._ukuran = ukuran_media(berkas) if berkas is not None else None
        self.label_ukuran = QLabel()
        self.label_ukuran.setWordWrap(True)
        self.peringatan_rasio = QLabel()
        self.peringatan_rasio.setWordWrap(True)
        self.peringatan_rasio.setStyleSheet("color: #92400e;")
        if berkas is not None:
            self.form.addRow("Ukuran", self.label_ukuran)
            self.form.addRow("", self.peringatan_rasio)
        self.tampil.currentIndexChanged.connect(self._perbarui_rasio)
        self._perbarui_rasio()

        self.detik = QSpinBox()
        # Satu di bawah batas bawah berarti "ikut pengaturan umum".
        self.detik.setRange(daftar_putar.DETIK_MIN - 1, daftar_putar.DETIK_MAKS)
        self.detik.setSpecialValueText("Ikut pengaturan umum")
        self.detik.setSuffix(" detik")
        self.detik.setValue(butir.detik or self.detik.minimum())
        if gambar:
            self.form.addRow("Lama tampil", self.detik)
        else:
            # Video selalu diputar sampai selesai.
            self.detik.setVisible(False)

    def _perbarui_rasio(self) -> None:
        from app.services.ukuran_media import keterangan_rasio

        keterangan, peringatan = keterangan_rasio(
            self._ukuran, self.tampil.currentData() or daftar_putar.TAMPIL_KEDUANYA
        )
        self.label_ukuran.setText(keterangan)
        self.peringatan_rasio.setText(f"⚠ {peringatan}" if peringatan else "")
        self.peringatan_rasio.setVisible(bool(peringatan))

    @staticmethod
    def _kotak_tanggal(nilai, cadangan: QDate) -> QDateEdit:
        kotak = QDateEdit()
        kotak.setCalendarPopup(True)
        kotak.setDisplayFormat("d MMM yyyy")
        kotak.setDate(
            QDate(nilai.year, nilai.month, nilai.day) if nilai is not None else cadangan
        )
        return kotak

    @property
    def butir(self) -> daftar_putar.Butir:
        mulai = self.tanggal_mulai.date().toPython() if self.pakai_mulai.isChecked() else None
        selesai = (
            self.tanggal_selesai.date().toPython() if self.pakai_selesai.isChecked() else None
        )
        detik = self.detik.value()
        return daftar_putar.Butir(
            self._nama,
            mulai,
            selesai,
            None if detik < daftar_putar.DETIK_MIN else detik,
            self.tampil.currentData() or daftar_putar.TAMPIL_KEDUANYA,
        )

    def simpan(self) -> None:
        butir = self.butir
        if butir.mulai and butir.selesai and butir.selesai < butir.mulai:
            self.tampilkan_kesalahan(
                "Tanggal selesai lebih awal dari tanggal mulai.", self.tanggal_selesai
            )
            return
        self.accept()
