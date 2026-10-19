"""
Tema tampilan aplikasi petugas.

Pilihan tema hidup di komputer ini saja (`tampilan.json` di folder
database, sejajar dengan `peran.json`): tiap petugas bebas memilih yang
nyaman di matanya, dan tidak ada yang berubah di komputer lain.

Cara kerjanya sengaja tidak menyentuh puluhan modul yang menulis
`setStyleSheet` dengan warna di dalamnya. Semua warna aplikasi berupa
kode hex, jadi tema diterapkan dengan MENGUBAH warna pada stylesheet yang
sudah jadi:

- tema berwarna menggeser rona keluarga indigo (warna utama aplikasi) ke
  rona tema, dengan terang dan kejenuhan tetap;
- tema gelap membalik terang warna netral menurut fungsinya — teks gelap
  menjadi terang, latar terang menjadi gelap — sedangkan teks putih pada
  tombol dan kepala yang gelap tetap putih.

Stylesheet asli tiap widget disimpan, sehingga tema dapat diganti
berulang-ulang tanpa menumpuk perubahan.
"""

from __future__ import annotations

import colorsys
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.logger import get_logger

logger = get_logger("ui.tema")

NAMA_BERKAS = "tampilan.json"
TEMA_BAWAAN = "indigo"

# Keluarga indigo: rentang rona (0..1) dan kejenuhan minimum yang dianggap
# "warna utama aplikasi". Abu-abu kebiruan (slate) jatuh di bawah rentang.
_RONA_MIN = 0.625
_RONA_MAX = 0.735
_JENUH_MIN = 0.35


@dataclass(frozen=True)
class Tema:
    kunci: str
    nama: str
    keterangan: str
    #: Warna contoh untuk kartu pilihan: (latar, kartu, aksen, teks).
    contoh: tuple[str, str, str, str]
    #: Rona baru untuk keluarga indigo (0..1), atau None bila tetap.
    rona: float | None = None
    gelap: bool = False
    #: Pergeseran rona netral ke hangat (0 = tidak).
    hangat: float = 0.0
    #: Kontras tinggi: teks dan tepi dipertegas.
    kontras: bool = False


TEMA: dict[str, Tema] = {
    t.kunci: t
    for t in (
        Tema(
            "indigo",
            "Indigo",
            "Tampilan bawaan: terang dengan aksen indigo.",
            ("#F4F7FB", "#FFFFFF", "#4F46E5", "#172033"),
        ),
        Tema(
            "samudra",
            "Samudra",
            "Terang dengan aksen teal yang segar dan tenang.",
            ("#F0F7F7", "#FFFFFF", "#0F766E", "#10262B"),
            rona=0.49,
        ),
        Tema(
            "zamrud",
            "Zamrud",
            "Hijau lembut; nyaman dipandang berjam-jam.",
            ("#F1F7F3", "#FFFFFF", "#15803D", "#12261A"),
            rona=0.40,
        ),
        Tema(
            "pasir",
            "Pasir",
            "Netral hangat berpendar jingga, rendah silau.",
            ("#FAF6F0", "#FFFFFF", "#C2410C", "#2A2118"),
            rona=0.06,
            hangat=0.085,
        ),
        Tema(
            "sakura",
            "Sakura",
            "Nuansa pink lembut yang ceria namun tetap bersih.",
            ("#FDF2F8", "#FFFFFF", "#DB2777", "#3B1030"),
            rona=0.915,
        ),
        Tema(
            "merdeka",
            "Merdeka",
            "Merah putih: aksen merah tegas di atas bidang putih bersih.",
            ("#FFF5F5", "#FFFFFF", "#CE1126", "#1F1416"),
            rona=0.985,
        ),
        Tema(
            "malam",
            "Malam",
            "Gelap modern: hemat mata di ruang redup.",
            ("#0F172A", "#1E293B", "#818CF8", "#E2E8F0"),
            gelap=True,
        ),
        Tema(
            "kontras",
            "Kontras Tinggi",
            "Teks dan tepi dipertegas untuk keterbacaan maksimal.",
            ("#FFFFFF", "#FFFFFF", "#1D4ED8", "#000000"),
            kontras=True,
        ),
    )
}

_HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
# Hanya properti warna; selektor seperti `QPushButton:hover` tidak cocok.
_DEKLARASI = re.compile(
    r"(?P<prop>(?<![\w-])(?:selection-background-color|selection-color|"
    r"alternate-background-color|background-color|background|gridline-color|"
    r"border-top|border-bottom|border-left|border-right|border-color|border|"
    r"outline|color))\s*:\s*(?P<nilai>[^;}\"]+)"
)
_WARNA_TEKS = {"color", "selection-color"}
_NAMA_WARNA = re.compile(r"(?<![\w#-])(?:white|black)(?![\w-])", re.IGNORECASE)
# Teks dalam HTML kaya: `color:#xxxxxx` / `color: #xxxxxx`.
_HTML_WARNA = re.compile(r"(?<![\w-])(color\s*:\s*)(#[0-9a-fA-F]{6})\b")


def _ke_hls(hexa: str) -> tuple[float, float, float]:
    hexa = hexa.lstrip("#")
    r, g, b = (int(hexa[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _dari_hls(h: float, l: float, s: float) -> str:  # noqa: E741
    r, g, b = colorsys.hls_to_rgb(h % 1.0, min(1.0, max(0.0, l)), min(1.0, max(0.0, s)))
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def _aksen(h: float, s: float) -> bool:
    return _RONA_MIN <= h <= _RONA_MAX and s >= _JENUH_MIN


def ubah_warna(hexa: str, tema: Tema, *, teks: bool) -> str:
    """Satu warna `#RRGGBB` menurut tema, dengan `teks` bila untuk huruf."""
    if tema.kunci == TEMA_BAWAAN:
        return hexa.upper()
    h, l, s = _ke_hls(hexa)  # noqa: E741

    if tema.gelap:
        if teks:
            # Teks gelap menjadi terang; teks yang sudah terang (putih pada
            # tombol) dibiarkan. Aksen tua pada teks (judul indigo) diangkat.
            if l < 0.62:
                l = 0.97 - l * 0.6  # noqa: E741
                if _aksen(h, s):
                    s = min(s, 0.85)
            return _dari_hls(h, l, s)
        # Latar dan tepi: yang terang digelapkan; yang sudah gelap
        # (kepala berwarna, tombol utama) tetap.
        if l > 0.5:
            l = 0.10 + (1.0 - l) * 0.55  # noqa: E741
            s = s * 0.8
        return _dari_hls(h, l, s)

    if tema.rona is not None and _aksen(h, s):
        h = tema.rona
    if tema.hangat and not _aksen(h, s) and s < _JENUH_MIN and 0.55 <= h <= 0.70:
        h = tema.hangat
        s = max(s, 0.25) if l > 0.6 else s
    if tema.kontras:
        if teks and l < 0.5:
            l = l * 0.35  # noqa: E741
        if not teks and l < 0.5:
            l = l * 0.6  # noqa: E741
        # Tepi dan garis abu-abu pucat menjadi tegas.
    return _dari_hls(h, l, s)


# ---------------------------------------------------------------------
# Kontras
# ---------------------------------------------------------------------

#: Rasio kontras minimum teks terhadap latarnya dalam satu aturan.
KONTRAS_MIN = 4.5
#: Teks pada kontrol nonaktif: boleh lebih lembut, tetapi harus tetap terbaca.
KONTRAS_MIN_NONAKTIF = 3.0
KONTRAS_MIN_TINGGI = 7.0

_ATURAN = re.compile(r"(?P<sel>[^{}]*)\{(?P<isi>[^{}]*)\}")
_BG = re.compile(
    r"(?<![\w-])background(?:-color)?\s*:\s*[^;}\"]*?(#[0-9a-fA-F]{6})\b"
)
_TEKS = re.compile(r"(?<![\w-])color\s*:\s*(#[0-9a-fA-F]{6})\b")


def _luminans(hexa: str) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    h = hexa.lstrip("#")
    r, g, b = (lin(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def rasio_kontras(a: str, b: str) -> float:
    """Rasio kontras WCAG antara dua warna `#RRGGBB` (1..21)."""
    la, lb = _luminans(a), _luminans(b)
    terang, gelap = max(la, lb), min(la, lb)
    return (terang + 0.05) / (gelap + 0.05)


def pastikan_kontras(teks: str, latar: str, minimum: float) -> str:
    """
    `teks` bila sudah cukup kontras terhadap `latar`; bila tidak, warna
    seronanya yang diterangkan atau digelapkan secukupnya.
    """
    if rasio_kontras(teks, latar) >= minimum:
        return teks.upper()
    h, l, s = _ke_hls(teks)  # noqa: E741
    arah = 1 if _luminans(latar) < 0.4 else -1
    for langkah in range(1, 21):
        calon = _dari_hls(h, l + arah * langkah * 0.05, s)
        if rasio_kontras(calon, latar) >= minimum:
            return calon
    return "#FFFFFF" if arah > 0 else "#000000"


def pastikan_kontras_latar(teks: str, latar: str, minimum: float) -> str:
    """
    Untuk teks putih pada latar sedang: gelapkan LATAR sampai cukup kontras,
    daripada mengganti teks putih tombol menjadi hitam.
    """
    if rasio_kontras(teks, latar) >= minimum:
        return latar.upper()
    h, l, s = _ke_hls(latar)  # noqa: E741
    for langkah in range(1, 21):
        calon = _dari_hls(h, l - langkah * 0.03, s)
        if rasio_kontras(teks, calon) >= minimum:
            return calon
    return latar.upper()


def _jaga_kontras(qss: str, minimum: float) -> str:
    """Perbaiki teks yang kurang kontras terhadap latar pada aturan yang sama."""

    def per_isi(isi: str, selektor: str) -> str:
        bg = _BG.search(isi)
        teks = _TEKS.search(isi)
        if bg is None or teks is None:
            return isi
        batas = KONTRAS_MIN_NONAKTIF if ":disabled" in selektor else minimum
        latar, huruf = bg.group(1), teks.group(1)
        if rasio_kontras(huruf, latar) >= batas:
            return isi
        if _luminans(huruf) > 0.8 and _luminans(latar) < 0.6:
            # Teks terang pada tombol/kepala berwarna: gelapkan latarnya.
            baru = pastikan_kontras_latar(huruf, latar, batas)
            return isi.replace(latar, baru)
        return isi.replace(huruf, pastikan_kontras(huruf, latar, batas))

    if "{" not in qss:
        return per_isi(qss, "")
    return _ATURAN.sub(
        lambda m: f"{m.group('sel')}{{{per_isi(m.group('isi'), m.group('sel'))}}}",
        qss,
    )


def ubah_qss(qss: str, tema: Tema) -> str:
    """Terapkan tema pada stylesheet (atau potongannya)."""
    if not qss or "#" not in qss:
        return qss
    minimum = KONTRAS_MIN_TINGGI if tema.kontras else KONTRAS_MIN
    if tema.kunci == TEMA_BAWAAN:
        return _jaga_kontras(qss, minimum)
    return _jaga_kontras(_ubah_warna_qss(qss, tema), minimum)


def _ubah_warna_qss(qss: str, tema: Tema) -> str:

    def per_deklarasi(m: re.Match[str]) -> str:
        prop = m.group("prop")
        teks = prop in _WARNA_TEKS
        # Nama warna dasar ditulis langsung di beberapa kartu; tanpa ini
        # latar `white` tetap putih pada tema gelap.
        mentah = _NAMA_WARNA.sub(
            lambda n: "#FFFFFF" if n.group(0).lower() == "white" else "#000000",
            m.group("nilai"),
        )
        nilai = _HEX.sub(
            lambda h: ubah_warna("#" + h.group(1), tema, teks=teks),
            mentah,
        )
        # Tepi pada tema kontras tinggi lebih tebal warnanya, bukan ukurannya.
        return f"{prop}: {nilai}"

    return _DEKLARASI.sub(per_deklarasi, qss)


def warna_tema(hexa: str, *, teks: bool = False) -> str:
    """
    Warna `#RRGGBB` menurut tema aktif, untuk kode yang menggambar sendiri
    dengan QPainter dan karena itu tidak lewat stylesheet.
    """
    return ubah_warna(hexa, _aktif, teks=teks)


def ubah_html(html: str, tema: Tema) -> str:
    """Warna teks di dalam HTML kaya (label papan, pil, dan sejenisnya)."""
    if tema.kunci == TEMA_BAWAAN or "color" not in html or "#" not in html:
        return html
    return _HTML_WARNA.sub(
        lambda m: m.group(1) + ubah_warna(m.group(2), tema, teks=True), html
    )


# ---------------------------------------------------------------------
# Penyimpanan per komputer
# ---------------------------------------------------------------------


def path_berkas_tema(db_path: Path | None = None) -> Path:
    override = os.environ.get("ANTRIAN_TAMPILAN_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if db_path is None:
        from app.core.config import get_config

        db_path = get_config().db_path
    return Path(db_path).expanduser().resolve().parent / NAMA_BERKAS


def baca_tema(path: Path | None = None) -> str:
    """Kunci tema tersimpan. Tidak pernah melempar galat."""
    try:
        data = json.loads((path or path_berkas_tema()).read_text(encoding="utf-8"))
        kunci = data.get("tema") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return TEMA_BAWAAN
    return kunci if kunci in TEMA else TEMA_BAWAAN


def simpan_tema(kunci: str, path: Path | None = None) -> bool:
    if kunci not in TEMA:
        raise ValueError(f"Tema tidak dikenal: {kunci}")
    try:
        target = path or path_berkas_tema()
        # Tulis ke berkas sementara lalu ganti: berkas tidak pernah terpotong.
        sementara = target.with_name(target.name + ".tmp")
        sementara.write_text(
            json.dumps({"tema": kunci}, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(sementara, target)
    except OSError:
        logger.warning("Tema tidak dapat disimpan", exc_info=True)
        return False
    return True


# ---------------------------------------------------------------------
# Penerapan langsung
# ---------------------------------------------------------------------

_aktif: Tema = TEMA[TEMA_BAWAAN]
_terpasang = False
_palet_asli = None
_ASLI_QSS = "_tema_qss_asli"
_ASLI_HTML = "_tema_html_asli"
#: Peran data pada sel tabel untuk menyimpan warna asli (sebelum tema).
_PERAN_FG = 0x0100 + 901
_PERAN_BG = 0x0100 + 902


def tema_aktif() -> Tema:
    return _aktif


def _pasang_penyaring() -> None:
    """Bungkus `setStyleSheet` dan `QLabel.setText` sekali saja."""
    global _terpasang
    if _terpasang:
        return
    from PySide6.QtWidgets import QLabel, QWidget

    qss_asli = QWidget.setStyleSheet
    teks_asli = QLabel.setText

    def set_style(self, qss):  # type: ignore[no-untyped-def]
        try:
            self.setProperty(_ASLI_QSS, qss)
        except Exception:  # noqa: BLE001 - widget yang sedang dihancurkan
            pass
        qss_asli(self, ubah_qss(qss, _aktif))

    def set_text(self, teks):  # type: ignore[no-untyped-def]
        if isinstance(teks, str) and "color" in teks:
            try:
                self.setProperty(_ASLI_HTML, teks)
            except Exception:  # noqa: BLE001
                pass
            teks = ubah_html(teks, _aktif)
        elif self.property(_ASLI_HTML) is not None:
            self.setProperty(_ASLI_HTML, None)
        teks_asli(self, teks)

    from PySide6.QtGui import QBrush, QColor
    from PySide6.QtWidgets import QTableWidgetItem

    fg_asli = QTableWidgetItem.setForeground
    bg_asli = QTableWidgetItem.setBackground

    def _warna(nilai, teks: bool):  # type: ignore[no-untyped-def]
        if _aktif.kunci == TEMA_BAWAAN:
            return nilai
        if isinstance(nilai, QBrush):
            warna = nilai.color()
        elif isinstance(nilai, QColor):
            warna = nilai
        else:
            return nilai
        if not warna.isValid():
            return nilai
        baru = QColor(ubah_warna(warna.name(), _aktif, teks=teks))
        baru.setAlpha(warna.alpha())
        return QBrush(baru) if isinstance(nilai, QBrush) else baru

    def _simpan_asli(item, peran: int, nilai) -> None:  # type: ignore[no-untyped-def]
        warna = nilai.color() if isinstance(nilai, QBrush) else nilai
        if isinstance(warna, QColor) and warna.isValid():
            item.setData(peran, warna.name(QColor.NameFormat.HexArgb))

    def set_fg(self, nilai):  # type: ignore[no-untyped-def]
        _simpan_asli(self, _PERAN_FG, nilai)
        fg_asli(self, _warna(nilai, True))

    def set_bg(self, nilai):  # type: ignore[no-untyped-def]
        _simpan_asli(self, _PERAN_BG, nilai)
        bg_asli(self, _warna(nilai, False))

    QWidget.setStyleSheet = set_style  # type: ignore[method-assign]
    QLabel.setText = set_text  # type: ignore[method-assign]
    QTableWidgetItem.setForeground = set_fg  # type: ignore[method-assign]
    QTableWidgetItem.setBackground = set_bg  # type: ignore[method-assign]
    _terpasang = True


def _terapkan_palet(app, tema: Tema) -> None:
    """Palet Qt untuk bagian yang tidak digambar lewat stylesheet."""
    global _palet_asli
    from PySide6.QtGui import QColor, QPalette

    if _palet_asli is None:
        _palet_asli = QPalette(app.palette())
    if not tema.gelap:
        app.setPalette(_palet_asli)
        return
    palet = QPalette(_palet_asli)
    peta = {
        QPalette.ColorRole.Window: "#0F172A",
        QPalette.ColorRole.WindowText: "#E2E8F0",
        QPalette.ColorRole.Base: "#1E293B",
        QPalette.ColorRole.AlternateBase: "#172033",
        QPalette.ColorRole.Text: "#E2E8F0",
        QPalette.ColorRole.Button: "#1E293B",
        QPalette.ColorRole.ButtonText: "#E2E8F0",
        QPalette.ColorRole.ToolTipBase: "#1E293B",
        QPalette.ColorRole.ToolTipText: "#E2E8F0",
        QPalette.ColorRole.PlaceholderText: "#94A3B8",
        QPalette.ColorRole.Highlight: "#4F46E5",
        QPalette.ColorRole.HighlightedText: "#FFFFFF",
    }
    for peran, warna in peta.items():
        palet.setColor(peran, QColor(warna))
    app.setPalette(palet)


def terapkan_tema(app, kunci: str) -> Tema:
    """
    Terapkan tema pada seluruh aplikasi, juga pada widget yang sudah ada.
    """
    global _aktif
    from app.ui.style import STYLESHEET

    _pasang_penyaring()
    _aktif = TEMA.get(kunci, TEMA[TEMA_BAWAAN])
    _terapkan_palet(app, _aktif)
    app.setStyleSheet(ubah_qss(STYLESHEET, _aktif))

    from PySide6.QtGui import QBrush, QColor
    from PySide6.QtWidgets import QLabel, QTableWidget

    for widget in app.allWidgets():
        if isinstance(widget, QTableWidget):
            for baris in range(widget.rowCount()):
                for kolom in range(widget.columnCount()):
                    sel = widget.item(baris, kolom)
                    if sel is None:
                        continue
                    for peran, atur in (
                        (_PERAN_FG, sel.setForeground),
                        (_PERAN_BG, sel.setBackground),
                    ):
                        nilai = sel.data(peran)
                        if isinstance(nilai, str):
                            atur(QBrush(QColor(nilai)))
        asli = widget.property(_ASLI_QSS)
        if isinstance(asli, str) and asli:
            widget.setStyleSheet(asli)
        if isinstance(widget, QLabel):
            html = widget.property(_ASLI_HTML)
            if isinstance(html, str):
                widget.setText(html)
    return _aktif
