# Anjungan Android

The Android app is a full-screen standing-kiosk client with large touch
targets. It detects the Android display's current orientation and sizes
controls to its available screen space. The existing Windows application
continues to own the database and issue queue numbers. The Android tablet
connects to the Windows server over the same trusted private Wi-Fi network
and prints receipts to a USB thermal printer using ESC/POS.
Mulai anjungan 2.4.4 tiket digambar di **server**, bukan di tablet:
`ticket_raster` pada jawaban `POST /v1/kiosk/tickets` adalah bitmap 1-bit
576 × 704 titik (72 × 88 mm, 203 DPI) yang memakai huruf Arial, ukuran pt,
penengahan, dan **Geser atas** tiket yang sama dengan pencetak Windows.
Tablet hanya mengirimnya ke printer (ESC/POS `GS v 0`). APK lama, atau
server tanpa Arial/Pillow, kembali ke `ticket_layout` yang digambar tablet
sendiri dengan Roboto — hasilnya lebih kecil dan tipis. **Uji cetak** di
tablet kini mencetak tiket contoh `UJI-000` dari `GET /v1/kiosk/ticket-sample`
sehingga sama dengan tiket sungguhan; tanpa server ia kembali ke tiket teks.
Sisa perbedaan dengan Windows hanya umpan kertas dan potongan, yang di
Windows diatur driver POS80.

## Server Windows

API anjungan adalah bagian dari komputer **server**: ia berjalan di komputer
yang memegang database PostgreSQL, dan anjungan Android hanya klien yang
menyambung ke sana. Menu **Layanan Anjungan** karena itu hanya muncul di
komputer yang perannya server.

1. Masuk sebagai Administrator, buka **Layanan Anjungan**.
2. Tekan **Pasang & nyalakan** dan setujui UAC. Satu izin itu membuka
   Firewall (TCP 8765, UDP 8766, semua profil jaringan tetapi hanya dari subnet lokal) dan mendaftarkan tugas
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
di tiap loket. Baris "NOMOR DI LOKET" (dulu "Sedang dilayani"; sejak 2.4.32
kartu loket yang baru memanggil berlatar hijau dengan tulisan "Dipanggil")
diletakkan menurut
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

### Suara panggilan (mulai APK 2.4.22)

Pengganti sementara selama layar antrian belum terpasang. Di Layanan
Anjungan → kartu Perangkat, pilih **Anjungan yang membunyikan panggilan**.
Hanya satu anjungan, dan hanya yang dipasangkan dengan kode, supaya
pengumuman tidak terdengar dua kali.

Pada pemasangan baru, anjungan PERTAMA yang dipasangkan langsung dipilih
bersuara, asal belum ada perangkat terpasang lain (anjungan atau layar
antrian Android) dan admin belum pernah mengubah pilihan ini. Layar antrian
Windows tidak terdaftar sebagai perangkat: bila memakainya, matikan suara
salah satunya.

Komputer server perlu suara Bahasa Indonesia Windows (Microsoft Andika):
Settings → Time & language → Language & region → tambah Bahasa Indonesia
dengan Speech. Tanpa itu paket suara dibuat dengan suara berlogat asing dan
Layanan Anjungan menampilkan peringatan di baris Paket suara.

- `/v1/kiosk/display` mengirim `call_sound` (anjungan ini bersuara atau
  tidak) dan `sound_pack_version`.
- Anjungan terpilih menanyakan `GET /v1/kiosk/calls?after=N` tiap 2 detik
  dan mengucapkan kalimat yang sama dengan layar antrian: TTS Bahasa
  Indonesia tablet, atau paket suara (`/v1/kiosk/sound`) bila tablet tidak
  punya, atau nada saja.
- Selama pengumuman, suara video iklan dikecilkan. Pengunjung yang sedang
  mengambil nomor tidak menunda pengumuman.
- Pilih **Tidak ada** kembali begitu layar antrian bersuara dipasang.
- Kartu Perangkat memperingatkan bila layar antrian Android yang tersambung
  juga bersuara (pengumuman terdengar dua kali).
