package id.sistemantrian.layar;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.GridLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Layar antrian untuk TV Android (docs/istilah.md).
 *
 * Hanya menampilkan dan membunyikan panggilan; tidak pernah menerbitkan
 * nomor. Isinya diambil dari API aplikasi server:
 *
 *   GET /v1/layar/state          papan: nomor tiap loket, berikutnya, jumlah menunggu
 *   GET /v1/layar/calls?after=N  panggilan baru sesudah id N, beserta kalimatnya
 *
 * Setiap panggilan — termasuk panggil ulang — punya id sendiri, sehingga
 * TV cukup mengingat id terakhir yang sudah dibunyikannya. Saat baru
 * menyala atau baru tersambung lagi, TV hanya mengambil id terakhir tanpa
 * membunyikan apa pun: nomor lama yang diumumkan ulang lebih membingungkan
 * daripada layar yang diam.
 */
public class MainActivity extends Activity implements TextToSpeech.OnInitListener {

    private static final String PREFS = "layar";
    private static final String SERVER = "server";
    private static final String TOKEN = "token";
    private static final String DEVICE_ID = "device_id";
    private static final String DEVICE_NAME = "device_name";
    private static final String DEVICE_KIND = "layar_antrian";
    private static final int DISCOVERY_PORT = 8766;
    private static final String DISCOVERY_REQUEST = "SISTEMANTRIAN_KIOSK_DISCOVER_V1";
    private static final String DISCOVERY_RESPONSE = "SISTEMANTRIAN_KIOSK_SERVER_V1";
    private static final String DEFAULT_TIMEZONE = "Asia/Jakarta";

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
    private static final int FAILURES_BEFORE_BANNER = 3;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newFixedThreadPool(2);
    private final ArrayDeque<String> speechQueue = new ArrayDeque<>();
    private final Map<String, LinearLayout> cardsByCounter = new HashMap<>();
    private final Map<String, Long> highlightUntil = new HashMap<>();

    private SharedPreferences preferences;
    private TextToSpeech tts;
    private boolean ttsReady;
    private boolean speaking;
    private ToneGenerator tone;

    private LinearLayout root;
    private TextView title;
    private TextView clock;
    private GridLayout grid;
    private LinearLayout nextList;
    private TextView moreLabel;
    private TextView footerName;
    private TextView banner;
    private LinearLayout body;

    private String serverTimezone = DEFAULT_TIMEZONE;
    private long serverOffsetMillis;
    private Long lastCallId;
    private boolean soundEnabled = true;
    private int failures;
    private long disconnectedSince;
    private String countersSignature = "";
    private int shiftStep;
    private boolean stateInFlight;
    private boolean callsInFlight;

