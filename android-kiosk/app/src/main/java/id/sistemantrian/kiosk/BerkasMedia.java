package id.sistemantrian.kiosk;

import android.graphics.Bitmap;

import java.io.File;
import java.io.FileInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.Locale;

/** Pembantu murni untuk berkas media: jenis, nama aman, ukuran, durasi. */
final class BerkasMedia {
    private BerkasMedia() { }

    static final String[] EKSTENSI_VIDEO = {".mp4", ".mkv", ".webm", ".avi"};

    static final String[] EKSTENSI_MEDIA = {
            ".mp4", ".mkv", ".webm", ".avi",
            ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"};

    static boolean berakhiran(String filename, String[] ekstensi) {
        String lower = filename.toLowerCase(Locale.ROOT);
        for (String item : ekstensi) {
            if (lower.endsWith(item)) return true;
        }
        return false;
    }

    static boolean isVideo(String filename) {
        return berakhiran(filename, EKSTENSI_VIDEO);
    }

    /** Nama berkas tanpa pemisah folder, untuk dipakai di folder tablet. */
    static String namaAman(String filename) {
        String nama = filename.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        return nama.isEmpty() || nama.startsWith(".") ? "_" + nama : nama;
    }

    static byte[] bacaBerkas(File berkas) throws Exception {
        if (berkas.length() > 32L * 1024 * 1024) {
            throw new IllegalStateException("Ukuran media melebihi 32 MB.");
        }
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int length;
        try (InputStream input = new FileInputStream(berkas)) {
            while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
        }
        return output.toByteArray();
    }

    static void hapusPohon(File berkas) {
        File[] anak = berkas.listFiles();
        if (anak != null) for (File item : anak) hapusPohon(item);
        //noinspection ResultOfMethodCallIgnored
        berkas.delete();
    }

    static Bitmap perkecilThumbnail(Bitmap asli) {
        if (asli.getWidth() <= 0) return asli;
        int lebar = 144;
        int tinggi = Math.max(1, Math.round(asli.getHeight() * (lebar / (float) asli.getWidth())));
        Bitmap kecil = Bitmap.createScaledBitmap(asli, lebar, tinggi, true);
        if (kecil != asli) asli.recycle();
        return kecil;
    }

    static String formatUkuran(long byteJumlah) {
        if (byteJumlah >= 1073741824L) {
            return String.format(Locale.ROOT, "%.1f GB", byteJumlah / 1073741824.0);
        }
        return String.format(Locale.ROOT, "%.1f MB", byteJumlah / 1048576.0);
    }

    static String formatDurasi(long milidetik) {
        long detik = Math.max(0L, Math.round(milidetik / 1000.0));
        return String.format(Locale.ROOT, "%d:%02d", detik / 60, detik % 60);
    }
}
