# Melanjutkan Pekerjaan — Sistem Antrian & Survey Kepuasan CRO

Dokumen serah terima. Berisi tujuan, keadaan sekarang, apa yang belum
selesai, dan hal-hal yang **jangan** diubah beserta alasannya.

> **Catatan Oktober 2026:** anjungan tidak lagi berjalan di Windows. Peran
> dan mode `anjungan`/`anjungan-totem` (`--kios`, `--kios-totem`, `--layar`)
> sudah dihapus; anjungan adalah tablet Android. Lihat
> [istilah.md](istilah.md). Bagian dokumen ini yang menyebut anjungan
> Windows adalah catatan sejarah.

---

## 1. Apa yang sedang dibangun

Aplikasi desktop untuk mengelola antrian pelayanan CRO (Customer Relations
Officer) di sebuah kantor pelayanan, sekaligus mengukur kepuasan pengunjung.

**Rencana pemakaian sebenarnya:**

- **5 komputer petugas**, masing-masing dengan login sendiri, melayani
  pengunjung **bersamaan**
- **1 komputer kios** menghadap pengunjung: menampilkan papan nomor
  terpanggil **sekaligus** tempat pengunjung mengambil nomornya sendiri dan
  mencetak tiket

Berjalan di jaringan lokal kantor. Tidak ada API, cloud, maupun
sinkronisasi ke luar.

| | |
|---|---|
| Platform | Windows 10 / 11 |
| Python | **3.13** (dikunci) |
| UI | PySide6 |
| Database | PostgreSQL (banyak loket) atau SQLite (satu komputer) |
| Timezone | Asia/Jakarta, disimpan sebagai datetime naive |

Baca [README.md](../README.md) untuk aturan bisnis lengkap. Baca
[acceptance-test.md](acceptance-test.md) untuk daftar uji terima.

---

## 2. Aturan yang WAJIB dipertahankan

Ini bukan preferensi gaya. Setiap butir punya alasan operasional, dan
beberapa di antaranya sudah dikunci oleh test.

### Bahasa dan gaya kode

- Seluruh nama fungsi, variabel, dan docstring memakai **Bahasa Indonesia**
- Docstring menjelaskan **MENGAPA**, bukan mengulang apa yang sudah terbaca
  dari kodenya. Lihat contoh di `app/services/queue_service.py`.
- `from __future__ import annotations` di setiap berkas
- DTO ke UI berupa `@dataclass(frozen=True)` — objek ORM tidak pernah lolos
  ke lapisan UI

### Lapisan

```
PySide6 UI → Service Layer → Repository Layer → SQLAlchemy → PostgreSQL/SQLite
```

- **UI tidak pernah menyentuh database langsung**
- Setiap metode service dimulai dengan
  `sesi = self.auth.require_permission(Permission.X)`
- Satu `session_scope()` per metode service
- Setiap mutasi dicatat lewat `audit_service.record(...)`
- Penegakan hak akses **hanya** di service layer. UI boleh menyembunyikan
  tombol, tetapi tidak boleh menjadi satu-satunya penjaga.

### Penanganan error

- Petugas **tidak pernah** melihat traceback, nama exception Python, atau
  pesan SQLite/PostgreSQL
- Setiap `AppError` membawa `user_message` berbahasa Indonesia
- UI memanggil service lewat `jalankan_aman()` dari `app/ui/common.py`
- Detail teknis masuk `logs/app.log`

### Data pribadi hanya di satu tempat

Sejak lembar pengaduan ada, aplikasi ini menyimpan nama, nomor pelanggan,
telepon, email, dan alamat pelapor. Seluruhnya **hanya** di tabel
`queue_note`. Yang harus tetap benar:

- **Jangan memindahkannya menjadi kolom di `queue`.** User PostgreSQL
  anjungan punya `SELECT` pada tabel itu, dan komputernya berdiri di ruang
  publik tanpa diawasi. Sudah dikunci test:
  `tests/test_note_service.py::test_anjungan_kios_tidak_dapat_membaca_lembar`.
