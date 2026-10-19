package id.sistemantrian.kiosk;

import android.content.Context;
import android.graphics.Color;
import android.graphics.SurfaceTexture;
import android.net.Uri;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.widget.FrameLayout;

import java.util.Map;

/**
 * Pemutar video di atas TextureView. VideoView memakai SurfaceView yang
 * digambar di lapisan terpisah dan tampil hitam pada emulator dan
 * sebagian panel (keluaran decoder tidak dikomposisi). TextureView
 * digambar lewat GL di dalam hierarki tampilan, sehingga terlihat di
 * mana pun, ikut peredupan dan animasi, dan rasio video dijaga (pas):
 * utuh, dengan pita hitam bila rasionya berbeda.
 */
final class VideoTekstur extends FrameLayout
        implements TextureView.SurfaceTextureListener {
    private final TextureView tekstur;
    private SurfaceTexture permukaan;
    private android.media.MediaPlayer pemain;
    private Uri sumber;
    private Map<String, String> header;
    private android.media.MediaPlayer.OnCompletionListener selesai;
    private android.media.MediaPlayer.OnErrorListener galat;
    private android.media.MediaPlayer.OnPreparedListener siap;
    private int lebarVideo;
    private int tinggiVideo;
    private boolean dihentikan;

    /** Penentu skala dibaca tiap kali bingkai dihitung, supaya pilihan teknisi langsung berlaku. */
    interface PenentuSkala {
        boolean isi();
    }

    private final PenentuSkala penentuSkala;

    VideoTekstur(Context konteks, PenentuSkala penentuSkala) {
        super(konteks);
        this.penentuSkala = penentuSkala;
        setBackgroundColor(Color.BLACK);
        tekstur = new TextureView(konteks);
        tekstur.setSurfaceTextureListener(this);
        addView(tekstur, new FrameLayout.LayoutParams(-1, -1, Gravity.CENTER));
    }

    void setOnCompletionListener(android.media.MediaPlayer.OnCompletionListener l) {
        selesai = l;
    }

    void setOnErrorListener(android.media.MediaPlayer.OnErrorListener l) {
        galat = l;
    }

    void setOnPreparedListener(android.media.MediaPlayer.OnPreparedListener l) {
        siap = l;
    }

    void setVideoURI(Uri uri) {
        setVideoURI(uri, null);
    }

    void setVideoURI(Uri uri, Map<String, String> headers) {
        sumber = uri;
        header = headers;
        mulaiBilaSiap();
    }

    void stopPlayback() {
        dihentikan = true;
        lepaskan();
    }

    private void mulaiBilaSiap() {
        if (pemain != null || sumber == null || permukaan == null || dihentikan) return;
        try {
            pemain = new android.media.MediaPlayer();
            pemain.setSurface(new Surface(permukaan));
            pemain.setOnVideoSizeChangedListener((p, w, h) -> {
                lebarVideo = w;
                tinggiVideo = h;
                pasKanKeBingkai();
            });
            pemain.setOnCompletionListener(p -> {
                if (selesai != null) selesai.onCompletion(p);
            });
            pemain.setOnErrorListener((p, what, extra) ->
                    galat != null && galat.onError(p, what, extra));
            pemain.setOnPreparedListener(p -> {
                if (siap != null) siap.onPrepared(p);
            });
            if (header == null) {
                pemain.setDataSource(getContext(), sumber);
            } else {
                pemain.setDataSource(getContext(), sumber, header);
            }
            pemain.prepareAsync();
        } catch (Exception e) {
            lepaskan();
            if (galat != null) {
                galat.onError(null, android.media.MediaPlayer.MEDIA_ERROR_UNKNOWN, 0);
            }
        }
    }

    private void lepaskan() {
        android.media.MediaPlayer lama = pemain;
        pemain = null;
        if (lama == null) return;
        try {
            lama.setOnCompletionListener(null);
            lama.setOnErrorListener(null);
            lama.setOnPreparedListener(null);
            lama.setOnVideoSizeChangedListener(null);
            lama.release();
        } catch (Exception ignored) {
            // Pemutar yang sudah rusak tidak perlu dilaporkan lagi.
        }
    }

    /** Rasio dijaga; teknisi memilih utuh (pas) atau penuh (isi). */
    private void pasKanKeBingkai() {
        int lebar = getWidth();
        int tinggi = getHeight();
        if (lebarVideo <= 0 || tinggiVideo <= 0 || lebar <= 0 || tinggi <= 0) return;
        boolean isi = penentuSkala.isi();
        float skala = isi
                ? Math.max(lebar / (float) lebarVideo, tinggi / (float) tinggiVideo)
                : Math.min(lebar / (float) lebarVideo, tinggi / (float) tinggiVideo);
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                Math.round(lebarVideo * skala), Math.round(tinggiVideo * skala),
                Gravity.CENTER);
        tekstur.setLayoutParams(params);
    }

    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        pasKanKeBingkai();
    }

    @Override
    protected void onDetachedFromWindow() {
        super.onDetachedFromWindow();
        lepaskan();
    }

    @Override
    public void onSurfaceTextureAvailable(SurfaceTexture st, int w, int h) {
        permukaan = st;
        mulaiBilaSiap();
    }

    @Override
    public void onSurfaceTextureSizeChanged(SurfaceTexture st, int w, int h) { }

    @Override
    public boolean onSurfaceTextureDestroyed(SurfaceTexture st) {
        lepaskan();
        permukaan = null;
        return true;
    }

    @Override
    public void onSurfaceTextureUpdated(SurfaceTexture st) { }
}
