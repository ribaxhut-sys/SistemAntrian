package id.sistemantrian.kiosk;

import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.os.Build;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Mengunduh APK anjungan dari server dan menyerahkannya ke PackageInstaller.
 * Berjalan di utas pemanggil (blokir). Bila gagal, sesi pemasangan
 * dibatalkan dan galatnya dilempar; pemanggil yang mengurus tampilan.
 */
final class PemasangPembaruan {
    /** Kemajuan unduhan; total 0 bila server tidak memberi panjang. */
    interface Kemajuan {
        void maju(long selesai, long total);
    }

    private PemasangPembaruan() { }

    static void unduhDanPasang(Context konteks, String base,
            KlienServer.PenyetelKepala kepala, String aksiStatus, Kemajuan kemajuan)
            throws Exception {
        HttpURLConnection connection = null;
        PackageInstaller.Session session = null;
        try {
            connection = (HttpURLConnection) new URL(base + "/v1/kiosk/app/apk").openConnection();
            connection.setConnectTimeout(5000);
            connection.setReadTimeout(30000);
            kepala.terapkan(connection);
            int code = connection.getResponseCode();
            if (code != 200) throw new IllegalStateException("server menjawab " + code);
            long total = connection.getContentLengthLong();

            PackageInstaller installer = konteks.getPackageManager().getPackageInstaller();
            PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                    PackageInstaller.SessionParams.MODE_FULL_INSTALL);
            params.setAppPackageName(konteks.getPackageName());
            if (total > 0) params.setSize(total);
            int sessionId = installer.createSession(params);
            session = installer.openSession(sessionId);
            try (InputStream input = connection.getInputStream();
                 OutputStream output = session.openWrite("anjungan.apk", 0, total)) {
                byte[] buffer = new byte[64 * 1024];
                long done = 0;
                long lastPost = 0;
                int length;
                while ((length = input.read(buffer)) != -1) {
                    output.write(buffer, 0, length);
                    done += length;
                    long now = System.currentTimeMillis();
                    if (now - lastPost > 200) {
                        lastPost = now;
                        kemajuan.maju(done, total);
                    }
                }
                session.fsync(output);
            }
            Intent status = new Intent(aksiStatus).setPackage(konteks.getPackageName());
            int flags = PendingIntent.FLAG_UPDATE_CURRENT
                    | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
            PendingIntent pending = PendingIntent.getBroadcast(
                    konteks, sessionId, status, flags);
            session.commit(pending.getIntentSender());
            session.close();
            session = null;
        } catch (Exception e) {
            if (session != null) session.abandon();
            throw e;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }
}
