# Keamanan sesi petugas

Ringkasan aturan sesi dan kata sandi, serta perilaku layar kerja yang terkait.

## Batas percobaan login

- Satu akun yang **gagal masuk berulang dalam 15 menit** ditunda bertingkat,
  dihitung dari percobaan gagal terakhir; percobaan berikutnya (termasuk
  dengan kata sandi benar) ditolak sampai penundaan lewat:

  | Gagal beruntun | Penundaan |
  |---|---|
  | 3 | tombol "Lupa kata sandi admin?" muncul di layar masuk |
  | 5–7 | 1 menit |
  | 8–9 | 5 menit |
  | 10 atau lebih | 15 menit |

- Hitungan dikosongkan oleh masuk yang berhasil dan oleh pemulihan admin.
- Dihitung dari audit log (`LOGIN_FAILED`), jadi percobaan dari komputer loket
  mana pun ikut terhitung dan tidak hilang saat aplikasi dibuka ulang.
- Percobaan yang **ditolak karena penundaan tidak dicatat** sebagai kegagalan
  baru. Tanpa itu penyerang dapat mengunci pemilik akun tanpa batas.
- Dihitung per **nama yang diketik**, bukan per akun yang ada: nama yang
  tidak terdaftar ditunda dengan pesan dan urutan yang sama, sehingga
  penundaan tidak membocorkan akun mana yang ada.
- Akun lain tidak terpengaruh. Kode: `AuthService._sisa_penundaan`,
  konstanta `TINGKAT_PENUNDAAN` dan `JENDELA_LOGIN_GAGAL_MENIT`.

## Kata sandi

- Panjang minimal **8 karakter** (`MIN_PASSWORD_LENGTH`). Akun bawaan
  `admin` / `admin123` tetap sah (8 karakter) dan wajib diganti saat masuk
  pertama.
- Kata sandi lama yang lebih pendek tetap dapat dipakai masuk; aturan ini
  berlaku saat kata sandi dibuat atau diganti.

## Kunci layar setelah menganggur

- Setelan **Keamanan › Kunci layar setelah menganggur** (`sesi.idle_menit`),
  bawaan **15 menit**, `0` mematikannya.
- Setelah tidak ada gerakan mouse atau papan ketik selama itu, jendela
  ditutup layar kunci yang meminta kata sandi akun yang sedang masuk.
  Nomor yang sedang dipegang loket **tidak dilepas**.
- Kata sandi salah dicatat sebagai percobaan gagal dan ikut batas percobaan
  di atas. **Keluar dari aplikasi** mengakhiri sesi.
- Hanya untuk sesi akun. Layar antrian dan anjungan tidak dikunci.

## Pemulihan database

`BackupService.restore` **menolak** berjalan bila ada loket yang tanda
hadirnya masih segar (≤ 90 detik) selain sesi yang memulihkan. Minta petugas
memilih **Keluar**, tunggu sebentar, lalu ulangi. Alasannya: memulihkan
database selagi loket bekerja dapat merusak nomor yang sedang dilayani.

## Jendela kerja

Jendela admin, supervisor, dan petugas dibuka **maksimal** (taskbar tetap
terlihat). `F11` untuk layar penuh, `Esc` kembali ke maksimal. Argumen
`--jendela` mempertahankan jendela biasa untuk pengembangan.

## Notifikasi penundaan login

