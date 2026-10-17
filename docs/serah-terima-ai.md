# Serah Terima untuk AI (Codex dan Claude)

Proyek ini dikerjakan bergantian oleh dua asisten AI, **Codex** dan
**Claude**, di bawah arahan satu pemilik. Dokumen ini adalah **satu sumber
kebenaran** tentang keadaan sekarang, aturan kerja, dan apa yang belum
selesai. Baca sebelum mengubah apa pun, dan **perbarui** di akhir setiap
sesi (bagian 3, 6, dan 9 paling sering berubah).

`AGENTS.md` (dibaca Codex) dan `CLAUDE.md` (dibaca Claude) di akar repo
hanya ringkasan aturan dan menunjuk ke sini. Jangan menyalin isi dokumen ini
ke sana; cukup perbarui di satu tempat.

Dokumen lain yang tetap berlaku: [lanjutan.md](lanjutan.md) (aturan kode dan
jebakan; bagian riwayat commit-nya sudah lama), [istilah.md](istilah.md),
[panduan-proyek.md](panduan-proyek.md), [android-kiosk.md](android-kiosk.md),
[layar-antrian.md](layar-antrian.md), [prioritas-antrian.md](prioritas-antrian.md),
[keamanan-sesi.md](keamanan-sesi.md).

Terakhir diperbarui: **17 Oktober 2026**, oleh Codex.

---

## 1. Aturan kerja bersama

**Bahasa.** Semua jawaban kepada pemilik dalam **Bahasa Indonesia**. Nama
fungsi, variabel, docstring, komentar, dan pesan commit juga Indonesia.
Docstring menjelaskan **mengapa**, bukan mengulang kodenya.

**Aturan kode** ada di [lanjutan.md](lanjutan.md) bagian 2 (lapisan UI →
service → repository, DTO `@dataclass(frozen=True)`, jebakan Qt, dan
seterusnya). Tambahan yang berlaku sekarang:

- Otorisasi ditegakkan di **service layer**, bukan hanya disembunyikan di UI
  (contoh: `create_queue` menolak prioritas dari peran selain yang berhak).
- Perubahan skema selalu lewat migrasi Alembic yang **menambah** kolom
  nullable; data lama tidak boleh berubah.

**Pengujian.**

- Pakai interpreter proyek: `.\.venv\Scripts\python.exe -m pytest ...`.
  `python` biasa menunjuk Python sistem tanpa PySide6.
- **Semua tes di PostgreSQL** database uji `antrian_uji` (URL ada di
  `~/.antrian-uji-db`). Jangan pernah menguji di database kerja `antrian`
  (fixture menjalankan `DROP SCHEMA`). Tanpa SQLite.
- **Satu proses pytest pada satu waktu** terhadap `antrian_uji`. Dua proses
  bersamaan saling merusak.
- Selama iterasi jalankan **tes terarah** (modul yang diubah dan
  tetangganya) dan `ruff check app tests alembic`. **Suite penuh** (±10–12
  menit, 1767 lulus) hanya **sekali sebelum push atau PR**; CI GitHub
  menjalankannya lagi.
- `build-installer.ps1` menjalankan tesnya sendiri, jadi lebih lama.

**Git.**

- **Jangan push** kecuali pemilik memintanya. Commit lokal boleh bila
  diminta.
- Periksa `git status` tepat sebelum commit; berkas bersama bisa tersapu
  sesi lain. Commit hanya berkas milik pekerjaan itu.
- Setiap PR diberi **Auto-fix** (`set_monitor auto_fix=true`) tanpa bertanya.
- Pesan commit Indonesia, diakhiri baris `Co-Authored-By:` asisten yang
  mengerjakan.

**Versi.**

- **Aplikasi Windows**: `app/__init__.py`, `build-installer.ps1`,
  `installer.iss`, README. Naik hanya saat pemilik meminta installer baru.
- **APK anjungan**: `android-kiosk/app/build.gradle`. **Jangan menaikkan
  versi per perubahan**; kumpulkan perubahan Android sampai pemilik meminta
  rilis. Naikkan angka **terakhir** (2.4.33 → 2.4.34), tidak melompat ke
  minor. Versi yang benar-benar dibagikan ada di `apk/anjungan.json`.

**Jangan mengubah pengaturan keamanan perangkat pemilik** (mis. mengaktifkan
ADB BlueStacks). Minta pemilik melakukannya.

**Sebelum migrasi ke database kerja** (`antrian`): backup dulu
(`pg_dump -Fc` ke folder `backup/`), jalankan migrasi, verifikasi jumlah
baris. Jangan menaruh APK baru di `apk/` tanpa persetujuan: komputer
pengembang ini juga berperan sebagai server, dan tablet yang tersambung
memperbarui diri dari folder itu. Selalu salin isi lama ke
`backup/apk-sebelum-<versi>/` dulu.

