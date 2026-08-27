# Sistem Antrian & Survey Kepuasan Pelayanan CRO

Aplikasi desktop lokal untuk mengelola antrian pelayanan CRO
(Customer Relations Officer) dan mengukur kepuasan pengunjung.

Aplikasi berjalan **di jaringan lokal saja**. Tidak ada API, cloud, maupun
sinkronisasi ke luar kantor.

| | |
|---|---|
| Platform | Windows 10 / 11 |
| Python | **3.13** (dikunci — jangan pakai 3.11 atau 3.14) |
| UI | PySide6 |
| Database | PostgreSQL (beberapa loket) atau SQLite (satu komputer) via SQLAlchemy |
| Timezone | Asia/Jakarta (WIB, UTC+7) |

## Memilih database

| Keadaan | Database |
|---|---|
| **Satu komputer** melayani sendirian | SQLite, satu berkas lokal. Tanpa pemasangan apa pun. |
| **Beberapa loket** melayani bersamaan | **PostgreSQL wajib**, dipasang di satu komputer server. |

**SQLite di folder bersama TIDAK bisa dipakai beberapa komputer.** Mode WAL
memakai shared memory yang tidak berfungsi di filesystem jaringan, dan
mematikan WAL pun SQLite mendokumentasikan bug locking di sana. Akibatnya
bukan sekadar lambat, melainkan nomor antrian kembar atau database rusak.

Pindah dari satu komputer ke beberapa loket berarti memasang PostgreSQL —
lihat bagian **Pemasangan Beberapa Loket** di bawah. Konsekuensinya: ada satu
komputer yang bila mati membuat seluruh loket berhenti.

---

## Ruang Lingkup

Sistem ini menangani **dua hal saja**:

1. **Antrian pelayanan** — ambil nomor, panggil, layani, selesaikan
2. **Survey kepuasan** — rating 1–5 setelah pelayanan selesai

Data disimpan agar dapat diketahui **jumlah antrian** dan **hasil survey**.

### Yang TIDAK termasuk

- Pendaftaran / data wajib pajak
- Pengaduan dan nomor pengaduan
- Data pribadi pengunjung dalam bentuk apa pun

Antrian bersifat **anonim**: pengunjung memilih jenis layanan lalu menerima
nomor. Tidak ada nama, NIK, nomor HP, maupun alamat yang dicatat.

---

## Aturan Bisnis Utama

**Nomor antrian menggunakan prefix per jenis layanan**, dan urutannya
direset setiap hari:

```
26 Agustus              27 Agustus
A-001  Konsultasi       A-001  Konsultasi
A-002  Konsultasi       A-002  Konsultasi
B-001  Pengaduan        B-001  Pengaduan
C-001  Informasi
```

**Tiket antrian** dicetak 80 × 88 mm. Cara mencetaknya diatur lewat
pengaturan `ticket.printer`:

| Nilai | Perilaku |
|---|---|
| `pdf` | Simpan sebagai berkas PDF di folder `tiket/` (bawaan, selalu berhasil) |
| `system` | Cetak ke printer Windows |
| `none` | Tidak mencetak; nomor cukup disebutkan dan tampil di layar |

**Kegagalan mencetak tidak pernah membatalkan antrian.** Nomor sudah terbit
dan tersimpan sebelum tiket dicetak; petugas cukup menyebutkan nomornya.

**Layar antrian berjalan sebagai kios.** Akun berperan `DISPLAY` membuka
aplikasi langsung dalam layar penuh, tanpa bilah atas, tanpa menu navigasi,
dan tanpa bilah status. Pengunjung tidak melihat nama petugas, lokasi
database, maupun tombol "Keluar" — tombol keluar yang terpampang di layar
publik hanya mengundang orang menutup aplikasi antrian.

**Layar pengunjung** (`--layar` atau pilihan saat start) menggabungkan papan
nomor dengan pengambilan nomor sendiri pada satu mesin, tanpa login. Jeda
`kiosk.cooldown_seconds` menahan satu orang menekan tombol berulang kali.

Petugas tetap dapat keluar dengan `Ctrl+Q`, dan `F11` mengembalikan jendela
ke ukuran biasa saat perlu dipindahkan ke monitor yang benar.

Mode ini ditentukan dari hak akses, bukan dari nama peran: akun yang hanya
boleh melihat layar antrian dan tidak boleh apa-apa lagi memang dipasang di
komputer publik.

