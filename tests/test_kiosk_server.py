"""Test helper pengaturan token dan Firewall API anjungan."""

from __future__ import annotations

import base64
import re
import subprocess

import pytest

from app.services import kiosk_server


def test_token_baru_acak_dan_cukup_panjang():
    pertama = kiosk_server.token_baru()
    kedua = kiosk_server.token_baru()

    assert len(pertama) >= 64
    assert pertama != kedua


def test_api_otomatis_tidak_dimulai_bila_pengaturan_mati(monkeypatch, tmp_path):
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: False)
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("API seharusnya tidak dijalankan"),
    )

    assert not kiosk_server.mulai_api_otomatis(
        tmp_path, tmp_path / "logs", token="token-cukup-panjang"
    )


def test_api_otomatis_memakai_token_tersimpan_dan_proses_detached(
    monkeypatch, tmp_path
):
    panggilan = {}
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: True)
    monkeypatch.setattr(kiosk_server, "api_sudah_berjalan", lambda port: False)
    monkeypatch.setattr(
        kiosk_server, "status_tugas_api", lambda: kiosk_server.StatusTugas(False)
    )
    monkeypatch.setattr(kiosk_server, "_firewall_sudah_siap", lambda: True)
    monkeypatch.setattr(kiosk_server, "muat_token", lambda: "token-stored")

    def mulai(args, **kwargs):
        panggilan.update(args=args, kwargs=kwargs)

    monkeypatch.setattr(kiosk_server.subprocess, "Popen", mulai)

    assert kiosk_server.mulai_api_otomatis(tmp_path, tmp_path / "logs")
    assert panggilan["args"][-1] == "--kios-api"
    assert panggilan["kwargs"]["env"]["ANTRIAN_KIOS_API_TOKEN"] == "token-stored"
    assert panggilan["kwargs"]["stdin"] == kiosk_server.subprocess.DEVNULL
    assert panggilan["kwargs"]["stdout"].name.endswith("kiosk-api.log")


def test_api_otomatis_mendahulukan_task_scheduler(monkeypatch, tmp_path):
    """Tugas yang terdaftar dinyalakan; tidak ada salinan kedua dijalankan."""
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: True)
    monkeypatch.setattr(kiosk_server, "api_sudah_berjalan", lambda port: False)
    monkeypatch.setattr(
        kiosk_server,
        "status_tugas_api",
        lambda: kiosk_server.StatusTugas(True, "python.exe", "-m app.main --kios-api"),
    )
    monkeypatch.setattr(kiosk_server, "_nyalakan_tugas", lambda: True)
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("Task Scheduler seharusnya dipakai"),
    )

    assert kiosk_server.mulai_api_otomatis(
        tmp_path, tmp_path / "logs", token="token-cukup-panjang"
    )


def test_api_otomatis_menulis_berkas_token_sebelum_menyalakan_tugas(
    monkeypatch, tmp_path
):
    """
    Aplikasi yang dibuka menyalakan tugas SYSTEM; tugas itu hanya membaca
    berkas. Token dari `setx` lama harus sudah tertulis sebelum tugasnya
    menyala, bukan baru saat petugas membuka Layanan Anjungan.
    """
    berkas = tmp_path / kiosk_server.NAMA_BERKAS_TOKEN
    monkeypatch.setattr(kiosk_server, "_db_path_aktif", lambda: tmp_path / "queue.db")
    monkeypatch.setenv("ANTRIAN_KIOS_API_TOKEN", "token-dari-setx-lama")
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: True)
    monkeypatch.setattr(kiosk_server, "api_sudah_berjalan", lambda port: False)
    monkeypatch.setattr(
        kiosk_server,
        "status_tugas_api",
        lambda: kiosk_server.StatusTugas(True, "python.exe", "-m app.main --kios-api"),
    )

    def nyalakan():
        assert berkas.read_text(encoding="utf-8").strip() == "token-dari-setx-lama"
        return True

    monkeypatch.setattr(kiosk_server, "_nyalakan_tugas", nyalakan)

    assert kiosk_server.mulai_api_otomatis(tmp_path, tmp_path / "logs")


def test_api_otomatis_tanpa_token_mencatat_alasannya(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: True)

    with caplog.at_level("WARNING", logger="antrian.kiosk_server"):
        assert not kiosk_server.mulai_api_otomatis(
            tmp_path, tmp_path / "logs", token=""
        )
    assert "token belum disiapkan" in caplog.text


def test_api_otomatis_bawaannya_menyala_di_luar_windows():
    """Tanpa pilihan tersimpan, API dinyalakan: mati harus dipilih tegas."""
    assert kiosk_server.muat_api_otomatis() is True


