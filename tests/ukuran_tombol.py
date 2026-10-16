"""
Pengukur teks tombol yang terpotong, dipakai ulang oleh tes tata letak.

Tombol dengan `width() < sizeHint().width()` berarti layout memerasnya lebih
sempit daripada yang dibutuhkan teksnya, sehingga huruf terpotong di tepi.
Pengukuran memakai ukuran render sungguhan (widget tampil), bukan tebakan dari
panjang string, jadi ikut menangkap huruf, stylesheet, dan tema yang berlaku.

Pengecualian hanya untuk tombol tanpa teks (ikon) dan tombol yang namanya
terdaftar eksplisit di `PENGECUALIAN` beserta alasannya.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QListWidget,
    QPushButton,
    QTabWidget,
    QToolButton,
    QWidget,
)

# objectName -> alasan. Kosong: belum ada tombol bertulisan yang sengaja
# dipotong. Tambah di sini hanya dengan alasan tertulis.
PENGECUALIAN: dict[str, str] = {}

# Label yang saling bergantian pada tombol yang sama. Tiap kelompok diuji
# dengan SEMUA anggotanya, karena layout dibangun dengan salah satunya saja.
KELOMPOK_LABEL_DINAMIS: tuple[tuple[str, ...], ...] = (
    ("Unduh & Perbarui", "Sedang mengunduh…"),
    ("Tutup Pendaftaran", "Buka Pendaftaran"),
    ("Mulai Istirahat", "Akhiri Istirahat"),
    ("Ganti Loket", "Batal"),
    ("Tampilkan", "Sembunyikan"),
    ("Aktifkan", "Nonaktifkan"),
    ("Pasang & nyalakan", "Pasang ulang & nyalakan ulang"),
)


def tombol_bertulisan(akar: QWidget) -> list[QAbstractButton]:
    """Tombol (push/tool) yang tampak dan punya teks di bawah `akar`."""
    hasil: list[QAbstractButton] = []
    for kelas in (QPushButton, QToolButton):
        for tombol in akar.findChildren(kelas):
            if not tombol.text().strip() or not tombol.isVisible():
                continue
            if tombol.objectName() in PENGECUALIAN:
                continue
            hasil.append(tombol)
    if isinstance(akar, (QPushButton, QToolButton)) and akar.text().strip():
        if akar.isVisible() and akar.objectName() not in PENGECUALIAN:
            hasil.append(akar)
    return hasil


def _siram_layout() -> None:
    """
    Paksa layout memproses perubahan teks sebelum diukur.

    `setText` hanya memposting LayoutRequest; di mesin yang lebih lambat
    (CI) satu putaran `processEvents` bisa terjadi sebelum layout berjalan,
    sehingga tombol masih selebar label lama.
    """
    for _ in range(3):
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        QApplication.processEvents()


def _nama(tombol: QAbstractButton) -> str:
    induk = tombol.window().windowTitle() or type(tombol.window()).__name__
    return f"{induk} › {type(tombol.parent()).__name__} › {tombol.text()!r}"


def tombol_terpotong(akar: QWidget) -> list[str]:
    """Deskripsi tombol yang lebih sempit/pendek daripada kebutuhan teksnya."""
    _siram_layout()
    masalah: list[str] = []
    for tombol in tombol_bertulisan(akar):
        butuh = tombol.sizeHint()
        # Lebar dibandingkan dengan sizeHint (kebutuhan teks + padding).
        # Tinggi hanya dipastikan cukup untuk barisnya: layout yang menekan
        # tombol 1-2 px di bawah sizeHint tidak memotong huruf, sedangkan
        # tinggi di bawah satu baris huruf pasti memotongnya.
        baris = tombol.text().count(chr(10)) + 1
        tinggi_huruf = tombol.fontMetrics().height() * baris
        if tombol.width() < butuh.width() or tombol.height() < tinggi_huruf:
            masalah.append(
                f"{_nama(tombol)}: {tombol.width()}x{tombol.height()} "
                f"< butuh {butuh.width()}x{butuh.height()}"
            )
    return masalah


def varian_label(akar: QWidget) -> Iterable[tuple[QAbstractButton, str]]:
    """Pasangan (tombol, label lain) untuk tombol yang labelnya bergantian."""
    for tombol in tombol_bertulisan(akar):
        # "&&" adalah cara menampilkan satu "&" (lihat _teks_tombol di
        # layanan_anjungan_page); dibandingkan dalam bentuk tampilannya.
        tampil = tombol.text().replace("&&", "&")
        for kelompok in KELOMPOK_LABEL_DINAMIS:
            if tampil in kelompok:
                for label in kelompok:
                    yield tombol, (
                        label.replace("&", "&&") if "&&" in tombol.text() else label
                    )


def periksa_semua_label(akar: QWidget) -> list[str]:
    """
    Pasang tiap label alternatif pada tombolnya lalu ukur lagi.

    Label dikembalikan sesudahnya supaya keadaan halaman tidak berubah.
    """
    masalah: list[str] = []
    for tombol, label in list(varian_label(akar)):
        asli = tombol.text()
        tombol.setText(label)
        tombol.updateGeometry()
        masalah.extend(
            f"[label {label!r}] {baris}"
            for baris in tombol_terpotong(tombol.window())
            if label in baris
        )
        tombol.setText(asli)
        tombol.updateGeometry()
    QApplication.processEvents()
    return masalah


def jelajahi(
    akar: QWidget,
    periksa: Callable[[QWidget], None],
    *,
    _sudah: set[int] | None = None,
) -> None:
    """
    Panggil `periksa(akar)` pada setiap keadaan tab/rail yang bisa dicapai.

    Hanya satu tab/rail yang tampak sekali waktu, jadi satu pemeriksaan di
    halaman awal melewatkan semua tombol di tab lain. Pemilihan awal
    dikembalikan sesudahnya.
    """
    sudah = _sudah if _sudah is not None else set()
    periksa(akar)
    kontainer = [
        w
        for w in akar.findChildren(QWidget)
        if isinstance(w, (QTabWidget, QListWidget))
        and w.isVisible()
        and id(w) not in sudah
        and (isinstance(w, QTabWidget) or w.objectName() == "railPengaturan")
    ]
    for penampung in kontainer:
        sudah.add(id(penampung))
        if isinstance(penampung, QTabWidget):
            awal = penampung.currentIndex()
            for indeks in range(penampung.count()):
                if not penampung.isTabEnabled(indeks):
                    continue
                penampung.setCurrentIndex(indeks)
                QApplication.processEvents()
                jelajahi(akar, periksa, _sudah=sudah)
            penampung.setCurrentIndex(awal)
        else:
            awal = penampung.currentRow()
            for baris in range(penampung.count()):
                penampung.setCurrentRow(baris)
                QApplication.processEvents()
                jelajahi(akar, periksa, _sudah=sudah)
            penampung.setCurrentRow(awal)
        QApplication.processEvents()
