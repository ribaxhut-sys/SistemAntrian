# Layar Antrian Android (Maxtor)

Aplikasi `android-kiosk/layar` untuk panel Android Maxtor, jenis yang sama
dengan anjungan ambil tiket. Tugasnya hanya menampilkan dan membunyikan
panggilan; ia tidak pernah menerbitkan nomor (lihat [istilah.md](istilah.md)).
Datanya diambil dari API aplikasi server, sama dengan yang dipakai anjungan.
**Suara panggilan keluar dari panel ini.**

## Memasang

1. Build di komputer pengembang: `.\build-android-kiosk.ps1` menghasilkan
   `dist\AntrianLayar-<versi>.apk` dan menaruh salinannya di folder `apk`
   (`layar.apk` + `layar.json`) untuk dibagikan server.
2. Pasang APK di panel untuk pertama kali (flashdisk + pengelola berkas, atau
   `adb install`). Pembaruan berikutnya diambil dari server (lihat di bawah).
3. Buka **Layar Antrian**. Saat pertama kali, dialog pengaturan muncul:
   - **Cari server otomatis**, atau ketik `http://<IP-server>:8765`;
   - isi nama layar, misalnya *Layar Ruang Tunggu*;
   - di komputer server: **Layanan Anjungan → Perangkat → + Tambah
     perangkat**, lalu ketik kode 6 angkanya di panel.
4. Panel muncul di daftar **Perangkat** dengan jenis **Layar antrian**.
5. Di komputer server tekan **Buat ulang paket suara** (Layanan Anjungan →
   Status) bila panel tidak punya suara Bahasa Indonesia.

Layar antrian **wajib** dipasangkan dengan kode. Token bersama anjungan dan
token tablet anjungan tidak diterima di `/v1/layar/*`.

## Sentuhan dan pengaturan

Layar ini hanya untuk ditonton. **Semua sentuhan diabaikan**, sehingga
pengunjung yang menyentuh panel tidak mengubah apa pun.

- Pengaturan dibuka dengan **menahan judul atau jam 3 detik**. Pada panel
  yang memakai remote/keyboard: tombol **MENU** atau **tahan OK**.
- Tombol kembali tidak menutup aplikasi.
- **Kunci aplikasi** (tombol di pengaturan) menyematkan layar sehingga
  tombol beranda dan aplikasi lain tidak bisa dibuka. Android meminta
  konfirmasi sekali. Sematan hilang bila panel dimulai ulang; untuk kunci
  permanen pakai fitur *kiosk/aplikasi tunggal* bawaan panel Maxtor.
- Kosongkan kode pasang bila hanya mengganti nama layar.

## Tegak atau mendatar

Aplikasi mengikuti arah panel dan menyusun ulang dirinya saat diputar, tanpa
memulai ulang.

- **Judul dan tanggal/jam selalu di tengah**, bertumpuk.
- **Mendatar:** kartu loket di kiri, kolom **Berikutnya** di kanan (2 nomor
  per baris, memanjang ke bawah sampai penuh).
- **Tegak:** kartu loket dua kolom di atas, **Berikutnya** di bawah (3 nomor
  per baris).
- Ukuran huruf dirancang untuk 1280×720 / 720×1280 dan ikut membesar pada
  panel 1080p atau 4K.

### Kartu loket menyesuaikan banyaknya antrian (tegak)

Semakin banyak yang menunggu, daftar **Berikutnya** bertambah per baris dan
kartu loket memendek:

- satu baris berisi 3 nomor; paling banyak 4 baris (12 nomor);
- daftar tidak pernah lebih dari **45%** tinggi papan;
- kartu loket tidak pernah lebih pendek dari **1/8 tinggi layar**; bila
  batas itu tercapai, baris tidak ditambah dan sisanya masuk *"dan N
  lainnya menunggu"*;
- kartu hanya bergerak saat jumlah **baris** berubah, dengan animasi halus,
  bukan setiap kali satu nomor bertambah;
