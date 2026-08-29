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
| A5 | Cabut kabel jaringan, buka aplikasi | Pemasangan SQLite satu komputer tetap berjalan normal | |

## A2. Pemasangan beberapa loket (PostgreSQL)

Lewati bagian ini bila hanya satu komputer yang dipakai.

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| A6 | Pasang PostgreSQL di komputer server, buat database `antrian` | Selesai tanpa error | |
| A7 | Setel `ANTRIAN_DB_URL` di satu loket, jalankan aplikasi | Skema terbentuk sendiri lewat migration | |
| A8 | Setel `ANTRIAN_DB_URL` di loket lainnya, jalankan aplikasi | Melihat data yang sama; migration tidak dijalankan ulang | |
| A9 | Periksa bilah status | Menunjuk server PostgreSQL, bukan berkas lokal | |
| A10 | **Dua loket menerbitkan nomor pada saat yang sama** | Nomor berurutan, **tidak ada yang kembar** | |
| A11 | Ulangi A10 beberapa kali dengan dua orang menekan bersamaan | Tetap tidak ada nomor kembar | |
| A12 | Loket A memanggil nomor; amati loket B dan layar antrian | Perubahan terlihat di semua komputer | |
| A13 | Dua loket mencoba memanggil nomor terdepan bersamaan | Hanya satu yang mendapatkannya | |
| A14 | Matikan server PostgreSQL saat loket sedang melayani | Pesan berbahasa Indonesia yang jelas, bukan traceback | |
| A15 | Nyalakan kembali server, lanjutkan melayani | Loket pulih sendiri tanpa perlu dibuka ulang | |
| A16 | Setel `ANTRIAN_DB_PATH` sekaligus `ANTRIAN_DB_URL` di satu loket | Tetap memakai PostgreSQL, tidak diam-diam kembali ke berkas lokal | |

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
| D8 | Terbitkan nomor saat sudah ada 3 orang menunggu | Tiket menyebut "Sisa antrian: 3" | |
| D9 | Terbitkan nomor saat tidak ada seorang pun menunggu | Tiket menyebut "Tidak ada sisa antrian" | |
| D10 | Terbitkan nomor layanan B saat yang menunggu semuanya layanan A | Angka sisa antrian menghitung SELURUH layanan, bukan layanan B saja | |

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
| F1 | Masuk sebagai DISPLAY di komputer/monitor kedua | Langsung layar penuh; tidak ada bilah atas, menu, bilah status, maupun bingkai jendela | |
| F1b | Amati layar dari posisi pengunjung | Tidak terlihat nama petugas, lokasi database, maupun tombol Keluar | |
| F1c | Tekan `F11` lalu `F11` lagi | Keluar dari layar penuh dan kembali lagi | |
| F1d | Tekan `F5` di layar kios | Data disegarkan; TIDAK muncul bilah status di bawah | |
| F1e | Tekan `Ctrl+Q` | Petugas tetap dapat menutup aplikasi | |
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
| I8 | **PostgreSQL:** backup dari komputer server | Berkas `.dump` terbentuk | |
| I9 | **PostgreSQL:** backup dari komputer loket tanpa pg_dump | Pesan jelas yang menyebut pengaturan folder perkakas, bukan traceback | |
| I10 | **PostgreSQL:** pulihkan dari `.dump`, lalu periksa dari loket lain | Seluruh loket melihat data yang sudah dipulihkan | |
| I11 | Periksa daftar proses saat backup berjalan | Kata sandi database TIDAK terlihat pada argumen perintah | |

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

## L. Anjungan ambil nomor (tanpa login)

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| L1 | Buka aplikasi tanpa argumen | Dialog pilihan **Layar Antrian** / **Anjungan Ambil Nomor** / **Layar Petugas** | |
| L2 | Pilih Anjungan Ambil Nomor | Langsung layar penuh; papan nomor + tombol ambil nomor; tanpa login, tanpa bilah status | |
| L3 | Buka dengan `AntrianCRO.exe --kios` | Dialog dilewati; anjungan terbuka sendiri | |
| L3b | Buka dengan `AntrianCRO.exe --layar` (pintasan lama) | Sama seperti `--kios`; pintasan lama tidak mati | |
| L4 | Sentuh satu jenis layanan | Nomor terbit (mis. `A-001`); tiket tercetak (bila printer aktif) | |
| L5 | Sentuh lagi segera setelahnya | Tombol mati dan ada keterangan menunggu; nomor kedua belum terbit | |
| L6 | Tunggu jeda selesai, ambil nomor lagi | Nomor berikutnya terbit | |
| L7 | Panggil nomor dari loket | Papan di anjungan menyegar paling lambat 2 detik | |
| L8 | Cabut printer / kehabisan kertas, ambil nomor | Nomor tetap terbit; hanya pencetakan yang gagal | |
| L9 | **PostgreSQL:** dari mesin anjungan, coba baca tabel `app_user` | Ditolak hak akses; hash kata sandi petugas tidak terbaca | |
| L10 | Panggil nomor dari loket, dengarkan anjungan | Anjungan **diam**; hanya televisi yang mengumumkan | |
| L11 | Setel `ANTRIAN_SUARA=1` di anjungan, buka ulang, panggil nomor | Anjungan ikut bersuara — pemasangan satu-mesin tetap bisa | |
| L12 | Setel `ANTRIAN_PRINTER=none` di satu komputer loket, terbitkan nomor dari sana | Loket itu tidak mencetak; anjungan tetap mencetak | |
| L13 | Setel `ANTRIAN_SUARA=yaa` (salah ketik) di televisi | Diperlakukan seperti tidak diisi; panggilan TETAP bersuara | |