    // =================================================================
    // Siklus hidup
    // =================================================================

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        hideSystemUi();
        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        buildScreen();
        tts = new TextToSpeech(this, this);
        try {
            tone = new ToneGenerator(AudioManager.STREAM_MUSIC, 90);
        } catch (RuntimeException e) {
            tone = null;
        }
        handler.post(clockTick);
        handler.postDelayed(burnInShift, 5 * 60 * 1000L);
        if (!isPaired()) {
            showBanner("Layar belum dipasangkan. Tekan MENU atau tahan OK pada remote.");
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
        if (tts != null) tts.shutdown();
        if (tone != null) tone.release();
        super.onDestroy();
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

    // Remote TV: MENU, SETTINGS, atau tahan OK membuka pengaturan.
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

    @Override
    public void onInit(int status) {
        if (status != TextToSpeech.SUCCESS) return;
        int hasil = tts.setLanguage(new Locale("id", "ID"));
        ttsReady = hasil != TextToSpeech.LANG_MISSING_DATA
                && hasil != TextToSpeech.LANG_NOT_SUPPORTED;
        tts.setOnUtteranceProgressListener(new android.speech.tts.UtteranceProgressListener() {
            @Override public void onStart(String id) { }
            @Override public void onDone(String id) { handler.post(() -> { speaking = false; speakNext(); }); }
            @Override public void onError(String id) { handler.post(() -> { speaking = false; speakNext(); }); }
        });
    }

    // =================================================================
    // Tampilan
    // =================================================================

    private float sp(float value) {
        float tinggi = getResources().getDisplayMetrics().heightPixels
                / getResources().getDisplayMetrics().scaledDensity;
        // Dirancang untuk 720 baris; TV 1080p dan 4K ikut membesar.
        return value * Math.max(0.7f, tinggi / 720f);
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

    private void buildScreen() {
        FrameLayout frame = new FrameLayout(this);
        GradientDrawable background = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM, new int[]{BG_TOP, BG_BOTTOM});
        frame.setBackground(background);

        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(28), dp(18), dp(28), dp(14));
        frame.addView(root, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout head = new LinearLayout(this);
        head.setGravity(Gravity.CENTER_VERTICAL);
        title = text("ANTRIAN PELAYANAN", 30, Color.WHITE, true);
        title.setLetterSpacing(0.04f);
        title.setOnLongClickListener(v -> { showSettings(); return true; });
        head.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        clock = text("", 20, LIGHT, false);
        head.addView(clock);
        root.addView(head);

        body = new LinearLayout(this);
        body.setPadding(0, dp(14), 0, dp(10));
        grid = new GridLayout(this);
        grid.setUseDefaultMargins(false);
        LinearLayout.LayoutParams gridParams = new LinearLayout.LayoutParams(0, -1, 3);
        gridParams.rightMargin = dp(18);
        body.addView(grid, gridParams);

        LinearLayout side = new LinearLayout(this);
        side.setOrientation(LinearLayout.VERTICAL);
        side.setPadding(dp(18), dp(14), dp(18), dp(14));
        side.setBackground(rounded(Color.argb(20, 255, 255, 255), dp(16)));
        side.addView(text("BERIKUTNYA", 20, LIGHT, true));
        nextList = new LinearLayout(this);
        nextList.setOrientation(LinearLayout.VERTICAL);
        side.addView(nextList);
        moreLabel = text("", 16, MUTED, false);
        moreLabel.setPadding(0, dp(10), 0, 0);
        side.addView(moreLabel);
        body.addView(side, new LinearLayout.LayoutParams(0, -1, 1.2f));
        root.addView(body, new LinearLayout.LayoutParams(-1, 0, 1));

        banner = text("", 18, Color.WHITE, true);
        banner.setPadding(dp(16), dp(8), dp(16), dp(8));
        banner.setBackground(rounded(AMBER, dp(10)));
        banner.setVisibility(View.GONE);
        root.addView(banner);

        LinearLayout foot = new LinearLayout(this);
        foot.setPadding(0, dp(6), 0, 0);
        foot.addView(text("Mohon perhatikan nomor Anda dipanggil", 14, MUTED, false),
                new LinearLayout.LayoutParams(0, -2, 1));
        footerName = text(deviceName(), 14, MUTED, false);
        foot.addView(footerName);
        root.addView(foot);

        setContentView(frame);
    }

    /** Kecilkan huruf sampai teks muat selebar `width` piksel. */
    private void fitText(TextView view, float maxSp, int width) {
        if (width <= 0) return;
        Paint paint = new Paint(view.getPaint());
        float size = sp(maxSp);
        String value = view.getText().toString();
        while (size > 12) {
            paint.setTextSize(TypedValue.applyDimension(
                    TypedValue.COMPLEX_UNIT_SP, size, getResources().getDisplayMetrics()));
            if (paint.measureText(value) <= width * 0.92f) break;
            size -= 2;
        }
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
    }

    private void buildCards(JSONArray counters) {
        grid.removeAllViews();
        cardsByCounter.clear();
        int jumlah = Math.max(1, counters.length());
        int kolom = jumlah <= 2 ? jumlah : jumlah <= 4 ? 2 : jumlah <= 6 ? 3 : 4;
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
            label.setPadding(0, dp(8), 0, dp(8));
            GradientDrawable top = new GradientDrawable();
            top.setColor(TEAL);
            top.setCornerRadii(new float[]{dp(16), dp(16), dp(16), dp(16), 0, 0, 0, 0});
            label.setBackground(top);
            card.addView(label);

            TextView number = text("", 72, INK, true);
            number.setGravity(Gravity.CENTER);
            number.setTag("number");
            // Nomor selalu SATU baris (PB-014, bukan PB- / 014): huruf
            // dikecilkan sampai muat, dan diukur ulang bila kartu berubah ukuran.
            number.setSingleLine(true);
            number.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
                if (r - l != or - ol) {
                    TextView tv = (TextView) v;
                    boolean status = tv.getCurrentTextColor() == MUTED;
                    tv.post(() -> fitText(tv, status ? 30 : 72, tv.getWidth()));
                }
            });
            card.addView(number, new LinearLayout.LayoutParams(-1, 0, 1));