**Layar antrian** menyegar setiap 2 detik dan membunyikan panggilan saat
ada panggilan baru maupun panggilan ulang: nada dua-nada, lalu pengumuman
lisan penuh ("Nomor antrian A, dua puluh tiga, silakan menuju Loket 2")
lewat mesin text-to-speech bawaan Windows (memakai suara Bahasa Indonesia
bila tersedia). Tidak ada berkas audio maupun dependency tambahan yang
perlu disiapkan — nada dibangkitkan sendiri dan TTS memakai mesin yang
sudah terpasang di OS. Komputer tanpa perangkat suara tetap berjalan
normal, hanya tanpa bunyi.

**Pintasan papan ketik** (petugas loket jarang menyentuh mouse):

| Layar | Pintasan |
|---|---|
| Terbitkan Nomor | `1`–`9` memilih jenis layanan |
| Pelayanan | `F2` panggil berikutnya · `F3` panggil ulang · `F4` mulai melayani · `F8` selesai |
| Semua layar | `F5` muat ulang · `F11` layar penuh · `Ctrl+Q` keluar |

**Menu per peran:**

| Peran | Menu |
|---|---|
| `REGISTRATION` | Terbitkan Nomor |
| `CRO` | Pelayanan · Survey Kepuasan |
| `SUPERVISOR` | Ringkasan Harian · Hasil Survey |
| `ADMIN` | Data Master · Pengaturan · Backup & Audit |
| `DISPLAY` | Layar Antrian |
| `KIOSK` | Layar Pengunjung (papan nomor + ambil nomor, tanpa login) |

**Status antrian:**

```
WAITING → CALLED → SERVING → COMPLETED

CALLED  → NO_SHOW
WAITING → CANCELLED
CALLED  → CANCELLED
SERVING → PAUSED → SERVING
```

Seluruh perpindahan status divalidasi di service layer. Transition ilegal ditolak.

**Survey kepuasan** memakai rating 1–5 (1 = Sangat Tidak Puas, 5 = Sangat Puas)
dengan feedback opsional. Survey menempel pada satu antrian dan tidak boleh
ganda. Survey **tidak mengubah status antrian** — antrian yang sudah
`COMPLETED` tetap `COMPLETED` walau ratingnya 1.

Hanya antrian berstatus `COMPLETED` yang dapat dinilai. Antrian yang
dibatalkan atau tidak hadir tidak pernah menerima pelayanan, sehingga tidak
ada yang bisa dinilai pengunjung.

Survey diisi lewat dua jalur, keduanya memakai layanan yang sama:

| Jalur | Cara |
|---|---|
| Layar kios | Menu **Survey Kepuasan**, dipasang pada monitor kedua atau tablet yang menghadap pengunjung. Pengunjung memilih nomornya sendiri lalu menekan nilai. |
| Diminta petugas | Tombol **Minta Survey** pada panel pelayanan, menyala setelah `F8`. Layar diserahkan kepada pengunjung untuk diisi. |

Survey **tidak muncul sendiri** setelah pelayanan selesai. Petugaslah yang
tahu apakah pengunjung masih di depan meja; dialog yang menyembul sendiri
justru menahan antrian berikutnya. Seluruh survey dapat dimatikan lewat
pengaturan `survey.enabled`.

**Ringkasan harian** tersedia untuk `SUPERVISOR`: jumlah antrian per status
dan per jenis layanan, rata-rata waktu tunggu dan waktu layanan, porsi
antrian yang tuntas dilayani, serta rata-rata dan sebaran nilai kepuasan
hari itu. Layar menyegar sendiri setiap `dashboard.refresh_seconds` detik.

Angka yang belum ada datanya ditampilkan `—`, bukan `0` — keduanya berbeda
arti bagi yang membacanya.

**Backup** berupa file SQLite utuh di folder `backup/`:

| Cara | Kapan |
|---|---|
| Otomatis | Satu kali setiap hari saat aplikasi dibuka, bila `backup.auto_enabled` aktif |
| Manual | Kapan saja oleh `ADMIN` lewat menu **Backup & Audit** |

Backup memakai *Online Backup API* bawaan SQLite, bukan penyalinan file
biasa. Aplikasi berjalan dalam mode WAL sehingga sebagian transaksi terbaru
belum masuk ke file utama; salinan mentahnya bisa tertinggal atau rusak.

