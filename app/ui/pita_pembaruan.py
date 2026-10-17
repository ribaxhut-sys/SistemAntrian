"""Pita pemberitahuan pembaruan aplikasi Windows."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar

from app.services.pembaruan_windows import InfoPembaruan
from app.ui.common import tombol
from app.ui.style import PRIMARY, PRIMARY_SOFT


class PitaPembaruan(QFrame):
    def __init__(
        self,
        tindakan: Callable[[], None],
        *,
        untuk_admin: bool = False,
        tunda: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.untuk_admin = untuk_admin
        self._boleh_tunda = tunda is not None
        self.setObjectName("pitaPembaruan")
        self.setStyleSheet(
            f"QFrame#pitaPembaruan {{ background: {PRIMARY_SOFT}; "
            f"border-bottom: 2px solid {PRIMARY}; }}"
        )
        susunan = QHBoxLayout(self)
        susunan.setContentsMargins(16, 9, 16, 9)
        susunan.setSpacing(12)
        self.pesan = QLabel()
        self.pesan.setWordWrap(True)
        self.pesan.setStyleSheet(f"font-weight: 600; color: {PRIMARY};")
        susunan.addWidget(self.pesan, stretch=1)
        self.progres = QProgressBar()
        self.progres.setObjectName("progresPembaruan")
        self.progres.setRange(0, 100)
        self.progres.setFixedWidth(150)
        self.progres.setTextVisible(True)
        self.progres.hide()
        susunan.addWidget(self.progres, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.tombol = tombol(self._teks_unduh(), variant="primary")
        self.tombol.clicked.connect(tindakan)
        susunan.addWidget(self.tombol, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.tombol_catatan = tombol("Apa yang baru?")
        self.tombol_catatan.clicked.connect(self.tampilkan_catatan)
        self.tombol_catatan.hide()
        susunan.addWidget(self.tombol_catatan, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.tombol_tunda = tombol("Ingatkan besok")
        if tunda is not None:
            self.tombol_tunda.clicked.connect(tunda)
            susunan.addWidget(
                self.tombol_tunda, alignment=Qt.AlignmentFlag.AlignVCenter
            )
        else:
            self.tombol_tunda.hide()
        self.info: InfoPembaruan | None = None
        self.hide()

    def _teks_unduh(self) -> str:
        return "Unduh pembaruan" if self.untuk_admin else "Unduh di latar belakang"

    @staticmethod
    def _ukuran(jumlah: int) -> str:
        return f"{jumlah / (1024 * 1024):.1f} MB"

    def tampilkan(self, info: InfoPembaruan | None) -> None:
        self.info = info
        if info is None:
            self.hide()
            return
        rincian = f" · {self._ukuran(info.ukuran_byte)} · terverifikasi" if self.untuk_admin else ""
        self.pesan.setText(
            f"Pembaruan Sistem Antrian CRO versi {info.versi} tersedia{rincian}."
        )
        self.progres.hide()
        self.tombol.setEnabled(True)
        self.tombol.setText(self._teks_unduh())
        self.tombol_tunda.setVisible(self._boleh_tunda)
        self.tombol_catatan.setVisible(bool(info.catatan))
        self.show()

    def tampilkan_catatan(self) -> None:
        """Catatan rilis sebagai teks biasa: isinya datang dari server lewat HTTP."""
        if self.info is None or not self.info.catatan:
            return
        kotak = QMessageBox(self)
        kotak.setWindowTitle(f"Apa yang baru di versi {self.info.versi}")
        kotak.setTextFormat(Qt.TextFormat.PlainText)
        kotak.setText(self.info.catatan)
        kotak.setIcon(QMessageBox.Icon.Information)
        kotak.exec()

    def sedang_mengunduh(self) -> None:
        if self.info is None:
            return
        self.progres.setValue(0)
        self.progres.show()
        self.pesan.setText(f"Mengunduh pembaruan versi {self.info.versi}…")
        self.tombol.setEnabled(False)
        self.tombol.setText("Mengunduh…")
        self.tombol_tunda.hide()

    def perbarui_kemajuan(self, jumlah: int, total: int) -> None:
        """Tampilkan byte nyata supaya petugas tahu unduhan tidak macet."""
        if self.info is None or total <= 0:
            return
        persen = min(100, round(jumlah * 100 / total))
        self.progres.setValue(persen)
        self.pesan.setText(
            f"Mengunduh versi {self.info.versi}: {self._ukuran(jumlah)} "
            f"dari {self._ukuran(total)}."
        )

    def siap_dipasang(self) -> None:
        if self.info is None:
            return
        self.progres.hide()
        self.pesan.setText(
            f"Pembaruan versi {self.info.versi} sudah diunduh dan siap dipasang."
        )
        self.tombol.setEnabled(True)
        self.tombol.setText(
            "Pasang sekarang" if self.untuk_admin else "Pasang setelah pelayanan"
        )
        self.tombol_tunda.hide()

    def pemasang_dibuka(self) -> None:
        if self.info is None:
            return
        self.progres.hide()
        self.pesan.setText(
            f"Pemasang versi {self.info.versi} sudah dibuka. Ikuti petunjuknya."
        )
        self.tombol.setText("Pemasang dibuka")
        self.tombol.setEnabled(False)
