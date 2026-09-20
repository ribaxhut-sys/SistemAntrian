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

#: Warna penanda layar pada dialog pilihan mode.
#:
#: Lima pilihan di layar pembuka bukan lima tombol yang setara: masing
#: masing adalah mesin yang berbeda. Warna dipakai supaya orang yang sudah
#: pernah membukanya mengenali barisnya tanpa membaca ulang penjelasannya,
#: dan supaya warna anjungan sama dengan tosca yang nanti ia lihat di layar
#: anjungan itu sendiri.
MODE_ANTRIAN = "#0284C7"
MODE_ANTRIAN_SOFT = "#E0F2FE"
MODE_ANJUNGAN = "#0D9488"
MODE_ANJUNGAN_SOFT = "#CCFBF1"
MODE_TOTEM = "#C2410C"
MODE_TOTEM_SOFT = "#FFEDD5"
MODE_ADMIN = "#7C3AED"
MODE_ADMIN_SOFT = "#EDE9FE"
MODE_PETUGAS = "#4F46E5"

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
#: Kartu layanan yang sedang ditekan. Wajib berbeda dari warna dasarnya:
#: layar sentuh resistif tidak terasa ditekan, dan kartu yang tidak berubah
#: apa pun membuat pengunjung menekannya dua kali.
DISPLAY_KIOS_TOMBOL_TEKAN = "#134E4A"
DISPLAY_KIOS_TOMBOL_TEKS = "#FFFFFF"
DISPLAY_KIOS_TOMBOL_MATI = "#E2E8F0"
DISPLAY_KIOS_TOMBOL_MATI_TEKS = "#64748B"
#: Kartu KELOMPOK di anjungan — Konsultasi, PBJT. Warnanya sengaja
#: berbeda dari kartu layanan biasa: menyentuhnya tidak menerbitkan nomor
#: apa pun, hanya membuka daftar isinya. Perbedaan itu tidak dapat
#: disampaikan lewat tulisan pada layar yang dibaca sambil berdiri.
DISPLAY_KIOS_KELOMPOK = "#155E75"
DISPLAY_KIOS_KELOMPOK_HOVER = "#164E63"
DISPLAY_KIOS_KELOMPOK_TEKAN = "#083344"
#: Kartu KEMBALI. Abu, bukan berwarna: ia bukan salah satu pilihan
#: layanan, dan tidak boleh ikut memperebutkan perhatian dengan kartu
#: yang benar-benar menerbitkan nomor. Tulisannya merah supaya kentara
#: sebagai jalan pulang, bukan sebagai jenis layanan.
DISPLAY_KIOS_KEMBALI = "#CBD5E1"
DISPLAY_KIOS_KEMBALI_HOVER = "#B6C2D2"
DISPLAY_KIOS_KEMBALI_TEKAN = "#94A3B8"
DISPLAY_KIOS_KEMBALI_TEKS = "#DC2626"
DISPLAY_KARTU_KOSONG = "#E2E8F0"
DISPLAY_NOMOR_KOSONG = "#64748B"

#: ----- Anjungan ambil nomor ----------------------------------------
#:
#: Panel bawah anjungan. Latarnya sengaja tetap terang untuk semua tema
#: papan: temanya boleh gelap, boleh terang, dan yang harus selalu terbaca
#: dari jarak satu lengan sambil berdiri adalah panel inilah.
KIOS_PANEL_ATAS = "#FFFFFF"
KIOS_PANEL_BAWAH = "#E9EEF5"
KIOS_JUDUL = "#0F172A"
KIOS_SUKSES = "#059669"
KIOS_SUKSES_TEKAN = "#047857"

