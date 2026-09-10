"""Halaman pengelolaan data master."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.errors import BusinessRuleError
from app.services.master_data_service import MasterDataService
from app.services.user_service import UserService
from app.ui.common import (
    jalankan_aman,
    keterangan,
    konfirmasi,
    tampilkan_info,
    tampilkan_peringatan,
    tombol,
)
from app.ui.settings.dialogs import (
    LABEL_PERAN,
    CategoryDialog,
    CounterCategoryDialog,
    CounterDialog,
    ResetPasswordDialog,
    UserDialog,
)
from app.ui.style import badge_status


class _TabelTab(QWidget):
    """
    Kerangka bersama tab data master: tabel di tengah, tombol aksi di atas.

    Tombol yang membutuhkan baris terpilih otomatis nonaktif selama belum
    ada yang dipilih, sehingga petugas tidak menekan tombol yang pasti gagal.
    """

    kolom: tuple[str, ...] = ()
    penjelasan: str = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tombol_perlu_pilihan: list = []

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(16, 16, 16, 16)
        susunan.setSpacing(12)

        if self.penjelasan:
            susunan.addWidget(keterangan(self.penjelasan))

        #: Pita peringatan, tersembunyi selama tidak ada yang perlu
        #: dikatakan. Disediakan sejak awal supaya tab yang memakainya
        #: tidak perlu menyusun ulang tata letaknya saat pertama muncul.
        self.peringatan = QLabel()
        self.peringatan.setObjectName("peringatanData")
        self.peringatan.setWordWrap(True)
        self.peringatan.setVisible(False)
        susunan.addWidget(self.peringatan)

        self.baris_aksi = QHBoxLayout()
        self.baris_aksi.setSpacing(8)
        susunan.addLayout(self.baris_aksi)

        self.tabel = QTableWidget(0, len(self.kolom))
        self.tabel.setHorizontalHeaderLabels(self.kolom)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.tabel.itemSelectionChanged.connect(self._perbarui_tombol)
        susunan.addWidget(self.tabel)

    # -----------------------------------------------------------------

    def tambah_aksi(
        self, teks: str, handler: Callable[[], None], *, perlu_pilihan: bool = False,
        variant: str = "",
    ):
        btn = tombol(teks, variant=variant)
        btn.clicked.connect(handler)
        self.baris_aksi.addWidget(btn)
        if perlu_pilihan:
            btn.setEnabled(False)
            self._tombol_perlu_pilihan.append(btn)
        return btn

    def selesai_menyusun_aksi(self) -> None:
        self.baris_aksi.addStretch()

    def setel_peringatan(self, teks: str) -> None:
        """Tampilkan pita peringatan, atau sembunyikan bila teksnya kosong."""
        self.peringatan.setText(teks)
        self.peringatan.setVisible(bool(teks))

    def _perbarui_tombol(self) -> None:
        ada = self.baris_terpilih() is not None
        for btn in self._tombol_perlu_pilihan:
            btn.setEnabled(ada)

    def baris_terpilih(self) -> int | None:
        baris = self.tabel.currentRow()
        return baris if baris >= 0 else None

    def id_terpilih(self) -> int | None:
        """ID data pada baris terpilih, disimpan di kolom pertama."""
        baris = self.baris_terpilih()
        if baris is None:
            return None
        item = self.tabel.item(baris, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def isi_baris(self, baris: int, nilai: list[str], data_id: int) -> None:
        for kolom, teks in enumerate(nilai):
            item = QTableWidgetItem(teks)
            if kolom == 0:
                item.setData(Qt.ItemDataRole.UserRole, data_id)
            self.tabel.setItem(baris, kolom, item)

    def pilih_id(self, data_id: int) -> None:
        """Sorot kembali baris dengan id ini setelah tabel disusun ulang."""
        for baris in range(self.tabel.rowCount()):
            item = self.tabel.item(baris, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == data_id:
                self.tabel.setCurrentCell(baris, 0)
                return

    def muat_ulang(self) -> None:  # pragma: no cover - diisi turunannya
        raise NotImplementedError


def _perbarui_peringatan_layanan(
    tab: _TabelTab, master: MasterDataService
) -> list:
    """
    Segarkan pita "layanan tanpa loket", dan kembalikan daftarnya.

    Peringatan yang sama dipasang di tab Loket DAN tab Jenis Layanan.
    Keadaannya lahir dari hubungan keduanya, jadi admin yang sedang
    membuka salah satunya harus dapat melihatnya tanpa perlu menebak
    bahwa jawabannya ada di tab sebelah.
    """
    berhasil, yatim = jalankan_aman(tab, master.layanan_tanpa_loket)
    yatim = yatim if berhasil else []
    if yatim:
        nama = ", ".join(kategori.name for kategori in yatim)
        tab.setel_peringatan(
            f"Tidak dilayani loket mana pun: {nama}. Nomornya masih bisa "
            "diambil di anjungan, tetapi tidak akan ada loket yang bisa "
            "memanggilnya."
        )
    else:
        tab.setel_peringatan("")
    return yatim


def _laporkan_cakupan_baru(tab: _TabelTab, sebelum: list, sesudah: list) -> None:
    """
    Beri tahu bila tindakan barusan meninggalkan layanan tanpa loket.

    Pita di atas tabel sudah mengabarkannya, tetapi pita itu menetap dan
    karenanya mudah terbaca sebagai bagian tetap dari halaman. Keadaan yang
    baru saja DIBUAT oleh tindakan admin perlu satu kotak yang harus
    ditutup — di situlah hubungan sebab-akibatnya masih terasa.

    Yang dilaporkan hanya yang bertambah. Layanan yang sudah tanpa loket
    sejak sebelum tindakan ini bukan akibat dari tindakan ini, dan
    menyebutkannya lagi setiap kali admin menyimpan apa pun akan membuat
    kotak ini cepat ditutup tanpa dibaca.
    """
    lama = {kategori.id for kategori in sebelum}
    baru = [kategori for kategori in sesudah if kategori.id not in lama]
    if not baru:
        return
    nama = ", ".join(kategori.name for kategori in baru)
    tampilkan_peringatan(
        tab,
        f"Tersimpan, tetapi kini tidak ada loket yang melayani {nama}.\n\n"
        "Pengunjung masih bisa mengambil nomornya di anjungan dan tidak akan "
        "ada yang bisa memanggilnya. Tambahkan jenis layanan itu ke salah "
        "satu loket, atau nonaktifkan layanannya.",
    )


class CounterTab(_TabelTab):
    """Pengelolaan loket."""

    kolom = ("Kode", "Nama Loket", "Jenis Layanan", "Status")
    penjelasan = (
        "Loket tidak dapat dihapus, hanya dinonaktifkan. Loket yang "
        "dinonaktifkan hilang dari pilihan petugas tetapi riwayat "
        "pemanggilannya tetap utuh. Loket yang jenis layanannya dibiarkan "
        "\"Semua\" memanggil antrian apa pun — itu keadaan yang disarankan "
        "kecuali memang ada loket khusus."
    )

    def __init__(self, master: MasterDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.master = master

        self.tambah_aksi("Tambah Loket", self.tambah, variant="primary")
        self.tambah_aksi("Ubah Nama", self.ubah, perlu_pilihan=True)
        self.tambah_aksi("Atur Layanan", self.atur_layanan, perlu_pilihan=True)
        self.tombol_status = self.tambah_aksi(
            "Nonaktifkan", self.ganti_status, perlu_pilihan=True
        )
        self.selesai_menyusun_aksi()

        self.data: list = []
        self.kategori: list = []
        #: Jenis layanan aktif yang tidak dilayani loket aktif mana pun.
        self.yatim: list = []
        self.muat_ulang()

    def muat_ulang(self) -> None:
        berhasil, data = jalankan_aman(self, self.master.list_counters)
        if not berhasil:
            return
        berhasil_kategori, kategori = jalankan_aman(self, self.master.list_categories)
        self.kategori = kategori if berhasil_kategori else []
        nama_kategori = {k.id: k.name for k in self.kategori}

        self.data = data
        self.tabel.setRowCount(len(data))
        for baris, loket in enumerate(data):
            layanan = (
                "Semua"
                if loket.melayani_semua
                else ", ".join(
                    nama_kategori.get(k, "?") for k in loket.category_ids
                )
            )
            self.isi_baris(
                baris,
                [loket.code, loket.name, layanan, badge_status(loket.is_active)],
                loket.id,
            )
        self.yatim = _perbarui_peringatan_layanan(self, self.master)
        self._perbarui_tombol()

    def atur_layanan(self) -> None:
        baris = self.baris_terpilih()
        if baris is None:
            return
        loket = self.data[baris]

        dialog = CounterCategoryDialog(self, counter=loket, categories=self.kategori)
        if dialog.exec() != CounterCategoryDialog.DialogCode.Accepted:
            return
        sebelum = self.yatim
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.master.set_counter_categories(loket.id, dialog.terpilih),
        )
        if berhasil:
            self.muat_ulang()
            _laporkan_cakupan_baru(self, sebelum, self.yatim)

    def _perbarui_tombol(self) -> None:
        super()._perbarui_tombol()
        baris = self.baris_terpilih()
        if baris is not None and baris < len(self.data):
            aktif = self.data[baris].is_active
            self.tombol_status.setText("Nonaktifkan" if aktif else "Aktifkan")

    def tambah(self) -> None:
        dialog = CounterDialog(self)
        if dialog.exec() != CounterDialog.DialogCode.Accepted:
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.master.create_counter(code=dialog.kode, name=dialog.nama),
        )
        if berhasil:
            self.muat_ulang()

    def ubah(self) -> None:
        baris = self.baris_terpilih()
        if baris is None:
            return
        loket = self.data[baris]

        dialog = CounterDialog(self, counter=loket)
        if dialog.exec() != CounterDialog.DialogCode.Accepted:
            return
        berhasil, _ = jalankan_aman(
            self, lambda: self.master.update_counter(loket.id, name=dialog.nama)
        )
        if berhasil:
            self.muat_ulang()

    def ganti_status(self) -> None:
        baris = self.baris_terpilih()
        if baris is None:
            return
        loket = self.data[baris]
        aktifkan = not loket.is_active

        if not aktifkan and not konfirmasi(
            self, f"Nonaktifkan {loket.name}?\n\nLoket tidak akan muncul lagi "
            "sebagai pilihan petugas."
        ):
            return

        sebelum = self.yatim
        berhasil, _ = jalankan_aman(
            self, lambda: self.master.set_counter_status(loket.id, aktifkan)
        )
        if berhasil:
            self.muat_ulang()
            _laporkan_cakupan_baru(self, sebelum, self.yatim)


class CategoryTab(_TabelTab):
    """Pengelolaan jenis layanan dan prefix nomor antrian."""

    kolom = ("Kode", "Nama Layanan", "Prefix", "Contoh Nomor", "Status")

    #: Penjorok baris anak pada kolom nama. Susunan induk-anak diperlihatkan
    #: lewat jarak, bukan lewat kolom "Induk" tersendiri: nama induknya
    #: sudah berdiri persis di atasnya, dan kolom yang mengulanginya di
    #: setiap baris anak hanya memakan lebar tanpa menambah keterangan.
    JOROK = "        "
    penjelasan = (
        "Prefix menentukan nomor antrian tiap jenis layanan. Prefix wajib "
        "berbeda antar layanan agar nomor tidak bertabrakan. Urutan baris di "
        "bawah ini adalah urutan tombol di anjungan; ubah dengan Naik dan "
        "Turun."
    )

    def __init__(self, master: MasterDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.master = master

        self.tambah_aksi("Tambah Jenis Layanan", self.tambah, variant="primary")
        self.tambah_aksi("Ubah", self.ubah, perlu_pilihan=True)
        self.tombol_naik = self.tambah_aksi(
            "Naik", lambda: self.pindahkan(naik=True), perlu_pilihan=True
        )
        self.tombol_turun = self.tambah_aksi(
            "Turun", lambda: self.pindahkan(naik=False), perlu_pilihan=True
        )
        self.tombol_status = self.tambah_aksi(
            "Nonaktifkan", self.ganti_status, perlu_pilihan=True
        )
        self.tambah_aksi("Hapus", self.hapus, perlu_pilihan=True)
        self.selesai_menyusun_aksi()

        self.data: list = []
        #: Jenis layanan aktif yang tidak dilayani loket aktif mana pun.
        self.yatim: list = []
        self.muat_ulang()

    def muat_ulang(self) -> None:
        berhasil, data = jalankan_aman(self, self.master.list_categories)
        if not berhasil:
            return

        self.data = data
        self.tabel.setRowCount(len(data))
        for baris, layanan in enumerate(data):
            self.isi_baris(
                baris,
                [
                    layanan.code,
                    self.JOROK * layanan.level + layanan.name,
                    layanan.prefix,
                    layanan.contoh_nomor,
                    badge_status(layanan.is_active),
                ],
                layanan.id,
            )
        self.yatim = _perbarui_peringatan_layanan(self, self.master)
        self._perbarui_tombol()

    def _perbarui_tombol(self) -> None:
        super()._perbarui_tombol()
        baris = self.baris_terpilih()
        if baris is not None and baris < len(self.data):
            aktif = self.data[baris].is_active
            self.tombol_status.setText("Nonaktifkan" if aktif else "Aktifkan")
        # Baris teratas tidak bisa naik dan baris terbawah tidak bisa
        # turun. Dimatikan di sini, bukan dijawab dengan pesan kesalahan
        # sesudah ditekan: batas urutan terlihat sendiri di layar, jadi
        # tombolnya tidak perlu berpura-pura masih bisa dipakai.
        #
        # Batasnya dihitung DI ANTARA SAUDARA SEKELOMPOK, bukan pada
        # seluruh tabel. PBB adalah baris kedua tabel tetapi baris pertama
        # di dalam Konsultasi; tombol Naik di situ tidak akan melakukan
        # apa pun bila ditekan.
        if baris is None or baris >= len(self.data):
            self.tombol_naik.setEnabled(False)
            self.tombol_turun.setEnabled(False)
            return
        induk = self.data[baris].parent_id
        saudara = [i for i, k in enumerate(self.data) if k.parent_id == induk]
        self.tombol_naik.setEnabled(baris != saudara[0])
        self.tombol_turun.setEnabled(baris != saudara[-1])

    def pindahkan(self, *, naik: bool) -> None:
        """
        Geser jenis layanan terpilih satu langkah, lalu sorot kembali.

        Tanpa penyorotan ulang, tombolnya hanya bisa ditekan sekali:
        tabel disusun ulang, pilihannya hilang, dan admin harus mengklik
        barisnya lagi untuk setiap satu langkah.
        """
        baris = self.baris_terpilih()
        if baris is None:
            return
        layanan = self.data[baris]

        berhasil, _ = jalankan_aman(
            self, lambda: self.master.pindahkan_category(layanan.id, naik=naik)
        )
        if berhasil:
            self.muat_ulang()
            self.pilih_id(layanan.id)

    def tambah(self) -> None:
        dialog = CategoryDialog(self, semua=self.data)
        if dialog.exec() != CategoryDialog.DialogCode.Accepted:
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.master.create_category(
                code=dialog.kode,
                name=dialog.nama,
                prefix=dialog.prefix,
                info_text=dialog.info_text,
                parent_id=dialog.induk_id,
            ),
        )
        if berhasil:
            self.muat_ulang()

    def ubah(self) -> None:
        baris = self.baris_terpilih()
        if baris is None:
            return
        layanan = self.data[baris]

        dialog = CategoryDialog(self, category=layanan, semua=self.data)
        if dialog.exec() != CategoryDialog.DialogCode.Accepted:
            return

        def simpan():
            return self.master.update_category(
                layanan.id,
                name=dialog.nama,
                prefix=dialog.prefix,
                info_text=dialog.info_text,
                parent_id=dialog.induk_id,
            )

        try:
            simpan()
        except BusinessRuleError:
            # Prefix terkunci karena sudah dipakai antrian. Nama dan info
            # anjungan tetap disimpan supaya perubahan petugas tidak hilang
            # percuma.
            berhasil, _ = jalankan_aman(
                self,
                lambda: self.master.update_category(
                    layanan.id,
                    name=dialog.nama,
                    info_text=dialog.info_text,
                    parent_id=dialog.induk_id,
                ),
            )
            if berhasil:
                tampilkan_info(
                    self,
                    "Nama berhasil diubah, tetapi prefix tidak dapat diubah "
                    "karena jenis layanan ini sudah dipakai antrian.",
                    "Sebagian tersimpan",
                )
            self.muat_ulang()
            return
        except Exception as exc:  # noqa: BLE001 - batas UI
            from app.ui.common import tampilkan_error

            tampilkan_error(self, exc)
            return

        self.muat_ulang()

    def hapus(self) -> None:
        """
        Hapus jenis layanan yang belum pernah dipakai.

        Service yang memutuskan boleh atau tidaknya — di sini cukup
        meneruskan penolakannya apa adanya, karena pesannya sudah
        menjelaskan bahwa yang benar adalah menonaktifkan.
        """
        baris = self.baris_terpilih()
        if baris is None:
            return
        layanan = self.data[baris]

        if not konfirmasi(
            self,
            f"Hapus {layanan.name} secara permanen?\n\nHanya bisa dihapus bila "
            "belum pernah dipakai satu nomor antrian pun. Bila sudah pernah, "
            "gunakan Nonaktifkan.",
        ):
            return

        berhasil, _ = jalankan_aman(
            self, lambda: self.master.delete_category(layanan.id)
        )
        if berhasil:
            self.muat_ulang()

    def ganti_status(self) -> None:
        baris = self.baris_terpilih()
        if baris is None:
            return
        layanan = self.data[baris]
        aktifkan = not layanan.is_active

        if not aktifkan and not konfirmasi(
            self,
            f"Nonaktifkan layanan {layanan.name}?\n\nNomor antrian "
            f"{layanan.prefix}- tidak akan diterbitkan lagi.",
        ):
            return

        sebelum = self.yatim
        berhasil, _ = jalankan_aman(
            self, lambda: self.master.set_category_status(layanan.id, aktifkan)
        )
        if berhasil:
            self.muat_ulang()
            _laporkan_cakupan_baru(self, sebelum, self.yatim)


class UserTab(_TabelTab):
    """Pengelolaan akun petugas."""

    kolom = (
        "Nama Pengguna",
        "Nama Lengkap",
        "Peran",
        "Loket Bawaan",
        "Status",
        "Terakhir Masuk",
    )
    penjelasan = (
        "Akun tidak dapat dihapus, hanya dinonaktifkan, agar riwayat "
        "pemanggilan dan survey yang menunjuk petugas tetap dapat dibaca. "
        "Loket bawaan langsung terpilih saat petugas masuk; petugas tetap "
        "boleh berpindah sendiri bila pindah meja."
    )

    def __init__(
        self,
        users: UserService,
        master: MasterDataService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.users = users
        self.master = master
        self.loket: list = []

        self.tambah_aksi("Tambah Akun", self.tambah, variant="primary")
        self.tambah_aksi("Ubah", self.ubah, perlu_pilihan=True)
        self.tambah_aksi("Setel Ulang Kata Sandi", self.reset_sandi, perlu_pilihan=True)
        self.tombol_status = self.tambah_aksi(
            "Nonaktifkan", self.ganti_status, perlu_pilihan=True
        )
        self.selesai_menyusun_aksi()

        self.data: list = []
        self.muat_ulang()

    def muat_ulang(self) -> None:
        berhasil, data = jalankan_aman(self, self.users.list_users)
        if not berhasil:
            return
        berhasil_loket, loket = jalankan_aman(self, self.master.list_counters)
        self.loket = loket if berhasil_loket else []
        nama_loket = {l.id: l.name for l in self.loket}

        self.data = data
        self.tabel.setRowCount(len(data))
        for baris, akun in enumerate(data):
            masuk = (
                akun.last_login_at.strftime("%d/%m/%Y %H:%M")
                if akun.last_login_at
                else "belum pernah"
            )
            self.isi_baris(
                baris,
                [
                    akun.username,
                    akun.full_name,
                    LABEL_PERAN.get(akun.role, akun.role.value),
                    nama_loket.get(akun.default_counter_id, "—"),
                    badge_status(akun.is_active),
                    masuk,
                ],
                akun.id,
            )
        self._perbarui_tombol()

    def _perbarui_tombol(self) -> None:
        super()._perbarui_tombol()
        baris = self.baris_terpilih()
        if baris is not None and baris < len(self.data):
            aktif = self.data[baris].is_active
            self.tombol_status.setText("Nonaktifkan" if aktif else "Aktifkan")

    def tambah(self) -> None:
        dialog = UserDialog(self, counters=self.loket)
        if dialog.exec() != UserDialog.DialogCode.Accepted:
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.users.create_user(
                username=dialog.username,
                full_name=dialog.nama_lengkap,
                password=dialog.password,
                role=dialog.peran,
                default_counter_id=dialog.loket_bawaan,
            ),
        )
        if berhasil:
            tampilkan_info(
                self,
                f"Akun {dialog.username} dibuat. Petugas akan diminta mengganti "
                "kata sandi saat pertama kali masuk.",
            )
            self.muat_ulang()

    def ubah(self) -> None:
        baris = self.baris_terpilih()
        if baris is None:
            return
        akun = self.data[baris]

        dialog = UserDialog(self, user=akun, counters=self.loket)
        if dialog.exec() != UserDialog.DialogCode.Accepted:
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.users.update_user(
                akun.id,
                full_name=dialog.nama_lengkap,
                role=dialog.peran,
                default_counter_id=dialog.loket_bawaan,
            ),
        )
        if berhasil:
            self.muat_ulang()

    def reset_sandi(self) -> None:
        baris = self.baris_terpilih()
        if baris is None:
            return
        akun = self.data[baris]

        dialog = ResetPasswordDialog(self, nama_petugas=akun.full_name)
        if dialog.exec() != ResetPasswordDialog.DialogCode.Accepted:
            return
        berhasil, _ = jalankan_aman(
            self, lambda: self.users.reset_password(akun.id, dialog.password)
        )
        if berhasil:
            tampilkan_info(
                self,
                f"Kata sandi {akun.username} telah disetel ulang. Petugas wajib "
                "menggantinya saat masuk berikutnya.",
            )
            self.muat_ulang()

    def ganti_status(self) -> None:
        baris = self.baris_terpilih()
        if baris is None:
            return
        akun = self.data[baris]
        aktifkan = not akun.is_active

        if not aktifkan and not konfirmasi(
            self,
            f"Nonaktifkan akun {akun.username}?\n\nPetugas tidak akan dapat "
            "masuk ke aplikasi.",
        ):
            return

        berhasil, _ = jalankan_aman(
            self, lambda: self.users.set_user_status(akun.id, aktifkan)
        )
        if berhasil:
            self.muat_ulang()


class BranchTab(QWidget):
    """Identitas kantor. Kode cabang tidak dapat diubah."""

    def __init__(self, master: MasterDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.master = master

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(16, 16, 16, 16)
        susunan.setSpacing(12)
        susunan.addWidget(
            keterangan(
                "Nama dan alamat kantor tampil pada tiket antrian dan laporan."
            )
        )

        from PySide6.QtWidgets import QFormLayout

        form = QFormLayout()
        form.setSpacing(12)

        self.label_kode = keterangan("—")
        form.addRow("Kode Cabang", self.label_kode)

        self.input_nama = QLineEdit()
        form.addRow("Nama Kantor", self.input_nama)

        self.input_alamat = QLineEdit()
        self.input_alamat.setPlaceholderText("opsional")
        form.addRow("Alamat", self.input_alamat)

        susunan.addLayout(form)

        baris = QHBoxLayout()
        self.tombol_simpan = tombol("SIMPAN", variant="primary")
        self.tombol_simpan.clicked.connect(self.simpan)
        baris.addWidget(self.tombol_simpan)
        baris.addStretch()
        susunan.addLayout(baris)
        susunan.addStretch()

        self.branch = None
        self.muat_ulang()

    def muat_ulang(self) -> None:
        berhasil, data = jalankan_aman(self, self.master.list_branches)
        if not berhasil or not data:
            return

        self.branch = data[0]
        self.label_kode.setText(self.branch.code)
        self.input_nama.setText(self.branch.name)
        self.input_alamat.setText(self.branch.address or "")

    def simpan(self) -> None:
        if self.branch is None:
            return
        berhasil, _ = jalankan_aman(
            self,
            lambda: self.master.update_branch(
                self.branch.id,
                name=self.input_nama.text(),
                address=self.input_alamat.text(),
            ),
        )
        if berhasil:
            tampilkan_info(self, "Identitas kantor tersimpan.")
            self.muat_ulang()


class MasterDataPage(QWidget):
    """Halaman data master, berisi tab loket, jenis layanan, akun, dan kantor."""

    def __init__(
        self,
        master: MasterDataService,
        users: UserService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)

        self.tab = QTabWidget()
        # Tanpa ini, Qt memasang panah gulir yang menutupi tab pertama dan
        # terakhir walaupun ruangnya masih lebar.
        self.tab.tabBar().setUsesScrollButtons(False)
        self.tab_loket = CounterTab(master)
        self.tab_layanan = CategoryTab(master)
        self.tab_akun = UserTab(users, master)
        self.tab_kantor = BranchTab(master)

        self.tab.addTab(self.tab_loket, "Loket")
        self.tab.addTab(self.tab_layanan, "Jenis Layanan")
        self.tab.addTab(self.tab_akun, "Akun Petugas")
        self.tab.addTab(self.tab_kantor, "Identitas Kantor")

        susunan.addWidget(self.tab)

        self.tab.currentChanged.connect(self._tab_berpindah)

    def _tab_berpindah(self, indeks: int) -> None:
        """
        Segarkan tab yang baru ditampilkan.

        Tab Loket dan tab Jenis Layanan memandang keadaan yang sama dari
        dua sisi: membatasi loket di satu tab mengubah peringatan "layanan
        tanpa loket" di tab sebelah. Tanpa penyegaran ini, admin yang
        berpindah tab menemukan peringatan yang sudah tidak benar lagi.
        """
        widget = self.tab.widget(indeks)
        if widget is not None:
            widget.muat_ulang()

    def muat_ulang(self) -> None:
        for tab in (self.tab_loket, self.tab_layanan, self.tab_akun, self.tab_kantor):
            tab.muat_ulang()
