r"""
Titik masuk aplikasi.

    .\.venv\Scripts\python.exe -m app.main

Urutan yang dijalankan:

    siapkan database -> pilih layar -> masuk -> jendela utama

Argumen:
    --tv          langsung membuka layar antrian ruang tunggu, tanpa dialog
                  pilihan dan tanpa login.
    --kios        langsung membuka anjungan ambil nomor, tanpa dialog
                  pilihan dan tanpa login.
    --kios-totem  langsung membuka anjungan berdiri (totem tiga pita),
                  tanpa dialog dan tanpa login.
    --layar       nama lama --kios. Dipertahankan supaya pintasan yang sudah
                  terpasang di komputer anjungan tidak mati saat aplikasi
                  diperbarui.
    --admin       langsung membuka layar admin. Dari source, masuk sebagai
                  administrator tanpa sandi; pada .exe tetap minta login.
    --petugas     langsung membuka layar petugas. Dari source, masuk sebagai
                  petugas CRO tanpa sandi; pada .exe tetap minta login.
    --init-only   hanya siapkan database lalu keluar, tanpa membuka jendela.
                  Berguna untuk memeriksa pemasangan di komputer baru.
    --setup       buka dialog peran komputer ini (satu komputer / server /
                  klien) sebelum menyambung ke database. Bukan deteksi
                  jaringan: orang yang memasang yang menunjuk.
    --jendela[=PERSEN]
                  buka mesin publik sebagai jendela, bukan layar penuh.
                  Totem tampil sebagai miniatur tegak dari 1080×1920:
                  sebesar yang muat di layar, paling besar 50%, atau
                  sebesar PERSEN yang diminta (mis. --jendela=40, supaya
                  layar antrian muat di sebelahnya) — tetapi tidak pernah
                  melebihi yang muat. Totem yang dibuka di layar mendatar
                  (laptop) otomatis tampil begini, juga bila dipilih lewat
                  dialog pilihan yang tidak bisa menulis argumen ini.

Kedua mesin publik dipasang dengan argumennya masing-masing supaya pulih
sendiri setelah mati listrik, tanpa perlu ada yang mengklik apa pun.
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
        return hanguskan_antrian_hari_lalu()


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
    tujuan = config.url_database.render_as_string(hide_password=True)
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
    persen_jendela: int | None = None,
) -> int:
    """
    Buka aplikasi berjendela. Import Qt ditunda sampai benar-benar dipakai.

    Menutup sebuah layar TIDAK pernah menutup proses aplikasi, hanya
    memundurkan satu langkah, seolah komputer baru dinyalakan:

        ganti kata sandi wajib dibatalkan -> kembali ke layar masuk
        layar masuk ditutup               -> kembali ke layar pilihan mode
        mesin publik ditutup              -> kembali ke layar pilihan mode
        layar pilihan mode ditutup        -> aplikasi berhenti

    Petugas yang logout tetap kembali langsung ke layar masuk, tanpa
    mampir ke layar pilihan. Layar pilihan mode adalah satu-satunya pintu
    keluar aplikasi. Dahulu menutup layar masuk ikut mematikan aplikasi,
    sehingga satu tekan Esc yang tidak sengaja membuat loket berhenti
    melayani.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog

    from app.services.auth_service import get_auth_service
    from app.ui.login.change_password_dialog import ChangePasswordDialog
    from app.ui.login.login_window import LoginWindow
    from app.ui.login.mode_dialog import (
        ANJUNGAN,
        ANJUNGAN_TOTEM,
        LAYAR_ADMIN,
        LAYAR_ANTRIAN,
        ModeDialog,
    )
    from app.ui.main_window import MainWindow
    from app.ui.style import STYLESHEET

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLESHEET)

    # Diinduk pada `app`, bukan pada jendela: jendela dibuka dan ditutup
    # berkali-kali oleh loop di bawah — setiap logout membuat yang baru —
    # sedangkan pergantian hari harus tetap terpantau di antaranya.
    penyapu = PenyapuHarian()
    pewaktu_hari = QTimer(app)
    pewaktu_hari.timeout.connect(penyapu.periksa)
    pewaktu_hari.start(SELANG_PERIKSA_HARI_MS)

    auth = get_auth_service()
    #: Argumen baris perintah hanya berlaku pada peluncuran pertama. Setelah
    #: layarnya ditutup, tetap lewat dialog pilihan seperti biasa — seseorang
    #: sudah hadir untuk menekan Ctrl+Q.
    mode_pertama = mode_awal

    while True:
        if mode_pertama is not None:
            mode = mode_pertama
            mode_pertama = None
        else:
            pilihan = ModeDialog()
            if pilihan.exec() != QDialog.DialogCode.Accepted:
                logger.info("Aplikasi ditutup dari layar pilihan")
                return 0
            mode = pilihan.pilihan

        if mode in (ANJUNGAN, ANJUNGAN_TOTEM, LAYAR_ANTRIAN):
            # Tanpa login: komputernya menghadap publik dan tidak diawasi.
            if mode in (ANJUNGAN, ANJUNGAN_TOTEM):
                auth.mulai_sesi_kios()
            else:
                auth.mulai_sesi_layar()
            jendela = MainWindow(
                auth,
                anjungan_totem=mode == ANJUNGAN_TOTEM,
                berjendela=berjendela,
                persen_pratinjau=persen_jendela,
            )
            jendela.tampilkan()
            app.exec()
            continue  # mesin publik ditutup -> kembali ke layar pilihan mode

        # Mode petugas: logout kembali langsung ke layar masuk, tidak
        # mampir dulu ke layar pilihan mode.
        while True:
            if lewati_login_pengembang():
                # Uji tampilan: jangan minta nama/sandi, dan jangan paksa
                # ganti sandi bawaan — keduanya menghalangi pekerjaan yang
                # sedang diuji. Admin dan petugas dipisah: admin tidak
                # punya hak memanggil, petugas tidak punya hak pengaturan.
                # Setelah jendela ditutup, kembali ke pilihan mode supaya
                # tidak masuk lagi diam-diam.
                if mode == LAYAR_ADMIN:
                    auth.mulai_sesi_pengembang()
                else:
                    auth.mulai_sesi_petugas()
            else:
                login = LoginWindow(auth)
                if login.exec() != QDialog.DialogCode.Accepted:
                    logger.info("Layar masuk ditutup, kembali ke layar pilihan")
                    break  # -> layar pilihan mode

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
            # tampilkan(), bukan show(): akun layar antrian dibuka penuh
            # tanpa bingkai jendela karena layarnya menghadap pengunjung.
            jendela.tampilkan()
            app.exec()
            if lewati_login_pengembang():
                break
            # petugas logout -> kembali langsung ke layar masuk


