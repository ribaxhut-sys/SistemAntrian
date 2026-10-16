# Dashboard

Dua layar pemantauan yang berbeda sudut pandangnya. Keduanya murni membaca:
tidak ada tombol yang mengubah antrian.

| | Dashboard (admin & supervisor) | Ringkasan Saya (petugas loket) | Ringkasan Saya (pendaftaran) |
|---|---|---|---|
| Menu | **Dashboard** | **Ringkasan Saya** | **Ringkasan Saya** |
| Hak akses | `DASHBOARD_VIEW` | `QUEUE_CALL` | `QUEUE_CREATE` |
| Cakupan | seluruh cabang, **pekerjaan semua petugas** | hanya loket dan nomor milik sesi yang masuk | hanya nomor yang diterbitkan sesi yang masuk |
| Saringan | tanggal, jenis layanan, loket, petugas | tanggal | tanggal |
| Sumber kode | `DashboardService.ringkasan()` | `ringkasan_petugas(tanggal)` | `ringkasan_pendaftaran(tanggal)` |
| Tampilan | `dashboard_page.py` | `petugas_page.py` (`DashboardPetugasPage`) | `petugas_page.py` (`DashboardPendaftaranPage`) |

Setiap akun melihat pekerjaannya sendiri berdasarkan login; admin dan
supervisor melihat tabel **Pekerjaan setiap petugas** (diterbitkan,
dipanggil, selesai, tidak hadir, dilewati, dibatalkan, rata-rata pelayanan,
kepuasan) yang mengikuti tanggal dan saringan.

## Peran dan permission

Tidak ada permission baru. Yang dipakai:

| Permission | Dipakai untuk | Pemegang |
|---|---|---|
| `DASHBOARD_VIEW` | membuka Dashboard dan pilihan saringannya | `ADMIN`, `SUPERVISOR` |
| `QUEUE_CALL` | membuka Ringkasan Saya (petugas loket) | `CRO` |
| `QUEUE_CREATE` | membuka Ringkasan Saya (pendaftaran) | `REGISTRATION` |
| `CONFIG_MANAGE` | membaca aktivitas terakhir (audit log) di Dashboard | `ADMIN` |
| `REPORT_VIEW`, `MASTER_MANAGE`, `CONFIG_MANAGE`, `BACKUP_MANAGE` | tombol akses cepat | sesuai peran |

Perubahan: `ADMIN` kini memegang `DASHBOARD_VIEW` (sebelumnya hanya
`SUPERVISOR`). `SUPERVISOR` melihat layar yang sama, tetapi tombol akses
cepat dan audit log hanya muncul bila sesinya memang berhak.

Hak akses ditegakkan **di service** (`require_permission`), bukan hanya
dengan menyembunyikan menu: `CRO`, `REGISTRATION`, dan `DISPLAY` ditolak
`ringkasan()`; `ADMIN`, `SUPERVISOR`, `REGISTRATION`, dan `DISPLAY`
ditolak `ringkasan_petugas()`; `SUPERVISOR` ditolak `aktivitas_terakhir()`.

`ringkasan_petugas()` **tidak menerima id petugas atau loket**. Cakupannya
ditentukan dari sesi dan loket bawaan akun di database, sehingga petugas
tidak dapat meminta data rekannya dengan memanggil service langsung.

## Isi Dashboard (admin & supervisor)

- Angka sekilas: total, menunggu, sedang dilayani, selesai, batal atau dilewati.
- Waktu dan capaian: belum selesai, rata-rata menunggu, rata-rata pelayanan,
  porsi tuntas dilayani.
- Grafik nomor terbit per jam.
- Antrian per jenis layanan (jenis layanan tanpa nomor tetap tampil bernilai 0).
- Papan loket dan petugas: aktif, istirahat, atau tidak aktif.
- Rincian per delapan status, kepuasan (survey).
- Akses cepat: Laporan Detail, Data Master (pengguna, petugas, loket, jenis
  layanan), Pengaturan, Backup & Pemulihan, Kesehatan Sistem.
- Aktivitas terakhir (audit log), hanya untuk `ADMIN`. Audit log lengkap
  tetap ada di menu **Backup**.