- Mulai APK 2.4.23 panggilan yang lebih tua dari 60 detik menurut jam server
  (`age_seconds`) tidak diucapkan, misalnya setelah Wi-Fi tablet sempat putus.
- Panggilan yang hampir bersamaan dari dua loket tidak terlewat: di
  PostgreSQL penulisan panggilan diantrekan (advisory lock), sehingga urutan
  id sama dengan urutan commit.
- Paket suara memakai suara Indonesia Windows (Microsoft Andika) dan
  diperbarui otomatis oleh API tiap menit bila ada kata nama loket baru.

### Iklan (mulai APK 2.4.21)

- **Syarat tayang.** Iklan hanya diputar bila **Tampilan panel anjungan** =
  Folder media. Mencentang iklan di **Daftar putar media** sementara panel
  masih Teks sambutan memindahkan pilihannya ke Folder media (tetap harus
  disimpan), dan baris daftar putar menampilkan peringatan selama keduanya
  tidak cocok.
- **Jadwal dan lama tampil.** Pilih berkas lalu **Atur jadwal…** (atau klik
  dua kali): tanggal mulai/selesai (keduanya ikut dihitung, menurut tanggal
  server) dan lama tampil khusus gambar itu (3–60 detik; kosong = pengaturan
  umum). Di luar tanggalnya berkas tidak dikirim ke tablet dan tidak
  dilayani `/v1/kiosk/media`. Disimpan di `kiosk.daftar_putar` sebagai objek
  `{"nama", "mulai", "selesai", "detik"}`; butir tanpa aturan tetap berupa
  nama saja, jadi nilai lama terbaca apa adanya. `welcome_media_files[].seconds`
  membawa lama tampilnya ke tablet.
- **Tempat tampil (APK 2.4.34.1).** Video untuk strip panel atas (mendatar,
  kecil) dan video untuk layar penuh (seluruh layar) berbeda bentuknya, jadi
  di dialog **Atur jadwal…** tiap berkas punya **Tampil di**: *Panel atas*,
  *Layar penuh*, atau *Keduanya* (bawaan). Disimpan sebagai `"tampil":
  "panel" | "penuh"` pada butir (tidak ditulis bila keduanya) dan dikirim ke
  tablet sebagai `welcome_media_files[].show`.
  - Normal: panel atas memutar berkas *Panel atas* dan *Keduanya*.
  - Menganggur melewati **Iklan layar penuh saat menganggur**: layar penuh
    memutar berkas *Layar penuh* dan *Keduanya*. Bila tidak ada satu pun,
    layar penuh tidak diaktifkan dan layar tetap menampilkan menu — video
    strip tidak dipaksa memenuhi layar, dan sebaliknya.
  - APK lama mengabaikan `show` dan memutar semuanya seperti dulu.
- **Saat pengunjung bertransaksi** (memilih layanan, konfirmasi, menunggu
  tiket, layar "Nomor Anda", atau 15 detik sejak sentuhan terakhir) video
  selalu dibisukan dan panel iklan diredupkan. Sub-menu layanan yang
  ditinggal 30 detik tanpa sentuhan kembali ke menu awal, begitu pula saat
  iklan memenuhi layar.
