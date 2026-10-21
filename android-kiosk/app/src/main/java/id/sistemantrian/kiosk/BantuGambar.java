package id.sistemantrian.kiosk;

import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;

/**
 * Pembuat huruf dan latar bersudut tumpul yang tidak bergantung pada keadaan
 * Activity. MainActivity memakainya lewat import statis.
 */
final class BantuGambar {
    private BantuGambar() { }

    /**
     * Satu-satunya tempat memilih huruf. Bila huruf merek (mis. Plus Jakarta
     * Sans) dibundel di assets, cukup ganti isi fungsi ini.
     */
    static Typeface huruf(int tebal) {
        if (tebal >= 800) return Typeface.create("sans-serif-black", Typeface.NORMAL);
        if (tebal >= 700) return Typeface.create("sans-serif", Typeface.BOLD);
        if (tebal >= 500) return Typeface.create("sans-serif-medium", Typeface.NORMAL);
        return Typeface.create("sans-serif", Typeface.NORMAL);
    }

    static GradientDrawable rounded(int color, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(radius);
        return shape;
    }

    static GradientDrawable roundedOutline(
            int color, int stroke, int radius, int strokeWidth) {
        GradientDrawable shape = rounded(color, radius);
        shape.setStroke(strokeWidth, stroke);
        return shape;
    }

    static GradientDrawable roundedGradient(
            int top, int bottom, int radius, int border, int borderWidth) {
        GradientDrawable shape = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM, new int[]{top, bottom});
        shape.setCornerRadius(radius);
        shape.setStroke(borderWidth, border);
        return shape;
    }

    static StateListDrawable stateBackground(int normal, int pressed, int radius) {
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_pressed},
                rounded(pressed, radius));
        states.addState(new int[]{}, rounded(normal, radius));
        return states;
    }
}
