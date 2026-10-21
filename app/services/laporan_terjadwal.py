"""
Laporan mingguan otomatis.

Laporan menuntut hak `REPORT_VIEW` di service layer, jadi tidak bisa dibuat
tanpa sesi seperti backup harian. Pemicunya adalah pemegang hak itu sendiri:
begitu admin atau supervisor membuka aplikasi, laporan minggu lalu (Senin
sampai Minggu) dibuat bila belum ada. Berkas yang sudah ada menjadi
penandanya, sehingga tidak perlu menyimpan keadaan di database dan
membuka aplikasi berkali-kali tidak menggandakan laporan.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.core import clock
from app.core.config import get_config
from app.core.logger import get_logger
from app.services.auth_service import AuthService
from app.services.permissions import Permission
from app.services.report_export import ekspor_pdf
from app.services.report_service import ReportService
from app.services.settings_service import SettingsService

logger = get_logger("laporan.terjadwal")

KUNCI_AKTIF = "laporan.mingguan_aktif"
KUNCI_FOLDER = "laporan.mingguan_folder"
NAMA_FOLDER_BAWAAN = "laporan-mingguan"


def minggu_lalu(hari: date) -> tuple[date, date]:
    """Senin dan Minggu pada minggu penuh sebelum minggu `hari`."""
    senin_ini = hari - timedelta(days=hari.weekday())
    return senin_ini - timedelta(days=7), senin_ini - timedelta(days=1)


def folder_laporan(settings: SettingsService) -> Path:
    isi = settings.get(KUNCI_FOLDER, "").strip()
    return Path(isi) if isi else get_config().base_dir / NAMA_FOLDER_BAWAAN


def nama_berkas(senin: date, minggu: date) -> str:
    return f"laporan-mingguan-{senin:%Y%m%d}-{minggu:%Y%m%d}.pdf"


def buat_laporan_mingguan_bila_perlu(
    auth: AuthService, *, hari: date | None = None
) -> Path | None:
    """
    Buat PDF minggu lalu bila fitur aktif, sesi berhak, dan berkasnya belum ada.

    Mengembalikan jalur berkas yang baru dibuat, atau None bila tidak ada
    yang dibuat. Tidak melempar galat: ini pekerjaan pelengkap yang tidak
    boleh mengganggu petugas yang baru membuka aplikasi.
    """
    try:
        if not auth.has_permission(Permission.REPORT_VIEW):
            return None
        settings = SettingsService(auth)
        if not settings.get_bool(KUNCI_AKTIF, False):
            return None
        senin, minggu = minggu_lalu(hari or clock.today())
        tujuan = folder_laporan(settings) / nama_berkas(senin, minggu)
        if tujuan.exists():
            return None
        tujuan.parent.mkdir(parents=True, exist_ok=True)
        layanan = ReportService(auth)
        laporan = layanan.laporan(senin, minggu)
        # Ditulis ke berkas sementara agar laporan separuh jadi tidak
        # dianggap sudah ada pada pembukaan aplikasi berikutnya.
        sementara = tujuan.with_name(f".{tujuan.name}.sementara")
        try:
            ekspor_pdf(laporan, sementara)
            sementara.replace(tujuan)
        finally:
            sementara.unlink(missing_ok=True)
        layanan.catat_unduhan(laporan, "pdf")
        logger.info("Laporan mingguan dibuat: %s", tujuan.name)
        return tujuan
    except Exception:  # noqa: BLE001 - pelengkap; jangan ganggu pembukaan aplikasi
        logger.exception("Laporan mingguan otomatis gagal")
        return None
