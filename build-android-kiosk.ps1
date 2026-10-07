<#
    Build the Android ticket kiosk APK.

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
    & $gradleWrapper --no-daemon clean assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "Build APK gagal." }
}
finally {
    Pop-Location
}

$apk = Join-Path $PSScriptRoot "android-kiosk\app\build\outputs\apk\debug\app-debug.apk"
if (-not (Test-Path $apk)) { throw "APK tidak ditemukan: $apk" }
$release = Join-Path $PSScriptRoot "dist\AntrianKiosk-1.3.apk"
New-Item -ItemType Directory -Path (Split-Path $release -Parent) -Force | Out-Null
Copy-Item -LiteralPath $apk -Destination $release -Force
Write-Host "Selesai: $release" -ForegroundColor Green