def mode_dari_argumen(argv: list[str]) -> str | None:
    """
    Mode mesin yang diminta lewat baris perintah, atau None bila tidak ada.

    `--tv` didahulukan bila keduanya tertulis: layar antrian adalah yang
    paling merugikan bila salah — papan kosong terlihat seluruh ruang
    tunggu, sedangkan anjungan yang keliru masih bisa digantikan petugas
    yang menerbitkan nomor dari mejanya.
    """
    from app.ui.login.mode_dialog import ANJUNGAN, ANJUNGAN_TOTEM, LAYAR_ADMIN, LAYAR_ANTRIAN, LAYAR_PETUGAS

    if "--tv" in argv:
        return LAYAR_ANTRIAN
    if "--kios-totem" in argv:
        return ANJUNGAN_TOTEM
    # --layar adalah nama lama --kios, dipertahankan supaya pintasan yang
    # sudah terpasang di komputer anjungan tidak mati saat aplikasi diperbarui.
    if "--kios" in argv or "--layar" in argv:
        return ANJUNGAN
    if "--admin" in argv:
        return LAYAR_ADMIN
    if "--petugas" in argv:
        return LAYAR_PETUGAS
    return None


def mode_awal_mesin(argv: list[str], db_path) -> str | None:
    """
    Mode peluncuran pertama: flag baris perintah, lalu peran yang tersimpan.

    Flag menang. Ia diketik untuk sekali jalan oleh orang yang sedang
    menguji sesuatu, dan tidak seharusnya kalah oleh berkas yang ditulis
    berminggu-minggu sebelumnya.

    Peran yang tersimpan menutup kegagalan yang paling mungkin terjadi di
    lapangan. Dahulu peran layar hanya hidup di dalam pintasan, sehingga
    komputer yang dinyalakan lewat .exe langsung — atau yang pintasannya
    rusak sesudah pembaruan — membuka dialog pilih-mode lalu layar login,
    tepat di depan pengunjung yang sedang menunggu.

    Hanya berlaku pada peluncuran PERTAMA, sama seperti flag. Sesudah
    layarnya ditutup, tetap lewat dialog pilihan: menutup papan menuntut
    Ctrl+Q, jadi seseorang memang sudah hadir — dan mesin yang selalu
    membuka papannya kembali tidak akan pernah bisa ditutup sama sekali.
    """
    dari_flag = mode_dari_argumen(argv)
    if dari_flag is not None:
        return dari_flag

    from app.core.peran import baca_peran, path_berkas_peran

    mode = baca_peran(path_berkas_peran(db_path)).mode
    if mode:
        logger.info("Peran tersimpan membuka mode '%s'.", mode)
    return mode or None


