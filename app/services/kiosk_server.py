"""
Layanan API anjungan di komputer SERVER: token, Firewall, Task Scheduler.

Anjungan Android hanya mengambil nomor, dan nomor hanya boleh diterbitkan
oleh pemilik database. Karena itu API ini adalah bagian dari peran server,
bukan fitur anjungan: ia berjalan di komputer yang PostgreSQL-nya lokal,
dan tablet hanya menyambung ke sana.

API didaftarkan sebagai tugas Task Scheduler yang berjalan saat Windows
menyala, di bawah akun SYSTEM. Alasannya operasional: server di kantor
dinyalakan pagi hari oleh siapa saja, dan anjungan harus sudah bisa
menerbitkan nomor sebelum ada yang sempat membuka aplikasi lalu masuk.
Aplikasi yang dibuka tetap memeriksa dan menyalakan API sebagai cadangan.

Token disimpan sebagai BERKAS di folder database, bukan di registry
pengguna. Akun SYSTEM tidak dapat membaca HKCU milik petugas, sehingga
token di registry membuat tugas saat Windows menyala tidak pernah bisa
mulai. Token lama di registry tetap dibaca, supaya tablet yang sudah
diatur tidak perlu diatur ulang.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("antrian.kiosk_server")

NAMA_NILAI_API_OTOMATIS = "ANTRIAN_KIOS_API_AUTO_START"
NAMA_BERKAS_TOKEN = "anjungan-token.txt"
NAMA_TUGAS = "AntrianCRO API Anjungan"
PANJANG_TOKEN_MINIMAL = 8
PORT_BAWAAN = 8765

#: SYSTEM dan Administrators penuh; pengguna yang masuk boleh membaca dan
#: MENJALANKAN tugas ini. Tanpa izin jalankan, aplikasi yang dibuka petugas
#: biasa tidak dapat menyalakan ulang API yang berhenti, dan akan
#: menjalankan salinan kedua di bawah akunnya sendiri.
SDDL_TUGAS = "D:(A;;FA;;;SY)(A;;FA;;;BA)(A;;GRGX;;;AU)"


def token_baru() -> str:
    """Buat token acak yang cukup kuat untuk dipakai pada jaringan lokal."""
    return secrets.token_urlsafe(48)


def _db_path_aktif() -> Path:
    from app.core.config import get_config

    return get_config().db_path


def path_berkas_token(db_path: Path | None = None) -> Path:
    """Letak token: folder database, bersebelahan dengan mesin.json."""
    db_path = _db_path_aktif() if db_path is None else db_path
    return Path(db_path).expanduser().resolve().parent / NAMA_BERKAS_TOKEN


def simpan_token(token: str, db_path: Path | None = None) -> None:
    """Simpan token ke berkas. Ditulis lewat berkas sementara lalu diganti."""
    token = token.strip()
    if len(token) < PANJANG_TOKEN_MINIMAL:
        raise ValueError(
            f"Token API harus minimal {PANJANG_TOKEN_MINIMAL} karakter."
        )
    path = path_berkas_token(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sementara = path.with_suffix(path.suffix + ".tmp")
    sementara.write_text(token + "\n", encoding="utf-8")
    sementara.replace(path)
    os.environ["ANTRIAN_KIOS_API_TOKEN"] = token


def muat_token_pengguna() -> str:
    """Token lama di registry pengguna Windows. Hanya dibaca, tidak ditulis."""
    try:
        import winreg
    except ImportError:
        return ""

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            nilai, _ = winreg.QueryValueEx(key, "ANTRIAN_KIOS_API_TOKEN")
    except OSError:
        return ""
    return str(nilai).strip()


def muat_token(db_path: Path | None = None) -> str:
    """
    Token yang berlaku: environment, lalu berkas, lalu registry lama.

    Environment tetap paling kuat, sama seperti ANTRIAN_DB_URL mengalahkan
    mesin.json, supaya pemasangan yang sudah memakai setx tidak berubah.
    """
    token = os.environ.get("ANTRIAN_KIOS_API_TOKEN", "").strip()
    if token:
        return token
    try:
        token = path_berkas_token(db_path).read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    return token or muat_token_pengguna()


def pastikan_berkas_token() -> str:
    """
    Pastikan token yang berlaku tertulis di berkas, lalu kembalikan token itu.

    Tugas Task Scheduler berjalan sebagai SYSTEM dan HANYA membaca berkas:
    environment dan registry milik akun petugas tidak terlihat olehnya.
    Token yang datang dari `setx` lama tampak sah di layar Layanan Anjungan,
    tetapi API yang dinyalakan Windows berhenti dengan "token belum
    disiapkan". Token baru dibuat bila belum ada sama sekali.
    """
    token = muat_token()
    try:
        tertulis = path_berkas_token().read_text(encoding="utf-8").strip()
    except OSError:
        tertulis = ""
    if len(token) < PANJANG_TOKEN_MINIMAL:
        token = token_baru()
    if tertulis != token:
        simpan_token(token)
    return token


def muat_api_otomatis() -> bool:
    """
    Apakah aplikasi menyalakan API saat dibuka. Bawaannya YA.

    Hanya mati bila petugas mematikannya secara tegas. Sebelumnya bawaannya
    mati, dan server yang lupa dicentang membuat anjungan tidak tersambung
    tanpa satu pesan pun di log.
    """
    try:
        import winreg
    except ImportError:
        return True

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            nilai, _ = winreg.QueryValueEx(key, NAMA_NILAI_API_OTOMATIS)
    except OSError:
        return True
    return not (nilai == 0 or str(nilai).strip().lower() in {"0", "false", "no", "off"})


def simpan_api_otomatis(aktif: bool) -> None:
    """Simpan pilihan mulai API otomatis pada profil pengguna Windows."""
    try:
        import winreg
    except ImportError as exc:
        raise RuntimeError("Pengaturan ini hanya tersedia di Windows.") from exc

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        winreg.SetValueEx(
            key, NAMA_NILAI_API_OTOMATIS, 0, winreg.REG_DWORD, int(aktif)
        )


def komputer_server() -> bool:
    """
    Apakah komputer ini pemilik database, satu-satunya tempat API berjalan.

    Sama dengan syarat API otomatis di app.main: peran SERVER dan
    PostgreSQL. Komputer loket, televisi, dan anjungan Windows tidak
    pernah menjalankan API, sehingga juga tidak diberi halamannya.
    """
    from app.core.config import get_config
    from app.core.mesin import SERVER, muat_pengaturan

    config = get_config()
    if config.dialect != "postgresql":
        return False
    return muat_pengaturan(config.db_path).peran == SERVER


def port_api() -> int:
    return int(os.environ.get("ANTRIAN_KIOS_API_PORT", str(PORT_BAWAAN)))


def perintah_api() -> tuple[str, list[str]]:
    """Program dan argumen untuk menjalankan API, dari .exe maupun source."""
    if getattr(sys, "frozen", False):
        return sys.executable, ["--kios-api"]
    return sys.executable, ["-m", "app.main", "--kios-api"]


#: Tanpa ini setiap pemeriksaan status memunculkan jendela PowerShell hitam
#: sekilas di depan petugas — dan pemeriksaannya berjalan berkala.
_TANPA_JENDELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _jalankan_powershell(script: str, *, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        creationflags=_TANPA_JENDELA,
    )


# Aturan berlaku di semua profil jaringan, tetapi hanya untuk alamat di
# subnet lokal. Dulu hanya profil Private: setiap kali Wi-Fi atau router
# berganti, Windows mencatat jaringan barunya Public dan tablet terblokir
# sampai seseorang dengan hak Administrator mengubah profilnya. Batas
# LocalSubnet tetap menutup port dari luar jaringan kantor.
_SKRIP_FIREWALL_CEK = r"""
$ErrorActionPreference = 'Stop'
$rules = @(
    @{ Name = 'Antrian CRO Kiosk API'; Protocol = 'TCP'; Port = '8765' },
    @{ Name = 'Antrian CRO Kiosk Discovery'; Protocol = 'UDP'; Port = '8766' }
)
foreach ($item in $rules) {
    $rule = Get-NetFirewallRule -DisplayName $item.Name -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' `
                -and $_.Action -eq 'Allow' `
                -and $_.Profile.ToString() -eq 'Any'
        } | Select-Object -First 1
    if ($null -eq $rule) { exit 1 }
    $filter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
    if ($filter.Protocol -ne $item.Protocol `
        -or $filter.LocalPort -notcontains $item.Port) { exit 1 }
    $alamat = Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $rule
    if (@($alamat.RemoteAddress) -notcontains 'LocalSubnet') { exit 1 }
}
Write-Output 'OK'
"""

_SKRIP_FIREWALL_PASANG = r"""
$rules = @(
    @{ Name = 'Antrian CRO Kiosk API'; Protocol = 'TCP'; Port = '8765' },
    @{ Name = 'Antrian CRO Kiosk Discovery'; Protocol = 'UDP'; Port = '8766' }
)
foreach ($item in $rules) {
    $rule = Get-NetFirewallRule -DisplayName $item.Name -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $rule) {
        New-NetFirewallRule -DisplayName $item.Name -Direction Inbound `
            -Action Allow -Protocol $item.Protocol -LocalPort $item.Port `
            -Profile Any -RemoteAddress LocalSubnet | Out-Null
    } else {
        Set-NetFirewallRule -InputObject $rule -Enabled True -Direction Inbound `
            -Action Allow -Profile Any -RemoteAddress LocalSubnet
        $rule | Get-NetFirewallPortFilter |
            Set-NetFirewallPortFilter -Protocol $item.Protocol -LocalPort $item.Port
    }
}
"""


def _firewall_sudah_siap() -> bool:
    """Periksa dulu apakah aturan yang diperlukan sudah berlaku."""
    try:
        result = _jalankan_powershell(_SKRIP_FIREWALL_CEK)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and (result.stdout or "").strip() == "OK"


def _ps_kutip(teks: str) -> str:
    """Kutip tunggal PowerShell: satu-satunya karakter khusus adalah '."""
    return "'" + teks.replace("'", "''") + "'"


#: Selang pemeriksa berkala tugas API, dalam menit.
MENIT_JAGA_API = 5


def _skrip_tugas_pasang(program: str, argumen: list[str], folder_kerja: str) -> str:
    """
    Daftarkan ulang tugas API lalu nyalakan.

    - Pemicu saat Windows menyala, ditunda 30 detik supaya layanan
      PostgreSQL sudah menerima sambungan.
    - Batas waktu eksekusi dimatikan: bawaan Task Scheduler membunuh tugas
      sesudah 72 jam, dan server kantor bisa menyala berminggu-minggu.
    - Dinyalakan ulang tiap menit bila gagal DIMULAI.
    - Pemicu kedua berulang tiap MENIT_JAGA_API menit tanpa batas. Selama
      API hidup pemicu itu diabaikan (MultipleInstances IgnoreNew); bila
      API berhenti di tengah jalan, pemicu berikutnya menyalakannya lagi.
      Tanpa ini Task Scheduler tidak pernah menyalakan ulang proses yang
      keluar sesudah berjalan — "RestartCount" hanya berlaku bila tugas
      gagal dimulai — dan API tetap mati sampai Windows dinyalakan ulang.
    """
    argumen_teks = " ".join(
        f'"{arg}"' if " " in arg else arg for arg in argumen
    )
    return f"""
$nama = {_ps_kutip(NAMA_TUGAS)}
Stop-ScheduledTask -TaskName $nama -ErrorAction SilentlyContinue
$aksi = New-ScheduledTaskAction -Execute {_ps_kutip(program)} `
    -Argument {_ps_kutip(argumen_teks)} -WorkingDirectory {_ps_kutip(folder_kerja)}
$pemicu = New-ScheduledTaskTrigger -AtStartup
$pemicu.Delay = 'PT30S'
$jaga = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes {MENIT_JAGA_API})
$pelaku = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$setelan = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $nama -Action $aksi -Trigger @($pemicu, $jaga) `
    -Principal $pelaku -Settings $setelan -Force | Out-Null
try {{
    $layanan = New-Object -ComObject 'Schedule.Service'
    $layanan.Connect()
    $layanan.GetFolder('\\').GetTask($nama).SetSecurityDescriptor({_ps_kutip(SDDL_TUGAS)}, 0)
}} catch {{ }}
Start-ScheduledTask -TaskName $nama
"""


_SKRIP_TUGAS_HAPUS = f"""
$nama = {_ps_kutip(NAMA_TUGAS)}
Stop-ScheduledTask -TaskName $nama -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $nama -Confirm:$false -ErrorAction SilentlyContinue
"""


_SKRIP_TUGAS_MULAI_ULANG = f"""
$nama = {_ps_kutip(NAMA_TUGAS)}
$tugas = Get-ScheduledTask -TaskName $nama -ErrorAction SilentlyContinue
if ($null -eq $tugas) {{
    throw "Tugas '$nama' belum terpasang. Tekan Pasang & nyalakan terlebih dahulu."
}}
Stop-ScheduledTask -TaskName $nama -ErrorAction SilentlyContinue
$batas = (Get-Date).AddSeconds(15)
while ((Get-ScheduledTask -TaskName $nama).State -eq 'Running') {{
    if ((Get-Date) -ge $batas) {{
        throw "API belum berhenti setelah 15 detik."
    }}
    Start-Sleep -Milliseconds 250
}}
Start-ScheduledTask -TaskName $nama
"""


def _jalankan_terangkat(script: str, *, pesan_gagal: str, timeout: int = 120) -> None:
    """Jalankan skrip PowerShell dengan hak Administrator (satu dialog UAC)."""
    script = "$ErrorActionPreference = 'Stop'\n" + script
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    elevated_command = (
        "$ErrorActionPreference = 'Stop'; "
        # Dialog UAC tetap muncul (memang harus); jendela PowerShell yang
        # diangkat tidak.
        "$process = Start-Process -FilePath 'powershell.exe' -Verb RunAs "
        "-WindowStyle Hidden -Wait -PassThru -ErrorAction Stop "
        f"-ArgumentList @('-NoProfile', '-EncodedCommand', '{encoded_script}'); "
        "exit $process.ExitCode"
    )
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                elevated_command,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            creationflags=_TANPA_JENDELA,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Permintaan izin Administrator melewati batas waktu.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or pesan_gagal)


def siapkan_firewall() -> None:
    """Izinkan API TCP dan pencarian UDP dari subnet lokal, dengan UAC."""
    if _firewall_sudah_siap():
        return
    _jalankan_terangkat(
        _SKRIP_FIREWALL_PASANG,
        pesan_gagal="Izin Administrator ditolak atau aturan Firewall gagal dibuat.",
    )


def pasang_layanan_api(folder_kerja: Path) -> None:
    """
    Firewall dan tugas Task Scheduler sekaligus, dengan satu dialog UAC.

    Selalu didaftarkan ulang, bukan hanya bila belum ada: menekan tombol
    ini juga cara memperbarui tugas sesudah aplikasi dipindah, dan cara
    menyalakan ulang API sesudah token diganti.
    """
    # Sebelum tugasnya didaftarkan: tugas yang menyala tanpa berkas token
    # langsung berhenti, dan Windows hanya mencatat kode keluar 2.
    pastikan_berkas_token()
    program, argumen = perintah_api()
    _jalankan_terangkat(
        _SKRIP_FIREWALL_PASANG
        + _skrip_tugas_pasang(program, argumen, str(folder_kerja)),
        pesan_gagal=(
            "Izin Administrator ditolak, atau Firewall dan Task Scheduler "
            "gagal diatur."
        ),
    )
    logger.info("Tugas Task Scheduler '%s' dipasang: %s %s", NAMA_TUGAS, program, argumen)


def hapus_layanan_api() -> None:
    """Hentikan dan hapus tugas Task Scheduler. Aturan Firewall dibiarkan."""
    _jalankan_terangkat(
        _SKRIP_TUGAS_HAPUS,
        pesan_gagal="Izin Administrator ditolak atau tugas gagal dihapus.",
    )
    logger.info("Tugas Task Scheduler '%s' dihapus", NAMA_TUGAS)


def mulai_ulang_layanan_api() -> None:
    """Hentikan proses API aktif dan jalankan lagi tugas API yang terpasang."""
    _jalankan_terangkat(
        _SKRIP_TUGAS_MULAI_ULANG,
        pesan_gagal="Izin Administrator ditolak atau API gagal dimulai ulang.",
    )
    logger.info("Tugas Task Scheduler '%s' dimulai ulang", NAMA_TUGAS)


def jadwalkan_mulai_ulang_layanan_api() -> None:
    """
    Jadwalkan restart dari proses API setelah respons HTTP terkirim.

    Hanya bila proses API ini memang dijalankan tugas Task Scheduler. API
    yang dinyalakan aplikasi petugas sendiri (cadangan bila tugasnya gagal
    dinyalakan) tidak terhenti oleh Stop-ScheduledTask, dan tugas yang lalu
    dinyalakan tidak dapat membuka port yang masih dipakainya — tablet akan
    menerima "berhasil" padahal tidak ada yang dimulai ulang.
    """
    try:
        hasil = _jalankan_powershell(
            f"(Get-ScheduledTask -TaskName {_ps_kutip(NAMA_TUGAS)} "
            "-ErrorAction SilentlyContinue).State"
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Keadaan tugas API tidak dapat dibaca.") from exc
    keadaan = (hasil.stdout or "").strip()
    if not keadaan:
        raise RuntimeError("Tugas API belum terpasang di Task Scheduler.")
    if keadaan != "Running":
        raise RuntimeError(
            "API ini tidak dijalankan oleh Task Scheduler. Mulai ulang dari "
            "Layanan Anjungan di komputer server."
        )
    # Jeda dua detik memberi waktu jawaban HTTP sampai ke tablet sebelum
    # proses ini dihentikan.
    script = (
        "$ErrorActionPreference = 'Stop'\nStart-Sleep -Seconds 2\n"
        + _SKRIP_TUGAS_MULAI_ULANG
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
             "Bypass", "-EncodedCommand", encoded],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, close_fds=True,
        )
    except OSError as exc:
        raise RuntimeError("Restart API tidak dapat dijadwalkan.") from exc
    logger.warning("Restart API anjungan dijadwalkan dari endpoint API")


@dataclass(frozen=True)
class StatusTugas:
    """Keadaan tugas Task Scheduler sebagaimana terbaca tanpa hak Administrator."""

    #: True terdaftar, False tidak ada, None tidak dapat diperiksa.
    terdaftar: bool | None
    program: str = ""
    argumen: str = ""
    #: Punya pemicu berulang yang menyalakan lagi API yang berhenti.
    #: Tugas yang dipasang versi lama belum memilikinya.
    berjaga: bool = False

    def cocok_dengan(self, program: str, argumen: list[str]) -> bool:
        """Apakah tugas menunjuk aplikasi yang sedang berjalan ini."""
        if not self.terdaftar:
            return False
        return (
            os.path.normcase(os.path.normpath(self.program))
            == os.path.normcase(os.path.normpath(program))
            and self.argumen.split() == [a.strip('"') for a in argumen]
        )


def status_tugas_api() -> StatusTugas:
    script = (
        f"$t = Get-ScheduledTask -TaskName {_ps_kutip(NAMA_TUGAS)} "
        "-ErrorAction SilentlyContinue\n"
        "if ($null -eq $t) { Write-Output 'TIDAK-ADA'; exit 0 }\n"
        "$a = $t.Actions | Select-Object -First 1\n"
        "Write-Output ('ADA|' + $a.Execute + '|' + $a.Arguments)\n"
        "$j = @($t.Triggers | Where-Object { $_.Repetition.Interval }).Count\n"
        "Write-Output ('JAGA|' + $j)\n"
    )
    try:
        result = _jalankan_powershell(script)
    except (OSError, subprocess.TimeoutExpired):
        return StatusTugas(terdaftar=None)
    keluaran = (result.stdout or "").strip()
    if result.returncode != 0 or not keluaran:
        return StatusTugas(terdaftar=None)
    if keluaran == "TIDAK-ADA":
        return StatusTugas(terdaftar=False)
    baris = keluaran.splitlines()
    _, program, argumen = (baris[0].split("|", 2) + ["", ""])[:3]
    berjaga = any(
        b.startswith("JAGA|") and b[5:].strip() not in {"", "0"} for b in baris[1:]
    )
    return StatusTugas(
        terdaftar=True, program=program, argumen=argumen.strip(), berjaga=berjaga
    )


def _nyalakan_tugas() -> bool:
    try:
        result = _jalankan_powershell(
            f"Start-ScheduledTask -TaskName {_ps_kutip(NAMA_TUGAS)}"
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def api_sudah_berjalan(port: int = PORT_BAWAAN) -> bool:
    """Periksa health API lokal agar startup tidak membuat proses ganda."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=1
        ) as response:
            return response.status == 200 and response.read(256) == b'{"status":"ok"}'
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def mulai_api_otomatis(
    base_dir: Path,
    log_dir: Path,
    *,
    token: str | None = None,
    lingkungan: dict[str, str] | None = None,
) -> bool:
    """
    Pastikan API berjalan saat aplikasi server dibuka.

    Urutannya: yang sudah berjalan dibiarkan; tugas Task Scheduler
    dinyalakan bila ada; bila tidak ada, API dijalankan sebagai proses
    terpisah di bawah akun petugas. Setiap alasan berhenti dicatat, karena
    anjungan yang tidak tersambung tanpa jejak di log adalah keluhan yang
    tidak dapat ditelusuri siapa pun.
    """
    if not muat_api_otomatis():
        logger.info("API anjungan tidak dinyalakan: dimatikan di Layanan Anjungan.")
        return False
    token_dari_pemanggil = token
    token = (muat_token() if token is None else token).strip()
    if len(token) < PANJANG_TOKEN_MINIMAL:
        logger.warning(
            "API anjungan tidak dinyalakan: token belum disiapkan. "
            "Buka Layanan Anjungan pada komputer server."
        )
        return False

    port = port_api()
    if api_sudah_berjalan(port):
        logger.info("API anjungan sudah berjalan di port %s.", port)
        return True

    status = status_tugas_api()
    if status.terdaftar and token_dari_pemanggil is None:
        # Tugas berjalan sebagai SYSTEM dan hanya membaca berkas token.
        # Token dari `setx` lama tampak sah di sini, tetapi tugas yang
        # dinyalakan tanpa berkasnya langsung berhenti ("token belum
        # disiapkan"). Menulis berkas tidak butuh hak Administrator.
        try:
            pastikan_berkas_token()
        except (OSError, ValueError):
            logger.warning("Berkas token API anjungan gagal ditulis", exc_info=True)
    if status.terdaftar and _nyalakan_tugas():
        logger.info("API anjungan dinyalakan lewat Task Scheduler.")
        return True

    if not _firewall_sudah_siap():
        logger.warning(
            "API anjungan tidak dinyalakan: aturan Firewall port %s belum ada. "
            "Tekan Pasang di Layanan Anjungan.",
            port,
        )
        return False

    child_environment = dict(os.environ if lingkungan is None else lingkungan)
    child_environment["ANTRIAN_KIOS_API_TOKEN"] = token
    program, argumen = perintah_api()

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "kiosk-api.log"
        creation_flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        with log_path.open("ab") as output:
            subprocess.Popen(
                [program, *argumen],
                cwd=str(base_dir),
                env=child_environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                close_fds=True,
                creationflags=creation_flags,
            )
    except OSError as exc:
        logger.warning("API anjungan gagal dijalankan: %s", exc)
        return False
    logger.info("API anjungan dijalankan sebagai proses terpisah (tanpa Task Scheduler).")
    return True
