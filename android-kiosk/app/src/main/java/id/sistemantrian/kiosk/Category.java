package id.sistemantrian.kiosk;

import org.json.JSONObject;

/** Satu jenis layanan (atau kelompok layanan) pada daftar layanan anjungan. */
final class Category {
    final int id;
    final String name;
    final String prefix;
    final String info;
    final Integer parentId;
    final boolean group;

    Category(JSONObject json) {
        id = json.optInt("id");
        name = json.optString("name");
        prefix = json.optString("prefix");
        info = json.optString("info");
        parentId = json.isNull("parent_id") ? null : json.optInt("parent_id");
        group = json.optBoolean("is_group");
    }
}
