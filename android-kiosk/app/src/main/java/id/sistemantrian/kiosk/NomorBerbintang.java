package id.sistemantrian.kiosk;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Paint;
import android.widget.TextView;

/**
 * Nomor prioritas pada daftar menunggu: bintang kecil di pojok kiri atas
 * ubin, digambar terpisah supaya teks nomornya tetap polos.
 */
final class NomorBerbintang extends TextView {
    private final Paint bintang = new Paint(Paint.ANTI_ALIAS_FLAG);

    NomorBerbintang(Context context) {
        super(context);
        bintang.setColor(Color.rgb(126, 34, 206));
    }

    @Override
    protected void onDraw(android.graphics.Canvas canvas) {
        super.onDraw(canvas);
        float kepadatan = getResources().getDisplayMetrics().density;
        float besar = Math.max(getTextSize() * 0.55f, 9 * kepadatan);
        bintang.setTextSize(besar);
        canvas.drawText("★", 5 * kepadatan, besar + 2 * kepadatan, bintang);
    }
}
