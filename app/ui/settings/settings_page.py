"""
Layar pengaturan aplikasi untuk administrator.

Kontrol yang ditampilkan mengikuti SKEMA di settings_service: kotak centang
untuk boleh/tidak, daftar pilihan untuk yang pilihannya terbatas, dan kotak
angka dengan batas atas-bawah. Dengan begitu nilai yang tidak masuk akal
tidak mungkin diketik sejak awal — bukan sekadar ditolak setelah disimpan.

Penegakan sesungguhnya tetap di service layer. Layar ini hanya membuat
kesalahan lebih sulit dilakukan.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.settings_service import (
    ANGKA,
    BERKAS,
    BOOLEAN,
    PILIHAN,
    Pengaturan,
    SettingsService,
    kelompok_pengaturan,
)
from app.ui.common import jalankan_aman, judul, keterangan, tombol
from app.ui.kiosk.sambutan import (
    folder_media_kios,
    jenis_sambutan_dari_berkas,
    salin_ke_media_kios,
)
from app.ui.style import BORDER, SUCCESS, TEXT_MUTED

#: Lama pesan hasil penyimpanan tampil, dalam milidetik.
JEDA_PESAN = 4000

FILTER_BERKAS_ANJUNGAN = (
    "Gambar dan video (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.mp4 *.mkv *.webm *.avi);;"
    "Gambar (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;"
    "Video (*.mp4 *.mkv *.webm *.avi);;"
    "Semua berkas (*)"
)


class _PemilihBerkas(QWidget):
    """Kotak path plus tombol untuk memilih berkas di komputer ini."""

    berkasDipilih = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        susunan = QHBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(8)

        self.isian = QLineEdit()
        self.isian.setPlaceholderText("ditambah ke folder media/kiosk")
        susunan.addWidget(self.isian, stretch=1)

        pilih = tombol("Pilih berkas…")
        pilih.setObjectName("tombolPilihBerkas")
        pilih.clicked.connect(self._pilih)
        susunan.addWidget(pilih)

    def text(self) -> str:
        return self.isian.text()

    def setText(self, nilai: str) -> None:  # noqa: N802 - menyamai QLineEdit
        self.isian.setText(nilai)

    def _pilih(self) -> None:
        folder = folder_media_kios()
        awal = str(folder) if folder.is_dir() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih gambar atau video anjungan",
            awal,
            FILTER_BERKAS_ANJUNGAN,
        )
        if not path:
            return
        tujuan = salin_ke_media_kios(Path(path))
        self.isian.setText(tujuan.name)
        self.berkasDipilih.emit(tujuan.name)


class _BarisPengaturan(QWidget):
    """Satu pengaturan: label, kontrol yang sesuai jenisnya, dan penjelasan."""

    def __init__(self, butir: Pengaturan, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.butir = butir

        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(0, 0, 0, 0)
        susunan.setSpacing(4)

        atas = QHBoxLayout()
        atas.setSpacing(12)

        label = QLabel(butir.label)
        label.setMinimumWidth(220)
        label.setWordWrap(True)
        atas.addWidget(label)

        self.kontrol = self._bangun_kontrol()
        atas.addWidget(self.kontrol, stretch=1)
        susunan.addLayout(atas)

        penjelasan = QLabel(butir.keterangan)
        penjelasan.setWordWrap(True)
        penjelasan.setStyleSheet(f"color: {TEXT_MUTED};")
        susunan.addWidget(penjelasan)

    def _bangun_kontrol(self) -> QWidget:
        if self.butir.jenis == BOOLEAN:
            return QCheckBox()

        if self.butir.jenis == PILIHAN:
            kotak = QComboBox()
            for nilai, teks in self.butir.pilihan:
                kotak.addItem(teks, nilai)
            return kotak

        if self.butir.jenis == ANGKA:
            angka = QSpinBox()
            # Batasnya diambil dari SKEMA yang sama dengan yang dipakai
            # service, sehingga tidak mungkin berbeda diam-diam.
            angka.setMinimum(self.butir.minimum if self.butir.minimum is not None else 0)
            angka.setMaximum(
                self.butir.maksimum if self.butir.maksimum is not None else 999_999
            )
            return angka

        if self.butir.jenis == BERKAS:
            return _PemilihBerkas()

        return QLineEdit()

    # -----------------------------------------------------------------

    def tampilkan(self, nilai: str) -> None:
        if self.butir.jenis == BOOLEAN:
            self.kontrol.setChecked(nilai.strip().lower() == "true")
        elif self.butir.jenis == PILIHAN:
            tampil = nilai
            if self.butir.kunci == "kiosk.welcome_kind" and nilai in (
                "gambar",
                "video",
            ):
                tampil = "media"
            indeks = self.kontrol.findData(tampil)
            # Nilai yang tidak dikenal (misalnya dari database lama) tidak
            # boleh membuat pilihan tampak kosong tanpa sebab.
            self.kontrol.setCurrentIndex(indeks if indeks >= 0 else 0)
        elif self.butir.jenis == ANGKA:
            try:
                self.kontrol.setValue(int(nilai))
            except ValueError:
                self.kontrol.setValue(self.kontrol.minimum())
        else:
            self.kontrol.setText(nilai)

    def nilai(self) -> str:
        if self.butir.jenis == BOOLEAN:
            return "true" if self.kontrol.isChecked() else "false"
        if self.butir.jenis == PILIHAN:
            return self.kontrol.currentData()
        if self.butir.jenis == ANGKA:
            return str(self.kontrol.value())
        return self.kontrol.text().strip()


class SettingsPage(QWidget):
    """Pengelolaan pengaturan aplikasi."""

    def __init__(self, settings: SettingsService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.baris: dict[str, _BarisPengaturan] = {}

        # Timer dimiliki widget ini, bukan QTimer.singleShot yang statis.
        # singleShot tidak terikat pada apa pun sehingga tetap menyala
        # setelah halamannya dihapus, lalu menyentuh label yang sudah tidak
        # ada — aplikasi berhenti bila ditutup tepat setelah menyimpan.
        self._penghapus_pesan = QTimer(self)
        self._penghapus_pesan.setSingleShot(True)

        self._bangun_tampilan()
        self.muat_ulang()
        pemilih = self.baris.get("kiosk.welcome_file")
        if pemilih is not None and isinstance(pemilih.kontrol, _PemilihBerkas):
            pemilih.kontrol.berkasDipilih.connect(self._sesuaikan_jenis_sambutan)

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        luar = QVBoxLayout(self)
        luar.setContentsMargins(24, 20, 24, 20)
        luar.setSpacing(14)

        luar.addWidget(judul("Pengaturan Aplikasi"))
        luar.addWidget(
            keterangan(
                "Perubahan berlaku setelah layar yang bersangkutan dimuat ulang "
                "atau aplikasi dibuka kembali."
            )
        )

        gulung = QScrollArea()
        gulung.setWidgetResizable(True)
        gulung.setFrameShape(QFrame.Shape.NoFrame)
        luar.addWidget(gulung, stretch=1)

        isi = QWidget()
        susunan = QVBoxLayout(isi)
        susunan.setContentsMargins(0, 0, 8, 0)
        susunan.setSpacing(18)

        for nama, butir_butir in kelompok_pengaturan().items():
            susunan.addWidget(self._bangun_kelompok(nama, butir_butir))
        susunan.addStretch()
        gulung.setWidget(isi)

        baris = QHBoxLayout()
        # Pesan hasil ditaruh sebaris dengan tombolnya, bukan sebagai kotak
        # dialog. Administrator sering mengubah beberapa pengaturan
        # berturut-turut, dan kotak yang harus ditutup setiap kali hanya
        # menambah pekerjaan.
        self.pesan = QLabel("")
        self.pesan.setVisible(False)
        self._penghapus_pesan.timeout.connect(lambda: self.pesan.setVisible(False))
        baris.addWidget(self.pesan)
        baris.addStretch()

        batal = tombol("Batalkan Perubahan")
        batal.clicked.connect(self.muat_ulang)
        baris.addWidget(batal)

        simpan = tombol("Simpan", variant="primary")
        simpan.clicked.connect(self.simpan)
        baris.addWidget(simpan)
        luar.addLayout(baris)

    def _bangun_kelompok(self, nama: str, butir_butir: list[Pengaturan]) -> QWidget:
        panel = QFrame()
        panel.setObjectName("kartuPengaturan")
        panel.setStyleSheet(
            f"QFrame#kartuPengaturan {{ background: white; border: 1px solid {BORDER};"
            " border-radius: 6px; }"
        )

        susunan = QVBoxLayout(panel)
        susunan.setContentsMargins(18, 16, 18, 16)
        susunan.setSpacing(14)

        kepala = QLabel(nama)
        kepala.setProperty("heading", "true")
        susunan.addWidget(kepala)

        for butir in butir_butir:
            baris = _BarisPengaturan(butir)
            self.baris[butir.kunci] = baris
            susunan.addWidget(baris)

        return panel

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        """Isi seluruh kontrol dari nilai yang tersimpan."""
        berhasil, tersimpan = jalankan_aman(
            self, self.settings.all, "Gagal membaca pengaturan"
        )
        if not berhasil or tersimpan is None:
            return
        for kunci, baris in self.baris.items():
            baris.tampilkan(tersimpan.get(kunci, ""))

    def simpan(self) -> None:
        """
        Simpan hanya pengaturan yang benar-benar berubah.

        Menulis semuanya akan memenuhi audit log dengan baris perubahan
        untuk nilai yang sebenarnya tidak disentuh, sehingga jejak perubahan
        yang sungguhan justru tenggelam.
        """
        berhasil, tersimpan = jalankan_aman(
            self, self.settings.all, "Gagal membaca pengaturan"
        )
        if not berhasil or tersimpan is None:
            return

        berubah = {
            kunci: baris.nilai()
            for kunci, baris in self.baris.items()
            if baris.nilai() != tersimpan.get(kunci)
        }
        if not berubah:
            self._beritahu("Tidak ada pengaturan yang berubah.")
            return

        for kunci, nilai in berubah.items():
            sukses, _ = jalankan_aman(
                self,
                lambda k=kunci, v=nilai: self.settings.set(k, v),
                "Gagal menyimpan pengaturan",
            )
            if not sukses:
                # Berhenti pada kegagalan pertama lalu muat ulang, supaya
                # yang tampil di layar sama dengan yang benar-benar tersimpan.
                self.muat_ulang()
                return

        self.muat_ulang()
        self._beritahu(f"{len(berubah)} pengaturan tersimpan.")

    def _sesuaikan_jenis_sambutan(self, nama: str) -> None:
        """Pilih berkas gambar/video ikut mengganti jenis tampilan panel."""
        jenis = jenis_sambutan_dari_berkas(nama)
        if jenis is None or "kiosk.welcome_kind" not in self.baris:
            return
        self.baris["kiosk.welcome_kind"].tampilkan(jenis)

    def _beritahu(self, teks: str) -> None:
        self.pesan.setText(teks)
        self.pesan.setStyleSheet(f"color: {SUCCESS}; font-weight: 600;")
        self.pesan.setVisible(True)
        self._penghapus_pesan.start(JEDA_PESAN)
