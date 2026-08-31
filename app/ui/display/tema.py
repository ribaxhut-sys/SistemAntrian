"""
Tema layar antrian yang menghadap pengunjung.

Satu kantor memasang layarnya di tempat yang berbeda-beda: ruang tunggu
gelap, lobi yang terang benderang, atau televisi besar di seberang ruangan.
Karena itu tampilan papan dapat dipilih administrator lewat pengaturan
`display.theme`, bukan ditetapkan sekali di kode.

Yang dipilih adalah **tampilan**, bukan isi: kelima tema membaca keadaan
antrian yang sama dan menampilkan loket yang sama. Tidak ada tema yang
menyembunyikan sebagian antrian.

Setiap palet membawa dua hal:

1. Warna — semuanya #RRGGBB atau rgba(). Qt tidak mendukung #RRGGBBAA dan
   membacanya sebagai warna yang sama sekali lain.
2. `tata_letak` — kerangka mana yang dipakai DisplayPage untuk menyusunnya.

Menambah tema baru cukup dengan menambah satu Palet di sini dan satu
pilihan di SKEMA pengaturan; DisplayPage tidak perlu diubah selama tata
letaknya salah satu dari yang sudah ada.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Kartu loket berjajar sebagai kisi, maksimum tiga kolom.
KISI = "kisi"
#: Panggilan terbaru mengisi panel besar, loket lain menjadi baris ringkas.
SOROTAN = "sorotan"
#: Panel informasi di kiri, kolom loket di kanan.
SPLIT = "split"


@dataclass(frozen=True)
class Palet:
    """Seluruh warna dan bentuk satu tema papan antrian."""

    kode: str
    label: str
    keterangan: str
    tata_letak: str

    #: Nilai `background` halaman. Boleh berupa qlineargradient.
    latar: str
    judul: str
    jam: str

    kartu: str
    kartu_kosong: str
    kartu_unggulan: str
    tepi_kartu: str
    tepi_unggulan: str
    #: Pita tipis di atas kartu. Kosong berarti kartu tanpa pita.
    pita: str

    nama: str
    nomor: str
    nomor_kosong: str
    layanan: str

    #: Status ditampilkan sebagai pil berlatar, bukan sekadar tulisan.
    status_berpil: bool
    status: str
    status_unggulan: str
    pil_latar: str
    pil_latar_mati: str

    panel: str
    panel_judul: str
    chip: str
    chip_teks: str
    chip_tepi: str

    radius: int = 28
    #: Nomor antrian ditulis dengan huruf yang lebih renggang, seperti papan
    #: keberangkatan. Hanya dipakai tema LED.
    renggang_nomor: int = 0


#: Tema bawaan bila pengaturannya belum pernah diisi.
TEMA_BAWAAN = "gelap"


PALET: dict[str, Palet] = {
    "gelap": Palet(
        kode="gelap",
        label="Kartu Gelap (bawaan)",
        keterangan="Kartu gelap dengan tepi menyala. Kontras tertinggi di ruang tunggu.",
        tata_letak=KISI,
        latar="#070C16",
        judul="#F8FAFC",
        jam="#64748B",
        kartu="#101B2D",
        kartu_kosong="#0D1526",
        kartu_unggulan=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #0E3A46, stop:1 #0B2430)"
        ),
        tepi_kartu="#1E3A5F",
        tepi_unggulan="#22D3EE",
        pita="",
        nama="#94A3B8",
        nomor="#E2E8F0",
        nomor_kosong="#334155",
        layanan="#64748B",
        status_berpil=True,
        status="#5EEAD4",
        status_unggulan="#052F2B",
        pil_latar="#22D3EE",
        pil_latar_mati="rgba(148, 163, 184, 30)",
        panel="rgba(148, 163, 184, 16)",
        panel_judul="#475569",
        chip="#101B2D",
        chip_teks="#E2E8F0",
        chip_tepi="#1E3A5F",
        radius=32,
    ),
    "terang": Palet(
        kode="terang",
        label="Terang Minimal",
        keterangan="Latar terang dan kartu putih. Paling nyaman di lobi yang benderang.",
        tata_letak=KISI,
        latar="#F1F5F9",
        judul="#0F172A",
        jam="#64748B",
        kartu="#FFFFFF",
        kartu_kosong="#FFFFFF",
        kartu_unggulan="#FFFFFF",
        tepi_kartu="#FFFFFF",
        tepi_unggulan="#0891B2",
        pita="#0F766E",
        nama="#0F766E",
        nomor="#0F172A",
        nomor_kosong="#CBD5E1",
        layanan="#64748B",
        status_berpil=False,
        status="#94A3B8",
        status_unggulan="#0891B2",
        pil_latar="#0891B2",
        pil_latar_mati="#E2E8F0",
        panel="#FFFFFF",
        panel_judul="#94A3B8",
        chip="#F1F5F9",
        chip_teks="#0F172A",
        chip_tepi="#F1F5F9",
        radius=30,
    ),
    "sorotan": Palet(
        kode="sorotan",
        label="Sorotan",
        keterangan="Nomor yang barusan dipanggil mengisi layar; loket lain menjadi daftar ringkas.",
        tata_letak=SOROTAN,
        latar=(
            "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #0A1020, stop:1 #12263F)"
        ),
        judul="#F8FAFC",
        jam="#7DD3FC",
        kartu="#16233A",
        kartu_kosong="#111C2E",
        kartu_unggulan=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #FFFFFF, stop:1 #E8F3F2)"
        ),
        tepi_kartu="#1E3A5F",
        tepi_unggulan="#22D3EE",
        pita="",
        nama="#E2E8F0",
        nomor="#FFFFFF",
        nomor_kosong="#475569",
        layanan="#94A3B8",
        status_berpil=True,
        status="#7DD3FC",
        status_unggulan="#FFFFFF",
        pil_latar="#0F766E",
        pil_latar_mati="rgba(148, 163, 184, 30)",
        panel="rgba(148, 163, 184, 16)",
        panel_judul="#94A3B8",
        chip="#E2E8F0",
        chip_teks="#0B1220",
        chip_tepi="#E2E8F0",
        radius=24,
    ),
    "split": Palet(
        kode="split",
        label="Split Informasi",
        keterangan=(
            "Panel pengumuman di kiri, kolom loket di kanan. Isi panelnya diatur "
            "lewat 'Pengumuman layar antrian'."
        ),
        tata_letak=SPLIT,
        latar="#0B1220",
        judul="#F8FAFC",
        jam="#7DD3FC",
        kartu="#FFFFFF",
        kartu_kosong="#E2E8F0",
        kartu_unggulan="#FFFFFF",
        tepi_kartu="#FFFFFF",
        tepi_unggulan="#22D3EE",
        pita="",
        nama="#0F766E",
        nomor="#0B1220",
        nomor_kosong="#94A3B8",
        layanan="#64748B",
        status_berpil=False,
        status="#64748B",
        status_unggulan="#0891B2",
        pil_latar="#0891B2",
        pil_latar_mati="#E2E8F0",
        panel="rgba(148, 163, 184, 16)",
        panel_judul="#94A3B8",
        chip="#FFFFFF",
        chip_teks="#0B1220",
        chip_tepi="#FFFFFF",
        radius=26,
    ),
    "modern": Palet(
        kode="modern",
        label="Modern Cerah",
        keterangan=(
            "Latar cerah berlapis dengan aksen biru-teal. Paling nyaman di "
            "anjungan yang dilihat dari dekat, dan terang di ruangan berjendela."
        ),
        tata_letak=KISI,
        # Cerah tapi tidak putih polos: gradien halus memberi kedalaman
        # tanpa mengurangi keterbacaan di ruangan terang.
        latar=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #F8FAFC, stop:1 #EAF0F6)"
        ),
        judul="#0F172A",
        jam="#64748B",
        kartu="#FFFFFF",
        kartu_kosong="#F1F5F9",
        kartu_unggulan=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #FFFFFF, stop:1 #E0F2FE)"
        ),
        tepi_kartu="#E2E8F0",
        tepi_unggulan="#0EA5E9",
        pita="",
        nama="#0F766E",
        nomor="#0F172A",
        nomor_kosong="#CBD5E1",
        layanan="#64748B",
        status_berpil=True,
        status="#0369A1",
        status_unggulan="#FFFFFF",
        pil_latar="#0EA5E9",
        pil_latar_mati="#E2E8F0",
        panel="#FFFFFF",
        panel_judul="#64748B",
        chip="#F1F5F9",
        chip_teks="#0F172A",
        chip_tepi="#E2E8F0",
        radius=28,
    ),
    "led": Palet(
        kode="led",
        label="Papan LED",
        keterangan=(
            "Hitam dengan angka kuning seperti papan keberangkatan. Paling terbaca "
            "dari jarak sangat jauh."
        ),
        tata_letak=KISI,
        latar="#05070A",
        judul="#FBBF24",
        jam="#A16207",
        kartu="#0B0F16",
        kartu_kosong="#080B11",
        kartu_unggulan="#141A0B",
        tepi_kartu="#1F2937",
        tepi_unggulan="#FBBF24",
        pita="",
        nama="#E5E7EB",
        nomor="#FBBF24",
        nomor_kosong="#374151",
        layanan="#6B7280",
        status_berpil=False,
        status="#34D399",
        status_unggulan="#FBBF24",
        pil_latar="#FBBF24",
        pil_latar_mati="#1F2937",
        panel="rgba(148, 163, 184, 12)",
        panel_judul="#6B7280",
        chip="#0B0F16",
        chip_teks="#FBBF24",
        chip_tepi="#1F2937",
        radius=12,
        renggang_nomor=4,
    ),
}


#: Pasangan (nilai tersimpan, tulisan di layar) untuk SKEMA pengaturan.
PILIHAN_TEMA: tuple[tuple[str, str], ...] = tuple(
    (p.kode, p.label) for p in PALET.values()
)


def palet_untuk(kode: str | None) -> Palet:
    """
    Palet sebuah tema, dengan tema bawaan sebagai jaring pengaman.

    Nilai yang tidak dikenal — misalnya sisa dari versi lain atau hasil
    suntingan langsung ke database — tidak boleh membuat layar publik gagal
    terbuka. Papan yang menyala dengan tampilan bawaan jauh lebih baik
    daripada papan yang tidak menyala sama sekali.
    """
    return PALET.get((kode or "").strip().lower(), PALET[TEMA_BAWAAN])
