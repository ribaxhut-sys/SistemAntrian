"""
Tampilan visual aplikasi.

Prioritas urutannya: kecepatan operasional, lalu kemudahan pakai, baru
keindahan. Karena itu ukuran huruf dibuat besar, kontras dibuat tinggi,
dan tombol dibuat lapang — petugas loket bekerja cepat sambil melayani
orang di depannya, bukan sambil mengamati layar.
"""

from __future__ import annotations

# Warna dasar
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
DANGER = "#DC2626"
SUCCESS = "#15803D"
WARNING = "#B45309"
TEXT = "#0F172A"
TEXT_MUTED = "#64748B"
BORDER = "#E2E8F0"
SURFACE = "#FFFFFF"
BACKGROUND = "#F1F5F9"

#: Warna dasar yang sama, dilarutkan menjadi latar.
#:
#: Dipakai untuk menandai KEADAAN pada panel yang lebar — kartu antrian
#: yang sedang ditangani, baris paling depan pada daftar tunggu. Latar
#: sepucat ini tetap menyisakan kontras teks yang aman, sedangkan warna
#: penuh pada bidang selebar itu justru membuat angkanya sulit dibaca.
PRIMARY_SOFT = "#EFF6FF"
DANGER_SOFT = "#FEF2F2"
SUCCESS_SOFT = "#F0FDF4"
WARNING_SOFT = "#FFFBEB"

#: Garis pembatas yang lebih tegas, untuk tepi yang memang perlu terlihat
#: (kepala tabel, tepi kartu aktif). BORDER biasa terlalu samar di situ.
BORDER_STRONG = "#CBD5E1"
#: Latar sekunder: baris tabel berselang, panel di dalam panel.
SURFACE_ALT = "#F8FAFC"

#: Sudut membulat. Satu nilai untuk kartu dan panel, satu untuk kontrol
#: kecil. Dua ukuran sudah cukup — lebih dari itu hanya membuat tampilan
#: tampak tidak disengaja.
RADIUS = 10
RADIUS_SM = 6

# Palet layar pengunjung. Dibaca dari seberang ruangan, jadi kontras
# lebih penting daripada keselarasan dengan UI petugas di meja.
DISPLAY_BG_ATAS = "#071422"
DISPLAY_BG_BAWAH = "#0B2A4A"
DISPLAY_JUDUL = "#F8FAFC"
#: Jam pada kepala papan. Sedikit lebih redup daripada judul supaya tetap
#: terbaca dari jauh tanpa bersaing dengan nomor antrian.
DISPLAY_JAM = "#CBD5E1"
DISPLAY_AKSEN = "#22D3EE"
DISPLAY_KARTU = "#FFFFFF"
DISPLAY_NOMOR = "#0F172A"
DISPLAY_KETERANGAN = "#0F766E"
DISPLAY_LOKET_BG = "#0F766E"
DISPLAY_LOKET_TEKS = "#FFFFFF"
DISPLAY_LAYANAN = "#475569"
DISPLAY_PANEL_BERIKUTNYA = "rgba(255, 255, 255, 22)"
DISPLAY_BERIKUTNYA_JUDUL = "#E2E8F0"
DISPLAY_BERIKUTNYA_KARTU = "#FFFFFF"
DISPLAY_BERIKUTNYA_TEKS = "#0F172A"
DISPLAY_BERIKUTNYA_KOSONG = "#94A3B8"
DISPLAY_KIOS_PANEL = "#F8FAFC"
DISPLAY_KIOS_TOMBOL = "#0F766E"
DISPLAY_KIOS_TOMBOL_HOVER = "#115E59"
DISPLAY_KIOS_TOMBOL_TEKS = "#FFFFFF"
DISPLAY_KIOS_TOMBOL_MATI = "#E2E8F0"
DISPLAY_KIOS_TOMBOL_MATI_TEKS = "#64748B"
DISPLAY_KARTU_KOSONG = "#E2E8F0"
DISPLAY_NOMOR_KOSONG = "#64748B"

FONT_SIZE_SMALL = 12
FONT_SIZE_BASE = 14
FONT_SIZE_LARGE = 18
FONT_SIZE_XL = 22
FONT_SIZE_HUGE = 32

