# Uji Terima Sistem Antrian & Survey CRO

Daftar periksa sebelum sistem dinyatakan siap dipakai di loket. Dikerjakan
pada komputer tujuan, bukan komputer pengembang, dan memakai `AntrianCRO.exe`
hasil build — bukan dijalankan dari source.

Isi kolom hasil dengan ✅ atau ❌ beserta catatan bila gagal.

---

## A. Pemasangan

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| A1 | Salin folder `dist\AntrianCRO` ke komputer tujuan | Folder tersalin utuh | |
| A2 | Jalankan `AntrianCRO.exe` pertama kali | Jendela masuk terbuka; folder `data`, `logs`, `backup` terbentuk sendiri | |
| A3 | Periksa `data\queue.db` | Berkas database ada dan berukuran > 0 | |
| A3b | Jalankan `AntrianCRO.exe --init-only`, lalu baca `logs\app.log` | Tercatat "Fondasi siap" beserta nomor revisi skema | |
| A4 | Tutup lalu buka kembali aplikasi | Terbuka normal, data tidak hilang | |
| A5 | Cabut kabel jaringan, buka aplikasi | Tetap berjalan normal — sistem ini 100% offline | |

## B. Masuk pertama kali

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| B1 | Masuk sebagai `admin` / `admin123` | Diterima, lalu dialog ganti kata sandi muncul dan tidak dapat dibatalkan | |
| B2 | Coba tutup dialog ganti kata sandi | Tidak bisa; aplikasi tidak dapat dipakai sebelum diganti | |
| B3 | Ganti kata sandi | Berhasil; menu administrasi terbuka | |
| B4 | Masuk dengan kata sandi lama | Ditolak dengan pesan yang jelas, bukan traceback | |

## C. Data master

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| C1 | Buat satu akun untuk tiap peran (REGISTRATION, CRO, SUPERVISOR, DISPLAY) | Tersimpan | |
| C2 | Tambah satu jenis layanan baru | Muncul di layar penerbitan nomor | |
| C3 | Nonaktifkan satu jenis layanan | Tidak lagi dapat menerbitkan nomor untuk layanan itu | |
| C4 | Tambah satu loket | Muncul di pilihan loket panel pelayanan | |

## C2. Pengaturan

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| C5 | Buka menu **Pengaturan** sebagai ADMIN | Seluruh pengaturan tampil terkelompok | |
| C6 | Ubah judul layar antrian, tekan Simpan | Tersimpan; layar antrian memakai judul baru | |
| C7 | Ubah beberapa pengaturan lalu tekan "Batalkan Perubahan" | Kembali ke nilai tersimpan, tidak ada yang berubah | |
| C8 | Tekan Simpan tanpa mengubah apa pun | Dinyatakan tidak ada yang berubah; audit log tidak bertambah | |
| C9 | Coba isi jeda penyegaran dengan 1 | Kotak angka menahannya di batas minimum | |
| C10 | Periksa tab Jejak Aktivitas | Perubahan tercatat sebagai `CHANGE_CONFIGURATION` | |