- **Iklan layar penuh.** Setelah **Iklan layar penuh saat menganggur**
  (bawaan 60 detik, 0 = mati) tanpa sentuhan, iklan memenuhi layar dengan
  ajakan "Sentuh layar untuk mengambil nomor antrian" (**panel di ATAS layar**, latar
  navy pekat, tetap tampil selama iklan; video diletakkan di bawah panel
  sehingga tidak ada bagian video tertutup dan rasio tetap terjaga (mode
  pas, pita hitam bila rasio berbeda). Tinggi panel ±12% tinggi layar untuk
  layar memanjang (>2:1, mis. ±4,4:1) dan ±8% untuk layar tegak/biasa,
  dibatasi 44–96 dp; huruf mengecil otomatis bila teks tak muat. Dibanding
  menimpa video dengan panel yang muncul-hilang: menimpa menutup bagian atas
  video pada layar memanjang (video sudah setinggi layar) dan perubahan
  ukuran area video tiap siklus memicu tata ulang pemutar, jadi dipilih
  panel tetap; ongkosnya hanya ±8–12% tinggi video). Kode:
  `tampilkanPanelAjakanIklan`; panel berdenyut halus (~2,8 detik/siklus; latar warna dasar↔puncak +-12% dan teks memudar ringan, tanpa skala sehingga video tidak berubah ukuran; `mulaiDenyutAjakanIklan`), dihentikan saat iklan selesai/disentuh, mode putar saja, onStop, onDestroy; belum diuji di perangkat, hanya dikompilasi. Sentuhan pertama hanya
  mengembalikan layar biasa, tidak diteruskan ke tombol layanan. Tidak aktif
  selama dialog terbuka, pembaruan APK, atau bila media gagal diputar.
  Mulai APK 2.4.34.1 iklan memenuhi **seluruh layar** tanpa margin, padding,
  sudut membulat, dan garis tepi, di atas latar hitam. Video dan gambar tetap
  utuh (rasio dijaga; pita hitam bila rasionya berbeda dengan layar), tidak
  dipotong. Siapkan video dengan rasio yang sama dengan layar tablet agar
  tidak ada pita hitam.
- **Laporan tayang.** Tablet menghitung berapa kali tiap berkas mulai tampil
  (satu berkas yang tampil terus dihitung tiap putaran/lama tampilnya) dan
  berapa kali gagal, lalu mengirimnya tiap menit ke
  `POST /v1/kiosk/media-report`. Server menyimpannya per hari, per tablet,
  per berkas (tabel `kiosk_media_tayang`). Daftar putar di Pengaturan
  menampilkan tayang hari ini dan 30 hari, serta **⚠ Gagal diputar di
  <tablet>** bila percobaan terakhir di tablet itu (kemarin atau hari ini)
  gagal; galatnya terbaca di tooltip.
- **Format video.** MP4 (H.264) dan WebM aman. MKV dan AVI masih diterima
  tetapi ditandai berisiko di daftar putar dan saat dipilih, karena pemutar
  bawaan Android sering tidak dapat memutarnya.

### Animasi (APK 2.4.12–2.4.13)

Daftar nomor menunggu (2.4.14): halaman berganti dengan ubin berbalik
seperti papan jadwal; nomor yang dipanggil mengecil lalu hilang dan ubin lain
bergeser mengisi; nomor yang baru diambil di tablet itu memakai warna utama
dan berdenyut ±10 detik, dan daftar membuka halamannya; titik di bawah
daftar menggantikan "1/3" dan terisi sampai halaman berganti. Daftar tidak
digambar ulang bila isinya tidak berubah.

Kartu layanan masuk berurutan; loket yang memanggil nomor baru berdenyut
dan angkanya bergulir; gambar iklan berganti dengan memudar (video tetap
diganti langsung); layar "Nomor Anda" menggambar tanda centang; nomor
menunggu yang baru muncul dengan "pop" dan halamannya bergeser; petunjuk
"Sentuh jenis layanan…" berdenyut pelan selama anjungan menganggur;
konfirmasi meluncur keluar saat Kembali; tema berganti dengan memudar.
Semua memakai animator Android, jadi ikut mati bila opsi pengembang
**Skala durasi animator** dimatikan.

### Judul anjungan (mulai APK 2.4.11)

**Pengaturan → Anjungan → Judul anjungan** mengganti tulisan di atas tablet
tanpa mengubah judul TV; kosong berarti ikut **Judul layar antrian**.
**Subjudul anjungan** menambah satu baris kecil di bawahnya (nama kantor,
jam layanan). ⚙ Pengaturan tablet → **Judul tablet ini** menimpa judul untuk
satu tablet dan langsung berlaku. Judul dan subjudul selalu satu baris;
hurufnya mengecil bila teksnya panjang.

### Tema anjungan (mulai APK 2.4.6)

