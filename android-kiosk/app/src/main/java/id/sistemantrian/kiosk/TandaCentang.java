package id.sistemantrian.kiosk;

import android.content.Context;
import android.graphics.Color;
import android.view.View;

/** Lingkaran hijau yang membesar, lalu centang putih yang tergambar. */
final class TandaCentang extends View {
    private final android.graphics.Paint lingkaran =
            new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
    private final android.graphics.Paint garis =
            new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
    private final android.graphics.Path centang = new android.graphics.Path();
    private final android.graphics.Path potongan = new android.graphics.Path();
    private android.graphics.PathMeasure ukur;
    private float kemajuan;

    TandaCentang(Context context, int warna) {
        super(context);
        lingkaran.setColor(warna);
        garis.setColor(Color.WHITE);
        garis.setStyle(android.graphics.Paint.Style.STROKE);
        garis.setStrokeCap(android.graphics.Paint.Cap.ROUND);
        garis.setStrokeJoin(android.graphics.Paint.Join.ROUND);
    }

    void gambar(long tunda) {
        android.animation.ValueAnimator animasi =
                android.animation.ValueAnimator.ofFloat(0f, 1f);
        animasi.setDuration(600);
        animasi.setStartDelay(tunda);
        animasi.setInterpolator(new android.view.animation.DecelerateInterpolator());
        animasi.addUpdateListener(a -> {
            kemajuan = (float) a.getAnimatedValue();
            invalidate();
        });
        animasi.start();
    }

    @Override
    protected void onSizeChanged(int lebar, int tinggi, int lebarLama, int tinggiLama) {
        centang.reset();
        centang.moveTo(lebar * 0.28f, tinggi * 0.52f);
        centang.lineTo(lebar * 0.44f, tinggi * 0.67f);
        centang.lineTo(lebar * 0.73f, tinggi * 0.36f);
        ukur = new android.graphics.PathMeasure(centang, false);
        garis.setStrokeWidth(Math.max(2f, lebar * 0.11f));
    }

    @Override
    protected void onDraw(android.graphics.Canvas canvas) {
        float jari = Math.min(getWidth(), getHeight()) / 2f
                * Math.min(1f, kemajuan * 2.2f);
        canvas.drawCircle(getWidth() / 2f, getHeight() / 2f, jari, lingkaran);
        if (ukur == null) return;
        float bagian = Math.max(0f, (kemajuan - 0.4f) / 0.6f);
        potongan.reset();
        ukur.getSegment(0f, ukur.getLength() * bagian, potongan, true);
        canvas.drawPath(potongan, garis);
    }
}
