"""
Suara panggilan antrian.

Suara BUKAN bagian penting sistem. Komputer tanpa kartu suara, tanpa
pengeras suara, atau dengan audio yang bermasalah harus tetap dapat
menjalankan seluruh alur pelayanan. Karena itu setiap kegagalan di modul
ini ditelan dan dicatat ke log, tidak pernah dilemparkan ke atas.

Nada panggilan dibangkitkan sendiri saat dibutuhkan, sehingga aplikasi
tidak bergantung pada berkas audio yang harus ikut dipaketkan.

Setelah nada, pengumuman lisan penuh ("Nomor antrian A, nol dua tiga,
silakan menuju Loket 2") diucapkan lewat text-to-speech bawaan Windows
(SAPI/WinRT via QtTextToSpeech, bagian dari PySide6 — tanpa dependency
tambahan dan tanpa internet). Suara dipilih otomatis dalam Bahasa
Indonesia bila tersedia di komputer; bila mesin TTS tidak tersedia sama
sekali, cukup nada saja yang berbunyi.
"""

from __future__ import annotations

import math
import re
import struct
import tempfile
import wave
from collections import deque
from pathlib import Path
from typing import Protocol

from app.core.config import get_config
from app.core.logger import get_logger
from app.utils.formatting import angka_ke_kata, eja_prefix

logger = get_logger("sound")

LAJU_SAMPEL = 44_100
NADA_HZ = (880.0, 1174.7)  # A5 lalu D6 — dua nada naik, khas bel antrian
DURASI_NADA = 0.18  # detik per nada

#: Pengumuman lisan menunggu di antrean maksimal sebanyak ini. Panggilan
#: beruntun yang lebih banyak dari ini biasanya berarti sesuatu sudah
#: telat diucapkan; membuang yang tertua lebih berguna bagi petugas
#: daripada memutar pengumuman basi setelah loket lain sudah maju.
MAKS_ANTREAN_UCAPAN = 5


# ---------------------------------------------------------------------
# Pembangkit nada
# ---------------------------------------------------------------------


def buat_nada_panggilan(berkas: Path) -> Path:
    """
    Bangkitkan berkas WAV berisi nada panggilan dua nada.

    Awal dan akhir tiap nada diredam agar tidak terdengar bunyi "klik".
    """
    berkas.parent.mkdir(parents=True, exist_ok=True)
    sampel: list[int] = []

    for frekuensi in NADA_HZ:
        jumlah = int(LAJU_SAMPEL * DURASI_NADA)
        redam = int(LAJU_SAMPEL * 0.01)
        for i in range(jumlah):
            nilai = math.sin(2 * math.pi * frekuensi * i / LAJU_SAMPEL)
            if i < redam:
                nilai *= i / redam
            elif i > jumlah - redam:
                nilai *= (jumlah - i) / redam
            sampel.append(int(nilai * 20_000))

    with wave.open(str(berkas), "wb") as keluaran:
        keluaran.setnchannels(1)
        keluaran.setsampwidth(2)
        keluaran.setframerate(LAJU_SAMPEL)
        keluaran.writeframes(b"".join(struct.pack("<h", s) for s in sampel))

    return berkas


def folder_suara() -> Path:
    """
    Lokasi berkas suara.

    Folder aplikasi dipakai bila dapat ditulisi. Bila tidak — misalnya .exe
    dipasang di Program Files — berpindah ke folder sementara, karena nada
    dapat dibangkitkan ulang kapan saja dan tidak perlu bertahan.
    """
    utama = get_config().base_dir / "assets" / "sounds"
    try:
        utama.mkdir(parents=True, exist_ok=True)
        uji = utama / ".tulis"
        uji.touch()
        uji.unlink()
        return utama
    except OSError:
        cadangan = Path(tempfile.gettempdir()) / "antrian-cro-sounds"
        cadangan.mkdir(parents=True, exist_ok=True)
        return cadangan


# ---------------------------------------------------------------------
# Pemutar
# ---------------------------------------------------------------------


class SoundPlayer(Protocol):
    """Kontrak pemutar suara panggilan."""

    aktif: bool

    def announce(self, queue_number: str, counter_name: str | None = None) -> bool: ...


