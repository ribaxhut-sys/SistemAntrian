"""Pengaturan token, firewall, dan proses API untuk anjungan Android."""

from __future__ import annotations

import base64
import os
import secrets
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

NAMA_NILAI_API_OTOMATIS = "ANTRIAN_KIOS_API_AUTO_START"


def token_baru() -> str:
    """Buat token acak yang cukup kuat untuk dipakai pada jaringan lokal."""
    return secrets.token_urlsafe(48)


def simpan_token_pengguna(token: str) -> None:
    """Simpan token di environment proses dan profil Windows pengguna."""
    os.environ["ANTRIAN_KIOS_API_TOKEN"] = token
    try:
        import winreg
    except ImportError as exc:
        raise RuntimeError("Penyimpanan token ini hanya tersedia di Windows.") from exc

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        winreg.SetValueEx(key, "ANTRIAN_KIOS_API_TOKEN", 0, winreg.REG_SZ, token)


def muat_token_pengguna() -> str:
    """Baca token API yang disimpan pada profil pengguna Windows."""
    try:
        import winreg
    except ImportError:
        return ""

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            nilai, _ = winreg.QueryValueEx(key, "ANTRIAN_KIOS_API_TOKEN")
    except FileNotFoundError:
        return ""
    return str(nilai).strip()


def muat_api_otomatis() -> bool:
    """Baca pilihan mulai API otomatis dari profil pengguna Windows."""
    try:
        import winreg
    except ImportError:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            nilai, _ = winreg.QueryValueEx(key, NAMA_NILAI_API_OTOMATIS)
    except FileNotFoundError:
        return False
    return nilai == 1 or str(nilai).strip().lower() in {"1", "true", "yes", "on"}


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


def _firewall_sudah_siap() -> bool:
    """Periksa dulu apakah aturan yang diperlukan sudah berlaku."""
    script = r"""
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
                -and $_.Profile.ToString().Contains('Private')
        } | Select-Object -First 1
    if ($null -eq $rule) { exit 1 }
    $filter = Get-NetFirewallPortFilter -AssociatedNetFirewallRule $rule
    if ($filter.Protocol -ne $item.Protocol `
        -or $filter.LocalPort -notcontains $item.Port) { exit 1 }
}
Write-Output 'OK'
"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and (result.stdout or "").strip() == "OK"


def api_sudah_berjalan(port: int = 8765) -> bool:
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
    """Mulai API terpisah sekali, bila token dan Firewall sudah disiapkan."""
    if not muat_api_otomatis():
        return False
    token = (token if token is not None else (
        os.environ.get("ANTRIAN_KIOS_API_TOKEN", "").strip()
        or muat_token_pengguna()
    )).strip()
    if len(token) < 8:
        return False

    port = int(os.environ.get("ANTRIAN_KIOS_API_PORT", "8765"))
    if api_sudah_berjalan(port):
        return True
    if not _firewall_sudah_siap():
        return False

    child_environment = dict(os.environ if lingkungan is None else lingkungan)
    child_environment["ANTRIAN_KIOS_API_TOKEN"] = token
    if getattr(sys, "frozen", False):
        arguments = [sys.executable, "--kios-api"]
    else:
        arguments = [sys.executable, "-m", "app.main", "--kios-api"]

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "kiosk-api.log"
        creation_flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        with log_path.open("ab") as output:
            subprocess.Popen(
                arguments,
                cwd=str(base_dir),
                env=child_environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                close_fds=True,
                creationflags=creation_flags,
            )
    except OSError:
        return False
    return True


def siapkan_firewall() -> None:
    """Izinkan API TCP dan pencarian UDP pada profil Private, dengan UAC."""
    if _firewall_sudah_siap():
        return
    script = r"""
$ErrorActionPreference = 'Stop'
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
            -Profile Private | Out-Null
    } else {
        Set-NetFirewallRule -InputObject $rule -Enabled True -Direction Inbound `
            -Action Allow -Profile Private
        $rule | Get-NetFirewallPortFilter |
            Set-NetFirewallPortFilter -Protocol $item.Protocol -LocalPort $item.Port
    }
}
"""
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    elevated_command = (
        "$ErrorActionPreference = 'Stop'; "
        "$process = Start-Process -FilePath 'powershell.exe' -Verb RunAs "
        "-Wait -PassThru -ErrorAction Stop "
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
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Penyiapan Firewall melewati batas waktu.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if not detail:
            detail = "Izin Administrator ditolak atau aturan Firewall gagal dibuat."
        raise RuntimeError(detail)
