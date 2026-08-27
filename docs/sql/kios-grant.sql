-- Hak user PostgreSQL untuk mesin kios pengunjung.
--
-- Jalankan sebagai superuser, pada database antrian, SETELAH skema
-- terbentuk (setelah aplikasi pernah dibuka sekali sebagai petugas).
--
-- Mesin kios menghadap publik dan tidak diawasi. Connection string-nya
-- tersimpan di komputer itu, jadi user ini sengaja tidak boleh membaca
-- app_user — tanpa larangan itu, siapa pun yang mengakses kios dapat
-- membaca hash kata sandi seluruh petugas.
--
-- Langkah 1 (database postgres, sekali saja):
--
--     CREATE USER antrian_kios WITH PASSWORD 'ganti-kata-sandi-kios';
--     GRANT CONNECT ON DATABASE antrian TO antrian_kios;
--
-- Langkah 2 (database antrian, berkas ini):

GRANT USAGE ON SCHEMA public TO antrian_kios;

GRANT SELECT, INSERT, UPDATE ON TABLE queue, queue_sequence TO antrian_kios;
GRANT SELECT ON TABLE service_category, counter, branch, queue_call TO antrian_kios;
GRANT SELECT ON TABLE application_setting TO antrian_kios;
GRANT INSERT ON TABLE audit_log TO antrian_kios;

GRANT USAGE, SELECT ON SEQUENCE queue_id_seq, audit_log_id_seq TO antrian_kios;

REVOKE ALL ON TABLE app_user FROM antrian_kios;
