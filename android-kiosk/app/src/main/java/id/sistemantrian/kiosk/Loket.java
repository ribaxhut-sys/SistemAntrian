package id.sistemantrian.kiosk;

import org.json.JSONObject;

/** Satu loket pada jawaban `/v1/kiosk/display`. */
final class Loket {
    final String nama;
    final String nomor;
    final String layanan;
    final String status;
    /** Bertambah tiap panggilan dan panggilan ulang. */
    final int panggilan;

    Loket(JSONObject json) {
        nama = json.optString("name", "");
        nomor = json.isNull("queue_number") ? "" : json.optString("queue_number", "");
        layanan = json.isNull("category") ? "" : json.optString("category", "");
        status = json.optString("status", "KOSONG");
        panggilan = json.optInt("call_count", 0);
    }

    String tanda() {
        return nama + "=" + nomor + "/" + layanan + "/" + status;
    }
}
