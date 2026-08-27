"""Dialog isian data master."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.security import MIN_PASSWORD_LENGTH
from app.models import UserRole
from app.ui.common import judul, keterangan, label_error, tombol

#: Nama peran dalam bahasa yang dipakai sehari-hari di kantor.
LABEL_PERAN: dict[UserRole, str] = {
    UserRole.ADMIN: "Administrator",
    UserRole.SUPERVISOR: "Supervisor",
    UserRole.REGISTRATION: "Petugas Pendaftaran",
    UserRole.CRO: "Petugas CRO",
    UserRole.DISPLAY: "Layar Antrian",
}


class _DialogIsian(QDialog):
    """Kerangka bersama seluruh dialog isian: form, pesan sebaris, dua tombol."""

    def __init__(self, parent: QWidget | None, judul_teks: str, penjelasan: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(judul_teks)
        self.setMinimumWidth(440)

        self._susunan = QVBoxLayout(self)
        self._susunan.setContentsMargins(28, 24, 28, 24)
        self._susunan.setSpacing(14)
        self._susunan.addWidget(judul(judul_teks))
        if penjelasan:
            self._susunan.addWidget(keterangan(penjelasan))

        self.form = QFormLayout()
        self.form.setSpacing(12)
        self._susunan.addLayout(self.form)

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
            kotak = QCheckBox(f"{kategori.name} ({kategori.prefix})")
            kotak.setChecked(kategori.id in terpilih)
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

    def __init__(self, parent: QWidget | None = None, *, category=None, prefix_terkunci: bool = False) -> None:
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

        self.input_prefix = QLineEdit(category.prefix if ubah else "")
        self.input_prefix.setPlaceholderText("A")
        self.input_prefix.setMaxLength(2)
        self.input_prefix.setEnabled(not prefix_terkunci)
        self.input_prefix.textChanged.connect(self._perbarui_contoh)
        self.form.addRow("Prefix", self.input_prefix)

        self.contoh = keterangan("")
        self.form.addRow("", self.contoh)
        self._perbarui_contoh(self.input_prefix.text())

        if prefix_terkunci:
            self.form.addRow(
                "",
                keterangan(
                    "Prefix tidak dapat diubah karena jenis layanan ini sudah "
                    "dipakai antrian."
                ),
            )

        (self.input_nama if ubah else self.input_kode).setFocus()

    def _perbarui_contoh(self, teks: str) -> None:
        bersih = teks.strip().upper()
        self.contoh.setText(
            f"Contoh nomor antrian: {bersih}-001" if bersih else "Contoh nomor antrian: —"
        )

    @property
    def kode(self) -> str:
        return self.input_kode.text().strip()

    @property
    def nama(self) -> str:
        return self.input_nama.text().strip()

    @property
    def prefix(self) -> str:
        return self.input_prefix.text().strip().upper()

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
