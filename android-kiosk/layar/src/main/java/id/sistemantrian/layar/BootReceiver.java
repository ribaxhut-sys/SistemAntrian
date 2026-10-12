package id.sistemantrian.layar;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Buka layar antrian sesudah TV dinyalakan.
 *
 * Banyak TV box mengizinkannya; Android 10+ di ponsel biasa tidak. Bila
 * tidak terbuka sendiri, jadikan aplikasi ini aplikasi awal di setelan
 * TV box (lihat docs/android-kiosk.md).
 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) return;
        Intent open = new Intent(context, MainActivity.class);
        open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            context.startActivity(open);
        } catch (Exception ignored) {
            // Sistem menolak membuka dari latar; ditangani lewat setelan TV box.
        }
    }
}
