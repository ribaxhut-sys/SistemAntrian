# Serah Terima untuk AI (Codex dan Claude)

Proyek ini dikerjakan bergantian oleh dua asisten AI, **Codex** dan
**Claude**, di bawah arahan satu pemilik. Dokumen ini adalah **satu sumber
kebenaran** tentang keadaan sekarang, aturan kerja, dan apa yang belum
selesai. Baca sebelum mengubah apa pun, dan **perbarui** di akhir setiap
sesi (bagian 3, 6, dan 9 paling sering berubah).

`AGENTS.md` (dibaca Codex) dan `CLAUDE.md` (dibaca Claude) di akar repo
hanya ringkasan aturan dan menunjuk ke sini. Jangan menyalin isi dokumen ini
ke sana; cukup perbarui di satu tempat.

Dokumen lain yang tetap berlaku: [lanjutan.md](lanjutan.md) (aturan kode dan
jebakan; bagian riwayat commit-nya sudah lama), [istilah.md](istilah.md),
[panduan-proyek.md](panduan-proyek.md), [android-kiosk.md](android-kiosk.md),
[layar-antrian.md](layar-antrian.md), [prioritas-antrian.md](prioritas-antrian.md),
[keamanan-sesi.md](keamanan-sesi.md).

Terakhir diperbarui: **20 Oktober 2026**, oleh Claude.

**Peningkatan layar antrian (20 Oktober 2026, Claude, cabang `fitur/identitas-bapenda`):**
penyegaran berkala `DisplayPage` kini lewat `muat_ulang_latar` (`PekerjaLatar`,
tidak menumpuk, kegagalan hanya dicatat tanpa dialog); `muat_ulang()` sinkron
tetap dipakai saat dibuat dan oleh tes. `test_display.py`: 168 lulus, lint
bersih. Pemeriksaan dugaan lain: `time.sleep(0.5)` di `layanan_anjungan_page.py`
**aman** (berjalan di pekerja latar `_jalankan`); peringatan tanda tangan
pembaruan, backup otomatis dengan salinan kedua, prosedur cadangan kunci
(`keamanan-sesi.md`), dan batas hadir 90 detik **sudah ada**, jadi tidak diubah.
Peringatan Starlette (`httpx` di `TestClient`) berasal dari dependensi; perbaikannya
`httpx2`, belum dilakukan karena mengubah dependensi. **Masih butuh pemilik/perangkat:**
bangun ulang + tanda tangan installer 1.2 (`build-installer.ps1`, lalu
`publikasikan-pembaruan.ps1` dengan kunci pemilik), uji PC bersih, uji APK 2.5.1
dan Maxtor, DPI 125/150%, uji lima loket. **Belum dikerjakan (besar, perlu
perangkat atau keputusan):** pemecahan `MainActivity.java`, ganti monkeypatch
tema, fitur baru (filter audit, laporan terjadwal, kesehatan tablet).

**Installer 1.2 dibangun (20 Oktober 2026, Claude):** `.\build-installer.ps1` tanpa `-SkipTests`, kode keluar 0; pytest 2054 lulus, 8 dilewati, 0 gagal (31 mnt 13 dtk). `dist\AntrianCRO-Setup-1.2.exe` 67.526.579 byte, sha256 `7d4f7bba3ea58d4caf4dda8858cfcdfb55a1cb46ebb56283798d597e4eb3cc87`; `dist\Pembaruan-AntrianCRO.exe` sha256 `7d4f7bba3ea58d4caf4dda8858cfcdfb55a1cb46ebb56283798d597e4eb3cc87`. **Ditandatangani pemilik 20 Okt 20:13** (`publikasikan-pembaruan.ps1`); `.sig` terverifikasi sah terhadap kunci publik tertanam untuk `dist` dan `dist\siap-publikasi\1.2` (sha256 `7d4f7bba...cc87`). **Belum disalin ke folder `pembaruan` server** dan **belum dipasang** di PC mana pun. Penomoran MainActivity: tahap 9 (`BantuGambar`) dan 10 (`BantuTeks`), kini 6499 baris. ADB BlueStacks: instal/push gagal `error: closed`; APK debug 2.5.1 harus diseret manual ke jendela BlueStacks (terpasang masih 2.5).

**Rilis APK 2.5.3 / layar 1.7 dan installer 1.2 final (20 Oktober 2026, 20:49, Claude):** judul Android 'Bapenda DKI Jakarta' kini dirilis. `apk\` berisi anjungan **2.5.3 (kode 57)** dan layar antrian **1.7 (kode 8)** (layar ikut dinaikkan karena judulnya berubah; tanpa itu tablet layar tidak memperbarui diri); `apk\` lama (2.5.2 dan 1.6) ada di `backup\apk-sebelum-2.5.3`. Terverifikasi `aapt2` dan isi dex: versi benar, judul lama hilang, anjungan masih memuat `/v1/kiosk/baterai`. Belum dipasang di perangkat. Kalimat 'apk\ masih 2.5.2 dengan judul lama, versi tidak dinaikkan' pada catatan di bawah sudah usang. Installer: `.\build-installer.ps1 -SkipTests`, kode keluar 0, log memuat 'APK anjungan ikut dalam installer'; `dist\AntrianCRO-Setup-1.2.exe` = `dist\Pembaruan-AntrianCRO.exe`, 67.513.096 byte, sha256 `fdf281677d42ad0a21cec10bd92f37dffc71f38010a3c64918a046bd7370a6dd` (menggantikan sha256 `9c8c8db3...` dan `8a5206a3...` di catatan bawah). **`.sig` di `dist` tidak sah untuk berkas ini; belum ditandatangani ulang.** Tanda tangan hanya perlu untuk pembaruan lewat server; pemasangan manual dari `AntrianCRO-Setup-1.2.exe` tidak memerlukannya.

**Judul Android diganti (20 Oktober 2026, Claude):** atas permintaan pemilik, judul di layar anjungan dan layar antrian Android kini hanya **"Bapenda DKI Jakarta"** (`NAMA_TAMPIL` di `MainActivity` kedua modul; sama dengan `identitas.INSTANSI`). Windows, tiket, laporan, dan label ikon peluncur (`android:label`) tidak berubah. Tes `tests/test_identitas.py::test_android_memakai_nama_instansi_saja`. Kedua modul terkompilasi (debug); **belum dirilis**: `apk\` masih 2.5.2 dengan judul lama, dan versi tidak dinaikkan. Tablet baru menampilkan judul ini setelah APK berikutnya (2.5.3 atas permintaan pemilik) dibagikan.

**APK anjungan 2.5.2 (kode 56) dirilis ke `apk\` dan installer 1.2 dibangun ulang (20 Oktober 2026, 20:39, Claude):** atas permintaan pemilik, versi dinaikkan 2.5.1 -> 2.5.2 (`android-kiosk/app/build.gradle`) agar tablet berkode 55 menerima kode terbaru (laporan baterai + tahap 8-10 `MainActivity`). `apk\` lama dicadangkan ke `backup\apk-sebelum-2.5.2` (anjungan 2.5.1 build 13:02 dan layar 1.6). `build-android-kiosk.ps1` sukses; `apk\anjungan.apk` (141.969 byte) terverifikasi `aapt2`: versionCode 56 / 2.5.2, memuat `/v1/kiosk/baterai` dan judul Bapenda; layar tetap 1.6 (kode 7, dibangun ulang tanpa perubahan kode sehingga tablet layar tidak memperbarui diri). Server membagikannya, jadi tablet tersambung kini ditawari pembaruan ke 2.5.2. APK rilis ini belum dipasang di perangkat (yang diuji di BlueStacks adalah build debug 2.5.1 dengan kode yang sama). Installer: `.\build-installer.ps1 -SkipTests`, kode keluar 0, log memuat 'APK anjungan ikut dalam installer'; `dist\AntrianCRO-Setup-1.2.exe` = `dist\Pembaruan-AntrianCRO.exe`, 67.525.468 byte, sha256 `9c8c8db324380f972151a657e30ccdbc70130d2058178b494e28b649e533024a` (menggantikan sha256 `8a5206a3...` di catatan bawah). **`.sig` di `dist` tidak sah untuk berkas ini; BELUM ditandatangani ulang** (`publikasikan-pembaruan.ps1`, kata sandi diketik pemilik).

**Installer 1.2 dibangun ulang tanpa pytest (20 Oktober 2026, 20:30, Claude):** `.\build-installer.ps1 -SkipTests`, kode keluar 0 (uji bundel di folder bersih tetap jalan; hanya pytest dilewati, karena suite penuh 2054 lulus pada kode yang hampir sama dan tes terarah penjaga migrasi lulus). Memuat perbaikan `AplikasiLebihLamaError`. `dist\AntrianCRO-Setup-1.2.exe` = `dist\Pembaruan-AntrianCRO.exe`, 67.525.378 byte, sha256 `8a5206a319ae78ce865d2c6212122e33ad578a976be04659d4088d3cef6b82a2`. **`.sig` lama tidak sah untuk berkas ini; BELUM ditandatangani ulang** (jalankan `publikasikan-pembaruan.ps1`, kata sandi kunci diketik pemilik; folder `dist\siap-publikasi\1.2` yang ada masih berisi build lama dan akan tertimpa). Build lama yang sudah ditandatangani: `dist\AntrianCRO-Setup-1.2.sebelum-perbaikan.exe.bak`. **Skenario pemasangan ulang diuji nyata** pada database sementara `antrian_skenario` (dibuat lalu dihapus; skrip: aplikasi `--init-only` sungguhan): (1) DB kosong -> revisi terbaru; (2) DB lama pada `f6d2a8c41b07` dan `e9c3b5a7d281` berisi data -> naik ke `a7e3c9d5b214` tanpa baris berkurang; (3) DB sudah terbaru, dibuka berulang -> tanpa perubahan; (4) DB lebih baru dari aplikasi -> keluar kode 1, pesan 'perbarui aplikasi', data dan revisi utuh. `mesin.json` lama berperan `sendiri`, rusak, atau tak dikenal sudah diuji di `tests/test_mesin.py` (diperlakukan belum ditetapkan, muncul dialog koneksi). Belum dibuktikan: menjalankan installer itu sendiri di PC bersih/PC berisi 1.0.x (tidak ada Sandbox, dan komputer ini punya pemasangan nyata 1.0.2).

**Pemeriksaan pemasangan 1.2 di PC lain (20 Oktober 2026, Claude):** Windows Sandbox tidak tersedia dan komputer ini sudah punya pemasangan nyata 1.0.2 (AppId sama, `%LOCALAPPDATA%\Programs\AntrianCRO`), jadi installer 1.2 sengaja TIDAK dijalankan di sini; uji pemasangan di PC bersih tetap harus dilakukan manusia. Terbukti dari kode dan build: installer hanya menimpa berkas program + `_internal` (`data`, `backup`, `logs` tidak disentuh), menolak menurunkan versi, uji bundel di folder bersih lulus. **Temuan:** aplikasi LEBIH LAMA daripada database gagal start (1.0.2 terhadap revisi `a7e3c9d5b214`: `Can't locate revision`, pesan menyesatkan 'tidak dapat menghubungi database'); database kerja `antrian` sudah di revisi itu, jadi PC berversi lama harus dipasang 1.2 dulu. **Perbaikan di kode (belum ada di installer 1.2 yang sudah ditandatangani):** `AplikasiLebihLamaError` di `app/core/migrations.py` (penjaga `_revisi_dikenal`) dan `_laporkan_aplikasi_lebih_lama` di `app/main.py` (pesan 'perbarui aplikasi', keluar kode 1, tanpa tombol ubah koneksi); tes di `tests/test_migration.py` dan `tests/test_ui.py`, dan alur `--init-only` nyata diuji terhadap `antrian_uji` dengan revisi dipalsukan lalu dipulihkan. Agar PC 1.2 kelak mendapat pesan ini bila databasenya naik ke versi lebih baru, **bangun ulang dan tanda tangani ulang 1.2 sebelum dibagikan** (belum dibagikan ke PC mana pun). **APK:** `apk\anjungan.apk` (2.5.1, kode 55) adalah build rilis jam 13:02 dari sesi lain (backup `backup\apk-sebelum-2.5.1`), SEBELUM laporan baterai dan tahap 8-10 `MainActivity`; installer 1.2 membawanya. Tablet berkode 55 tidak akan memperbarui diri ke build debug yang saya uji; membagikan kode terbaru butuh versi dinaikkan (2.5.2) atas permintaan pemilik.