**Memeriksa permintaan terhadap aplikasi.** Cocokkan tiap permintaan dengan
kode, dokumen, dan tes sebelum mengerjakan; bila tidak cocok dengan keadaan
aplikasi, laporkan ketidakcocokannya (pernah terjadi: "petugas pendaftaran"
ternyata tidak ada di lapangan).

---

## 2. Gambaran sistem (ringkas)

Empat bagian, rinci di [istilah.md](istilah.md):

| Bagian | Perangkat | Kode |
|---|---|---|
| Anjungan | Tablet Android + printer thermal | `android-kiosk/app` |
| Layar antrian | Panel Android Maxtor | `android-kiosk/layar` |
| Aplikasi server | PC Windows peran server: PostgreSQL + API (port 8765) | `app/kiosk_api.py` |
| Aplikasi petugas | PC Windows tiap loket | `app/` (PySide6) |

Di lapangan **tidak ada petugas pendaftaran**: pengunjung mengambil nomor
sendiri di anjungan, dan yang ada hanya petugas yang melayani (CRO) dan
petugas yang berjaga tanpa perangkat. Panel layar antrian: **Maxtor
MDDW-55DS** (55 inci; resolusi belum terverifikasi). Ukuran fisik panel
anjungan/layar yang disebut pemilik ±120 × 27 cm (rasio ±4,4 : 1, panel
memanjang).

---

## 3. Keadaan sekarang (17 Oktober 2026)

