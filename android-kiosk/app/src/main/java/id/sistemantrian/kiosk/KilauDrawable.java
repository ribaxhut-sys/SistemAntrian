package id.sistemantrian.kiosk;

import android.graphics.Color;

/** Pita cahaya miring yang menyapu sebuah pil dari kiri ke kanan. */
final class KilauDrawable extends android.graphics.drawable.Drawable {
    private final android.graphics.Paint cat =
            new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
    private final android.graphics.Path tepi = new android.graphics.Path();
    private final float radius;
    private int warna = Color.WHITE;
    /** 0..1 sepanjang sapuan; negatif berarti tidak tampil. */
    private float posisi = -1f;

    KilauDrawable(float radius) {
        this.radius = radius;
    }

    void aturWarna(int baru) {
        warna = baru;
        invalidateSelf();
    }

    void aturPosisi(float baru) {
        posisi = baru;
        invalidateSelf();
    }

    @Override
    public void draw(android.graphics.Canvas kanvas) {
        android.graphics.Rect b = getBounds();
        if (posisi < 0f || b.isEmpty()) return;
        float pita = Math.max(b.height() * 1.6f, b.width() * 0.22f);
        float tengah = b.left - pita + (b.width() + pita * 2f) * posisi;
        int bening = warna & 0x00FFFFFF;
        int puncak = bening | 0xB4000000;
        cat.setShader(new android.graphics.LinearGradient(
                tengah - pita / 2f, b.top, tengah + pita / 2f, b.bottom,
                new int[]{bening, puncak, bening}, null,
                android.graphics.Shader.TileMode.CLAMP));
        tepi.reset();
        tepi.addRoundRect(new android.graphics.RectF(b), radius, radius,
                android.graphics.Path.Direction.CW);
        kanvas.save();
        kanvas.clipPath(tepi);
        kanvas.drawRect(b, cat);
        kanvas.restore();
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
