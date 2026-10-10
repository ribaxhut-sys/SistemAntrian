# Sistem Antrian & Survey Kepuasan Pelayanan CRO

Panduan menyeluruh untuk pemasangan, penggunaan, PostgreSQL multi-PC,
anjungan Android, backup, dan pengembangan ada di
[docs/panduan-proyek.md](docs/panduan-proyek.md).

Aplikasi desktop lokal untuk mengelola antrian pelayanan CRO
(Customer Relations Officer) dan mengukur kepuasan pengunjung.

Aplikasi berjalan **di jaringan lokal saja**. Tidak ada API, cloud, maupun
sinkronisasi ke luar kantor.

| | |
|---|---|
| Platform | Windows 10 / 11 |
| Python | **3.13** (dikunci — jangan pakai 3.11 atau 3.14) |
| UI | PySide6 |
| Database | PostgreSQL (beberapa loket) atau SQLite (satu komputer) via SQLAlchemy |
| Timezone | Asia/Jakarta (WIB, UTC+7) |

## Memilih database

| Keadaan | Database |
|---|---|
| **Satu komputer** melayani sendirian | SQLite, satu berkas lokal. Tanpa pemasangan apa pun. |
| **Beberapa loket** melayani bersamaan | **PostgreSQL wajib**, dipasang di satu komputer server. |

**SQLite di folder bersama TIDAK bisa dipakai beberapa komputer.** Mode WAL
memakai shared memory yang tidak berfungsi di filesystem jaringan, dan
mematikan WAL pun SQLite mendokumentasikan bug locking di sana. Akibatnya
bukan sekadar lambat, melainkan nomor antrian kembar atau database rusak.

Pindah dari satu komputer ke beberapa loket berarti memasang PostgreSQL —
lihat bagian **Pemasangan Beberapa Loket** di bawah. Konsekuensinya: ada satu
komputer yang bila mati membuat seluruh loket berhenti.

---

## Ruang Lingkup

Sistem ini menangani **dua hal saja**:

1. **Antrian pelayanan** — ambil nomor, panggil, layani, selesaikan
2. **Survey kepuasan** — rating 1–5 setelah pelayanan selesai

Data disimpan agar dapat diketahui **jumlah antrian** dan **hasil survey**.

### Yang TIDAK termasuk

- Pendaftaran / data wajib pajak
- Nomor pengaduan dan penelusuran tindak lanjutnya

**Antrian sendiri tetap anonim.** Pengunjung memilih jenis layanan lalu
menerima nomor; tabel `queue` tidak pernah memuat nama, NIK, nomor HP,
maupun alamat.

