# Istilah: empat bagian sistem

Setiap bagian punya satu tugas. Bila sebuah fitur tidak jelas masuk ke
mana, tabel ini yang memutuskan.

| Bagian | Perangkat | Tugasnya | Bukan tugasnya |
|---|---|---|---|
| **Anjungan** | Tablet Android + printer thermal USB | Pengunjung memilih jenis layanan, nomor terbit di server, tiket dicetak | Menampilkan antrian, jumlah yang menunggu, nomor loket |
| **Layar antrian** | TV Android (Maxtor) | Menampilkan nomor yang dipanggil tiap loket dan membunyikan panggilan | Menerbitkan nomor |
| **Aplikasi server** | Satu PC Windows dengan peran *server* | Memegang database PostgreSQL, menjalankan API untuk anjungan dan layar antrian (Task Scheduler), backup harian, menu **Layanan Anjungan** | — |
| **Aplikasi petugas** | PC Windows di tiap loket (peran *klien*) | Petugas masuk, memanggil, melayani, menyelesaikan, menulis pengaduan; admin mengelola data master, pengguna, dan pengaturan | Menjalankan API atau backup |

## Siapa menyambung ke mana

```
Anjungan (Android) ──┐
                     ├── API (HTTP, LAN) ──► Aplikasi server ──► PostgreSQL
Layar antrian (TV) ──┘                              ▲
                                                    │
Aplikasi petugas (Windows) ─────────────────────────┘ (langsung ke PostgreSQL)
```

* Anjungan dan layar antrian adalah **klien**: tidak punya database,
  tidak menyimpan antrian, dan tidak bisa bekerja tanpa aplikasi server.
* Aplikasi server dan aplikasi petugas adalah aplikasi Windows yang sama
  (`AntrianCRO.exe`); yang membedakan adalah peran komputernya
  (`data\mesin.json`: *server* atau *klien*).

## Peralihan

* Anjungan **tidak lagi** berjalan di Windows. Mode `--kios`, `--kios-totem`,
  dan `--layar` sudah dihapus.
* Layar antrian Windows (`AntrianCRO.exe --tv`) **masih ada** sebagai
  pengganti sementara sampai aplikasi layar antrian Android selesai, lalu
  ikut dihapus.

## Di dalam kode

| Istilah | Nama di kode |
|---|---|
| Anjungan | `anjungan` (jenis perangkat), `android-kiosk/`, `/v1/kiosk/...` |
| Layar antrian | `layar_antrian` (jenis perangkat), `app/ui/display/` (Windows, sementara) |
| Aplikasi server | peran mesin `server`, `app/kiosk_api.py`, `app/services/kiosk_server.py` |
| Aplikasi petugas | peran mesin `klien`, `app/ui/queue/`, `app/ui/main_window.py` |
