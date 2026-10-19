package id.sistemantrian.kiosk;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Unduhan berkas dari server anjungan (blokir; panggil dari utas pengunduh).
 * Pesan galatnya langsung layak ditampilkan di status perangkat.
 */
final class UnduhServer {
    private static final int BATAS_MEDIA_MEMORI = 32 * 1024 * 1024;

    private UnduhServer() { }

    /** Media kecil yang cukup di memori (maksimal 32 MB). */
    static byte[] keMemori(String url, KlienServer.PenyetelKepala kepala) throws Exception {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setConnectTimeout(8000);
            connection.setReadTimeout(20000);
            kepala.terapkan(connection);
            int code = connection.getResponseCode();
            if (code >= 400) throw new IllegalStateException("Media tidak dapat dimuat.");
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            int length;
            try (InputStream input = connection.getInputStream()) {
                while ((length = input.read(buffer)) != -1) {
                    if (output.size() + length > BATAS_MEDIA_MEMORI) {
                        throw new IllegalStateException("Ukuran media melebihi 32 MB.");
                    }
                    output.write(buffer, 0, length);
                }
            }
            return output.toByteArray();
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    /**
     * Salinan media ke folder tablet lewat berkas .part lalu diganti nama,
     * supaya unduhan setengah jalan tidak pernah terbaca sebagai salinan utuh.
     */
    static void keBerkas(String url, File folder, String kunci, long cadanganRuang,
            KlienServer.PenyetelKepala kepala) throws Exception {
        File tujuan = new File(folder, kunci);
        File sementara = new File(folder, kunci + ".part");
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setConnectTimeout(8000);
            connection.setReadTimeout(30000);
            kepala.terapkan(connection);
            if (connection.getResponseCode() >= 400) {
                throw new IllegalStateException("Media tidak dapat diunduh.");
            }
            long panjang = connection.getContentLengthLong();
            if (panjang > 0 && folder.getUsableSpace() < panjang + cadanganRuang) {
                throw new IllegalStateException("Ruang penyimpanan tablet tidak cukup.");
            }
            try (InputStream input = connection.getInputStream();
                 OutputStream output = new FileOutputStream(sementara)) {
                byte[] buffer = new byte[64 * 1024];
                int length;
                while ((length = input.read(buffer)) != -1) {
                    output.write(buffer, 0, length);
                }
            }
            if (panjang > 0 && sementara.length() != panjang) {
                throw new IllegalStateException("Unduhan media terputus.");
            }
            if (!sementara.renameTo(tujuan)) {
                throw new IllegalStateException("Salinan media tidak dapat disimpan.");
            }
        } finally {
            if (connection != null) connection.disconnect();
            if (sementara.exists()) {
                //noinspection ResultOfMethodCallIgnored
                sementara.delete();
            }
        }
    }

    /** Klip paket suara kecil, cukup di memori; panjang harus cocok. */
    static byte[] byteKecil(String url, KlienServer.PenyetelKepala kepala) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        try {
            connection.setConnectTimeout(8000);
            connection.setReadTimeout(15000);
            kepala.terapkan(connection);
            if (connection.getResponseCode() != 200) {
                throw new IllegalStateException("Paket suara tidak dapat diunduh.");
            }
            long panjang = connection.getContentLengthLong();
            ByteArrayOutputStream isi = new ByteArrayOutputStream();
            try (InputStream input = connection.getInputStream()) {
                byte[] buffer = new byte[16 * 1024];
                int length;
                while ((length = input.read(buffer)) != -1) isi.write(buffer, 0, length);
            }
            if (panjang >= 0 && isi.size() != panjang) {
                throw new IllegalStateException("Unduhan paket suara terputus.");
            }
            return isi.toByteArray();
        } finally {
            connection.disconnect();
        }
    }
}