**Pengaturan → Anjungan → Tema anjungan**: *Biru instansi* (bawaan), *Hijau
segar*, *Kontras tinggi* (hitam-kuning, huruf 12% lebih besar), *Gelap
elegan*, dan *Merah putih (perayaan)* dengan pita "Dirgahayu Republik
Indonesia ke-N" di panel sambutan. **Merah putih otomatis setiap Agustus**
(bawaan menyala) membuat server mengirim `merah_putih` selama Agustus lalu
kembali ke tema pilihan pada 1 September. Tema dikirim sebagai `theme` pada
`GET /v1/kiosk/display`; ⚙ Pengaturan tablet → **Tema tablet ini** dapat
menimpanya untuk satu tablet. Pergantian tema membangun ulang layar, tetapi
ditunda selama pengunjung sedang di layar konfirmasi atau hasil nomor.

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

### Putaran iklan layar penuh (setelah 2.4.34.1, belum dirilis)

Iklan layar penuh tidak lagi berputar tanpa henti: setelah
**Putaran iklan layar penuh** (`kiosk.iklan_putaran`, bawaan **2**, 0 = terus)
putaran selesai, anjungan kembali ke tampilan antrian dan menunggu
**Iklan layar penuh saat menganggur** dari nol; bila tetap tidak ada
kegiatan, iklan muncul lagi, dan seterusnya. Satu putaran = seluruh daftar
layar penuh diputar sekali (satu video = diputar sekali sampai selesai; satu
gambar = tampil sekali selama lama tampilnya). Dikirim ke tablet sebagai
`fullscreen_ad_loops` pada `/v1/kiosk/display`. Sentuhan tetap langsung
kembali ke menu dan menyetel ulang hitungan. Mode putar saja tetap berputar
terus (tidak ada tampilan antrian untuk kembali).

### Animasi kembali ke antrian (setelah 2.4.34.1, belum dirilis)

Saat iklan layar penuh selesai, tiga panel (judul dan loket, pilihan layanan,
hasil nomor) masuk dari **arah acak yang berbeda satu sama lain** (kiri,
kanan, atas, bawah) dan berbeda dari kali sebelumnya, dengan pantulan kecil.
Putaran habis: **1800 ms** per panel, berurutan 250 ms, pantulan 0,3.
Pengunjung menyentuh: 900 ms tanpa jeda, supaya tidak menunda pilihan
layanan. Hanya geser dan transparansi.

**Mulai sebelum iklan berakhir.** Pada berkas terakhir di putaran terakhir,
iklan meredup (600 ms, suara dibisukan) lalu tampilan antrian mulai masuk
`kiosk.animasi_mulai_detik` (bawaan **2** detik; `return_animation_lead_seconds`)
sebelum berkas itu selesai, jadi akhir iklan bertumpuk dengan animasi. Berkas
yang lebih pendek dari jeda itu mulai segera; 0 = animasi baru mulai setelah
iklan selesai. Waktu mulai dihitung dari durasi video (`getDuration`) atau lama
tampil gambar. Sentuhan di tengah peredupan membatalkannya dan langsung ke
menu.
Saklar **Animasi saat kembali ke antrian** (`kiosk.animasi_kembali`, bawaan
nyala; `return_animation` pada `/v1/kiosk/display`); dilewati otomatis bila
animasi dimatikan di pengaturan Android tablet.

### Animasi nomor menunggu (setelah 2.4.34.1, belum dirilis)

Nomor menunggu tidak lagi muncul sekaligus: **baris demi baris** (selang 200
ms) dan **di dalam baris tiap nomor** selang 70 ms, dengan gaya yang **diacak
dari gaya lama papan**: *papan balik* (berputar dari sumbu horizontal),
*papan balik tegak* (sumbu vertikal), dan *pop* (membesar dengan pantulan),
berbeda dari nomor sebelumnya. Total selang dibatasi 1,5 detik; paling banyak
24 nomor dianimasikan. Dipakai saat panel pertama tampil, saat **halaman
berganti**, dan saat **kembali dari iklan** (mulai sesudah panelnya hampir
tiba). **Nomor baru bertambah tetap memakai *pop*** (bukan acak) supaya jelas
itu nomor baru. Saklar **Animasi nomor menunggu**
(`kiosk.animasi_nomor_menunggu`, bawaan nyala; `waiting_animation` pada
`/v1/kiosk/display`); dilewati bila animasi Android dimatikan. Bila saklar
mati, perilaku lama (papan balik berurutan 45 ms saat halaman berganti, pop
untuk nomor baru) dipakai.

