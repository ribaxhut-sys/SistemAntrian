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

## Yang sengaja belum dikerjakan

- Parameter scrypt tidak dinaikkan (menambah waktu hash pada seluruh login
  dan suite tes); perlu pengukuran lebih dulu.
- Matikan token bersama API kiosk dan ikat API ke IP LAN: langkah operasional
  di Layanan Anjungan dan pada lingkungan server.