**Server kerja dimigrasi dan diuji di BlueStacks (20 Oktober 2026, Claude):** dump `backup/antrian-20261020-201700-sebelum-migrasi-baterai.dump` (+ `.sha256`), lalu `antrian` naik `f1b4c8d2a6e9` -> `a7e3c9d5b214` (jumlah baris tetap: queue 95, app_user 3, audit_log 473, kiosk_device 2, service_category 12). Tugas terjadwal `AntrianCRO API Anjungan` dimulai ulang tanpa elevasi (Running, `/health` 200), jadi kode baru (termasuk `/v1/kiosk/baterai`) aktif. APK debug 2.5.1 (kode 55) diseret pemilik ke BlueStacks (ADB `install`/`push` gagal `error: closed`); terverifikasi: judul Bapenda, 'Terhubung ke server', tanpa crash, dan baterai 100% tidak diisi tercatat di `kiosk_device` lalu tampil di Kesehatan Sistem ('baterai 100%'; peringatan yang muncul berasal dari printer, emulator tidak punya). Migrasi berjalan otomatis di setiap start aplikasi (`siapkan_database`), termasuk `--kios-api` dan `--init-only`; PC dengan aplikasi LEBIH LAMA dari database dapat gagal inisialisasi (revisi tak dikenal), jadi perbarui semua loket ke 1.2 setelah server naik. Belum diuji: papan PIN, panggilan menghentikan iklan, Maxtor asli.

**Peningkatan lanjutan (20 Oktober 2026, Claude, cabang `fitur/identitas-bapenda`, belum di-push):**
backup lebih dulu: `backup/antrian-20261020-184421-sebelum-peningkatan.dump` (+ `.sha256`,
196 entri terbaca `pg_restore -l`) dan `backup/repo-20261020-184421.bundle`. Lalu:
(1) `httpx2==2.15.1` menggantikan `httpx` di `requirements-dev.txt` (peringatan Starlette hilang);
(2) **Jejak Aktivitas** (menu Backup) punya filter tindakan, pelaku ("sistem" = tanpa
pengguna), dan rentang tanggal: `audit_service.list_terakhir(aksi, pelaku, sejak, sampai)`,
`daftar_aksi()`, `tests/test_filter_audit.py`; (3) **laporan mingguan otomatis**
(`app/services/laporan_terjadwal.py`, pengaturan `laporan.mingguan_aktif` (bawaan **mati**)
dan `laporan.mingguan_folder`): karena laporan menuntut `REPORT_VIEW`, PDF minggu lalu
(Senin-Minggu) dibuat 20 dtk setelah admin/supervisor membuka aplikasi bila berkasnya
belum ada (berkas = penanda), tercatat `EXPORT_REPORT`; `tests/test_laporan_terjadwal.py`;
(4) **baterai tablet**: migrasi **`a7e3c9d5b214`** (head baru; 3 kolom nullable di
`kiosk_device`), `POST /v1/kiosk/baterai`, anjungan Android melapor tiap 5 menit/saat
berubah ≥5 poin (`laporkanBaterai`), Kesehatan Sistem: <=20% tanpa charger PERINGATAN,
<=10% MASALAH, laporan >30 menit diabaikan; **database kerja `antrian` belum di-migrasi**
(berjalan otomatis saat aplikasi dibuka; backup sudah ada), APK hanya dikompilasi
(versi tidak dinaikkan, `apk/` tidak disentuh); (5) `MainActivity` tahap 8:
`BantuWarna`, `Loket`, `Category` berkas sendiri (6564 baris). **Sengaja tidak
dikerjakan:** penggantian monkeypatch tema (ratusan titik gaya, tanpa uji visual
risikonya lebih besar dari manfaatnya; ketergantungan urutan tes sudah dijaga fixture
`tema_dan_gaya_pulih`) dan pemecahan `MainActivity` per layar (butuh uji perangkat tiap
tahap). Suite penuh setelah semua perubahan ini: **2054 lulus, 8 dilewati, 0 gagal** (30 mnt 42 dtk), lint bersih. Yang tetap menunggu manusia: bangun ulang + tanda tangan installer 1.2, uji PC
bersih, uji APK 2.5.1/Maxtor/baterai di perangkat, DPI 125/150%, uji lima loket.

**Peningkatan layar antrian (20 Oktober 2026, Claude, cabang `fitur/identitas-bapenda`):**
keputusan pemilik: tampil **"Sistem Antrian CRO - Bapenda DKI Jakarta"**, tidak
dapat diubah admin; nama produk teknis (`APP_NAME`, jalur data, tugas
terjadwal) tetap `Sistem Antrian CRO` supaya pembaruan PC lama tidak putus.
Konstanta ada di `app/core/identitas.py` (`NAMA_TAMPIL`, `JUDUL_TIKET`). Dipakai
di judul jendela, layar masuk, dialog, kepala aplikasi, layar antrian, tiket,
kop laporan, `/v1/kiosk/display` dan `/v1/display` (`title` selalu identitas),
publisher installer. Pengaturan `ticket.header`, `display.title`, `kiosk.judul`
**dihapus** dari skema, bawaan, dan seed (baris lama di database diabaikan).
Android: judul anjungan dan layar terkunci di kode (`NAMA_TAMPIL`), kolom
"Judul tablet ini" dihapus, `android:label` memuat "Bapenda DKI Jakarta"; kedua
modul terkompilasi, **belum diuji di perangkat**. Tes penjaga:
`tests/test_identitas.py`. **Versi dinaikkan atas permintaan pemilik:**
Windows `1.2` (`app/__init__.py`, `installer.iss`, `build-installer.ps1`,
README), APK anjungan `2.5.1` (kode 55); APK layar tetap 1.6 (kode 7). Suite
penuh: 2023 lulus, 7 gagal karena tes memakai pengaturan judul lama; tujuh tes
itu diperbarui dan modul terkait lulus (166). **Installer 1.2 dan APK 2.5.1
belum dibangun**; `dist\AntrianCRO-Setup-1.0.11.exe` dan tanda tangannya
(`.sig`) milik 1.0.11, jadi rilis 1.2 harus dibangun ulang dan ditandatangani
ulang (`publikasikan-pembaruan.ps1`). Catatan perubahan lain hari ini: PR #4
(audit produksi), build bertes 1.0.11 lulus, skrip `publikasikan-pembaruan.ps1`
menyiapkan folder siap salin untuk server.

