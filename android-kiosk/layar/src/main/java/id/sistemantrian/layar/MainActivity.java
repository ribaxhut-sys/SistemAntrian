package id.sistemantrian.layar;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.ToneGenerator;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.transition.AutoTransition;
import android.transition.TransitionManager;
import android.util.DisplayMetrics;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.GridLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Layar antrian untuk panel Android Maxtor (docs/istilah.md, docs/layar-antrian.md).
 *
 * Hanya menampilkan dan membunyikan panggilan; tidak pernah menerbitkan
 * nomor. Isinya diambil dari API aplikasi server:
 *
 *   GET /v1/layar/state?next=12  papan: nomor tiap loket, berikutnya, jumlah menunggu
 *   GET /v1/layar/calls?after=N  panggilan baru sesudah id N, beserta kalimat dan klipnya
 *   GET /v1/layar/sound          paket suara (untuk panel tanpa TTS Bahasa Indonesia)
 *   GET /v1/layar/app/apk        APK terbaru untuk memperbarui diri
 *
 * Setiap panggilan — termasuk panggil ulang — punya id sendiri, sehingga
 * layar cukup mengingat id terakhir yang sudah dibunyikannya. Saat baru
 * menyala atau baru tersambung lagi, layar hanya mengambil id terakhir tanpa
 * membunyikan apa pun: nomor lama yang diumumkan ulang lebih membingungkan
 * daripada layar yang diam.
 *
 * Panel Maxtor berlayar sentuh dan bisa dipasang tegak atau mendatar. Layar
 * ini hanya untuk ditonton: semua sentuhan diabaikan, kecuali menahan judul
 * 3 detik untuk membuka pengaturan.
 */
public class MainActivity extends Activity implements TextToSpeech.OnInitListener {

    /** Identitas tetap; tidak mengikuti judul dari server (app/core/identitas.py). */
    private static final String NAMA_TAMPIL = "CRO";

    private static final String PREFS = "layar";
    private static final String TEMA = "tema";
    private static final String TEMA_BENING = "bening";
    /** Tema yang dapat dipilih di pengaturan: {id, nama, deskripsi}. Disimpan per perangkat. */
    private static final String[][] TEMA_DAFTAR = {
            {TEMA_BENING, "Bening",
                    "Latar putih: strip loket, 3 nomor berikutnya, lalu daftar menunggu."},
            {"dinding", "Dinding",
                    "Dinding nomor berwarna menurut status, dengan banner panggilan terbaru di atas."},
    };
    private static final String SERVER = "server";
    private static final String TOKEN = "token";
    private static final String DEVICE_ID = "device_id";
    private static final String DEVICE_NAME = "device_name";
    private static final String PACK_VERSION = "sound_pack_version";
    private static final String DEVICE_KIND = "layar_antrian";
    private static final int DISCOVERY_PORT = 8766;
    private static final String DISCOVERY_REQUEST = "SISTEMANTRIAN_KIOSK_DISCOVER_V1";
    private static final String DISCOVERY_RESPONSE = "SISTEMANTRIAN_KIOSK_SERVER_V1";
    private static final String DEFAULT_TIMEZONE = "Asia/Jakarta";
    private static final String ACTION_INSTALL_STATUS = "id.sistemantrian.layar.INSTALL_STATUS";
    private static final String JEDA = "_jeda";

    // Tema Bening (latar putih, aksen teal); lihat docs/layar-antrian.md.
    private static final int BG_TOP = Color.WHITE;
    private static final int BG_BOTTOM = Color.WHITE;
    private static final int TEAL = Color.rgb(15, 118, 110);
    private static final int ACCENT = Color.rgb(8, 145, 178);
    private static final int INK = Color.rgb(15, 23, 42);
    private static final int MUTED = Color.rgb(100, 116, 139);
    private static final int LIGHT = Color.rgb(51, 65, 85);
    private static final int GARIS = Color.rgb(203, 213, 225);
    private static final int AMBER = Color.rgb(180, 83, 9);

    private static final long STATE_INTERVAL_MS = 2000;
    private static final long CALLS_INTERVAL_MS = 1000;
    private static final long HIGHLIGHT_MS = 10000;
    private static final long TITLE_HOLD_MS = 3000;
    private static final long PACK_RETRY_MS = 60000;
    private static final int FAILURES_BEFORE_BANNER = 3;
    /**
     * Panggilan yang lebih tua dari ini (umur menurut jam server ditambah
     * lama antre di panel) tidak diucapkan lagi; sama dengan anjungan.
     */
    private static final double MAX_CALL_AGE_SECONDS = 60;
    /** Antrean ucapan paling panjang; yang tertua dibuang lebih dulu. */
    private static final int MAX_SPEECH_QUEUE = 10;

    // Daftar "Berikutnya": paling banyak 12 nomor, maksimal 45% tinggi papan,
    // dan kartu loket tidak pernah lebih pendek dari 1/8 tinggi layar.
    /** Baris nomor "Berikutnya" yang selalu disediakan; huruf menyesuaikan tinggi layar. */
    private static final int NEXT_BARIS = 10;
    private static final int NEXT_MAX = 300;
    /** Lama satu halaman nomor menunggu sebelum berganti, bila nomornya lebih dari satu halaman. */
    private static final long HALAMAN_MS = 8000;
    /** Jeda antar gelombang "kartu dibalik" pada daftar nomor (tema Dinding). */
    private static final long BALIK_MS = 30000;
    /** Lama tiap setengah putaran kartu dan jeda antarbaris pada gelombang kartu dibalik. */
    private static final long BALIK_SETENGAH_MS = 900;
    private static final long BALIK_JEDA_BARIS_MS = 320;
    /** Tinggi strip loket pada layar tegak. */
    private static final int CARD_TEGAK_DP = 84;
    /** Lebar kolom status di ujung kanan kartu loket. */
    private static final int STATUS_KOLOM_DP = 112;
    private static final float NEXT_SP = 30;
    /** Nomor teratas yang dipisah di atas daftar: yang akan dipanggil berikutnya. */
    private static final int AKAN_JUMLAH = 3;
    /** Tinggi bagian "AKAN DIPANGGIL" (label + pil) dan judul daftar, untuk hitungan baris. */
    private static final int AKAN_DP = 84;
    private static final float NEXT_SP_MIN = 16;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newFixedThreadPool(2);
    private final ExecutorService downloader = Executors.newSingleThreadExecutor();
    private final ArrayDeque<JSONObject> speechQueue = new ArrayDeque<>();
    private final Map<String, LinearLayout> cardsByCounter = new HashMap<>();
    private final Map<String, Long> highlightUntil = new HashMap<>();
    /** Denyut pil status loket yang sedang memanggil, per nama loket. */
    private final Map<String, android.animation.ObjectAnimator> denyut = new HashMap<>();
    private final Map<String, String> packClips = new HashMap<>();

    private SharedPreferences preferences;
    private TextToSpeech tts;
    private boolean ttsChecked;
    private boolean ttsReady;
    private boolean speaking;
    private ToneGenerator tone;
    private MediaPlayer player;

    private boolean portrait;
    private LinearLayout root;
    private LinearLayout head;
    private TextView title;
    private TextView clock;
    private GridLayout grid;
    private LinearLayout side;
    private TextView nextHeader;
    /** Tema aktif; null berarti Bening (susunan bawaan di MainActivity). */
    private TemaLayar tema;
    private LinearLayout akanRow;
    private TextView listHeader;
    private LinearLayout nextList;
    private final NomorMenunggu[] akanPil = new NomorMenunggu[AKAN_JUMLAH];
    private TextView moreLabel;
    private TextView footerName;
    private TextView banner;
    private LinearLayout body;

    private JSONObject lastState;
    private String bannerMessage;
    private String serverTimezone = DEFAULT_TIMEZONE;
    private long serverOffsetMillis;
    private Long lastCallId;
    private boolean soundEnabled = true;
    private int failures;
    private long disconnectedSince;
    private String countersSignature = "";
    private int nextRowsShown = -1;
    /** Ukuran huruf nomor "Berikutnya" saat ini (mengecil agar 10 baris muat). */
    private float nextSp = NEXT_SP;
    private float nextSpDibangun = -1;
    /** Halaman nomor "Berikutnya" yang sedang tampil (mulai 0) dan jumlah halamannya. */
    private int halaman = 0;
    private int halamanTotal = 1;
    private int shiftStep;
    private boolean stateInFlight;
    private boolean callsInFlight;
    private boolean packDownloading;
    private long packRetryAt;

    // Pembaruan APK dari server.
    private int minVersionCode;
    private int latestVersionCode;
    private String latestVersionName = "";
    private boolean updating;
    private AlertDialog updateDialog;

    private final Runnable titleHold = this::showSettings;

