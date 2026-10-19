package id.sistemantrian.kiosk;

import android.content.Context;
import android.view.View;

/** Panah tebal (› atau ‹) untuk kartu kelompok dan Kembali. */
final class TandaPanah extends View {
    private final android.graphics.Paint cat =
            new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
    private final android.graphics.Path jalur = new android.graphics.Path();
    private final boolean kanan;

    TandaPanah(Context context, boolean kanan, int warna) {
        super(context);
        this.kanan = kanan;
        cat.setColor(warna);
        cat.setStyle(android.graphics.Paint.Style.STROKE);
        cat.setStrokeCap(android.graphics.Paint.Cap.ROUND);
        cat.setStrokeJoin(android.graphics.Paint.Join.ROUND);
    }

    @Override
    protected void onDraw(android.graphics.Canvas canvas) {
        float w = getWidth();
        float h = getHeight();
        cat.setStrokeWidth(Math.max(3f, w * 0.15f));
        float dekat = kanan ? 0.36f : 0.64f;
        float jauh = kanan ? 0.66f : 0.34f;
        jalur.reset();
        jalur.moveTo(w * dekat, h * 0.2f);
        jalur.lineTo(w * jauh, h * 0.5f);
        jalur.lineTo(w * dekat, h * 0.8f);
        canvas.drawPath(jalur, cat);
    }
}
