# Sistem Antrian & Survey Kepuasan Pelayanan CRO

Aplikasi desktop lokal untuk mengelola antrian pelayanan CRO
(Customer Relations Officer) dan mengukur kepuasan pengunjung.

Aplikasi berjalan **100% offline**. Tidak ada server, API, cloud, maupun
sinkronisasi. Seluruh data tersimpan pada satu file SQLite lokal.

| | |
|---|---|
| Platform | Windows 10 / 11 |
| Python | **3.13** (dikunci — jangan pakai 3.11 atau 3.14) |
| UI | PySide6 |
| Database | SQLite (satu file lokal, tanpa server) via SQLAlchemy |
| Timezone | Asia/Jakarta (WIB, UTC+7) |

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
| Semua layar | `F5` muat ulang · `Ctrl+Q` keluar |

**Menu per peran:**

| Peran | Menu |
|---|---|
| `REGISTRATION` | Terbitkan Nomor |
| `CRO` | Pelayanan · Survey Kepuasan |
| `SUPERVISOR` | Ringkasan Harian |
| `ADMIN` | Data Master · Pengaturan · Backup & Audit |
| `DISPLAY` | Layar Antrian |

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

---

## Menjalankan Test

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

Selalu panggil interpreter `.venv` secara eksplisit. Menjalankan `pytest`
langsung berisiko memakai Python global yang versinya berbeda.

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

Berkas backup adalah database SQLite biasa dan dapat disalin ke media lain
untuk arsip. Menaruhnya di komputer yang sama dengan aslinya tidak
melindungi apa pun bila komputer itu rusak.

---

## Dependency

**Runtime** (`requirements.txt`)

| Paket | Kegunaan |
|---|---|
| PySide6 | UI desktop, cetak tiket (QtPrintSupport), suara panggilan (QtMultimedia) |
| SQLAlchemy | ORM dan akses SQLite |
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
PySide6 UI  →  Service Layer  →  Repository Layer  →  SQLAlchemy  →  SQLite
```

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
| `survey.enabled` | `true` | Aktifkan survey kepuasan |
| `dashboard.refresh_seconds` | `30` | Jeda penyegaran ringkasan harian |
| `backup.auto_enabled` | `true` | Backup otomatis harian saat aplikasi dibuka |
| `backup.retention_days` | `30` | Lama backup disimpan sebelum dihapus |

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
