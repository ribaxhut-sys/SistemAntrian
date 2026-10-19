package id.sistemantrian.kiosk;

import android.graphics.Color;
import android.view.View;

/** Bidang sentuh pemilih warna: pita hue (bilahHue) atau kejenuhan x kecerahan. */
final class BidangWarnaKilau extends View {
    private final float[] hsv;
    private final boolean bilahHue;
    private final Runnable saatBerubah;
    private final Runnable saatLepas;
    private final android.graphics.Paint cat =
            new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);

    BidangWarnaKilau(android.content.Context konteks, float[] hsv, boolean bilahHue,
            Runnable saatBerubah, Runnable saatLepas) {
        super(konteks);
        this.hsv = hsv;
        this.bilahHue = bilahHue;
        this.saatBerubah = saatBerubah;
        this.saatLepas = saatLepas;
    }

    @Override
    protected void onDraw(android.graphics.Canvas kanvas) {
        int w = getWidth();
        int h = getHeight();
        float tebal = getResources().getDisplayMetrics().density * 3f;
        cat.setStyle(android.graphics.Paint.Style.FILL);
        if (bilahHue) {
            int[] warna = new int[7];
            for (int i = 0; i < warna.length; i++) {
                warna[i] = Color.HSVToColor(new float[]{i * 60f, 1f, 1f});
            }
            cat.setShader(new android.graphics.LinearGradient(0, 0, w, 0, warna, null,
                    android.graphics.Shader.TileMode.CLAMP));
            kanvas.drawRect(0, 0, w, h, cat);
            cat.setShader(null);
            float x = hsv[0] / 360f * w;
            cat.setStyle(android.graphics.Paint.Style.STROKE);
            cat.setStrokeWidth(tebal);
            cat.setColor(Color.WHITE);
            kanvas.drawRect(x - tebal, tebal / 2, x + tebal, h - tebal / 2, cat);
            return;
        }
        cat.setShader(new android.graphics.LinearGradient(0, 0, w, 0, Color.WHITE,
                Color.HSVToColor(new float[]{hsv[0], 1f, 1f}),
                android.graphics.Shader.TileMode.CLAMP));
        kanvas.drawRect(0, 0, w, h, cat);
        cat.setShader(new android.graphics.LinearGradient(0, 0, 0, h, 0x00000000,
                (int) (255 * (1f - MainActivity.NILAI_MINIMUM_KILAU)) << 24,
                android.graphics.Shader.TileMode.CLAMP));
        kanvas.drawRect(0, 0, w, h, cat);
        cat.setShader(null);
        float cx = hsv[1] * w;
        float cy = (1f - hsv[2]) / (1f - MainActivity.NILAI_MINIMUM_KILAU) * h;
        cat.setStyle(android.graphics.Paint.Style.STROKE);
        cat.setStrokeWidth(tebal);
        cat.setColor(Color.BLACK);
        kanvas.drawCircle(cx, cy, tebal * 3.3f, cat);
        cat.setColor(Color.WHITE);
        kanvas.drawCircle(cx, cy, tebal * 3f, cat);
    }

    @Override
    public boolean onTouchEvent(android.view.MotionEvent e) {
        int aksi = e.getActionMasked();
        if (aksi == android.view.MotionEvent.ACTION_DOWN && getParent() != null) {
            getParent().requestDisallowInterceptTouchEvent(true);
        }
        if (aksi == android.view.MotionEvent.ACTION_DOWN
                || aksi == android.view.MotionEvent.ACTION_MOVE) {
            float x = Math.max(0f, Math.min(1f, e.getX() / Math.max(1, getWidth())));
            float y = Math.max(0f, Math.min(1f, e.getY() / Math.max(1, getHeight())));
            if (bilahHue) {
                hsv[0] = Math.min(359.99f, x * 360f);
            } else {
                hsv[1] = x;
                hsv[2] = 1f - y * (1f - MainActivity.NILAI_MINIMUM_KILAU);
            }
            saatBerubah.run();
            return true;
        }
        if (aksi == android.view.MotionEvent.ACTION_UP) {
            saatLepas.run();
            performClick();
            return true;
        }
        return super.onTouchEvent(e);
    }

    @Override
    public boolean performClick() {
        return super.performClick();
    }
}
