"""
Tema layar antrian yang menghadap pengunjung.

Satu kantor memasang layarnya di tempat yang berbeda-beda: ruang tunggu
gelap, lobi yang terang benderang, atau televisi besar di seberang ruangan.
Karena itu tampilan papan dapat dipilih administrator lewat pengaturan
`display.theme`, bukan ditetapkan sekali di kode.

Yang dipilih adalah **tampilan**, bukan isi: ketujuh tema membaca keadaan
antrian yang sama dan menampilkan loket yang sama. Tidak ada tema yang
menyembunyikan sebagian antrian.

Tujuh tema, enam kerangka:

===========  =========  =========================================
Tema         Kerangka   Dibuat untuk
===========  =========  =========================================
Kaca Malam   KISI       ruang tunggu redup, layar besar
Bento        BENTO      lobi terang, loket yang tidak sama penting
Papan LED    TABEL      jarak sangat jauh, layar memanjang
Fokus        FOKUS      kantor 1-3 loket, satu nomor per waktu
Sorotan      SOROTAN    ruangan ramai, panggilan mudah terlewat
Split        SPLIT      layar yang merangkap papan pengumuman
Kontras      KISI       pengunjung lanjut usia, ruangan silau
===========  =========  =========================================

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
#: Kisi tak simetris: loket yang sedang dipanggil menempati sel besar,
#: loket lain sel kecil di sekelilingnya.
BENTO = "bento"
#: Baris melintang bergaris tipis — NOMOR / LOKET / STATUS — seperti papan
#: keberangkatan bandara.
TABEL = "tabel"
#: Satu nomor raksasa selebar layar, loket lain menjadi pita tipis di
#: bawahnya.
FOKUS = "fokus"


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

    #: Tebal tepi kartu. Kartu unggulan selalu satu piksel lebih tebal.
    #: Tema kontras tinggi menaikkannya; tema kaca justru mengandalkan
    #: tepi tipis yang nyaris tak terlihat.
    tebal_tepi: int = 2
    #: Sudut kartu nomor menunggu. Dipisah dari `radius` karena kartu
    #: nomor jauh lebih kecil: sudut 30px pada kartu setinggi 60px
    #: memakan hurufnya sendiri.
    radius_chip: int = 14
    #: Garis rambut pemisah baris pada kerangka TABEL. Kosong berarti
    #: memakai `tepi_kartu`.
    garis: str = ""
    #: Kepekatan bayangan di bawah kartu, 0-255. Nol berarti papan datar
    #: tanpa bayangan sama sekali — yang memang dituju tema LED dan
    #: Kontras Tinggi, dan yang membuat papannya terbaca sebagai cetakan
    #: alih-alih sebagai kartu melayang.
    bayangan: int = 110

    #: Warna di dalam panel sorotan yang besar (kerangka SOROTAN dan
    #: FOKUS). Terpisah dari kartu biasa karena panel itu boleh punya
    #: terang-gelap yang berlawanan dengan papannya: kartu putih di atas
    #: latar gelap, atau sebaliknya.
    sorot_nomor: str = "#0B1220"
    sorot_teks: str = "#475569"
    #: Tulisan di dalam pil status panel sorotan. Berdiri sendiri karena
    #: pil itu berlatar `pil_latar` yang pekat, sementara status kartu
    #: biasa berlatar papan.
    sorot_pil_teks: str = "#FFFFFF"

    #: Panel pengumuman kerangka SPLIT.
    info_latar: str = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #123A52, stop:1 #0F766E)"
    )
    info_judul: str = "#CFFAFE"
    info_teks: str = "#E0F2FE"


#: Tema bawaan bila pengaturannya belum pernah diisi.
TEMA_BAWAAN = "kaca"


PALET: dict[str, Palet] = {
    "kaca": Palet(
        kode="kaca",
        label="Kaca Malam (bawaan)",
        keterangan=(
            "Kartu kaca tembus pandang di atas gradien malam. Kontras tinggi "
            "tanpa hitam pekat, paling nyaman di ruang tunggu yang lampunya redup."
        ),
        tata_letak=KISI,
        # Gradien diagonal, bukan tegak: tepi kartu kaca memantulkan
        # perbedaan warna latarnya, dan gradien yang berjalan menyerong
        # membuat setiap kartu punya tepi terang di sisi yang berbeda.
        latar=(
            "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #080C1A, stop:0.55 #101833, stop:1 #0B1226)"
        ),
        judul="#F8FAFC",
        jam="#8FA3C8",
        # Kaca = putih yang sangat tipis di atas latar. Warna pekat di sini
        # akan mematikan seluruh maksud temanya.
        kartu="rgba(148, 163, 184, 22)",
        kartu_kosong="rgba(148, 163, 184, 10)",
        kartu_unggulan=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 rgba(56, 189, 248, 70), stop:1 rgba(99, 102, 241, 38))"
        ),
        tepi_kartu="rgba(148, 163, 184, 48)",
        tepi_unggulan="#67E8F9",
        pita="",
        nama="#C7D2FE",
        nomor="#FFFFFF",
        nomor_kosong="#41506B",
        layanan="#93A5C4",
        status_berpil=True,
        status="#A5F3FC",
        status_unggulan="#062A33",
        pil_latar="#67E8F9",
        pil_latar_mati="rgba(148, 163, 184, 38)",
        panel="rgba(148, 163, 184, 18)",
        panel_judul="#93A5C4",
        chip="rgba(148, 163, 184, 24)",
        chip_teks="#F1F5F9",
        chip_tepi="rgba(148, 163, 184, 48)",
        radius=26,
        radius_chip=16,
        bayangan=130,
        sorot_nomor="#F8FAFC",
        sorot_teks="#93A5C4",
    ),
    "bento": Palet(
        kode="bento",
        label="Bento Terang",
        keterangan=(
            "Kisi tak simetris: loket yang sedang dipanggil menempati sel besar, "
            "loket lain sel kecil di sekelilingnya. Terang, untuk lobi berjendela."
        ),
        tata_letak=BENTO,
        latar=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #F7F8FC, stop:1 #EAEEF6)"
        ),
        judul="#111827",
        jam="#6B7280",
        kartu="#FFFFFF",
        kartu_kosong="#F3F4F6",
        kartu_unggulan=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #FFFFFF, stop:1 #EEF0FF)"
        ),
        tepi_kartu="#E5E7EB",
        tepi_unggulan="#6366F1",
        pita="",
        nama="#6B7280",
        nomor="#111827",
        nomor_kosong="#D1D5DB",
        layanan="#9CA3AF",
        status_berpil=True,
        status="#4F46E5",
        status_unggulan="#FFFFFF",
        pil_latar="#6366F1",
        pil_latar_mati="#EEF0FF",
        panel="#FFFFFF",
        # Abu-abu medium (#9CA3AF) di atas panel putih hampir tidak terbaca
        # dari seberang ruangan: "MENUNGGU GILIRAN" dan nama kolom layanan
        # tampak seperti watermark. Abu-abu gelap tetap sekunder terhadap
        # nomor, tetapi kontrasnya cukup untuk dibaca.
        panel_judul="#374151",
        chip="#F9FAFB",
        chip_teks="#111827",
        chip_tepi="#E5E7EB",
        radius=30,
        radius_chip=18,
        # Bayangan tipis saja. Di latar terang, bayangan pekat terbaca
        # sebagai kotoran pada layar, bukan sebagai kedalaman.
        bayangan=45,
        sorot_nomor="#111827",
        sorot_teks="#6B7280",
    ),
    "led": Palet(
        kode="led",
        label="Papan LED",
        keterangan=(
            "Baris hitam dengan angka kuning seperti papan keberangkatan bandara. "
            "Paling terbaca dari jarak sangat jauh dan pada layar memanjang."
        ),
        tata_letak=TABEL,
        latar="#000000",
        judul="#FDE047",
        jam="#A16207",
        # Baris papan keberangkatan tidak berkartu: yang memisahkannya
        # adalah garis rambut, dan latarnya sehitam papannya.
        kartu="#000000",
        kartu_kosong="#000000",
        kartu_unggulan="#161200",
        tepi_kartu="#1F2937",
        tepi_unggulan="#FDE047",
        pita="",
        nama="#E5E7EB",
        nomor="#FDE047",
        nomor_kosong="#3F3F46",
        layanan="#71717A",
        status_berpil=False,
        status="#4ADE80",
        status_unggulan="#FDE047",
        pil_latar="#FDE047",
        pil_latar_mati="#1F2937",
        panel="rgba(250, 204, 21, 14)",
        panel_judul="#A16207",
        chip="#000000",
        chip_teks="#FDE047",
        chip_tepi="#3F3F46",
        radius=8,
        renggang_nomor=6,
        radius_chip=4,
        garis="#27272A",
        bayangan=0,
        sorot_nomor="#FDE047",
        sorot_teks="#A16207",
    ),
    "fokus": Palet(
        kode="fokus",
        label="Fokus Nomor",
        keterangan=(
            "Satu nomor raksasa selebar layar, loket lain menjadi pita tipis di "
            "bawahnya. Untuk kantor dengan sedikit loket, atau layar yang jauh."
        ),
        tata_letak=FOKUS,
        latar=(
            "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #04070E, stop:1 #0B1524)"
        ),
        judul="#E2E8F0",
        jam="#64748B",
        kartu="#0D1524",
        kartu_kosong="#0A101B",
        # Panel sorotan gelap, bukan putih: nomor setinggi seperempat layar
        # dengan latar putih menjadi lampu sorot yang menyilaukan di
        # ruangan yang lampunya diredupkan.
        kartu_unggulan=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #0C2018, stop:1 #060F0C)"
        ),
        tepi_kartu="#1E293B",
        tepi_unggulan="#34D399",
        pita="",
        nama="#94A3B8",
        nomor="#E2E8F0",
        nomor_kosong="#334155",
        layanan="#64748B",
        status_berpil=False,
        status="#34D399",
        status_unggulan="#A7F3D0",
        pil_latar="#10B981",
        pil_latar_mati="rgba(148, 163, 184, 30)",
        panel="rgba(148, 163, 184, 14)",
        panel_judul="#64748B",
        chip="#0D1524",
        chip_teks="#D1FAE5",
        chip_tepi="#1E293B",
        radius=22,
        radius_chip=12,
        bayangan=140,
        sorot_nomor="#ECFDF5",
        sorot_teks="#6EE7B7",
        sorot_pil_teks="#03231A",
    ),
    "sorotan": Palet(
        kode="sorotan",
        label="Sorotan",
        keterangan=(
            "Nomor yang barusan dipanggil mengisi panel putih besar di atas latar "
            "gelap; loket lain menjadi daftar ringkas di sebelahnya."
        ),
        tata_letak=SOROTAN,
        latar=(
            "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #0E0A1E, stop:1 #241038)"
        ),
        judul="#FAF5FF",
        jam="#C4B5FD",
        kartu="#1C1030",
        kartu_kosong="#170D28",
        kartu_unggulan=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #FFFFFF, stop:1 #FDF2F8)"
        ),
        tepi_kartu="#3B1E56",
        tepi_unggulan="#F472B6",
        pita="",
        nama="#E9D5FF",
        nomor="#F5F3FF",
        nomor_kosong="#4C1D95",
        layanan="#A78BFA",
        status_berpil=True,
        status="#F9A8D4",
        status_unggulan="#FFFFFF",
        pil_latar="#DB2777",
        pil_latar_mati="rgba(216, 180, 254, 32)",
        panel="rgba(216, 180, 254, 16)",
        panel_judul="#A78BFA",
        chip="#1C1030",
        chip_teks="#F5F3FF",
        chip_tepi="#3B1E56",
        radius=24,
        radius_chip=14,
        bayangan=150,
        # Panelnya putih, jadi isinya digelapkan — kebalikan dari papannya.
        sorot_nomor="#1A0B2E",
        sorot_teks="#6B7280",
    ),
    "split": Palet(
        kode="split",
        label="Split Informasi",
        keterangan=(
            "Panel pengumuman di kiri, kolom loket di kanan. Isi panelnya diatur "
            "lewat 'Pengumuman layar antrian'."
        ),
        tata_letak=SPLIT,
        latar=(
            "qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #06131A, stop:1 #0A2028)"
        ),
        judul="#ECFEFF",
        jam="#5EEAD4",
        kartu="#FFFFFF",
        kartu_kosong="#E2E8F0",
        kartu_unggulan="#FFFFFF",
        tepi_kartu="#FFFFFF",
        tepi_unggulan="#14B8A6",
        pita="",
        nama="#0F766E",
        nomor="#0B1220",
        nomor_kosong="#94A3B8",
        layanan="#64748B",
        status_berpil=False,
        status="#64748B",
        status_unggulan="#0D9488",
        pil_latar="#0D9488",
        pil_latar_mati="#E2E8F0",
        panel="rgba(148, 163, 184, 16)",
        panel_judul="#99F6E4",
        chip="#FFFFFF",
        chip_teks="#0B1220",
        chip_tepi="#FFFFFF",
        radius=26,
        radius_chip=14,
        bayangan=120,
        sorot_nomor="#0B1220",
        sorot_teks="#64748B",
        info_latar=(
            "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #0F766E, stop:1 #155E75)"
        ),
        info_judul="#99F6E4",
        info_teks="#ECFEFF",
    ),
    "kontras": Palet(
        kode="kontras",
        label="Kontras Tinggi",
        keterangan=(
            "Putih, hitam, dan satu kuning penanda. Tanpa gradien dan tanpa "
            "bayangan — untuk pengunjung lanjut usia dan ruangan yang silau."
        ),
        tata_letak=KISI,
        # Putih polos, bukan gradien. Gradien apa pun menurunkan kontras
        # tulisan di sebagian layar, dan itulah satu-satunya hal yang
        # dijaga tema ini.
        latar="#FFFFFF",
        judul="#000000",
        jam="#3F3F46",
        kartu="#FFFFFF",
        kartu_kosong="#F4F4F5",
        kartu_unggulan="#FFF8DB",
        tepi_kartu="#000000",
        tepi_unggulan="#000000",
        pita="",
        nama="#000000",
        nomor="#000000",
        nomor_kosong="#71717A",
        layanan="#3F3F46",
        status_berpil=True,
        # Penanda "sedang dipanggil" adalah kuning, dan tulisannya tetap
        # hitam: kuning dengan tulisan putih adalah pasangan warna yang
        # paling sering gagal dibaca di ruangan terang.
        status="#000000",
        status_unggulan="#000000",
        pil_latar="#FFD400",
        pil_latar_mati="#E4E4E7",
        panel="#F4F4F5",
        panel_judul="#000000",
        chip="#FFFFFF",
        chip_teks="#000000",
        chip_tepi="#000000",
        radius=14,
        tebal_tepi=3,
        radius_chip=8,
        bayangan=0,
        sorot_nomor="#000000",
        sorot_teks="#3F3F46",
    ),
}


#: Tema lama yang sudah tidak ada, dipetakan ke penggantinya yang paling
#: mirip.
#:
#: Kode tema tersimpan di database, bukan di berkas program. Tanpa peta
#: ini, setiap kantor yang sudah pernah memilih temanya akan mendapati
#: papannya kembali ke tema bawaan setelah pembaruan — tanpa tahu sebabnya,
#: dan tanpa tahu bahwa pilihan yang dulu dipakainya masih ada dengan nama
#: lain.
ALIAS: dict[str, str] = {
    "gelap": "kaca",
    "terang": "bento",
    "modern": "bento",
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
    bersih = (kode or "").strip().lower()
    bersih = ALIAS.get(bersih, bersih)
    return PALET.get(bersih, PALET[TEMA_BAWAAN])
