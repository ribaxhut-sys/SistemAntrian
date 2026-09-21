"""
Dialog menetapkan peran komputer ini: terhadap database, dan terhadap
pengunjung.

Bukan deteksi jaringan. Orang yang memasang memilih: satu komputer,
server, atau klien. Pilihan itu disimpan di mesin.json pada komputer
ini saja, lalu komputer klien menuliskan alamat yang ditampilkan di
sini — bukan mencari sendiri siapa yang sedang menyala.

Bagian kedua menjawab pertanyaan yang berbeda: komputer ini menghadap
pengunjung sebagai apa. Jawabannya ditulis ke berkas TERPISAH,
`peran.json`, karena berkas itu dirancang untuk disalin antar-komputer
sedangkan mesin.json memuat kata sandi database dan tidak boleh disalin
ke mana pun. Lihat app.core.peran.

Peran MENGISI ketiga isian di bawahnya, tidak mengunci. Isian yang
dibiarkan pada "Ikut peran" mengikuti tabel simpulan, sehingga perbaikan
tabel itu di versi berikutnya sampai ke seluruh komputer tanpa satu pun
harus didatangi. Isian yang diubah menyatakan kehendak, dan kehendak itu
tersimpan apa adanya.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import APP_NAME, get_config
from app.core.mesin import (
    KLIEN,
    SENDIRI,
    SERVER,
    alamat_ipv4_lokal,
    env_url_mengalahkan,
    kesalahan_isian,
    muat_pengaturan,
    path_berkas_mesin,
    PengaturanMesin,
    tulis_berkas_mesin,
    uji_koneksi,
)
from app.core.peran import (
    ADMIN as PERAN_ADMIN,
    ANJUNGAN as PERAN_ANJUNGAN,
    ANJUNGAN_TOTEM as PERAN_ANJUNGAN_TOTEM,
    BAWAAN,
    LABEL,
    PAPAN_MEMANJANG,
    PETUGAS as PERAN_PETUGAS,
    TELEVISI,
    PeranKomputer,
    baca_peran,
    path_berkas_peran,
    tulis_peran,
)
from app.ui.common import keterangan, label_error, tombol

#: Urutan peran di kotak pilihan, dari yang paling banyak jumlahnya di
#: kantor ke yang paling jarang. Namanya diambil dari app.core.peran supaya
#: bilah status dan dialog ini tidak pernah menyebut hal yang sama dengan
#: dua kata yang berbeda.
NAMA_PERAN: tuple[tuple[str, str], ...] = (
    ("", "Belum ditetapkan — tanya setiap kali dibuka"),
    *(
        (kode, LABEL[kode])
        for kode in (
            PERAN_PETUGAS,
            PERAN_ADMIN,
            PERAN_ANJUNGAN,
            PERAN_ANJUNGAN_TOTEM,
            TELEVISI,
            PAPAN_MEMANJANG,
        )
    ),
)

NAMA_PENCETAK: tuple[tuple[str | None, str], ...] = (
    (None, ""),  # diisi ulang mengikuti peran
    ("none", "Tidak mencetak"),
    ("pdf", "Simpan sebagai PDF di folder tiket"),
    ("system", "Cetak ke printer Windows"),
)

NAMA_SUARA: tuple[tuple[bool | None, str], ...] = (
    (None, ""),
    (True, "Bunyikan panggilan"),
    (False, "Diam"),
)

NAMA_BENTUK: tuple[tuple[str | None, str], ...] = (
    (None, ""),
    ("lebar", "Televisi biasa, lebih lebar daripada tinggi"),
    ("memanjang", "Papan memanjang, seperti pita di atas pintu"),
    ("tegak", "Layar berdiri, lebih tinggi daripada lebar"),
)

#: Bunyi "Ikut peran (…)" untuk tiap kemungkinan bawaan. Yang kosong
#: berarti peran itu memang tidak berpendapat, dan yang berlaku adalah
#: pengaturan bersama di database.
_SEBUTAN_PENCETAK = {"": "ikut pengaturan", "none": "tidak mencetak"}
_SEBUTAN_SUARA = {None: "ikut pengaturan", True: "bunyikan", False: "diam"}
_SEBUTAN_BENTUK = {"": "diukur sendiri"}


class SetupMesinDialog(QDialog):
    """Tanya bagaimana komputer ini memakai database."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dialogMesin")
        self.setWindowTitle(f"{APP_NAME} — Komputer ini")
        self.setFixedWidth(560)

        cfg = get_config()
        self._db_path = cfg.db_path
        self._url_semula = cfg.database_url
        self.pengaturan_tersimpan: PengaturanMesin | None = None
        self.peran_tersimpan: PeranKomputer | None = None

        self._bangun_tampilan()
        self._muat(muat_pengaturan(self._db_path))
        self._peran_semula = baca_peran(path_berkas_peran(self._db_path))
        self._muat_peran(self._peran_semula)
        self._perbarui_tampilan()

    @property
    def memerlukan_buka_ulang(self) -> bool:
        """
        True bila isian yang baru disimpan tidak akan dipakai sebelum
        aplikasi dibuka ulang.

        Peran ikut dihitung. Mode dibaca sekali saat peluncuran — lihat
        `mode_awal_mesin` di app.main — sehingga televisi yang baru saja
        ditetapkan tetap menampilkan layar yang sedang terbuka sampai
        aplikasinya dijalankan lagi.
        """
        if self.peran_tersimpan is not None and (
            self.peran_tersimpan != self._peran_semula
        ):
            return True
        if self.pengaturan_tersimpan is None:
            return False
        if env_url_mengalahkan():
            return False
        url_baru = self.pengaturan_tersimpan.ke_url() or f"sqlite:///{self._db_path}"
        return url_baru != self._url_semula

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(28, 24, 28, 20)
        susunan.setSpacing(12)

        judul = QLabel("Bagaimana komputer ini dipakai?")
        judul.setProperty("heading", "true")
        susunan.addWidget(judul)
        susunan.addWidget(
            keterangan(
                "Hanya SATU komputer di kantor yang boleh menjadi server. "
                "Komputer lain menuliskan alamatnya. Aplikasi tidak mencari "
                "sendiri siapa yang menyala."
            )
        )

        self._peringatan_env = QLabel(
            "Komputer ini memakai ANTRIAN_DB_URL, sehingga isian di bawah "
            "tidak dipakai sampai variabel itu dihapus."
        )
        self._peringatan_env.setProperty("error", "true")
        self._peringatan_env.setWordWrap(True)
        self._peringatan_env.setVisible(env_url_mengalahkan())
        susunan.addWidget(self._peringatan_env)

        self._grup = QButtonGroup(self)
        self.radio_sendiri = self._radio(
            "Satu komputer saja",
            "Database berkas lokal di mesin ini. Tanpa jaringan, tanpa PostgreSQL.",
        )
        self.radio_server = self._radio(
            "Komputer ini adalah SERVER",
            "PostgreSQL dipasang di mesin ini. Komputer loket, anjungan, dan "
            "televisi menyambung ke alamat yang ditampilkan di bawah.",
        )
        self.radio_klien = self._radio(
            "Komputer ini menyambung ke SERVER",
            "Isi alamat komputer server. Anjungan memakai pengguna "
            "antrian_kios, televisi memakai antrian_layar — bukan akun petugas.",
        )
        self._grup.addButton(self.radio_sendiri)
        self._grup.addButton(self.radio_server)
        self._grup.addButton(self.radio_klien)
        susunan.addWidget(self._baris_peran(self.radio_sendiri))
        susunan.addWidget(self._baris_peran(self.radio_server))
        susunan.addWidget(self._baris_peran(self.radio_klien))
        self._grup.buttonClicked.connect(self._perbarui_tampilan)

        self._panel_server = self._bangun_panel_server()
        susunan.addWidget(self._panel_server)

        self._panel_postgres = self._bangun_panel_postgres()
        susunan.addWidget(self._panel_postgres)

        self._panel_peran = self._bangun_panel_peran()
        susunan.addWidget(self._panel_peran)

        self._label_error = label_error()
        susunan.addWidget(self._label_error)

        susunan.addStretch(1)
        susunan.addLayout(self._bangun_tombol())

    def _radio(self, judul: str, penjelasan: str) -> QRadioButton:
        tombol_radio = QRadioButton(judul)
        tombol_radio.setToolTip(penjelasan)
        return tombol_radio

    def _baris_peran(self, tombol_radio: QRadioButton) -> QWidget:
        """Judul radio plus penjelasan yang terbaca tanpa harus diam di atasnya."""
        kotak = QWidget()
        susunan = QVBoxLayout(kotak)
        susunan.setContentsMargins(0, 2, 0, 6)
        susunan.setSpacing(2)
        susunan.addWidget(tombol_radio)
        teks = QLabel(tombol_radio.toolTip())
        teks.setProperty("muted", "true")
        teks.setWordWrap(True)
        teks.setContentsMargins(22, 0, 0, 0)
        susunan.addWidget(teks)
        return kotak

    def _bangun_panel_server(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panelAlamatServer")
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(12, 8, 12, 8)
        susunan.setSpacing(6)

        self._label_alamat = QLabel()
        self._label_alamat.setObjectName("alamatServer")
        self._label_alamat.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._label_alamat.setWordWrap(True)
        susunan.addWidget(self._label_alamat)

        salin = tombol("Salin alamat")
        salin.setObjectName("tombolSalinAlamat")
        salin.setAutoDefault(False)
        salin.clicked.connect(self._salin_alamat)
        baris = QHBoxLayout()
        baris.addWidget(salin)
        baris.addStretch(1)
        susunan.addLayout(baris)
        return panel

    def _bangun_panel_postgres(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout(panel)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(8)

        self.isian_host = QLineEdit()
        self.isian_host.setObjectName("isianHost")
        self.isian_host.setPlaceholderText("contoh: 192.168.1.10")
        form.addRow("Alamat server", self.isian_host)

        self.isian_port = QSpinBox()
        self.isian_port.setObjectName("isianPort")
        self.isian_port.setRange(1, 65535)
        self.isian_port.setValue(5432)
        form.addRow("Port", self.isian_port)

        self.isian_database = QLineEdit()
        self.isian_database.setObjectName("isianDatabase")
        self.isian_database.setPlaceholderText("antrian")
        form.addRow("Database", self.isian_database)

        self.isian_pengguna = QLineEdit()
        self.isian_pengguna.setObjectName("isianPengguna")
        self.isian_pengguna.setPlaceholderText("antrian")
        form.addRow("Pengguna", self.isian_pengguna)

        self.isian_sandi = QLineEdit()
        self.isian_sandi.setObjectName("isianSandi")
        self.isian_sandi.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Kata sandi", self.isian_sandi)

        return panel

    def _bangun_panel_peran(self) -> QWidget:
        """
        Bagian kedua: komputer ini menghadap pengunjung sebagai apa.

        Satu pertanyaan, lalu tiga isian yang SUDAH TERISI olehnya. Isian
        itu tidak disembunyikan dan tidak dikunci: orang tidak perlu keluar
        dari perannya untuk menyimpang sedikit darinya, dan yang dibiarkan
        pada "Ikut peran" tetap ikut ketika tabel simpulan diperbaiki.
        """
        panel = QWidget()
        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(0, 8, 0, 0)
        susunan.setSpacing(8)

        judul = QLabel("Komputer ini dipakai sebagai")
        judul.setProperty("heading", "true")
        susunan.addWidget(judul)
        susunan.addWidget(
            keterangan(
                "Komputer yang sudah ditetapkan membuka layarnya sendiri, "
                "apa pun cara ia dinyalakan — tidak lagi bergantung pada "
                "pintasan yang benar."
            )
        )

        form = QFormLayout()
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(8)

        self.pilih_peran = self._kotak_pilih("pilihPeran", NAMA_PERAN)
        self.pilih_peran.currentIndexChanged.connect(self._perbarui_bawaan_peran)
        form.addRow("Peran", self.pilih_peran)

        self.pilih_pencetak = self._kotak_pilih("pilihPencetak", NAMA_PENCETAK)
        form.addRow("Pencetak tiket", self.pilih_pencetak)

        self.pilih_suara = self._kotak_pilih("pilihSuara", NAMA_SUARA)
        form.addRow("Suara panggilan", self.pilih_suara)

        self.pilih_bentuk = self._kotak_pilih("pilihBentuk", NAMA_BENTUK)
        form.addRow("Bentuk layar", self.pilih_bentuk)

        susunan.addLayout(form)
        return panel

    @staticmethod
    def _kotak_pilih(nama: str, isi) -> QComboBox:
        """Kotak pilihan yang menyimpan nilainya sebagai data, bukan teks."""
        kotak = QComboBox()
        kotak.setObjectName(nama)
        for nilai, teks in isi:
            kotak.addItem(teks, userData=nilai)
        return kotak

    @staticmethod
    def _pilih_nilai(kotak: QComboBox, nilai) -> None:
        """Pilih butir yang datanya `nilai`; butir pertama bila tidak ada."""
        indeks = kotak.findData(nilai)
        kotak.setCurrentIndex(indeks if indeks >= 0 else 0)

    def _perbarui_bawaan_peran(self) -> None:
        """
        Tulis ulang bunyi "Ikut peran (…)" mengikuti peran yang dipilih.

        Inilah yang membuat perannya terbaca tanpa membuka dokumen mana
        pun: memilih "Anjungan ambil nomor" langsung memperlihatkan bahwa
        mesin itu akan DIAM, dan orang yang tidak menghendakinya dapat
        mengubahnya di tempat yang sama.
        """
        bawaan = BAWAAN.get(self.pilih_peran.currentData() or "")
        pencetak = bawaan.printer if bawaan is not None else ""
        suara = bawaan.suara if bawaan is not None else None
        bentuk = bawaan.bentuk_layar if bawaan is not None else ""

        self.pilih_pencetak.setItemText(
            0, f"Ikut peran ({_SEBUTAN_PENCETAK.get(pencetak, pencetak)})"
        )
        self.pilih_suara.setItemText(0, f"Ikut peran ({_SEBUTAN_SUARA[suara]})")
        self.pilih_bentuk.setItemText(
            0, f"Ikut peran ({_SEBUTAN_BENTUK.get(bentuk, bentuk)})"
        )

    def _muat_peran(self, peran: PeranKomputer) -> None:
        self._pilih_nilai(self.pilih_peran, peran.peran)
        self._pilih_nilai(self.pilih_pencetak, peran.printer)
        self._pilih_nilai(self.pilih_suara, peran.suara)
        self._pilih_nilai(self.pilih_bentuk, peran.bentuk_layar)
        self._perbarui_bawaan_peran()

    def _peran_dari_form(self) -> PeranKomputer:
        return PeranKomputer(
            peran=self.pilih_peran.currentData() or "",
            printer=self.pilih_pencetak.currentData(),
            suara=self.pilih_suara.currentData(),
            bentuk_layar=self.pilih_bentuk.currentData(),
        )

    def _bangun_tombol(self) -> QHBoxLayout:
        baris = QHBoxLayout()
        uji = tombol("Uji koneksi")
        uji.setObjectName("tombolUjiKoneksi")
        uji.setAutoDefault(False)
        uji.clicked.connect(self._uji)
        baris.addWidget(uji)
        baris.addStretch(1)

        batal = tombol("Batal")
        batal.setAutoDefault(False)
        batal.clicked.connect(self.reject)
        baris.addWidget(batal)

        simpan = tombol("Simpan", variant="primary", default=True)
        simpan.setObjectName("tombolSimpanMesin")
        simpan.clicked.connect(self._simpan)
        baris.addWidget(simpan)
        return baris

    def _peran_terpilih(self) -> str:
        if self.radio_server.isChecked():
            return SERVER
        if self.radio_klien.isChecked():
            return KLIEN
        return SENDIRI

    def _pengaturan_dari_form(self) -> PengaturanMesin:
        return PengaturanMesin(
            peran=self._peran_terpilih(),
            host=self.isian_host.text().strip(),
            port=int(self.isian_port.value()),
            nama_database=self.isian_database.text().strip(),
            pengguna=self.isian_pengguna.text().strip(),
            sandi=self.isian_sandi.text(),
        )

    def _muat(self, pengaturan: PengaturanMesin) -> None:
        self.radio_sendiri.setChecked(pengaturan.peran == SENDIRI)
        self.radio_server.setChecked(pengaturan.peran == SERVER)
        self.radio_klien.setChecked(pengaturan.peran == KLIEN)
        self.isian_host.setText(pengaturan.host)
        self.isian_port.setValue(pengaturan.port)
        self.isian_database.setText(pengaturan.nama_database)
        self.isian_pengguna.setText(pengaturan.pengguna)
        self.isian_sandi.setText(pengaturan.sandi)

    def _perbarui_tampilan(self) -> None:
        peran = self._peran_terpilih()
        self._panel_server.setVisible(peran == SERVER)
        self._panel_postgres.setVisible(peran != SENDIRI)
        self.isian_host.setVisible(peran == KLIEN)
        # Baris "Alamat server" ikut disembunyikan: label form menempel
        # pada field, dan field yang invisible masih menyisakan labelnya
        # bila tidak ikut di-hide lewat item form. QFormLayout tidak
        # menyembunyikan label otomatis di semua versi Qt, jadi label
        # diisi ulang lewat setEnabled + buddy row hide via field.
        form = self._panel_postgres.layout()
        if isinstance(form, QFormLayout):
            label = form.labelForField(self.isian_host)
            if label is not None:
                label.setVisible(peran == KLIEN)

        alamat = alamat_ipv4_lokal()
        if alamat:
            daftar = "  ·  ".join(alamat)
            self._label_alamat.setText(
                "Tulis alamat ini di komputer loket, anjungan, dan televisi:\n"
                f"{daftar}"
            )
        else:
            self._label_alamat.setText(
                "Alamat jaringan komputer ini tidak terbaca. Sambungkan "
                "kabel atau Wi-Fi, lalu buka dialog ini lagi. Komputer "
                "klien menuliskan IP mesin ini, bukan kata 'server'."
            )
        self._tampilkan_error("")

    def _tampilkan_error(self, pesan: str) -> None:
        self._label_error.setText(pesan)
        self._label_error.setVisible(bool(pesan))

    def _salin_alamat(self) -> None:
        alamat = alamat_ipv4_lokal()
        if not alamat:
            self._tampilkan_error(
                "Tidak ada alamat yang dapat disalin. Periksa jaringan."
            )
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(alamat[0])
        self._tampilkan_error("")

    def _uji(self) -> None:
        pengaturan = self._pengaturan_dari_form()
        if pengaturan.peran == SENDIRI:
            self._tampilkan_error(
                "Satu komputer tidak perlu diuji: databasenya berkas lokal."
            )
            return
        salah = kesalahan_isian(pengaturan)
        if salah:
            self._tampilkan_error(salah)
            return
        gagal = uji_koneksi(pengaturan.ke_url())
        if gagal:
            self._tampilkan_error(gagal)
            return
        self._tampilkan_error("")
        from app.ui.common import tampilkan_info

        tampilkan_info(self, "Koneksi berhasil.", "Uji koneksi")

    def _simpan(self) -> None:
        pengaturan = self._pengaturan_dari_form()
        salah = kesalahan_isian(pengaturan)
        if salah:
            self._tampilkan_error(salah)
            return
        tulis_berkas_mesin(path_berkas_mesin(self._db_path), pengaturan)
        self.pengaturan_tersimpan = pengaturan

        # Berkas kedua, sengaja terpisah: yang ini aman disalin ke komputer
        # lain sebagai contekan, yang di atas memuat kata sandi database.
        peran = self._peran_dari_form()
        tulis_peran(path_berkas_peran(self._db_path), peran)
        self.peran_tersimpan = peran
        self.accept()
