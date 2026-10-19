package id.sistemantrian.kiosk;

import android.graphics.Color;

final class Tema {
    final int latar, kartu, garis, ink, muted, utama, lembut, emas, abu, hasil, teksTombol;
    final int[][] chip;
    final float skala;
    final boolean gelap;

    Tema(int latar, int kartu, int garis, int ink, int muted, int utama, int lembut,
         int emas, int abu, int hasil, int teksTombol, int[][] chip, float skala,
         boolean gelap) {
        this.latar = latar;
        this.kartu = kartu;
        this.garis = garis;
        this.ink = ink;
        this.muted = muted;
        this.utama = utama;
        this.lembut = lembut;
        this.emas = emas;
        this.abu = abu;
        this.hasil = hasil;
        this.teksTombol = teksTombol;
        this.chip = chip;
        this.skala = skala;
        this.gelap = gelap;
    }

    static Tema dari(String kode) {
        switch (kode) {
            case "hijau":
                return new Tema(Color.rgb(242, 248, 244), Color.WHITE, Color.rgb(214, 233, 221),
                        Color.rgb(13, 59, 42), Color.rgb(85, 117, 102), Color.rgb(17, 120, 90),
                        Color.rgb(220, 241, 230), Color.rgb(233, 216, 74), Color.rgb(238, 245, 240),
                        Color.rgb(13, 59, 42), Color.WHITE, new int[][]{
                        {Color.rgb(214, 241, 227), Color.rgb(15, 107, 74)},
                        {Color.rgb(232, 245, 201), Color.rgb(77, 122, 15)},
                        {Color.rgb(253, 236, 207), Color.rgb(154, 91, 10)},
                        {Color.rgb(215, 238, 245), Color.rgb(14, 106, 133)}}, 1f, false);
            case "kontras":
                // Hitam-kuning dan huruf 12% lebih besar: keterbacaan dulu.
                return new Tema(Color.WHITE, Color.WHITE, Color.BLACK,
                        Color.BLACK, Color.rgb(31, 31, 31), Color.BLACK,
                        Color.rgb(255, 230, 0), Color.rgb(255, 230, 0), Color.rgb(235, 235, 235),
                        Color.BLACK, Color.rgb(255, 230, 0), new int[][]{
                        {Color.BLACK, Color.rgb(255, 230, 0)}}, 1.12f, false);
            case "gelap":
                return new Tema(Color.rgb(11, 18, 32), Color.rgb(20, 29, 48), Color.rgb(36, 49, 77),
                        Color.rgb(238, 242, 251), Color.rgb(147, 163, 196), Color.rgb(91, 140, 255),
                        Color.rgb(28, 42, 71), Color.rgb(245, 183, 42), Color.rgb(26, 35, 56),
                        Color.rgb(0, 8, 20), Color.WHITE, new int[][]{
                        {Color.rgb(31, 53, 102), Color.rgb(156, 188, 255)},
                        {Color.rgb(23, 63, 51), Color.rgb(127, 224, 178)},
                        {Color.rgb(69, 53, 26), Color.rgb(245, 200, 105)},
                        {Color.rgb(53, 35, 77), Color.rgb(207, 166, 245)}}, 1f, true);
            case "merah_putih":
                return new Tema(Color.rgb(255, 247, 246), Color.WHITE, Color.rgb(243, 214, 211),
                        Color.rgb(92, 11, 11), Color.rgb(138, 90, 87), Color.rgb(200, 16, 46),
                        Color.rgb(253, 228, 225), Color.WHITE, Color.rgb(250, 240, 239),
                        Color.rgb(200, 16, 46), Color.WHITE, new int[][]{
                        {Color.rgb(200, 16, 46), Color.WHITE},
                        {Color.rgb(253, 228, 225), Color.rgb(200, 16, 46)}}, 1f, false);
            default:
                return new Tema(Color.rgb(244, 247, 252), Color.WHITE, Color.rgb(223, 230, 243),
                        Color.rgb(11, 42, 91), Color.rgb(91, 107, 134), Color.rgb(30, 79, 163),
                        Color.rgb(227, 235, 250), Color.rgb(245, 183, 42), Color.rgb(241, 245, 249),
                        Color.rgb(11, 42, 91), Color.WHITE, new int[][]{
                        {Color.rgb(219, 231, 255), Color.rgb(30, 79, 163)},
                        {Color.rgb(220, 245, 232), Color.rgb(15, 122, 74)},
                        {Color.rgb(253, 236, 207), Color.rgb(161, 88, 10)},
                        {Color.rgb(240, 226, 251), Color.rgb(123, 63, 176)},
                        {Color.rgb(207, 244, 244), Color.rgb(14, 116, 120)},
                        {Color.rgb(253, 226, 221), Color.rgb(176, 58, 36)}}, 1f, false);
        }
    }
}