- Tombol **Segarkan**, kotak **Segarkan otomatis** (jeda dari
  `dashboard.refresh_seconds`, minimal 5 detik).

## Isi Ringkasan Saya (petugas)

- Nama petugas, loket, dan status (aktif, istirahat, loket dinonaktifkan,
  loket belum dipilih).
- Nomor yang sedang dipegang beserta lama sejak dipanggil.
- Antrean berikutnya untuk loket ini dan jumlah yang tersisa.
- Hitungan hari ini: selesai, tidak hadir, dilewati, dibatalkan, rata-rata
  pelayanan.
- Riwayat nomor yang ditangani petugas hari ini (30 terbaru).
- Peringatan: loket belum dipilih, loket istirahat, loket dinonaktifkan,
  tidak ada antrean.
- Tombol **Buka Pelayanan**. Tindakan (panggil berikutnya, panggil ulang,
  selesai, lewati, batalkan) tetap hanya di menu **Pelayanan**; lihat
  [catatan desain](#catatan-keputusan-desain).

"Selesai bertugas" adalah tombol **Keluar** (logout), yang melepas tanda
hadir petugas di loketnya; layar ini tidak dapat dibuka setelahnya.

## Definisi metrik

Semua angka dihitung dari satu tanggal (`queue_date`) di cabang sesi, lalu
disaring. Waktu memakai `clock` (WIB, tanpa zona).

| Metrik | Definisi |
|---|---|
| Total antrian | Jumlah baris `queue` pada tanggal dan saringan |
| Menunggu | Status `WAITING` |
| Sedang dilayani | Status `CALLED`, `SERVING`, atau `PAUSED` |
| Selesai | Status `COMPLETED` |
| Batal atau dilewati | Status `CANCELLED`, `NO_SHOW`, atau `SKIPPED` |
| Belum selesai | Total dikurangi (`COMPLETED` + `NO_SHOW` + `CANCELLED`); nomor dilewati masih dihitung |
| Rata-rata menunggu | Rata-rata `called_at − created_at` untuk nomor yang pernah dipanggil |
| Rata-rata pelayanan | Rata-rata `completed_at − serving_at` untuk nomor `COMPLETED` yang punya kedua waktu |
| Tuntas dilayani | `COMPLETED` ÷ (`COMPLETED` + `NO_SHOW` + `CANCELLED`); `-` bila belum ada yang tuntas |
| Per jam | Jumlah nomor menurut jam `created_at` (terbit), 24 butir |
| Per jenis layanan | Jumlah nomor per kategori daun (kelompok menu tidak ditampilkan) |
| Status loket | `Tidak aktif` bila loket dinonaktifkan atau tanda hadir petugas lebih tua dari `BATAS_HADIR_PETUGAS_DETIK` (90 detik); `Istirahat` bila `on_break`; selain itu `Aktif` |
| Nomor aktif loket | Nomor `CALLED`/`SERVING`/`PAUSED` yang dipegang loket **saat ini** (tidak mengikuti tanggal saringan) |
| Diterbitkan (per petugas) | Jumlah audit `CREATE_QUEUE` milik petugas untuk nomor bertanggal itu; tidak dihitung bila saringan loket aktif |
| Pekerjaan petugas | Nomor menurut `served_by_user_id`; dipanggil = punya `called_at` |
| Kepuasan | Rating survey yang `submitted_at`-nya pada tanggal itu, disaring menurut layanan/loket/petugas yang sama |

Catatan saringan: menyaring menurut **loket** atau **petugas** hanya
mencakup nomor yang sudah dipanggil, sehingga "Menunggu" bernilai 0.
Petugas dipetakan dari `served_by_user_id`.

Nilai tanpa data tampil `—`, bukan `0`: keduanya berbeda arti.

Rata-rata menunggu/pelayanan dihitung oleh `DashboardService.ringkasan()`
di Python, bukan `QueueRepository.rata_rata_durasi()` (SQL). Definisinya
sama; ringkasan harian lama (`ringkasan_hari_ini`) tetap memakai repository
dan dipertahankan untuk pemanggil yang sudah ada.

## Sumber data

| Data | Tabel | Query |
|---|---|---|
| Nomor dan waktu | `queue` | satu `SELECT` kolom pada tanggal + saringan |
| Layanan | `service_category` | satu `SELECT` (daun, per cabang) |
| Loket + petugas | `counter` ⟕ `app_user` | satu `SELECT` dengan join |
| Nomor aktif per loket | `queue` | satu `SELECT` (hari ini) |
| Survey | `satisfaction_survey` | satu `SELECT` rating |
| Audit | `audit_log` | `audit_service.list_terakhir` (tanpa kolom `meta`) |
| Petugas: loket & antrean | `app_user`, `counter`, `queue` | `get` + `list_menunggu` + `SELECT` riwayat |

Tidak ada query per baris (tanpa N+1). Seluruh pembacaan berada dalam
satu `session_scope`.

## Menjalankan dan menguji

```powershell
# Aplikasi (login sebagai admin, supervisor, atau petugas CRO)
.\.venv\Scripts\python.exe -m app.main

# Test dashboard, di PostgreSQL uji (database yang boleh dikosongkan)
$env:ANTRIAN_DB_URL = "postgresql+psycopg://postgres:<sandi>@127.0.0.1:5432/antrian_uji"
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_operasional.py tests/test_dashboard_ui.py tests/test_dashboard_service.py -q
.\.venv\Scripts\python.exe -m ruff check .
```

Cakupan test: hak akses per peran, hitungan per status, rata-rata waktu,
saringan tanggal/layanan/loket/petugas, tanpa data, beberapa loket berjalan
bersamaan, status loket, survey tersaring, kegagalan memuat, dan menu per
peran. Kompatibilitas dialect terjaga karena angka dihitung di Python;
proyek ini diuji di PostgreSQL (lihat `docs/panduan-proyek.md`).

## Menambah metrik baru

1. Tambahkan kolom yang dibutuhkan ke `select` di
   `DashboardService.ringkasan()` (atau `ringkasan_petugas()`).
2. Hitung di loop agregasi yang sudah ada; jangan membuat query terpisah.
3. Tambahkan field ke `DashboardOperasional` / `DashboardPetugas`.
4. Tampilkan di `dashboard_page.py` / `petugas_page.py` (`KartuAngka`).
5. Tulis test di `tests/test_dashboard_operasional.py`, catat definisinya
   di tabel di atas.

## Perubahan database

Tidak ada migrasi dan tidak ada perubahan skema. Seluruh data berasal dari
tabel dan kolom yang sudah ada.

## Catatan keputusan desain

- **Satu layar admin/supervisor.** Admin dan supervisor sama-sama
  memantau; yang membedakan hanya tombol akses cepat dan audit log, yang
  dikendalikan permission, bukan dua salinan layar.
- **Tombol aksi petugas tetap di Pelayanan.** Menggandakan tombol panggil,
  selesai, lewati, dan batalkan membuat dua layar yang mengubah nomor yang
  sama, beserta aturan survey, pengaduan, dan konfirmasi di dalamnya.
  Ringkasan Saya hanya memantau dan membawa petugas ke Pelayanan.
- **Hitung di Python, bukan SQL per dialect.** Sama seperti laporan:
  hasilnya identik di semua database dan barisnya hanya satu hari.
- **Audit log tanpa `meta`.** Kolom itu memuat rincian internal yang tidak
  perlu tampil di ringkasan.
- **Kegagalan memuat tidak menampilkan dialog.** Penyegaran otomatis akan
  menumpuk dialog bila database mati; pesan sebaris menggantikannya dan
  angka terakhir yang berhasil dimuat tetap tampil.
- **Grafik digambar sendiri** (`GrafikBatang`); 24 batang tidak sepadan
  dengan dependensi pustaka grafik.

## Riwayat perubahan

- 2026-10-15 (lanjutan) — Tabel pekerjaan setiap petugas di Dashboard;
  Ringkasan Saya dapat dibuka per tanggal; Ringkasan Saya untuk petugas
  pendaftaran (nomor yang diterbitkannya).
- 2026-10-15 — Dashboard admin/supervisor dengan saringan, papan loket,
  grafik per jam, akses cepat, dan audit log; menu **Ringkasan Saya** untuk
  petugas loket. `ADMIN` mendapat `DASHBOARD_VIEW`. Menu **Ringkasan
  Harian** dinamai ulang **Dashboard**.
