r"""
Titik masuk aplikasi.

    .\.venv\Scripts\python.exe -m app.main

Urutan yang dijalankan:

    siapkan database -> masuk -> jendela utama

Argumen:
    --tv          langsung membuka layar antrian ruang tunggu, tanpa dialog
                  pilihan dan tanpa login. Cadangan sampai aplikasi layar
                  antrian Android siap (docs/istilah.md).
    --admin       langsung membuka layar loket sebagai administrator.
                  Tetap minta nama dan sandi: beberapa petugas berbagi
                  komputer yang sama.
    --petugas     langsung membuka layar loket. Tetap minta nama dan sandi.
    --init-only   hanya siapkan database lalu keluar, tanpa membuka jendela.
                  Berguna untuk memeriksa pemasangan di komputer baru.
    --setup       buka dialog peran komputer ini (satu komputer / server /
                  klien) sebelum menyambung ke database. Bukan deteksi
                  jaringan: orang yang memasang yang menunjuk.
    --kios-api    jalankan API aplikasi server untuk anjungan Android.
    --jendela     buka layar antrian sebagai jendela, bukan layar penuh.

Anjungan tidak lagi berjalan di Windows: anjungan adalah tablet Android
(docs/istilah.md). Layar antrian dipasang dengan --tv supaya pulih sendiri
setelah mati listrik, tanpa perlu ada yang mengklik apa pun.
"""

from __future__ import annotations

import sys

from app.core.config import APP_NAME, get_config, lewati_login_pengembang, reset_config
from app.core.database import dispose_engine, init_database
from app.core.logger import get_logger, setup_logging
from app.core.migrations import current_revision
from app.core.seed import seed_initial_data

logger = get_logger("main")

#: Selang pemeriksaan pergantian tanggal, dalam milidetik.
#:
#: Semenit sekali. Yang dikerjakan hanya membandingkan dua tanggal di
#: memori — database baru disentuh pada satu pemeriksaan dalam sehari,
#: yaitu yang pertama sesudah tengah malam.
SELANG_PERIKSA_HARI_MS = 60_000


def pasang_ikon(app) -> None:
    """
    Ikon jendela dan taskbar. Ikon .exe sendiri dipasang PyInstaller.

    Berkas yang hilang tidak menghentikan apa pun: aplikasi tetap jalan
    dengan ikon bawaan Qt.
    """
    from PySide6.QtGui import QIcon

    from app.core.config import resource_dir

    berkas = resource_dir() / "assets" / "ikon" / "antrian.ico"
    if berkas.is_file():
        app.setWindowIcon(QIcon(str(berkas)))


def siapkan_database() -> dict[str, int]:
    """Jalankan migration dan isi data master awal."""
    init_database()
    return seed_initial_data()


def backup_harian() -> None:
    """
    Buat backup harian sebelum aplikasi dipakai.

    Dijalankan setelah migration supaya yang tersalin adalah database yang
    skemanya sudah terbaru. Kegagalannya tidak pernah menghentikan aplikasi —
    kehilangan backup satu hari jauh lebih ringan akibatnya daripada loket
    yang tidak bisa melayani sama sekali.
    """
    from app.services.auth_service import get_auth_service
    from app.services.backup_service import BackupService

    hasil = BackupService(get_auth_service()).backup_otomatis_bila_perlu()
    logger.info("Backup otomatis: %s", hasil.pesan)


def hanguskan_antrian_hari_lalu() -> int:
    """
    Hanguskan nomor sisa hari-hari sebelumnya, dan kembalikan jumlahnya.

    Pergantian hari sudah mengakhiri antrian di mata pengunjung: seluruh
    layar dan daftar loket disaring `queue_date == hari ini`, sehingga
    nomor kemarin tidak pernah tampil maupun terpanggil. Yang belum ikut
    berakhir hanyalah statusnya di basis data.

    Kegagalannya tidak pernah menghentikan aplikasi, sama seperti backup
    harian di atas: laporan yang keliru satu hari jauh lebih ringan
    akibatnya daripada loket yang tidak bisa melayani sama sekali.
    """
    from app.services.auth_service import get_auth_service
    from app.services.queue_service import QueueService

    try:
        jumlah = QueueService(get_auth_service()).hanguskan_hari_lalu()
    except Exception:
        logger.exception("Sapuan nomor antrian hari lalu gagal")
        return 0
    if jumlah:
        logger.info("Nomor antrian hari lalu hangus: %d nomor", jumlah)
    return jumlah


