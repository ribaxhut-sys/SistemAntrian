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

## Server Windows

API anjungan adalah bagian dari komputer **server**: ia berjalan di komputer
yang memegang database PostgreSQL, dan anjungan Android hanya klien yang
menyambung ke sana. Menu **Layanan Anjungan** karena itu hanya muncul di
komputer yang perannya server.

1. Masuk sebagai Administrator, buka **Layanan Anjungan**.
2. Tekan **Pasang & nyalakan** dan setujui UAC. Satu izin itu membuka
   Firewall (TCP 8765, UDP 8766, profil Private) dan mendaftarkan tugas
   Task Scheduler `AntrianCRO API Anjungan`.
3. Salin alamat server dan token ke tablet.

Tugas Task Scheduler berjalan di bawah akun SYSTEM, 30 detik setelah Windows
menyala, tanpa batas waktu, dan dinyalakan ulang tiap menit bila berhenti.
Jadi anjungan sudah dapat mengambil nomor walaupun belum ada yang membuka
aplikasi di server. Saat aplikasi server dibuka, ia memeriksa API dan
menyalakannya bila mati (dapat dimatikan lewat centang di halaman itu).

Token disimpan di `data\anjungan-token.txt`, bersebelahan dengan
`mesin.json`, supaya dapat dibaca akun SYSTEM. Token lama di registry
pengguna tetap dibaca. Sesudah **Buat token baru**, tekan **Pasang ulang &
nyalakan ulang**, lalu isi token baru di setiap tablet.

Bila aplikasi server dipindah (misalnya dari source ke `.exe`), status Task
Scheduler menunjukkan "Menunjuk lokasi lain"; tekan **Pasang ulang**.
Variabel lingkungan yang dipasang dengan `setx` untuk satu pengguna (misalnya
`ANTRIAN_DB_URL`) TIDAK terbaca oleh akun SYSTEM; pakai `mesin.json`.

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

Anjungan Android hanya mengambil nomor. API memberinya daftar layanan aktif,
status pendaftaran (buka/tutup dan jeda antar-pengambilan), media sambutan,
dan penerbitan tiket, ditambah daftar nomor yang menunggu dan nomor yang
sedang dilayani tiap loket. Baris "SEDANG DILAYANI" diletakkan menurut
pengaturan **Posisi baris loket di anjungan**: *Otomatis* menaruhnya di panel
bawah bila panel atas memutar media, dan di panel atas bila tidak ada media
atau semua berkasnya gagal diputar; *Pindahkan ke panel bawah/atas* menetapkan
letaknya; *Sembunyikan* menghilangkan barisnya (anjungan 2.4.3; APK lama
membacanya sebagai Otomatis). Mulai 2.4.3, ⚙ Pengaturan tablet → **Posisi
baris loket di tablet ini** dapat menimpa pilihan server untuk tablet itu
saja; bawaannya *Ikuti pengaturan server*. Panggilan bersuara tetap urusan papan
antrian televisi. Layarnya: panel informasi, kartu layanan
dengan navigasi kelompok, konfirmasi pilihan, dan hasil tiket. The information panel uses the Windows
kiosk welcome text or cycles the image/video files from `media\kiosk`
that are checked in **Daftar putar media**, in that order. A single video
loops without a black gap; a file that fails is skipped, and only when every
file fails does the panel fall back to text (retried every two minutes).
Video sound follows **Suara video anjungan** (off by default).

### Sumber media sambutan (per tablet, mulai APK 2.4.2)

Dipilih di ⚙ **Pengaturan** tablet → **Sumber media sambutan**, berlaku
seketika tanpa tombol Simpan:

* **Daftar putar server (disalin ke tablet)** — bawaan. Tablet mengikuti
  Daftar putar media di server, mengunduh tiap berkas sekali ke penyimpanan
  internalnya, lalu memutar dari salinan itu. Berkas yang belum selesai
  diunduh diputar langsung lewat jaringan. Salinan diunduh ulang bila ukuran
  atau waktu ubah berkas di server berubah (`welcome_media_files` pada
  `GET /v1/kiosk/display`), dan dibuang bila berkasnya keluar dari daftar
  putar. Unduhan yang gagal dicoba lagi setelah dua menit.
* **Folder media di tablet ini** — memutar gambar/video di
  `Android/data/id.sistemantrian.kiosk/files/Media`, urut nama berkas, tanpa
  jaringan sama sekali. Isi folder lewat kabel USB dari komputer, atau
  **Kelola media tablet → Tambah berkas** (pemilih berkas Android). Berkas
  dapat dihapus dari dialog yang sama. Folder kosong = teks sambutan.
  Folder ini ikut terhapus bila aplikasi di-uninstall (pembaruan APK tidak
  menghapusnya).

Lama tampil gambar, suara video, dan posisi baris loket tetap mengikuti
pengaturan server pada kedua sumber.

