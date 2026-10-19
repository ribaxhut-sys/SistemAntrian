"""Panel Kesehatan Sistem dan endpoint /health/siap."""

from __future__ import annotations

import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AuthorizationError
from app.services import kesehatan_service as ks
from app.services.status_anjungan import MASALAH, NORMAL, PERINGATAN
from tests.conftest import TEST_PASSWORD

SEKARANG = datetime(2026, 10, 12, 9, 0)
TOKEN_PANJANG = "Zq3xK9vB2mN7pL4tR8wY1uE6iO0aSdFgHjK"


# ---------------------------------------------------------------------
# Penyamaran rahasia
# ---------------------------------------------------------------------


def test_samarkan_menghapus_kata_sandi_url_dan_token():
    teks = ks.samarkan(
        "gagal postgresql+psycopg://antrian:Rahasia99@10.0.0.5:5432/antrian "
        f"password=abc123 Authorization: Bearer {TOKEN_PANJANG} token={TOKEN_PANJANG}"
    )
    assert "Rahasia99" not in teks
    assert "abc123" not in teks
    assert TOKEN_PANJANG not in teks
    # Yang bukan rahasia tetap terbaca supaya pesannya masih berguna.
    assert "antrian:***@10.0.0.5:5432" in teks


def test_ringkas_galat_hanya_24_jam_terakhir_dan_disamarkan():
    baris = [
        "2026-10-10 08:00:00 | ERROR    | antrian.lama | sudah lewat",
        "2026-10-12 07:00:00 | INFO     | antrian.x | bukan galat",
        "2026-10-12 07:30:00 | ERROR    | antrian.backup | Backup otomatis gagal",
        "Traceback (most recent call last):",
        "2026-10-12 08:15:00 | CRITICAL | antrian.db | url postgresql://u:Sandi1@h/db",
    ]
    hasil = ks.ringkas_galat(baris, SEKARANG)
    assert hasil.tingkat == PERINGATAN
    assert hasil.ringkasan.startswith("2 galat")
    assert "08:15" in hasil.ringkasan
    # Terbaru lebih dahulu.
    assert hasil.rincian[0].startswith("08:15 antrian.db")
    assert all("Sandi1" not in r for r in hasil.rincian)
    assert all("sudah lewat" not in r for r in hasil.rincian)


def test_ringkas_galat_tanpa_galat_normal():
    assert ks.ringkas_galat([], SEKARANG).tingkat == NORMAL


# ---------------------------------------------------------------------
# Penilaian murni
# ---------------------------------------------------------------------


def test_nilai_backup_belum_ada_adalah_masalah_bila_dibuat_di_sini():
    assert ks.nilai_backup(terakhir=None, sekarang=SEKARANG).tingkat == MASALAH
    lain = ks.nilai_backup(terakhir=None, dibuat_di_sini=False, sekarang=SEKARANG)
    assert lain.tingkat == ks.INFO


def test_nilai_backup_umur_dan_salinan_kedua():
    segar = ks.nilai_backup(
        terakhir=SEKARANG - timedelta(hours=2),
        nama_berkas="queue-x.db",
        ukuran="1 MB",
        jumlah=3,
        sekarang=SEKARANG,
    )
    assert segar.tingkat == NORMAL
    assert "queue-x.db" in segar.ringkasan

    lama = ks.nilai_backup(terakhir=SEKARANG - timedelta(days=5), sekarang=SEKARANG)
    assert lama.tingkat == PERINGATAN
    assert "5 hari" in lama.ringkasan

    belum_tersalin = ks.nilai_backup(
        terakhir=SEKARANG,
        folder_salinan=Path("E:/backup"),
        salinan_ada=False,
        sekarang=SEKARANG,
    )
    assert belum_tersalin.tingkat == PERINGATAN
    assert "belum tersalin" in belum_tersalin.saran[0]

    tak_terjangkau = ks.nilai_backup(
        terakhir=SEKARANG,
        folder_salinan=Path("E:/backup"),
        salinan_ada=None,
        sekarang=SEKARANG,
    )
    assert "tidak terjangkau" in tak_terjangkau.saran[0]