def anonimkan_pengaduan_lama() -> int:
    """
    Kosongkan identitas pelapor yang melewati masa simpannya.

    Terpisah dari sapuan nomor antrian supaya gagalnya yang satu tidak
    membatalkan yang lain, dan sama-sama tidak pernah menghentikan
    aplikasi.
    """
    from app.services.auth_service import get_auth_service
    from app.services.note_service import NoteService

    try:
        return NoteService(get_auth_service()).anonimkan_kedaluwarsa()
    except Exception:
        logger.exception("Anonimisasi identitas pelapor gagal")
        return 0


class PenyapuHarian:
    """
    Menjalankan sapuan begitu tanggal berganti, tanpa aplikasi dibuka ulang.

    Sapuan saat aplikasi mulai saja tidak cukup di sini: anjungan dan layar
    ruang tunggu dipasang untuk menyala terus dan pulih sendiri setelah
    mati listrik, sehingga keduanya bisa berhari-hari tidak pernah dimulai
    ulang — dan justru dua mesin itulah yang paling lama menyala.

    Yang dibandingkan tanggal, bukan hitungan mundur menuju tengah malam.
    Komputer yang tertidur atau jamnya dikoreksi membuat hitungan mundur
    meleset tanpa ketahuan, sedangkan tanggal yang berbeda tetap berbeda
    walau pemeriksaannya terlambat setengah jam.
    """

    def __init__(self, hari_awal=None) -> None:
        from app.core import clock

        #: Tanggal yang sapuannya sudah dianggap selesai. Diisi hari ini,
        #: bukan kosong: sapuan awal di `main()` sudah menanganinya, dan
        #: mengulangnya sedetik kemudian hanya menambah satu query.
        self.hari = hari_awal or clock.today()

    def periksa(self) -> int:
        """Sapu bila tanggal sudah berganti. Kembalikan jumlah yang hangus."""
        from app.core import clock

        hari = clock.today()
        if hari == self.hari:
            return 0
        logger.info("Tanggal berganti: %s -> %s", self.hari, hari)
        # Tanggalnya dicatat SEBELUM menyapu. Bila sapuannya gagal —
        # database sedang tidak terjangkau tengah malam — pemeriksaan
        # semenit lagi tidak boleh mencobanya berulang-ulang sepanjang
        # hari; sapuan berikutnya toh berjalan saat aplikasi dibuka lagi.
        self.hari = hari
        jumlah = hanguskan_antrian_hari_lalu()
        anonimkan_pengaduan_lama()
        return jumlah


def _laporkan_kegagalan_database(config, *, berjendela: bool) -> bool:
    """
    Beri tahu petugas bahwa database tidak dapat dihubungi.

    Wajib berupa jendela, bukan sekadar print. Aplikasi didistribusikan
    sebagai .exe berjendela yang tidak punya terminal, sehingga tanpa ini
    petugas hanya melihat aplikasi gagal terbuka tanpa keterangan apa pun.

    Kegagalan seperti ini menjadi hal biasa begitu database berada di
    komputer lain: server belum menyala, kabel jaringan terlepas, atau
    alamatnya salah ketik.

    Kata sandi database TIDAK pernah ikut ditampilkan.

    True bila petugas memilih mengubah koneksi, supaya percobaan berikutnya
    memakai alamat baru tanpa menutup proses.
    """
    try:
        tujuan = config.url_database.render_as_string(hide_password=True)
    except ValueError:
        tujuan = "PostgreSQL belum diatur"
    pesan = (
        "Aplikasi tidak dapat menghubungi database.\n\n"
        f"Database  : {tujuan}\n"
        f"Detail    : {config.log_dir / 'app.log'}\n\n"
        "Pastikan komputer server menyala dan jaringan tersambung, "
        "lalu buka kembali aplikasi ini."
    )

    print(pesan, file=sys.stderr)
    if not berjendela:
        return False

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        from app.ui.style import STYLESHEET

        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        pasang_ikon(app)
        app.setStyleSheet(STYLESHEET)
        kotak = QMessageBox()
        kotak.setIcon(QMessageBox.Icon.Critical)
        kotak.setWindowTitle(APP_NAME)
        kotak.setText("Aplikasi tidak dapat menghubungi database.")
        kotak.setInformativeText(pesan)
        tutup = kotak.addButton("Tutup", QMessageBox.ButtonRole.RejectRole)
        kotak.addButton("Ubah koneksi", QMessageBox.ButtonRole.ActionRole)
        kotak.setDefaultButton(tutup)
        kotak.exec()
        return kotak.clickedButton() is not tutup
    except Exception:
        # Qt sendiri gagal dimuat. Tidak ada lagi yang bisa ditampilkan;
        # yang penting aplikasi berhenti dengan rapi, bukan menumpuk error.
        logger.exception("Pesan kegagalan database tidak dapat ditampilkan")
        return False