def test_token_tersimpan_sebagai_berkas_di_folder_database(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTRIAN_KIOS_API_TOKEN", raising=False)
    db_path = tmp_path / "data" / "queue.db"

    kiosk_server.simpan_token("token-rahasia-panjang", db_path)
    monkeypatch.delenv("ANTRIAN_KIOS_API_TOKEN", raising=False)

    assert (tmp_path / "data" / kiosk_server.NAMA_BERKAS_TOKEN).is_file()
    assert kiosk_server.muat_token(db_path) == "token-rahasia-panjang"


def test_token_environment_mengalahkan_berkas(monkeypatch, tmp_path):
    db_path = tmp_path / "queue.db"
    kiosk_server.simpan_token("token-dari-berkas", db_path)
    monkeypatch.setenv("ANTRIAN_KIOS_API_TOKEN", "token-dari-env")

    assert kiosk_server.muat_token(db_path) == "token-dari-env"


def test_token_pendek_ditolak(tmp_path):
    with pytest.raises(ValueError):
        kiosk_server.simpan_token("pendek", tmp_path / "queue.db")


def test_token_dari_environment_ditulis_ke_berkas_untuk_system(monkeypatch, tmp_path):
    """
    Token dari `setx` lama hanya terlihat oleh akun petugas.

    Tugas Task Scheduler berjalan sebagai SYSTEM dan hanya membaca berkas;
    tanpa berkas itu API berhenti dengan "token belum disiapkan" walau
    layar Layanan Anjungan menampilkan token yang sah.
    """
    monkeypatch.setattr(kiosk_server, "_db_path_aktif", lambda: tmp_path / "queue.db")
    monkeypatch.setenv("ANTRIAN_KIOS_API_TOKEN", "token-dari-setx-lama")

    assert kiosk_server.pastikan_berkas_token() == "token-dari-setx-lama"

    berkas = tmp_path / kiosk_server.NAMA_BERKAS_TOKEN
    assert berkas.read_text(encoding="utf-8").strip() == "token-dari-setx-lama"


def test_pasang_layanan_menulis_berkas_token_lebih_dulu(monkeypatch, tmp_path):
    monkeypatch.setattr(kiosk_server, "_db_path_aktif", lambda: tmp_path / "queue.db")
    monkeypatch.delenv("ANTRIAN_KIOS_API_TOKEN", raising=False)
    monkeypatch.setattr(kiosk_server, "muat_token_pengguna", lambda: "")
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0),
    )

    kiosk_server.pasang_layanan_api(tmp_path)

    token = (tmp_path / kiosk_server.NAMA_BERKAS_TOKEN).read_text(encoding="utf-8")
    assert len(token.strip()) >= kiosk_server.PANJANG_TOKEN_MINIMAL


def _skrip_terangkat(perintah: str) -> str:
    cocok = re.search(r"-EncodedCommand', '([^']+)'", perintah)
    assert cocok is not None
    return base64.b64decode(cocok.group(1)).decode("utf-16le")


def test_pasang_layanan_mendaftarkan_tugas_saat_windows_menyala(monkeypatch, tmp_path):
    panggilan = []

    def jalankan(args, **kwargs):
        panggilan.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(kiosk_server.subprocess, "run", jalankan)
    monkeypatch.setattr(kiosk_server, "_db_path_aktif", lambda: tmp_path / "queue.db")

    kiosk_server.pasang_layanan_api(tmp_path)

    assert len(panggilan) == 1, "Firewall dan tugas memakai satu dialog UAC"
    assert "-Verb RunAs" in panggilan[0][-1]
    script = _skrip_terangkat(panggilan[0][-1])
    assert kiosk_server.NAMA_TUGAS in script
    assert "-AtStartup" in script
    assert "'SYSTEM'" in script
    assert "[TimeSpan]::Zero" in script, "batas 72 jam bawaan harus dimatikan"
    assert "--kios-api" in script
    assert str(tmp_path) in script
    assert "-Profile Private" in script
    assert "Start-ScheduledTask" in script
    # Pemeriksa berkala: API yang berhenti di tengah jalan dinyalakan lagi.
    assert "-RepetitionInterval (New-TimeSpan -Minutes 5)" in script
    assert "-Trigger @($pemicu, $jaga)" in script
    assert "-MultipleInstances IgnoreNew" in script


def test_status_tugas_membaca_perintah_terdaftar(monkeypatch):
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 0, stdout="ADA|C:\\App\\AntrianCRO.exe|--kios-api\n"
        ),
    )

    status = kiosk_server.status_tugas_api()

    assert status.terdaftar is True
    assert status.cocok_dengan("C:\\App\\AntrianCRO.exe", ["--kios-api"])
    assert not status.cocok_dengan("D:\\Lain\\AntrianCRO.exe", ["--kios-api"])


