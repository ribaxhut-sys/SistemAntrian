<#
    Build APK anjungan dan APK layar antrian (keduanya panel Android Maxtor).

    Requires JDK 17 and Android SDK Platform 35. Set ANDROID_HOME to the
    SDK directory if Android Studio installed it outside the usual location.
#>

$ErrorActionPreference = "Stop"

$sdk = $env:ANDROID_HOME
if (-not $sdk) { $sdk = $env:ANDROID_SDK_ROOT }
if (-not $sdk) { $sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk" }
if (-not (Test-Path (Join-Path $sdk "platforms\android-35"))) {
    throw "Android SDK Platform 35 tidak ditemukan. Pasang melalui Android Studio atau set ANDROID_HOME."
}

$javaCandidates = @()
if ($env:JAVA_HOME) { $javaCandidates += Join-Path $env:JAVA_HOME "bin\java.exe" }
$javaCandidates += Get-ChildItem "$env:ProgramFiles\Eclipse Adoptium" `
    -Directory -Filter "jdk-17*" -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName "bin\java.exe" }
$javaCandidates += "$env:ProgramFiles\Android\Android Studio\jbr\bin\java.exe"
$javaCandidates += "$env:LOCALAPPDATA\Programs\Android Studio\jbr\bin\java.exe"
$pathJava = Get-Command java.exe -ErrorAction SilentlyContinue
if ($pathJava) { $javaCandidates += $pathJava.Source }

$javaExe = $null
$javaHome = $null
foreach ($candidate in $javaCandidates) {
    if (-not (Test-Path $candidate)) { continue }
    $version = (& $env:ComSpec /d /c "`"$candidate`" -version 2>&1" |
        Select-Object -First 1)
    if ($version -match 'version "(1\.)?17\.') {
        $javaExe = $candidate
        $javaHome = Split-Path (Split-Path $candidate -Parent) -Parent
        break
    }
}
if (-not $javaExe) { throw "JDK 17 tidak ditemukan. Pasang JDK 17 atau Android Studio." }
$env:JAVA_HOME = $javaHome
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:PATH = "$(Split-Path $javaExe -Parent);$env:PATH"

$gradleWrapper = Join-Path $PSScriptRoot "android-kiosk\gradlew.bat"
if (-not (Test-Path $gradleWrapper)) {
    throw "Gradle Wrapper tidak ditemukan di android-kiosk\gradlew.bat."
}

Push-Location (Join-Path $PSScriptRoot "android-kiosk")
try {
    # Gradle/javac menulis peringatan biasa ke stderr. Dengan "Stop", PowerShell 5.1
    # menganggapnya error bila keluaran dialirkan ke pipa; yang menentukan hanya kode keluar.
    $ErrorActionPreference = "Continue"
    & $gradleWrapper --no-daemon clean assembleDebug 2>&1 | ForEach-Object { "$_" }
    $gradleExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($gradleExit -ne 0) { throw "Build APK gagal (kode $gradleExit)." }
}
finally {
    Pop-Location
}

$apk = Join-Path $PSScriptRoot "android-kiosk\app\build\outputs\apk\debug\app-debug.apk"
if (-not (Test-Path $apk)) { throw "APK tidak ditemukan: $apk" }
# Versi dibaca dari build.gradle supaya nama berkas, keterangan untuk server,
# dan isi APK tidak pernah berbeda.
$gradleText = Get-Content (Join-Path $PSScriptRoot "android-kiosk\app\build.gradle") -Raw
if ($gradleText -notmatch 'versionCode\s+(\d+)') { throw "versionCode tidak ditemukan di build.gradle." }
$versionCode = [int]$Matches[1]
if ($gradleText -notmatch 'versionName\s+"([^"]+)"') { throw "versionName tidak ditemukan di build.gradle." }
$versionName = $Matches[1]

$release = Join-Path $PSScriptRoot "dist\AntrianKiosk-$versionName.apk"
New-Item -ItemType Directory -Path (Split-Path $release -Parent) -Force | Out-Null
Copy-Item -LiteralPath $apk -Destination $release -Force

# Salinan yang dibagikan server ke tablet (Layanan Anjungan, pembaruan APK).
$apkFolder = Join-Path $PSScriptRoot "apk"
New-Item -ItemType Directory -Path $apkFolder -Force | Out-Null
Copy-Item -LiteralPath $apk -Destination (Join-Path $apkFolder "anjungan.apk") -Force
@{ version_code = $versionCode; version_name = $versionName } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $apkFolder "anjungan.json") -Encoding UTF8

# Layar antrian: APK terpisah. Pemasangan pertama manual; sesudah itu layar
# memperbarui diri dari salinan di folder apk (Pengaturan layar -> Perbarui).
$layarApk = Join-Path $PSScriptRoot "android-kiosk\layar\build\outputs\apk\debug\layar-debug.apk"
if (-not (Test-Path $layarApk)) { throw "APK layar antrian tidak ditemukan: $layarApk" }
$layarGradle = Get-Content (Join-Path $PSScriptRoot "android-kiosk\layar\build.gradle") -Raw
if ($layarGradle -notmatch 'versionCode\s+(\d+)') { throw "versionCode layar tidak ditemukan." }
$layarCode = [int]$Matches[1]
if ($layarGradle -notmatch 'versionName\s+"([^"]+)"') { throw "versionName layar tidak ditemukan." }
$layarName = $Matches[1]
$layarRelease = Join-Path $PSScriptRoot "dist\AntrianLayar-$layarName.apk"
Copy-Item -LiteralPath $layarApk -Destination $layarRelease -Force
Copy-Item -LiteralPath $layarApk -Destination (Join-Path $apkFolder "layar.apk") -Force
@{ version_code = $layarCode; version_name = $layarName } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $apkFolder "layar.json") -Encoding UTF8

Write-Host "Selesai: $release" -ForegroundColor Green
Write-Host "Selesai: $layarRelease" -ForegroundColor Green
Write-Host "Server membagikan anjungan $versionName (kode $versionCode) dan layar $layarName (kode $layarCode) dari: $apkFolder" -ForegroundColor Green
