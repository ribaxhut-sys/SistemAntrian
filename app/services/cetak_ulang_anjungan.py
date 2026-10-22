"""
Cetak ulang tiket di anjungan tempat nomor itu diambil.

Petugas loket (aplikasi Windows) dan tablet anjungan hanya bertemu di
database, jadi permintaan petugas diantrikan di `kiosk_cetak_ulang` dan
diambil tablet lewat API pada penyegaran berikutnya. Modul ini tidak
memeriksa hak pengguna; pemeriksaan itu dilakukan `QueueService`, sedangkan
pengambilan oleh tablet dijaga token perangkat di API.
"""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.models import KioskCetakUlang, KioskDevice, KioskTicketRequest

MENUNGGU = "MENUNGGU"
DIAMBIL = "DIAMBIL"
SELESAI = "SELESAI"
GAGAL = "GAGAL"
KEDALUWARSA = "KEDALUWARSA"

#: Perintah yang tidak diambil tablet dalam waktu ini dibuang: pengunjung
#: sudah pergi, dan tiket tidak boleh keluar sendiri berjam-jam kemudian.
UMUR_MAKS_MENIT = 10
#: Batas jumlah perintah sekali ambil, supaya satu penyegaran tidak mencetak
#: tumpukan tiket.
BATAS_SEKALI_AMBIL = 3


def perangkat_penerbit(queue_id: int) -> tuple[str, str] | None:
    """
    (device_id, nama) anjungan yang menerbitkan nomor ini, atau None.

    None berarti nomor tidak berasal dari anjungan yang dapat ditunjuk:
    diterbitkan dari Windows, atau tablet lama yang memakai token bersama
    tanpa menyebut dirinya, atau tablet itu sudah dicabut.
    """
    with session_scope() as session:
        baris = session.execute(
            sa.select(KioskDevice.device_id, KioskDevice.nama)
            .join(KioskTicketRequest, KioskTicketRequest.device_id == KioskDevice.device_id)
            .where(
                KioskTicketRequest.queue_id == queue_id,
                KioskDevice.dicabut_pada.is_(None),
                # Hanya tablet berpasangan yang bisa mengambil perintahnya
                # (token bersama tidak dapat membuktikan identitasnya).
                KioskDevice.token_hash.is_not(None),
            )
        ).first()
        return (baris.device_id, baris.nama) if baris is not None else None


#: Anjungan dianggap aktif bila terlihat (menghubungi server) dalam waktu ini.
AKTIF_MENIT = 3


def perangkat_tujuan(queue_id: int) -> tuple[str, str] | None:
    """
    (device_id, nama) anjungan tempat tiket cetak ulang nomor ini dikeluarkan.

    Penerbit nomor didahulukan bila ia aktif. Nomor yang tidak berasal dari
    anjungan (pendaftaran, atau perangkat yang sudah dicabut) maupun yang
    penerbitnya sedang mati dialihkan ke anjungan lain yang aktif, paling
    baru terlihat lebih dulu. Bila tidak ada anjungan aktif sama sekali,
    penerbit (kalau ada) tetap dipakai supaya petugas menerima saran
    "tablet tidak menjawab"; None bila tidak ada anjungan berpasangan.
    """
    batas = clock.now() - timedelta(minutes=AKTIF_MENIT)
    penerbit = perangkat_penerbit(queue_id)
    with session_scope() as session:
        aktif = session.execute(
            sa.select(KioskDevice.device_id, KioskDevice.nama, KioskDevice.terakhir_terlihat)
            .where(
                KioskDevice.jenis == "anjungan",
                KioskDevice.dicabut_pada.is_(None),
                KioskDevice.token_hash.is_not(None),
                KioskDevice.terakhir_terlihat >= batas,
            )
            .order_by(KioskDevice.terakhir_terlihat.desc())
        ).all()
    ids = {baris.device_id: baris.nama for baris in aktif}
    if penerbit is not None and penerbit[0] in ids:
        return penerbit
    if aktif:
        return (aktif[0].device_id, aktif[0].nama)
    return penerbit


def antrikan(session, queue_id: int, device_id: str, user_id: int | None) -> KioskCetakUlang:
    """Buat perintah baru; permintaan kembar yang masih menunggu dipakai ulang."""
    ada = session.scalar(
        sa.select(KioskCetakUlang).where(
            KioskCetakUlang.queue_id == queue_id,
            KioskCetakUlang.device_id == device_id,
            KioskCetakUlang.status == MENUNGGU,
        )
    )
    if ada is not None:
        return ada
    baru = KioskCetakUlang(
        device_id=device_id,
        queue_id=queue_id,
        diminta_oleh_user_id=user_id,
        status=MENUNGGU,
    )
    session.add(baru)
    session.flush()
    return baru


def ambil_untuk_perangkat(device_id: str) -> list[tuple[int, int]]:
    """
    Perintah yang menunggu untuk tablet ini, sebagai [(id_perintah, queue_id)].

    Yang diambil langsung ditandai DIAMBIL dalam satu pernyataan, sehingga
    dua penyegaran yang tumpang tindih tidak mencetak tiket dua kali. Yang
    sudah terlalu lama menunggu ditandai KEDALUWARSA dan tidak dikirim.
    """
    sekarang = clock.now()
    batas = sekarang - timedelta(minutes=UMUR_MAKS_MENIT)
    with session_scope() as session:
        session.execute(
            sa.update(KioskCetakUlang)
            .where(
                KioskCetakUlang.device_id == device_id,
                KioskCetakUlang.status == MENUNGGU,
                KioskCetakUlang.created_at < batas,
            )
            .values(status=KEDALUWARSA, selesai_pada=sekarang)
        )
        ids = list(
            session.scalars(
                sa.select(KioskCetakUlang.id)
                .where(
                    KioskCetakUlang.device_id == device_id,
                    KioskCetakUlang.status == MENUNGGU,
                )
                .order_by(KioskCetakUlang.id)
                .limit(BATAS_SEKALI_AMBIL)
            )
        )
        if not ids:
            return []
        diambil = session.execute(
            sa.update(KioskCetakUlang)
            .where(KioskCetakUlang.id.in_(ids), KioskCetakUlang.status == MENUNGGU)
            .values(status=DIAMBIL, diambil_pada=sekarang)
            .returning(KioskCetakUlang.id, KioskCetakUlang.queue_id)
        ).all()
        return sorted((r.id, r.queue_id) for r in diambil)


def catat_hasil(perintah_id: int, device_id: str, berhasil: bool, pesan: str) -> bool:
    """Catat hasil cetak dari tablet; False bila perintah bukan milik tablet ini."""
    with session_scope() as session:
        baris = session.scalar(
            sa.select(KioskCetakUlang).where(
                KioskCetakUlang.id == perintah_id,
                KioskCetakUlang.device_id == device_id,
            )
        )
        if baris is None:
            return False
        baris.status = SELESAI if berhasil else GAGAL
        baris.selesai_pada = clock.now()
        baris.pesan = (pesan or "")[:190]
        return True


def status_terakhir(queue_id: int) -> tuple[str, str] | None:
    """(status, pesan) perintah cetak ulang terbaru untuk nomor ini, atau None."""
    with session_scope() as session:
        baris = session.execute(
            sa.select(KioskCetakUlang.status, KioskCetakUlang.pesan)
            .where(KioskCetakUlang.queue_id == queue_id)
            .order_by(KioskCetakUlang.id.desc())
            .limit(1)
        ).first()
        return (baris.status, baris.pesan or "") if baris is not None else None
