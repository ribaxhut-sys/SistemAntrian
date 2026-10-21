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

## Mencabut prioritas dari nomor yang sudah dipanggil

Bila pengunjung memilih prioritas sendiri di anjungan, loket memanggilnya, lalu
petugas melihat ia tidak berhak, tombol **Cabut prioritas** pada pita nomor aktif
membuka dialog dengan dua tindak lanjut:

- **Kembalikan ke antrian dan panggil berikutnya** (bawaan): prioritas dicabut,
  nomor kembali berstatus Menunggu dengan urutan datang semula, loket bebas
  memanggil nomor berikutnya. Pengunjung duduk kembali dan dipanggil pada
  gilirannya. Riwayat pemanggilannya tidak dihapus.
- **Tetap layani sebagai nomor biasa**: hanya prioritasnya yang dicabut; nomor
  tetap Dipanggil di loket yang sama.

Alasan wajib (Tidak memenuhi syarat, Salah pilih di anjungan, Lainnya) dan
dicatat di audit `CLEAR_PRIORITY` bersama `alasan_cabut` dan `dikembalikan`.
Hanya nomor berstatus **Dipanggil** yang dapat dikembalikan; nomor yang sudah
dilayani ditolak (`QueueService.cabut_prioritas(..., kembalikan=True)`).
Dialog juga punya kotak **Cetak ulang tiket tanpa tanda prioritas** (bawaan
tercentang), dan kartu nomor aktif punya tombol **Cetak ulang tiket** yang membaca
keadaan nomor saat itu. Hasilnya mengikuti pencetak mesin ini: komputer petugas
tanpa printer menjawab "Printer tidak digunakan." (peran petugas bawaannya tidak
mencetak). Pencabutan dari daftar Menunggu tetap tanpa dialog. Layar antrian Android
menyaring nomor yang sudah dipanggil dari daftar menunggu dan menyegarkan diri
seketika, sehingga nomor yang dikembalikan hilang dari kotak loket dan muncul
lagi di daftar menunggu. Tiket yang sudah dicetak tetap bertuliskan "· Prioritas".

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