**Perataan.** Nomor menunggu mengisi dari **atas** panel: bila tidak penuh,
ruang kosong ada di bawah (sebelumnya blok nomor di tengah vertikal dan ikut
bergeser tiap ada nomor dipanggil). Titik halaman tetap di bagian bawah.

### Panel keluar saat iklan akan muncul; kotak prioritas di atas (setelah 2.4.34.1, belum dirilis)

- Kotak prioritas kini di **atas** tombol layanan (`showCategories`), di semua
  tingkat menu.
- Kebalikan animasi kembali: ±1,5 detik sebelum waktu menganggur habis, tiga panel
  keluar ke arah acak (`mulaiKeluarPanel`, arah dari `arahPanelBaru`, dipakai
  bersama animasi masuk), lalu iklan memudar masuk tanpa transisi lain
  (`panelSudahKeluar`). Disentuh atau ada panggilan di tengah animasi → panel
  kembali dan iklan batal (`batalkanKeluarPanel`).
- Setelan server **Animasi saat iklan akan muncul** (`kiosk.animasi_iklan_muncul`,
  API `ad_entry_animation`, bawaan aktif). Dilewati bila animasi Android mati,
  mode putar saja, atau waktu menganggur < 5 detik.

### Bintang prioritas pada nomor menunggu (setelah 2.4.34.1, belum dirilis)

Nomor prioritas diberi bintang kecil di **pojok kiri atas ubin** (digambar terpisah, teks nomor tetap polos) dan latar amber lembut di daftar nomor menunggu, **tanpa menyebut alasan**
(lansia/disabilitas/ibu hamil tidak pernah dikirim ke perangkat publik).
- Anjungan: `/v1/kiosk/display` mengirim `waiting_priority_numbers` (subset
  `waiting_queue_numbers`); `nomorPrioritasMenunggu` masuk tanda gambar ulang.
- Layar antrian Android: `/v1/layar/state` mengirim `next_priority` (subset `next`).
- Layar Windows: `LabelNomorMenunggu` (display_page.py) menggambar bintang bila `QueueInfo.prioritas`.
- Nomor milik pengunjung di anjungan tetap berlatar `UTAMA` (sorotan tidak tertimpa kuning).
- Server: `QueueService.nomor_prioritas_menunggu_untuk_layar()`.

### Warna kilau bebas (setelah 2.4.34.1, belum dirilis)

Pengaturan > warna kilau: bulatan pelangi "+" di barisan paling depan, sebelum 7 warna tetap,
membuka pemilih (pita jenis warna, bidang kejenuhan x kecerahan, isian hex).
Disimpan per tablet di `warna_kilau` sebagai `#RRGGBB`; pilihan lama (`emas`,
`biru`, dst.) tetap berlaku. Kecerahan dibatasi minimal 0,5
(`NILAI_MINIMUM_KILAU`) supaya sapuan terlihat; sapuan pratinjau jalan saat jari
dilepas. Kode: `bukaPemilihWarnaKilau`, `BidangWarnaKilau`.

### Warna latar iklan penuh per tablet (setelah 2.4.34.1, belum dirilis)

Pengaturan (dialog yang dilindungi PIN) > bagian Tampilan > **Warna latar iklan
layar penuh**: 5 bulatan cepat (navy, hitam, hijau tua, merah marun, ungu tua)
dan bulatan "+" yang membuka isian `#RRGGBB` dengan pratinjau. Disimpan lokal di
SharedPreferences kunci `latar_iklan_penuh` (bukan di server; tanpa kolom DB,
tanpa API). Bawaan navy `#0F172A`.
- Validasi (`uraiLatarIklan`): wajib `#RRGGBB` dan luminans relatif WCAG <= 0,6;
  isian yang tak sah mematikan tombol "Pakai warna ini" dengan pesan, nilai
  tersimpan yang tak sah jatuh ke navy.
