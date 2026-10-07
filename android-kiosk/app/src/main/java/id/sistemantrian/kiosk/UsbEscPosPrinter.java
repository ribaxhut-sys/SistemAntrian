package id.sistemantrian.kiosk;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.hardware.usb.UsbConstants;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbEndpoint;
import android.hardware.usb.UsbInterface;
import android.hardware.usb.UsbManager;
import android.os.Build;

import java.io.ByteArrayOutputStream;
import java.nio.charset.Charset;
import java.util.List;
import java.util.function.Consumer;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

final class UsbEscPosPrinter {
    private static final String ACTION_USB_PERMISSION = "id.sistemantrian.kiosk.USB_PERMISSION";
    private static final float DOTS_PER_MM = 8f;
    private static final float DOTS_PER_POINT = DOTS_PER_MM * 25.4f / 72f;

    private UsbEscPosPrinter() {}

    static String detect(Activity activity) {
        UsbManager manager = (UsbManager) activity.getSystemService(Context.USB_SERVICE);
        UsbDevice device = findPrinter(manager);
        if (device == null) {
            return manager.getDeviceList().isEmpty()
                    ? "Printer belum terdeteksi. Sambungkan printer yang menyala dengan kabel USB OTG, lalu deteksi lagi. Android tidak memerlukan pemasangan driver terpisah."
                    : "Perangkat USB terpasang, tetapi printer ESC/POS kompatibel tidak ditemukan. Periksa dukungan OTG dan kabel printer.";
        }
        String name = device.getProductName();
        if (name == null || name.trim().isEmpty()) {
            name = "Perangkat USB " + device.getDeviceName();
        }
        return "Printer terdeteksi: " + name + ". Akan dipilih otomatis saat mencetak.";
    }

    static void print(Activity activity, String number, List<String> lines, Consumer<String> done) {
        print(activity, number, lines, null, false, done);
    }

    static void print(
            Activity activity, String number, List<String> lines,
            JSONObject layout, Consumer<String> done) {
        print(activity, number, lines, layout, false, done);
    }

    static void printTest(Activity activity, Consumer<String> done) {
        List<String> lines = List.of(
                "CONTOH TIKET",
                "UJI CETAK - TIDAK MENERBITKAN NOMOR",
                "",
                "ANTRIAN PELAYANAN",
                "UJI-001",
                "Layanan: Contoh",
                "",
                "Periksa hasil cetak dan potongan kertas."
        );
        print(activity, "UJI-001", lines, null, true, done);
    }