**Audit 20 Oktober 2026 (Codex):** lint `ruff check app tests alembic alat`
bersih. Tes terarah untuk keluar/ambil alih, Pelayanan Aktif, pembaruan
Windows, catatan wajib, dan laporan: **117 lulus, 1 peringatan deprecation
Starlette, 0 gagal** (162 detik). Status tetap **Siap staging/UAT**, belum
siap produksi: build installer tanpa `-SkipTests`, uji PC bersih, tanda tangan
installer, serta uji perangkat Android masih belum terbukti. Workspace masih
memiliki salinan installer lama yang sengaja belum terlacak di
`backup/installer-1.0.11-sebelum-audit/`; jangan dihapus tanpa persetujuan.

**Build bertes 20 Oktober 2026 (Claude):** `.\build-installer.ps1` tanpa `-SkipTests` selesai dengan kode keluar 0 (menyelesaikan sisa risiko "build tanpa `-SkipTests`" di atas). Pytest: **2030 lulus, 8 dilewati, 0 gagal** (37 mnt 24 dtk), lalu PyInstaller dan Inno Setup berhasil; perbaikan `tests/conftest.py` (menunggu `_UTAS_TERTINGGAL`) terbukti. `dist\AntrianCRO-Setup-1.0.11.exe` (67.126.060 byte, dibangun 20 Okt 10:56, sha256 `05454E84744629ACAD6DFFA2374EB43D408B78BE762CE1EC1F276A8FD4F0344D`) kini installer **bertes**, tetapi **belum ditandatangani** dan **belum dipasang** di PC mana pun. `dist\Pembaruan-AntrianCRO.exe` belum ditandatangani (butuh kunci Ed25519 pemilik). Backup sebelum build: `backup/*-20261020-101139*` (dump `antrian`, salinan `data/` dan `apk/`, bundle repo 69 MB).

**Server kerja diperiksa 20 Oktober 2026 (Claude):** database `antrian` **sudah di head `f1b4c8d2a6e9`** (catatan bagian 3 yang menyebut `d6a1f3b8c704` dan migrasi tertunda sudah usang). API anjungan berjalan sebagai tugas terjadwal `AntrianCRO API Anjungan` (`python -m app.main --kios-api`, port 8765), terakhir mulai 20 Okt 11:17, lebih baru dari berkas kode terakhir (19 Okt 19:20), jadi sudah memakai kode terbaru; tidak perlu restart. Yang masih menunggu manusia: tanda tangan `Pembaruan-AntrianCRO.exe`, uji installer di PC bersih, uji APK/Maxtor di perangkat, DPI 125/150%, dan uji lima loket.

**Dugaan bottleneck (belum diukur, lalu diukur: tidak terbukti di jaringan lokal, median `display_state` 11–12 ms dengan 8–9 SQL):** `DisplayPage.muat_ulang` (`app/ui/display/display_page.py`) memanggil `queue.display_state` di utas UI tiap 2 detik; bila PostgreSQL lambat atau putus, layar antrian Windows membeku. Halaman Pelayanan sudah memuat di latar belakang (`_mulai_muat_latar`) dan bisa jadi contoh. `time.sleep(0.5)` di `layanan_anjungan_page.py` (baris ~604 dan ~621) belum diperiksa konteks utasnya. Ukur durasi `display_state` pada data nyata sebelum mengubah.

**Aturan keluar petugas 19 Oktober 2026:** nomor berstatus `CALLED` yang
ditinggalkan petugas dikembalikan ke `WAITING`. Nomor `SERVING` atau `PAUSED`
tetap aktif agar petugas lain dapat mengambil alih tanpa menghilangkan waktu
mulai pelayanan.

**Pembaruan audit 19 Oktober 2026:** worker ekspor laporan kini dihentikan
secara aman saat halaman ditutup; timer jeda penerbitan dan penyegaran
dashboard dimiliki widget dan dihentikan saat teardown; catatan rilis Windows
ikut dilindungi tanda tangan Ed25519. Tes terarah terkait lulus 132 kasus dan
lint bersih. Kompilasi debug kedua modul Android juga berhasil.

**Audit kesiapan produksi 19 Oktober 2026 (Claude):** status **Siap staging/UAT**, belum siap produksi.

Temuan dan perbaikan (semuanya di service/UI, dengan tes regresi di `tests/test_logout_ambil_alih.py`, `tests/test_queue_service.py`, `tests/test_ui.py`):

1. **KRITIS, diperbaiki:** admin, supervisor, dan pendaftaran **tidak dapat keluar dari aplikasi**. `siapkan_logout_petugas` mewajibkan `QUEUE_CALL` (hanya CRO), sehingga peran lain mendapat dialog "Belum dapat keluar" dan `closeEvent` membatalkan penutupan. Kini peran tanpa `QUEUE_CALL` langsung mendapat daftar kosong. Dialog itu juga membuat tes UI lama (tutup `MainWindow` sebagai admin) menggantung tanpa batas.
2. **TINGGI, diperbaiki:** commit `161b627` dan `c821f8f` mengubah hak daftar dan menu **Pelayanan Aktif** menjadi `QUEUE_CALL`, sehingga **admin kehilangan halamannya** (Alihkan, Batalkan Paksa, Selesaikan Paksa). `list_pelayanan_aktif` kini menerima `QUEUE_CALL` atau `QUEUE_REASSIGN`; menu memakai `_Menu.atau`; tombol di halaman mengikuti peran (CRO hanya Ambil Alih, admin hanya tiga tombol admin).
3. **SEDANG, diperbaiki:** `ambil_alih_pelayanan` tidak memeriksa pemilik lama, jadi CRO mana pun dapat merebut nomor rekan yang masih hadir dan melayani. Kini ditolak bila pemilik masih memberi tanda hadir loket (`petugas_terlihat_pada` ≥ `BATAS_HADIR_PETUGAS_DETIK`); pemilik yang keluar atau komputernya mati (tanda basi) dapat diambil alih. Admin tetap memakai `alihkan_pelayanan`.
4. Fitur keluar/ambil alih sebelumnya **tanpa satu pun tes**; kini 24 tes: CALLED kembali ke WAITING dengan audit `RETURN_QUEUE_TO_WAITING`; SERVING/PAUSED tetap dan `serving_at` utuh; ambil alih tanpa `QUEUE_REASSIGN`; ditolak untuk CALLED/WAITING/selesai, untuk peran tanpa hak, untuk cabang lain, dan bila petugas masih memegang nomor lain; dua petugas berebut satu nomor (thread) tidak pernah menghasilkan dua pemilik.
5. Dua tes lama (`test_queue_service`, `test_ui`) usang terhadap rancangan ambil alih dan diperbarui.

Pemeriksaan: `ruff check app tests alembic alat` bersih. Suite penuh (satu proses, `antrian_uji`, pada commit `b2d5ae4`): **2030 lulus, 8 dilewati, 0 gagal** (25 mnt 44 dtk). Ronde sebelumnya (sebelum perbaikan menu dan tombol Pelayanan Aktif) 2028 lulus dan 2 gagal di `test_ui.py`; keduanya sudah diperbaiki. Migrasi diuji pada salinan dump `backup/antrian-20261019-073311.dump` (checksum cocok, `pg_restore` ke DB sementara, `e9c3b5a7d281` naik ke `f1b4c8d2a6e9`, jumlah baris queue/app_user/audit_log tetap 90/3/397; DB sementara dihapus, `antrian` tidak disentuh). Pairing anjungan: pembatas tebakan per IP dan global sudah ada.

Installer: `dist\AntrianCRO-Setup-1.0.11.exe` dibangun ulang 19 Okt 20:45 dengan `-SkipTests` (sha256 `05ae6e2c...ac7de`, 67.123.826 byte; belum ditandatangani, belum dipasang) agar memuat perbaikan audit; versi tetap 1.0.11. Salinan lama di `backup/installer-1.0.11-sebelum-audit/`. Build bertes pertama membuat pytest keluar non-nol walau 2030 lulus (utas `_PemeriksaAnjungan` yang dilepas `_lepas_utas_berjalan` masih hidup saat proses keluar, lalu `Logging error: I/O operation on closed file`); `tests/conftest.py` kini menunggu `_UTAS_TERTINGGAL` di akhir sesi dan `build-installer.ps1` mencetak kode keluar pytest. **Belum terbukti** memperbaikinya: build bertes belum diulang sampai selesai; jalankan `.\build-installer.ps1` tanpa `-SkipTests` sebelum rilis resmi.

Sisa risiko: (a) APK dan panel Maxtor belum diuji di perangkat; (b) installer 1.0.11 belum diuji di PC bersih dan belum ditandatangani; (c) API server dan database kerja belum memakai kode/migrasi baru; (d) tes backup/restore memakai alat PostgreSQL di PATH, bila tidak ada tes dilewati; (e) DPI Windows 125/150% belum diuji nyata; (f) pemilik yang komputernya mati baru dapat diambil alih setelah tanda hadir basi (`BATAS_HADIR_PETUGAS_DETIK`); sebelum itu hanya admin yang dapat mengalihkan.

---

## 1. Aturan kerja bersama

**Bahasa.** Semua jawaban kepada pemilik dalam **Bahasa Indonesia**. Nama
fungsi, variabel, docstring, komentar, dan pesan commit juga Indonesia.
Docstring menjelaskan **mengapa**, bukan mengulang kodenya.

