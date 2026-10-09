package id.sistemantrian.kiosk;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInfo;
import android.database.Cursor;
import android.content.pm.PackageInstaller;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.text.InputType;
import android.text.TextUtils;
import android.transition.AutoTransition;
import android.transition.TransitionManager;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.GridLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import android.widget.VideoView;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

public final class MainActivity extends Activity {
    private static final String PREFS = "kiosk";
    private static final String SERVER = "server";
    private static final String TOKEN = "token";
    private static final String DEVICE_ID = "device_id";
    private static final String DEVICE_NAME = "device_name";
    // Jenis perangkat menurut docs/istilah.md: aplikasi ini adalah anjungan.
    private static final String DEVICE_KIND = "anjungan";

    // Warna tema aktif. Bukan konstanta: diisi terapkanPalet() setiap kali
    // layar dibangun, sehingga mengganti tema cukup membangun ulang layar.
    private int INK;
    private int MUTED;
    private int UTAMA;
    private int LATAR;
    private int KARTU;
    private int GARIS;
    private int LEMBUT;
    private int EMAS;
    private int ABU_LEMBUT;
    private int HASIL;
    private int TEKS_TOMBOL;
    /** Kapsul huruf awalan per layanan: {latar, tulisan}, dipilih dari awalannya. */
    private int[][] WARNA_LAYANAN;
    private static final int GREEN = Color.rgb(22, 163, 74);
    private static final int RED = Color.rgb(220, 38, 38);

    private static final String TEMA_TABLET = "tema";
    private static final String IKUTI_SERVER_TEMA = "server";
    private static final String[][] PILIHAN_TEMA = {
            {IKUTI_SERVER_TEMA, "Ikuti pengaturan server"},
            {"biru", "Biru instansi"},
            {"hijau", "Hijau segar"},
            {"kontras", "Kontras tinggi"},
            {"gelap", "Gelap elegan"},
            {"merah_putih", "Merah putih (perayaan)"},
    };
    private Tema temaWarna;
    private String temaAktif = "";
    private String temaServer = "biru";
    private String judulServer = "";

    /** Satu set warna tampilan anjungan. */
    private static final class Tema {
        final int latar, kartu, garis, ink, muted, utama, lembut, emas, abu, hasil, teksTombol;
        final int[][] chip;
        final float skala;
        final boolean gelap;

        Tema(int latar, int kartu, int garis, int ink, int muted, int utama, int lembut,
             int emas, int abu, int hasil, int teksTombol, int[][] chip, float skala,
             boolean gelap) {
            this.latar = latar;
            this.kartu = kartu;
            this.garis = garis;
            this.ink = ink;
            this.muted = muted;
            this.utama = utama;
            this.lembut = lembut;
            this.emas = emas;
            this.abu = abu;
            this.hasil = hasil;
            this.teksTombol = teksTombol;
            this.chip = chip;
            this.skala = skala;
            this.gelap = gelap;
        }
    }

    private static int rgb(int r, int g, int b) {
        return Color.rgb(r, g, b);
    }

    private static Tema tema(String kode) {
        switch (kode) {
            case "hijau":
                return new Tema(rgb(242, 248, 244), Color.WHITE, rgb(214, 233, 221),
                        rgb(13, 59, 42), rgb(85, 117, 102), rgb(17, 120, 90),
                        rgb(220, 241, 230), rgb(233, 216, 74), rgb(238, 245, 240),
                        rgb(13, 59, 42), Color.WHITE, new int[][]{
                        {rgb(214, 241, 227), rgb(15, 107, 74)},
                        {rgb(232, 245, 201), rgb(77, 122, 15)},
                        {rgb(253, 236, 207), rgb(154, 91, 10)},
                        {rgb(215, 238, 245), rgb(14, 106, 133)}}, 1f, false);
            case "kontras":
                // Hitam-kuning dan huruf 12% lebih besar: keterbacaan dulu.
                return new Tema(Color.WHITE, Color.WHITE, Color.BLACK,
                        Color.BLACK, rgb(31, 31, 31), Color.BLACK,
                        rgb(255, 230, 0), rgb(255, 230, 0), rgb(235, 235, 235),
                        Color.BLACK, rgb(255, 230, 0), new int[][]{
                        {Color.BLACK, rgb(255, 230, 0)}}, 1.12f, false);
            case "gelap":
                return new Tema(rgb(11, 18, 32), rgb(20, 29, 48), rgb(36, 49, 77),
                        rgb(238, 242, 251), rgb(147, 163, 196), rgb(91, 140, 255),
                        rgb(28, 42, 71), rgb(245, 183, 42), rgb(26, 35, 56),
                        rgb(0, 8, 20), Color.WHITE, new int[][]{
                        {rgb(31, 53, 102), rgb(156, 188, 255)},
                        {rgb(23, 63, 51), rgb(127, 224, 178)},
                        {rgb(69, 53, 26), rgb(245, 200, 105)},
                        {rgb(53, 35, 77), rgb(207, 166, 245)}}, 1f, true);
            case "merah_putih":
                return new Tema(rgb(255, 247, 246), Color.WHITE, rgb(243, 214, 211),
                        rgb(92, 11, 11), rgb(138, 90, 87), rgb(200, 16, 46),
                        rgb(253, 228, 225), Color.WHITE, rgb(250, 240, 239),
                        rgb(200, 16, 46), Color.WHITE, new int[][]{
                        {rgb(200, 16, 46), Color.WHITE},
                        {rgb(253, 228, 225), rgb(200, 16, 46)}}, 1f, false);
            default:
                return new Tema(rgb(244, 247, 252), Color.WHITE, rgb(223, 230, 243),
                        rgb(11, 42, 91), rgb(91, 107, 134), rgb(30, 79, 163),
                        rgb(227, 235, 250), rgb(245, 183, 42), rgb(241, 245, 249),
                        rgb(11, 42, 91), Color.WHITE, new int[][]{
                        {rgb(219, 231, 255), rgb(30, 79, 163)},
                        {rgb(220, 245, 232), rgb(15, 122, 74)},
                        {rgb(253, 236, 207), rgb(161, 88, 10)},
                        {rgb(240, 226, 251), rgb(123, 63, 176)},
                        {rgb(207, 244, 244), rgb(14, 116, 120)},
                        {rgb(253, 226, 221), rgb(176, 58, 36)}}, 1f, false);
        }
    }

    private void terapkanPalet(Tema t) {
        temaWarna = t;
        INK = t.ink;
        MUTED = t.muted;
        UTAMA = t.utama;
        LATAR = t.latar;
        KARTU = t.kartu;
        GARIS = t.garis;
        LEMBUT = t.lembut;
        EMAS = t.emas;
        ABU_LEMBUT = t.abu;
        HASIL = t.hasil;
        TEKS_TOMBOL = t.teksTombol;
        WARNA_LAYANAN = t.chip;
    }

    /** Pilihan tablet bila diatur, selain itu tema dari server. */
    private String temaBerlaku() {
        String tablet = preferences == null ? IKUTI_SERVER_TEMA
                : preferences.getString(TEMA_TABLET, IKUTI_SERVER_TEMA);
        return IKUTI_SERVER_TEMA.equals(tablet) ? temaServer : tablet;
    }

    /**
     * Bangun ulang layar bila tema berubah. Ditunda selama pengunjung
     * sedang memilih atau melihat nomornya; penyegaran 5 detik berikutnya
     * mencobanya lagi.
     */
    private void terapkanTemaBilaBerubah() {
        if (temaBerlaku().equals(temaAktif)) return;
        if (showingConfirmation || showingResult || requestInFlight
                || updating || updateRequired) return;
        bangunUlangTampilan();
    }

    private void bangunUlangTampilan() {
        buildHome();
        mediaSignature = "";
        displayedWelcomeText = "";
        tampilanLoket = "";
        terapkanMediaSambutan();
        terapkanBarisLoket();
        tampilkanNomorMenunggu();
        if (lastDisplaySuccessMillis > 0L) {
            tampilkanStatusKoneksi("Terhubung ke server", Color.rgb(6, 95, 70),
                    Color.rgb(209, 250, 229));
        }
        if (!hasServerConfig()) {
            showServerPlaceholder("Server belum diatur. Hubungkan melalui tombol Pengaturan.");
        }
    }

    /** Dialog mengikuti terang/gelap tema, supaya judul dan tombolnya terbaca. */
    private AlertDialog.Builder pembuatDialog() {
        return new AlertDialog.Builder(this, temaWarna != null && temaWarna.gelap
                ? android.R.style.Theme_Material_Dialog_Alert
                : android.R.style.Theme_Material_Light_Dialog_Alert);
    }

    /** Latar sambutan tema merah putih: pita merah berisi ucapan, lalu putih. */
    private static final class LatarBendera extends android.graphics.drawable.Drawable {
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
            merah.setColor(rgb(200, 16, 46));
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
    private static final int KOLOM_NOMOR_MENUNGGU = 4;
    // Tiga baris nomor menunggu; dua bila baris loket ikut berada di panel bawah.
    private static final int BARIS_NOMOR_MENUNGGU = 3;
    private static final int BARIS_NOMOR_MENUNGGU_BERSAMA_LOKET = 2;
    // Lama layar "NOMOR ANDA" sebelum kembali ke menu layanan. Sengaja tidak
    // mengikuti jeda kios: jeda itu tetap berlaku lewat tombol yang mati dan
    // hitung mundur "Mohon tunggu", pengunjung tidak perlu menunggu di sini.
    private static final long LAMA_HASIL_MS = 4000L;
    private static final int DISCOVERY_PORT = 8766;
    private static final String DISCOVERY_REQUEST = "SISTEMANTRIAN_KIOSK_DISCOVER_V1";
    private static final String DISCOVERY_RESPONSE = "SISTEMANTRIAN_KIOSK_SERVER_V1";
    private static final String DEFAULT_TOKEN = "bapendacro";

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final List<Category> categories = new ArrayList<>();
    private final List<Category> path = new ArrayList<>();
    private final List<View> ticketChoices = new ArrayList<>();
    private SharedPreferences preferences;
    private FrameLayout contentSlot;
    private FrameLayout resultSlot;
    private TextView resultTitle;
    private TextView displayTitle;
    private TextView timeLabel;
    private TextView connectionLabel;
    private TextView welcome;
    private FrameLayout mediaSlot;
    private TextView invitation;
    private TextView hint;
    private Category pendingCategory;
    private String pendingRequestId;
    private float uiScale = 1f;
    private long readyAtMillis;
    private boolean registrationOpen = true;
    private boolean requestInFlight;
    private boolean showingConfirmation;
    private boolean showingResult;
    private boolean categoriesLoaded;
    private String mediaSignature = "";
    private List<String> welcomeMedia = new ArrayList<>();
    private int welcomeSlideSeconds = 10;
    private int mediaIndex;
    private String welcomeFallbackText = "";
    private String displayedWelcomeText = "";
    private final List<String> waitingQueueNumbers = new ArrayList<>();
    private final List<Loket> loketList = new ArrayList<>();
    private LinearLayout rootLayout;
    private LinearLayout loketAtas;
    private LinearLayout loketBawah;
    /** Pengaturan server: otomatis, atas, atau bawah. */
    private String posisiLoket = "otomatis";
    private boolean adaMediaSambutan;
    /** Media sambutan ada di daftar, tetapi gagal dimuat di tablet ini. */
    private boolean mediaGagal;
    private String tampilanLoket = "";
    /** Panel bawah sedang memakai latar gelap layar "Nomor Anda". */
    private boolean panelHasilGelap;
    private LinearLayout panelHasil;
    private long batasKonfirmasiMillis;
    /** Pengaturan server: video anjungan bersuara atau tidak. */
    private boolean suaraVideo;
    private android.media.MediaPlayer pemutarVideo;
    /** Berkas daftar putar yang gagal dimuat pada putaran ini. */
    private final Set<String> berkasGagal = new HashSet<>();
    private int barisMenunggu = BARIS_NOMOR_MENUNGGU;
    private int waitingPage;
    private int displayFailures;
    private long lastDisplaySuccessMillis;

    // Sumber media sambutan, dipilih per tablet di Pengaturan. "server":
    // daftar putar dari server, disalin ke tablet dan diputar dari salinan
    // itu (sebelum salinannya lengkap, diputar langsung lewat jaringan).
    // "tablet": berkas di folder media tablet ini sendiri, tanpa jaringan.
    private static final String SUMBER_MEDIA = "sumber_media";
    private static final String SUMBER_SERVER = "server";
    private static final String SUMBER_TABLET = "tablet";
    private static final int PILIH_MEDIA_TABLET = 41;
    // Letak baris loket khusus tablet ini; "server" = ikuti pengaturan server.
    private static final String POSISI_LOKET_TABLET = "posisi_loket";
    private static final String IKUTI_SERVER = "server";
    private static final String[][] PILIHAN_POSISI_LOKET = {
            {IKUTI_SERVER, "Ikuti pengaturan server"},
            {"otomatis", "Otomatis mengikuti iklan (bawah bila ada iklan)"},
            {"bawah", "Pindahkan loket ke panel bawah"},
            {"atas", "Pindahkan loket ke panel atas"},
            {"sembunyi", "Sembunyikan baris loket"},
    };
    private static final long CADANGAN_RUANG_BYTES = 50L * 1024 * 1024;
    private static final long JEDA_UNDUH_ULANG_MS = 120_000L;
    // Unduhan media terpisah dari `worker`, supaya video besar tidak
    // menahan permintaan API (tiket, display) di belakangnya.
    private final ExecutorService pengunduh = Executors.newSingleThreadExecutor();
    private String serverKind = "teks";
    private List<String> serverMedia = new ArrayList<>();
    /** Nama berkas server -> nama salinannya (ukuran-waktu-nama). */
    private final Map<String, String> kunciSalinan = new HashMap<>();
    /** Kunci salinan yang sedang diunduh; hanya disentuh di thread UI. */
    private final Set<String> sedangDiunduh = new HashSet<>();
    private final Map<String, Long> unduhGagalPada = new HashMap<>();
    /** Video yang sedang diputar langsung dari server, belum dari salinan. */
    private String videoLewatJaringan;

    private static final class Loket {
        final String nama;
        final String nomor;
        final String layanan;
        final String status;

        Loket(JSONObject json) {
            nama = json.optString("name", "");
            nomor = json.isNull("queue_number") ? "" : json.optString("queue_number", "");
            layanan = json.isNull("category") ? "" : json.optString("category", "");
            status = json.optString("status", "KOSONG");
        }

        String tanda() {
            return nama + "=" + nomor + "/" + layanan + "/" + status;
        }
    }

    private static final class Category {
        final int id;
        final String name;
        final String prefix;
        final String info;
        final Integer parentId;
        final boolean group;

        Category(JSONObject json) {
            id = json.optInt("id");
            name = json.optString("name");
            prefix = json.optString("prefix");
            info = json.optString("info");
            parentId = json.isNull("parent_id") ? null : json.optInt("parent_id");
            group = json.optBoolean("is_group");
        }
    }

    private interface Success {
        void accept(JSONObject json) throws Exception;
    }

    private interface Failure {
        void accept(String message);
    }

    // Jam selalu waktu Indonesia dari server, bukan setelan tablet: tablet
    // tanpa internet sering salah jam, dan zonanya bisa di luar Indonesia.
    private static final String DEFAULT_TIMEZONE = "Asia/Jakarta";
    private String serverTimezone = DEFAULT_TIMEZONE;

