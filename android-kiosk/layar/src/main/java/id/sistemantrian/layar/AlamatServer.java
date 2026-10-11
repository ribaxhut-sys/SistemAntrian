package id.sistemantrian.layar;

import java.net.URI;
import java.util.Locale;

/**
 * Penjaga alamat server sebelum token dikirim.
 *
 * API anjungan berjalan di jaringan kantor dengan HTTP biasa, karena
 * sertifikat HTTPS belum tersedia di sana; karena itu cleartext tetap
 * diizinkan di manifest. Yang dicegah di sini adalah token terkirim tanpa
 * enkripsi ke alamat DI LUAR jaringan lokal (salah ketik, atau alamat
 * internet): untuk itu https:// wajib.
 *
 * network_security_config tidak dapat dipakai untuk aturan ini karena
 * hanya mengenal nama domain, bukan rentang alamat IP. Pemeriksaannya murni
 * membaca teks alamat, tanpa DNS, sehingga aman dipanggil dari utas mana pun.
 *
 * Salinan yang sama ada di modul anjungan (id.sistemantrian.kiosk); ubah
 * keduanya bersamaan.
 */
final class AlamatServer {
    static final String PESAN_DITOLAK =
            "Alamat http:// hanya untuk server di jaringan lokal "
                    + "(mis. http://192.168.1.10:8765). Untuk alamat lain gunakan https://.";

    private AlamatServer() {
    }

    /** Benar bila token boleh dikirim ke alamat ini. */
    static boolean aman(String url) {
        if (url == null) return false;
        URI uri;
        try {
            uri = new URI(url.trim());
        } catch (Exception e) {
            return false;
        }
        String skema = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (skema.equals("https")) return true;
        if (!skema.equals("http")) return false;
        String host = uri.getHost();
        if (host == null) {
            // URI menolak nama komputer bergaris bawah; ambil dari authority.
            String authority = uri.getRawAuthority();
            if (authority == null) return false;
            authority = authority.substring(authority.lastIndexOf('@') + 1);
            int titikDua = authority.lastIndexOf(':');
            host = titikDua > 0 && !authority.endsWith("]")
                    ? authority.substring(0, titikDua) : authority;
        }
        return hostLokal(host);
    }

    static boolean hostLokal(String host) {
        if (host == null || host.isEmpty()) return false;
        String h = host.toLowerCase(Locale.ROOT);
        if (h.startsWith("[") && h.endsWith("]")) h = h.substring(1, h.length() - 1);
        if (h.equals("localhost") || h.endsWith(".local") || h.endsWith(".lan")
                || h.endsWith(".home.arpa") || h.endsWith(".localdomain")) {
            return true;
        }
        if (h.contains(":")) {
            // IPv6: loopback, link-local fe80::/10, unique local fc00::/7.
            return h.equals("::1") || h.startsWith("fe8") || h.startsWith("fe9")
                    || h.startsWith("fea") || h.startsWith("feb")
                    || h.startsWith("fc") || h.startsWith("fd");
        }
        int[] ip = ipv4(h);
        // Nama komputer tanpa titik (mis. "server-antrian") hanya dikenal di LAN.
        if (ip == null) return !h.contains(".");
        return ip[0] == 10
                || ip[0] == 127
                || (ip[0] == 172 && ip[1] >= 16 && ip[1] <= 31)
                || (ip[0] == 192 && ip[1] == 168)
                || (ip[0] == 169 && ip[1] == 254);
    }

    private static int[] ipv4(String h) {
        String[] bagian = h.split("\\.", -1);
        if (bagian.length != 4) return null;
        int[] hasil = new int[4];
        for (int i = 0; i < 4; i++) {
            if (bagian[i].isEmpty() || bagian[i].length() > 3) return null;
            for (int j = 0; j < bagian[i].length(); j++) {
                if (!Character.isDigit(bagian[i].charAt(j))) return null;
            }
            hasil[i] = Integer.parseInt(bagian[i]);
            if (hasil[i] > 255) return null;
        }
        return hasil;
    }
}
