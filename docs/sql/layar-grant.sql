-- Hak user PostgreSQL untuk komputer layar antrian (televisi ruang tunggu).
--
-- Jalankan sebagai superuser, pada database antrian, SETELAH skema
-- terbentuk (setelah aplikasi pernah dibuka sekali sebagai petugas).
--
-- Terpisah dari antrian_kios dan sengaja lebih sempit lagi. Televisi ruang
-- tunggu hanya MEMBACA: tidak ada seorang pun yang berdiri di depannya
-- untuk mengambil nomor, sehingga hak menulis ke tabel queue di sana murni
-- kelebihan yang tidak pernah dipakai. Komputernya sama tidak diawasinya
-- dengan anjungan, dan connection string-nya sama-sama tersimpan di mesin
-- itu.
--
-- Satu-satunya yang ditulisnya adalah jejak audit saat layar dibuka dan
-- ditutup.
--
-- Langkah 1 (database postgres, sekali saja):
--
--     CREATE USER antrian_layar WITH PASSWORD 'ganti-kata-sandi-layar';
--     GRANT CONNECT ON DATABASE antrian TO antrian_layar;
--
-- Langkah 2 (database antrian, berkas ini):

GRANT USAGE ON SCHEMA public TO antrian_layar;

GRANT SELECT ON TABLE queue, service_category, counter, branch, queue_call
    TO antrian_layar;
GRANT SELECT ON TABLE application_setting TO antrian_layar;
GRANT INSERT ON TABLE audit_log TO antrian_layar;

GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO antrian_layar;

REVOKE ALL ON TABLE app_user FROM antrian_layar;

-- Lembar pengaduan berisi nama, nomor pelanggan, telepon, email, dan
-- alamat pelapor — satu-satunya data pribadi di seluruh database.
-- Mesin ini berdiri di ruang publik tanpa diawasi siapa pun, dan
-- tidak punya satu pun alasan untuk membacanya. Ditulis eksplisit,
-- bukan sekadar dibiarkan tidak di-GRANT: GRANT yang tidak pernah
-- diberikan tidak terbaca sebagai keputusan, dan orang berikutnya
-- yang menambahkan hak akses tidak akan tahu bahwa tabel ini
-- memang sengaja ditinggalkan.
REVOKE ALL ON TABLE queue_note FROM antrian_layar;
