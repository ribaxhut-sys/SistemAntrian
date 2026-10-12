# Prosedur Darurat — Server Database Mati

Pada pemasangan beberapa loket, **seluruh loket, anjungan, dan layar
televisi bergantung pada satu komputer server** (PostgreSQL + API
anjungan). Bila server mati, tidak ada nomor yang dapat diterbitkan,
dipanggil, maupun diselesaikan. Dokumen ini adalah langkah yang dijalankan
petugas sampai server pulih.

Cetak halaman ini dan tempel di setiap meja loket, bersama beberapa lembar
**Catatan Darurat** (bagian 4).

---

## 1. Tanda-tandanya

- Pita merah di bagian atas aplikasi loket: **"Server database tidak
  terjangkau"**. Pita muncul setelah ±20 detik tanpa sambungan dan hilang
  sendiri saat pulih.
- Anjungan menampilkan pesan gagal mengambil nomor.
- Televisi berhenti memperbarui nomor.

Bila hanya **satu** loket yang melihat pita merah sementara loket lain
normal, masalahnya di komputer atau kabel loket itu, bukan di server.

## 2. Langkah petugas loket

1. **Jangan menutup aplikasi.** Sambungan pulih sendiri begitu server
   kembali; aplikasi yang ditutup harus login ulang.
2. Beri tahu administrator.
3. Layani dengan **nomor manual**:
   - Pakai awalan **D** (darurat) dan nomor urut dari kertas di loket
     masing-masing, misalnya Loket 2 memakai `D2-01`, `D2-02`, …, supaya
     dua loket tidak memberikan nomor yang sama.
   - Panggil secara lisan.
   - Catat di **Catatan Darurat**: nomor, jam datang, jenis layanan, jam
     selesai.
4. Pengunjung yang sudah memegang tiket sebelum server mati tetap
   dilayani menurut urutan tiketnya; catat juga di lembar yang sama.
5. Pengaduan yang diterima selama darurat ditulis di kertas, lalu
   dimasukkan ke aplikasi setelah pulih. **Simpan kertasnya di tempat
   terkunci** — isinya data pribadi pelapor — dan hancurkan setelah
   dimasukkan.

## 3. Langkah administrator

1. Pastikan komputer server menyala dan kabel jaringannya tersambung.
2. Di server, buka `services.msc` dan periksa layanan
   **postgresql-x64-17** berstatus *Running*. Bila berhenti, klik
   **Start**.
3. Periksa ruang disk server. Disk penuh menghentikan PostgreSQL.
4. Buka aplikasi di server sebagai ADMIN → **Kesehatan Sistem** untuk
   ringkasan database, API anjungan, backup, dan disk.
5. Bila server tidak dapat dipulihkan dalam waktu wajar dan ada komputer
   pengganti, pulihkan backup terbaru di sana (lihat
   [panduan-proyek.md](panduan-proyek.md) bagian 8). **Kunci enkripsi
   backup** dibutuhkan: lihat catatan kunci yang disimpan saat enkripsi
   diaktifkan, lalu masukkan lewat **Backup → Masukkan Kunci**.
6. Setelah pulih, umumkan ke loket. Nomor manual yang masih menunggu
   dilayani lebih dahulu; tidak perlu dimasukkan sebagai nomor antrian
   baru.

## 4. Catatan Darurat (cetak beberapa lembar per loket)

Loket: ______  Tanggal: ______________  Petugas: ____________________

| No. darurat | Jam datang | Jenis layanan | Jam selesai | Keterangan |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |

Lembar ini diserahkan ke penyelia di akhir hari. Jumlahnya ditambahkan
secara manual ke laporan harian, karena antrian selama darurat tidak
tercatat di aplikasi.

## 5. Mencegah sebelum terjadi

- Pasang **UPS** di komputer server, sakelar jaringan, dan router.
- Atur BIOS server agar menyala sendiri setelah listrik pulih
  (*Restore on AC power loss: Power On*).
- Pastikan backup harian terbentuk dan **folder salinan kedua** terisi
  (menu **Backup**). Lakukan uji pemulihan ke komputer lain setidaknya
  sekali sebelum operasional dan setiap tiga bulan.
- Simpan catatan **kunci enkripsi backup** di tempat terpisah dari server
  (misalnya amplop tertutup di lemari penyelia).