- **Jangan memasukkan isinya ke audit log.** Audit dibaca ADMIN dan ikut ke
  setiap berkas backup. Dikunci
  `tests/test_note_service.py::test_isi_lembar_tidak_pernah_masuk_audit_log`.
- **Penulis tidak boleh menghapus.** Menulis milik CRO, menghapus milik
  ADMIN, dan penghapusan tercatat.
- **Berkas backup kini berisi data pribadi.** Siapa pun yang menyalin
  folder backup menyalin arsip pelapor.

### Jebakan yang sudah pernah menggigit

**Jangan pakai `QMessageBox.exec()` pada layar yang tidak diawasi petugas.**
Dialog modal menyangkut begitu pengunjung berbalik pergi, dan orang
berikutnya menemukan layar yang tidak bisa dipakai. Ini juga membuat test
suite **hang tanpa pesan**. Pakai label sebaris yang hilang sendiri.

**Jangan pakai `QTimer.singleShot`.** Timer statis tidak terikat pada widget
mana pun, tetap menyala setelah halamannya dihapus, lalu menyentuh label
yang sudah tidak ada → `libshiboken: Internal C++ object already deleted`.
Pakai `QTimer(self)` dengan `setSingleShot(True)`.

**`self.statusBar()` MEMBUAT bilah status bila belum ada.** Memanggilnya di
mode kios memunculkan bilah yang sengaja tidak dibangun, lengkap dengan
lokasi database di depan pengunjung. Sudah dijaga di
`MainWindow.muat_ulang_halaman`. Lokasi itu sendiri adalah *permanent
widget* (`statusDatabase`) supaya F5 tidak menghapusnya.

**`$ErrorActionPreference = "Stop"` merusak skrip PowerShell.** pytest,
PyInstaller, dan docker menulis keterangan biasa ke stderr, dan Windows
PowerShell 5.1 memperlakukan setiap barisnya sebagai error fatal. Skrip di
proyek ini memakai `"Continue"` dan memeriksa `$LASTEXITCODE`.

---

## 3. Riwayat commit

| Commit | Isi |
|---|---|
| `fe44670` | Seluruh aplikasi Phase 0–9 (fondasi sampai packaging) |
| `869af8b` | Layar pengaturan untuk ADMIN + validasi berbasis SKEMA |
| `7ca5bb2` | Layar antrian sebagai kios layar penuh |
| `cc377d0` | Penegakan batas panggilan + layar hasil survey supervisor |
| `535a60e` | **Port PostgreSQL** untuk beberapa loket serentak |
| `8d30d0b` | Kios pengunjung tanpa login |
| `152ac4d` | Layar pengunjung terbaca dari seberang ruangan |
| `2a1f804` | Papan televisi mengikuti ukuran layar + pilihan tema |
| `3ab265a` | Loket dan jenis layanan per petugas; istirahat dan tutup hari |
| `0a0a727` | Televisi dipisah dari anjungan; papan menunggu per jenis layanan |
| `9642b4d` | Ruang kerja pengaduan dan catatan petugas per antrian |
| `d1e820b` | Panel kanan berpindah otomatis: Menunggu Dilayani <-> Pengaduan |
| `210f1b6` | Layar Pengaduan & Catatan menyegar sendiri tiap 30 detik |
| `dff4b3a` | Anjungan tidak lagi menampilkan kartu loket; diganti angka ringkasan |

### Yang paling penting dari `535a60e`

Ada **race yang selama ini tersembunyi** di penomoran antrian.
`terbitkan_nomor` dulu melakukan `UPDATE` lalu `INSERT` bila barisnya belum
ada — dua penulis dapat sama-sama menemukan barisnya kosong lalu sama-sama
menyisipkan. SQLite menyembunyikannya karena `BEGIN IMMEDIATE` mengunci
seluruh database; **di PostgreSQL celah itu nyata**.

Sekarang satu pernyataan atomik:

```sql
INSERT INTO queue_sequence (branch_id, queue_date, category_id, last_number)
VALUES (:branch_id, :queue_date, :category_id, 1)
ON CONFLICT (branch_id, queue_date, category_id)
DO UPDATE SET last_number = queue_sequence.last_number + 1
RETURNING last_number
```