STYLESHEET = f"""
QWidget {{
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: {FONT_SIZE_BASE}px;
    color: {TEXT};
}}

QMainWindow, QDialog {{
    background: {BACKGROUND};
}}

QLabel[heading="true"] {{
    font-size: {FONT_SIZE_LARGE}px;
    font-weight: 700;
}}

QLabel[muted="true"] {{
    color: {TEXT_MUTED};
}}

QLabel[error="true"] {{
    color: {DANGER};
    font-weight: 600;
}}

/* Judul kecil di atas sekelompok kontrol. Huruf kapital berspasi lebar
   membedakannya dari isi tanpa perlu garis pemisah tambahan. */
QLabel[kapsi="true"] {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 700;
    letter-spacing: 1px;
}}

QLineEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 8px 10px;
    min-height: 22px;
}}

QLineEdit:hover, QComboBox:hover {{
    border: 1px solid {PRIMARY};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {PRIMARY};
    padding: 7px 9px;
}}

/* Kotak teks panjang mengikuti gaya QLineEdit. Tanpa ini, isian alamat
   dan deskripsi pengaduan tampil sebagai kotak putih bergaris tipis bawaan
   Qt di tengah formulir yang seluruh isiannya sudah bergaya lain. */
QPlainTextEdit, QTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 6px 8px;
}}

QPlainTextEdit:hover, QTextEdit:hover {{
    border: 1px solid {PRIMARY};
}}

QPlainTextEdit:focus, QTextEdit:focus {{
    border: 2px solid {PRIMARY};
    padding: 5px 7px;
}}

QPlainTextEdit:disabled, QTextEdit:disabled {{
    background: {SURFACE_ALT};
    color: #A3AEC0;
}}

QTabWidget::pane {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    top: -1px;
}}

QTabBar::tab {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: {RADIUS_SM}px;
    border-top-right-radius: {RADIUS_SM}px;
    color: {TEXT_MUTED};
    padding: 7px 16px;
    margin-right: 3px;
    font-weight: 600;
}}

/* Tab terpilih dibedakan warna DAN garis atas tebal. Perbedaan warna saja
   terlalu tipis dilihat sekilas pada monitor kantor yang jarang dikalibrasi. */
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {PRIMARY_DARK};
    border-top: 2px solid {PRIMARY};
}}

QLineEdit[invalid="true"] {{
    border: 2px solid {DANGER};
    padding: 7px 9px;
}}

/* Isian wajib yang masih kosong, ditandai hanya ketika kewajibannya sudah
   berlaku — bukan sejak formulir dibuka. Peringatan yang menyala sebelum
   ada yang salah cepat berhenti dibaca. */
QLineEdit[wajib="true"] {{
    border: 2px solid {WARNING};
    background: {WARNING_SOFT};
    padding: 7px 9px;
}}

QPlainTextEdit[wajib="true"] {{
    border: 2px solid {WARNING};
    padding: 5px 7px;
}}

QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    outline: none;
}}

QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 9px 18px;
    min-height: 22px;
    font-weight: 600;
}}

QPushButton:hover {{
    background: {SURFACE_ALT};
    border: 1px solid {PRIMARY};
    color: {PRIMARY_DARK};
}}

QPushButton:pressed {{
    background: {PRIMARY_SOFT};
}}

QPushButton:disabled {{
    color: #A3AEC0;
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
}}

QPushButton[variant="primary"] {{
    background: {PRIMARY};
    border: 1px solid {PRIMARY};
    color: white;
    font-weight: 700;
}}

QPushButton[variant="primary"]:hover {{
    background: {PRIMARY_DARK};
    border: 1px solid {PRIMARY_DARK};
    color: white;
}}

/* Wajib ada. Selector [variant="primary"] lebih spesifik daripada
   QPushButton:disabled, sehingga tanpa aturan ini tombol primer yang
   sedang nonaktif tetap tampak biru dan mengundang untuk diklik. */
QPushButton[variant="primary"]:disabled {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    color: #A3AEC0;
}}

/* Penyelesaian pelayanan. Dibedakan dari primer karena keduanya sering
   menyala bersamaan, dan petugas perlu membedakannya tanpa membaca. */
QPushButton[variant="success"] {{
    background: {SUCCESS};
    border: 1px solid {SUCCESS};
    color: white;
    font-weight: 700;
}}

QPushButton[variant="success"]:hover {{
    background: #166534;
    border: 1px solid #166534;
    color: white;
}}

QPushButton[variant="success"]:disabled {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    color: #A3AEC0;
}}

/* Loket yang sedang istirahat. Keadaan yang harus terlihat dari kejauhan
   oleh supervisor yang lewat, bukan hanya oleh petugas yang duduk di
   depannya. */
QPushButton[variant="warning"] {{
    background: {WARNING_SOFT};
    border: 1px solid {WARNING};
    color: {WARNING};
    font-weight: 700;
}}

QPushButton[variant="warning"]:hover {{
    background: #FEF3C7;
    border: 1px solid {WARNING};
    color: {WARNING};
}}

QPushButton[variant="warning"]:disabled {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    color: #A3AEC0;
}}

QPushButton[variant="danger"] {{
    color: {DANGER};
    border: 1px solid #F2C2C2;
    font-weight: 600;
}}

QPushButton[variant="danger"]:hover {{
    background: {DANGER_SOFT};
    border: 1px solid {DANGER};
    color: {DANGER};
}}

QPushButton[variant="danger"]:disabled {{
    color: #A3AEC0;
    border: 1px solid {BORDER};
}}

QTableWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    gridline-color: transparent;
    outline: none;
}}

QTableWidget::item {{
    padding: 8px 4px;
    border-bottom: 1px solid {BORDER};
}}

QTableWidget::item:selected {{
    background: {PRIMARY_SOFT};
    color: {TEXT};
}}

QHeaderView::section {{
    background: {SURFACE_ALT};
    border: none;
    border-bottom: 1px solid {BORDER_STRONG};
    padding: 9px 6px;
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 700;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-height: 32px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {SURFACE};
    border-radius: {RADIUS_SM}px;
}}

QTabBar::tab {{
    padding: 9px 18px;
    border: 1px solid {BORDER};
    border-bottom: none;
    background: {SURFACE_ALT};
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background: {SURFACE};
    color: {PRIMARY_DARK};
    font-weight: 700;
}}

QListWidget#navigasi {{
    background: #0F1F3D;
    border: none;
    outline: none;
    color: #C7D2E5;
}}

QListWidget#navigasi::item {{
    padding: 14px 18px;
    border: none;
    border-left: 3px solid transparent;
}}

QListWidget#navigasi::item:selected {{
    background: {PRIMARY};
    border-left: 3px solid #93C5FD;
    color: white;
    font-weight: 700;
}}

QListWidget#navigasi::item:hover:!selected {{
    background: #1B2E52;
    color: white;
}}

QFrame#panelHeader {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}

QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}
"""


def badge_status(active: bool) -> str:
    """Label status yang mudah dibaca sekilas."""
    return "Aktif" if active else "Nonaktif"
