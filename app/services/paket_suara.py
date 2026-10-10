"""
Paket suara untuk layar antrian Android.

Layar antrian Maxtor yang membunyikan panggilan. Bila perangkat itu punya
text-to-speech Bahasa Indonesia, kalimat lengkap diucapkannya sendiri.
Panel Android komersial sering tidak punya; untuk itu aplikasi server
membuat PAKET klip WAV pendek dengan suara Windows, dan layar memutar
potongan-potongannya berurutan:

    "Nomor antrian" · pe · be · nol · satu · empat · "silakan menuju" · loket · satu

Kosakatanya kecil dan tetap — huruf, angka, dua frasa — ditambah kata-kata
dari nama loket yang aktif. Urutan klip untuk satu panggilan disusun
`token_pengumuman`, mengikuti kalimat yang sama dengan
`sound_service.teks_pengumuman`, sehingga Windows, TTS perangkat, dan
paket suara menyebut hal yang sama.

Klip dibuat lewat PowerShell (bawaan Windows, tanpa dependensi Python
tambahan): suara Indonesia Microsoft Andika lewat WinRT bila terpasang,
selain itu System.Speech.
"""

from __future__ import annotations

import array
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

NAMA_FOLDER = Path("media") / "suara-layar"
NAMA_INDEKS = "paket.json"
JEDA = "_jeda"

#: Sampel di bawah ambang ini dianggap hening (16-bit, maksimum 32767).
AMBANG_HENING = 500
#: Sisa hening yang dibiarkan di depan dan belakang kata, supaya awal dan
#: akhir ucapan tidak terpotong.
SISA_HENING_DEPAN = 0.03
SISA_HENING_BELAKANG = 0.06

