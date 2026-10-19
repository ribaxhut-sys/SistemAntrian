package id.sistemantrian.kiosk;

import android.graphics.Color;
import android.graphics.Typeface;

/** Latar sambutan tema merah putih: pita merah berisi ucapan, lalu putih. */
final class LatarBendera extends android.graphics.drawable.Drawable {
    private final android.graphics.Paint merah =
            new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
    private final android.graphics.Paint putih =
            new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
    private final android.graphics.Paint tulisan =
            new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
    private final float radius;
    private final String ucapan;

    LatarBendera(float radius, String ucapan) {
        this.radius = radius;
        this.ucapan = ucapan;
        merah.setColor(Color.rgb(200, 16, 46));
        putih.setColor(Color.WHITE);
        tulisan.setColor(Color.WHITE);
        tulisan.setTextAlign(android.graphics.Paint.Align.CENTER);
        tulisan.setTypeface(Typeface.create("sans-serif-black", Typeface.NORMAL));
    }

    @Override
    public void draw(android.graphics.Canvas canvas) {
        android.graphics.Rect b = getBounds();
        if (b.isEmpty()) return;
        android.graphics.Path bentuk = new android.graphics.Path();
        bentuk.addRoundRect(new android.graphics.RectF(b), radius, radius,
                android.graphics.Path.Direction.CW);
        canvas.save();
        canvas.clipPath(bentuk);
        float batas = b.top + b.height() * 0.42f;
        canvas.drawRect(b.left, b.top, b.right, batas, merah);
        canvas.drawRect(b.left, batas, b.right, b.bottom, putih);
        float tinggiPita = batas - b.top;
        tulisan.setTextSize(Math.min(tinggiPita * 0.34f,
                b.width() * 0.92f / Math.max(1, ucapan.length()) * 1.9f));
        float y = b.top + tinggiPita / 2f - (tulisan.descent() + tulisan.ascent()) / 2f;
        canvas.drawText(ucapan, b.exactCenterX(), y, tulisan);
        canvas.restore();
    }

    @Override
    public void setAlpha(int alpha) {
    }

    @Override
    public void setColorFilter(android.graphics.ColorFilter filter) {
    }

    @Override
    public int getOpacity() {
        return android.graphics.PixelFormat.TRANSLUCENT;
    }
}