## D. Penerbitan nomor

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| D1 | Masuk sebagai REGISTRATION, terbitkan nomor layanan A | Muncul `A-001` | |
| D2 | Terbitkan lagi | `A-002` | |
| D3 | Terbitkan nomor layanan B | `B-001`, bukan `B-003` | |
| D4 | Tekan tombol angka `1`–`9` | Memilih jenis layanan tanpa mouse | |
| D5 | Periksa folder `tiket\` | Berkas PDF tiket terbentuk (bila `ticket.printer` = `pdf`) | |
| D6 | Setel `ticket.printer` = `none`, terbitkan nomor | Nomor tetap terbit, tidak ada PDF, tidak ada error | |
| D7 | Ubah tanggal komputer ke hari berikutnya, terbitkan nomor | Kembali ke `A-001` | |

## E. Alur pelayanan

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| E1 | Masuk sebagai CRO, tekan `F2` | Nomor terdepan terpanggil ke loket terpilih | |
| E2 | Tekan `F2` lagi tanpa menyelesaikan | Ditolak dengan pesan bahwa loket masih menangani nomor | |
| E3 | Tekan `F3` | Panggilan ulang tercatat; hitungan panggilan naik | |
| E4 | Tekan `F4` lalu `F8` | Status berpindah Dilayani lalu Selesai | |
| E5 | Panggil nomor, tandai Tidak Hadir | Status `NO_SHOW`; nomor tidak kembali ke daftar tunggu | |
| E6 | Batalkan nomor yang masih menunggu | Status `CANCELLED` | |
| E7 | Tunda lalu lanjutkan pelayanan | Kembali ke Dilayani; waktu penundaan tetap terhitung | |

## F. Layar antrian

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| F1 | Masuk sebagai DISPLAY di komputer/monitor kedua | Hanya menu Layar Antrian yang tersedia | |
| F2 | Panggil satu nomor dari loket | Layar berubah paling lambat 2 detik | |
| F3 | Dengarkan suara | Nada dua-nada lalu pengumuman lisan lengkap dengan nomor loket | |
| F4 | Panggil ulang nomor yang sama | Berbunyi lagi, bukan diam | |
| F5 | Jalankan di komputer tanpa perangkat suara | Tetap berjalan normal, hanya tanpa bunyi | |

## G. Survey kepuasan

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| G1 | Sebagai CRO, selesaikan satu pelayanan | Tombol "Minta Survey" menyala | |
| G2 | Tekan "Minta Survey", pilih nilai, kirim | Tersimpan; tombol kembali padam | |
| G3 | Buka menu "Survey Kepuasan" | Nomor yang sudah dinilai tidak muncul lagi di daftar | |
| G4 | Isi survey dari layar kios untuk nomor lain | Tersimpan; muncul ucapan terima kasih | |
| G5 | Coba menilai nomor yang sama dua kali | Ditolak dengan pesan bahwa nomor sudah pernah dinilai | |
| G6 | Beri nilai 1 pada satu pelayanan | Status antrian TETAP Selesai, tidak berubah | |
| G7 | Setel `survey.enabled` = `false` | Layar survey menyatakan dinonaktifkan; tombol padam | |

## H. Ringkasan harian

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| H1 | Masuk sebagai SUPERVISOR | Hanya menu Ringkasan Harian yang tersedia | |
| H2 | Cocokkan angka per status dengan kenyataan di loket | Sama persis | |
| H3 | Periksa rata-rata menunggu dan pelayanan | Terisi wajar; `—` bila memang belum ada datanya | |
| H4 | Periksa ringkasan kepuasan | Rata-rata dan sebaran nilai sesuai survey yang masuk | |
| H5 | Terbitkan nomor baru dari komputer lain, tunggu 30 detik | Angka menyegar sendiri tanpa ditekan `F5` | |
| H6 | Coba memanggil atau menyelesaikan antrian | Tidak ada tombolnya — supervisor memantau, tidak mengubah | |

## I. Backup dan pemulihan

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| I1 | Masuk sebagai ADMIN, buka "Backup & Audit" | Folder backup tertulis di layar | |
| I2 | Tekan "Backup Sekarang" | Berkas `queue-YYYYMMDD-HHMMSS.db` muncul di daftar dan di folder | |
| I3 | Tutup lalu buka aplikasi keesokan harinya | Backup otomatis harian terbentuk sendiri | |
| I4 | Buka aplikasi dua kali dalam satu hari | Backup otomatis hanya dibuat sekali | |
| I5 | Terbitkan beberapa nomor, lalu pulihkan dari backup sebelumnya | Nomor-nomor itu hilang; backup pengaman ikut terbentuk | |
| I6 | Buka tab "Jejak Aktivitas" | Terlihat baris BACKUP dan RESTORE beserta pelakunya | |
| I7 | Telusuri seluruh jejak aktivitas | TIDAK ada satu pun kata sandi yang tercatat | |

## J. Hak akses

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| J1 | Masuk sebagai CRO | Tidak ada menu Data Master maupun Backup | |
| J2 | Masuk sebagai SUPERVISOR | Tidak dapat memanggil atau menyelesaikan antrian | |
| J3 | Masuk sebagai ADMIN | Tidak dapat memanggil maupun menerbitkan antrian | |
| J4 | Masuk sebagai DISPLAY | Hanya layar antrian; tidak ada fungsi lain sama sekali | |
| J5 | Nonaktifkan sebuah akun, coba masuk dengan akun itu | Ditolak | |

## K. Ketahanan

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| K1 | Matikan komputer paksa saat ada antrian berjalan, nyalakan lagi | Data sebelum mati tetap ada; aplikasi terbuka normal | |
| K2 | Buka aplikasi di dua komputer sekaligus menunjuk database yang sama | Nomor antrian tidak pernah kembar | |
| K3 | Jadikan folder `tiket\` hanya-baca, terbitkan nomor | Nomor tetap terbit; hanya pencetakan yang gagal | |
| K4 | Periksa `logs\app.log` | Kejadian tercatat; tidak ada kata sandi di dalamnya | |
| K5 | Picu sebuah kegagalan (mis. hapus folder backup saat backup) | Pesan berbahasa Indonesia yang jelas, bukan traceback Python | |

---

## Persetujuan

| | Nama | Tanggal | Tanda tangan |
|---|---|---|---|
| Diuji oleh | | | |
| Disetujui oleh | | | |