class NullSoundPlayer:
    """
    Tidak membunyikan apa pun.

    Dipakai ketika suara dimatikan lewat pengaturan, ketika perangkat audio
    tidak tersedia, dan pada seluruh test. Riwayat pengumumannya disimpan
    supaya alurnya tetap dapat diperiksa.
    """

    aktif = False

    def __init__(self) -> None:
        self.diumumkan: list[tuple[str, str | None]] = []

    def announce(self, queue_number: str, counter_name: str | None = None) -> bool:
        self.diumumkan.append((queue_number, counter_name))
        return False


def _eja_digit(digit: str) -> str:
    """Eja satu deret digit satu per satu ("006" -> "nol nol enam")."""
    return " ".join(angka_ke_kata(int(d)) for d in digit)


def _ucapkan_angka_dalam_teks(teks: str) -> str:
    """
    Ganti setiap deret digit dalam teks bebas menjadi ejaan digit lepas.

    Nama loket sering ditulis dengan angka Barat ("Loket 02"); dieja per
    digit ("Loket nol dua") supaya nol yang tertulis tidak pernah hilang
    dari yang diucapkan.
    """
    return re.sub(r"\d+", lambda m: _eja_digit(m.group()), teks)


def _teks_pengumuman(queue_number: str, counter_name: str | None) -> str:
    """
    Susun kalimat pengumuman dari nomor antrian.

    "A-006" -> "Nomor antrian A, nol nol enam, silakan menuju Loket 2."
    Prefix dan nomor sama-sama dieja per karakter/digit, bukan diucapkan
    sebagai bilangan wajar, supaya angka nol yang tertulis selalu ikut
    terdengar.
    """
    prefix, _, sisa = queue_number.partition("-")
    nomor = _eja_digit(sisa) if sisa.isdigit() else sisa

    kalimat = f"Nomor antrian {eja_prefix(prefix)}, {nomor}"
    if counter_name:
        kalimat += f", silakan menuju {_ucapkan_angka_dalam_teks(counter_name)}"
    return kalimat + "."