**Cabang kerja:** `fitur/tema-tampilan-dan-kartu-berikutnya`, dibuat dari
`origin/main` (PR #2 sudah ter-merge). **Belum di-push**, belum ada PR. Isinya
commit berikut di atas `main`:

| Commit | Isi |
|---|---|
| `31e83b2` | Tema tampilan petugas, kartu "Berikutnya & hari ini", perbaikan audit |
| `33664be` | Nomor prioritas dan urutan panggil 3:1 |
| `885cb52` | Prioritas mandiri dari anjungan, petugas pelayanan menandai |
| `5426aa7` `da92546` | Layar penuh tanpa bingkai; penyatuan versi APK |
| `e5944c3` | Prioritas **ditandai hanya di anjungan**, **dicabut hanya oleh petugas** |
| `96437f7` | `.gitignore` salinan APK sebelum rilis |
| `ac4c5f4` | Video lewat TextureView; label "Sentuh layar" di paling atas |
| `62f3878` | Aplikasi Windows 1.0.10 |
| `178d088` | Salinan media: status per tablet, Segarkan media, Salin dari server |
| `37fb744` | Tempat tampil per berkas: panel atas / layar penuh / keduanya |
| `543d5f3` | Anjungan 2.4.34.1 |
| `eea7ab2` | Dokumentasi serah terima untuk Codex dan Claude |
| `338783c` | PIN pengaturan anjungan di server (hash, verifikasi, dialog admin) |
| (berikutnya) | Android: papan PIN, mode putar saja, tempat tampil folder tablet |

**Versi.**

| | Dikodekan | Dibangun | Dibagikan/terpasang |
|---|---|---|---|
| Aplikasi Windows | 1.0.11 | belum dibangun (terakhir `dist\AntrianCRO-Setup-1.0.10.exe`) | belum dipasang di PC mana pun |
| APK anjungan | 2.4.34.2 (kode 52) | belum dibangun rilis (hanya debug) | `apk/` masih 2.4.34.1; belum ada panel asli |
| APK layar antrian | 1.5 (kode 6) | `dist\AntrianLayar-1.5.apk` | tidak berubah |
| `VERSI_MINIMAL` APK (server) | 49 | | tablet 2.4.33 tetap diterima |

**Migrasi Alembic** (head: `e9c3b5a7d281`):
`c3f8a1d7e592` kolom `queue.prioritas` → `d6a1f3b8c704` `queue.prioritas_asal`
→ `e9c3b5a7d281` status salinan media di `kiosk_device`.

**Database.**

- `antrian_uji`: sudah di head; di-reset dan di-seed ulang selama audit Codex
  16 Oktober 2026. Semua tes audit setelah koreksi dijalankan dengan URL
  PostgreSQL `antrian_uji` yang diverifikasi eksplisit; SQLite tidak dipakai lagi.
- `antrian` (kerja): di `d6a1f3b8c704`. **`e9c3b5a7d281` belum diterapkan**;
  berjalan otomatis saat aplikasi Windows dibuka berikutnya. Backup sebelum
  migrasi prioritas: `backup/queue-20261016-102726-sebelum-prioritas.dump`.
- Akun uji (hanya `antrian_uji`): `cro` / `rahasia123`. Akun kerja: `admin`,
  `daffa` (CRO), `daffa2` (CRO); kata sandinya milik pemilik, jangan
  dicari atau disimpan.

**Proses yang berjalan di komputer ini.**

- API anjungan (port 8765) memakai **kode lama**. Harus dimulai ulang agar
  `priority_enabled`, `media_refresh`, `show`, dan endpoint `media-library`
  tersedia untuk tablet. Jenis prosesnya (layanan atau tugas terjadwal)
  belum diperiksa.
- Aplikasi Windows yang terbuka juga memakai kode sebelum perubahan
  terakhir; tutup dan buka ulang.

---

## 4. Fitur yang ditambahkan Oktober 2026

### 4.1 Tab Tampilan dan tema petugas

- Menu **Tampilan** (paling kanan) untuk semua akun kecuali layar antrian/kios;
  8 tema: Indigo (bawaan), Samudra, Zamrud, Pasir, Sakura, Merdeka, Malam,
  Kontras Tinggi. Disimpan **per komputer** di `tampilan.json` (folder
  database, di-`.gitignore`; override env `ANTRIAN_TAMPILAN_PATH`).
- Kode: `app/ui/tema_petugas.py` (mengubah warna hex pada stylesheet jadi,
  tidak menyentuh puluhan modul), `app/ui/tampilan_page.py`, wiring di
  `MainWindow._susun_menu` (`MENU_TAMPILAN`, `pelengkap`, `tanpa_peran`) dan
  `app/main.py` (`terapkan_tema(app, baca_tema())`).
- **Penjaga kontras otomatis** (rasio ≥ 4,5; 7 pada Kontras Tinggi; 3 untuk
  tombol nonaktif). Tes: `tests/test_tema_petugas.py`.
- Cara kerja memakai monkeypatch global `QWidget.setStyleSheet`,
  `QLabel.setText`, `QTableWidgetItem.setForeground/Background`
  (dipasang sekali). Pilihan sadar; alternatifnya lapisan gaya terpusat yang
  mengubah puluhan modul. Kode yang menggambar sendiri dengan QPainter
  harus memakai `warna_tema()` (contoh: grafik di `dashboard_page.py`).
- Tes yang menyentuh tema **harus mengembalikan** stylesheet/palet aplikasi
  (lihat fixture `_kembalikan_tema`), kalau tidak tes tata letak lain gagal.

### 4.2 Halaman Pelayanan

- **Papan tunggu** (`app/ui/queue/papan_tunggu.py`) pindah ke tab
  *Menunggu Dilayani*, berbentuk kartu per layanan + kartu **Semua**; kartu
  **dapat diklik untuk menyaring** tabel di bawahnya. Tingginya mengikuti isi.
- **Kartu "Berikutnya & hari ini"** (`kartu_berikutnya.py`) di kolom kiri,
  memakai sisa tinggi dan tidak tampak bila terlalu sempit (tidak pernah
  membuat halaman bergulir).
- Tombol **Mulai Istirahat** sejajar dengan kotak Loket dan Jenis Layanan.
- Menu atas (pil) di tengah vertikal; tab "Pengaduan && Catatan" (dua `&`).

### 4.3 Nomor prioritas — dokumen rinci: [prioritas-antrian.md](prioritas-antrian.md)

- **Ditandai hanya di anjungan** (kotak "Saya lansia / disabilitas / ibu
  hamil" di menu awal; `priority` pada `POST /v1/kiosk/tickets`) atau oleh
  petugas pendaftaran bila suatu saat ada. **Dicabut hanya oleh petugas
  pelayanan** (`QueueService.cabut_prioritas`). Petugas pelayanan **tidak
  bisa menandai**; ada tesnya.
- Kolom `queue.prioritas` (`LANSIA/DISABILITAS/IBU_HAMIL/PRIORITAS`) dan
  `prioritas_asal` (`PENDAFTARAN/MANDIRI`).
- Urutan: `app/services/urutan_prioritas.py` (fungsi murni). Otomatis 3
  prioritas : 1 biasa (`queue.rasio_prioritas`, 0 = prioritas selalu dulu);
  pilihan petugas **Prioritas dulu / Biasa dulu** berlaku satu panggilan.
  Dipakai `call_next`, `list_waiting`, layar antrian, anjungan, sisa antrian
  di tiket, dan dashboard petugas.
- Saklar `kiosk.prioritas_aktif`; `priority_enabled` pada `/v1/kiosk/display`.
- Audit: `CREATE_QUEUE` (dengan alasan dan asal), `CLEAR_PRIORITY`.
- UI: ★ di tabel dan kartu, pita "★ PRIORITAS · … · dipilih pengunjung,
  mohon periksa" + tombol **Cabut prioritas** di kartu nomor aktif.
  Tiket mencetak "· Prioritas" pada baris layanan.

### 4.4 Anjungan Android (2.4.34.1)

- **Kotak prioritas** di menu awal, dikosongkan tiap tiket terbit/dibatalkan/
  masuk iklan layar penuh. Kartu layanan dikurangi tingginya (`dp(66)`).
- **Iklan layar penuh tanpa bingkai**: margin, padding, sudut, garis tepi
  dihapus di atas latar hitam (`bukaBingkaiIklanPenuh`). Rasio video dijaga
  (pas). Label **"Sentuh layar…"** kini **panel tetap di ATAS layar** (navy pekat, tinggi ±12% layar memanjang / ±8% layar tegak, 44–96 dp); video di bawahnya, fit tanpa terpotong (`tampilkanPanelAjakanIklan`; sebelumnya strip gradasi di dasar yang muncul-hilang). Belum diuji di perangkat, hanya dikompilasi.
- **Pemutar video `VideoTekstur`** (TextureView + MediaPlayer) menggantikan
  `VideoView`. Alasan: di BlueStacks `VideoView` (SurfaceView) tampil hitam
  padahal pemutar berjalan (decoder perangkat lunak mengeluarkan buffer
  YV12 yang tidak dikomposisi). **Belum terbukti memperbaikinya di
  perangkat** (lihat bagian 6).
- **Tempat tampil per berkas**: `daftar_putar.Butir.tampil`
  (`panel/penuh/keduanya`), `welcome_media_files[].show`. Panel atas memutar
  *Panel atas*+*Keduanya*; layar penuh memutar *Layar penuh*+*Keduanya*;
  bila tidak ada media layar penuh, layar penuh **tidak aktif** (tidak
  dipaksa). Dialog **Atur jadwal…** punya kolom **Tampil di**.
- **Salinan media** ([android-kiosk.md](android-kiosk.md), bagian
  "Salinan media"): kolom **Media** di kartu perangkat (status tersalin),
  tombol **Segarkan media** (`media_refresh`), dan **Salin dari server**
  (`/v1/kiosk/media-library`) di Kelola media tablet.

- **Panggilan mengalahkan iklan** ([android-kiosk.md](android-kiosk.md),
  bagian "Panggilan mengalahkan iklan"): panggilan/panggilan ulang petugas
  menghentikan iklan layar penuh, banner nomor ±6 detik, hitungan menganggur
  diulang. Setelan **Panggilan menghentikan iklan** (grup Iklan Anjungan,
  `kiosk.panggilan_hentikan_iklan`, API `call_interrupts_ad`; per loket
  `call_count`). Dibangun sebagai APK debug, **belum diverifikasi di perangkat**
  dan belum dirilis.

- **Dialog Media di tablet ini** dirombak (ringkasan, kelompok Video/Gambar,
  gambar mini, menu Aksi, Hapus semua); lihat android-kiosk.md. APK debug saja,
  belum diverifikasi di perangkat.

- **Warna kilau bebas** per tablet (pemilih warna + hex); lihat android-kiosk.md.
  APK debug saja, belum diverifikasi di perangkat.

- **Bintang prioritas** pada nomor menunggu (anjungan, layar Android, layar
  Windows), tanpa alasan; kini bintang kecil di pojok kiri atas ubin + latar amber lembut (bukan lagi " ★" di belakang nomor); lihat android-kiosk.md. APK debug saja, belum diuji di perangkat.

- **Panel keluar sebelum iklan muncul** dan **kotak prioritas di atas tombol
  layanan**; lihat android-kiosk.md. APK debug saja, belum diuji di perangkat.

### 4.4b PIN pengaturan anjungan dan mode putar saja

Rinci di [android-kiosk.md](android-kiosk.md) (bagian "PIN pengaturan dan
mode putar saja"). Ringkas: PIN 6 angka satu untuk semua tablet, diatur admin
di Layanan Anjungan (server menyimpan hash PBKDF2-SHA1; kode
`app/services/pin_anjungan.py`, API `POST /v1/kiosk/pin/verifikasi`,
`settings_pin` pada `/v1/kiosk/display`). Server tidak terjangkau ≥ 30 detik →
anjungan hanya memutar video (jalan pulih: tahan pojok kiri bawah 5 detik +
PIN). Media dari server mengikuti aturan server; media dari folder tablet
mengikuti aturan tablet (tombol tempat tampil di Kelola media tablet).
Keputusan pemilik: PIN diatur sekali di server; tanpa server semua fitur
mati kecuali video. **Belum dirilis** (APK `apk/` masih 2.4.34.1 tanpa ini).

### 4.5 Keamanan login

- Penundaan login **bertingkat** per nama pengguna, dihitung dari audit
  `LOGIN_FAILED` (jendela 15 menit; 5–7 gagal → 1 menit, 8–9 → 5 menit, ≥10
  → 15 menit; dikosongkan oleh login berhasil atau pemulihan admin).
  Tombol "Lupa kata sandi admin?" baru muncul setelah 3 kali gagal.
  Rinci: [keamanan-sesi.md](keamanan-sesi.md).

### 4.6 Pembaruan aplikasi Windows

- `GET /v1/windows/update` dan `/download`, pita pembaruan di aplikasi,
  installer 1.0.10. Folder `pembaruan` di komputer server berisi
  `Pembaruan-AntrianCRO.exe` + `.version`.

---

## 5. Keputusan pemilik (jangan dibalik tanpa bertanya)

1. Prioritas ditandai **di anjungan** oleh pengunjung (dibantu petugas
   berjaga lisan), dicabut oleh petugas pelayanan. Kategori: lansia,
   disabilitas, ibu hamil. Urutan 3:1, rasio dapat diatur admin, petugas
   dapat memilih langsung.
2. Anjungan memutar **video layar penuh saat menganggur, sentuhan kembali ke
   menu**; layar penuh harus memenuhi **seluruh layar tanpa terpotong**.
   Video untuk panel atas dan layar penuh **dibedakan**.
3. Versi APK tidak dinaikkan per perubahan; format `2.4.34.1` dipakai pemilik
   untuk rilis berikutnya.
4. Tema ada 8, termasuk **Sakura** (pink) dan **Merdeka** (merah putih).
5. Suite penuh hanya sebelum push; **tidak push tanpa diminta**.

---

## 6. Belum selesai / belum terverifikasi

**Belum terverifikasi di perangkat** (ADB BlueStacks sering menolak perintah
dengan `error: closed`):

- Pemutar `VideoTekstur` apakah benar menampilkan video di BlueStacks.
- Papan PIN, mode putar saja (mematikan server lalu menunggu 30 detik), dan
  jalan pulih sentuh-tahan pojok kiri bawah.
- Kotak prioritas di menu awal, tombol Salin dari server, pemisahan panel
  atas/layar penuh, dan layar penuh tanpa bingkai.
- Semua belum pernah dijalankan di panel Maxtor asli.

**Pekerjaan yang sudah disepakati tetapi belum dibuat:**

- **Mode "memanjang" untuk anjungan** (panel ±4,4 : 1): tiga bagian
  (judul+loket, layanan, hasil nomor) saat ini **bertumpuk vertikal**;
  usul: berdampingan bila lebar ÷ tinggi > 2,5.
- Opsi `kiosk.video_skala` = pas/isi (saat ini hanya *pas*).
- Pratinjau/peringatan rasio video terhadap tempat tampilnya.
- Laporan: jumlah dan rata-rata tunggu nomor prioritas, jumlah dicabut.
- Perkiraan tunggu di tiket masih menghitung urutan datang (bisa sedikit
  terlalu rendah untuk nomor biasa yang disisipi prioritas).
- Merge/PR cabang ke `main`.

**Hal yang perlu tindakan manusia:**

- Mulai ulang API server (kode baru) dan buka ulang aplikasi Windows
  (menerapkan migrasi `e9c3b5a7d281`).
- Pasang APK 2.4.34.1 ke BlueStacks/tablet (seret ke jendela BlueStacks, atau
  ⚙ Pengaturan → Perbarui bila server membagikannya).
- Memastikan resolusi panel (`adb shell wm size`; BlueStacks Pie64 = 2160 ×
  3840 tegak).
- Memasang installer 1.0.10 di PC loket setelah pemilik puas.

**Risiko yang diketahui:**

- Monkeypatch tema (bagian 4.1).
- Kotak prioritas anjungan tidak memverifikasi kebenaran; pengawasnya
  petugas berjaga dan petugas loket (dapat mencabut).
- Sesi sebelumnya sempat membuat `data/tampilan.json` dari tes yang tidak
  mengisolasi env; sudah diisolasi di `tests/conftest.py` (`app_config`,
  `env_mesin`).

**Perbaikan keamanan 16 Oktober 2026 (Claude)**, rinci di
[keamanan-sesi.md](keamanan-sesi.md). Tiga temuan keamanan Codex di bawah
sudah ditutup:

- Pembaruan Windows wajib bertanda tangan Ed25519 (`tanda_sah`,
  `alat/tandatangani_pembaruan.py`, berkas `Pembaruan-AntrianCRO.sig`).
  **Rilis 1.0.11 berikutnya harus ditandatangani pemilik**; tanpa `.sig`,
  PC loket 1.0.11 tidak menawarkan pembaruan. PC 1.0.10 (tanpa verifikasi)
  tetap menerima seperti dulu.
- `X-Device-Id` token bersama yang milik tablet terpasang diabaikan; pembatas
  PIN per IP; hash PIN hanya ke tablet terpasang.
- Kode pasang ditandai dengan UPDATE bersyarat; pembatas tebakan per IP +
  gabungan, di bawah `lock_tebakan`.
- Juga: Kesehatan Sistem › **Kata sandi bawaan** dan **Pembaruan Windows di
  server**; job CI **Audit dependency** (`pip-audit==2.9.0 --no-deps`);
  `backup/*.bundle` di `.gitignore`.
- **Menunggu keputusan pemilik:** enkripsi berkas backup; mematikan token
  bersama dan mengikat API ke IP LAN (langkah operasional).

**Temuan audit Codex 16 Oktober 2026 (sisa yang belum diperbaiki):**

- `GET /v1/kiosk/display` terukur menjalankan **41 pernyataan SQL** per polling
  pada PostgreSQL uji. Android memanggilnya tiap 5 detik, atau tiap 1 detik saat
  iklan penuh dan interupsi panggilan aktif. Pengaturan perlu dibaca sekali,
  hasil antrian prioritas dipakai ulang, dan respons statis layak di-cache.
- Dua tes layout stabil gagal pada 1366 x 768: kelompok **Iklan Anjungan**
  membutuhkan gulir vertikal 287 px pada mode loket maupun server. Dua tes
  Pelayanan lain sempat gagal saat suite gabungan tetapi lulus saat diulang
  terarah, menunjukkan state global tema/layout masih bergantung urutan tes.
- `MainActivity` anjungan membuat executor `pembuatThumbnail`, tetapi tidak
  mematikannya di `onDestroy`; executor lain sudah dimatikan.
- Infrastruktur tes masih berbawaan SQLite (`tests/conftest.py` dan
  `test-postgres.ps1` bahkan menyebut tes harian SQLite), bertentangan dengan
  aturan proyek. Audit pertama sempat jatuh ke SQLite sebelum dikoreksi. Tambah
  penjaga fail-fast agar pytest menolak selain PostgreSQL `antrian_uji`.

Verifikasi audit: `ruff check app tests alembic` dan compile Python lulus;
299 tes keamanan/API terarah lulus di PostgreSQL (2 dilewati); 513 tes
wiring/UI lulus, 4 gagal, 2 dilewati; pengulangan empat kegagalan menghasilkan
2 gagal layout yang stabil dan 2 lulus; 26 tes migrasi/database/penomoran lulus,
4 tes khusus SQLite dilewati; kedua APK debug berhasil dikompilasi. Pencarian
OSV terhadap 17 dependency langsung tidak menemukan advisory yang cocok dengan
versi terpasang. Suite penuh tidak dijalankan karena aturan proyek membatasinya
untuk sebelum push/PR.

Audit teks tombol (16 Oktober 2026, Claude; menggantikan catatan Codex yang
menyatakan "tidak ditemukan potongan" — pemeriksaan permanen ternyata menemukan
tiga):

- **Terbukti terpotong** (lebar < `sizeHint()`): (1) "Panggil Berikutnya · F2"
  di Pelayanan, 250 px dari 254 px, karena `setFixedWidth(250)` pada
  pembungkus tombol; (2) "Pasang ulang & nyalakan ulang" di Layanan Anjungan
  pada 800×600 dan Windows 125%/150%, karena sebaris dengan kotak centang
  panjang; (3) "Segarkan media" di tabel perangkat, 131 px dari 135 px, karena
  lebar kolom aksi dihitung dari `sizeHint()` sebelum tombol dipolish.
- **Perbaikan:** `service_page.py` (pembungkus tombol memakai kebijakan
  `Minimum`, tanpa lebar tetap/minimum buatan); `layanan_anjungan_page.py`
  (kotak centang pindah ke baris sendiri); `kartu_perangkat.py`
  (`_atur_lebar_aksi`: polish dulu, dihitung ulang saat kartu tampil, sisa 16 px
  karena widget sel ±12 px lebih sempit dari kolomnya).
- **Tes permanen:** `tests/ukuran_tombol.py` (pengukur reusable) dan
  `tests/test_teks_tombol.py`: 4 peran × 800×600 / 1280×720 / 1366×768; 4 peran
  × ukuran logis Windows 125% (1093×614) dan 150% (911×512); admin & CRO dengan
  font-size stylesheet ×1,25 dan ×1,5; keadaan khusus (pita pembaruan dua
  label, pita anjungan, perangkat terpasang, nomor sedang dilayani, Buka/Tutup
  Pendaftaran); 13 dialog × font 100%/150%. Semua label bergantian (Unduh &
  Perbarui/Sedang mengunduh…, Mulai/Akhiri Istirahat, Ganti Loket/Batal,
  Tampilkan/Sembunyikan, Aktifkan/Nonaktifkan, Pasang…) dipasang satu per satu.
  Syarat lulus: lebar ≥ `sizeHint().width()` dan tinggi ≥ satu baris huruf
  (tinggi tidak dibandingkan ke `sizeHint` karena layout boleh menekan 1–2 px
  tanpa memotong huruf). Pengecualian: `PENGECUALIAN` di `ukuran_tombol.py`
  (kosong).
- **Hasil uji** (PostgreSQL `antrian_uji` via `~/.antrian-uji-db`, satu proses
  pytest, divalidasi `postgresql` + nama tepat `antrian_uji`): `test_teks_tombol.py`
  seluruhnya lulus (57 tes). Gabungan dengan `test_ui`, `test_dashboard_ui`,
  `test_active_service_ui`, `test_notes_ui`, `test_daftar_putar_ui`,
  `test_tema_petugas`: 357 lulus, 2 dilewati, 4 gagal — 2 itu `Iklan Anjungan`
  287 px (temuan lama bagian ini), 2 itu tes Pelayanan 1366×768 yang **lulus
  bila dijalankan sendiri** (ketergantungan urutan lama yang sudah tercatat;
  belum dipastikan apakah tes baru memperparahnya). `ruff check app tests
  alembic` lulus. Suite penuh tidak dijalankan.
- **Suite penuh sebelum push** (16 Oktober 2026, 30 menit): 1808 lulus, 3 gagal yang kemudian diperbaiki: enam pengaturan `kiosk.*` (iklan_putaran, animasi_*, panggilan_hentikan_iklan) belum ada di seed (`app/core/seed.py`), dan grup "Iklan Anjungan" bergulir 287 px di 1366×768 sehingga dipecah: grup baru "Perilaku Iklan" memuat putaran iklan, empat animasi, dan panggilan menghentikan iklan. Dua error `caplog` hanya karena bendera `-p no:logging` saya.
- **Belum teruji:** DPI Windows sungguhan (Qt offscreen tidak menskalakan
  piksel; 125%/150% hanya didekati lewat ukuran jendela logis dan font-size
  stylesheet), font Segoe UI pada mesin lain, `SurveyDialog`, dialog
  `CounterCategoryDialog`, dan tombol yang hanya muncul pada data tertentu.
  Label pita pembaruan tidak lagi memakai `&`, sehingga risiko Qt membacanya
  sebagai penanda pintasan sudah hilang.

**Pengalaman pembaruan Windows 17 Oktober 2026 (Codex):**

- Alur dipisah menjadi **unduh → siap dipasang → pasang**, sehingga selesai
  mengunduh tidak lagi langsung membuka installer. Pita menampilkan progres
  persen dan MB. Admin melihat ukuran serta status terverifikasi dengan tombol
  **Unduh pembaruan / Pasang sekarang**; petugas memakai **Unduh di latar
  belakang / Pasang setelah pelayanan**.
- `PembaruanWindowsService` menolak pemasangan oleh CRO yang masih memegang
  nomor aktif. Penjaga berada di service layer. Pemeriksaan ruang disk menyisakan
  cadangan 64 MB; gagal unduh atau gagal membuka installer dapat dicoba lagi.
- Tes PostgreSQL terarah `test_pembaruan_windows.py` + `test_teks_tombol.py`:
  **76 lulus**, satu peringatan deprecation Starlette. `ruff check app tests
  alembic` dan `git diff --check` lulus.
- Belum dibuat: tombol tunda per versi, melanjutkan unduhan terputus, catatan
  rilis, pemasangan terjadwal, audit hasil setelah aplikasi hidup kembali, dan
  pemantauan versi seluruh PC.

**Unduh PDF/Excel admin dan petugas 17 Oktober 2026 (Codex):**

- Admin/supervisor tetap mendapat menu **Laporan** seluruh cabang. CRO kini
  mendapat **Laporan Saya** dengan rentang tanggal, PDF, dan Excel berisi hanya
  nomor yang ditangani akun yang sedang masuk. `laporan_petugas()` tidak
  menerima id petugas dari UI; cakupan ditentukan dari sesi dan ditegakkan oleh
  `QUEUE_CALL` di service layer.
- Laporan pribadi tidak menampilkan lembar **Per petugas** maupun **Petugas per
  layanan** yang redundan. Nama petugas, judul personal, serta nama berkas
  `laporan-saya-...` membedakannya dari laporan seluruh cabang.
- Tombol menjadi **Unduh PDF/Unduh Excel**. UI menampilkan proses dan hasil
  secara sebaris, menambahkan ekstensi yang hilang, memakai folder home bila
  Documents tidak ada, dan menulis ke berkas sementara sebelum mengganti tujuan
  supaya laporan lama tidak rusak bila ekspor gagal.
- Tes terarah PostgreSQL `test_report_service.py` + `test_teks_tombol.py`:
  **73 lulus**. Suite penuh belum dijalankan karena tidak sedang push/PR.

---

## 7. Perintah penting

```powershell
# Tes terarah
.\.venv\Scripts\python.exe -m pytest -q tests/test_prioritas.py tests/test_kiosk_api.py
# Lint
ruff check app tests alembic
# Suite penuh (sekali sebelum push)
.\.venv\Scripts\python.exe -m pytest -q
# Aplikasi Windows dari kode (database mengikuti data\mesin.json)
.\.venv\Scripts\python.exe -m app.main
# Installer Windows (menjalankan tes sendiri; keluaran di dist\)
.\build-installer.ps1
# APK anjungan + layar; MENYALIN ke apk\ (dibagikan server). Backup apk\ dulu.
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
.\build-android-kiosk.ps1
# Hanya compile APK debug (tidak menyentuh apk\)
cd android-kiosk; .\gradlew.bat --no-daemon :app:assembleDebug
```

**Menjalankan aplikasi terhadap database uji** (aman, tanpa menyentuh data
kerja): set `ANTRIAN_DB_URL` dari `~/.antrian-uji-db`, serta
`ANTRIAN_TAMPILAN_PATH` dan `ANTRIAN_PERAN_PATH` ke berkas sementara.
Skrip bantu pernah menjalankan `upgrade_to_head()` + `seed_initial_data()`
lalu mengisi nomor contoh lewat sesi anjungan (`AuthService.mulai_sesi_kios`).

**ADB ke BlueStacks.** Pakai server ADB sendiri (`adb -P 5038 ...`) bila
server 5037 mati. Instance `Pie64` di `127.0.0.1:5555` / `emulator-5554`.
Koneksi sering putus (`error: closed`); `adb connect` ulang atau
`kill-server` + `start-server`. `adb push` kadang gagal; alternatifnya
menyeret APK ke jendela BlueStacks. Tangkapan layar:
`adb -P 5038 -s emulator-5554 exec-out screencap -p > layar.png`. Log:
`adb ... shell "logcat -d -t 800"`.

**Catatan alat.**

- Heredoc `python - <<'PYEOF'` dengan banyak tanda kutip tiga kadang
  merusak shell; tulis skrip ke berkas lalu jalankan.
- Berkas di repo bercampur LF/CRLF; skrip pengedit membaca dengan
  `newline=""`, memakai `\n` di memori, dan menulis kembali dengan akhiran
  asli. Jangan menyisipkan BOM (Set-Content PowerShell 5.1 `-Encoding UTF8`
  menambahkannya; Gradle gagal).
- Di string Python non-raw, `\b` menjadi karakter backspace; pakai raw string
  atau `chr(92) + "b"` untuk regex.

---

## 8. Peta berkas untuk fitur baru

| Area | Berkas |
|---|---|
| Tema | `app/ui/tema_petugas.py`, `app/ui/tampilan_page.py`, `tests/test_tema_petugas.py` |
| Papan tunggu / kartu | `app/ui/queue/papan_tunggu.py`, `kartu_berikutnya.py`, `service_page.py` |
| Prioritas | `app/services/urutan_prioritas.py`, `queue_service.py` (`create_queue`, `call_next`, `cabut_prioritas`), `app/models/queue.py`, `app/ui/registration/registration_page.py`, `tests/test_prioritas.py` |
| Salinan media | `app/models/kiosk_device.py`, `app/services/device_service.py`, `app/kiosk_api.py`, `app/ui/settings/kartu_perangkat.py` |
| Tempat tampil | `app/services/daftar_putar.py`, `app/ui/settings/dialogs.py` (`JadwalIklanDialog`), `settings_page.py` |
| Anjungan Android | `android-kiosk/app/src/main/java/id/sistemantrian/kiosk/MainActivity.java` (satu berkas besar) |
| Migrasi | `alembic/versions/c3f8a1d7e592_*`, `d6a1f3b8c704_*`, `e9c3b5a7d281_*` |
| Login bertingkat | `app/services/auth_service.py` (`TINGKAT_PENUNDAAN`), `app/ui/login/login_window.py` |

---

## 9. Riwayat pembaruan dokumen ini

| Tanggal | Oleh | Perubahan |
|---|---|---|
| 2026-10-16 | Claude | Dokumen dibuat; mencakup seluruh pekerjaan Oktober 2026 di atas |
| 2026-10-16 | Claude | Ditambah: panggilan mengalahkan iklan (setelan, `call_count`, banner, polling 1 detik) |
| 2026-10-16 | Codex | Audit penuh bug, wiring, performa, dan keamanan; temuan serta hasil tes PostgreSQL dicatat di bagian 6. |
| 2026-10-16 | Codex | Audit teks tombol pada tiga ukuran jendela; tidak ditemukan potongan, celah tes regresi dicatat di bagian 6. |
| 2026-10-16 | Claude | Tes permanen teks tombol (`tests/test_teks_tombol.py`, `tests/ukuran_tombol.py`); tiga tombol terpotong diperbaiki (bagian 6). |
| 2026-10-16 | Claude | Warna latar iklan penuh per tablet, murni Android (SharedPreferences `latar_iklan_penuh`, kontrol di dialog Pengaturan > Tampilan; tanpa server/DB); rincian di android-kiosk.md. APK debug terkompilasi, belum diuji di perangkat, belum di-commit. |
| 2026-10-16 | Claude | Perbaikan keamanan: pembaruan Windows bertanda tangan, celah `X-Device-Id`, hash PIN, kode pasang, Kesehatan, pip-audit (bagian 6) |
| 2026-10-17 | Codex | Audit pengalaman pembaruan Windows untuk admin dan petugas; saran pembedaan alur peran dicatat di bagian 6. |
| 2026-10-17 | Codex | Alur pembaruan admin/petugas dibuat dua tahap dengan progres, pemeriksaan ruang disk, dan pengunci pelayanan aktif. |
| 2026-10-17 | Codex | Laporan Saya PDF/Excel ditambahkan untuk CRO; ekspor admin/petugas memakai status sebaris dan penyimpanan atomik. |

Saat menutup sesi: perbarui bagian 3 (keadaan, commit, versi), 6 (belum
selesai), dan tabel di atas.