## M. Layar antrian televisi (tanpa login)

Dijalankan di komputer televisi ruang tunggu, terpisah dari anjungan.

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| M1 | Buka dengan `AntrianCRO.exe --tv` | Dialog dilewati; papan nomor layar penuh, tanpa login | |
| M2 | Amati layarnya | Hanya papan nomor — tidak ada tombol ambil nomor, bilah atas, maupun bilah status | |
| M3 | Panggil satu nomor dari loket | Nada "ting" terdengar lebih dulu, baru pengumuman lisan | |
| M4 | Berdiri di ujung ruang tunggu | Nomor antrian terbaca dari jarak itu | |
| M5 | Cabut listrik komputer televisi, nyalakan lagi | Papan kembali sendiri tanpa ada yang mengetik apa pun | |
| M6 | **PostgreSQL:** dari mesin televisi, coba terbitkan nomor lewat SQL | Ditolak hak akses; televisi hanya boleh membaca | |
| M7 | **PostgreSQL:** dari mesin televisi, coba baca tabel `app_user` | Ditolak hak akses | |
| M8 | Terbitkan nomor pada satu layanan lebih banyak dari `display.list_rows` x 2 | Daftar bawah terbagi halaman; judulnya menyebut "1 / 2" | |
| M9 | Amati satu menit tanpa menyentuh apa pun | Halaman berganti sendiri sesuai `display.rotate_seconds`, lalu kembali ke halaman 1 | |
| M10 | Berdiri di ujung ruang tunggu saat halaman berganti | Masih sempat membaca satu halaman penuh sebelum berganti | |
| M11 | Sisakan antrian lebih sedikit dari satu halaman | Halaman berhenti berganti; tidak ada kedipan | |
| M12 | Panggil nomor sampai halaman terakhir habis saat sedang tampil | Layar kembali ke halaman 1, tidak menjadi kosong | |
| M13 | Ganti tema ke Sorotan dan Split | Daftar menunggu tetap ada, nomornya tidak berdempetan | |
| M14 | Terbitkan nomor pada dua jenis layanan berbeda | Daftar bawah terbagi sebanyak jenis layanan; tiap kolom berjudul nama layanannya | |
| M15 | Biarkan satu jenis layanan tanpa antrian | Kolomnya tetap ada, berisi "—"; lebar papan tidak berubah-ubah | |
| M16 | Nonaktifkan satu jenis layanan yang masih ada yang menunggu | Kolomnya tetap tampil sampai nomor terakhirnya dipanggil | |
| M17 | Perhatikan nomor pada daftar bawah | Angka utuh — tidak ada yang terpotong atas atau bawahnya | |
| M18 | Isi 10 nomor pada satu layanan | Tampil 2 kolom x 5 baris di dalam kolom layanan itu | |
| M19 | Ubah **Baris nomor per kolom** menjadi 3, buka ulang layar | Tiga baris; hurufnya membesar mengikuti ruang yang lowong | |
| M20 | Isi **Ukuran huruf nomor menunggu** dengan 90, buka ulang | Huruf tetap diperkecil agar muat; tidak ada yang terpotong | |

## N. Pengaduan dan catatan petugas

Bagian ini menguji satu-satunya tempat data pribadi pengunjung disimpan.
Jalankan seluruhnya, termasuk yang tampak sepele.

| # | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|
| N1 | Buka panel Pelayanan tanpa memanggil nomor | Kartu **Data Pelapor** terlihat tetapi isiannya mati; panel kanan menampilkan tab **Menunggu Dilayani** | |
| N1b | Amati kartu Data Pelapor | Lima isian terbaca utuh; tidak ada label atau kotak yang saling menimpa | |
| N2 | Panggil satu nomor | Isian Data Pelapor hidup; panel kanan **berpindah sendiri** ke tab Pengaduan & Catatan | |
| N2a | Amati tab Pengaduan & Catatan | Berisi kotak **Pengaduan** dan **Catatan Petugas** saja — tanpa isian identitas | |
| N2b | Amati kedua kotak | Label dan isian terbaca utuh; tidak ada yang saling menimpa atau terpotong | |
| N2c | Perkecil jendela sekecil mungkin | Berhenti pada ukuran minimum aplikasi; isian tetap tidak tergencet | |
| N2d | Perhatikan kapsul di kanan atas panel | Bertuliskan KOSONG; berubah menjadi CATATAN lalu PENGADUAN mengikuti isian | |
| N2e | Ketik keluhan tanpa mengisi Data Pelapor | Nama dan No. Pelanggan di kartu Data Pelapor **langsung** bertanda wajib dan berbingkai kuning — tanpa menekan apa pun | |
| N2f | Tekan Simpan dalam keadaan itu | Ditahan; keterangan di kaki panel meminta melengkapi Data Pelapor; keluhan yang tertulis tetap ada | |
| N2g | Lengkapi Nama dan No. Pelanggan | Bingkai kuning hilang sendiri begitu diisi, tanpa menekan Simpan | |
| N2h | Tekan Simpan | Tersimpan; identitas ikut tersimpan bersama keluhannya | |
| N2i | Perhatikan penghitung huruf di bawah kotak | Angkanya berjalan; berubah warna mendekati batas | |
| N3 | Klik tab **Menunggu Dilayani** secara manual, lalu tekan `F3` (panggil ulang) | Tab **tetap** di Menunggu Dilayani — memanggil ulang tidak mengganti antrian yang dipegang loket | |
| N3b | Dari keadaan itu, tekan `F9` | Berpindah ke tab Pengaduan & Catatan, kursor langsung di kotak yang relevan | |
| N4 | Isi Catatan Petugas saja, tekan Ctrl+S | Tersimpan; waktu simpan muncul; isian **tidak** ikut terhapus | |
| N5 | Isi Deskripsi Pengaduan tanpa nama, tekan Simpan | Ditolak dengan kalimat Indonesia yang jelas; isian tetap ada | |
| N6 | Lengkapi nama dan nomor pelanggan, simpan | Tersimpan | |
| N7 | Isi email `budi.contoh.id` (tanpa @) | Ditolak; bentuk emailnya disebut | |
| N8 | Isi telepon `0812` | Ditolak; terlalu pendek | |
| N9 | Ketik keluhan valid (nama & nomor pelanggan terisi), tekan `F8` | Pelayanan selesai; lembar tersimpan otomatis tanpa menekan Simpan lebih dulu; panel kanan kembali ke tab Menunggu Dilayani | |
| N9b | Ketik deskripsi TANPA nama, tekan `F8` | Pelayanan **TIDAK** selesai; keterangan di kaki panel muncul; isian tetap ada | |
| N10 | Selesaikan pelayanan, panggil nomor berikutnya | **Data Pelapor kosong** dan kedua kotak kosong — bukan isian nomor sebelumnya | |
| N11 | Panggil ulang nomor yang lembarnya sudah terisi | Data Pelapor dan kedua kotak terisi kembali seperti terakhir disimpan | |
| N11b | Terbitkan beberapa nomor lagi hingga ada yang menunggu lebih dari 10 menit, lihat judul tab | Judul menyebut jumlah menunggu dan "N lama" | |
| N12 | Buka menu **Pengaduan & Catatan** | Daftar lembar muncul, terbaru di atas | |
| N13 | Cari dengan nama pelapor | Hanya lembar milik nama itu yang tampil | |
| N14 | Cari dengan nomor pelanggan, lalu dengan sepenggal isi pengaduan | Keduanya menemukan lembar yang benar | |
| N15 | Centang **Hanya pengaduan** | Lembar yang hanya berisi catatan petugas hilang dari daftar | |
| N16 | Pilih satu baris | Rincian muncul di kanan; isian yang kosong tidak ditampilkan sebagai "-" | |
| N17 | Periksa layar ini sebagai CRO | Tombol **Hapus Lembar** tidak ada sama sekali | |
| N18 | Masuk sebagai SUPERVISOR, buka menu yang sama | Dapat membaca; tidak ada tombol Hapus | |
| N19 | Masuk sebagai ADMIN, hapus satu lembar | Dikonfirmasi lebih dahulu, lalu hilang dari daftar | |
| N20 | Periksa tab Jejak Aktivitas | Ada `SAVE_NOTE` dan `DELETE_NOTE`; **tidak ada** nama, telepon, atau isi pengaduan di dalamnya | |
| N21 | Buka lembar kemarin dari panel pelayanan, coba ubah | Ditolak: lembar hari sebelumnya tidak dapat disunting | |
| N22 | **PostgreSQL:** dari mesin anjungan, `SELECT * FROM queue_note` | Ditolak hak akses | |
| N23 | **PostgreSQL:** dari mesin televisi, perintah yang sama | Ditolak hak akses | |
| N24 | Buat satu backup, lalu periksa siapa yang dapat membuka folder backup | Folder backup kini berisi data pribadi — pastikan aksesnya memang terbatas | |

---

## Persetujuan

| | Nama | Tanggal | Tanda tangan |
|---|---|---|---|
| Diuji oleh | | | |
| Disetujui oleh | | | |
