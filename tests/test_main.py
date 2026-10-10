"""Test titik masuk aplikasi."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    from app.ui.login.mode_dialog import LAYAR_ADMIN, LAYAR_ANTRIAN, LAYAR_PETUGAS

    assert mode_dari_argumen(["--tv"]) == LAYAR_ANTRIAN
    assert mode_dari_argumen(["--admin"]) == LAYAR_ADMIN
    assert mode_dari_argumen(["--petugas"]) == LAYAR_PETUGAS


def test_anjungan_tidak_lagi_dibuka_di_windows() -> None:
    """
    Anjungan adalah tablet Android (docs/istilah.md). Pintasan lama yang
    masih memakai --kios, --kios-totem, atau --layar membuka dialog biasa.
    """
    from app.main import mode_dari_argumen

    for argumen in (["--kios"], ["--kios-totem"], ["--layar"]):
        assert mode_dari_argumen(argumen) is None


def test_layar_antrian_didahulukan_bila_dua_argumen_tertulis() -> None:
    """
    Papan kosong terlihat seluruh ruang tunggu, sedangkan anjungan yang
    keliru masih bisa digantikan petugas yang menerbitkan nomor dari
    mejanya.
    """
    from app.main import mode_dari_argumen
    from app.ui.login.mode_dialog import LAYAR_ANTRIAN

    assert mode_dari_argumen(["--kios", "--tv"]) == LAYAR_ANTRIAN
    assert mode_dari_argumen(["--kios-totem", "--tv"]) == LAYAR_ANTRIAN


def test_jendela_bukan_mode_mesin() -> None:
    """`--jendela` hanya meniadakan layar penuh, tidak memilih mesin."""
    from app.main import mode_dari_argumen
    from app.ui.login.mode_dialog import LAYAR_ANTRIAN

    assert mode_dari_argumen(["--jendela"]) is None
    assert mode_dari_argumen(["--tv", "--jendela"]) == LAYAR_ANTRIAN


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


def test_jendela_dibaca() -> None:
    from app.main import berjendela_dari_argumen

    assert berjendela_dari_argumen([]) is False
    assert berjendela_dari_argumen(["--tv"]) is False
    assert berjendela_dari_argumen(["--jendela"]) is True
    # Bentuk lama --jendela=PERSEN tetap dibaca sebagai --jendela.
    assert berjendela_dari_argumen(["--tv", "--jendela=40"]) is True


# ---------------------------------------------------------------------
# Peran komputer ini (server / klien)
# ---------------------------------------------------------------------

def test_setup_awal_dilewati_selama_pengembangan(tmp_path, monkeypatch) -> None:
    from app.main import perlu_setup_awal

    monkeypatch.setattr("app.main.lewati_login_pengembang", lambda: True)
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)
    monkeypatch.delenv("ANTRIAN_LEWATI_SETUP", raising=False)
    assert perlu_setup_awal([], tmp_path / "queue.db", sedang_uji=False) is False


def test_setup_awal_pada_exe_baru(tmp_path, monkeypatch) -> None:
    """
    .exe yang baru disalin ke komputer server harus menanyakan perannya.

    Tanpa itu, lima loket diam-diam masing-masing memakai SQLite sendiri.
    """
    from app.main import perlu_setup_awal

    monkeypatch.setattr("app.main.lewati_login_pengembang", lambda: False)
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)
    monkeypatch.delenv("ANTRIAN_LEWATI_SETUP", raising=False)
    monkeypatch.delenv("ANTRIAN_MESIN_PATH", raising=False)
    assert perlu_setup_awal([], tmp_path / "queue.db", sedang_uji=False) is True


def test_setup_awal_tidak_menghalangi_layar_antrian_setelah_mati_listrik(
    tmp_path, monkeypatch
) -> None:
    from app.main import perlu_setup_awal

    monkeypatch.setattr("app.main.lewati_login_pengembang", lambda: False)
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)
    assert perlu_setup_awal(["--tv"], tmp_path / "queue.db", sedang_uji=False) is False


def test_setup_awal_tidak_menghalangi_server_api_anjungan(
    tmp_path, monkeypatch
) -> None:
    from app.main import perlu_setup_awal

    monkeypatch.setattr("app.main.lewati_login_pengembang", lambda: False)
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)
    assert (
        perlu_setup_awal(["--kios-api"], tmp_path / "queue.db", sedang_uji=False)
        is False
    )


def test_setup_awal_dilewati_bila_url_environment_sudah_ada(
    tmp_path, monkeypatch
) -> None:
    from app.main import perlu_setup_awal

    monkeypatch.setattr("app.main.lewati_login_pengembang", lambda: False)
    monkeypatch.setenv(
        "ANTRIAN_DB_URL", "postgresql+psycopg://a:b@192.168.1.10/antrian"
    )
    assert perlu_setup_awal([], tmp_path / "queue.db", sedang_uji=False) is False


def test_setup_awal_dilewati_bila_berkas_mesin_sudah_ada(
    tmp_path, monkeypatch
) -> None:
    from app.core.mesin import PengaturanMesin, path_berkas_mesin, tulis_berkas_mesin
    from app.main import perlu_setup_awal

    monkeypatch.setattr("app.main.lewati_login_pengembang", lambda: False)
    monkeypatch.delenv("ANTRIAN_DB_URL", raising=False)
    monkeypatch.delenv("ANTRIAN_MESIN_PATH", raising=False)
    db = tmp_path / "queue.db"
    tulis_berkas_mesin(path_berkas_mesin(db), PengaturanMesin())
    assert perlu_setup_awal([], db, sedang_uji=False) is False


# ---------------------------------------------------------------------
# Mode peluncuran dari peran yang tersimpan
# ---------------------------------------------------------------------

def _tulis_peran(folder, **isian):
    """Tulis peran.json di folder database sebuah mesin."""
    from app.core.peran import PeranKomputer, tulis_peran

    folder.mkdir(parents=True, exist_ok=True)
    tulis_peran(folder / "peran.json", PeranKomputer(**isian))
    return folder / "queue.db"


def test_tanpa_flag_dan_tanpa_berkas_tetap_lewat_dialog(tmp_path, monkeypatch):
    """Perilaku lama tidak berubah untuk komputer yang belum ditetapkan."""
    monkeypatch.delenv("ANTRIAN_PERAN_PATH", raising=False)
    from app.main import mode_awal_mesin

    assert mode_awal_mesin([], tmp_path / "data" / "queue.db") is None


def test_peran_layar_tersimpan_tidak_lagi_mengubah_startup_windows(tmp_path, monkeypatch):
    """Konfigurasi televisi lama kembali aman ke login petugas."""
    monkeypatch.delenv("ANTRIAN_PERAN_PATH", raising=False)
    from app.main import mode_awal_mesin
    db = _tulis_peran(tmp_path / "data", peran="televisi")

    assert mode_awal_mesin([], db) is None


def test_flag_mengalahkan_peran_tersimpan(tmp_path, monkeypatch):
    """
    Flag diketik untuk sekali jalan oleh orang yang sedang menguji
    sesuatu, dan tidak boleh kalah oleh berkas dari minggu lalu.
    """
    monkeypatch.delenv("ANTRIAN_PERAN_PATH", raising=False)
    from app.main import mode_awal_mesin
    from app.ui.login.mode_dialog import LAYAR_ADMIN

    db = _tulis_peran(tmp_path / "data", peran="televisi")

    assert mode_awal_mesin(["--admin"], db) == LAYAR_ADMIN


def test_berkas_peran_rusak_kembali_ke_dialog(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTRIAN_PERAN_PATH", raising=False)
    from app.main import mode_awal_mesin

    folder = tmp_path / "data"
    folder.mkdir(parents=True)
    (folder / "peran.json").write_text("{ rusak", encoding="utf-8")

    assert mode_awal_mesin([], folder / "queue.db") is None


@pytest.mark.parametrize(
    ("peran", "publik"),
    [
        ("televisi", False),
        ("papan-memanjang", False),
        # Peran lama dari berkas sebelum anjungan pindah ke Android.
        ("anjungan", False),
        ("anjungan-totem", False),
        ("petugas", False),
        ("admin", False),
    ],
)
def test_mesin_publik_dikenali_dari_berkas_seperti_dari_flag(
    tmp_path, monkeypatch, peran, publik
):
    """
    Hanya --tv eksplisit yang masih dianggap mesin publik. Berkas lama
    tidak boleh lagi mengalihkan aplikasi Windows dari login petugas.
    """
    monkeypatch.delenv("ANTRIAN_PERAN_PATH", raising=False)
    from app.main import _mesin_publik_tanpa_jaga

    db = _tulis_peran(tmp_path / "data", peran=peran)

    assert _mesin_publik_tanpa_jaga([], db) is publik


def test_mesin_publik_tanpa_folder_database_tidak_menebak(tmp_path):
    """Pemanggil lama yang tidak menyebut folder tetap berperilaku sama."""
    from app.main import _mesin_publik_tanpa_jaga

    assert _mesin_publik_tanpa_jaga([]) is False
    assert _mesin_publik_tanpa_jaga(["--tv"]) is True
