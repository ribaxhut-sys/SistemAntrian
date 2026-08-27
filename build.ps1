<#
    Bangun AntrianCRO.exe.

        .\build.ps1

    Hasilnya ada di dist\AntrianCRO\. Seluruh folder itulah yang disalin ke
    komputer tujuan, bukan hanya berkas .exe-nya.

    Interpreter .venv dipanggil eksplisit. Memanggil "pyinstaller" langsung
    berisiko memakai Python global yang versinya berbeda dari yang dikunci
    proyek ini (3.13).
#>

# JANGAN diubah menjadi "Stop". pytest dan PyInstaller sama-sama menulis
# keterangan biasa ke stderr, dan Windows PowerShell 5.1 memperlakukan setiap
# baris stderr dari program native sebagai error yang menghentikan skrip —
# build akan gagal padahal tidak ada yang salah. Keberhasilan tiap langkah
# diperiksa lewat $LASTEXITCODE, bukan lewat stderr.
$ErrorActionPreference = "Continue"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment belum dibuat. Jalankan: py -3.13 -m venv .venv"
}

Write-Host "==> Menjalankan test lebih dahulu" -ForegroundColor Cyan
& $python -m pytest tests -q
if ($LASTEXITCODE -ne 0) {
    throw "Test gagal. Build dihentikan agar .exe yang rusak tidak ikut terdistribusi."
}

Write-Host "==> Membersihkan hasil build sebelumnya" -ForegroundColor Cyan
foreach ($folder in @("build", "dist")) {
    $path = Join-Path $PSScriptRoot $folder
    if (Test-Path $path) { Remove-Item -Recurse -Force $path -ErrorAction Stop }
}

Write-Host "==> Membangun AntrianCRO.exe" -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm (Join-Path $PSScriptRoot "AntrianCRO.spec")
if ($LASTEXITCODE -ne 0) { throw "Build gagal." }

$hasil = Join-Path $PSScriptRoot "dist\AntrianCRO\AntrianCRO.exe"
if (-not (Test-Path $hasil)) { throw "Build selesai tetapi AntrianCRO.exe tidak ditemukan." }

# Wajib. Berkas migration dimuat dari file .py saat runtime, sehingga
# dependency-nya tidak terlihat oleh analisis import PyInstaller. Kegagalan
# semacam itu HANYA muncul saat .exe dijalankan, bukan saat dibangun — dan
# tanpa pemeriksaan ini akan lolos sampai ke komputer petugas.
Write-Host "==> Memeriksa .exe pada folder bersih" -ForegroundColor Cyan
$uji = Join-Path $env:TEMP "antrian-uji-build"
if (Test-Path $uji) { Remove-Item -Recurse -Force $uji -ErrorAction Stop }
Copy-Item -Recurse (Split-Path $hasil) $uji -ErrorAction Stop

# -Wait wajib. AntrianCRO.exe adalah aplikasi berjendela, dan tanpa -Wait
# PowerShell melanjutkan sebelum prosesnya selesai sehingga exit code-nya
# tidak pernah terbaca.
$proses = Start-Process -FilePath (Join-Path $uji "AntrianCRO.exe") `
    -ArgumentList "--init-only" -Wait -PassThru -ErrorAction Stop
if ($proses.ExitCode -ne 0) {
    $log = Join-Path $uji "logs\app.log"
    if (Test-Path $log) { Get-Content $log -Tail 30 }
    throw ".exe gagal menyiapkan database. Lihat keluaran log di atas."
}
Remove-Item -Recurse -Force $uji

Write-Host ""
Write-Host "Selesai: $hasil" -ForegroundColor Green
Write-Host "Salin seluruh folder dist\AntrianCRO ke komputer tujuan."