    private final BroadcastReceiver installReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            int status = intent.getIntExtra(
                    PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirm != null) {
                    confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(confirm);
                }
                return;
            }
            if (status == PackageInstaller.STATUS_SUCCESS) return;
            String message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            finishUpdate("Pembaruan dibatalkan atau gagal" + (message == null ? "." : ": " + message));
        }
    };

    // =================================================================
    // Siklus hidup
    // =================================================================

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        hideSystemUi();
        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        loadPack();
        buildScreen();
        tts = new TextToSpeech(this, this);
        try {
            tone = new ToneGenerator(AudioManager.STREAM_MUSIC, 90);
        } catch (RuntimeException e) {
            tone = null;
        }
        IntentFilter installFilter = new IntentFilter(ACTION_INSTALL_STATUS);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(installReceiver, installFilter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(installReceiver, installFilter);
        }
        handler.post(clockTick);
        handler.postDelayed(putarHalaman, HALAMAN_MS);
        handler.postDelayed(balikBarisTugas, BALIK_MS);
        handler.postDelayed(burnInShift, 5 * 60 * 1000L);
        if (!isPaired()) {
            showBanner("Layar belum dipasangkan. Tahan judul 3 detik untuk membuka pengaturan.");
            handler.postDelayed(this::showSettings, 800);
        }
        handler.post(statePoll);
        handler.post(callsPoll);
    }

    @Override
    protected void onResume() {
        super.onResume();
        hideSystemUi();
    }

    @Override
    protected void onDestroy() {
        for (android.animation.ObjectAnimator a : denyut.values()) a.cancel();
        if (tema != null) tema.hentikan();
        handler.removeCallbacksAndMessages(null);
        worker.shutdownNow();
        downloader.shutdownNow();
        try {
            unregisterReceiver(installReceiver);
        } catch (IllegalArgumentException ignored) {
            // Belum terdaftar.
        }
        releasePlayer();
        if (tts != null) tts.shutdown();
        if (tone != null) tone.release();
        super.onDestroy();
    }

    /** Panel diputar: susun ulang tanpa memulai ulang aplikasi (manifest: configChanges). */
    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        susunUlang();
        hideSystemUi();
    }

    /** Bangun ulang layar (orientasi atau tema berubah) lalu isi dengan keadaan terakhir. */
    private void susunUlang() {
        buildScreen();
        if (lastState != null) {
            JSONObject state = lastState;
            // Tunggu ukuran baru terpasang supaya tinggi kartu dihitung benar.
            body.post(() -> applyState(state));
        }
        if (failures >= FAILURES_BEFORE_BANNER) body.setAlpha(0.55f);
    }

    private void hideSystemUi() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
    }

    // Remote / keyboard: MENU, SETTINGS, atau tahan OK membuka pengaturan.
    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_MENU || keyCode == KeyEvent.KEYCODE_SETTINGS) {
            showSettings();
            return true;
        }
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            event.startTracking();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public boolean onKeyLongPress(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            showSettings();
            return true;
        }
        return super.onKeyLongPress(keyCode, event);
    }

    /** Tombol kembali tidak menutup layar antrian. */
    @Override
    public void onBackPressed() {
        // Sengaja kosong.
    }

    /**
     * Kunci sentuh: layar hanya untuk ditonton, jadi semua sentuhan ditelan.
     * Satu-satunya pengecualian: tahan judul (atau jam) 3 detik untuk membuka
     * pengaturan. Sentuhan sekilas pengunjung tidak melakukan apa-apa.
     */
    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                handler.removeCallbacks(titleHold);
                if (hitsHeader(event)) handler.postDelayed(titleHold, TITLE_HOLD_MS);
                break;
            case MotionEvent.ACTION_MOVE:
                if (!hitsHeader(event)) handler.removeCallbacks(titleHold);
                break;
            default:
                // Lepas, batal, atau jari kedua: batalkan hitungan.
                handler.removeCallbacks(titleHold);
                break;
        }
        return true;
    }

    private boolean hitsHeader(MotionEvent event) {
        if (head == null) return false;
        Rect area = new Rect();
        if (!head.getGlobalVisibleRect(area)) return false;
        return area.contains((int) event.getRawX(), (int) event.getRawY());
    }

    @Override
    public void onInit(int status) {
        ttsChecked = true;
        if (status != TextToSpeech.SUCCESS) return;
        int hasil = tts.setLanguage(new Locale("id", "ID"));
        ttsReady = hasil != TextToSpeech.LANG_MISSING_DATA
                && hasil != TextToSpeech.LANG_NOT_SUPPORTED;
        tts.setOnUtteranceProgressListener(new android.speech.tts.UtteranceProgressListener() {
            @Override public void onStart(String id) { }
            @Override public void onDone(String id) { handler.post(() -> finishSpeech(0)); }
            @Override public void onError(String id) { handler.post(() -> finishSpeech(0)); }
        });
    }

    // =================================================================
    // Tampilan
    // =================================================================

    /**
     * Skala huruf. Dirancang untuk 1280×720 (mendatar) atau 720×1280 (tegak);
     * panel 1080p dan 4K ikut membesar, sama besar di kedua arah.
     */
    private float scale() {
        DisplayMetrics metrics = getResources().getDisplayMetrics();
        float w = metrics.widthPixels / metrics.scaledDensity;
        float h = metrics.heightPixels / metrics.scaledDensity;
        float longSide = Math.max(w, h);
        float shortSide = Math.min(w, h);
        return Math.max(0.7f, Math.min(longSide / 1280f, shortSide / 720f));
    }

    private float sp(float value) {
        return value * scale();
    }

    private float spToPx(float value) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, value,
                getResources().getDisplayMetrics());
    }

    private int dp(float value) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value,
                getResources().getDisplayMetrics()));
    }

    /**
     * Nomor menunggu. Nomor prioritas ditandai bintang kecil di pojok kiri
     * atas dan latar kuning lembut; teks nomornya tetap polos.
     */
    private static final class NomorMenunggu extends TextView {
        private static final int AMBER = Color.rgb(245, 158, 11);
        private final Paint bintang = new Paint(Paint.ANTI_ALIAS_FLAG);
        private boolean prioritas;

        NomorMenunggu(Context context) {
            super(context);
            bintang.setColor(AMBER);
        }

        private int gaya = -1;

        /**
         * Pil nomor: abu muda untuk nomor biasa, amber muda untuk prioritas,
         * teal muda untuk nomor yang paling dekat dipanggil. Sel kosong tanpa latar.
         */
        void setGaya(boolean ada, boolean nilaiPrioritas, boolean pertama, boolean disorot) {
            terapkan(!ada ? 0 : nilaiPrioritas ? 2 : pertama ? 3 : disorot ? 4 : 1,
                    ada && nilaiPrioritas);
        }

        /**
         * Pil "akan dipanggil": nomor pertama teal penuh dengan teks putih,
         * nomor berikutnya teal muda; slot tanpa nomor abu redup.
         */
        void setGayaAkan(boolean ada, boolean nilaiPrioritas, boolean pertama) {
            terapkan(!ada ? 6 : nilaiPrioritas ? 2 : pertama ? 5 : 3, ada && nilaiPrioritas);
        }

        /** Gaya langsung menurut kode: 7 = dilayani (biru), 8 = dipanggil (oranye), selain itu seperti setGaya. */
        void setGayaKode(int kode, boolean tandaiPrioritas) {
            terapkan(kode, tandaiPrioritas);
        }

        private void terapkan(int baru, boolean tandaiPrioritas) {
            // Prioritas satu warna di semua tema dan di anjungan: ungu lembut.
            if (baru == 2) baru = 13;
            prioritas = tandaiPrioritas;
            if (baru == gaya) return;
            gaya = baru;
            float kerapatan = getResources().getDisplayMetrics().density;
            // Datar: tanpa bayangan dan tanpa aksen bertumpuk; hanya garis tipis.
            setElevation(0f);
            if (baru == 12) {
                GradientDrawable badan = new GradientDrawable();
                badan.setColor(Color.WHITE);
                badan.setCornerRadius(12 * kerapatan);
                badan.setStroke(Math.max(1, Math.round(kerapatan)), Color.rgb(226, 232, 240));
                setBackground(badan);
                setTextColor(Color.rgb(51, 65, 85));
            } else if (baru == 0 || baru == 11) {
                setBackground(null);
                if (baru == 11) setTextColor(INK);
            } else {
                float density = getResources().getDisplayMetrics().density;
                GradientDrawable latar = new GradientDrawable();
                latar.setCornerRadius(12 * density);
                int isi = baru == 2 ? Color.rgb(254, 243, 199)
                        : baru == 3 ? Color.rgb(204, 251, 241)
                        : baru == 4 ? Color.WHITE
                        : baru == 5 ? TEAL
                        : baru == 7 ? Color.rgb(219, 234, 254)
                        : baru == 8 ? Color.rgb(254, 243, 199)
                        : baru == 9 ? Color.rgb(220, 252, 231)
                        : baru == 10 ? Color.rgb(254, 226, 226)
                        : baru == 13 ? Color.rgb(243, 232, 255)
                        : baru == 6 ? Color.rgb(248, 250, 252) : Color.rgb(241, 245, 249);
                int garis = baru == 2 ? AMBER : baru == 3 || baru == 4 || baru == 5 ? TEAL
                        : baru == 7 ? Color.rgb(147, 197, 253) : baru == 8 ? Color.rgb(252, 211, 77)
                        : baru == 9 ? Color.rgb(134, 239, 172) : baru == 10 ? Color.rgb(252, 165, 165)
                        : baru == 13 ? Color.rgb(216, 180, 254) : GARIS;
                // Prioritas pada tema Dinding berwarna ungu lembut; bintangnya ikut.
                bintang.setColor(baru == 13 ? Color.rgb(126, 34, 206) : AMBER);
                latar.setColor(isi);
                latar.setStroke(Math.round(density), garis);
                setBackground(latar);
                setTextColor(baru == 3 ? TEAL : baru == 5 ? Color.WHITE
                        : baru == 7 ? Color.rgb(55, 90, 170) : baru == 8 ? Color.rgb(161, 90, 20)
                        : baru == 9 ? Color.rgb(36, 110, 72) : baru == 10 ? Color.rgb(176, 64, 64)
                        : baru == 13 ? Color.rgb(120, 60, 170)
                        : baru == 6 ? MUTED : INK);
            }
            invalidate();
        }

        @Override
        protected void onDraw(android.graphics.Canvas canvas) {
            super.onDraw(canvas);
            if (!prioritas) return;
            float besar = Math.max(getTextSize() * 0.32f,
                    10 * getResources().getDisplayMetrics().density);
            bintang.setTextSize(besar);
            canvas.drawText("★", 4 * getResources().getDisplayMetrics().density,
                    besar + 2 * getResources().getDisplayMetrics().density, bintang);
        }
    }

    // =================================================================
    // Tema tampilan (per perangkat)
    // =================================================================

    /**
     * Isi layar di bawah judul/jam dan di atas banner/kaki. Polling server,
     * suara, dan pembaruan tetap di MainActivity; tema hanya menggambar.
     */
    private abstract class TemaLayar {
        abstract View bangun(boolean tegak);

        /** Keadaan terbaru dari server (tiap polling). */
        abstract void terapkan(JSONObject state);

        /** Satu panggilan baru (sebelum suara dibunyikan). */
        void panggilanBaru(JSONObject call) { }

        /** Pergantian halaman berkala (tiap HALAMAN_MS). */
        void putarHalaman() { }

        /** Gelombang kartu dibalik pada baris-baris nomor (tiap BALIK_MS). */
        void balikBaris() { }

        /** Hentikan animasi sebelum tema diganti atau aplikasi ditutup. */
        void hentikan() { }
    }

    private TemaLayar buatTema(String id) {
        if ("dinding".equals(id)) return new TemaDinding();
        return null;
    }

    /** Baris pil bergulir: kolom x baris nomor menunggu, bergantian halaman. */
    private final class DaftarPil {
        final LinearLayout wadah;
        private final int kolom;
        private final float besarSp;
        private final int tinggiBarisDp;
        /** Paling banyak baris per halaman; tinggi baris menyesuaikan sisa ruang sampai tinggiMaksDp. */
        int maksBaris = Integer.MAX_VALUE;
        int tinggiMaksDp;
        private int halaman = 0;
        int halamanTotal = 1;
        private String tanda = "";
        private java.util.List<String> nomor = new java.util.ArrayList<>();
        private java.util.Set<String> prioritas = new java.util.HashSet<>();
        private java.util.Map<String, Integer> khusus = new java.util.HashMap<>();
        /** Nomor menunggu tanpa latar, garis, dan warna; hanya yang berstatus khusus berwarna. */
        boolean polos = false;
        private java.util.Map<String, Float> redup = new java.util.HashMap<>();
        /** Halaman baru saja berganti: semua pil muncul bertahap, bukan bergeser. */
        private boolean halamanBerganti = false;

        DaftarPil(int kolom, float besarSp, int tinggiBarisDp) {
            this.kolom = kolom;
            this.besarSp = besarSp;
            this.tinggiBarisDp = tinggiBarisDp;
            this.tinggiMaksDp = tinggiBarisDp;
            wadah = new LinearLayout(MainActivity.this);
            wadah.setOrientation(LinearLayout.VERTICAL);
            wadah.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
                if (b - t != ob - ot) v.post(this::gambar);
            });
        }

        void isi(java.util.List<String> daftar, java.util.Set<String> prior) {
            isi(daftar, prior, new java.util.HashMap<>());
        }

        /** `gayaKhusus`: nomor -> kode gaya (7 dilayani, 8 dipanggil) yang mengalahkan gaya biasa. */
        void isi(java.util.List<String> daftar, java.util.Set<String> prior,
                 java.util.Map<String, Integer> gayaKhusus) {
            isi(daftar, prior, gayaKhusus, new java.util.HashMap<>());
        }

        /** `kepudaran`: nomor -> kepekatan (0..1); nomor yang baru dilayani memudar sebelum hilang. */
        void isi(java.util.List<String> daftar, java.util.Set<String> prior,
                 java.util.Map<String, Integer> gayaKhusus, java.util.Map<String, Float> kepudaran) {
            nomor = daftar;
            prioritas = prior;
            khusus = gayaKhusus;
            redup = kepudaran;
            gambar();
        }

        void putar() {
            if (halamanTotal <= 1) return;
            halaman = (halaman + 1) % halamanTotal;
            halamanBerganti = true;
            gambar();
        }

        /**
         * Gelombang "kartu dibalik": semua baris berputar pada sumbu mendatar dari atas
         * ke bawah, jeda BALIK_JEDA_BARIS_MS antarbaris. Separuh pertama memutar ke samping (90 derajat),
         * separuh kedua memutar kembali dari sisi seberang.
         */
        void balik() {
            float jarak = 8000f * getResources().getDisplayMetrics().density;
            for (int r = 0; r < wadah.getChildCount(); r++) {
                final View baris = wadah.getChildAt(r);
                baris.setCameraDistance(jarak);
                baris.animate().cancel();
                baris.setRotationX(0f);
                baris.animate().rotationX(90f).setStartDelay(r * BALIK_JEDA_BARIS_MS)
                        .setDuration(BALIK_SETENGAH_MS)
                        .setInterpolator(new android.view.animation.AccelerateInterpolator()).withEndAction(() -> {
                    baris.setRotationX(-90f);
                    baris.animate().rotationX(0f).setStartDelay(0).setDuration(BALIK_SETENGAH_MS)
                            .setInterpolator(new android.view.animation.DecelerateInterpolator()).start();
                }).start();
            }
        }

        /** Teks "Halaman x dari n" bila lebih dari satu halaman, selain itu kosong. */
        String keterangan() {
            if (halamanTotal <= 1) return "";
            StringBuilder titik = new StringBuilder();
            for (int h = 0; h < halamanTotal && h < 10; h++) titik.append(h == halaman ? "\u25CF " : "\u25CB ");
            return titik + " Halaman " + (halaman + 1) + " dari " + halamanTotal;
        }

        void gambar() {
            int tinggi = wadah.getHeight();
            // Baris sebanyak yang muat pada tinggi minimum, dibatasi maksBaris; tinggi tiap
            // baris lalu dibagi rata dari sisa ruang (paling tinggi tinggiMaksDp), dan
            // huruf mengikuti tinggi baris.
            int baris = Math.max(1, Math.min(maksBaris, tinggi / dp(tinggiBarisDp)));
            int tinggiBaris = Math.max(dp(tinggiBarisDp), Math.min(dp(tinggiMaksDp), tinggi / baris));
            final float besarIni = Math.min(besarSp,
                    tinggiBaris / getResources().getDisplayMetrics().density * 0.52f);
            int perHalaman = baris * kolom;
            halamanTotal = Math.max(1, (int) Math.ceil(nomor.size() / (double) perHalaman));
            if (halaman >= halamanTotal) halaman = 0;
            int awal = halaman * perHalaman;
            int tampil = Math.max(0, Math.min(nomor.size() - awal, perHalaman));
            int barisTampil = (int) Math.ceil(tampil / (double) kolom);
            StringBuilder sig = new StringBuilder().append(wadah.getWidth()).append('x').append(tinggi).append('#');
            for (int i = 0; i < tampil; i++) {
                String n = nomor.get(awal + i);
                Float pekat = redup.get(n);
                sig.append(n).append(prioritas.contains(n) ? "*" : "").append(khusus.get(n))
                        .append(pekat == null ? "" : "~" + Math.round(pekat * 10)).append(',');
            }
            if (tinggi <= 0 || sig.toString().equals(tanda)) return;
            tanda = sig.toString();
            // Posisi pil sebelum digambar ulang, untuk animasi geser (C).
            final java.util.Map<String, int[]> lama = new java.util.HashMap<>();
            for (int r = 0; r < wadah.getChildCount(); r++) {
                View barisLama = wadah.getChildAt(r);
                if (!(barisLama instanceof LinearLayout)) continue;
                LinearLayout br = (LinearLayout) barisLama;
                for (int c = 0; c < br.getChildCount(); c++) {
                    View v = br.getChildAt(c);
                    if (v instanceof TextView) {
                        lama.put(((TextView) v).getText().toString(),
                                new int[]{br.getLeft() + v.getLeft(), br.getTop() + v.getTop()});
                    }
                }
            }
            final boolean semuaBaru = lama.isEmpty() || halamanBerganti;
            halamanBerganti = false;
            final java.util.List<NomorMenunggu> pilBaru = new java.util.ArrayList<>();
            wadah.removeAllViews();
            for (int r = 0; r < barisTampil; r++) {
                LinearLayout row = new LinearLayout(MainActivity.this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                for (int c = 0; c < kolom; c++) {
                    int idx = r * kolom + c;
                    LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, tinggiBaris, 1);
                    lp.setMargins(dp(3), dp(2), dp(3), dp(2));
                    if (idx >= tampil) {
                        row.addView(new View(MainActivity.this), lp);
                        continue;
                    }
                    String n = nomor.get(awal + idx);
                    NomorMenunggu pil = new NomorMenunggu(MainActivity.this);
                    pil.setText(n);
                    pil.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp(besarIni));
                    pil.setTextColor(INK);
                    pil.setGravity(Gravity.CENTER);
                    pil.setSingleLine(true);
                    pil.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
                    pil.setPadding(dp(4), 0, dp(4), 0);
                    Float pekat = redup.get(n);
                    if (pekat != null) pil.setAlpha(pekat);
                    Integer kode = khusus.get(n);
                    if (kode != null) pil.setGayaKode(kode, false);
                    else if (polos) {
                        // Hanya prioritas yang berwarna (amber + bintang); selebihnya polos.
                        if (prioritas.contains(n)) pil.setGayaKode(13, true);
                        else pil.setGayaKode(12, false);
                    }
                    else pil.setGaya(true, prioritas.contains(n), awal + idx == 0, false);
                    pil.addOnLayoutChangeListener((v, l, t, rr, b, ol, ot, or, ob) -> {
                        if (rr - l != or - ol) v.post(() -> fitText((TextView) v, besarIni, v.getWidth() - dp(8), 0));
                    });
                    row.addView(pil, lp);
                    pilBaru.add(pil);
                }
                wadah.addView(row);
            }
            // A: halaman baru, pil muncul satu per satu. B: nomor baru membesar halus.
            // C: nomor yang sudah ada bergeser mulus ke tempat barunya.
            wadah.getViewTreeObserver().addOnPreDrawListener(new android.view.ViewTreeObserver.OnPreDrawListener() {
                @Override
                public boolean onPreDraw() {
                    wadah.getViewTreeObserver().removeOnPreDrawListener(this);
                    int urut = 0;
                    for (NomorMenunggu pil : pilBaru) {
                        View induk = (View) pil.getParent();
                        float akhirAlpha = pil.getAlpha();
                        int[] awalPos = lama.get(pil.getText().toString());
                        if (semuaBaru) {
                            pil.setAlpha(0f);
                            pil.animate().alpha(akhirAlpha).setStartDelay(Math.min(urut, 30) * 20L)
                                    .setDuration(300).start();
                            urut++;
                        } else if (awalPos == null) {
                            pil.setAlpha(0f);
                            pil.setScaleX(0.9f);
                            pil.setScaleY(0.9f);
                            pil.animate().alpha(akhirAlpha).scaleX(1f).scaleY(1f).setDuration(300).start();
                        } else {
                            float dx = awalPos[0] - (induk.getLeft() + pil.getLeft());
                            float dy = awalPos[1] - (induk.getTop() + pil.getTop());
                            if (dx != 0f || dy != 0f) {
                                pil.setTranslationX(dx);
                                pil.setTranslationY(dy);
                                pil.animate().translationX(0f).translationY(0f).setDuration(250).start();
                            }
                        }
                    }
                    return true;
                }
            });
        }
    }

    private java.util.Set<String> himpunanPrioritas(JSONObject state) {
        java.util.Set<String> hasil = new java.util.HashSet<>();
        JSONArray baris = state.optJSONArray("next_priority");
        for (int i = 0; baris != null && i < baris.length(); i++) hasil.add(baris.optString(i));
        return hasil;
    }

    private java.util.List<String> daftarMenunggu(JSONObject state) {
        java.util.List<String> hasil = new java.util.ArrayList<>();
        JSONArray baris = state.optJSONArray("next");
        for (int i = 0; baris != null && i < baris.length(); i++) hasil.add(baris.optString(i));
        return hasil;
    }

    private void aturPilStatus(TextView pil, String label, String kunciDenyut) {
        boolean ada = label != null && !label.isEmpty();
        pil.setVisibility(ada ? View.VISIBLE : View.INVISIBLE);
        if (ada) {
            boolean dilayani = "Dilayani".equalsIgnoreCase(label);
            pil.setText(label.toUpperCase(Locale.ROOT));
            pil.setTextColor(dilayani ? Color.rgb(55, 90, 170) : Color.rgb(161, 90, 20));
            pil.setBackground(rounded(dilayani ? Color.rgb(219, 234, 254) : Color.rgb(254, 243, 199), dp(14)));
        }
        aturDenyut(kunciDenyut, pil, ada && "Dipanggil".equalsIgnoreCase(label));
    }

    /** Kecilkan huruf sampai muat lebar (dan tinggi bila `denganTinggi`) setiap kali ukuran view berubah. */
    private void pasKe(TextView view, float maxSp, boolean denganTinggi) {
        view.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
            if (r - l != or - ol || (denganTinggi && b - t != ob - ot)) {
                v.post(() -> fitText((TextView) v, maxSp, v.getWidth() - dp(6),
                        denganTinggi ? v.getHeight() : 0));
            }
        });
    }

    // -----------------------------------------------------------------
    // Tema Dinding: dinding nomor berwarna menurut status
    // -----------------------------------------------------------------

    private final class TemaDinding extends TemaLayar {
        private LinearLayout loketWadah;
        private LinearLayout panggilWadah;
        private DaftarPil dinding;
        private TextView keterangan;
        private boolean tegakIni;
        private String tandaLoket = "";
        private String tandaPanggil = "";
        private String nomorBaru = "";
        private final java.util.Map<String, LinearLayout> chipLoket = new java.util.HashMap<>();
        /** Keterangan "MEMANGGIL" pada kotak loket yang sedang memanggil; titiknya bergerak. */
        private final java.util.List<TextView> statusMemanggil = new java.util.ArrayList<>();
        private int langkahTitik = 0;
        private final Runnable titikTugas = new Runnable() {
            @Override
            public void run() {
                langkahTitik = (langkahTitik + 1) % 4;
                for (TextView tv : statusMemanggil) tampilkanMemanggil(tv);
                if (!statusMemanggil.isEmpty()) handler.postDelayed(this, 500);
            }
        };
        private final java.util.Map<String, Long> urutanPanggil = new java.util.HashMap<>();
        private int tinggiAkar = 0;
        private JSONObject terakhirState;
        /** Kapan nomor pertama kali terlihat sudah dilayani/selesai; dasar kepudaran. */
        private final java.util.Map<String, Long> dilayaniSejak = new java.util.HashMap<>();
        private boolean sudahMuatAwal = false;
        private static final long MEMUDAR_MS = 20000;

        @Override
        View bangun(boolean tegak) {
            tegakIni = tegak;
            tandaLoket = "";
            tandaPanggil = "";
            chipLoket.clear();
            LinearLayout akar = new LinearLayout(MainActivity.this);
            akar.setOrientation(LinearLayout.VERTICAL);
            tinggiAkar = 0;
            // Anggaran tinggi blok "sedang dipanggil" bergantung pada tinggi layar; hitung ulang bila berubah.
            akar.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
                if (b - t != ob - ot) {
                    tinggiAkar = b - t;
                    if (terakhirState != null) v.post(() -> terapkan(terakhirState));
                }
            });

            // Daftar loket paling atas: nomor yang dipegang tiap loket dan statusnya.
            loketWadah = new LinearLayout(MainActivity.this);
            loketWadah.setOrientation(LinearLayout.VERTICAL);
            // Jarak dari judul dan jam supaya kotak loket tidak menempel.
            loketWadah.setPadding(0, dp(28), 0, dp(8));
            akar.addView(loketWadah, new LinearLayout.LayoutParams(-1, -2));

            // Satu baris untuk setiap nomor yang sedang dipanggil; tingginya mengikuti jumlahnya.
            panggilWadah = new LinearLayout(MainActivity.this);
            panggilWadah.setOrientation(LinearLayout.VERTICAL);
            akar.addView(panggilWadah, new LinearLayout.LayoutParams(-1, -2));

            // Petunjuk warna.
            LinearLayout legenda = new LinearLayout(MainActivity.this);
            legenda.setOrientation(LinearLayout.HORIZONTAL);
            legenda.setPadding(0, dp(8), 0, dp(4));
            String[] nama = {"Dipanggil", "Baru dilayani", "Dilewati", "Prioritas"};
            int[] warna = {Color.rgb(252, 211, 77), Color.rgb(147, 197, 253), Color.rgb(252, 165, 165),
                    Color.rgb(216, 180, 254)};
            for (int i = 0; i < nama.length; i++) {
                LinearLayout item = new LinearLayout(MainActivity.this);
                item.setOrientation(LinearLayout.HORIZONTAL);
                item.setGravity(Gravity.CENTER_VERTICAL);
                View titik = new View(MainActivity.this);
                titik.setBackground(rounded(warna[i], dp(5)));
                LinearLayout.LayoutParams lpTitik = new LinearLayout.LayoutParams(dp(10), dp(10));
                lpTitik.rightMargin = dp(3);
                item.addView(titik, lpTitik);
                TextView t = text(nama[i], 12, LIGHT, false);
                pasKe(t, 12, false);
                item.addView(t, new LinearLayout.LayoutParams(0, -2, 1));
                legenda.addView(item, new LinearLayout.LayoutParams(0, -2, 1));
            }
            akar.addView(legenda, new LinearLayout.LayoutParams(-1, -2));

            // Paling banyak 15 baris; tinggi baris 50-66 dp menyesuaikan sisa layar, huruf sampai 30sp.
            dinding = new DaftarPil(tegak ? 3 : 5, 30, 50);
            dinding.maksBaris = 15;
            dinding.tinggiMaksDp = 66;
            dinding.polos = true;
            akar.addView(dinding.wadah, new LinearLayout.LayoutParams(-1, 0, 1));
            keterangan = text("", 14, MUTED, false);
            keterangan.setPadding(0, dp(4), 0, 0);
            akar.addView(keterangan);
            return akar;
        }

        /**
         * Satu kartu per loket, selalu satu baris (dua baris hanya bila loketnya
         * lebih dari 7): nomor di atas, nama loket di bawah dengan titik status.
         * Status dibawa warna garis dan titik (lihat petunjuk warna); semua
         * teks dikecilkan sampai muat, tidak pernah dipotong.
         */
        private void gambarLoket(JSONArray loket) {
            StringBuilder sig = new StringBuilder();
            for (int i = 0; i < loket.length(); i++) {
                JSONObject l = loket.optJSONObject(i);
                if (l == null) continue;
                sig.append(l.optString("name")).append('=').append(l.isNull("queue_number")
                        ? l.optString("status", "") : l.optString("queue_number")).append('!')
                        .append(l.optString("status", "")).append(';');
            }
            sig.append(tegakIni);
            if (sig.toString().equals(tandaLoket)) return;
            tandaLoket = sig.toString();
            hentikanDenyut("chip:");
            handler.removeCallbacks(titikTugas);
            statusMemanggil.clear();
            loketWadah.removeAllViews();
            chipLoket.clear();
            int jumlah = loket.length();
            if (jumlah == 0) return;
            // Sampai 5 loket: huruf terbesar; 6-7: satu tingkat lebih kecil; lebih dari 7: dua baris.
            int kolom = jumlah <= 7 ? jumlah : (int) Math.ceil(jumlah / 2.0);
            float besarNomor = jumlah <= 5 ? 30 : 24;
            float besarNama = jumlah <= 5 ? 14 : 12;
            int baris = (int) Math.ceil(jumlah / (double) kolom);
            for (int r = 0; r < baris; r++) {
                LinearLayout row = new LinearLayout(MainActivity.this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                for (int c = 0; c < kolom; c++) {
                    int idx = r * kolom + c;
                    LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(jumlah <= 5 ? 146 : 122), 1);
                    lp.setMargins(dp(3), dp(3), dp(3), dp(3));
                    JSONObject l = idx < jumlah ? loket.optJSONObject(idx) : null;
                    if (l == null) {
                        row.addView(new View(MainActivity.this), lp);
                        continue;
                    }
                    boolean ada = !l.isNull("queue_number");
                    String status = l.optString("status", "");
                    boolean dilayani = "Dilayani".equalsIgnoreCase(status);
                    int warna = !ada ? MUTED : dilayani ? Color.rgb(55, 90, 170) : Color.rgb(161, 90, 20);
                    int isiChip = !ada ? Color.WHITE
                            : dilayani ? Color.rgb(219, 234, 254) : Color.rgb(254, 243, 199);
                    int garisChip = !ada ? GARIS
                            : dilayani ? Color.rgb(147, 197, 253) : Color.rgb(252, 211, 77);
                    LinearLayout chip = new LinearLayout(MainActivity.this);
                    chip.setOrientation(LinearLayout.VERTICAL);
                    chip.setGravity(Gravity.CENTER);
                    GradientDrawable latar = rounded(isiChip, dp(12));
                    latar.setStroke(dp(ada ? 2 : 1), garisChip);
                    chip.setBackground(latar);
                    chip.setPadding(dp(4), dp(6), dp(4), dp(6));
                    // Susunan tetap di semua kotak: nama loket di atas, nomor di tengah, status di
                    // bawah. Selama DIPANGGIL nomornya hanya tampil di blok "SEDANG DIPANGGIL",
                    // jadi tempat nomor dibiarkan kosong; nomor baru muncul setelah dilayani.
                    boolean masihMemanggil = "Dipanggil".equalsIgnoreCase(status);
                    chip.setGravity(Gravity.CENTER_HORIZONTAL);

                    TextView nama = text(l.optString("name"), besarNama + 4, LIGHT, true);
                    nama.setGravity(Gravity.CENTER);
                    pasKe(nama, besarNama + 4, false);
                    chip.addView(nama, new LinearLayout.LayoutParams(-1, -2));

                    String isi = masihMemanggil ? "" : ada ? l.optString("queue_number") : "\u2013";
                    TextView nomor = text(isi, besarNomor, warna, false);
                    nomor.setGravity(Gravity.CENTER);
                    // Tanpa ruang tambahan font, dan diukur terhadap lebar DAN tinggi sisa kotak
                    // supaya nomor tidak terpotong.
                    nomor.setIncludeFontPadding(false);
                    pasKe(nomor, besarNomor, true);
                    chip.addView(nomor, new LinearLayout.LayoutParams(-1, 0, 1));

                    // Keterangan status: DIPANGGIL / DILAYANI, atau SIAP / ISTIRAHAT bila loket kosong.
                    String teksStatus = ada ? status.toUpperCase(Locale.ROOT)
                            : "ISTIRAHAT".equals(status) ? "ISTIRAHAT" : "SIAP";
                    TextView keteranganStatus = text(teksStatus, jumlah <= 5 ? 14 : 12, warna, true);
                    keteranganStatus.setGravity(Gravity.CENTER);
                    // Di kotak loket kata kerjanya dari sisi loket: MEMANGGIL (blok nomor tetap DIPANGGIL).
                    if (masihMemanggil) {
                        statusMemanggil.add(keteranganStatus);
                        tampilkanMemanggil(keteranganStatus);
                    }
                    pasKe(keteranganStatus, jumlah <= 5 ? 14 : 12, false);
                    chip.addView(keteranganStatus, new LinearLayout.LayoutParams(-1, -2));

                    row.addView(chip, lp);
                    chipLoket.put(l.optString("name"), chip);
                }
                loketWadah.addView(row, new LinearLayout.LayoutParams(-1, -2));
            }
            if (!statusMemanggil.isEmpty()) handler.postDelayed(titikTugas, 500);
        }

        /** "MEMANGGIL" diikuti 0-3 titik; titik yang belum muncul tetap memakan tempat agar lebar teks tetap. */
        private void tampilkanMemanggil(TextView tv) {
            android.text.SpannableString teks = new android.text.SpannableString("MEMANGGIL...");
            if (langkahTitik < 3) {
                teks.setSpan(new android.text.style.ForegroundColorSpan(Color.TRANSPARENT),
                        9 + langkahTitik, 12, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
            tv.setText(teks);
        }

        private void hentikanDenyutBaris() {
            hentikanDenyut("dinding:");
        }

        private void hentikanDenyut(String awalan) {
            java.util.Iterator<java.util.Map.Entry<String, android.animation.ObjectAnimator>> it =
                    denyut.entrySet().iterator();
            while (it.hasNext()) {
                java.util.Map.Entry<String, android.animation.ObjectAnimator> e = it.next();
                if (e.getKey().startsWith(awalan)) {
                    e.getValue().cancel();
                    it.remove();
                }
            }
        }

        /**
         * Satu baris per nomor yang sedang dipanggil. Makin banyak barisnya,
         * makin kecil hurufnya dan makin pendek barisnya, sehingga dinding
         * nomor di bawahnya menyesuaikan sisanya.
         */
        private void gambarPanggil(java.util.List<String[]> aktif) {
            StringBuilder sig = new StringBuilder().append(tegakIni).append('#').append(tinggiAkar).append('#')
                    .append(nomorBaru).append('#');
            for (String[] a : aktif) sig.append(a[0]).append('@').append(a[1]).append('/').append(a[2]).append(';');
            if (sig.toString().equals(tandaPanggil)) return;
            tandaPanggil = sig.toString();
            hentikanDenyutBaris();
            panggilWadah.removeAllViews();

            int n = aktif.size();
            if (n == 0) {
                TextView kosong = text("Belum ada nomor yang sedang dipanggil", 16, MUTED, false);
                kosong.setGravity(Gravity.CENTER);
                GradientDrawable latar = rounded(Color.rgb(248, 250, 252), dp(12));
                latar.setStroke(dp(1), GARIS);
                kosong.setBackground(latar);
                kosong.setPadding(dp(8), dp(10), dp(8), dp(10));
                pasKe(kosong, 16, false);
                panggilWadah.addView(kosong, new LinearLayout.LayoutParams(-1, -2));
                return;
            }
            judulPanggil();
            // Anggaran: blok ini paling banyak sepertiga tinggi layar, supaya dinding nomor
            // di bawahnya tetap punya ruang. Baris dikecilkan dahulu, lalu dikurangi.
            int anggaran = tinggiAkar > 0 ? Math.round(tinggiAkar * 0.34f) : dp(260);
            int ruangBaris = anggaran - dp(22);
            int minBaris = dp(46);
            int tampil = Math.max(1, Math.min(Math.min(n, 6), ruangBaris / minBaris));
            int idealDp = tampil == 1 ? 92 : tampil == 2 ? 74 : tampil == 3 ? 62 : tampil == 4 ? 54 : 46;
            int tinggiBaris = Math.max(minBaris - dp(6), Math.min(dp(idealDp), ruangBaris / tampil - dp(6)));
            float tinggiDp = tinggiBaris / getResources().getDisplayMetrics().density;
            float besarNomor = Math.min(60f, tinggiDp * 0.62f);
            float besarLoket = Math.max(13f, Math.min(22f, tinggiDp * 0.24f));
            for (int i = 0; i < tampil; i++) {
                String[] a = aktif.get(i);
                LinearLayout row = new LinearLayout(MainActivity.this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                row.setGravity(Gravity.CENTER_VERTICAL);
                GradientDrawable latarBaris = rounded(Color.rgb(204, 251, 241), dp(16));
                latarBaris.setStroke(dp(1), Color.rgb(153, 246, 228));
                row.setBackground(latarBaris);
                row.setPadding(dp(12), dp(2), dp(12), dp(2));
                TextView nomor = text(a[0], besarNomor, Color.rgb(17, 94, 89), false);
                nomor.setGravity(Gravity.CENTER);
                pasKe(nomor, besarNomor, true);
                row.addView(nomor, new LinearLayout.LayoutParams(0, -1, 1.5f));
                LinearLayout teks = new LinearLayout(MainActivity.this);
                teks.setOrientation(LinearLayout.VERTICAL);
                teks.setGravity(Gravity.CENTER_VERTICAL);
                TextView loket = text(a[1].toUpperCase(Locale.ROOT), besarLoket, Color.rgb(17, 94, 89), true);
                pasKe(loket, besarLoket, false);
                teks.addView(loket, new LinearLayout.LayoutParams(-1, -2));
                if (!a[2].isEmpty() && tinggiDp >= 60) {
                    float besarLayanan = Math.max(12f, besarLoket - 5);
                    TextView layanan = text(a[2], besarLayanan, Color.rgb(15, 118, 110), false);
                    pasKe(layanan, besarLayanan, false);
                    teks.addView(layanan, new LinearLayout.LayoutParams(-1, -2));
                }
                row.addView(teks, new LinearLayout.LayoutParams(0, -2, 1.7f));
                TextView status = text("", tinggiDp >= 70 ? 16 : 13, Color.WHITE, true);
                status.setGravity(Gravity.CENTER);
                status.setPadding(dp(10), dp(3), dp(10), dp(3));
                aturPilStatus(status, "Dipanggil", "dinding:" + a[1]);
                row.addView(status, new LinearLayout.LayoutParams(-2, -2));
                LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, tinggiBaris);
                lp.setMargins(0, dp(3), 0, dp(3));
                panggilWadah.addView(row, lp);
                if (a[0].equals(nomorBaru)) {
                    nomor.setScaleX(0.8f);
                    nomor.setScaleY(0.8f);
                    nomor.animate().scaleX(1f).scaleY(1f).setDuration(350)
                            .setInterpolator(new android.view.animation.OvershootInterpolator()).start();
                    kedipkan(row);
                }
            }
            if (n > tampil) {
                TextView lagi = text("+" + (n - tampil) + " nomor lain sedang dipanggil", 13, MUTED, true);
                lagi.setGravity(Gravity.CENTER);
                panggilWadah.addView(lagi, new LinearLayout.LayoutParams(-1, -2));
            }
            nomorBaru = "";
        }

        private void judulPanggil() {
            TextView judul = text("SEDANG DIPANGGIL", 13, LIGHT, true);
            judul.setPadding(dp(2), 0, 0, dp(1));
            panggilWadah.addView(judul, new LinearLayout.LayoutParams(-1, -2));
        }

        @Override
        void terapkan(JSONObject state) {
            terakhirState = state;
            JSONArray loket = state.optJSONArray("counters");
            if (loket == null) loket = new JSONArray();
            gambarLoket(loket);

            // Yang sedang dipanggil: loket berstatus Dipanggil, yang terbaru lebih dulu.
            java.util.List<String[]> aktif = new java.util.ArrayList<>();
            for (int i = 0; i < loket.length(); i++) {
                JSONObject l = loket.optJSONObject(i);
                if (l == null || l.isNull("queue_number")) continue;
                if (!"Dipanggil".equalsIgnoreCase(l.optString("status"))) continue;
                aktif.add(new String[]{l.optString("queue_number"), l.optString("name"),
                        l.isNull("category") ? "" : l.optString("category")});
            }
            java.util.Collections.sort(aktif, (x, y) -> {
                Long wx = urutanPanggil.get(x[0]);
                Long wy = urutanPanggil.get(y[0]);
                return Long.compare(wy == null ? 0L : wy, wx == null ? 0L : wx);
            });
            gambarPanggil(aktif);

            java.util.List<String> daftarNomor = new java.util.ArrayList<>();
            java.util.Map<String, Integer> khusus = new java.util.HashMap<>();
            // Semua nomor yang sudah dipanggil hari ini (terbaru dulu), lalu yang menunggu.
            JSONArray dipanggil = state.optJSONArray("called");
            long sekarang = System.currentTimeMillis();
            java.util.Map<String, Float> kepudaran = new java.util.HashMap<>();
            for (int i = 0; dipanggil != null && i < dipanggil.length(); i++) {
                JSONObject d = dipanggil.optJSONObject(i);
                if (d == null) continue;
                String nomor = d.optString("n");
                String st = d.optString("s");
                // Nomor yang sudah dilayani (atau selesai) memudar selama MEMUDAR_MS lalu
                // hilang dari dinding; yang tetap: sedang dipanggil dan dilewati. Nomor
                // yang sedang dilayani tetap terlihat di kotak loketnya.
                boolean dilayani = "Dilayani".equalsIgnoreCase(st) || "Ditunda".equalsIgnoreCase(st);
                boolean selesai = "Selesai".equalsIgnoreCase(st);
                if (dilayani || selesai) {
                    Long sejak = dilayaniSejak.get(nomor);
                    if (sejak == null) {
                        // Waktu muat pertama: yang sudah lama dilayani tidak perlu memudar lagi.
                        sejak = sudahMuatAwal ? sekarang : sekarang - MEMUDAR_MS;
                        dilayaniSejak.put(nomor, sejak);
                    }
                    long lalu = sekarang - sejak;
                    if (lalu >= MEMUDAR_MS) continue;
                    daftarNomor.add(nomor);
                    khusus.put(nomor, selesai ? 9 : 7);
                    kepudaran.put(nomor, Math.max(0.25f, 1f - 0.75f * lalu / (float) MEMUDAR_MS));
                    continue;
                }
                dilayaniSejak.remove(nomor);
                daftarNomor.add(nomor);
                khusus.put(nomor, "Dipanggil".equalsIgnoreCase(st) ? 8 : 10);
            }
            if (dipanggil == null) {
                // Server lama tanpa riwayat: pakai nomor yang dipegang loket.
                for (int i = 0; i < loket.length(); i++) {
                    JSONObject l = loket.optJSONObject(i);
                    if (l == null || l.isNull("queue_number")) continue;
                    if (!"Dipanggil".equalsIgnoreCase(l.optString("status"))) continue;
                    String nomor = l.optString("queue_number");
                    daftarNomor.add(nomor);
                    khusus.put(nomor, 8);
                }
            }
            sudahMuatAwal = true;
            int sudah = 0;
            for (Integer kode : khusus.values()) if (kode == 8) sudah++;
            for (String nomor : daftarMenunggu(state)) daftarNomor.add(nomor);

            dinding.isi(daftarNomor, himpunanPrioritas(state), khusus, kepudaran);
            int total = Math.max(state.optInt("total_waiting"), 0);
            String ket = dinding.keterangan();
            keterangan.setText((ket.isEmpty() ? "" : ket + " \u00B7 ")
                    + sudah + " dipanggil \u00B7 " + total + " menunggu");
        }

        @Override
        void panggilanBaru(JSONObject call) {
            String nomor = call.optString("queue_number");
            if (nomor.isEmpty()) return;
            nomorBaru = nomor;
            urutanPanggil.put(nomor, System.currentTimeMillis());
            LinearLayout chip = chipLoket.get(call.optString("counter_name"));
            if (chip != null) kedipkan(chip);
            // Barisnya sendiri digambar saat keadaan terbaru dari server tiba (segera sesudah ini).
        }

        @Override
        void putarHalaman() {
            dinding.putar();
        }

        @Override
        void balikBaris() {
            dinding.balik();
        }

        @Override
        void hentikan() {
            hentikanDenyutBaris();
            hentikanDenyut("chip:");
            handler.removeCallbacks(titikTugas);
            statusMemanggil.clear();
        }
    }

    private TextView text(String value, float size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp(size));
        view.setTextColor(color);
        view.setTypeface(Typeface.create("sans-serif", bold ? Typeface.BOLD : Typeface.NORMAL));
        view.setSingleLine(true);
        return view;
    }

    /** Latar kartu loket: putih dengan garis tipis agar terbaca di atas layar putih. */
    private GradientDrawable kartu(boolean sorot) {
        GradientDrawable bg = rounded(Color.WHITE, dp(16));
        if (sorot) bg.setStroke(dp(6), ACCENT);
        else bg.setStroke(dp(1), GARIS);
        return bg;
    }

    private GradientDrawable rounded(int color, float radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(radius);
        return shape;
    }

    /**
     * Susun layar sesuai arah panel.
     *
     *   Mendatar: kartu loket di kiri, kolom "Berikutnya" di kanan.
     *   Tegak:    kartu loket dua kolom di atas, "Berikutnya" di bawah.
     *
     * Judul dan jam selalu bertumpuk di tengah.
     */
    /** Susunan bawaan (tema Bening): kartu loket di kiri/atas, panel samping di kanan/bawah. */
    private void buildBeningBody() {
        body = new LinearLayout(this);
        body.setOrientation(portrait ? LinearLayout.VERTICAL : LinearLayout.HORIZONTAL);
        body.setPadding(0, dp(12), 0, dp(10));
        grid = new GridLayout(this);
        grid.setUseDefaultMargins(false);

        side = new LinearLayout(this);
        side.setOrientation(LinearLayout.VERTICAL);
        side.setPadding(dp(18), dp(12), dp(18), dp(12));
        GradientDrawable panel = rounded(Color.rgb(241, 245, 249), dp(16));
        panel.setStroke(dp(1), GARIS);
        side.setBackground(panel);
        nextHeader = text("AKAN DIPANGGIL", 18, LIGHT, true);
        side.addView(nextHeader);
        akanRow = new LinearLayout(this);
        akanRow.setOrientation(LinearLayout.HORIZONTAL);
        akanRow.setPadding(0, dp(4), 0, dp(6));
        String[] labelAkan = {"BERIKUTNYA", "KE-2", "KE-3"};
        float[] besarAkan = {30, 26, 26};
        for (int i = 0; i < AKAN_JUMLAH; i++) {
            final float besar = besarAkan[i];
            LinearLayout slot = new LinearLayout(this);
            slot.setOrientation(LinearLayout.VERTICAL);
            slot.setGravity(Gravity.CENTER_HORIZONTAL);
            TextView label = text(labelAkan[i], 11, i == 0 ? TEAL : MUTED, true);
            label.setGravity(Gravity.CENTER);
            slot.addView(label, new LinearLayout.LayoutParams(-1, -2));
            NomorMenunggu pil = new NomorMenunggu(this);
            pil.setText("\u2013");
            pil.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp(besar));
            pil.setGravity(Gravity.CENTER);
            pil.setSingleLine(true);
            pil.setTypeface(Typeface.create("sans-serif-medium", i == 0 ? Typeface.BOLD : Typeface.NORMAL));
            pil.setPadding(dp(4), dp(6), dp(4), dp(6));
            pil.setGayaAkan(false, false, i == 0);
            pil.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
                if (r - l != or - ol) {
                    v.post(() -> fitText((TextView) v, besar, v.getWidth() - dp(8), 0));
                }
            });
            LinearLayout.LayoutParams lpPil = new LinearLayout.LayoutParams(-1, -2);
            lpPil.topMargin = dp(2);
            slot.addView(pil, lpPil);
            akanPil[i] = pil;
            LinearLayout.LayoutParams lpSlot = new LinearLayout.LayoutParams(0, -2, i == 0 ? 1.25f : 1f);
            lpSlot.setMargins(dp(3), 0, dp(3), 0);
            akanRow.addView(slot, lpSlot);
        }
        side.addView(akanRow, new LinearLayout.LayoutParams(-1, -2));
        View garis = new View(this);
        garis.setBackgroundColor(GARIS);
        side.addView(garis, new LinearLayout.LayoutParams(-1, dp(1)));
        listHeader = text("MENUNGGU", 16, LIGHT, true);
        listHeader.setPadding(0, dp(8), 0, dp(2));
        side.addView(listHeader);
        nextList = new LinearLayout(this);
        nextList.setOrientation(LinearLayout.VERTICAL);
        side.addView(nextList, new LinearLayout.LayoutParams(-1, -2));
        moreLabel = text("", 16, MUTED, false);
        moreLabel.setPadding(0, dp(8), 0, 0);
        side.addView(moreLabel);

        if (portrait) {
            // Tegak: loket berupa strip ringkas setinggi isinya; sisa layar
            // dipakai daftar "Berikutnya" supaya lebih banyak nomor terlihat.
            body.addView(grid, new LinearLayout.LayoutParams(-1, -2));
            LinearLayout.LayoutParams sideParams = new LinearLayout.LayoutParams(-1, 0, 1);
            sideParams.topMargin = dp(10);
            body.addView(side, sideParams);
        } else {
            LinearLayout.LayoutParams gridParams = new LinearLayout.LayoutParams(0, -1, 3);
            gridParams.rightMargin = dp(18);
            body.addView(grid, gridParams);
            body.addView(side, new LinearLayout.LayoutParams(0, -1, 1.2f));
        }
        root.addView(body, new LinearLayout.LayoutParams(-1, 0, 1));
    }

    private void buildScreen() {
        DisplayMetrics metrics = getResources().getDisplayMetrics();
        portrait = metrics.heightPixels > metrics.widthPixels;

        FrameLayout frame = new FrameLayout(this);
        GradientDrawable background = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM, new int[]{BG_TOP, BG_BOTTOM});
        frame.setBackground(background);

        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        if (portrait) {
            root.setPadding(dp(16), dp(16), dp(16), dp(10));
        } else {
            root.setPadding(dp(28), dp(16), dp(28), dp(14));
        }
        frame.addView(root, new FrameLayout.LayoutParams(-1, -1));

        head = new LinearLayout(this);
        head.setOrientation(LinearLayout.VERTICAL);
        head.setGravity(Gravity.CENTER_HORIZONTAL);
        title = text(NAMA_TAMPIL,
                30, INK, true);
        title.setGravity(Gravity.CENTER);
        title.setLetterSpacing(0.04f);
        // Judul panjang dikecilkan supaya tetap satu baris di layar tegak.
        title.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
            if (r - l != or - ol) v.post(() -> fitText((TextView) v, 30, v.getWidth(), 0));
        });
        head.addView(title, new LinearLayout.LayoutParams(-1, -2));
        clock = text("", 20, LIGHT, false);
        clock.setGravity(Gravity.CENTER);
        clock.setPadding(0, dp(2), 0, 0);
        head.addView(clock, new LinearLayout.LayoutParams(-1, -2));
        root.addView(head, new LinearLayout.LayoutParams(-1, -2));

        if (tema != null) tema.hentikan();
        tema = buatTema(preferences.getString(TEMA, TEMA_BENING));
        if (tema != null) {
            body = new LinearLayout(this);
            body.setOrientation(LinearLayout.VERTICAL);
            body.setPadding(0, dp(10), 0, dp(6));
            body.addView(tema.bangun(portrait), new LinearLayout.LayoutParams(-1, -1));
            root.addView(body, new LinearLayout.LayoutParams(-1, 0, 1));
        } else {
            buildBeningBody();
        }

        banner = text("", 18, Color.WHITE, true);
        banner.setPadding(dp(16), dp(8), dp(16), dp(8));
        banner.setBackground(rounded(AMBER, dp(10)));
        banner.setSingleLine(false);
        if (bannerMessage == null) {
            banner.setVisibility(View.GONE);
        } else {
            banner.setText(bannerMessage);
        }
        root.addView(banner);

        LinearLayout foot = new LinearLayout(this);
        foot.setPadding(0, dp(6), 0, 0);
        foot.addView(text("Mohon perhatikan nomor Anda dipanggil", 14, MUTED, false),
                new LinearLayout.LayoutParams(0, -2, 1));
        footerName = text(deviceName(), 14, MUTED, false);
        foot.addView(footerName);
        root.addView(foot);

        cardsByCounter.clear();
        countersSignature = "";
        nextRowsShown = -1;
        shiftStep = 0;
        setContentView(frame);
    }

    /**
     * Kecilkan huruf sampai teks muat selebar `width` piksel dan (bila
     * `height` > 0) setinggi `height` piksel. Teks tidak pernah dipatah.
     */
    private void fitText(TextView view, float maxSp, int width, int height) {
        if (width <= 0) return;
        Paint paint = new Paint(view.getPaint());
        float size = sp(maxSp);
        String value = view.getText().toString();
        while (size > 12) {
            paint.setTextSize(spToPx(size));
            Paint.FontMetrics metrics = paint.getFontMetrics();
            boolean fitsWidth = paint.measureText(value) <= width * 0.92f;
            boolean fitsHeight = height <= 0 || (metrics.descent - metrics.ascent) <= height * 0.95f;
            if (fitsWidth && fitsHeight) break;
            size -= 2;
        }
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
    }

    /**
     * Teks pada loket yang aktif tetapi tidak sedang memanggil. Satu baris
     * pendek: "KOSONG" mengaburkan apakah loketnya atau antriannya yang kosong.
     */
    private static String teksLoketTanpaPanggilan(String status) {
        return "ISTIRAHAT".equals(status) ? "Istirahat" : "Siap melayani";
    }

    private void fitNumber(TextView number) {
        boolean status = number.getCurrentTextColor() == MUTED;
        fitText(number, status ? 30 : 72, number.getWidth(), number.getHeight());
    }

    private int columnsFor(int jumlah) {
        if (portrait) return 1;
        return jumlah <= 2 ? jumlah : jumlah <= 4 ? 2 : jumlah <= 6 ? 3 : 4;
    }

    /** Pil berdenyut selama dipanggil; dihentikan (dan dipulihkan) bila tidak. */
    private void aturDenyut(String loket, TextView pil, boolean aktif) {
        android.animation.ObjectAnimator animasi = denyut.get(loket);
        if (!aktif) {
            if (animasi != null) {
                animasi.cancel();
                denyut.remove(loket);
            }
            pil.setScaleX(1f);
            pil.setScaleY(1f);
            pil.setAlpha(1f);
            return;
        }
        if (animasi != null && animasi.getTarget() == pil) return;
        if (animasi != null) animasi.cancel();
        animasi = android.animation.ObjectAnimator.ofPropertyValuesHolder(pil,
                android.animation.PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.08f),
                android.animation.PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.08f),
                android.animation.PropertyValuesHolder.ofFloat(View.ALPHA, 1f, 0.8f));
        animasi.setDuration(900);
        animasi.setRepeatCount(android.animation.ValueAnimator.INFINITE);
        animasi.setRepeatMode(android.animation.ValueAnimator.REVERSE);
        animasi.start();
        denyut.put(loket, animasi);
    }

    private void buildCards(JSONArray counters) {
        for (android.animation.ObjectAnimator a : denyut.values()) a.cancel();
        denyut.clear();
        grid.removeAllViews();
        cardsByCounter.clear();
        int jumlah = Math.max(1, counters.length());
        int kolom = columnsFor(jumlah);
        int baris = (int) Math.ceil(jumlah / (double) kolom);
        grid.setColumnCount(kolom);
        grid.setRowCount(baris);
        for (int i = 0; i < counters.length(); i++) {
            JSONObject counter = counters.optJSONObject(i);
            String name = counter == null ? "" : counter.optString("name");
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(portrait ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
            card.setBackground(kartu(false));
            card.setClipToOutline(true);

            TextView label = text(name.toUpperCase(Locale.ROOT), 22, Color.WHITE, true);
            label.setGravity(Gravity.CENTER);
            label.setPadding(dp(6), dp(6), dp(6), dp(6));
            GradientDrawable top = new GradientDrawable();
            top.setColor(TEAL);
            top.setCornerRadii(portrait
                    ? new float[]{dp(16), dp(16), 0, 0, 0, 0, dp(16), dp(16)}
                    : new float[]{dp(16), dp(16), dp(16), dp(16), 0, 0, 0, 0});
            label.setBackground(top);
            label.setSingleLine(true);
            // Nama loket dan jenis layanan dikecilkan sampai muat; tidak pernah terpotong.
            label.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
                if (r - l != or - ol) {
                    v.post(() -> fitText((TextView) v, 22, v.getWidth() - v.getPaddingLeft() - v.getPaddingRight(), 0));
                }
            });
            // Tegak: blok teal (nama loket) di kiri, isi di kanan.
            card.addView(label, portrait
                    ? new LinearLayout.LayoutParams(0, -1, 1)
                    : new LinearLayout.LayoutParams(-1, -2));

            // Isi kartu: nomor + jenis layanan di tengah, status di ujung
            // kanan pada kolom selebar tetap. Lebar tetap itu menjaga nomor
            // dan nama layanan tetap rata tengah, apa pun statusnya.
            LinearLayout isi = new LinearLayout(this);
            isi.setOrientation(LinearLayout.HORIZONTAL);
            card.addView(isi, portrait
                    ? new LinearLayout.LayoutParams(0, -1, 2)
                    : new LinearLayout.LayoutParams(-1, 0, 1));
            LinearLayout tengah = new LinearLayout(this);
            tengah.setOrientation(LinearLayout.VERTICAL);
            isi.addView(tengah, new LinearLayout.LayoutParams(0, -1, 1));

            TextView number = text("", 72, INK, true);
            number.setGravity(Gravity.CENTER);
            number.setTag("number");
            // Nomor selalu SATU baris (PB-014, bukan PB- / 014): huruf
            // dikecilkan sampai muat lebar DAN tinggi kartu, dan diukur ulang
            // setiap kali kartu memendek atau memanjang.
            number.setSingleLine(true);
            number.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
                if (r - l != or - ol || b - t != ob - ot) {
                    v.post(() -> fitNumber((TextView) v));
                }
            });
            tengah.addView(number, new LinearLayout.LayoutParams(-1, 0, 1));

            TextView category = text("", 16, Color.rgb(71, 85, 105), false);
            category.setGravity(Gravity.CENTER);
            category.setPadding(0, 0, 0, dp(portrait ? 4 : 8));
            category.setTag("category");
            category.setSingleLine(true);
            category.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
                if (r - l != or - ol) v.post(() -> fitText((TextView) v, 16, v.getWidth(), 0));
            });
            tengah.addView(category, new LinearLayout.LayoutParams(-1, -2));

            // Status (Dilayani / Dipanggil); hanya terlihat bila loket memegang nomor.
            TextView status = text("", 17, Color.WHITE, true);
            status.setGravity(Gravity.CENTER);
            status.setSingleLine(true);
            status.setPadding(dp(5), dp(3), dp(5), dp(3));
            status.setTag("status");
            status.setVisibility(View.INVISIBLE);
            LinearLayout kolomStatus = new LinearLayout(this);
            kolomStatus.setGravity(Gravity.CENTER);
            kolomStatus.setPadding(0, 0, dp(8), 0);
            kolomStatus.addView(status, new LinearLayout.LayoutParams(-2, -2));
            isi.addView(kolomStatus, new LinearLayout.LayoutParams(dp(STATUS_KOLOM_DP), -1));

            GridLayout.LayoutParams params = new GridLayout.LayoutParams(
                    GridLayout.spec(i / kolom, portrait ? 0f : 1f),
                    GridLayout.spec(i % kolom, 1f));
            params.width = 0;
            params.height = portrait ? dp(CARD_TEGAK_DP) : 0;
            params.setMargins(dp(6), dp(portrait ? 4 : 6), dp(6), dp(portrait ? 4 : 6));
            grid.addView(card, params);
            cardsByCounter.put(name, card);
        }
    }

    /**
     * Buang dari daftar menunggu setiap nomor yang sudah dipanggil atau sedang
     * dipegang loket, lalu hitung ulang jumlah menunggu. Pengaman di sisi layar:
     * nomor yang sudah dilayani tidak boleh tampil sebagai menunggu di tema mana pun.
     */
    private JSONObject saring(JSONObject state) {
        JSONArray next = state.optJSONArray("next");
        if (next == null || next.length() == 0) return state;
        java.util.Set<String> sudah = new java.util.HashSet<>();
        JSONArray dipanggil = state.optJSONArray("called");
        for (int i = 0; dipanggil != null && i < dipanggil.length(); i++) {
            JSONObject d = dipanggil.optJSONObject(i);
            if (d != null) sudah.add(d.optString("n"));
        }
        JSONArray loket = state.optJSONArray("counters");
        for (int i = 0; loket != null && i < loket.length(); i++) {
            JSONObject l = loket.optJSONObject(i);
            if (l != null && !l.isNull("queue_number")) sudah.add(l.optString("queue_number"));
        }
        if (sudah.isEmpty()) return state;
        JSONArray baru = new JSONArray();
        int buang = 0;
        for (int i = 0; i < next.length(); i++) {
            String nomor = next.optString(i);
            if (sudah.contains(nomor)) buang++;
            else baru.put(nomor);
        }
        if (buang == 0) return state;
        JSONArray priorBaru = new JSONArray();
        JSONArray prior = state.optJSONArray("next_priority");
        for (int i = 0; prior != null && i < prior.length(); i++) {
            if (!sudah.contains(prior.optString(i))) priorBaru.put(prior.optString(i));
        }
        try {
            JSONObject salinan = new JSONObject(state.toString());
            salinan.put("next", baru);
            salinan.put("next_priority", priorBaru);
            salinan.put("total_waiting", Math.max(0, state.optInt("total_waiting") - buang));
            return salinan;
        } catch (org.json.JSONException e) {
            return state;
        }
    }

    private void applyState(JSONObject asli) {
        JSONObject state = saring(asli);
        lastState = state;
        // Judul dari server sengaja diabaikan: identitas tidak dapat diubah.
        if (!NAMA_TAMPIL.contentEquals(title.getText())) {
            title.setText(NAMA_TAMPIL);
            title.post(() -> fitText(title, 30, title.getWidth(), 0));
        }
        soundEnabled = state.optBoolean("sound_enabled", true);
        String zone = state.optString("timezone", DEFAULT_TIMEZONE);
        serverTimezone = zone.startsWith("Asia/") ? zone : DEFAULT_TIMEZONE;
        long serverTime = state.optLong("server_time_ms", 0L);
        if (serverTime > 0L) serverOffsetMillis = serverTime - System.currentTimeMillis();

        if (tema != null) {
            tema.terapkan(state);
            applyVersion(state);
            syncSoundPack(state.optString("sound_pack_version", ""));
            return;
        }

        JSONArray counters = state.optJSONArray("counters");
        if (counters == null) counters = new JSONArray();
        StringBuilder signature = new StringBuilder();
        for (int i = 0; i < counters.length(); i++) {
            JSONObject counter = counters.optJSONObject(i);
            signature.append(counter == null ? "" : counter.optString("name")).append('|');
        }
        if (!signature.toString().equals(countersSignature)) {
            countersSignature = signature.toString();
            buildCards(counters);
        }
        long now = System.currentTimeMillis();
        for (int i = 0; i < counters.length(); i++) {
            JSONObject counter = counters.optJSONObject(i);
            if (counter == null) continue;
            LinearLayout card = cardsByCounter.get(counter.optString("name"));
            if (card == null) continue;
            TextView number = card.findViewWithTag("number");
            TextView category = card.findViewWithTag("category");
            boolean ada = !counter.isNull("queue_number");
            String value = ada ? counter.optString("queue_number")
                    : teksLoketTanpaPanggilan(counter.optString("status", "KOSONG"));
            boolean changed = !value.contentEquals(number.getText())
                    || number.getCurrentTextColor() != (ada ? INK : MUTED);
            number.setText(value);
            number.setTextColor(ada ? INK : MUTED);
            category.setText(ada && !counter.isNull("category") ? counter.optString("category") : " ");
            category.post(() -> fitText(category, 16, category.getWidth(), 0));
            TextView status = card.findViewWithTag("status");
            String label = counter.optString("status", "");
            status.setVisibility(ada ? View.VISIBLE : View.INVISIBLE);
            if (ada) {
                status.setText(label.toUpperCase(Locale.ROOT));
                // Lebar isi pil dibatasi kolomnya; huruf dikecilkan bila "DIPANGGIL" tidak muat.
                fitText(status, 17, (int) ((dp(STATUS_KOLOM_DP) - dp(8) - dp(10)) / 0.92f), 0);
                boolean dilayani = "Dilayani".equalsIgnoreCase(label);
                status.setTextColor(dilayani ? TEAL : Color.WHITE);
                status.setBackground(rounded(dilayani ? Color.WHITE : AMBER, dp(10)));
            }
            aturDenyut(counter.optString("name"), status, ada && "Dipanggil".equalsIgnoreCase(label));
            if (changed) number.post(() -> fitNumber(number));
            Long until = highlightUntil.get(counter.optString("name"));
            boolean hot = until != null && until > now;
            card.setBackground(kartu(hot));
        }

        applyNext(state);
        applyVersion(state);
        syncSoundPack(state.optString("sound_pack_version", ""));
    }

    // -----------------------------------------------------------------
    // "Berikutnya": 10 baris, bergantian halaman bila lebih banyak
    // -----------------------------------------------------------------

    private int perRow() {
        return portrait ? 3 : 2;
    }

    private int nextRowHeight() {
        Paint paint = new Paint();
        paint.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        paint.setTextSize(spToPx(sp(nextSp)));
        Paint.FontMetricsInt metrics = paint.getFontMetricsInt();
        // Padding pil (10dp) dan jarak antarpil (4dp).
        return metrics.bottom - metrics.top + dp(14);
    }

    private int fixedSideHeight() {
        return side.getPaddingTop() + side.getPaddingBottom()
                + nextHeader.getLineHeight()
                + dp(AKAN_DP) + dp(1)
                + listHeader.getLineHeight() + listHeader.getPaddingTop() + listHeader.getPaddingBottom()
                + moreLabel.getLineHeight() + moreLabel.getPaddingTop();
    }

    /**
     * Berapa baris nomor yang boleh tampil. Sepuluh baris selalu dijatah:
     * bila tinggi layar tidak cukup, huruf dikecilkan (tidak lebih kecil
     * dari NEXT_SP_MIN) sebelum barisnya dikurangi.
     */
    private int nextRowsAllowed(int wanted) {
        int limit = Math.min(wanted, NEXT_BARIS);
        if (limit == 0) return 0;
        int board = body.getHeight() - body.getPaddingTop() - body.getPaddingBottom();
        if (board <= 0) return Math.min(limit, 1);  // belum diukur; dihitung ulang pada polling berikutnya
        nextSp = NEXT_SP;
        int rowHeight = nextRowHeight();
        int dipakaiLoket = 0;
        if (portrait) {
            // Strip loket setinggi tetap; daftar menempati seluruh sisanya.
            dipakaiLoket = Math.max(1, grid.getRowCount()) * dp(CARD_TEGAK_DP + 8) + dp(10);
        }
        int ruang = board - dipakaiLoket - fixedSideHeight();
        if (ruang < NEXT_BARIS * rowHeight) {
            nextSp = Math.max(NEXT_SP_MIN, NEXT_SP * ruang / (float) (NEXT_BARIS * rowHeight));
            rowHeight = nextRowHeight();
        }
        int fit = ruang / Math.max(1, rowHeight);
        return Math.max(1, Math.min(limit, fit));
    }

    private void applyNext(JSONObject state) {
        JSONArray next = state.optJSONArray("next");
        java.util.Set<String> prioritas = new java.util.HashSet<>();
        JSONArray prioritasRows = state.optJSONArray("next_priority");
        for (int i = 0; prioritasRows != null && i < prioritasRows.length(); i++) {
            prioritas.add(prioritasRows.optString(i));
        }
        int semua = next == null ? 0 : next.length();
        int jumlahAkan = Math.min(AKAN_JUMLAH, semua);
        for (int i = 0; i < AKAN_JUMLAH; i++) {
            String nomor = i < jumlahAkan ? next.optString(i) : "";
            NomorMenunggu pil = akanPil[i];
            pil.setGayaAkan(!nomor.isEmpty(), prioritas.contains(nomor), i == 0);
            String teks = nomor.isEmpty() ? "\u2013" : nomor;
            if (!teks.contentEquals(pil.getText())) {
                pil.setText(teks);
                final float besar = i == 0 ? 30 : 26;
                pil.post(() -> fitText(pil, besar, pil.getWidth() - dp(8), 0));
            }
        }
        // Daftar bawah dimulai dari nomor ke-4; tiga teratas tidak diulang.
        int available = Math.max(0, semua - jumlahAkan);
        int per = perRow();
        int wanted = (int) Math.ceil(available / (double) per);
        int rows = nextRowsAllowed(wanted);
        int perHalaman = Math.max(1, rows * per);
        halamanTotal = Math.max(1, (int) Math.ceil(available / (double) perHalaman));
        if (halaman >= halamanTotal) halaman = 0;
        int awal = halaman * perHalaman;
        int shown = Math.max(0, Math.min(available - awal, perHalaman));

        if (rows != nextRowsShown || nextSp != nextSpDibangun) {
            // Hanya saat jumlah BARIS berubah kartu ikut bergerak, dan geraknya halus.
            if (nextRowsShown >= 0) {
                AutoTransition transition = new AutoTransition();
                transition.setDuration(200);
                TransitionManager.beginDelayedTransition(body, transition);
            }
            nextRowsShown = rows;
            nextSpDibangun = nextSp;
            nextList.removeAllViews();
            for (int r = 0; r < rows; r++) {
                LinearLayout row = new LinearLayout(this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                for (int c = 0; c < per; c++) {
                    NomorMenunggu cell = new NomorMenunggu(this);
                    cell.setText("");
                    cell.setTextSize(nextSp);
                    cell.setTextColor(INK);
                    cell.setGravity(Gravity.CENTER);
                    cell.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
                    cell.setPadding(dp(4), dp(5), dp(4), dp(5));
                    LinearLayout.LayoutParams pil = new LinearLayout.LayoutParams(0, -2, 1);
                    pil.setMargins(dp(3), dp(2), dp(3), dp(2));
                    row.addView(cell, pil);
                }
                nextList.addView(row);
            }
        }
        for (int i = 0; i < rows * per; i++) {
            LinearLayout row = (LinearLayout) nextList.getChildAt(i / per);
            NomorMenunggu cell = (NomorMenunggu) row.getChildAt(i % per);
            String value = i < shown ? next.optString(jumlahAkan + awal + i) : "";
            cell.setGaya(!value.isEmpty(), prioritas.contains(value), false, false);
            if (!value.contentEquals(cell.getText())) {
                cell.setText(value);
                cell.post(() -> fitText(cell, nextSp, cell.getWidth(), 0));
            }
        }
        if (halamanTotal > 1) {
            StringBuilder titik = new StringBuilder();
            for (int h = 0; h < halamanTotal && h < 10; h++) titik.append(h == halaman ? "\u25CF " : "\u25CB ");
            moreLabel.setText(titik + " Halaman " + (halaman + 1) + " dari " + halamanTotal
                    + " \u00B7 " + Math.max(0, state.optInt("total_waiting") - jumlahAkan) + " menunggu");
        } else {
            int lainnya = Math.max(0, state.optInt("total_waiting") - jumlahAkan) - shown;
            moreLabel.setText(lainnya > 0 ? "dan " + lainnya + " lainnya menunggu"
                    : semua == 0 ? "Tidak ada yang menunggu" : "");
        }
    }

    /** Ganti halaman nomor menunggu tiap HALAMAN_MS dengan transisi pudar. */
    private final Runnable balikBarisTugas = new Runnable() {
        @Override
        public void run() {
            handler.postDelayed(this, BALIK_MS);
            if (tema != null) tema.balikBaris();
        }
    };

    private final Runnable putarHalaman = new Runnable() {
        @Override
        public void run() {
            handler.postDelayed(this, HALAMAN_MS);
            if (tema != null) {
                tema.putarHalaman();
                return;
            }
            if (lastState == null || halamanTotal <= 1 || nextList == null) return;
            halaman = (halaman + 1) % halamanTotal;
            nextList.animate().alpha(0f).setDuration(250).withEndAction(() -> {
                if (lastState != null) applyNext(lastState);
                nextList.animate().alpha(1f).setDuration(250).start();
            }).start();
        }
    };

    // -----------------------------------------------------------------

    private void showBanner(String message) {
        bannerMessage = message;
        banner.setText(message);
        banner.setVisibility(View.VISIBLE);
    }

    private void hideBanner() {
        bannerMessage = null;
        banner.setVisibility(View.GONE);
    }

    private void setConnected(boolean connected) {
        if (connected) {
            if (failures >= FAILURES_BEFORE_BANNER) {
                // Tersambung lagi: panggilan selama terputus TIDAK dibunyikan.
                lastCallId = null;
            }
            failures = 0;
            disconnectedSince = 0;
            hideBanner();
            body.setAlpha(1f);
            return;
        }
        failures++;
        if (disconnectedSince == 0) disconnectedSince = now();
        if (failures >= FAILURES_BEFORE_BANNER) {
            body.setAlpha(0.55f);
            speechQueue.clear();
            SimpleDateFormat jam = new SimpleDateFormat("HH:mm", new Locale("id", "ID"));
            jam.setTimeZone(TimeZone.getTimeZone(serverTimezone));
            showBanner("Terputus dari server sejak " + jam.format(new Date(disconnectedSince))
                    + " — mencoba menyambung lagi…");
        }
    }

    private long now() {
        return System.currentTimeMillis() + serverOffsetMillis;
    }

    private final Runnable clockTick = new Runnable() {
        @Override
        public void run() {
            SimpleDateFormat format = new SimpleDateFormat(
                    "EEEE, d MMMM yyyy · HH:mm:ss", new Locale("id", "ID"));
            format.setTimeZone(TimeZone.getTimeZone(serverTimezone));
            String label = "Asia/Makassar".equals(serverTimezone) ? "WITA"
                    : "Asia/Jayapura".equals(serverTimezone) ? "WIT" : "WIB";
            clock.setText(format.format(new Date(now())) + " " + label);
            handler.postDelayed(this, 1000);
        }
    };

    // Geser isi beberapa piksel tiap 5 menit supaya layar tidak terbakar.
    private final Runnable burnInShift = new Runnable() {
        @Override
        public void run() {
            int[][] langkah = {{0, 0}, {4, 0}, {4, 4}, {0, 4}};
            shiftStep = (shiftStep + 1) % langkah.length;
            root.setTranslationX(dp(langkah[shiftStep][0]));
            root.setTranslationY(dp(langkah[shiftStep][1]));
            handler.postDelayed(this, 5 * 60 * 1000L);
        }
    };

    // =================================================================
    // Jaringan
    // =================================================================

    private boolean isPaired() {
        return !preferences.getString(SERVER, "").trim().isEmpty()
                && !preferences.getString(TOKEN, "").trim().isEmpty();
    }

    private String deviceId() {
        String id = preferences.getString(DEVICE_ID, "");
        if (id.isEmpty()) {
            id = UUID.randomUUID().toString();
            preferences.edit().putString(DEVICE_ID, id).apply();
        }
        return id;
    }

    private String deviceName() {
        String name = preferences.getString(DEVICE_NAME, "").trim();
        return name.isEmpty() ? ("Layar " + Build.MODEL) : name;
    }

    private int appVersionCode() {
        try {
            android.content.pm.PackageInfo info =
                    getPackageManager().getPackageInfo(getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? (int) info.getLongVersionCode() : info.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    private String appVersionName() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "?";
        }
    }

    /** Sambungan ke server dengan kepala permintaan perangkat ini. */
    private HttpURLConnection open(String path, int readTimeoutMs) throws IOException {
        String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
        // Token tidak dikirim tanpa enkripsi ke luar jaringan lokal (AlamatServer).
        if (!AlamatServer.aman(base)) throw new IOException(AlamatServer.PESAN_DITOLAK);
        HttpURLConnection connection = (HttpURLConnection) new URL(base + path).openConnection();
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(readTimeoutMs);
        connection.setRequestProperty("Authorization",
                "Bearer " + preferences.getString(TOKEN, ""));
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("X-Device-Id", deviceId());
        connection.setRequestProperty("X-Device-Name", deviceName());
        connection.setRequestProperty("X-Device-Kind", DEVICE_KIND);
        connection.setRequestProperty("X-App-Version-Code", String.valueOf(appVersionCode()));
        connection.setRequestProperty("X-App-Version-Name", appVersionName());
        return connection;
    }

    private static byte[] readAll(InputStream stream) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        if (stream == null) return output.toByteArray();
        try (InputStream input = stream) {
            byte[] buffer = new byte[8192];
            int length;
            while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
        }
        return output.toByteArray();
    }

    private interface Done {
        void accept(int code, Object body);
    }

    /** Permintaan HTTP di utas pekerja; hasil kembali ke utas tampilan. */
    private void request(String method, String path, JSONObject payload, Done done) {
        worker.execute(() -> {
            int code;
            Object parsed = null;
            HttpURLConnection connection = null;
            try {
                connection = open(path, 5000);
                connection.setRequestMethod(method);
                if (payload != null) {
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    connection.getOutputStream().write(payload.toString().getBytes(StandardCharsets.UTF_8));
                }
                code = connection.getResponseCode();
                InputStream stream = code < 400 ? connection.getInputStream() : connection.getErrorStream();
                String text = new String(readAll(stream), StandardCharsets.UTF_8);
                parsed = text.isEmpty() ? null : new JSONTokener(text).nextValue();
            } catch (Exception e) {
                code = -1;
            } finally {
                if (connection != null) connection.disconnect();
            }
            final int finalCode = code;
            final Object finalBody = parsed;
            handler.post(() -> done.accept(finalCode, finalBody));
        });
    }

    private boolean segarkanLagi;

    private void ambilState() {
        if (!isPaired()) return;
        if (stateInFlight) {
            // Jawaban yang sedang berjalan bisa lebih lama dari panggilan terbaru: ulangi sesudahnya.
            segarkanLagi = true;
            return;
        }
        stateInFlight = true;
        request("GET", "/v1/layar/state?next=" + NEXT_MAX, null, (code, response) -> {
            stateInFlight = false;
            if (code == 200 && response instanceof JSONObject) {
                setConnected(true);
                applyState((JSONObject) response);
            } else if (code == 401) {
                showBanner("Layar ini belum dipasangkan atau sudah dicabut. "
                        + "Tahan judul 3 detik untuk memasangkan.");
                dimBody();
            } else {
                setConnected(false);
            }
            if (segarkanLagi) {
                segarkanLagi = false;
                ambilState();
            }
        });
    }

    private final Runnable statePoll = new Runnable() {
        @Override
        public void run() {
            handler.postDelayed(this, STATE_INTERVAL_MS);
            ambilState();
        }
    };

    private void dimBody() {
        body.setAlpha(0.55f);
        speechQueue.clear();
    }

    private final Runnable callsPoll = new Runnable() {
        @Override
        public void run() {
            handler.postDelayed(this, CALLS_INTERVAL_MS);
            if (!isPaired() || callsInFlight || failures >= FAILURES_BEFORE_BANNER) return;
            callsInFlight = true;
            String path = lastCallId == null ? "/v1/layar/calls" : "/v1/layar/calls?after=" + lastCallId;
            final boolean first = lastCallId == null;
            request("GET", path, null, (code, response) -> {
                callsInFlight = false;
                if (code != 200 || !(response instanceof JSONObject)) return;
                JSONObject json = (JSONObject) response;
                lastCallId = json.optLong("last_id", lastCallId == null ? 0 : lastCallId);
                if (first) return;
                JSONArray calls = json.optJSONArray("calls");
                if (calls == null) return;
                for (int i = 0; i < calls.length(); i++) announce(calls.optJSONObject(i));
            });
        }
    };

    // =================================================================
    // Suara
    // =================================================================

    /** Kedip singkat kartu loket yang baru memanggil, supaya mata tertarik ke sana. */
    private void kedipkan(View kartu) {
        android.animation.ObjectAnimator kedip =
                android.animation.ObjectAnimator.ofFloat(kartu, View.ALPHA, 1f, 0.35f);
        kedip.setDuration(300);
        kedip.setRepeatCount(5);
        kedip.setRepeatMode(android.animation.ValueAnimator.REVERSE);
        kedip.addListener(new android.animation.AnimatorListenerAdapter() {
            @Override public void onAnimationEnd(android.animation.Animator a) { kartu.setAlpha(1f); }
            @Override public void onAnimationCancel(android.animation.Animator a) { kartu.setAlpha(1f); }
        });
        kartu.setAlpha(1f);
        kedip.start();
    }

    private void announce(JSONObject call) {
        if (call == null) return;
        String counter = call.optString("counter_name");
        highlightUntil.put(counter, System.currentTimeMillis() + HIGHLIGHT_MS);
        if (tema != null) tema.panggilanBaru(call);
        // Nomor yang baru dipanggil harus segera hilang dari daftar menunggu.
        ambilState();
        LinearLayout card = cardsByCounter.get(counter);
        if (card != null) {
            TextView number = card.findViewWithTag("number");
            number.setText(call.optString("queue_number"));
            number.setTextColor(INK);
            number.post(() -> fitNumber(number));
            card.setBackground(kartu(true));
            kedipkan(card);
        }
        if (!soundEnabled) return;
        try {
            call.put("_received_ms", System.currentTimeMillis());
        } catch (org.json.JSONException ignored) {
            // Tanpa catatan waktu, panggilan dianggap baru.
        }
        speechQueue.add(call);
        while (speechQueue.size() > MAX_SPEECH_QUEUE) speechQueue.poll();
        speakNext();
    }

    /**
     * Bunyikan panggilan berikutnya. Urutan pilihan suara:
     *   1. TTS perangkat, bila punya Bahasa Indonesia;
     *   2. paket suara dari server (klip WAV disambung);
     *   3. nada saja.
     */
    private void speakNext() {
        if (speaking) return;
        JSONObject call = nextFreshCall();
        if (call == null) return;
        speaking = true;
        if (tone != null) tone.startTone(ToneGenerator.TONE_PROP_BEEP2, 600);
        // Jeda sesudah nada, supaya kata pertama tidak tertelan nadanya.
        handler.postDelayed(() -> {
            String text = call == null ? "" : call.optString("text");
            JSONArray tokens = call == null ? null : call.optJSONArray("tokens");
            if (ttsReady && !text.isEmpty()) {
                int hasil = tts.speak(text, TextToSpeech.QUEUE_FLUSH, new Bundle(),
                        UUID.randomUUID().toString());
                if (hasil != TextToSpeech.SUCCESS) finishSpeech(1500);
            } else if (!packClips.isEmpty() && tokens != null && tokens.length() > 0) {
                playTokens(tokens, 0);
            } else {
                finishSpeech(1500);
            }
        }, 900);
    }

    /**
     * Panggilan berikutnya yang belum basi. Panel yang tertinggal (lima loket
     * memanggil bersamaan, atau Wi-Fi sempat putus) melewati yang sudah lama
     * daripada mengumumkan nomor yang orangnya mungkin sudah di loket.
     */
    private JSONObject nextFreshCall() {
        long now = System.currentTimeMillis();
        while (!speechQueue.isEmpty()) {
            JSONObject call = speechQueue.poll();
            if (call == null) continue;
            double age = call.optDouble("age_seconds", 0)
                    + (now - call.optLong("_received_ms", now)) / 1000.0;
            if (age <= MAX_CALL_AGE_SECONDS) return call;
        }
        return null;
    }

    private void finishSpeech(long delayMs) {
        speaking = false;
        if (delayMs <= 0) {
            speakNext();
        } else {
            handler.postDelayed(this::speakNext, delayMs);
        }
    }

    /** Putar klip paket suara satu per satu; `_jeda` = diam sejenak, klip hilang dilewati. */
    private void playTokens(JSONArray tokens, int index) {
        if (index >= tokens.length()) {
            finishSpeech(600);
            return;
        }
        String token = tokens.optString(index);
        if (JEDA.equals(token)) {
            handler.postDelayed(() -> playTokens(tokens, index + 1), 250);
            return;
        }
        String name = packClips.get(token);
        File clip = name == null ? null : new File(packDir(), name);
        if (clip == null || !clip.isFile()) {
            playTokens(tokens, index + 1);
            return;
        }
        releasePlayer();
        try {
            MediaPlayer media = new MediaPlayer();
            player = media;
            media.setAudioStreamType(AudioManager.STREAM_MUSIC);
            media.setDataSource(clip.getAbsolutePath());
            media.setOnCompletionListener(p -> {
                releasePlayer();
                playTokens(tokens, index + 1);
            });
            media.setOnErrorListener((p, what, extra) -> {
                releasePlayer();
                playTokens(tokens, index + 1);
                return true;
            });
            media.prepare();
            media.start();
        } catch (Exception e) {
            releasePlayer();
            playTokens(tokens, index + 1);
        }
    }

    private void releasePlayer() {
        if (player == null) return;
        try {
            player.release();
        } catch (RuntimeException ignored) {
            // Sudah dilepas.
        }
        player = null;
    }

    private File packDir() {
        return new File(getFilesDir(), "suara");
    }

    private void loadPack() {
        packClips.clear();
        File index = new File(packDir(), "paket.json");
        if (!index.isFile()) return;
        try (FileInputStream input = new FileInputStream(index)) {
            JSONObject json = new JSONObject(new String(readAll(input), StandardCharsets.UTF_8));
            JSONObject clips = json.optJSONObject("clips");
            if (clips == null) return;
            Iterator<String> keys = clips.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                packClips.put(key, clips.optString(key));
            }
        } catch (Exception e) {
            packClips.clear();
        }
    }

    private static void deleteTree(File file) {
        File[] children = file.listFiles();
        if (children != null) for (File child : children) deleteTree(child);
        //noinspection ResultOfMethodCallIgnored
        file.delete();
    }

    /**
     * Unduh paket suara bila versinya di server berubah. Panel yang punya
     * TTS Bahasa Indonesia tidak membutuhkannya. Paket baru diunduh ke
     * folder sementara dan baru menggantikan yang lama sesudah lengkap.
     */
    private void syncSoundPack(String serverVersion) {
        if (serverVersion.isEmpty() || !ttsChecked || ttsReady || packDownloading) return;
        if (serverVersion.equals(preferences.getString(PACK_VERSION, "")) && !packClips.isEmpty()) return;
        if (System.currentTimeMillis() < packRetryAt) return;
        packDownloading = true;
        downloader.execute(() -> {
            String version = null;
            File staging = new File(getFilesDir(), "suara-baru");
            try {
                HttpURLConnection connection = open("/v1/layar/sound", 10000);
                JSONObject index;
                try {
                    if (connection.getResponseCode() != 200) throw new IOException("indeks paket");
                    index = new JSONObject(new String(
                            readAll(connection.getInputStream()), StandardCharsets.UTF_8));
                } finally {
                    connection.disconnect();
                }
                deleteTree(staging);
                if (!staging.mkdirs()) throw new IOException("folder paket");
                JSONObject clips = index.getJSONObject("clips");
                Iterator<String> keys = clips.keys();
                while (keys.hasNext()) {
                    String file = clips.getString(keys.next());
                    if (!file.matches("[A-Za-z0-9_.-]+")) {
                        throw new IOException("nama klip paket tidak sah");
                    }
                    HttpURLConnection clip = open("/v1/layar/sound/"
                            + URLEncoder.encode(file, "UTF-8"), 15000);
                    try {
                        if (clip.getResponseCode() != 200) {
                            throw new IOException("klip paket tidak lengkap: " + file);
                        }
                        long expected = clip.getContentLengthLong();
                        try (InputStream input = clip.getInputStream();
                             OutputStream output = new FileOutputStream(new File(staging, file))) {
                            byte[] buffer = new byte[16 * 1024];
                            int length;
                            while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
                        }
                        File downloaded = new File(staging, file);
                        if (expected >= 0 && downloaded.length() != expected) {
                            throw new IOException("unduhan klip terputus: " + file);
                        }
                    } finally {
                        clip.disconnect();
                    }
                }
                try (OutputStream output = new FileOutputStream(new File(staging, "paket.json"))) {
                    output.write(index.toString().getBytes(StandardCharsets.UTF_8));
                }
                File target = packDir();
                deleteTree(target);
                if (!staging.renameTo(target)) throw new IOException("pasang paket");
                version = index.optString("version");
            } catch (Exception e) {
                deleteTree(staging);
            }
            final String done = version;
            handler.post(() -> {
                packDownloading = false;
                if (done == null) {
                    packRetryAt = System.currentTimeMillis() + PACK_RETRY_MS;
                    return;
                }
                preferences.edit().putString(PACK_VERSION, done).apply();
                loadPack();
            });
        });
    }

    // =================================================================
    // Pembaruan APK
    // =================================================================

    private void applyVersion(JSONObject state) {
        minVersionCode = state.optInt("app_min_version_code", 0);
        latestVersionCode = state.optInt("app_latest_version_code", 0);
        latestVersionName = state.optString("app_latest_version_name", "");
        if (appVersionCode() < minVersionCode) {
            showBanner("Aplikasi layar perlu diperbarui"
                    + (latestVersionName.isEmpty() ? "" : " ke versi " + latestVersionName)
                    + ". Tahan judul 3 detik, lalu tekan Perbarui.");
        }
    }

    private boolean updateAvailable() {
        return latestVersionCode > appVersionCode();
    }

    private void startUpdate() {
        if (updating) return;
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            Toast.makeText(this,
                    "Izinkan \"Pasang aplikasi tidak dikenal\" untuk Layar Antrian, "
                            + "lalu kembali dan tekan Perbarui lagi.",
                    Toast.LENGTH_LONG).show();
            startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getPackageName())));
            return;
        }
        // Layar yang disematkan tidak bisa menampilkan konfirmasi pemasangan.
        if (isLocked()) {
            try {
                stopLockTask();
            } catch (RuntimeException ignored) {
                // Tidak disematkan oleh aplikasi ini.
            }
        }
        updating = true;
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(20), dp(12), dp(20), dp(4));
        ProgressBar bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(1000);
        panel.addView(bar, new LinearLayout.LayoutParams(-1, dp(16)));
        TextView progress = new TextView(this);
        progress.setText("Menghubungi server…");
        progress.setPadding(0, dp(8), 0, 0);
        panel.addView(progress);
        updateDialog = new AlertDialog.Builder(this)
                .setTitle("Memperbarui ke versi " + latestVersionName)
                .setView(panel)
                .setCancelable(false)
                .create();
        updateDialog.show();

        downloader.execute(() -> {
            HttpURLConnection connection = null;
            PackageInstaller.Session session = null;
            try {
                connection = open("/v1/layar/app/apk", 30000);
                int code = connection.getResponseCode();
                if (code != 200) throw new IllegalStateException("server menjawab " + code);
                long total = connection.getContentLengthLong();

                PackageInstaller installer = getPackageManager().getPackageInstaller();
                PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                        PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(getPackageName());
                if (total > 0) params.setSize(total);
                int sessionId = installer.createSession(params);
                session = installer.openSession(sessionId);
                try (InputStream input = connection.getInputStream();
                     OutputStream output = session.openWrite("layar.apk", 0, total)) {
                    byte[] buffer = new byte[64 * 1024];
                    long done = 0;
                    long lastPost = 0;
                    int length;
                    while ((length = input.read(buffer)) != -1) {
                        output.write(buffer, 0, length);
                        done += length;
                        long now = System.currentTimeMillis();
                        if (now - lastPost > 200) {
                            lastPost = now;
                            final long current = done;
                            handler.post(() -> {
                                if (total > 0) bar.setProgress((int) (current * 1000 / total));
                                progress.setText(String.format(new Locale("id", "ID"),
                                        "%.1f MB%s", current / 1048576.0,
                                        total > 0 ? String.format(new Locale("id", "ID"),
                                                " dari %.1f MB", total / 1048576.0) : ""));
                            });
                        }
                    }
                    session.fsync(output);
                }
                Intent status = new Intent(ACTION_INSTALL_STATUS).setPackage(getPackageName());
                int flags = PendingIntent.FLAG_UPDATE_CURRENT
                        | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                PendingIntent pending = PendingIntent.getBroadcast(this, sessionId, status, flags);
                session.commit(pending.getIntentSender());
                session.close();
                session = null;
                handler.post(() -> {
                    bar.setProgress(1000);
                    progress.setText("Memasang… setujui di layar Android.");
                });
            } catch (Exception e) {
                if (session != null) session.abandon();
                String message = e.getMessage() == null ? "server tidak dapat dihubungi" : e.getMessage();
                handler.post(() -> finishUpdate("Unduhan gagal: " + message));
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private void finishUpdate(String message) {
        updating = false;
        if (updateDialog != null) {
            updateDialog.dismiss();
            updateDialog = null;
        }
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    // =================================================================
    // Kunci aplikasi (sematkan layar)
    // =================================================================

    private boolean isLocked() {
        ActivityManager manager = (ActivityManager) getSystemService(ACTIVITY_SERVICE);
        return manager != null
                && manager.getLockTaskModeState() != ActivityManager.LOCK_TASK_MODE_NONE;
    }

    /**
     * Tutup aplikasi sepenuhnya. Kunci aplikasi dilepas dulu: aplikasi yang
     * masih disematkan tidak dapat ditinggalkan. Menyala lagi saat perangkat
     * dinyalakan ulang (BootReceiver) atau dibuka dari daftar aplikasi.
     */
    private void konfirmasiKeluar(AlertDialog pengaturan) {
        new AlertDialog.Builder(this)
                .setTitle("Keluar dari aplikasi?")
                .setMessage("Layar berhenti menampilkan antrian dan membunyikan "
                        + "panggilan sampai aplikasi dibuka lagi.")
                .setNegativeButton("Batal", null)
                .setPositiveButton("Keluar", (d, w) -> {
                    pengaturan.dismiss();
                    if (isLocked()) {
                        try {
                            stopLockTask();
                        } catch (RuntimeException ignored) {
                            // Tidak disematkan oleh aplikasi ini.
                        }
                    }
                    finishAndRemoveTask();
                })
                .show();
    }

    private void toggleLock() {
        try {
            if (isLocked()) {
                stopLockTask();
                Toast.makeText(this, "Kunci aplikasi dibuka.", Toast.LENGTH_LONG).show();
            } else {
                // Tanpa device owner Android menampilkan konfirmasi "sematkan aplikasi".
                startLockTask();
            }
        } catch (RuntimeException e) {
            Toast.makeText(this, "Kunci aplikasi tidak didukung perangkat ini.",
                    Toast.LENGTH_LONG).show();
        }
    }

    // =================================================================
    // Pengaturan dan pemasangan
    // =================================================================

    private void showSettings() {
        LinearLayout fields = new LinearLayout(this);
        fields.setOrientation(LinearLayout.VERTICAL);
        fields.setPadding(dp(20), dp(4), dp(20), 0);
        EditText server = new EditText(this);
        server.setHint("Alamat server, contoh http://192.168.1.10:8765");
        server.setSingleLine(true);
        server.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        server.setText(preferences.getString(SERVER, ""));
        fields.addView(server);
        Button find = new Button(this);
        find.setText("Cari server otomatis");
        fields.addView(find);
        EditText name = new EditText(this);
        name.setHint("Nama layar, contoh Layar Ruang Tunggu");
        name.setSingleLine(true);
        name.setText(deviceName());
        fields.addView(name);
        EditText code = new EditText(this);
        code.setHint("Kode pasang 6 angka dari Layanan Anjungan");
        code.setSingleLine(true);
        code.setInputType(InputType.TYPE_CLASS_NUMBER);
        fields.addView(code);
        TextView info = new TextView(this);
        info.setText("Kode dibuat di komputer server: Layanan Anjungan → Perangkat → "
                + "Tambah perangkat. Kosongkan kode bila hanya mengganti nama.");
        fields.addView(info);

        TextView temaJudul = new TextView(this);
        temaJudul.setText("Tema tampilan (hanya untuk layar ini)");
        temaJudul.setPadding(0, dp(12), 0, 0);
        fields.addView(temaJudul);
        String[] namaTema = new String[TEMA_DAFTAR.length];
        int terpilih = 0;
        String temaSekarang = preferences.getString(TEMA, TEMA_BENING);
        for (int i = 0; i < TEMA_DAFTAR.length; i++) {
            namaTema[i] = TEMA_DAFTAR[i][1];
            if (TEMA_DAFTAR[i][0].equals(temaSekarang)) terpilih = i;
        }
        android.widget.Spinner temaPilih = new android.widget.Spinner(this);
        temaPilih.setAdapter(new android.widget.ArrayAdapter<>(this,
                android.R.layout.simple_spinner_dropdown_item, namaTema));
        temaPilih.setSelection(terpilih, false);
        fields.addView(temaPilih);
        TextView temaInfo = new TextView(this);
        temaInfo.setText(TEMA_DAFTAR[terpilih][2]);
        fields.addView(temaInfo);
        temaPilih.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(android.widget.AdapterView<?> parent, View view, int posisi, long id) {
                String baru = TEMA_DAFTAR[posisi][0];
                temaInfo.setText(TEMA_DAFTAR[posisi][2]);
                if (baru.equals(preferences.getString(TEMA, TEMA_BENING))) return;
                preferences.edit().putString(TEMA, baru).apply();
                susunUlang();
            }

            @Override
            public void onNothingSelected(android.widget.AdapterView<?> parent) { }
        });

        TextView version = new TextView(this);
        String suara = ttsReady ? "TTS perangkat (Bahasa Indonesia)"
                : !packClips.isEmpty() ? "paket suara server (" + packClips.size() + " klip)"
                : "nada saja";
        version.setText("Versi aplikasi " + appVersionName() + " (" + appVersionCode() + ")"
                + " · Suara: " + suara);
        version.setPadding(0, dp(10), 0, 0);
        fields.addView(version);

        Button update = new Button(this);
        update.setText("Perbarui ke versi " + latestVersionName);
        update.setVisibility(updateAvailable() ? View.VISIBLE : View.GONE);
        fields.addView(update);

        Button keluar = new Button(this);
        keluar.setText("Keluar dari aplikasi");
        fields.addView(keluar);

        find.setOnClickListener(v -> {
            find.setEnabled(false);
            find.setText("Mencari…");
            discoverServer(address -> {
                server.setText(address);
                find.setEnabled(true);
                find.setText("Cari server otomatis");
            }, message -> {
                find.setEnabled(true);
                find.setText("Cari server otomatis");
                Toast.makeText(this, message, Toast.LENGTH_LONG).show();
            });
        });

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("Pengaturan layar antrian")
                .setView(fields)
                .setPositiveButton("Simpan", null)
                .setNegativeButton("Tutup", null)
                .setNeutralButton(isLocked() ? "Buka kunci" : "Kunci aplikasi", (d, w) -> toggleLock())
                .create();
        update.setOnClickListener(v -> {
            dialog.dismiss();
            startUpdate();
        });
        keluar.setOnClickListener(v -> konfirmasiKeluar(dialog));
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String address = server.getText().toString().trim();
            String digits = code.getText().toString().replaceAll("[^0-9]", "");
            if (!(address.startsWith("http://") || address.startsWith("https://"))) {
                server.setError("Alamat harus diawali http://");
                return;
            }
            if (!AlamatServer.aman(address)) {
                server.setError(AlamatServer.PESAN_DITOLAK);
                return;
            }
            if (digits.isEmpty() && isPaired() && address.equals(preferences.getString(SERVER, ""))) {
                // Hanya ganti nama; token lama tetap dipakai.
                preferences.edit().putString(DEVICE_NAME, name.getText().toString().trim()).apply();
                footerName.setText(deviceName());
                dialog.dismiss();
                return;
            }
            if (digits.length() != 6) {
                code.setError("Kode pasang 6 angka");
                return;
            }
            preferences.edit()
                    .putString(SERVER, address)
                    .putString(DEVICE_NAME, name.getText().toString().trim())
                    .apply();
            footerName.setText(deviceName());
            try {
                JSONObject payload = new JSONObject()
                        .put("code", digits)
                        .put("device_id", deviceId())
                        .put("name", deviceName())
                        .put("kind", DEVICE_KIND);
                request("POST", "/v1/kiosk/pair", payload, (status, response) -> {
                    if (status == 200 && response instanceof JSONObject) {
                        preferences.edit().putString(TOKEN,
                                ((JSONObject) response).optString("token")).apply();
                        dialog.dismiss();
                        lastCallId = null;
                        failures = 0;
                        hideBanner();
                        body.setAlpha(1f);
                        Toast.makeText(this, "Layar terpasang ke server.", Toast.LENGTH_LONG).show();
                    } else {
                        String detail = response instanceof JSONObject
                                ? ((JSONObject) response).optString("detail", "Kode ditolak server.")
                                : "Server tidak dapat dihubungi.";
                        code.setError(detail);
                    }
                });
            } catch (Exception e) {
                code.setError("Kode tidak dapat dikirim.");
            }
        }));
        dialog.show();
    }

    private interface Found {
        void accept(String value);
    }

    private void discoverServer(Found found, Found failed) {
        worker.execute(() -> {
            try (DatagramSocket socket = new DatagramSocket()) {
                socket.setBroadcast(true);
                socket.setSoTimeout(900);
                byte[] request = DISCOVERY_REQUEST.getBytes(StandardCharsets.UTF_8);
                DatagramPacket broadcast = new DatagramPacket(request, request.length,
                        InetAddress.getByName("255.255.255.255"), DISCOVERY_PORT);
                for (int attempt = 0; attempt < 4; attempt++) socket.send(broadcast);
                // Semua jawaban dikumpulkan: dua server yang menjawab
                // berarti salah satunya keliru, dan memilih yang tercepat
                // bisa mengarahkan panel ke komputer yang salah.
                java.util.Set<String> addresses = new java.util.LinkedHashSet<>();
                long deadline = System.currentTimeMillis() + 4500;
                byte[] buffer = new byte[512];
                while (System.currentTimeMillis() < deadline) {
                    DatagramPacket response = new DatagramPacket(buffer, buffer.length);
                    try {
                        socket.receive(response);
                    } catch (java.net.SocketTimeoutException timeout) {
                        continue;
                    }
                    JSONObject json;
                    try {
                        json = new JSONObject(new String(
                                response.getData(), 0, response.getLength(), StandardCharsets.UTF_8));
                    } catch (org.json.JSONException notServer) {
                        continue;
                    }
                    if (!DISCOVERY_RESPONSE.equals(json.optString("service"))) continue;
                    int port = json.optInt("api_port", 8765);
                    if (port < 1 || port > 65535) continue;
                    if (addresses.isEmpty()) {
                        deadline = Math.min(deadline, System.currentTimeMillis() + 1500);
                    }
                    addresses.add("http://" + response.getAddress().getHostAddress() + ":" + port);
                }
                if (addresses.size() == 1) {
                    String address = addresses.iterator().next();
                    handler.post(() -> found.accept(address));
                } else if (addresses.size() > 1) {
                    String list = android.text.TextUtils.join(", ", addresses);
                    handler.post(() -> failed.accept("Lebih dari satu server menjawab ("
                            + list + "). Isi alamat server yang benar secara manual."));
                } else {
                    handler.post(() -> failed.accept("Server tidak ditemukan. Isi alamat secara manual."));
                }
            } catch (Exception e) {
                handler.post(() -> failed.accept("Pencarian gagal: " + e.getMessage()));
            }
        });
    }
}
