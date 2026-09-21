# Rancangan — Menetapkan Peran Tiap Komputer

Dokumen rancangan, belum ada kodenya. Berisi masalah yang dipecahkan,
bentuk yang diusulkan, dan hal-hal yang sengaja **tidak** dikerjakan
beserta alasannya.

Ditujukan untuk pemasangan sebenarnya: 5 komputer loket, 1 anjungan ambil
nomor, 1 televisi ruang tunggu, dan — bila jadi dipasang — 1 papan LED
memanjang di atas pintu.

---

## 1. Masalah

Pertanyaan "komputer ini dipakai sebagai apa" sekarang dijawab di **empat
tempat yang berbeda**, dan tiga di antaranya tidak punya tampilan sama
sekali.

| Yang ditentukan | Disimpan di | Cara menyetel | Bertahan? |
|---|---|---|---|
| Server / klien / berdiri sendiri | `data/mesin.json` | Dialog "Atur komputer ini" | ya |
| Peran layar (TV / anjungan / loket) | — | flag pintasan `--tv`, `--kios`, … | hanya selama pintasannya dipakai |
| Bentuk layar | `ANTRIAN_BENTUK_LAYAR` | `setx` di command prompt | tanpa tampilan |
| Printer tiket | `ANTRIAN_PRINTER` | `setx` | tanpa tampilan |
| Suara panggilan | `ANTRIAN_SUARA` | `setx` | tanpa tampilan |

Untuk tujuh komputer, pemasang menjalankan empat ritual berbeda per mesin.

### Kegagalan yang paling mungkin terjadi

Peran layar hanya hidup di dalam pintasan. Cukup satu orang menyalakan
`AntrianCRO.exe` langsung — atau pintasannya rusak setelah pembaruan — dan
**televisi ruang tunggu membuka dialog pilih-mode lalu layar login, di
depan pengunjung**. Komputer itu tidak tahu apa pun tentang dirinya
sendiri; yang tahu hanyalah ikon yang diklik.

---

## 2. Yang sudah benar dan JANGAN diubah

- **`data/mesin.json` dan dialog "Atur komputer ini"** menangani peran
  database dengan benar, lengkap dengan tombol Uji koneksi. Itu bagian
  yang paling berbahaya bila salah — dua PostgreSQL yang sama-sama
  "menang" menghasilkan nomor antrian kembar — dan bagian itu sudah aman.
- **`ANTRIAN_DB_URL` mengalahkan berkas.** Pemasangan lama yang memakai
  `setx` tidak boleh berubah perilakunya. Janji yang sama berlaku untuk
  seluruh environment variable di rancangan ini.
- **Flag CLI yang sudah ada** (`--tv`, `--kios`, `--kios-totem`, `--layar`,
  `--admin`, `--petugas`) tetap bekerja persis seperti sekarang. Pintasan
  yang sudah dibuat di komputer mana pun tidak boleh rusak.
- **Tidak ada deteksi otomatis peran.** Alasannya sama dengan yang sudah
  ditulis di `app/core/mesin.py`: menebak salah satu kali jauh lebih mahal
  daripada bertanya sekali saat pemasangan.

---

## 3. Bentuk yang diusulkan

### 3.1 Satu pertanyaan, bukan lima

Pemasang menjawab **satu** pertanyaan — *"Komputer ini dipakai sebagai
apa?"* — dan sisanya disimpulkan:

| Peran | Halaman yang dibuka | Printer | Suara | Bentuk layar |
|---|---|---|---|---|
| Loket petugas | layar petugas | **tidak mencetak** | ikut pengaturan | ikut pengukuran |
| Loket admin | layar admin | **tidak mencetak** | ikut pengaturan | ikut pengukuran |
| Anjungan ambil nomor | anjungan | ikut pengaturan | **diam** | ikut pengukuran |
| Anjungan berdiri (totem) | anjungan totem | ikut pengaturan | **diam** | ikut pengukuran |
| Televisi ruang tunggu | papan antrean | **tidak mencetak** | ikut pengaturan | ikut pengukuran |
| Papan memanjang di atas pintu | papan antrean | **tidak mencetak** | **diam** | **memanjang** |

Peran hanya menyatakan apa yang benar-benar diketahuinya tentang mesin itu,
dan diam untuk sisanya. "Tidak mencetak" adalah fakta tentang komputer loket
— tidak ada pencetak yang menempel padanya. Tetapi *bagaimana* mencetak,
bagi mesin yang memang mencetak, tetap keputusan seluruh sistem lewat
`ticket.printer`; peran tidak berhak menebaknya.