- Turunan otomatis (`terapkanLatarIklanPenuh`): teks putih di latar gelap,
  hitam di latar terang (kontras tertinggi); puncak denyut = warna dasar
  digeser 12% (ke putih untuk latar gelap, ke hitam untuk latar terang).
  Siklus tetap 2,8 detik.
- Satu sumber: variabel `latarIklanPenuh` (menggantikan konstanta
  `LATAR_IKLAN_PENUH`) dipakai panel ajakan, sisi video (`VideoTekstur`), latar
  gambar, `rootLayout`, dan `panelInfo`. Hanya panel atas yang berdenyut.
  Perubahan saat iklan tampil langsung diterapkan. Kode: `barisLatarIklan`,
  `bukaIsianLatarIklan`. Belum diuji di perangkat, hanya dikompilasi.

### Latar kertas (setelah 2.4.34.1, belum dirilis)

Latar di belakang panel anjungan bisa berupa kertas: warna tema dihangatkan ke
krem dan diberi butiran halus (bitmap 128x128 dibuat di kode, diulang), panel
mendapat bayangan sedikit lebih tebal. Pengaturan per tablet **Latar belakang
tablet ini** (kunci `latar_kertas`): `polos` (bawaan, tampilan tidak berubah),
`tema` (kertas hanya di tema terang; gelap dan kontras tinggi tetap polos),
`kertas` (selalu). Berlaku seketika lewat bangun ulang tampilan.

### Dialog Media di tablet ini (setelah 2.4.34.1, belum dirilis)

Pengaturan > Kelola media tablet (`showMediaTablet`). Isi: ringkasan (jumlah,
total ukuran, sumber aktif, sisa ruang), penanda "N berkas di server belum ada
di tablet" (ketuk untuk Salin dari server; hilang diam-diam bila server tidak
terjangkau), daftar dikelompokkan **Video** dan **Gambar** dengan gambar mini
(video: ikon putar + durasi; dibuat di latar belakang, di-cache), lencana tempat
tampil, menu **Aksi** per berkas (panel atas / layar penuh / keduanya / Hapus),
menu **Lainnya** > Hapus semua berkas. Keadaan kosong menampilkan tombol besar
Salin dari server dan Tambah berkas. Dialog dibuka ulang sesudah tiap aksi.

### Panggilan mengalahkan iklan (setelah 2.4.34.1, belum dirilis)

Prioritas tampilan: **panggilan > transaksi pengunjung > iklan layar penuh >
iklan panel**. Saat petugas memanggil atau memanggil ulang nomor, iklan layar
penuh langsung berhenti (animasi panel masuk 900 ms), nomor dan loket tampil
besar sebagai banner ±6 detik, dan hitungan menganggur dimulai dari nol.

- Server: `/v1/kiosk/display` mengirim `call_interrupts_ad` (setelan
  **Panggilan menghentikan iklan**, grup *Iklan Anjungan*, bawaan aktif) dan
  `call_count` per loket (jumlah panggilan + panggilan ulang).
- Tablet mengenali panggilan baru dari perubahan `nomor#call_count` loket
  berstatus Dipanggil (`deteksiPanggilanBaru`). Muatan pertama tidak dihitung.
  Selama iklan layar penuh aktif, display diambil tiap 1 detik (biasanya 5).
- Tidak berlaku pada mode putar saja; tidak mengganggu layar konfirmasi atau
  hasil (iklan tetap dihentikan, banner ditahan).
- Pembatalan: peredupan/animasi awal menjelang akhir iklan dibatalkan.

### Teks loket tanpa panggilan (setelah 2.4.34.1, belum dirilis)

Loket yang aktif tetapi tidak sedang memanggil menampilkan **"Siap melayani"**
(satu baris, huruf menyusut otomatis sampai muat); loket istirahat
menampilkan "Istirahat". Berlaku di baris "NOMOR DI LOKET" anjungan dan di
kartu loket layar antrian (`status` `KOSONG` dari `/v1/kiosk/display` dan
`/v1/layar/state` tidak diubah). Sebelumnya anjungan menampilkan "—" dan layar
antrian menampilkan "KOSONG".

### PIN pengaturan dan mode putar saja (setelah 2.4.34.1, belum dirilis)