**Aturan kode** ada di [lanjutan.md](lanjutan.md) bagian 2 (lapisan UI →
service → repository, DTO `@dataclass(frozen=True)`, jebakan Qt, dan
seterusnya). Tambahan yang berlaku sekarang:

- Otorisasi ditegakkan di **service layer**, bukan hanya disembunyikan di UI
  (contoh: `create_queue` menolak prioritas dari peran selain yang berhak).
- Perubahan skema selalu lewat migrasi Alembic yang **menambah** kolom
  nullable; data lama tidak boleh berubah.

**Pengujian.**

- Pakai interpreter proyek: `.\.venv\Scripts\python.exe -m pytest ...`.
  `python` biasa menunjuk Python sistem tanpa PySide6.
- **Semua tes di PostgreSQL** database uji `antrian_uji` (URL ada di
  `~/.antrian-uji-db`). Jangan pernah menguji di database kerja `antrian`
  (fixture menjalankan `DROP SCHEMA`). Tanpa SQLite.
- **Satu proses pytest pada satu waktu** terhadap `antrian_uji`. Dua proses
  bersamaan saling merusak.
- Selama iterasi jalankan **tes terarah** (modul yang diubah dan
  tetangganya) dan `ruff check app tests alembic`. **Suite penuh** (±10–12
  menit, 1767 lulus) hanya **sekali sebelum push atau PR**; CI GitHub
  menjalankannya lagi.
- `build-installer.ps1` menjalankan tesnya sendiri, jadi lebih lama.

**Git.**

- **Jangan push** kecuali pemilik memintanya. Commit lokal boleh bila
  diminta.
- Periksa `git status` tepat sebelum commit; berkas bersama bisa tersapu
  sesi lain. Commit hanya berkas milik pekerjaan itu.
- Setiap PR diberi **Auto-fix** (`set_monitor auto_fix=true`) tanpa bertanya.
- Pesan commit Indonesia, diakhiri baris `Co-Authored-By:` asisten yang
  mengerjakan.

**Versi.**

- **Aplikasi Windows**: `app/__init__.py`, `build-installer.ps1`,
  `installer.iss`, README. Naik hanya saat pemilik meminta installer baru.
- **APK anjungan**: `android-kiosk/app/build.gradle`. **Jangan menaikkan
  versi per perubahan**; kumpulkan perubahan Android sampai pemilik meminta
  rilis. Naikkan angka **terakhir** (2.4.33 → 2.4.34), tidak melompat ke
  minor. Versi yang benar-benar dibagikan ada di `apk/anjungan.json`.

**Jangan mengubah pengaturan keamanan perangkat pemilik** (mis. mengaktifkan
ADB BlueStacks). Minta pemilik melakukannya.

**Sebelum migrasi ke database kerja** (`antrian`): backup dulu
(`pg_dump -Fc` ke folder `backup/`), jalankan migrasi, verifikasi jumlah
baris. Jangan menaruh APK baru di `apk/` tanpa persetujuan: komputer
pengembang ini juga berperan sebagai server, dan tablet yang tersambung
memperbarui diri dari folder itu. Selalu salin isi lama ke
`backup/apk-sebelum-<versi>/` dulu.

**Memeriksa permintaan terhadap aplikasi.** Cocokkan tiap permintaan dengan
kode, dokumen, dan tes sebelum mengerjakan; bila tidak cocok dengan keadaan
aplikasi, laporkan ketidakcocokannya (pernah terjadi: "petugas pendaftaran"
ternyata tidak ada di lapangan).

---

## 2. Gambaran sistem (ringkas)

Empat bagian, rinci di [istilah.md](istilah.md):

| Bagian | Perangkat | Kode |
|---|---|---|
| Anjungan | Tablet Android + printer thermal | `android-kiosk/app` |
| Layar antrian | Panel Android Maxtor | `android-kiosk/layar` |
| Aplikasi server | PC Windows peran server: PostgreSQL + API (port 8765) | `app/kiosk_api.py` |
| Aplikasi petugas | PC Windows tiap loket | `app/` (PySide6) |

Di lapangan **tidak ada petugas pendaftaran**: pengunjung mengambil nomor
sendiri di anjungan, dan yang ada hanya petugas yang melayani (CRO) dan
petugas yang berjaga tanpa perangkat. Panel layar antrian: **Maxtor
MDDW-55DS** (55 inci; resolusi belum terverifikasi). Ukuran fisik panel
anjungan/layar yang disebut pemilik ±120 × 27 cm (rasio ±4,4 : 1, panel
memanjang).

---

## 3. Keadaan sekarang (17 Oktober 2026)