def test_nilai_disk_ambang():
    gb = 1024**3
    assert ks.nilai_disk("Disk", Path("C:/"), 100 * gb, 50 * gb).tingkat == NORMAL
    assert ks.nilai_disk("Disk", Path("C:/"), 100 * gb, gb // 2).tingkat == PERINGATAN
    assert ks.nilai_disk("Disk", Path("C:/"), 100 * gb, 10 * 1024**2).tingkat == MASALAH


def test_nilai_migrasi():
    assert ks.nilai_migrasi("a1", "a1", True).tingkat == NORMAL
    assert ks.nilai_migrasi("a0", "a1", True).tingkat == MASALAH
    lebih_baru = ks.nilai_migrasi("zz", "a1", False)
    assert lebih_baru.tingkat == PERINGATAN
    assert "Perbarui aplikasi" in lebih_baru.saran[0]


def _perangkat(**ubah):
    data = dict(
        nama="Tablet Depan",
        jenis="anjungan",
        label_jenis="Anjungan",
        terakhir_terlihat=SEKARANG - timedelta(seconds=20),
        versi_nama="2.4.2",
        versi_kode=42,
        printer_ok=True,
        printer_pesan="",
        printer_waktu=SEKARANG - timedelta(minutes=5),
    )
    data.update(ubah)
    return SimpleNamespace(**data)


def test_nilai_perangkat():
    normal = ks.nilai_perangkat(_perangkat(), {"anjungan": 42}, SEKARANG)
    assert normal.tingkat == NORMAL
    assert normal.nama == "Anjungan: Tablet Depan"
    bawaan = ks.nilai_perangkat(_perangkat(nama="Anjungan SM-S908E"), {}, SEKARANG)
    assert bawaan.nama == "Anjungan SM-S908E"

    lama = ks.nilai_perangkat(_perangkat(versi_kode=40), {"anjungan": 42}, SEKARANG)
    assert lama.tingkat == PERINGATAN
    assert "APK" in lama.saran[0]

    printer = ks.nilai_perangkat(
        _perangkat(printer_ok=False, printer_pesan=f"USB gagal token={TOKEN_PANJANG}"),
        {},
        SEKARANG,
    )
    assert printer.tingkat == PERINGATAN
    assert TOKEN_PANJANG not in " ".join(printer.rincian)

    # Galat printer kemarin dari tablet yang belum menyala lagi: keterangan saja.
    printer_kemarin = ks.nilai_perangkat(
        _perangkat(
            terakhir_terlihat=SEKARANG - timedelta(days=1),
            printer_ok=False,
            printer_pesan="printer USB tidak ditemukan",
            printer_waktu=SEKARANG - timedelta(days=1),
        ),
        {},
        SEKARANG,
    )
    assert printer_kemarin.tingkat == ks.INFO
    assert printer_kemarin.rincian

    terputus = ks.nilai_perangkat(
        _perangkat(terakhir_terlihat=SEKARANG - timedelta(minutes=30)), {}, SEKARANG
    )
    assert terputus.tingkat == PERINGATAN

    # Tablet cadangan yang tidak menyala hari ini bukan masalah.
    cadangan = ks.nilai_perangkat(
        _perangkat(terakhir_terlihat=SEKARANG - timedelta(days=2)), {}, SEKARANG
    )
    assert cadangan.tingkat == ks.INFO


# ---------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------


def _service(auth):
    from app.services.backup_service import BackupService

    return ks.KesehatanService(auth, BackupService(auth))


def test_hanya_admin_yang_boleh_memeriksa(auth):
    auth.login("cro", TEST_PASSWORD)
    with pytest.raises(AuthorizationError):
        _service(auth).periksa()


def test_laporan_admin_tanpa_rahasia(admin_auth, app_config):
    from sqlalchemy import select

    from app.core.database import session_scope
    from app.models import User

    laporan = _service(admin_auth).periksa()
    per_nama = {p.nama: p for p in laporan.butir}

    assert per_nama["Database"].tingkat == NORMAL
    assert per_nama["Revisi migrasi"].tingkat == NORMAL
    assert "Backup terakhir" in per_nama
    assert any(p.nama.startswith("Disk") for p in laporan.butir)
    assert "Galat penting (24 jam)" in per_nama
    if app_config.memakai_sqlite:
        assert per_nama["API anjungan"].tingkat == ks.INFO
        assert per_nama["Backup terakhir"].tingkat == MASALAH

    with session_scope() as s:
        hash_admin = s.scalar(select(User.password_hash).where(User.username == "admin"))
    semua = " ".join(
        " ".join((p.ringkasan, *p.saran, *p.rincian)) for p in laporan.butir
    )
    assert hash_admin not in semua
    assert TEST_PASSWORD not in semua


def test_satu_pemeriksaan_gagal_tidak_menghilangkan_yang_lain(admin_auth, monkeypatch):
    def rusak():
        raise OSError("disk hilang")

    monkeypatch.setattr(ks, "_periksa_disk", rusak)
    laporan = _service(admin_auth).periksa()
    per_nama = {p.nama: p for p in laporan.butir}
    assert per_nama["Kapasitas disk"].tingkat == PERINGATAN
    assert "Tidak dapat diperiksa" in per_nama["Kapasitas disk"].ringkasan
    assert per_nama["Database"].tingkat == NORMAL


# ---------------------------------------------------------------------
# /health dan /health/siap
# ---------------------------------------------------------------------


def _klien():
    from fastapi.testclient import TestClient

    from app.kiosk_api import create_app

    return TestClient(create_app("token-uji-panjang", SimpleNamespace()))


def test_health_lama_tetap_byte_demi_byte(database):
    jawab = _klien().get("/health")
    assert jawab.status_code == 200
    # api_sudah_berjalan dan api_terjangkau membandingkan isi persis ini.
    assert jawab.content == b'{"status":"ok"}'


def test_health_siap_ok_bila_database_dan_skema_sesuai(database):
    jawab = _klien().get("/health/siap")
    assert jawab.status_code == 200
    assert jawab.json() == {"status": "ok", "database": "ok", "skema": "ok"}


def test_health_siap_503_tanpa_membocorkan_detail(database, monkeypatch):
    import app.kiosk_api as api

    monkeypatch.setattr(api, "periksa_koneksi", lambda: False)
    jawab = _klien().get("/health/siap")
    assert jawab.status_code == 503
    assert jawab.json() == {
        "status": "gagal",
        "database": "gagal",
        "skema": "tidak_diketahui",
    }


def test_health_siap_503_bila_skema_tertinggal(database, monkeypatch):
    import app.kiosk_api as api

    monkeypatch.setattr(api, "current_revision", lambda: "revisi_lama")
    jawab = _klien().get("/health/siap")
    assert jawab.status_code == 503
    assert jawab.json()["skema"] == "tidak_sesuai"


@pytest.mark.parametrize(("kode", "harapan"), [(503, False), (404, None)])
def test_api_siap_membedakan_gagal_dan_versi_lama(monkeypatch, kode, harapan):
    from app.services import status_anjungan

    def urlopen(url, timeout):
        raise urllib.error.HTTPError(url, kode, "x", {}, None)

    monkeypatch.setattr(status_anjungan.urllib.request, "urlopen", urlopen)
    assert status_anjungan.api_siap("127.0.0.1", 8765) is harapan


# ---------------------------------------------------------------------
# Layar
# ---------------------------------------------------------------------


def test_layar_kesehatan_menampilkan_hasil(qtbot, admin_auth):
    from app.ui.settings.kesehatan_page import KesehatanPage

    halaman = KesehatanPage(_service(admin_auth))
    qtbot.addWidget(halaman)
    # Belum memeriksa sebelum dibuka: semua halaman menu dibangun saat login.
    assert halaman.laporan is None

    halaman.show()
    qtbot.waitUntil(lambda: halaman.laporan is not None, timeout=15_000)
    qtbot.waitUntil(lambda: halaman.tombol_periksa.isEnabled(), timeout=5_000)
    assert halaman.tabel.rowCount() == len(halaman.laporan.butir)
    assert halaman.tabel.item(0, 1).text() == "Database"
    halaman.hentikan()


def test_menu_kesehatan_hanya_untuk_admin(qtbot, auth, antrian_siap):
    from app.ui.main_window import MainWindow

    for peran, harapan in (("admin", True), ("cro", False), ("supervisor", False)):
        auth.logout()
        auth.login(peran, TEST_PASSWORD)
        jendela = MainWindow(auth)
        qtbot.addWidget(jendela)
        menu = [jendela.navigasi.item(i).text() for i in range(jendela.navigasi.count())]
        assert ("Kesehatan Sistem" in menu) is harapan


def test_nilai_backup_kegagalan_terakhir_adalah_masalah():
    hasil = ks.nilai_backup(
        terakhir=SEKARANG - timedelta(hours=1),
        gagal_pada=SEKARANG,
        pesan_gagal="Disk penuh: backup tidak dapat ditulis.",
        # Salinan kedua yang tertinggal tidak boleh menurunkan tingkatnya.
        folder_salinan=Path("E:/backup"),
        salinan_ada=False,
        sekarang=SEKARANG,
    )
    assert hasil.tingkat == MASALAH
    assert "Disk penuh" in hasil.ringkasan


def test_nilai_token_bersama():
    assert ks.nilai_token_bersama(False, 3).tingkat == NORMAL
    # Masih ada tablet lama tanpa pasangan: wajar, hanya keterangan.
    assert ks.nilai_token_bersama(True, 0).tingkat == ks.INFO
    sudah = ks.nilai_token_bersama(True, 2)
    assert sudah.tingkat == PERINGATAN
    assert "dicabut" in sudah.ringkasan


def test_nilai_hash_kata_sandi_normal_dan_peringatan():
    from app.services import kesehatan_service as ks

    assert ks.nilai_hash_kata_sandi(0, 5).tingkat == ks.NORMAL
    hasil = ks.nilai_hash_kata_sandi(2, 5)
    assert hasil.tingkat == ks.PERINGATAN
    assert "2 dari 5" in hasil.ringkasan


def test_nilai_sandi_bawaan():
    assert ks.nilai_sandi_bawaan([]).tingkat == NORMAL
    hasil = ks.nilai_sandi_bawaan(["admin"])
    assert hasil.tingkat == MASALAH
    assert "admin" in hasil.ringkasan
    assert "admin123" not in " ".join((hasil.ringkasan, *hasil.saran))


def test_periksa_sandi_bawaan_menemukan_akun(auth, users):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.core.security import hash_password
    from app.core.seed import DEFAULT_ADMIN_PASSWORD
    from app.models import User

    with session_scope() as s:
        s.execute(
            sa.update(User).where(User.username != "cro").values(
                password_hash=hash_password(TEST_PASSWORD)
            )
        )
    assert ks._periksa_sandi_bawaan().tingkat == NORMAL

    with session_scope() as s:
        s.execute(
            sa.update(User).where(User.username == "cro").values(
                password_hash=hash_password(DEFAULT_ADMIN_PASSWORD)
            )
        )
    hasil = ks._periksa_sandi_bawaan()
    assert hasil.tingkat == MASALAH
    assert "cro" in hasil.ringkasan


def _login_tercatat(komputer, versi, umur):
    import json

    from app.core import clock
    from app.core.database import session_scope
    from app.models import AuditAction, AuditLog

    meta = {"role": "CRO"}
    if komputer is not None:
        meta["komputer"] = komputer
    if versi is not None:
        meta["versi_aplikasi"] = versi
    with session_scope() as s:
        s.add(
            AuditLog(
                action=AuditAction.LOGIN.value,
                entity_type="app_user",
                meta=json.dumps(meta),
                created_at=clock.now() - umur,
            )
        )


def _kosongkan_login():
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditAction, AuditLog

    with session_scope() as s:
        s.execute(
            sa.delete(AuditLog).where(
                AuditLog.action.in_(
                    [AuditAction.LOGIN.value, AuditAction.WINDOWS_PC_PING.value]
                )
            )
        )


def test_periksa_komputer_windows_tanpa_catatan(auth):
    _kosongkan_login()

    (hasil,) = ks._periksa_komputer_windows()

    assert hasil.tingkat == ks.INFO
    assert "30 hari" in hasil.ringkasan


def test_periksa_komputer_windows_memakai_login_terbaru_per_pc(auth):
    from app import __version__

    _kosongkan_login()
    # PC-LOKET-1: login terbaru sudah versi sekarang; yang lama diabaikan.
    _login_tercatat("PC-LOKET-1", "1.0.9", timedelta(days=2))
    _login_tercatat("PC-LOKET-1", __version__, timedelta(hours=1))
    # PC-LOKET-2 masih versi lama.
    _login_tercatat("PC-LOKET-2", "1.0.9", timedelta(days=1))
    # Di luar jendela 30 hari dan login lama tanpa nama komputer: tidak dihitung.
    _login_tercatat("PC-GUDANG", "1.0.1", timedelta(days=31))
    _login_tercatat(None, None, timedelta(hours=2))

    hasil = {p.nama: p for p in ks._periksa_komputer_windows()}

    assert set(hasil) == {"PC Windows: PC-LOKET-1", "PC Windows: PC-LOKET-2"}
    terkini = hasil["PC Windows: PC-LOKET-1"]
    assert terkini.tingkat == NORMAL
    assert __version__ in terkini.ringkasan and not terkini.saran
    tertinggal = hasil["PC Windows: PC-LOKET-2"]
    assert tertinggal.tingkat == PERINGATAN
    assert "1.0.9" in tertinggal.ringkasan
    assert tertinggal.saran


def test_periksa_komputer_windows_versi_tidak_diketahui(auth):
    _kosongkan_login()
    _login_tercatat("PC-LAMA", None, timedelta(hours=3))

    (hasil,) = ks._periksa_komputer_windows()

    assert hasil.tingkat == PERINGATAN
    assert "tidak diketahui" in hasil.ringkasan


def test_nilai_tanda_pembaruan():
    assert ks.nilai_tanda_pembaruan(False).tingkat == ks.INFO
    assert ks.nilai_tanda_pembaruan(True, "1.0.12", True).tingkat == NORMAL
    tanpa = ks.nilai_tanda_pembaruan(True, "1.0.12", False)
    assert tanpa.tingkat == PERINGATAN
    assert "1.0.12" in tanpa.ringkasan


def test_periksa_kata_sandi_mendeteksi_nilai_tanpa_hash(auth, users):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import User
    from app.services import kesehatan_service as ks

    assert ks._periksa_kata_sandi().tingkat == ks.NORMAL

    with session_scope() as s:
        s.execute(
            sa.update(User).where(User.username == "cro").values(password_hash="teks-biasa")
        )

    hasil = ks._periksa_kata_sandi()
    assert hasil.tingkat == ks.PERINGATAN


def test_denyut_pc_tanpa_login_ikut_terlihat_di_kesehatan(auth):
    import json

    from app.core import clock
    from app.core.database import session_scope
    from app.models import AuditAction, AuditLog

    _kosongkan_login()
    with session_scope() as s:
        s.add(
            AuditLog(
                action=AuditAction.WINDOWS_PC_PING.value,
                entity_type="windows_pc",
                meta=json.dumps({"komputer": "PC-BELUM-LOGIN", "versi_aplikasi": "1.0.9"}),
                created_at=clock.now() - timedelta(hours=1),
            )
        )

    (hasil,) = ks._periksa_komputer_windows()

    assert hasil.nama == "PC Windows: PC-BELUM-LOGIN"
    assert hasil.tingkat == PERINGATAN
    assert "1.0.9" in hasil.ringkasan