def test_status_tugas_mengenali_pemeriksa_berkala(monkeypatch):
    def jalankan(keluaran):
        monkeypatch.setattr(
            kiosk_server.subprocess,
            "run",
            lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=keluaran),
        )
        return kiosk_server.status_tugas_api()

    baru = jalankan("ADA|C:\\App\\AntrianCRO.exe|--kios-api\nJAGA|1\n")
    lama = jalankan("ADA|C:\\App\\AntrianCRO.exe|--kios-api\nJAGA|0\n")

    assert baru.berjaga and baru.cocok_dengan("C:\\App\\AntrianCRO.exe", ["--kios-api"])
    assert not lama.berjaga, "tugas versi lama harus diminta Pasang ulang"


@pytest.mark.parametrize(
    ("keadaan", "pesan"),
    [("", "belum terpasang"), ("Ready", "tidak dijalankan oleh Task Scheduler")],
)
def test_restart_dari_tablet_hanya_untuk_api_milik_tugas(monkeypatch, keadaan, pesan):
    """API yang dinyalakan aplikasi petugas tidak terhenti oleh Stop-ScheduledTask."""
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=keadaan),
    )
    dijalankan = []
    monkeypatch.setattr(
        kiosk_server.subprocess, "Popen", lambda *a, **k: dijalankan.append(a)
    )

    with pytest.raises(RuntimeError, match=pesan):
        kiosk_server.jadwalkan_mulai_ulang_layanan_api()
    assert dijalankan == []


def test_restart_dari_tablet_memakai_skrip_mulai_ulang_yang_sama(monkeypatch):
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="Running\n"),
    )
    dijalankan = []
    monkeypatch.setattr(
        kiosk_server.subprocess, "Popen", lambda args, **k: dijalankan.append(args)
    )

    kiosk_server.jadwalkan_mulai_ulang_layanan_api()

    skrip = base64.b64decode(dijalankan[0][-1]).decode("utf-16le")
    assert skrip.startswith("$ErrorActionPreference = 'Stop'\nStart-Sleep -Seconds 2\n")
    assert skrip.endswith(kiosk_server._SKRIP_TUGAS_MULAI_ULANG)


def test_status_tugas_tidak_ada(monkeypatch):
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="TIDAK-ADA\n"),
    )

    assert kiosk_server.status_tugas_api().terdaftar is False


def test_api_otomatis_menghindari_proses_ganda(monkeypatch, tmp_path):
    monkeypatch.setattr(kiosk_server, "muat_api_otomatis", lambda: True)
    monkeypatch.setattr(kiosk_server, "api_sudah_berjalan", lambda port: True)
    monkeypatch.setattr(
        kiosk_server.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("API sudah berjalan"),
    )

    assert kiosk_server.mulai_api_otomatis(
        tmp_path, tmp_path / "logs", token="token-cukup-panjang"
    )


def test_siapkan_firewall_meminta_elevasi_dan_membatasi_ke_private(monkeypatch):
    panggilan = []

    def jalankan(args, **kwargs):
        panggilan.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(kiosk_server.subprocess, "run", jalankan)

    kiosk_server.siapkan_firewall()

    args, kwargs = panggilan[-1]
    perintah = args[-1]
    cocok = re.search(r"-EncodedCommand', '([^']+)'", perintah)
    assert cocok is not None
    script = base64.b64decode(cocok.group(1)).decode("utf-16le")
    assert "-Verb RunAs" in perintah
    assert "8765" in script
    assert "8766" in script
    assert "-Profile Private" in script
    assert kwargs["timeout"] == 120
    assert len(panggilan) == 2


def test_firewall_yang_sudah_sesuai_tidak_meminta_elevasi(monkeypatch):
    panggilan = []

    def jalankan(args, **kwargs):
        panggilan.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="OK\n")

    monkeypatch.setattr(kiosk_server.subprocess, "run", jalankan)

    kiosk_server.siapkan_firewall()

    assert len(panggilan) == 1
    assert "-Verb RunAs" not in panggilan[0]


def test_kegagalan_siapkan_firewall_dilaporkan_ke_pemanggil(monkeypatch):
    panggilan = []

    def gagal(args, **kwargs):
        panggilan.append(args)
        if len(panggilan) == 1:
            return subprocess.CompletedProcess(args, 0, stdout="")
        return subprocess.CompletedProcess(args, 1, stderr="Izin dibatalkan")

    monkeypatch.setattr(kiosk_server.subprocess, "run", gagal)

    with pytest.raises(RuntimeError, match="Izin dibatalkan"):
        kiosk_server.siapkan_firewall()