If the tablet loses its connection after requesting a number, use **Ulangi
permintaan tiket**. The APK reuses the same request ID, so the server returns
the existing ticket instead of issuing a second number.

### Idempotensi `POST /v1/kiosk/tickets`

* Kuncinya pasangan **(`device_id`, `request_id`)**, disimpan di tabel
  `kiosk_ticket_request` dengan constraint unik. `device_id` diambil dari
  token perangkat hasil pasang; untuk token bersama lama, dari header
  `X-Device-Id` (kosong bila tidak dikirim — semua perangkat tanpa
  identitas berbagi satu ruang kunci).
* Kunci disisipkan **dalam transaksi yang sama** dengan baris antriannya.
  Nomor tidak pernah terbit tanpa kuncinya, sehingga permintaan ulang tetap
  menerima nomor yang sama sesudah API dinyalakan ulang.
* Permintaan ulang diperiksa sebelum jeda dan sebelum status pendaftaran:
  nomornya sudah terbit, jadi tetap dijawab 200 dengan tiket yang sama.
* `request_id` yang sama dengan **`category_id` berbeda** ditolak
  **409** ("Permintaan tiket ini sudah dipakai untuk jenis layanan lain").
  Tablet harus membuat `request_id` baru untuk setiap pilihan layanan.
* Permintaan kembar yang tiba bersamaan: yang kalah membentur constraint
  unik, transaksinya batal seluruhnya (nomor urut tidak ikut naik), lalu
  menerima tiket milik yang menang.
* Kunci yang berumur lebih dari 7 hari dibuang saat tiket baru terbit.

### Jeda antar-pengambilan

`kiosk.cooldown_seconds` berlaku **per perangkat** (`device_id`): nomor yang
baru terbit di Tablet A tidak menahan Tablet B. `cooldown_remaining_seconds`
pada `GET /v1/kiosk/display` juga dihitung untuk perangkat penanya. Catatan
jeda disimpan di memori API, bukan di database — jedanya hanya beberapa
detik dan API yang dinyalakan ulang butuh waktu lebih lama dari itu.

## Memasangkan tablet dengan kode

Setiap tablet mendapat token sendiri, sehingga satu tablet yang hilang dapat
dicabut tanpa mengatur ulang yang lain.

1. Di aplikasi server: **Layanan Anjungan → Perangkat → + Tambah perangkat**.
   Muncul kode 6 angka, berlaku 10 menit dan sekali pakai.
2. Di tablet: ⚙ **Pengaturan** → isi alamat server (atau **Cari**), nama
   perangkat, dan kode itu → **Simpan**.
3. Tablet muncul di daftar **Perangkat** beserta waktu terakhir terlihat,
   alamat IP, versi aplikasi, dan hasil cetak terakhir.

**Cabut** menghentikan token tablet itu seketika. Sepuluh kode salah
berturut-turut menghanguskan semua kode yang masih terbuka.

Selama peralihan, token bersama yang lama tetap diterima (centang **Terima
token bersama** di kartu Perangkat). Tablet yang memakainya tetap tercatat
di daftar, ditandai belum dipasangkan. Matikan centang itu setelah semua
tablet dipasangkan dengan kode.

## Pembaruan APK dari server

`build-android-kiosk.ps1` menaruh APK beserta versinya di folder `apk\`
(`anjungan.apk` dan `anjungan.json`), dan `build-installer.ps1` membawanya ke
sebelah `AntrianCRO.exe`. Server membagikannya ke tablet; statusnya terlihat
pada baris **APK anjungan** di Layanan Anjungan.

- Server menetapkan versi minimal (`VERSI_MINIMAL` di
  `app/services/apk_anjungan.py`). Tablet di bawahnya berhenti menerbitkan
  nomor, server menolak tiketnya (HTTP 426), dan layar tablet menawarkan
  **PERBARUI DARI SERVER**.
- Versi baru yang belum wajib hanya diberitahukan di ⚙ Pengaturan tablet.
- Pertama kali, Android meminta izin "Pasang aplikasi tidak dikenal" untuk
  Anjungan Antrian, lalu meminta konfirmasi pemasangan.
- Fitur ini ada mulai versi 1.4: tablet 1.3 dipasang manual sekali.
- Android hanya menerima pembaruan yang ditandatangani kunci yang sama.
  APK debug ditandatangani kunci komputer yang mem-build-nya, jadi selalu
  build dari komputer yang sama.
- Naikkan `versionCode`/`versionName` di `android-kiosk/app/build.gradle`
  setiap rilis, dan naikkan `VERSI_MINIMAL` bila jawaban API berubah.

## Android tablet and USB printer

Install `AntrianKiosk-1.4.apk`, connect the tablet to the same Wi-Fi, and
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

The generated APK is `dist\AntrianKiosk-1.4.apk`.
