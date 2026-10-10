"""
Alat bantu UI bersama.

Yang terpenting di sini adalah penanganan error: petugas tidak boleh
pernah melihat traceback, nama exception Python, atau pesan SQLite. Yang
tampil hanyalah kalimat yang bisa ditindaklanjuti; detail teknisnya masuk
ke file log.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QWidget

from app.core.errors import AppError
from app.core.logger import get_logger

logger = get_logger("ui")

T = TypeVar("T")

_PEKERJA_TERTINGGAL: set["PekerjaLatar"] = set()

PESAN_TAK_TERDUGA = (
    "Terjadi kesalahan yang tidak terduga. Silakan coba kembali.\n"
    "Bila terus berulang, hubungi administrator."
)


class PekerjaLatar(QThread):
    """Jalankan satu fungsi lambat tanpa menahan event loop Qt."""

    berhasil = Signal(object)
    gagal = Signal(object)

    def __init__(self, aksi: Callable[[], object], parent=None) -> None:
        super().__init__(parent)
        self.aksi = aksi

    def run(self) -> None:
        try:
            hasil = self.aksi()
        except Exception as exc:  # noqa: BLE001 - exception dikirim ke thread UI
            logger.exception("Pekerjaan latar UI gagal")
            self.gagal.emit(exc)
            return
        self.berhasil.emit(hasil)


def lepaskan_pekerja(pekerja: PekerjaLatar) -> None:
    """Biarkan worker yang macet selesai tanpa bergantung pada halaman UI."""
    if not pekerja.isRunning():
        return

    # Halaman induk sedang ditutup. Putuskan semua callback agar hasil yang
    # datang terlambat tidak mengakses widget yang sudah dihancurkan.
    for sinyal in (pekerja.berhasil, pekerja.gagal, pekerja.finished):
        try:
            sinyal.disconnect()
        except (RuntimeError, TypeError):
            pass

    pekerja.setParent(None)
    _PEKERJA_TERTINGGAL.add(pekerja)

    def selesai() -> None:
        _PEKERJA_TERTINGGAL.discard(pekerja)
        pekerja.deleteLater()

    pekerja.finished.connect(selesai)
    if pekerja.isFinished():
        selesai()


def pesan_untuk_user(exc: Exception) -> str:
    """
    Ubah exception menjadi kalimat yang layak dibaca petugas.

    Hanya AppError yang pesannya memang disiapkan untuk dibaca manusia.
    Selain itu dianggap kegagalan tak terduga dan pesannya disamarkan,
    karena isinya bisa saja memuat nama tabel atau potongan SQL.
    """
    if isinstance(exc, AppError):
        return exc.user_message
    return PESAN_TAK_TERDUGA


def tampilkan_error(parent: QWidget | None, exc: Exception, judul: str = "Gagal") -> None:
    """Tampilkan kegagalan sebagai kotak pesan, dan catat detailnya ke log."""
    if isinstance(exc, AppError):
        logger.warning("%s: %s", type(exc).__name__, exc.user_message)
    else:
        logger.exception("Kesalahan tak terduga pada UI")

    kotak = QMessageBox(parent)
    kotak.setIcon(QMessageBox.Icon.Warning)
    kotak.setWindowTitle(judul)
    kotak.setText(pesan_untuk_user(exc))
    kotak.setStandardButtons(QMessageBox.StandardButton.Ok)
    kotak.exec()


def tampilkan_info(parent: QWidget | None, pesan: str, judul: str = "Berhasil") -> None:
    kotak = QMessageBox(parent)
    kotak.setIcon(QMessageBox.Icon.Information)
    kotak.setWindowTitle(judul)
    kotak.setText(pesan)
    kotak.setStandardButtons(QMessageBox.StandardButton.Ok)
    kotak.exec()


def tampilkan_peringatan(
    parent: QWidget | None, pesan: str, judul: str = "Perhatian"
) -> None:
    """
    Kabar yang perlu dibaca, tetapi bukan kegagalan.

    Dibedakan dari `tampilkan_info` karena ikonnya: tindakan yang berhasil
    disimpan namun meninggalkan keadaan yang keliru — loket yang baru
    dibatasi sehingga satu jenis layanan tidak dilayani siapa pun — tidak
    boleh tampil dengan ikon yang sama seperti "berhasil".
    """
    kotak = QMessageBox(parent)
    kotak.setIcon(QMessageBox.Icon.Warning)
    kotak.setWindowTitle(judul)
    kotak.setText(pesan)
    kotak.setStandardButtons(QMessageBox.StandardButton.Ok)
    kotak.exec()


def konfirmasi(parent: QWidget | None, pertanyaan: str, judul: str = "Konfirmasi") -> bool:
    """
    Minta persetujuan untuk tindakan yang tidak sepele.

    Bawaannya "Tidak", supaya menekan Enter karena refleks tidak langsung
    menjalankan tindakan.
    """
    kotak = QMessageBox(parent)
    kotak.setIcon(QMessageBox.Icon.Question)
    kotak.setWindowTitle(judul)
    kotak.setText(pertanyaan)
    kotak.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    kotak.setDefaultButton(QMessageBox.StandardButton.No)
    kotak.button(QMessageBox.StandardButton.Yes).setText("Ya")
    kotak.button(QMessageBox.StandardButton.No).setText("Tidak")
    return kotak.exec() == QMessageBox.StandardButton.Yes


def jalankan_aman(
    parent: QWidget | None, aksi: Callable[[], T], judul: str = "Gagal"
) -> tuple[bool, T | None]:
    """
    Jalankan pemanggilan service dan tangani kegagalannya.

    Mengembalikan (berhasil, hasil). Dipakai agar setiap handler tombol
    tidak perlu menulis blok try/except yang sama berulang kali.
    """
    try:
        return True, aksi()
    except Exception as exc:  # noqa: BLE001 - sengaja menangkap semuanya di batas UI
        tampilkan_error(parent, exc, judul)
        return False, None


def tombol(teks: str, *, variant: str = "", default: bool = False) -> QPushButton:
    """Tombol dengan gaya sesuai perannya."""
    btn = QPushButton(teks)
    if variant:
        btn.setProperty("variant", variant)
    btn.setDefault(default)
    btn.setAutoDefault(default)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def setel_variant(btn: QPushButton, variant: str = "") -> None:
    """
    Ganti gaya sebuah tombol setelah tombol itu terlanjur tampil.

    Mengubah property saja TIDAK cukup: Qt sudah menghitung gaya tombol
    ketika pertama kali digambar dan tidak menghitungnya ulang dengan
    sendirinya. Tanpa unpolish/polish, tombol Istirahat berganti tulisan
    tetapi warnanya tetap seperti semula.
    """
    btn.setProperty("variant", variant)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


def judul(teks: str) -> QLabel:
    label = QLabel(teks)
    label.setProperty("heading", "true")
    return label


def keterangan(teks: str) -> QLabel:
    label = QLabel(teks)
    label.setProperty("muted", "true")
    label.setWordWrap(True)
    return label


def label_error() -> QLabel:
    """
    Label pesan kesalahan yang tampil di dalam form.

    Untuk kesalahan pengisian form, pesan sebaris jauh lebih cepat
    ditindaklanjuti daripada kotak dialog yang harus ditutup dulu.
    """
    label = QLabel("")
    label.setProperty("error", "true")
    label.setWordWrap(True)
    label.setVisible(False)
    return label