**Cabang kerja:** `fitur/tema-tampilan-dan-kartu-berikutnya`, dibuat dari
`origin/main` (PR #2 sudah ter-merge). **Belum di-push**, belum ada PR. Isinya
commit berikut di atas `main`:

| Commit | Isi |
|---|---|
| `31e83b2` | Tema tampilan petugas, kartu "Berikutnya & hari ini", perbaikan audit |
| `33664be` | Nomor prioritas dan urutan panggil 3:1 |
| `885cb52` | Prioritas mandiri dari anjungan, petugas pelayanan menandai |
| `5426aa7` `da92546` | Layar penuh tanpa bingkai; penyatuan versi APK |
| `e5944c3` | Prioritas **ditandai hanya di anjungan**, **dicabut hanya oleh petugas** |
| `96437f7` | `.gitignore` salinan APK sebelum rilis |
| `ac4c5f4` | Video lewat TextureView; label "Sentuh layar" di paling atas |
| `62f3878` | Aplikasi Windows 1.0.10 |
| `178d088` | Salinan media: status per tablet, Segarkan media, Salin dari server |
| `37fb744` | Tempat tampil per berkas: panel atas / layar penuh / keduanya |
| `543d5f3` | Anjungan 2.4.34.1 |
| `eea7ab2` | Dokumentasi serah terima untuk Codex dan Claude |
| `338783c` | PIN pengaturan anjungan di server (hash, verifikasi, dialog admin) |
| (berikutnya) | Android: papan PIN, mode putar saja, tempat tampil folder tablet |
| `2f03a22` | Keamanan (pembaruan bertanda tangan, PIN, kode pasang), alur pembaruan admin/petugas, Laporan Saya |
| (commit 17 Okt) | Tanpa SQLite, polling anjungan ≤ 10 SQL, pembaruan lanjut-unduh/tunda/audit hasil, versi PC di Kesehatan, laporan prioritas, mode memanjang + Pas/Isi (Android) |

**Versi.**

| | Dikodekan | Dibangun | Dibagikan/terpasang |
|---|---|---|---|
| Aplikasi Windows | 1.0.11 | `dist\AntrianCRO-Setup-1.0.11.exe` (dibangun 19 Okt 2026 dengan `-SkipTests` karena suite penuh baru lulus; belum ditandatangani) | belum dipasang di PC mana pun |
| APK anjungan | **2.5** (kode 54; keputusan pemilik 19 Okt 2026, lompat dari 2.4.34.3) | `dist\antrianCRO-2.4.34.3.apk` (build debug); 2.5 belum dibangun | `apk/` masih 2.4.34.3; 2.5 menunggu permintaan rilis |
| APK layar antrian | 1.6 (kode 7) | `dist\AntrianLayar-1.6.apk` | dibagikan dari `apk/`; belum diuji di perangkat |
| `VERSI_MINIMAL` APK (server) | 49 | | tablet 2.4.33 tetap diterima |

**Migrasi Alembic** (head: `f1b4c8d2a6e9`, kolom `service_category.frasa_catatan`; sebelumnya `e9c3b5a7d281`):
`c3f8a1d7e592` kolom `queue.prioritas` → `d6a1f3b8c704` `queue.prioritas_asal`
→ `e9c3b5a7d281` status salinan media di `kiosk_device`.

**Database.**

- `antrian_uji`: sudah di head; di-reset dan di-seed ulang selama audit Codex
  16 Oktober 2026. Semua tes audit setelah koreksi dijalankan dengan URL
  PostgreSQL `antrian_uji` yang diverifikasi eksplisit; SQLite tidak dipakai lagi.
- `antrian` (kerja): di `d6a1f3b8c704`. **`e9c3b5a7d281` belum diterapkan**;
  berjalan otomatis saat aplikasi Windows dibuka berikutnya. Backup sebelum
  migrasi prioritas: `backup/queue-20261016-102726-sebelum-prioritas.dump`.
- Akun uji (hanya `antrian_uji`): `cro` / `rahasia123`. Akun kerja: `admin`,
  `daffa` (CRO), `daffa2` (CRO); kata sandinya milik pemilik, jangan
  dicari atau disimpan.

**Proses yang berjalan di komputer ini.**

- API anjungan (port 8765) memakai **kode lama**. Harus dimulai ulang agar
  `priority_enabled`, `media_refresh`, `show`, dan endpoint `media-library`
  tersedia untuk tablet. Jenis prosesnya (layanan atau tugas terjadwal)
  belum diperiksa.
- Aplikasi Windows yang terbuka juga memakai kode sebelum perubahan
  terakhir; tutup dan buka ulang.

---

## 4. Fitur yang ditambahkan Oktober 2026

### 4.1 Tab Tampilan dan tema petugas

- Menu **Tampilan** (paling kanan) untuk semua akun kecuali layar antrian/kios;
  8 tema: Indigo (bawaan), Samudra, Zamrud, Pasir, Sakura, Merdeka, Malam,
  Kontras Tinggi. Disimpan **per komputer** di `tampilan.json` (folder
  database, di-`.gitignore`; override env `ANTRIAN_TAMPILAN_PATH`).
- Kode: `app/ui/tema_petugas.py` (mengubah warna hex pada stylesheet jadi,
  tidak menyentuh puluhan modul), `app/ui/tampilan_page.py`, wiring di
  `MainWindow._susun_menu` (`MENU_TAMPILAN`, `pelengkap`, `tanpa_peran`) dan
  `app/main.py` (`terapkan_tema(app, baca_tema())`).
- **Penjaga kontras otomatis** (rasio ≥ 4,5; 7 pada Kontras Tinggi; 3 untuk
  tombol nonaktif). Tes: `tests/test_tema_petugas.py`.
- Cara kerja memakai monkeypatch global `QWidget.setStyleSheet`,
  `QLabel.setText`, `QTableWidgetItem.setForeground/Background`
  (dipasang sekali). Pilihan sadar; alternatifnya lapisan gaya terpusat yang
  mengubah puluhan modul. Kode yang menggambar sendiri dengan QPainter
  harus memakai `warna_tema()` (contoh: grafik di `dashboard_page.py`).
- Tes yang menyentuh tema **harus mengembalikan** stylesheet/palet aplikasi
  (lihat fixture `_kembalikan_tema`), kalau tidak tes tata letak lain gagal.

### 4.2 Halaman Pelayanan

- **Papan tunggu** (`app/ui/queue/papan_tunggu.py`) pindah ke tab
  *Menunggu Dilayani*, berbentuk kartu per layanan + kartu **Semua**; kartu
  **dapat diklik untuk menyaring** tabel di bawahnya. Tingginya mengikuti isi.
- **Kartu "Berikutnya & hari ini"** (`kartu_berikutnya.py`) di kolom kiri,
  memakai sisa tinggi dan tidak tampak bila terlalu sempit (tidak pernah
  membuat halaman bergulir).
- Tombol **Mulai Istirahat** sejajar dengan kotak Loket dan Jenis Layanan.
- Menu atas (pil) di tengah vertikal; tab "Pengaduan && Catatan" (dua `&`).

### 4.3 Nomor prioritas — dokumen rinci: [prioritas-antrian.md](prioritas-antrian.md)

- **Ditandai hanya di anjungan** (kotak "Saya lansia / disabilitas / ibu
  hamil" di menu awal; `priority` pada `POST /v1/kiosk/tickets`) atau oleh
  petugas pendaftaran bila suatu saat ada. **Dicabut hanya oleh petugas
  pelayanan** (`QueueService.cabut_prioritas`). Petugas pelayanan **tidak
  bisa menandai**; ada tesnya.
- Kolom `queue.prioritas` (`LANSIA/DISABILITAS/IBU_HAMIL/PRIORITAS`) dan
  `prioritas_asal` (`PENDAFTARAN/MANDIRI`).
- Urutan: `app/services/urutan_prioritas.py` (fungsi murni). Otomatis 3
  prioritas : 1 biasa (`queue.rasio_prioritas`, 0 = prioritas selalu dulu);
  pilihan petugas **Prioritas dulu / Biasa dulu** berlaku satu panggilan.
  Dipakai `call_next`, `list_waiting`, layar antrian, anjungan, sisa antrian
  di tiket, dan dashboard petugas.
- Saklar `kiosk.prioritas_aktif`; `priority_enabled` pada `/v1/kiosk/display`.
- Audit: `CREATE_QUEUE` (dengan alasan dan asal), `CLEAR_PRIORITY`.
- UI: ★ di tabel dan kartu, pita "★ PRIORITAS · … · dipilih pengunjung,
  mohon periksa" + tombol **Cabut prioritas** di kartu nomor aktif.
  Tiket mencetak "· Prioritas" pada baris layanan.

### 4.4 Anjungan Android (2.4.34.1)

- **Kotak prioritas** di menu awal, dikosongkan tiap tiket terbit/dibatalkan/
  masuk iklan layar penuh. Kartu layanan dikurangi tingginya (`dp(66)`).
- **Iklan layar penuh tanpa bingkai**: margin, padding, sudut, garis tepi
  dihapus di atas latar hitam (`bukaBingkaiIklanPenuh`). Rasio video dijaga
  (pas). Label **"Sentuh layar…"** kini **panel tetap di ATAS layar** (navy pekat, tinggi ±12% layar memanjang / ±8% layar tegak, 44–96 dp); video di bawahnya, fit tanpa terpotong (`tampilkanPanelAjakanIklan`; sebelumnya strip gradasi di dasar yang muncul-hilang). Belum diuji di perangkat, hanya dikompilasi.
- **Pemutar video `VideoTekstur`** (TextureView + MediaPlayer) menggantikan
  `VideoView`. Alasan: di BlueStacks `VideoView` (SurfaceView) tampil hitam
  padahal pemutar berjalan (decoder perangkat lunak mengeluarkan buffer
  YV12 yang tidak dikomposisi). **Belum terbukti memperbaikinya di
  perangkat** (lihat bagian 6).
- **Tempat tampil per berkas**: `daftar_putar.Butir.tampil`
  (`panel/penuh/keduanya`), `welcome_media_files[].show`. Panel atas memutar
  *Panel atas*+*Keduanya*; layar penuh memutar *Layar penuh*+*Keduanya*;
  bila tidak ada media layar penuh, layar penuh **tidak aktif** (tidak
  dipaksa). Dialog **Atur jadwal…** punya kolom **Tampil di**.
- **Salinan media** ([android-kiosk.md](android-kiosk.md), bagian
  "Salinan media"): kolom **Media** di kartu perangkat (status tersalin),
  tombol **Segarkan media** (`media_refresh`), dan **Salin dari server**
  (`/v1/kiosk/media-library`) di Kelola media tablet.

- **Panggilan mengalahkan iklan** ([android-kiosk.md](android-kiosk.md),
  bagian "Panggilan mengalahkan iklan"): panggilan/panggilan ulang petugas
  menghentikan iklan layar penuh, banner nomor ±6 detik, hitungan menganggur
  diulang. Setelan **Panggilan menghentikan iklan** (grup Iklan Anjungan,
  `kiosk.panggilan_hentikan_iklan`, API `call_interrupts_ad`; per loket
  `call_count`). Dibangun sebagai APK debug, **belum diverifikasi di perangkat**
  dan belum dirilis.

- **Dialog Media di tablet ini** dirombak (ringkasan, kelompok Video/Gambar,
  gambar mini, menu Aksi, Hapus semua); lihat android-kiosk.md. APK debug saja,
  belum diverifikasi di perangkat.

- **Warna kilau bebas** per tablet (pemilih warna + hex); lihat android-kiosk.md.
  APK debug saja, belum diverifikasi di perangkat.

- **Bintang prioritas** pada nomor menunggu (anjungan, layar Android, layar
  Windows), tanpa alasan; kini bintang kecil di pojok kiri atas ubin + latar amber lembut (bukan lagi " ★" di belakang nomor); lihat android-kiosk.md. APK debug saja, belum diuji di perangkat.

- **Panel keluar sebelum iklan muncul** dan **kotak prioritas di atas tombol
  layanan**; lihat android-kiosk.md. APK debug saja, belum diuji di perangkat.

### 4.4b PIN pengaturan anjungan dan mode putar saja

Rinci di [android-kiosk.md](android-kiosk.md) (bagian "PIN pengaturan dan
mode putar saja"). Ringkas: PIN 6 angka satu untuk semua tablet, diatur admin
di Layanan Anjungan (server menyimpan hash PBKDF2-SHA1; kode
`app/services/pin_anjungan.py`, API `POST /v1/kiosk/pin/verifikasi`,
`settings_pin` pada `/v1/kiosk/display`). Server tidak terjangkau ≥ 30 detik →
anjungan hanya memutar video (jalan pulih: tahan pojok kiri bawah 5 detik +
PIN). Media dari server mengikuti aturan server; media dari folder tablet
mengikuti aturan tablet (tombol tempat tampil di Kelola media tablet).
Keputusan pemilik: PIN diatur sekali di server; tanpa server semua fitur
mati kecuali video. **Belum dirilis** (APK `apk/` masih 2.4.34.1 tanpa ini).

### 4.5 Keamanan login

- Penundaan login **bertingkat** per nama pengguna, dihitung dari audit
  `LOGIN_FAILED` (jendela 15 menit; 5–7 gagal → 1 menit, 8–9 → 5 menit, ≥10
  → 15 menit; dikosongkan oleh login berhasil atau pemulihan admin).
  Tombol "Lupa kata sandi admin?" baru muncul setelah 3 kali gagal.
  Rinci: [keamanan-sesi.md](keamanan-sesi.md).

### 4.6 Pembaruan aplikasi Windows

- `GET /v1/windows/update` dan `/download`, pita pembaruan di aplikasi,
  installer 1.0.10. Folder `pembaruan` di komputer server berisi
  `Pembaruan-AntrianCRO.exe` + `.version`.

---

## 5. Keputusan pemilik (jangan dibalik tanpa bertanya)

1. Prioritas ditandai **di anjungan** oleh pengunjung (dibantu petugas
   berjaga lisan), dicabut oleh petugas pelayanan. Kategori: lansia,
   disabilitas, ibu hamil. Urutan 3:1, rasio dapat diatur admin, petugas
   dapat memilih langsung.
2. Anjungan memutar **video layar penuh saat menganggur, sentuhan kembali ke
   menu**; layar penuh harus memenuhi **seluruh layar tanpa terpotong**.
   Video untuk panel atas dan layar penuh **dibedakan**.
3. Versi APK tidak dinaikkan per perubahan; format `2.4.34.1` dipakai pemilik
   untuk rilis berikutnya.
4. Tema ada 8, termasuk **Sakura** (pink) dan **Merdeka** (merah putih).
5. Suite penuh hanya sebelum push; **tidak push tanpa diminta**.

---

## 6. Belum selesai / belum terverifikasi

**Belum terverifikasi di perangkat** (ADB BlueStacks sering menolak perintah
dengan `error: closed`):

- Pemutar `VideoTekstur` apakah benar menampilkan video di BlueStacks.
- Papan PIN, mode putar saja (mematikan server lalu menunggu 30 detik), dan
  jalan pulih sentuh-tahan pojok kiri bawah.
- Kotak prioritas di menu awal, tombol Salin dari server, pemisahan panel
  atas/layar penuh, dan layar penuh tanpa bingkai.
- Semua belum pernah dijalankan di panel Maxtor asli.

**Pekerjaan yang sudah disepakati tetapi belum dibuat:**

- Ekspor laporan di latar belakang (data besar).
- Merge/PR cabang ke `main`.

**Hal yang perlu tindakan manusia:**

- Mulai ulang API server (kode baru) dan buka ulang aplikasi Windows
  (menerapkan migrasi `e9c3b5a7d281`).
- Pasang APK 2.4.34.1 ke BlueStacks/tablet (seret ke jendela BlueStacks, atau
  ⚙ Pengaturan → Perbarui bila server membagikannya).
- Memastikan resolusi panel (`adb shell wm size`; BlueStacks Pie64 = 2160 ×
  3840 tegak).
- Memasang installer 1.0.10 di PC loket setelah pemilik puas.

**Risiko yang diketahui:**

- Monkeypatch tema (bagian 4.1).
- Kotak prioritas anjungan tidak memverifikasi kebenaran; pengawasnya
  petugas berjaga dan petugas loket (dapat mencabut).
- Sesi sebelumnya sempat membuat `data/tampilan.json` dari tes yang tidak
  mengisolasi env; sudah diisolasi di `tests/conftest.py` (`app_config`,
  `env_mesin`).

**Perbaikan keamanan 16 Oktober 2026 (Claude)**, rinci di
[keamanan-sesi.md](keamanan-sesi.md). Tiga temuan keamanan Codex di bawah
sudah ditutup:

- Pembaruan Windows wajib bertanda tangan Ed25519 (`tanda_sah`,
  `alat/tandatangani_pembaruan.py`, berkas `Pembaruan-AntrianCRO.sig`).
  **Rilis 1.0.11 berikutnya harus ditandatangani pemilik**; tanpa `.sig`,
  PC loket 1.0.11 tidak menawarkan pembaruan. PC 1.0.10 (tanpa verifikasi)
  tetap menerima seperti dulu.
- `X-Device-Id` token bersama yang milik tablet terpasang diabaikan; pembatas
  PIN per IP; hash PIN hanya ke tablet terpasang.
- Kode pasang ditandai dengan UPDATE bersyarat; pembatas tebakan per IP +
  gabungan, di bawah `lock_tebakan`.
- Juga: Kesehatan Sistem › **Kata sandi bawaan** dan **Pembaruan Windows di
  server**; job CI **Audit dependency** (`pip-audit==2.9.0 --no-deps`);
  `backup/*.bundle` di `.gitignore`.
- Keputusan pemilik 17 Okt: enkripsi **hanya salinan kedua**; alamat API
  **dipilih admin** di Layanan Anjungan (bawaan semua antarmuka). Keduanya
  sudah dibuat (lihat di bawah dan keamanan-sesi.md). Mematikan token bersama
  tetap langkah operasional.

**Pekerjaan 17 Oktober 2026 (Codex, dilanjutkan Claude)** — terhenti di tengah
karena batas pemakaian Codex habis pukul 17:37; Claude menambah tes tahap
terakhir dan meng-commit-nya.

- **SQLite dihapus dari aplikasi**, bukan hanya dari tes: `AppConfig` menolak
  URL kosong atau selain PostgreSQL; pilihan "satu komputer" hilang dari dialog
  mesin. Pemasangan lama bermode satu komputer **diarahkan ke dialog koneksi**
  saat dibuka. Penjaga di `tests/conftest.py` membaca `~/.antrian-uji-db` dan
  menolak apa pun selain PostgreSQL bernama tepat `antrian_uji`;
  `test-postgres.ps1` diperbaiki (sebelumnya `antrian_test`).
- **Polling `/v1/kiosk/display` ≤ 10 pernyataan SQL** (dari 41): satu cuplikan
  pengaturan, daftar menunggu/prioritas dibaca sekali
  (`tests/test_tiket_anjungan.py::test_polling_layar_anjungan_tidak_mengulang_query_yang_sama`).
- **Pembaruan Windows**: lanjut-unduh berkas `.exe.tmp`, **Tunda sampai besok**
  per versi (`pembaruan-lokal.json` di folder data), dan audit
  `WINDOWS_UPDATE_RESULT` sekali setelah aplikasi hidup kembali.
- **Versi PC di Kesehatan Sistem**: audit `LOGIN` kini menyimpan `komputer`
  (hostname) dan `versi_aplikasi`; `_periksa_komputer_windows` menampilkan satu
  baris per PC dari login terbaru 30 hari terakhir (versi lama = PERINGATAN).
  PC yang belum login dengan versi ini belum terlihat.
- **Laporan**: jumlah prioritas, prioritas dicabut, rata-rata tunggu prioritas,
  penanda per nomor di Excel/PDF.
- **Android (APK debug saja, belum diuji di perangkat, `apk/` tidak disentuh)**:
  tata letak tiga kolom bila lebar ÷ tinggi > 2,5; pilihan video **Pas/Isi** per
  tablet (`skala_video`); executor `pembuatThumbnail` dimatikan di `onDestroy`.
- **Belum dikerjakan dari rencana Codex**: ekspor laporan di latar belakang.

**Sisa pekerjaan 17 Oktober 2026 (Claude)**:

- **Perkiraan tunggu** nomor biasa ditambah perkiraan penyalip prioritas:
  laju prioritas terbit 60 menit terakhir × lama tunggu, dibatasi rasio
  (`sisipan_prioritas`, `QueueRepository.jumlah_prioritas_terbit_sejak`).
  Nomor prioritas tidak berubah.
- **Ukuran media di Atur jadwal…**: lebar × tinggi dan rasio (gambar via
  Pillow, MP4/MOV/3GP/M4V dari kotak `tkhd`, termasuk rotasi ponsel);
  peringatan bila berkas tegak dipakai di panel atas
  (`app/services/ukuran_media.py`). MKV/WebM/AVI: "tidak terbaca".
- **Audit unduhan laporan** `EXPORT_REPORT` (format, cakupan cabang/pribadi,
  rentang tanggal; tanpa nama/letak berkas) lewat `ReportService.catat_unduhan`.
- **Catatan rilis**: `Pembaruan-AntrianCRO.catatan.txt` (opsional, `--catatan`
  di alat tanda tangan) → `release_notes` di API → tombol **Apa yang baru?**
  di pita pembaruan (teks biasa, tidak ditandatangani).
- **Enkripsi salinan backup kedua** dan **alamat API pilihan admin**:
  rinci di keamanan-sesi.md.
- Tes backup PostgreSQL di komputer ini butuh `C:\Program Files\PostgreSQL\17\bin`
  di PATH; tanpa itu tes backup **dilewati** (bukan lulus).

**Temuan audit Codex 16 Oktober 2026 (sisa yang belum diperbaiki):**

- Dua tes layout stabil gagal pada 1366 x 768: kelompok **Iklan Anjungan**
  membutuhkan gulir vertikal 287 px pada mode loket maupun server. Dua tes
  Pelayanan lain sempat gagal saat suite gabungan tetapi lulus saat diulang
  terarah, menunjukkan state global tema/layout masih bergantung urutan tes.

Verifikasi audit: `ruff check app tests alembic` dan compile Python lulus;
299 tes keamanan/API terarah lulus di PostgreSQL (2 dilewati); 513 tes
wiring/UI lulus, 4 gagal, 2 dilewati; pengulangan empat kegagalan menghasilkan
2 gagal layout yang stabil dan 2 lulus; 26 tes migrasi/database/penomoran lulus,
4 tes khusus SQLite dilewati; kedua APK debug berhasil dikompilasi. Pencarian
OSV terhadap 17 dependency langsung tidak menemukan advisory yang cocok dengan
versi terpasang. Suite penuh tidak dijalankan karena aturan proyek membatasinya
untuk sebelum push/PR.

Audit teks tombol (16 Oktober 2026, Claude; menggantikan catatan Codex yang
menyatakan "tidak ditemukan potongan" — pemeriksaan permanen ternyata menemukan
tiga):

- **Terbukti terpotong** (lebar < `sizeHint()`): (1) "Panggil Berikutnya · F2"
  di Pelayanan, 250 px dari 254 px, karena `setFixedWidth(250)` pada
  pembungkus tombol; (2) "Pasang ulang & nyalakan ulang" di Layanan Anjungan
  pada 800×600 dan Windows 125%/150%, karena sebaris dengan kotak centang
  panjang; (3) "Segarkan media" di tabel perangkat, 131 px dari 135 px, karena
  lebar kolom aksi dihitung dari `sizeHint()` sebelum tombol dipolish.
- **Perbaikan:** `service_page.py` (pembungkus tombol memakai kebijakan
  `Minimum`, tanpa lebar tetap/minimum buatan); `layanan_anjungan_page.py`
  (kotak centang pindah ke baris sendiri); `kartu_perangkat.py`
  (`_atur_lebar_aksi`: polish dulu, dihitung ulang saat kartu tampil, sisa 16 px
  karena widget sel ±12 px lebih sempit dari kolomnya).
- **Tes permanen:** `tests/ukuran_tombol.py` (pengukur reusable) dan
  `tests/test_teks_tombol.py`: 4 peran × 800×600 / 1280×720 / 1366×768; 4 peran
  × ukuran logis Windows 125% (1093×614) dan 150% (911×512); admin & CRO dengan
  font-size stylesheet ×1,25 dan ×1,5; keadaan khusus (pita pembaruan dua
  label, pita anjungan, perangkat terpasang, nomor sedang dilayani, Buka/Tutup
  Pendaftaran); 13 dialog × font 100%/150%. Semua label bergantian (Unduh &
  Perbarui/Sedang mengunduh…, Mulai/Akhiri Istirahat, Ganti Loket/Batal,
  Tampilkan/Sembunyikan, Aktifkan/Nonaktifkan, Pasang…) dipasang satu per satu.
  Syarat lulus: lebar ≥ `sizeHint().width()` dan tinggi ≥ satu baris huruf
  (tinggi tidak dibandingkan ke `sizeHint` karena layout boleh menekan 1–2 px
  tanpa memotong huruf). Pengecualian: `PENGECUALIAN` di `ukuran_tombol.py`
  (kosong).
- **Hasil uji** (PostgreSQL `antrian_uji` via `~/.antrian-uji-db`, satu proses
  pytest, divalidasi `postgresql` + nama tepat `antrian_uji`): `test_teks_tombol.py`
  seluruhnya lulus (57 tes). Gabungan dengan `test_ui`, `test_dashboard_ui`,
  `test_active_service_ui`, `test_notes_ui`, `test_daftar_putar_ui`,
  `test_tema_petugas`: 357 lulus, 2 dilewati, 4 gagal — 2 itu `Iklan Anjungan`
  287 px (temuan lama bagian ini), 2 itu tes Pelayanan 1366×768 yang **lulus
  bila dijalankan sendiri** (ketergantungan urutan lama yang sudah tercatat;
  belum dipastikan apakah tes baru memperparahnya). `ruff check app tests
  alembic` lulus. Suite penuh tidak dijalankan.
- **Suite penuh sebelum push** (16 Oktober 2026, 30 menit): 1808 lulus, 3 gagal yang kemudian diperbaiki: enam pengaturan `kiosk.*` (iklan_putaran, animasi_*, panggilan_hentikan_iklan) belum ada di seed (`app/core/seed.py`), dan grup "Iklan Anjungan" bergulir 287 px di 1366×768 sehingga dipecah: grup baru "Perilaku Iklan" memuat putaran iklan, empat animasi, dan panggilan menghentikan iklan. Dua error `caplog` hanya karena bendera `-p no:logging` saya.
- **Belum teruji:** DPI Windows sungguhan (Qt offscreen tidak menskalakan
  piksel; 125%/150% hanya didekati lewat ukuran jendela logis dan font-size
  stylesheet), font Segoe UI pada mesin lain, `SurveyDialog`, dialog
  `CounterCategoryDialog`, dan tombol yang hanya muncul pada data tertentu.
  Label pita pembaruan tidak lagi memakai `&`, sehingga risiko Qt membacanya
  sebagai penanda pintasan sudah hilang.

**Pengalaman pembaruan Windows 17 Oktober 2026 (Codex):**

- Alur dipisah menjadi **unduh → siap dipasang → pasang**, sehingga selesai
  mengunduh tidak lagi langsung membuka installer. Pita menampilkan progres
  persen dan MB. Admin melihat ukuran serta status terverifikasi dengan tombol
  **Unduh pembaruan / Pasang sekarang**; petugas memakai **Unduh di latar
  belakang / Pasang setelah pelayanan**.
- `PembaruanWindowsService` menolak pemasangan oleh CRO yang masih memegang
  nomor aktif. Penjaga berada di service layer. Pemeriksaan ruang disk menyisakan
  cadangan 64 MB; gagal unduh atau gagal membuka installer dapat dicoba lagi.
- Tes PostgreSQL terarah `test_pembaruan_windows.py` + `test_teks_tombol.py`:
  **76 lulus**, satu peringatan deprecation Starlette. `ruff check app tests
  alembic` dan `git diff --check` lulus.
- Belum dibuat: tombol tunda per versi, melanjutkan unduhan terputus, catatan
  rilis, pemasangan terjadwal, audit hasil setelah aplikasi hidup kembali, dan
  pemantauan versi seluruh PC.

**Unduh PDF/Excel admin dan petugas 17 Oktober 2026 (Codex):**

- Admin/supervisor tetap mendapat menu **Laporan** seluruh cabang. CRO kini
  mendapat **Laporan Saya** dengan rentang tanggal, PDF, dan Excel berisi hanya
  nomor yang ditangani akun yang sedang masuk. `laporan_petugas()` tidak
  menerima id petugas dari UI; cakupan ditentukan dari sesi dan ditegakkan oleh
  `QUEUE_CALL` di service layer.
- Laporan pribadi tidak menampilkan lembar **Per petugas** maupun **Petugas per
  layanan** yang redundan. Nama petugas, judul personal, serta nama berkas
  `laporan-saya-...` membedakannya dari laporan seluruh cabang.
- Tombol menjadi **Unduh PDF/Unduh Excel**. UI menampilkan proses dan hasil
  secara sebaris, menambahkan ekstensi yang hilang, memakai folder home bila
  Documents tidak ada, dan menulis ke berkas sementara sebelum mengganti tujuan
  supaya laporan lama tidak rusak bila ekspor gagal.
- Tes terarah PostgreSQL `test_report_service.py` + `test_teks_tombol.py`:
  **73 lulus**. Suite penuh belum dijalankan karena tidak sedang push/PR.

---

## 7. Perintah penting

```powershell
# Tes terarah
.\.venv\Scripts\python.exe -m pytest -q tests/test_prioritas.py tests/test_kiosk_api.py
# Lint
ruff check app tests alembic
# Suite penuh (sekali sebelum push)
.\.venv\Scripts\python.exe -m pytest -q
# Aplikasi Windows dari kode (database mengikuti data\mesin.json)
.\.venv\Scripts\python.exe -m app.main
# Installer Windows (menjalankan tes sendiri; keluaran di dist\)
.\build-installer.ps1
# APK anjungan + layar; MENYALIN ke apk\ (dibagikan server). Backup apk\ dulu.
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
.\build-android-kiosk.ps1
# Hanya compile APK debug (tidak menyentuh apk\)
cd android-kiosk; .\gradlew.bat --no-daemon :app:assembleDebug
```

**Menjalankan aplikasi terhadap database uji** (aman, tanpa menyentuh data
kerja): set `ANTRIAN_DB_URL` dari `~/.antrian-uji-db`, serta
`ANTRIAN_TAMPILAN_PATH` dan `ANTRIAN_PERAN_PATH` ke berkas sementara.
Skrip bantu pernah menjalankan `upgrade_to_head()` + `seed_initial_data()`
lalu mengisi nomor contoh lewat sesi anjungan (`AuthService.mulai_sesi_kios`).

**ADB ke BlueStacks.** Pakai server ADB sendiri (`adb -P 5038 ...`) bila
server 5037 mati. Instance `Pie64` di `127.0.0.1:5555` / `emulator-5554`.
Koneksi sering putus (`error: closed`); `adb connect` ulang atau
`kill-server` + `start-server`. `adb push` kadang gagal; alternatifnya
menyeret APK ke jendela BlueStacks. Tangkapan layar:
`adb -P 5038 -s emulator-5554 exec-out screencap -p > layar.png`. Log:
`adb ... shell "logcat -d -t 800"`.

**Catatan alat.**

- Heredoc `python - <<'PYEOF'` dengan banyak tanda kutip tiga kadang
  merusak shell; tulis skrip ke berkas lalu jalankan.
- Berkas di repo bercampur LF/CRLF; skrip pengedit membaca dengan
  `newline=""`, memakai `\n` di memori, dan menulis kembali dengan akhiran
  asli. Jangan menyisipkan BOM (Set-Content PowerShell 5.1 `-Encoding UTF8`
  menambahkannya; Gradle gagal).
- Di string Python non-raw, `\b` menjadi karakter backspace; pakai raw string
  atau `chr(92) + "b"` untuk regex.

---

## 8. Peta berkas untuk fitur baru

| Area | Berkas |
|---|---|
| Tema | `app/ui/tema_petugas.py`, `app/ui/tampilan_page.py`, `tests/test_tema_petugas.py` |
| Papan tunggu / kartu | `app/ui/queue/papan_tunggu.py`, `kartu_berikutnya.py`, `service_page.py` |
| Prioritas | `app/services/urutan_prioritas.py`, `queue_service.py` (`create_queue`, `call_next`, `cabut_prioritas`), `app/models/queue.py`, `app/ui/registration/registration_page.py`, `tests/test_prioritas.py` |
| Salinan media | `app/models/kiosk_device.py`, `app/services/device_service.py`, `app/kiosk_api.py`, `app/ui/settings/kartu_perangkat.py` |
| Tempat tampil | `app/services/daftar_putar.py`, `app/ui/settings/dialogs.py` (`JadwalIklanDialog`), `settings_page.py` |
| Anjungan Android | `android-kiosk/app/src/main/java/id/sistemantrian/kiosk/MainActivity.java` (satu berkas besar) |
| Migrasi | `alembic/versions/c3f8a1d7e592_*`, `d6a1f3b8c704_*`, `e9c3b5a7d281_*` |
| Login bertingkat | `app/services/auth_service.py` (`TINGKAT_PENUNDAAN`), `app/ui/login/login_window.py` |

---

## 9. Riwayat pembaruan dokumen ini

| Tanggal | Oleh | Perubahan |
|---|---|---|
| 2026-10-16 | Claude | Dokumen dibuat; mencakup seluruh pekerjaan Oktober 2026 di atas |
| 2026-10-16 | Claude | Ditambah: panggilan mengalahkan iklan (setelan, `call_count`, banner, polling 1 detik) |
| 2026-10-16 | Codex | Audit penuh bug, wiring, performa, dan keamanan; temuan serta hasil tes PostgreSQL dicatat di bagian 6. |
| 2026-10-16 | Codex | Audit teks tombol pada tiga ukuran jendela; tidak ditemukan potongan, celah tes regresi dicatat di bagian 6. |
| 2026-10-16 | Claude | Tes permanen teks tombol (`tests/test_teks_tombol.py`, `tests/ukuran_tombol.py`); tiga tombol terpotong diperbaiki (bagian 6). |
| 2026-10-16 | Claude | Warna latar iklan penuh per tablet, murni Android (SharedPreferences `latar_iklan_penuh`, kontrol di dialog Pengaturan > Tampilan; tanpa server/DB); rincian di android-kiosk.md. APK debug terkompilasi, belum diuji di perangkat, belum di-commit. |
| 2026-10-16 | Claude | Perbaikan keamanan: pembaruan Windows bertanda tangan, celah `X-Device-Id`, hash PIN, kode pasang, Kesehatan, pip-audit (bagian 6) |
| 2026-10-17 | Codex | Audit pengalaman pembaruan Windows untuk admin dan petugas; saran pembedaan alur peran dicatat di bagian 6. |
| 2026-10-17 | Codex | Alur pembaruan admin/petugas dibuat dua tahap dengan progres, pemeriksaan ruang disk, dan pengunci pelayanan aktif. |
| 2026-10-17 | Codex | Laporan Saya PDF/Excel ditambahkan untuk CRO; ekspor admin/petugas memakai status sebaris dan penyimpanan atomik. |
| 2026-10-17 | Claude | Sisa pekerjaan: perkiraan tunggu + prioritas, ukuran media, audit unduhan laporan, catatan rilis, enkripsi salinan backup, alamat API (bagian 6). |
| 2026-10-17 | Codex → Claude | Tanpa SQLite, polling anjungan, pembaruan lanjut/tunda/audit, versi PC, laporan prioritas, Android memanjang; Codex terhenti (batas pemakaian), Claude menambah tes versi PC + meta login dan meng-commit (bagian 6). |
| 2026-10-19 | Claude | Kebersihan tes: fixture `tema_dan_gaya_pulih` (autouse) di conftest, `mesin_backup_tersedia` mencari pg_dump di Program Files sendiri dan GAGAL di CI bila tak ada, tes penjaga monkeypatch tema, `backup/*.patch` di `.gitignore`. Ekspor laporan latar belakang sedang dikerjakan sesi lain (report_page.py), jangan diulang. Denyut versi PC: klien mengirim `X-Komputer`/`X-Versi-App` saat memeriksa pembaruan, server mencatat `WINDOWS_PC_PING` (satu per PC per 6 jam, maks 120/jam), Kesehatan Sistem menggabungkannya dengan login; PC yang masih 1.0.10 ke bawah tetap tak terlihat sampai dipasang 1.0.11. |
| 2026-10-19 | Claude | Pemecahan `MainActivity.java` tahap 1: `VideoTekstur` pindah ke berkas sendiri (`VideoTekstur.java`, skala Pas/Isi lewat `PenentuSkala`); perilaku tidak berubah, APK debug terkompilasi, belum diuji di perangkat. Tahap 2: `KilauDrawable`, `LatarBendera`, `TandaPanah`, `TandaCentang`, `NomorBerbintang` juga berkas sendiri (MainActivity 7421 → 7052 baris). Tahap 3: `BidangWarnaKilau` dan `Tema` (+ pabrik `Tema.dari`) juga berkas sendiri (MainActivity kini 6889 baris). Tahap 4: `KlienServer.panggil` (satu permintaan JSON, blokir), `PenolakanServer`, `JSONObjectBuilder` berkas sendiri; `request()` di MainActivity tinggal mengatur utas dan callback (MainActivity 6818 baris). Tahap 5: tiga unduhan (media ke memori, salinan ke berkas .part, paket suara) pindah ke `UnduhServer` (MainActivity 6740 baris). Tahap 6: unduh+pasang APK pembaruan pindah ke `PemasangPembaruan`, salin dari server ke `UnduhServer.keBerkasGanti`; `HttpURLConnection` di MainActivity tinggal `applyHeaders` (MainActivity 6659 baris). Tahap 7: pembantu murni berkas media (jenis, nama aman, baca berkas, ukuran, durasi, thumbnail) ke `BerkasMedia` (MainActivity 6596 baris). Sisa: pemecahan per layar (menu awal, pengaturan, dialog media, iklan), yang bergantung pada keadaan bersama Activity dan sebaiknya dikerjakan satu layar per tahap dengan uji perangkat. Kesehatan Sistem juga memberi peringatan bila porsi prioritas 7 hari > 40%. |
| 2026-10-19 | Claude | Laporan dirapikan: laporan pribadi tanpa kolom/kartu menunggu dan prioritas (kartu 'Nomor dipanggil'); kartu berwarna + pembanding periode sebelumnya (`Laporan.total_sebelumnya`, `kartu_ringkasan`), sorotan, grafik tren (`grafik_tren.py`, `deret_tren`), tabel layar ringkas dan dapat diurutkan + baris total, tab Riwayat saya, tombol Tahun ini, keadaan kosong. Survei kini dihitung pada hari nomor terbit. Belum di-commit. |
| 2026-10-19 | Claude | Catatan petugas WAJIB untuk menyelesaikan pelayanan: tombol Selesai dihapus, diganti **Simpan & Selesai (F8)** di kaki panel catatan (`TombolSelesai`: menyala bila nomor sedang dilayani DAN catatan memadai, min. 10 huruf dengan >=3 huruf berbeda, `catatan_memadai`). `QueueService.complete(..., wajib_catatan=True)` memeriksa lembar tersimpan (UI memakainya; pemanggil lain tetap default tanpa syarat). Kalimat cepat per jenis layanan (`service_category.frasa_catatan`, migrasi f1b4c8d2a6e9, diatur di dialog Data Master, bawaan `FRASA_BAWAAN`). Simpan draf otomatis tiap 15 dtk. Admin: `selesaikan_paksa` + tombol di halaman Pelayanan Aktif (tanpa syarat catatan, alasan wajib, audit COMPLETE_QUEUE paksa=True). Belum di-commit. |
| 2026-10-19 | Claude | Rilis APK anjungan **2.4.34.3** (ubin nomor menunggu hampir datar, pergantian halaman memudar tanpa putaran 3D) dan layar **1.6** (nomor menunggu lebih datar); `apk/` lama disalin ke `backup/apk-sebelum-2.4.34.3/`. Suite penuh 1997 lulus, lalu push cabang. Temuan: simpan otomatis NotePanel (15 dtk) dulu menulis ke DB sesudah panel ditutup (kini hanya bila jendela tampil). `build-installer.ps1` kini memakai PostgreSQL `antrian_uji` (dari `ANTRIAN_DB_URL` atau `~/.antrian-uji-db`) untuk uji bundel, bukan SQLite. **Regresi papan tunggu (d5b3fbf) tidak terreproduksi** (19 Okt, sesi berikutnya): tes `tests/test_regresi_papan_panggil.py` (tampil, panggil nomor, tunggu 300 ms; 800x600, 1093x614, 1366x768, 1920x1080) lulus di HEAD maupun di `d5b3fbf` sendiri. Tes dijaga tetap ada; bila proses Qt mati tanpa pesan lagi, mulai dari sini. |
| 2026-10-20 | Claude | Backup penuh, build installer bertes lulus (2030 lulus, kode keluar 0), dugaan bottleneck layar antrian (bagian atas). |
| 2026-10-19 | Claude | Audit kesiapan produksi: keluar aplikasi untuk peran tanpa QUEUE_CALL, akses admin ke Pelayanan Aktif, ambil alih tidak merebut dari pemilik yang masih hadir, 24 tes baru (lihat bagian atas). Status Siap staging/UAT. |
| 2026-10-20 | Codex | Audit ulang: lint bersih dan 117 tes terarah lulus; status tetap Siap staging/UAT, dengan build installer tanpa `-SkipTests` dan validasi perangkat/PC bersih sebagai sisa risiko. |

Saat menutup sesi: perbarui bagian 3 (keadaan, commit, versi), 6 (belum
selesai), dan tabel di atas.