    private static void print(
            Activity activity, String number, List<String> lines,
            JSONObject layout, boolean test, Consumer<String> done) {
        UsbManager manager = (UsbManager) activity.getSystemService(Context.USB_SERVICE);
        UsbDevice device = findPrinter(manager);
        if (device == null) {
            done.accept(test
                    ? "Printer USB tidak ditemukan. Pastikan kabel OTG terpasang."
                    : "Nomor " + number + " terbit, tetapi printer USB tidak ditemukan.");
            return;
        }
        if (manager.hasPermission(device)) {
            printGranted(manager, device, activity, number, lines, layout, test, done);
            return;
        }

        IntentFilter filter = new IntentFilter(ACTION_USB_PERMISSION);
        BroadcastReceiver receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                try {
                    if (Build.VERSION.SDK_INT >= 33) activity.unregisterReceiver(this);
                    else activity.unregisterReceiver(this);
                } catch (IllegalArgumentException ignored) {
                    // The activity may have closed while Android was asking for USB permission.
                }
                boolean granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false);
                UsbDevice grantedDevice = intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);
                if (granted && grantedDevice != null) {
                    printGranted(
                            manager, grantedDevice, activity, number, lines,
                            layout, test, done);
                } else {
                    done.accept(test
                            ? "Izin akses printer USB ditolak."
                            : "Nomor " + number + " terbit, izin printer USB ditolak.");
                }
            }
        };
        if (Build.VERSION.SDK_INT >= 33) activity.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED);
        else activity.registerReceiver(receiver, filter);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 31) flags |= PendingIntent.FLAG_MUTABLE;
        PendingIntent permissionIntent = PendingIntent.getBroadcast(
                activity, device.getDeviceId(), new Intent(ACTION_USB_PERMISSION).setPackage(activity.getPackageName()), flags);
        manager.requestPermission(device, permissionIntent);
    }

    private static UsbDevice findPrinter(UsbManager manager) {
        UsbDevice fallback = null;
        for (UsbDevice device : manager.getDeviceList().values()) {
            for (int i = 0; i < device.getInterfaceCount(); i++) {
                UsbInterface usbInterface = device.getInterface(i);
                if (bulkOut(usbInterface) == null || usbInterface.getInterfaceClass() == UsbConstants.USB_CLASS_HID) {
                    continue;
                }
                if (usbInterface.getInterfaceClass() == 7) return device;
                if (fallback == null) fallback = device;
            }
        }
        return fallback;
    }

    private static UsbInterface printerInterface(UsbDevice device) {
        UsbInterface fallback = null;
        for (int i = 0; i < device.getInterfaceCount(); i++) {
            UsbInterface usbInterface = device.getInterface(i);
            if (bulkOut(usbInterface) == null || usbInterface.getInterfaceClass() == UsbConstants.USB_CLASS_HID) {
                continue;
            }
            if (usbInterface.getInterfaceClass() == 7) return usbInterface;
            if (fallback == null) fallback = usbInterface;
        }
        return fallback;
    }

    private static UsbEndpoint bulkOut(UsbInterface usbInterface) {
        for (int i = 0; i < usbInterface.getEndpointCount(); i++) {
            UsbEndpoint endpoint = usbInterface.getEndpoint(i);
            if (endpoint.getDirection() == UsbConstants.USB_DIR_OUT
                    && endpoint.getType() == UsbConstants.USB_ENDPOINT_XFER_BULK) return endpoint;
        }
        return null;
    }

    private static void printGranted(
            UsbManager manager, UsbDevice device, Activity activity,
            String number, List<String> lines, JSONObject layout,
            boolean test, Consumer<String> done) {
        new Thread(() -> {
            String message;
            UsbDeviceConnection connection = manager.openDevice(device);
            if (connection == null) {
                message = test
                        ? "Printer USB terdeteksi, tetapi tidak dapat dibuka."
                        : "Nomor " + number + " terbit, tetapi printer USB tidak dapat dibuka.";
            } else {
                UsbInterface usbInterface = printerInterface(device);
                UsbEndpoint output = usbInterface == null ? null : bulkOut(usbInterface);
                boolean claimed = usbInterface != null && connection.claimInterface(usbInterface, true);
                if (output == null || !claimed) {
                    message = test
                            ? "Printer USB tidak mendukung antarmuka cetak yang diperlukan."
                            : "Nomor " + number + " terbit, tetapi antarmuka printer USB tidak didukung.";
                } else {
                    try {
                        byte[] receipt = layout == null
                                ? format(number, lines) : format(layout);
                        boolean sent = true;
                        for (int offset = 0; offset < receipt.length; offset += 2048) {
                            int length = Math.min(2048, receipt.length - offset);
                            int written = connection.bulkTransfer(output, receipt, offset, length, 5000);
                            if (written != length) {
                                sent = false;
                                break;
                            }
                        }
                        message = sent
                                ? (test ? "Contoh tiket berhasil dicetak."
                                        : "Tiket " + number + " tercetak.")
                                : (test ? "Pengiriman contoh tiket ke printer gagal."
                                        : "Nomor " + number + " terbit, tetapi pengiriman ke printer gagal.");
                    } catch (RuntimeException error) {
                        message = test
                                ? "Format contoh cetak tidak didukung printer."
                                : "Nomor " + number + " terbit, tetapi format cetak tidak didukung.";
                    } catch (JSONException error) {
                        message = test
                                ? "Tata letak contoh cetak tidak valid."
                                : "Nomor " + number + " terbit, tetapi tata letak cetak tidak valid.";
                    }
                    connection.releaseInterface(usbInterface);
                }
                connection.close();
            }
            String outcome = message;
            activity.runOnUiThread(() -> done.accept(outcome));
        }).start();
    }

    private static byte[] format(String number, List<String> lines) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.write(0x1b); output.write('@');
        Charset charset = Charset.forName("IBM437");
        for (String line : lines) {
            if (line.isEmpty()) {
                output.write('\n');
                continue;
            }
            boolean isNumber = line.equals(number);
            output.write(0x1b); output.write('a'); output.write(isNumber ? 1 : 0);
            output.write(0x1b); output.write('E'); output.write(isNumber ? 1 : 0);
            output.write(0x1d); output.write('!'); output.write(isNumber ? 0x11 : 0);
            byte[] text = line.getBytes(charset);
            output.write(text, 0, text.length);
            output.write('\n');
        }
        output.write(0x1b); output.write('a'); output.write(0);
        output.write(0x1b); output.write('E'); output.write(0);
        output.write(0x1d); output.write('!'); output.write(0);
        output.write('\n'); output.write('\n'); output.write('\n');
        output.write(0x1d); output.write('V'); output.write(1);
        return output.toByteArray();
    }

    private static byte[] format(JSONObject layout) throws JSONException {
        int width = (int) Math.round(layout.getDouble("width_mm") * DOTS_PER_MM);
        int height = (int) Math.round(layout.getDouble("height_mm") * DOTS_PER_MM);
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        canvas.drawColor(Color.WHITE);

        JSONArray rows = layout.getJSONArray("rows");
        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        paint.setColor(Color.BLACK);
        paint.setTextAlign(Paint.Align.CENTER);
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.getJSONObject(i);
            float y = (float) row.getDouble("y_mm") * DOTS_PER_MM;
            if (row.optBoolean("line")) {
                paint.setStrokeWidth(Math.max(1f, 0.35f * DOTS_PER_MM));
                canvas.drawLine(
                        3f * DOTS_PER_MM, y,
                        width - 3f * DOTS_PER_MM, y, paint);
                continue;
            }
            boolean bold = row.optBoolean("bold");
            paint.setTypeface(Typeface.create(
                    "sans-serif", bold ? Typeface.BOLD : Typeface.NORMAL));
            paint.setTextSize((float) row.getDouble("size") * DOTS_PER_POINT);
            canvas.drawText(row.getString("text"), width / 2f, y, paint);
        }

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.write(0x1b);
        output.write('@');
        int rowBytes = (width + 7) / 8;
        output.write(0x1d);
        output.write('v');
        output.write('0');
        output.write(0);
        output.write(rowBytes & 0xff);
        output.write((rowBytes >> 8) & 0xff);
        output.write(height & 0xff);
        output.write((height >> 8) & 0xff);
        for (int y = 0; y < height; y++) {
            for (int byteIndex = 0; byteIndex < rowBytes; byteIndex++) {
                int packed = 0;
                for (int bit = 0; bit < 8; bit++) {
                    int x = byteIndex * 8 + bit;
                    if (x < width && isBlack(bitmap.getPixel(x, y))) {
                        packed |= 0x80 >> bit;
                    }
                }
                output.write(packed);
            }
        }
        bitmap.recycle();
        output.write('\n');
        output.write('\n');
        output.write('\n');
        output.write(0x1d);
        output.write('V');
        output.write(1);
        return output.toByteArray();
    }

    private static boolean isBlack(int color) {
        int luminance = (Color.red(color) * 299
                + Color.green(color) * 587
                + Color.blue(color) * 114) / 1000;
        return luminance < 160;
    }
}
