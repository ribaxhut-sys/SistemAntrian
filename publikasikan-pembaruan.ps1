<#
.SYNOPSIS
    Menandatangani pembaruan Windows dan menyiapkan folder siap salin ke server.

.DESCRIPTION
    Dijalankan pengembang SETELAH build-installer.ps1. Menanyakan kata sandi
    kunci (lewat alat/tandatangani_pembaruan.py; tidak pernah ditulis), lalu
    mengumpulkan tiga berkas yang harus ada di folder `pembaruan` server ke
    dist\siap-publikasi\<versi>\ dan memeriksa ulang isinya. Tidak
    menyentuh server: salin folder itu (flashdisk atau berbagi jaringan).

.PARAMETER Kunci
    Berkas kunci rahasia. Bawaan: kunci di folder pengembang.

.PARAMETER Catatan
    Berkas teks "apa yang baru" (opsional).
#>
param(
    [string]$Kunci = "D:\sistemantrian kunci\kunci-reset.pem",
    [string]$Catatan = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$dist = Join-Path $PSScriptRoot "dist"
$exe = Join-Path $dist "Pembaruan-AntrianCRO.exe"

if (-not (Test-Path -LiteralPath $exe)) { throw "Belum ada $exe; jalankan build-installer.ps1 dulu." }
if (-not (Test-Path -LiteralPath $Kunci)) { throw "Kunci tidak ditemukan: $Kunci" }

$argumen = @("alat\tandatangani_pembaruan.py", $exe, "--kunci", $Kunci)
if ($Catatan) { $argumen += @("--catatan", $Catatan) }
& $python @argumen
if ($LASTEXITCODE -ne 0) { throw "Penandatanganan gagal (kode $LASTEXITCODE); tidak ada yang disiapkan." }

$versi = (Get-Content (Join-Path $dist "Pembaruan-AntrianCRO.version") -Raw).Trim()
$tujuan = Join-Path $dist "siap-publikasi\$versi"
New-Item -ItemType Directory -Force $tujuan | Out-Null
$berkas = @("Pembaruan-AntrianCRO.exe", "Pembaruan-AntrianCRO.version", "Pembaruan-AntrianCRO.sig")
if ($Catatan) { $berkas += "Pembaruan-AntrianCRO.catatan.txt" }
foreach ($nama in $berkas) {
    Copy-Item -LiteralPath (Join-Path $dist $nama) -Destination $tujuan -Force
}

# Periksa ulang salinannya: tanda tangan harus sah untuk berkas di folder tujuan.
$cek = @"
import hashlib, sys
from pathlib import Path
sys.path.insert(0, r'$PSScriptRoot')
from app.services.pembaruan_windows import info_pembaruan, tanda_sah
info = info_pembaruan(Path(r'$tujuan'))
if info is None or not info.tanda or not tanda_sah(info):
    print('GAGAL: folder tujuan tidak lengkap atau tanda tangan tidak sah'); raise SystemExit(1)
print('OK: versi', info.versi, '| sha256', info.sha256)
"@
& $python -I -c $cek
if ($LASTEXITCODE -ne 0) { throw "Pemeriksaan folder tujuan gagal." }

Write-Host ""
Write-Host "Siap disalin ke folder 'pembaruan' di server:" -ForegroundColor Green
Write-Host "  $tujuan"
Get-ChildItem $tujuan | Select-Object Name, Length | Format-Table -AutoSize