def pratinjau_dari_argumen(argv: list[str]) -> tuple[bool | None, int | None]:
    """
    Baca `--jendela` dan `--jendela=PERSEN`: (berjendela, persen).

    `berjendela` None berarti argumennya tidak ditulis, dan jendela memilih
    sendiri — totem yang dibuka di layar mendatar otomatis tampil sebagai
    pratinjau tegak (lihat MainWindow). Persen yang tidak terbaca diabaikan
    dengan peringatan, bukan menggagalkan peluncuran: salah ketik di
    pintasan tidak boleh berakhir sebagai layar yang tidak mau terbuka.
    """
    berjendela: bool | None = None
    persen: int | None = None
    for arg in argv:
        if arg == "--jendela":
            berjendela = True
        elif arg.startswith("--jendela="):
            berjendela = True
            nilai = arg.split("=", 1)[1].strip().rstrip("%").strip()
            try:
                persen = int(nilai)
            except ValueError:
                logger.warning(
                    "Persentase %r pada --jendela tidak terbaca; memakai bawaan",
                    nilai,
                )
    return berjendela, persen


def _mesin_publik_tanpa_jaga(argv: list[str], db_path=None) -> bool:
    """
    True bila mesin ini pulih sendiri tanpa klik.

    Dibaca dari flag pintasan, dan — bila folder databasenya diketahui —
    juga dari peran yang tersimpan. Keduanya wajib dijawab sama: sesudah
    peran dapat disimpan di berkas, mesin yang menyebut dirinya televisi
    lewat `peran.json` tidak boleh diperlakukan berbeda daripada mesin yang
    menyebutnya lewat `--tv`.
    """
    if any(flag in argv for flag in ("--tv", "--kios", "--kios-totem", "--layar")):
        return True
    if db_path is None:
        return False

    from app.core.peran import baca_peran, path_berkas_peran

    return baca_peran(path_berkas_peran(db_path)).publik


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

    from app.core.mesin import path_berkas_mesin

    if sedang_uji is None:
        sedang_uji = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if sedang_uji:
        return False
    lewati = os.environ.get("ANTRIAN_LEWATI_SETUP", "").strip().lower()
    if lewati in {"1", "true", "ya", "yes", "on"}:
        return False
    if os.environ.get("ANTRIAN_DB_URL", "").strip():
        return False
    if "--init-only" in argv:
        return False
    if _mesin_publik_tanpa_jaga(argv, db_path):
        return False
    if lewati_login_pengembang():
        return False
    return not path_berkas_mesin(db_path).is_file()


def _jalankan_dialog_mesin() -> bool:
    """
    Tampilkan dialog peran komputer ini. True bila disimpan.

    Memuat ulang konfigurasi setelah disimpan supaya percobaan koneksi
    berikutnya memakai alamat baru. Engine lama dilepas dulu — Windows
    menahan berkas SQLite yang masih terbuka.
    """
    from PySide6.QtWidgets import QApplication, QDialog

    from app.ui.login.setup_mesin_dialog import SetupMesinDialog
    from app.ui.style import STYLESHEET

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
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

    config = get_config()
    setup_logging(config)

    if "--setup" in argv or perlu_setup_awal(argv, config.db_path):
        _jalankan_dialog_mesin()
        config = get_config()

    while True:
        try:
            dibuat = siapkan_database()
            backup_harian()
            # SESUDAH backup: bila sapuan ini ternyata keliru, keadaan sebelum
            # disapu masih tersimpan pada backup pagi ini.
            hanguskan_antrian_hari_lalu()
            break
        except Exception:
            # Traceback hanya masuk log, tidak pernah ditampilkan ke petugas.
            logger.exception("Inisialisasi database gagal")
            if not _laporkan_kegagalan_database(config, berjendela=not hanya_init):
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
        # Import Qt ditunda sampai jendela benar-benar dibuka, sehingga mode
        # dibaca di sini dan bukan di awal main(): --init-only harus tetap
        # berjalan di komputer yang PySide6-nya belum lengkap.
        berjendela, persen_jendela = pratinjau_dari_argumen(argv)
        return _jalankan_ui(
            mode_awal=mode_awal_mesin(argv, config.db_path),
            berjendela=berjendela,
            persen_jendela=persen_jendela,
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