- Percobaan gagal kelima langsung memberi tahu: "akun ditunda N menit".
- Percobaan berikutnya menyebut **sisa waktu** ("coba lagi dalam 3 menit
  20 detik"), dan penundaan dihitung dari percobaan tertua dalam jendela.
- Awal penundaan dicatat **sekali** di audit sebagai `LOGIN_LOCKED`, sehingga
  muncul di "Aktivitas terakhir" Dashboard admin.

## Admin lupa kata sandi: kunci dari pengembang

Bila tidak ada admin lain untuk menyetel ulang, pulihkan dengan kunci yang
hanya dapat dibuat pengembang (tanda tangan digital Ed25519).

1. Di layar masuk pilih **Lupa kata sandi admin?**, lalu **Buat kode
   tantangan**. Kode (`ANTR-...`) berisi ID pemasangan, nama akun, nomor
   acak, dan masa berlaku 24 jam. Tidak ada kata sandi di dalamnya.
2. Kirim kode itu kepada pengembang.
3. Pengembang memeriksa permintaan, menandatangani dengan alat kunci
   miliknya, dan mengirim **kunci respons** (`RESP-...`).
4. Admin menempel kunci respons dan memilih kata sandi baru. Akun wajib
   mengganti kata sandi lagi saat masuk, dan penundaan login sebelumnya
   dihapus. Dicatat sebagai `RESET_ADMIN_KEY`.

Sifat keamanannya:

- Aplikasi hanya menyimpan kunci **publik** (`app/core/kunci_publik.py`),
  yang tidak dapat dipakai membuat tanda tangan.
- Respons berlaku untuk **satu pemasangan, satu akun, satu kali pakai**;
  nomor acak yang sudah dipakai diingat.
- Percobaan respons yang salah dibatasi 5 kali dalam 5 menit (hitungan
  bersama untuk seluruh pemasangan).
- Kode tantangan dibuat tanpa memeriksa apakah akunnya ada atau berperan
  admin, supaya layar masuk tidak membuka daftar akun admin. Pemeriksaan
  dilakukan saat pemulihan, setelah tanda tangan terbukti sah.
- Kunci publik kosong berarti fitur belum aktif dan layar menyatakannya.
- **Batas:** orang yang memegang akun `postgres` atau administrator Windows
  di server tetap dapat mengubah database langsung.

### Alat pengembang

Alatnya **tidak ada di repository dan tidak ikut installer**; ia berada di
folder pengembang di luar proyek (mis. `D:\sistemantrian kunci`) beserta
kunci rahasianya (`kunci-reset.pem`, terenkripsi kata sandi kunci).

- **Buat kunci** (sekali): tab *Buat kunci*, lalu tempel baris
  `KUNCI_PUBLIK_BASE64 = "..."` ke `app/core/kunci_publik.py` dan bangun
  ulang aplikasi.
- **Tanda tangani**: tab *Tanda tangani*, tempel kode tantangan, periksa
  akun dan masa berlakunya, masukkan kata sandi kunci, kirim kunci respons.
- Simpan **salinan cadangan** `kunci-reset.pem` di tempat terpisah. Jika
  berkas atau kata sandinya hilang, jalur ini tidak dapat dipakai lagi
  (jalur database tetap ada).
- Format kode di alat harus sama dengan `app/services/pemulihan_admin.py`;
  alat menyediakan `uji_kompatibilitas.py` untuk memeriksanya.

## Penyimpanan kata sandi dan nama pengguna

| Data | Penyimpanan |
|---|---|
| Kata sandi | hash **scrypt** bergaram acak; tidak dapat dibalik, tidak masuk log maupun audit |
| Nama pengguna dan nama lengkap | teks biasa: dipakai untuk login, keunikan, dan laporan |

Hash lebih tepat daripada enkripsi untuk kata sandi: tidak ada kunci yang
dapat dicuri untuk membukanya. Nama pengguna tidak dienkripsi di kolomnya;
perlindungan data diam diberikan oleh enkripsi disk server dan folder
backup (BitLocker). **Kesehatan Sistem** memeriksa bahwa setiap akun memakai
hash yang sah.

## Menghapus dan mengarsipkan petugas

- **Hapus permanen** hanya untuk akun yang belum punya riwayat apa pun
  (antrian, panggilan, catatan pengaduan, survey, dan audit log). Akun yang
  pernah masuk punya jejak audit; menghapusnya mengosongkan pelaku pada
  barisnya, sehingga ia diarsipkan, bukan dihapus.
- Akun yang pernah bekerja **diarsipkan**: dinonaktifkan, dilepas dari loket,
  riwayatnya utuh dan namanya tetap tampil di laporan lama. Nama dapat
  disamarkan menjadi `Petugas diarsipkan #n`.
- Hanya `ADMIN`; tidak untuk diri sendiri, tidak untuk akun ADMIN lain
  (akun petugas, pendaftaran, supervisor, dan layar antrian yang diizinkan), dan
  ditolak bila petugas masih masuk di loket. Dicatat sebagai `DELETE_USER`
  atau `ARCHIVE_USER`.
- Tombol **Hapus / Arsipkan** ada di Data Master › Pengguna.

## Catatan keterbatasan

- Penundaan login dapat dipakai orang lain untuk menunda akun tertentu
  sampai 15 menit (kompromi yang diterima; akun lain dan admin lain tidak
  terpengaruh).
- Nama pengguna lama tetap ada di meta audit setelah penyamaran nama; yang
  disamarkan hanya akunnya.
- Kunci layar membaca `sesi.idle_menit` saat jendela dibuka; perubahan
  berlaku pada sesi berikutnya. Layar pemantauan yang sengaja dibiarkan
  menyala dapat diatur ke `0`.

## API anjungan: token bersama dan pembatas tebakan

- `X-Device-Id` pada **token bersama** diisi pengirim sendiri. Bila ID itu
  milik tablet yang **sudah dipasangkan**, permintaan diperlakukan tanpa ID:
  tidak mencatat kontak, status printer, maupun status media atas nama
  tablet itu (`device_service.keadaan_perangkat`).
- Penundaan **PIN pengaturan** dikunci per tablet terpasang, atau per
  **alamat IP** untuk token bersama; mengganti `X-Device-Id` tidak lagi
  mengosongkan hitungan.
- **Hash PIN** (`settings_pin` di `/v1/kiosk/display`) hanya dikirim ke tablet
  terpasang. PIN 6 angka = sejuta kemungkinan, jadi hash yang bocor dapat
  ditebak habis di luar server dalam hitungan menit. Tablet token bersama
  memakai salinan yang sudah ia simpan (atau tanpa PIN bila belum pernah).
- **Kode pasang**: tebakan salah dibatasi 10 per IP dalam 10 menit (IP itu
  mendapat 429), dan semua kode terbuka dihanguskan bila satu IP mencapai
  10 atau gabungan semua IP mencapai 30. Kode ditandai terpakai dengan
  pembaruan bersyarat, sehingga dua permintaan bersamaan tidak dapat
  memakai kode yang sama.

## Pembaruan Windows bertanda tangan

- PC loket hanya menawarkan pembaruan dari server yang **bertanda tangan
  Ed25519** atas (versi, ukuran, SHA-256), diverifikasi terhadap kunci
  publik yang sama dengan pemulihan admin (`app/core/kunci_publik.py`),
  dengan pemisah domain `antrian-pembaruan-windows-v1`. Tanpa tanda tangan
  sah, pembaruan diabaikan dan dicatat di log.
- Alur rilis: `build-installer.ps1`, lalu di komputer pengembang
  `.\.venv\Scripts\python.exe alat\tandatangani_pembaruan.py
  dist\Pembaruan-AntrianCRO.exe --kunci "<folder kunci>\kunci-reset.pem"`.
  Alat menulis `.version` dan `.sig`; salin ketiga berkas ke folder
  `pembaruan` di komputer server. Alat menolak menulis bila kuncinya tidak
  cocok dengan kunci publik tertanam.
- **Kesehatan Sistem** memberi peringatan bila installer di server tidak
  bertanda tangan sah.

## Kata sandi bawaan

**Kesehatan Sistem › Kata sandi bawaan** (MASALAH) menyebut akun aktif yang
masih memakai kata sandi seed. Yang ditampilkan hanya nama akunnya.

## Berkas rahasia di komputer

`mesin.json` (sandi PostgreSQL) dan `anjungan-token.txt` berada di folder
data di bawah `%LOCALAPPDATA%` (installer per pengguna), sehingga izin
bawaan profil Windows sudah membatasinya ke pemilik akun, SYSTEM, dan
Administrator. ACL tambahan sengaja tidak dipasang: berisiko memutus tugas
SYSTEM yang membaca token. Pengecualian: menjalankan dari kode di drive lain
(mis. `D:\SistemAntrian\data`) mengikuti izin drive tersebut.

## Enkripsi salinan backup kedua

Keputusan pemilik (17 Oktober 2026): **backup di server tetap polos**
(pemulihan cepat); yang dienkripsi hanya **salinan kedua** (folder lain atau
flashdisk, `backup.salinan_folder`), karena salinan itulah yang dibawa pergi.

- **Backup › Atur Sandi Salinan…** (minimal 12 karakter). Kata sandi **tidak
  disimpan**: dari sandi diturunkan pasangan kunci X25519 (scrypt N=2^15);
  database hanya menyimpan kunci publik + garam (`backup.salinan_kunci_enkripsi`).
  Backup otomatis cukup memakai kunci publik.
- Salinan menjadi `<nama>.dump.antrianenc` (AES-256-GCM per potongan 1 MiB,
  urutan dan akhir berkas dilindungi). Tidak ada salinan polos maupun
  `.sha256` di folder kedua selama sandi diatur; sidik SHA-256 ada di kepala
  berkas. Retensi ikut menghapus salinan terenkripsi yang kedaluwarsa.
- **Buka Salinan Terenkripsi…**: berkas dibuka ke folder backup sebagai backup
  biasa (beserta `.sha256`), lalu **Uji Backup** dan **Pulihkan** seperti biasa.
- **Sandi hilang = salinan terenkripsi tidak dapat dibuka.** Backup di server
  tidak terpengaruh. Mengganti sandi tidak mengubah salinan lama (tetap
  terbuka dengan sandi lamanya). Kode: `app/services/sandi_backup.py`.

## Alamat API anjungan

- **Layanan Anjungan › Dengarkan di**: *Semua antarmuka (bawaan)* atau satu
  IPv4 LAN komputer ini (`kiosk.api_alamat`). Berlaku setelah **Pasang ulang
  & nyalakan ulang**.
- Dengan IP terpilih, API mendengar di IP itu **dan 127.0.0.1** (pemeriksa
  kesehatan dan status bar di server mengetuk 127.0.0.1).
- Bila IP terpilih tidak lagi dimiliki komputer (DHCP), API **kembali ke semua
  antarmuka** dan mencatat peringatan di log, supaya tablet tidak putus.
  Beri IP tetap pada server sebelum memakai pilihan ini.
- `ANTRIAN_KIOS_API_HOST` tetap menang (pengembangan). Pencarian UDP 8766
  tetap di semua antarmuka (siaran LAN). Firewall tetap `LocalSubnet`.

## Yang sengaja belum dikerjakan

- Parameter scrypt tidak dinaikkan (menambah waktu hash pada seluruh login
  dan suite tes); perlu pengukuran lebih dulu.
- Mematikan token bersama: langkah operasional di Layanan Anjungan setelah
  semua tablet dipasangkan (peringatannya ada di Kesehatan Sistem).
