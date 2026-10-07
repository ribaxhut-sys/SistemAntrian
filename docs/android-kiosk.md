# Anjungan Android

The Android app is a full-screen standing-kiosk client with large touch
targets. It detects the Android display's current orientation and sizes
controls to its available screen space. The existing Windows application
continues to own the database and issue queue numbers. The Android tablet
connects to the Windows server over the same trusted private Wi-Fi network
and prints receipts to a USB thermal printer using ESC/POS.
Ticket content, row order, spacing, font sizes, and separator positions are
provided by the Windows API. Android renders the shared layout as a
monochrome ESC/POS image to follow the Windows 72 mm thermal layout, rather
than printing a separate plain-text design. Small differences can remain
because of printer font rasterization and physical feed calibration.

## Windows server

In the Windows application, open **Server Anjungan Android**. The page
creates a strong API token and shows the computer's local IPv4 address.
Choose **Siapkan Firewall & Jalankan Server**; Windows asks for
Administrator permission once to allow TCP 8765 and UDP 8766 on the Private
network profile. Copy the token shown there into the Android server settings.
Enable **Mulai API otomatis saat aplikasi Windows dibuka** if the API should
start with the Windows application. The detached API process stays active
after the desktop window closes and ends when Windows shuts down. This option
only starts automatically on a computer configured as the PostgreSQL server.
The token and Firewall rules must be set up once first, and the application
must be run under the same Windows user that saved the setting.

In BlueStacks, enter `http://<IPv4-Windows>:8765` manually if automatic
discovery does not find the server. Use the IPv4 address shown in the Windows
page and the token displayed there. Do not use `localhost`: it refers to
BlueStacks itself. Android and Windows must be able to reach each other on
the same trusted private network.

For troubleshooting or when running the API directly from source, the
equivalent commands are:

```powershell
Set-Location D:\SistemAntrian
.\.venv\Scripts\python.exe -m app.main --kios-api
```

For a packaged installation, the API can also be started from PowerShell:

```powershell
.\AntrianCRO.exe --kios-api
```

Do not forward either port from the internet. Keep the server and Android
kiosk on the same trusted LAN; the HTTP connection is not encrypted.

The kiosk API supplies the active service list, live counter/queue status,
registration availability, and ticket issue requests. The Android screen
uses the same standing-totem structure as the Windows kiosk: information
panel, service cards with group navigation, selection confirmation, ticket
result, and the live counter strip. The information panel uses the Windows
kiosk welcome text or cycles the configured image/video files from
`media\kiosk`.

If the tablet loses its connection after requesting a number, use **Ulangi
permintaan tiket**. The APK reuses the same request ID, so the running server
returns the existing ticket instead of issuing a second number.

## Android tablet and USB printer

Install `AntrianKiosk-1.3.apk`, connect the tablet to the same Wi-Fi, and
connect the POS80/IWare IW-J200 II printer using a USB host/OTG adapter. At
first launch the kiosk screen appears without requiring server details.
The kiosk searches the local network automatically. If no server is found,
open the gear icon and tap **Cari** beside the server field, or use **Cari
Server Otomatis** on the screen. Enter the token if it differs from
`bapendacro`. Until a server is found the display stays on its setup message and
shows the ticket-taking workflow preview; actual service choices and ticket
issuance remain unavailable until the server connects.

Service buttons resize to the available kiosk panel height and automatically
shrink their text to fit. If the current service list cannot fit while
preserving a minimum touch target, the list can scroll instead of clipping
buttons. To keep every service visible without scrolling, organize many
services into groups and keep each level to a few choices.

Use **Pengaturan Server > Uji terbitkan & cetak** to try the ticket flow
independently of the server. After confirmation, the kiosk shows and prints
a sample marked `UJI-001`. This is a local simulation: it does not call the
server, create a queue number, save a database record, or consume an
official number. The first test may prompt for Android USB permission.

The printer is detected automatically whenever a print is requested. In
server settings, **Deteksi printer USB** checks it without printing. Android
does not need a separate driver for compatible ESC/POS USB printers; connect
the powered printer through a supported USB host/OTG port. If it is not
detected, check OTG support, cable, power, and USB permission. The APK supports
Android 7.0 (API 24) and newer. USB host is optional for installation and
screen preview, but the display must support USB host/OTG to print.
Android's raw USB printing requires a
printer interface with a bulk OUT endpoint and ESC/POS support. Confirm the
specific tablet, OTG adapter, printer cable, and paper feed with a physical
test before leaving the kiosk unattended. If printing fails, the issued
number remains valid and is shown on screen.

If Android reports **“There was a problem parsing the package”**, first
copy the APK again and confirm the file is complete. Check the display's
Android version under **Settings > About**; Android versions older than 7.0
cannot install this APK. The Maxtor MDDW-55DS hardware has not yet been
physically tested with this build.

## Build the APK

Install Android Studio (including Android SDK Platform 35) and JDK 17, then
run from the repository root:

```powershell
.\build-android-kiosk.ps1
```

The generated APK is `dist\AntrianKiosk-1.3.apk`.