**JANGAN memecahnya kembali menjadi dua pernyataan.** Ada test yang mengunci
**bentuk pernyataannya**, bukan sekadar hasilnya:
`tests/test_database.py::test_penomoran_memakai_satu_pernyataan_atomik`.

---

## 4. Keadaan test terakhir yang terverifikasi

| Dialect | Hasil |
|---|---|
| SQLite | **890 lolos** (29 Agustus 2026, termasuk papan per-layanan, sisa antrian di tiket, lembar pengaduan, penyegaran otomatis layar Pengaduan, dan anjungan tanpa kartu loket) |
| PostgreSQL | **598 lolos, 25 dilewati** — putaran lama, SEBELUM perubahan papan per-layanan |

**Angka PostgreSQL itu sudah basi.** Suite belum pernah dijalankan ulang
terhadap PostgreSQL sejak papan per-layanan, `ringkasan_tiket`, dan
pengaturan per-mesin masuk. Docker Desktop tidak berjalan di mesin
pengembang saat putaran terakhir, sehingga skrip `test-postgres.ps1` tidak dapat
dipakai. **Jalankan sebelum rilis** — `ringkasan_tiket` dan
`_kelompokkan_per_layanan` membaca antrian dengan cara baru, dan itu justru
lapisan yang dialect-nya paling menentukan.

Skip PostgreSQL lebih banyak dari 6 yang tercatat sebelumnya. Test
`sqlite_saja` memang dilewati; sisanya hampir seluruhnya backup karena
`pg_dump`/`pg_restore` tidak ada di PATH mesin pengembang. **Backup
PostgreSQL belum terbukti pada putaran ini.**

Yang paling menentukan dan **sudah terbukti hijau di PostgreSQL**:
`tests/test_queue_numbering.py::test_penerbitan_bersamaan_tidak_menghasilkan_nomor_kembar`
— 8 utas × 12 nomor memperebutkan satu baris sequence.

---

## 5. Mesin publik — SUDAH di-commit

Anjungan dan layar antrian tanpa login, `--kios`/`--tv`, jeda pengambilan,
GRANT PostgreSQL, dan dokumentasinya sudah masuk tree. Test UI keduanya
sudah dijalankan (bukan hanya test service).

### Keputusan desain yang sudah disepakati pemilik

1. **Dialog pilihan saat start** — "Layar Antrian", "Anjungan Ambil Nomor",
   atau "Layar Petugas". Dua yang pertama langsung masuk tanpa login;
   petugas wajib login.
2. **Argumen `--tv` dan `--kios`** melewati dialog itu. Dipasang pada
   shortcut Startup kedua mesin publik supaya mati listrik tidak berhenti
   di dialog. `--layar` dipertahankan sebagai nama lama `--kios`.
3. **User PostgreSQL terpisah** untuk tiap mesin publik, **tanpa akses
   `app_user`**. Skripnya: [sql/kios-grant.sql](sql/kios-grant.sql) dan
   [sql/layar-grant.sql](sql/layar-grant.sql) — yang kedua hanya membaca.
4. **Jeda antar-pengambilan nomor** (`kiosk.cooldown_seconds`, bawaan 10
   detik). Hanya sesi anjungan — meja pendaftaran tidak ikut diperlambat.
5. Kegagalan di layar anjungan memakai **label sebaris**, bukan `QMessageBox`.
6. **Pencetak dan pengeras suara adalah sifat MESIN**, ditimpa lewat
   `ANTRIAN_PRINTER` dan `ANTRIAN_SUARA`. Anjungan diam secara bawaan
   supaya tidak berbunyi bersahutan dengan televisi.