Yang "ikut pengaturan" mengikuti nilai bersama di database, persis seperti
mesin yang tidak menyebut apa-apa lewat environment hari ini. Yang "ikut
pengukuran" menyerahkan bentuk layarnya pada papan, yang mengukur sendiri.

Dua baris yang diam bukan kebetulan, dan keduanya punya alasan yang sama.
README sudah mencatatnya untuk anjungan: ia sengaja tidak berbunyi supaya
tidak bersahutan dengan televisi. **Papan memanjang mewarisi alasan itu
persis** — kantor yang memasang televisi *dan* pita di atas pintu akan
mendapat dua pengeras suara memanggil nomor yang sama, setengah detik
berselisih, sepanjang hari.

### 3.2 Peran MENGISI formulir, bukan mengunci

Peran bukan kotak tertutup. Memilih "Televisi ruang tunggu" **mengisi**
keempat isian di bawahnya, dan isian itu tetap terlihat serta tetap dapat
diubah. Tidak ada yang perlu keluar dari peran untuk menyimpang darinya —
cukup ubah satu isian, dan namanya menjadi *"Televisi ruang tunggu
(disesuaikan)"*.

Isian yang tidak lagi mengikuti perannya diberi tanda, dan setiap isian
punya jalan pulang: **"Kembalikan ke bawaan peran"**, satu per isian dan
satu untuk seluruh mesin. Pilihan yang tidak dapat dibatalkan dari dalam
aplikasi hanya akan membuat orang takut mencobanya.

### 3.3 Di mana disimpan: berkas BARU, bukan `mesin.json`

Peran komputer ditulis ke **`data/peran.json`**, terpisah dari
`mesin.json`.

Alasannya bukan kerapian melainkan keamanan. `mesin.json` menyimpan **kata
sandi database**, dan docstring-nya sudah memperingatkan supaya tidak
disalin ke komputer anjungan, ke git, maupun ke log. Begitu peran layar
ikut masuk ke berkas yang sama, orang justru akan lebih tergoda
menyalinnya antar-komputer sebagai contekan — dan ikut menyebarkan
sandinya ke tujuh mesin.

`peran.json` tidak memuat rahasia apa pun. Ia aman dibuka, dibaca, dan
disalin sebagai contoh.

### 3.4 Yang disimpan adalah PILIHAN, bukan hasil simpulannya

Ini keputusan terpenting di seluruh dokumen, dan yang paling mudah
terlewat.

Godaannya adalah menyimpan hasil akhirnya:

```json
{ "peran": "tv", "printer": "none", "suara": true, "bentuk_layar": "auto" }
```

Jangan. Yang disimpan adalah niatnya, dan yang mengikuti peran dibiarkan
kosong:

```json
{ "peran": "tv", "printer": null, "suara": null, "bentuk_layar": "memanjang" }
```

`null` berarti *"ikut perannya"*. Nilai berarti *"saya memang mau yang
ini"*. Pada contoh di atas hanya bentuk layar yang benar-benar dipilih
manusia — panel LED yang menerima gambar 16:9 lalu memotong sepetak
memanjang darinya.

Bedanya baru terasa kemudian. Bila suatu saat ternyata televisi sebaiknya
ikut diam — kantor memasang pengeras suara tersendiri — versi baru cukup
mengubah satu tabel simpulan, dan ketujuh komputer langsung ikut betul.
Dengan bentuk yang pertama, ketujuhnya membeku pada nilai yang ditulis saat
pemasangan dan harus didatangi satu per satu.

### 3.5 Berkas yang enak ditulis tangan

Lima komputer loket isinya sama persis. Pemasang akan menyalin satu
`peran.json` ke empat mesin lain lewat Notepad, dan itu **harus didukung**,
bukan dilawan:

- kunci berbahasa Indonesia, sama seperti seluruh kode di repositori ini
- nilai yang terbaca manusia — `"anjungan-totem"`, bukan angka `3`
- berkas rusak atau setengah tertulis tidak pernah menjatuhkan aplikasi;
  perilakunya kembali seperti sekarang dan kejadiannya dicatat di log

Dialog menyimpan lewat tombol **Simpan**, bukan otomatis saat diketik —
sama seperti `SetupMesinDialog` yang sudah ada. Host yang baru setengah
diketik tidak boleh langsung berlaku.

### 3.6 Urutan kewenangan

Untuk **peran layar**:

```
flag CLI  →  data/peran.json  →  dialog pilih mode
```

