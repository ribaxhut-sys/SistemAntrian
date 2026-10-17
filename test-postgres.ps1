<#
    Jalankan seluruh test terhadap PostgreSQL.

        .\test-postgres.ps1
        .\test-postgres.ps1 tests\test_queue_numbering.py -v

    Semua test wajib memakai PostgreSQL `antrian_uji`. Penjaga di conftest
    menolak nama database lain sebelum fixture sempat menghapus schema.

    Secara bawaan URL dibaca dari ~/.antrian-uji-db. Docker lama tetap dapat
    dipakai hanya bila containernya juga menyediakan database `antrian_uji`.
#>

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs = @("tests", "-q")
)

# JANGAN "Stop": pytest dan docker menulis keterangan biasa ke stderr, dan
# Windows PowerShell 5.1 memperlakukan setiap barisnya sebagai error yang
# menghentikan skrip. Keberhasilan diperiksa lewat $LASTEXITCODE.
$ErrorActionPreference = "Continue"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment belum dibuat. Jalankan: py -3.13 -m venv .venv"
}

$berkasUrl = Join-Path $HOME ".antrian-uji-db"
if (-not (Test-Path $berkasUrl)) {
    throw "Berkas ~/.antrian-uji-db tidak ditemukan."
}
$env:ANTRIAN_DB_URL = (Get-Content $berkasUrl -Raw).Trim()
Write-Host "==> Menjalankan test pada PostgreSQL antrian_uji" -ForegroundColor Cyan

& $python -m pytest @PytestArgs
$hasil = $LASTEXITCODE

Remove-Item Env:\ANTRIAN_DB_URL

if ($hasil -ne 0) {
    Write-Host ""
    Write-Host "Test GAGAL di PostgreSQL." -ForegroundColor Red
    exit $hasil
}

Write-Host ""
Write-Host "Seluruh test lolos di PostgreSQL." -ForegroundColor Green
