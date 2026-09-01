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
    --layar       nama lama --kios. Dipertahankan supaya pintasan yang sudah
                  terpasang di komputer anjungan tidak mati saat aplikasi
                  diperbarui.
    --admin       langsung membuka layar admin. Dari source, masuk sebagai
                  administrator tanpa sandi; pada .exe tetap minta login.
    --petugas     langsung membuka layar petugas. Dari source, masuk sebagai
                  petugas CRO tanpa sandi; pada .exe tetap minta login.
    --init-only   hanya siapkan database lalu keluar, tanpa membuka jendela.
                  Berguna untuk memeriksa pemasangan di komputer baru.

Kedua mesin publik dipasang dengan argumennya masing-masing supaya pulih
sendiri setelah mati listrik, tanpa perlu ada yang mengklik apa pun.
"""

from __future__ import annotations

import sys

from app.core.config import APP_NAME, get_config, lewati_login_pengembang
from app.core.database import dispose_engine, init_database
from app.core.logger import get_logger, setup_logging
from app.core.migrations import current_revision
from app.core.seed import seed_initial_data

logger = get_logger("main")


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


def _laporkan_kegagalan_database(config, *, berjendela: bool) -> None:
    """
    Beri tahu petugas bahwa database tidak dapat dihubungi.

    Wajib berupa jendela, bukan sekadar print. Aplikasi didistribusikan
    sebagai .exe berjendela yang tidak punya terminal, sehingga tanpa ini
    petugas hanya melihat aplikasi gagal terbuka tanpa keterangan apa pun.

    Kegagalan seperti ini menjadi hal biasa begitu database berada di
    komputer lain: server belum menyala, kabel jaringan terlepas, atau
    alamatnya salah ketik.

    Kata sandi database TIDAK pernah ikut ditampilkan.
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
        return

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        kotak = QMessageBox()
        kotak.setIcon(QMessageBox.Icon.Critical)
        kotak.setWindowTitle(APP_NAME)
        kotak.setText("Aplikasi tidak dapat menghubungi database.")
        kotak.setInformativeText(pesan)
        kotak.exec()
        del app
    except Exception:
        # Qt sendiri gagal dimuat. Tidak ada lagi yang bisa ditampilkan;
        # yang penting aplikasi berhenti dengan rapi, bukan menumpuk error.
        logger.exception("Pesan kegagalan database tidak dapat ditampilkan")


def _jalankan_ui(*, mode_awal: str | None = None) -> int:
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
    from PySide6.QtWidgets import QApplication, QDialog

    from app.services.auth_service import get_auth_service
    from app.ui.login.change_password_dialog import ChangePasswordDialog
    from app.ui.login.login_window import LoginWindow
    from app.ui.login.mode_dialog import (
        ANJUNGAN,
        LAYAR_ADMIN,
        LAYAR_ANTRIAN,
        ModeDialog,
    )
    from app.ui.main_window import MainWindow
    from app.ui.style import STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLESHEET)

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

        if mode in (ANJUNGAN, LAYAR_ANTRIAN):
            # Tanpa login: komputernya menghadap publik dan tidak diawasi.
            if mode == ANJUNGAN:
                auth.mulai_sesi_kios()
            else:
                auth.mulai_sesi_layar()
            jendela = MainWindow(auth)
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
    from app.ui.login.mode_dialog import ANJUNGAN, LAYAR_ADMIN, LAYAR_ANTRIAN, LAYAR_PETUGAS

    if "--tv" in argv:
        return LAYAR_ANTRIAN
    # --layar adalah nama lama --kios, dipertahankan supaya pintasan yang
    # sudah terpasang di komputer anjungan tidak mati saat aplikasi diperbarui.
    if "--kios" in argv or "--layar" in argv:
        return ANJUNGAN
    if "--admin" in argv:
        return LAYAR_ADMIN
    if "--petugas" in argv:
        return LAYAR_PETUGAS
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    hanya_init = "--init-only" in argv

    config = get_config()
    setup_logging(config)

    try:
        dibuat = siapkan_database()
        backup_harian()
    except Exception:
        # Traceback hanya masuk log, tidak pernah ditampilkan ke petugas.
        logger.exception("Inisialisasi database gagal")
        _laporkan_kegagalan_database(config, berjendela=not hanya_init)
        return 1

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
        return _jalankan_ui(mode_awal=mode_dari_argumen(argv))
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
