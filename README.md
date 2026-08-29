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
- Nomor pengaduan dan penelusuran tindak lanjutnya

**Antrian sendiri tetap anonim.** Pengunjung memilih jenis layanan lalu
menerima nomor; tabel `queue` tidak pernah memuat nama, NIK, nomor HP,
maupun alamat.

**Satu pengecualian, dan tempatnya satu saja.** Petugas dapat menulis
pengaduan beserta identitas pelapor pada tabel terpisah `queue_note` —
lihat [Pengaduan dan catatan petugas](#pengaduan-dan-catatan-petugas).
Terpisah bukan karena rapi, melainkan karena hak akses: komputer anjungan
dapat membaca tabel `queue`, dan pengaduan tidak boleh ikut terbaca dari
mesin yang berdiri di ruang publik tanpa diawasi.

Akibat yang tidak boleh dilupakan: **berkas backup kini berisi data
pribadi.** Folder backup setara lemari arsip, bukan lagi salinan angka.

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

**Tiket antrian** dicetak 80 × 88 mm. Selain nomor, jenis layanan, loket,
tanggal, dan jam, tiket menyebut **sisa antrian** pada saat tiket dicetak:
banyaknya nomor yang masih menunggu di depan pemegang tiket, dihitung lintas
seluruh jenis layanan karena urutan pemanggilan memang lintas layanan.
Angkanya foto sesaat, bukan janji. Bila gagal dibaca, tiket tetap tercetak
tanpa baris itu.

Cara mencetaknya diatur lewat pengaturan `ticket.printer`:

| Nilai | Perilaku |
|---|---|
| `pdf` | Simpan sebagai berkas PDF di folder `tiket/` (bawaan, selalu berhasil) |
| `system` | Cetak ke printer Windows |
| `none` | Tidak mencetak; nomor cukup disebutkan dan tampil di layar |

**Kegagalan mencetak tidak pernah membatalkan antrian.** Nomor sudah terbit
dan tersimpan sebelum tiket dicetak; petugas cukup menyebutkan nomornya.

**Tiga jenis mesin, tiga layar yang berbeda.** Yang menentukan adalah
sifat komputernya, bukan siapa yang sedang memakainya:

| Mesin | Pintasan | Isi layar | Suara | Login |
|---|---|---|---|---|
| Televisi ruang tunggu | `AntrianCRO.exe --tv` | Papan nomor besar, dibaca dari seberang ruangan | ya | tidak |
| Anjungan ambil nomor | `AntrianCRO.exe --kios` | Pilih layanan, cetak tiket, papan nomor kecil | tidak | tidak |
| Komputer loket (3–5 unit) | `AntrianCRO.exe` | Memanggil dan melayani antrian | tidak | ya |

Kedua mesin publik berjalan **tanpa login**. Komputer yang menghadap publik
dan tidak diawasi tidak boleh menyimpan kata sandi petugas — atau lebih
buruk, memaksa seseorang mengetikkannya setiap pagi sampai sandi itu
tertempel di bawah keyboard. Keduanya juga membuka layar penuh tanpa bilah
atas, tanpa menu navigasi, dan tanpa bilah status: pengunjung tidak melihat
nama petugas, lokasi database, maupun tombol "Keluar" yang hanya mengundang
orang menutup aplikasi antrian.

**Anjungan diam secara bawaan.** Bila anjungan ikut bersuara sementara
televisi juga bersuara, pengunjung mendengar dua pengumuman yang saling
menyusul — keduanya menyegarkan sendiri tiap dua detik dan tidak akan
pernah sinkron. Pemasangan satu-mesin yang anjungannya merangkap papan
nomor menyalakannya kembali dengan `ANTRIAN_SUARA=1`.

Jeda `kiosk.cooldown_seconds` menahan satu orang menekan tombol ambil nomor
berulang kali. Akun berperan `DISPLAY` tetap ada dan tetap membuka papan
yang sama, berguna saat supervisor ingin melihat papan dari mejanya.

Petugas tetap dapat keluar dengan `Ctrl+Q`, dan `F11` mengembalikan jendela
ke ukuran biasa saat perlu dipindahkan ke monitor yang benar.

**Layar antrian** menyegar setiap 2 detik dan membunyikan panggilan saat
ada panggilan baru maupun panggilan ulang: nada dua-nada, lalu — setelah
nadanya selesai — pengumuman lisan penuh ("Nomor antrian A, nol dua tiga,
silakan menuju Loket 2") lewat mesin text-to-speech bawaan Windows (memakai
suara Bahasa Indonesia bila tersedia). Tidak ada berkas audio maupun
dependency tambahan yang perlu disiapkan — nada dibangkitkan sendiri dan
TTS memakai mesin yang sudah terpasang di OS. Komputer tanpa perangkat
suara tetap berjalan normal, hanya tanpa bunyi.

**Daftar menunggu di televisi terbagi per jenis layanan.** Tiga jenis
layanan berarti separuh bawah layar terbagi tiga kolom, masing-masing
berjudul nama layanannya:

```
MENUNGGU GILIRAN                              1 / 2
   A · Konsultasi     B · Pengaduan     C · Informasi
   A-013  A-018       B-006  B-011      C-002   —
   A-014  A-019       B-007  B-012      C-003   —
   A-015  A-020       B-008    —          —     —
   A-016    —         B-009    —          —     —
   A-017    —         B-010    —          —     —
```

Setiap layanan mendapat **dua kolom**, karena panel ini lebar dan pendek —
sekitar 1800×400 piksel pada televisi 1080p. Menumpuk sepuluh nomor ke
bawah menghabiskan sisi yang langka dan menyia-nyiakan sisi yang berlimpah:
hurufnya terpaksa turun sampai 18px agar muat. Dua kolom membuat huruf yang
sama muat pada 37px. Nomor dibaca menurun dulu, baru pindah ke kolom
kanannya — urutan baca koran.

Loket dapat dibatasi jenis layanan yang boleh dipanggilnya, sehingga
urutan panggil memang berjalan per layanan. Satu antrean gabungan
menyiratkan urutan yang tidak pernah terjadi — A-020 tampak akan dipanggil
sebelum B-003 padahal keduanya antre di loket yang berbeda.

Isinya seluruh nomor yang menunggu, bukan tiga teratas: yang dicari orang
yang sudah duduk adalah nomornya sendiri, bukan siapa berikutnya. Bila
tidak muat satu layar, daftarnya terbagi menjadi halaman yang berganti
sendiri, dan judul panelnya menyebut halaman ke berapa dari berapa — tanpa
itu, pengunjung yang belum melihat nomornya akan mengira nomornya hilang
lalu bertanya ke loket.

| Pengaturan | Bawaan | Arti |
|---|---|---|
| `display.list_rows` | 5 | Baris per kolom (1–12). Dua kolom per layanan, jadi 5 berarti 10 nomor per layanan |
| `display.list_font_size` | 0 | Ukuran huruf nomor; **0 = menyesuaikan sendiri** dengan tinggi papan |
| `display.rotate_seconds` | 3 | Jeda pergantian halaman; **0 = tidak berpindah sendiri** |
| `display.next_count` | 3 | Hanya untuk papan kecil di dalam anjungan |

**Huruf menyesuaikan tinggi papan, dan tingginya diturunkan dari metrik
huruf.** Tinggi baris tidak lagi berupa konstanta — ia dihitung dari huruf
yang harus dimuatnya, sehingga nomor terpotong tidak mungkin lagi terjadi
berapa pun yang diisi admin. `display.list_font_size` diperlakukan sebagai
batas **atas**: papan tetap memperkecilnya bila barisnya tidak muat, dan
bila huruf sudah menyentuh batas terkecil yang masih pantas dibaca, yang
dikurangi adalah barisnya — satu halaman lagi lebih baik daripada nomor
yang tidak terbaca.

Beberapa hal yang sengaja dibuat begitu:

- **Layanan yang sedang sepi tetap mendapat kolomnya** (berisi "—"). Kolom
  yang muncul dan hilang mengikuti isinya membuat lebar seluruh papan
  berubah beberapa detik sekali.
- **Layanan yang dinonaktifkan di tengah hari tetap tampil** selama masih
  ada yang menunggu padanya. Nomor yang sudah terbit tidak batal, dan
  orangnya masih duduk di ruangan itu.
- **Jumlah halaman mengikuti kolom terpanjang**, sehingga halaman berhenti
  setelah layanan paling ramai habis — bukan yang paling sepi.
- **Rotasi berhenti sendiri bila cukup satu halaman.** Halaman yang
  berpindah ke dirinya sendiri terbaca sebagai layar berkedip rusak.
- **Hari yang sangat ramai dibatasi 5 halaman**, sisanya disebut sebagai
  jumlah ("DAN 47 LAINNYA") alih-alih diputar sampai tidak ada yang sabar
  menunggunya kembali.
- **Lebih dari 6 jenis layanan kembali ke daftar gabungan.** Tujuh kolom
  pada satu televisi semuanya terpotong, dan daftar berhalaman lebih
  terbaca daripada tujuh kolom yang tak satu pun memuat nomor secara utuh.

**Panel pelayanan** disusun dua kolom: kartu antrian yang sedang ditangani
beserta seluruh tombolnya di kiri, daftar tunggu di kanan. Kartu berganti
warna mengikuti status — abu-abu saat menganggur, jingga saat nomor sudah
dipanggil tetapi orangnya belum datang, hijau saat pelayanan berjalan,
kuning saat loket istirahat — dan menampilkan penghitung waktu berjalan.
Pada daftar tunggu, baris paling depan ditandai dan kolom lama menunggu
berubah warna setelah 10 dan 20 menit.

Tombol yang tidak sah untuk status saat ini **dinonaktifkan, bukan
disembunyikan**. Posisinya tetap sehingga petugas tidak perlu mencari ulang
setiap kali status berubah — itulah yang menentukan bentuk kisi tombolnya.

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
| `CRO` | Pelayanan · Survey Kepuasan · Pengaduan & Catatan |
| `SUPERVISOR` | Pengaduan & Catatan · Ringkasan Harian · Hasil Survey |
| `ADMIN` | Data Master · Pengaturan · Backup & Audit |
| `DISPLAY` | Layar Antrian |
| `KIOSK` | Anjungan Ambil Nomor (papan nomor + ambil nomor, tanpa login) |

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

### Pengaduan dan catatan petugas

Setiap nomor antrian punya satu **lembar kerja**, dibuka petugas dari panel
pelayanan lewat tombol **Pengaduan & Catatan** atau `F9`. Formulirnya
berupa dialog tersendiri, bukan panel yang menempel di layar pelayanan:
tujuh isian tidak muat pada kolom yang sudah memuat kartu antrian beserta
seluruh tombol tindakan. Yang tertinggal di layar adalah keadaannya —
sudah terisi atau belum, dan kapan terakhir disimpan — supaya lembar yang
tersembunyi di balik dialog tidak terlupakan.

Isinya dua bagian:

| Bagian | Isi | Wajib |
|---|---|---|
| **Pengaduan** | Nama, nomor pelanggan, telepon, email, alamat, deskripsi keluhan | Nama, nomor pelanggan, dan deskripsi — bila pengaduan diisi sama sekali |
| **Catatan petugas** | Catatan internal atas pelayanan itu | Tidak. Boleh berdiri sendiri tanpa pengaduan |

**Deskripsi dan catatan sengaja tidak disatukan.** Deskripsi adalah kata
pengunjung; catatan adalah penilaian petugas. Bercampur dalam satu kotak,
penilaian internal ikut terbaca sebagai keluhan pelanggan oleh siapa pun
yang membukanya kemudian.

Aturan yang menjaganya:

- **Satu antrian satu lembar.** Petugas kedua menyunting lembar yang sama,
  bukan menumpuk lembar tandingan yang isinya saling bertentangan.
- **Hanya dapat disunting pada hari yang sama.** Pengaduan yang masih bisa
  diubah berhari-hari kemudian tidak berguna sebagai bukti apa pun.
- **Isinya tidak pernah masuk audit log.** Audit mencatat *bahwa* sebuah
  lembar disimpan, oleh siapa, untuk nomor mana — tidak pernah apa yang
  tertulis di dalamnya.
- **Menutup dialog dengan isian yang belum disimpan selalu ditanyakan.**
  Yang menceritakan keluhannya sudah selesai berbicara; teks yang hilang
  karena satu klik tidak dapat diketik ulang.
- **Dialog tidak menutup sendiri setelah disimpan** (`Ctrl+S`). Petugas
  sering menyimpan di tengah pembicaraan lalu meneruskan mengetik.
- **Menulis milik CRO, menghapus milik ADMIN.** Penulis yang sekaligus
  dapat menghilangkan tulisannya membuat catatan itu tidak berguna sebagai
  bukti. Penghapusan tercatat di audit log.
- **Tidak ada pembersihan otomatis.** Lembar disimpan sampai ada yang
  menghapusnya lewat menu **Pengaduan & Catatan**.

Seluruh petugas CRO dan supervisor dapat mencari lembar lama menurut nama,
nomor pelanggan, isi pengaduan, catatan, atau nomor antrian — pengunjung
yang kembali esok hari ke loket lain tidak perlu menceritakan keluhannya
dari awal.

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
| `ADMIN` | user, cabang, loket, jenis layanan, konfigurasi, backup, **menghapus lembar pengaduan** |
| `SUPERVISOR` | dashboard, laporan, hasil survey, membaca pengaduan (tanpa mengubah apa pun) |
| `REGISTRATION` | menerbitkan nomor antrian, mencetak tiket |
| `CRO` | memanggil, melayani, menunda, menyelesaikan, no-show, batal, menulis dan membaca pengaduan |
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

Saat dibuka tanpa argumen, aplikasi menanyakan layar mana yang akan
dipakai: **Layar Antrian**, **Anjungan Ambil Nomor** (keduanya tanpa login),
atau **Layar Petugas** (wajib masuk).

Kedua mesin publik sebaiknya **melewati dialog itu**, supaya mati listrik
siang hari tidak meninggalkan papan nomor kosong sampai ada yang mengklik:

```powershell
.\.venv\Scripts\python.exe -m app.main --tv      # televisi ruang tunggu
.\.venv\Scripts\python.exe -m app.main --kios    # anjungan ambil nomor
```

Pasang perintah yang sama pada pintasan Startup Windows, atau pada
`AntrianCRO.exe --tv` / `AntrianCRO.exe --kios` di komputer yang sudah
di-build. `--layar` adalah nama lama `--kios` dan masih berlaku, supaya
pintasan yang sudah terpasang tidak mati saat aplikasi diperbarui.

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

### Setelan yang berbeda di tiap mesin

Pencetak tiket menempel pada satu komputer dan pengeras suara pada komputer
lain, sedangkan `ticket.printer` dan `display.sound_enabled` di layar
Pengaturan bernilai satu untuk seluruh sistem. Dua environment variable
menimpanya **hanya di mesin yang bersangkutan**:

| Variable | Nilai | Dipasang di |
|---|---|---|
| `ANTRIAN_PRINTER` | `pdf`, `system`, `none` | Mesin yang punya (atau tidak punya) pencetak tiket |
| `ANTRIAN_SUARA` | `1` / `0` | Mesin yang harus bersuara, atau harus diam |

```powershell
# Anjungan: mencetak tiket, tetapi diam (televisi yang mengumumkan)
setx ANTRIAN_PRINTER "system"

# Komputer loket: tidak punya pencetak tiket dan tidak perlu bersuara
setx ANTRIAN_PRINTER "none"
```

Keduanya boleh dikosongkan. Mesin yang tidak menyebut apa-apa mengikuti
pengaturan bersama — kecuali suara pada anjungan, yang memang diam secara
bawaan. Nilai yang salah ketik diperlakukan seperti tidak diisi, bukan
sebagai "tidak": satu huruf keliru tidak boleh mendiamkan panggilan tanpa
jejak.

### User PostgreSQL terbatas untuk mesin publik

Anjungan dan televisi ruang tunggu menghadap publik. Connection string-nya
tetap ada di mesin itu, jadi **jangan** memakai user `antrian` yang sama
dengan petugas — user itu dapat membaca tabel `app_user` (hash kata sandi
seluruh petugas).

1. Buat user terpisah, lalu jalankan skripnya sebagai superuser pada
   database `antrian`:
   [kios-grant.sql](docs/sql/kios-grant.sql) untuk anjungan,
   [layar-grant.sql](docs/sql/layar-grant.sql) untuk televisi.
2. Di komputer yang bersangkutan, arahkan ke user itu:

```powershell
# Anjungan ambil nomor
setx ANTRIAN_DB_URL "postgresql+psycopg://antrian_kios:ganti-kata-sandi-kios@192.168.1.10:5432/antrian"

# Televisi ruang tunggu
setx ANTRIAN_DB_URL "postgresql+psycopg://antrian_layar:ganti-kata-sandi-layar@192.168.1.10:5432/antrian"
```

3. Tambah baris `pg_hba.conf` untuk keduanya, tetap dibatasi jaringan
   kantor:

```
host    antrian    antrian_kios     192.168.1.0/24    scram-sha-256
host    antrian    antrian_layar    192.168.1.0/24    scram-sha-256
```

Keduanya tidak punya hak apa pun pada `app_user`. Anjungan boleh
menerbitkan nomor, membaca papan antrian, dan menulis jejak audit;
televisi **hanya membaca** — tidak ada seorang pun yang berdiri di depannya
untuk mengambil nomor, sehingga hak menulis di sana murni kelebihan yang
tidak pernah dipakai.

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