- **PIN pengaturan.** Satu PIN 6 angka untuk semua tablet, diatur admin di
  Layanan Anjungan → **PIN anjungan ▾** (atur/ganti/hapus). Server menyimpan
  hash PBKDF2-SHA1 berbumbu (`kiosk.pin_pengaturan`, tidak tampil di
  Pengaturan), bukan PIN-nya (`app/services/pin_anjungan.py`). Tombol ⚙ di
  anjungan meminta PIN lewat papan angka; tablet memverifikasi ke server
  (`POST /v1/kiosk/pin/verifikasi`, penundaan 1/5/15 menit per tablet setelah
  5/10/15 kali salah, dihitung di server) dan, bila server tidak terjangkau,
  dengan hash terakhir yang dikirim pada `/v1/kiosk/display`
  (`settings_pin`). Pengaturan menutup sendiri setelah 2 menit tanpa
  sentuhan.
  - **Tidak diminta** pada tablet yang belum pernah tersambung (belum
    dipasang, supaya alamat server dapat diisi) dan bila server belum
    memasang PIN.
- **Mode putar saja.** Bila server tidak terjangkau ≥ 30 detik (dan tablet
  pernah tersambung), semua fitur mati: tanpa menu, tiket, kotak prioritas,
  dan ⚙. Layar memutar video dari salinan di tablet (daftar *Layar penuh*;
  bila kosong, daftar *Panel atas*) dengan teks redup "Menghubungkan ke
  server…". Tanpa media: "Layanan antrian sementara tidak tersedia. Silakan
  hubungi petugas." Kembali normal otomatis begitu server terjangkau; tidak
  menyela pengunjung yang sedang di layar konfirmasi atau hasil nomor.
  Daftar media terakhir disimpan di tablet supaya mode ini bekerja sesudah
  dinyalakan ulang saat server mati.
- **Jalan pulih.** Dalam mode putar saja, sentuh-tahan pojok kiri bawah
  5 detik (tanpa tanda di layar) membuka papan PIN yang diperiksa dengan hash
  tersimpan; bila benar, ⚙ terbuka untuk memperbaiki alamat server.
- **Tempat tampil untuk folder tablet.** Pada sumber media *Folder media di
  tablet ini*, tiap berkas di **Kelola media tablet** punya tombol *Keduanya /
  Panel atas / Layar penuh* (disimpan di tablet menurut nama berkas). Pada
  sumber server, aturan server yang berlaku.

### Salinan media: status, segarkan, dan salin dari server

- **Status per anjungan.** Tablet melaporkan berapa berkas daftar putar yang
  sudah tersalin utuh (`POST /v1/kiosk/media-status`: `total`, `copied`,
  `bytes`). Kartu perangkat di **Layanan Anjungan** menampilkannya di kolom
  **Media**, mis. "2 dari 3 tersalin · 58 MB" (hijau bila lengkap, kuning
  bila belum). Dilaporkan saat angkanya berubah dan paling lama lima menit
  sekali.
- **Segarkan media.** Tombol **Segarkan media** pada baris anjungan meminta
  tablet itu memeriksa dan menyalin ulang medianya sekarang, dengan
  melewati jeda coba-ulang unduhan yang gagal. Server menyimpan penandanya
  (`kiosk_device.media_segarkan`) dan mengirimnya sebagai `media_refresh`
  pada `GET /v1/kiosk/display`; tablet menanganinya sekali per penanda.
- **Salin dari server.** Di ⚙ Pengaturan tablet → **Kelola media tablet** →
  **Salin dari server**: daftar SEMUA berkas di folder media server
  (`GET /v1/kiosk/media-library`, bukan hanya daftar putar), dipilih lalu
  disalin ke folder media tablet (`GET /v1/kiosk/media-library/{nama}`).
  Dipakai bila sumber media = Folder media di tablet ini (tanpa jaringan).

If the tablet loses its connection after requesting a number, use **Ulangi
permintaan tiket**. The APK reuses the same request ID, so the server returns
the existing ticket instead of issuing a second number.

Mulai APK 2.4.33:

- Sebelum tombol Ulangi muncul, tablet mencoba lagi dua kali secara senyap
  (jeda 1,5 detik) dengan `request_id` yang sama.
