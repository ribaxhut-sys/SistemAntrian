"""
Peran komputer ini terhadap PENGUNJUNG: dipakai sebagai apa.

Berbeda dari `app.core.mesin`, yang mengatur peran terhadap DATABASE —
server, klien, atau berdiri sendiri. Yang di sini menjawab pertanyaan lain:
layar mana yang dibuka komputer ini, apakah ia mencetak tiket, apakah ia
berbunyi, dan berbentuk apa papannya.

Isinya hidup di berkas `peran.json` di folder database komputer ini,
TERPISAH dari `mesin.json`. Alasannya bukan kerapian melainkan keamanan:
`mesin.json` memuat kata sandi database dan tidak boleh disalin ke komputer
lain, sedangkan berkas ini justru dirancang untuk disalin — lima komputer
loket isinya sama persis, dan pemasang yang menyalinnya lewat Notepad
sedang melakukan hal yang benar.

Yang disimpan adalah PILIHAN, bukan hasil simpulannya. Kosong berarti "ikut
perannya". Menyimpan hasil akhirnya membekukan ketujuh komputer pada nilai
yang ditulis saat pemasangan: perbaikan tabel simpulan di versi berikutnya
tidak akan pernah sampai ke sana, dan tiap mesin harus didatangi satu per
satu.

Peran hanya menyatakan apa yang benar-benar diketahuinya tentang mesin itu,
dan diam untuk sisanya. "Tidak mencetak" adalah fakta tentang komputer
loket — memang tidak ada pencetak yang menempel padanya. Tetapi BAGAIMANA
mencetak, bagi mesin yang memang mencetak, tetap keputusan seluruh sistem
lewat `ticket.printer`; peran tidak berhak menebaknya.

Environment variable tetap mengalahkan berkas ini, sama seperti
ANTRIAN_DB_URL mengalahkan `mesin.json`. Pemasangan yang sudah memakai
`setx ANTRIAN_PRINTER` hari ini harus berperilaku sama persis besok.

Lihat docs/peran-komputer.md untuk rancangan lengkapnya.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("antrian.peran")

NAMA_BERKAS = "peran.json"

#: Peran yang dikenali. Nilainya terbaca manusia dan ditulis dengan huruf
#: kecil: berkas ini memang diniatkan untuk dibuka di Notepad.
PETUGAS = "petugas"
ADMIN = "admin"
ANJUNGAN = "anjungan"
ANJUNGAN_TOTEM = "anjungan-totem"
TELEVISI = "televisi"
PAPAN_MEMANJANG = "papan-memanjang"

#: Mode tampilan yang diminta ke `app.main`.
#:
#: Ditulis ulang di sini, TIDAK diimpor dari app.ui.login.mode_dialog:
#: lapisan core tidak boleh bergantung pada lapisan tampilan. Supaya
#: keduanya tidak diam-diam berbeda, ada test yang membandingkannya —
#: pola yang sama dipakai daftar tema di settings_service.
MODE_PETUGAS = "petugas"
MODE_ADMIN = "admin"
MODE_ANJUNGAN = "anjungan"
MODE_ANJUNGAN_TOTEM = "anjungan-totem"
MODE_LAYAR_ANTRIAN = "antrian"

#: Mode yang menghadap pengunjung tanpa ada yang menjaganya.
#:
#: Komputer seperti ini tidak boleh berhenti di dialog mana pun. Anjungan
#: yang pulih sesudah mati listrik, dan televisi yang menyala bersama
#: sakelar lampu pagi hari, tidak punya siapa pun untuk menekan tombol.
MODE_PUBLIK = frozenset(
    {MODE_ANJUNGAN, MODE_ANJUNGAN_TOTEM, MODE_LAYAR_ANTRIAN}
)

#: Nilai `ticket.printer` yang berarti mesin ini tidak mencetak sama sekali.
TIDAK_MENCETAK = "none"

#: Nilai yang dikenali untuk kedua isian bebas. Ditulis ulang di sini dengan
#: alasan yang sama seperti nama mode — core tidak bergantung pada lapisan di
#: atasnya — dan dijaga sepasang test agar tidak diam-diam berbeda.
#:
#: Nilai yang tidak dikenali diperlakukan seperti tidak diisi, bukan ditolak
#: dengan galat. Sikap yang sama sudah dipakai `_bool_from_env` di
#: app.core.config: salah ketik di satu komputer tidak boleh mengubah
#: perilakunya tanpa jejak, dan tidak boleh pula membuatnya gagal dibuka.
PENCETAK_SAH = frozenset({"pdf", "system", "none"})
BENTUK_SAH = frozenset({"lebar", "memanjang", "tegak"})


@dataclass(frozen=True)
class BawaanPeran:
    """
    Apa yang disimpulkan dari sebuah peran.

    Bidang yang kosong — `""` atau `None` — berarti peran ini TIDAK
    berpendapat, dan yang berlaku adalah pengaturan bersama di database.
    Diamnya disengaja: peran yang menebak terlalu banyak akan menimpa
    keputusan yang seharusnya milik seluruh kantor.
    """

    mode: str
    printer: str = ""
    suara: bool | None = None
    bentuk_layar: str = ""


#: Tabel simpulan. Satu-satunya tempat yang boleh menjawab "peran ini
#: berarti apa"; dialog dan `main` membacanya dari sini.
BAWAAN: dict[str, BawaanPeran] = {
    PETUGAS: BawaanPeran(mode=MODE_PETUGAS, printer=TIDAK_MENCETAK),
    ADMIN: BawaanPeran(mode=MODE_ADMIN, printer=TIDAK_MENCETAK),
    # Anjungan sengaja DIAM. Pengunjung berdiri beberapa langkah dari
    # televisi ruang tunggu, dan dua pengeras suara yang memanggil nomor
    # yang sama dengan selisih setengah detik terdengar seperti kerusakan.
    ANJUNGAN: BawaanPeran(mode=MODE_ANJUNGAN, suara=False),
    ANJUNGAN_TOTEM: BawaanPeran(mode=MODE_ANJUNGAN_TOTEM, suara=False),
    TELEVISI: BawaanPeran(mode=MODE_LAYAR_ANTRIAN, printer=TIDAK_MENCETAK),
    # Papan memanjang mewarisi diamnya anjungan, dan karena alasan yang
    # persis sama: kantor yang memasang televisi DAN pita di atas pintu
    # mendapat dua suara untuk satu panggilan, sepanjang hari.
    PAPAN_MEMANJANG: BawaanPeran(
        mode=MODE_LAYAR_ANTRIAN,
        printer=TIDAK_MENCETAK,
        suara=False,
        bentuk_layar="memanjang",
    ),
}

PERAN_SAH = frozenset(BAWAAN)

#: Nama peran untuk dibaca manusia.
#:
#: Disebut menurut BENDA-nya, bukan menurut mode teknis yang dibukanya:
#: orang yang memasang mengenali komputernya dari tempat ia berdiri di
#: ruangan, bukan dari nama halaman yang muncul di layarnya.
LABEL: dict[str, str] = {
    PETUGAS: "Loket petugas",
    ADMIN: "Loket admin",
    ANJUNGAN: "Anjungan ambil nomor",
    ANJUNGAN_TOTEM: "Anjungan berdiri (totem)",
    TELEVISI: "Televisi ruang tunggu",
    PAPAN_MEMANJANG: "Papan memanjang di atas pintu",
}


@dataclass(frozen=True)
class PeranKomputer:
    """
    Pilihan yang tersimpan pada satu komputer.

    `peran` kosong berarti komputer ini belum pernah ditetapkan, dan
    aplikasi berperilaku persis seperti sebelum berkas ini ada: dialog
    pilih-mode muncul saat dibuka.

    Ketiga bidang lainnya `None` berarti "ikut perannya". Diisi berarti
    orang yang memasang memang menghendaki nilai itu — dan pilihannya tidak
    boleh hilang hanya karena tabel simpulan berubah di versi berikutnya.
    """

    peran: str = ""
    printer: str | None = None
    suara: bool | None = None
    bentuk_layar: str | None = None

    @property
    def bawaan(self) -> BawaanPeran | None:
        """Simpulan perannya, atau None bila perannya tidak dikenali."""
        return BAWAAN.get(self.peran)

    @property
    def ditetapkan(self) -> bool:
        """Komputer ini sudah pernah ditetapkan perannya."""
        return self.bawaan is not None

    @property
    def mode(self) -> str:
        """Mode tampilan yang diminta, atau "" bila belum ditetapkan."""
        bawaan = self.bawaan
        return bawaan.mode if bawaan is not None else ""

    @property
    def printer_efektif(self) -> str:
        """Pencetak mesin ini; "" berarti ikut `ticket.printer`."""
        if self.printer is not None:
            return self.printer
        bawaan = self.bawaan
        return bawaan.printer if bawaan is not None else ""

    @property
    def suara_efektif(self) -> bool | None:
        """
        Mesin ini berbunyi atau tidak; None berarti ikut pengaturan bersama.

        None BUKAN sama dengan False — perbedaan yang sama sudah dipakai
        AppConfig.suara, dan hasil di sini memang masuk ke sana.
        """
        if self.suara is not None:
            return self.suara
        bawaan = self.bawaan
        return bawaan.suara if bawaan is not None else None

    @property
    def bentuk_efektif(self) -> str:
        """Bentuk layar mesin ini; "" berarti papan mengukur sendiri."""
        if self.bentuk_layar is not None:
            return self.bentuk_layar
        bawaan = self.bawaan
        return bawaan.bentuk_layar if bawaan is not None else ""

    @property
    def label(self) -> str:
        """
        Nama peran untuk ditampilkan, "" bila belum ditetapkan.

        Diberi tanda "(disesuaikan)" bila ada isian yang menyimpang dari
        bawaannya. Orang yang memasang tujuh komputer perlu melihat bahwa
        satu di antaranya tidak lagi sama dengan saudara-saudaranya, tanpa
        harus membuka tiap isian satu per satu.
        """
        nama = LABEL.get(self.peran, "")
        if nama and self.disesuaikan:
            return f"{nama} (disesuaikan)"
        return nama

    @property
    def publik(self) -> bool:
        """
        Komputer ini menghadap pengunjung dan tidak ada yang menjaganya.

        Lihat MODE_PUBLIK. Dipakai untuk memutuskan apakah aplikasi boleh
        berhenti di sebuah dialog saat dibuka — dan jawabannya tidak boleh
        berbeda antara mesin yang menyebut perannya lewat pintasan dan
        mesin yang menyebutnya lewat berkas.
        """
        return self.mode in MODE_PUBLIK

    @property
    def disesuaikan(self) -> bool:
        """
        Ada isian yang menyimpang dari bawaan perannya.

        Dipakai tampilan untuk menulis "Televisi ruang tunggu
        (disesuaikan)" — orang perlu melihat bahwa mesin ini tidak lagi
        sama dengan saudaranya, tanpa harus membuka tiap isian.
        """
        if not self.ditetapkan:
            return False
        return any(
            nilai is not None
            for nilai in (self.printer, self.suara, self.bentuk_layar)
        )

    def ke_dict(self) -> dict:
        """
        Bentuk yang ditulis ke berkas.

        Bidang yang "ikut peran" ditulis sebagai `null`, bukan dibuang.
        Berkas ini dibaca dan disunting manusia, dan kunci yang hadir
        dengan nilai null menunjukkan bahwa pilihan itu ADA — sedangkan
        kunci yang hilang terbaca seperti fitur yang belum dibuat.
        """
        return {
            "peran": self.peran,
            "printer": self.printer,
            "suara": self.suara,
            "bentuk_layar": self.bentuk_layar,
        }


def _teks(nilai) -> str | None:
    """Nilai teks yang sudah dirapikan, atau None bila bukan teks berisi."""
    if not isinstance(nilai, str):
        return None
    bersih = nilai.strip().lower()
    return bersih or None


def _boolean(nilai) -> bool | None:
    """
    Nilai boolean dari JSON, atau None bila tidak berpendapat.

    Menerima tulisan manusia juga — berkas ini disunting di Notepad, dan
    orang yang mengetik "ya" tidak sedang melakukan kesalahan.
    """
    if isinstance(nilai, bool):
        return nilai
    teks = _teks(nilai)
    if teks in {"true", "1", "ya", "yes", "on"}:
        return True
    if teks in {"false", "0", "tidak", "no", "off"}:
        return False
    return None


def _dari_daftar(nilai, sah: frozenset[str], sebutan: str) -> str | None:
    """Nilai yang dikenali, atau None — dengan jejak di log bila salah ketik."""
    teks = _teks(nilai)
    if teks is None:
        return None
    if teks not in sah:
        logger.warning("%s '%s' tidak dikenali; diabaikan.", sebutan, teks)
        return None
    return teks


def dari_dict(data: dict) -> PeranKomputer:
    """
    Bangun pilihan dari isi berkas, mengabaikan apa pun yang tidak dikenali.

    Peran yang salah ketik diperlakukan seperti belum ditetapkan, bukan
    ditolak dengan galat: berkas yang keliru di satu komputer tidak boleh
    membuat komputer itu gagal dibuka sama sekali.
    """
    peran = _teks(data.get("peran")) or ""
    if peran not in PERAN_SAH:
        if peran:
            logger.warning("Peran '%s' tidak dikenali; diabaikan.", peran)
        peran = ""
    return PeranKomputer(
        peran=peran,
        printer=_dari_daftar(data.get("printer"), PENCETAK_SAH, "Pencetak"),
        suara=_boolean(data.get("suara")),
        bentuk_layar=_dari_daftar(
            data.get("bentuk_layar"), BENTUK_SAH, "Bentuk layar"
        ),
    )


def path_berkas_peran(db_path: Path) -> Path:
    """
    Letak `peran.json`.

    Mengikuti folder database, sama seperti `mesin.json`, supaya test yang
    mengarahkan ANTRIAN_DB_PATH ke folder sementara tidak membaca berkas
    milik pengembang. ANTRIAN_PERAN_PATH menimpa lokasi itu bila diisi.
    """
    override = os.environ.get("ANTRIAN_PERAN_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(db_path).expanduser().resolve().parent / NAMA_BERKAS


def baca_peran(path: Path) -> PeranKomputer:
    """
    Baca berkas peran. Tidak pernah melempar galat.

    Berkas yang hilang, rusak, setengah tertulis, atau berisi sesuatu yang
    bukan objek JSON sama-sama menghasilkan pilihan kosong — dan pilihan
    kosong berarti aplikasi berperilaku persis seperti sebelum berkas ini
    ada. Komputer yang berkasnya rusak tetap dapat dibuka; yang hilang
    hanyalah kenyamanannya.
    """
    try:
        isi = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return PeranKomputer()
    except OSError as galat:
        logger.warning("Berkas peran tidak terbaca (%s): %s", path, galat)
        return PeranKomputer()

    try:
        data = json.loads(isi)
    except ValueError as galat:
        logger.warning("Berkas peran rusak (%s): %s", path, galat)
        return PeranKomputer()

    if not isinstance(data, dict):
        logger.warning("Berkas peran bukan objek JSON (%s).", path)
        return PeranKomputer()
    return dari_dict(data)


def tulis_peran(path: Path, peran: PeranKomputer) -> None:
    """
    Tulis berkas peran, membuat foldernya bila perlu.

    Ditulis lewat berkas sementara lalu diganti namanya. Aplikasi yang
    ditutup paksa di tengah penulisan — dan komputer yang menghadap publik
    memang sering dimatikan lewat tombol — tidak menyisakan berkas separuh
    jadi yang harus dihapus orang dengan tangan.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    sementara = path.with_suffix(path.suffix + ".tmp")
    sementara.write_text(
        json.dumps(peran.ke_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    sementara.replace(path)
    logger.info("Peran komputer disimpan sebagai '%s'.", peran.peran or "(kosong)")
