"""
Test dashboard admin/supervisor dan dashboard petugas.

Yang dikunci di sini: siapa boleh membaca apa (ditegakkan di service, bukan
di menu), definisi tiap angka, saringan tanggal/layanan/loket/petugas,
keadaan tanpa data, serta beberapa loket yang berjalan bersamaan.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa

from app.core import clock
from app.core.database import session_scope
from app.core.errors import AuthorizationError
from app.core.security import hash_password
from app.models import Counter, Queue, QueueStatus, RecordStatus, User, UserRole
from app.services.dashboard_service import (
    LOKET_AKTIF,
    LOKET_ISTIRAHAT,
    LOKET_TIDAK_AKTIF,
    PETUGAS_AKTIF,
    PETUGAS_BELUM_ADA_LOKET,
    PETUGAS_ISTIRAHAT,
    PETUGAS_LOKET_NONAKTIF,
    DashboardService,
    FilterDashboard,
)
from app.services.queue_service import QueueService
from tests.conftest import TEST_PASSWORD

# ---------------------------------------------------------------------
# Bantuan
# ---------------------------------------------------------------------


def _masuk(auth, peran: str) -> None:
    auth.logout()
    auth.login(peran, TEST_PASSWORD)


def _antrian(auth, peran: str) -> QueueService:
    _masuk(auth, peran)
    return QueueService(auth)


def _dashboard(auth, peran: str) -> DashboardService:
    _masuk(auth, peran)
    return DashboardService(auth)


def _buat_cro(users: dict, username: str, nama: str) -> int:
    with session_scope() as s:
        user = User(
            branch_id=users["branch_id"],
            username=username,
            full_name=nama,
            password_hash=hash_password(TEST_PASSWORD),
            role=UserRole.CRO,
        )
        s.add(user)
        s.flush()
        return user.id


def _atur_antrian(queue_id: int, **nilai) -> None:
    """Tetapkan kolom waktu/tanggal sebuah nomor secara deterministik."""
    with session_scope() as s:
        s.execute(sa.update(Queue).where(Queue.id == queue_id).values(**nilai))


def _atur_loket(counter_id: int, **nilai) -> None:
    with session_scope() as s:
        s.execute(sa.update(Counter).where(Counter.id == counter_id).values(**nilai))


def _ikat_loket(user_id: int, counter_id: int | None) -> None:
    with session_scope() as s:
        s.execute(
            sa.update(User).where(User.id == user_id).values(default_counter_id=counter_id)
        )


def _layani_selesai(auth, loket: int, peran: str = "cro"):
    antrian = _antrian(auth, peran)
    dipanggil = antrian.call_next(loket)
    antrian.start_service(dipanggil.id)
    return antrian.complete(dipanggil.id)


# ---------------------------------------------------------------------
# Hak akses
# ---------------------------------------------------------------------


@pytest.mark.parametrize("peran", ["admin", "supervisor"])
def test_admin_dan_supervisor_boleh_membuka_dashboard(auth, antrian_siap, peran):
    layanan = _dashboard(auth, peran)

    assert layanan.ringkasan().total == 0
    assert layanan.opsi_filter().loket


@pytest.mark.parametrize("peran", ["cro", "registration", "display"])
def test_peran_lain_ditolak_dashboard_operasional(auth, antrian_siap, peran):
    layanan = _dashboard(auth, peran)

    with pytest.raises(AuthorizationError):
        layanan.ringkasan()
    with pytest.raises(AuthorizationError):
        layanan.opsi_filter()


@pytest.mark.parametrize("peran", ["admin", "supervisor", "registration", "display"])
def test_hanya_petugas_loket_boleh_dashboard_petugas(auth, antrian_siap, peran):
    layanan = _dashboard(auth, peran)

    with pytest.raises(AuthorizationError):
        layanan.ringkasan_petugas()


def test_petugas_tidak_boleh_membaca_audit_log_dashboard(auth, antrian_siap):
    with pytest.raises(AuthorizationError):
        _dashboard(auth, "cro").aktivitas_terakhir()
    with pytest.raises(AuthorizationError):
        _dashboard(auth, "supervisor").aktivitas_terakhir()


def test_admin_membaca_audit_log_tanpa_isi_meta(auth, antrian_siap):
    daftar = _dashboard(auth, "admin").aktivitas_terakhir()

    assert daftar, "login admin harus tercatat"
    assert all(not hasattr(entri, "meta") for entri in daftar)
    assert all(entri.pelaku for entri in daftar)


# ---------------------------------------------------------------------
# Keadaan kosong
# ---------------------------------------------------------------------


def test_dashboard_tanpa_data_tidak_menampilkan_nol_palsu(auth, antrian_siap):
    hasil = _dashboard(auth, "admin").ringkasan()

    assert hasil.total == 0
    assert (hasil.menunggu, hasil.dilayani, hasil.selesai, hasil.batal_lewati) == (0, 0, 0, 0)
    assert hasil.rata_menunggu_detik is None
    assert hasil.rata_layanan_detik is None
    assert hasil.label_rata_menunggu == "—"
    assert len(hasil.per_jam) == 24
    assert sum(hasil.per_jam.values()) == 0
    assert hasil.survey.jumlah == 0
    # Jenis layanan dan loket tetap tampil, supaya susunannya tidak berubah.
    assert len(hasil.per_layanan) >= 2
    assert hasil.loket


def test_tanggal_tanpa_antrian_kosong(auth, antrian_siap, terbitkan):
    terbitkan("A", 2)
    kemarin = clock.today() - timedelta(days=1)

    hasil = _dashboard(auth, "admin").ringkasan(FilterDashboard(tanggal=kemarin))

    assert hasil.total == 0
    assert hasil.tanggal == kemarin


# ---------------------------------------------------------------------
# Hitungan per status
# ---------------------------------------------------------------------


def test_hitungan_per_status_dan_kelompoknya(auth, antrian_siap, terbitkan):
    loket = antrian_siap["loket"]
    terbitkan("A", 6)

    cro = _antrian(auth, "cro")
    selesai = cro.call_next(loket[0])
    cro.start_service(selesai.id)
    cro.complete(selesai.id)

    dilewati = cro.call_next(loket[0])
    cro.skip(dilewati.id)

    batal = cro.call_next(loket[0])
    cro.cancel(batal.id)

    tidak_hadir = cro.call_next(loket[0])
    cro.no_show(tidak_hadir.id)

    sedang = cro.call_next(loket[0])
    cro.start_service(sedang.id)

    hasil = _dashboard(auth, "admin").ringkasan()

    assert hasil.total == 6
    assert hasil.per_status[QueueStatus.COMPLETED] == 1
    assert hasil.per_status[QueueStatus.SKIPPED] == 1
    assert hasil.per_status[QueueStatus.CANCELLED] == 1
    assert hasil.per_status[QueueStatus.NO_SHOW] == 1
    assert hasil.per_status[QueueStatus.SERVING] == 1
    assert hasil.per_status[QueueStatus.WAITING] == 1
    assert hasil.selesai == 1
    assert hasil.dilayani == 1
    assert hasil.menunggu == 1
    # batal + tidak hadir + dilewati
    assert hasil.batal_lewati == 3


def test_dilayani_mencakup_dipanggil_dilayani_dan_ditunda(auth, antrian_siap, terbitkan):
    loket = antrian_siap["loket"]
    terbitkan("A", 3)
    cro = _antrian(auth, "cro")
    cro.call_next(loket[0])  # CALLED
    kedua = cro.call_next(loket[1])
    cro.start_service(kedua.id)  # SERVING
    ketiga = cro.call_next(loket[2])
    cro.start_service(ketiga.id)
    cro.pause(ketiga.id)  # PAUSED

    hasil = _dashboard(auth, "supervisor").ringkasan()

    assert hasil.dilayani == 3
    assert hasil.menunggu == 0


# ---------------------------------------------------------------------
# Rata-rata waktu
# ---------------------------------------------------------------------


def test_rata_rata_menunggu_dan_layanan(auth, antrian_siap, terbitkan):
    loket = antrian_siap["loket"]
    nomor = terbitkan("A", 2)
    cro = _antrian(auth, "cro")
    dasar = clock.now().replace(microsecond=0)

    for baris, (tunggu, lama) in zip(nomor, ((60, 120), (180, 240)), strict=True):
        dipanggil = cro.call_next(loket[0])
        cro.start_service(dipanggil.id)
        cro.complete(dipanggil.id)
        _atur_antrian(
            dipanggil.id,
            created_at=dasar,
            called_at=dasar + timedelta(seconds=tunggu),
            serving_at=dasar + timedelta(seconds=tunggu),
            completed_at=dasar + timedelta(seconds=tunggu + lama),
        )
        assert baris.id  # kedua nomor memang terbit

    hasil = _dashboard(auth, "admin").ringkasan()

    assert hasil.rata_menunggu_detik == pytest.approx(120.0)
    assert hasil.rata_layanan_detik == pytest.approx(180.0)


def test_rata_layanan_hanya_dari_yang_selesai_dan_menunggu_hanya_yang_dipanggil(
    auth, antrian_siap, terbitkan
):
    loket = antrian_siap["loket"]
    terbitkan("A", 2)
    cro = _antrian(auth, "cro")
    batal = cro.call_next(loket[0])
    cro.cancel(batal.id)

    hasil = _dashboard(auth, "admin").ringkasan()

    assert hasil.rata_layanan_detik is None
    assert hasil.rata_menunggu_detik is not None  # nomor batal sempat dipanggil


# ---------------------------------------------------------------------
# Saringan
# ---------------------------------------------------------------------


def test_saringan_tanggal(auth, antrian_siap, terbitkan):
    nomor = terbitkan("A", 3)
    kemarin = clock.today() - timedelta(days=1)
    _atur_antrian(nomor[0].id, queue_date=kemarin)

    layanan = _dashboard(auth, "admin")

    assert layanan.ringkasan().total == 2
    assert layanan.ringkasan(FilterDashboard(tanggal=kemarin)).total == 1


def test_saringan_jenis_layanan(auth, antrian_siap, terbitkan):
    terbitkan("A", 2)
    terbitkan("B", 1)
    kategori = antrian_siap["kategori"]

    layanan = _dashboard(auth, "admin")
    hanya_a = layanan.ringkasan(FilterDashboard(category_id=kategori["A"]))
    hanya_b = layanan.ringkasan(FilterDashboard(category_id=kategori["B"]))

    assert hanya_a.total == 2
    assert hanya_b.total == 1
    assert len(hanya_a.per_layanan) == 1
    assert sum(hanya_a.per_layanan.values()) == 2


def test_beberapa_loket_berjalan_bersamaan(auth, antrian_siap, terbitkan, users):
    loket = antrian_siap["loket"]
    dua = _buat_cro(users, "cro2", "Petugas Dua")
    satu = users["CRO"]
    terbitkan("A", 4)

    cro_satu = _antrian(auth, "cro")
    a = cro_satu.call_next(loket[0])
    cro_satu.start_service(a.id)

    cro_dua = _antrian(auth, "cro2")
    b = cro_dua.call_next(loket[1])
    cro_dua.start_service(b.id)
    cro_dua.complete(b.id)

    layanan = _dashboard(auth, "admin")
    semua = layanan.ringkasan()
    papan = {baris.counter_id: baris for baris in semua.loket}

    assert semua.dilayani == 1
    assert semua.selesai == 1
    assert papan[loket[0]].nomor_aktif == a.queue_number
    assert papan[loket[0]].dipanggil == 1
    assert papan[loket[1]].selesai == 1
    assert papan[loket[1]].nomor_aktif is None

    per_loket = layanan.ringkasan(FilterDashboard(counter_id=loket[1]))
    assert per_loket.total == 1
    assert per_loket.selesai == 1
    assert [b.counter_id for b in per_loket.loket] == [loket[1]]

    per_petugas = layanan.ringkasan(FilterDashboard(user_id=dua))
    assert per_petugas.total == 1
    assert per_petugas.selesai == 1
    petugas_satu = layanan.ringkasan(FilterDashboard(user_id=satu))
    assert petugas_satu.total == 1
    assert petugas_satu.dilayani == 1


def test_saringan_loket_tidak_memuat_nomor_menunggu(auth, antrian_siap, terbitkan):
    """Nomor yang belum dipanggil belum dimiliki loket mana pun."""
    loket = antrian_siap["loket"]
    terbitkan("A", 2)

    hasil = _dashboard(auth, "admin").ringkasan(FilterDashboard(counter_id=loket[0]))

    assert hasil.total == 0
    assert hasil.menunggu == 0


# ---------------------------------------------------------------------
# Grafik per jam
# ---------------------------------------------------------------------


def test_per_jam_mengelompokkan_waktu_terbit(auth, antrian_siap, terbitkan):
    nomor = terbitkan("A", 3)
    hari = clock.today()
    from datetime import datetime

    _atur_antrian(nomor[0].id, created_at=datetime(hari.year, hari.month, hari.day, 8, 5))
    _atur_antrian(nomor[1].id, created_at=datetime(hari.year, hari.month, hari.day, 8, 55))
    _atur_antrian(nomor[2].id, created_at=datetime(hari.year, hari.month, hari.day, 13, 0))

    per_jam = _dashboard(auth, "admin").ringkasan().per_jam

    assert per_jam[8] == 2
    assert per_jam[13] == 1
    assert sum(per_jam.values()) == 3


# ---------------------------------------------------------------------
# Status loket dan petugas
# ---------------------------------------------------------------------


def test_status_loket_aktif_istirahat_dan_tidak_aktif(auth, antrian_siap, users):
    loket = antrian_siap["loket"]
    sekarang = clock.now()
    # Loket 0: petugas hadir, bekerja.
    _atur_loket(
        loket[0], petugas_user_id=users["CRO"], petugas_terlihat_pada=sekarang, on_break=False
    )
    # Loket 1: petugas hadir tetapi istirahat.
    _atur_loket(
        loket[1], petugas_user_id=users["CRO"], petugas_terlihat_pada=sekarang, on_break=True
    )
    # Loket 2: tanda hadir basi, dianggap tidak ada orangnya.
    _atur_loket(
        loket[2],
        petugas_user_id=users["CRO"],
        petugas_terlihat_pada=sekarang - timedelta(minutes=10),
        on_break=False,
    )

    papan = {b.counter_id: b for b in _dashboard(auth, "admin").ringkasan().loket}

    assert papan[loket[0]].status == LOKET_AKTIF
    assert papan[loket[0]].petugas == "Petugas Cro"
    assert papan[loket[1]].status == LOKET_ISTIRAHAT
    assert papan[loket[2]].status == LOKET_TIDAK_AKTIF
    assert papan[loket[2]].petugas is None


def test_loket_nonaktif_selalu_tidak_aktif(auth, antrian_siap, users):
    loket = antrian_siap["loket"]
    _atur_loket(
        loket[0],
        petugas_user_id=users["CRO"],
        petugas_terlihat_pada=clock.now(),
        status=RecordStatus.INACTIVE,
    )

    papan = {b.counter_id: b for b in _dashboard(auth, "admin").ringkasan().loket}

    assert papan[loket[0]].status == LOKET_TIDAK_AKTIF


# ---------------------------------------------------------------------
# Survey pada saringan
# ---------------------------------------------------------------------


def test_survey_mengikuti_saringan(auth, antrian_siap, terbitkan):
    from app.services.survey_service import SurveyService

    loket = antrian_siap["loket"]
    terbitkan("A", 1)
    terbitkan("B", 1)
    cro = _antrian(auth, "cro")
    survey = SurveyService(auth)
    for prefix in ("A", "B"):
        dipanggil = cro.call_next(loket[0], category_id=antrian_siap["kategori"][prefix])
        cro.start_service(dipanggil.id)
        cro.complete(dipanggil.id)
        survey.submit(dipanggil.id, 5 if prefix == "A" else 3)

    layanan = _dashboard(auth, "admin")
    semua = layanan.ringkasan().survey
    hanya_a = layanan.ringkasan(
        FilterDashboard(category_id=antrian_siap["kategori"]["A"])
    ).survey

    assert semua.jumlah == 2
    assert semua.rata_rata == pytest.approx(4.0)
    assert hanya_a.jumlah == 1
    assert hanya_a.rata_rata == pytest.approx(5.0)


# ---------------------------------------------------------------------
# Dashboard petugas
# ---------------------------------------------------------------------


def test_petugas_tanpa_loket_diberi_peringatan(auth, antrian_siap):
    hasil = _dashboard(auth, "cro").ringkasan_petugas()

    assert hasil.status == PETUGAS_BELUM_ADA_LOKET
    assert hasil.counter_id is None
    assert "Loket belum dipilih" in hasil.peringatan


def test_petugas_tanpa_antrian_diberi_peringatan(auth, antrian_siap, users):
    _ikat_loket(users["CRO"], antrian_siap["loket"][0])

    hasil = _dashboard(auth, "cro").ringkasan_petugas()

    assert hasil.status == PETUGAS_AKTIF
    assert hasil.aktif is None
    assert hasil.sisa_antrian == 0
    assert "Tidak ada antrian" in hasil.peringatan


def test_dashboard_petugas_memuat_nomor_aktif_antrean_dan_hitungan(
    auth, antrian_siap, terbitkan, users
):
    loket = antrian_siap["loket"][0]
    _ikat_loket(users["CRO"], loket)
    terbitkan("A", 4)
    cro = _antrian(auth, "cro")

    pertama = cro.call_next(loket)
    cro.start_service(pertama.id)
    cro.complete(pertama.id)
    kedua = cro.call_next(loket)
    cro.skip(kedua.id)
    ketiga = cro.call_next(loket)

    hasil = _dashboard(auth, "cro").ringkasan_petugas()

    assert hasil.status == PETUGAS_AKTIF
    assert hasil.nama_loket
    assert hasil.aktif is not None
    assert hasil.aktif.nomor == ketiga.queue_number
    assert hasil.aktif.status is QueueStatus.CALLED
    assert hasil.sejak_dipanggil_detik is not None
    assert hasil.sisa_antrian == 1
    assert len(hasil.berikutnya) == 1
    assert hasil.selesai == 1
    assert hasil.dilewati == 1
    assert hasil.tidak_hadir == 0
    assert hasil.peringatan is None
    nomor_riwayat = {r.nomor for r in hasil.riwayat}
    assert pertama.queue_number in nomor_riwayat
    assert kedua.queue_number in nomor_riwayat
    assert ketiga.queue_number not in nomor_riwayat  # masih dipegang


def test_petugas_hanya_melihat_riwayat_miliknya(auth, antrian_siap, terbitkan, users):
    loket = antrian_siap["loket"]
    _buat_cro(users, "cro2", "Petugas Dua")
    _ikat_loket(users["CRO"], loket[0])
    terbitkan("A", 2)

    milik_lain = _antrian(auth, "cro2")
    lain = milik_lain.call_next(loket[1])
    milik_lain.start_service(lain.id)
    milik_lain.complete(lain.id)

    saya = _antrian(auth, "cro")
    sendiri = saya.call_next(loket[0])
    saya.start_service(sendiri.id)
    saya.complete(sendiri.id)

    hasil = _dashboard(auth, "cro").ringkasan_petugas()

    assert [r.nomor for r in hasil.riwayat] == [sendiri.queue_number]
    assert hasil.selesai == 1


def test_antrean_berikutnya_mengikuti_layanan_loket(auth, antrian_siap, terbitkan, users):
    from app.services.master_data_service import MasterDataService

    loket = antrian_siap["loket"][0]
    _ikat_loket(users["CRO"], loket)
    terbitkan("A", 2)
    terbitkan("B", 3)
    _masuk(auth, "admin")
    MasterDataService(auth).set_counter_categories(
        loket, [antrian_siap["kategori"]["A"]]
    )

    hasil = _dashboard(auth, "cro").ringkasan_petugas()

    assert hasil.sisa_antrian == 2
    assert all(b.layanan == hasil.berikutnya[0].layanan for b in hasil.berikutnya)


def test_status_istirahat_dan_loket_nonaktif_pada_dashboard_petugas(
    auth, antrian_siap, users
):
    loket = antrian_siap["loket"][0]
    _ikat_loket(users["CRO"], loket)

    _atur_loket(loket, on_break=True)
    istirahat = _dashboard(auth, "cro").ringkasan_petugas()
    assert istirahat.status == PETUGAS_ISTIRAHAT
    assert "istirahat" in istirahat.peringatan.lower()

    _atur_loket(loket, on_break=False, status=RecordStatus.INACTIVE)
    nonaktif = _dashboard(auth, "cro").ringkasan_petugas()
    assert nonaktif.status == PETUGAS_LOKET_NONAKTIF


# ---------------------------------------------------------------------
# Pekerjaan setiap petugas (admin) dan dashboard per login
# ---------------------------------------------------------------------


def test_admin_melihat_pekerjaan_semua_petugas(auth, antrian_siap, users):
    loket = antrian_siap["loket"]
    _buat_cro(users, "cro2", "Petugas Dua")
    kategori = antrian_siap["kategori"]

    _masuk(auth, "registration")
    pendaftaran = QueueService(auth)
    for _ in range(3):
        pendaftaran.create_queue(kategori["A"])

    satu = _antrian(auth, "cro")
    a = satu.call_next(loket[0])
    satu.start_service(a.id)
    satu.complete(a.id)

    dua = _antrian(auth, "cro2")
    b = dua.call_next(loket[1])
    dua.no_show(b.id)

    baris = {p.nama: p for p in _dashboard(auth, "admin").ringkasan().per_petugas}

    assert baris["Petugas Registration"].diterbitkan == 3
    assert baris["Petugas Registration"].peran == "Pendaftaran"
    assert baris["Petugas Cro"].selesai == 1
    assert baris["Petugas Cro"].dipanggil == 1
    assert baris["Petugas Dua"].tidak_hadir == 1
    assert baris["Petugas Dua"].selesai == 0


def test_pekerjaan_petugas_mengikuti_saringan_petugas(auth, antrian_siap, terbitkan, users):
    loket = antrian_siap["loket"]
    dua = _buat_cro(users, "cro2", "Petugas Dua")
    terbitkan("A", 2)
    _layani_selesai(auth, loket[0], "cro")
    cro2 = _antrian(auth, "cro2")
    n = cro2.call_next(loket[1])
    cro2.start_service(n.id)
    cro2.complete(n.id)

    hasil = _dashboard(auth, "supervisor").ringkasan(FilterDashboard(user_id=dua))

    assert [p.nama for p in hasil.per_petugas] == ["Petugas Dua"]


def test_dashboard_petugas_pada_tanggal_lalu(auth, antrian_siap, terbitkan, users):
    loket = antrian_siap["loket"][0]
    _ikat_loket(users["CRO"], loket)
    terbitkan("A", 1)
    selesai = _layani_selesai(auth, loket)
    kemarin = clock.today() - timedelta(days=1)
    _atur_antrian(selesai.id, queue_date=kemarin)

    layanan = _dashboard(auth, "cro")

    assert layanan.ringkasan_petugas().selesai == 0
    assert layanan.ringkasan_petugas(kemarin).selesai == 1


def test_dashboard_pendaftaran_hanya_milik_sendiri(auth, antrian_siap, users):
    kategori = antrian_siap["kategori"]
    _masuk(auth, "registration")
    for prefix in ("A", "A", "B"):
        QueueService(auth).create_queue(kategori[prefix])

    milik = DashboardService(auth).ringkasan_pendaftaran()

    assert milik.total == 3
    assert sum(milik.per_layanan.values()) == 3
    assert len(milik.terakhir) == 3

    # Akun lain tidak mewarisi angkanya.
    with session_scope() as s:
        s.execute(sa.update(User).where(User.id == users["ADMIN"]).values(role=UserRole.REGISTRATION))
    kosong = _dashboard(auth, "admin").ringkasan_pendaftaran()
    assert kosong.total == 0


@pytest.mark.parametrize("peran", ["admin", "supervisor", "cro", "display"])
def test_dashboard_pendaftaran_ditolak_selain_pendaftaran(auth, antrian_siap, peran):
    with pytest.raises(AuthorizationError):
        _dashboard(auth, peran).ringkasan_pendaftaran()