Komputer yang sudah punya `peran.json` **tidak pernah lagi menampilkan
dialog pilih-mode**. Itulah yang menutup kegagalan di bagian 1.

Untuk **printer, suara, dan bentuk layar**:

```
environment  →  data/peran.json  →  pengaturan database  →  bawaan kode
```

Environment tetap di urutan teratas. Mesin yang sudah disetel dengan
`setx ANTRIAN_PRINTER` hari ini harus berperilaku sama persis besok.

---

## 4. Perubahan per berkas

| Berkas | Perubahan |
|---|---|
| `app/core/peran.py` | **baru** — dataclass `PeranKomputer`, baca/tulis `peran.json`, dan tabel simpulan di 3.1 |
| `app/ui/login/setup_mesin_dialog.py` | bagian kedua: "Komputer ini dipakai sebagai" — peran mengisi isian di bawahnya, isian tetap dapat diubah, ada "Kembalikan ke bawaan peran", dan tombol **Uji cetak** di samping Uji koneksi |
| `app/main.py` | urutan flag → `peran.json` → dialog |
| `app/core/config.py` | `printer`, `suara`, `bentuk_layar` membaca `peran.json` bila environment kosong |
| `app/ui/main_window.py` | bilah status menampilkan peran di samping lokasi database |
| `tests/test_peran.py` | **baru** — simpulan tiap peran, urutan kewenangan, berkas rusak/hilang |

### Uji cetak

Pasangan yang paling berguna untuk tombol Uji koneksi yang sudah ada.
Printer IWare IW-J200 menuntut driver POS80 resmi di port CP001 dan harus
menjadi printer default; bila salah satu meleset, ketahuannya baru saat
pengunjung pertama sudah berdiri di depan anjungan. Jauh lebih murah
ketahuan ketika pemasang masih duduk di depan mesinnya.

### Bilah status

`teks_status_database` sudah menulis `Database: PostgreSQL @ host:5432/antrian`.
Ditambah perannya menjadi:

```
Televisi ruang tunggu · Database: PostgreSQL @ 192.168.1.10:5432/antrian
```

Saat memasang tujuh komputer, memastikan sekilas mana yang mana — tanpa
membuka dialog satu per satu — menghemat lebih banyak waktu daripada yang
terlihat.

---

## 5. Yang sengaja TIDAK dikerjakan

- **Deteksi peran dari hostname atau jaringan.** Lihat bagian 2.
- **Memindahkan peran ke tabel pengaturan database.** Peran adalah sifat
  satu mesin; pengaturan bersama bernilai satu untuk seluruh sistem.
  Menaruhnya di sana berarti menyetel televisi ikut menyetel anjungan —
  persis masalah yang sudah dipecahkan `ANTRIAN_PRINTER`.
- **Memindahkan sandi database ke Windows Credential Manager.** Layak
  dikerjakan, tetapi berdiri sendiri dan tidak menghalangi rancangan ini.
  Dicatat di sini supaya tidak hilang.
- **Menghapus flag CLI.** Lihat bagian 2.

---

## 6. Risiko dan koordinasi

`mesin.json` beserta dialognya baru dibuat pada commit `325b1b4`, oleh
pekerjaan yang mungkin masih berjalan. Bagian 3 dan 4 menyentuh berkas yang
sama. **Pastikan pekerjaan itu selesai sebelum rancangan ini dimulai**,
supaya keduanya tidak saling menimpa.

Risiko lain: `peran.json` yang rusak atau terhapus tidak boleh membuat
aplikasi gagal terbuka. Bila berkasnya tidak terbaca, perilakunya kembali
persis seperti sekarang — dialog pilih-mode muncul — dan kejadiannya
dicatat di log.

---

## 7. Urutan pengerjaan

Bertahap, tiap tahap berdiri sendiri dan punya tesnya sendiri.

1. **`app/core/peran.py` + tesnya.** Tanpa tampilan, tanpa menyentuh
   berkas siapa pun. Seluruh tabel simpulan dan urutan kewenangan diuji
   di sini.
2. **`app/main.py` membaca `peran.json`.** Menutup kegagalan utama:
   televisi berhenti membuka dialog di depan pengunjung.
3. **Dialog menulis `peran.json`.** Sampai tahap ini berkasnya masih
   ditulis tangan; sesudahnya tidak perlu lagi.
4. **Bilah status, penimpaan per butir, dan Uji cetak.** Kenyamanan,
   bukan keharusan — tetapi Uji cetak akan sering dipakai.

Tahap 1 dan 2 sudah cukup untuk memasang tujuh komputer dengan selamat.