#: Pil petunjuk di bawah judul panel: latar, tulisan.
#:
#: Satu baris yang sama menjawab lima keadaan yang sangat berbeda —
#: mengajak, menyuruh menunggu, mengabarkan nomor terbit, melaporkan
#: tiket yang gagal dicetak, dan melaporkan kegagalan. Warna pil membuat
#: keadaannya terbaca sebelum kalimatnya sempat dibaca; pengunjung yang
#: menunggu sepuluh detik tidak menyangka mesinnya rusak bila baris itu
#: terlihat sedang menghitung, bukan diam.
#:
#: Dua keadaan hasil cetak sengaja PEKAT, bukan pastel seperti yang lain.
#: Keduanya muncul tepat ketika nomor sudah terbit dan pengunjung hanya
#: memandang layar sekejap sebelum berbalik, jadi keduanya harus terbaca
#: sebagai warna, bukan sebagai tulisan yang perlu dieja lebih dulu.
#:
#: "gagal" kuning, bukan merah: nomornya tetap sah — `_cetak()` tidak
#: pernah menggagalkan pengambilan nomor — dan merah membuat pengunjung
#: mengira nomornya batal lalu mengambil satu lagi.
KIOS_PIL = {
    "ajak": ("#E2E8F0", "#475569"),
    "konfirmasi": ("#E0E7FF", "#3730A3"),
    "tunggu": ("#FEF3C7", "#92400E"),
    "hasil": ("#10B981", "#04231A"),
    "gagal": ("#F59E0B", "#1F1300"),
    "salah": ("#FEE2E2", "#991B1B"),
}

#: Kotak huruf di dalam kartu layanan, dan pasangannya saat kartu mati.
#:
#: Sekadar putih tembus pandang di atas warna kartu, bukan warna
#: tersendiri: yang dibutuhkan kotak ini hanyalah memberi huruf layanan
#: tempat yang tetap, bukan menambah satu warna lagi ke panel.
KIOS_KOTAK_HURUF = "rgba(255, 255, 255, 42)"
KIOS_KOTAK_HURUF_MATI = "rgba(15, 23, 42, 20)"


FONT_SIZE_SMALL = 12
FONT_SIZE_BASE = 14
FONT_SIZE_LARGE = 18
FONT_SIZE_XL = 22
FONT_SIZE_HUGE = 32

#: Urutan font, dari yang paling diinginkan ke cadangan yang pasti ada.
#:
#: Inter dan Poppins TIDAK ikut Windows: bila belum dipasang di mesin
#: anjungan, Qt diam-diam turun ke nama berikutnya — Segoe UI Variable,
#: font modern bawaan Windows 11. Jadi tampilannya tetap rapi tanpa font
#: tambahan, dan otomatis memakai Inter/Poppins begitu font itu dipasang.
#: Jangan hapus cadangannya: nama font yang tidak ada tanpa cadangan
#: membuat Qt memilih font pengganti apa adanya.
FONT_UI = '"Inter", "Poppins", "Segoe UI Variable", "Segoe UI", Arial, sans-serif'

