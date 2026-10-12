# Sekali jalan: pasang paket, jalankan tes, build APK. Hasil lengkap di logs\periksa-dan-build.log
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$log = Join-Path $PSScriptRoot "logs\periksa-dan-build.log"
New-Item -ItemType Directory -Path (Split-Path $log) -Force | Out-Null
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Set-Content -LiteralPath $log -Encoding UTF8
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$hasil = [ordered]@{}

function Langkah($nama, [scriptblock]$kerja) {
    Write-Host "`n=== $nama ===" -ForegroundColor Cyan
    "`n=== $nama ===" | Add-Content -LiteralPath $log -Encoding UTF8
    try {
        & $kerja 2>&1 | ForEach-Object { $baris = "$_"; Write-Host $baris; Add-Content -LiteralPath $log -Value $baris -Encoding UTF8 }
        $ok = ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE)
    } catch {
        $baris = "GAGAL: $($_.Exception.Message)"; Write-Host $baris -ForegroundColor Red; Add-Content -LiteralPath $log -Value $baris -Encoding UTF8
        $ok = $false
    }
    $script:hasil[$nama] = if ($ok) { "OK" } else { "GAGAL (kode $LASTEXITCODE)" }
}

Langkah "pip install" { & $py -m pip install -r requirements.txt --disable-pip-version-check }
Langkah "pytest" { & $py -m pytest -q -p no:cacheprovider }
Langkah "build APK" { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "build-android-kiosk.ps1") }

Write-Host "`n=== RINGKASAN ===" -ForegroundColor Cyan; Add-Content -LiteralPath $log -Value "`n=== RINGKASAN ===" -Encoding UTF8
foreach ($k in $hasil.Keys) { $baris = "{0,-12} {1}" -f $k, $hasil[$k]; Write-Host $baris; Add-Content -LiteralPath $log -Value $baris -Encoding UTF8 }
Write-Host "`nLog lengkap: $log" -ForegroundColor Green
Read-Host "Tekan Enter untuk menutup"