- `display.next_count` di server tetap berlaku sebagai jumlah minimal yang
  dikirim; layar meminta sampai 300 (`?next=300`); lebih dari satu halaman nomor bergantian tampil.

## Tema Bening

Nama tema tampilan layar antrian saat ini (disimpan 21 Oktober 2026). Latar
putih, aksen teal, nuansa bersih dan resmi. Belum ada pilihan tema di
pengaturan; layar hanya punya tema ini, dan tampilan gelap lama sudah tidak
ada. Nilainya ada di konstanta warna `MainActivity.java` modul `layar`.

- **Warna:** latar putih `#FFFFFF`; teal `#0F766E` (blok nama loket, nomor
  pertama); tinta `#0F172A` (nomor, judul); teks sekunder `#334155` dan
  `#64748B`; garis `#CBD5E1`; amber `#B45309` (banner, status DIPANGGIL,
  prioritas); sorotan panggilan cyan `#0891B2`.
- **Kartu loket (tegak):** strip 84 dp satu loket per baris. Kiri blok teal
  berisi nama loket; tengah nomor besar dan nama layanan rata tengah; kanan
  kolom status 112 dp berisi pil DILAYANI (putih, teks teal) atau DIPANGGIL
  (amber, berdenyut pelan). Kartu yang baru memanggil berkedip sekitar
  2 detik.
- **Panel samping:** judul **AKAN DIPANGGIL** berisi 3 nomor teratas urutan
  panggil (BERIKUTNYA teal penuh, KE-2 dan KE-3 teal muda; slot kosong
  abu redup), garis pemisah, lalu **MENUNGGU** berisi nomor ke-4 dan seterusnya
  sebagai pil abu muda 3 kolom, sampai 10 baris. Lebih dari satu halaman
  bergantian tiap 8 detik dengan transisi pudar. Nomor prioritas berpil amber
  dengan bintang.
- **Teks:** tanggal memakai nama bulan lengkap ("Rabu, 21 Oktober 2026").

## Memilih tema tampilan

Tema dipilih **per perangkat** di pengaturan layar (tahan judul 3 detik, lalu
"Tema tampilan"); pilihannya tersimpan di perangkat itu saja dan berlaku
seketika. Judul, jam, banner, polling, suara, dan pembaruan sama di semua tema.

| Tema | Susunan |
|---|---|
| **Bening** (bawaan) | Strip loket, 3 nomor "AKAN DIPANGGIL", daftar "MENUNGGU" (lihat di atas). |
| **Dinding** | Baris kotak loket (nama, nomor, status; MEMANGGIL saat memanggil), blok "SEDANG DIPANGGIL" satu baris per nomor, lalu dinding nomor menunggu (maksimal 15 baris, kartu dibalik tiap 30 detik, nomor yang baru dilayani memudar 20 detik, prioritas ungu). |

Tema lain (Panggung, Papan, Lajur) pernah dibuat lalu dihapus; perangkat yang
menyimpan pilihan itu kembali ke Bening.

Tema berada di `MainActivity.java` modul `layar` sebagai kelas dalam
(`TemaLayar` dan turunannya); menambah tema berarti satu kelas baru, satu
baris di `buatTema`, dan satu baris di `TEMA_DAFTAR`.

## Yang ditampilkan

- Satu kartu per loket: nomor yang sedang dipanggil/dilayani, atau
  ISTIRAHAT/KOSONG. Nomor selalu **satu baris** (PB-014); hurufnya
  dikecilkan sampai muat lebar dan tinggi kartu.
- Panggilan terbaru disorot 10 detik.
- Daftar **Berikutnya** dan sisa yang menunggu.
- Jam dan zona waktu dari server (WIB), bukan dari setelan panel.

## Suara

Setiap panggilan, termasuk panggil ulang, berbunyi nada lalu diucapkan
dengan kalimat yang sama dengan layar antrian Windows
(`sound_service.teks_pengumuman`), misalnya *"Nomor antrian P B, nol satu
empat, silakan menuju Loket satu."* Urutan pilihan suara:

1. **Text-to-speech panel** bila punya Bahasa Indonesia.
2. **Paket suara dari server**: klip WAV pendek (huruf, angka, dua frasa,
   dan kata-kata nama loket) yang dibuat aplikasi server dengan suara
   Windows dan disambung di panel. Panel mengunduhnya sendiri setiap kali
   versinya berubah. Buat ulang paket bila nama loket berubah; status
   **Paket suara** di Layanan Anjungan memberi tahu bila ada kata yang
   belum punya klip.
3. **Nada saja** bila keduanya tidak ada.

Di pengaturan panel tertulis suara mana yang sedang dipakai.

- Mengikuti pengaturan **display.sound_enabled** di server.
- Panel yang baru menyala atau baru tersambung lagi **tidak** membunyikan
  panggilan yang sudah lewat.
- Mulai APK layar 1.5 panggilan yang lebih tua dari 60 detik menurut jam
  server (`age_seconds` ditambah lama antre di panel) tidak diucapkan, dan
  antrean ucapan paling banyak 10 panggilan — sama dengan anjungan. Kartu
  loketnya tetap disorot.
- Sesudah database dipulihkan dari backup, server mengarahkan panel ke id
  panggilan terakhir yang sebenarnya, sehingga suara tidak diam selamanya.
- Bila layar antrian Windows (`--tv`) masih menyala di ruangan yang sama,
  matikan suara salah satunya supaya panggilan tidak terdengar dua kali.

## Pembaruan aplikasi

Server membagikan `apk\layar.apk`. Bila versinya lebih baru, pengaturan
panel menampilkan tombol **Perbarui ke versi …**; Android meminta izin
*Pasang aplikasi tidak dikenal* sekali, lalu konfirmasi pemasangan. Bila
versi panel di bawah `VERSI_MINIMAL_LAYAR` (app/services/apk_anjungan.py),
papan menampilkan pita peringatan sampai diperbarui.

## Saat server tidak terjangkau

Sesudah tiga kegagalan berturut-turut (sekitar 6 detik), papan terakhir
tetap tampil tetapi diredupkan, muncul pita *"Terputus dari server sejak
…"*, dan tidak ada suara. Begitu tersambung, papan kembali normal.

## Menyala sendiri

- Aplikasi mencoba membuka diri sesudah panel menyala (`BOOT_COMPLETED`).
  Bila panel tidak mengizinkannya, jadikan **Layar Antrian** aplikasi awal
  (*startup app* / *auto start*) di setelan panel.
- Layar dijaga tetap menyala, dan isi papan digeser beberapa piksel tiap
  5 menit supaya panel tidak terbakar.

## Peralihan dari layar antrian Windows

Layar antrian Windows (`AntrianCRO.exe --tv`) tetap ada sampai layar Maxtor
terbukti berjalan di kantor. Sesudah itu ia dihapus, sama seperti anjungan
Windows (docs/istilah.md).

## API

| Endpoint | Isi |
|---|---|
| `GET /v1/layar/state?next=N` | judul, `sound_enabled`, kartu loket (`name`, `queue_number`, `category`, `status`), `next` (sampai 12), `total_waiting`, `server_time_ms`, `timezone`, `app_min_version_code`, `app_latest_version_code`, `app_latest_version_name`, `sound_pack_version` |
| `GET /v1/layar/calls` | tanpa `after`: hanya `last_id`; dengan `after=N`: panggilan baru (`id`, `queue_number`, `counter_name`, `call_number`, `text`, `tokens`) |
| `GET /v1/layar/sound` | indeks paket suara: `version`, `voice`, `clips` (kunci → berkas) |
| `GET /v1/layar/sound/{berkas}` | satu klip WAV dari indeks |
| `GET /v1/layar/app/apk` | APK layar antrian terbaru |
