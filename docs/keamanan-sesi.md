# Keamanan sesi petugas

Ringkasan aturan sesi dan kata sandi, serta perilaku layar kerja yang terkait.

## Batas percobaan login

- Satu akun yang **gagal masuk 5 kali dalam 5 menit** ditunda: percobaan
  berikutnya (termasuk dengan kata sandi benar) ditolak sampai jendela
  5 menit itu lewat.
- Dihitung dari audit log (`LOGIN_FAILED`), jadi percobaan dari komputer loket
  mana pun ikut terhitung dan tidak hilang saat aplikasi dibuka ulang.
- Percobaan yang **ditolak karena penundaan tidak dicatat** sebagai kegagalan
  baru. Tanpa itu penyerang dapat mengunci pemilik akun tanpa batas.
- Akun lain tidak terpengaruh. Kode: `AuthService._terlalu_banyak_gagal`,
  konstanta `BATAS_LOGIN_GAGAL` dan `BATAS_LOGIN_GAGAL_MENIT`.

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
- Percobaan respons yang salah dibatasi 5 kali dalam 5 menit.
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
  (antrian, panggilan, catatan pengaduan, survey).
- Akun yang pernah bekerja **diarsipkan**: dinonaktifkan, dilepas dari loket,
  riwayatnya utuh dan namanya tetap tampil di laporan lama. Nama dapat
  disamarkan menjadi `Petugas diarsipkan #n`.
- Hanya `ADMIN`; tidak untuk diri sendiri, tidak untuk akun ADMIN lain, dan
  ditolak bila petugas masih masuk di loket. Dicatat sebagai `DELETE_USER`
  atau `ARCHIVE_USER`.
- Tombol **Hapus / Arsipkan** ada di Data Master › Pengguna.

## Yang sengaja belum dikerjakan

- Parameter scrypt tidak dinaikkan (menambah waktu hash pada seluruh login
  dan suite tes); perlu pengukuran lebih dulu.
- Matikan token bersama API kiosk dan ikat API ke IP LAN: langkah operasional
  di Layanan Anjungan dan pada lingkungan server (peringatannya sudah ada di
  Kesehatan Sistem).
