package id.sistemantrian.kiosk;

import android.graphics.Color;

/**
 * Hitungan warna murni, tanpa keadaan Activity. MainActivity memakainya lewat
 * import statis, sehingga pemanggilnya tidak berubah.
 */
final class BantuWarna {
    private BantuWarna() { }

    /** Luminans relatif WCAG 0..1 (sama dengan app/services/warna_iklan.py). */
    static double luminansWarna(int warna) {
        double[] c = {Color.red(warna) / 255.0, Color.green(warna) / 255.0,
                Color.blue(warna) / 255.0};
        for (int i = 0; i < 3; i++) {
            c[i] = c[i] <= 0.03928 ? c[i] / 12.92 : Math.pow((c[i] + 0.055) / 1.055, 2.4);
        }
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    }

    /** Campuran dua warna; `porsi` 0 = warna pertama, 1 = warna kedua. */
    static int campur(int satu, int dua, float porsi) {
        return Color.rgb(
                Math.round(Color.red(satu) + (Color.red(dua) - Color.red(satu)) * porsi),
                Math.round(Color.green(satu) + (Color.green(dua) - Color.green(satu)) * porsi),
                Math.round(Color.blue(satu) + (Color.blue(dua) - Color.blue(satu)) * porsi));
    }

    static int darker(int color) {
        return Color.rgb(
                Math.max(0, (int) (Color.red(color) * 0.82)),
                Math.max(0, (int) (Color.green(color) * 0.82)),
                Math.max(0, (int) (Color.blue(color) * 0.82)));
    }
}