STYLESHEET = f"""
QWidget {{
    font-family: {FONT_UI};
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

QLineEdit, QComboBox, QSpinBox {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: 8px 10px;
    min-height: 22px;
}}

QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
    border: 1px solid {PRIMARY};
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
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

QFrame#panelHeader {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}

QLabel#judulMerek {{
    font-size: {FONT_SIZE_LARGE}px;
    font-weight: 700;
}}

QLabel#tandaMerek {{
    background: {PRIMARY};
    color: white;
    border-radius: 8px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 800;
}}

/* Menu kerja: deretan pil di kepala, bukan daftar gelap di kiri.
   Latar track membedakannya dari tombol aksi di kanan kepala, dan
   pil terpilih berwarna penuh supaya terbaca sekilas tanpa membaca
   ulang seluruh baris. */
QFrame#navigasi {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QPushButton#navPil {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 7px 14px;
    min-height: 20px;
    color: {TEXT_MUTED};
    font-weight: 600;
}}

QPushButton#navPil:hover:!checked {{
    background: {SURFACE};
    border: none;
    color: {TEXT};
}}

QPushButton#navPil:checked {{
    background: {PRIMARY};
    border: none;
    color: white;
    font-weight: 700;
}}

QPushButton#navPil:checked:hover {{
    background: {PRIMARY_DARK};
    border: none;
    color: white;
}}

QFrame#chipPengguna {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: 20px;
}}

QLabel#inisialPengguna {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY_DARK};
    border-radius: 14px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 800;
}}

QLabel#namaPengguna {{
    color: {TEXT};
    font-weight: 600;
}}

QPushButton#tombolKepala {{
    padding: 7px 14px;
    min-height: 20px;
}}

QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}px;
}}

/* Pita peringatan di atas tabel data master. Bukan pesan kegagalan —
   tidak ada yang gagal — melainkan keadaan yang tersimpan dengan sah namun
   keliru, dan yang hanya bisa dilihat dari halaman ini. Karena itu ia
   menetap di layar, bukan muncul sekali lalu hilang. */
QLabel#peringatanData {{
    background: {WARNING_SOFT};
    border: 1px solid {WARNING};
    border-radius: {RADIUS_SM}px;
    color: {WARNING};
    padding: 10px 14px;
    font-weight: 600;
}}

/* ----- Layar Pengaturan -------------------------------------------- */

/* Daftar kelompok di kiri layar Pengaturan. Sengaja lebih tenang
   daripada pil navigasi utama: yang satu berpindah layar, yang satu
   lagi hanya berpindah bagian di dalam satu layar. */
QWidget#panelRailPengaturan {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}

QLineEdit#cariPengaturan {{
    background: {SURFACE_ALT};
    padding: 10px 12px;
}}

QLineEdit#cariPengaturan:focus {{
    padding: 9px 11px;
}}

QListWidget#railPengaturan {{
    background: transparent;
    border: none;
    outline: none;
}}

QListWidget#railPengaturan::item {{
    padding: 9px 12px;
    border: none;
    border-left: 3px solid transparent;
    border-radius: {RADIUS_SM}px;
    color: {TEXT_MUTED};
    font-weight: 600;
}}

QListWidget#railPengaturan::item:selected {{
    background: {PRIMARY_SOFT};
    border-left: 3px solid {PRIMARY};
    color: {PRIMARY_DARK};
    font-weight: 700;
}}

QListWidget#railPengaturan::item:hover:!selected {{
    background: {SURFACE_ALT};
    color: {TEXT};
}}

QFrame#kartuPengaturan {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}

/* Satu baris pengaturan. Tepi kiri disediakan sejak awal walau tembus
   pandang: tanpa itu, baris yang berubah bertambah lebar 3 piksel dan
   seluruh isinya bergeser tepat ketika ditandai. */
QFrame#barisPengaturan {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
}}

QFrame#barisPengaturan:hover {{
    background: {SURFACE_ALT};
}}

QFrame#barisPengaturan[berubah="true"] {{
    background: {PRIMARY_SOFT};
    border-left: 3px solid {PRIMARY};
}}

QFrame#barisPengaturan[berubah="true"]:hover {{
    background: {PRIMARY_SOFT};
}}

QFrame#barisPengaturan QCheckBox::indicator {{
    width: 20px;
    height: 20px;
}}

QLabel[namaPengaturan="true"] {{
    font-weight: 600;
}}

/* Bar tombol di dasar layar Pengaturan, dipisahkan garis dari isinya
   supaya tetap terbaca sebagai tempat yang tetap ketika isi di atasnya
   bergulung. */
QFrame#barPengaturan {{
    background: {SURFACE};
    border: none;
    border-top: 1px solid {BORDER};
}}

QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}

/* ----- Layar pembuka: pilihan mode ---------------------------------- */

/* Layar pertama yang dilihat orang, dan satu-satunya layar yang dilihat
   oleh orang yang belum tentu memasang aplikasi ini. Karena itu ia dibuat
   putih dan lapang, bukan abu-abu seperti layar kerja: tidak ada data yang
   perlu dibaca di sini, hanya satu keputusan yang perlu diambil. */
QDialog#dialogMode,
QDialog#dialogMesin {{
    background: {SURFACE};
}}

QLabel#judulMerek {{
    font-size: 25px;
    font-weight: 800;
    letter-spacing: -0.4px;
}}

QLabel#subJudulMerek {{
    color: {TEXT_MUTED};
    font-size: 14px;
}}

/* Lencana persegi membulat di kepala dialog. Gradien dipakai hanya di dua
   tempat pada layar ini — di sini dan pada kartu utama — supaya keduanya
   terbaca sebagai satu merek, bukan sebagai hiasan yang tersebar. */
QLabel#lencanaMerek {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 {PRIMARY}, stop:1 {MODE_PETUGAS});
    border-radius: 16px;
    color: white;
    font-size: 19px;
    font-weight: 800;
    letter-spacing: 0.5px;
}}

/* Satu pilihan layar. Seluruh kartu adalah tombolnya, bukan hanya kotak
   kecil di dalamnya: sasaran klik selebar ini penting di komputer anjungan
   yang mousenya sering setengah rusak.

   Judul dan penjelasan digambar oleh QLabel di dalam kartu, sehingga teks
   tombolnya sendiri dibuat tembus pandang. Teks itu tetap disetel karena
   itulah nama tombol yang dibaca oleh uji dan oleh pembaca layar. */
QPushButton#kartuMode {{
    background: {SURFACE};
    border: 2px solid {BORDER};
    border-radius: 16px;
    color: transparent;
    padding: 0;
    text-align: left;
    min-height: 96px;
}}

QPushButton#kartuMode:hover {{
    background: {SURFACE_ALT};
    border: 2px solid {BORDER_STRONG};
    color: transparent;
}}

QPushButton#kartuMode:focus {{
    border: 2px solid {PRIMARY};
}}

QPushButton#kartuMode:pressed {{
    background: {BORDER};
}}

QPushButton#kartuMode[aksen="antrian"]:hover {{
    background: {MODE_ANTRIAN_SOFT};
    border: 2px solid {MODE_ANTRIAN};
}}

QPushButton#kartuMode[aksen="anjungan"]:hover {{
    background: {MODE_ANJUNGAN_SOFT};
    border: 2px solid {MODE_ANJUNGAN};
}}

QPushButton#kartuMode[aksen="totem"]:hover {{
    background: {MODE_TOTEM_SOFT};
    border: 2px solid {MODE_TOTEM};
}}

QPushButton#kartuMode[aksen="admin"]:hover {{
    background: {MODE_ADMIN_SOFT};
    border: 2px solid {MODE_ADMIN};
}}

/* Kartu petugas: satu-satunya bidang berwarna penuh di layar ini. Di
   komputer loket inilah pilihan yang hampir selalu benar, dan orang yang
   ragu akan menekan yang paling menonjol. */
QPushButton#kartuMode[utama="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 {PRIMARY}, stop:1 {MODE_PETUGAS});
    border: 2px solid {PRIMARY_DARK};
}}

QPushButton#kartuMode[utama="true"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 {PRIMARY_DARK}, stop:1 #4338CA);
    border: 2px solid {PRIMARY_DARK};
}}

/* Kartu yang sedang dipilih papan ketik. Tebalnya tepi tidak berubah,
   hanya warnanya — tepi yang menebal saat difokus menggeser seluruh isi
   kartu satu piksel setiap kali orang menekan Tab. */
QPushButton#kartuMode[utama="true"]:focus {{
    border: 2px solid #E0E7FF;
}}

QLabel#judulMode {{
    color: {TEXT};
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 0.6px;
}}

QLabel#penjelasanMode {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

QPushButton#kartuMode[utama="true"] QLabel#judulMode {{
    color: white;
}}

QPushButton#kartuMode[utama="true"] QLabel#penjelasanMode {{
    color: #C7D2FE;
}}

/* Kotak ikon. Warnanya yang membedakan satu baris dari baris lain saat
   dilirik sekilas; emoji di dalamnya hanya penguat. */
QLabel#ikonMode {{
    border-radius: 14px;
    font-size: 24px;
}}

QLabel#ikonMode[aksen="antrian"] {{ background: {MODE_ANTRIAN_SOFT}; }}
QLabel#ikonMode[aksen="anjungan"] {{ background: {MODE_ANJUNGAN_SOFT}; }}
QLabel#ikonMode[aksen="totem"] {{ background: {MODE_TOTEM_SOFT}; }}
QLabel#ikonMode[aksen="admin"] {{ background: {MODE_ADMIN_SOFT}; }}
QLabel#ikonMode[aksen="petugas"] {{ background: rgba(255, 255, 255, 45); }}

QLabel#tandaPanah {{
    color: {BORDER_STRONG};
    font-size: 20px;
    font-weight: 700;
}}

QPushButton#kartuMode[utama="true"] QLabel#tandaPanah {{
    color: #C7D2FE;
}}

/* Catatan kaki tentang pintasan baris perintah. Ditaruh di dalam kotak
   abu agar terbaca sebagai keterangan pemasangan, bukan sebagai pilihan
   kelima yang gagal digambar. */
QFrame#catatanMode {{
    background: {SURFACE_ALT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}

QLabel#catatanTeks {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

QFrame#panelAlamatServer {{
    background: {PRIMARY_SOFT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}

QLabel#alamatServer {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
}}
"""


def badge_status(active: bool) -> str:
    """Label status yang mudah dibaca sekilas."""
    return "Aktif" if active else "Nonaktif"
