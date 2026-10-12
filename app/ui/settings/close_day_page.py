"""
Layar Tutup Hari / Lanjutkan untuk administrator.

Dua tindakan yang saling melengkapi:

* **Tutup Hari** — mencadangkan database, menghentikan pendaftaran nomor
  baru, lalu membatalkan seluruh antrian yang belum selesai. Dipakai di
  akhir jam operasional.
* **Lanjutkan** — kebalikan Tutup Hari dalam satu tombol: mengembalikan
  antrian dari Tutup Hari PALING BARU menjadi menunggu lagi (bila ada dan
  belum disentuh lagi sejak itu — lihat `QueueService.buka_kembali_hari`),
  lalu menyalakan kembali pendaftaran nomor baru bila masih tertutup
  (`QueueService.buka_pendaftaran`). Tombol ini tetap berguna sendirian
  untuk membuka pendaftaran yang ditutup manual di luar Tutup Hari (lihat
  halaman Registrasi), bukan hanya untuk membatalkan Tutup Hari. Tidak
  perlu ditekan di pagi hari dalam keadaan normal: pendaftaran yang
  ditutup kemarin otomatis terbuka lagi begitu tanggal berganti.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.services.backup_service import BackupService
from app.services.queue_service import LABEL_STATUS, STATUS_BELUM_SELESAI, QueueService
from app.ui.common import jalankan_aman, judul, keterangan, konfirmasi, tampilkan_info, tombol


class CloseDayPage(QWidget):
    """Penutupan dan pembukaan hari operasional."""

    def __init__(
        self,
        queue: QueueService,
        backup: BackupService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.backup = backup

        self._bangun_tampilan()
        self.muat_ulang()

    # -----------------------------------------------------------------
    # Tampilan
    # -----------------------------------------------------------------

    def _bangun_tampilan(self) -> None:
        susunan = QVBoxLayout(self)
        susunan.setContentsMargins(24, 20, 24, 20)
        susunan.setSpacing(20)

        susunan.addWidget(judul("Tutup Hari"))
        susunan.addWidget(
            keterangan(
                "Database dicadangkan otomatis, pendaftaran nomor baru "
                "dihentikan, lalu seluruh nomor yang belum selesai — "
                "menunggu, dipanggil, dilayani, maupun ditunda — dibatalkan. "
                "Nomor yang sudah selesai dilayani tidak tersentuh."
            )
        )
        self.label_ringkasan = keterangan("")
        susunan.addWidget(self.label_ringkasan)
        self.tombol_tutup = tombol("Tutup Hari", variant="danger")
        self.tombol_tutup.clicked.connect(self.tutup_hari)
        susunan.addWidget(self.tombol_tutup)

        susunan.addWidget(judul("Lanjutkan"))
        susunan.addWidget(
            keterangan(
                "Salah pencet Tutup Hari? Kembalikan antrian yang baru saja "
                "dibatalkan menjadi menunggu lagi, seolah belum pernah "
                "dipanggil, lalu buka kembali pendaftaran nomor baru. Juga "
                "bisa dipakai sendirian untuk membuka pendaftaran yang "
                "ditutup manual di luar Tutup Hari."
            )
        )
        self.label_lanjutkan = keterangan("")
        susunan.addWidget(self.label_lanjutkan)
        self.tombol_lanjutkan = tombol("Lanjutkan", variant="primary")
        self.tombol_lanjutkan.clicked.connect(self.lanjutkan)
        susunan.addWidget(self.tombol_lanjutkan)

        susunan.addStretch()

    # -----------------------------------------------------------------
    # Data
    # -----------------------------------------------------------------

    def muat_ulang(self) -> None:
        self._muat_ringkasan_tutup()
        self._muat_ringkasan_lanjutkan()

    def _muat_ringkasan_tutup(self) -> None:
        berhasil, ringkasan = jalankan_aman(
            self, self.queue.ringkasan_tutup_hari, "Gagal membaca ringkasan antrian"
        )
        if not berhasil:
            self.tombol_tutup.setEnabled(False)
            return

        ringkasan = ringkasan or {}
        total = sum(ringkasan.values())
        if total == 0:
            self.label_ringkasan.setText("Tidak ada antrian yang tersisa untuk ditutup.")
            self.tombol_tutup.setEnabled(False)
            return

        # Urutannya mengikuti STATUS_BELUM_SELESAI, sumber yang sama dengan
        # yang dipakai `ringkasan_tutup_hari()` untuk menyusun kuncinya.
        # Menyalin daftarnya ke sini akan diam-diam menghilangkan status
        # baru dari ringkasan, padahal antriannya tetap ikut dibatalkan.
        rincian = ", ".join(
            f"{LABEL_STATUS[status]}: {ringkasan.get(status, 0)}"
            for status in STATUS_BELUM_SELESAI
            if ringkasan.get(status, 0) > 0
        )
        self.label_ringkasan.setText(f"{total} antrian akan dibatalkan ({rincian}).")
        self.tombol_tutup.setEnabled(True)

    def _muat_ringkasan_lanjutkan(self) -> None:
        berhasil, jumlah = jalankan_aman(
            self, self.queue.ringkasan_buka_kembali_hari, "Gagal membaca ringkasan"
        )
        jumlah = jumlah or 0
        if not berhasil:
            self.tombol_lanjutkan.setEnabled(False)
            return

        berhasil, terbuka = jalankan_aman(
            self, self.queue.pendaftaran_dibuka, "Gagal membaca status pendaftaran"
        )
        if not berhasil:
            self.tombol_lanjutkan.setEnabled(False)
            return

        if jumlah == 0 and terbuka:
            self.label_lanjutkan.setText(
                "Tidak ada Tutup Hari untuk dibatalkan, dan pendaftaran sudah terbuka."
            )
            self.tombol_lanjutkan.setEnabled(False)
            return

        potongan = []
        if jumlah > 0:
            potongan.append(f"{jumlah} antrian dapat dikembalikan menunggu")
        if not terbuka:
            potongan.append("pendaftaran nomor baru akan dibuka")
        self.label_lanjutkan.setText(", ".join(potongan).capitalize() + ".")
        self.tombol_lanjutkan.setEnabled(True)

    # -----------------------------------------------------------------
    # Tindakan
    # -----------------------------------------------------------------

    def tutup_hari(self) -> None:
        if not konfirmasi(
            self,
            "Tutup hari sekarang?\n\n"
            "Database akan dicadangkan otomatis, pendaftaran nomor baru "
            "dihentikan, lalu seluruh antrian yang belum selesai — termasuk "
            "yang sedang dipanggil, dilayani, atau ditunda — dibatalkan. "
            "Bila tertekan keliru, tersedia tombol Lanjutkan sesudah ini.",
            "Tutup Hari",
        ):
            return

        berhasil, _ = jalankan_aman(
            self, lambda: self.backup.backup(alasan="tutup_hari"), "Gagal membuat backup"
        )
        if not berhasil and not konfirmasi(
            self,
            "Backup database gagal dibuat. Lanjutkan menutup hari TANPA "
            "cadangan pengaman?",
            "Backup Gagal",
        ):
            return

        berhasil, _ = jalankan_aman(
            self, self.queue.tutup_pendaftaran, "Gagal menghentikan pendaftaran"
        )
        if not berhasil:
            return

        berhasil, jumlah = jalankan_aman(self, self.queue.tutup_hari, "Gagal menutup hari")
        if not berhasil:
            return

        tampilkan_info(self, f"{jumlah} antrian dibatalkan. Hari ini ditutup.")
        self.muat_ulang()

    def lanjutkan(self) -> None:
        if not konfirmasi(
            self,
            "Kembalikan antrian dari Tutup Hari terakhir menjadi menunggu lagi "
            "dan buka kembali pendaftaran nomor baru?",
            "Lanjutkan",
        ):
            return

        berhasil, jumlah = jalankan_aman(
            self, self.queue.buka_kembali_hari, "Gagal melanjutkan"
        )
        if not berhasil:
            return

        berhasil, terbuka = jalankan_aman(
            self, self.queue.pendaftaran_dibuka, "Gagal membaca status pendaftaran"
        )
        if berhasil and not terbuka:
            berhasil, _ = jalankan_aman(
                self, self.queue.buka_pendaftaran, "Gagal membuka pendaftaran"
            )
            if not berhasil:
                return

        tampilkan_info(
            self, f"{jumlah} antrian dikembalikan menunggu. Pendaftaran dibuka."
        )
        self.muat_ulang()