**Kegagalan backup otomatis tidak pernah menghentikan aplikasi.** Kehilangan
backup satu hari jauh lebih ringan akibatnya daripada loket yang tidak bisa
melayani sama sekali.

Backup yang lebih tua dari `backup.retention_days` dihapus otomatis.
Nilai nol atau negatif diabaikan, agar salah konfigurasi tidak menghapus
salinan yang baru saja dibuat.

**Pemulihan** hanya dapat dilakukan `ADMIN`, dikonfirmasi dua kali, dan
selalu menyalin database yang sedang berjalan terlebih dahulu sebagai
cadangan pengaman. Setelah dipulihkan, aplikasi perlu ditutup dan dibuka
kembali agar seluruh layar membaca data yang baru.

---

## Status Pengembangan

| Phase | Nama | Status |
|---|---|---|
| 0 | Environment Lock | ✅ Selesai |
| 1 | Foundation (config, database, models, seed, logging) | ✅ Selesai |
| 2 | Authentication | ✅ Selesai |
| 3 | Master Data (branch, counter, jenis layanan, user) | ✅ Selesai |
| 4 | Queue + Service Flow | ✅ Selesai |
| 5 | Ticket + Display + Sound | ✅ Selesai |
| 6 | Satisfaction Survey | ✅ Selesai |
| 7 | Dashboard Harian | ✅ Selesai |
| 8 | Backup + Audit + Hardening | ✅ Selesai |
| 9 | Packaging + Acceptance Test | ✅ Selesai |

---

## Login Pertama Kali

Saat database dibuat pertama kali, sistem membuat satu akun administrator:

| | |
|---|---|
| Nama pengguna | `admin` |
| Kata sandi | `admin123` |

**Kata sandi ini tidak rahasia dan wajib diganti.** Akun tersebut ditandai
`must_change_password`, sehingga seluruh kewenangannya ditolak sampai kata
sandinya diganti — admin bisa masuk, tetapi belum bisa mengerjakan apa pun.

Akun bawaan hanya dibuat bila database belum berisi user sama sekali.
Menghapusnya setelah membuat akun sendiri tidak akan memunculkannya lagi.

### Peran dan kewenangan

| Peran | Kewenangan |
|---|---|
| `ADMIN` | user, cabang, loket, jenis layanan, konfigurasi, backup |
| `SUPERVISOR` | dashboard, laporan, hasil survey (tanpa mengubah antrian) |
| `REGISTRATION` | menerbitkan nomor antrian, mencetak tiket |
| `CRO` | memanggil, melayani, menunda, menyelesaikan, no-show, batal |
| `DISPLAY` | hanya layar antrian |
| `KIOSK` | papan nomor dan pengambilan nomor sendiri, **tanpa akun** |

`KIOSK` bukan akun yang dibuat administrator. Sesi itu dibuka tanpa login
pada komputer yang menghadap pengunjung. Menyimpan kata sandi petugas di
mesin publik justru menciptakan kebocoran yang tidak perlu.

Pembagian ini disengaja: tidak ada satu peran pun yang dapat melakukan
segalanya. `ADMIN` mengelola sistem tetapi tidak melayani antrian, dan
`SUPERVISOR` memantau tetapi tidak mengubah antrian.

Kata sandi disimpan sebagai hash scrypt bergaram acak. Kata sandi asli tidak
pernah disimpan, tidak pernah masuk log, dan tidak pernah masuk audit log.

---

## Setup Development

Prasyarat: Python 3.13 terpasang dan dapat dipanggil lewat `py -3.13`.

### 1. Buat virtual environment

```powershell
py -3.13 -m venv .venv
```