    // Pembaruan APK dari server. Di bawah versi minimal, anjungan berhenti
    // menerbitkan nomor: APK lama salah membaca jawaban API yang baru.
    private static final String ACTION_INSTALL_STATUS =
            "id.sistemantrian.kiosk.INSTALL_STATUS";
    private int minVersionCode = 0;
    private int latestVersionCode = 0;
    private String latestVersionName = "";
    private boolean updateRequired;
    private boolean updating;
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
            updating = false;
            String message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            String text = "Pembaruan dibatalkan atau gagal"
                    + (message == null ? "." : ": " + message);
            if (updateRequired) {
                showUpdatePanel(text);
            } else {
                Toast.makeText(MainActivity.this, text, Toast.LENGTH_LONG).show();
                path.clear();
                showCategories();
            }
        }
    };
    private long serverOffsetMillis = 0L;

    private static String zoneLabel(String zone) {
        if ("Asia/Makassar".equals(zone)) return "WITA";
        if ("Asia/Jayapura".equals(zone)) return "WIT";
        return "WIB";
    }

    private final Runnable clock = new Runnable() {
        @Override
        public void run() {
            updateAvailability();
            perbaruiHitungMundurKonfirmasi();
            if (timeLabel != null) {
                SimpleDateFormat format = new SimpleDateFormat(
                        "EEEE, d MMM yyyy · HH:mm:ss",
                        new Locale("id", "ID"));
                format.setTimeZone(TimeZone.getTimeZone(serverTimezone));
                timeLabel.setText(format.format(
                        new Date(System.currentTimeMillis() + serverOffsetMillis))
                        + " " + zoneLabel(serverTimezone));
            }
            handler.postDelayed(this, 1000);
        }
    };

    private final Runnable displayRefresh = new Runnable() {
        @Override
        public void run() {
            if (contentSlot != null && hasServerConfig()) {
                loadDisplay();
            } else if (contentSlot != null && sumberTablet()) {
                // Berkas yang baru disalin lewat USB ikut terbaca.
                terapkanMediaSambutan();
                terapkanBarisLoket();
            }
            handler.postDelayed(this, 5000);
        }
    };

    private final Runnable waitingPageRotation = new Runnable() {
        @Override
        public void run() {
            if (!showingResult && !showingConfirmation
                    && waitingQueueNumbers.size() > nomorPerHalaman()) {
                int halaman = jumlahHalamanMenunggu();
                waitingPage = (waitingPage + 1) % halaman;
                tampilkanNomorMenunggu();
            }
            handler.postDelayed(this, 4500);
        }
    };

    private final Runnable nextSlide = () -> advanceSlide();
    // Semua media gagal (server mati sebentar, berkas rusak): coba lagi
    // berkala, supaya iklan kembali sendiri tanpa menyalakan ulang tablet.
    private static final long COBA_MEDIA_LAGI_MS = 120_000L;
    private final Runnable cobaMediaLagi = () -> {
        if (!mediaGagal || welcomeMedia.isEmpty()) return;
        berkasGagal.clear();
        mediaGagal = false;
        terapkanBarisLoket();
        showWelcomeMedia(0);
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        IntentFilter installFilter = new IntentFilter(ACTION_INSTALL_STATUS);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(installReceiver, installFilter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(installReceiver, installFilter);
        }
        buildHome();
        if (sumberTablet()) {
            terapkanMediaSambutan();
            terapkanBarisLoket();
        }
        if (hasServerConfig()) {
            loadCategories();
            loadDisplay();
        } else {
            showServerPlaceholder(
                    "Server belum diatur. Hubungkan melalui tombol Pengaturan.");
            discoverServer(server -> {
                preferences.edit().putString(SERVER, server)
                        .putString(TOKEN, preferences.getString(TOKEN, DEFAULT_TOKEN))
                        .apply();
                showServerPlaceholder("Server ditemukan: " + server);
                loadCategories();
                loadDisplay();
            }, message -> showServerPlaceholder(
                    "Server belum ditemukan. " + message));
        }
    }

    private void buildHome() {
        float density = getResources().getDisplayMetrics().density;
        float widthDp = getResources().getDisplayMetrics().widthPixels / density;
        float heightDp = getResources().getDisplayMetrics().heightPixels / density;
        temaAktif = temaBerlaku();
        terapkanPalet(tema(temaAktif));
        uiScale = Math.max(0.8f, Math.min(2.2f,
                Math.min(widthDp / 360f, heightDp / 640f))) * temaWarna.skala;

        LinearLayout root = new LinearLayout(this);
        rootLayout = root;
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(LATAR);
        root.setPadding(dp(10), dp(8), dp(10), dp(8));

        LinearLayout infoPanel = panel();
        infoPanel.setPadding(dp(18), dp(12), dp(18), dp(12));
        LinearLayout titleRow = new LinearLayout(this);
        titleRow.setGravity(Gravity.CENTER);
        displayTitle = text(judulServer.isEmpty() ? "ANTRIAN PELAYANAN CRO" : judulServer,
                18, INK, true);
        displayTitle.setTypeface(huruf(800));
        displayTitle.setGravity(Gravity.CENTER);
        titleRow.addView(displayTitle, new LinearLayout.LayoutParams(0, -2, 1));
        Button settings = smallButton("⚙");
        settings.setContentDescription("Pengaturan server");
        settings.setOnClickListener(v -> showSettings());
        titleRow.addView(settings, new LinearLayout.LayoutParams(dp(42), dp(38)));
        infoPanel.addView(titleRow);
        timeLabel = text("", 14, MUTED, false);
        timeLabel.setGravity(Gravity.CENTER);
        infoPanel.addView(timeLabel);
        connectionLabel = text("● Server belum diatur", 12, MUTED, true);
        connectionLabel.setGravity(Gravity.CENTER);
        connectionLabel.setPadding(dp(12), dp(4), dp(12), dp(4));
        connectionLabel.setBackground(rounded(ABU_LEMBUT, dp(16)));
        LinearLayout.LayoutParams connectionParams =
                new LinearLayout.LayoutParams(-2, -2);
        connectionParams.gravity = Gravity.CENTER;
        connectionParams.topMargin = dp(4);
        infoPanel.addView(connectionLabel, connectionParams);
        loketAtas = barisLoketKosong();
        infoPanel.addView(loketAtas, new LinearLayout.LayoutParams(-1, -2));
        mediaSlot = new FrameLayout(this);
        welcome = text(
                "Sentuh salah satu layanan di bawah untuk mengambil nomor.",
                24, INK, true);
        welcome.setGravity(Gravity.CENTER);
        welcome.setPadding(dp(12), dp(10), dp(12), dp(10));
        pasangSatuBaris(welcome, 9, 24);
        if ("merah_putih".equals(temaAktif)) {
            java.util.Calendar kalender = java.util.Calendar.getInstance(
                    TimeZone.getTimeZone(serverTimezone));
            kalender.setTimeInMillis(System.currentTimeMillis() + serverOffsetMillis);
            int ke = kalender.get(java.util.Calendar.YEAR) - 1945;
            welcome.setBackground(new LatarBendera(dp(18),
                    "Dirgahayu Republik Indonesia ke-" + ke));
            welcome.setGravity(Gravity.CENTER_HORIZONTAL | Gravity.BOTTOM);
            welcome.setPadding(dp(12), dp(10), dp(12), dp(18));
        }
        mediaSlot.addView(welcome, new FrameLayout.LayoutParams(-1, -1));
        infoPanel.addView(mediaSlot, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(infoPanel, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout kioskPanel = panel();
        kioskPanel.setPadding(dp(14), dp(12), dp(14), dp(12));
        invitation = text("Pilih layanan", 22, INK, true);
        invitation.setTypeface(huruf(800));
        invitation.setGravity(Gravity.CENTER);
        kioskPanel.addView(invitation);

        hint = text("Sentuh jenis layanan yang Anda butuhkan", 14,
                MUTED, true);
        hint.setGravity(Gravity.CENTER);
        hint.setPadding(dp(12), dp(6), dp(12), dp(6));
        hint.setBackground(rounded(LEMBUT, dp(24)));
        LinearLayout.LayoutParams hintParams =
                new LinearLayout.LayoutParams(-2, -2);
        hintParams.gravity = Gravity.CENTER;
        hintParams.topMargin = dp(8);
        hintParams.bottomMargin = dp(8);
        kioskPanel.addView(hint, hintParams);

        contentSlot = new FrameLayout(this);
        kioskPanel.addView(contentSlot, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(kioskPanel, new LinearLayout.LayoutParams(-1, 0, 1));

        // Tiga bagian yang setara membuat pilihan layanan berada tepat di
        // tengah layar, sehingga mudah dijangkau pada tablet yang dipasang
        // tegak. Hasil nomor mendapat ruang sendiri di bagian bawah.
        LinearLayout resultPanel = panel();
        resultPanel.setPadding(dp(14), dp(12), dp(14), dp(12));
        panelHasil = resultPanel;
        resultTitle = text("Nomor menunggu", 17, INK, true);
        resultTitle.setTypeface(huruf(800));
        resultTitle.setGravity(Gravity.CENTER);
        resultPanel.addView(resultTitle);
        loketBawah = barisLoketKosong();
        resultPanel.addView(loketBawah, new LinearLayout.LayoutParams(-1, -2));
        resultSlot = new FrameLayout(this);
        resultPanel.addView(resultSlot, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(resultPanel, new LinearLayout.LayoutParams(-1, 0, 1));

        setContentView(root);
        showCategories();
        handler.removeCallbacks(clock);
        handler.post(clock);
        handler.removeCallbacks(displayRefresh);
        handler.postDelayed(displayRefresh, 5000);
        handler.removeCallbacks(waitingPageRotation);
        handler.postDelayed(waitingPageRotation, 4500);
    }

    private LinearLayout panel() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        layout.setBackground(roundedOutline(KARTU, GARIS, dp(24), dp(1)));
        layout.setElevation(dp(1));
        return layout;
    }

    private void loadCategories() {
        if (!hasServerConfig()) {
            showServerPlaceholder(
                    "Server belum diatur. Hubungkan melalui tombol Pengaturan.");
            return;
        }
        request("GET", "/v1/kiosk/categories", null, json -> {
            JSONArray rows = json.getJSONArray("data");
            categories.clear();
            for (int i = 0; i < rows.length(); i++) {
                categories.add(new Category(rows.getJSONObject(i)));
            }
            categoriesLoaded = true;
            if (!showingConfirmation && !showingResult) showCategories();
        }, message -> {
            categoriesLoaded = false;
            showServerPlaceholder("Tidak dapat memuat layanan: " + message);
        });
    }

    private void loadDisplay() {
        if (!hasServerConfig()) {
            tampilkanStatusKoneksi("Server belum diatur", Color.rgb(100, 116, 139),
                    Color.rgb(226, 232, 240));
            return;
        }
        if (lastDisplaySuccessMillis == 0L) {
            tampilkanStatusKoneksi("Menghubungkan…", Color.rgb(30, 64, 175),
                    Color.rgb(219, 234, 254));
        }
        request("GET", "/v1/kiosk/display", null, json -> {
            JSONObject display = json.getJSONObject("data");
            displayFailures = 0;
            lastDisplaySuccessMillis = System.currentTimeMillis();
            tampilkanStatusKoneksi("Terhubung ke server", Color.rgb(6, 95, 70),
                    Color.rgb(209, 250, 229));
            String title = display.optString("title", "").trim();
            if (!title.isEmpty()) {
                judulServer = title;
                displayTitle.setText(title);
            }
            temaServer = display.optString("theme", "biru");
            terapkanTemaBilaBerubah();
            JSONArray mediaRows = display.optJSONArray("welcome_media");
            List<String> media = new ArrayList<>();
            if (mediaRows != null) {
                for (int i = 0; i < mediaRows.length(); i++) {
                    media.add(mediaRows.getString(i));
                }
            }
            // Server lama tidak mengirim ukuran dan waktu ubah: tanpa itu
            // salinan tidak dapat diperiksa, jadi media tetap diputar lewat
            // jaringan seperti sebelumnya.
            kunciSalinan.clear();
            JSONArray infoRows = display.optJSONArray("welcome_media_files");
            if (infoRows != null) {
                for (int i = 0; i < infoRows.length(); i++) {
                    JSONObject row = infoRows.optJSONObject(i);
                    if (row == null) continue;
                    String nama = row.optString("name", "");
                    if (nama.isEmpty()) continue;
                    kunciSalinan.put(nama, row.optLong("size", 0L) + "-"
                            + row.optLong("modified_ms", 0L) + "-" + namaAman(nama));
                }
            }
            serverKind = display.optString("welcome_kind", "teks");
            serverMedia = media;
            welcomeFallbackText = display.optString("welcome_text", "");
            welcomeSlideSeconds = Math.max(1, display.optInt("welcome_slide_seconds", 10));
            terapkanMediaSambutan();
            if (!sumberTablet()) sinkronkanSalinan();
            registrationOpen = display.optBoolean("registration_open", true);
            JSONArray waitingRows = display.optJSONArray("waiting_queue_numbers");
            List<String> terbaru = new ArrayList<>();
            if (waitingRows != null) {
                for (int i = 0; i < waitingRows.length(); i++) {
                    String nomor = waitingRows.optString(i, "").trim();
                    if (!nomor.isEmpty()) terbaru.add(nomor);
                }
            }
            if (!waitingQueueNumbers.equals(terbaru)) {
                waitingQueueNumbers.clear();
                waitingQueueNumbers.addAll(terbaru);
                waitingPage = 0;
            }
            posisiLoket = display.optString("counter_position", "otomatis");
            boolean suara = display.optBoolean("video_sound", false);
            if (suara != suaraVideo) {
                suaraVideo = suara;
                aturSuaraVideo();
            }
            JSONArray loketRows = display.optJSONArray("counters");
            loketList.clear();
            if (loketRows != null) {
                for (int i = 0; i < loketRows.length(); i++) {
                    JSONObject row = loketRows.optJSONObject(i);
                    if (row != null) loketList.add(new Loket(row));
                }
            }
            terapkanBarisLoket();
            if (!showingResult && !showingConfirmation) tampilkanNomorMenunggu();
            minVersionCode = display.optInt("app_min_version_code", 0);
            latestVersionCode = display.optInt("app_latest_version_code", 0);
            latestVersionName = display.isNull("app_latest_version_name")
                    ? "" : display.optString("app_latest_version_name", "");
            boolean required = appVersionCode() < minVersionCode;
            if (required && !updateRequired && !updating) {
                updateRequired = true;
                showUpdatePanel(null);
            } else if (!required && updateRequired) {
                updateRequired = false;
                path.clear();
                showCategories();
            }
            String zone = display.optString("timezone", DEFAULT_TIMEZONE);
            serverTimezone = zone.startsWith("Asia/") ? zone : DEFAULT_TIMEZONE;
            long serverTime = display.optLong("server_time_ms", 0L);
            if (serverTime > 0L) {
                serverOffsetMillis = serverTime - System.currentTimeMillis();
            }
            long serverCooldown = Math.max(0L,
                    (long) Math.ceil(display.optDouble("cooldown_remaining_seconds", 0)));
            if (!requestInFlight) {
                readyAtMillis = Math.max(readyAtMillis,
                        System.currentTimeMillis() + serverCooldown * 1000L);
            }
            updateAvailability();
        }, message -> {
            displayFailures++;
            if (displayFailures >= 2) {
                String terakhir = lastDisplaySuccessMillis == 0L ? ""
                        : " · terakhir " + jamLokal(lastDisplaySuccessMillis);
                tampilkanStatusKoneksi("Server tidak terhubung" + terakhir,
                        Color.rgb(153, 27, 27), Color.rgb(254, 226, 226));
            } else {
                tampilkanStatusKoneksi("Menghubungkan…", Color.rgb(30, 64, 175),
                        Color.rgb(219, 234, 254));
            }
            if (hint != null && !showingConfirmation && !showingResult) {
                setHint("Server tidak merespons. Periksa jaringan atau Pengaturan.", "salah");
            }
            // Media di folder tablet tidak bergantung pada server.
            if (sumberTablet()) {
                terapkanMediaSambutan();
                terapkanBarisLoket();
            }
        });
    }

    private String jamLokal(long waktu) {
        SimpleDateFormat format = new SimpleDateFormat("HH:mm:ss", new Locale("id", "ID"));
        return format.format(new Date(waktu));
    }

    private void tampilkanStatusKoneksi(String status, int warnaTeks, int warnaLatar) {
        if (connectionLabel == null) return;
        connectionLabel.setText("● " + status);
        connectionLabel.setTextColor(warnaTeks);
        connectionLabel.setBackground(rounded(warnaLatar, dp(16)));
    }

    private boolean hasServerConfig() {
        return preferences != null
                && !preferences.getString(SERVER, "").trim().isEmpty()
                && !preferences.getString(TOKEN, "").trim().isEmpty();
    }

    private void showServerPlaceholder(String message) {
        if (contentSlot == null) return;
        tampilkanStatusKoneksi("Server belum diatur", Color.rgb(100, 116, 139),
                Color.rgb(226, 232, 240));
        showingConfirmation = false;
        showingResult = false;
        ticketChoices.clear();
        contentSlot.removeAllViews();
        invitation.setText("ANJUNGAN ANTRIAN");
        setHint("Pengaturan server dapat diisi sekarang atau nanti", "tunggu");

        LinearLayout placeholder = new LinearLayout(this);
        placeholder.setOrientation(LinearLayout.VERTICAL);
        placeholder.setGravity(Gravity.CENTER);
        placeholder.setPadding(dp(16), dp(8), dp(16), dp(8));
        TextView status = text(message, 18, MUTED, true);
        status.setGravity(Gravity.CENTER);
        placeholder.addView(status);

        LinearLayout previewCards = new LinearLayout(this);
        previewCards.setGravity(Gravity.CENTER);
        String[] examples = {"PILIH LAYANAN", "KONFIRMASI", "NOMOR TIKET"};
        for (int i = 0; i < examples.length; i++) {
            TextView card = text(examples[i], 11, MUTED, true);
            card.setGravity(Gravity.CENTER);
            card.setBackground(rounded(Color.rgb(226, 232, 240), dp(12)));
            LinearLayout.LayoutParams cardParams =
                    new LinearLayout.LayoutParams(0, dp(62), 1);
            cardParams.setMargins(dp(3), dp(10), dp(3), dp(4));
            previewCards.addView(card, cardParams);
        }
        placeholder.addView(previewCards);

        TextView guidance = text(
                "Sambungkan server di Pengaturan untuk memuat layanan aktif dan menerbitkan tiket.",
                14, MUTED, false);
        guidance.setGravity(Gravity.CENTER);
        placeholder.addView(guidance);

        if (hasServerConfig()) {
            Button retry = actionButton("COBA HUBUNGKAN LAGI", false);
            retry.setOnClickListener(v -> {
                setHint("Menghubungkan ke server…", "tunggu");
                loadCategories();
                loadDisplay();
            });
            LinearLayout.LayoutParams retryParams =
                    new LinearLayout.LayoutParams(-1, dp(52));
            retryParams.topMargin = dp(8);
            placeholder.addView(retry, retryParams);
        }
        Button settings = actionButton("PENGATURAN SERVER", true);
        settings.setOnClickListener(v -> showSettings());
        LinearLayout.LayoutParams settingsParams =
                new LinearLayout.LayoutParams(-1, dp(54));
        settingsParams.topMargin = dp(8);
        placeholder.addView(settings, settingsParams);
        Button findServer = actionButton("CARI SERVER OTOMATIS", false);
        findServer.setOnClickListener(v -> {
            showServerPlaceholder("Mencari server di jaringan lokal…");
            discoverServer(server -> {
                preferences.edit().putString(SERVER, server)
                        .putString(TOKEN, preferences.getString(TOKEN, DEFAULT_TOKEN))
                        .apply();
                showServerPlaceholder("Server ditemukan: " + server);
                loadCategories();
                loadDisplay();
            }, error -> showServerPlaceholder(
                    "Server belum ditemukan. " + error));
        });
        LinearLayout.LayoutParams findParams =
                new LinearLayout.LayoutParams(-1, dp(50));
        findParams.topMargin = dp(8);
        placeholder.addView(findServer, findParams);
        contentSlot.addView(placeholder);
    }

    private static boolean isMediaKind(String kind) {
        return "media".equals(kind) || "gambar".equals(kind) || "video".equals(kind);
    }

    private void applyWelcomeText(String value) {
        String message = value.trim();
        String normalized = message.isEmpty()
                ? "Sentuh salah satu layanan di bawah untuk mengambil nomor."
                : message;
        if (normalized.equals(displayedWelcomeText)
                && mediaSlot.getChildCount() == 1
                && mediaSlot.getChildAt(0) == welcome) return;
        displayedWelcomeText = normalized;
        welcome.setText(normalized);
        pemutarVideo = null;
        mediaSlot.removeAllViews();
        mediaSlot.addView(welcome, new FrameLayout.LayoutParams(-1, -1));
    }

    private void showWelcomeMedia(int index) {
        if (welcomeMedia.isEmpty() || mediaSlot == null) return;
        mediaIndex = index;
        String filename = welcomeMedia.get(index);
        String signature = mediaSignature + "|" + filename;
        handler.removeCallbacks(nextSlide);
        pemutarVideo = null;
        videoLewatJaringan = null;
        mediaSlot.removeAllViews();
        String url = mediaUrl(filename);
        // Folder tablet: selalu berkas lokal. Server: salinan bila sudah
        // lengkap, bila belum diputar langsung lewat jaringan.
        File lokal = berkasMedia(filename);
        if (isVideo(filename)) {
            VideoView video = new VideoView(this);
            video.setBackgroundColor(Color.BLACK);
            mediaSlot.addView(video, new FrameLayout.LayoutParams(-1, -1));
            video.setOnCompletionListener(player -> advanceSlide());
            video.setOnErrorListener((player, what, extra) -> {
                mediaGagalDiputar(signature, filename);
                return true;
            });
            video.setOnPreparedListener(player -> {
                pemutarVideo = player;
                aturSuaraVideo();
                // Satu video saja: diulang oleh pemutar, tanpa layar hitam.
                player.setLooping(welcomeMedia.size() == 1);
                player.start();
                mediaBerhasilDiputar(filename);
            });
            if (lokal != null) {
                video.setVideoURI(Uri.fromFile(lokal));
            } else {
                videoLewatJaringan = filename;
                video.setVideoURI(Uri.parse(url), authHeaders());
            }
        } else {
            ImageView image = new ImageView(this);
            image.setScaleType(ImageView.ScaleType.FIT_CENTER);
            image.setBackgroundColor(Color.rgb(248, 250, 252));
            mediaSlot.addView(image, new FrameLayout.LayoutParams(-1, -1));
            worker.execute(() -> {
                try {
                    byte[] bytes = lokal != null ? bacaBerkas(lokal) : downloadMedia(url);
                    Bitmap bitmap = decodeImage(bytes, mediaSlot.getWidth(), mediaSlot.getHeight());
                    if (bitmap == null) {
                        throw new IllegalStateException("Gambar sambutan tidak dapat dibaca.");
                    }
                    runOnUiThread(() -> {
                        if (!isCurrentMedia(signature, filename)) {
                            return;
                        }
                        image.setImageBitmap(bitmap);
                        mediaBerhasilDiputar(filename);
                        // Satu gambar saja tampil terus, tidak diunduh ulang.
                        if (welcomeMedia.size() > 1) {
                            handler.postDelayed(nextSlide, welcomeSlideSeconds * 1000L);
                        }
                    });
                } catch (Exception e) {
                    runOnUiThread(() -> mediaGagalDiputar(signature, filename));
                }
            });
        }
    }

    private boolean isCurrentMedia(String signature, String filename) {
        return signature.equals(mediaSignature + "|" + filename)
                && mediaIndex >= 0 && mediaIndex < welcomeMedia.size()
                && filename.equals(welcomeMedia.get(mediaIndex));
    }

    /** Suara mengikuti pengaturan server, juga untuk video yang sedang berputar. */
    private void aturSuaraVideo() {
        if (pemutarVideo == null) return;
        float volume = suaraVideo ? 1f : 0f;
        try {
            pemutarVideo.setVolume(volume, volume);
        } catch (IllegalStateException e) {
            pemutarVideo = null;  // video sudah diganti atau dilepas
        }
    }

    private void mediaBerhasilDiputar(String filename) {
        berkasGagal.remove(filename);
        if (mediaGagal) {
            mediaGagal = false;
            terapkanBarisLoket();
        }
    }

    /**
     * Satu berkas gagal: lewati ke berkas berikutnya. Baru bila SEMUA berkas
     * gagal, panel kembali ke teks sambutan dan dicoba lagi berkala.
     */
    private void mediaGagalDiputar(String signature, String filename) {
        if (!isCurrentMedia(signature, filename)) return;
        berkasGagal.add(filename);
        if (berkasGagal.containsAll(welcomeMedia)) {
            showMediaFallback(signature);
            handler.removeCallbacks(cobaMediaLagi);
            handler.postDelayed(cobaMediaLagi, COBA_MEDIA_LAGI_MS);
        } else {
            handler.removeCallbacks(nextSlide);
            handler.postDelayed(nextSlide, 500L);
        }
    }

    private void showMediaFallback(String signature) {
        if (signature.equals(mediaSignature + "|"
                + (mediaIndex >= 0 && mediaIndex < welcomeMedia.size()
                ? welcomeMedia.get(mediaIndex) : ""))) {
            handler.removeCallbacks(nextSlide);
            applyWelcomeText(welcomeFallbackText);
            mediaGagal = true;
            terapkanBarisLoket();
        }
    }

    private void advanceSlide() {
        if (!welcomeMedia.isEmpty()) {
            showWelcomeMedia((mediaIndex + 1) % welcomeMedia.size());
        }
    }

    private String mediaUrl(String filename) {
        String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
        return base + "/v1/kiosk/media/" + Uri.encode(filename);
    }

    private java.util.Map<String, String> authHeaders() {
        java.util.Map<String, String> headers = new java.util.HashMap<>();
        headers.put("Authorization", "Bearer " + preferences.getString(TOKEN, ""));
        return headers;
    }

    private byte[] downloadMedia(String mediaUrl) throws Exception {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(mediaUrl).openConnection();
            connection.setConnectTimeout(8000);
            connection.setReadTimeout(20000);
            applyHeaders(connection);
            int code = connection.getResponseCode();
            if (code >= 400) throw new IllegalStateException("Media tidak dapat dimuat.");
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            int length;
            try (InputStream input = connection.getInputStream()) {
                while ((length = input.read(buffer)) != -1) {
                    if (output.size() + length > 32 * 1024 * 1024) {
                        throw new IllegalStateException("Ukuran media melebihi 32 MB.");
                    }
                    output.write(buffer, 0, length);
                }
            }
            return output.toByteArray();
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private static final String[] EKSTENSI_VIDEO = {".mp4", ".mkv", ".webm", ".avi"};
    private static final String[] EKSTENSI_MEDIA = {
            ".mp4", ".mkv", ".webm", ".avi",
            ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"};

    private static boolean berakhiran(String filename, String[] ekstensi) {
        String lower = filename.toLowerCase(Locale.ROOT);
        for (String item : ekstensi) {
            if (lower.endsWith(item)) return true;
        }
        return false;
    }

    private static boolean isVideo(String filename) {
        return berakhiran(filename, EKSTENSI_VIDEO);
    }

    /** Nama berkas tanpa pemisah folder, untuk dipakai di folder tablet. */
    private static String namaAman(String filename) {
        String nama = filename.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        return nama.isEmpty() || nama.startsWith(".") ? "_" + nama : nama;
    }

    private boolean sumberTablet() {
        return preferences != null
                && SUMBER_TABLET.equals(preferences.getString(SUMBER_MEDIA, SUMBER_SERVER));
    }

    /**
     * Folder media milik tablet ini: Android/data/id.sistemantrian.kiosk/files/Media.
     * Terlihat dari komputer lewat kabel USB (MTP) tanpa izin penyimpanan.
     */
    private File folderMediaTablet() {
        File folder = getExternalFilesDir("Media");
        if (folder == null) folder = new File(getFilesDir(), "media-tablet");
        //noinspection ResultOfMethodCallIgnored
        folder.mkdirs();
        return folder;
    }

    /** Salinan media server; tersembunyi, diatur sepenuhnya oleh aplikasi. */
    private File folderSalinan() {
        File folder = new File(getFilesDir(), "media-server");
        //noinspection ResultOfMethodCallIgnored
        folder.mkdirs();
        return folder;
    }

    /** Gambar dan video di folder tablet, urut nama seperti di Windows. */
    private List<File> daftarMediaTablet() {
        List<File> hasil = new ArrayList<>();
        File[] isi = folderMediaTablet().listFiles();
        if (isi == null) return hasil;
        for (File item : isi) {
            String nama = item.getName();
            if (item.isFile() && !nama.startsWith(".") && berakhiran(nama, EKSTENSI_MEDIA)) {
                hasil.add(item);
            }
        }
        hasil.sort((a, b) -> a.getName().compareToIgnoreCase(b.getName()));
        return hasil;
    }

    /** Berkas lokal untuk diputar, atau null bila harus lewat jaringan. */
    private File berkasMedia(String filename) {
        if (sumberTablet()) return new File(folderMediaTablet(), filename);
        String kunci = kunciSalinan.get(filename);
        if (kunci == null) return null;
        File salinan = new File(folderSalinan(), kunci);
        return salinan.isFile() ? salinan : null;
    }

    /**
     * Pilih daftar putar menurut sumber media, lalu mulai ulang putaran bila
     * isinya berubah. Pemanggil yang lalu memanggil terapkanBarisLoket().
     */
    private void terapkanMediaSambutan() {
        if (mediaSlot == null) return;
        boolean tablet = sumberTablet();
        List<String> media = new ArrayList<>();
        String signature;
        boolean putar;
        if (tablet) {
            StringBuilder tanda = new StringBuilder(SUMBER_TABLET);
            for (File item : daftarMediaTablet()) {
                media.add(item.getName());
                tanda.append('|').append(item.getName()).append(':')
                        .append(item.length()).append(':').append(item.lastModified());
            }
            signature = tanda.toString();
            putar = !media.isEmpty();
        } else {
            media.addAll(serverMedia);
            List<String> kunci = new ArrayList<>();
            for (String nama : media) kunci.add(String.valueOf(kunciSalinan.get(nama)));
            signature = serverKind + "|" + TextUtils.join("|", media)
                    + "|" + TextUtils.join("|", kunci);
            putar = isMediaKind(serverKind) && !media.isEmpty();
        }
        adaMediaSambutan = putar;
        if (!signature.equals(mediaSignature)) {
            mediaSignature = signature;
            mediaGagal = false;
            berkasGagal.clear();
            handler.removeCallbacks(cobaMediaLagi);
            welcomeMedia = media;
            mediaIndex = 0;
            applyWelcomeText(welcomeFallbackText);
            if (putar) {
                showWelcomeMedia(0);
            } else {
                handler.removeCallbacks(nextSlide);
            }
        } else if (!putar) {
            applyWelcomeText(welcomeFallbackText);
        }
    }

    /**
     * Unduh media daftar putar server yang belum punya salinan, satu per
     * satu, lalu buang salinan yang tidak lagi ada di daftar putar.
     */
    private void sinkronkanSalinan() {
        Set<String> dipakai = new HashSet<>();
        for (String nama : serverMedia) {
            String kunci = kunciSalinan.get(nama);
            if (kunci == null) continue;
            dipakai.add(kunci);
            if (sedangDiunduh.contains(kunci) || new File(folderSalinan(), kunci).isFile()) {
                continue;
            }
            Long gagal = unduhGagalPada.get(kunci);
            if (gagal != null
                    && System.currentTimeMillis() - gagal < JEDA_UNDUH_ULANG_MS) {
                continue;
            }
            sedangDiunduh.add(kunci);
            String url = mediaUrl(nama);
            pengunduh.execute(() -> {
                boolean berhasil;
                try {
                    unduhSalinan(url, kunci);
                    berhasil = true;
                } catch (Exception e) {
                    berhasil = false;
                }
                boolean selesai = berhasil;
                runOnUiThread(() -> salinanSelesai(nama, kunci, selesai));
            });
        }
        if (kunciSalinan.isEmpty() && !serverMedia.isEmpty()) return;  // server lama
        // Antre di belakang unduhan, jadi tidak membuang berkas yang sedang ditulis.
        pengunduh.execute(() -> {
            File[] isi = folderSalinan().listFiles();
            if (isi == null) return;
            for (File item : isi) {
                String nama = item.getName();
                String kunci = nama.endsWith(".part")
                        ? nama.substring(0, nama.length() - 5) : nama;
                if (!dipakai.contains(kunci)) {
                    //noinspection ResultOfMethodCallIgnored
                    item.delete();
                }
            }
        });
    }

    /** Berjalan di thread pengunduh. */
    private void unduhSalinan(String url, String kunci) throws Exception {
        File folder = folderSalinan();
        File tujuan = new File(folder, kunci);
        File sementara = new File(folder, kunci + ".part");
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(url).openConnection();
            connection.setConnectTimeout(8000);
            connection.setReadTimeout(30000);
            applyHeaders(connection);
            if (connection.getResponseCode() >= 400) {
                throw new IllegalStateException("Media tidak dapat diunduh.");
            }
            long panjang = connection.getContentLengthLong();
            if (panjang > 0 && folder.getUsableSpace() < panjang + CADANGAN_RUANG_BYTES) {
                throw new IllegalStateException("Ruang penyimpanan tablet tidak cukup.");
            }
            try (InputStream input = connection.getInputStream();
                 OutputStream output = new FileOutputStream(sementara)) {
                byte[] buffer = new byte[64 * 1024];
                int length;
                while ((length = input.read(buffer)) != -1) {
                    output.write(buffer, 0, length);
                }
            }
            if (panjang > 0 && sementara.length() != panjang) {
                throw new IllegalStateException("Unduhan media terputus.");
            }
            if (!sementara.renameTo(tujuan)) {
                throw new IllegalStateException("Salinan media tidak dapat disimpan.");
            }
        } finally {
            if (connection != null) connection.disconnect();
            if (sementara.exists()) {
                //noinspection ResultOfMethodCallIgnored
                sementara.delete();
            }
        }
    }

    private void salinanSelesai(String nama, String kunci, boolean berhasil) {
        sedangDiunduh.remove(kunci);
        if (!berhasil) {
            unduhGagalPada.put(kunci, System.currentTimeMillis());
            return;
        }
        unduhGagalPada.remove(kunci);
        // Satu video yang diulang terus tidak pernah berganti berkas: pindahkan
        // sekarang ke salinannya, supaya tidak lagi memakai jaringan.
        if (!sumberTablet() && nama.equals(videoLewatJaringan)
                && welcomeMedia.size() == 1 && isCurrentMedia(
                        mediaSignature + "|" + nama, nama)) {
            showWelcomeMedia(mediaIndex);
        }
    }

    private static byte[] bacaBerkas(File berkas) throws Exception {
        if (berkas.length() > 32L * 1024 * 1024) {
            throw new IllegalStateException("Ukuran media melebihi 32 MB.");
        }
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int length;
        try (InputStream input = new FileInputStream(berkas)) {
            while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
        }
        return output.toByteArray();
    }

    private Bitmap decodeImage(byte[] bytes, int width, int height) {
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        int targetWidth = Math.max(1, width);
        int targetHeight = Math.max(1, height);
        int sample = 1;
        while (bounds.outWidth / (sample * 2) >= targetWidth
                && bounds.outHeight / (sample * 2) >= targetHeight) {
            sample *= 2;
        }
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sample;
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
    }

    private void showCategories() {
        showCategories(false);
    }

    private void showCategories(boolean keepResult) {
        // Panel unduhan tidak boleh tertimpa penyegaran daftar layanan.
        if (updating) return;
        if (updateRequired) {
            showUpdatePanel(null);
            return;
        }
        showingConfirmation = false;
        if (!keepResult) {
            showingResult = false;
            showIdleResult();
        }
        ticketChoices.clear();
        invitation.setText("Pilih layanan");
        contentSlot.removeAllViews();

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setOverScrollMode(View.OVER_SCROLL_IF_CONTENT_SCROLLS);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER);
        int kolomLayar = Math.max(1, Math.min(3,
                Math.round(getResources().getDisplayMetrics().widthPixels
                        / getResources().getDisplayMetrics().density / 118f)));
        // Nama layanan selalu satu baris. Nama yang panjang mendapat kartu
        // lebih lebar (kolom lebih sedikit) supaya hurufnya tidak mengecil
        // sampai sulit dibaca.
        Integer induk = path.isEmpty() ? null : path.get(path.size() - 1).id;
        int terpanjang = 0;
        for (Category item : categories) {
            if (Objects.equals(item.parentId, induk)) {
                terpanjang = Math.max(terpanjang, item.name.length());
            }
        }
        int columns = terpanjang > 30 ? 1
                : terpanjang > 18 ? Math.min(kolomLayar, 2) : kolomLayar;
        GridLayout grid = new GridLayout(this);
        grid.setColumnCount(columns);
        grid.setAlignmentMode(GridLayout.ALIGN_BOUNDS);
        grid.setUseDefaultMargins(false);
        grid.setPadding(dp(2), dp(2), dp(2), dp(2));

        List<Category> visible = new ArrayList<>();
        Integer parent = path.isEmpty() ? null : path.get(path.size() - 1).id;
        if (!path.isEmpty()) {
            addCard(grid, "‹", "Kembali", null, new int[]{ABU_LEMBUT, MUTED}, () -> {
                path.remove(path.size() - 1);
                showCategories();
            }, columns);
        }
        for (Category item : categories) {
            if (Objects.equals(item.parentId, parent)) {
                visible.add(item);
                addCategoryCard(grid, item, columns);
            }
        }
        if (visible.isEmpty()) {
            TextView empty = text(
                    categoriesLoaded ? "Tidak ada layanan aktif."
                            : "Layanan akan tampil setelah server terhubung.",
                    18, MUTED, true);
            empty.setGravity(Gravity.CENTER);
            content.addView(empty);
            if (categoriesLoaded) {
                setHint("Periksa pengaturan layanan pada server.", "tunggu");
            } else {
                setHint("Server belum mengirim daftar layanan.", "tunggu");
            }
        } else if (path.isEmpty()) {
            setHint(visible.size() == 1
                    ? "Sentuh tombol di bawah untuk mengambil nomor"
                    : "Sentuh jenis layanan yang Anda butuhkan", "ajak");
        } else {
            Category selected = path.get(path.size() - 1);
            setHint(selected.name + " — pilih layanan, atau sentuh Kembali", "ajak");
        }
        content.addView(grid);
        scroll.addView(content);
        contentSlot.addView(scroll);
        scroll.post(() -> fitCategoryCards(scroll, grid, columns));
        updateAvailability();
    }

    // -----------------------------------------------------------------
    // Baris "SEDANG DILAYANI": di panel atas atau bawah
    // -----------------------------------------------------------------

    private LinearLayout barisLoketKosong() {
        LinearLayout strip = new LinearLayout(this);
        strip.setOrientation(LinearLayout.VERTICAL);
        strip.setVisibility(View.GONE);
        return strip;
    }

    /** "atas", "bawah", atau "" bila tidak ada loket aktif. */
    /** Pilihan tablet bila diatur, selain itu pilihan server. */
    private String posisiLoketBerlaku() {
        String tablet = preferences == null ? IKUTI_SERVER
                : preferences.getString(POSISI_LOKET_TABLET, IKUTI_SERVER);
        return IKUTI_SERVER.equals(tablet) ? posisiLoket : tablet;
    }

    private String letakLoket() {
        if (loketList.isEmpty()) return "";
        String posisi = posisiLoketBerlaku();
        if ("sembunyi".equals(posisi)) return "";
        if ("atas".equals(posisi) || "bawah".equals(posisi)) return posisi;
        // Otomatis: panel atas milik media bila media benar-benar berputar.
        return adaMediaSambutan && !mediaGagal ? "bawah" : "atas";
    }

    /**
     * Pasang baris loket di panel yang sesuai.
     *
     * Ketiga panel anjungan berbobot sama, sehingga memindahkan baris ini
     * tidak menggeser tombol layanan di panel tengah. Di panel atas tanpa
     * media, baris loket mengambil seluruh ruang media dan kartunya besar.
     */
    private void terapkanBarisLoket() {
        if (loketAtas == null || loketBawah == null) return;
        String letak = letakLoket();
        boolean besar = "atas".equals(letak) && !(adaMediaSambutan && !mediaGagal);
        String susunan = letak + (besar ? "|besar|" : "|ringkas|");
        StringBuilder tanda = new StringBuilder(susunan);
        for (Loket loket : loketList) tanda.append(loket.tanda()).append(';');
        if (tanda.toString().equals(tampilanLoket)) return;
        if (!tampilanLoket.isEmpty() && !tampilanLoket.startsWith(susunan) && rootLayout != null) {
            AutoTransition transisi = new AutoTransition();
            transisi.setDuration(350);
            TransitionManager.beginDelayedTransition(rootLayout, transisi);
        }
        tampilanLoket = tanda.toString();

        loketAtas.removeAllViews();
        loketBawah.removeAllViews();
        loketAtas.setVisibility("atas".equals(letak) ? View.VISIBLE : View.GONE);
        loketBawah.setVisibility("bawah".equals(letak) ? View.VISIBLE : View.GONE);
        mediaSlot.setVisibility(besar ? View.GONE : View.VISIBLE);
        loketAtas.setLayoutParams(besar
                ? new LinearLayout.LayoutParams(-1, 0, 1)
                : new LinearLayout.LayoutParams(-1, -2));
        if (!letak.isEmpty()) {
            isiBarisLoket("atas".equals(letak) ? loketAtas : loketBawah, besar);
        }
        if (panelHasilGelap) loketBawah.setVisibility(View.GONE);

        int baris = "bawah".equals(letak)
                ? BARIS_NOMOR_MENUNGGU_BERSAMA_LOKET : BARIS_NOMOR_MENUNGGU;
        if (baris != barisMenunggu) {
            barisMenunggu = baris;
            if (!showingResult && !showingConfirmation) tampilkanNomorMenunggu();
        }
    }

    private void isiBarisLoket(LinearLayout strip, boolean besar) {
        strip.setPadding(0, dp(besar ? 8 : 4), 0, dp(4));
        TextView judul = text("Sedang dilayani", besar ? 14 : 12, MUTED, true);
        judul.setGravity(Gravity.CENTER);
        strip.addView(judul, new LinearLayout.LayoutParams(-1, -2));

        int jumlah = loketList.size();
        // Ringkas: selalu satu deret. Besar: paling banyak dua deret.
        int kolom = besar && jumlah > 4 ? (jumlah + 1) / 2 : jumlah;
        LinearLayout deret = null;
        for (int i = 0; i < jumlah; i++) {
            if (i % kolom == 0) {
                deret = new LinearLayout(this);
                deret.setOrientation(LinearLayout.HORIZONTAL);
                strip.addView(deret, besar
                        ? new LinearLayout.LayoutParams(-1, 0, 1)
                        : new LinearLayout.LayoutParams(-1, dp(54)));
            }
            deret.addView(kartuLoket(loketList.get(i), besar), selLoket());
        }
        // Deret terakhir yang tidak penuh diisi sel kosong agar kartunya sama lebar.
        int sisa = jumlah % kolom;
        for (int i = 0; sisa > 0 && i < kolom - sisa; i++) {
            deret.addView(new View(this), selLoket());
        }
    }

    private LinearLayout.LayoutParams selLoket() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1f);
        params.setMargins(dp(3), dp(3), dp(3), dp(3));
        return params;
    }

    private View kartuLoket(Loket loket, boolean besar) {
        LinearLayout kartu = new LinearLayout(this);
        kartu.setOrientation(LinearLayout.VERTICAL);
        kartu.setGravity(Gravity.CENTER);
        kartu.setPadding(dp(4), dp(2), dp(4), dp(2));
        boolean melayani = !loket.nomor.isEmpty();
        kartu.setBackground(rounded(melayani ? LEMBUT : ABU_LEMBUT, dp(16)));

        TextView nama = text(loket.nama, besar ? 15 : 11, MUTED, true);
        nama.setGravity(Gravity.CENTER);
        pasangAutoFit(nama, 9, besar ? 15 : 11, 1);
        kartu.addView(nama, new LinearLayout.LayoutParams(-1, -2));

        String isi = melayani ? loket.nomor
                : "ISTIRAHAT".equals(loket.status) ? "Istirahat" : "—";
        int maks = melayani ? (besar ? 40 : 18) : (besar ? 18 : 12);
        TextView nomor = text(isi, maks, melayani ? INK : MUTED, true);
        if (melayani) {
            nomor.setTypeface(huruf(800));
            nomor.setFontFeatureSettings("tnum");
        }
        nomor.setGravity(Gravity.CENTER);
        pasangAutoFit(nomor, 10, maks, 1);
        kartu.addView(nomor, new LinearLayout.LayoutParams(-1, 0, 1));

        if (besar && melayani && !loket.layanan.isEmpty()) {
            TextView layanan = text(loket.layanan, 13, UTAMA, false);
            layanan.setGravity(Gravity.CENTER);
            pasangAutoFit(layanan, 9, 13, 1);
            kartu.addView(layanan, new LinearLayout.LayoutParams(-1, -2));
        }
        return kartu;
    }

    private void showIdleResult() {
        kembalikanPanelHasil();
        tampilkanNomorMenunggu();
    }

    /** Kembalikan panel bawah dari layar gelap "Nomor Anda" ke tampilan biasa. */
    private void kembalikanPanelHasil() {
        if (!panelHasilGelap) return;
        panelHasilGelap = false;
        if (panelHasil != null) {
            panelHasil.setBackground(roundedOutline(KARTU, GARIS, dp(24), dp(1)));
        }
        if (resultTitle != null) resultTitle.setTextColor(INK);
        tampilanLoket = "";  // paksa baris loket digambar ulang
        terapkanBarisLoket();
    }

    private int nomorPerHalaman() {
        return KOLOM_NOMOR_MENUNGGU * barisMenunggu;
    }

    private int jumlahHalamanMenunggu() {
        return Math.max(1, (waitingQueueNumbers.size() + nomorPerHalaman() - 1)
                / nomorPerHalaman());
    }

    /** Daftar baca-saja seluruh nomor yang masih menunggu pada hari ini. */
    private void tampilkanNomorMenunggu() {
        if (resultSlot == null) return;
        resultSlot.removeAllViews();
        int halaman = jumlahHalamanMenunggu();
        waitingPage = Math.min(waitingPage, halaman - 1);
        if (resultTitle != null) {
            resultTitle.setText("Nomor menunggu"
                    + (halaman > 1 ? "  " + (waitingPage + 1) + "/" + halaman : ""));
        }

        if (waitingQueueNumbers.isEmpty()) {
            TextView kosong = text("Belum ada nomor yang menunggu.", 16, MUTED, false);
            kosong.setGravity(Gravity.CENTER);
            kosong.setPadding(dp(12), dp(8), dp(12), dp(8));
            resultSlot.addView(kosong, new FrameLayout.LayoutParams(-1, -1));
            return;
        }

        // Baris LinearLayout berbobot, bukan GridLayout: GridLayout yang
        // dibungkus wrap_content membagi lebar 0 ke kolom berbobot, sehingga
        // ubin nomor selebar nol dan daftarnya tampak kosong.
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setGravity(Gravity.CENTER_VERTICAL);
        page.setPadding(dp(2), dp(2), dp(2), dp(2));

        int awal = waitingPage * nomorPerHalaman();
        int akhir = Math.min(awal + nomorPerHalaman(), waitingQueueNumbers.size());
        LinearLayout baris = null;
        for (int index = awal; index < akhir; index++) {
            if ((index - awal) % KOLOM_NOMOR_MENUNGGU == 0) {
                baris = new LinearLayout(this);
                baris.setOrientation(LinearLayout.HORIZONTAL);
                page.addView(baris, new LinearLayout.LayoutParams(-1, -2));
            }
            TextView nomor = text(waitingQueueNumbers.get(index), 19, INK, true);
            nomor.setTypeface(huruf(800));
            nomor.setFontFeatureSettings("tnum");
            nomor.setGravity(Gravity.CENTER);
            nomor.setPadding(dp(4), dp(4), dp(4), dp(4));
            nomor.setBackground(rounded(LEMBUT, dp(16)));
            pasangAutoFit(nomor, 12, 20, 1);
            baris.addView(nomor, selNomorMenunggu());
        }
        // Baris terakhir diisi sel kosong supaya ubinnya tetap selebar ubin lain.
        int sisa = (akhir - awal) % KOLOM_NOMOR_MENUNGGU;
        for (int i = 0; baris != null && sisa > 0 && i < KOLOM_NOMOR_MENUNGGU - sisa; i++) {
            baris.addView(new View(this), selNomorMenunggu());
        }
        resultSlot.addView(page, new FrameLayout.LayoutParams(-1, -1));
    }

    private LinearLayout.LayoutParams selNomorMenunggu() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(52), 1f);
        params.setMargins(dp(3), dp(3), dp(3), dp(3));
        return params;
    }

    private void fitCategoryCards(ScrollView scroll, GridLayout grid, int columns) {
        int count = grid.getChildCount();
        int rows = (count + columns - 1) / columns;
        if (rows < 1 || contentSlot.getHeight() <= 0) return;

        int rowGap = dp(8);
        int availablePerRow = (contentSlot.getHeight() - dp(8)) / rows;
        int preferredHeight = availablePerRow - rowGap;
        int minimumHeight = dp(56);
        int cardHeight = Math.max(minimumHeight, Math.min(dp(132), preferredHeight));
        scroll.setVerticalScrollBarEnabled(preferredHeight < minimumHeight);

        for (int i = 0; i < count; i++) {
            View child = grid.getChildAt(i);
            GridLayout.LayoutParams params = (GridLayout.LayoutParams) child.getLayoutParams();
            params.height = cardHeight;
            child.setLayoutParams(params);
        }
    }

    /** Warna kapsul tetap untuk tiap awalan, supaya A selalu biru, B selalu hijau. */
    private int[] warnaLayanan(String kunci) {
        int indeks = kunci.isEmpty() ? 0 : Character.toUpperCase(kunci.charAt(0)) - 'A';
        return WARNA_LAYANAN[Math.floorMod(indeks, WARNA_LAYANAN.length)];
    }

    private static String awalanLayanan(Category item) {
        if (!item.prefix.isEmpty()) return item.prefix;
        return item.name.isEmpty() ? "•" : item.name.substring(0, 1).toUpperCase(Locale.ROOT);
    }

    private void addCategoryCard(GridLayout grid, Category item, int columns) {
        addCard(grid, item.group ? "›" : awalanLayanan(item), item.name,
                item.group ? "Lihat pilihan layanan" : null,
                item.group ? new int[]{LEMBUT, INK} : warnaLayanan(awalanLayanan(item)), () -> {
                    if (item.group) {
                        path.add(item);
                        showCategories();
                    } else {
                        pendingCategory = item;
                        showConfirmation();
                    }
                }, columns);
        if (!item.group) ticketChoices.add(grid.getChildAt(grid.getChildCount() - 1));
    }

    /** Kartu layanan: kapsul huruf awalan berwarna, lalu nama layanan. */
    private void addCard(
            GridLayout grid, String awalan, String label, String keterangan,
            int[] warna, Runnable action, int columns) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.HORIZONTAL);
        card.setGravity(Gravity.CENTER_VERTICAL);
        card.setPadding(dp(12), dp(8), dp(12), dp(8));
        card.setBackground(latarKartu());
        card.setElevation(dp(2));
        // Kapsul awalan kecil (A, RS, HT, ...): nama layanan yang dibaca,
        // awalannya cukup sebagai penanda warna.
        TextView chip = text(awalan, 16, warna[1], true);
        chip.setTypeface(huruf(800));
        chip.setGravity(Gravity.CENTER);
        chip.setPadding(dp(3), 0, dp(3), 0);
        chip.setBackground(rounded(warna[0], dp(11)));
        pasangSatuBaris(chip, 8, 16);
        card.addView(chip, new LinearLayout.LayoutParams(dp(36), dp(36)));
        LinearLayout tulisan = new LinearLayout(this);
        tulisan.setOrientation(LinearLayout.VERTICAL);
        tulisan.setGravity(Gravity.CENTER_VERTICAL);
        TextView nama = text(label, 19, INK, true);
        nama.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        pasangSatuBaris(nama, 8, 21);
        tulisan.addView(nama, new LinearLayout.LayoutParams(-1, 0, 1));
        if (keterangan != null) {
            TextView ket = text(keterangan, 12, MUTED, false);
            pasangSatuBaris(ket, 8, 12);
            tulisan.addView(ket, new LinearLayout.LayoutParams(-1, -2));
        }
        LinearLayout.LayoutParams tulisanParams = new LinearLayout.LayoutParams(0, -1, 1);
        tulisanParams.leftMargin = dp(8);
        card.addView(tulisan, tulisanParams);
        int widthDp = Math.round(getResources().getDisplayMetrics().widthPixels
                / getResources().getDisplayMetrics().density);
        int cellWidth = Math.max(1, (widthDp - 46) / columns);
        GridLayout.LayoutParams params = new GridLayout.LayoutParams();
        params.width = 0;
        params.height = dp(Math.min(110, Math.max(72, cellWidth * 7 / 10)));
        // Tanpa FILL, GridLayout dapat menyelaraskan baseline TextView.
        // Kartu dua atau tiga baris lalu tampak lebih rendah daripada kartu
        // satu baris pada baris grid yang sama.
        params.rowSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f);
        params.columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f);
        params.setGravity(Gravity.FILL);
        params.setMargins(dp(4), dp(4), dp(4), dp(4));
        grid.addView(card, params);
        pasangEfekSentuh(card);
        card.setOnClickListener(v -> {
            v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
            action.run();
        });
    }

    private StateListDrawable latarKartu() {
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_pressed},
                roundedOutline(LEMBUT, UTAMA, dp(20), dp(2)));
        states.addState(new int[]{}, roundedOutline(KARTU, GARIS, dp(20), dp(1)));
        return states;
    }

    /** Mengecil sedikit saat disentuh dan memantul saat dilepas. */
    private void pasangEfekSentuh(View view) {
        view.setOnTouchListener((v, event) -> {
            int aksi = event.getActionMasked();
            if (aksi == android.view.MotionEvent.ACTION_DOWN && v.isEnabled()) {
                v.animate().scaleX(0.96f).scaleY(0.96f).setDuration(90)
                        .setInterpolator(new android.view.animation.DecelerateInterpolator())
                        .start();
            } else if (aksi == android.view.MotionEvent.ACTION_UP
                    || aksi == android.view.MotionEvent.ACTION_CANCEL) {
                v.animate().scaleX(1f).scaleY(1f).setDuration(280)
                        .setInterpolator(new android.view.animation.OvershootInterpolator(2.2f))
                        .start();
            }
            return false;
        });
    }

    private void showConfirmation() {
        showingConfirmation = true;
        showingResult = false;
        invitation.setText("Pastikan pilihan Anda");
        contentSlot.removeAllViews();

        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setGravity(Gravity.CENTER);
        page.setPadding(dp(4), dp(4), dp(4), dp(4));

        // Penanda langkah: pilih layanan, pastikan, ambil tiket.
        LinearLayout langkah = new LinearLayout(this);
        langkah.setGravity(Gravity.CENTER_VERTICAL);
        for (int i = 0; i < 3; i++) {
            View bar = new View(this);
            bar.setBackground(rounded(i < 2 ? UTAMA : GARIS, dp(4)));
            LinearLayout.LayoutParams barParams = new LinearLayout.LayoutParams(dp(28), dp(5));
            barParams.rightMargin = dp(5);
            langkah.addView(bar, barParams);
        }
        TextView langkahTeks = text("Langkah 2 dari 3", 12, MUTED, true);
        langkahTeks.setPadding(dp(4), 0, 0, 0);
        langkah.addView(langkahTeks);
        LinearLayout.LayoutParams langkahParams = new LinearLayout.LayoutParams(-2, -2);
        langkahParams.gravity = Gravity.CENTER;
        langkahParams.bottomMargin = dp(10);
        page.addView(langkah, langkahParams);

        LinearLayout identity = new LinearLayout(this);
        identity.setGravity(Gravity.CENTER_VERTICAL);
        identity.setPadding(dp(14), dp(12), dp(14), dp(12));
        identity.setBackground(roundedOutline(KARTU, GARIS, dp(24), dp(1)));
        int[] warna = warnaLayanan(awalanLayanan(pendingCategory));
        TextView prefix = text(awalanLayanan(pendingCategory), 22, warna[1], true);
        prefix.setTypeface(huruf(800));
        prefix.setGravity(Gravity.CENTER);
        prefix.setPadding(dp(4), 0, dp(4), 0);
        prefix.setBackground(rounded(warna[0], dp(16)));
        pasangSatuBaris(prefix, 10, 22);
        identity.addView(prefix, new LinearLayout.LayoutParams(dp(52), dp(52)));
        LinearLayout namaLayanan = new LinearLayout(this);
        namaLayanan.setOrientation(LinearLayout.VERTICAL);
        namaLayanan.setPadding(dp(14), 0, 0, 0);
        TextView serviceName = text(pendingCategory.name, 23, INK, true);
        serviceName.setTypeface(huruf(800));
        namaLayanan.addView(serviceName);
        if (!pendingCategory.info.trim().isEmpty()) {
            TextView info = text(pendingCategory.info.trim(), 13, MUTED, false);
            info.setMaxLines(2);
            info.setEllipsize(TextUtils.TruncateAt.END);
            namaLayanan.addView(info);
        }
        identity.addView(namaLayanan, new LinearLayout.LayoutParams(0, -2, 1));
        page.addView(identity, new LinearLayout.LayoutParams(-1, -2));

        LinearLayout actions = new LinearLayout(this);
        actions.setGravity(Gravity.CENTER);
        actions.setPadding(0, dp(12), 0, 0);
        Button cancel = actionButton("Kembali", false);
        cancel.setOnClickListener(v -> {
            v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
            showingConfirmation = false;
            pendingCategory = null;
            pendingRequestId = null;
            showCategories();
        });
        actions.addView(cancel, new LinearLayout.LayoutParams(0, dp(58), 2));
        Button yes = actionButton("Ya, ambil nomor", true);
        yes.setOnClickListener(v -> {
            v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
            issueTicket();
        });
        pasangEfekSentuh(yes);
        LinearLayout.LayoutParams yesParams = new LinearLayout.LayoutParams(0, dp(58), 3);
        yesParams.leftMargin = dp(10);
        actions.addView(yes, yesParams);
        page.addView(actions, new LinearLayout.LayoutParams(-1, -2));
        contentSlot.addView(page);
        page.setAlpha(0f);
        page.setTranslationX(dp(24));
        page.animate().alpha(1f).translationX(0f).setDuration(240)
                .setInterpolator(new android.view.animation.DecelerateInterpolator()).start();
        handler.removeCallbacks(confirmTimeout);
        handler.postDelayed(confirmTimeout, 15000);
        batasKonfirmasiMillis = System.currentTimeMillis() + 15000;
        perbaruiHitungMundurKonfirmasi();
    }

    /** Sisa waktu sebelum pilihan dibatalkan sendiri, terlihat oleh pengunjung. */
    private void perbaruiHitungMundurKonfirmasi() {
        if (!showingConfirmation || requestInFlight) return;
        long sisa = Math.max(0L,
                (batasKonfirmasiMillis - System.currentTimeMillis() + 999L) / 1000L);
        setHint("Sentuh Ya untuk mengambil nomor · kembali otomatis dalam "
                + sisa + " detik", "konfirmasi");
    }

    private final Runnable confirmTimeout = () -> {
        if (showingConfirmation) {
            pendingCategory = null;
            pendingRequestId = null;
            showCategories();
            setHint("Pilihan dibatalkan karena tidak ada aktivitas.", "ajak");
        }
    };

    private void issueTicket() {
        if (pendingCategory == null || requestInFlight) return;
        handler.removeCallbacks(confirmTimeout);
        requestInFlight = true;
        if (pendingRequestId == null) pendingRequestId = UUID.randomUUID().toString();
        setHint("Mengambil nomor…", "tunggu");
        request("POST", "/v1/kiosk/tickets",
                new JSONObjectBuilder()
                        .put("category_id", pendingCategory.id)
                        .put("request_id", pendingRequestId)
                        .build(),
                json -> {
                    requestInFlight = false;
                    JSONObject ticket = json.getJSONObject("data");
                    String number = ticket.getString("queue_number");
                    Category issued = pendingCategory;
                    pendingCategory = null;
                    pendingRequestId = null;
                    int cooldownSeconds = Math.max(
                            0, ticket.optInt("cooldown_seconds", 10));
                    readyAtMillis = System.currentTimeMillis() + cooldownSeconds * 1000L;
                    JSONArray lines = ticket.getJSONArray("ticket_lines");
                    List<String> receipt = new ArrayList<>();
                    for (int i = 0; i < lines.length(); i++) receipt.add(lines.getString(i));
                    JSONObject layout = ticket.optJSONObject("ticket_layout");
                    JSONObject raster = ticket.optJSONObject("ticket_raster");
                    showResult(number, issued.name);
                    updateAvailability();
                    UsbEscPosPrinter.print(this, number, receipt, layout, raster, message -> {
                        boolean printed = message.contains("tercetak");
                        reportPrinter(printed, message);
                        if (hint != null && showingResult) {
                            setHint(message, printed ? "hasil" : "gagal");
                        }
                    });
                    loadDisplay();
                },
                message -> {
                    requestInFlight = false;
                    setHint("Nomor belum dapat dipastikan. Sentuh ulang untuk mencoba lagi.", "salah");
                    showRetry();
                });
    }

    private void showRetry() {
        kembalikanPanelHasil();
        if (resultTitle != null) resultTitle.setText("Permintaan tiket belum selesai");
        resultSlot.removeAllViews();
        LinearLayout retry = new LinearLayout(this);
        retry.setGravity(Gravity.CENTER);
        Button button = actionButton("Ulangi permintaan tiket", true);
        button.setOnClickListener(v -> issueTicket());
        retry.addView(button, new LinearLayout.LayoutParams(-1, dp(64)));
        resultSlot.addView(retry, new FrameLayout.LayoutParams(-1, -1));
    }

    private void showResult(String number, String service) {
        showingConfirmation = false;
        showingResult = true;
        boolean testTicket = number.startsWith("UJI-");
        // Daftar layanan tetap berada di panel tengah. Selama hasil tampil,
        // tombolnya dinonaktifkan agar satu pengunjung tidak mengambil dua
        // nomor sebelum tiket pertama selesai dicetak.
        showCategories(true);
        // Panel bawah berubah gelap dan tiket "keluar dari printer": nomor
        // besar di kartu putih, lalu bilah yang menyusut sampai layar kembali.
        panelHasilGelap = true;
        if (panelHasil != null) panelHasil.setBackground(rounded(HASIL, dp(24)));
        if (loketBawah != null) loketBawah.setVisibility(View.GONE);
        if (resultTitle != null) {
            resultTitle.setText(testTicket ? "Tiket uji" : "Nomor Anda");
            resultTitle.setTextColor(Color.WHITE);
        }
        LinearLayout result = new LinearLayout(this);
        result.setOrientation(LinearLayout.VERTICAL);
        result.setGravity(Gravity.CENTER);
        LinearLayout tiket = new LinearLayout(this);
        tiket.setOrientation(LinearLayout.VERTICAL);
        tiket.setGravity(Gravity.CENTER);
        tiket.setPadding(dp(12), dp(10), dp(12), dp(10));
        tiket.setBackground(rounded(KARTU, dp(22)));
        TextView serviceView = text(testTicket ? "Contoh tiket" : service, 14, UTAMA, true);
        serviceView.setGravity(Gravity.CENTER);
        pasangAutoFit(serviceView, 10, 14, 1);
        tiket.addView(serviceView, new LinearLayout.LayoutParams(-1, -2));
        TextView numberView = text(number, 56, INK, true);
        numberView.setTypeface(huruf(800));
        numberView.setFontFeatureSettings("tnum");
        numberView.setGravity(Gravity.CENTER);
        pasangAutoFit(numberView, 24, 60, 1);
        tiket.addView(numberView, new LinearLayout.LayoutParams(-1, dp(66)));
        LinearLayout.LayoutParams tiketParams = new LinearLayout.LayoutParams(-1, -2);
        tiketParams.leftMargin = dp(28);
        tiketParams.rightMargin = dp(28);
        result.addView(tiket, tiketParams);
        TextView ambil = text("Silakan ambil tiket Anda", 14, Color.argb(225, 255, 255, 255), true);
        ambil.setGravity(Gravity.CENTER);
        ambil.setPadding(0, dp(8), 0, dp(6));
        result.addView(ambil);
        FrameLayout jalur = new FrameLayout(this);
        jalur.setBackground(rounded(UTAMA, dp(4)));
        View isiJalur = new View(this);
        isiJalur.setBackground(rounded(EMAS, dp(4)));
        jalur.addView(isiJalur, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout.LayoutParams jalurParams = new LinearLayout.LayoutParams(dp(160), dp(5));
        jalurParams.gravity = Gravity.CENTER;
        result.addView(jalur, jalurParams);
        resultSlot.removeAllViews();
        resultSlot.addView(result, new FrameLayout.LayoutParams(-1, -1));
        tiket.setAlpha(0f);
        tiket.setTranslationY(dp(36));
        tiket.animate().alpha(1f).translationY(0f).setDuration(420)
                .setInterpolator(new android.view.animation.OvershootInterpolator(1.1f)).start();
        isiJalur.setPivotX(0f);
        isiJalur.animate().scaleX(0f).setDuration(LAMA_HASIL_MS)
                .setInterpolator(new android.view.animation.LinearInterpolator()).start();
        setHint("Nomor sudah terbit. Tiket sedang dicetak…", "hasil");
        handler.removeCallbacks(resultTimeout);
        handler.postDelayed(resultTimeout, LAMA_HASIL_MS);
    }

    private final Runnable resultTimeout = () -> {
        if (!showingResult) return;
        path.clear();
        showCategories();
    };

    private void updateAvailability() {
        if (ticketChoices.isEmpty() || showingConfirmation) return;
        long seconds = Math.max(0L,
                (readyAtMillis - System.currentTimeMillis() + 999L) / 1000L);
        boolean enabled = registrationOpen && seconds == 0 && !requestInFlight && !showingResult;
        for (View choice : ticketChoices) {
            if (choice.isEnabled() == enabled) continue;
            choice.setEnabled(enabled);
            choice.animate().alpha(enabled ? 1f : 0.45f).setDuration(200).start();
        }
        if (showingResult) return;
        if (!registrationOpen) {
            setHint("Pendaftaran nomor antrian sedang ditutup sementara.", "tunggu");
        } else if (seconds > 0) {
            setHint("Mohon tunggu " + seconds
                    + " detik sebelum mengambil nomor berikutnya.", "tunggu");
        } else {
            String message = path.isEmpty()
                    ? "Sentuh jenis layanan yang Anda butuhkan"
                    : path.get(path.size() - 1).name
                            + " — pilih layanan, atau sentuh Kembali";
            setHint(message, "ajak");
        }
    }

    private void setHint(String message, String tone) {
        if (hint == null) return;
        hint.setText(message);
        int bg = LEMBUT;
        int fg = UTAMA;
        if ("konfirmasi".equals(tone)) {
            bg = LEMBUT;
            fg = INK;
        } else if ("tunggu".equals(tone)) {
            bg = Color.rgb(254, 243, 199);
            fg = Color.rgb(146, 64, 14);
        } else if ("hasil".equals(tone)) {
            bg = Color.rgb(220, 245, 232);
            fg = Color.rgb(15, 122, 74);
        } else if ("gagal".equals(tone) || "salah".equals(tone)) {
            bg = "gagal".equals(tone) ? Color.rgb(245, 158, 11)
                    : Color.rgb(254, 226, 226);
            fg = "gagal".equals(tone) ? Color.rgb(31, 19, 0)
                    : Color.rgb(153, 27, 27);
        }
        hint.setTextColor(fg);
        hint.setBackground(rounded(bg, dp(24)));
    }

    private void request(
            String method, String path, org.json.JSONObject body,
            Success success, Failure failure) {
        worker.execute(() -> {
            HttpURLConnection connection = null;
            try {
                String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
                connection = (HttpURLConnection) new URL(base + path).openConnection();
                connection.setRequestMethod(method);
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(8000);
                applyHeaders(connection);
                connection.setRequestProperty("Accept", "application/json");
                if (body != null) {
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                    connection.getOutputStream().write(
                            body.toString().getBytes(StandardCharsets.UTF_8));
                }
                int code = connection.getResponseCode();
                InputStream stream = code < 400
                        ? connection.getInputStream() : connection.getErrorStream();
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                byte[] buffer = new byte[4096];
                int length;
                while ((length = stream.read(buffer)) != -1) output.write(buffer, 0, length);
                stream.close();
                Object response = new JSONTokener(
                        new String(output.toByteArray(), StandardCharsets.UTF_8))
                        .nextValue();
                if (code >= 400) {
                    String detail = response instanceof JSONObject
                            ? ((JSONObject) response).optString(
                                    "detail", "Server menolak permintaan.")
                            : "Server menolak permintaan.";
                    throw new IllegalStateException(detail);
                }
                JSONObject wrapped = new JSONObject().put("data", response);
                handler.post(() -> {
                    try {
                        success.accept(wrapped);
                    } catch (Exception e) {
                        failure.accept("Jawaban server tidak dapat dibaca.");
                    }
                });
            } catch (Exception e) {
                String message = e.getMessage() == null
                        ? "Server tidak dapat dihubungi." : e.getMessage();
                handler.post(() -> failure.accept(message));
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    /** UUID perangkat ini, dibuat sekali dan disimpan selamanya. */
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
        return name.isEmpty() ? ("Anjungan " + Build.MODEL) : name;
    }

    /** Kepala yang dikirim pada setiap permintaan ke server. */
    private void applyHeaders(HttpURLConnection connection) {
        connection.setRequestProperty("Authorization",
                "Bearer " + preferences.getString(TOKEN, ""));
        connection.setRequestProperty("X-Device-Id", deviceId());
        connection.setRequestProperty("X-Device-Name", deviceName());
        connection.setRequestProperty("X-Device-Kind", DEVICE_KIND);
        connection.setRequestProperty("X-App-Version-Code", String.valueOf(appVersionCode()));
        connection.setRequestProperty("X-App-Version-Name", appVersionName());
    }

    /** Hasil cetak terakhir, untuk kolom Printer di Layanan Anjungan. Tidak pernah mengganggu. */
    private void reportPrinter(boolean ok, String message) {
        try {
            JSONObject body = new JSONObject()
                    .put("ok", ok)
                    .put("message", message == null ? "" : message.length() > 190
                            ? message.substring(0, 190) : message);
            request("POST", "/v1/kiosk/printer", body, json -> { }, error -> { });
        } catch (Exception ignored) {
            // Laporan printer hanya keterangan.
        }
    }

    private int appVersionCode() {
        try {
            PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28
                    ? (int) info.getLongVersionCode() : info.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    private String appVersionName() {
        try {
            String name = getPackageManager()
                    .getPackageInfo(getPackageName(), 0).versionName;
            return name == null ? "?" : name;
        } catch (Exception e) {
            return "?";
        }
    }

    private String requiredVersionLabel() {
        return latestVersionCode >= minVersionCode && !latestVersionName.isEmpty()
                ? latestVersionName : "kode " + minVersionCode;
    }

    private void showUpdatePanel(String error) {
        if (contentSlot == null) return;
        showingConfirmation = false;
        showingResult = false;
        ticketChoices.clear();
        contentSlot.removeAllViews();
        invitation.setText("APLIKASI PERLU DIPERBARUI");
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setGravity(Gravity.CENTER);
        panel.setPadding(dp(16), dp(8), dp(16), dp(8));
        TextView detail = text("Versi tablet " + appVersionName()
                + " · server membutuhkan " + requiredVersionLabel()
                + "\nPengambilan nomor dihentikan sampai diperbarui.", 15, MUTED, true);
        detail.setGravity(Gravity.CENTER);
        panel.addView(detail);
        if (error != null) {
            TextView errorView = text(error, 14, RED, true);
            errorView.setGravity(Gravity.CENTER);
            errorView.setPadding(0, dp(8), 0, 0);
            panel.addView(errorView);
        }
        Button update = actionButton("PERBARUI DARI SERVER", true);
        update.setEnabled(latestVersionCode > appVersionCode());
        update.setOnClickListener(v -> startUpdate());
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(60));
        params.topMargin = dp(14);
        panel.addView(update, params);
        TextView note = text(latestVersionCode > appVersionCode()
                ? "Untuk petugas. Android akan meminta izin memasang."
                : "APK baru belum tersedia di server. Jalankan build-android-kiosk.ps1 di komputer server.",
                12, MUTED, false);
        note.setGravity(Gravity.CENTER);
        note.setPadding(0, dp(8), 0, 0);
        panel.addView(note);
        contentSlot.addView(panel);
        setHint("Hubungi petugas untuk memperbarui anjungan", "tunggu");
    }

    private void startUpdate() {
        if (updating) return;
        if (Build.VERSION.SDK_INT >= 26
                && !getPackageManager().canRequestPackageInstalls()) {
            Toast.makeText(this,
                    "Izinkan \"Pasang aplikasi tidak dikenal\" untuk Anjungan Antrian, "
                            + "lalu kembali dan tekan Perbarui lagi.",
                    Toast.LENGTH_LONG).show();
            startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getPackageName())));
            return;
        }
        updating = true;
        contentSlot.removeAllViews();
        invitation.setText("MENGUNDUH VERSI " + latestVersionName);
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setGravity(Gravity.CENTER);
        panel.setPadding(dp(16), dp(8), dp(16), dp(8));
        android.widget.ProgressBar bar = new android.widget.ProgressBar(
                this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(1000);
        panel.addView(bar, new LinearLayout.LayoutParams(-1, dp(16)));
        TextView progress = text("Menghubungi server…", 14, MUTED, true);
        progress.setGravity(Gravity.CENTER);
        progress.setPadding(0, dp(8), 0, 0);
        panel.addView(progress);
        contentSlot.addView(panel);
        setHint("Jangan matikan tablet selama pembaruan", "tunggu");

        new Thread(() -> {
            HttpURLConnection connection = null;
            PackageInstaller.Session session = null;
            try {
                String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
                connection = (HttpURLConnection) new URL(base + "/v1/kiosk/app/apk").openConnection();
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(30000);
                applyHeaders(connection);
                int code = connection.getResponseCode();
                if (code != 200) throw new IllegalStateException(
                        "server menjawab " + code);
                long total = connection.getContentLengthLong();

                PackageInstaller installer = getPackageManager().getPackageInstaller();
                PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(
                        PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(getPackageName());
                if (total > 0) params.setSize(total);
                int sessionId = installer.createSession(params);
                session = installer.openSession(sessionId);
                try (InputStream input = connection.getInputStream();
                     OutputStream output = session.openWrite("anjungan.apk", 0, total)) {
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
                PendingIntent pending = PendingIntent.getBroadcast(
                        this, sessionId, status, flags);
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
                handler.post(() -> {
                    updating = false;
                    if (updateRequired) {
                        showUpdatePanel("Unduhan gagal: " + message);
                    } else {
                        Toast.makeText(this, "Unduhan gagal: " + message,
                                Toast.LENGTH_LONG).show();
                        path.clear();
                        showCategories();
                    }
                });
            } finally {
                if (connection != null) connection.disconnect();
            }
        }).start();
    }

    /** Tukar kode pasang dengan token khusus perangkat ini. */
    private void pairDevice(String code, AlertDialog dialog, EditText codeField) {
        try {
            JSONObject body = new JSONObject()
                    .put("code", code)
                    .put("device_id", deviceId())
                    .put("name", deviceName())
                    .put("kind", DEVICE_KIND);
            codeField.setEnabled(false);
            request("POST", "/v1/kiosk/pair", body, json -> {
                String deviceToken = json.getJSONObject("data").getString("token");
                preferences.edit().putString(TOKEN, deviceToken).apply();
                dialog.dismiss();
                Toast.makeText(this, "Tablet terpasang ke server.", Toast.LENGTH_LONG).show();
                categories.clear();
                path.clear();
                categoriesLoaded = false;
                showServerPlaceholder("Tablet terpasang. Menghubungkan ke server…");
                loadCategories();
                loadDisplay();
            }, message -> {
                codeField.setEnabled(true);
                codeField.setError(message);
            });
        } catch (Exception e) {
            codeField.setError("Kode tidak dapat dikirim.");
        }
    }

    private void showSettings() {
        LinearLayout fields = new LinearLayout(this);
        fields.setPadding(dp(16), 0, dp(16), dp(8));
        fields.setOrientation(LinearLayout.VERTICAL);

        LinearLayout koneksi = bagianPengaturan(fields, "Koneksi server",
                "Pencarian otomatis bekerja di jaringan lokal yang sama.");
        EditText server = isianPengaturan(koneksi, "Alamat server",
                "http://192.168.1.10:8765");
        server.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        server.setText(preferences.getString(SERVER, ""));
        koneksi.removeView(server);
        LinearLayout serverRow = new LinearLayout(this);
        serverRow.setGravity(Gravity.CENTER_VERTICAL);
        serverRow.addView(server, new LinearLayout.LayoutParams(0, -2, 1));
        Button findServer = smallButton("Cari");
        findServer.setOnClickListener(v -> {
            findServer.setEnabled(false);
            findServer.setText("…");
            discoverServer(address -> {
                server.setText(address);
                findServer.setEnabled(true);
                findServer.setText("Cari");
                Toast.makeText(this, "Server ditemukan: " + address,
                        Toast.LENGTH_LONG).show();
            }, message -> {
                findServer.setEnabled(true);
                findServer.setText("Cari");
                Toast.makeText(this, message, Toast.LENGTH_LONG).show();
            });
        });
        LinearLayout.LayoutParams cariParams = new LinearLayout.LayoutParams(-2, dp(44));
        cariParams.leftMargin = dp(8);
        serverRow.addView(findServer, cariParams);
        koneksi.addView(serverRow);
        EditText token = isianPengaturan(koneksi, "Token API anjungan", "Token API anjungan");
        token.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        token.setText(preferences.getString(TOKEN, DEFAULT_TOKEN));
        EditText name = isianPengaturan(koneksi, "Nama perangkat", "Anjungan Lobi");
        name.setText(deviceName());
        EditText pairCode = isianPengaturan(koneksi, "Kode pasang",
                "6 angka dari Layanan Anjungan");
        pairCode.setInputType(InputType.TYPE_CLASS_NUMBER);
        TextView pairHint = text(
                "Isi kode pasang untuk mendapat token khusus tablet ini; token di atas tidak perlu diketik.",
                12, MUTED, false);
        pairHint.setPadding(dp(2), dp(6), 0, 0);
        koneksi.addView(pairHint);

        LinearLayout printer = bagianPengaturan(fields, "Printer tiket",
                "Printer ESC/POS USB dideteksi otomatis, tanpa driver tambahan.");
        TextView printerStatus = text(UsbEscPosPrinter.detect(this), 13, INK, false);
        printerStatus.setPadding(dp(2), dp(6), 0, 0);
        printer.addView(printerStatus);
        Button detectPrinter = smallButton("Deteksi printer USB");
        detectPrinter.setOnClickListener(v ->
                printerStatus.setText(UsbEscPosPrinter.detect(this)));
        printer.addView(detectPrinter, tombolPengaturan());

        LinearLayout tampilan = bagianPengaturan(fields, "Tampilan anjungan",
                "Berlaku seketika untuk tablet ini, tanpa tombol Simpan.");
        tampilan.addView(labelPengaturan("Sumber media sambutan"));
        RadioGroup sumber = new RadioGroup(this);
        RadioButton dariServer = radioPengaturan("Daftar putar server (disalin ke tablet)");
        RadioButton dariTablet = radioPengaturan("Folder media di tablet ini");
        sumber.addView(dariServer);
        sumber.addView(dariTablet);
        sumber.check(sumberTablet() ? dariTablet.getId() : dariServer.getId());
        tampilan.addView(sumber);
        TextView mediaStatus = text(ringkasanMedia(), 12, MUTED, false);
        mediaStatus.setPadding(dp(2), dp(2), 0, 0);
        tampilan.addView(mediaStatus);
        Button kelolaMedia = smallButton("Kelola media tablet");
        kelolaMedia.setOnClickListener(v -> showMediaTablet());
        tampilan.addView(kelolaMedia, tombolPengaturan());
        tampilan.addView(labelPengaturan("Posisi baris loket di tablet ini"));
        RadioGroup posisi = new RadioGroup(this);
        String posisiTersimpan = preferences.getString(POSISI_LOKET_TABLET, IKUTI_SERVER);
        for (String[] pilihan : PILIHAN_POSISI_LOKET) {
            RadioButton tombolPosisi = radioPengaturan(pilihan[1]);
            tombolPosisi.setTag(pilihan[0]);
            posisi.addView(tombolPosisi);
            if (pilihan[0].equals(posisiTersimpan)) posisi.check(tombolPosisi.getId());
        }
        if (posisi.getCheckedRadioButtonId() == -1) {
            posisi.check(posisi.getChildAt(0).getId());
        }
        posisi.setOnCheckedChangeListener((group, checkedId) -> {
            Object nilai = group.findViewById(checkedId).getTag();
            preferences.edit().putString(POSISI_LOKET_TABLET, String.valueOf(nilai)).apply();
            terapkanBarisLoket();
        });
        tampilan.addView(posisi);
        tampilan.addView(labelPengaturan("Tema tablet ini"));
        RadioGroup pilihanTema = new RadioGroup(this);
        String temaTersimpan = preferences.getString(TEMA_TABLET, IKUTI_SERVER_TEMA);
        for (String[] pilihan : PILIHAN_TEMA) {
            RadioButton tombolTema = radioPengaturan(pilihan[1]);
            tombolTema.setTag(pilihan[0]);
            pilihanTema.addView(tombolTema);
            if (pilihan[0].equals(temaTersimpan)) pilihanTema.check(tombolTema.getId());
        }
        if (pilihanTema.getCheckedRadioButtonId() == -1) {
            pilihanTema.check(pilihanTema.getChildAt(0).getId());
        }
        pilihanTema.setOnCheckedChangeListener((group, checkedId) -> {
            Object nilai = group.findViewById(checkedId).getTag();
            preferences.edit().putString(TEMA_TABLET, String.valueOf(nilai)).apply();
            terapkanTemaBilaBerubah();
        });
        tampilan.addView(pilihanTema);
        // Berlaku seketika, terpisah dari tombol Simpan: tidak menyentuh
        // alamat server atau token.
        sumber.setOnCheckedChangeListener((group, checkedId) -> {
            preferences.edit().putString(SUMBER_MEDIA,
                    checkedId == dariTablet.getId() ? SUMBER_TABLET : SUMBER_SERVER).apply();
            terapkanMediaSambutan();
            terapkanBarisLoket();
            if (!sumberTablet() && hasServerConfig()) sinkronkanSalinan();
            mediaStatus.setText(ringkasanMedia());
        });

        LinearLayout perawatan = bagianPengaturan(fields, "Aplikasi dan server", null);
        boolean newer = latestVersionCode > appVersionCode();
        TextView versionInfo = text("Versi aplikasi " + appVersionName()
                + (newer ? " · versi " + latestVersionName + " tersedia di server"
                        : latestVersionCode > 0 ? " · terbaru" : ""),
                13, newer ? Color.rgb(180, 83, 9) : INK, newer);
        versionInfo.setPadding(dp(2), dp(6), 0, 0);
        perawatan.addView(versionInfo);
        Button updateButton = smallButton("Perbarui ke " + latestVersionName);
        if (newer) perawatan.addView(updateButton, tombolPengaturan());
        Button restartApi = smallButton("Restart API server");
        restartApi.setEnabled(hasServerConfig());
        restartApi.setOnClickListener(v -> confirmRestartApi(restartApi));
        perawatan.addView(restartApi, tombolPengaturan());
        AlertDialog dialog = pembuatDialog()
                .setTitle("Pengaturan anjungan")
                .setView(gulungan(fields))
                .setPositiveButton("Simpan", null)
                .setNeutralButton("Uji cetak", null)
                .setNegativeButton("Batal", null).create();
        if (dialog.getWindow() != null) {
            dialog.getWindow().setBackgroundDrawable(rounded(LATAR, dp(28)));
        }
        dialog.setOnShowListener(d -> {
            rapikanTombolDialog(dialog);
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                    String address = server.getText().toString().trim();
                    String apiToken = token.getText().toString().trim();
                    String code = pairCode.getText().toString().replaceAll("[^0-9]", "");
                    if (!(address.startsWith("http://") || address.startsWith("https://"))) {
                        server.setError("Alamat harus diawali http:// atau https://");
                        return;
                    }
                    preferences.edit().putString(DEVICE_NAME, name.getText().toString().trim())
                            .apply();
                    if (!code.isEmpty()) {
                        if (code.length() != 6) {
                            pairCode.setError("Kode pasang 6 angka");
                            return;
                        }
                        preferences.edit().putString(SERVER, address).apply();
                        pairDevice(code, dialog, pairCode);
                        return;
                    }
                    if (apiToken.length() < 8) {
                        token.setError("Token minimal 8 karakter");
                        return;
                    }
                    preferences.edit().putString(SERVER, address)
                            .putString(TOKEN, apiToken).apply();
                    dialog.dismiss();
                    categories.clear();
                    path.clear();
                    categoriesLoaded = false;
                    showServerPlaceholder("Pengaturan tersimpan. Menghubungkan ke server…");
                    loadCategories();
                    loadDisplay();
                });
            updateButton.setOnClickListener(v -> {
                dialog.dismiss();
                startUpdate();
            });
            dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v -> {
                dialog.dismiss();
                confirmTestTicket();
            });
        });
        dialog.show();
    }

    /** Kartu satu bagian di dialog pengaturan: judul, keterangan, lalu isinya. */
    private LinearLayout bagianPengaturan(LinearLayout induk, String judul, String keterangan) {
        LinearLayout kartu = new LinearLayout(this);
        kartu.setOrientation(LinearLayout.VERTICAL);
        kartu.setPadding(dp(14), dp(12), dp(14), dp(14));
        kartu.setBackground(roundedOutline(KARTU, GARIS, dp(18), dp(1)));
        TextView kepala = text(judul, 15, INK, true);
        kepala.setTypeface(huruf(800));
        kartu.addView(kepala);
        if (keterangan != null) {
            TextView ket = text(keterangan, 12, MUTED, false);
            ket.setPadding(0, dp(2), 0, 0);
            kartu.addView(ket);
        }
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(10);
        induk.addView(kartu, params);
        return kartu;
    }

    private TextView labelPengaturan(String isi) {
        TextView label = text(isi, 12, MUTED, true);
        label.setPadding(dp(2), dp(12), 0, dp(2));
        return label;
    }

    /** Kolom isian berlabel dengan latar lembut, ditambahkan ke bagian. */
    private EditText isianPengaturan(LinearLayout bagian, String label, String petunjuk) {
        TextView judul = labelPengaturan(label);
        judul.setPadding(dp(2), dp(10), 0, dp(4));
        bagian.addView(judul);
        EditText isian = new EditText(this);
        isian.setHint(petunjuk);
        isian.setSingleLine(true);
        isian.setTextColor(INK);
        isian.setHintTextColor(Color.rgb(148, 163, 184));
        isian.setTextSize(15 * uiScale);
        isian.setPadding(dp(12), dp(10), dp(12), dp(10));
        isian.setBackground(roundedOutline(LATAR, GARIS, dp(12), dp(1)));
        bagian.addView(isian, new LinearLayout.LayoutParams(-1, -2));
        return isian;
    }

    private RadioButton radioPengaturan(String isi) {
        RadioButton tombol = new RadioButton(this);
        tombol.setId(View.generateViewId());
        tombol.setText(isi);
        tombol.setTextColor(INK);
        tombol.setTextSize(14 * uiScale);
        tombol.setButtonTintList(android.content.res.ColorStateList.valueOf(UTAMA));
        tombol.setPadding(dp(4), dp(6), 0, dp(6));
        return tombol;
    }

    private LinearLayout.LayoutParams tombolPengaturan() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-2, dp(44));
        params.topMargin = dp(8);
        return params;
    }

    /** Dialog pengaturan makin panjang; tablet kecil perlu menggulungnya. */
    private ScrollView gulungan(View isi) {
        ScrollView scroll = new ScrollView(this);
        scroll.addView(isi);
        return scroll;
    }

    private String ringkasanMedia() {
        if (sumberTablet()) {
            int jumlah = daftarMediaTablet().size();
            return jumlah == 0
                    ? "Folder media tablet masih kosong; panel menampilkan teks sambutan."
                    : jumlah + " berkas di folder tablet, diputar urut nama berkas.";
        }
        if (serverMedia.isEmpty()) return "Daftar putar server kosong atau belum dimuat.";
        if (kunciSalinan.isEmpty()) {
            return "Server belum mengirim info berkas; media diputar lewat jaringan.";
        }
        int siap = 0;
        for (String nama : serverMedia) {
            String kunci = kunciSalinan.get(nama);
            if (kunci != null && new File(folderSalinan(), kunci).isFile()) siap++;
        }
        return siap + " dari " + serverMedia.size()
                + " berkas sudah tersimpan di tablet"
                + (siap < serverMedia.size() ? "; sisanya diputar lewat jaringan sambil diunduh."
                        : "; diputar tanpa jaringan.");
    }

    /** Daftar berkas di folder media tablet: tambah dari tablet, atau hapus. */
    private void showMediaTablet() {
        LinearLayout isi = new LinearLayout(this);
        isi.setOrientation(LinearLayout.VERTICAL);
        isi.setPadding(dp(20), dp(4), dp(20), 0);
        TextView petunjuk = text(
                "Dipakai bila sumber media sambutan = Folder media di tablet ini. "
                        + "Salin gambar/video lewat kabel USB dari komputer ke folder:\n"
                        + folderMediaTablet().getAbsolutePath()
                        + "\natau tekan Tambah berkas. Urutan putar mengikuti nama berkas "
                        + "(01_..., 02_...). Video paling aman MP4 (H.264).",
                12, MUTED, false);
        isi.addView(petunjuk);
        List<File> berkas = daftarMediaTablet();
        if (berkas.isEmpty()) {
            TextView kosong = text("Folder masih kosong.", 14, INK, true);
            kosong.setPadding(0, dp(10), 0, dp(4));
            isi.addView(kosong);
        }
        AlertDialog[] dialog = new AlertDialog[1];
        for (File item : berkas) {
            LinearLayout baris = new LinearLayout(this);
            baris.setGravity(Gravity.CENTER_VERTICAL);
            baris.setPadding(0, dp(6), 0, 0);
            String ukuran = String.format(Locale.ROOT, "%.1f MB", item.length() / 1048576.0);
            TextView nama = text(item.getName() + "\n" + (isVideo(item.getName())
                    ? "video" : "gambar") + " · " + ukuran, 13, INK, false);
            baris.addView(nama, new LinearLayout.LayoutParams(0, -2, 1));
            Button hapus = smallButton("Hapus");
            hapus.setOnClickListener(v -> pembuatDialog()
                    .setTitle("Hapus " + item.getName() + "?")
                    .setMessage("Berkas dihapus dari tablet ini.")
                    .setNegativeButton("Batal", null)
                    .setPositiveButton("Hapus", (d, w) -> {
                        //noinspection ResultOfMethodCallIgnored
                        item.delete();
                        terapkanMediaSambutan();
                        terapkanBarisLoket();
                        if (dialog[0] != null) dialog[0].dismiss();
                        showMediaTablet();
                    }).show());
            baris.addView(hapus);
            isi.addView(baris);
        }
        dialog[0] = pembuatDialog()
                .setTitle("Media di tablet")
                .setView(gulungan(isi))
                .setPositiveButton("Tambah berkas", (d, w) -> pilihMediaTablet())
                .setNegativeButton("Tutup", null)
                .show();
        rapikanTombolDialog(dialog[0]);
    }

    private void pilihMediaTablet() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[] {"image/*", "video/*"});
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        try {
            startActivityForResult(intent, PILIH_MEDIA_TABLET);
        } catch (Exception e) {
            Toast.makeText(this, "Pemilih berkas tidak tersedia di tablet ini. "
                    + "Salin berkas lewat kabel USB.", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PILIH_MEDIA_TABLET || resultCode != RESULT_OK || data == null) return;
        List<Uri> pilihan = new ArrayList<>();
        if (data.getClipData() != null) {
            for (int i = 0; i < data.getClipData().getItemCount(); i++) {
                pilihan.add(data.getClipData().getItemAt(i).getUri());
            }
        } else if (data.getData() != null) {
            pilihan.add(data.getData());
        }
        if (pilihan.isEmpty()) return;
        Toast.makeText(this, "Menyalin " + pilihan.size() + " berkas…", Toast.LENGTH_SHORT).show();
        File folder = folderMediaTablet();
        pengunduh.execute(() -> {
            int berhasil = 0;
            List<String> ditolak = new ArrayList<>();
            for (Uri uri : pilihan) {
                String nama = namaDariUri(uri);
                if (nama == null || !berakhiran(nama, EKSTENSI_MEDIA)) {
                    ditolak.add(nama == null ? uri.getLastPathSegment() : nama);
                    continue;
                }
                File tujuan = new File(folder, namaAman(nama));
                File sementara = new File(folder, "." + tujuan.getName() + ".part");
                try (InputStream input = getContentResolver().openInputStream(uri);
                     OutputStream output = new FileOutputStream(sementara)) {
                    if (input == null) throw new IllegalStateException("Berkas tidak terbaca.");
                    byte[] buffer = new byte[64 * 1024];
                    int length;
                    while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
                } catch (Exception e) {
                    //noinspection ResultOfMethodCallIgnored
                    sementara.delete();
                    ditolak.add(nama);
                    continue;
                }
                //noinspection ResultOfMethodCallIgnored
                tujuan.delete();  // berkas bernama sama diganti
                if (sementara.renameTo(tujuan)) {
                    berhasil++;
                } else {
                    //noinspection ResultOfMethodCallIgnored
                    sementara.delete();
                    ditolak.add(nama);
                }
            }
            int jumlah = berhasil;
            runOnUiThread(() -> {
                String pesan = jumlah + " berkas ditambahkan ke folder tablet."
                        + (ditolak.isEmpty() ? ""
                        : " Gagal atau bukan gambar/video: " + TextUtils.join(", ", ditolak));
                Toast.makeText(this, pesan, Toast.LENGTH_LONG).show();
                terapkanMediaSambutan();
                terapkanBarisLoket();
                showMediaTablet();
            });
        });
    }

    private String namaDariUri(Uri uri) {
        try (Cursor cursor = getContentResolver().query(
                uri, new String[] {OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                String nama = cursor.getString(0);
                if (nama != null && !nama.trim().isEmpty()) return nama.trim();
            }
        } catch (Exception ignored) {
            // Jatuh ke segmen terakhir URI.
        }
        String segmen = uri.getLastPathSegment();
        if (segmen == null) return null;
        int garis = segmen.lastIndexOf('/');
        return garis >= 0 ? segmen.substring(garis + 1) : segmen;
    }

    private void confirmRestartApi(Button restartButton) {
        pembuatDialog()
                .setTitle("Restart API server?")
                .setMessage("Anjungan akan terputus beberapa detik. Permintaan ini "
                        + "hanya berlaku untuk tablet yang sudah terhubung ke server.")
                .setNegativeButton("Batal", null)
                .setPositiveButton("Restart API", (dialog, which) -> {
                    restartButton.setEnabled(false);
                    restartButton.setText("Memulai ulang API…");
                    request("POST", "/v1/kiosk/restart-api", null, json -> {
                        Toast.makeText(this, "API sedang dimulai ulang.", Toast.LENGTH_LONG).show();
                        handler.postDelayed(() -> {
                            restartButton.setEnabled(true);
                            restartButton.setText("Restart API server");
                            loadCategories();
                            loadDisplay();
                        }, 5500);
                    }, error -> {
                        restartButton.setEnabled(true);
                        restartButton.setText("Restart API server");
                        Toast.makeText(this, "Restart API gagal: " + error,
                                Toast.LENGTH_LONG).show();
                    });
                }).show();
    }

    private void discoverServer(Consumer<String> found, Consumer<String> failed) {
        worker.execute(() -> {
            try (DatagramSocket socket = new DatagramSocket()) {
                socket.setBroadcast(true);
                socket.setSoTimeout(900);
                byte[] request = DISCOVERY_REQUEST.getBytes(StandardCharsets.UTF_8);
                DatagramPacket broadcast = new DatagramPacket(
                        request, request.length,
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
                    JSONObject data = new JSONObject(new String(
                            response.getData(), response.getOffset(),
                            response.getLength(), StandardCharsets.UTF_8));
                    if (!DISCOVERY_RESPONSE.equals(data.optString("service"))) continue;
                    int port = data.optInt("api_port", 8765);
                    if (port < 1 || port > 65535) continue;
                    String address = "http://" + response.getAddress().getHostAddress()
                            + ":" + port;
                    handler.post(() -> found.accept(address));
                    return;
                }
                handler.post(() -> failed.accept(
                        "Pastikan server berjalan dan perangkat berada di Wi-Fi/LAN yang sama."));
            } catch (Exception e) {
                String message = e.getMessage() == null
                        ? "Pencarian jaringan gagal." : e.getMessage();
                handler.post(() -> failed.accept(message));
            }
        });
    }

    private void confirmTestTicket() {
        AlertDialog dialog = pembuatDialog()
                .setTitle("Mode uji — bukan antrean resmi")
                .setMessage("Aplikasi akan menampilkan dan mencetak tiket contoh UJI-000 "
                        + "dengan tampilan tiket dari server. Nomor ini tidak disimpan dan "
                        + "tidak mengubah urutan nomor resmi.")
                .setNegativeButton("Batal", null)
                .setPositiveButton("Tampilkan & cetak", (clickedDialog, which) -> {
                    showResult("UJI-000", "CONTOH PELAYANAN");
                    setHint("Tiket uji dicetak tanpa mengubah antrean resmi.", "konfirmasi");
                    Consumer<String> selesai = message -> {
                        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
                        if (showingResult) {
                            setHint(message, message.contains("berhasil") ? "hasil" : "gagal");
                        }
                    };
                    if (!hasServerConfig()) {
                        UsbEscPosPrinter.printTest(this, selesai);
                        return;
                    }
                    // Server lama atau mati: tetap uji printer dengan tiket teks.
                    request("GET", "/v1/kiosk/ticket-sample", null,
                            json -> UsbEscPosPrinter.printTest(
                                    this, json.getJSONObject("data"), selesai),
                            error -> UsbEscPosPrinter.printTest(this, selesai));
                })
                .create();
        dialog.setOnShowListener(ignored -> rapikanTombolDialog(dialog));
        dialog.show();
    }

    private Button smallButton(String value) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextColor(UTAMA);
        button.setAllCaps(false);
        button.setTypeface(huruf(700));
        button.setBackground(stateOutline(KARTU, LEMBUT, dp(20)));
        button.setStateListAnimator(null);
        button.setGravity(Gravity.CENTER);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        button.setPadding(dp(12), dp(6), dp(12), dp(6));
        tulisanTombolUtuh(button, 15);
        return button;
    }

    private Button actionButton(String label, boolean primary) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextColor(primary ? TEKS_TOMBOL : INK);
        button.setAllCaps(false);
        button.setTypeface(huruf(800));
        button.setStateListAnimator(null);
        button.setGravity(Gravity.CENTER);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        button.setPadding(dp(12), dp(4), dp(12), dp(4));
        pasangSatuBaris(button, 9, primary ? 18 : 16);
        button.setBackground(primary
                ? stateBackground(UTAMA, darker(UTAMA), dp(29))
                : stateOutline(KARTU, LEMBUT, dp(29)));
        return button;
    }

    private void rapikanTombolDialog(AlertDialog dialog) {
        int[] tombol = {
                AlertDialog.BUTTON_POSITIVE,
                AlertDialog.BUTTON_NEGATIVE,
                AlertDialog.BUTTON_NEUTRAL,
        };
        for (int id : tombol) {
            Button button = dialog.getButton(id);
            if (button == null) continue;
            button.setAllCaps(false);
            button.setTypeface(huruf(700));
            button.setTextColor(id == AlertDialog.BUTTON_POSITIVE ? UTAMA : MUTED);
            button.setGravity(Gravity.CENTER);
            button.setPadding(dp(8), dp(4), dp(8), dp(4));
            tulisanTombolUtuh(button, 14);
        }
    }

    /**
     * Label tombol yang lebarnya mengikuti isi: satu baris, ukuran tetap,
     * tanpa "…". Tombolnya yang melebar, bukan tulisannya yang dipotong.
     */
    private void tulisanTombolUtuh(TextView view, int ukuranSp) {
        view.setSingleLine(true);
        view.setEllipsize(null);
        view.setIncludeFontPadding(false);
        view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, ukuranSp * uiScale);
    }

    /**
     * Label satu baris di kotak berukuran tetap: huruf mengecil sampai
     * seluruh tulisan muat, tidak pernah pecah dua baris atau terpotong "…".
     */
    private void pasangSatuBaris(TextView view, int minimumSp, int maksimumSp) {
        pasangAutoFit(view, minimumSp, maksimumSp, 1);
        view.setEllipsize(null);
    }

    /**
     * Sesuaikan ukuran tulisan terhadap kotak tombol/kartu yang sebenarnya.
     * Autosize bawaan tersedia mulai Android 8. Tablet Android 7 tetap
     * didukung dengan fallback yang mengecilkan teks satu tingkat demi satu
     * tingkat hanya bila tulisan lebih tinggi dari ruang yang tersedia.
     */
    private void pasangAutoFit(TextView view, int minimumSp, int maksimumSp, int maksimumBaris) {
        view.setMaxLines(maksimumBaris);
        view.setEllipsize(TextUtils.TruncateAt.END);
        view.setIncludeFontPadding(false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            int minimum = Math.max(1, Math.round(minimumSp * uiScale));
            int maksimum = Math.max(minimum, Math.round(maksimumSp * uiScale));
            view.setAutoSizeTextTypeUniformWithConfiguration(
                    minimum, maksimum, 1, android.util.TypedValue.COMPLEX_UNIT_SP);
            return;
        }

        view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, maksimumSp * uiScale);
        view.addOnLayoutChangeListener((changed, left, top, right, bottom,
                                        oldLeft, oldTop, oldRight, oldBottom) ->
                kecilkanTeksBilaPerlu(view, minimumSp, maksimumBaris));
        view.post(() -> kecilkanTeksBilaPerlu(view, minimumSp, maksimumBaris));
    }

    private void kecilkanTeksBilaPerlu(TextView view, int minimumSp, int maksimumBaris) {
        if (view.getWidth() <= 0 || view.getHeight() <= 0 || view.getLayout() == null) return;
        android.text.Layout layout = view.getLayout();
        int tinggiTersedia = view.getHeight() - view.getPaddingTop() - view.getPaddingBottom();
        boolean terpotong = false;
        for (int baris = 0; baris < layout.getLineCount(); baris++) {
            if (layout.getEllipsisCount(baris) > 0) {
                terpotong = true;
                break;
            }
        }
        int lebarTersedia = view.getWidth() - view.getPaddingLeft() - view.getPaddingRight();
        boolean terlaluLebar = maksimumBaris == 1
                && view.getPaint().measureText(view.getText().toString()) > lebarTersedia;
        boolean tidakMuat = layout.getLineCount() > maksimumBaris
                || layout.getHeight() > tinggiTersedia || terpotong || terlaluLebar;
        if (!tidakMuat) return;

        float kepadatanFont = getResources().getDisplayMetrics().scaledDensity;
        float minimumPx = minimumSp * uiScale * kepadatanFont;
        float ukuranBerikutnya = Math.max(minimumPx, view.getTextSize() - kepadatanFont);
        if (ukuranBerikutnya >= view.getTextSize()) return;
        view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX, ukuranBerikutnya);
        view.requestLayout();
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size * uiScale);
        view.setTextColor(color);
        view.setTypeface(huruf(bold ? 700 : 400));
        return view;
    }

    /**
     * Satu-satunya tempat memilih huruf. Bila huruf merek (mis. Plus Jakarta
     * Sans) dibundel di assets, cukup ganti isi fungsi ini.
     */
    private static Typeface huruf(int tebal) {
        if (tebal >= 800) return Typeface.create("sans-serif-black", Typeface.NORMAL);
        if (tebal >= 700) return Typeface.create("sans-serif", Typeface.BOLD);
        if (tebal >= 500) return Typeface.create("sans-serif-medium", Typeface.NORMAL);
        return Typeface.create("sans-serif", Typeface.NORMAL);
    }

    private int dp(int value) {
        return Math.round(value * uiScale * getResources().getDisplayMetrics().density);
    }

    private static GradientDrawable rounded(int color, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(radius);
        return shape;
    }

    private static GradientDrawable roundedOutline(
            int color, int stroke, int radius, int strokeWidth) {
        GradientDrawable shape = rounded(color, radius);
        shape.setStroke(strokeWidth, stroke);
        return shape;
    }

    private static GradientDrawable roundedGradient(
            int top, int bottom, int radius, int border, int borderWidth) {
        GradientDrawable shape = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM, new int[]{top, bottom});
        shape.setCornerRadius(radius);
        shape.setStroke(borderWidth, border);
        return shape;
    }

    private StateListDrawable stateOutline(int normal, int pressed, int radius) {
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_pressed},
                roundedOutline(pressed, UTAMA, radius, dp(2)));
        states.addState(new int[]{}, roundedOutline(normal, GARIS, radius, dp(2)));
        return states;
    }

    private static StateListDrawable stateBackground(
            int normal, int pressed, int radius) {
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_pressed},
                rounded(pressed, radius));
        states.addState(new int[]{}, rounded(normal, radius));
        return states;
    }

    private static int darker(int color) {
        return Color.rgb(
                Math.max(0, (int) (Color.red(color) * 0.82)),
                Math.max(0, (int) (Color.green(color) * 0.82)),
                Math.max(0, (int) (Color.blue(color) * 0.82)));
    }

    private static final class JSONObjectBuilder {
        private final org.json.JSONObject json = new org.json.JSONObject();

        JSONObjectBuilder put(String key, Object value) {
            try {
                json.put(key, value);
                return this;
            } catch (org.json.JSONException e) {
                throw new IllegalStateException(e);
            }
        }

        org.json.JSONObject build() {
            return json;
        }
    }

    @Override
    protected void onDestroy() {
        try {
            unregisterReceiver(installReceiver);
        } catch (IllegalArgumentException ignored) {
            // Belum terdaftar.
        }
        handler.removeCallbacksAndMessages(null);
        worker.shutdownNow();
        pengunduh.shutdownNow();
        super.onDestroy();
    }
}
