package id.sistemantrian.kiosk;

import static id.sistemantrian.kiosk.BantuGambar.huruf;
import static id.sistemantrian.kiosk.BantuGambar.rounded;
import static id.sistemantrian.kiosk.BantuGambar.roundedGradient;
import static id.sistemantrian.kiosk.BantuGambar.roundedOutline;
import static id.sistemantrian.kiosk.BantuGambar.stateBackground;
import static id.sistemantrian.kiosk.BantuTeks.awalanLayanan;
import static id.sistemantrian.kiosk.BantuTeks.heks;
import static id.sistemantrian.kiosk.BantuTeks.isMediaKind;
import static id.sistemantrian.kiosk.BantuTeks.labelTempatLokal;
import static id.sistemantrian.kiosk.BantuTeks.tempatBerikutnya;
import static id.sistemantrian.kiosk.BantuTeks.zoneLabel;
import static id.sistemantrian.kiosk.BantuWarna.campur;
import static id.sistemantrian.kiosk.BantuWarna.darker;
import static id.sistemantrian.kiosk.BantuWarna.luminansWarna;

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
import android.graphics.Paint;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.ToneGenerator;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.text.InputType;
import android.text.TextUtils;
import android.transition.AutoTransition;
import android.transition.TransitionManager;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.GridLayout;
import android.widget.ImageView;
import android.view.TextureView;
import android.view.Surface;
import android.graphics.SurfaceTexture;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

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
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
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
    /** Warna kilau petunjuk ajakan di tablet ini; "mati" mematikannya. */
    private static final String WARNA_KILAU = "warna_kilau";
    /** Warna latar iklan penuh `#RRGGBB`, disimpan per tablet. */
    private static final String LATAR_IKLAN_KUNCI = "latar_iklan_penuh";
    private static final String SKALA_VIDEO = "skala_video";
    private static final String VIDEO_PAS = "pas";
    private static final String VIDEO_ISI = "isi";
    private static final String[][] PILIHAN_SKALA_VIDEO = {
            {VIDEO_PAS, "Pas — video utuh, mungkin ada ruang di sisi"},
            {VIDEO_ISI, "Isi — memenuhi bingkai, tepi video dapat terpotong"},
    };
    private static final String[][] PILIHAN_LATAR_IKLAN = {{"Navy", "#0F172A"},
            {"Hitam", "#000000"}, {"Hijau tua", "#064E3B"},
            {"Merah marun", "#4C0519"}, {"Ungu tua", "#3B0764"}};
    private static final String KILAU_TEMA = "tema";
    /** Kecerahan terendah warna kilau bebas; yang lebih gelap tak terlihat di latar. */
    static final float NILAI_MINIMUM_KILAU = 0.5f;
    private static final String[][] PILIHAN_KILAU = {
            {KILAU_TEMA, "Ikut tema"},
            {"putih", "Putih"},
            {"emas", "Emas"},
            {"biru", "Biru"},
            {"hijau", "Hijau"},
            {"merah", "Merah muda"},
            {"ungu", "Ungu"},
            {"mati", "Tanpa kilau"},
    };
    private static final String IKUTI_SERVER_TEMA = "server";
    private static final String[][] PILIHAN_TEMA = {
            {IKUTI_SERVER_TEMA, "Ikuti pengaturan server"},
            {"biru", "Biru instansi"},
            {"hijau", "Hijau segar"},
            {"kontras", "Kontras tinggi"},
            {"gelap", "Gelap elegan"},
            {"merah_putih", "Merah putih (perayaan)"},
    };
    /** Latar kertas per tablet: polos (bawaan), ikut tema, atau selalu kertas. */
    private static final String LATAR_KERTAS = "latar_kertas";
    private static final String KERTAS_POLOS = "polos";
    private static final String KERTAS_IKUT_TEMA = "tema";
    private static final String KERTAS_SELALU = "kertas";
    private static final String[][] PILIHAN_LATAR = {
            {KERTAS_POLOS, "Polos"},
            {KERTAS_IKUT_TEMA, "Ikut tema (kertas di tema terang)"},
            {KERTAS_SELALU, "Kertas"},
    };
    private boolean kertasTerbangun;
    private Bitmap butiranKertas;
    private Tema temaWarna;
    private String temaAktif = "";
    private String temaServer = "biru";
    private String judulServer = "";
    private String subjudulServer = "";
    /** Judul khusus tablet ini; kosong berarti ikut judul dari server. */
    private static final String JUDUL_TABLET = "judul";
    private TextView subtitleLabel;

    /** Satu set warna tampilan anjungan. */
    
    private static int rgb(int r, int g, int b) {
        return Color.rgb(r, g, b);
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

    /**
     * Identitas tetap aplikasi. Tidak dapat diubah dari server maupun dari
     * pengaturan tablet; ubah hanya di sini (dan di app/core/identitas.py).
     */
    static final String NAMA_TAMPIL = "Bapenda DKI Jakarta";

    private String judulBerlaku() {
        return NAMA_TAMPIL;
    }

    private void perbaruiJudul() {
        if (displayTitle != null && !displayTitle.getText().toString().equals(judulBerlaku())) {
            displayTitle.setText(judulBerlaku());
        }
        if (subtitleLabel != null) {
            if (!subtitleLabel.getText().toString().equals(subjudulServer)) {
                subtitleLabel.setText(subjudulServer);
            }
            subtitleLabel.setVisibility(subjudulServer.isEmpty() ? View.GONE : View.VISIBLE);
        }
        sembunyikanUntukIklanPenuh();
    }

    /**
     * Apakah latar kertas dipakai. "Ikut tema" hanya di tema terang: tema
     * gelap dan kontras tinggi tetap polos agar keterbacaannya terjaga.
     */
    private boolean kertasAktif(Tema t, String namaTema) {
        String pilihan = preferences == null ? KERTAS_POLOS
                : preferences.getString(LATAR_KERTAS, KERTAS_POLOS);
        if (KERTAS_SELALU.equals(pilihan)) return true;
        return KERTAS_IKUT_TEMA.equals(pilihan) && !t.gelap && !"kontras".equals(namaTema);
    }

    /** Warna latar tema dihangatkan ke krem, lalu diberi butiran halus yang diulang. */
    private android.graphics.drawable.Drawable latarKertas(int dasar) {
        int krem = Color.rgb(244, 239, 230);
        int warna = Color.rgb(
                (Color.red(dasar) * 3 + Color.red(krem) * 7) / 10,
                (Color.green(dasar) * 3 + Color.green(krem) * 7) / 10,
                (Color.blue(dasar) * 3 + Color.blue(krem) * 7) / 10);
        if (butiranKertas == null) {
            int sisi = 128;
            int[] titik = new int[sisi * sisi];
            java.util.Random acak = new java.util.Random(7);
            for (int i = 0; i < titik.length; i++) {
                int r = acak.nextInt(100);
                // Bintik gelap atau terang berkepekatan rendah (maks. ~5%).
                if (r < 22) titik[i] = Color.argb(6 + acak.nextInt(7), 90, 70, 40);
                else if (r < 34) titik[i] = Color.argb(6 + acak.nextInt(7), 255, 255, 255);
            }
            butiranKertas = Bitmap.createBitmap(titik, sisi, sisi, Bitmap.Config.ARGB_8888);
        }
        android.graphics.drawable.BitmapDrawable ubin =
                new android.graphics.drawable.BitmapDrawable(getResources(), butiranKertas);
        ubin.setTileModeXY(android.graphics.Shader.TileMode.REPEAT,
                android.graphics.Shader.TileMode.REPEAT);
        return new android.graphics.drawable.LayerDrawable(new android.graphics.drawable.Drawable[]{
                new android.graphics.drawable.ColorDrawable(warna), ubin});
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
        String baru = temaBerlaku();
        if (baru.equals(temaAktif) && kertasAktif(Tema.dari(baru), baru) == kertasTerbangun) return;
        if (showingConfirmation || showingResult || requestInFlight
                || updating || updateRequired) return;
        bangunUlangTampilan();
    }

    private void bangunUlangTampilan() {
        lepasDaftarMenunggu();
        // Potret layar lama (setengah resolusi, hemat memori) ditumpuk di atas
        // layar baru lalu dipudarkan: tema berganti tanpa berkedip.
        Bitmap potret = null;
        View lama = rootLayout;
        if (lama != null && lama.getWidth() > 0 && lama.getHeight() > 0) {
            try {
                potret = Bitmap.createBitmap(Math.max(1, lama.getWidth() / 2),
                        Math.max(1, lama.getHeight() / 2), Bitmap.Config.RGB_565);
                android.graphics.Canvas kanvas = new android.graphics.Canvas(potret);
                kanvas.scale(0.5f, 0.5f);
                lama.draw(kanvas);
            } catch (RuntimeException | OutOfMemoryError e) {
                potret = null;  // tanpa peralihan pun tetap benar
            }
        }
        int lebarLama = lama == null ? 0 : lama.getWidth();
        int tinggiLama = lama == null ? 0 : lama.getHeight();
        hentikanKilauAjakan();
        buildHome();
        if (potret != null) {
            android.graphics.drawable.BitmapDrawable tumpukan =
                    new android.graphics.drawable.BitmapDrawable(getResources(), potret);
            tumpukan.setBounds(0, 0, lebarLama, tinggiLama);
            View baru = rootLayout;
            baru.getOverlay().add(tumpukan);
            android.animation.ValueAnimator pudar =
                    android.animation.ValueAnimator.ofInt(255, 0);
            pudar.setDuration(400);
            pudar.addUpdateListener(a -> tumpukan.setAlpha((int) a.getAnimatedValue()));
            Bitmap dilepas = potret;
            pudar.addListener(new android.animation.AnimatorListenerAdapter() {
                @Override
                public void onAnimationEnd(android.animation.Animator animasi) {
                    baru.getOverlay().remove(tumpukan);
                    dilepas.recycle();
                }
            });
            pudar.start();
        }
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
        // Setiap dialog yang tampil lewat sini ikut timer diam bersama
        // (lihat pasangAutoTutup), jadi tidak ada yang tertinggal terbuka.
        return new AlertDialog.Builder(this, temaWarna != null && temaWarna.gelap
                ? android.R.style.Theme_Material_Dialog_Alert
                : android.R.style.Theme_Material_Light_Dialog_Alert) {
            @Override
            public AlertDialog show() {
                AlertDialog dialog = create();
                dialog.show();
                pasangAutoTutup(dialog);
                return dialog;
            }
        };
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
    /**
     * Antrean khusus penerbitan tiket. `worker` juga melayani pembaruan
     * layar tiap 5 detik, daftar layanan, dan laporan; satu permintaan yang
     * menggantung di sana tidak boleh membuat pengunjung ikut menunggu.
     */
    private final ExecutorService penerbit = Executors.newSingleThreadExecutor();
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
    /** Server menampilkan kotak prioritas (setelan priority_enabled). */
    private boolean prioritasAktifServer = false;
    /** Pengunjung mencentang "Saya lansia / disabilitas / ibu hamil". */
    private boolean prioritasDipilih = false;
    private boolean requestInFlight;
    private boolean showingConfirmation;
    private boolean showingResult;
    private boolean categoriesLoaded;
    /** categories_version server saat daftar layanan terakhir dimuat. */
    private String versiLayanan = "";
    /**
     * Pesan yang bertahan beberapa detik. Tanpa ini petunjuk biasa menimpanya
     * pada detik berikutnya (updateAvailability berjalan tiap detik), sehingga
     * "Pilihan dibatalkan..." atau penolakan server nyaris tidak terbaca.
     */
    private String pesanSementara = "";
    private String nadaSementara = "ajak";
    private long pesanSementaraSampai;
    private static final long LAMA_PESAN_SEMENTARA_MS = 6000L;
    private String mediaSignature = "";
    private List<String> welcomeMedia = new ArrayList<>();
    private int welcomeSlideSeconds = 10;
    private int mediaIndex;
    private String welcomeFallbackText = "";
    private String displayedWelcomeText = "";
    private final List<String> waitingQueueNumbers = new ArrayList<>();
    /** Nomor menunggu yang diberi bintang prioritas (tanpa alasan). */
    private final java.util.Set<String> nomorPrioritasMenunggu = new java.util.HashSet<>();
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
    private boolean menungguUkuranPanel;
    /** Nomor terakhir tiap loket, untuk menyorot loket yang baru memanggil. */
    private final Map<String, String> nomorLoketTerakhir = new HashMap<>();
    private boolean nomorLoketPernahTampil;
    /** Nomor menunggu dan halaman yang terakhir tampil, untuk animasi perubahan. */
    private final Set<String> nomorMenungguTerakhir = new HashSet<>();
    private int halamanMenungguTerakhir = -1;
    private boolean menungguPernahTampil;
    /** Ubin nomor yang sedang tampil, untuk animasi keluar dan geser. */
    private final Map<String, View> ubinTampil = new HashMap<>();
    private final Map<String, int[]> posisiUbinLama = new HashMap<>();
    private boolean sedangMengeluarkan;
    /** Tanda isi daftar terakhir; sama berarti tidak perlu digambar ulang. */
    private String tandaMenunggu = "";
    private long halamanMulaiMillis;
    private static final long LAMA_HALAMAN_MENUNGGU_MS = 4500L;
    /** Nomor yang baru diambil di tablet ini, disorot sebentar di daftar. */
    private String nomorSaya = "";
    private long batasSorotMillis;
    private boolean sorotDidenyutkan;
    private boolean sorotDitunjukkan;
    /** Panel bawah sedang memakai latar gelap layar "Nomor Anda". */
    private boolean panelHasilGelap;
    private LinearLayout panelHasil;
    private long batasKonfirmasiMillis;
    /** Pengaturan server: video anjungan bersuara atau tidak. */
    private boolean suaraVideo;
    private android.media.MediaPlayer pemutarVideo;

    // Suara panggilan. Anjungan yang dipilih admin di Layanan Anjungan
    // merangkap pengeras suara selama layar antrian belum terpasang.
    private static final String VERSI_PAKET_SUARA = "sound_pack_version";
    private static final String TOKEN_JEDA = "_jeda";
    private static final long SELANG_PANGGILAN_MS = 2000L;
    private static final long SELANG_CETAK_ULANG_MS = 3000L;
    private static final long COBA_PAKET_LAGI_MS = 120_000L;
    /**
     * Panggilan yang lebih tua dari ini tidak diucapkan lagi: tablet yang
     * sempat putus lalu tersambung tidak mengumumkan nomor yang mungkin
     * sudah dilayani. Umurnya menurut jam server (age_seconds).
     */
    private static final double BATAS_UMUR_PANGGILAN_DETIK = 60;
    /** Jaring pengaman saja; yang basi sudah dibuang menurut umurnya. */
    private static final int MAKS_ANTREAN_UCAPAN = 10;
    /** Volume video iklan selama pengumuman, supaya kalimatnya jelas. */
    private static final float VOLUME_VIDEO_SAAT_PANGGILAN = 0.15f;
    /** Thread sendiri: penerbitan nomor tidak boleh menunggu di belakang polling. */
    private final ExecutorService pemanggil = Executors.newSingleThreadExecutor();
    private boolean suaraPanggilan;
    private Long panggilanTerakhir;
    private boolean panggilanDiminta;
    private final ArrayDeque<JSONObject> antreanUcapan = new ArrayDeque<>();
    private final Map<String, String> klipPaket = new HashMap<>();
    private boolean sedangMengumumkan;
    private TextToSpeech tts;
    private boolean ttsDiperiksa;
    private boolean ttsSiap;
    private ToneGenerator nada;
    private MediaPlayer pemutarKlip;
    private boolean paketDiunduh;
    private long paketCobaLagiPada;
    private String versiPaketServer = "";
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
    /** Gambar mini dan durasi di dialog Media di tablet; dibuat di latar belakang. */
    private final ExecutorService pembuatThumbnail = Executors.newSingleThreadExecutor();
    private final android.util.LruCache<String, Bitmap> cacheThumbnail =
            new android.util.LruCache<>(48);
    private final Map<String, Long> cacheDurasi = new java.util.concurrent.ConcurrentHashMap<>();
    private String serverKind = "teks";
    private List<String> serverMedia = new ArrayList<>();
    /**
     * Di mana tiap berkas daftar putar server tampil: "panel" (strip atas),
     * "penuh" (iklan layar penuh saat menganggur), atau "keduanya".
     * Server lama tidak menyebutnya: semuanya keduanya.
     */
    private final Map<String, String> tampilBerkas = new HashMap<>();
    /** Daftar yang diputar sekarang: true = daftar layar penuh. */
    private boolean mediaModePenuh;

    // --- PIN pengaturan, mode putar saja, dan tempat tampil lokal -----------
    private static final String PIN_AKTIF = "pin_aktif";
    private static final String PIN_SALT = "pin_salt";
    private static final String PIN_HASH = "pin_hash";
    private static final String PIN_ITER = "pin_iter";
    private static final String PIN_GAGAL = "pin_gagal";
    private static final String PIN_TUNDA_SAMPAI = "pin_tunda_sampai";
    private static final String PERNAH_TERHUBUNG = "pernah_terhubung";
    private static final String DISPLAY_TERAKHIR = "display_terakhir";
    private static final String TAMPIL_LOKAL = "tampil_lokal";
    /** Gagal terhubung selama ini membuat tablet masuk mode putar saja. */
    private static final long BATAS_PUTAR_SAJA_MS = 30_000L;
    /** Seluruh dialog pengaturan menutup sendiri bila tidak disentuh selama ini. */
    private static final long BATAS_DIAM_PENGATURAN_MS = 60_000L;
    /** Peringatan "akan menutup" pada sekian milidetik terakhir. */
    private static final long PERINGATAN_DIAM_PENGATURAN_MS = 10_000L;
    /** Sentuh-tahan di pojok kiri bawah selama ini membuka jalan pulih. */
    private static final long TAHAN_PULIH_MS = 5_000L;
    /** Waktu gagal terhubung yang pertama; 0 = tersambung. */
    private long gagalSejak;
    /** Server tidak terjangkau: hanya memutar video, tanpa fitur lain. */
    private boolean putarSaja;
    private String mediaTerakhirTersimpan = "";
    /** Nama berkas server -> nama salinannya (ukuran-waktu-nama). */
    private final Map<String, String> kunciSalinan = new HashMap<>();
    /** Kunci salinan yang sedang diunduh; hanya disentuh di thread UI. */
    private final Set<String> sedangDiunduh = new HashSet<>();
    private final Map<String, Long> unduhGagalPada = new HashMap<>();
    /** Penanda permintaan "segarkan media" terakhir yang sudah ditangani. */
    private static final String MEDIA_SEGARKAN_DITANGANI = "media_segarkan_ditangani";
    /** Status salinan media terakhir yang dilaporkan: {total, tersalin}. */
    private int[] statusMediaTerakhir;
    private int bateraiTerakhirPersen = -1;
    private boolean bateraiTerakhirMengisi;
    private long bateraiTerakhirWaktu;
    private long statusMediaWaktu;
    /** Video yang sedang diputar langsung dari server, belum dari salinan. */
    private String videoLewatJaringan;
    /** Lama tampil khusus tiap gambar dari server (detik). */
    private final Map<String, Integer> detikPerBerkas = new HashMap<>();

    // Iklan dan pengunjung. Selama pengunjung bertransaksi (memilih layanan
    // sampai tiketnya keluar, atau baru saja menyentuh layar) video dibisukan
    // dan panel iklan diredupkan, supaya perhatiannya tidak terbagi. Setelah
    // tablet lama tidak disentuh, iklan diperbesar memenuhi layar.
    private static final long JEDA_TRANSAKSI_MS = 15_000L;
    /**
     * Sub-menu layanan yang ditinggal pengunjung kembali ke menu awal. Tanpa
     * ini pengunjung berikutnya mendapati pilihan orang lain, dan tablet
     * tidak pernah dianggap menganggur.
     */
    private static final long KEMBALI_KE_MENU_AWAL_MS = 20_000L;
    private long sentuhTerakhirMillis = System.currentTimeMillis();
    private boolean sedangBertransaksi;
    private float targetTirai = 0f;
    /** Pengaturan server: detik tanpa sentuhan sebelum iklan layar penuh; 0 = mati. */
    private int iklanPenuhDetik = 60;
    /** Putaran iklan layar penuh sebelum kembali ke antrian; 0 = terus. */
    private int iklanPutaran = 2;
    private int putaranIklanSelesai;
    /** Server menyalakan animasi tiga panel saat kembali ke antrian. */
    private boolean animasiKembali = true;
    /** Tiga panel keluar sebelum iklan layar penuh (server: ad_entry_animation). */
    private boolean animasiIklanMuncul = true;
    private boolean sedangKeluarPanel;
    /** Panel baru saja keluar; masukIklanPenuh tidak memakai transisi dan memulihkan posisi. */
    private boolean panelSudahKeluar;
    private static final long ANIMASI_KELUAR_MS = 1500L;
    private static final long JEDA_PANEL_KELUAR_MS = 150L;
    private final Runnable masukSetelahPanelKeluar = () -> {
        if (!sedangKeluarPanel) return;
        sedangKeluarPanel = false;
        panelSudahKeluar = true;
        masukIklanPenuh();
    };
    /** Panggilan petugas mengalahkan iklan (server: call_interrupts_ad). */
    private boolean panggilanHentikanIklan = true;
    /** Penanda panggilan terakhir tiap loket: nomor#jumlah panggilan; null = belum dimuat. */
    private Map<String, String> penandaPanggilanLoket;
    private android.widget.PopupWindow bannerPanggilan;
    /** Pita di atas layar selama tiket dicetak ulang atas permintaan petugas. */
    private android.widget.PopupWindow bannerCetakUlang;
    private TextView teksBannerCetakUlang;
    private android.widget.ProgressBar putarBannerCetakUlang;
    private static final long LAMA_BANNER_PANGGILAN_MS = 6_000L;
    /** Hasil cetak ulang (berhasil atau gagal) tampil sebentar sebelum pita hilang. */
    private static final long LAMA_BANNER_CETAK_ULANG_MS = 3_500L;
    private static final long DURASI_PANEL_PANGGILAN_MS = 900L;
    /** Nomor menunggu muncul berurutan, gaya acak (server: waiting_animation). */
    private boolean animasiNomorAktif = true;
    /** Bangun ulang nomor menunggu dengan animasi masuk (sesudah kembali dari iklan). */
    private boolean ulangiAnimasiNomor;
    private long jedaAwalNomorMs;
    private int gayaNomorTerakhir = -1;
    /** Paling banyak nomor yang dianimasikan; sisanya langsung tampil. */
    private static final int BATAS_NOMOR_ANIMASI = 24;
    private static final long JEDA_BARIS_NOMOR_MS = 200L;
    private static final long JEDA_KOLOM_NOMOR_MS = 70L;
    private static final long BATAS_TOTAL_JEDA_NOMOR_MS = 1500L;
    /** Animasi mulai sekian milidetik sebelum iklan terakhir berakhir; 0 = sesudahnya. */
    private long animasiMulaiMs = 2000L;
    /** Lama iklan meredup sebelum panel-panel masuk. */
    private static final long DURASI_REDUP_IKLAN_MS = 600L;
    /** Panel masuk: penuh (putaran habis) dan singkat (disentuh). */
    private static final long DURASI_PANEL_PENUH_MS = 1800L;
    private static final long JEDA_PANEL_PENUH_MS = 250L;
    private static final long DURASI_PANEL_SENTUH_MS = 900L;
    /** Kembali karena putaran habis (bukan sentuhan): animasi penuh. */
    private boolean keluarDenganAnimasiPenuh;
    private int arahAnimasiTerakhir = -1;
    private final java.util.Random acakArah = new java.util.Random();
    private boolean iklanPenuh;
    // Keadaan bingkai sebelum iklan memenuhi layar, untuk dipulihkan.
    private int[] paddingRootAsli;
    private int[] paddingInfoAsli;
    private android.graphics.drawable.Drawable latarInfoAsli;
    private float elevasiInfoAsli;
    /** Sisa gestur yang membangunkan layar iklan; tidak diteruskan ke tombol. */
    private boolean menelanSentuhan;
    private final Map<View, Integer> visibilitasSebelumIklanPenuh = new HashMap<>();
    private LinearLayout panelInfo;
    private LinearLayout panelLayanan;
    private FrameLayout bingkaiMedia;
    private View tiraiMedia;
    private TextView ajakanIklanPenuh;
    /**
     * SATU sumber warna latar iklan penuh (setelan tablet LATAR_IKLAN_KUNCI,
     * bawaan navy):
     * panel ajakan, sisi kiri/kanan video, latar gambar, rootLayout dan
     * panelInfo semuanya memakainya. Sisi video tidak ikut berdenyut.
     */
    private static final int LATAR_IKLAN_BAWAAN = Color.rgb(15, 23, 42);
    private int latarIklanPenuh = LATAR_IKLAN_BAWAAN;
    /** Putih untuk latar gelap, hitam untuk latar terang. */
    private int teksIklanPenuh = Color.WHITE;
    /** Puncak denyut panel: warna dasar digeser 12% (terang untuk gelap). */
    private int puncakDenyutIklan = Color.rgb(44, 51, 68);
    /** Luminans relatif tertinggi yang diterima untuk latar panel. */
    private static final double LUMINANS_MAKS_IKLAN = 0.6;
    private Runnable denyutAjakanIklan;
    private android.animation.ValueAnimator animatorDenyutAjakan;

    // Laporan tayang ke server: jumlah tayang dan gagal sejak laporan
    // terakhir, dikirim tiap menit. Hanya untuk media dari server; berkas di
    // folder tablet tidak dikenal server.
    private static final long SELANG_LAPORAN_TAYANG_MS = 60_000L;
    private final Map<String, int[]> hitungTayang = new HashMap<>();
    private final Map<String, String> galatTayang = new HashMap<>();
    private final Map<String, Boolean> terakhirGagal = new HashMap<>();
    private boolean laporanTayangTerkirim;

    private interface Success {
        void accept(JSONObject json) throws Exception;
    }

    private interface Failure {
        void accept(String message);
    }

    /**
     * Jawaban 4xx: server sudah memutuskan (pendaftaran ditutup, layanan
     * nonaktif, perlu pembaruan). Mengulang permintaan yang sama tidak akan
     * mengubah jawabannya, berbeda dengan jaringan putus atau galat 5xx.
     */
    private interface Ditolak {
        void accept(int kode, String detail);
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

    private final Runnable clock = new Runnable() {
        @Override
        public void run() {
            updateAvailability();
            perbaruiHitungMundurKonfirmasi();
            perbaruiIklan();
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
            // Selama iklan memenuhi layar, panggilan baru harus terlihat segera.
            handler.postDelayed(this, iklanPenuh && panggilanHentikanIklan ? 1000 : 5000);
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
            handler.postDelayed(this, LAMA_HALAMAN_MENUNGGU_MS);
        }
    };

    private final Runnable nextSlide = () -> advanceSlide();
    /**
     * Satu berkas yang tampil terus (satu video diulang pemutar, satu gambar
     * tanpa pergantian) tetap dihitung tayang tiap putaran atau tiap lama
     * tampilnya, bukan sekali seumur hidup.
     */
    private String ulangTayangBerkas;
    private long ulangTayangMs;
    private final Runnable ulangTayang = new Runnable() {
        @Override
        public void run() {
            String nama = ulangTayangBerkas;
            if (nama == null || welcomeMedia.size() != 1
                    || !nama.equals(welcomeMedia.get(0)) || mediaGagal) return;
            catatTayang(nama);
            handler.postDelayed(this, ulangTayangMs);
        }
    };

    private final Runnable kirimLaporanTayang = new Runnable() {
        @Override
        public void run() {
            kirimLaporanTayang();
            handler.postDelayed(this, SELANG_LAPORAN_TAYANG_MS);
        }
    };
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
        muatMediaTerakhir();
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
        boolean modeMemanjang = widthDp / Math.max(1f, heightDp) > 2.5f;
        temaAktif = temaBerlaku();
        terapkanPalet(Tema.dari(temaAktif));
        kertasTerbangun = kertasAktif(temaWarna, temaAktif);
        uiScale = Math.max(0.8f, Math.min(2.2f,
                Math.min(widthDp / 360f, heightDp / 640f))) * temaWarna.skala;

        LinearLayout root = new LinearLayout(this);
        rootLayout = root;
        // Panel papan ±4,4:1 kehilangan hampir seluruh tinggi bila tiga bagian
        // ditumpuk. Pada bentuk ini judul, layanan, dan hasil berdampingan;
        // tablet biasa tetap memakai susunan tegak yang mudah dijangkau.
        root.setOrientation(modeMemanjang
                ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        if (kertasTerbangun) root.setBackground(latarKertas(LATAR));
        else root.setBackgroundColor(LATAR);
        root.setPadding(dp(10), dp(8), dp(10), dp(8));

        LinearLayout infoPanel = panel();
        panelInfo = infoPanel;
        iklanPenuh = false;
        menelanSentuhan = false;
        visibilitasSebelumIklanPenuh.clear();
        hentikanDenyutAjakanIklan();
        infoPanel.setPadding(dp(18), dp(12), dp(18), dp(12));
        LinearLayout titleRow = new LinearLayout(this);
        titleRow.setGravity(Gravity.CENTER);
        displayTitle = text(judulBerlaku(), 18, INK, true);
        displayTitle.setTypeface(huruf(800));
        displayTitle.setGravity(Gravity.CENTER);
        pasangSatuBaris(displayTitle, 10, 18);
        titleRow.addView(displayTitle, new LinearLayout.LayoutParams(0, -2, 1));
        Button settings = smallButton("⚙");
        settings.setContentDescription("Pengaturan server");
        settings.setOnClickListener(v -> bukaPengaturan());
        titleRow.addView(settings, new LinearLayout.LayoutParams(dp(42), dp(38)));
        infoPanel.addView(titleRow);
        subtitleLabel = text(subjudulServer, 13, MUTED, true);
        subtitleLabel.setGravity(Gravity.CENTER);
        pasangSatuBaris(subtitleLabel, 9, 13);
        subtitleLabel.setVisibility(subjudulServer.isEmpty() ? View.GONE : View.VISIBLE);
        infoPanel.addView(subtitleLabel, new LinearLayout.LayoutParams(-1, -2));
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
        // Bingkai: media, tirai peredup di atasnya (juga menutupi video,
        // yang digambar di permukaan sendiri dan tidak dapat dipudarkan),
        // lalu ajakan menyentuh saat iklan memenuhi layar.
        bingkaiMedia = new FrameLayout(this);
        bingkaiMedia.addView(mediaSlot, new FrameLayout.LayoutParams(-1, -1));
        tiraiMedia = new View(this);
        tiraiMedia.setBackgroundColor(Color.BLACK);
        tiraiMedia.setAlpha(0f);
        targetTirai = 0f;
        sedangBertransaksi = false;
        bingkaiMedia.addView(tiraiMedia, new FrameLayout.LayoutParams(-1, -1));
        terapkanLatarIklanPenuh(preferences.getString(LATAR_IKLAN_KUNCI, ""));
        ajakanIklanPenuh = text("Sentuh layar untuk mengambil nomor antrian",
                20, Color.WHITE, true);
        ajakanIklanPenuh.setShadowLayer(dp(2), 0, dp(1), Color.argb(160, 0, 0, 0));
        ajakanIklanPenuh.setGravity(Gravity.CENTER);
        ajakanIklanPenuh.setMaxLines(1);
        ajakanIklanPenuh.setBackgroundColor(latarIklanPenuh);
        ajakanIklanPenuh.setTextColor(teksIklanPenuh);
        ajakanIklanPenuh.setVisibility(View.GONE);
        bingkaiMedia.addView(ajakanIklanPenuh, new FrameLayout.LayoutParams(-1, dp(56),
                Gravity.TOP));
        infoPanel.addView(bingkaiMedia, new LinearLayout.LayoutParams(-1, 0, 1));
        root.addView(infoPanel, parameterPanel(modeMemanjang, 1f));

        LinearLayout kioskPanel = panel();
        panelLayanan = kioskPanel;
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
        root.addView(kioskPanel, parameterPanel(modeMemanjang, 1.35f));

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
        root.addView(resultPanel, parameterPanel(modeMemanjang, 1f));

        setContentView(root);
        showCategories();
        handler.removeCallbacks(clock);
        handler.post(clock);
        handler.removeCallbacks(displayRefresh);
        handler.postDelayed(displayRefresh, 5000);
        muatPaketSuara();
        handler.post(pollingPanggilan);
        handler.postDelayed(pollingCetakUlang, SELANG_CETAK_ULANG_MS);
        handler.removeCallbacks(waitingPageRotation);
        handler.postDelayed(waitingPageRotation, LAMA_HALAMAN_MENUNGGU_MS);
        handler.removeCallbacks(kirimLaporanTayang);
        handler.postDelayed(kirimLaporanTayang, SELANG_LAPORAN_TAYANG_MS);
    }

    private LinearLayout panel() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        layout.setBackground(roundedOutline(KARTU, GARIS, dp(24), dp(1)));
        layout.setElevation(dp(kertasTerbangun ? 3 : 1));
        return layout;
    }

    private LinearLayout.LayoutParams parameterPanel(boolean memanjang, float bobot) {
        LinearLayout.LayoutParams parameter = memanjang
                ? new LinearLayout.LayoutParams(0, -1, bobot)
                : new LinearLayout.LayoutParams(-1, 0, bobot);
        int sela = dp(4);
        parameter.setMargins(sela, sela, sela, sela);
        return parameter;
    }

    private void loadCategories() {
        loadCategories(false);
    }

    /**
     * `latar`: penyegaran karena categories_version berubah. Gagal di latar
     * tidak menghapus daftar yang sedang dipakai; dicoba lagi pada
     * /display berikutnya.
     */
    private void loadCategories(boolean latar) {
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
            sesuaikanJalur();
            if (!showingConfirmation && !showingResult) showCategories();
        }, message -> {
            if (latar && categoriesLoaded) {
                versiLayanan = "";
                return;
            }
            categoriesLoaded = false;
            showServerPlaceholder("Tidak dapat memuat layanan: " + message);
        });
    }

    /**
     * Sub-menu yang sedang dibuka mengikuti daftar baru: nama kelompok yang
     * diganti ikut berganti, dan kelompok yang hilang atau berhenti menjadi
     * kelompok mengembalikan pengunjung ke tingkat di atasnya.
     */
    private void sesuaikanJalur() {
        List<Category> jalur = new ArrayList<>();
        for (Category lama : path) {
            Category baru = null;
            for (Category item : categories) {
                if (item.id == lama.id) {
                    baru = item;
                    break;
                }
            }
            if (baru == null || !baru.group) break;
            jalur.add(baru);
        }
        path.clear();
        path.addAll(jalur);
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
            gagalSejak = 0L;
            preferences.edit().putBoolean(PERNAH_TERHUBUNG, true).apply();
            simpanPinDariServer(display.optJSONObject("settings_pin"));
            simpanMediaTerakhir(display);
            lastDisplaySuccessMillis = System.currentTimeMillis();
            tampilkanStatusKoneksi("Terhubung ke server", Color.rgb(6, 95, 70),
                    Color.rgb(209, 250, 229));
            String title = display.optString("title", "").trim();
            if (!title.isEmpty()) judulServer = title;
            subjudulServer = display.optString("subtitle", "").trim();
            perbaruiJudul();
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
            detikPerBerkas.clear();
            tampilBerkas.clear();
            JSONArray infoRows = display.optJSONArray("welcome_media_files");
            if (infoRows != null) {
                for (int i = 0; i < infoRows.length(); i++) {
                    JSONObject row = infoRows.optJSONObject(i);
                    if (row == null) continue;
                    String nama = row.optString("name", "");
                    if (nama.isEmpty()) continue;
                    kunciSalinan.put(nama, row.optLong("size", 0L) + "-"
                            + row.optLong("modified_ms", 0L) + "-" + BerkasMedia.namaAman(nama));
                    tampilBerkas.put(nama, row.optString("show", "keduanya"));
                    int detik = row.isNull("seconds") ? 0 : row.optInt("seconds", 0);
                    if (detik > 0) detikPerBerkas.put(nama, detik);
                }
            }
            iklanPenuhDetik = Math.max(0, display.optInt("fullscreen_ad_idle_seconds", 60));
            iklanPutaran = Math.max(0, display.optInt("fullscreen_ad_loops", 2));
            animasiKembali = display.optBoolean("return_animation", true);
            animasiIklanMuncul = display.optBoolean("ad_entry_animation", true);
            panggilanHentikanIklan = display.optBoolean("call_interrupts_ad", true);
            animasiNomorAktif = display.optBoolean("waiting_animation", true);
            animasiMulaiMs = Math.max(0, Math.min(5,
                    display.optInt("return_animation_lead_seconds", 2))) * 1000L;
            serverKind = display.optString("welcome_kind", "teks");
            serverMedia = media;
            welcomeFallbackText = display.optString("welcome_text", "");
            welcomeSlideSeconds = Math.max(1, display.optInt("welcome_slide_seconds", 10));
            terapkanMediaSambutan();
            long mintaSegarkan = display.optLong("media_refresh", 0L);
            if (mintaSegarkan != 0L && mintaSegarkan
                    != preferences.getLong(MEDIA_SEGARKAN_DITANGANI, 0L)) {
                // Admin menekan "Segarkan media" untuk tablet ini: coba lagi
                // unduhan yang tertunda tanpa menunggu jeda, dan laporkan.
                preferences.edit().putLong(MEDIA_SEGARKAN_DITANGANI, mintaSegarkan).apply();
                unduhGagalPada.clear();
                statusMediaTerakhir = null;
            }
            laporkanBaterai();
            if (!sumberTablet()) {
                sinkronkanSalinan();
                laporkanStatusMedia();
            }
            registrationOpen = display.optBoolean("registration_open", true);
            boolean prioritasBaruAktif = display.optBoolean("priority_enabled", false);
            boolean prioritasBerubah = prioritasBaruAktif != prioritasAktifServer;
            prioritasAktifServer = prioritasBaruAktif;
            // Menu pertama digambar sebelum jawaban ini tiba; gambar ulang sekali
            // agar kotak prioritas muncul (atau hilang) tanpa menunggu pemicu lain.
            if (prioritasBerubah && categoriesLoaded && !showingConfirmation
                    && !showingResult && !updating && !updateRequired) {
                showCategories();
            }
            String versi = display.optString("categories_version", "");
            if (!versi.isEmpty() && !versi.equals(versiLayanan)) {
                // Daftar yang dimuat saat menyala sudah sesuai versi pertama.
                boolean pertama = versiLayanan.isEmpty();
                versiLayanan = versi;
                if (!pertama && categoriesLoaded) loadCategories(true);
            }
            JSONArray waitingRows = display.optJSONArray("waiting_queue_numbers");
            List<String> terbaru = new ArrayList<>();
            if (waitingRows != null) {
                for (int i = 0; i < waitingRows.length(); i++) {
                    String nomor = waitingRows.optString(i, "").trim();
                    if (!nomor.isEmpty()) terbaru.add(nomor);
                }
            }
            JSONArray prioritasRows = display.optJSONArray("waiting_priority_numbers");
            java.util.Set<String> prioritasBaru = new java.util.HashSet<>();
            if (prioritasRows != null) {
                for (int i = 0; i < prioritasRows.length(); i++) {
                    String nomor = prioritasRows.optString(i, "").trim();
                    if (!nomor.isEmpty()) prioritasBaru.add(nomor);
                }
            }
            if (!nomorPrioritasMenunggu.equals(prioritasBaru)) {
                nomorPrioritasMenunggu.clear();
                nomorPrioritasMenunggu.addAll(prioritasBaru);
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
            aturSuaraPanggilan(display.optBoolean("call_sound", false));
            versiPaketServer = display.isNull("sound_pack_version")
                    ? "" : display.optString("sound_pack_version", "");
            sinkronkanPaketSuara();
            JSONArray loketRows = display.optJSONArray("counters");
            loketList.clear();
            if (loketRows != null) {
                for (int i = 0; i < loketRows.length(); i++) {
                    JSONObject row = loketRows.optJSONObject(i);
                    if (row != null) loketList.add(new Loket(row));
                }
            }
            deteksiPanggilanBaru();
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
            if (gagalSejak == 0L) gagalSejak = System.currentTimeMillis();
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
        settings.setOnClickListener(v -> bukaPengaturan());
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
        handler.removeCallbacks(ulangTayang);
        handler.removeCallbacks(akhirIklanAwal);
        ulangTayangBerkas = null;
        pemutarVideo = null;
        videoLewatJaringan = null;
        String url = mediaUrl(filename);
        // Folder tablet: selalu berkas lokal. Server: salinan bila sudah
        // lengkap, bila belum diputar langsung lewat jaringan.
        File lokal = berkasMedia(filename);
        if (BerkasMedia.isVideo(filename)) {
            // Video digambar di permukaan tersendiri yang tidak dapat
            // dipudarkan; yang lama langsung diganti.
            mediaSlot.removeAllViews();
            VideoTekstur video = new VideoTekstur(this, () -> VIDEO_ISI.equals(
                    preferences.getString(SKALA_VIDEO, VIDEO_PAS)));
            video.setBackgroundColor(iklanPenuh ? latarIklanPenuh : Color.BLACK);
            mediaSlot.addView(video, new FrameLayout.LayoutParams(-1, -1));
            video.setOnCompletionListener(player -> advanceSlide());
            video.setOnErrorListener((player, what, extra) -> {
                mediaGagalDiputar(signature, filename,
                        "Video tidak dapat diputar (what=" + what + ", extra=" + extra + ")");
                return true;
            });
            video.setOnPreparedListener(player -> {
                pemutarVideo = player;
                aturSuaraVideo();
                // Satu video saja: diulang oleh pemutar, tanpa layar hitam.
                boolean ulang = welcomeMedia.size() == 1 && !putaranDibatasi();
                player.setLooping(ulang);
                player.start();
                mediaBerhasilDiputar(filename);
                jadwalkanAkhirIklanAwal(player.getDuration());
                if (ulang && player.getDuration() > 0) {
                    jadwalkanUlangTayang(filename, player.getDuration());
                }
            });
            if (lokal != null) {
                video.setVideoURI(Uri.fromFile(lokal));
            } else {
                videoLewatJaringan = filename;
                video.setVideoURI(Uri.parse(url), authHeaders(url));
            }
        } else {
            // Gambar baru memudar di atas tampilan lama, lalu yang lama dibuang:
            // tidak ada kilatan kosong saat gambar berikutnya dimuat.
            for (int i = 0; i < mediaSlot.getChildCount(); i++) {
                View lama = mediaSlot.getChildAt(i);
                if (lama instanceof VideoTekstur) ((VideoTekstur) lama).stopPlayback();
            }
            ImageView image = new ImageView(this);
            image.setScaleType(VIDEO_ISI.equals(
                    preferences.getString(SKALA_VIDEO, VIDEO_PAS))
                    ? ImageView.ScaleType.CENTER_CROP : ImageView.ScaleType.FIT_CENTER);
            image.setBackgroundColor(iklanPenuh ? latarIklanPenuh : KARTU);
            image.setAlpha(0f);
            mediaSlot.addView(image, new FrameLayout.LayoutParams(-1, -1));
            worker.execute(() -> {
                try {
                    byte[] bytes = lokal != null ? BerkasMedia.bacaBerkas(lokal) : downloadMedia(url);
                    Bitmap bitmap = decodeImage(bytes, mediaSlot.getWidth(), mediaSlot.getHeight());
                    if (bitmap == null) {
                        throw new IllegalStateException("Gambar sambutan tidak dapat dibaca.");
                    }
                    runOnUiThread(() -> {
                        if (!isCurrentMedia(signature, filename)) {
                            mediaSlot.removeView(image);
                            return;
                        }
                        image.setImageBitmap(bitmap);
                        image.animate().alpha(1f).setDuration(500)
                                .withEndAction(() -> buangSelain(image)).start();
                        mediaBerhasilDiputar(filename);
                        jadwalkanAkhirIklanAwal(detikTampil(filename) * 1000L);
                        // Satu gambar saja tampil terus, tidak diunduh ulang.
                        if (welcomeMedia.size() > 1 || putaranDibatasi()) {
                            handler.postDelayed(nextSlide, detikTampil(filename) * 1000L);
                        } else {
                            jadwalkanUlangTayang(filename, detikTampil(filename) * 1000L);
                        }
                    });
                } catch (Exception e) {
                    String pesan = e.getMessage() == null
                            ? e.getClass().getSimpleName() : e.getMessage();
                    runOnUiThread(() -> {
                        mediaSlot.removeView(image);
                        mediaGagalDiputar(signature, filename, pesan);
                    });
                }
            });
        }
    }

    /** Buang isi panel media selain tampilan yang sedang tampil. */
    private void buangSelain(View tetap) {
        if (tetap.getParent() != mediaSlot) return;
        for (int i = mediaSlot.getChildCount() - 1; i >= 0; i--) {
            if (mediaSlot.getChildAt(i) != tetap) mediaSlot.removeViewAt(i);
        }
    }

    private boolean isCurrentMedia(String signature, String filename) {
        return signature.equals(mediaSignature + "|" + filename)
                && mediaIndex >= 0 && mediaIndex < welcomeMedia.size()
                && filename.equals(welcomeMedia.get(mediaIndex));
    }

    /** Lama tampil gambar ini: aturan khusus dari server, atau pengaturan umum. */
    private int detikTampil(String filename) {
        Integer khusus = sumberTablet() ? null : detikPerBerkas.get(filename);
        return khusus != null && khusus > 0 ? khusus : welcomeSlideSeconds;
    }

    private void jadwalkanUlangTayang(String filename, long ms) {
        handler.removeCallbacks(ulangTayang);
        ulangTayangBerkas = filename;
        ulangTayangMs = Math.max(3000L, ms);
        handler.postDelayed(ulangTayang, ulangTayangMs);
    }

    /**
     * Suara mengikuti pengaturan server, juga untuk video yang sedang
     * berputar. Selama pengunjung bertransaksi video selalu bisu.
     */
    private void aturSuaraVideo() {
        if (pemutarVideo == null) return;
        float volume = !suaraVideo || sedangBertransaksi ? 0f
                : sedangMengumumkan ? VOLUME_VIDEO_SAAT_PANGGILAN : 1f;
        try {
            pemutarVideo.setVolume(volume, volume);
        } catch (IllegalStateException e) {
            pemutarVideo = null;  // video sudah diganti atau dilepas
        }
    }

    private void mediaBerhasilDiputar(String filename) {
        catatTayang(filename);
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
    private void mediaGagalDiputar(String signature, String filename, String pesan) {
        if (!isCurrentMedia(signature, filename)) return;
        catatGagal(filename, pesan);
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
        if (welcomeMedia.isEmpty()) return;
        int berikut = (mediaIndex + 1) % welcomeMedia.size();
        if (berikut == 0 && putaranDibatasi()) {
            putaranIklanSelesai++;
            if (putaranIklanSelesai >= iklanPutaran) {
                selesaiPutaranIklan();
                return;
            }
        }
        showWelcomeMedia(berikut);
    }

    /** Iklan layar penuh dibatasi jumlah putarannya (bukan putar saja, bukan 0). */
    private boolean putaranDibatasi() {
        return iklanPenuh && !putarSaja && iklanPutaran > 0;
    }

    /**
     * Putaran iklan habis: kembali ke tampilan antrian dan mulai menunggu waktu
     * menganggur dari nol, sampai iklan muncul lagi bila masih tidak ada
     * kegiatan.
     */
    private void selesaiPutaranIklan() {
        sentuhTerakhirMillis = System.currentTimeMillis();
        keluarDenganAnimasiPenuh = true;
        keluarIklanPenuh();
    }

    // -----------------------------------------------------------------
    // Pengunjung dan iklan
    // -----------------------------------------------------------------

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        int aksi = event.getActionMasked();
        sentuhTerakhirMillis = System.currentTimeMillis();
        if (putarSaja) return tanganiSentuhanPutarSaja(event);
        if (iklanPenuh || menelanSentuhan) {
            // Sentuhan pertama hanya membangunkan layar. Diteruskan ke tombol
            // di bawahnya berarti pengunjung memilih layanan yang belum
            // pernah ia lihat.
            if (aksi == MotionEvent.ACTION_DOWN) {
                menelanSentuhan = true;
                keluarIklanPenuh();
                perbaruiIklan();
            }
            if (aksi == MotionEvent.ACTION_UP || aksi == MotionEvent.ACTION_CANCEL) {
                menelanSentuhan = false;
            }
            return true;
        }
        boolean hasil = super.dispatchTouchEvent(event);
        if (aksi == MotionEvent.ACTION_DOWN) perbaruiIklan();
        return hasil;
    }

    @Override
    public void onWindowFocusChanged(boolean fokus) {
        super.onWindowFocusChanged(fokus);
        // Selama dialog (Pengaturan, pembaruan) terbuka sentuhannya tidak
        // lewat sini; waktunya dihitung sebagai sedang dipakai.
        sentuhTerakhirMillis = System.currentTimeMillis();
    }

    private boolean pengunjungBertransaksi(long sekarang) {
        return showingConfirmation || showingResult || requestInFlight
                || sekarang - sentuhTerakhirMillis < JEDA_TRANSAKSI_MS;
    }

    /** Bisu, redup, dan layar penuh mengikuti keadaan pengunjung. Dipanggil tiap detik. */
    private void perbaruiIklan() {
        if (bingkaiMedia == null) return;
        long sekarang = System.currentTimeMillis();
        perbaruiModePutarSaja(sekarang);
        if (!hasWindowFocus()) sentuhTerakhirMillis = sekarang;
        if (!path.isEmpty() && !showingConfirmation && !showingResult && !requestInFlight
                && !updating && !updateRequired
                && sekarang - sentuhTerakhirMillis >= KEMBALI_KE_MENU_AWAL_MS) {
            path.clear();
            showCategories();
        }
        boolean mediaJalan = adaMediaSambutan && !mediaGagal;
        boolean transaksi = pengunjungBertransaksi(sekarang);
        if (transaksi != sedangBertransaksi) {
            sedangBertransaksi = transaksi;
            aturSuaraVideo();
        }
        float tirai = transaksi && mediaJalan && !iklanPenuh ? 0.55f : 0f;
        if (tirai != targetTirai) {
            targetTirai = tirai;
            tiraiMedia.animate().alpha(tirai).setDuration(350).start();
        }
        boolean bolehPenuh = putarSaja || (iklanPenuhDetik > 0 && !mediaGagal
                && adaMediaLayarPenuh() && !updating && !updateRequired);
        long ambang = iklanPenuhDetik * 1000L;
        long diam = sekarang - sentuhTerakhirMillis;
        boolean siapMasuk = !iklanPenuh && bolehPenuh && !transaksi;
        if (sedangKeluarPanel && (!siapMasuk || diam < ambang - ANIMASI_KELUAR_MS - 700L)) {
            // Pengunjung menyentuh, atau ada panggilan: panel kembali dan iklan batal.
            batalkanKeluarPanel();
        }
        if (iklanPenuh && !bolehPenuh) {
            keluarIklanPenuh();
        } else if (siapMasuk && !sedangKeluarPanel) {
            if (diam >= ambang) {
                masukIklanPenuh();
            } else if (animasiIklanMuncul && !putarSaja && ambang >= 5000L
                    && animasiPanelDipakai() && diam >= ambang - ANIMASI_KELUAR_MS) {
                mulaiKeluarPanel(ambang - diam);
            }
        }
    }

    /** Tiga panel keluar ke arah acak yang berbeda; iklan masuk sesudahnya. */
    private void mulaiKeluarPanel(long sisaMs) {
        View[] panel = {panelInfo, panelLayanan, panelHasil};
        List<Integer> arah = arahPanelBaru();
        long total = Math.max(700L, sisaMs);
        long durasi = Math.max(450L, total - 2 * JEDA_PANEL_KELUAR_MS);
        int lebar = rootLayout.getWidth();
        int tinggi = rootLayout.getHeight();
        sedangKeluarPanel = true;
        for (int i = 0; i < panel.length; i++) {
            View tampilan = panel[i];
            if (tampilan == null || tampilan.getVisibility() != View.VISIBLE) continue;
            float dx = 0f;
            float dy = 0f;
            switch (arah.get(i)) {
                case 0: dx = -lebar; break;
                case 1: dx = lebar; break;
                case 2: dy = -tinggi; break;
                default: dy = tinggi; break;
            }
            tampilan.animate().cancel();
            tampilan.animate()
                    .translationX(dx).translationY(dy).alpha(0f)
                    .setStartDelay(i * JEDA_PANEL_KELUAR_MS)
                    .setDuration(durasi)
                    .setInterpolator(new android.view.animation.AccelerateInterpolator(1.3f))
                    .start();
        }
        handler.postDelayed(masukSetelahPanelKeluar, total);
    }

    /** Pengunjung menyentuh atau ada panggilan di tengah animasi keluar: panel kembali. */
    private void batalkanKeluarPanel() {
        if (!sedangKeluarPanel) return;
        sedangKeluarPanel = false;
        handler.removeCallbacks(masukSetelahPanelKeluar);
        View[] panel = {panelInfo, panelLayanan, panelHasil};
        for (View tampilan : panel) {
            if (tampilan == null) continue;
            tampilan.animate().cancel();
            tampilan.animate().translationX(0f).translationY(0f).alpha(1f)
                    .setStartDelay(0L).setDuration(350L)
                    .setInterpolator(new android.view.animation.DecelerateInterpolator())
                    .start();
        }
    }

    private void pulihkanPosisiPanel() {
        View[] panel = {panelInfo, panelLayanan, panelHasil};
        for (View tampilan : panel) {
            if (tampilan == null) continue;
            tampilan.animate().cancel();
            tampilan.setTranslationX(0f);
            tampilan.setTranslationY(0f);
            tampilan.setAlpha(1f);
        }
    }

    private void masukIklanPenuh() {
        if (rootLayout == null || iklanPenuh) return;
        handler.removeCallbacks(masukSetelahPanelKeluar);
        sedangKeluarPanel = false;
        // Panel sudah keluar layar: tanpa transisi, iklan langsung memudar masuk.
        boolean tanpaTransisi = panelSudahKeluar;
        panelSudahKeluar = false;
        // Pengunjung berikutnya tidak boleh mewarisi centang prioritas.
        prioritasDipilih = false;
        // Yang bangun dari layar iklan selalu mendapati menu awal.
        if (!path.isEmpty()) {
            path.clear();
            showCategories();
        }
        iklanPenuh = true;
        putaranIklanSelesai = 0;
        visibilitasSebelumIklanPenuh.clear();
        if (!tanpaTransisi) {
            AutoTransition transisi = new AutoTransition();
            transisi.setDuration(450);
            TransitionManager.beginDelayedTransition(rootLayout, transisi);
        }
        sembunyikanUntukIklanPenuh();
        if (tanpaTransisi) pulihkanPosisiPanel();
        bukaBingkaiIklanPenuh();
        mediaModePenuh = true;
        terapkanMediaSambutan();
        if (tanpaTransisi) {
            bingkaiMedia.setAlpha(0f);
            bingkaiMedia.animate().alpha(1f).setDuration(450L).start();
        }
        hentikanDenyutAjakanIklan();
        tampilkanPanelAjakanIklan();
    }

    /**
     * Panel ajakan di ATAS layar, tetap tampil selama iklan. Video diletakkan
     * di bawahnya (margin atas `mediaSlot` = tinggi panel), jadi tidak ada
     * bagian video yang tertutup dan rasio dijaga oleh mode pas. Tinggi
     * proporsional: ~12% tinggi layar untuk layar memanjang (>2:1), ~8% untuk
     * layar tegak/biasa, dibatasi 44-96 dp; huruf mengecil bila teks tak muat.
     */
    private void tampilkanPanelAjakanIklan() {
        android.util.DisplayMetrics dm = getResources().getDisplayMetrics();
        boolean memanjang = dm.widthPixels > 2f * dm.heightPixels;
        int tinggi = Math.round(dm.heightPixels * (memanjang ? 0.09f : 0.06f));
        tinggi = Math.max(dp(36), Math.min(dp(72), tinggi));
        float huruf = tinggi * 0.5f;
        String teks = ajakanIklanPenuh.getText().toString();
        android.graphics.Paint ukur = new android.graphics.Paint(ajakanIklanPenuh.getPaint());
        ukur.setTypeface(ajakanIklanPenuh.getTypeface());
        int lebarSedia = dm.widthPixels - dp(32);
        ukur.setTextSize(huruf);
        while (huruf > dp(12) && ukur.measureText(teks) > lebarSedia) {
            huruf -= dp(1);
            ukur.setTextSize(huruf);
        }
        ajakanIklanPenuh.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX, huruf);
        FrameLayout.LayoutParams lp =
                (FrameLayout.LayoutParams) ajakanIklanPenuh.getLayoutParams();
        lp.height = tinggi;
        lp.gravity = Gravity.TOP;
        ajakanIklanPenuh.setLayoutParams(lp);
        FrameLayout.LayoutParams lm = (FrameLayout.LayoutParams) mediaSlot.getLayoutParams();
        lm.topMargin = tinggi;
        mediaSlot.setLayoutParams(lm);
        ajakanIklanPenuh.setAlpha(1f);
        ajakanIklanPenuh.setVisibility(View.VISIBLE);
        mulaiDenyutAjakanIklan();
    }

    /**
     * Yang berdenyut hanya TEKS ajakan (~2,4 detik per siklus): alfa turun ke
     * 55% dan ukuran naik 4%. Latar panel dan sisi kiri/kanan video tetap diam
     * agar video tidak tampak berkedip; skala 4% pada teks (jauh lebih kecil
     * daripada panel) tidak pernah menyentuh video di bawahnya.
     */
    private void mulaiDenyutAjakanIklan() {
        hentikanAnimatorDenyutAjakan();
        ajakanIklanPenuh.setBackgroundColor(latarIklanPenuh);
        animatorDenyutAjakan = android.animation.ValueAnimator.ofFloat(0f, 1f);
        animatorDenyutAjakan.setDuration(1200);
        animatorDenyutAjakan.setRepeatMode(android.animation.ValueAnimator.REVERSE);
        animatorDenyutAjakan.setRepeatCount(android.animation.ValueAnimator.INFINITE);
        animatorDenyutAjakan.setInterpolator(new android.view.animation.AccelerateDecelerateInterpolator());
        animatorDenyutAjakan.addUpdateListener(a -> {
            float f = (Float) a.getAnimatedValue();
            ajakanIklanPenuh.setAlpha(1f - 0.45f * f);
            ajakanIklanPenuh.setScaleX(1f + 0.04f * f);
            ajakanIklanPenuh.setScaleY(1f + 0.04f * f);
        });
        animatorDenyutAjakan.start();
    }

    /** `#RRGGBB` yang sah dan tidak terlalu terang, atau null. */
    static Integer uraiLatarIklan(String hex) {
        if (hex == null || !hex.matches("#[0-9A-Fa-f]{6}")) return null;
        int warna = Color.parseColor(hex);
        return luminansWarna(warna) > LUMINANS_MAKS_IKLAN ? null : warna;
    }

    /**
     * Pakai warna latar iklan penuh dari server; nilai tak sah jatuh ke navy
     * bawaan. Teks putih/hitam dan puncak denyut dihitung dari warna ini.
     */
    private void terapkanLatarIklanPenuh(String hex) {
        Integer baru = uraiLatarIklan(hex);
        int warna = baru != null ? baru : LATAR_IKLAN_BAWAAN;
        if (warna == latarIklanPenuh) return;
        latarIklanPenuh = warna;
        double lum = luminansWarna(warna);
        boolean teksPutih = 1.05 / (lum + 0.05) >= (lum + 0.05) / 0.05;
        teksIklanPenuh = teksPutih ? Color.WHITE : Color.BLACK;
        int sasaran = teksPutih ? 255 : 0;
        puncakDenyutIklan = Color.rgb(
                Math.round(Color.red(warna) + (sasaran - Color.red(warna)) * 0.12f),
                Math.round(Color.green(warna) + (sasaran - Color.green(warna)) * 0.12f),
                Math.round(Color.blue(warna) + (sasaran - Color.blue(warna)) * 0.12f));
        if (ajakanIklanPenuh != null) {
            ajakanIklanPenuh.setTextColor(teksIklanPenuh);
            if (teksPutih) {
                ajakanIklanPenuh.setShadowLayer(dp(2), 0, dp(1), Color.argb(160, 0, 0, 0));
            } else {
                ajakanIklanPenuh.setShadowLayer(0, 0, 0, Color.TRANSPARENT);
            }
        }
        if (!iklanPenuh) {
            if (ajakanIklanPenuh != null) ajakanIklanPenuh.setBackgroundColor(warna);
            return;
        }
        // Sedang tampil: semua permukaan berganti sekaligus ke satu warna.
        if (rootLayout != null) rootLayout.setBackgroundColor(warna);
        if (panelInfo != null) panelInfo.setBackgroundColor(warna);
        aturLatarGambarMedia(warna);
        if (ajakanIklanPenuh != null
                && ajakanIklanPenuh.getVisibility() == View.VISIBLE
                && animatorDenyutAjakan != null) {
            mulaiDenyutAjakanIklan();
        } else if (ajakanIklanPenuh != null) {
            ajakanIklanPenuh.setBackgroundColor(warna);
        }
    }

    private void hentikanAnimatorDenyutAjakan() {
        if (animatorDenyutAjakan != null) {
            animatorDenyutAjakan.removeAllUpdateListeners();
            animatorDenyutAjakan.cancel();
            animatorDenyutAjakan = null;
            if (ajakanIklanPenuh != null) {
                ajakanIklanPenuh.setBackgroundColor(latarIklanPenuh);
                ajakanIklanPenuh.setTextColor(teksIklanPenuh);
                ajakanIklanPenuh.setScaleX(1f);
                ajakanIklanPenuh.setScaleY(1f);
                ajakanIklanPenuh.setAlpha(1f);
            }
        }
    }

    /**
     * Saat iklan memenuhi layar, semua selain bingkai media disembunyikan.
     * Dipanggil lagi setelah penyegaran yang mengatur ulang visibilitas
     * (judul, baris loket); visibilitas yang baru ditetapkan penyegaran itu
     * yang dipulihkan nanti.
     */
    private void sembunyikanUntukIklanPenuh() {
        if (!iklanPenuh || panelInfo == null) return;
        List<View> sasaran = new ArrayList<>();
        for (int i = 0; i < panelInfo.getChildCount(); i++) {
            View anak = panelInfo.getChildAt(i);
            if (anak != bingkaiMedia) sasaran.add(anak);
        }
        if (panelLayanan != null) sasaran.add(panelLayanan);
        if (panelHasil != null) sasaran.add(panelHasil);
        for (View view : sasaran) {
            if (view.getVisibility() != View.GONE
                    || !visibilitasSebelumIklanPenuh.containsKey(view)) {
                visibilitasSebelumIklanPenuh.put(view, view.getVisibility());
            }
            view.setVisibility(View.GONE);
        }
        bingkaiMedia.setVisibility(View.VISIBLE);
    }

    /**
     * Iklan memenuhi SELURUH layar: tanpa margin, padding, sudut membulat,
     * dan garis tepi, di atas latar hitam. Video tetap utuh (rasio dijaga,
     * pita hitam bila rasionya berbeda), bukan dipotong.
     */
    private void bukaBingkaiIklanPenuh() {
        if (rootLayout == null || panelInfo == null) return;
        if (paddingRootAsli == null) {
            paddingRootAsli = new int[]{rootLayout.getPaddingLeft(),
                    rootLayout.getPaddingTop(), rootLayout.getPaddingRight(),
                    rootLayout.getPaddingBottom()};
            paddingInfoAsli = new int[]{panelInfo.getPaddingLeft(),
                    panelInfo.getPaddingTop(), panelInfo.getPaddingRight(),
                    panelInfo.getPaddingBottom()};
            latarInfoAsli = panelInfo.getBackground();
            elevasiInfoAsli = panelInfo.getElevation();
        }
        rootLayout.setPadding(0, 0, 0, 0);
        rootLayout.setBackgroundColor(latarIklanPenuh);
        panelInfo.setPadding(0, 0, 0, 0);
        panelInfo.setBackgroundColor(latarIklanPenuh);
        panelInfo.setElevation(0f);
        aturLatarGambarMedia(latarIklanPenuh);
    }

    private void pulihkanBingkaiIklanPenuh() {
        if (paddingRootAsli == null || rootLayout == null || panelInfo == null) return;
        rootLayout.setPadding(paddingRootAsli[0], paddingRootAsli[1],
                paddingRootAsli[2], paddingRootAsli[3]);
        rootLayout.setBackgroundColor(LATAR);
        panelInfo.setPadding(paddingInfoAsli[0], paddingInfoAsli[1],
                paddingInfoAsli[2], paddingInfoAsli[3]);
        panelInfo.setBackground(latarInfoAsli);
        panelInfo.setElevation(elevasiInfoAsli);
        aturLatarGambarMedia(KARTU);
        paddingRootAsli = null;
        paddingInfoAsli = null;
        latarInfoAsli = null;
    }

    /** Warna di balik gambar yang tidak memenuhi bingkai (FIT_CENTER). */
    private void aturLatarGambarMedia(int warna) {
        if (mediaSlot == null) return;
        for (int i = 0; i < mediaSlot.getChildCount(); i++) {
            View anak = mediaSlot.getChildAt(i);
            if (anak instanceof ImageView) anak.setBackgroundColor(warna);
            else if (anak instanceof VideoTekstur) {
                anak.setBackgroundColor(warna == KARTU ? Color.BLACK : warna);
            }
        }
    }

    private void keluarIklanPenuh() {
        if (!iklanPenuh) return;
        iklanPenuh = false;
        handler.removeCallbacks(akhirIklanAwal);
        bingkaiMedia.animate().cancel();
        bingkaiMedia.setAlpha(1f);
        boolean animasiPanel = animasiPanelDipakai();
        if (rootLayout != null && !animasiPanel) {
            AutoTransition transisi = new AutoTransition();
            transisi.setDuration(300);
            TransitionManager.beginDelayedTransition(rootLayout, transisi);
        }
        for (Map.Entry<View, Integer> isi : visibilitasSebelumIklanPenuh.entrySet()) {
            isi.getKey().setVisibility(isi.getValue());
        }
        visibilitasSebelumIklanPenuh.clear();
        pulihkanBingkaiIklanPenuh();
        mediaModePenuh = false;
        terapkanMediaSambutan();
        hentikanDenyutAjakanIklan();
        ajakanIklanPenuh.setVisibility(View.GONE);
        FrameLayout.LayoutParams lm = (FrameLayout.LayoutParams) mediaSlot.getLayoutParams();
        lm.topMargin = 0;
        mediaSlot.setLayoutParams(lm);
        perbaruiJudul();
        tampilanLoket = "";  // paksa baris loket ditata ulang
        terapkanBarisLoket();
        if (animasiPanel) animasiPanelMasuk(keluarDenganAnimasiPenuh);
        keluarDenganAnimasiPenuh = false;
    }

    /**
     * Pada berkas TERAKHIR di putaran terakhir, iklan meredup dan tampilan
     * antrian mulai masuk `animasiMulaiMs` sebelum berkas itu selesai, jadi
     * akhir iklan bertumpuk dengan animasi. Berkas yang lebih pendek dari
     * jeda itu mulai segera.
     */
    private void jadwalkanAkhirIklanAwal(long durasiMs) {
        handler.removeCallbacks(akhirIklanAwal);
        if (durasiMs <= 0L || animasiMulaiMs <= 0L || !putaranDibatasi()
                || !animasiPanelDipakai()
                || putaranIklanSelesai != iklanPutaran - 1
                || welcomeMedia.isEmpty() || mediaIndex != welcomeMedia.size() - 1) {
            return;
        }
        long tunda = Math.max(0L, durasiMs - (animasiMulaiMs + DURASI_REDUP_IKLAN_MS));
        handler.postDelayed(akhirIklanAwal, tunda);
    }

    private final Runnable akhirIklanAwal = () -> {
        if (!putaranDibatasi()) return;
        handler.removeCallbacks(nextSlide);
        handler.removeCallbacks(ulangTayang);
        if (pemutarVideo != null) {
            try {
                pemutarVideo.setVolume(0f, 0f);
            } catch (IllegalStateException ignored) {
                // Pemutar sudah dilepas; peredupan tetap berjalan.
            }
        }
        bingkaiMedia.animate().alpha(0f).setDuration(DURASI_REDUP_IKLAN_MS)
                .withEndAction(() -> {
                    if (!putaranDibatasi()) return;
                    sentuhTerakhirMillis = System.currentTimeMillis();
                    keluarDenganAnimasiPenuh = true;
                    keluarIklanPenuh();
                }).start();
    };

    // --- panggilan petugas mengalahkan iklan --------------------------------

    /** Bandingkan loket dengan pengecekan sebelumnya; panggilan baru memicu sorotan. */
    private void deteksiPanggilanBaru() {
        Map<String, String> sekarang = new HashMap<>();
        Loket terbaru = null;
        boolean ada = false;
        for (Loket loket : loketList) {
            if (loket.nomor.isEmpty() || !"Dipanggil".equalsIgnoreCase(loket.status)) continue;
            String tanda = loket.nomor + "#" + loket.panggilan;
            sekarang.put(loket.nama, tanda);
            if (penandaPanggilanLoket != null && !tanda.equals(penandaPanggilanLoket.get(loket.nama))) {
                terbaru = loket;
                ada = true;
            }
        }
        boolean pertama = penandaPanggilanLoket == null;
        penandaPanggilanLoket = sekarang;
        if (pertama || !ada || terbaru == null) return;
        panggilanBaru(terbaru);
    }

    /**
     * Panggilan baru (atau ulang): iklan layar penuh berhenti, tampilan antrian
     * muncul dengan animasi sedang, nomornya ditampilkan besar sebentar, dan
     * hitungan menganggur dimulai dari nol supaya iklan tidak langsung kembali.
     */
    private void panggilanBaru(Loket loket) {
        if (!panggilanHentikanIklan || putarSaja) return;
        sentuhTerakhirMillis = System.currentTimeMillis();
        batalkanKeluarPanel();
        if (iklanPenuh) {
            handler.removeCallbacks(akhirIklanAwal);
            keluarDenganAnimasiPenuh = false;
            keluarIklanPenuh();
        }
        if (!showingConfirmation && !showingResult) {
            tampilkanBannerPanggilan(loket.nomor, loket.nama);
        }
    }

    /** Nomor besar di tengah layar selama beberapa detik; sentuhan tetap tembus. */
    private void tampilkanBannerPanggilan(String nomor, String loket) {
        if (bannerPanggilan != null) {
            bannerPanggilan.dismiss();
            bannerPanggilan = null;
        }
        LinearLayout isi = new LinearLayout(this);
        isi.setOrientation(LinearLayout.VERTICAL);
        isi.setGravity(Gravity.CENTER);
        isi.setPadding(dp(36), dp(24), dp(36), dp(24));
        isi.setBackground(rounded(Color.argb(235, 4, 120, 87), dp(28)));
        TextView judul = text("Nomor dipanggil", 16, Color.WHITE, true);
        judul.setGravity(Gravity.CENTER);
        isi.addView(judul);
        TextView angka = text(nomor, 64, Color.WHITE, true);
        angka.setTypeface(huruf(800));
        angka.setGravity(Gravity.CENTER);
        pasangSatuBaris(angka, 28, 64);
        isi.addView(angka, new LinearLayout.LayoutParams(dp(280), -2));
        TextView tujuan = text("→ " + loket, 24, Color.WHITE, true);
        tujuan.setGravity(Gravity.CENTER);
        pasangSatuBaris(tujuan, 12, 24);
        isi.addView(tujuan, new LinearLayout.LayoutParams(dp(280), -2));
        android.widget.PopupWindow jendela = new android.widget.PopupWindow(
                isi, ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        jendela.setTouchable(false);
        jendela.setFocusable(false);
        bannerPanggilan = jendela;
        View decor = getWindow().getDecorView();
        decor.post(() -> {
            if (bannerPanggilan != jendela || isFinishing()) return;
            try {
                jendela.showAtLocation(decor, Gravity.CENTER, 0, 0);
            } catch (RuntimeException ignored) {
                // Jendela belum siap; sorotan kartu loket tetap tampil.
                return;
            }
            isi.setAlpha(0f);
            isi.setScaleX(0.85f);
            isi.setScaleY(0.85f);
            isi.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(350).start();
            handler.postDelayed(() -> {
                if (bannerPanggilan != jendela) return;
                isi.animate().alpha(0f).setDuration(350).withEndAction(() -> {
                    if (bannerPanggilan == jendela) bannerPanggilan = null;
                    try {
                        jendela.dismiss();
                    } catch (RuntimeException ignored) {
                        // Sudah tertutup.
                    }
                }).start();
            }, LAMA_BANNER_PANGGILAN_MS);
        });
    }

    /** Animasi dipakai bila server menyalakannya dan Android tidak mematikan animasi. */
    private boolean animasiPanelDipakai() {
        if (!animasiKembali || rootLayout == null) return false;
        float skala = android.provider.Settings.Global.getFloat(getContentResolver(),
                android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f);
        return skala > 0f;
    }

    /**
     * Tiga panel (judul dan loket, pilihan layanan, hasil nomor) masuk dari
     * arah acak yang berbeda satu sama lain, dan berbeda dari kali
     * sebelumnya. Penuh (putaran habis): 1800 ms berurutan 250 ms; singkat
     * (pengunjung menyentuh): 900 ms tanpa jeda agar tidak menunda pilihan.
     * Hanya geser dan transparansi; tata letak akhirnya tidak berubah.
     */
    /** Arah: 0 kiri, 1 kanan, 2 atas, 3 bawah. Tiga arah berbeda dari empat, berbeda dari kali lalu. */
    private List<Integer> arahPanelBaru() {
        List<Integer> arah = new ArrayList<>(java.util.Arrays.asList(0, 1, 2, 3));
        java.util.Collections.shuffle(arah, acakArah);
        int kombinasi = arah.get(0) * 16 + arah.get(1) * 4 + arah.get(2);
        if (kombinasi == arahAnimasiTerakhir) {
            java.util.Collections.rotate(arah, 1);
            kombinasi = arah.get(0) * 16 + arah.get(1) * 4 + arah.get(2);
        }
        arahAnimasiTerakhir = kombinasi;
        return arah;
    }

    private void animasiPanelMasuk(boolean penuh) {
        if (animasiNomorAktif) {
            // Nomor menunggu dibangun ulang dan muncul sesudah panelnya hampir tiba.
            ulangiAnimasiNomor = true;
            jedaAwalNomorMs = penuh ? 1000L : 400L;
            tandaMenunggu = "";
            if (!showingResult) tampilkanNomorMenunggu();
        }
        View[] panel = {panelInfo, panelLayanan, panelHasil};
        List<Integer> arah = arahPanelBaru();
        long durasi = penuh ? DURASI_PANEL_PENUH_MS : DURASI_PANEL_PANGGILAN_MS;
        long jeda = penuh ? JEDA_PANEL_PENUH_MS : 0L;
        int lebar = rootLayout.getWidth();
        int tinggi = rootLayout.getHeight();
        for (int i = 0; i < panel.length; i++) {
            View tampilan = panel[i];
            if (tampilan == null || tampilan.getVisibility() != View.VISIBLE) continue;
            float dx = 0f;
            float dy = 0f;
            switch (arah.get(i)) {
                case 0: dx = -lebar; break;
                case 1: dx = lebar; break;
                case 2: dy = -tinggi; break;
                default: dy = tinggi; break;
            }
            tampilan.animate().cancel();
            tampilan.setTranslationX(dx);
            tampilan.setTranslationY(dy);
            tampilan.setAlpha(0f);
            tampilan.animate()
                    .translationX(0f).translationY(0f).alpha(1f)
                    .setStartDelay(i * jeda)
                    .setDuration(durasi)
                    .setInterpolator(new android.view.animation.OvershootInterpolator(0.3f))
                    .start();
        }
    }

    private void hentikanDenyutAjakanIklan() {
        hentikanAnimatorDenyutAjakan();
        if (denyutAjakanIklan != null) {
            handler.removeCallbacks(denyutAjakanIklan);
            denyutAjakanIklan = null;
        }
        if (ajakanIklanPenuh != null) {
            ajakanIklanPenuh.animate().cancel();
            ajakanIklanPenuh.setAlpha(1f);
        }
    }

    // -----------------------------------------------------------------
    // Laporan tayang
    // -----------------------------------------------------------------

    private void catatTayang(String filename) {
        if (sumberTablet()) return;
        int[] hitung = hitungTayang.get(filename);
        if (hitung == null) hitungTayang.put(filename, hitung = new int[2]);
        hitung[0]++;
        terakhirGagal.put(filename, false);
    }

    private void catatGagal(String filename, String pesan) {
        if (sumberTablet()) return;
        int[] hitung = hitungTayang.get(filename);
        if (hitung == null) hitungTayang.put(filename, hitung = new int[2]);
        hitung[1]++;
        galatTayang.put(filename, pesan == null ? "" : pesan);
        terakhirGagal.put(filename, true);
    }

    /**
     * Kirim jumlah sejak laporan terakhir. Bila gagal terkirim, jumlahnya
     * dikembalikan dan ikut laporan berikutnya.
     */
    private void kirimLaporanTayang() {
        if (laporanTayangTerkirim || hitungTayang.isEmpty() || !hasServerConfig()) return;
        Map<String, int[]> kiriman = new HashMap<>(hitungTayang);
        Map<String, String> galat = new HashMap<>(galatTayang);
        Map<String, Boolean> gagalTerakhir = new HashMap<>(terakhirGagal);
        hitungTayang.clear();
        galatTayang.clear();
        JSONObject body;
        try {
            JSONArray items = new JSONArray();
            for (Map.Entry<String, int[]> isi : kiriman.entrySet()) {
                String pesan = galat.get(isi.getKey());
                items.put(new JSONObject()
                        .put("name", isi.getKey())
                        .put("plays", isi.getValue()[0])
                        .put("failures", isi.getValue()[1])
                        .put("error", pesan == null ? "" : pesan.length() > 190
                                ? pesan.substring(0, 190) : pesan)
                        .put("last_failed", Boolean.TRUE.equals(gagalTerakhir.get(isi.getKey()))));
                if (items.length() >= 100) break;
            }
            body = new JSONObject().put("items", items);
        } catch (Exception e) {
            return;  // laporan hanya keterangan
        }
        laporanTayangTerkirim = true;
        request("POST", "/v1/kiosk/media-report", body,
                json -> laporanTayangTerkirim = false,
                error -> {
                    laporanTayangTerkirim = false;
                    for (Map.Entry<String, int[]> isi : kiriman.entrySet()) {
                        int[] sekarang = hitungTayang.get(isi.getKey());
                        if (sekarang == null) {
                            hitungTayang.put(isi.getKey(), isi.getValue());
                        } else {
                            sekarang[0] += isi.getValue()[0];
                            sekarang[1] += isi.getValue()[1];
                        }
                        String pesan = galat.get(isi.getKey());
                        if (pesan != null && !galatTayang.containsKey(isi.getKey())) {
                            galatTayang.put(isi.getKey(), pesan);
                        }
                    }
                });
    }

    private String mediaUrl(String filename) {
        String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
        return base + "/v1/kiosk/media/" + Uri.encode(filename);
    }

    private java.util.Map<String, String> authHeaders(String url) {
        java.util.Map<String, String> headers = new java.util.HashMap<>();
        if (AlamatServer.aman(url)) {
            headers.put("Authorization", "Bearer " + preferences.getString(TOKEN, ""));
        }
        return headers;
    }

    private byte[] downloadMedia(String mediaUrl) throws Exception {
        return UnduhServer.keMemori(mediaUrl, this::applyHeaders);
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
            if (item.isFile() && !nama.startsWith(".") && BerkasMedia.berakhiran(nama, BerkasMedia.EKSTENSI_MEDIA)) {
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
    /** Apakah berkas tampil di panel atas (penuh=false) atau layar penuh. */
    private boolean tampilDi(String nama, boolean penuh) {
        String tempat = tampilBerkas.get(nama);
        if (tempat == null || "keduanya".equals(tempat)) return true;
        return penuh ? "penuh".equals(tempat) : "panel".equals(tempat);
    }

    /** Ada media yang boleh memenuhi layar saat anjungan menganggur. */
    private boolean adaMediaLayarPenuh() {
        if (sumberTablet()) {
            for (File item : daftarMediaTablet()) {
                if (tampilLokalDi(item.getName(), true)) return true;
            }
            return false;
        }
        if (!isMediaKind(serverKind)) return false;
        for (String nama : serverMedia) {
            if (tampilDi(nama, true)) return true;
        }
        return false;
    }

    private void terapkanMediaSambutan() {
        if (mediaSlot == null) return;
        boolean tablet = sumberTablet();
        List<String> media = new ArrayList<>();
        String signature;
        boolean putar;
        if (tablet) {
            StringBuilder tanda = new StringBuilder(SUMBER_TABLET)
                    .append(mediaModePenuh ? "|penuh" : "|panel");
            for (File item : daftarMediaTablet()) {
                if (!tampilLokalDi(item.getName(), mediaModePenuh)) continue;
                media.add(item.getName());
                tanda.append('|').append(item.getName()).append(':')
                        .append(item.length()).append(':').append(item.lastModified());
            }
            signature = tanda.toString();
            putar = !media.isEmpty();
        } else {
            for (String nama : serverMedia) {
                if (tampilDi(nama, mediaModePenuh)) media.add(nama);
            }
            if (media.isEmpty() && putarSaja) {
                // Putar saja: tanpa daftar layar penuh, pakai daftar panel atas.
                for (String nama : serverMedia) {
                    if (tampilDi(nama, false)) media.add(nama);
                }
            }
            List<String> kunci = new ArrayList<>();
            for (String nama : media) kunci.add(String.valueOf(kunciSalinan.get(nama)));
            signature = serverKind + (mediaModePenuh ? "|penuh|" : "|panel|")
                    + TextUtils.join("|", media) + "|" + TextUtils.join("|", kunci);
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
            applyWelcomeText(teksCadanganMedia());
            if (putar) {
                showWelcomeMedia(0);
            } else {
                handler.removeCallbacks(nextSlide);
            }
        } else if (!putar) {
            applyWelcomeText(teksCadanganMedia());
        }
    }

    /** Teks di panel media bila tidak ada gambar atau video yang dapat diputar. */
    private String teksCadanganMedia() {
        if (putarSaja) {
            return "Layanan antrian sementara tidak tersedia.\nSilakan hubungi petugas.";
        }
        return welcomeFallbackText;
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

    /**
     * Lapor tingkat baterai ke server untuk Kesehatan Sistem. Hanya bila
     * berubah 5 poin atau lebih, status pengisian berganti, atau sudah lima
     * menit; baterai tablet anjungan yang habis di tengah jam layanan adalah
     * gangguan yang paling mudah dicegah bila terlihat lebih dulu.
     */
    private void laporkanBaterai() {
        if (!hasServerConfig()) return;
        Intent baterai = registerReceiver(null,
                new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        if (baterai == null) return;
        int level = baterai.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1);
        int skala = baterai.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, -1);
        if (level < 0 || skala <= 0) return;
        int persen = Math.round(level * 100f / skala);
        int status = baterai.getIntExtra(android.os.BatteryManager.EXTRA_STATUS, -1);
        boolean mengisi = status == android.os.BatteryManager.BATTERY_STATUS_CHARGING
                || status == android.os.BatteryManager.BATTERY_STATUS_FULL;
        long sekarang = System.currentTimeMillis();
        if (bateraiTerakhirPersen >= 0
                && Math.abs(persen - bateraiTerakhirPersen) < 5
                && mengisi == bateraiTerakhirMengisi
                && sekarang - bateraiTerakhirWaktu < 300_000L) {
            return;
        }
        bateraiTerakhirPersen = persen;
        bateraiTerakhirMengisi = mengisi;
        bateraiTerakhirWaktu = sekarang;
        request("POST", "/v1/kiosk/baterai",
                new JSONObjectBuilder()
                        .put("percent", persen)
                        .put("charging", mengisi)
                        .build(),
                json -> { }, error -> { });
    }

    /**
     * Lapor ke server berapa berkas daftar putar yang sudah tersalin utuh.
     * Hanya bila angkanya berubah atau sudah lima menit, supaya tidak
     * membebani jaringan; server menampilkannya di kartu perangkat.
     */
    private void laporkanStatusMedia() {
        if (!hasServerConfig() || sumberTablet()) return;
        int total = serverMedia.size();
        int tersalin = 0;
        long byteTotal = 0L;
        for (String nama : serverMedia) {
            File berkas = berkasMedia(nama);
            if (berkas != null) {
                tersalin++;
                byteTotal += berkas.length();
            }
        }
        long sekarang = System.currentTimeMillis();
        if (statusMediaTerakhir != null && statusMediaTerakhir[0] == total
                && statusMediaTerakhir[1] == tersalin
                && sekarang - statusMediaWaktu < 300_000L) {
            return;
        }
        statusMediaTerakhir = new int[]{total, tersalin};
        statusMediaWaktu = sekarang;
        request("POST", "/v1/kiosk/media-status",
                new JSONObjectBuilder()
                        .put("total", total)
                        .put("copied", tersalin)
                        .put("bytes", byteTotal)
                        .build(),
                json -> { }, error -> { });
    }

    /** Berjalan di thread pengunduh. */
    private void unduhSalinan(String url, String kunci) throws Exception {
        UnduhServer.keBerkas(url, folderSalinan(), kunci, CADANGAN_RUANG_BYTES,
                this::applyHeaders);
    }

    private void salinanSelesai(String nama, String kunci, boolean berhasil) {
        sedangDiunduh.remove(kunci);
        laporkanStatusMedia();
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

        // Tanpa gulir: kartu disusun dalam baris berbobot yang membagi
        // seluruh tinggi panel. Jumlah kolom dan ukuran huruf dihitung dari
        // ukuran panel, sehingga semua layanan selalu terlihat sekaligus.
        if (contentSlot.getHeight() <= 0 && !menungguUkuranPanel) {
            menungguUkuranPanel = true;
            contentSlot.addOnLayoutChangeListener(new View.OnLayoutChangeListener() {
                @Override
                public void onLayoutChange(View v, int kiri, int atas, int kanan, int bawah,
                                           int kiriLama, int atasLama, int kananLama,
                                           int bawahLama) {
                    if (bawah - atas <= 0) return;
                    contentSlot.removeOnLayoutChangeListener(this);
                    menungguUkuranPanel = false;
                    contentSlot.post(() -> {
                        if (!showingConfirmation && !updating && !updateRequired) {
                            showCategories(showingResult);
                        }
                    });
                }
            });
        }
        Integer parent = path.isEmpty() ? null : path.get(path.size() - 1).id;
        List<Category> visible = new ArrayList<>();
        for (Category item : categories) {
            if (Objects.equals(item.parentId, parent)) visible.add(item);
        }
        int jumlahKartu = visible.size() + (path.isEmpty() ? 0 : 1);
        int[] susunan = susunanKartu(jumlahKartu, visible);
        int columns = susunan[0];
        int tinggiKartu = susunan[1];

        List<View> kartuList = new ArrayList<>();
        if (!path.isEmpty()) {
            kartuList.add(buatKartu("‹", "Kembali", null, new int[]{ABU_LEMBUT, MUTED}, () -> {
                path.remove(path.size() - 1);
                showCategories();
            }, tinggiKartu));
        }
        for (Category item : visible) {
            View kartu = buatKartuLayanan(item, tinggiKartu);
            kartuList.add(kartu);
            if (!item.group) ticketChoices.add(kartu);
        }

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setGravity(Gravity.CENTER);
        content.setPadding(dp(2), dp(2), dp(2), dp(2));
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
        } else {
            if (path.isEmpty()) {
                setHint(visible.size() == 1
                        ? "Sentuh tombol di bawah untuk mengambil nomor"
                        : "Sentuh jenis layanan yang Anda butuhkan", "ajak");
            } else {
                Category selected = path.get(path.size() - 1);
                setHint(selected.name + " — pilih layanan, atau sentuh Kembali", "ajak");
            }
            // Kotak prioritas DI ATAS tombol layanan: dibaca lebih dulu ("apakah Anda
            // prioritas?"), baru memilih layanan. Terlihat sejak menu awal, supaya
            // petugas yang berjaga dapat mengarahkan pengunjung lansia mencentangnya.
            if (prioritasAktifServer) {
                LinearLayout.LayoutParams kotak = new LinearLayout.LayoutParams(-1, dp(44));
                kotak.setMargins(dp(4), dp(2), dp(4), dp(4));
                content.addView(buatKotakPrioritas(), kotak);
            }
            int baris = (kartuList.size() + columns - 1) / columns;
            for (int r = 0; r < baris; r++) {
                LinearLayout deret = new LinearLayout(this);
                deret.setOrientation(LinearLayout.HORIZONTAL);
                for (int c = 0; c < columns; c++) {
                    int i = r * columns + c;
                    LinearLayout.LayoutParams sel = new LinearLayout.LayoutParams(0, -1, 1f);
                    sel.setMargins(dp(4), dp(4), dp(4), dp(4));
                    // Sel kosong di deret terakhir menjaga lebar kartu tetap sama.
                    deret.addView(i < kartuList.size() ? kartuList.get(i) : new View(this), sel);
                }
                // Tinggi deret dibatasi supaya kartu tidak raksasa bila layanannya sedikit.
                LinearLayout.LayoutParams ukuranDeret = tinggiKartu > 0
                        ? new LinearLayout.LayoutParams(-1, tinggiKartu + dp(8))
                        : new LinearLayout.LayoutParams(-1, 0, 1f);
                content.addView(deret, ukuranDeret);
            }
        }
        contentSlot.addView(content, new FrameLayout.LayoutParams(-1, -1));
        // Kartu masuk satu per satu: memudar dan naik sedikit.
        for (int i = 0; i < kartuList.size(); i++) {
            View kartu = kartuList.get(i);
            kartu.setAlpha(0f);
            kartu.setTranslationY(dp(14));
            kartu.animate().alpha(1f).translationY(0f)
                    .setStartDelay(40L * i).setDuration(260)
                    .setInterpolator(new android.view.animation.DecelerateInterpolator())
                    .start();
        }
        updateAvailability();
    }

    /**
     * Pilih jumlah kolom dan tinggi kartu supaya SEMUA kartu muat di panel.
     *
     * Kolom awal dari lebar layar dan nama terpanjang (nama panjang butuh
     * kartu lebar). Bila kartunya jadi terlalu pendek, kolom ditambah
     * selama kartu masih cukup lebar. Mengembalikan {kolom, tinggi kartu px};
     * tinggi 0 berarti ukuran panel belum diketahui.
     */
    private int[] susunanKartu(int jumlah, List<Category> visible) {
        float satuan = getResources().getDisplayMetrics().density * uiScale;
        int lebarPanel = contentSlot.getWidth();
        int tinggiPanel = contentSlot.getHeight() - dp(4)
                - (prioritasAktifServer ? dp(50) : 0);
        int kolomLayar = Math.max(1, Math.min(3,
                Math.round(getResources().getDisplayMetrics().widthPixels
                        / getResources().getDisplayMetrics().density / 118f)));
        int terpanjang = 0;
        for (Category item : visible) terpanjang = Math.max(terpanjang, item.name.length());
        int kolom = terpanjang > 30 ? 1 : terpanjang > 18 ? Math.min(kolomLayar, 2) : kolomLayar;
        kolom = Math.max(1, Math.min(kolom, Math.max(1, jumlah)));
        if (tinggiPanel <= 0 || lebarPanel <= 0 || jumlah == 0) return new int[]{kolom, 0};

        int tinggi = tinggiPanel / ((jumlah + kolom - 1) / kolom) - dp(8);
        while (tinggi < dp(72) && kolom < Math.min(4, jumlah)
                && lebarPanel / (kolom + 1) >= Math.round(96 * satuan)) {
            kolom++;
            tinggi = tinggiPanel / ((jumlah + kolom - 1) / kolom) - dp(8);
        }
        return new int[]{kolom, Math.max(dp(32), Math.min(dp(128), tinggi))};
    }

    // -----------------------------------------------------------------
    // Baris "NOMOR DI LOKET": di panel atas atau bawah    // -----------------------------------------------------------------
    // Baris "NOMOR DI LOKET": di panel atas atau bawah
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
        bingkaiMedia.setVisibility(besar ? View.GONE : View.VISIBLE);
        loketAtas.setLayoutParams(besar
                ? new LinearLayout.LayoutParams(-1, 0, 1)
                : new LinearLayout.LayoutParams(-1, -2));
        if (!letak.isEmpty()) {
            isiBarisLoket("atas".equals(letak) ? loketAtas : loketBawah, besar);
        }
        if (panelHasilGelap) loketBawah.setVisibility(View.GONE);
        sembunyikanUntukIklanPenuh();

        int baris = "bawah".equals(letak)
                ? BARIS_NOMOR_MENUNGGU_BERSAMA_LOKET : BARIS_NOMOR_MENUNGGU;
        if (baris != barisMenunggu) {
            barisMenunggu = baris;
            if (!showingResult && !showingConfirmation) tampilkanNomorMenunggu();
        }
    }

    private void isiBarisLoket(LinearLayout strip, boolean besar) {
        strip.setPadding(0, dp(besar ? 8 : 4), 0, dp(4));
        // Bukan "Sedang dilayani": nomor di sini bisa baru dipanggil (orangnya
        // belum datang), dilayani, atau ditunda; loketnya bisa istirahat.
        TextView judul = text("Nomor di loket", besar ? 14 : 12, MUTED, true);
        judul.setGravity(Gravity.CENTER);
        strip.addView(judul, new LinearLayout.LayoutParams(-1, -2));

        int jumlah = loketList.size();
        boolean sorotPerubahan = nomorLoketPernahTampil;
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
            Loket loket = loketList.get(i);
            View kartu = kartuLoket(loket, besar);
            deret.addView(kartu, selLoket());
            String lama = nomorLoketTerakhir.put(loket.nama, loket.nomor);
            if (sorotPerubahan && !loket.nomor.isEmpty() && !loket.nomor.equals(lama)) {
                sorotLoket(kartu);
            }
        }
        nomorLoketPernahTampil = true;
        // Deret terakhir yang tidak penuh diisi sel kosong agar kartunya sama lebar.
        int sisa = jumlah % kolom;
        for (int i = 0; sisa > 0 && i < kolom - sisa; i++) {
            deret.addView(new View(this), selLoket());
        }
    }

    /**
     * Loket yang baru memanggil: angkanya bergulir masuk dari atas, lalu
     * kartunya berdenyut tiga kali supaya pengunjung melihat perubahannya.
     */
    private void sorotLoket(View kartu) {
        View nomor = kartu.findViewWithTag("nomor");
        if (nomor != null) {
            nomor.setAlpha(0f);
            nomor.setTranslationY(-dp(18));
            nomor.animate().alpha(1f).translationY(0f).setDuration(380)
                    .setInterpolator(new android.view.animation.OvershootInterpolator(1.4f))
                    .start();
        }
        android.animation.ObjectAnimator denyut =
                android.animation.ObjectAnimator.ofPropertyValuesHolder(kartu,
                        android.animation.PropertyValuesHolder.ofFloat(View.SCALE_X, 1f, 1.06f),
                        android.animation.PropertyValuesHolder.ofFloat(View.SCALE_Y, 1f, 1.06f));
        denyut.setDuration(220);
        denyut.setRepeatCount(5);
        denyut.setRepeatMode(android.animation.ValueAnimator.REVERSE);
        denyut.setStartDelay(200);
        denyut.start();
    }

    private LinearLayout.LayoutParams selLoket() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1f);
        params.setMargins(dp(3), dp(3), dp(3), dp(3));
        return params;
    }

    /**
     * Kartu satu loket. Nomornya selalu tepat di tengah kartu, mendatar dan
     * tegak: kartu berupa FrameLayout, nomor mengisi seluruh kartu dengan
     * jarak atas dan bawah yang SAMA, sedangkan nama loket (atas) dan nama
     * layanan (bawah) menempel di tepinya tanpa ikut menggeser nomor.
     */
    /** Hijau "silakan datang" untuk kartu loket yang baru memanggil. */
    private static final int HIJAU_PANGGIL = Color.rgb(4, 120, 87);
    private static final int HIJAU_PANGGIL_LATAR = Color.rgb(220, 245, 232);

    private View kartuLoket(Loket loket, boolean besar) {
        FrameLayout kartu = new FrameLayout(this);
        boolean melayani = !loket.nomor.isEmpty();
        // Nomor yang baru dipanggil menunggu pemiliknya berjalan ke loket:
        // itu yang paling perlu dilihat pengunjung, jadi kartunya dibedakan.
        boolean dipanggil = melayani && "Dipanggil".equalsIgnoreCase(loket.status);
        // Kartu besar diberi ruang agar nama loket dan keterangan tidak
        // mepet tepi; garis tepi 2 dp pada kartu "dipanggil" ditambahkan agar
        // jaraknya sama dengan kartu tanpa garis. Kartu ringkas tetap rapat.
        int garis = dipanggil ? dp(2) : 0;
        if (besar) {
            kartu.setPadding(dp(8) + garis, dp(10) + garis, dp(8) + garis, dp(10) + garis);
        } else {
            kartu.setPadding(dp(4), dp(3), dp(4), dp(3));
        }
        kartu.setBackground(dipanggil
                ? roundedOutline(HIJAU_PANGGIL_LATAR, HIJAU_PANGGIL, dp(16), dp(2))
                : rounded(melayani ? LEMBUT : ABU_LEMBUT, dp(16)));

        String isi = melayani ? loket.nomor
                : "ISTIRAHAT".equals(loket.status) ? "Istirahat" : "Siap melayani";
        // Kartu ringkas setinggi 54 dp memuat nama, nomor, dan keadaannya.
        int maks = melayani ? (besar ? 40 : 16) : (besar ? 18 : 12);
        TextView nomor = text(isi, maks, melayani ? INK : MUTED, true);
        if (melayani) {
            nomor.setTypeface(huruf(800));
            nomor.setFontFeatureSettings("tnum");
        }
        nomor.setTag("nomor");
        pasangSatuBaris(nomor, 9, maks);
        nomor.setGravity(Gravity.CENTER);
        // Kotak nomor setinggi tulisannya, diletakkan tepat di tengah kartu
        // oleh FrameLayout. Selebar kartu dikurangi ruang yang sama di kiri
        // dan kanan, supaya pengukur huruf tahu lebar yang tersedia.
        FrameLayout.LayoutParams letakNomor = new FrameLayout.LayoutParams(-1, -2, Gravity.CENTER);
        kartu.addView(nomor, letakNomor);

        TextView nama = text(loket.nama, besar ? 15 : 11, MUTED, true);
        nama.setGravity(Gravity.CENTER);
        pasangSatuBaris(nama, 8, besar ? 15 : 11);
        kartu.addView(nama, new FrameLayout.LayoutParams(-1, -2,
                Gravity.TOP | Gravity.CENTER_HORIZONTAL));

        // Keadaan tiap kartu mengikuti yang sedang terjadi di loketnya:
        // Dipanggil, Dilayani, atau Ditunda (label dari server).
        String bawah = "";
        if (melayani) {
            String keadaan = loket.status.isEmpty() ? "" : loket.status;
            bawah = besar && !loket.layanan.isEmpty()
                    ? (keadaan.isEmpty() ? loket.layanan : keadaan + " · " + loket.layanan)
                    : keadaan;
        }
        if (!bawah.isEmpty()) {
            int ukuran = besar ? 13 : 9;
            boolean ditunda = "Ditunda".equalsIgnoreCase(loket.status);
            int warna = dipanggil ? HIJAU_PANGGIL : ditunda ? MUTED : UTAMA;
            TextView keterangan = text(bawah, ukuran, warna, dipanggil);
            keterangan.setGravity(Gravity.CENTER);
            if (besar) keterangan.setPadding(0, 0, 0, dp(2));
            pasangSatuBaris(keterangan, 8, ukuran);
            kartu.addView(keterangan, new FrameLayout.LayoutParams(-1, -2,
                    Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL));
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

    private boolean sorotAktif() {
        return !nomorSaya.isEmpty() && System.currentTimeMillis() < batasSorotMillis;
    }

    /** Lupakan ubin yang tampil; dipanggil saat panel bawah dipakai isi lain. */
    private void lepasDaftarMenunggu() {
        ubinTampil.clear();
        posisiUbinLama.clear();
        tandaMenunggu = "";
    }

    /**
     * Daftar baca-saja seluruh nomor yang masih menunggu pada hari ini.
     *
     * Animasinya: nomor yang dipanggil loket mengecil dan hilang lalu ubin
     * lain bergeser mengisi; halaman berganti dengan ubin berbalik satu per
     * satu seperti papan jadwal; nomor baru muncul dengan "pop"; nomor milik
     * pengunjung tablet ini memakai warna utama dan berdenyut sebentar.
     */
    private void tampilkanNomorMenunggu() {
        if (resultSlot == null || sedangMengeluarkan) return;
        // Langsung ke halaman yang memuat nomor milik pengunjung.
        if (sorotAktif() && !sorotDitunjukkan) {
            int letak = waitingQueueNumbers.indexOf(nomorSaya);
            if (letak >= 0) {
                waitingPage = letak / nomorPerHalaman();
                sorotDitunjukkan = true;
            }
        }
        int halaman = jumlahHalamanMenunggu();
        waitingPage = Math.min(waitingPage, halaman - 1);
        boolean halamanBerganti = waitingPage != halamanMenungguTerakhir;
        String tanda = TextUtils.join(",", waitingQueueNumbers) + "|"
                + TextUtils.join(",", nomorPrioritasMenunggu) + "|" + waitingPage
                + "|" + barisMenunggu + "|" + sorotAktif() + "|" + temaAktif;
        if (tanda.equals(tandaMenunggu) && resultSlot.getChildCount() > 0) return;

        // Nomor yang dipanggil keluar dulu, baru daftar disusun ulang.
        if (menungguPernahTampil && !halamanBerganti && !ubinTampil.isEmpty()) {
            List<View> keluar = new ArrayList<>();
            for (Map.Entry<String, View> ubin : ubinTampil.entrySet()) {
                if (!waitingQueueNumbers.contains(ubin.getKey())) keluar.add(ubin.getValue());
            }
            if (!keluar.isEmpty()) {
                posisiUbinLama.clear();
                for (Map.Entry<String, View> ubin : ubinTampil.entrySet()) {
                    int[] xy = new int[2];
                    ubin.getValue().getLocationOnScreen(xy);
                    posisiUbinLama.put(ubin.getKey(), xy);
                }
                sedangMengeluarkan = true;
                for (View v : keluar) {
                    v.animate().scaleX(0.5f).scaleY(0.5f).alpha(0f).setDuration(260)
                            .setInterpolator(new android.view.animation.AccelerateInterpolator())
                            .start();
                }
                handler.postDelayed(() -> {
                    sedangMengeluarkan = false;
                    tandaMenunggu = "";
                    if (!showingResult) tampilkanNomorMenunggu();
                }, 280);
                return;
            }
        }

        tandaMenunggu = tanda;
        resultSlot.removeAllViews();
        ubinTampil.clear();
        if (resultTitle != null) resultTitle.setText("Nomor menunggu");
        if (halamanBerganti) halamanMulaiMillis = System.currentTimeMillis();

        if (waitingQueueNumbers.isEmpty()) {
            menungguPernahTampil = true;
            nomorMenungguTerakhir.clear();
            halamanMenungguTerakhir = waitingPage;
            TextView kosong = text("Belum ada nomor yang menunggu.", 16, MUTED, false);
            kosong.setGravity(Gravity.CENTER);
            kosong.setPadding(dp(12), dp(8), dp(12), dp(8));
            resultSlot.addView(kosong, new FrameLayout.LayoutParams(-1, -1));
            return;
        }

        LinearLayout wadah = new LinearLayout(this);
        wadah.setOrientation(LinearLayout.VERTICAL);
        // Baris LinearLayout berbobot, bukan GridLayout: GridLayout yang
        // dibungkus wrap_content membagi lebar 0 ke kolom berbobot, sehingga
        // ubin nomor selebar nol dan daftarnya tampak kosong.
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        // Nomor mengisi dari ATAS: bila tidak penuh, ruang kosong ada di bawah.
        // Nomor pertama selalu di tempat yang sama, dan saat nomor dipanggil
        // hanya yang di bawahnya yang bergeser naik.
        page.setGravity(Gravity.TOP);
        page.setPadding(dp(2), dp(4), dp(2), dp(2));
        wadah.addView(page, new LinearLayout.LayoutParams(-1, 0, 1));

        boolean sorot = sorotAktif();
        // Jarak kamera tetap dipasang: animasi masuk gaya acak masih memutar
        // ubin, dan tanpa ini perspektifnya terlalu kuat.
        float kamera = 8000f * getResources().getDisplayMetrics().density;
        int awal = waitingPage * nomorPerHalaman();
        int akhir = Math.min(awal + nomorPerHalaman(), waitingQueueNumbers.size());
        List<View> ubinBaru = new ArrayList<>();
        int jumlahBarisHalaman = ((akhir - awal) + KOLOM_NOMOR_MENUNGGU - 1) / KOLOM_NOMOR_MENUNGGU;
        LinearLayout baris = null;
        for (int index = awal; index < akhir; index++) {
            if ((index - awal) % KOLOM_NOMOR_MENUNGGU == 0) {
                baris = new LinearLayout(this);
                baris.setOrientation(LinearLayout.HORIZONTAL);
                page.addView(baris, new LinearLayout.LayoutParams(-1, -2));
            }
            String isi = waitingQueueNumbers.get(index);
            boolean milikSaya = sorot && isi.equals(nomorSaya);
            boolean prioritasIni = nomorPrioritasMenunggu.contains(isi);
            TextView nomor = prioritasIni ? new NomorBerbintang(this) : new TextView(this);
            nomor.setText(isi);
            nomor.setTextSize(19 * uiScale);
            nomor.setTextColor(milikSaya ? TEKS_TOMBOL : INK);
            nomor.setTypeface(huruf(800));
            nomor.setFontFeatureSettings("tnum");
            nomor.setGravity(Gravity.CENTER);
            // Hampir datar: tebing tipis di dasar. Padding bawah menambah
            // tebal tebing agar angka tetap di tengah muka, bukan di tengah
            // seluruh ubin.
            nomor.setPadding(dp(4), dp(4), dp(4), dp(4) + dp(1));
            nomor.setBackground(ubinTimbul(milikSaya ? UTAMA
                    : prioritasIni ? Color.rgb(243, 232, 255) : LEMBUT, dp(16)));
            nomor.setCameraDistance(kamera);
            pasangSatuBaris(nomor, 10, 20);
            baris.addView(nomor, selNomorMenunggu());
            ubinTampil.put(isi, nomor);
            ubinBaru.add(nomor);
            int urutan = index - awal;
            boolean animasiMasuk = animasiNomorAktif && animasiSistemAktif()
                    && urutan < BATAS_NOMOR_ANIMASI
                    && (!menungguPernahTampil || halamanBerganti || ulangiAnimasiNomor);
            if (animasiMasuk) {
                animasiMasukNomor(nomor, urutan / KOLOM_NOMOR_MENUNGGU,
                        urutan % KOLOM_NOMOR_MENUNGGU, jumlahBarisHalaman);
            } else if (halamanBerganti && menungguPernahTampil) {
                // Halaman berganti: ubin muncul memudar satu per satu, tanpa
                // putaran 3D.
                nomor.setAlpha(0f);
                nomor.animate().alpha(1f).setStartDelay(35L * urutan)
                        .setDuration(240)
                        .setInterpolator(new android.view.animation.DecelerateInterpolator())
                        .start();
            } else if (menungguPernahTampil && !nomorMenungguTerakhir.contains(isi)) {
                // Nomor yang baru diambil muncul dengan "pop" kecil.
                nomor.setAlpha(0f);
                nomor.setScaleX(0.6f);
                nomor.setScaleY(0.6f);
                nomor.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(320)
                        .setInterpolator(new android.view.animation.OvershootInterpolator(2f))
                        .start();
            }
            if (milikSaya && !sorotDidenyutkan) {
                sorotDidenyutkan = true;
                android.animation.ObjectAnimator denyut =
                        android.animation.ObjectAnimator.ofPropertyValuesHolder(nomor,
                                android.animation.PropertyValuesHolder.ofFloat(
                                        View.SCALE_X, 1f, 1.08f),
                                android.animation.PropertyValuesHolder.ofFloat(
                                        View.SCALE_Y, 1f, 1.08f));
                denyut.setDuration(320);
                denyut.setRepeatCount(5);
                denyut.setRepeatMode(android.animation.ValueAnimator.REVERSE);
                denyut.setStartDelay(400);
                denyut.start();
            }
        }
        // Baris terakhir diisi sel kosong supaya ubinnya tetap selebar ubin lain.
        int sisa = (akhir - awal) % KOLOM_NOMOR_MENUNGGU;
        for (int i = 0; baris != null && sisa > 0 && i < KOLOM_NOMOR_MENUNGGU - sisa; i++) {
            baris.addView(new View(this), selNomorMenunggu());
        }

        // Titik halaman: titik aktif memanjang dan terisi sampai halaman berganti.
        if (halaman > 1) {
            LinearLayout titik = new LinearLayout(this);
            titik.setGravity(Gravity.CENTER);
            titik.setPadding(0, dp(6), 0, 0);
            for (int i = 0; i < halaman; i++) {
                boolean aktif = i == waitingPage;
                FrameLayout satu = new FrameLayout(this);
                satu.setBackground(rounded(GARIS, dp(3)));
                LinearLayout.LayoutParams ukuran =
                        new LinearLayout.LayoutParams(dp(aktif ? 28 : 6), dp(6));
                ukuran.leftMargin = dp(3);
                ukuran.rightMargin = dp(3);
                titik.addView(satu, ukuran);
                if (aktif) {
                    View isian = new View(this);
                    isian.setBackground(rounded(UTAMA, dp(3)));
                    satu.addView(isian, new FrameLayout.LayoutParams(-1, -1));
                    float sudah = Math.min(1f, (System.currentTimeMillis() - halamanMulaiMillis)
                            / (float) LAMA_HALAMAN_MENUNGGU_MS);
                    isian.setPivotX(0f);
                    isian.setScaleX(sudah);
                    isian.animate().scaleX(1f)
                            .setDuration(Math.max(0L, (long) ((1f - sudah)
                                    * LAMA_HALAMAN_MENUNGGU_MS)))
                            .setInterpolator(new android.view.animation.LinearInterpolator())
                            .start();
                }
            }
            wadah.addView(titik, new LinearLayout.LayoutParams(-1, -2));
        }
        resultSlot.addView(wadah, new FrameLayout.LayoutParams(-1, -1));

        // Sesudah nomor dipanggil: ubin yang tersisa bergeser dari tempat lamanya.
        if (!posisiUbinLama.isEmpty()) {
            Map<String, int[]> lama = new HashMap<>(posisiUbinLama);
            posisiUbinLama.clear();
            page.post(() -> {
                for (Map.Entry<String, View> ubin : ubinTampil.entrySet()) {
                    View v = ubin.getValue();
                    int[] dulu = lama.get(ubin.getKey());
                    if (dulu == null) {
                        if (v.getAlpha() == 1f) {
                            v.setAlpha(0f);
                            v.animate().alpha(1f).setDuration(300).start();
                        }
                        continue;
                    }
                    int[] kini = new int[2];
                    v.getLocationOnScreen(kini);
                    if (dulu[0] == kini[0] && dulu[1] == kini[1]) continue;
                    v.setTranslationX(dulu[0] - kini[0]);
                    v.setTranslationY(dulu[1] - kini[1]);
                    v.animate().translationX(0f).translationY(0f).setDuration(320)
                            .setInterpolator(new android.view.animation.DecelerateInterpolator())
                            .start();
                }
            });
        }
        halamanMenungguTerakhir = waitingPage;
        nomorMenungguTerakhir.clear();
        nomorMenungguTerakhir.addAll(waitingQueueNumbers);
        menungguPernahTampil = true;
        ulangiAnimasiNomor = false;
        jedaAwalNomorMs = 0L;
    }

    private boolean animasiSistemAktif() {
        return android.provider.Settings.Global.getFloat(getContentResolver(),
                android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f;
    }

    /**
     * Nomor menunggu masuk berurutan: baris demi baris, dan di dalam baris
     * tiap nomor selang pendek. Gayanya diacak dari gaya lama papan: papan
     * balik (berputar dari sumbu horizontal), papan balik tegak (sumbu
     * vertikal), dan pop (membesar dengan pantulan), dan berbeda dari nomor
     * sebelumnya. Total selang dibatasi supaya daftar panjang tidak lambat.
     */
    private void animasiMasukNomor(View nomor, int baris, int kolom, int jumlahBaris) {
        float skala = 1f;
        long maksJeda = (jumlahBaris - 1) * JEDA_BARIS_NOMOR_MS
                + (KOLOM_NOMOR_MENUNGGU - 1) * JEDA_KOLOM_NOMOR_MS;
        if (maksJeda > BATAS_TOTAL_JEDA_NOMOR_MS) {
            skala = BATAS_TOTAL_JEDA_NOMOR_MS / (float) maksJeda;
        }
        long jeda = jedaAwalNomorMs
                + (long) ((baris * JEDA_BARIS_NOMOR_MS + kolom * JEDA_KOLOM_NOMOR_MS) * skala);
        int gaya;
        do {
            gaya = acakArah.nextInt(3);
        } while (gaya == gayaNomorTerakhir);
        gayaNomorTerakhir = gaya;
        nomor.setAlpha(0.3f);
        android.view.ViewPropertyAnimator animasi = nomor.animate().alpha(1f);
        android.view.animation.Interpolator kurva =
                new android.view.animation.DecelerateInterpolator();
        long durasi = 360L;
        if (gaya == 0) {
            // Papan balik: berputar dari sumbu horizontal.
            nomor.setRotationX(90f);
            animasi.rotationX(0f);
        } else if (gaya == 1) {
            // Papan balik tegak: berputar dari sumbu vertikal.
            nomor.setRotationY(90f);
            animasi.rotationY(0f);
        } else {
            // Pop: membesar dengan pantulan.
            nomor.setAlpha(0f);
            nomor.setScaleX(0.6f);
            nomor.setScaleY(0.6f);
            animasi.scaleX(1f).scaleY(1f);
            kurva = new android.view.animation.OvershootInterpolator(2f);
            durasi = 420L;
        }
        animasi.setStartDelay(jeda).setDuration(durasi).setInterpolator(kurva).start();
    }

    private LinearLayout.LayoutParams selNomorMenunggu() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(52), 1f);
        params.setMargins(dp(3), dp(3), dp(3), dp(3));
        return params;
    }

    /** Warna kapsul tetap untuk tiap awalan, supaya A selalu biru, B selalu hijau. */
    private int[] warnaLayanan(String kunci) {
        int indeks = kunci.isEmpty() ? 0 : Character.toUpperCase(kunci.charAt(0)) - 'A';
        return WARNA_LAYANAN[Math.floorMod(indeks, WARNA_LAYANAN.length)];
    }

    private View buatKartuLayanan(Category item, int tinggiKartu) {
        return buatKartu(item.group ? "›" : awalanLayanan(item), item.name,
                item.group ? "Lihat pilihan layanan" : null,
                item.group ? new int[]{LEMBUT, INK} : warnaLayanan(awalanLayanan(item)), () -> {
                    if (item.group) {
                        path.add(item);
                        showCategories();
                    } else {
                        pendingCategory = item;
                        showConfirmation();
                    }
                }, tinggiKartu);
    }

    /**
     * Kartu layanan: latar lembut berwarna layanan, kode kecil di pojok
     * kiri atas, dan nama layanan besar di tengah kartu, satu baris. Kartu
     * yang pendek menaruh kode di kiri nama supaya keduanya tetap muat.
     * Ukuran huruf mengikuti tinggi kartu, sehingga tidak pernah perlu gulir.
     *
     * Teks diletakkan sebagai kotak yang ditengahkan oleh FrameLayout, bukan
     * lewat gravity teks: TextView satu baris tidak selalu menengahkan
     * tulisannya secara tegak.
     */
    private View buatKartu(String awalan, String label, String keterangan,
                           int[] warna, Runnable action, int tinggiKartu) {
        // Tinggi kartu dalam satuan dp anjungan (sudah termasuk skala layar).
        float tinggi = tinggiKartu > 0
                ? tinggiKartu / (getResources().getDisplayMetrics().density * uiScale) : 96f;
        boolean lega = tinggi >= 80f;
        int kodeSp = Math.round(Math.max(11f, Math.min(14f, tinggi * 0.13f)));
        int namaSp = Math.round(Math.max(12f, Math.min(22f, tinggi * (lega ? 0.22f : 0.26f))));
        boolean adaKeterangan = keterangan != null && tinggi >= 88f;

        FrameLayout card = new FrameLayout(this);
        card.setPadding(dp(8), dp(6), dp(8), dp(6));
        // Kontras tinggi tetap putih: tulisan hitam harus setajam mungkin.
        int latar = "kontras".equals(temaAktif) ? KARTU : campur(KARTU, warna[0], 0.45f);
        card.setBackground(latarKartu(latar));
        card.setElevation(dp(2));

        FrameLayout kapsul = new FrameLayout(this);
        kapsul.setBackground(rounded(warna[0], dp(8)));
        kapsul.setPadding(dp(8), dp(2), dp(8), dp(2));
        TextView kode = text(awalan, kodeSp, warna[1], true);
        kode.setTypeface(huruf(800));
        kode.setSingleLine(true);
        kode.setIncludeFontPadding(false);
        kapsul.addView(kode, new FrameLayout.LayoutParams(-2, -2, Gravity.CENTER));

        TextView nama = text(label, namaSp, INK, true);
        nama.setTypeface(huruf(800));
        pasangSatuBaris(nama, 9, namaSp);

        // Kartu kelompok (›) dan Kembali (‹): panah besar yang digambar di
        // sisi arahnya, bukan karakter kecil di kapsul kode.
        boolean panahKanan = "›".equals(awalan);
        if (panahKanan || "‹".equals(awalan)) {
            // Panah dan nama berdampingan: nama memakai SEMUA sisa lebar di
            // samping panah. Ruang kosong simetris di sisi seberang panah
            // dulu membuat nama di kartu sempit mengecil lalu terpotong.
            int ukuran = Math.round(Math.max(20f, Math.min(30f, tinggi * 0.30f))
                    * getResources().getDisplayMetrics().density * uiScale);
            TandaPanah panah = new TandaPanah(this, panahKanan, panahKanan ? UTAMA : warna[1]);
            LinearLayout tengah = new LinearLayout(this);
            tengah.setOrientation(LinearLayout.VERTICAL);
            tengah.setGravity(Gravity.CENTER_HORIZONTAL);
            nama.setGravity(Gravity.CENTER_HORIZONTAL);
            tengah.addView(nama, new LinearLayout.LayoutParams(-1, -2));
            if (adaKeterangan) {
                TextView ket = text(keterangan, 11, MUTED, false);
                ket.setGravity(Gravity.CENTER_HORIZONTAL);
                pasangSatuBaris(ket, 8, 11);
                tengah.addView(ket, new LinearLayout.LayoutParams(-1, -2));
            }
            LinearLayout baris = new LinearLayout(this);
            baris.setGravity(Gravity.CENTER_VERTICAL);
            LinearLayout.LayoutParams ukuranPanah = new LinearLayout.LayoutParams(ukuran, ukuran);
            LinearLayout.LayoutParams ukuranTengah = new LinearLayout.LayoutParams(0, -2, 1f);
            if (panahKanan) {
                baris.addView(tengah, ukuranTengah);
                ukuranPanah.leftMargin = dp(4);
                baris.addView(panah, ukuranPanah);
            } else {
                ukuranPanah.rightMargin = dp(4);
                baris.addView(panah, ukuranPanah);
                baris.addView(tengah, ukuranTengah);
            }
            card.addView(baris, new FrameLayout.LayoutParams(-1, -2, Gravity.CENTER));
            pasangEfekSentuh(card);
            card.setOnClickListener(v -> {
                v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
                action.run();
            });
            return card;
        }

        if (lega) {
            card.addView(kapsul, new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.START));
            LinearLayout tengah = new LinearLayout(this);
            tengah.setOrientation(LinearLayout.VERTICAL);
            tengah.setGravity(Gravity.CENTER_HORIZONTAL);
            nama.setGravity(Gravity.CENTER_HORIZONTAL);
            tengah.addView(nama, new LinearLayout.LayoutParams(-1, -2));
            if (adaKeterangan) {
                TextView ket = text(keterangan, 11, MUTED, false);
                ket.setGravity(Gravity.CENTER_HORIZONTAL);
                pasangSatuBaris(ket, 8, 11);
                tengah.addView(ket, new LinearLayout.LayoutParams(-1, -2));
            }
            // Ruang yang sama di atas dan bawah setinggi kapsul kode, supaya
            // nama tetap di tengah kartu tanpa menabrak kode di pojok.
            int ruang = Math.round(kodeSp * uiScale
                    * getResources().getDisplayMetrics().scaledDensity * 1.25f) + dp(6);
            tengah.setPadding(0, ruang, 0, ruang);
            card.addView(tengah, new FrameLayout.LayoutParams(-1, -2, Gravity.CENTER));
        } else {
            LinearLayout baris = new LinearLayout(this);
            baris.setGravity(Gravity.CENTER_VERTICAL);
            baris.addView(kapsul, new LinearLayout.LayoutParams(-2, -2));
            nama.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
            LinearLayout.LayoutParams namaParams = new LinearLayout.LayoutParams(0, -2, 1f);
            namaParams.leftMargin = dp(8);
            baris.addView(nama, namaParams);
            card.addView(baris, new FrameLayout.LayoutParams(-1, -2, Gravity.CENTER));
        }
        pasangEfekSentuh(card);
        card.setOnClickListener(v -> {
            v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
            action.run();
        });
        return card;
    }

    private StateListDrawable latarKartu(int latar) {
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_pressed},
                roundedOutline(LEMBUT, UTAMA, dp(20), dp(2)));
        states.addState(new int[]{}, roundedOutline(latar, GARIS, dp(20), dp(1)));
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
        TextView info = null;
        if (!pendingCategory.info.trim().isEmpty()) {
            info = text(pendingCategory.info.trim(), 13, MUTED, false);
            info.setMaxLines(2);
            info.setEllipsize(TextUtils.TruncateAt.END);
            namaLayanan.addView(info);
        }
        identity.addView(namaLayanan, new LinearLayout.LayoutParams(0, -2, 1));
        page.addView(identity, new LinearLayout.LayoutParams(-1, -2));

        // Penanda saja: kotaknya dicentang di menu awal.
        if (prioritasAktifServer && prioritasDipilih) {
            TextView tandaPrioritas = text(
                    "★ Prioritas: lansia / disabilitas / ibu hamil", 14, Color.rgb(120, 60, 170), true);
            tandaPrioritas.setGravity(Gravity.CENTER);
            tandaPrioritas.setPadding(dp(14), dp(8), dp(14), dp(8));
            tandaPrioritas.setBackground(roundedOutline(
                    Color.rgb(243, 232, 255), Color.rgb(216, 180, 254), dp(18), dp(1)));
            LinearLayout.LayoutParams tandaParams = new LinearLayout.LayoutParams(-1, -2);
            tandaParams.topMargin = dp(10);
            page.addView(tandaPrioritas, tandaParams);
        }

        LinearLayout actions = new LinearLayout(this);
        actions.setGravity(Gravity.CENTER);
        actions.setPadding(0, dp(12), 0, 0);
        Button cancel = actionButton("Kembali", false);
        cancel.setOnClickListener(v -> {
            // Selama permintaan berjalan nomornya mungkin sudah terbit di
            // server; membatalkan sekarang meninggalkan nomor tanpa tiket.
            if (requestInFlight) return;
            v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
            v.setEnabled(false);
            showingConfirmation = false;
            pendingCategory = null;
            pendingRequestId = null;
            keluarDariKonfirmasi(null);
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
        TextView keterangan = info;
        contentSlot.post(() -> pasKanKonfirmasi(
                page, langkah, keterangan, identity, actions, cancel, yes));
        page.setAlpha(0f);
        page.setTranslationX(dp(24));
        page.animate().alpha(1f).translationX(0f).setDuration(240)
                .setInterpolator(new android.view.animation.DecelerateInterpolator()).start();
        handler.removeCallbacks(confirmTimeout);
        handler.postDelayed(confirmTimeout, 15000);
        batasKonfirmasiMillis = System.currentTimeMillis() + 15000;
        perbaruiHitungMundurKonfirmasi();
    }

    /**
     * Halaman konfirmasi harus muat di panel tengah. Panel itu bisa pendek
     * karena iklan dan baris loket ikut berbagi tinggi layar; tanpa ini
     * isinya meluap dan tombol Kembali / Ya terpangkas di tepi bawah.
     * Yang paling tidak penting dilepas lebih dulu.
     */
    private void pasKanKonfirmasi(LinearLayout page, View langkah, View info,
                                  View identity, View actions, Button... tombol) {
        int tinggi = contentSlot.getHeight();
        if (tinggi <= 0 || page.getParent() != contentSlot) return;
        int lebar = contentSlot.getWidth();
        if (muatDi(page, lebar, tinggi)) return;
        langkah.setVisibility(View.GONE);
        if (muatDi(page, lebar, tinggi)) return;
        if (info != null) info.setVisibility(View.GONE);
        if (muatDi(page, lebar, tinggi)) return;
        page.setPadding(dp(4), 0, dp(4), 0);
        identity.setPadding(dp(10), dp(6), dp(10), dp(6));
        actions.setPadding(0, dp(6), 0, 0);
        if (muatDi(page, lebar, tinggi)) return;
        // Terakhir: tombol memendek, tetapi tidak di bawah sasaran sentuh wajar.
        int lebih = page.getMeasuredHeight() - tinggi;
        for (Button b : tombol) {
            ViewGroup.LayoutParams params = b.getLayoutParams();
            params.height = Math.max(dp(44), params.height - lebih);
            b.setLayoutParams(params);
        }
    }

    /** Tinggi yang dibutuhkan `view` pada lebar ini muat dalam `tinggi`. */
    private boolean muatDi(View view, int lebar, int tinggi) {
        view.measure(
                View.MeasureSpec.makeMeasureSpec(lebar, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED));
        return view.getMeasuredHeight() <= tinggi;
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
            showingConfirmation = false;
            pendingCategory = null;
            pendingRequestId = null;
            prioritasDipilih = false;
            // Pengunjung yang diam selama ini kemungkinan sudah pergi; orang
            // berikutnya harus mendapati menu awal, bukan sub-menu pilihan
            // orang lain. Tombol Kembali tetap mundur satu tingkat.
            path.clear();
            keluarDariKonfirmasi("Pilihan dibatalkan karena tidak ada aktivitas.");
        }
    };

    /** Layar konfirmasi meluncur keluar ke kanan, lalu menu layanan tampil. */
    private void keluarDariKonfirmasi(String pesan) {
        handler.removeCallbacks(confirmTimeout);
        handler.removeCallbacks(batasUlangi);
        handler.removeCallbacks(cobaTiketLagi);
        View halaman = contentSlot == null ? null : contentSlot.getChildAt(0);
        Runnable kembali = () -> {
            if (showingConfirmation || showingResult || requestInFlight) return;
            showCategories();
            if (pesan != null) tampilkanPesanSementara(pesan, "tunggu");
        };
        if (halaman == null) {
            kembali.run();
            return;
        }
        halaman.animate().alpha(0f).translationX(dp(28)).setDuration(180)
                .setInterpolator(new android.view.animation.AccelerateInterpolator())
                .withEndAction(kembali).start();
    }

    /** Percobaan ulang senyap sebelum tombol Ulangi ditampilkan. */
    private static final int COBA_TIKET_SENYAP = 2;
    private static final long JEDA_COBA_TIKET_MS = 1500L;
    /**
     * Lama layar Ulangi menunggu sentuhan. Sesudah itu tablet mencoba sekali
     * lagi; bila tetap gagal, pilihan dibatalkan dan menu awal kembali.
     * Tanpa batas ini layar Ulangi bertahan selamanya, dan pengunjung
     * berikutnya yang menyentuhnya menerima nomor milik orang sebelumnya
     * (request_id yang sama) untuk layanan yang tidak ia pilih.
     */
    private static final long BATAS_ULANGI_MS = 30_000L;
    private int gagalTiketBeruntun;
    private boolean percobaanTiketTerakhir;

    private final Runnable cobaTiketLagi = () -> kirimPermintaanTiket();

    private final Runnable batasUlangi = () -> {
        if (!showingConfirmation || requestInFlight || pendingCategory == null) return;
        percobaanTiketTerakhir = true;
        kirimPermintaanTiket();
    };

    /** Sentuhan pengunjung pada "Ya, ambil nomor" atau "Ulangi". */
    private void issueTicket() {
        if (pendingCategory == null || requestInFlight) return;
        gagalTiketBeruntun = 0;
        percobaanTiketTerakhir = false;
        kirimPermintaanTiket();
    }

    /**
     * Kotak "Saya lansia / disabilitas / ibu hamil", besar agar mudah
     * disentuh. Keadaannya (`prioritasDipilih`) dibawa ke tiket yang diambil
     * sesudahnya dan dikosongkan setiap tiket terbit atau pengunjung pergi.
     */
    private Button buatKotakPrioritas() {
        Button prioritas = new Button(this);
        prioritas.setAllCaps(false);
        prioritas.setTypeface(huruf(800));
        prioritas.setStateListAnimator(null);
        prioritas.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        prioritas.setMinHeight(0);
        prioritas.setMinimumHeight(0);
        prioritas.setPadding(dp(16), dp(4), dp(16), dp(4));
        pasangSatuBaris(prioritas, 9, 14);
        Runnable gambar = () -> {
            prioritas.setText((prioritasDipilih ? "☑  " : "☐  ")
                    + "Saya lansia / disabilitas / ibu hamil");
            // Prioritas satu warna di semua layar: ungu lembut saat dicentang.
            prioritas.setTextColor(prioritasDipilih ? Color.rgb(120, 60, 170) : INK);
            prioritas.setBackground(prioritasDipilih
                    ? roundedOutline(Color.rgb(243, 232, 255), Color.rgb(216, 180, 254), dp(18), dp(2))
                    : roundedOutline(KARTU, GARIS, dp(18), dp(2)));
        };
        gambar.run();
        prioritas.setOnClickListener(v -> {
            if (requestInFlight) return;
            v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
            prioritasDipilih = !prioritasDipilih;
            gambar.run();
        });
        return prioritas;
    }

    /**
     * Isi permintaan tiket. `priority` hanya dikirim bila dicentang, jadi
     * server lama maupun yang menonaktifkan pilihan ini tidak melihat bidang
     * baru pada permintaan biasa.
     */
    private org.json.JSONObject bodiTiket() {
        JSONObjectBuilder isi = new JSONObjectBuilder()
                .put("category_id", pendingCategory.id)
                .put("request_id", pendingRequestId);
        if (prioritasAktifServer && prioritasDipilih) isi.put("priority", true);
        return isi.build();
    }

    private void kirimPermintaanTiket() {
        if (pendingCategory == null || requestInFlight) return;
        handler.removeCallbacks(confirmTimeout);
        handler.removeCallbacks(batasUlangi);
        handler.removeCallbacks(cobaTiketLagi);
        requestInFlight = true;
        if (pendingRequestId == null) pendingRequestId = UUID.randomUUID().toString();
        setHint("Mengambil nomor…", "tunggu");
        request(penerbit, "POST", "/v1/kiosk/tickets",
                bodiTiket(),
                json -> {
                    // Seluruh jawaban dibaca dulu. Bila ada yang tidak
                    // terbaca, pilihan dan request_id masih utuh sehingga
                    // Ulangi meminta nomor yang SAMA, bukan nomor baru.
                    JSONObject ticket = json.getJSONObject("data");
                    String number = ticket.getString("queue_number");
                    int cooldownSeconds = Math.max(
                            0, ticket.optInt("cooldown_seconds", 10));
                    JSONArray lines = ticket.getJSONArray("ticket_lines");
                    List<String> receipt = new ArrayList<>();
                    for (int i = 0; i < lines.length(); i++) receipt.add(lines.getString(i));
                    JSONObject layout = ticket.optJSONObject("ticket_layout");
                    JSONObject raster = ticket.optJSONObject("ticket_raster");
                    requestInFlight = false;
                    gagalTiketBeruntun = 0;
                    percobaanTiketTerakhir = false;
                    Category issued = pendingCategory;
                    pendingCategory = null;
                    pendingRequestId = null;
                    prioritasDipilih = false;
                    readyAtMillis = System.currentTimeMillis() + cooldownSeconds * 1000L;
                    nomorSaya = number;
                    batasSorotMillis = System.currentTimeMillis() + LAMA_HASIL_MS + 10_000L;
                    sorotDidenyutkan = false;
                    sorotDitunjukkan = false;
                    showResult(number, issued == null ? "" : issued.name);
                    updateAvailability();
                    cetakTiketPengunjung(number, receipt, layout, raster);
                    loadDisplay();
                },
                message -> {
                    requestInFlight = false;
                    if (!showingConfirmation || pendingCategory == null) return;
                    if (percobaanTiketTerakhir) {
                        batalkanTiketGagal();
                        return;
                    }
                    if (gagalTiketBeruntun < COBA_TIKET_SENYAP) {
                        // Gangguan jaringan sesaat: coba lagi dengan
                        // request_id yang sama sebelum pengunjung diminta
                        // menyentuh Ulangi. Server memberi nomor yang sama
                        // bila permintaan sebelumnya ternyata sudah sampai.
                        gagalTiketBeruntun++;
                        setHint("Menghubungi server lagi…", "tunggu");
                        handler.postDelayed(cobaTiketLagi, JEDA_COBA_TIKET_MS);
                        return;
                    }
                    setHint("Nomor belum dapat dipastikan. Sentuh ulang untuk mencoba lagi.", "salah");
                    showRetry();
                },
                (kode, detail) -> {
                    // Server menolak dengan alasan yang jelas; tombol Ulangi
                    // hanya akan mendapat jawaban yang sama. Tampilkan
                    // alasannya, lalu kembali ke daftar layanan yang segar.
                    requestInFlight = false;
                    gagalTiketBeruntun = 0;
                    percobaanTiketTerakhir = false;
                    showingConfirmation = false;
                    pendingCategory = null;
                    pendingRequestId = null;
                    prioritasDipilih = false;
                    showIdleResult();
                    keluarDariKonfirmasi(null);
                    tampilkanPesanSementara(detail, "salah");
                    loadCategories(true);
                    loadDisplay();
                });
    }

    /** Percobaan terakhir sesudah layar Ulangi dibiarkan juga gagal. */
    private void batalkanTiketGagal() {
        gagalTiketBeruntun = 0;
        percobaanTiketTerakhir = false;
        showingConfirmation = false;
        pendingCategory = null;
        pendingRequestId = null;
        prioritasDipilih = false;
        // Pengunjung kemungkinan sudah pergi; orang berikutnya mendapati
        // menu awal, bukan sub-menu pilihan orang lain.
        path.clear();
        showIdleResult();
        keluarDariKonfirmasi("Permintaan tiket dibatalkan karena server tidak merespons.");
    }

    private void showRetry() {
        kembalikanPanelHasil();
        if (resultTitle != null) resultTitle.setText("Permintaan tiket belum selesai");
        lepasDaftarMenunggu();
        resultSlot.removeAllViews();
        LinearLayout retry = new LinearLayout(this);
        retry.setGravity(Gravity.CENTER);
        Button button = actionButton("Ulangi permintaan tiket", true);
        button.setOnClickListener(v -> issueTicket());
        retry.addView(button, new LinearLayout.LayoutParams(-1, dp(64)));
        resultSlot.addView(retry, new FrameLayout.LayoutParams(-1, -1));
        handler.removeCallbacks(batasUlangi);
        handler.postDelayed(batasUlangi, BATAS_ULANGI_MS);
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
        kolomHasil = result;
        tombolCetakUlang = null;
        LinearLayout tiket = new LinearLayout(this);
        tiket.setOrientation(LinearLayout.VERTICAL);
        tiket.setGravity(Gravity.CENTER);
        tiket.setPadding(dp(12), dp(10), dp(12), dp(10));
        tiket.setBackground(rounded(KARTU, dp(22)));
        TextView serviceView = text(testTicket ? "Contoh tiket" : service, 14, UTAMA, true);
        serviceView.setGravity(Gravity.CENTER);
        pasangSatuBaris(serviceView, 9, 14);
        tiket.addView(serviceView, new LinearLayout.LayoutParams(-1, -2));
        TextView numberView = text(number, 56, INK, true);
        numberView.setTypeface(huruf(800));
        numberView.setFontFeatureSettings("tnum");
        numberView.setGravity(Gravity.CENTER);
        pasangSatuBaris(numberView, 24, 60);
        tiket.addView(numberView, new LinearLayout.LayoutParams(-1, dp(66)));
        LinearLayout.LayoutParams tiketParams = new LinearLayout.LayoutParams(-1, -2);
        tiketParams.leftMargin = dp(28);
        tiketParams.rightMargin = dp(28);
        result.addView(tiket, tiketParams);
        LinearLayout ambilBaris = new LinearLayout(this);
        ambilBaris.setGravity(Gravity.CENTER);
        ambilBaris.setPadding(0, dp(8), 0, dp(6));
        TandaCentang centang = new TandaCentang(this, GREEN);
        ambilBaris.addView(centang, new LinearLayout.LayoutParams(dp(22), dp(22)));
        TextView ambil = text("Silakan ambil tiket Anda", 14, Color.argb(225, 255, 255, 255), true);
        ambil.setPadding(dp(8), 0, 0, 0);
        ambilBaris.addView(ambil);
        result.addView(ambilBaris);
        FrameLayout jalur = new FrameLayout(this);
        jalur.setBackground(rounded(UTAMA, dp(4)));
        View isiJalur = new View(this);
        isiJalur.setBackground(rounded(EMAS, dp(4)));
        jalur.addView(isiJalur, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout.LayoutParams jalurParams = new LinearLayout.LayoutParams(dp(160), dp(5));
        jalurParams.gravity = Gravity.CENTER;
        result.addView(jalur, jalurParams);
        lepasDaftarMenunggu();
        resultSlot.removeAllViews();
        resultSlot.addView(result, new FrameLayout.LayoutParams(-1, -1));
        tiket.setAlpha(0f);
        tiket.setTranslationY(dp(36));
        tiket.animate().alpha(1f).translationY(0f).setDuration(420)
                .setInterpolator(new android.view.animation.OvershootInterpolator(1.1f)).start();
        centang.gambar(180L);
        isiJalur.setPivotX(0f);
        isiJalur.animate().scaleX(0f).setDuration(LAMA_HASIL_MS)
                .setInterpolator(new android.view.animation.LinearInterpolator()).start();
        setHint("Nomor sudah terbit. Tiket sedang dicetak…", "hasil");
        handler.removeCallbacks(resultTimeout);
        handler.postDelayed(resultTimeout, LAMA_HASIL_MS);
    }

    /** Kolom hasil yang sedang tampil; tombol Cetak ulang ditambahkan ke sini bila cetak gagal. */
    private LinearLayout kolomHasil;
    private View tombolCetakUlang;
    private static final long LAMA_HASIL_GAGAL_CETAK_MS = 45_000L;

    /**
     * Cetak tiket pengunjung. Bila gagal (kertas habis, kertas macet, kabel
     * lepas), nomor tetap sah: pengunjung diberi saran dan tombol Cetak ulang,
     * dan layar hasil bertahan lebih lama supaya ia sempat mencatat nomornya.
     */
    private void cetakTiketPengunjung(String number, List<String> receipt,
                                      JSONObject layout, JSONObject raster) {
        UsbEscPosPrinter.print(this, number, receipt, layout, raster, message -> {
            boolean printed = message.contains("tercetak");
            reportPrinter(printed, message);
            if (!showingResult || hint == null) return;
            if (printed) {
                setHint(message, "hasil");
                if (tombolCetakUlang != null && kolomHasil != null) {
                    kolomHasil.removeView(tombolCetakUlang);
                    tombolCetakUlang = null;
                }
                return;
            }
            setHint("Tiket belum tercetak (mungkin kertas habis). Sentuh Cetak ulang, "
                    + "atau catat nomor Anda dan sampaikan ke petugas.", "gagal");
            if (kolomHasil != null && tombolCetakUlang == null) {
                Button ulang = actionButton("Cetak ulang tiket", true);
                ulang.setOnClickListener(v -> {
                    v.setEnabled(false);
                    setHint("Mencetak ulang tiket…", "tunggu");
                    cetakTiketPengunjung(number, receipt, layout, raster);
                    handler.postDelayed(() -> v.setEnabled(true), 3000);
                });
                tombolCetakUlang = ulang;
                kolomHasil.addView(ulang, new LinearLayout.LayoutParams(-1, dp(56)));
            }
            handler.removeCallbacks(resultTimeout);
            handler.postDelayed(resultTimeout, LAMA_HASIL_GAGAL_CETAK_MS);
        });
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
        if (System.currentTimeMillis() < pesanSementaraSampai) {
            setHint(pesanSementara, nadaSementara);
            return;
        }
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

    private void tampilkanPesanSementara(String pesan, String nada) {
        pesanSementara = pesan;
        nadaSementara = nada;
        pesanSementaraSampai = System.currentTimeMillis() + LAMA_PESAN_SEMENTARA_MS;
        setHint(pesan, nada);
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
        if ("ajak".equals(tone)) {
            mulaiKilauAjakan();
        } else {
            hentikanKilauAjakan();
        }
    }

    /**
     * Petunjuk "Sentuh jenis layanan..." diam, lalu sesekali disapu pita
     * cahaya dengan jeda acak. Gerak tanpa henti melelahkan mata dan lama-lama
     * tidak diperhatikan; kilau yang jarang dan tak terduga justru menarik
     * pandangan. Berhenti begitu ada yang memilih layanan. Warnanya dipilih
     * per tablet di Pengaturan (WARNA_KILAU), termasuk mematikannya.
     */
    private static final long JEDA_KILAU_MIN_MS = 8_000L;
    private static final long JEDA_KILAU_MAX_MS = 20_000L;
    private static final long LAMA_SAPUAN_KILAU_MS = 3_600L;
    private final java.util.Random acakKilau = new java.util.Random();
    private boolean kilauAjakanAktif;
    private KilauDrawable kilauAjakan;
    private android.animation.ValueAnimator sapuanKilau;

    private final Runnable kilauAjakanSekali = new Runnable() {
        @Override
        public void run() {
            if (!kilauAjakanAktif || hint == null) return;
            sapukanKilau();
            handler.postDelayed(this, jedaKilauAcak());
        }
    };

    private long jedaKilauAcak() {
        return JEDA_KILAU_MIN_MS
                + (long) (acakKilau.nextDouble() * (JEDA_KILAU_MAX_MS - JEDA_KILAU_MIN_MS));
    }

    /** Satu sapuan kiri ke kanan; tidak terjadi apa-apa bila kilau dimatikan. */
    private void sapukanKilau() {
        sapukanKilau(warnaKilau());
    }

    private void sapukanKilau(Integer warna) {
        if (warna == null || hint == null) return;
        if (kilauAjakan == null || hint.getForeground() != kilauAjakan) {
            kilauAjakan = new KilauDrawable(dp(24));
            hint.setForeground(kilauAjakan);
        }
        kilauAjakan.aturWarna(warna);
        if (sapuanKilau != null) sapuanKilau.cancel();
        KilauDrawable sasaran = kilauAjakan;
        sapuanKilau = android.animation.ValueAnimator.ofFloat(0f, 1f);
        sapuanKilau.setDuration(LAMA_SAPUAN_KILAU_MS);
        sapuanKilau.setInterpolator(
                new android.view.animation.AccelerateDecelerateInterpolator());
        sapuanKilau.addUpdateListener(a -> sasaran.aturPosisi((float) a.getAnimatedValue()));
        sapuanKilau.addListener(new android.animation.AnimatorListenerAdapter() {
            @Override
            public void onAnimationEnd(android.animation.Animator animasi) {
                sasaran.aturPosisi(-1f);
            }
        });
        sapuanKilau.start();
    }

    /** Warna kilau tablet ini, atau null bila dimatikan. */
    private Integer warnaKilau() {
        return warnaKilau(preferences == null ? KILAU_TEMA
                : preferences.getString(WARNA_KILAU, KILAU_TEMA));
    }

    private Integer warnaKilau(String pilihan) {
        if (pilihan.startsWith("#")) {
            // Warna bebas pilihan petugas; dijaga cukup terang agar sapuannya terlihat.
            try {
                float[] hsv = new float[3];
                Color.colorToHSV(Color.parseColor(pilihan), hsv);
                hsv[2] = Math.max(hsv[2], NILAI_MINIMUM_KILAU);
                return Color.HSVToColor(hsv);
            } catch (IllegalArgumentException e) {
                return EMAS;
            }
        }
        switch (pilihan) {
            case "mati":
                return null;
            case "putih":
                return Color.WHITE;
            case "emas":
                return Color.rgb(251, 191, 36);
            case "biru":
                return Color.rgb(96, 165, 250);
            case "hijau":
                return Color.rgb(52, 211, 153);
            case "merah":
                return Color.rgb(248, 113, 113);
            case "ungu":
                return Color.rgb(167, 139, 250);
            default:
                return EMAS;  // ikut tema
        }
    }

    private void mulaiKilauAjakan() {
        // Dipanggil tiap detik lewat updateAvailability; jadwal yang sudah
        // berjalan dibiarkan.
        if (kilauAjakanAktif) return;
        kilauAjakanAktif = true;
        handler.postDelayed(kilauAjakanSekali, jedaKilauAcak());
    }

    private void hentikanKilauAjakan() {
        kilauAjakanAktif = false;
        handler.removeCallbacks(kilauAjakanSekali);
        if (sapuanKilau != null) {
            sapuanKilau.cancel();
            sapuanKilau = null;
        }
        if (kilauAjakan != null) kilauAjakan.aturPosisi(-1f);
    }


    // =================================================================
    // Cetak ulang tiket atas permintaan petugas
    // =================================================================

    private boolean cetakUlangDiminta;

    /**
     * Tanya server tiap beberapa detik apakah petugas meminta tiket dicetak
     * ulang di tablet ini (mis. sesudah prioritas dicabut). Server hanya
     * mengirim tiap perintah sekali, jadi tidak ada cetak ganda; hasilnya
     * dilaporkan balik. Tidak menyentuh layar pengunjung.
     */
    private final Runnable pollingCetakUlang = new Runnable() {
        @Override
        public void run() {
            handler.postDelayed(this, SELANG_CETAK_ULANG_MS);
            if (!hasServerConfig() || cetakUlangDiminta) return;
            cetakUlangDiminta = true;
            request(pemanggil, "GET", "/v1/kiosk/cetak-ulang", null, json -> {
                cetakUlangDiminta = false;
                JSONArray tugas = json.getJSONObject("data").optJSONArray("jobs");
                if (tugas == null) return;
                for (int i = 0; i < tugas.length(); i++) {
                    JSONObject tugasIni = tugas.optJSONObject(i);
                    if (tugasIni != null) cetakUlangTiket(tugasIni);
                }
            }, message -> cetakUlangDiminta = false);
        }
    };

    private void cetakUlangTiket(JSONObject tugas) {
        final long id = tugas.optLong("id", -1);
        if (id < 0) return;
        String nomor = tugas.optString("queue_number", "");
        List<String> baris = new ArrayList<>();
        JSONArray teks = tugas.optJSONArray("ticket_lines");
        if (teks != null) {
            for (int i = 0; i < teks.length(); i++) baris.add(teks.optString(i));
        }
        tampilkanBannerCetakUlang(nomor);
        UsbEscPosPrinter.print(this, nomor, baris,
                tugas.optJSONObject("ticket_layout"), tugas.optJSONObject("ticket_raster"),
                message -> {
                    boolean tercetak = message.contains("tercetak");
                    handler.post(() -> hasilBannerCetakUlang(nomor, tercetak));
                    try {
                        JSONObject hasil = new JSONObject()
                                .put("ok", tercetak)
                                .put("message", message.length() > 190
                                        ? message.substring(0, 190) : message);
                        request(pemanggil, "POST", "/v1/kiosk/cetak-ulang/" + id + "/hasil",
                                hasil, json -> { }, error -> { });
                    } catch (Exception ignored) {
                        // Laporan hasil hanya keterangan bagi petugas.
                    }
                });
    }

    /**
     * Pita "Sedang mencetak ulang tiket ..." di atas layar. Tidak menutup
     * layanan di bawahnya dan tidak menangkap sentuhan, sehingga pengunjung
     * lain tetap bisa memilih layanan sementara tiket dicetak ulang.
     */
    private void tampilkanBannerCetakUlang(String nomor) {
        tutupBannerCetakUlang();
        LinearLayout isi = new LinearLayout(this);
        isi.setOrientation(LinearLayout.HORIZONTAL);
        isi.setGravity(Gravity.CENTER_VERTICAL);
        isi.setPadding(dp(20), dp(12), dp(20), dp(12));
        isi.setBackground(rounded(Color.argb(240, 30, 41, 59), dp(18)));
        android.widget.ProgressBar putar = new android.widget.ProgressBar(
                this, null, android.R.attr.progressBarStyleSmall);
        putar.setIndeterminate(true);
        putarBannerCetakUlang = putar;
        isi.addView(putar, new LinearLayout.LayoutParams(dp(24), dp(24)));
        TextView teks = text(
                nomor.isEmpty() ? "Sedang mencetak ulang tiket…"
                        : "Sedang mencetak ulang tiket " + nomor + "…",
                16, Color.WHITE, true);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
        lp.leftMargin = dp(12);
        isi.addView(teks, lp);
        teksBannerCetakUlang = teks;
        int lebar = Math.min(getResources().getDisplayMetrics().widthPixels - dp(32), dp(520));
        android.widget.PopupWindow jendela = new android.widget.PopupWindow(
                isi, lebar, ViewGroup.LayoutParams.WRAP_CONTENT);
        jendela.setTouchable(false);
        jendela.setFocusable(false);
        bannerCetakUlang = jendela;
        View decor = getWindow().getDecorView();
        decor.post(() -> {
            if (bannerCetakUlang != jendela || isFinishing()) return;
            try {
                jendela.showAtLocation(decor, Gravity.TOP | Gravity.CENTER_HORIZONTAL, 0, dp(24));
            } catch (RuntimeException ignored) {
                // Jendela belum siap; tiket tetap dicetak, hanya pitanya yang tidak tampil.
            }
        });
    }

    /** Ganti isi pita dengan hasil cetak, lalu tutup sesudah beberapa detik. */
    private void hasilBannerCetakUlang(String nomor, boolean tercetak) {
        android.widget.PopupWindow jendela = bannerCetakUlang;
        if (jendela == null || teksBannerCetakUlang == null) return;
        if (putarBannerCetakUlang != null) putarBannerCetakUlang.setVisibility(View.GONE);
        teksBannerCetakUlang.setText(tercetak
                ? "Tiket " + nomor + " sudah dicetak ulang"
                : "Tiket " + nomor + " tidak dapat dicetak. Mohon hubungi petugas.");
        View latar = (View) teksBannerCetakUlang.getParent();
        latar.setBackground(rounded(tercetak
                ? Color.argb(240, 4, 120, 87) : Color.argb(240, 180, 83, 9), dp(18)));
        handler.postDelayed(() -> {
            if (bannerCetakUlang == jendela) tutupBannerCetakUlang();
        }, LAMA_BANNER_CETAK_ULANG_MS);
    }

    private void tutupBannerCetakUlang() {
        android.widget.PopupWindow jendela = bannerCetakUlang;
        bannerCetakUlang = null;
        teksBannerCetakUlang = null;
        putarBannerCetakUlang = null;
        if (jendela == null) return;
        try {
            jendela.dismiss();
        } catch (RuntimeException ignored) {
            // Sudah tertutup.
        }
    }

    // =================================================================
    // Suara panggilan
    // =================================================================

    private final Runnable pollingPanggilan = new Runnable() {
        @Override
        public void run() {
            handler.postDelayed(this, SELANG_PANGGILAN_MS);
            if (!suaraPanggilan || !hasServerConfig()) {
                // Dinyalakan lagi nanti: mulai dari panggilan terbaru saat
                // itu, bukan mengucapkan semua yang lewat selama mati.
                panggilanTerakhir = null;
                return;
            }
            if (panggilanDiminta) return;
            panggilanDiminta = true;
            final boolean pertama = panggilanTerakhir == null;
            String path = pertama ? "/v1/kiosk/calls"
                    : "/v1/kiosk/calls?after=" + panggilanTerakhir;
            request(pemanggil, "GET", path, null, json -> {
                panggilanDiminta = false;
                JSONObject isi = json.getJSONObject("data");
                panggilanTerakhir = isi.optLong("last_id",
                        panggilanTerakhir == null ? 0 : panggilanTerakhir);
                if (pertama || !suaraPanggilan) return;
                JSONArray calls = isi.optJSONArray("calls");
                if (calls == null) return;
                long diterima = System.currentTimeMillis();
                for (int i = 0; i < calls.length(); i++) {
                    JSONObject call = calls.optJSONObject(i);
                    if (call == null) continue;
                    call.put("_diterima_ms", diterima);
                    antreanUcapan.add(call);
                }
                while (antreanUcapan.size() > MAKS_ANTREAN_UCAPAN) antreanUcapan.poll();
                ucapkanBerikutnya();
            }, message -> panggilanDiminta = false);
        }
    };

    private void aturSuaraPanggilan(boolean aktif) {
        if (aktif == suaraPanggilan) return;
        suaraPanggilan = aktif;
        if (aktif) {
            siapkanSuara();
            return;
        }
        antreanUcapan.clear();
        if (tts != null) tts.stop();
        lepasPemutarKlip();
        selesaiMengumumkan(-1);
    }

    /** TTS dan nada baru disiapkan saat anjungan ini pertama kali dipilih bersuara. */
    private void siapkanSuara() {
        if (nada == null) {
            try {
                nada = new ToneGenerator(AudioManager.STREAM_MUSIC, 90);
            } catch (RuntimeException e) {
                nada = null;  // perangkat tanpa keluaran suara
            }
        }
        if (tts != null) return;
        tts = new TextToSpeech(this, status -> {
            ttsDiperiksa = true;
            if (status == TextToSpeech.SUCCESS) {
                int hasil = tts.setLanguage(new Locale("id", "ID"));
                ttsSiap = hasil != TextToSpeech.LANG_MISSING_DATA
                        && hasil != TextToSpeech.LANG_NOT_SUPPORTED;
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String id) { }
                    @Override public void onDone(String id) {
                        handler.post(() -> selesaiMengumumkan(600));
                    }
                    @Override public void onError(String id) {
                        handler.post(() -> selesaiMengumumkan(600));
                    }
                });
            }
            // Tanpa TTS Bahasa Indonesia, paket suara server yang dipakai.
            handler.post(this::sinkronkanPaketSuara);
        });
    }

    /**
     * Ucapkan panggilan berikutnya. Urutan pilihan suara sama dengan layar
     * antrian: TTS Bahasa Indonesia tablet, paket suara server, nada saja.
     * Pengunjung yang sedang mengambil nomor tidak menunda pengumuman:
     * orang yang dipanggil bisa terlewat bila harus menunggu.
     */
    private void ucapkanBerikutnya() {
        if (sedangMengumumkan || !suaraPanggilan) return;
        JSONObject call = ambilPanggilanSegar();
        if (call == null) return;
        sedangMengumumkan = true;
        aturSuaraVideo();
        if (nada != null) nada.startTone(ToneGenerator.TONE_PROP_BEEP2, 600);
        // Jeda sesudah nada, supaya kata pertama tidak tertelan nadanya.
        handler.postDelayed(() -> {
            if (!sedangMengumumkan) return;  // dimatikan admin di tengah jalan
            String teks = call.optString("text");
            JSONArray tokens = call.optJSONArray("tokens");
            if (ttsSiap && !teks.isEmpty()) {
                int hasil = tts.speak(teks, TextToSpeech.QUEUE_FLUSH, new Bundle(),
                        UUID.randomUUID().toString());
                if (hasil != TextToSpeech.SUCCESS) selesaiMengumumkan(1500);
            } else if (!klipPaket.isEmpty() && tokens != null && tokens.length() > 0) {
                putarKlip(tokens, 0);
            } else {
                selesaiMengumumkan(1500);
            }
        }, 900);
    }

    /**
     * Panggilan berikutnya yang belum basi. Umurnya = umur saat diterima
     * ditambah lama menunggu giliran di tablet; server lama tanpa
     * age_seconds dianggap baru.
     */
    private JSONObject ambilPanggilanSegar() {
        long sekarang = System.currentTimeMillis();
        while (!antreanUcapan.isEmpty()) {
            JSONObject call = antreanUcapan.poll();
            double umur = call.optDouble("age_seconds", 0)
                    + (sekarang - call.optLong("_diterima_ms", sekarang)) / 1000.0;
            if (umur <= BATAS_UMUR_PANGGILAN_DETIK) return call;
        }
        return null;
    }

    /** Pengumuman selesai; berikutnya menyusul setelah jeda. Negatif = berhenti. */
    private void selesaiMengumumkan(long jedaMs) {
        if (!sedangMengumumkan) return;
        sedangMengumumkan = false;
        aturSuaraVideo();
        if (jedaMs >= 0) handler.postDelayed(this::ucapkanBerikutnya, jedaMs);
    }

    /** Putar klip paket suara satu per satu; token jeda = diam sejenak, klip hilang dilewati. */
    private void putarKlip(JSONArray tokens, int indeks) {
        if (!sedangMengumumkan) return;
        if (indeks >= tokens.length()) {
            selesaiMengumumkan(600);
            return;
        }
        String token = tokens.optString(indeks);
        if (TOKEN_JEDA.equals(token)) {
            handler.postDelayed(() -> putarKlip(tokens, indeks + 1), 250);
            return;
        }
        String nama = klipPaket.get(token);
        File klip = nama == null ? null : new File(folderPaketSuara(), nama);
        if (klip == null || !klip.isFile()) {
            putarKlip(tokens, indeks + 1);
            return;
        }
        lepasPemutarKlip();
        try {
            MediaPlayer media = new MediaPlayer();
            pemutarKlip = media;
            media.setAudioStreamType(AudioManager.STREAM_MUSIC);
            media.setDataSource(klip.getAbsolutePath());
            media.setOnCompletionListener(p -> {
                lepasPemutarKlip();
                putarKlip(tokens, indeks + 1);
            });
            media.setOnErrorListener((p, what, extra) -> {
                lepasPemutarKlip();
                putarKlip(tokens, indeks + 1);
                return true;
            });
            media.prepare();
            media.start();
        } catch (Exception e) {
            lepasPemutarKlip();
            putarKlip(tokens, indeks + 1);
        }
    }

    private void lepasPemutarKlip() {
        if (pemutarKlip == null) return;
        try {
            pemutarKlip.release();
        } catch (RuntimeException ignored) {
            // Sudah dilepas.
        }
        pemutarKlip = null;
    }

    private File folderPaketSuara() {
        return new File(getFilesDir(), "suara");
    }

    private void muatPaketSuara() {
        klipPaket.clear();
        File indeks = new File(folderPaketSuara(), "paket.json");
        if (!indeks.isFile()) return;
        try (FileInputStream input = new FileInputStream(indeks)) {
            ByteArrayOutputStream isi = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int length;
            while ((length = input.read(buffer)) != -1) isi.write(buffer, 0, length);
            JSONObject json = new JSONObject(new String(isi.toByteArray(), StandardCharsets.UTF_8));
            JSONObject clips = json.optJSONObject("clips");
            if (clips == null) return;
            Iterator<String> keys = clips.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                klipPaket.put(key, clips.optString(key));
            }
        } catch (Exception e) {
            klipPaket.clear();
        }
    }

    /**
     * Unduh paket suara bila anjungan ini bersuara, tablet tidak punya TTS
     * Bahasa Indonesia, dan versinya di server berubah. Paket baru diunduh
     * ke folder sementara dan baru menggantikan yang lama sesudah lengkap.
     */
    private void sinkronkanPaketSuara() {
        String versi = versiPaketServer;
        if (!suaraPanggilan || versi.isEmpty() || !ttsDiperiksa || ttsSiap || paketDiunduh) return;
        if (versi.equals(preferences.getString(VERSI_PAKET_SUARA, "")) && !klipPaket.isEmpty()) return;
        if (System.currentTimeMillis() < paketCobaLagiPada) return;
        paketDiunduh = true;
        String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
        pengunduh.execute(() -> {
            String terpasang = null;
            File sementara = new File(getFilesDir(), "suara-baru");
            try {
                JSONObject indeks = new JSONObject(new String(
                        unduhBytes(base + "/v1/kiosk/sound"), StandardCharsets.UTF_8));
                BerkasMedia.hapusPohon(sementara);
                if (!sementara.mkdirs()) throw new IllegalStateException("folder paket");
                JSONObject clips = indeks.getJSONObject("clips");
                Iterator<String> keys = clips.keys();
                while (keys.hasNext()) {
                    String nama = clips.getString(keys.next());
                    if (!nama.matches("[A-Za-z0-9_.-]+")) {
                        throw new IllegalStateException("nama klip paket tidak sah");
                    }
                    byte[] isi = unduhBytes(base + "/v1/kiosk/sound/"
                            + URLEncoder.encode(nama, "UTF-8"));
                    try (OutputStream output = new FileOutputStream(new File(sementara, nama))) {
                        output.write(isi);
                    }
                }
                try (OutputStream output = new FileOutputStream(new File(sementara, "paket.json"))) {
                    output.write(indeks.toString().getBytes(StandardCharsets.UTF_8));
                }
                File tujuan = folderPaketSuara();
                BerkasMedia.hapusPohon(tujuan);
                if (!sementara.renameTo(tujuan)) throw new IllegalStateException("pasang paket");
                terpasang = indeks.optString("version");
            } catch (Exception e) {
                BerkasMedia.hapusPohon(sementara);
            }
            final String selesai = terpasang;
            handler.post(() -> {
                paketDiunduh = false;
                if (selesai == null) {
                    paketCobaLagiPada = System.currentTimeMillis() + COBA_PAKET_LAGI_MS;
                    return;
                }
                preferences.edit().putString(VERSI_PAKET_SUARA, selesai).apply();
                muatPaketSuara();
            });
        });
    }

    /** Berjalan di thread pengunduh. Klip paket suara kecil, cukup di memori. */
    private byte[] unduhBytes(String url) throws Exception {
        return UnduhServer.byteKecil(url, this::applyHeaders);
    }

    private void request(
            String method, String path, org.json.JSONObject body,
            Success success, Failure failure) {
        request(worker, method, path, body, success, failure, null);
    }

    private void request(
            ExecutorService pelaksana, String method, String path, org.json.JSONObject body,
            Success success, Failure failure) {
        request(pelaksana, method, path, body, success, failure, null);
    }

    /** `ditolak` menerima jawaban 4xx; tanpa itu 4xx ikut ke `failure`. */
    private void request(
            ExecutorService pelaksana, String method, String path, org.json.JSONObject body,
            Success success, Failure failure, Ditolak ditolak) {
        pelaksana.execute(() -> {
            try {
                String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
                JSONObject wrapped = KlienServer.panggil(
                        base, method, path, body, this::applyHeaders);
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
                if (e instanceof PenolakanServer && ditolak != null) {
                    int kode = ((PenolakanServer) e).kode;
                    handler.post(() -> ditolak.accept(kode, message));
                } else {
                    handler.post(() -> failure.accept(message));
                }
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
        // Pertahanan terakhir: token tidak ikut ke alamat di luar jaringan lokal
        // lewat http://. Server akan menolak dengan 401, bukan aplikasi yang macet.
        if (AlamatServer.aman(connection.getURL().toString())) {
            connection.setRequestProperty("Authorization",
                    "Bearer " + preferences.getString(TOKEN, ""));
        }
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
            try {
                String base = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
                PemasangPembaruan.unduhDanPasang(this, base, this::applyHeaders,
                        ACTION_INSTALL_STATUS, (selesai, total) -> handler.post(() -> {
                            if (total > 0) bar.setProgress((int) (selesai * 1000 / total));
                            progress.setText(String.format(new Locale("id", "ID"),
                                    "%.1f MB%s", selesai / 1048576.0,
                                    total > 0 ? String.format(new Locale("id", "ID"),
                                            " dari %.1f MB", total / 1048576.0) : ""));
                        }));
                handler.post(() -> {
                    bar.setProgress(1000);
                    progress.setText("Memasang… setujui di layar Android.");
                });
            } catch (Exception e) {
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


    // =====================================================================
    // PIN pengaturan, mode putar saja, dan tempat tampil lokal
    // =====================================================================

    /**
     * Tombol ⚙. Tablet yang belum pernah tersambung (belum dipasang) atau
     * server yang belum memasang PIN membuka pengaturan langsung; selain itu
     * PIN diminta.
     */
    private void bukaPengaturan() {
        boolean terpasang = hasServerConfig()
                && preferences.getBoolean(PERNAH_TERHUBUNG, false);
        if (!terpasang || !preferences.getBoolean(PIN_AKTIF, false)) {
            showSettings();
            return;
        }
        tampilkanPapanPin(this::showSettings, false);
    }

    private void simpanPinDariServer(JSONObject pin) {
        if (pin == null) return;
        SharedPreferences.Editor editor = preferences.edit();
        boolean aktif = pin.optBoolean("enabled", false);
        editor.putBoolean(PIN_AKTIF, aktif);
        if (aktif) {
            editor.putString(PIN_SALT, pin.optString("salt", ""))
                    .putString(PIN_HASH, pin.optString("hash", ""))
                    .putInt(PIN_ITER, pin.optInt("iterations", 100000));
        }
        editor.apply();
    }

    /** PIN diperiksa ke server bila tersambung; tanpa jaringan, dengan hash tersimpan. */
    private void tampilkanPapanPin(Runnable setelahBenar, boolean paksaLokal) {
        StringBuilder isi = new StringBuilder();
        LinearLayout kolom = new LinearLayout(this);
        kolom.setOrientation(LinearLayout.VERTICAL);
        kolom.setGravity(Gravity.CENTER_HORIZONTAL);
        kolom.setPadding(dp(16), dp(8), dp(16), dp(8));
        TextView titik = text("○ ○ ○ ○ ○ ○", 30, INK, true);
        titik.setGravity(Gravity.CENTER);
        kolom.addView(titik);
        TextView pesan = text("Masukkan PIN pengaturan", 14, MUTED, false);
        pesan.setGravity(Gravity.CENTER);
        pesan.setPadding(0, dp(6), 0, dp(10));
        kolom.addView(pesan);
        AlertDialog[] dialog = new AlertDialog[1];
        Runnable gambar = () -> {
            StringBuilder t = new StringBuilder();
            for (int i = 0; i < 6; i++) t.append(i < isi.length() ? "● " : "○ ");
            titik.setText(t.toString().trim());
        };
        Runnable periksa = () -> {
            long tunda = preferences.getLong(PIN_TUNDA_SAMPAI, 0L) - System.currentTimeMillis();
            if (tunda > 0) {
                pesan.setText("Terlalu banyak percobaan. Coba lagi dalam "
                        + (tunda / 1000L + 1L) + " detik.");
                isi.setLength(0);
                gambar.run();
                return;
            }
            String pin = isi.toString();
            Runnable lokal = () -> hasilPin(cocokPinLokal(pin), 0, pesan, isi, gambar,
                    dialog, setelahBenar);
            if (paksaLokal || !hasServerConfig()) {
                lokal.run();
                return;
            }
            request("POST", "/v1/kiosk/pin/verifikasi",
                    new JSONObjectBuilder().put("pin", pin).build(),
                    json -> {
                        JSONObject data = json.getJSONObject("data");
                        hasilPin(data.optBoolean("ok", false),
                                data.optInt("locked_seconds", 0), pesan, isi, gambar,
                                dialog, setelahBenar);
                    }, error -> lokal.run());
        };
        String[][] tombolAngka = {
                {"1", "2", "3"}, {"4", "5", "6"}, {"7", "8", "9"}, {"Hapus", "0", "Batal"}};
        for (String[] deret : tombolAngka) {
            LinearLayout baris = new LinearLayout(this);
            baris.setGravity(Gravity.CENTER);
            for (String label : deret) {
                Button angka = actionButton(label, false);
                angka.setOnClickListener(v -> {
                    v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
                    if ("Hapus".equals(label)) {
                        if (isi.length() > 0) isi.setLength(isi.length() - 1);
                    } else if ("Batal".equals(label)) {
                        if (dialog[0] != null) dialog[0].dismiss();
                        return;
                    } else if (isi.length() < 6) {
                        isi.append(label);
                    }
                    gambar.run();
                    if (isi.length() == 6) periksa.run();
                });
                LinearLayout.LayoutParams ukuran = new LinearLayout.LayoutParams(dp(84), dp(58));
                ukuran.setMargins(dp(4), dp(4), dp(4), dp(4));
                baris.addView(angka, ukuran);
            }
            kolom.addView(baris);
        }
        dialog[0] = pembuatDialog()
                .setTitle("PIN pengaturan")
                .setView(kolom)
                .show();
        pasangAutoTutup(dialog[0]);
    }

    private void hasilPin(boolean benar, int kunciDetik, TextView pesan, StringBuilder isi,
                          Runnable gambar, AlertDialog[] dialog, Runnable setelahBenar) {
        isi.setLength(0);
        gambar.run();
        if (benar) {
            preferences.edit().putInt(PIN_GAGAL, 0).putLong(PIN_TUNDA_SAMPAI, 0L).apply();
            if (dialog[0] != null) dialog[0].dismiss();
            setelahBenar.run();
            return;
        }
        int gagal = preferences.getInt(PIN_GAGAL, 0) + 1;
        long tunda = kunciDetik * 1000L;
        if (tunda == 0L) {
            tunda = gagal >= 15 ? 900_000L : gagal >= 10 ? 300_000L : gagal >= 5 ? 60_000L : 0L;
        }
        preferences.edit().putInt(PIN_GAGAL, gagal)
                .putLong(PIN_TUNDA_SAMPAI, tunda > 0 ? System.currentTimeMillis() + tunda : 0L)
                .apply();
        pesan.setText(tunda > 0
                ? "PIN salah. Coba lagi dalam " + (tunda / 1000L) + " detik."
                : "PIN salah.");
    }

    private boolean cocokPinLokal(String pin) {
        if (!preferences.getBoolean(PIN_AKTIF, false)) return true;
        try {
            byte[] salt = heks(preferences.getString(PIN_SALT, ""));
            javax.crypto.SecretKeyFactory pabrik =
                    javax.crypto.SecretKeyFactory.getInstance("PBKDF2WithHmacSHA1");
            byte[] hitung = pabrik.generateSecret(new javax.crypto.spec.PBEKeySpec(
                    pin.toCharArray(), salt, preferences.getInt(PIN_ITER, 100000), 160))
                    .getEncoded();
            return java.security.MessageDigest.isEqual(
                    hitung, heks(preferences.getString(PIN_HASH, "")));
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * Seluruh dialog pengaturan berbagi SATU timer diam: sentuhan di dialog
     * mana pun menyetelnya ulang, sepuluh detik terakhir diberi peringatan, dan
     * saat habis SEMUA dialog ditutup sekaligus. Menutup juga saat aplikasi
     * masuk latar. Membuka pengaturan lagi meminta PIN lagi.
     */
    private final List<AlertDialog> dialogPengaturan = new ArrayList<>();
    private long sentuhPengaturanTerakhir;
    private Toast peringatanDiam;

    private final Runnable periksaDiamPengaturan = new Runnable() {
        @Override
        public void run() {
            if (dialogPengaturan.isEmpty()) return;
            long diam = System.currentTimeMillis() - sentuhPengaturanTerakhir;
            if (diam >= BATAS_DIAM_PENGATURAN_MS) {
                tutupSemuaPengaturan();
                return;
            }
            long sisa = BATAS_DIAM_PENGATURAN_MS - diam;
            if (sisa <= PERINGATAN_DIAM_PENGATURAN_MS) {
                if (peringatanDiam != null) peringatanDiam.cancel();
                peringatanDiam = Toast.makeText(MainActivity.this,
                        "Pengaturan menutup dalam " + (sisa / 1000L + 1L)
                                + " detik. Sentuh layar untuk melanjutkan.",
                        Toast.LENGTH_SHORT);
                peringatanDiam.show();
            }
            handler.postDelayed(this, 1000L);
        }
    };

    private void tutupSemuaPengaturan() {
        handler.removeCallbacks(periksaDiamPengaturan);
        if (peringatanDiam != null) {
            peringatanDiam.cancel();
            peringatanDiam = null;
        }
        List<AlertDialog> salinan = new ArrayList<>(dialogPengaturan);
        dialogPengaturan.clear();
        for (AlertDialog dialog : salinan) {
            if (dialog.isShowing()) dialog.dismiss();
        }
    }

    private void pasangAutoTutup(AlertDialog dialog) {
        if (dialogPengaturan.contains(dialog)) return;  // sudah terpasang
        sentuhPengaturanTerakhir = System.currentTimeMillis();
        boolean pertama = dialogPengaturan.isEmpty();
        dialogPengaturan.add(dialog);
        if (pertama) {
            handler.removeCallbacks(periksaDiamPengaturan);
            handler.postDelayed(periksaDiamPengaturan, 1000L);
        }
        dialog.setOnDismissListener(d -> {
            dialogPengaturan.remove(dialog);
            if (dialogPengaturan.isEmpty()) {
                handler.removeCallbacks(periksaDiamPengaturan);
                if (peringatanDiam != null) {
                    peringatanDiam.cancel();
                    peringatanDiam = null;
                }
            }
        });
        android.view.Window jendela = dialog.getWindow();
        if (jendela == null) return;
        android.view.Window.Callback asli = jendela.getCallback();
        jendela.setCallback((android.view.Window.Callback) java.lang.reflect.Proxy
                .newProxyInstance(android.view.Window.Callback.class.getClassLoader(),
                        new Class<?>[]{android.view.Window.Callback.class},
                        (proxy, metode, argumen) -> {
                            String nama = metode.getName();
                            if ("dispatchTouchEvent".equals(nama)
                                    || "dispatchKeyEvent".equals(nama)) {
                                sentuhPengaturanTerakhir = System.currentTimeMillis();
                            }
                            try {
                                return metode.invoke(asli, argumen);
                            } catch (java.lang.reflect.InvocationTargetException e) {
                                throw e.getCause();
                            }
                        }));
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (iklanPenuh && !putarSaja && ajakanIklanPenuh != null
                && ajakanIklanPenuh.getVisibility() == View.VISIBLE) {
            mulaiDenyutAjakanIklan();
        }
    }

    @Override
    protected void onStop() {
        // Layar mati atau tombol Home: pengaturan tidak boleh tertinggal terbuka.
        tutupSemuaPengaturan();
        hentikanAnimatorDenyutAjakan();
        super.onStop();
    }

    // --- mode putar saja ----------------------------------------------------

    /**
     * Server tidak terjangkau selama BATAS_PUTAR_SAJA_MS (dan tablet pernah
     * tersambung): semua fitur dimatikan dan hanya video yang diputar.
     * Kembali normal sendiri begitu server terjangkau. Pengunjung yang sedang
     * di layar konfirmasi atau melihat nomor tidak diganggu.
     */
    private void perbaruiModePutarSaja(long sekarang) {
        boolean pernah = hasServerConfig() && preferences.getBoolean(PERNAH_TERHUBUNG, false);
        boolean harus = pernah && gagalSejak != 0L
                && sekarang - gagalSejak >= BATAS_PUTAR_SAJA_MS;
        if (harus && !putarSaja && !showingConfirmation && !showingResult
                && !requestInFlight && !updating) {
            masukPutarSaja();
        } else if (!harus && putarSaja) {
            keluarPutarSaja();
        }
    }

    private void masukPutarSaja() {
        if (putarSaja || rootLayout == null) return;
        putarSaja = true;
        welcome.setTextColor(Color.WHITE);
        masukIklanPenuh();
        mediaModePenuh = true;
        terapkanMediaSambutan();
        hentikanDenyutAjakanIklan();
        ajakanIklanPenuh.setText("Menghubungkan ke server…");
        ajakanIklanPenuh.setAlpha(0.55f);
    }

    private void keluarPutarSaja() {
        if (!putarSaja) return;
        putarSaja = false;
        handler.removeCallbacks(bukaPulih);
        welcome.setTextColor(INK);
        ajakanIklanPenuh.setText("Sentuh layar untuk mengambil nomor antrian");
        keluarDenganAnimasiPenuh = true;
        keluarIklanPenuh();
        mediaModePenuh = false;
        terapkanMediaSambutan();
        loadCategories();
        loadDisplay();
    }

    /** Layar tidak merespons sentuhan, kecuali tahan pojok kiri bawah (jalan pulih). */
    private boolean tanganiSentuhanPutarSaja(MotionEvent event) {
        int aksi = event.getActionMasked();
        int lebar = rootLayout == null ? 0 : rootLayout.getWidth();
        int tinggi = rootLayout == null ? 0 : rootLayout.getHeight();
        boolean pojok = event.getX() < lebar * 0.2f && event.getY() > tinggi * 0.8f;
        if (aksi == MotionEvent.ACTION_DOWN) {
            if (pojok) handler.postDelayed(bukaPulih, TAHAN_PULIH_MS);
        } else if (aksi == MotionEvent.ACTION_UP || aksi == MotionEvent.ACTION_CANCEL
                || (aksi == MotionEvent.ACTION_MOVE && !pojok)) {
            handler.removeCallbacks(bukaPulih);
        }
        return true;
    }

    /** Jalan pulih: PIN diperiksa dengan hash tersimpan, tanpa jaringan. */
    private final Runnable bukaPulih = () -> {
        if (!preferences.getBoolean(PIN_AKTIF, false)) {
            showSettings();
        } else {
            tampilkanPapanPin(this::showSettings, true);
        }
    };

    /** Daftar media terakhir dari server, agar mode putar saja bekerja sesudah dinyalakan ulang. */
    private void simpanMediaTerakhir(JSONObject display) {
        try {
            JSONObject ringkas = new JSONObject();
            for (String kunci : new String[]{"welcome_kind", "welcome_media",
                    "welcome_media_files", "fullscreen_ad_idle_seconds", "fullscreen_ad_loops",
                    "welcome_slide_seconds", "welcome_text"}) {
                if (display.has(kunci)) ringkas.put(kunci, display.get(kunci));
            }
            String teks = ringkas.toString();
            if (teks.equals(mediaTerakhirTersimpan)) return;
            mediaTerakhirTersimpan = teks;
            preferences.edit().putString(DISPLAY_TERAKHIR, teks).apply();
        } catch (Exception ignored) {
            // Gagal menyimpan hanya berarti mode putar saja memakai data yang ada.
        }
    }

    private void muatMediaTerakhir() {
        String teks = preferences.getString(DISPLAY_TERAKHIR, "");
        if (teks.isEmpty()) return;
        mediaTerakhirTersimpan = teks;
        try {
            JSONObject display = new JSONObject(teks);
            serverKind = display.optString("welcome_kind", "teks");
            welcomeFallbackText = display.optString("welcome_text", "");
            iklanPenuhDetik = Math.max(0, display.optInt("fullscreen_ad_idle_seconds", 60));
            iklanPutaran = Math.max(0, display.optInt("fullscreen_ad_loops", 2));
            welcomeSlideSeconds = Math.max(1, display.optInt("welcome_slide_seconds", 10));
            List<String> media = new ArrayList<>();
            JSONArray nama = display.optJSONArray("welcome_media");
            if (nama != null) {
                for (int i = 0; i < nama.length(); i++) media.add(nama.getString(i));
            }
            kunciSalinan.clear();
            detikPerBerkas.clear();
            tampilBerkas.clear();
            JSONArray info = display.optJSONArray("welcome_media_files");
            if (info != null) {
                for (int i = 0; i < info.length(); i++) {
                    JSONObject row = info.optJSONObject(i);
                    if (row == null) continue;
                    String berkas = row.optString("name", "");
                    if (berkas.isEmpty()) continue;
                    kunciSalinan.put(berkas, row.optLong("size", 0L) + "-"
                            + row.optLong("modified_ms", 0L) + "-" + BerkasMedia.namaAman(berkas));
                    tampilBerkas.put(berkas, row.optString("show", "keduanya"));
                    int detik = row.isNull("seconds") ? 0 : row.optInt("seconds", 0);
                    if (detik > 0) detikPerBerkas.put(berkas, detik);
                }
            }
            serverMedia = media;
        } catch (Exception ignored) {
            // Data tersimpan rusak: abaikan, server akan mengirim yang baru.
        }
    }

    // --- tempat tampil untuk media di folder tablet ---------------------------

    private String tampilLokal(String nama) {
        try {
            return new JSONObject(preferences.getString(TAMPIL_LOKAL, "{}"))
                    .optString(nama, "keduanya");
        } catch (Exception e) {
            return "keduanya";
        }
    }

    private void aturTampilLokal(String nama, String tempat) {
        try {
            JSONObject isi = new JSONObject(preferences.getString(TAMPIL_LOKAL, "{}"));
            if ("keduanya".equals(tempat)) {
                isi.remove(nama);
            } else {
                isi.put(nama, tempat);
            }
            preferences.edit().putString(TAMPIL_LOKAL, isi.toString()).apply();
        } catch (Exception ignored) {
            // Preferensi rusak: pilihan tidak tersimpan, berkas tetap tampil di keduanya.
        }
    }

    /** Berkas folder tablet tampil di panel atas (penuh=false) atau layar penuh. */
    private boolean tampilLokalDi(String nama, boolean penuh) {
        String tempat = tampilLokal(nama);
        if ("keduanya".equals(tempat)) return true;
        return penuh ? "penuh".equals(tempat) : "panel".equals(tempat);
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
        tampilan.addView(labelPengaturan("Cara gambar dan video memenuhi bingkai"));
        tampilan.addView(pilihanTarik(PILIHAN_SKALA_VIDEO,
                preferences.getString(SKALA_VIDEO, VIDEO_PAS), nilai -> {
                    preferences.edit().putString(SKALA_VIDEO, nilai).apply();
                    if (!welcomeMedia.isEmpty()) showWelcomeMedia(mediaIndex);
                }), new LinearLayout.LayoutParams(-1, -2));
        Button kelolaMedia = smallButton("Kelola media tablet");
        kelolaMedia.setOnClickListener(v -> showMediaTablet());
        tampilan.addView(kelolaMedia, tombolPengaturan());
        tampilan.addView(labelPengaturan("Posisi baris loket di tablet ini"));
        tampilan.addView(pilihanTarik(PILIHAN_POSISI_LOKET,
                preferences.getString(POSISI_LOKET_TABLET, IKUTI_SERVER), nilai -> {
                    preferences.edit().putString(POSISI_LOKET_TABLET, nilai).apply();
                    terapkanBarisLoket();
                }), new LinearLayout.LayoutParams(-1, -2));
        tampilan.addView(labelPengaturan("Tema tablet ini"));
        tampilan.addView(pilihanTarik(PILIHAN_TEMA,
                preferences.getString(TEMA_TABLET, IKUTI_SERVER_TEMA), nilai -> {
                    preferences.edit().putString(TEMA_TABLET, nilai).apply();
                    terapkanTemaBilaBerubah();
                }), new LinearLayout.LayoutParams(-1, -2));
        tampilan.addView(labelPengaturan("Latar belakang tablet ini"));
        tampilan.addView(pilihanTarik(PILIHAN_LATAR,
                preferences.getString(LATAR_KERTAS, KERTAS_POLOS), nilai -> {
                    preferences.edit().putString(LATAR_KERTAS, nilai).apply();
                    terapkanTemaBilaBerubah();
                }), new LinearLayout.LayoutParams(-1, -2));
        tampilan.addView(labelPengaturan("Warna kilau petunjuk"));
        tampilan.addView(barisWarnaKilau());
        tampilan.addView(labelPengaturan("Warna latar iklan layar penuh"));
        tampilan.addView(barisLatarIklan());
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
        // Sebaris, sama lebar. Huruf mengecil bila dialog sempit (tablet
        // tegak), bukan terpotong.
        LinearLayout barisAplikasi = new LinearLayout(this);
        barisAplikasi.setOrientation(LinearLayout.HORIZONTAL);
        Button restartApi = smallButton("Restart API server");
        restartApi.setEnabled(hasServerConfig());
        restartApi.setOnClickListener(v -> confirmRestartApi(restartApi));
        pasangSatuBaris(restartApi, 11, 15);
        barisAplikasi.addView(restartApi, new LinearLayout.LayoutParams(0, dp(44), 1));
        Button keluar = smallButton("Keluar dari aplikasi");
        pasangSatuBaris(keluar, 11, 15);
        LinearLayout.LayoutParams keluarParams = new LinearLayout.LayoutParams(0, dp(44), 1);
        keluarParams.leftMargin = dp(8);
        barisAplikasi.addView(keluar, keluarParams);
        LinearLayout.LayoutParams barisParams = new LinearLayout.LayoutParams(-1, -2);
        barisParams.topMargin = dp(8);
        perawatan.addView(barisAplikasi, barisParams);
        // Satu kartu per tab: empat kartu bertumpuk membuat dialog harus
        // digulir jauh, dan teknisi mencari-cari bagian yang dimaksud.
        View[] kartuTab = {koneksi, printer, tampilan, perawatan};
        String[] namaTab = {"Koneksi", "Printer", "Tampilan", "Aplikasi"};
        LinearLayout barisTab = new LinearLayout(this);
        barisTab.setPadding(dp(16), dp(4), dp(16), 0);
        List<TextView> tombolTab = new ArrayList<>();
        java.util.function.IntConsumer pilihTab = indeks -> {
            tabPengaturan = indeks;
            for (int i = 0; i < kartuTab.length; i++) {
                boolean aktif = i == indeks;
                kartuTab[i].setVisibility(aktif ? View.VISIBLE : View.GONE);
                TextView t = tombolTab.get(i);
                t.setTextColor(aktif ? TEKS_TOMBOL : INK);
                t.setBackground(aktif ? rounded(UTAMA, dp(18))
                        : roundedOutline(KARTU, GARIS, dp(18), dp(1)));
            }
        };
        for (int i = 0; i < namaTab.length; i++) {
            TextView t = text(namaTab[i], 14, INK, true);
            t.setGravity(Gravity.CENTER);
            pasangSatuBaris(t, 10, 14);
            int indeks = i;
            t.setOnClickListener(v -> pilihTab.accept(indeks));
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(38), 1);
            if (i > 0) params.leftMargin = dp(6);
            barisTab.addView(t, params);
            tombolTab.add(t);
        }
        pilihTab.accept(tabPengaturan);
        LinearLayout isiDialog = new LinearLayout(this);
        isiDialog.setOrientation(LinearLayout.VERTICAL);
        isiDialog.addView(barisTab);
        isiDialog.addView(gulungan(fields), new LinearLayout.LayoutParams(-1, -2));
        AlertDialog dialog = pembuatDialog()
                .setTitle("Pengaturan anjungan")
                .setView(isiDialog)
                .setPositiveButton("Simpan", null)
                .setNeutralButton("Uji cetak", null)
                .setNegativeButton("Batal", null).create();
        keluar.setOnClickListener(v -> konfirmasiKeluar(dialog));
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
                        pilihTab.accept(0);
                        server.setError("Alamat harus diawali http:// atau https://");
                        return;
                    }
                    if (!AlamatServer.aman(address)) {
                        pilihTab.accept(0);
                        server.setError(AlamatServer.PESAN_DITOLAK);
                        return;
                    }
                    preferences.edit().putString(DEVICE_NAME, name.getText().toString().trim())
                            .apply();
                    if (!code.isEmpty()) {
                        if (code.length() != 6) {
                            pilihTab.accept(0);
                            pairCode.setError("Kode pasang 6 angka");
                            return;
                        }
                        preferences.edit().putString(SERVER, address).apply();
                        pairDevice(code, dialog, pairCode);
                        return;
                    }
                    if (apiToken.length() < 8) {
                        pilihTab.accept(0);
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
        pasangAutoTutup(dialog);
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

    /**
     * Pilihan warna kilau sebagai satu baris bulatan, bukan daftar radio:
     * dialog Pengaturan sudah panjang. Menyentuh bulatan langsung
     * memperlihatkan sapuannya pada petunjuk di belakang dialog.
     */
    private View barisWarnaKilau() {
        android.widget.HorizontalScrollView gulir = new android.widget.HorizontalScrollView(this);
        gulir.setHorizontalScrollBarEnabled(false);
        LinearLayout baris = new LinearLayout(this);
        baris.setGravity(Gravity.CENTER_VERTICAL);
        baris.setPadding(0, dp(4), 0, dp(4));
        gulir.addView(baris);
        TextView keterangan = text("", 12, MUTED, false);
        List<TextView> bulatan = new ArrayList<>();
        TextView lain = text("+", 18, Color.WHITE, true);
        lain.setGravity(Gravity.CENTER);
        lain.setShadowLayer(dp(2), 0f, 0f, Color.BLACK);
        lain.setContentDescription("Warna lain");
        Runnable[] segarkanRef = new Runnable[1];
        Runnable segarkan = () -> {
            String aktif = preferences.getString(WARNA_KILAU, KILAU_TEMA);
            if (aktif.startsWith("#")) {
                lain.setBackground(roundedOutline(warnaKilau(aktif), INK, dp(18), dp(3)));
                keterangan.setText("Warna sendiri " + aktif.toUpperCase(Locale.ROOT));
            } else {
                GradientDrawable pelangi = new GradientDrawable();
                pelangi.setShape(GradientDrawable.OVAL);
                pelangi.setGradientType(GradientDrawable.SWEEP_GRADIENT);
                pelangi.setColors(new int[]{Color.RED, Color.YELLOW, Color.GREEN,
                        Color.CYAN, Color.BLUE, Color.MAGENTA, Color.RED});
                pelangi.setStroke(dp(1), GARIS);
                lain.setBackground(pelangi);
            }
            for (int i = 0; i < bulatan.size(); i++) {
                TextView b = bulatan.get(i);
                String kunci = PILIHAN_KILAU[i][0];
                boolean dipilih = kunci.equals(aktif);
                Integer warna = warnaKilau(kunci);
                int isi = warna == null ? KARTU : warna;
                b.setBackground(roundedOutline(isi, dipilih ? INK : GARIS, dp(18),
                        dp(dipilih ? 3 : 1)));
                if (dipilih) keterangan.setText(PILIHAN_KILAU[i][1]);
            }
        };
        segarkanRef[0] = segarkan;
        lain.setOnClickListener(v -> bukaPemilihWarnaKilau(segarkanRef[0]));
        LinearLayout.LayoutParams paramLain = new LinearLayout.LayoutParams(dp(36), dp(36));
        paramLain.rightMargin = dp(8);
        baris.addView(lain, paramLain);
        for (String[] pilihan : PILIHAN_KILAU) {
            TextView b = text("mati".equals(pilihan[0]) ? "✕"
                    : KILAU_TEMA.equals(pilihan[0]) ? "T" : "", 13, MUTED, true);
            b.setGravity(Gravity.CENTER);
            b.setContentDescription(pilihan[1]);
            b.setOnClickListener(v -> {
                preferences.edit().putString(WARNA_KILAU, pilihan[0]).apply();
                segarkan.run();
                sapukanKilau();
            });
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(36), dp(36));
            params.rightMargin = dp(8);
            baris.addView(b, params);
            bulatan.add(b);
        }
        baris.addView(keterangan);
        segarkan.run();
        return gulir;
    }

    /** Baris bulatan pilihan cepat latar iklan penuh + "+" untuk isian hex. */
    private View barisLatarIklan() {
        android.widget.HorizontalScrollView gulir = new android.widget.HorizontalScrollView(this);
        gulir.setHorizontalScrollBarEnabled(false);
        LinearLayout baris = new LinearLayout(this);
        baris.setGravity(Gravity.CENTER_VERTICAL);
        baris.setPadding(0, dp(4), 0, dp(4));
        gulir.addView(baris);
        TextView keterangan = text("", 12, MUTED, false);
        List<TextView> bulatan = new ArrayList<>();
        TextView lain = text("+", 18, Color.WHITE, true);
        lain.setGravity(Gravity.CENTER);
        lain.setContentDescription("Warna lain");
        Runnable segarkan = () -> {
            String aktif = String.format(Locale.ROOT, "#%06X", latarIklanPenuh & 0xFFFFFF);
            boolean cepat = false;
            for (int i = 0; i < bulatan.size(); i++) {
                boolean dipilih = PILIHAN_LATAR_IKLAN[i][1].equals(aktif);
                cepat |= dipilih;
                bulatan.get(i).setBackground(roundedOutline(
                        Color.parseColor(PILIHAN_LATAR_IKLAN[i][1]), dipilih ? INK : GARIS,
                        dp(18), dp(dipilih ? 3 : 1)));
                if (dipilih) keterangan.setText(PILIHAN_LATAR_IKLAN[i][0]);
            }
            if (!cepat) keterangan.setText("Warna sendiri " + aktif);
            lain.setBackground(roundedOutline(cepat ? KARTU : latarIklanPenuh,
                    cepat ? GARIS : INK, dp(18), dp(cepat ? 1 : 3)));
            lain.setTextColor(cepat ? MUTED : teksIklanPenuh);
        };
        for (String[] pilihan : PILIHAN_LATAR_IKLAN) {
            TextView b = text("", 13, MUTED, true);
            b.setContentDescription(pilihan[0]);
            b.setOnClickListener(v -> {
                simpanLatarIklan(pilihan[1]);
                segarkan.run();
            });
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(dp(36), dp(36));
            params.rightMargin = dp(8);
            baris.addView(b, params);
            bulatan.add(b);
        }
        lain.setOnClickListener(v -> bukaIsianLatarIklan(segarkan));
        LinearLayout.LayoutParams paramLain = new LinearLayout.LayoutParams(dp(36), dp(36));
        paramLain.rightMargin = dp(8);
        baris.addView(lain, paramLain);
        baris.addView(keterangan);
        segarkan.run();
        return gulir;
    }

    /** Simpan dan terapkan; nilai tak sah ditolak (warna tidak berubah). */
    private boolean simpanLatarIklan(String hex) {
        if (uraiLatarIklan(hex) == null) return false;
        preferences.edit().putString(LATAR_IKLAN_KUNCI, hex.toUpperCase(Locale.ROOT)).apply();
        terapkanLatarIklanPenuh(hex);
        return true;
    }

    private void bukaIsianLatarIklan(Runnable sesudahSimpan) {
        LinearLayout isi = new LinearLayout(this);
        isi.setOrientation(LinearLayout.VERTICAL);
        isi.setPadding(dp(20), dp(8), dp(20), 0);
        View contoh = new View(this);
        EditText isianHex = new EditText(this);
        isianHex.setSingleLine(true);
        isianHex.setTextColor(INK);
        isianHex.setTextSize(14 * uiScale);
        isianHex.setHint("#RRGGBB");
        isianHex.setText(String.format(Locale.ROOT, "#%06X", latarIklanPenuh & 0xFFFFFF));
        isianHex.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(7)});
        TextView pesan = text("", 12, Color.rgb(185, 28, 28), false);
        pesan.setPadding(0, dp(6), 0, 0);
        LinearLayout bawah = new LinearLayout(this);
        bawah.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams paramContoh = new LinearLayout.LayoutParams(dp(44), dp(44));
        paramContoh.rightMargin = dp(12);
        bawah.addView(contoh, paramContoh);
        bawah.addView(isianHex, new LinearLayout.LayoutParams(0, -2, 1));
        isi.addView(bawah, new LinearLayout.LayoutParams(-1, -2));
        isi.addView(pesan);
        AlertDialog dialog = pembuatDialog()
                .setTitle("Warna latar iklan penuh")
                .setView(gulungan(isi))
                .setNegativeButton("Batal", null)
                .setPositiveButton("Pakai warna ini", null).show();
        rapikanTombolDialog(dialog);
        Button pakai = dialog.getButton(AlertDialog.BUTTON_POSITIVE);
        Runnable periksa = () -> {
            String teks = isianHex.getText().toString().trim();
            Integer warna = uraiLatarIklan(teks);
            pakai.setEnabled(warna != null);
            if (warna != null) {
                contoh.setBackground(roundedOutline(warna, GARIS, dp(12), dp(1)));
                pesan.setText("");
            } else {
                contoh.setBackground(roundedOutline(KARTU, GARIS, dp(12), dp(1)));
                pesan.setText(teks.matches("#[0-9a-fA-F]{6}")
                        ? "Warna terlalu terang untuk panel. Pilih yang lebih gelap."
                        : "Tulis warna sebagai #RRGGBB, misalnya #0F172A.");
            }
        };
        isianHex.addTextChangedListener(new android.text.TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence c, int a, int b, int d) {
            }

            @Override
            public void onTextChanged(CharSequence c, int a, int b, int d) {
            }

            @Override
            public void afterTextChanged(android.text.Editable e) {
                periksa.run();
            }
        });
        pakai.setOnClickListener(v -> {
            if (simpanLatarIklan(isianHex.getText().toString().trim())) {
                sesudahSimpan.run();
                dialog.dismiss();
            }
        });
        periksa.run();
    }

    /**
     * Pemilih warna bebas: pita jenis warna (hue), bidang kejenuhan x kecerahan,
     * dan isian hex. Kecerahan dibatasi dari NILAI_MINIMUM_KILAU supaya sapuan
     * tidak hilang di latar gelap. Disimpan sebagai "#RRGGBB" di WARNA_KILAU.
     */
    private void bukaPemilihWarnaKilau(Runnable sesudahSimpan) {
        float[] hsv = new float[3];
        Color.colorToHSV(warnaKilau(preferences.getString(WARNA_KILAU, KILAU_TEMA)) == null
                ? EMAS : warnaKilau(preferences.getString(WARNA_KILAU, KILAU_TEMA)), hsv);
        hsv[2] = Math.max(hsv[2], NILAI_MINIMUM_KILAU);

        LinearLayout isi = new LinearLayout(this);
        isi.setOrientation(LinearLayout.VERTICAL);
        isi.setPadding(dp(20), dp(8), dp(20), 0);

        TextView hex = text("", 14, INK, true);
        EditText isianHex = new EditText(this);
        isianHex.setSingleLine(true);
        isianHex.setTextColor(INK);
        isianHex.setTextSize(14 * uiScale);
        isianHex.setHint("#RRGGBB");
        isianHex.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(7)});
        View contoh = new View(this);

        boolean[] sedangMenulis = new boolean[1];
        BidangWarnaKilau[] bidang = new BidangWarnaKilau[2];
        Runnable perbarui = () -> {
            int warna = Color.HSVToColor(hsv);
            contoh.setBackground(roundedOutline(warna, GARIS, dp(12), dp(1)));
            sedangMenulis[0] = true;
            isianHex.setText(String.format(Locale.ROOT, "#%06X", warna & 0xFFFFFF));
            sedangMenulis[0] = false;
            for (BidangWarnaKilau b : bidang) if (b != null) b.invalidate();
        };
        Runnable lepas = () -> sapukanKilau(Color.HSVToColor(hsv));

        BidangWarnaKilau bidangSv = new BidangWarnaKilau(this, hsv, false, perbarui, lepas);
        BidangWarnaKilau bidangHue = new BidangWarnaKilau(this, hsv, true, perbarui, lepas);
        bidang[0] = bidangSv;
        bidang[1] = bidangHue;
        isi.addView(bidangSv, new LinearLayout.LayoutParams(-1, dp(180)));
        LinearLayout.LayoutParams paramHue = new LinearLayout.LayoutParams(-1, dp(32));
        paramHue.topMargin = dp(12);
        isi.addView(bidangHue, paramHue);

        LinearLayout bawah = new LinearLayout(this);
        bawah.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams paramContoh = new LinearLayout.LayoutParams(dp(44), dp(44));
        paramContoh.rightMargin = dp(12);
        bawah.addView(contoh, paramContoh);
        bawah.addView(isianHex, new LinearLayout.LayoutParams(0, -2, 1));
        LinearLayout.LayoutParams paramBawah = new LinearLayout.LayoutParams(-1, -2);
        paramBawah.topMargin = dp(12);
        isi.addView(bawah, paramBawah);
        TextView catatan = text("Warna yang terlalu gelap otomatis dicerahkan agar sapuannya terlihat.",
                12, MUTED, false);
        catatan.setPadding(0, dp(6), 0, 0);
        isi.addView(catatan);

        isianHex.addTextChangedListener(new android.text.TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence c, int a, int b, int d) {
            }

            @Override
            public void onTextChanged(CharSequence c, int a, int b, int d) {
            }

            @Override
            public void afterTextChanged(android.text.Editable e) {
                if (sedangMenulis[0]) return;
                String teks = e.toString().trim();
                if (!teks.matches("#?[0-9a-fA-F]{6}")) return;
                Color.colorToHSV(Color.parseColor(teks.startsWith("#") ? teks : "#" + teks), hsv);
                hsv[2] = Math.max(hsv[2], NILAI_MINIMUM_KILAU);
                contoh.setBackground(roundedOutline(Color.HSVToColor(hsv), GARIS, dp(12), dp(1)));
                for (BidangWarnaKilau b : bidang) b.invalidate();
            }
        });
        perbarui.run();

        AlertDialog dialog = pembuatDialog()
                .setTitle("Warna kilau sendiri")
                .setView(gulungan(isi))
                .setNegativeButton("Batal", null)
                .setPositiveButton("Pakai warna ini", (d, w) -> {
                    preferences.edit().putString(WARNA_KILAU,
                            String.format(Locale.ROOT, "#%06X", Color.HSVToColor(hsv) & 0xFFFFFF))
                            .apply();
                    if (sesudahSimpan != null) sesudahSimpan.run();
                    sapukanKilau();
                }).show();
        rapikanTombolDialog(dialog);
    }


    /** Tab Pengaturan terakhir; dibuka lagi di tab yang sama selama aplikasi hidup. */
    private int tabPengaturan;

    /**
     * Menu tarik-turun satu baris untuk pilihan {kunci, label}. Dipanggil
     * hanya bila pengguna benar-benar mengganti pilihan, bukan saat menu
     * pertama kali dipasang.
     */
    private android.widget.Spinner pilihanTarik(
            String[][] pilihan, String terpilih, java.util.function.Consumer<String> saatDipilih) {
        String[] label = new String[pilihan.length];
        int awal = 0;
        for (int i = 0; i < pilihan.length; i++) {
            label[i] = pilihan[i][1];
            if (pilihan[i][0].equals(terpilih)) awal = i;
        }
        android.widget.Spinner menu = new android.widget.Spinner(this);
        android.widget.ArrayAdapter<String> isi = new android.widget.ArrayAdapter<String>(
                this, android.R.layout.simple_spinner_item, label) {
            @Override
            public View getView(int posisi, View lama, android.view.ViewGroup induk) {
                TextView t = (TextView) super.getView(posisi, lama, induk);
                t.setTextColor(INK);
                t.setTextSize(15 * uiScale);
                return t;
            }
        };
        isi.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        menu.setAdapter(isi);
        menu.setSelection(awal, false);
        menu.setPadding(dp(6), dp(4), dp(6), dp(4));
        menu.setBackground(roundedOutline(LATAR, GARIS, dp(12), dp(1)));
        int[] terakhir = {awal};
        menu.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(android.widget.AdapterView<?> induk, View tampilan,
                                       int posisi, long id) {
                if (posisi == terakhir[0]) return;
                terakhir[0] = posisi;
                saatDipilih.accept(pilihan[posisi][0]);
            }

            @Override
            public void onNothingSelected(android.widget.AdapterView<?> induk) {
            }
        });
        return menu;
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

    /**
     * Tutup aplikasi sepenuhnya, misalnya untuk membuka Pengaturan Android
     * atau mematikan tablet. Dikonfirmasi dulu: tombolnya berada di dialog
     * yang dapat dibuka siapa pun lewat ikon roda gigi.
     */
    private void konfirmasiKeluar(AlertDialog pengaturan) {
        AlertDialog tanya = pembuatDialog()
                .setTitle("Keluar dari aplikasi?")
                .setMessage("Anjungan berhenti menerbitkan nomor sampai aplikasi "
                        + "dibuka lagi dari layar utama tablet.")
                .setNegativeButton("Batal", null)
                .setPositiveButton("Keluar", (d, w) -> {
                    pengaturan.dismiss();
                    finishAndRemoveTask();
                })
                .create();
        if (tanya.getWindow() != null) {
            tanya.getWindow().setBackgroundDrawable(rounded(LATAR, dp(28)));
        }
        tanya.show();
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

    /**
     * Kelola media tablet: ringkasan (jumlah, ukuran, sumber aktif, sisa ruang),
     * daftar dikelompokkan Video dan Gambar dengan gambar mini, lencana tempat
     * tampil, dan menu Aksi per berkas. Dialog dibuka ulang sesudah tiap aksi.
     */
    private void showMediaTablet() {
        List<File> berkas = daftarMediaTablet();
        List<File> daftarVideo = new ArrayList<>();
        List<File> daftarGambar = new ArrayList<>();
        long total = 0L;
        for (File item : berkas) {
            total += item.length();
            (BerkasMedia.isVideo(item.getName()) ? daftarVideo : daftarGambar).add(item);
        }
        AlertDialog[] dialog = new AlertDialog[1];
        LinearLayout isi = new LinearLayout(this);
        isi.setOrientation(LinearLayout.VERTICAL);
        isi.setPadding(dp(20), dp(4), dp(20), 0);

        LinearLayout kepala = new LinearLayout(this);
        kepala.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout teksKepala = new LinearLayout(this);
        teksKepala.setOrientation(LinearLayout.VERTICAL);
        teksKepala.addView(text(berkas.isEmpty() ? "Belum ada berkas"
                : berkas.size() + " berkas · " + BerkasMedia.formatUkuran(total), 14, INK, true));
        TextView sumber = text("Sumber aktif: "
                + (sumberTablet() ? "folder tablet, diputar tanpa jaringan"
                : "server (berkas di sini dipakai bila sumber diganti ke folder tablet)")
                + " · sisa ruang " + BerkasMedia.formatUkuran(sisaRuangTablet()), 12, MUTED, false);
        teksKepala.addView(sumber);
        TextView belumSalin = text("", 12, UTAMA, true);
        belumSalin.setVisibility(View.GONE);
        belumSalin.setOnClickListener(v -> {
            if (dialog[0] != null) dialog[0].dismiss();
            tampilkanPustakaServer();
        });
        teksKepala.addView(belumSalin);
        kepala.addView(teksKepala, new LinearLayout.LayoutParams(0, -2, 1));
        if (!berkas.isEmpty()) {
            Button lainnya = smallButton("Lainnya");
            lainnya.setOnClickListener(v -> {
                android.widget.PopupMenu menu = new android.widget.PopupMenu(this, v);
                menu.getMenu().add(0, 1, 0, "Hapus semua berkas");
                menu.setOnMenuItemClickListener(item -> {
                    konfirmasiHapusSemuaMedia(berkas.size(), dialog);
                    return true;
                });
                menu.show();
            });
            kepala.addView(lainnya);
        }
        isi.addView(kepala);

        if (berkas.isEmpty()) {
            TextView kosong = text("Belum ada media di tablet ini. Salin dari server atau "
                    + "tambah dari tablet; sampai ada berkas, panel menampilkan teks sambutan.",
                    14, INK, false);
            kosong.setPadding(0, dp(14), 0, dp(4));
            isi.addView(kosong);
            Button salin = actionButton("Salin dari server", true);
            salin.setOnClickListener(v -> {
                if (dialog[0] != null) dialog[0].dismiss();
                tampilkanPustakaServer();
            });
            isi.addView(salin, tombolPengaturan());
            Button tambah = actionButton("Tambah berkas", false);
            tambah.setOnClickListener(v -> {
                if (dialog[0] != null) dialog[0].dismiss();
                pilihMediaTablet();
            });
            isi.addView(tambah, tombolPengaturan());
        } else {
            tambahBagianMedia(isi, "Video", daftarVideo, dialog);
            tambahBagianMedia(isi, "Gambar", daftarGambar, dialog);
        }

        dialog[0] = pembuatDialog()
                .setTitle("Media di tablet ini")
                .setView(gulungan(isi))
                .setPositiveButton("Salin dari server", (d, w) -> tampilkanPustakaServer())
                .setNeutralButton("Tambah berkas", (d, w) -> pilihMediaTablet())
                .setNegativeButton("Tutup", null)
                .show();
        rapikanTombolDialog(dialog[0]);
        tandaiBelumDisalin(belumSalin, dialog[0]);
    }

    private void tambahBagianMedia(
            LinearLayout isi, String judul, List<File> daftar, AlertDialog[] dialog) {
        if (daftar.isEmpty()) return;
        TextView kepala = text(judul + " (" + daftar.size() + ")", 13, MUTED, true);
        kepala.setPadding(0, dp(14), 0, dp(2));
        isi.addView(kepala);
        for (File item : daftar) tambahBarisMedia(isi, item, dialog);
    }

    private void tambahBarisMedia(LinearLayout isi, File item, AlertDialog[] dialog) {
        boolean video = BerkasMedia.isVideo(item.getName());
        LinearLayout baris = new LinearLayout(this);
        baris.setGravity(Gravity.CENTER_VERTICAL);
        baris.setPadding(0, dp(6), 0, dp(6));

        FrameLayout bingkai = new FrameLayout(this);
        ImageView gambar = new ImageView(this);
        gambar.setScaleType(ImageView.ScaleType.CENTER_CROP);
        gambar.setBackground(rounded(LEMBUT, dp(8)));
        gambar.setClipToOutline(true);
        bingkai.addView(gambar, new FrameLayout.LayoutParams(dp(72), dp(48)));
        if (video) {
            TextView putar = text("▶", 16, Color.WHITE, true);
            putar.setGravity(Gravity.CENTER);
            putar.setShadowLayer(dp(3), 0f, 0f, Color.BLACK);
            bingkai.addView(putar, new FrameLayout.LayoutParams(dp(72), dp(48)));
        }
        baris.addView(bingkai, new LinearLayout.LayoutParams(dp(72), dp(48)));

        LinearLayout kolom = new LinearLayout(this);
        kolom.setOrientation(LinearLayout.VERTICAL);
        kolom.setPadding(dp(10), 0, dp(8), 0);
        TextView nama = text(item.getName(), 13, INK, true);
        nama.setSingleLine(true);
        nama.setEllipsize(android.text.TextUtils.TruncateAt.MIDDLE);
        kolom.addView(nama);
        String dasarInfo = (video ? "video" : "gambar") + " · " + BerkasMedia.formatUkuran(item.length());
        TextView info = text(dasarInfo, 12, MUTED, false);
        kolom.addView(info);
        String tempat = tampilLokal(item.getName());
        TextView lencana = text(labelTempatLokal(tempat), 11, UTAMA, true);
        lencana.setBackground(rounded((UTAMA & 0x00FFFFFF) | 0x26000000, dp(10)));
        lencana.setPadding(dp(8), dp(2), dp(8), dp(2));
        LinearLayout.LayoutParams paramLencana = new LinearLayout.LayoutParams(-2, -2);
        paramLencana.topMargin = dp(3);
        kolom.addView(lencana, paramLencana);
        baris.addView(kolom, new LinearLayout.LayoutParams(0, -2, 1));

        Button aksi = smallButton("Aksi");
        aksi.setOnClickListener(v -> {
            android.widget.PopupMenu menu = new android.widget.PopupMenu(this, v);
            menu.getMenu().add(0, 1, 0, (tempat.equals("panel") ? "✓ " : "") + "Tampil di panel atas");
            menu.getMenu().add(0, 2, 1, (tempat.equals("penuh") ? "✓ " : "") + "Tampil di layar penuh");
            menu.getMenu().add(0, 3, 2, (tempat.equals("keduanya") ? "✓ " : "") + "Tampil di keduanya");
            menu.getMenu().add(0, 4, 3, "Hapus");
            menu.setOnMenuItemClickListener(pilihan -> {
                int id = pilihan.getItemId();
                if (id == 4) {
                    konfirmasiHapusMedia(item, dialog);
                    return true;
                }
                aturTampilLokal(item.getName(),
                        id == 1 ? "panel" : id == 2 ? "penuh" : "keduanya");
                terapkanMediaSambutan();
                terapkanBarisLoket();
                if (dialog[0] != null) dialog[0].dismiss();
                showMediaTablet();
                return true;
            });
            menu.show();
        });
        baris.addView(aksi);
        isi.addView(baris);
        muatThumbnail(item, video, gambar, info, dasarInfo);
    }

    private void konfirmasiHapusMedia(File item, AlertDialog[] dialog) {
        pembuatDialog()
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
                }).show();
    }

    private void konfirmasiHapusSemuaMedia(int jumlah, AlertDialog[] dialog) {
        pembuatDialog()
                .setTitle("Hapus semua berkas?")
                .setMessage("Seluruh " + jumlah + " berkas dihapus dari tablet ini. "
                        + "Berkas di server tidak terpengaruh.")
                .setNegativeButton("Batal", null)
                .setPositiveButton("Hapus semua", (d, w) -> {
                    for (File item : daftarMediaTablet()) {
                        //noinspection ResultOfMethodCallIgnored
                        item.delete();
                    }
                    terapkanMediaSambutan();
                    terapkanBarisLoket();
                    if (dialog[0] != null) dialog[0].dismiss();
                    showMediaTablet();
                }).show();
    }

    /** Gambar mini (dan durasi video) dibuat di latar belakang lalu disimpan di cache. */
    private void muatThumbnail(
            File item, boolean video, ImageView gambar, TextView info, String dasarInfo) {
        String kunci = item.getName() + "|" + item.lastModified() + "|" + item.length();
        Bitmap ada = cacheThumbnail.get(kunci);
        Long durasiAda = cacheDurasi.get(kunci);
        if (ada != null) gambar.setImageBitmap(ada);
        if (durasiAda != null) info.setText(dasarInfo + " · " + BerkasMedia.formatDurasi(durasiAda));
        if (ada != null && (!video || durasiAda != null)) return;
        pembuatThumbnail.execute(() -> {
            Bitmap hasil = null;
            long durasi = -1L;
            try {
                if (video) {
                    android.media.MediaMetadataRetriever pembaca =
                            new android.media.MediaMetadataRetriever();
                    try {
                        pembaca.setDataSource(item.getPath());
                        String teks = pembaca.extractMetadata(
                                android.media.MediaMetadataRetriever.METADATA_KEY_DURATION);
                        if (teks != null) durasi = Long.parseLong(teks);
                        Bitmap bingkaiPertama = pembaca.getFrameAtTime(0L,
                                android.media.MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
                        if (bingkaiPertama != null) hasil = BerkasMedia.perkecilThumbnail(bingkaiPertama);
                    } finally {
                        pembaca.release();
                    }
                } else {
                    BitmapFactory.Options batas = new BitmapFactory.Options();
                    batas.inJustDecodeBounds = true;
                    BitmapFactory.decodeFile(item.getPath(), batas);
                    int sampel = 1;
                    while (batas.outWidth / (sampel * 2) >= 288) sampel *= 2;
                    BitmapFactory.Options opsi = new BitmapFactory.Options();
                    opsi.inSampleSize = sampel;
                    Bitmap besar = BitmapFactory.decodeFile(item.getPath(), opsi);
                    if (besar != null) hasil = BerkasMedia.perkecilThumbnail(besar);
                }
            } catch (Exception | OutOfMemoryError ignored) {
                // Berkas rusak atau tidak terbaca: baris tetap tampil tanpa gambar mini.
            }
            final Bitmap akhir = hasil;
            final long lama = durasi;
            if (akhir != null) cacheThumbnail.put(kunci, akhir);
            if (lama > 0L) cacheDurasi.put(kunci, lama);
            handler.post(() -> {
                if (akhir != null) gambar.setImageBitmap(akhir);
                if (lama > 0L) info.setText(dasarInfo + " · " + BerkasMedia.formatDurasi(lama));
            });
        });
    }

    /** Beri tahu bila ada berkas di server yang belum ada di folder tablet. */
    private void tandaiBelumDisalin(TextView penanda, AlertDialog dialog) {
        if (!hasServerConfig()) return;
        request("GET", "/v1/kiosk/media-library", null, json -> {
            JSONArray baris = json.getJSONArray("data");
            java.util.Set<String> ada = new java.util.HashSet<>();
            for (File item : daftarMediaTablet()) ada.add(item.getName());
            int belum = 0;
            for (int i = 0; i < baris.length(); i++) {
                if (!ada.contains(BerkasMedia.namaAman(baris.getJSONObject(i).getString("name")))) belum++;
            }
            if (belum > 0 && dialog.isShowing()) {
                penanda.setText(belum + " berkas di server belum ada di tablet. Ketuk untuk menyalin.");
                penanda.setVisibility(View.VISIBLE);
            }
        }, pesan -> {
            // Server lama atau tidak terjangkau: penanda ini tidak penting, diam saja.
        });
    }

    private long sisaRuangTablet() {
        try {
            return new android.os.StatFs(folderMediaTablet().getPath()).getAvailableBytes();
        } catch (Exception e) {
            return 0L;
        }
    }

    /**
     * "Salin dari server": daftar SEMUA berkas di folder media server (bukan
     * hanya daftar putar), dipilih lalu disalin ke folder media tablet. Dipakai
     * bila tablet memutar dari "Folder media di tablet ini" tanpa jaringan.
     */
    private void tampilkanPustakaServer() {
        if (!hasServerConfig()) {
            Toast.makeText(this, "Alamat server belum diatur.", Toast.LENGTH_LONG).show();
            return;
        }
        Toast.makeText(this, "Mengambil daftar media dari server…", Toast.LENGTH_SHORT).show();
        request("GET", "/v1/kiosk/media-library", null, json -> {
            JSONArray baris = json.getJSONArray("data");
            if (baris.length() == 0) {
                Toast.makeText(this, "Folder media di server masih kosong.",
                        Toast.LENGTH_LONG).show();
                return;
            }
            String[] nama = new String[baris.length()];
            String[] label = new String[baris.length()];
            boolean[] dipilih = new boolean[baris.length()];
            for (int i = 0; i < baris.length(); i++) {
                JSONObject item = baris.getJSONObject(i);
                nama[i] = item.getString("name");
                label[i] = nama[i] + "\n" + (item.optBoolean("video") ? "video" : "gambar")
                        + " · " + String.format(Locale.ROOT, "%.1f MB",
                        item.optLong("size", 0L) / 1048576.0);
            }
            AlertDialog dialog = pembuatDialog()
                    .setTitle("Salin dari server")
                    .setMultiChoiceItems(label, dipilih, (d, i, ya) -> dipilih[i] = ya)
                    .setNegativeButton("Batal", null)
                    .setPositiveButton("Salin ke tablet", (d, w) -> {
                        List<String> terpilih = new ArrayList<>();
                        for (int i = 0; i < nama.length; i++) {
                            if (dipilih[i]) terpilih.add(nama[i]);
                        }
                        salinDariServer(terpilih);
                    })
                    .show();
            rapikanTombolDialog(dialog);
        }, pesan -> Toast.makeText(this, "Tidak dapat mengambil daftar media: " + pesan,
                Toast.LENGTH_LONG).show());
    }

    private void salinDariServer(List<String> terpilih) {
        if (terpilih.isEmpty()) return;
        Toast.makeText(this, "Menyalin " + terpilih.size() + " berkas dari server…",
                Toast.LENGTH_SHORT).show();
        File folder = folderMediaTablet();
        String basis = preferences.getString(SERVER, "").trim().replaceAll("/+$", "");
        pengunduh.execute(() -> {
            int berhasil = 0;
            List<String> gagal = new ArrayList<>();
            for (String nama : terpilih) {
                try {
                    UnduhServer.keBerkasGanti(
                            basis + "/v1/kiosk/media-library/" + Uri.encode(nama),
                            folder, BerkasMedia.namaAman(nama), CADANGAN_RUANG_BYTES, this::applyHeaders);
                    berhasil++;
                } catch (Exception e) {
                    gagal.add(nama);
                }
            }
            int jumlah = berhasil;
            runOnUiThread(() -> {
                String pesan = jumlah + " berkas disalin ke folder tablet."
                        + (gagal.isEmpty() ? ""
                        : " Gagal: " + TextUtils.join(", ", gagal));
                Toast.makeText(this, pesan, Toast.LENGTH_LONG).show();
                terapkanMediaSambutan();
                terapkanBarisLoket();
                showMediaTablet();
            });
        });
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
                if (nama == null || !BerkasMedia.berakhiran(nama, BerkasMedia.EKSTENSI_MEDIA)) {
                    ditolak.add(nama == null ? uri.getLastPathSegment() : nama);
                    continue;
                }
                File tujuan = new File(folder, BerkasMedia.namaAman(nama));
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

                // Semua jawaban dikumpulkan, bukan yang pertama saja: bila
                // dua komputer menjawab (API ikut menyala di PC loket, atau
                // perangkat asing), tablet tidak boleh memilih salah satunya
                // diam-diam lalu mengirim token ke sana.
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
                    JSONObject data;
                    try {
                        data = new JSONObject(new String(
                                response.getData(), response.getOffset(),
                                response.getLength(), StandardCharsets.UTF_8));
                    } catch (org.json.JSONException bukanServer) {
                        continue;
                    }
                    if (!DISCOVERY_RESPONSE.equals(data.optString("service"))) continue;
                    int port = data.optInt("api_port", 8765);
                    if (port < 1 || port > 65535) continue;
                    if (addresses.isEmpty()) {
                        // Jawaban lain dari jaringan yang sama datang dalam sekejap.
                        deadline = Math.min(deadline, System.currentTimeMillis() + 1500);
                    }
                    addresses.add("http://" + response.getAddress().getHostAddress()
                            + ":" + port);
                }
                if (addresses.size() == 1) {
                    String address = addresses.iterator().next();
                    handler.post(() -> found.accept(address));
                } else if (addresses.size() > 1) {
                    String daftar = android.text.TextUtils.join(", ", addresses);
                    handler.post(() -> failed.accept("Lebih dari satu server menjawab ("
                            + daftar + "). Isi alamat server yang benar di Pengaturan."));
                } else {
                    handler.post(() -> failed.accept(
                            "Pastikan server berjalan dan perangkat berada di Wi-Fi/LAN yang sama."));
                }
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
     * Label satu baris: huruf mengecil sampai seluruh tulisan muat selebar
     * kotaknya, tidak pernah pecah dua baris atau terpotong "…".
     *
     * Lebar tulisan diukur sendiri, bukan lewat autosize Android: autosize
     * diam saja pada teks yang tingginya wrap_content, dan teks itu lalu
     * terbungkus ke baris kedua yang tersembunyi ("Lihat pilihan layanan"
     * tampil "Lihat pilihan"). Cara ini juga sama di Android 7.
     */
    private void pasangSatuBaris(TextView view, int minimumSp, int maksimumSp) {
        view.setSingleLine(true);
        view.setEllipsize(null);
        view.setIncludeFontPadding(false);
        float kepadatan = getResources().getDisplayMetrics().scaledDensity;
        float maksPx = maksimumSp * uiScale * kepadatan;
        float minPx = minimumSp * uiScale * kepadatan;
        view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX, maksPx);
        Runnable pas = () -> {
            int lebar = view.getWidth() - view.getTotalPaddingLeft() - view.getTotalPaddingRight();
            if (lebar <= 0) return;
            android.text.TextPaint ukur = new android.text.TextPaint(view.getPaint());
            ukur.setTextSize(maksPx);
            float perlu = ukur.measureText(view.getText().toString());
            float ukuran = perlu <= lebar ? maksPx
                    : Math.max(minPx, (float) Math.floor(maksPx * lebar / perlu * 0.97f));
            // Lebar huruf tidak persis sebanding ukurannya: periksa lagi.
            String isi = view.getText().toString();
            while (ukuran > minPx) {
                ukur.setTextSize(ukuran);
                if (ukur.measureText(isi) <= lebar) break;
                ukuran -= 1f;
            }
            if (Math.abs(view.getTextSize() - ukuran) > 0.5f) {
                view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX, ukuran);
            }
        };
        view.addOnLayoutChangeListener((v, kiri, atas, kanan, bawah,
                                        kiriLama, atasLama, kananLama, bawahLama) -> {
            if (kanan - kiri != kananLama - kiriLama) v.post(pas);
        });
        view.addTextChangedListener(new android.text.TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence teks, int awal, int jumlah, int sesudah) {
            }

            @Override
            public void onTextChanged(CharSequence teks, int awal, int sebelum, int jumlah) {
            }

            @Override
            public void afterTextChanged(android.text.Editable teks) {
                view.post(pas);
            }
        });
        view.post(pas);
    }


    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size * uiScale);
        view.setTextColor(color);
        view.setTypeface(huruf(bold ? 700 : 400));
        return view;
    }

    private int dp(int value) {
        return Math.round(value * uiScale * getResources().getDisplayMetrics().density);
    }

    /**
     * Ubin nomor menunggu yang hampir datar: muka dengan gradasi tipis di
     * atas "tebing" setebal 1 dp. Dulu tebingnya 3 dp dengan muka sangat
     * terang, sehingga nomor menunggu terbaca seperti tombol timbul yang
     * bersaing dengan kartu layanan. Tanpa elevation, sehingga bayangan tidak
     * terpotong baris induk dan animasi pop ubin tetap mulus.
     */
    private android.graphics.drawable.Drawable ubinTimbul(int warna, int radius) {
        int tebing = campur(warna, Color.BLACK, 0.10f);
        int atas = campur(warna, Color.WHITE, 0.12f);
        GradientDrawable muka = roundedGradient(atas, warna, radius,
                campur(warna, Color.BLACK, 0.05f), dp(1));
        android.graphics.drawable.LayerDrawable lapis =
                new android.graphics.drawable.LayerDrawable(
                        new android.graphics.drawable.Drawable[]{rounded(tebing, radius), muka});
        lapis.setLayerInset(1, 0, 0, 0, dp(1));
        return lapis;
    }

    private StateListDrawable stateOutline(int normal, int pressed, int radius) {
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_pressed},
                roundedOutline(pressed, UTAMA, radius, dp(2)));
        states.addState(new int[]{}, roundedOutline(normal, GARIS, radius, dp(2)));
        return states;
    }

    @Override
    protected void onDestroy() {
        try {
            unregisterReceiver(installReceiver);
        } catch (IllegalArgumentException ignored) {
            // Belum terdaftar.
        }
        handler.removeCallbacksAndMessages(null);
        tutupBannerCetakUlang();
        hentikanKilauAjakan();
        hentikanDenyutAjakanIklan();
        antreanUcapan.clear();
        lepasPemutarKlip();
        if (tts != null) tts.shutdown();
        if (nada != null) nada.release();
        worker.shutdownNow();
        penerbit.shutdownNow();
        pengunduh.shutdownNow();
        pemanggil.shutdownNow();
        pembuatThumbnail.shutdownNow();
        super.onDestroy();
    }
}