### 2. Install dependency

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` sudah memuat seluruh runtime dependency.
Untuk instalasi runtime saja, gunakan `requirements.txt`.

### 3. Siapkan database

```powershell
.\.venv\Scripts\python.exe -m app.main
```

Perintah ini menjalankan migration dan mengisi data master awal.
Aman diulang: migration dan seed sama-sama idempotent.

### 4. Verifikasi environment

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

Seluruh test harus PASSED sebelum melanjutkan pengembangan.

### 5. Jalankan aplikasi

```powershell
.\.venv\Scripts\python.exe -m app.main
```

Gunakan `--init-only` untuk menyiapkan database saja tanpa membuka jendela —
berguna saat memeriksa pemasangan di komputer baru. Hasilnya juga tercatat
di `logs/app.log`, karena `AntrianCRO.exe` berjendela dan tidak punya
terminal untuk menampilkannya.

Saat dibuka tanpa argumen, aplikasi menanyakan layar mana yang akan dipakai:
**Layar Pengunjung** (kios, tanpa login) atau **Layar Petugas** (wajib masuk).

Komputer kios sebaiknya **melewati dialog itu**, supaya mati listrik siang
hari tidak meninggalkan papan nomor kosong sampai ada yang mengklik:

```powershell
.\.venv\Scripts\python.exe -m app.main --layar
```

Pasang perintah yang sama pada pintasan Startup Windows, atau pada
`AntrianCRO.exe --layar` di komputer kios yang sudah di-build.

Jeda antar-pengambilan nomor di kios diatur lewat `kiosk.cooldown_seconds`
(bawaan 10 detik). Jeda ini **hanya** berlaku pada sesi kios — meja
pendaftaran melayani rombongan yang datang bersamaan dan tidak ikut
diperlambat.

---

## Menjalankan Test

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

Selalu panggil interpreter `.venv` secara eksplisit. Menjalankan `pytest`
langsung berisiko memakai Python global yang versinya berbeda.

Perintah di atas menguji di atas **SQLite** karena jauh lebih cepat. Tetapi
SQLite bukan yang dipakai kantor dengan beberapa loket, sehingga sebelum
rilis seluruh test wajib dijalankan juga di PostgreSQL:

```powershell
.\test-postgres.ps1
```

Skrip itu menyalakan PostgreSQL di Docker, menjalankan seluruh suite
terhadapnya, lalu membiarkan container hidup agar pengulangan tidak perlu
menunggu. Hentikan dengan `docker compose down -v`.

Test yang tidak bermakna pada dialect yang sedang diuji akan **dilewati**,
bukan gagal — PRAGMA SQLite tidak ada padanannya di PostgreSQL, dan backup
PostgreSQL membutuhkan `pg_dump`. Perhatikan jumlah yang dilewati: test
backup yang terlewat berarti backup belum terbukti sama sekali.

---

## Pemasangan Beberapa Loket (PostgreSQL)

### Di komputer server

1. Pasang PostgreSQL 17:

```powershell
winget install --id PostgreSQL.PostgreSQL.17
```

2. Buat database dan penggunanya:

```sql
CREATE USER antrian WITH PASSWORD 'ganti-kata-sandi-ini';
CREATE DATABASE antrian OWNER antrian;
```

3. Izinkan komputer loket menyambung. Pada `postgresql.conf`:

```
listen_addresses = '*'
```

Pada `pg_hba.conf`, sesuaikan dengan rentang alamat jaringan kantor:

```
host    antrian    antrian    192.168.1.0/24    scram-sha-256
```

Jangan memakai `0.0.0.0/0`. Batasi persis pada jaringan kantor.

4. Buka port 5432 pada Windows Firewall, hanya untuk jaringan lokal.

### Di tiap komputer loket

Setel environment variable, lalu jalankan aplikasi seperti biasa:

```powershell
setx ANTRIAN_DB_URL "postgresql+psycopg://antrian:ganti-kata-sandi-ini@192.168.1.10:5432/antrian"
```

Migration dijalankan otomatis oleh aplikasi yang pertama kali dibuka.
Sisanya tinggal menyambung.

`ANTRIAN_DB_URL` **mengalahkan** `ANTRIAN_DB_PATH`. Komputer yang sudah
diarahkan ke server tidak akan diam-diam kembali memakai berkas SQLite lokal
hanya karena variabel lama tertinggal.

### User PostgreSQL terbatas untuk mesin kios

Komputer kios menghadap publik. Connection string-nya tetap ada di mesin
itu, jadi **jangan** memakai user `antrian` yang sama dengan petugas —
user itu dapat membaca tabel `app_user` (hash kata sandi seluruh petugas).

1. Buat user terpisah, lalu jalankan [docs/sql/kios-grant.sql](docs/sql/kios-grant.sql)
   sebagai superuser pada database `antrian`.
2. Di komputer kios, arahkan ke user itu:

```powershell
setx ANTRIAN_DB_URL "postgresql+psycopg://antrian_kios:ganti-kata-sandi-kios@192.168.1.10:5432/antrian"
```

3. Tambah baris `pg_hba.conf` khusus untuk user kios, tetap dibatasi
   jaringan kantor:

```
host    antrian    antrian_kios    192.168.1.0/24    scram-sha-256
```

User kios tidak punya hak apa pun pada `app_user`. Ia hanya boleh
menerbitkan nomor, membaca papan antrian, dan menulis jejak audit.

### Backup dijalankan di komputer server

Backup PostgreSQL memakai `pg_dump`, yang ikut terpasang bersama PostgreSQL.
Komputer loket biasanya tidak memilikinya. Bila foldernya tidak ada di PATH,
isi pengaturan **Folder perkakas PostgreSQL** dengan
`C:\Program Files\PostgreSQL\17\bin`.

---

## Membangun `AntrianCRO.exe`

```powershell
.\build.ps1
```

Skrip ini menjalankan seluruh test terlebih dahulu dan menghentikan build
bila ada yang gagal, supaya `.exe` yang rusak tidak ikut terdistribusi.

Hasilnya berada di `dist\AntrianCRO\`. **Salin seluruh folder tersebut**,
bukan hanya berkas `.exe`-nya.

Dibangun sebagai satu folder (*onedir*), bukan satu berkas (*onefile*).
Mode *onefile* membongkar seluruh isi PySide6 ke folder temporary setiap
kali aplikasi dibuka — beberapa detik penundaan di depan loket yang sedang
melayani, setiap hari.

Saat dijalankan pertama kali di komputer baru, aplikasi membuat sendiri
folder `data`, `logs`, `backup`, beserta database dan akun administrator
bawaan. Tidak ada langkah pemasangan tambahan.

Lokasi penyimpanan dapat dipindahkan tanpa mengubah kode, lewat
environment variable `ANTRIAN_DB_PATH`, `ANTRIAN_BACKUP_DIR`, dan
`ANTRIAN_LOG_DIR`.

Sebelum diserahkan ke pengguna, kerjakan daftar periksa pada
[docs/acceptance-test.md](docs/acceptance-test.md) di komputer tujuan.

---

## Memulihkan Database dari Backup

1. Masuk sebagai `ADMIN`, buka menu **Backup & Audit**.
2. Pilih berkas backup pada daftar, tekan **Pulihkan**.
3. Konfirmasi dua kali.
4. **Tutup dan buka kembali aplikasi.**

Seluruh antrian dan survey yang tercatat setelah tanggal backup akan
hilang. Database yang sedang berjalan otomatis disalin lebih dahulu sebagai
cadangan pengaman, sehingga salah pilih berkas masih dapat diperbaiki.

Berkas backup dapat disalin ke media lain untuk arsip: `.db` pada SQLite
adalah database yang dapat dibuka langsung, `.dump` pada PostgreSQL adalah
arsip `pg_dump` format custom. **Menaruhnya di komputer yang sama dengan
aslinya tidak melindungi apa pun bila komputer itu rusak.**

Pada PostgreSQL, pemulihan memakai `pg_restore --clean --single-transaction`
sehingga kegagalan di tengah jalan membatalkan seluruhnya — database tidak
pernah tertinggal separuh terpulihkan.

---

## Dependency

**Runtime** (`requirements.txt`)

| Paket | Kegunaan |
|---|---|
| PySide6 | UI desktop, cetak tiket (QtPrintSupport), suara panggilan (QtMultimedia) |
| SQLAlchemy | ORM dan akses database |
| psycopg | Driver PostgreSQL — wajib bila lebih dari satu loket |
| alembic | Migration skema — agar update aplikasi tidak menghapus data lama |
| pydantic | Validasi data internal |
| reportlab | PDF tiket dan laporan |
| tzdata | Database timezone IANA — **wajib**, Windows tidak menyediakannya |

**Development** (`requirements-dev.txt`)

| Paket | Kegunaan |
|---|---|
| pytest | Automated testing |
| pyinstaller | Packaging `AntrianCRO.exe` |

Seluruh versi di-pin exact (`==`) demi build yang reproducible.
Jangan menambah dependency tanpa kebutuhan nyata.

---

## Arsitektur

```
PySide6 UI  →  Service Layer  →  Repository Layer  →  SQLAlchemy  →  PostgreSQL / SQLite
```

Dialect dipilih saat aplikasi berjalan lewat `ANTRIAN_DB_URL`. Yang berbeda
di antara keduanya hanya tiga tempat, dan semuanya sudah dipagari:

| Berbeda | Di mana |
|---|---|
| PRAGMA, pool, penguncian | [app/core/database.py](app/core/database.py) |
| Selisih waktu di SQL | `QueueRepository._selisih_detik` — SQLite tidak punya tipe interval |
| Cara backup | [app/services/backup_engines.py](app/services/backup_engines.py) |

**Penomoran antrian tidak termasuk yang berbeda,** dan itu disengaja.
Keamanannya bersandar pada satu pernyataan `INSERT … ON CONFLICT DO UPDATE …
RETURNING` yang berlaku sama di kedua dialect — bukan pada perilaku kunci
milik salah satunya. Bentuk sebelumnya (UPDATE dahulu, INSERT bila tidak
ada barisnya) menyimpan celah yang tidak pernah terlihat di SQLite karena
`BEGIN IMMEDIATE` mengunci seluruh database, tetapi nyata di PostgreSQL.

Ada test yang mengunci **bentuk pernyataannya**, bukan sekadar hasilnya,
agar pemecahan kembali menjadi dua pernyataan tidak lolos diam-diam.

Relasi data:

```
Branch ─┬─ User
        ├─ Counter
        ├─ ServiceCategory
        └─ Queue ─┬─ QueueCall
                  └─ SatisfactionSurvey