**Satu pengecualian, dan tempatnya satu saja.** Petugas dapat menulis
pengaduan beserta identitas pelapor pada tabel terpisah `queue_note` —
lihat [Pengaduan dan catatan petugas](#pengaduan-dan-catatan-petugas).
Terpisah bukan karena rapi, melainkan karena hak akses: komputer anjungan
dapat membaca tabel `queue`, dan pengaduan tidak boleh ikut terbaca dari
mesin yang berdiri di ruang publik tanpa diawasi.

Akibat yang tidak boleh dilupakan: **berkas backup kini berisi data
pribadi.** Folder backup setara lemari arsip, bukan lagi salinan angka.

---

## Aturan Bisnis Utama

**Nomor antrian menggunakan prefix per jenis layanan**, dan urutannya
direset setiap hari:

```
26 Agustus              27 Agustus
PB-001 PBB              PB-001 PBB
PB-002 PBB              PB-002 PBB
B-001  Pengaduan        B-001  Pengaduan
C-001  Informasi
```

**Jenis layanan boleh bertingkat, paling dalam tiga tingkat.** Yang punya
anak berubah peran menjadi KELOMPOK: di anjungan ia hanya membuka daftar
isinya dan **tidak pernah menerbitkan nomor**. Susunan bawaannya:

```
Konsultasi            ← kelompok, tanpa nomor
    PBB               PB-001
    PKB               KB-001
    PAT               AT-001
    Reklame           RK-001
    PBJT              ← kelompok, tanpa nomor
        Restoran      RS-001
        Parkir        PR-001
        Hotel         HT-001
        Hiburan       HB-001
Pengaduan             B-001
Informasi             C-001
```

Nomor terbit atas nama DAUN, bukan atas nama kelompoknya. Karena itu tiap
jenis pajak punya deret sendiri, dan loket dapat dispesialisasikan lewat
**Loket → Jenis Layanan** — misalnya satu loket khusus PBB. Kelompok
ditolak `create_queue()` di service layer, bukan sekadar disembunyikan
dari layar: anjungan memegang daftar layanan di memori dan bisa saja masih
memegang daftar lama beberapa detik sesudah admin menambahkan anak
pertama ke sebuah jenis layanan.

Susunannya diubah dari **Pengaturan → Jenis Layanan**, lewat kolom
**Induk** pada dialog Tambah/Ubah. Tombol **Naik**/**Turun** menggeser
kedudukan **di antara saudara sekelompok** saja; pindah kelompok adalah
perbuatan lain dan tidak boleh terjadi karena Naik ditekan sekali terlalu
banyak.

Tiga hal yang mengikutinya, dan mudah terlupakan:

- **Menonaktifkan kelompok ikut menonaktifkan seluruh isinya.** Kalau
  tidak, PBB dan PKB justru naik menjadi kartu tingkat teratas di
  anjungan — persis kebalikan dari yang diminta admin saat menutup
  Konsultasi. Mengaktifkannya kembali juga mengembalikan isinya.
- **Kelompok yang seluruh anaknya nonaktif kembali menjadi jenis layanan
  biasa** dan menerbitkan nomornya sendiri. Jauh lebih baik daripada
  kartu yang membuka daftar kosong di depan pengunjung yang sudah berdiri
  di sana.
- **Kelompok tidak ikut diperingatkan sebagai "layanan tanpa loket".** Ia
  tidak pernah punya antrian yang bisa terlantar, dan memperingatkannya
  hanya akan mengubur peringatan yang sungguhan.

**Tiket antrian** dicetak 80 × 88 mm. Selain nomor, jenis layanan, loket,
tanggal, dan jam, tiket menyebut **sisa antrian** pada saat tiket dicetak:
banyaknya nomor yang masih menunggu di depan pemegang tiket, dihitung lintas
seluruh jenis layanan karena urutan pemanggilan memang lintas layanan.
Angkanya foto sesaat, bukan janji. Bila gagal dibaca, tiket tetap tercetak
tanpa baris itu.

Cara mencetaknya diatur lewat pengaturan `ticket.printer`:

| Nilai | Perilaku |
|---|---|
| `pdf` | Simpan sebagai berkas PDF di folder `tiket/` (bawaan, selalu berhasil) |
| `system` | Cetak ke printer Windows |
| `none` | Tidak mencetak; nomor cukup disebutkan dan tampil di layar |

**Kegagalan mencetak tidak pernah membatalkan antrian.** Nomor sudah terbit
dan tersimpan sebelum tiket dicetak; petugas cukup menyebutkan nomornya.

**Empat bagian, tugasnya tidak bercampur** (rincian: [docs/istilah.md](docs/istilah.md)):

| Bagian | Perangkat | Tugas | Login |
|---|---|---|---|
| **Anjungan** | Tablet Android + printer USB | Pengunjung memilih layanan, nomor dicetak | tidak |
| **Layar antrian** | Panel Android Maxtor | Menampilkan dan membunyikan panggilan | tidak |
| **Aplikasi server** | 1 PC Windows berperan server | Database, API untuk anjungan/layar antrian, backup, Layanan Anjungan | ya |
| **Aplikasi petugas** | PC Windows di tiap loket | Memanggil dan melayani; admin mengelola data | ya |

Anjungan dan layar antrian tidak lagi menjadi pilihan pada aplikasi Windows.
Keduanya berjalan di Android; Windows langsung membuka login petugas.

Sesudah petugas masuk, panel pelayanan memakai **loket bawaan akun** dan
mengunci pilihannya agar roda mouse atau salah klik tidak memindahkan meja
diam-diam. Akun yang belum memiliki loket bawaan wajib memilih dan
mengonfirmasinya satu kali. Perpindahan berikutnya dilakukan lewat **Ganti
Loket**, disimpan untuk login berikutnya, dan ditolak selama loket lama atau
loket tujuan masih menangani antrian.

Jika petugas meninggalkan pelayanan aktif, pengambilalihan dilakukan ADMIN
melalui **Pelayanan Aktif**, bukan dengan meminjam akun lama. Admin memilih
petugas pengganti (beserta loket bawaannya) dan menulis alasan. Pelayanan yang
sudah berjalan dialihkan dalam keadaan Ditunda agar petugas baru meninjaunya
sebelum melanjutkan. Jika pelayanan tidak akan diteruskan, ADMIN memakai
**Batalkan Paksa**. Kedua tindakan dicatat lengkap dalam jejak aktivitas.

Layar antrian berjalan **tanpa login**: komputer yang menghadap publik dan
tidak diawasi tidak boleh menyimpan kata sandi petugas. Ia membuka layar
penuh tanpa bilah atas, menu navigasi, maupun bilah status.

**Anjungan hanya mengambil nomor.** Ia tidak menampilkan kartu loket,
jumlah yang menunggu, maupun daftar nomor — di layar maupun di struk. Itu
urusan layar antrian.

Jeda `kiosk.cooldown_seconds` menahan satu orang menekan tombol ambil nomor
berulang kali. Akun berperan `DISPLAY` tetap ada dan tetap membuka papan
yang sama, berguna saat supervisor ingin melihat papan dari mejanya.

Petugas tetap dapat keluar dengan `Ctrl+Q`, dan `F11` mengembalikan jendela
ke ukuran biasa saat perlu dipindahkan ke monitor yang benar.

**Layar antrian** menyegar setiap 2 detik dan membunyikan panggilan saat
ada panggilan baru maupun panggilan ulang: nada dua-nada, lalu — setelah
nadanya selesai — pengumuman lisan penuh ("Nomor antrian A, nol dua tiga,
silakan menuju Loket 2") lewat mesin text-to-speech bawaan Windows (memakai
suara Bahasa Indonesia bila tersedia). Tidak ada berkas audio maupun
dependency tambahan yang perlu disiapkan — nada dibangkitkan sendiri dan
TTS memakai mesin yang sudah terpasang di OS. Komputer tanpa perangkat
suara tetap berjalan normal, hanya tanpa bunyi.

**Daftar menunggu di televisi terbagi per jenis layanan.** Tiga jenis
layanan berarti separuh bawah layar terbagi tiga kolom, masing-masing
berjudul nama layanannya:

```
MENUNGGU GILIRAN                              1 / 2
   A · Konsultasi     B · Pengaduan     C · Informasi
   A-013  A-018       B-006  B-011      C-002   —
   A-014  A-019       B-007  B-012      C-003   —
   A-015  A-020       B-008    —          —     —
   A-016    —         B-009    —          —     —
   A-017    —         B-010    —          —     —
```

Setiap layanan mendapat **dua kolom**, karena panel ini lebar dan pendek —
sekitar 1800×400 piksel pada televisi 1080p. Menumpuk sepuluh nomor ke
bawah menghabiskan sisi yang langka dan menyia-nyiakan sisi yang berlimpah:
hurufnya terpaksa turun sampai 18px agar muat. Dua kolom membuat huruf yang
sama muat pada 37px. Nomor dibaca menurun dulu, baru pindah ke kolom
kanannya — urutan baca koran.

Loket dapat dibatasi jenis layanan yang boleh dipanggilnya, sehingga
urutan panggil memang berjalan per layanan. Satu antrean gabungan
menyiratkan urutan yang tidak pernah terjadi — A-020 tampak akan dipanggil
sebelum B-003 padahal keduanya antre di loket yang berbeda.

Isinya seluruh nomor yang menunggu, bukan tiga teratas: yang dicari orang
yang sudah duduk adalah nomornya sendiri, bukan siapa berikutnya. Bila
tidak muat satu layar, daftarnya terbagi menjadi halaman yang berganti
sendiri, dan judul panelnya menyebut halaman ke berapa dari berapa — tanpa
itu, pengunjung yang belum melihat nomornya akan mengira nomornya hilang
lalu bertanya ke loket.

**Tujuh tampilan, satu isi.** Bentuk papan dipilih admin lewat
`display.theme`. Yang berbeda hanya tata letak dan warnanya — seluruh loket
dan seluruh antrian menunggu tetap tampil pada ketujuhnya, karena papan yang
menyembunyikan sebagian antrian mengirim orang bertanya ke loket.

| `display.theme` | Bentuk | Dipilih ketika |
|---|---|---|
| `kaca` *(bawaan)* | Kartu kaca tembus pandang di atas gradien malam | Ruang tunggu berlampu redup |
| `bento` | Kisi tak simetris; loket yang memanggil menempati sel besar | Lobi terang, dan loket tidak sama sibuknya |
| `led` | Baris hitam berangka kuning seperti papan keberangkatan | Dibaca dari jarak sangat jauh, atau layar memanjang |
| `fokus` | Satu nomor raksasa; loket lain menjadi pita di bawahnya | Kantor dengan sedikit loket |
| `sorotan` | Panel putih besar berisi panggilan terbaru | Ruangan ramai, panggilan mudah terlewat |
| `split` | Panel pengumuman di kiri, kolom loket di kanan | Layar yang merangkap papan pengumuman (`display.info`) |
| `kontras` | Putih–hitam dan satu kuning penanda, tanpa gradien | Pengunjung lanjut usia, atau ruangan yang silau |

Nama tema lama (`gelap`, `terang`, `modern`) tetap dikenali dan dipetakan ke
penggantinya, sehingga pembaruan tidak mengembalikan papan yang sudah
disetel ke tampilan bawaan.

**Kartu loket mengecil sendiri saat loketnya banyak.** Lima loket bertumpuk
dua baris menuntut tinggi dua kali lipat, dan yang mengalah selalu daftar
menunggu di bawahnya. Karena itu huruf kartu ikut mengecil mengikuti
banyaknya baris, dan panel daftar menunggu dipatok pada jatahnya — sekitar
separuh papan — supaya keduanya tidak saling menghabiskan.

| Pengaturan | Bawaan | Arti |
|---|---|---|
| `display.theme` | `kaca` | Bentuk papan; tujuh pilihan di tabel atas |
| `display.list_rows` | 5 | Baris per kolom (1–12). Dua kolom per layanan, jadi 5 berarti 10 nomor per layanan (satu kolom pada tema `sorotan` dan `split`, yang panelnya sempit) |
| `display.list_font_size` | 0 | Ukuran huruf nomor; **0 = menyesuaikan sendiri** dengan tinggi papan |
| `display.rotate_seconds` | 3 | Jeda pergantian halaman; **0 = tidak berpindah sendiri** |
| `display.next_count` | 3 | Hanya untuk papan kecil di dalam anjungan |

**Huruf menyesuaikan tinggi papan, dan tingginya diturunkan dari metrik
huruf.** Tinggi baris tidak lagi berupa konstanta — ia dihitung dari huruf
yang harus dimuatnya, sehingga nomor terpotong tidak mungkin lagi terjadi
berapa pun yang diisi admin. `display.list_font_size` diperlakukan sebagai
batas **atas**: papan tetap memperkecilnya bila barisnya tidak muat, dan
bila huruf sudah menyentuh batas terkecil yang masih pantas dibaca, yang
dikurangi adalah barisnya — satu halaman lagi lebih baik daripada nomor
yang tidak terbaca.

Beberapa hal yang sengaja dibuat begitu:

- **Layanan yang sedang sepi tetap mendapat kolomnya** (berisi "—"). Kolom
  yang muncul dan hilang mengikuti isinya membuat lebar seluruh papan
  berubah beberapa detik sekali.
- **Layanan yang dinonaktifkan di tengah hari tetap tampil** selama masih
  ada yang menunggu padanya. Nomor yang sudah terbit tidak batal, dan
  orangnya masih duduk di ruangan itu.
- **Jumlah halaman mengikuti kolom terpanjang**, sehingga halaman berhenti
  setelah layanan paling ramai habis — bukan yang paling sepi.
- **Rotasi berhenti sendiri bila cukup satu halaman.** Halaman yang
  berpindah ke dirinya sendiri terbaca sebagai layar berkedip rusak.
- **Hari yang sangat ramai dibatasi 5 halaman**, sisanya disebut sebagai
  jumlah ("DAN 47 LAINNYA") alih-alih diputar sampai tidak ada yang sabar
  menunggunya kembali.
- **Lebih dari 6 jenis layanan kembali ke daftar gabungan.** Tujuh kolom
  pada satu televisi semuanya terpotong, dan daftar berhalaman lebih
  terbaca daripada tujuh kolom yang tak satu pun memuat nomor secara utuh.

**Panel pelayanan** disusun dua kolom: kartu antrian yang sedang ditangani
beserta seluruh tombolnya di kiri, daftar tunggu di kanan. Kartu berganti
warna mengikuti status — abu-abu saat menganggur, jingga saat nomor sudah
dipanggil tetapi orangnya belum datang, hijau saat pelayanan berjalan,
kuning saat loket istirahat — dan menampilkan penghitung waktu berjalan.
Pada daftar tunggu, baris paling depan ditandai dan kolom lama menunggu
berubah warna setelah 10 dan 20 menit.

Tombol yang tidak sah untuk status saat ini **dinonaktifkan, bukan
disembunyikan**. Posisinya tetap sehingga petugas tidak perlu mencari ulang
setiap kali status berubah — itulah yang menentukan bentuk kisi tombolnya.

**Pintasan papan ketik** (petugas loket jarang menyentuh mouse):

| Layar | Pintasan |
|---|---|
| Terbitkan Nomor | `1`–`9` memilih jenis layanan |
| Pelayanan | `F2` panggil berikutnya · `F3` panggil ulang · `F4` mulai melayani · `F8` selesai |
| Layar kerja | `Ctrl+1`–`Ctrl+9` berpindah menu sesuai urutan pil di bilah atas |
| Semua layar | `F5` muat ulang · `F11` layar penuh · `Ctrl+Q` keluar |

**Menu per peran.** Pada layar kerja, menu menempel sebagai pil di bilah atas — bukan kolom kiri — supaya panel pelayanan mendapat lebar penuh. Anjungan dan televisi tidak menampilkan menu.

| Peran | Menu |
|---|---|
| `REGISTRATION` | Terbitkan Nomor |
| `CRO` | Pelayanan · Survey Kepuasan · Pengaduan |
| `SUPERVISOR` | Pengaduan · Ringkasan Harian · Laporan · Hasil Survey |
| `ADMIN` | Pengaduan · Data Master · Pengaturan · Backup · Tutup Hari |
| `DISPLAY` | Layar Antrian |
| `KIOSK` | Tidak ada layar Windows; sesi API untuk anjungan Android |

**Status antrian:**

```
WAITING → CALLED → SERVING → COMPLETED

CALLED  → NO_SHOW
WAITING → CANCELLED
CALLED  → CANCELLED
SERVING → PAUSED → SERVING
```

Seluruh perpindahan status divalidasi di service layer. Transition ilegal ditolak.

**Survey kepuasan** memakai rating 1–5 (1 = Sangat Tidak Puas, 5 = Sangat Puas)
dengan feedback opsional. Survey menempel pada satu antrian dan tidak boleh
ganda. Survey **tidak mengubah status antrian** — antrian yang sudah
`COMPLETED` tetap `COMPLETED` walau ratingnya 1.

Hanya antrian berstatus `COMPLETED` yang dapat dinilai. Antrian yang
dibatalkan atau tidak hadir tidak pernah menerima pelayanan, sehingga tidak
ada yang bisa dinilai pengunjung.

Survey diisi lewat dua jalur, keduanya memakai layanan yang sama:

| Jalur | Cara |
|---|---|
| Layar kios | Menu **Survey Kepuasan**, dipasang pada monitor kedua atau tablet yang menghadap pengunjung. Pengunjung memilih nomornya sendiri lalu menekan nilai. |
| Diminta petugas | Tombol **Minta Survey** pada panel pelayanan, menyala setelah `F8`. Layar diserahkan kepada pengunjung untuk diisi. |

Survey **tidak muncul sendiri** setelah pelayanan selesai. Petugaslah yang
tahu apakah pengunjung masih di depan meja; dialog yang menyembul sendiri
justru menahan antrian berikutnya. Seluruh survey dapat dimatikan lewat
pengaturan `survey.enabled`.

**Ringkasan harian** tersedia untuk `SUPERVISOR`: jumlah antrian per status
dan per jenis layanan, rata-rata waktu tunggu dan waktu layanan, porsi
antrian yang tuntas dilayani, serta rata-rata dan sebaran nilai kepuasan
hari itu. Layar menyegar sendiri setiap `dashboard.refresh_seconds` detik.

Angka yang belum ada datanya ditampilkan `—`, bukan `0` — keduanya berbeda
arti bagi yang membacanya.

**Backup** berupa file SQLite utuh di folder `backup/`:

| Cara | Kapan |
|---|---|
| Otomatis | Satu kali setiap hari saat aplikasi dibuka, bila `backup.auto_enabled` aktif |
| Manual | Kapan saja oleh `ADMIN` lewat menu **Backup** |

Backup memakai *Online Backup API* bawaan SQLite, bukan penyalinan file
biasa. Aplikasi berjalan dalam mode WAL sehingga sebagian transaksi terbaru
belum masuk ke file utama; salinan mentahnya bisa tertinggal atau rusak.

**Kegagalan backup otomatis tidak pernah menghentikan aplikasi.** Kehilangan
backup satu hari jauh lebih ringan akibatnya daripada loket yang tidak bisa
melayani sama sekali.

Backup yang lebih tua dari `backup.retention_days` dihapus otomatis.
Nilai nol atau negatif diabaikan, agar salah konfigurasi tidak menghapus
salinan yang baru saja dibuat.

**Pemulihan** hanya dapat dilakukan `ADMIN`, dikonfirmasi dua kali, dan
selalu menyalin database yang sedang berjalan terlebih dahulu sebagai
cadangan pengaman. Setelah dipulihkan, aplikasi perlu ditutup dan dibuka
kembali agar seluruh layar membaca data yang baru.

### Pengaduan dan catatan petugas

Setiap nomor antrian punya satu **lembar kerja**, dan pengisiannya dipecah
mengikuti cara petugas bekerja — bukan dialog, keduanya menyatu di panel
kerja:

| Bagian | Di mana | Alasan |
|---|---|---|
| **Data Pelapor** — nama, no. pelanggan, telepon, email, alamat | Kartu tetap di kolom kiri, layar pelayanan | Ditulis sambil **bertanya** kepada orang di depan meja; isian pendek yang harus dapat diisi seketika |
| **Pengaduan** dan **Catatan Petugas** | Tab **Pengaduan & Catatan** di panel kanan | Ditulis sambil **mendengarkan**; kotak panjang yang butuh ruang, dan panel kanan jauh lebih lebar daripada sisa kolom kiri |

**Panel kanan berpindah tab SENDIRI** mengikuti status loket: **Menunggu
Dilayani** selagi loket kosong — saat petugas memilih siapa berikutnya —
lalu otomatis berganti ke **Pengaduan & Catatan** begitu sebuah nomor
dipanggil, saat petugas mulai berbicara dengan orangnya. Tab tetap dapat
dibuka manual kapan pun (atau lewat `F9`), dan berpindah manual tidak
dipaksa kembali oleh penyegaran data selama antrian yang dipegang loket
belum berganti — memanggil ulang (`F3`) tidak menyeret petugas keluar dari
tab yang sengaja ia buka sendiri untuk melirik daftar tunggu.

Kedua kotak keluhan berada dalam **satu halaman**, bukan tab terpisah. Tab
menyembunyikan separuh formulir di balik klik, dan yang tersembunyi justru
catatan petugas, bagian yang paling sering lupa diisi.

**Yang menyimpan adalah panel kanan itu sendiri**, beserta identitas yang
dibacanya dari kartu Data Pelapor. Identitas tidak pernah tersimpan
sendirian: nama pengunjung tanpa keluhan maupun catatan hanyalah data
pribadi tanpa satu pun alasan.

Isi lembarnya:

| Bagian | Isi | Wajib |
|---|---|---|
| **Pengaduan** | Nama, nomor pelanggan, telepon, email, alamat, deskripsi keluhan | Nama, nomor pelanggan, dan deskripsi — bila pengaduan diisi sama sekali |
| **Catatan petugas** | Catatan internal atas pelayanan itu | Tidak. Boleh berdiri sendiri tanpa pengaduan |

**Deskripsi dan catatan sengaja tidak disatukan.** Deskripsi adalah kata
pengunjung; catatan adalah penilaian petugas. Bercampur dalam satu kotak,
penilaian internal ikut terbaca sebagai keluhan pelanggan oleh siapa pun
yang membukanya kemudian.

Aturan yang menjaganya:

- **Satu antrian satu lembar.** Petugas kedua menyunting lembar yang sama,
  bukan menumpuk lembar tandingan yang isinya saling bertentangan.
- **Hanya dapat disunting pada hari yang sama.** Pengaduan yang masih bisa
  diubah berhari-hari kemudian tidak berguna sebagai bukti apa pun.
- **Isinya tidak pernah masuk audit log.** Audit mencatat *bahwa* sebuah
  lembar disimpan, oleh siapa, untuk nomor mana — tidak pernah apa yang
  tertulis di dalamnya.
- **Menyelesaikan pelayanan (`F8`) menyimpan lembarnya lebih dahulu.**
  Kegagalan menyimpan — biasanya karena Nama atau No. Pelanggan belum
  diisi padahal ada deskripsi — membatalkan penyelesaian: kartu antrian
  berganti kosong begitu selesai, sedangkan yang menceritakan keluhannya
  sudah berdiri meninggalkan meja.
- **Simpan (`Ctrl+S`) tidak mengosongkan isian.** Petugas sering menyimpan
  di tengah pembicaraan lalu meneruskan mengetik.
- **Formulirnya mengikuti apa yang sedang diketik.** Begitu deskripsi
  terisi, kapsul di panel berubah menjadi PENGADUAN dan Nama serta No.
  Pelanggan yang masih kosong langsung ditandai wajib di kartu Data
  Pelapor — kedua kartu saling terlihat, sehingga tandanya tidak perlu
  menunggu apa pun ditutup. Penghitung huruf memperingatkan sebelum
  batasnya tercapai, bukan sesudah.
- **Berganti nomor mengosongkan Data Pelapor dan kedua kotak.** Identitas
  maupun keluhan yang tertinggal dari nomor sebelumnya berarti keluhan
  orang ini tersimpan atas nama orang lain.
- **Judul tab Menunggu Dilayani menyebut jumlah yang sudah lama menunggu.**
  Begitu sebuah nomor dipanggil, panel berpindah ke Pengaduan & Catatan dan
  daftar tunggu tidak lagi terlihat tanpa mengklik tabnya — judul tab
  inilah satu-satunya yang tersisa untuk memberi tahu ada yang sudah
  menunggu lebih dari 10 menit.
- **Menulis milik CRO, menghapus milik ADMIN.** Penulis yang sekaligus
  dapat menghilangkan tulisannya membuat catatan itu tidak berguna sebagai
  bukti. Penghapusan tercatat di audit log.
- **Tidak ada pembersihan otomatis.** Lembar disimpan sampai ada yang
  menghapusnya lewat menu **Pengaduan**.

Seluruh petugas CRO dan supervisor dapat mencari lembar lama menurut nama,
nomor pelanggan, isi pengaduan, catatan, atau nomor antrian — pengunjung
yang kembali esok hari ke loket lain tidak perlu menceritakan keluhannya
dari awal.

Layar **Pengaduan & Catatan** menyegar sendiri setiap 30 detik, seperti
Ringkasan Harian — petugas lain terus menulis lembar baru sepanjang hari,
dan layar yang dibiarkan terbuka tidak boleh menyiratkan lembar seseorang
tidak pernah masuk. Penyegaran diam-diam ini memakai kriteria pencarian
yang TERAKHIR DISUBMIT, bukan apa pun yang sedang diketik: pencarian
sengaja hanya berjalan saat Enter/Cari ditekan, dan penyegaran otomatis
tidak boleh mendahului petugas yang belum selesai mengetik kata kuncinya.
Baris yang sedang dibaca juga tidak melompat sendiri — dipertahankan
selama lembarnya masih ada di hasil yang baru.

### Menu bertingkat di anjungan

Menyentuh kartu **Konsultasi** tidak menerbitkan nomor apa pun: kisi
kartunya berganti isi menjadi PBB, PKB, PAT, Reklame, dan PBJT, dan
menyentuh PBJT menggantinya sekali lagi menjadi Restoran, Parkir, Hotel,
dan Hiburan. Baru di kartu terdalam layar konfirmasi muncul.

Yang membedakan kartu kelompok dari kartu layanan hanyalah warna dan satu
tanda — kartunya lebih biru, dan di tempat prefix berdiri tanda `›`, bukan
huruf. Huruf besar di kartu anjungan dibaca pengunjung sebagai nomor yang
akan ia terima; memajang "PJ" pada kartu yang tidak pernah menerbitkan
nomor menjanjikan PJ-001 yang tidak akan pernah ada.

Dua pengaman untuk layar yang berdiri tanpa penjaga:

- **Kartu KEMBALI berdiri paling depan**, sebesar kartu layanan lainnya,
  dan **tidak ikut dimatikan selama jeda pengambilan nomor**. Jalan keluar
  tidak boleh menjadi satu-satunya sasaran sentuh yang lebih kecil
  daripada yang lain, dan jeda tidak boleh mengurung pengunjung di dalam
  menu.
- **Anjungan pulang sendiri ke menu utama** setelah 25 detik tanpa
  disentuh, dan segera sesudah sebuah nomor terbit. Pengunjung yang
  berbalik pergi tidak boleh meninggalkan layar tersangkut di dalam PBJT
  untuk orang berikutnya — orang berikutnya itu tidak tahu ia sedang
  berada di dalam kelompok, dan akan mencari Pengaduan pada daftar yang
  memang tidak memuatnya.

Bila admin menonaktifkan sebuah kelompok tepat ketika ada pengunjung
berdiri di dalamnya, jalurnya dipangkas ke tingkat terdekat yang masih
ada — bukan dibiarkan menunjuk id yang sudah lenyap dan menghasilkan layar
tanpa satu kartu pun.

### Panel informasi anjungan

Paruh atas anjungan berisi satu panel yang bergantian isinya, dan seluruh
berkasnya hidup **di mesin anjungan, bukan di database**. Pengaturan
bersama hanya menyimpan jenis tampilan sambutan; gambar dan videonya
disalin ke folder di sebelah aplikasi pada mesin itu sendiri.

| Keadaan | Isi panel | Berapa lama |
|---|---|---|
| Menganggur | Sambutan: teks, atau isi `media/kiosk` berputar bergiliran | terus-menerus |
| Kelompok dibuka | Media/Info kelompok itu — mis. "Siapkan SPPT dan KTP" pada Konsultasi | selama pengunjung memilih di dalamnya |
| Layanan disentuh | Media layanan itu, atau **Info Anjungan** berupa teks bila tidak ada berkasnya | sampai YA/BATAL, maksimal 15 detik |
| Nomor terbit | Kartu nomor: nomor besar, jenis layanan, sisa antrian, arahan | sampai tombol hidup lagi |

**Media per jenis layanan** dipasang dari **Pengaturan → Media Anjungan per
Jenis Layanan** (atau dari dialog Ubah Jenis Layanan), dan tersimpan di
`media/kiosk/layanan/<kode-layanan>/`. Foldernya dinamai menurut *kode*,
bukan prefix: prefix masih boleh diubah selama layanannya belum dipakai
antrian, sedangkan kode dikunci sejak dibuat.

Beberapa hal yang sengaja dibuat begitu:

- **Satu berkas per layanan, bukan playlist.** Panelnya hanya tampil belasan
  detik; sebuah putaran tidak akan sempat berjalan, dan akan bertabrakan
  dengan mesin putar sambutan.
- **Video diulang terus sampai pengunjung menekan YA atau BATAL.** Karena
  itu klip pendek 5–10 detik justru paling baik: yang datang di tengah tetap
  melihat pesannya utuh dalam beberapa detik. Usahakan frame awal dan
  akhirnya mirip, supaya sambungan tiap putaran tidak berkedip. Layar
  konfirmasi tetap menutup sendiri setelah 15 detik — mengulang tidak
  memperpanjang apa pun.
- **Selalu tanpa suara.** Suara panel akan bertabrakan dengan pengumuman
  nomor.
- **Media mengalahkan Info Anjungan** bila keduanya diisi. Panelnya kecil dan
  nama layanan sudah tampil besar di panel konfirmasi di bawahnya.
- **Setelah nomor terbit, panel TIDAK menyambung klip sambutan yang tadi
  terpotong**, melainkan lanjut ke item berikutnya. Orang yang menontonnya
  sudah pergi membawa nomornya; yang berdiri berikutnya adalah orang baru.
- **`media/kiosk/layanan/` tidak ikut diputar sebagai sambutan** — putaran
  sambutan hanya membaca berkas, bukan folder.

**Kartu nomor sengaja dibuat sebesar itu.** Kegagalan mencetak tidak pernah
membatalkan antrian, sehingga saat printer kehabisan kertas layar inilah
satu-satunya catatan nomor yang dipegang pengunjung — cukup besar untuk
difoto dengan ponsel dari jarak berdiri. Arahannya ikut berubah menurut
keadaan cetak: `none` berarti "silakan tunggu", cetak berhasil berarti
"ambil tiket Anda", dan cetak gagal menyuruh pengunjung memfoto atau
mencatat nomornya. Kalimat yang sama dipakai kartu dan panel bawah, dan
baris sisa antrian memakai penyusun yang sama dengan struk tiket.

Kartu bertahan setidaknya sampai tombol A/B/C hidup lagi
(`kiosk.cooldown_seconds`), supaya tidak ada saat layar tampak siap dipakai
padahal tombolnya masih mati.

---

## Status Pengembangan

| Phase | Nama | Status |
|---|---|---|
| 0 | Environment Lock | ✅ Selesai |
| 1 | Foundation (config, database, models, seed, logging) | ✅ Selesai |
| 2 | Authentication | ✅ Selesai |
| 3 | Master Data (branch, counter, jenis layanan, user) | ✅ Selesai |
| 4 | Queue + Service Flow | ✅ Selesai |
| 5 | Ticket + Display + Sound | ✅ Selesai |
| 6 | Satisfaction Survey | ✅ Selesai |
| 7 | Dashboard Harian | ✅ Selesai |
| 8 | Backup + Audit + Hardening | ✅ Selesai |
| 9 | Packaging + Acceptance Test | ✅ Selesai |

---

## Login Pertama Kali

Saat database dibuat pertama kali, sistem membuat satu akun administrator:

| | |
|---|---|
| Nama pengguna | `admin` |
| Kata sandi | `admin123` |

**Kata sandi ini tidak rahasia dan wajib diganti.** Akun tersebut ditandai
`must_change_password`, sehingga seluruh kewenangannya ditolak sampai kata
sandinya diganti — admin bisa masuk, tetapi belum bisa mengerjakan apa pun.

Akun bawaan hanya dibuat bila database belum berisi user sama sekali.
Menghapusnya setelah membuat akun sendiri tidak akan memunculkannya lagi.

### Peran dan kewenangan

| Peran | Kewenangan |
|---|---|
| `ADMIN` | user, cabang, loket, jenis layanan, konfigurasi, backup, **menghapus lembar pengaduan** |
| `SUPERVISOR` | dashboard, laporan, hasil survey, membaca pengaduan (tanpa mengubah apa pun) |
| `REGISTRATION` | menerbitkan nomor antrian, mencetak tiket |
| `CRO` | memanggil, melayani, menunda, menyelesaikan, no-show, batal, menulis dan membaca pengaduan |
| `DISPLAY` | hanya layar antrian |
| `KIOSK` | papan nomor dan pengambilan nomor sendiri, **tanpa akun** |

`KIOSK` bukan akun yang dibuat administrator. Sesi itu dibuka tanpa login
pada komputer yang menghadap pengunjung. Menyimpan kata sandi petugas di
mesin publik justru menciptakan kebocoran yang tidak perlu.

Pembagian ini disengaja: tidak ada satu peran pun yang dapat melakukan
segalanya. `ADMIN` mengelola sistem tetapi tidak melayani antrian, dan
`SUPERVISOR` memantau tetapi tidak mengubah antrian.

Kata sandi disimpan sebagai hash scrypt bergaram acak. Kata sandi asli tidak
pernah disimpan, tidak pernah masuk log, dan tidak pernah masuk audit log.

---

## Setup Development

Prasyarat: Python 3.13 terpasang dan dapat dipanggil lewat `py -3.13`.

### 1. Buat virtual environment

```powershell
py -3.13 -m venv .venv
```

### 2. Install dependency

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` sudah memuat seluruh runtime dependency.
Untuk instalasi runtime saja, gunakan `requirements.txt`.

### 3. Siapkan database

```powershell
.\.venv\Scripts\python.exe -m app.main
```

Perintah ini menjalankan migration dan mengisi data master awal.
Aman diulang: migration dan seed sama-sama idempotent.

### 4. Verifikasi environment

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

Seluruh test harus PASSED sebelum melanjutkan pengembangan.

### 5. Jalankan aplikasi

```powershell
.\.venv\Scripts\python.exe -m app.main
```

Gunakan `--init-only` untuk menyiapkan database saja tanpa membuka jendela —
berguna saat memeriksa pemasangan di komputer baru. Hasilnya juga tercatat
di `logs/app.log`, karena `AntrianCRO.exe` berjendela dan tidak punya
terminal untuk menampilkannya.

Saat dibuka tanpa argumen, aplikasi langsung menampilkan **Login Petugas**.
Tombol **Atur komputer ini** pada layar yang sama mengatur komputer sebagai
server, klien, atau pemasangan satu komputer. Bila database tidak dapat
dihubungi, tombol **Ubah koneksi** tetap tersedia sebelum login.

`--tv` dan `--jendela` hanya dipertahankan sementara sebagai kompatibilitas
pintasan lama; keduanya tidak ditawarkan oleh antarmuka Windows baru.

Jeda antar-pengambilan nomor di anjungan diatur lewat
`kiosk.cooldown_seconds` (bawaan 10 detik). Jeda ini **hanya** berlaku pada
anjungan — meja pendaftaran melayani rombongan yang datang bersamaan dan
tidak ikut diperlambat — dan dihitung **per tablet**: nomor yang baru terbit
di satu tablet tidak menahan tablet lain. Lihat `docs/android-kiosk.md`
untuk idempotensi permintaan tiket.

---

## Menjalankan Test

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```

Selalu panggil interpreter `.venv` secara eksplisit. Menjalankan `pytest`
langsung berisiko memakai Python global yang versinya berbeda.

Perintah di atas menguji di atas **SQLite** karena jauh lebih cepat. Tetapi
SQLite bukan yang dipakai kantor dengan beberapa loket, sehingga sebelum
rilis seluruh test wajib dijalankan juga di PostgreSQL:

```powershell
.\test-postgres.ps1
```

Skrip itu menyalakan PostgreSQL di Docker, menjalankan seluruh suite
terhadapnya, lalu membiarkan container hidup agar pengulangan tidak perlu
menunggu. Hentikan dengan `docker compose down -v`.

Test yang tidak bermakna pada dialect yang sedang diuji akan **dilewati**,
bukan gagal — PRAGMA SQLite tidak ada padanannya di PostgreSQL, dan backup
PostgreSQL membutuhkan `pg_dump`. Perhatikan jumlah yang dilewati: test
backup yang terlewat berarti backup belum terbukti sama sekali.

---

## Pemasangan Beberapa Loket (PostgreSQL)

### Di komputer server

1. Pasang PostgreSQL 17:

```powershell
winget install --id PostgreSQL.PostgreSQL.17
```

2. Buat database dan penggunanya:

```sql
CREATE USER antrian WITH PASSWORD 'ganti-kata-sandi-ini';
CREATE DATABASE antrian OWNER antrian;
```

3. Izinkan komputer loket menyambung. Pada `postgresql.conf`:

```
listen_addresses = '*'
```

Pada `pg_hba.conf`, sesuaikan dengan rentang alamat jaringan kantor:

```
host    antrian    antrian    192.168.1.0/24    scram-sha-256
```

Jangan memakai `0.0.0.0/0`. Batasi persis pada jaringan kantor.

4. Buka port 5432 pada Windows Firewall, hanya untuk jaringan lokal.

### Di tiap komputer loket

Setel environment variable, lalu jalankan aplikasi seperti biasa:

```powershell
setx ANTRIAN_DB_URL "postgresql+psycopg://antrian:ganti-kata-sandi-ini@192.168.1.10:5432/antrian"
```

Migration dijalankan otomatis oleh aplikasi yang pertama kali dibuka.
Sisanya tinggal menyambung.

`ANTRIAN_DB_URL` **mengalahkan** `ANTRIAN_DB_PATH`. Komputer yang sudah
diarahkan ke server tidak akan diam-diam kembali memakai berkas SQLite lokal
hanya karena variabel lama tertinggal.

Bilah status di komputer loket menampilkan `PostgreSQL @ alamat-server`,
bukan path `queue.db`. Bila server mati, tulisannya berubah menjadi
**tidak terjangkau** — aplikasi **tidak** jatuh ke database lokal. Anjungan
dan televisi tidak menampilkan bilah ini.

### Setelan yang berbeda di tiap mesin

Pencetak tiket menempel pada satu komputer dan pengeras suara pada komputer
lain, sedangkan `ticket.printer` dan `display.sound_enabled` di layar
Pengaturan bernilai satu untuk seluruh sistem. Dua environment variable
menimpanya **hanya di mesin yang bersangkutan**:

| Variable | Nilai | Dipasang di |
|---|---|---|
| `ANTRIAN_PRINTER` | `pdf`, `system`, `none` | Mesin yang punya (atau tidak punya) pencetak tiket |
| `ANTRIAN_SUARA` | `1` / `0` | Mesin yang harus bersuara, atau harus diam |

```powershell
# Meja pendaftaran: mencetak tiket ke printer Windows
setx ANTRIAN_PRINTER "system"

# Komputer loket: tidak punya pencetak tiket dan tidak perlu bersuara
setx ANTRIAN_PRINTER "none"
```

Keduanya boleh dikosongkan. Mesin yang tidak menyebut apa-apa mengikuti
pengaturan bersama. Nilai yang salah ketik diperlakukan seperti tidak diisi, bukan
sebagai "tidak": satu huruf keliru tidak boleh mendiamkan panggilan tanpa
jejak.

### User PostgreSQL terbatas untuk layar antrian

Televisi ruang tunggu menghadap publik. Connection string-nya tetap ada di
mesin itu, jadi **jangan** memakai user `antrian` yang sama dengan petugas —
user itu dapat membaca tabel `app_user` (hash kata sandi seluruh petugas).

1. Buat user terpisah, lalu jalankan
   [layar-grant.sql](docs/sql/layar-grant.sql) sebagai superuser pada
   database `antrian`.
2. Di komputer televisi, arahkan ke user itu:

```powershell
setx ANTRIAN_DB_URL "postgresql+psycopg://antrian_layar:ganti-kata-sandi-layar@192.168.1.10:5432/antrian"
```

3. Tambah baris `pg_hba.conf`, tetap dibatasi jaringan kantor:

```
host    antrian    antrian_layar    192.168.1.0/24    scram-sha-256
```

Televisi **hanya membaca**. Anjungan Android tidak menyambung ke database
sama sekali; ia lewat API aplikasi server.

### Backup dijalankan di komputer server

Backup PostgreSQL memakai `pg_dump`, yang ikut terpasang bersama PostgreSQL.
Backup otomatis harian hanya dibuat di komputer **server**; komputer loket
melewatinya (tercatat di log) karena biasanya tidak punya `pg_dump`.

`pg_dump` dicari di PATH, lalu di `C:\Program Files\PostgreSQL\<versi>\bin`
(versi tertinggi). Pengaturan **Folder perkakas PostgreSQL** hanya perlu
diisi bila PostgreSQL dipasang di tempat lain.

Isi **Folder salinan kedua** (misalnya disk `D:` atau flashdisk) agar setiap
backup juga tersalin ke luar disk database. Masa simpannya sama; bila folder
itu tidak tersedia, backup utama tetap dibuat dan kegagalannya tercatat.

---

## Membangun `AntrianCRO.exe`

```powershell
.\build.ps1
```

Skrip ini menjalankan seluruh test terlebih dahulu dan menghentikan build
bila ada yang gagal, supaya `.exe` yang rusak tidak ikut terdistribusi.

Hasilnya berada di `dist\AntrianCRO\`. **Salin seluruh folder tersebut**,
bukan hanya berkas `.exe`-nya.

Dibangun sebagai satu folder (*onedir*), bukan satu berkas (*onefile*).
Mode *onefile* membongkar seluruh isi PySide6 ke folder temporary setiap
kali aplikasi dibuka — beberapa detik penundaan di depan loket yang sedang
melayani, setiap hari.

Saat dijalankan pertama kali di komputer baru, aplikasi membuat sendiri
folder `data`, `logs`, `backup`, beserta database dan akun administrator
bawaan. Tidak ada langkah pemasangan tambahan.

Lokasi penyimpanan dapat dipindahkan tanpa mengubah kode, lewat
environment variable `ANTRIAN_DB_PATH`, `ANTRIAN_BACKUP_DIR`, dan
`ANTRIAN_LOG_DIR`.

### Membuat installer Windows versi 1.0

Pasang Inno Setup 6, lalu dari PowerShell di folder proyek jalankan:

```powershell
.\build-installer.ps1
```

Skrip menjalankan seluruh test, membangun dan menguji aplikasi di folder
sementara, lalu menghasilkan `dist\AntrianCRO-Setup-1.0.2.exe`. Installer
dipasang untuk pengguna saat ini ke `%LOCALAPPDATA%\Programs\AntrianCRO`,
membuat pintasan Start Menu, dan menawarkan pintasan Desktop. Data aplikasi
tidak dihapus saat aplikasi di-uninstall.

Sebelum diserahkan ke pengguna, kerjakan daftar periksa pada
[docs/acceptance-test.md](docs/acceptance-test.md) di komputer tujuan.

## APK Anjungan Android

APK Android hanya menangani pemilihan layanan, penerbitan nomor lewat API
server Windows, dan pencetakan ke printer thermal USB. Server Windows tetap
harus menyala. Langkah pemasangan, token API, kebutuhan USB host/OTG, dan
cara membangun APK dijelaskan di [docs/android-kiosk.md](docs/android-kiosk.md).

---

## Memulihkan Database dari Backup

1. Masuk sebagai `ADMIN`, buka menu **Backup**.
2. Pilih berkas backup pada daftar, tekan **Pulihkan**.
3. Konfirmasi dua kali.
4. **Tutup dan buka kembali aplikasi.**

Seluruh antrian dan survey yang tercatat setelah tanggal backup akan
hilang. Database yang sedang berjalan otomatis disalin lebih dahulu sebagai
cadangan pengaman, sehingga salah pilih berkas masih dapat diperbaiki.

Berkas backup dapat disalin ke media lain untuk arsip: `.db` pada SQLite
adalah database yang dapat dibuka langsung, `.dump` pada PostgreSQL adalah
arsip `pg_dump` format custom. **Menaruhnya di komputer yang sama dengan
aslinya tidak melindungi apa pun bila komputer itu rusak.**

Pada PostgreSQL, pemulihan memakai `pg_restore --clean --single-transaction`
sehingga kegagalan di tengah jalan membatalkan seluruhnya — database tidak
pernah tertinggal separuh terpulihkan.

---

## Dependency

**Runtime** (`requirements.txt`)

| Paket | Kegunaan |
|---|---|
| PySide6 | UI desktop, cetak tiket (QtPrintSupport), suara panggilan (QtMultimedia) |
| SQLAlchemy | ORM dan akses database |
| psycopg | Driver PostgreSQL — wajib bila lebih dari satu loket |
| alembic | Migration skema — agar update aplikasi tidak menghapus data lama |
| pydantic | Validasi data internal |
| reportlab | PDF tiket dan laporan |
| tzdata | Database timezone IANA — **wajib**, Windows tidak menyediakannya |
| FastAPI + Uvicorn | API lokal yang menghubungkan APK anjungan ke server antrean |

**Development** (`requirements-dev.txt`)

| Paket | Kegunaan |
|---|---|
| pytest | Automated testing |
| pyinstaller | Packaging `AntrianCRO.exe` |

Seluruh versi di-pin exact (`==`) demi build yang reproducible.
Jangan menambah dependency tanpa kebutuhan nyata.

---

## Arsitektur

```
PySide6 UI  →  Service Layer  →  Repository Layer  →  SQLAlchemy  →  PostgreSQL / SQLite
```

Dialect dipilih saat aplikasi berjalan lewat `ANTRIAN_DB_URL`. Yang berbeda
di antara keduanya hanya tiga tempat, dan semuanya sudah dipagari:

| Berbeda | Di mana |
|---|---|
| PRAGMA, pool, penguncian | [app/core/database.py](app/core/database.py) |
| Selisih waktu di SQL | `QueueRepository._selisih_detik` — SQLite tidak punya tipe interval |
| Cara backup | [app/services/backup_engines.py](app/services/backup_engines.py) |

**Penomoran antrian tidak termasuk yang berbeda,** dan itu disengaja.
Keamanannya bersandar pada satu pernyataan `INSERT … ON CONFLICT DO UPDATE …
RETURNING` yang berlaku sama di kedua dialect — bukan pada perilaku kunci
milik salah satunya. Bentuk sebelumnya (UPDATE dahulu, INSERT bila tidak
ada barisnya) menyimpan celah yang tidak pernah terlihat di SQLite karena
`BEGIN IMMEDIATE` mengunci seluruh database, tetapi nyata di PostgreSQL.

Ada test yang mengunci **bentuk pernyataannya**, bukan sekadar hasilnya,
agar pemecahan kembali menjadi dua pernyataan tidak lolos diam-diam.

Relasi data:

```
Branch ─┬─ User
        ├─ Counter
        ├─ ServiceCategory
        └─ Queue ─┬─ QueueCall
                  └─ SatisfactionSurvey
```

Aturan yang ditegakkan:

- UI **tidak boleh** mengakses database secara langsung.
- Seluruh business rule dan authorization berada di **service layer**.
- Nomor antrian tidak boleh duplikat dalam satu hari — dijamin oleh
  transaction SQLite dan constraint `UNIQUE(branch_id, queue_date, queue_number)`.
- Setiap pemanggilan dicatat di `QueueCall` dan tidak pernah ditimpa.

Database aplikasi berada di `data/queue.db` dan tidak di-commit ke git.

Struktur layer:

```
app/
  core/          config, database, migration, clock, security, logging, seed
  models/        tabel SQLAlchemy
  repositories/  query database
  services/      aturan bisnis dan hak akses
  ui/            layar PySide6
  utils/         format tampilan berbahasa Indonesia
```

**Pengaturan** diubah `ADMIN` lewat menu **Pengaturan**. Layarnya membagi
pengaturan menurut kelompok di kolom kiri, dengan kotak cari di atasnya
(Ctrl+F) dan bilah Simpan di bawah yang hanya menyala bila ada yang
berubah. Baris yang belum disimpan ditandai; Batalkan Perubahan meminta
konfirmasi dulu.

| Kunci | Bawaan | Kegunaan |
|---|---|---|
| `ticket.printer` | `pdf` | Cara mencetak tiket: `pdf`, `system`, `none` |
| `ticket.header` | `BAPENDA DKI JAKARTA` | Judul di baris paling atas tiket; boleh dikosongkan |
| `ticket.footer` | — | Teks penutup pada tiket |
| `display.title` | — | Judul pada layar antrian |
| `display.next_count` | `3` | Jumlah nomor berikutnya yang ditampilkan |
| `display.sound_enabled` | `true` | Suara saat nomor dipanggil |
| `queue.max_call_attempts` | `3` | Batas pemanggilan sebelum dianggap tidak hadir |
| `kiosk.cooldown_seconds` | `10` | Jeda antar-pengambilan nomor di mesin kios (detik) |
| `survey.enabled` | `true` | Aktifkan survey kepuasan |
| `dashboard.refresh_seconds` | `30` | Jeda penyegaran ringkasan harian |
| `backup.auto_enabled` | `true` | Backup otomatis harian saat aplikasi dibuka |
| `backup.retention_days` | `30` | Lama backup disimpan sebelum dihapus |
| `backup.pg_dump_path` | — | Folder perkakas PostgreSQL bila tidak ada di PATH |
| `backup.salinan_folder` | — | Folder salinan kedua backup (disk lain/flashdisk) |

Jenis dan batas tiap pengaturan dijelaskan sekali saja pada `SKEMA` di
[app/services/settings_service.py](app/services/settings_service.py). Layar
memakainya untuk memilih kontrol yang tepat — kotak centang, daftar pilihan,
atau kotak angka berbatas — dan `set()` memakainya untuk menolak nilai yang
tidak masuk akal. UI dapat dilewati, service tidak, sehingga keduanya wajib
bersandar pada keterangan yang sama.

**Audit log** mencatat setiap tindakan yang mengubah data, beserta pelaku
dan waktunya, dan dapat dibaca `ADMIN` lewat menu **Backup**.
Kata sandi, hash kata sandi, dan token tidak pernah masuk audit log —
disaring sebelum disimpan, bukan sekadar tidak dikirim.
