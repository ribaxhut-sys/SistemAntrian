import base64
import hashlib
import io
import json
from types import SimpleNamespace
import urllib.error

import pytest
from fastapi.testclient import TestClient

from app.services.pembaruan_windows import (
    InfoPembaruan,
    NAMA_INSTALLER,
    NAMA_TANDA,
    NAMA_VERSI,
    PembaruanError,
    PembaruanWindowsService,
    audit_hasil_pembaruan,
    catat_pemasangan_dimulai,
    info_pembaruan,
    lebih_baru,
    periksa_pembaruan,
    pembaruan_ditunda,
    pesan_tanda_tangan,
    tanda_sah,
    tunda_pembaruan,
    unduh_pembaruan,
)


def _pasangan_kunci():
    """Kunci uji sekali pakai; kunci pengembang asli tidak pernah ada di tes."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    rahasia = Ed25519PrivateKey.generate()
    publik = rahasia.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return rahasia, base64.b64encode(publik).decode("ascii")


def _tandatangani(rahasia, versi, ukuran, sha):
    return base64.b64encode(rahasia.sign(pesan_tanda_tangan(versi, ukuran, sha))).decode()


def _server(monkeypatch, isi):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_, **__: _Jawaban(json.dumps(isi).encode())
    )


class _Jawaban(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_perbandingan_versi_angka():
    assert lebih_baru("1.0.9", "1.0.8")
    assert lebih_baru("1.1", "1.0.99")
    assert not lebih_baru("1.0.8.0", "1.0.8")
    assert not lebih_baru("1.0.7", "1.0.8")


def test_tunda_pembaruan_hanya_berlaku_untuk_versi_dan_hari_yang_disimpan(
    app_config,
):
    from datetime import date

    tunda_pembaruan("1.2.3", sampai=date(2026, 10, 18), config=app_config)

    assert pembaruan_ditunda(
        "1.2.3", hari=date(2026, 10, 17), config=app_config
    )
    assert not pembaruan_ditunda(
        "1.2.4", hari=date(2026, 10, 17), config=app_config
    )
    assert not pembaruan_ditunda(
        "1.2.3", hari=date(2026, 10, 18), config=app_config
    )


def test_hasil_pemasangan_dicatat_sekali(app_config, database):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditAction, AuditLog

    catat_pemasangan_dimulai("9.8.7", config=app_config)

    assert audit_hasil_pembaruan(
        versi_terpasang="9.8.7", config=app_config
    ) is True
    assert audit_hasil_pembaruan(
        versi_terpasang="9.8.7", config=app_config
    ) is None
    with session_scope() as session:
        jumlah = session.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.WINDOWS_UPDATE_RESULT.value)
        )
    assert jumlah == 1


def test_info_pembaruan_membaca_installer_dan_checksum(tmp_path):
    isi = b"installer-yang-ditandatangani"
    (tmp_path / NAMA_INSTALLER).write_bytes(isi)
    (tmp_path / NAMA_VERSI).write_text("1.2.3\n", encoding="utf-8")

    info = info_pembaruan(tmp_path)

    assert info is not None
    assert info.versi == "1.2.3"
    assert info.ukuran_byte == len(isi)
    assert info.sha256 == hashlib.sha256(isi).hexdigest()


def test_periksa_pembaruan_hanya_menerima_versi_lebih_baru(monkeypatch):
    sha = "a" * 64

    def buka(*_, **__):
        return _Jawaban(
            json.dumps(
                {"latest_version": "1.0.9", "size": 123, "sha256": sha}
            ).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", buka)
    # Tanpa kunci publik (build tanpa fitur kunci): perilaku lama.
    info = periksa_pembaruan(
        "http://server:8765", versi_terpasang="1.0.8", kunci_publik_b64=""
    )
    assert info is not None and info.versi == "1.0.9"
    assert periksa_pembaruan(
        "http://server:8765", versi_terpasang="1.0.9", kunci_publik_b64=""
    ) is None


def test_pembaruan_bertanda_tangan_sah_diterima(monkeypatch):
    rahasia, publik = _pasangan_kunci()
    sha = "b" * 64
    _server(monkeypatch, {
        "latest_version": "1.0.9", "size": 123, "sha256": sha,
        "signature": _tandatangani(rahasia, "1.0.9", 123, sha),
    })

    info = periksa_pembaruan(
        "http://server:8765", versi_terpasang="1.0.8", kunci_publik_b64=publik
    )

    assert info is not None and tanda_sah(info, publik)


@pytest.mark.parametrize("ubah", ["tanpa", "versi", "ukuran", "sha", "kunci_lain"])
def test_pembaruan_tanpa_tanda_tangan_sah_tidak_ditawarkan(monkeypatch, ubah):
    """Penyerang yang menyamar sebagai server tidak dapat menyodorkan installer."""
    rahasia, publik = _pasangan_kunci()
    lain, _ = _pasangan_kunci()
    sha = "c" * 64
    tanda = {
        "tanpa": "",
        "versi": _tandatangani(rahasia, "1.0.10", 123, sha),
        "ukuran": _tandatangani(rahasia, "1.0.9", 124, sha),
        "sha": _tandatangani(rahasia, "1.0.9", 123, "d" * 64),
        "kunci_lain": _tandatangani(lain, "1.0.9", 123, sha),
    }[ubah]
    _server(monkeypatch, {
        "latest_version": "1.0.9", "size": 123, "sha256": sha, "signature": tanda,
    })

    assert periksa_pembaruan(
        "http://server:8765", versi_terpasang="1.0.8", kunci_publik_b64=publik
    ) is None


def test_tanda_tangan_pemulihan_admin_tidak_sah_sebagai_pembaruan():
    """Domain berbeda: kunci yang sama menandatangani dua hal."""
    from app.services import pemulihan_admin

    rahasia, publik = _pasangan_kunci()
    sha = "e" * 64
    mentah = f"1.0.9\n123\n{sha}".encode()
    tanda = base64.b64encode(rahasia.sign(pemulihan_admin.DOMAIN + mentah)).decode()

    assert not tanda_sah(InfoPembaruan("1.0.9", None, 123, sha, tanda), publik)


def test_kunci_publik_tertanam_dipakai_bawaan(monkeypatch):
    """Tanpa argumen, kunci di app/core/kunci_publik.py yang menentukan."""
    rahasia, _ = _pasangan_kunci()
    sha = "f" * 64
    _server(monkeypatch, {
        "latest_version": "99.0", "size": 1, "sha256": sha,
        "signature": _tandatangani(rahasia, "99.0", 1, sha),
    })

    assert periksa_pembaruan("http://server:8765", versi_terpasang="1.0.8") is None


def test_unduhan_ditolak_bila_checksum_berbeda(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_, **__: _Jawaban(b"isi-berubah")
    )
    info = InfoPembaruan("1.0.9", tmp_path / NAMA_INSTALLER, 11, "0" * 64)

    with pytest.raises(PembaruanError, match="keamanan"):
        unduh_pembaruan(info, "http://server:8765")


def test_unduhan_melaporkan_kemajuan(monkeypatch, tmp_path):
    isi = b"installer-yang-cukup-panjang"
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_, **__: _Jawaban(isi)
    )
    info = InfoPembaruan(
        "1.0.9", tmp_path / NAMA_INSTALLER, len(isi), hashlib.sha256(isi).hexdigest()
    )
    kemajuan = []

    hasil = unduh_pembaruan(
        info, "http://server:8765", kemajuan=lambda jumlah, total: kemajuan.append((jumlah, total))
    )

    assert hasil.read_bytes() == isi
    assert kemajuan[0] == (0, len(isi))
    assert kemajuan[-1] == (len(isi), len(isi))


def test_unduhan_melanjutkan_berkas_sementara(monkeypatch, tmp_path):
    isi = b"installer-yang-dapat-dilanjutkan"
    awal = isi[:12]
    folder = tmp_path / "AntrianCRO" / "pembaruan"
    folder.mkdir(parents=True)
    (folder / "AntrianCRO-Setup-1.0.9.exe.tmp").write_bytes(awal)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    permintaan = []

    class JawabanSebagian(_Jawaban):
        status = 206

    def buka(request, **_):
        permintaan.append(request)
        return JawabanSebagian(isi[len(awal) :])

    monkeypatch.setattr("urllib.request.urlopen", buka)
    info = InfoPembaruan(
        "1.0.9", tmp_path / NAMA_INSTALLER, len(isi), hashlib.sha256(isi).hexdigest()
    )

    hasil = unduh_pembaruan(info, "http://server:8765")

    assert hasil.read_bytes() == isi
    assert permintaan[0].get_header("Range") == f"bytes={len(awal)}-"


def test_unduhan_gagal_mempertahankan_bagian_yang_sudah_ada(monkeypatch, tmp_path):
    folder = tmp_path / "AntrianCRO" / "pembaruan"
    folder.mkdir(parents=True)
    sementara = folder / "AntrianCRO-Setup-1.0.9.exe.tmp"
    sementara.write_bytes(b"sebagian")
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_, **__: (_ for _ in ()).throw(urllib.error.URLError("putus")),
    )
    info = InfoPembaruan("1.0.9", tmp_path / NAMA_INSTALLER, 100, "0" * 64)

    with pytest.raises(PembaruanError):
        unduh_pembaruan(info, "http://server:8765")

    assert sementara.read_bytes() == b"sebagian"


def test_unduhan_ditolak_bila_ruang_tidak_cukup(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        "app.services.pembaruan_windows.shutil.disk_usage",
        lambda *_: SimpleNamespace(free=0),
    )
    info = InfoPembaruan("1.0.9", tmp_path / NAMA_INSTALLER, 100, "0" * 64)

    with pytest.raises(PembaruanError, match="Ruang penyimpanan"):
        unduh_pembaruan(info, "http://server:8765")


def test_api_membagikan_installer_windows(monkeypatch, tmp_path):
    from app import kiosk_api

    folder = tmp_path / "pembaruan"
    folder.mkdir()
    isi = b"installer-rilis"
    (folder / NAMA_INSTALLER).write_bytes(isi)
    (folder / NAMA_VERSI).write_text("1.0.9", encoding="utf-8")
    (folder / NAMA_TANDA).write_text("dGFuZGE=\n", encoding="utf-8")
    monkeypatch.setattr(kiosk_api, "base_dir", lambda: tmp_path)

    client = TestClient(kiosk_api.create_app("token-rilis-panjang", object()))
    metadata = client.get("/v1/windows/update")
    unduhan = client.get("/v1/windows/update/download")

    assert metadata.status_code == 200
    assert metadata.json() == {
        "latest_version": "1.0.9",
        "size": len(isi),
        "sha256": hashlib.sha256(isi).hexdigest(),
        "signature": "dGFuZGE=",
        "release_notes": "",
    }
    assert unduhan.status_code == 200
    assert unduhan.content == isi


@pytest.mark.parametrize("untuk_admin", [False, True])
def test_pita_menampilkan_versi_progres_dan_siap_pasang(
    qtbot, tmp_path, untuk_admin
):
    from app.ui.pita_pembaruan import PitaPembaruan

    pita = PitaPembaruan(lambda: None, untuk_admin=untuk_admin)
    qtbot.addWidget(pita)
    info = InfoPembaruan(
        "1.1.0", tmp_path / NAMA_INSTALLER, 10 * 1024 * 1024, "a" * 64
    )

    pita.tampilkan(info)

    assert not pita.isHidden()
    assert "1.1.0" in pita.pesan.text()
    assert pita.tombol.isEnabled()
    assert pita.tombol.text() == (
        "Unduh pembaruan" if untuk_admin else "Unduh di latar belakang"
    )
    pita.sedang_mengunduh()
    assert not pita.tombol.isEnabled()
    pita.perbarui_kemajuan(5 * 1024 * 1024, 10 * 1024 * 1024)
    assert pita.progres.value() == 50
    assert "5.0 MB" in pita.pesan.text()
    pita.siap_dipasang()
    assert pita.tombol.isEnabled()
    assert pita.tombol.text() == (
        "Pasang sekarang" if untuk_admin else "Pasang setelah pelayanan"
    )


def test_cro_tidak_boleh_memasang_saat_memegang_nomor(
    auth, antrian_siap, terbitkan
):
    from app.core.errors import BusinessRuleError
    from app.services.queue_service import QueueService
    from tests.conftest import TEST_PASSWORD

    terbitkan("A")
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    aktif = QueueService(auth).call_next(antrian_siap["loket"][0])

    with pytest.raises(BusinessRuleError, match=aktif.queue_number):
        PembaruanWindowsService(auth).pastikan_pemasangan_diizinkan()


def test_admin_boleh_memasang_walau_cabang_masih_melayani(
    auth, antrian_siap, terbitkan
):
    from app.services.queue_service import QueueService
    from tests.conftest import TEST_PASSWORD

    terbitkan("A")
    auth.logout()
    auth.login("cro", TEST_PASSWORD)
    QueueService(auth).call_next(antrian_siap["loket"][0])
    auth.logout()
    auth.login("admin", TEST_PASSWORD)

    PembaruanWindowsService(auth).pastikan_pemasangan_diizinkan()


def test_denyut_pc_dicatat_sekali_dan_dibatasi(auth):
    import sqlalchemy as sa

    from app.core.database import session_scope
    from app.models import AuditAction, AuditLog
    from app.services import pembaruan_windows as pw

    pw._denyut_terakhir.clear()
    pw._denyut_jam.clear()
    with session_scope() as s:
        s.execute(
            sa.delete(AuditLog).where(
                AuditLog.action == AuditAction.WINDOWS_PC_PING.value
            )
        )

    assert pw.catat_denyut_pc("PC-LOKET-9", "1.0.10", "10.0.0.9") is True
    assert pw.catat_denyut_pc("PC-LOKET-9", "1.0.10", "10.0.0.9") is False
    assert pw.catat_denyut_pc("", "1.0.10") is False
    assert pw.catat_denyut_pc("PC<script>", "abc") is False

    with session_scope() as s:
        jumlah = s.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == AuditAction.WINDOWS_PC_PING.value)
        )
    assert jumlah == 1
    pw._denyut_terakhir.clear()
    pw._denyut_jam.clear()
