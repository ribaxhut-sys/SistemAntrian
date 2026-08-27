<#
    Jalankan seluruh test terhadap PostgreSQL.

        .\test-postgres.ps1
        .\test-postgres.ps1 tests\test_queue_numbering.py -v

    Test harian cukup dijalankan di SQLite karena jauh lebih cepat:

        .\.venv\Scripts\python.exe -m pytest tests -q

    Tetapi SQLite BUKAN yang dipakai di kantor. Suite inilah yang
    membuktikan aplikasi benar pada dialect yang sungguh-sungguh dipakai,
    dan wajib hijau sebelum rilis.

    Membutuhkan Docker: container PostgreSQL dinyalakan otomatis bila belum
    berjalan, dan sengaja DIBIARKAN hidup setelah selesai supaya menjalankan
    ulang tidak perlu menunggu.
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

Write-Host "==> Menyiapkan PostgreSQL" -ForegroundColor Cyan
& docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "Container PostgreSQL gagal dinyalakan." }

# Migration pertama gagal bila server belum siap menerima koneksi. Container
# baru butuh beberapa detik untuk inisialisasi, dan "running" belum berarti
# "siap" — karena itu yang ditunggu status healthy, bukan sekadar hidup.
Write-Host "==> Menunggu PostgreSQL siap" -ForegroundColor Cyan
$batas = 60
for ($i = 0; $i -lt $batas; $i++) {
    $sehat = & docker inspect --format "{{.State.Health.Status}}" antrian-postgres-test 2>$null
    if ($sehat -eq "healthy") { break }
    Start-Sleep -Seconds 1
}
if ($sehat -ne "healthy") { throw "PostgreSQL tidak siap setelah $batas detik." }

$env:ANTRIAN_DB_URL = "postgresql+psycopg://antrian:antrian_test@localhost:55432/antrian_test"
Write-Host "==> Menjalankan test terhadap $($env:ANTRIAN_DB_URL)" -ForegroundColor Cyan

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
Write-Host "Container dibiarkan hidup. Hentikan dengan: docker compose down -v"
