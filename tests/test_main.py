"""Test titik masuk aplikasi."""

from __future__ import annotations

from pathlib import Path

from app.core import config as config_module
from app.core import database as database_module
from app.core import logger as logger_module
from app.main import main


def test_init_only_mencatat_fondasi_siap_ke_log(
    tmp_path: Path, monkeypatch
) -> None:
    """
    A3b: komputer baru menjalankan --init-only lalu membaca app.log.

    fileConfig Alembic pernah menimpa logging sehingga baris itu hilang
    tepat pada pemasangan pertama — satu-satunya saat pemeriksaan ini
    benar-benar dibutuhkan.
    """
    monkeypatch.setenv("ANTRIAN_DB_PATH", str(tmp_path / "queue.db"))
    monkeypatch.setenv("ANTRIAN_BACKUP_DIR", str(tmp_path / "backup"))
    monkeypatch.setenv("ANTRIAN_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)

    config_module.reset_config()
    database_module.dispose_engine()
    logger_module._configured = False

    assert main(["--init-only"]) == 0

    log = (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
    assert "Fondasi siap" in log
    assert "Migrasi selesai" in log
    assert "admin123" not in log.lower()


# ---------------------------------------------------------------------
# Mode mesin dari baris perintah
# ---------------------------------------------------------------------

def test_tanpa_argumen_mode_ditanyakan() -> None:
    """None berarti dialog pilihan yang menentukan, bukan mode bawaan."""
    from app.main import mode_dari_argumen

    assert mode_dari_argumen([]) is None
    assert mode_dari_argumen(["--init-only"]) is None


def test_argumen_membuka_mesin_yang_sesuai() -> None:
    from app.main import mode_dari_argumen
    from app.ui.login.mode_dialog import ANJUNGAN, LAYAR_ADMIN, LAYAR_ANTRIAN, LAYAR_PETUGAS

    assert mode_dari_argumen(["--tv"]) == LAYAR_ANTRIAN
    assert mode_dari_argumen(["--kios"]) == ANJUNGAN
    assert mode_dari_argumen(["--admin"]) == LAYAR_ADMIN
    assert mode_dari_argumen(["--petugas"]) == LAYAR_PETUGAS


def test_pintasan_lama_layar_tetap_membuka_anjungan() -> None:
    """
    `--layar` sudah terpasang pada shortcut Startup komputer anjungan.

    Memutusnya saat aplikasi diperbarui berarti mesin itu berhenti di
    dialog pilihan setiap mati listrik — tepat keadaan yang argumen ini
    diciptakan untuk mencegah.
    """
    from app.main import mode_dari_argumen
    from app.ui.login.mode_dialog import ANJUNGAN

    assert mode_dari_argumen(["--layar"]) == ANJUNGAN


def test_layar_antrian_didahulukan_bila_dua_argumen_tertulis() -> None:
    """
    Papan kosong terlihat seluruh ruang tunggu, sedangkan anjungan yang
    keliru masih bisa digantikan petugas yang menerbitkan nomor dari
    mejanya.
    """
    from app.main import mode_dari_argumen
    from app.ui.login.mode_dialog import LAYAR_ANTRIAN

    assert mode_dari_argumen(["--kios", "--tv"]) == LAYAR_ANTRIAN


# ---------------------------------------------------------------------
# Sapuan otomatis saat tanggal berganti
# ---------------------------------------------------------------------

def _majukan_hari(monkeypatch, selisih_hari: int) -> None:
    """Geser `clock.today()` maju beberapa hari, tanpa menyentuh jam mesin."""
    from datetime import timedelta

    from app.core import clock

    asli = clock.today()
    monkeypatch.setattr(clock, "today", lambda: asli + timedelta(days=selisih_hari))


def test_penyapu_diam_selama_tanggalnya_belum_berganti(monkeypatch) -> None:
    """Pemeriksaan semenit sekali tidak boleh menyentuh database tiap menit."""
    from app import main as main_module

    dipanggil = []
    monkeypatch.setattr(
        main_module, "hanguskan_antrian_hari_lalu", lambda: dipanggil.append(1) or 0
    )

    penyapu = main_module.PenyapuHarian()

    assert penyapu.periksa() == 0
    assert penyapu.periksa() == 0
    assert dipanggil == []


def test_penyapu_menyapu_begitu_tanggal_berganti(monkeypatch) -> None:
    """
    Anjungan dan layar ruang tunggu menyala terus dan pulih sendiri setelah
    mati listrik, sehingga bisa berhari-hari tidak pernah dibuka ulang.
    """
    from app import main as main_module

    penyapu = main_module.PenyapuHarian()
    monkeypatch.setattr(main_module, "hanguskan_antrian_hari_lalu", lambda: 3)
    _majukan_hari(monkeypatch, 1)

    assert penyapu.periksa() == 3


def test_penyapu_hanya_menyapu_sekali_untuk_hari_yang_sama(monkeypatch) -> None:
    """Pemeriksaan berikutnya semenit lagi tidak mengulang pekerjaan itu."""
    from app import main as main_module

    penyapu = main_module.PenyapuHarian()
    jumlah_sapuan = []
    monkeypatch.setattr(
        main_module,
        "hanguskan_antrian_hari_lalu",
        lambda: jumlah_sapuan.append(1) or 0,
    )
    _majukan_hari(monkeypatch, 1)

    penyapu.periksa()
    penyapu.periksa()
    penyapu.periksa()

    assert len(jumlah_sapuan) == 1


def test_sapuan_yang_gagal_tidak_dicoba_ulang_sepanjang_hari(monkeypatch) -> None:
    """
    Database tidak terjangkau tengah malam bukan alasan mencoba 1440 kali.

    Sapuan berikutnya toh berjalan saat aplikasi dibuka lagi.
    """
    from app import main as main_module

    penyapu = main_module.PenyapuHarian()
    percobaan = []

    def gagal() -> int:
        # Meniru `hanguskan_antrian_hari_lalu` yang menelan kegagalannya
        # sendiri lalu mengembalikan nol.
        percobaan.append(1)
        return 0

    monkeypatch.setattr(main_module, "hanguskan_antrian_hari_lalu", gagal)
    _majukan_hari(monkeypatch, 1)

    penyapu.periksa()
    penyapu.periksa()

    assert len(percobaan) == 1