7. **Anjungan tidak menampilkan kartu loket** (29 Agustus 2026). Diminta
   pemilik setelah melihat papan kios yang masih menyalin bentuk televisi
   — kartu per loket dengan status KOSONG/SEDANG DIPANGGIL — padahal
   pengunjung yang berdiri di anjungan belum memegang nomor sama sekali
   dan tidak butuh tahu loket mana yang kosong. Diganti dengan satu angka
   ringkasan (`DisplayPage._bangun_ringkasan_kios`, dipakai hanya saat
   `kompak=True`): jumlah antrian yang masih menunggu DITAMBAH yang
   sedang dilayani — keduanya sama-sama "berlangsung", belum selesai.
   Daftar Menunggu Giliran di bawahnya mendapat porsi jauh lebih besar
   (stretch 4:1, dari sebelumnya 5:2 untuk kartu loket) karena ruang yang
   dulu dipakai kartu loket sekarang kosong. TV (`kompak=False`) sama
   sekali tidak tersentuh — kartu loketnya tetap seperti semula.

### Keputusan pemilik atas lembar pengaduan (29 Agustus 2026)

Diputuskan setelah tegangannya dengan sifat anonim disampaikan, dan
ditegaskan ulang oleh pemilik:

1. Lembar menempel pada **nomor antrian**, bukan buku catatan harian.
2. **Seluruh petugas CRO** boleh membaca, karena itu ada layar
   **Pengaduan & Catatan** dengan pencarian. Tanpa layar itu, "semua boleh
   membaca" tidak berarti apa-apa.
3. Isian: nama, nomor pelanggan, deskripsi (**wajib** bila ada pengaduan);
   telepon, email, alamat (opsional); catatan petugas (berdiri sendiri).
4. **Tanpa nomor pengaduan tersendiri** — dirujuk lewat nomor antrian dan
   tanggalnya.
5. **Tanpa status tindak lanjut.** Cukup dicatat.
6. **Pengisiannya dipecah dua**, mengikuti cara petugas bekerja: Data
   Pelapor sebagai kartu tetap di kolom kiri layar pelayanan (ditulis
   sambil bertanya), keluhan dan catatan di tab **Pengaduan & Catatan**
   pada panel kanan (ditulis sambil mendengarkan). Bentuk pertama
   menempelkan ketujuhnya ke kolom kiri dan tidak muat — barisnya
   tergencet sampai label dan isian saling menimpa. Bentuk kedua memakai
   dialog terpisah; bentuk sekarang inline, sebagai tab yang berbagi
   tempat dengan Menunggu Dilayani. Dikunci test
   `test_isian_pelapor_tidak_saling_menimpa` dan
   `test_kotak_pengaduan_tidak_saling_menimpa` di
   `tests/test_notes_ui.py`.
7. **Panel kanan berpindah tab SENDIRI** mengikuti status loket —
   Menunggu Dilayani selagi kosong, Pengaduan & Catatan begitu nomor
   dipanggil — bukan dikunci di balik modal. Percobaan awal memindahkan
   Menunggu Dilayani ke dialog terpisah ditolak: kolom lama-menunggunya
   sengaja berubah warna setelah 10/20 menit supaya terlihat SEKILAS
   tanpa mengklik apa pun, dan modal akan menguburnya. Judul tab
   Menunggu Dilayani tetap menyebut jumlah yang sudah lama menunggu
   sebagai penggantinya begitu tab itu tidak sedang aktif.
8. **Disimpan selamanya, dihapus manual** oleh ADMIN. Tidak ada pembersihan
   otomatis — yang berarti tabel ini hanya bertambah, dan pencariannya
   sengaja selalu dibatasi jumlah.
9. **Layar Pengaduan & Catatan menyegar sendiri tiap 30 detik**, seperti
   Ringkasan Harian. Penyegaran berkala memakai kriteria pencarian
   TERAKHIR DISUBMIT, bukan membaca `isian_cari` secara langsung — kotak
   itu boleh jadi sedang diketik separuh jalan saat timer kebetulan
   berbunyi, dan pencarian di layar ini sengaja hanya berjalan saat
   Enter/Cari ditekan. Baris yang sedang dibaca dipertahankan lintas
   penyegaran selama lembarnya masih ada di hasil yang baru — dicocokkan
   lewat id, bukan indeks baris.

### Langkah berikutnya

**Build .exe** setelah commit:

```powershell
.\build.ps1
```

`dist/` tertinggal beberapa commit.

