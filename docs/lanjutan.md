# Melanjutkan Pekerjaan — Sistem Antrian & Survey Kepuasan CRO

Dokumen serah terima. Berisi tujuan, keadaan sekarang, apa yang belum
selesai, dan hal-hal yang **jangan** diubah beserta alasannya.

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
mode kios memunculkan bilah yang sengaja tidak dibangun, lengkap dengan path
database di depan pengunjung. Sudah dijaga di `MainWindow.muat_ulang_halaman`.

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
| SQLite | **623 lolos** |
| PostgreSQL | **598 lolos, 25 dilewati** |

Skip PostgreSQL lebih banyak dari 6 yang tercatat sebelumnya. Test
`sqlite_saja` memang dilewati; sisanya hampir seluruhnya backup karena
`pg_dump`/`pg_restore` tidak ada di PATH mesin pengembang. **Backup
PostgreSQL belum terbukti pada putaran ini.**

Yang paling menentukan dan **sudah terbukti hijau di PostgreSQL**:
`tests/test_queue_numbering.py::test_penerbitan_bersamaan_tidak_menghasilkan_nomor_kembar`
— 8 utas × 12 nomor memperebutkan satu baris sequence.

---

## 5. Kios pengunjung — SUDAH di-commit

Kios tanpa login, `--layar`, jeda pengambilan, GRANT PostgreSQL, dan
dokumentasinya sudah masuk tree. Test UI kios sudah dijalankan (bukan
hanya test service).

### Keputusan desain yang sudah disepakati pemilik

1. **Dialog pilihan saat start** — "Layar Pengunjung" atau "Layar Petugas".
   Pengunjung langsung masuk tanpa login; petugas wajib login.
2. **Argumen `--layar`** melewati dialog itu. Dipasang pada shortcut
   Startup komputer kios supaya mati listrik tidak berhenti di dialog.
3. **User PostgreSQL terpisah** untuk mesin kios, **tanpa akses `app_user`**.
   Skripnya: [sql/kios-grant.sql](sql/kios-grant.sql).
4. **Jeda antar-pengambilan nomor** (`kiosk.cooldown_seconds`, bawaan 10
   detik). Hanya sesi kios — meja pendaftaran tidak ikut diperlambat.
5. Kegagalan di layar kios memakai **label sebaris**, bukan `QMessageBox`.

### Langkah berikutnya

**Build .exe** setelah commit:

```powershell
.\build.ps1
```

`dist/` tertinggal beberapa commit.

Lalu uji terima di komputer sungguhan — lihat bagian 8.

---

## 6. Yang belum pernah diverifikasi manusia

Ini penting dan jangan dianggap selesai:

- **Tampilan GUI secara visual.** Seluruh test berjalan headless
  (`QT_QPA_PLATFORM=offscreen`). Yang terbukti adalah struktur widget dan
  perilakunya, **bukan** bahwa tata letaknya tidak berantakan, teks tidak
  terpotong, atau `showFullScreen()` benar-benar memenuhi layar.
- **Suara panggilan TTS** — belum pernah didengarkan.
- **Cetak ke printer Windows sungguhan** (`ticket.printer` = `system`).
- **Pemasangan 5 komputer + PostgreSQL sungguhan.** Konkurensi terbukti
  lewat 8 utas dalam satu proses, bukan lewat 5 mesin di jaringan.
- **`docs/acceptance-test.md`** — belum satu bagian pun dijalankan.

---

## 7. Perintah penting

```powershell
# Test harian (SQLite, cepat)
.\.venv\Scripts\python.exe -m pytest tests -q

# Test terhadap PostgreSQL (wajib sebelum rilis)
.\test-postgres.ps1
docker compose down -v          # menghentikan container uji

# Jalankan aplikasi
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m app.main --layar        # langsung kios
.\.venv\Scripts\python.exe -m app.main --init-only    # periksa pemasangan

# Build .exe (menjalankan test dan memverifikasi .exe di folder bersih)
.\build.ps1
```

Selalu panggil interpreter `.venv` secara eksplisit. Memanggil `pytest`
atau `python` langsung berisiko memakai Python global yang versinya berbeda.

PostgreSQL 17 terpasang di `C:\Program Files\PostgreSQL\17\bin` tetapi
**tidak ada di PATH** — itu keadaan bawaan installer Windows, dan sudah
diantisipasi lewat pengaturan `backup.pg_dump_path`.

---

## 8. Rencana setelah kios selesai

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

## 9. Cara bekerja yang diharapkan

- Kerjakan satu langkah, jalankan test, baru lanjut. Jangan menumpuk
  perubahan besar tanpa menjalankan test.
- Bila sebuah test gagal, **pahami dulu apakah test-nya yang basi atau
  kodenya yang rusak**. Beberapa test di proyek ini sengaja mengunci aturan
  bisnis — mengubahnya agar hijau berarti membatalkan aturan itu.
- Bila menemukan sesuatu yang belum terbukti jalan, **katakan terus terang**
  daripada membiarkannya tampak selesai. Backup yang belum pernah dijalankan
  adalah backup yang belum tentu ada saat dibutuhkan.
- Test yang dilewati (`skipped`) **bukan** test yang lolos.
