r"""
Titik masuk aplikasi.

    .\.venv\Scripts\python.exe -m app.main

Urutan yang dijalankan:

    siapkan database -> masuk -> (wajib ganti kata sandi) -> jendela utama

Argumen:
    --init-only   hanya siapkan database lalu keluar, tanpa membuka jendela.
                  Berguna untuk memeriksa pemasangan di komputer baru.
"""

from __future__ import annotations

import sys

from app.core.config import APP_NAME, get_config
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


def _jalankan_ui() -> int:
    """Buka aplikasi berjendela. Import Qt ditunda sampai benar-benar dipakai."""
    from PySide6.QtWidgets import QApplication, QDialog

    from app.services.auth_service import get_auth_service
    from app.ui.login.change_password_dialog import ChangePasswordDialog
    from app.ui.login.login_window import LoginWindow
    from app.ui.main_window import MainWindow
    from app.ui.style import STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLESHEET)

    auth = get_auth_service()

    login = LoginWindow(auth)
    if login.exec() != QDialog.DialogCode.Accepted:
        logger.info("Aplikasi ditutup dari layar masuk")
        return 0

    sesi = auth.require_session()

    # Akun dengan kata sandi bawaan tidak boleh dipakai bekerja sebelum
    # kata sandinya diganti. Dialognya tidak dapat dibatalkan.
    if sesi.must_change_password:
        dialog = ChangePasswordDialog(auth, wajib=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            auth.logout()
            logger.info("Aplikasi ditutup tanpa mengganti kata sandi wajib")
            return 0

    jendela = MainWindow(auth)
    # tampilkan(), bukan show(): akun layar antrian dibuka penuh tanpa
    # bingkai jendela karena layarnya menghadap pengunjung.
    jendela.tampilkan()
    return app.exec()


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
        return _jalankan_ui()
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
