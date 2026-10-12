[CmdletBinding()]
param(
    [switch]$SkipTests
)

<#
    Build installer Windows Sistem Antrian CRO 1.0.5.

        .\build-installer.ps1

    Requires Inno Setup 6 and the project .venv. The application bundle is
    built in a unique temporary directory so existing build\ and dist\ output
    is left untouched.
#>

$ErrorActionPreference = "Continue"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment belum dibuat. Jalankan: py -3.13 -m venv .venv"
}

$compiler = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source
if (-not $compiler) {
    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $candidate) {
            $compiler = $candidate
            break
        }
    }
}
if (-not $compiler) {
    throw "Inno Setup 6 belum terpasang. Pasang Inno Setup 6, lalu jalankan skrip ini lagi."
}

$stageRoot = Join-Path $env:TEMP "AntrianCRO-installer-$PID"
$bundle = Join-Path $stageRoot "dist\AntrianCRO"
$work = Join-Path $stageRoot "work"
$cleanTest = Join-Path $stageRoot "uji"
$output = Join-Path $PSScriptRoot "dist"
$previousAntrianEnv = @{}

try {
    New-Item -ItemType Directory -Path $stageRoot -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $output -Force -ErrorAction Stop | Out-Null

    Get-ChildItem Env: | Where-Object { $_.Name -like "ANTRIAN_*" } | ForEach-Object {
        $previousAntrianEnv[$_.Name] = $_.Value
        Remove-Item "Env:\$($_.Name)"
    }
    $env:ANTRIAN_DB_PATH = Join-Path $stageRoot "test-data\queue.db"
    $env:ANTRIAN_BACKUP_DIR = Join-Path $stageRoot "test-backup"
    $env:ANTRIAN_LOG_DIR = Join-Path $stageRoot "test-logs"

    Push-Location $PSScriptRoot
    try {
        Write-Host "==> Menyiapkan database sementara untuk callback Qt yang terlambat" -ForegroundColor Cyan
        & $python -m app.main --init-only
        if ($LASTEXITCODE -ne 0) { throw "Database uji sementara gagal disiapkan." }

        if ($SkipTests) {
            Write-Host "==> Test dilewati atas permintaan" -ForegroundColor Yellow
        }
        else {
            Write-Host "==> Menjalankan test" -ForegroundColor Cyan
            & $python -m pytest tests -q
            if ($LASTEXITCODE -ne 0) { throw "Test gagal. Installer tidak dibuat." }
        }

        Write-Host "==> Membangun bundel aplikasi sementara" -ForegroundColor Cyan
        & $python -m PyInstaller --noconfirm --clean `
            --workpath $work `
            --distpath (Join-Path $stageRoot "dist") `
            (Join-Path $PSScriptRoot "AntrianCRO.spec")
        if ($LASTEXITCODE -ne 0) { throw "Build aplikasi gagal." }

        $exe = Join-Path $bundle "AntrianCRO.exe"
        if (-not (Test-Path $exe)) { throw "AntrianCRO.exe tidak ditemukan di hasil build." }

        # Qt6Core.dll wajib memakai icuuc.dll milik Windows. Salinan ICU lain
        # di dalam bundel membuat PySide6.QtWidgets gagal dimuat.
        $icuAsing = Get-ChildItem -Path $bundle -Recurse -Include "icuuc*.dll", "icuin*.dll", "icudt*.dll"
        if ($icuAsing) {
            throw "Bundel berisi DLL ICU yang bentrok dengan Qt: $($icuAsing.FullName -join ', ')"
        }

        # APK anjungan ikut terpasang di sebelah .exe, supaya server hasil
        # installer dapat langsung membagikannya ke tablet.
        $apkSource = Join-Path $PSScriptRoot "apk"
        if (Test-Path (Join-Path $apkSource "anjungan.apk")) {
            Copy-Item -LiteralPath $apkSource -Destination (Join-Path $bundle "apk") -Recurse -Force
            Write-Host "==> APK anjungan ikut dalam installer" -ForegroundColor Cyan
        }
        else {
            Write-Host "==> apk\anjungan.apk belum ada; jalankan build-android-kiosk.ps1 dulu bila tablet perlu diperbarui dari server" -ForegroundColor Yellow
        }

        Write-Host "==> Menguji aplikasi hasil build di folder bersih" -ForegroundColor Cyan
        Copy-Item -LiteralPath $bundle -Destination $cleanTest -Recurse -ErrorAction Stop
        $proses = Start-Process -FilePath (Join-Path $cleanTest "AntrianCRO.exe") `
            -ArgumentList "--init-only" -Wait -PassThru -ErrorAction Stop
        if ($proses.ExitCode -ne 0) {
            $log = Join-Path $cleanTest "logs\app.log"
            if (Test-Path $log) { Get-Content $log -Tail 30 }
            throw "Aplikasi hasil build gagal menyiapkan database."
        }

        Write-Host "==> Membuat installer Windows" -ForegroundColor Cyan
        $env:ANTRIAN_SOURCE_DIR = $bundle
        $env:ANTRIAN_OUTPUT_DIR = $output
        & $compiler (Join-Path $PSScriptRoot "installer.iss")
        if ($LASTEXITCODE -ne 0) { throw "Kompilasi installer gagal." }
    }
    finally {
        Pop-Location
    }
}
finally {
    Get-ChildItem Env: | Where-Object { $_.Name -like "ANTRIAN_*" } | ForEach-Object {
        Remove-Item "Env:\$($_.Name)" -ErrorAction SilentlyContinue
    }
    foreach ($name in $previousAntrianEnv.Keys) {
        Set-Item "Env:\$name" $previousAntrianEnv[$name]
    }
    Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$installer = Join-Path $output "AntrianCRO-Setup-1.0.5.exe"
if (-not (Test-Path $installer)) { throw "Installer tidak ditemukan: $installer" }

Write-Host ""
Write-Host "Selesai: $installer" -ForegroundColor Green
