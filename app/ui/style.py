"""
Tampilan visual aplikasi.

Prioritas urutannya: kecepatan operasional, lalu kemudahan pakai, baru
keindahan. Karena itu ukuran huruf dibuat besar, kontras dibuat tinggi,
dan tombol dibuat lapang — petugas loket bekerja cepat sambil melayani
orang di depannya, bukan sambil mengamati layar.
"""

from __future__ import annotations

# Warna dasar
PRIMARY = "#1565C0"
PRIMARY_DARK = "#0D47A1"
DANGER = "#C62828"
SUCCESS = "#2E7D32"
WARNING = "#EF6C00"
TEXT = "#1A1A1A"
TEXT_MUTED = "#5F6368"
BORDER = "#D0D5DD"
SURFACE = "#FFFFFF"
BACKGROUND = "#F4F6F8"

FONT_SIZE_BASE = 14
FONT_SIZE_LARGE = 18
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
    font-weight: 600;
}}

QLabel[muted="true"] {{
    color: {TEXT_MUTED};
}}

QLabel[error="true"] {{
    color: {DANGER};
    font-weight: 600;
}}

QLineEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 8px 10px;
    min-height: 22px;
}}

QLineEdit:focus, QComboBox:focus {{
    border: 2px solid {PRIMARY};
    padding: 7px 9px;
}}

QLineEdit[invalid="true"] {{
    border: 2px solid {DANGER};
    padding: 7px 9px;
}}

QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 9px 18px;
    min-height: 22px;
}}

QPushButton:hover {{
    background: #ECEFF1;
}}

QPushButton:disabled {{
    color: #9AA0A6;
    background: #F1F3F4;
}}

QPushButton[variant="primary"] {{
    background: {PRIMARY};
    border: 1px solid {PRIMARY};
    color: white;
    font-weight: 600;
}}

QPushButton[variant="primary"]:hover {{
    background: {PRIMARY_DARK};
}}

/* Wajib ada. Selector [variant="primary"] lebih spesifik daripada
   QPushButton:disabled, sehingga tanpa aturan ini tombol primer yang
   sedang nonaktif tetap tampak biru dan mengundang untuk diklik. */
QPushButton[variant="primary"]:disabled {{
    background: #F1F3F4;
    border: 1px solid {BORDER};
    color: #9AA0A6;
}}

QPushButton[variant="danger"] {{
    color: {DANGER};
    font-weight: 600;
}}

QPushButton[variant="danger"]:disabled {{
    color: #9AA0A6;
}}

QTableWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    gridline-color: #ECEFF1;
}}

QTableWidget::item {{
    padding: 6px;
}}

QTableWidget::item:selected {{
    background: #E3F2FD;
    color: {TEXT};
}}

QHeaderView::section {{
    background: #ECEFF1;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px;
    font-weight: 600;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {SURFACE};
    border-radius: 4px;
}}

QTabBar::tab {{
    padding: 9px 18px;
    border: 1px solid {BORDER};
    border-bottom: none;
    background: #ECEFF1;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background: {SURFACE};
    font-weight: 600;
}}

QListWidget#navigasi {{
    background: {PRIMARY_DARK};
    border: none;
    outline: none;
    color: #E8EAED;
}}

QListWidget#navigasi::item {{
    padding: 14px 18px;
    border: none;
}}

QListWidget#navigasi::item:selected {{
    background: {PRIMARY};
    color: white;
    font-weight: 600;
}}

QListWidget#navigasi::item:hover:!selected {{
    background: #1A56A0;
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
