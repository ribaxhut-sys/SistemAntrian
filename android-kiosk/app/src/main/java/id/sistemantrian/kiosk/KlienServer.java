package id.sistemantrian.kiosk;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

import org.json.JSONException;
import org.json.JSONObject;
import org.json.JSONTokener;

/**
 * Satu permintaan JSON ke server anjungan, dikerjakan di utas pemanggil
 * (blokir). Pemanggil yang memilih utas dan mengembalikan hasil ke UI.
 * Galat 4xx dilempar sebagai {@link PenolakanServer}; galat lain sebagai
 * IllegalStateException berisi pesan yang layak ditampilkan.
 */
final class KlienServer {
    /** Pasang kepala (token, identitas perangkat) pada sambungan. */
    interface PenyetelKepala {
        void terapkan(HttpURLConnection sambungan);
    }

    private KlienServer() { }

    /** Mengembalikan {"data": <jawaban>}. */
    static JSONObject panggil(String base, String method, String path, JSONObject body,
            PenyetelKepala kepala) throws Exception {
        if (!AlamatServer.aman(base)) {
            throw new IllegalStateException(AlamatServer.PESAN_DITOLAK);
        }
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(base + path).openConnection();
            connection.setRequestMethod(method);
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(8000);
            kepala.terapkan(connection);
            connection.setRequestProperty("Accept", "application/json");
            if (body != null) {
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                connection.getOutputStream().write(
                        body.toString().getBytes(StandardCharsets.UTF_8));
            }
            int code = connection.getResponseCode();
            InputStream stream = code < 400
                    ? connection.getInputStream() : connection.getErrorStream();
            // Jawaban galat tanpa isi membuat getErrorStream() null.
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            if (stream != null) {
                byte[] buffer = new byte[4096];
                int length;
                while ((length = stream.read(buffer)) != -1) output.write(buffer, 0, length);
                stream.close();
            }
            String teks = new String(output.toByteArray(), StandardCharsets.UTF_8).trim();
            Object response = null;
            try {
                response = teks.isEmpty() ? null : new JSONTokener(teks).nextValue();
            } catch (JSONException e) {
                if (code < 400) throw e;
            }
            if (code >= 400) {
                String detail = response instanceof JSONObject
                        ? ((JSONObject) response).optString("detail", "")
                        : "";
                if (detail.trim().isEmpty()) {
                    detail = "Server menolak permintaan (HTTP " + code + ").";
                }
                if (code < 500) throw new PenolakanServer(code, detail);
                throw new IllegalStateException(detail);
            }
            return new JSONObject().put("data", response);
        } finally {
            if (connection != null) connection.disconnect();
        }
    }
}