```

Aturan yang ditegakkan:

- UI **tidak boleh** mengakses database secara langsung.
- Seluruh business rule dan authorization berada di **service layer**.
- Nomor antrian tidak boleh duplikat dalam satu hari — dijamin oleh
  transaction SQLite dan constraint `UNIQUE(branch_id, queue_date, queue_number)`.
- Setiap pemanggilan dicatat di `QueueCall` dan tidak pernah ditimpa.

Database aplikasi berada di `data/queue.db` dan tidak di-commit ke git.

Struktur layer:

```
app/
  core/          config, database, migration, clock, security, logging, seed
  models/        tabel SQLAlchemy
  repositories/  query database
  services/      aturan bisnis dan hak akses
  ui/            layar PySide6
  utils/         format tampilan berbahasa Indonesia
```

**Pengaturan** diubah `ADMIN` lewat menu **Pengaturan**:

| Kunci | Bawaan | Kegunaan |
|---|---|---|
| `ticket.printer` | `pdf` | Cara mencetak tiket: `pdf`, `system`, `none` |
| `ticket.footer` | — | Teks penutup pada tiket |
| `display.title` | — | Judul pada layar antrian |
| `display.next_count` | `3` | Jumlah nomor berikutnya yang ditampilkan |
| `display.sound_enabled` | `true` | Suara saat nomor dipanggil |
| `queue.max_call_attempts` | `3` | Batas pemanggilan sebelum dianggap tidak hadir |
| `kiosk.cooldown_seconds` | `10` | Jeda antar-pengambilan nomor di mesin kios (detik) |
| `survey.enabled` | `true` | Aktifkan survey kepuasan |
| `dashboard.refresh_seconds` | `30` | Jeda penyegaran ringkasan harian |
| `backup.auto_enabled` | `true` | Backup otomatis harian saat aplikasi dibuka |
| `backup.retention_days` | `30` | Lama backup disimpan sebelum dihapus |
| `backup.pg_dump_path` | — | Folder perkakas PostgreSQL bila tidak ada di PATH |

Jenis dan batas tiap pengaturan dijelaskan sekali saja pada `SKEMA` di
[app/services/settings_service.py](app/services/settings_service.py). Layar
memakainya untuk memilih kontrol yang tepat — kotak centang, daftar pilihan,
atau kotak angka berbatas — dan `set()` memakainya untuk menolak nilai yang
tidak masuk akal. UI dapat dilewati, service tidak, sehingga keduanya wajib
bersandar pada keterangan yang sama.

**Audit log** mencatat setiap tindakan yang mengubah data, beserta pelaku
dan waktunya, dan dapat dibaca `ADMIN` lewat menu **Backup & Audit**.
Kata sandi, hash kata sandi, dan token tidak pernah masuk audit log —
disaring sebelum disimpan, bukan sekadar tidak dikirim.
