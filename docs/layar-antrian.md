# Layar Antrian Android (TV)

Aplikasi `android-kiosk/layar` untuk TV Android atau TV box. Tugasnya
hanya menampilkan dan membunyikan panggilan; ia tidak pernah menerbitkan
nomor (lihat [istilah.md](istilah.md)). Datanya diambil dari API aplikasi
server, sama dengan yang dipakai anjungan.

## Memasang

1. Build di komputer pengembang: `.\build-android-kiosk.ps1` menghasilkan
   `dist\AntrianLayar-1.0.apk` di samping APK anjungan.
2. Pasang APK di TV (flashdisk + pengelola berkas, atau `adb install`).
3. Buka **Layar Antrian**. Saat pertama kali, dialog pemasangan muncul:
   - **Cari server otomatis**, atau ketik `http://<IP-server>:8765`;
   - isi nama layar, misalnya *TV Ruang Tunggu*;
   - di komputer server: **Layanan Anjungan → Perangkat → + Tambah
     perangkat**, lalu ketik kode 6 angkanya di TV.
4. TV muncul di daftar **Perangkat** dengan jenis **Layar antrian**.

Layar antrian **wajib** dipasangkan dengan kode. Token bersama anjungan dan
token tablet anjungan tidak diterima di `/v1/layar/*`.

Pengaturan dibuka lagi dengan tombol **MENU** pada remote, atau **tahan
OK**, atau tahan judul papan bila TV-nya layar sentuh.

## Yang ditampilkan

- Satu kartu per loket: nomor yang sedang dipanggil/dilayani, atau
  ISTIRAHAT/KOSONG. Nomor selalu **satu baris** (PB-014); hurufnya
  dikecilkan sampai muat selebar kartu.
- Panggilan terbaru disorot 10 detik.
- Kolom **Berikutnya** (jumlahnya mengikuti `display.next_count`) dan sisa
  yang menunggu.
- Jam dan zona waktu dari server (WIB), bukan dari setelan TV.

## Suara

Setiap panggilan, termasuk panggil ulang, berbunyi nada lalu diucapkan
dengan kalimat yang sama dengan layar antrian Windows
(`sound_service.teks_pengumuman`), misalnya *"Nomor antrian P B, nol satu
empat, silakan menuju Loket satu."*

- Ucapan memakai text-to-speech Android dengan bahasa Indonesia. Bila TV
  belum punya suara Bahasa Indonesia, yang berbunyi hanya nadanya. Pasang
  lewat **Setelan → Bahasa → Output text-to-speech** (misalnya Speech
  Services by Google, unduh data Bahasa Indonesia).
- Mengikuti pengaturan **display.sound_enabled** di server.
- TV yang baru menyala atau baru tersambung lagi **tidak** membunyikan
  panggilan yang sudah lewat.
- Bila layar antrian Windows (`--tv`) masih menyala di ruangan yang sama,
  matikan suara salah satunya supaya panggilan tidak terdengar dua kali.

## Saat server tidak terjangkau

Sesudah tiga kegagalan berturut-turut (sekitar 6 detik), papan terakhir
tetap tampil tetapi diredupkan, muncul pita *"Terputus dari server sejak
…"*, dan tidak ada suara. Begitu tersambung, papan kembali normal.

## Menyala sendiri

- Aplikasi mencoba membuka diri sesudah TV menyala (`BOOT_COMPLETED`).
  Banyak TV box mengizinkannya; bila tidak, jadikan **Layar Antrian**
  aplikasi awal (*startup app* / *auto start*) di setelan TV box.
- Layar dijaga tetap menyala, dan isi papan digeser beberapa piksel tiap
  5 menit supaya panel tidak terbakar.

## Peralihan dari layar antrian Windows

Layar antrian Windows (`AntrianCRO.exe --tv`) tetap ada sampai TV Android
terbukti berjalan di kantor. Sesudah itu ia dihapus, sama seperti anjungan
Windows (docs/istilah.md).

## API

| Endpoint | Isi |
|---|---|
| `GET /v1/layar/state` | judul, `sound_enabled`, kartu loket (`name`, `queue_number`, `category`, `status`), `next`, `total_waiting`, `server_time_ms`, `timezone` |
| `GET /v1/layar/calls` | tanpa `after`: hanya `last_id`; dengan `after=N`: panggilan baru (`id`, `queue_number`, `counter_name`, `call_number`, `text`) |
