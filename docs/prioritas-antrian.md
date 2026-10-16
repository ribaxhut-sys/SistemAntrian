# Nomor prioritas

Nomor yang didahulukan untuk lansia, disabilitas, dan ibu hamil.

## Siapa yang menandai, siapa yang mencabut

| Aksi | Siapa | Di mana |
|---|---|---|
| **Menandai** | Pengunjung sendiri | Kotak **"Saya lansia / disabilitas / ibu hamil"** di menu awal anjungan Android (APK 2.4.34.1). Petugas yang berjaga mengarahkannya. |
| **Menandai** | Petugas pendaftaran (bila ada) | Pilihan "Pengunjung prioritas" pada layar Terbitkan Nomor |
| **Mencabut** | Petugas pelayanan | Tombol **Cabut prioritas** pada daftar Menunggu dan pada pita nomor aktif |

Petugas pelayanan **tidak dapat menandai**: `QueueService.cabut_prioritas`
hanya mencabut, sehingga satu-satunya jalan menandai adalah anjungan atau
petugas pendaftaran. Pengunjung yang mencentang tetapi tidak berhak dicabut
oleh petugas dan kembali ke urutan datangnya semula.

Alasan disimpan pada `queue.prioritas` (`LANSIA`, `DISABILITAS`, `IBU_HAMIL`,
atau `PRIORITAS` untuk pilihan anjungan yang tidak merinci) dan asalnya pada
`queue.prioritas_asal` (`PENDAFTARAN` atau `MANDIRI`). Penerbitan dan
pencabutan dicatat di audit (`CREATE_QUEUE`, `CLEAR_PRIORITY`).

## Pengaturan

- **`kiosk.prioritas_aktif`** (Pengaturan › Antrian): menampilkan kotak di
  anjungan. Bila dimatikan, tablet yang masih menampilkannya tetap mendapat
  nomor biasa.
- **`queue.rasio_prioritas`** (bawaan 3): lihat di bawah.

## Urutan panggil

Fungsi murni `app.services.urutan_prioritas.susun`, dipakai service dan
pratinjau di layar petugas:

- **Otomatis (bawaan):** nomor prioritas lebih dulu, tetapi setiap
  `queue.rasio_prioritas` nomor prioritas yang dipanggil beruntun, satu nomor
  biasa disisipkan bila ada. `0` berarti prioritas selalu lebih dulu.
- **Prioritas dulu / Biasa dulu:** pilihan petugas di kepala halaman
  Pelayanan ("Urutan panggil"), berlaku untuk **satu panggilan** lalu kembali
  ke Otomatis.
- Di dalam tiap kelompok urutannya tetap siapa datang lebih dahulu.
- "Beruntun" dihitung dari pemanggilan terbaru hari ini, lintas loket.
- Layar antrian, anjungan, sisa antrian di tiket, dan daftar menunggu semua
  memakai urutan yang sama dengan yang benar-benar terpanggil.

## Tampilan

- Tabel Menunggu Dilayani dan kartu "Berikutnya" menandai nomor prioritas
  dengan ★.
- Pita **★ PRIORITAS** pada kartu nomor aktif; untuk pilihan anjungan memuat
  "dipilih pengunjung, mohon periksa".
- Tiket mencetak "· Prioritas" pada baris jenis layanan.

## Batasan

- Perkiraan waktu tunggu pada tiket masih menghitung urutan datang; untuk
  nomor biasa yang disisipi prioritas angkanya bisa sedikit terlalu rendah.
- Kotak anjungan tidak memeriksa kebenaran: pengawasnya adalah petugas yang
  berjaga dan petugas loket yang dapat mencabutnya.
