# Nomor prioritas

Nomor yang didahulukan untuk lansia, disabilitas, dan ibu hamil.

## Siapa yang menandai

Hanya **petugas pendaftaran**, saat menerbitkan nomor, lewat pilihan
"Pengunjung prioritas" di layar Terbitkan Nomor. Pilihan kembali ke "Biasa"
setiap nomor terbit supaya pengunjung berikutnya tidak ikut didahulukan.
Anjungan dan peran lain ditolak oleh service (`QueueService.create_queue`),
bukan hanya disembunyikan di layar.

Alasan disimpan pada kolom `queue.prioritas` (`LANSIA`, `DISABILITAS`,
`IBU_HAMIL`; kosong = biasa) dan dicatat pada audit `CREATE_QUEUE`.

## Urutan panggil

Fungsi murni `app.services.urutan_prioritas.susun`, dipakai service dan
pratinjau di layar petugas:

- **Otomatis (bawaan):** nomor prioritas lebih dulu, tetapi setiap
  `queue.rasio_prioritas` (bawaan **3**) nomor prioritas yang dipanggil
  beruntun, satu nomor biasa disisipkan bila ada. `0` berarti prioritas
  selalu lebih dulu. Admin mengubahnya di Pengaturan › Antrian.
- **Prioritas dulu / Biasa dulu:** pilihan petugas di kepala halaman
  Pelayanan ("Urutan panggil"), berlaku untuk **satu panggilan** lalu kembali
  ke Otomatis.
- Di dalam tiap kelompok urutannya tetap siapa datang lebih dahulu.
- "Beruntun" dihitung dari pemanggilan terbaru hari ini, lintas loket.

## Tampilan

- Tabel Menunggu Dilayani dan kartu "Berikutnya" memakai urutan panggil dan
  menandai nomor prioritas dengan ★.
- Tiket mencetak "· Prioritas" pada baris jenis layanan.

## Batasan

- Perkiraan waktu tunggu pada tiket masih menghitung urutan datang; untuk
  nomor biasa yang disisipi prioritas angkanya bisa sedikit terlalu rendah.
- Prioritas tidak dapat diubah sesudah nomor terbit; batalkan dan terbitkan
  ulang bila salah menandai.