Lalu uji terima di komputer sungguhan — lihat bagian 8.

---

## 6. Peran tiap komputer — dua berkas, dua pertanyaan

Setiap komputer menjawab dua pertanyaan yang berbeda. Jawabannya disimpan
di dua berkas TERPISAH di folder database mesin itu, dan keduanya diabaikan
git: isinya sifat satu mesin, bukan isi repositori.

| Berkas | Menjawab | Ditulis oleh |
|---|---|---|
| `data/mesin.json` | peran terhadap **database**: sendiri / server / klien | dialog "Atur komputer ini" |
| `data/peran.json` | peran terhadap **pengunjung**: dipakai sebagai apa | dialog yang sama, bagian kedua |

**`mesin.json` JANGAN pernah disalin antar-komputer** — ia memuat kata
sandi database. `peran.json` justru sebaliknya: ia dirancang untuk disalin
lewat Notepad, karena lima komputer loket isinya sama persis. Ada test yang
menjaga sandi dan alamat server tidak pernah bocor ke berkas yang boleh
disalin itu.

### Peran yang dikenali

| Peran | Layar yang dibuka | Pencetak | Suara | Bentuk layar |
|---|---|---|---|---|
| `petugas` / `admin` | layar masing-masing | tidak mencetak | ikut pengaturan | ikut pengukuran |
| `anjungan` / `anjungan-totem` | anjungan | ikut pengaturan | **diam** | ikut pengukuran |
| `televisi` | papan antrean | tidak mencetak | ikut pengaturan | ikut pengukuran |
| `papan-memanjang` | papan antrean | tidak mencetak | **diam** | **memanjang** |

Dua baris yang diam punya alasan yang sama: kantor yang memasang televisi
DAN pita di atas pintu akan mendapat dua pengeras suara memanggil nomor
yang sama dengan selisih setengah detik, sepanjang hari.

Peran hanya menyatakan apa yang benar-benar diketahuinya tentang mesin itu.
"Tidak mencetak" adalah fakta tentang komputer loket; tetapi BAGAIMANA
mencetak, bagi mesin yang memang mencetak, tetap keputusan seluruh kantor
lewat `ticket.printer`.

Yang disimpan adalah **pilihan, bukan hasil simpulannya**. `null` berarti
"ikut peran", sehingga perbaikan tabel simpulan di versi berikutnya sampai
ke seluruh komputer tanpa satu pun harus didatangi.

### Urutan kewenangan

```
peran layar         : flag CLI  →  peran.json  →  dialog pilih-mode
pencetak / suara /
bentuk layar        : environment  →  peran.json  →  pengaturan database
koneksi database    : ANTRIAN_DB_URL  →  mesin.json  →  SQLite lokal
```

Environment sengaja tetap di atas berkas. Pemasangan yang sudah memakai
`setx ANTRIAN_PRINTER` jauh sebelum berkas peran ada harus berperilaku sama
persis sesudahnya.

### Bentuk layar

`display.screen_shape` (bawaan `auto`) memilih antara `lebar`, `memanjang`,
dan `tegak`. Bawaannya hampir selalu cukup — papan mengukur layarnya
sendiri sesudah tampil, lalu MainWindow membangunnya ulang bila bentuknya
ternyata lain.

Satu kasus tidak dapat diukur: panel LED yang menerima HDMI 1920x1080 lalu
memotong sepetak memanjang darinya. Windows melaporkan layar 16:9,
sementara yang menyala berbentuk pita. Untuk itulah pilihan manual ada.

Papan memanjang melepas judul, jam, dan daftar menunggu, menjajarkan kartu
loket mendatar, dan berhenti meminta nomor menunggu dari database.

Rancangan lengkapnya: [peran-komputer.md](peran-komputer.md).

---

## 7. Yang belum pernah diverifikasi manusia

Ini penting dan jangan dianggap selesai:

- **Tampilan GUI secara visual.** Seluruh test berjalan headless
  (`QT_QPA_PLATFORM=offscreen`). Yang terbukti adalah struktur widget dan
  perilakunya, **bukan** bahwa tata letaknya tidak berantakan, teks tidak
  terpotong, atau `showFullScreen()` benar-benar memenuhi layar.
