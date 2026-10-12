# Panduan Proyek Sistem Antrian

Panduan ini merangkum fungsi, komponen, instalasi, konfigurasi jaringan,
operasional, backup, dan pengembangan Sistem Antrian CRO. README tetap
menjadi rujukan rinci aturan aplikasi; dokumen khusus di bagian [Dokumentasi
terkait](#dokumentasi-terkait) menjelaskan prosedur tertentu.

## 1. Ringkasan

Sistem Antrian CRO adalah aplikasi Windows untuk mengelola nomor antrean
pelayanan dan survey kepuasan. Aplikasi desktop memakai PySide6. Data berada
di SQLite untuk satu komputer atau PostgreSQL untuk beberapa komputer yang
melayani bersamaan.

APK Android adalah klien anjungan: ia meminta daftar layanan dan menerbitkan
nomor melalui API pada aplikasi Windows. Android tidak mengakses PostgreSQL
secara langsung. Server Windows menyimpan database dan menjadi penghubung
untuk permintaan Android.

```text
PC petugas ───────────────┐
PC loket lain ────────────┼── PostgreSQL di PC server
                          │
BlueStacks / Android ── API di PC server ──┘
                         TCP 8765
```

Untuk jaringan lokal tepercaya:

| Layanan | Protokol dan port | Kegunaan |
|---|---|---|
| PostgreSQL | TCP 5432 | Koneksi aplikasi desktop ke database bersama |
| API anjungan | TCP 8765 | Permintaan data layanan dan tiket dari Android |
| Discovery anjungan | UDP 8766 | Pencarian otomatis server dari Android |

Jangan teruskan port tersebut dari router ke internet. API menggunakan HTTP
lokal tanpa enkripsi; gunakan hanya pada jaringan privat yang tepercaya.
Aplikasi Android hanya mau memakai `http://` ke alamat jaringan lokal;
alamat lain wajib `https://` (lihat [panduan anjungan
Android](android-kiosk.md#http-lokal-dan-https-mulai-anjungan-2424-layar-12)).

## 2. Pilih bentuk pemasangan

### Satu komputer

Gunakan SQLite bawaan aplikasi. Tidak perlu memasang PostgreSQL. Database
berada di `data\queue.db`.

### Beberapa komputer (misalnya 4–6 PC)

Pasang PostgreSQL pada **satu** PC server. Pasang aplikasi Sistem Antrian pada
setiap PC yang memerlukannya dan arahkan semuanya ke database PostgreSQL yang
sama. Jangan menaruh berkas SQLite di folder jaringan untuk dipakai bersama:
SQLite tidak aman untuk penggunaan serentak oleh banyak komputer.

Peran umum:

| Komputer | Peran |
|---|---|
| Satu PC yang selalu aktif | PostgreSQL, aplikasi Sistem Antrian, dan bila dipakai API anjungan |
| PC loket/petugas lainnya | Aplikasi Sistem Antrian sebagai klien PostgreSQL |
| Tablet atau BlueStacks | APK Anjungan Android, tersambung ke API Windows |

Tetapkan alamat IP lokal yang stabil untuk PC server, misalnya melalui DHCP
reservation router. Bila PC server mati, klien tidak dapat melayani antrean
sampai koneksi database pulih.

## 3. Memasang aplikasi Windows

Untuk pengguna akhir, jalankan installer Sistem Antrian Windows. Installer
menyertakan runtime Python dan paket aplikasi; Python tidak perlu dipasang
terpisah. Installer **tidak menyertakan PostgreSQL Server**.

Pada penggunaan pertama:

1. Buka aplikasi dan siapkan database/peran komputer.
2. Login dengan akun awal `admin` / `admin123` bila database baru.
3. Ganti kata sandi awal saat diminta; jangan terus memakai kata sandi bawaan.
4. Buat akun petugas lain sesuai perannya.

Data, log, dan backup disimpan pada folder aplikasi/configurasi yang aktif.
Jangan menghapus folder data saat memperbarui aplikasi. Uninstall aplikasi
tidak dimaksudkan untuk menghapus data kerja.

## 4. Menyiapkan PostgreSQL untuk beberapa PC

### 4.1 Pasang PostgreSQL Server

Unduh installer Windows dari [halaman resmi PostgreSQL untuk
Windows](https://www.postgresql.org/download/windows/), lalu pilih PostgreSQL
17 untuk Windows 64-bit. Installer interaktif EDB menyediakan PostgreSQL
Server dan pgAdmin. Catat kata sandi pengguna administratif `postgres` saat
instalasi; kata sandi itu tidak sama dengan kata sandi aplikasi.

Biarkan port bawaan `5432` jika belum dipakai layanan lain. Pastikan layanan
PostgreSQL berjalan setelah instalasi.

### 4.2 Buat database dan pengguna aplikasi

Pada aplikasi Windows di PC server:

1. Buka dialog **Atur komputer ini** / penyiapan peran database.
2. Pilih **Komputer ini adalah SERVER**.
3. Isi kata sandi yang ingin dipakai oleh pengguna database `antrian`.
4. Tekan **Siapkan database**.
5. Masukkan kata sandi `postgres` yang dibuat ketika memasang PostgreSQL.

Dialog akan membuat atau memperbarui pengguna `antrian` dan membuat database
`antrian` bila belum ada. Kata sandi `postgres` hanya digunakan untuk
penyiapan dan tidak disimpan oleh aplikasi. Setelah siap, koneksi server
menggunakan PostgreSQL lokal pada `127.0.0.1:5432`.

Ketika aplikasi pertama kali tersambung, migration Alembic membuat atau
memperbarui skema tanpa menghapus data lama.

### 4.3 Izinkan PostgreSQL menerima koneksi LAN

PostgreSQL harus mendengarkan pada antarmuka jaringan, bukan hanya loopback.
Pada berkas `postgresql.conf`, atur:

```conf
listen_addresses = '*'
```

Pada `pg_hba.conf`, izinkan hanya subnet kantor yang benar. Contoh bila
jaringan kantor adalah `192.168.1.0/24`:

```conf
host    antrian    antrian    192.168.1.0/24    scram-sha-256
```

Jangan gunakan `0.0.0.0/0` atau metode autentikasi `trust`. Dialog **Siapkan
database** mencoba menambahkan baris untuk subnet lokal pada `pg_hba.conf`.
Jika Windows tidak mengizinkan aplikasi mengubah berkas tersebut, tambahkan
baris di atas secara manual. Setelah mengubah `listen_addresses`, restart
layanan PostgreSQL; setelah mengubah `pg_hba.conf`, muat ulang konfigurasi
atau restart layanan.

Batasi Windows Firewall PostgreSQL ke jaringan kantor dan profil **Private**.
Contoh berikut mengizinkan hanya satu subnet; ganti subnet sesuai jaringan
yang benar:

```powershell
New-NetFirewallRule -DisplayName "Antrian PostgreSQL LAN" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5432 `
  -RemoteAddress 192.168.1.0/24 -Profile Private
```

Pastikan koneksi Windows aktif memang berprofil Private sebelum memakai
aturan tersebut:

```powershell
Get-NetConnectionProfile |
  Format-Table InterfaceAlias, NetworkCategory
```

Jangan ubah jaringan umum menjadi Private tanpa memastikan jaringan itu
tepercaya. Jangan membuka port `5432` ke internet.

### 4.4 Hubungkan komputer petugas

Di tiap PC klien, buka **Atur komputer ini**:

1. Pilih **Komputer ini menyambung ke SERVER**.
2. Tekan **Cari di jaringan** atau masukkan IP lokal server.
3. Masukkan kata sandi pengguna `antrian` yang dibuat di langkah server.
4. Uji koneksi, kemudian simpan.

Bila menggunakan konfigurasi manual/env, bentuk URL adalah:

```text
postgresql+psycopg://antrian:<kata-sandi>@<IP-server>:5432/antrian
```

Hindari menaruh URL berisi kata sandi di tiket, log, tangkapan layar, atau
repository. `ANTRIAN_DB_URL`, bila disetel, mengalahkan konfigurasi pada
berkas `data\mesin.json`. Dokumentasi detail berada di bagian
[Pemasangan Beberapa Loket](../README.md#pemasangan-beberapa-loket-postgresql).

### 4.5 Verifikasi database

Pada setiap komputer, aplikasi harus menampilkan status database PostgreSQL
yang menunjuk host server. Pastikan beberapa PC melihat data layanan,
perubahan panggilan, dan nomor yang sama. Sebelum pemakaian sungguhan,
lakukan uji dua PC menerbitkan nomor hampir bersamaan dan pastikan tidak ada
nomor duplikat. Daftar uji lengkap ada di [uji terima](acceptance-test.md).

## 5. Menyiapkan API anjungan Android

Lakukan ini setelah aplikasi Windows di PC server sudah tersambung ke database
bersama PostgreSQL:

1. Login sebagai Administrator di aplikasi Windows pada PC server. Menu
   **Layanan Anjungan** hanya muncul di PC yang perannya server.
2. Buka **Layanan Anjungan**, tekan **Pasang & nyalakan**, lalu setujui UAC.
   Satu izin itu membuka Firewall (TCP `8765`, UDP `8766`, semua profil jaringan tetapi
   hanya dari subnet lokal)
   dan mendaftarkan tugas Task Scheduler `AntrianCRO API Anjungan` yang
   menyala sendiri setiap kali Windows dinyalakan, walaupun aplikasi belum
   dibuka.
3. Pastikan ketiga status (API, Task Scheduler, Firewall) bertanda Normal.
   Bilah status di bawah jendela juga menampilkan "API anjungan: ● berjalan".
4. Catat alamat server dan token yang ditampilkan.
5. Bila aplikasi server dipindah atau token diganti, tekan **Pasang ulang &
   nyalakan ulang**.
6. Di BlueStacks atau tablet, buka pengaturan server dan isi
   `http://<IP-PC-server>:8765` serta token yang sama.
7. Gunakan **Cari** bila jaringan mendukung broadcast. Jika tidak, isi alamat
   server secara manual.

Alamat server harus menunjuk ke PC Windows, bukan `localhost` dan bukan
alamat database. Jika API berjalan tetapi memakai SQLite lokal, PC lain dan
Android tidak akan melihat antrean PostgreSQL; pastikan status database
Windows menunjukkan host PostgreSQL server sebelum menjalankan anjungan.

Gunakan token acak yang dibuat aplikasi. Jangan memakai token contoh atau
token yang mudah ditebak. Mengganti token mengharuskan konfigurasi token
Android diperbarui. Rincian Android/USB ada di
[panduan anjungan Android](android-kiosk.md).

## 6. Fungsi utama

- **Penerbitan antrean:** nomor berprefix menurut jenis layanan, urut harian,
  dengan pencegahan nomor ganda di database.
- **Pelayanan loket:** pemanggilan, panggil ulang, mulai/lanjutkan layanan,
  selesai, tidak hadir, pembatalan, dan pencatatan riwayat pemanggilan.
- **Layar antrean:** papan ruang tunggu, suara panggilan, serta tampilan yang
  dapat disesuaikan untuk monitor lebar, memanjang, atau tegak.
- **Anjungan Windows dan Android:** pemilihan layanan mandiri dan penerbitan
  tiket. Android meminta nomor melalui API Windows.
- **Survey kepuasan:** rating setelah pelayanan dan ringkasan hasil.
- **Data master dan akun:** cabang, loket, jenis layanan bertingkat, user,
  peran, dan pengaturan aplikasi.
- **Backup dan audit:** pencadangan database, pemulihan, serta pencatatan
  tindakan administratif.
- **Catatan pengaduan:** data identitas berada di tabel terpisah. Batasi akses
  backup dan jangan menaruhnya di folder publik.

Lihat [README](../README.md) untuk aturan bisnis lengkap dan tabel hak akses.

## 7. Keamanan dan batas jaringan

- Tempatkan PostgreSQL dan API hanya di jaringan kantor/pribadi yang
  dikendalikan.
- **Pisahkan jaringan perangkat antrian dari Wi-Fi tamu.** API anjungan
  memakai HTTP biasa dengan token; siapa pun di jaringan yang sama dapat
  menyadap token itu. Bila tablet tersambung lewat Wi-Fi, pakai SSID
  khusus (WPA2/WPA3, sandi tidak dibagikan ke pengunjung) atau VLAN
  tersendiri untuk server, PC loket, televisi, dan tablet. Jangan pernah
  menyambungkan tablet anjungan ke Wi-Fi yang sandinya ditempel untuk
  umum.
- Batasi akses `5432` pada subnet klien yang benar. API `8765` dan
  discovery `8766` dibuka di semua profil jaringan tetapi hanya untuk
  `LocalSubnet`, sehingga Wi-Fi yang tercatat Public tidak memblokir tablet.
  Pemasangan lama (hanya profil Private) diperbarui dengan **Pasang ulang**.
- Jangan membuat port-forwarding router atau membuka layanan ke internet.
- Jangan kirim kata sandi PostgreSQL atau token API melalui chat, log, atau
  repository.
- Buat kata sandi unik untuk `postgres`, `antrian`, dan token API.
- Backup berisi data aplikasi; dalam konfigurasi tertentu juga dapat berisi
  data pengaduan. Lindungi file backup dan simpan salinan di perangkat/media
  lain yang aman.
- Untuk komputer publik, gunakan konfigurasi akun PostgreSQL terbatas yang
  dijelaskan di bagian
  [User PostgreSQL terbatas untuk mesin publik](../README.md#user-postgresql-terbatas-untuk-mesin-publik).

## 8. Backup, pemulihan, dan pemeliharaan

Backup otomatis disimpan sesuai pengaturan aplikasi. Periksa secara berkala
bahwa berkas backup terbentuk dan tidak hanya tersimpan pada disk PC server.
Untuk PostgreSQL, aplikasi memakai `pg_dump` dan `pg_restore`; installer
PostgreSQL memasang alat tersebut pada folder `bin`-nya. Jika aplikasi tidak
menemukannya otomatis, isi pengaturan **Folder perkakas PostgreSQL** dengan
contoh `C:\Program Files\PostgreSQL\17\bin`.

Setiap backup baru disertai berkas checksum `<nama-backup>.sha256` (format
`sha256sum`), yang ikut disalin ke folder salinan kedua dan ikut terhapus
bersama backup-nya oleh retensi. Layar **Backup** menampilkan waktu backup
terakhir yang berhasil; bila percobaan terakhir gagal, penyebabnya tampil
dengan kalimat yang dapat ditindaklanjuti (disk penuh, folder tidak dapat
ditulis, `pg_dump` gagal, dan sebagainya). Catatan ini disimpan di
`backup\.status-backup.json`.

Tombol **Uji Backup** memeriksa backup terpilih tanpa menyentuh database
aktif: checksum dicocokkan, lalu isinya diuji. Untuk SQLite, backup
dipulihkan ke berkas sementara dan diperiksa dengan `PRAGMA
integrity_check`. Untuk PostgreSQL, seluruh isi dump dibaca oleh
`pg_restore` tanpa sambungan ke server; pemulihan ke database sementara
tidak dilakukan karena membutuhkan hak `CREATE DATABASE` yang sengaja tidak
dimiliki user aplikasi. Pemulihan menolak backup yang checksumnya tidak
cocok. Backup lama tanpa checksum tetap dapat diuji dan dipulihkan.

Untuk pemulihan, login sebagai Administrator, buka menu **Backup**, pilih
arsip yang benar, lalu ikuti konfirmasi. Setelah pemulihan, tutup dan buka
kembali aplikasi. Data transaksi setelah tanggal backup akan hilang.
Sebelum operasional, lakukan uji pemulihan pada salinan/lingkungan uji.

**Melindungi backup.** Backup berisi identitas pelapor pengaduan, tetapi
tidak dienkripsi oleh aplikasi: di server ia terletak di sebelah database
aktif, jadi yang dilindungi adalah aksesnya dan salinan yang keluar.

- Folder `backup\` dan `data\` di server: Properties → Security, hanya
  akun admin Windows yang boleh membaca.
- Flashdisk/disk **salinan kedua**: klik kanan drive → *Turn on BitLocker*
  (BitLocker To Go). Simpan *recovery key*-nya di amplop terpisah dari
  server. Flashdisk tetap dapat dibuka di komputer Windows mana pun dengan
  sandinya.
- Bila server berupa PC biasa yang mudah diangkat orang, aktifkan juga
  BitLocker pada disknya.

**Masa simpan identitas pelapor.** Nama, nomor pelanggan, telepon, email,
dan alamat pada lembar pengaduan dikosongkan otomatis setelah 24 bulan
(Pengaturan → Pengaduan; `0` = selamanya). Isi pengaduan tetap disimpan.

Bila server mati di tengah pelayanan, ikuti
[prosedur-darurat.md](prosedur-darurat.md).

## 9. Menjalankan dari source dan pengujian

Persyaratan pengembangan: Windows, Python **3.13**, dan PowerShell.

```powershell
Set-Location D:\SistemAntrian
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m app.main
```

Argumen mesin yang umum:

```powershell
.\.venv\Scripts\python.exe -m app.main --admin
.\.venv\Scripts\python.exe -m app.main --setup
.\.venv\Scripts\python.exe -m app.main --kios-api
```

Jalankan test sebelum perubahan dirilis — di **PostgreSQL**, database uji
yang boleh dikosongkan (bukan `antrian` produksi), dengan folder `bin`
PostgreSQL di `PATH` supaya test backup tidak dilewati:

```powershell
$env:PATH = "C:\Program Files\PostgreSQL\17\bin;$env:PATH"
$env:ANTRIAN_DB_URL = "postgresql+psycopg://postgres:<sandi>@127.0.0.1:5432/antrian_uji"
.\.venv\Scripts\python.exe -m pytest tests -q
```

Periksa juga lint ringan (hanya galat nyata, aturannya di `ruff.toml`):

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

Di GitHub Actions (`.github/workflows/tes.yml`) hanya ada job
**PostgreSQL**: lint lalu seluruh suite, memakai PostgreSQL bawaan image
runner Windows, di setiap push dan atas permintaan (*Run workflow*). Proteksi
branch `main` mewajibkan pemeriksaan ini. `tests/test_migration.py` menguji
setiap migrasi turun lalu naik kembali.

Untuk pengujian PostgreSQL tersedia `.\test-postgres.ps1`. Build aplikasi
Windows dilakukan dengan `.\build.ps1`; pembuatan installer memerlukan Inno
Setup 6 dan menggunakan `.\build-installer.ps1`. Build APK memerlukan JDK 17
dan Android SDK Platform 35, lalu `.\build-android-kiosk.ps1`.

## 10. Struktur kode

```text
app/
  core/          konfigurasi, koneksi database, migration, keamanan
  models/        model SQLAlchemy
  repositories/  operasi baca/tulis data
  services/      aturan bisnis dan hak akses
  ui/            antarmuka desktop PySide6
  kiosk_api.py   API FastAPI untuk anjungan Android
alembic/         migration skema database
android-kiosk/   aplikasi APK Android
tests/           pengujian otomatis
docs/            panduan operasional dan pengembangan
```

Alur desktop: UI → service → repository → SQLAlchemy → SQLite/PostgreSQL.
Aturan bisnis dan otorisasi ditempatkan di service, bukan hanya disembunyikan
di UI. Jangan mengubah skema database secara manual tanpa migration Alembic.

## 11. Diagnostik cepat

Mulailah dari menu **Kesehatan Sistem** (Administrator). Layar itu memeriksa
koneksi database, revisi migrasi, API anjungan, tablet terakhir terhubung
beserta versi APK dan printernya, printer tiket komputer ini, backup
terakhir dan salinan keduanya, sisa disk, serta galat penting 24 jam
terakhir dari `logs\app.log`. Kata sandi, token, dan untaian mirip rahasia
disamarkan sebelum ditampilkan.

API anjungan mempunyai dua endpoint tanpa token:

| Endpoint | Arti |
|---|---|
| `GET /health` | Proses API menyala. Isinya selalu `{"status":"ok"}` dan tidak boleh diubah: aplikasi (termasuk versi lama di komputer loket) membandingkannya persis. |
| `GET /health/siap` | API siap melayani: `200` bila database terjangkau dan skemanya sesuai, `503` bila tidak. Isinya hanya kata keadaan (`database`, `skema`), tanpa alamat atau pesan galat. |

| Gejala | Periksa |
|---|---|
| Klien menampilkan database tidak terjangkau | Layanan PostgreSQL aktif, IP server, TCP `5432`, `listen_addresses`, `pg_hba.conf`, dan Firewall |
| PC melihat database lokal, bukan server | Pilihan peran klien tersimpan atau `ANTRIAN_DB_URL` lama mengalahkan konfigurasi mesin |
| Android tidak menemukan server | API aktif, jaringan sama, aturan Firewall terbaru, UDP `8766`; coba IP manual |
| Android menerima koneksi ditolak/timeout | Alamat `http://IP:8765`, API aktif, TCP `8765`, subnet dan Firewall |
| Android menolak otorisasi | Token di Android harus sama persis dengan token server |
| API tidak dapat mulai | Periksa database aktif, token minimal 8 karakter, port `8765` tidak dipakai, lalu lihat `logs\app.log` dan `logs\kiosk-api-stderr.log` |
| Database berhasil dibuat tetapi klien tak dapat masuk | Atur `listen_addresses`, tambahkan subnet benar ke `pg_hba.conf`, lalu reload/restart PostgreSQL |
| Printer Android tidak mencetak | Pastikan USB host/OTG, kabel, daya, izin USB, dan printer ESC/POS; kegagalan cetak tidak membatalkan nomor |

## Dokumentasi terkait

- [README — panduan dan aturan aplikasi](../README.md)
- [PostgreSQL dan banyak komputer](../README.md#pemasangan-beberapa-loket-postgresql)
- [Anjungan Android dan printer USB](android-kiosk.md)
- [Uji terima sebelum operasional](acceptance-test.md)
- [Peran komputer](peran-komputer.md)
- [Catatan lanjutan pengembangan](lanjutan.md)
