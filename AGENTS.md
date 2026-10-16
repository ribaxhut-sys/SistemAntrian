# AGENTS.md — Sistem Antrian & Survey Kepuasan CRO

Dibaca oleh Codex (dan asisten lain). Proyek ini dikerjakan bergantian oleh
Codex dan Claude. **Sumber kebenaran: [docs/serah-terima-ai.md](docs/serah-terima-ai.md)**
(keadaan sekarang, aturan kerja, yang belum selesai). Baca dulu, dan
perbarui di akhir sesi.

## Ringkasan aturan

- **Bahasa Indonesia** untuk jawaban ke pemilik, nama kode, docstring, dan
  pesan commit. Docstring menjelaskan *mengapa*.
- Aturan kode dan jebakan Qt: `docs/lanjutan.md` bagian 2.
- **Tes**: `.\.venv\Scripts\python.exe -m pytest ...` (bukan `python` biasa),
  hanya di PostgreSQL `antrian_uji` (`~/.antrian-uji-db`), **satu proses
  pytest sekali waktu**, jangan pernah di database `antrian`.
- Iterasi dengan **tes terarah** + `ruff check app tests alembic`. Suite
  penuh **sekali sebelum push/PR**.
- **Jangan push** kecuali diminta. Periksa `git status` tepat sebelum
  commit. Setiap PR: aktifkan Auto-fix.
- **Versi APK tidak dinaikkan per perubahan**; versi aplikasi Windows hanya
  naik saat installer baru diminta. Daftar berkas versi: serah-terima-ai.md.
- Migrasi Alembic hanya **menambah** kolom nullable. Backup (`pg_dump -Fc`
  ke `backup/`) sebelum migrasi ke database kerja.
- Jangan menaruh APK di `apk/` tanpa persetujuan (komputer ini juga server;
  tablet memperbarui diri dari sana). Backup isi lama dulu.
- Jangan mengubah pengaturan keamanan perangkat pemilik (mis. ADB
  BlueStacks); minta pemilik.
- Otorisasi di **service layer**, bukan hanya UI.
- Cocokkan permintaan dengan kode/dokumen/tes; laporkan bila tidak cocok.