- Layar Ulangi bertahan 30 detik. Tanpa sentuhan, tablet mencoba sekali
  lagi; bila tetap gagal, pilihan dibatalkan dan menu awal kembali. Dulu
  layar ini bertahan selamanya, dan pengunjung berikutnya yang menyentuhnya
  menerima nomor milik orang sebelumnya untuk layanan yang tidak ia pilih.
- Tombol **Kembali** tidak bereaksi selama permintaan masih berjalan,
  supaya nomor yang mungkin sudah terbit tidak tertinggal tanpa tiket.
- Penerbitan tiket memakai antrean kerja sendiri, tidak lagi menunggu di
  belakang pembaruan layar atau laporan yang sedang menggantung.

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
tablet dipasangkan dengan kode. Selama token bersama diterima, tablet yang
dicabut masih dapat masuk memakai token itu; menu **Kesehatan Sistem**
memberi peringatan bila token bersama masih aktif padahal sudah ada tablet
yang dipasangkan.

## HTTP lokal dan HTTPS (mulai anjungan 2.4.24, layar 1.2)

API anjungan memakai HTTP biasa di jaringan kantor, karena sertifikat HTTPS
belum tersedia di sana. Aplikasi Android karena itu tetap mengizinkan
cleartext, tetapi **hanya ke alamat jaringan lokal**:

- `10.x.x.x`, `172.16–31.x.x`, `192.168.x.x`, `127.x.x.x`, `169.254.x.x`,
  IPv6 lokal (`::1`, `fe80::/10`, `fc00::/7`);
- nama komputer tanpa titik (`http://server-antrian:8765`), atau nama
  berakhiran `.local`, `.lan`, `.home.arpa`, `.localdomain`.

Alamat lain (nama domain internet atau IP publik) wajib `https://`. Tablet
menolak menyimpan alamat seperti itu, dan token tidak pernah dikirim ke sana
lewat HTTP. Aturan ini ada di `AlamatServer.java` (salinan identik di modul
anjungan dan layar). `network_security_config` tidak dipakai karena hanya
mengenal nama domain, bukan rentang IP.

Bila kelak ada sertifikat, cukup isi alamat `https://…` di tablet; tidak ada
perubahan aplikasi yang diperlukan, asalkan sertifikatnya dipercaya Android.
Jangan meneruskan port `8765` ke internet sebagai pengganti HTTPS.

## Pembaruan APK dari server

`build-android-kiosk.ps1` menaruh APK beserta versinya di folder `apk\`
(`anjungan.apk` dan `anjungan.json`), dan `build-installer.ps1` membawanya ke
sebelah `AntrianCRO.exe`. Server membagikannya ke tablet; statusnya terlihat
pada baris **APK anjungan** di Layanan Anjungan.

- Server menetapkan versi minimal (`VERSI_MINIMAL` di
  `app/services/apk_anjungan.py`). Tablet di bawahnya berhenti menerbitkan
  nomor, server menolak tiketnya (HTTP 426), dan layar tablet menawarkan
  **PERBARUI DARI SERVER**.
- Sejak server ini versi minimalnya 49 (APK 2.4.33): tablet 2.4.32 ke bawah
  wajib memperbarui sebelum dapat melayani lagi, karena layar Ulangi pada
  APK lama dapat memberi nomor orang sebelumnya kepada pengunjung berikutnya.
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

Install `antrianCRO-<versi>.apk`, connect the tablet to the same Wi-Fi, and
connect the POS80/IWare IW-J200 II printer using a USB host/OTG adapter. At
first launch the kiosk screen appears without requiring server details.
The kiosk searches the local network automatically. If no server is found,
open the gear icon and tap **Cari** beside the server field, or use **Cari
Server Otomatis** on the screen. Then pair the tablet with the 6-digit code
from **Layanan Anjungan → Perangkat → + Tambah perangkat**. There is no
working default token: the server generates a random one, so the
`bapendacro` placeholder in old APKs is always rejected. Until a server is found the display stays on its setup message and
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

The generated APK is `dist\antrianCRO-<versi>.apk`.