#: Nama huruf Indonesia: diucapkan sama oleh suara bahasa apa pun.
HURUF = {
    "A": "a", "B": "be", "C": "ce", "D": "de", "E": "e", "F": "ef", "G": "ge",
    "H": "ha", "I": "i", "J": "je", "K": "ka", "L": "el", "M": "em", "N": "en",
    "O": "o", "P": "pe", "Q": "ki", "R": "er", "S": "es", "T": "te", "U": "u",
    "V": "ve", "W": "we", "X": "eks", "Y": "ye", "Z": "zet",
}
ANGKA = ("nol", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan")
FRASA = {"nomor_antrian": "Nomor antrian", "silakan_menuju": "silakan menuju"}


def _slug(kata: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", kata.lower()).strip("_")


def _token_teks(teks: str) -> list[str]:
    """Kata bebas (nama loket) menjadi token: kata_xxx, digit dieja."""
    hasil: list[str] = []
    for bagian in re.findall(r"\d+|[^\W\d_]+", teks):
        if bagian.isdigit():
            hasil += [f"angka_{d}" for d in bagian]
        else:
            hasil.append(f"kata_{_slug(bagian)}")
    return hasil


def token_pengumuman(queue_number: str, counter_name: str | None) -> list[str]:
    """Urutan klip untuk satu panggilan; `_jeda` berarti diam sejenak."""
    prefix, _, sisa = queue_number.partition("-")
    token = ["nomor_antrian"]
    token += [f"huruf_{h.lower()}" for h in prefix.upper() if h in HURUF]
    token.append(JEDA)
    if sisa.isdigit():
        token += [f"angka_{d}" for d in sisa]
    else:
        token += _token_teks(sisa)
    if counter_name:
        token += [JEDA, "silakan_menuju"] + _token_teks(counter_name)
    return token


def kosakata(nama_loket: list[str]) -> dict[str, str]:
    """Seluruh klip yang dibutuhkan: kunci → teks yang diucapkan."""
    hasil = dict(FRASA)
    hasil.update({f"huruf_{h.lower()}": nama for h, nama in HURUF.items()})
    hasil.update({f"angka_{i}": kata for i, kata in enumerate(ANGKA)})
    for nama in nama_loket:
        for bagian in re.findall(r"[^\W\d_]+", nama):
            hasil.setdefault(f"kata_{_slug(bagian)}", bagian.lower())
    return hasil


@dataclass(frozen=True)
class InfoPaket:
    versi: str
    suara: str
    klip: dict[str, str]

    @property
    def jumlah(self) -> int:
        return len(self.klip)

    def kurang(self, nama_loket: list[str]) -> list[str]:
        """Kata dari nama loket yang belum punya klip (perlu dibuat ulang)."""
        return sorted(k for k in kosakata(nama_loket) if k not in self.klip)


def nama_loket_aktif() -> list[str]:
    """Nama loket aktif; kata-katanya ikut dibuatkan klip."""
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import Counter, RecordStatus

    with session_scope() as session:
        return list(
            session.scalars(
                sa.select(Counter.name).where(Counter.status == RecordStatus.ACTIVE)
            )
        )


def pangkas_hening(berkas: Path) -> None:
    """
    Buang hening panjang di awal dan akhir satu klip WAV 16-bit.

    Suara Windows menambahkan sekitar 0,8 detik hening sesudah tiap
    ucapan. Kalimat panggilan disambung dari 8-10 klip, sehingga tanpa
    dipangkas pengumumannya terdengar terpatah-patah dengan jeda bertotal
    beberapa detik. Jeda yang memang dikehendaki diatur token `_jeda`.
    """
    with wave.open(str(berkas), "rb") as masuk:
        parameter = masuk.getparams()
        isi = masuk.readframes(masuk.getnframes())
    if parameter.sampwidth != 2:
        return
    sampel = array.array("h", isi)
    if sys.byteorder == "big":
        sampel.byteswap()
    saluran = parameter.nchannels
    keras = [i for i, v in enumerate(sampel) if abs(v) > AMBANG_HENING]
    if not keras:
        return
    laju = parameter.framerate
    awal = max(0, keras[0] // saluran - int(laju * SISA_HENING_DEPAN))
    akhir = min(len(sampel) // saluran, keras[-1] // saluran + 1 + int(laju * SISA_HENING_BELAKANG))
    hasil = sampel[awal * saluran:akhir * saluran]
    if sys.byteorder == "big":
        hasil.byteswap()
    with wave.open(str(berkas), "wb") as keluar:
        keluar.setnchannels(saluran)
        keluar.setsampwidth(2)
        keluar.setframerate(laju)
        keluar.writeframes(hasil.tobytes())


def folder_paket(base: Path) -> Path:
    return Path(base) / NAMA_FOLDER


def info_paket(folder: Path) -> InfoPaket | None:
    try:
        data = json.loads((Path(folder) / NAMA_INDEKS).read_text(encoding="utf-8"))
        return InfoPaket(versi=str(data["versi"]), suara=str(data.get("suara", "")),
                         klip=dict(data["klip"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


#: Suara Indonesia Windows (Microsoft Andika) hanya terpasang sebagai suara
#: OneCore, yang TIDAK terlihat oleh System.Speech: lewat System.Speech
#: paket selalu jatuh ke David/Zira berlogat Inggris. Karena itu suara
#: Indonesia dicari dulu lewat WinRT (Windows.Media.SpeechSynthesis, yang
#: juga dipakai QtTextToSpeech di aplikasi Windows); System.Speech hanya
#: cadangan bila WinRT tidak punya suara id-ID atau tidak tersedia.
_SKRIP = r"""
$ErrorActionPreference = 'Stop'
$daftar = Get-Content -LiteralPath $args[0] -Raw -Encoding UTF8 | ConvertFrom-Json
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $suara = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Language -eq 'id-ID' } | Select-Object -First 1
} catch { $suara = $null }
if ($suara) {
    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
    function Tunggu($op, [Type]$jenis) {
        $t = $asTask.MakeGenericMethod($jenis).Invoke($null, @($op)); $null = $t.Wait(-1); $t.Result
    }
    $s = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
    $s.Voice = $suara
    foreach ($butir in $daftar) {
        $aliran = Tunggu ($s.SynthesizeTextToStreamAsync($butir.teks)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
        $ukuran = [uint32]$aliran.Size
        $baca = New-Object Windows.Storage.Streams.DataReader($aliran.GetInputStreamAt(0))
        $null = Tunggu ($baca.LoadAsync($ukuran)) ([uint32])
        $isi = New-Object byte[] $ukuran
        $baca.ReadBytes($isi)
        [IO.File]::WriteAllBytes($butir.berkas, $isi)
        $baca.Dispose(); $aliran.Dispose()
    }
    $s.Dispose()
    Write-Output ($suara.DisplayName + '|' + $suara.Language)
    exit 0
}
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$id = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'id-ID' } | Select-Object -First 1
if ($id) { $s.SelectVoice($id.VoiceInfo.Name) }
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($butir in $daftar) {
    $s.SetOutputToWaveFile($butir.berkas, $format)
    $s.Speak($butir.teks)
}
$s.SetOutputToNull()
Write-Output ($s.Voice.Name + '|' + $s.Voice.Culture.Name)
"""


def buat_paket(folder: Path, nama_loket: list[str], *, timeout: int = 300) -> InfoPaket:
    """
    Buat ulang seluruh klip lewat suara Windows, lalu tulis indeksnya.

    Indeks ditulis TERAKHIR, sesudah semua klip jadi: layar yang mengunduh
    di tengah pembuatan tetap memakai paket lama yang utuh.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    kata = kosakata(nama_loket)
    klip = {kunci: f"{kunci}.wav" for kunci in kata}
    with tempfile.TemporaryDirectory() as sementara:
        daftar = Path(sementara) / "daftar.json"
        daftar.write_text(
            json.dumps(
                [{"berkas": str(folder / klip[k]), "teks": teks} for k, teks in kata.items()],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        hasil = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", f"& {{{_SKRIP}}} '{daftar}'"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if hasil.returncode != 0:
        detail = (hasil.stderr or hasil.stdout).strip().splitlines()
        raise RuntimeError(
            "Suara Windows gagal membuat klip: " + (detail[-1] if detail else "tanpa keterangan")
        )
    for berkas in klip.values():
        try:
            pangkas_hening(folder / berkas)
        except (OSError, EOFError, wave.Error):
            pass  # klip tetap dapat diputar, hanya jedanya lebih panjang
    nama, _, budaya = (hasil.stdout.strip().splitlines() or ["|"])[-1].partition("|")
    suara = f"{nama} ({'Indonesia' if budaya == 'id-ID' else budaya or '?'})"
    versi = hashlib.sha256(
        json.dumps(
            {
                "suara": suara,
                "kata": kata,
                # Cara memangkas ikut menentukan isi klip: tablet yang sudah
                # menyimpan klip versi lama harus mengunduh ulang.
                "pangkas": [AMBANG_HENING, SISA_HENING_DEPAN, SISA_HENING_BELAKANG],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    info = InfoPaket(versi=versi, suara=suara, klip=klip)
    (folder / NAMA_INDEKS).write_text(
        json.dumps({"versi": versi, "suara": suara, "klip": klip}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return info


class SuaraTurunError(RuntimeError):
    """Paket baru berlogat lain, sedangkan paket terpasang berbahasa Indonesia."""


def suara_indonesia(info: InfoPaket | None) -> bool:
    return info is not None and info.suara.endswith("(Indonesia)")


def perbarui_bila_perlu(folder: Path, nama_loket: list[str]) -> InfoPaket | None:
    """
    Buat ulang paket bila belum ada atau ada kata nama loket tanpa klip.

    Dipanggil berkala oleh API anjungan di komputer server, sehingga loket
    yang ditambah atau diganti namanya dari PC admin mana pun tetap
    terdengar di perangkat tanpa TTS Indonesia — tanpa menunggu admin
    menekan "Buat ulang paket suara".

    API berjalan sebagai akun SYSTEM, yang belum tentu melihat suara
    Indonesia. Karena itu paket dibangun di folder sementara dan baru
    dipasang bila suaranya tidak turun: paket berbahasa Indonesia tidak
    pernah ditimpa paket berlogat Inggris. Klip disalin lebih dulu dan
    indeks paling akhir, seperti `buat_paket`.

    Mengembalikan paket yang baru dipasang, atau None bila tidak perlu.
    SuaraTurunError bila paket baru ditolak karena suaranya.
    """
    folder = Path(folder)
    lama = info_paket(folder)
    if lama is not None and not lama.kurang(nama_loket):
        return None
    sementara = folder.with_name(folder.name + "-baru")
    shutil.rmtree(sementara, ignore_errors=True)
    try:
        baru = buat_paket(sementara, nama_loket)
        if suara_indonesia(lama) and not suara_indonesia(baru):
            raise SuaraTurunError(
                f"Paket tetap memakai {lama.suara}: proses ini hanya mendapat {baru.suara}. "
                "Tekan Buat ulang paket suara di Layanan Anjungan."
            )
        folder.mkdir(parents=True, exist_ok=True)
        for berkas in baru.klip.values():
            shutil.copyfile(sementara / berkas, folder / berkas)
        shutil.copyfile(sementara / NAMA_INDEKS, folder / NAMA_INDEKS)
        return baru
    finally:
        shutil.rmtree(sementara, ignore_errors=True)

