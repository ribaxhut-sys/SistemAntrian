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

    private static final String PREFS = "layar";
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

    private static final int BG_TOP = Color.rgb(7, 20, 34);
    private static final int BG_BOTTOM = Color.rgb(11, 42, 74);
    private static final int TEAL = Color.rgb(15, 118, 110);
    private static final int ACCENT = Color.rgb(34, 211, 238);
    private static final int INK = Color.rgb(15, 23, 42);
    private static final int MUTED = Color.rgb(148, 163, 184);
    private static final int LIGHT = Color.rgb(226, 232, 240);
    private static final int AMBER = Color.rgb(180, 83, 9);

    private static final long STATE_INTERVAL_MS = 2000;
    private static final long CALLS_INTERVAL_MS = 1000;
    private static final long HIGHLIGHT_MS = 10000;
    private static final long TITLE_HOLD_MS = 3000;
    private static final long PACK_RETRY_MS = 60000;
    private static final int FAILURES_BEFORE_BANNER = 3;

    // Daftar "Berikutnya": paling banyak 12 nomor, maksimal 45% tinggi papan,
    // dan kartu loket tidak pernah lebih pendek dari 1/8 tinggi layar.
    private static final int NEXT_MAX = 12;
    private static final float NEXT_SHARE_MAX = 0.45f;
    private static final int CARD_MIN_FRACTION = 8;
    private static final float NEXT_SP = 34;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newFixedThreadPool(2);
    private final ExecutorService downloader = Executors.newSingleThreadExecutor();
    private final ArrayDeque<JSONObject> speechQueue = new ArrayDeque<>();
    private final Map<String, LinearLayout> cardsByCounter = new HashMap<>();
    private final Map<String, Long> highlightUntil = new HashMap<>();
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
    private LinearLayout nextList;
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
        buildScreen();
        if (lastState != null) {
            JSONObject state = lastState;
            // Tunggu ukuran baru terpasang supaya tinggi kartu dihitung benar.
            body.post(() -> applyState(state));
        }
        if (failures >= FAILURES_BEFORE_BANNER) body.setAlpha(0.55f);
        hideSystemUi();
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

    private TextView text(String value, float size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp(size));
        view.setTextColor(color);
        view.setTypeface(Typeface.create("sans-serif", bold ? Typeface.BOLD : Typeface.NORMAL));
        view.setSingleLine(true);
        return view;
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
        title = text(title == null ? "ANTRIAN PELAYANAN" : title.getText().toString(),
                30, Color.WHITE, true);
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

        body = new LinearLayout(this);
        body.setOrientation(portrait ? LinearLayout.VERTICAL : LinearLayout.HORIZONTAL);
        body.setPadding(0, dp(12), 0, dp(10));
        grid = new GridLayout(this);
        grid.setUseDefaultMargins(false);

        side = new LinearLayout(this);
        side.setOrientation(LinearLayout.VERTICAL);
        side.setPadding(dp(18), dp(12), dp(18), dp(12));
        side.setBackground(rounded(Color.argb(20, 255, 255, 255), dp(16)));
        nextHeader = text("BERIKUTNYA", 20, LIGHT, true);
        side.addView(nextHeader);
        nextList = new LinearLayout(this);
        nextList.setOrientation(LinearLayout.VERTICAL);
        side.addView(nextList, new LinearLayout.LayoutParams(-1, -2));
        moreLabel = text("", 16, MUTED, false);
        moreLabel.setPadding(0, dp(8), 0, 0);
        side.addView(moreLabel);

        if (portrait) {
            body.addView(grid, new LinearLayout.LayoutParams(-1, 0, 1));
            LinearLayout.LayoutParams sideParams = new LinearLayout.LayoutParams(-1, -2);
            sideParams.topMargin = dp(10);
            body.addView(side, sideParams);
        } else {
            LinearLayout.LayoutParams gridParams = new LinearLayout.LayoutParams(0, -1, 3);
            gridParams.rightMargin = dp(18);
            body.addView(grid, gridParams);
            body.addView(side, new LinearLayout.LayoutParams(0, -1, 1.2f));
        }
        root.addView(body, new LinearLayout.LayoutParams(-1, 0, 1));

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

    private void fitNumber(TextView number) {
        boolean status = number.getCurrentTextColor() == MUTED;
        fitText(number, status ? 30 : 72, number.getWidth(), number.getHeight());
    }

    private int columnsFor(int jumlah) {
        if (portrait) return jumlah <= 1 ? 1 : 2;
        return jumlah <= 2 ? jumlah : jumlah <= 4 ? 2 : jumlah <= 6 ? 3 : 4;
    }

    private void buildCards(JSONArray counters) {
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
            card.setOrientation(LinearLayout.VERTICAL);
            card.setBackground(rounded(Color.WHITE, dp(16)));
            card.setClipToOutline(true);

            TextView label = text(name.toUpperCase(Locale.ROOT), 22, Color.WHITE, true);
            label.setGravity(Gravity.CENTER);
            label.setPadding(dp(6), dp(6), dp(6), dp(6));
            GradientDrawable top = new GradientDrawable();
            top.setColor(TEAL);
            top.setCornerRadii(new float[]{dp(16), dp(16), dp(16), dp(16), 0, 0, 0, 0});
            label.setBackground(top);
            card.addView(label);

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
            card.addView(number, new LinearLayout.LayoutParams(-1, 0, 1));

            TextView category = text("", 16, Color.rgb(71, 85, 105), false);
            category.setGravity(Gravity.CENTER);
            category.setPadding(0, 0, 0, dp(8));
            category.setTag("category");
            card.addView(category);

            GridLayout.LayoutParams params = new GridLayout.LayoutParams(
                    GridLayout.spec(i / kolom, 1f), GridLayout.spec(i % kolom, 1f));
            params.width = 0;
            params.height = 0;
            params.setMargins(dp(6), dp(6), dp(6), dp(6));
            grid.addView(card, params);
            cardsByCounter.put(name, card);
        }
    }

    private void applyState(JSONObject state) {
        lastState = state;
        String judul = state.optString("title", "").trim();
        if (!judul.isEmpty() && !judul.contentEquals(title.getText())) {
            title.setText(judul);
            title.post(() -> fitText(title, 30, title.getWidth(), 0));
        }
        soundEnabled = state.optBoolean("sound_enabled", true);
        String zone = state.optString("timezone", DEFAULT_TIMEZONE);
        serverTimezone = zone.startsWith("Asia/") ? zone : DEFAULT_TIMEZONE;
        long serverTime = state.optLong("server_time_ms", 0L);
        if (serverTime > 0L) serverOffsetMillis = serverTime - System.currentTimeMillis();

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
            String value = ada ? counter.optString("queue_number") : counter.optString("status", "KOSONG");
            boolean changed = !value.contentEquals(number.getText())
                    || number.getCurrentTextColor() != (ada ? INK : MUTED);
            number.setText(value);
            number.setTextColor(ada ? INK : MUTED);
            category.setText(ada && !counter.isNull("category") ? counter.optString("category") : " ");
            if (changed) number.post(() -> fitNumber(number));
            Long until = highlightUntil.get(counter.optString("name"));
            boolean hot = until != null && until > now;
            GradientDrawable bg = rounded(Color.WHITE, dp(16));
            if (hot) bg.setStroke(dp(6), ACCENT);
            card.setBackground(bg);
        }

        applyNext(state);
        applyVersion(state);
        syncSoundPack(state.optString("sound_pack_version", ""));
    }

    // -----------------------------------------------------------------
    // "Berikutnya": tumbuh per baris, kartu loket memendek mengikutinya
    // -----------------------------------------------------------------

    private int perRow() {
        return portrait ? 3 : 2;
    }

    private int nextRowHeight() {
        Paint paint = new Paint();
        paint.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        paint.setTextSize(spToPx(sp(NEXT_SP)));
        Paint.FontMetricsInt metrics = paint.getFontMetricsInt();
        return metrics.bottom - metrics.top + dp(10);
    }

    private int fixedSideHeight() {
        return side.getPaddingTop() + side.getPaddingBottom()
                + nextHeader.getLineHeight()
                + moreLabel.getLineHeight() + moreLabel.getPaddingTop();
    }

    /**
     * Berapa baris nomor yang boleh tampil.
     *
     * Tegak: tiap baris tambahan memendekkan kartu loket. Baris ditambah
     * hanya selama panel tidak lebih dari 45% papan DAN kartu masih setinggi
     * minimal 1/8 layar. Mendatar: kolom samping memanjang ke bawah sampai
     * penuh; kartu tidak terpengaruh.
     */
    private int nextRowsAllowed(int wanted) {
        int limit = Math.min(wanted, (int) Math.ceil(NEXT_MAX / (double) perRow()));
        if (limit <= 1) return limit;
        int board = body.getHeight() - body.getPaddingTop() - body.getPaddingBottom();
        if (board <= 0) return 1;  // belum diukur; dihitung ulang pada polling berikutnya
        int rowHeight = nextRowHeight();
        if (!portrait) {
            int fit = (board - fixedSideHeight()) / Math.max(1, rowHeight);
            return Math.max(1, Math.min(limit, fit));
        }
        int cardRows = Math.max(1, grid.getRowCount());
        int minCard = getResources().getDisplayMetrics().heightPixels / CARD_MIN_FRACTION;
        int minGrid = cardRows * (minCard + dp(12));
        int rows = limit;
        while (rows > 1) {
            int panel = fixedSideHeight() + rows * rowHeight + dp(10);
            if (panel <= board * NEXT_SHARE_MAX && board - panel >= minGrid) break;
            rows--;
        }
        return rows;
    }

    private void applyNext(JSONObject state) {
        JSONArray next = state.optJSONArray("next");
        int available = next == null ? 0 : next.length();
        int per = perRow();
        int wanted = (int) Math.ceil(available / (double) per);
        int rows = nextRowsAllowed(wanted);
        int shown = Math.min(available, rows * per);

        if (rows != nextRowsShown) {
            // Hanya saat jumlah BARIS berubah kartu ikut bergerak, dan geraknya halus.
            if (nextRowsShown >= 0) {
                AutoTransition transition = new AutoTransition();
                transition.setDuration(400);
                TransitionManager.beginDelayedTransition(body, transition);
            }
            nextRowsShown = rows;
            nextList.removeAllViews();
            for (int r = 0; r < rows; r++) {
                LinearLayout row = new LinearLayout(this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                for (int c = 0; c < per; c++) {
                    TextView cell = text("", NEXT_SP, Color.WHITE, true);
                    cell.setPadding(0, dp(5), dp(4), dp(5));
                    row.addView(cell, new LinearLayout.LayoutParams(0, -2, 1));
                }
                nextList.addView(row);
            }
        }
        for (int i = 0; i < rows * per; i++) {
            LinearLayout row = (LinearLayout) nextList.getChildAt(i / per);
            TextView cell = (TextView) row.getChildAt(i % per);
            String value = i < shown ? next.optString(i) : "";
            if (!value.contentEquals(cell.getText())) {
                cell.setText(value);
                cell.post(() -> fitText(cell, NEXT_SP, cell.getWidth(), 0));
            }
        }
        int lainnya = state.optInt("total_waiting") - shown;
        moreLabel.setText(lainnya > 0 ? "dan " + lainnya + " lainnya menunggu"
                : shown == 0 ? "Tidak ada yang menunggu" : "");
    }

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
                    "EEEE, d MMM yyyy · HH:mm:ss", new Locale("id", "ID"));
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

    private final Runnable statePoll = new Runnable() {
        @Override
        public void run() {
            handler.postDelayed(this, STATE_INTERVAL_MS);
            if (!isPaired() || stateInFlight) return;
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
            });
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

    private void announce(JSONObject call) {
        if (call == null) return;
        String counter = call.optString("counter_name");
        highlightUntil.put(counter, System.currentTimeMillis() + HIGHLIGHT_MS);
        LinearLayout card = cardsByCounter.get(counter);
        if (card != null) {
            TextView number = card.findViewWithTag("number");
            number.setText(call.optString("queue_number"));
            number.setTextColor(INK);
            number.post(() -> fitNumber(number));
            GradientDrawable bg = rounded(Color.WHITE, dp(16));
            bg.setStroke(dp(6), ACCENT);
            card.setBackground(bg);
        }
        if (!soundEnabled) return;
        speechQueue.add(call);
        speakNext();
    }

    /**
     * Bunyikan panggilan berikutnya. Urutan pilihan suara:
     *   1. TTS perangkat, bila punya Bahasa Indonesia;
     *   2. paket suara dari server (klip WAV disambung);
     *   3. nada saja.
     */
    private void speakNext() {
        if (speaking || speechQueue.isEmpty()) return;
        JSONObject call = speechQueue.poll();
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
                    if (!file.matches("[A-Za-z0-9_.-]+")) continue;
                    HttpURLConnection clip = open("/v1/layar/sound/"
                            + URLEncoder.encode(file, "UTF-8"), 15000);
                    try {
                        if (clip.getResponseCode() != 200) continue;
                        try (InputStream input = clip.getInputStream();
                             OutputStream output = new FileOutputStream(new File(staging, file))) {
                            byte[] buffer = new byte[16 * 1024];
                            int length;
                            while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
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
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String address = server.getText().toString().trim();
            String digits = code.getText().toString().replaceAll("[^0-9]", "");
            if (!(address.startsWith("http://") || address.startsWith("https://"))) {
                server.setError("Alamat harus diawali http://");
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
                long deadline = System.currentTimeMillis() + 4500;
                byte[] buffer = new byte[512];
                while (System.currentTimeMillis() < deadline) {
                    DatagramPacket response = new DatagramPacket(buffer, buffer.length);
                    try {
                        socket.receive(response);
                    } catch (java.net.SocketTimeoutException timeout) {
                        continue;
                    }
                    JSONObject json = new JSONObject(new String(
                            response.getData(), 0, response.getLength(), StandardCharsets.UTF_8));
                    if (!DISCOVERY_RESPONSE.equals(json.optString("service"))) continue;
                    String address = "http://" + response.getAddress().getHostAddress()
                            + ":" + json.optInt("api_port", 8765);
                    handler.post(() -> found.accept(address));
                    return;
                }
                handler.post(() -> failed.accept("Server tidak ditemukan. Isi alamat secara manual."));
            } catch (Exception e) {
                handler.post(() -> failed.accept("Pencarian gagal: " + e.getMessage()));
            }
        });
    }
}
