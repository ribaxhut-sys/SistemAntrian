"""
Dialog menetapkan peran komputer ini: terhadap database, dan terhadap
pengunjung.

Orang yang memasang memilih: satu komputer, server, atau klien.
Pilihan itu disimpan di mesin.json pada komputer ini saja. Komputer
klien mencari PostgreSQL di jaringan yang sama; bila lebih dari satu
yang menjawab, orang itu yang memilih, bukan aplikasi.

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

from PySide6.QtCore import Qt, QThread, Signal
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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import APP_NAME, get_config
from app.core.mesin import (
    DATABASE_BAWAAN,
    KLIEN,
    PENGGUNA_BAWAAN,
    PORT_BAWAAN,
    SENDIRI,
    SERVER,
    alamat_ipv4_lokal,
    cari_server_jaringan,
    env_url_mengalahkan,
    kesalahan_isian,
    muat_pengaturan,
    path_berkas_mesin,
    PengaturanMesin,
    siapkan_database_lokal,
    tulis_berkas_mesin,
    uji_koneksi,
)
from app.core.peran import (
    ADMIN as PERAN_ADMIN,
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

#: Pengguna yang boleh tertinggal dari pemasangan lama. Selain ketiga
#: ini, dialog mengembalikan ke pengguna antrian: isiannya tidak lagi
#: ditampilkan, jadi nilai asing tidak boleh tersimpan diam-diam.
_PENGGUNA_TETAP = frozenset({PENGGUNA_BAWAAN, "antrian_kios", "antrian_layar"})


class _PencariServer(QThread):
    """Pindaian jaringan di utas sendiri supaya dialog tetap dapat diklik."""

    selesai = Signal(object)

    def __init__(self, port: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._port = port

    def run(self) -> None:
        self.selesai.emit(cari_server_jaringan(port=self._port))


def _tiket_contoh() -> "TicketData":
    """
    Tiket palsu untuk uji cetak.

    Nomornya sengaja tidak menyerupai nomor sungguhan, dan catatan kakinya
    mengatakannya sendiri. Kertas uji yang tertinggal di meja anjungan
    tidak boleh terbaca sebagai giliran milik siapa pun.
    """
    from app.core import clock
    from app.services.ticket_service import TicketData

    return TicketData(
        queue_number="UJI-000",
        category_name="Uji Cetak",
        office_name=APP_NAME,
        issued_at=clock.now(),
        footer="Tiket contoh untuk menguji pencetak. Bukan nomor antrian.",
    )


class SetupMesinDialog(QDialog):
    """Tanya bagaimana komputer ini memakai database."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dialogMesin")
        self.setWindowTitle(f"{APP_NAME} — Komputer ini")
        # Lebar dikunci supaya penjelasan yang dibungkus tidak berubah
        # tinggi setiap kali jendela ditarik. Tingginya mengikuti isi,
        # dan isi itu disusun dua kolom agar muat di layar loket yang pendek.
        self.setFixedWidth(960)

        cfg = get_config()
        self._db_path = cfg.db_path
        self._base_dir = cfg.base_dir
        self._url_semula = cfg.database_url
        self.pengaturan_tersimpan: PengaturanMesin | None = None
        self.peran_tersimpan: PeranKomputer | None = None
        self._sandi_tersimpan = ""
        self._wajib_ulang = False
        self._port_terbuka = False

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
        susunan.setContentsMargins(20, 14, 20, 12)
        susunan.setSpacing(8)

        judul = QLabel("Bagaimana komputer ini dipakai?")
        judul.setProperty("heading", "true")
        susunan.addWidget(judul)
        susunan.addWidget(
            keterangan(
                "Hanya SATU komputer di kantor yang boleh menjadi server. "
                "Komputer lain mencari PostgreSQL di jaringan yang sama. "
                "Bila lebih dari satu yang menjawab, pilih yang memang "
                "server antrian."
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
            "PostgreSQL dipasang di mesin ini. Yang diisi hanya kata sandi "
            "database. Bila pengguna antrian belum ada, tekan Siapkan database.",
        )
        self.radio_klien = self._radio(
            "Komputer ini menyambung ke SERVER",
            "Cari server di jaringan yang sama. Kata sandinya sama dengan "
            "yang dibuat di komputer server. Port dan pengguna sudah tetap.",
        )
        self._grup.addButton(self.radio_sendiri)
        self._grup.addButton(self.radio_server)
        self._grup.addButton(self.radio_klien)
        self._grup.buttonClicked.connect(self._perbarui_tampilan)

        self._panel_server = self._bangun_panel_server()
        self._panel_postgres = self._bangun_panel_postgres()
        self._panel_peran = self._bangun_panel_peran()

        # Dua kolom karena dua pertanyaan ini tidak bergantung satu sama
        # lain. Menumpuknya membuat tombol Simpan jatuh ke bawah lipatan
        # pada layar loket yang pendek.
        kiri = QWidget()
        susunan_kiri = QVBoxLayout(kiri)
        susunan_kiri.setContentsMargins(0, 0, 0, 0)
        susunan_kiri.setSpacing(2)
        susunan_kiri.addWidget(self._baris_peran(self.radio_sendiri))
        susunan_kiri.addWidget(self._baris_peran(self.radio_server))
        susunan_kiri.addWidget(self._baris_peran(self.radio_klien))
        susunan_kiri.addWidget(self._panel_server)
        susunan_kiri.addWidget(self._panel_postgres)
        susunan_kiri.addStretch(1)

        kanan = QWidget()
        susunan_kanan = QVBoxLayout(kanan)
        susunan_kanan.setContentsMargins(0, 0, 0, 0)
        susunan_kanan.setSpacing(0)
        susunan_kanan.addWidget(self._panel_peran)
        susunan_kanan.addStretch(1)

        garis = QFrame()
        garis.setObjectName("garisBagiMesin")
        garis.setFixedWidth(1)
        garis.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )

        bagi = QHBoxLayout()
        bagi.setSpacing(16)
        bagi.addWidget(kiri, 1)
        bagi.addWidget(garis)
        bagi.addWidget(kanan, 1)
        susunan.addLayout(bagi)

        self._label_error = label_error()
        susunan.addWidget(self._label_error)
        susunan.addLayout(self._bangun_tombol())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sesuaikan_tinggi()

    def closeEvent(self, event) -> None:
        pencari = getattr(self, "_pencari", None)
        if pencari is not None and pencari.isRunning():
            pencari.wait(8000)
        super().closeEvent(event)

    def _sesuaikan_tinggi(self) -> None:
        """
        Kunci tinggi ke isi yang sedang terlihat.

        Label penjelasan membungkus kata, jadi tinggi dialog baru benar
        sesudah lebarnya diketahui. Tanpa ini Qt memakai tinggi satu baris
        dan isinya terpotong, atau memanjang kosong di bawah tombol.
        """
        if not self.isVisible() or self.layout() is None:
            return
        self.ensurePolished()
        tinggi = self.layout().totalHeightForWidth(self.width())
        if tinggi > 0:
            self.setFixedHeight(tinggi)

    def _radio(self, judul: str, penjelasan: str) -> QRadioButton:
        tombol_radio = QRadioButton(judul)
        tombol_radio.setToolTip(penjelasan)
        return tombol_radio

    def _baris_peran(self, tombol_radio: QRadioButton) -> QWidget:
        """Judul radio plus penjelasan yang terbaca tanpa harus diam di atasnya."""
        kotak = QWidget()
        susunan = QVBoxLayout(kotak)
        susunan.setContentsMargins(0, 0, 0, 2)
        susunan.setSpacing(0)
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
        susunan = QHBoxLayout(panel)
        susunan.setContentsMargins(10, 6, 10, 6)
        susunan.setSpacing(8)

        self._label_alamat = QLabel()
        self._label_alamat.setObjectName("alamatServer")
        self._label_alamat.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._label_alamat.setWordWrap(True)
        susunan.addWidget(self._label_alamat, 1)

        salin = tombol("Salin alamat")
        salin.setObjectName("tombolSalinAlamat")
        salin.setAutoDefault(False)
        salin.clicked.connect(self._salin_alamat)
        susunan.addWidget(salin, 0, Qt.AlignmentFlag.AlignVCenter)
        return panel

    def _bangun_panel_postgres(self) -> QWidget:
        """
        Kata sandi diketik sekali. Kotak kedua muncul bila sandi yang
        sudah tersimpan diganti, atau bila PostgreSQL menolaknya.
        Port disembunyikan sampai 5432 tidak menjawab.
        """
        panel = QWidget()
        luar = QVBoxLayout(panel)
        luar.setContentsMargins(0, 4, 0, 0)
        luar.setSpacing(6)

        self._baris_host = QWidget()
        baris_host = QHBoxLayout(self._baris_host)
        baris_host.setContentsMargins(0, 0, 0, 0)
        baris_host.setSpacing(8)
        self._label_host = QLabel("Alamat server")
        self.isian_host = QLineEdit()
        self.isian_host.setObjectName("isianHost")
        self.isian_host.setPlaceholderText("tekan Cari di jaringan")
        self.isian_host.setReadOnly(True)
        baris_host.addWidget(self._label_host)
        baris_host.addWidget(self.isian_host, 1)
        self._tombol_cari = tombol("Cari di jaringan")
        self._tombol_cari.setObjectName("tombolCariServer")
        self._tombol_cari.setAutoDefault(False)
        self._tombol_cari.clicked.connect(self._cari_server)
        baris_host.addWidget(self._tombol_cari)
        luar.addWidget(self._baris_host)

        self._pilih_server = QComboBox()
        self._pilih_server.setObjectName("pilihServer")
        self._pilih_server.currentIndexChanged.connect(self._pilih_alamat_server)
        self._baris_pilih = self._kolom_isian("Pilih server", self._pilih_server)
        self._baris_pilih.setVisible(False)
        luar.addWidget(self._baris_pilih)

        self._tombol_ubah_port = tombol("Ubah port")
        self._tombol_ubah_port.setObjectName("tombolUbahPort")
        self._tombol_ubah_port.setAutoDefault(False)
        self._tombol_ubah_port.setToolTip(
            "Peran Loket admin. Nomor yang diganti harus sama di setiap komputer."
        )
        self._tombol_ubah_port.clicked.connect(self._buka_ubah_port)
        self._tombol_ubah_port.hide()
        luar.addWidget(self._tombol_ubah_port, 0, Qt.AlignmentFlag.AlignLeft)

        self.isian_port = QSpinBox()
        self.isian_port.setObjectName("isianPort")
        self.isian_port.setRange(1, 65535)
        self.isian_port.setValue(PORT_BAWAAN)
        self._baris_port = self._kolom_isian("Port", self.isian_port)
        self._baris_port.setVisible(False)
        self.isian_port.hide()
        luar.addWidget(self._baris_port)

        self.isian_sandi = QLineEdit()
        self.isian_sandi.setObjectName("isianSandi")
        self.isian_sandi.setEchoMode(QLineEdit.EchoMode.Password)
        self.isian_sandi.setPlaceholderText("sandi database antrian")
        self.isian_sandi.textChanged.connect(self._perbarui_ulang_sandi)
        self._tombol_tampil_sandi = tombol("Tampilkan")
        self._tombol_tampil_sandi.setObjectName("tombolTampilSandi")
        self._tombol_tampil_sandi.setAutoDefault(False)
        self._tombol_tampil_sandi.clicked.connect(self._tukar_tampil_sandi)
        baris_sandi = QWidget()
        susunan_sandi = QHBoxLayout(baris_sandi)
        susunan_sandi.setContentsMargins(0, 0, 0, 0)
        susunan_sandi.setSpacing(8)
        susunan_sandi.addWidget(self.isian_sandi, 1)
        susunan_sandi.addWidget(self._tombol_tampil_sandi)
        luar.addWidget(self._kolom_isian("Kata sandi database", baris_sandi))

        self.isian_ulang = QLineEdit()
        self.isian_ulang.setObjectName("isianUlangSandi")
        self.isian_ulang.setEchoMode(QLineEdit.EchoMode.Password)
        self.isian_ulang.setPlaceholderText("sandi yang sama")
        self._baris_ulang = self._kolom_isian("Ketik ulang kata sandi", self.isian_ulang)
        self._baris_ulang.setVisible(False)
        luar.addWidget(self._baris_ulang)

        self._tombol_siapkan = tombol("Siapkan database")
        self._tombol_siapkan.setObjectName("tombolSiapkanDatabase")
        self._tombol_siapkan.setAutoDefault(False)
        self._tombol_siapkan.clicked.connect(self._siapkan_database)
        luar.addWidget(self._tombol_siapkan, 0, Qt.AlignmentFlag.AlignLeft)

        self.isian_database = QLineEdit(panel)
        self.isian_database.setObjectName("isianDatabase")
        self.isian_database.setText(DATABASE_BAWAAN)
        self.isian_database.hide()

        self.isian_pengguna = QLineEdit(panel)
        self.isian_pengguna.setObjectName("isianPengguna")
        self.isian_pengguna.setText(PENGGUNA_BAWAAN)
        self.isian_pengguna.hide()
        return panel

    @staticmethod
    def _kolom_isian(judul: str, widget: QWidget) -> QWidget:
        kotak = QWidget()
        susunan = QVBoxLayout(kotak)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(2)
        susunan.addWidget(QLabel(judul))
        susunan.addWidget(widget)
        return kotak

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
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(6)

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
        form.setContentsMargins(0, 2, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        self.pilih_peran = self._kotak_pilih("pilihPeran", NAMA_PERAN)
        self.pilih_peran.currentIndexChanged.connect(self._perbarui_bawaan_peran)
        self.pilih_peran.currentIndexChanged.connect(self._perbarui_tombol_port)
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

        cetak = tombol("Uji cetak")
        cetak.setObjectName("tombolUjiCetak")
        cetak.setAutoDefault(False)
        cetak.clicked.connect(self._uji_cetak)
        baris.addWidget(cetak)

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
        pengguna = self.isian_pengguna.text().strip()
        if pengguna not in _PENGGUNA_TETAP:
            pengguna = PENGGUNA_BAWAAN
        return PengaturanMesin(
            peran=self._peran_terpilih(),
            host=self.isian_host.text().strip(),
            port=int(self.isian_port.value()),
            nama_database=DATABASE_BAWAAN,
            pengguna=pengguna,
            sandi=self.isian_sandi.text(),
        )

    def _muat(self, pengaturan: PengaturanMesin) -> None:
        self.radio_sendiri.setChecked(pengaturan.peran == SENDIRI)
        self.radio_server.setChecked(pengaturan.peran == SERVER)
        self.radio_klien.setChecked(pengaturan.peran == KLIEN)
        self._sandi_tersimpan = pengaturan.sandi
        self._wajib_ulang = False
        self._port_terbuka = pengaturan.port != PORT_BAWAAN
        self.isian_host.setText(pengaturan.host)
        self.isian_port.setValue(pengaturan.port)
        self.isian_database.setText(pengaturan.nama_database)
        self.isian_pengguna.setText(pengaturan.pengguna)
        self.isian_sandi.blockSignals(True)
        self.isian_sandi.setText(pengaturan.sandi)
        self.isian_sandi.blockSignals(False)
        self.isian_ulang.clear()

    def _tampilkan_port(self, tampak: bool) -> None:
        """Port hanya terlihat bila 5432 tidak menjawab, sudah diganti, atau admin membukanya."""
        self._port_terbuka = tampak
        self._baris_port.setVisible(tampak)
        self.isian_port.setVisible(tampak)

    def _perbarui_tombol_port(self) -> None:
        """
        Ubah port tanpa kegagalan hanya untuk peran Loket admin.

        Komputer lain tetap dapat mengisi port bila pencarian atau uji
        koneksi gagal: nomor itu milik seluruh kantor, bukan milik admin.
        """
        admin = self.pilih_peran.currentData() == PERAN_ADMIN
        self._tombol_ubah_port.setVisible(admin and self._peran_terpilih() != SENDIRI)

    def _buka_ubah_port(self) -> None:
        if self.pilih_peran.currentData() != PERAN_ADMIN:
            return
        self._tampilkan_port(True)

    def _tukar_tampil_sandi(self) -> None:
        """Tampilkan sandi di layar ini saja. Tidak disalin dan tidak ditulis ke log."""
        tersembunyi = self.isian_sandi.echoMode() == QLineEdit.EchoMode.Password
        mode = (
            QLineEdit.EchoMode.Normal
            if tersembunyi
            else QLineEdit.EchoMode.Password
        )
        self.isian_sandi.setEchoMode(mode)
        self.isian_ulang.setEchoMode(mode)
        self._tombol_tampil_sandi.setText("Sembunyikan" if tersembunyi else "Tampilkan")

    def _perbarui_ulang_sandi(self) -> None:
        """
        Kotak kedua untuk sandi yang berubah atau yang baru ditolak.

        Sandi pertama, yang belum pernah tersimpan, cukup diketik sekali.
        """
        berubah = bool(self._sandi_tersimpan) and (
            self.isian_sandi.text() != self._sandi_tersimpan
        )
        self._baris_ulang.setVisible(berubah or self._wajib_ulang)
        if self._baris_ulang.isHidden():
            self.isian_ulang.clear()

    def _salah_ketik_ulang(self) -> str | None:
        if self._peran_terpilih() == SENDIRI or self._baris_ulang.isHidden():
            return None
        if not self.isian_sandi.text():
            return "Kata sandi database belum diisi. Ketik ulang di kedua kotak."
        if self.isian_sandi.text() != self.isian_ulang.text():
            return "Ketik ulang kata sandi yang sama di kedua kotak."
        return None

    def _sandi_diterima(self) -> None:
        self._wajib_ulang = False
        self._sandi_tersimpan = self.isian_sandi.text()
        self.isian_ulang.clear()
        self._perbarui_ulang_sandi()

    def _sesudah_gagal_sambungan(self, pesan: str) -> None:
        """
        Penolakan pengguna antrian tidak mengosongkan sandi.

        PostgreSQL memakai kalimat yang sama bila akunnya belum ada dan
        bila sandinya salah. Mengosongkan kotak membuat orang mengetik
        ulang sandi yang tidak punya akun. Tombol Siapkan database yang
        membuat akun itu.
        """
        if "menolak pengguna antrian" in pesan.lower():
            self.isian_sandi.setFocus()
            self._tampilkan_error(
                "Pengguna antrian belum ada di PostgreSQL, atau kata "
                "sandinya tidak cocok. Isi kata sandi yang ingin dipakai, "
                "lalu tekan Siapkan database. Sandi pengguna postgres "
                "akan diminta sekali dan tidak disimpan."
            )
            return
        if "tidak menjawab" in pesan.lower() or "tidak dapat menghubungi" in pesan.lower():
            self._tampilkan_port(True)
            self._tampilkan_error(
                f"PostgreSQL tidak menjawab di port {self.isian_port.value()}. "
                "Ganti port bila nomor itu bentrok atau PostgreSQL memakai "
                "port lain. Seluruh komputer kantor harus memakai port yang sama."
            )
            return
        self._tampilkan_error(pesan)

    def _perbarui_tampilan(self) -> None:
        peran = self._peran_terpilih()
        self._panel_server.setVisible(peran == SERVER)
        self._panel_postgres.setVisible(peran != SENDIRI)
        # Pembungkusnya yang dilipat, supaya baris tidak menyisakan
        # tinggi kosong. Isiannya ikut disembunyikan: isHidden() pada
        # anak tidak menjadi benar hanya karena induknya tertutup.
        host_terlihat = peran == KLIEN
        self._baris_host.setVisible(host_terlihat)
        self.isian_host.setVisible(host_terlihat)
        self._tombol_cari.setVisible(host_terlihat)
        self._tombol_siapkan.setVisible(peran == SERVER)
        if peran != KLIEN:
            self._baris_pilih.setVisible(False)
        self._tampilkan_port(self._port_terbuka)
        self._perbarui_tombol_port()
        self._perbarui_ulang_sandi()

        alamat = alamat_ipv4_lokal()
        if alamat:
            daftar = "  ·  ".join(alamat)
            self._label_alamat.setText(
                "Komputer lain mencari server ini di jaringan yang sama, "
                "atau menuliskan alamat berikut:\n"
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
        self._tampilkan_catatan(pesan, galat=True)

    def _tampilkan_catatan(self, pesan: str, *, galat: bool) -> None:
        self._label_error.setProperty("error", "true" if galat else "false")
        self._label_error.setProperty("muted", "true" if pesan and not galat else "false")
        gaya = self._label_error.style()
        gaya.unpolish(self._label_error)
        gaya.polish(self._label_error)
        self._label_error.setText(pesan)
        self._label_error.setVisible(bool(pesan))
        self._sesuaikan_tinggi()

    def _cari_server(self) -> None:
        if getattr(self, "_pencari", None) is not None and self._pencari.isRunning():
            return
        self._tombol_cari.setEnabled(False)
        self._baris_pilih.setVisible(False)
        self._tampilkan_catatan("Mencari PostgreSQL di jaringan ini…", galat=False)
        self._pencari = _PencariServer(int(self.isian_port.value()), self)
        self._pencari.selesai.connect(self._sesudah_cari)
        self._pencari.start()

    def _sesudah_cari(self, hasil: object) -> None:
        self._tombol_cari.setEnabled(True)
        daftar = tuple(hasil)
        self._pilih_server.blockSignals(True)
        self._pilih_server.clear()
        for ip in daftar:
            self._pilih_server.addItem(ip, userData=ip)
        self._pilih_server.blockSignals(False)

        if not daftar:
            self.isian_host.setReadOnly(False)
            self.isian_host.setPlaceholderText("192.168.1.10")
            self._tampilkan_port(True)
            self._tampilkan_error(
                f"Tidak ada PostgreSQL di port {self.isian_port.value()}. "
                "Ganti port bila server memakai nomor lain, atau isi "
                "alamat bila server berada di jaringan yang berbeda."
            )
            return

        self.isian_host.setReadOnly(True)
        if len(daftar) == 1:
            self.isian_host.setText(daftar[0])
            self._baris_pilih.setVisible(False)
            self._tampilkan_catatan(
                f"Ditemukan satu PostgreSQL: {daftar[0]}. Isi kata sandi, "
                "lalu Uji koneksi. Sandi tidak dikirim selama pencarian.",
                galat=False,
            )
            return

        self._baris_pilih.setVisible(True)
        self.isian_host.setText(daftar[0])
        self._tampilkan_catatan(
            "Ditemukan beberapa PostgreSQL. Pilih yang memang server "
            "antrian. Aplikasi tidak memilih sendiri.",
            galat=False,
        )

    def _pilih_alamat_server(self) -> None:
        alamat = self._pilih_server.currentData()
        if alamat:
            self.isian_host.setText(str(alamat))

    def _siapkan_database(self) -> None:
        """
        Buat pengguna dan database antrian di mesin ini.

        Sandi postgres ditanya sekali dan tidak ditulis ke mesin.json.
        Sandi yang sudah diketik di form menjadi sandi pengguna antrian.
        """
        if not self.isian_sandi.text():
            self._tampilkan_error(
                "Isi kata sandi database antrian terlebih dahulu. "
                "Sandi itulah yang akan dibuat."
            )
            return
        salah_sandi = self._salah_ketik_ulang()
        if salah_sandi:
            self._tampilkan_error(salah_sandi)
            return
        from PySide6.QtWidgets import QInputDialog, QLineEdit

        sandi_postgres, jadi = QInputDialog.getText(
            self,
            "Siapkan database",
            "Kata sandi pengguna postgres, yaitu sandi saat PostgreSQL "
            "dipasang. Sandi ini tidak disimpan.\n\n"
            "Sandi di form akan menjadi sandi pengguna antrian.",
            QLineEdit.EchoMode.Password,
        )
        if not jadi:
            return
        hasil = siapkan_database_lokal(
            self.isian_sandi.text(),
            sandi_postgres,
            port=int(self.isian_port.value()),
        )
        if hasil.gagal:
            self._sesudah_gagal_sambungan(hasil.gagal)
            return
        gagal = uji_koneksi(self._pengaturan_dari_form().ke_url())
        if gagal:
            self._sesudah_gagal_sambungan(gagal)
            return
        self._sandi_diterima()
        self._tampilkan_error("")
        from app.ui.common import tampilkan_info

        pesan = "Database antrian siap. Komputer ini dapat menyimpan."
        if hasil.peringatan:
            pesan = f"{pesan}\n\n{hasil.peringatan}"
        tampilkan_info(self, pesan, "Siapkan database")

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
        salah_sandi = self._salah_ketik_ulang()
        if salah_sandi:
            self._tampilkan_error(salah_sandi)
            return
        gagal = uji_koneksi(pengaturan.ke_url())
        if gagal:
            self._sesudah_gagal_sambungan(gagal)
            return
        self._sandi_diterima()
        self._tampilkan_error("")
        from app.ui.common import tampilkan_info

        tampilkan_info(self, "Koneksi berhasil.", "Uji koneksi")

    def _uji_cetak(self) -> None:
        """
        Cetak satu tiket contoh memakai setelan yang sedang di layar.

        Pasangan "Uji koneksi", dan sama pentingnya. Pencetak IWare IW-J200
        menuntut driver POS80 resmi pada port CP001 dan harus menjadi
        pencetak default; bila salah satunya meleset, ketahuannya baru
        ketika pengunjung pertama sudah berdiri di depan anjungan. Jauh
        lebih murah ketahuan sekarang, selagi pemasang masih duduk di depan
        mesinnya.

        Memakai nilai yang sedang DIPILIH, bukan yang sudah tersimpan:
        orang menguji sebelum menyimpan, bukan sesudah.
        """
        from app.services.ticket_service import buat_printer

        mode = self._peran_dari_form().printer_efektif
        if mode == "none":
            self._tampilkan_error(
                "Komputer ini disetel tidak mencetak apa pun, jadi tidak "
                "ada yang dapat diuji."
            )
            return
        if not mode:
            self._tampilkan_error(
                "Peran ini mengikuti pengaturan bersama, yang baru terbaca "
                "sesudah database tersambung. Pilih cara mencetak di atas "
                "untuk mengujinya sekarang."
            )
            return

        hasil = buat_printer(mode, self._base_dir / "tiket").cetak(_tiket_contoh())
        if hasil.gagal:
            self._tampilkan_error(hasil.pesan)
            return
        self._tampilkan_error("")

        from app.ui.common import tampilkan_info

        tujuan = (
            f" Tersimpan di {hasil.berkas}."
            if hasil.berkas is not None
            else ""
        )
        tampilkan_info(
            self,
            f"Tiket contoh dikirim ke pencetak.{tujuan}",
            "Uji cetak",
        )

    def _simpan(self) -> None:
        pengaturan = self._pengaturan_dari_form()
        salah = kesalahan_isian(pengaturan)
        if salah:
            self._tampilkan_error(salah)
            return
        salah_sandi = self._salah_ketik_ulang()
        if salah_sandi:
            self._tampilkan_error(salah_sandi)
            return
        tulis_berkas_mesin(path_berkas_mesin(self._db_path), pengaturan)
        self.pengaturan_tersimpan = pengaturan

        # Berkas kedua, sengaja terpisah: yang ini aman disalin ke komputer
        # lain sebagai contekan, yang di atas memuat kata sandi database.
        peran = self._peran_dari_form()
        tulis_peran(path_berkas_peran(self._db_path), peran)
        self.peran_tersimpan = peran
        self.accept()
