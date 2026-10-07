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

Klip dibuat lewat PowerShell + System.Speech (bawaan Windows, tanpa
dependensi Python tambahan), dengan suara Bahasa Indonesia bila ada.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

NAMA_FOLDER = Path("media") / "suara-layar"
NAMA_INDEKS = "paket.json"
JEDA = "_jeda"

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


def folder_paket(base: Path) -> Path:
    return Path(base) / NAMA_FOLDER


def info_paket(folder: Path) -> InfoPaket | None:
    try:
        data = json.loads((Path(folder) / NAMA_INDEKS).read_text(encoding="utf-8"))
        return InfoPaket(versi=str(data["versi"]), suara=str(data.get("suara", "")),
                         klip=dict(data["klip"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


_SKRIP = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$daftar = Get-Content -LiteralPath $args[0] -Raw -Encoding UTF8 | ConvertFrom-Json
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
    nama, _, budaya = (hasil.stdout.strip().splitlines() or ["|"])[-1].partition("|")
    suara = f"{nama} ({'Indonesia' if budaya == 'id-ID' else budaya or '?'})"
    versi = hashlib.sha256(
        json.dumps({"suara": suara, "kata": kata}, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    info = InfoPaket(versi=versi, suara=suara, klip=klip)
    (folder / NAMA_INDEKS).write_text(
        json.dumps({"versi": versi, "suara": suara, "klip": klip}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return info
