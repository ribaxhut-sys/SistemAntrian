package id.sistemantrian.kiosk;

import java.util.Locale;

/**
 * Pembantu teks dan penamaan murni, tanpa keadaan Activity. MainActivity
 * memakainya lewat import statis.
 */
final class BantuTeks {
    private BantuTeks() { }

    static String zoneLabel(String zone) {
        if ("Asia/Makassar".equals(zone)) return "WITA";
        if ("Asia/Jayapura".equals(zone)) return "WIT";
        return "WIB";
    }

    static boolean isMediaKind(String kind) {
        return "media".equals(kind) || "gambar".equals(kind) || "video".equals(kind);
    }

    static String awalanLayanan(Category item) {
        if (!item.prefix.isEmpty()) return item.prefix;
        return item.name.isEmpty() ? "•" : item.name.substring(0, 1).toUpperCase(Locale.ROOT);
    }

    static String tempatBerikutnya(String sekarang) {
        if ("keduanya".equals(sekarang)) return "panel";
        return "panel".equals(sekarang) ? "penuh" : "keduanya";
    }

    static String labelTempatLokal(String tempat) {
        if ("panel".equals(tempat)) return "Panel atas";
        return "penuh".equals(tempat) ? "Layar penuh" : "Keduanya";
    }

    static byte[] heks(String teks) {
        byte[] hasil = new byte[teks.length() / 2];
        for (int i = 0; i < hasil.length; i++) {
            hasil[i] = (byte) Integer.parseInt(teks.substring(2 * i, 2 * i + 2), 16);
        }
        return hasil;
    }
}