def _jalankan_ui(
    *,
    mode_awal: str | None = None,
    berjendela: bool | None = None,
) -> int:
    """
    Buka aplikasi berjendela. Import Qt ditunda sampai benar-benar dipakai.

    Aplikasi Windows biasa langsung membuka layar masuk:

        ganti kata sandi wajib dibatalkan -> kembali ke layar masuk
        layar masuk ditutup               -> aplikasi berhenti
        mesin publik lama ditutup         -> aplikasi berhenti

    Petugas yang logout kembali langsung ke layar masuk. Mode layar antrian
    hanya tersisa sebagai kompatibilitas untuk argumen --tv lama; ia tidak
    pernah lagi ditawarkan pada alur pembukaan biasa.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog

    from app.services.auth_service import get_auth_service
    from app.ui.login.change_password_dialog import ChangePasswordDialog
    from app.ui.login.login_window import LoginWindow
    from app.ui.login.mode_dialog import LAYAR_ANTRIAN
    from app.ui.main_window import MainWindow
    from app.ui.style import STYLESHEET
    from app.ui.tema_petugas import baca_tema, terapkan_tema

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    pasang_ikon(app)
    app.setStyleSheet(STYLESHEET)
    # Tema pilihan petugas di komputer ini (tab Tampilan).
    terapkan_tema(app, baca_tema())

    # Diinduk pada `app`, bukan pada jendela: jendela dibuka dan ditutup
    # berkali-kali oleh loop di bawah — setiap logout membuat yang baru —
    # sedangkan pergantian hari harus tetap terpantau di antaranya.
    penyapu = PenyapuHarian()
    pewaktu_hari = QTimer(app)
    pewaktu_hari.timeout.connect(penyapu.periksa)
    pewaktu_hari.start(SELANG_PERIKSA_HARI_MS)

    auth = get_auth_service()
    if mode_awal == LAYAR_ANTRIAN:
        # Jalur kompatibilitas bagi pintasan --tv lama. Tidak ada lagi tombol
        # yang dapat membukanya dari aplikasi Windows biasa.
        auth.mulai_sesi_layar()
        jendela = MainWindow(auth, berjendela=berjendela)
        jendela.tampilkan()
        app.exec()
        return 0

    # Beberapa petugas berbagi satu komputer, jadi nama dan sandi selalu
    # diminta. Logout mengulang loop ini; menutup login mengakhiri aplikasi.
    while True:
        login = LoginWindow(auth)
        if login.exec() != QDialog.DialogCode.Accepted:
            logger.info("Layar masuk ditutup; aplikasi berhenti")
            return 0

        sesi = auth.require_session()

            # Akun dengan kata sandi bawaan tidak boleh dipakai bekerja
            # sebelum kata sandinya diganti. Membatalkannya mengembalikan ke
            # layar masuk, bukan menutup aplikasi: petugas lain yang kata
            # sandinya sudah benar masih bisa langsung memakai loketnya.
        if sesi.must_change_password:
            dialog = ChangePasswordDialog(auth, wajib=True)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                auth.logout()
                logger.info("Kata sandi wajib tidak diganti, kembali ke layar masuk")
                continue

        jendela = MainWindow(auth)
        jendela.tampilkan()
        app.exec()
        # petugas logout -> kembali langsung ke layar masuk


def mode_dari_argumen(argv: list[str]) -> str | None:
    """
    Mode mesin yang diminta lewat baris perintah, atau None bila tidak ada.

    `--tv` didahulukan: papan kosong terlihat seluruh ruang tunggu.

    `--kios`, `--kios-totem`, dan `--layar` (anjungan Windows) sudah tidak
    ada; pintasan lama yang masih memakainya mengikuti alur Login Petugas.
    """
    from app.ui.login.mode_dialog import LAYAR_ADMIN, LAYAR_ANTRIAN, LAYAR_PETUGAS

    if "--tv" in argv:
        return LAYAR_ANTRIAN
    if "--admin" in argv:
        return LAYAR_ADMIN
    if "--petugas" in argv:
        return LAYAR_PETUGAS
    return None


def mode_awal_mesin(argv: list[str], db_path) -> str | None:
    """
    Mode peluncuran pertama hanya dari flag kompatibilitas baris perintah.

    Flag menang. Ia diketik untuk sekali jalan oleh orang yang sedang
    menguji sesuatu, dan tidak seharusnya kalah oleh berkas yang ditulis
    berminggu-minggu sebelumnya.

    Peran layar yang tersimpan tidak lagi mengubah aplikasi Windows menjadi
    papan antrian. Instalasi lama karena itu aman kembali ke login petugas,
    sedangkan --tv tetap tersedia sementara untuk pintasan lama yang memang
    menyebutkannya secara eksplisit.
    """
    return mode_dari_argumen(argv)


def berjendela_dari_argumen(argv: list[str]) -> bool:
    """`--jendela`: layar antrian dibuka sebagai jendela, untuk diuji di laptop."""
    return any(arg == "--jendela" or arg.startswith("--jendela=") for arg in argv)


def _mesin_publik_tanpa_jaga(argv: list[str], db_path=None) -> bool:
    """
    True bila mesin ini pulih sendiri tanpa klik.

    Hanya flag --tv lama yang masih boleh melewati dialog awal. Peran layar
    yang tersimpan sengaja diabaikan agar pembukaan biasa selalu menuju
    aplikasi petugas Windows.
    """
    return "--tv" in argv


def perlu_setup_awal(
    argv: list[str], db_path, *, sedang_uji: bool | None = None
) -> bool:
    """
    True bila .exe baru dibuka dan peran komputer ini belum ditetapkan.

    Dilewati di source (lewati login pengembang), di test, saat URL
    environment sudah diisi, dan pada pintasan mesin publik: anjungan
    yang pulih setelah mati listrik tidak boleh berhenti di dialog.
    """
    import os

    from app.core.mesin import PERAN_SAH, baca_berkas_mesin, path_berkas_mesin

    if sedang_uji is None:
        sedang_uji = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if sedang_uji:
        return False
    lewati = os.environ.get("ANTRIAN_LEWATI_SETUP", "").strip().lower()
    if lewati in {"1", "true", "ya", "yes", "on"}:
        return False
    if os.environ.get("ANTRIAN_DB_URL", "").strip():
        return False
    if "--init-only" in argv or "--kios-api" in argv:
        return False
    if "--tv" in argv:
        return False
    if lewati_login_pengembang():
        return False
    tersimpan = baca_berkas_mesin(path_berkas_mesin(db_path))
    return tersimpan is None or tersimpan.peran not in PERAN_SAH


def _harus_mulai_api_anjungan_otomatis(config, argv: list[str]) -> bool:
    """API otomatis hanya untuk peluncuran biasa pada mesin PostgreSQL server."""
    if any(arg in argv for arg in ("--kios-api", "--init-only", "--setup")):
        return False

    from app.core.mesin import SERVER, muat_pengaturan
    from app.services.kiosk_server import muat_api_otomatis

    if not muat_api_otomatis() or config.dialect != "postgresql":
        return False
    if muat_pengaturan(config.db_path).peran != SERVER:
        return False

    host = (config.url_database.host or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        logger.warning(
            "API otomatis dilewati: peran mesin SERVER tersimpan, tetapi "
            "database aktif tidak menunjuk PostgreSQL lokal."
        )
        return False
    return True


def _jalankan_dialog_mesin() -> bool:
    """
    Tampilkan dialog peran komputer ini. True bila disimpan.

    Memuat ulang konfigurasi setelah disimpan supaya percobaan koneksi
    berikutnya memakai alamat baru. Engine lama dilepas lebih dahulu.
    """
    from PySide6.QtWidgets import QApplication, QDialog

    from app.ui.login.setup_mesin_dialog import SetupMesinDialog
    from app.ui.style import STYLESHEET

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    pasang_ikon(app)
    app.setStyleSheet(STYLESHEET)

    dialog = SetupMesinDialog()
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False
    dispose_engine()
    reset_config()
    return True


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    hanya_init = "--init-only" in argv
    # API anjungan dijalankan Task Scheduler di bawah akun SYSTEM, tanpa
    # layar. Dialog galat di sana tidak terlihat siapa pun dan menahan
    # proses selamanya; lebih baik keluar dengan kode galat supaya Task
    # Scheduler mencobanya lagi semenit kemudian.
    tanpa_layar = hanya_init or "--kios-api" in argv

    config = get_config()
    setup_logging(config)

    if "--setup" in argv or perlu_setup_awal(argv, config.db_path):
        _jalankan_dialog_mesin()
        config = get_config()

    while True:
        try:
            dibuat = siapkan_database()
            from app.services.pembaruan_windows import audit_hasil_pembaruan

            audit_hasil_pembaruan(config=config)
            backup_harian()
            # SESUDAH backup: bila sapuan ini ternyata keliru, keadaan sebelum
            # disapu masih tersimpan pada backup pagi ini.
            hanguskan_antrian_hari_lalu()
            anonimkan_pengaduan_lama()
            break
        except Exception:
            # Traceback hanya masuk log, tidak pernah ditampilkan ke petugas.
            logger.exception("Inisialisasi database gagal")
            if not _laporkan_kegagalan_database(config, berjendela=not tanpa_layar):
                return 1
            if not _jalankan_dialog_mesin():
                return 1
            config = get_config()

    if hanya_init:
        # Ikut dicatat ke log, bukan hanya dicetak. Aplikasi dibangun sebagai
        # .exe berjendela sehingga tidak punya terminal — tanpa baris log ini,
        # hasil pemeriksaan pemasangan di komputer baru tidak terlihat sama
        # sekali.
        # Kata sandi database tidak boleh ikut tercetak maupun tercatat.
        ringkasan = (
            f"Database  : {config.url_database.render_as_string(hide_password=True)}\n"
            f"Revisi    : {current_revision()}\n"
            f"Seed baru : {dibuat}\n"
            "Fondasi siap."
        )
        logger.info("Pemeriksaan pemasangan:\n%s", ringkasan)
        print(ringkasan)
        dispose_engine()
        return 0

    try:
        if "--kios-api" in argv:
            from app.kiosk_api import serve

            return serve()

        if _harus_mulai_api_anjungan_otomatis(config, argv):
            from app.services.kiosk_server import mulai_api_otomatis

            if not mulai_api_otomatis(config.base_dir, config.log_dir):
                logger.warning(
                    "API anjungan tidak dimulai otomatis. Buka menu "
                    "'Layanan Anjungan' lalu tekan Pasang & nyalakan."
                )

        # Import Qt ditunda sampai jendela benar-benar dibuka, sehingga mode
        # dibaca di sini dan bukan di awal main(): --init-only harus tetap
        # berjalan di komputer yang PySide6-nya belum lengkap.
        return _jalankan_ui(
            mode_awal=mode_awal_mesin(argv, config.db_path),
            berjendela=berjendela_dari_argumen(argv),
        )
    except Exception:
        logger.exception("Kesalahan tak terduga pada aplikasi")
        print(
            "Aplikasi berhenti karena kesalahan yang tidak terduga.\n"
            f"Detail tersimpan pada: {config.log_dir / 'app.log'}",
            file=sys.stderr,
        )
        return 1
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