- **Suara panggilan TTS** — nada dan urutannya belum pernah didengarkan
  di komputer sungguhan setelah jeda nada→ucapan ditambahkan.
- **Pemasangan dua mesin publik sekaligus** (televisi + anjungan). Yang
  terbukti adalah pemutar anjungan benar-benar diam; bahwa keduanya tidak
  bersahutan hanya dapat dipastikan dengan mendengarnya di ruangan.
- **Cetak ke printer Windows sungguhan** (`ticket.printer` = `system`).
- **Pemasangan 5 komputer + PostgreSQL sungguhan.** Konkurensi terbukti
  lewat 8 utas dalam satu proses, bukan lewat 5 mesin di jaringan.
- **`docs/acceptance-test.md`** — belum satu bagian pun dijalankan.

---

## 8. Perintah penting

```powershell
# Test harian (SQLite, cepat)
.\.venv\Scripts\python.exe -m pytest tests -q

# Test terhadap PostgreSQL (wajib sebelum rilis)
.\test-postgres.ps1
docker compose down -v          # menghentikan container uji

# Jalankan aplikasi
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m app.main --tv           # televisi ruang tunggu
.\.venv\Scripts\python.exe -m app.main --init-only    # periksa pemasangan

# Build .exe (menjalankan test dan memverifikasi .exe di folder bersih)
.\build.ps1
```

```powershell
# Penimpaan per mesin (mengalahkan pengaturan bersama di database)
setx ANTRIAN_PRINTER system         # pdf | system | none
setx ANTRIAN_SUARA 0                # 1 | 0
setx ANTRIAN_BENTUK_LAYAR memanjang # lebar | memanjang | tegak
setx ANTRIAN_DB_URL "postgresql+psycopg://antrian:sandi@192.168.1.10/antrian"
```

Ketiga yang pertama kini dapat diisi lewat dialog "Atur komputer ini" —
lihat bagian 6. `setx` tetap bekerja dan tetap menang.

Selalu panggil interpreter `.venv` secara eksplisit. Memanggil `pytest`
atau `python` langsung berisiko memakai Python global yang versinya berbeda.

PostgreSQL 17 terpasang di `C:\Program Files\PostgreSQL\17\bin` tetapi
**tidak ada di PATH** — itu keadaan bawaan installer Windows, dan sudah
diantisipasi lewat pengaturan `backup.pg_dump_path`.

---

## 9. Rencana setelah kios selesai

Belum dikerjakan sama sekali, sesuai urutan kepentingannya:

1. **Uji terima di komputer sungguhan.** Ini yang paling menentukan apakah
   sistem layak dipakai, dan tidak ada test otomatis yang bisa
   menggantikannya.
2. **Ikon aplikasi** — masih ikon bawaan PyInstaller.
3. **Laporan historis per rentang tanggal** dan export PDF. Sengaja
   dilewati sebelumnya atas keputusan pemilik; `SurveyService.list_terakhir()`
   dan `DashboardService` sudah menyediakan datanya.
4. **Laporan performa per loket/petugas** — kolom denormalisasi di
   `satisfaction_survey` (`counter_id`, `officer_id`) sudah disiapkan sejak
   awal justru untuk ini.

---

## 10. Cara bekerja yang diharapkan

- Kerjakan satu langkah, jalankan test, baru lanjut. Jangan menumpuk
  perubahan besar tanpa menjalankan test.
- Bila sebuah test gagal, **pahami dulu apakah test-nya yang basi atau
  kodenya yang rusak**. Beberapa test di proyek ini sengaja mengunci aturan
  bisnis — mengubahnya agar hijau berarti membatalkan aturan itu.
- Bila menemukan sesuatu yang belum terbukti jalan, **katakan terus terang**
  daripada membiarkannya tampak selesai. Backup yang belum pernah dijalankan
  adalah backup yang belum tentu ada saat dibutuhkan.
- Test yang dilewati (`skipped`) **bukan** test yang lolos.