class ChimeSoundPlayer:
    """
    Membunyikan nada panggilan, lalu mengucapkan pengumuman lengkap.

    Nada memakai QtMultimedia (berkas WAV yang dibangkitkan sendiri).
    Ucapan memakai QtTextToSpeech, bagian dari PySide6, memanfaatkan mesin
    text-to-speech yang sudah terpasang di Windows — tanpa dependency
    tambahan, tanpa internet, dan tanpa berkas rekaman yang perlu disiapkan.

    Kegagalan salah satu bagian tidak menggagalkan bagian lainnya: nada
    tetap berbunyi walau TTS tidak tersedia, dan sebaliknya.
    """

    aktif = True

    def __init__(self, folder: Path | None = None) -> None:
        self.folder = folder or folder_suara()
        self.berkas_nada = self.folder / "panggilan.wav"
        self._efek = None
        self._tts = None
        self._antrean_ucapan: deque[str] = deque()
        self._siap = self._siapkan_nada()
        self._siapkan_tts()

    def _siapkan_nada(self) -> bool:
        try:
            if not self.berkas_nada.exists():
                buat_nada_panggilan(self.berkas_nada)

            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect

            efek = QSoundEffect()
            efek.setSource(QUrl.fromLocalFile(str(self.berkas_nada)))
            efek.setVolume(0.8)
            self._efek = efek
            return True
        except Exception:  # noqa: BLE001 - audio tidak boleh menggagalkan aplikasi
            logger.warning("Perangkat suara tidak tersedia; panggilan berjalan tanpa nada")
            return False

    def _siapkan_tts(self) -> None:
        """
        Siapkan mesin text-to-speech.

        Kegagalan di sini TIDAK dianggap fatal seperti kegagalan nada.
        Komputer tanpa mesin TTS terpasang (jarang di Windows, tetapi
        mungkin pada instalasi minimal) tetap harus bisa memanggil dengan
        nada saja.
        """
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech

            tts = QTextToSpeech()
            suara_indonesia = next(
                (v for v in tts.availableVoices() if v.locale().name().startswith("id")),
                None,
            )
            if suara_indonesia is not None:
                tts.setVoice(suara_indonesia)
            else:
                logger.info(
                    "Suara Bahasa Indonesia tidak tersedia untuk text-to-speech; "
                    "memakai suara bawaan mesin"
                )
            # QTextToSpeech.say() memutus ucapan yang sedang berjalan begitu
            # dipanggil lagi — dua loket memanggil berdekatan akan saling
            # menimpa bila say() dipanggil langsung. stateChanged dipakai
            # untuk tahu kapan ucapan sebelumnya selesai, supaya pengumuman
            # berikutnya menunggu gilirannya di `_antrean_ucapan` alih-alih
            # memotong yang masih berjalan.
            tts.stateChanged.connect(self._lanjutkan_antrean)
            self._tts = tts
        except Exception:  # noqa: BLE001 - audio tidak boleh menggagalkan aplikasi
            logger.info("Text-to-speech tidak tersedia; panggilan berjalan tanpa ucapan lisan")
            self._tts = None

    def _lanjutkan_antrean(self, *_diabaikan: object) -> None:
        """
        Ucapkan pengumuman berikutnya di antrean, bila mesin TTS sedang diam.

        Dipanggil baik lewat sinyal `stateChanged` (parameter statusnya
        diabaikan, dibaca ulang lewat `state()` supaya satu sumber
        kebenaran) maupun langsung dari `announce()` saat antrean baru
        terisi.
        """
        if self._tts is None or not self._antrean_ucapan:
            return

        # Seluruh badannya dijaga, bukan `say()` saja. Membaca `state()` —
        # dan mengimpor Qt untuk membandingkannya — sama-sama menyentuh
        # mesin TTS bawaan sistem, dan mesin yang cacat gagal justru di
        # situ. Modul ini berjanji tidak pernah melempar apa pun ke atas:
        # suara hanyalah pelengkap, sedangkan nomor yang gagal dipanggil
        # karenanya berarti pengunjung tidak dilayani.
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech

            if self._tts.state() != QTextToSpeech.State.Ready:
                return

            # Dikeluarkan dari antrean sebelum diucapkan: pengumuman yang
            # gagal tidak boleh dicoba terus-menerus dan menahan giliran
            # nomor berikutnya.
            self._tts.say(self._antrean_ucapan.popleft())
        except Exception:  # noqa: BLE001 - suara tidak boleh menggagalkan panggilan
            logger.exception("Gagal mengucapkan pengumuman panggilan")

    def announce(self, queue_number: str, counter_name: str | None = None) -> bool:
        """
        Bunyikan panggilan. Mengembalikan True bila nada berhasil dibunyikan.

        Ucapan lisan bersifat tambahan di atas nada dan tidak memengaruhi
        nilai kembalian: nada adalah bentuk paling minimal dari panggilan
        yang masih berguna bagi pengunjung, ucapan hanyalah pelengkap.
        Kegagalan tidak pernah dilemparkan: nomor tetap tampil di layar dan
        petugas tetap dapat memanggil secara lisan sendiri.

        Ucapan tidak langsung diputar, melainkan masuk antrean dan menunggu
        ucapan sebelumnya (bila ada) selesai — lihat `_lanjutkan_antrean`.
        """
        berhasil = False

        if self._siap and self._efek is not None:
            try:
                self._efek.play()
                logger.debug("Nada panggilan dibunyikan untuk %s", queue_number)
                berhasil = True
            except Exception:  # noqa: BLE001
                logger.exception("Gagal membunyikan nada panggilan")

        if self._tts is not None:
            if len(self._antrean_ucapan) >= MAKS_ANTREAN_UCAPAN:
                terbuang = self._antrean_ucapan.popleft()
                logger.warning("Antrean ucapan penuh; pengumuman lama dibuang: %s", terbuang)
            self._antrean_ucapan.append(_teks_pengumuman(queue_number, counter_name))
            self._lanjutkan_antrean()

        return berhasil


def buat_pemutar(aktifkan: bool) -> SoundPlayer:
    """
    Pilih pemutar sesuai pengaturan.

    Bila penyiapan audio gagal, otomatis turun ke pemutar diam alih-alih
    membiarkan aplikasi berjalan dengan pemutar yang rusak.
    """
    if not aktifkan:
        return NullSoundPlayer()

    pemutar = ChimeSoundPlayer()
    return pemutar if pemutar._siap else NullSoundPlayer()