            TextView category = text("", 16, Color.rgb(71, 85, 105), false);
            category.setGravity(Gravity.CENTER);
            category.setPadding(0, 0, 0, dp(10));
            category.setTag("category");
            card.addView(category);

            GridLayout.LayoutParams params = new GridLayout.LayoutParams(
                    GridLayout.spec(i / kolom, 1f), GridLayout.spec(i % kolom, 1f));
            params.width = 0;
            params.height = 0;
            params.setMargins(dp(8), dp(8), dp(8), dp(8));
            grid.addView(card, params);
            cardsByCounter.put(name, card);
        }
    }

    private void applyState(JSONObject state) {
        String judul = state.optString("title", "").trim();
        if (!judul.isEmpty()) title.setText(judul);
        soundEnabled = state.optBoolean("sound_enabled", true);
        String zone = state.optString("timezone", DEFAULT_TIMEZONE);
        serverTimezone = zone.startsWith("Asia/") ? zone : DEFAULT_TIMEZONE;
        long serverTime = state.optLong("server_time_ms", 0L);
        if (serverTime > 0L) serverOffsetMillis = serverTime - System.currentTimeMillis();

        JSONArray counters = state.optJSONArray("counters");
        if (counters == null) counters = new JSONArray();
        StringBuilder signature = new StringBuilder();
        for (int i = 0; i < counters.length(); i++) {
            signature.append(counters.optJSONObject(i).optString("name")).append('|');
        }
        if (!signature.toString().equals(countersSignature)) {
            countersSignature = signature.toString();
            buildCards(counters);
        }
        long now = System.currentTimeMillis();
        for (int i = 0; i < counters.length(); i++) {
            JSONObject counter = counters.optJSONObject(i);
            LinearLayout card = cardsByCounter.get(counter.optString("name"));
            if (card == null) continue;
            TextView number = card.findViewWithTag("number");
            TextView category = card.findViewWithTag("category");
            boolean ada = !counter.isNull("queue_number");
            number.setText(ada ? counter.optString("queue_number") : counter.optString("status", "KOSONG"));
            number.setTextColor(ada ? INK : MUTED);
            category.setText(ada && !counter.isNull("category") ? counter.optString("category") : " ");
            final float maxSp = ada ? 72 : 30;
            number.post(() -> fitText(number, maxSp, number.getWidth()));
            Long until = highlightUntil.get(counter.optString("name"));
            boolean hot = until != null && until > now;
            GradientDrawable bg = rounded(Color.WHITE, dp(16));
            if (hot) bg.setStroke(dp(6), ACCENT);
            card.setBackground(bg);
        }

        nextList.removeAllViews();
        JSONArray next = state.optJSONArray("next");
        int shown = next == null ? 0 : next.length();
        for (int i = 0; i < shown; i++) {
            TextView row = text(next.optString(i), 38, Color.WHITE, true);
            row.setPadding(0, dp(6), 0, dp(6));
            nextList.addView(row);
        }
        int lainnya = state.optInt("total_waiting") - shown;
        moreLabel.setText(lainnya > 0 ? "dan " + lainnya + " lainnya menunggu"
                : shown == 0 ? "Tidak ada yang menunggu" : "");
    }

    private void showBanner(String message) {
        banner.setText(message);
        banner.setVisibility(View.VISIBLE);
    }

    private void setConnected(boolean connected) {
        if (connected) {
            if (failures >= FAILURES_BEFORE_BANNER) {
                // Tersambung lagi: panggilan selama terputus TIDAK dibunyikan.
                lastCallId = null;
            }
            failures = 0;
            disconnectedSince = 0;
            banner.setVisibility(View.GONE);
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

    private interface Done {
        void accept(int code, Object body);
    }

    /** Permintaan HTTP di utas pekerja; hasil kembali ke utas tampilan. */
    private void request(String method, String path, JSONObject body, Done done) {
        worker.execute(() -> {
            int code = -1;
            Object parsed = null;
            HttpURLConnection connection = null;
            try {
                String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
                connection = (HttpURLConnection) new URL(base + path).openConnection();
                connection.setRequestMethod(method);
                connection.setConnectTimeout(3000);
                connection.setReadTimeout(5000);
                connection.setRequestProperty("Authorization",
                        "Bearer " + preferences.getString(TOKEN, ""));
                connection.setRequestProperty("Accept", "application/json");
                connection.setRequestProperty("X-Device-Id", deviceId());
                connection.setRequestProperty("X-Device-Name", deviceName());
                connection.setRequestProperty("X-Device-Kind", DEVICE_KIND);
                connection.setRequestProperty("X-App-Version-Code", String.valueOf(appVersionCode()));
                if (body != null) {
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    connection.getOutputStream().write(body.toString().getBytes(StandardCharsets.UTF_8));
                }
                code = connection.getResponseCode();
                InputStream stream = code < 400 ? connection.getInputStream() : connection.getErrorStream();
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                if (stream != null) {
                    byte[] buffer = new byte[4096];
                    int length;
                    while ((length = stream.read(buffer)) != -1) output.write(buffer, 0, length);
                    stream.close();
                }
                String text = new String(output.toByteArray(), StandardCharsets.UTF_8);
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
            request("GET", "/v1/layar/state", null, (code, body) -> {
                stateInFlight = false;
                if (code == 200 && body instanceof JSONObject) {
                    setConnected(true);
                    applyState((JSONObject) body);
                } else if (code == 401) {
                    showBanner("Layar ini belum dipasangkan atau sudah dicabut. Tekan MENU untuk memasangkan.");
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
            request("GET", path, null, (code, body) -> {
                callsInFlight = false;
                if (code != 200 || !(body instanceof JSONObject)) return;
                JSONObject json = (JSONObject) body;
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
            GradientDrawable bg = rounded(Color.WHITE, dp(16));
            bg.setStroke(dp(6), ACCENT);
            card.setBackground(bg);
        }
        if (!soundEnabled) return;
        speechQueue.add(call.optString("text"));
        speakNext();
    }

    private void speakNext() {
        if (speaking || speechQueue.isEmpty()) return;
        String next = speechQueue.poll();
        speaking = true;
        if (tone != null) tone.startTone(ToneGenerator.TONE_PROP_BEEP2, 600);
        // Jeda sesudah nada, supaya kata pertama tidak tertelan nadanya.
        handler.postDelayed(() -> {
            if (ttsReady && next != null && !next.isEmpty()) {
                Bundle params = new Bundle();
                tts.speak(next, TextToSpeech.QUEUE_FLUSH, params, UUID.randomUUID().toString());
            } else {
                // Tanpa suara Bahasa Indonesia di TV: nada saja.
                speaking = false;
                handler.postDelayed(this::speakNext, 1500);
            }
        }, 900);
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
        name.setHint("Nama layar, contoh TV Ruang Tunggu");
        name.setSingleLine(true);
        name.setText(deviceName());
        fields.addView(name);
        EditText code = new EditText(this);
        code.setHint("Kode pasang 6 angka dari Layanan Anjungan");
        code.setSingleLine(true);
        code.setInputType(InputType.TYPE_CLASS_NUMBER);
        fields.addView(code);
        TextView info = new TextView(this);
        info.setText("Kode dibuat di komputer server: Layanan Anjungan → Perangkat → Tambah perangkat.");
        fields.addView(info);

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
                .setTitle("Hubungkan layar antrian")
                .setView(fields)
                .setPositiveButton("Sambungkan", null)
                .setNegativeButton("Batal", null)
                .create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String address = server.getText().toString().trim();
            String digits = code.getText().toString().replaceAll("[^0-9]", "");
            if (!(address.startsWith("http://") || address.startsWith("https://"))) {
                server.setError("Alamat harus diawali http://");
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
                        banner.setVisibility(View.GONE);
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
