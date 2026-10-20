"""Skenario pemasangan ulang: database kosong, database lama, database sudah terbaru.

Memakai database sementara `antrian_skenario` (dibuat lalu dihapus); tidak menyentuh
`antrian` maupun `antrian_uji`.
"""
import os
import subprocess
import tempfile
from pathlib import Path

import sqlalchemy as sa

AKAR = Path(r"D:\SistemAntrian")
PY = str(AKAR / ".venv" / "Scripts" / "python.exe")
dasar = Path.home().joinpath(".antrian-uji-db").read_text().strip()
assert dasar.endswith("/antrian_uji")
induk = dasar.rsplit("/", 1)[0]
url = induk + "/antrian_skenario"
admin = sa.create_engine(dasar, isolation_level="AUTOCOMMIT")
with admin.connect() as c:
    c.execute(sa.text("DROP DATABASE IF EXISTS antrian_skenario"))
    c.execute(sa.text("CREATE DATABASE antrian_skenario"))

t = tempfile.mkdtemp()
env = dict(os.environ, ANTRIAN_DB_URL=url, ANTRIAN_DB_PATH=t + r"\data", ANTRIAN_LOG_DIR=t + r"\logs",
           ANTRIAN_BACKUP_DIR=t + r"\backup", ANTRIAN_MESIN_PATH=t + r"\mesin.json")
eng = sa.create_engine(url)
TABEL = ("app_user", "service_category", "counter", "branch", "application_setting", "audit_log")


def jalankan(*arg):
    return subprocess.run([PY, *arg], cwd=AKAR, env=env, capture_output=True, text=True, timeout=300)


def keadaan():
    with eng.connect() as c:
        rev = c.scalar(sa.text("select version_num from alembic_version"))
        n = {x: c.scalar(sa.text(f"select count(*) from {x}")) for x in TABEL}
    return rev, n


def init(judul):
    r = jalankan("-m", "app.main", "--init-only")
    rev, n = keadaan()
    print(f"{judul}: exit={r.returncode} revisi={rev}")
    return r.returncode, rev, n


try:
    # 1. database kosong
    k1, rev1, n1 = init("1. DB kosong -> pasang baru")
    assert k1 == 0

    # 2. database lama: turunkan ke revisi lama, lalu pasang versi baru
    for lama in ("f6d2a8c41b07", "e9c3b5a7d281"):
        r = jalankan("-c", f"import sys; sys.path.insert(0, r'{AKAR}'); from alembic import command; "
                     f"from app.core.migrations import alembic_config; command.downgrade(alembic_config(), '{lama}')")
        assert r.returncode == 0, r.stderr[-400:]
        rev_turun, _ = keadaan()
        with eng.begin() as c:  # data pemakaian di versi lama
            c.execute(sa.text("insert into audit_log(action, created_at) values ('UJI_SKENARIO', now())"))
        sebelum = keadaan()[1]
        k, rev, sesudah = init(f"2. DB lama ({rev_turun}) -> pasang 1.2")
        assert k == 0
        hilang = {x: (sebelum[x], sesudah[x]) for x in TABEL if sesudah[x] < sebelum[x]}
        print("   baris sebelum/sesudah:", sebelum, sesudah, "| berkurang:", hilang or "tidak ada")
        assert not hilang

    # 3. database sudah terbaru (pasang ulang versi yang sama)
    k3, rev3, n3 = init("3. DB sudah terbaru -> pasang ulang")
    k4, rev4, n4 = init("3b. sekali lagi")
    assert k3 == 0 and k4 == 0 and n3 == n4

    # 4. database terbaru + aplikasi lama (revisi tak dikenal) -> pesan jelas, data utuh
    with eng.begin() as c:
        c.execute(sa.text("update alembic_version set version_num='revisi_dari_masa_depan'"))
    sebelum = keadaan()[1]
    r = jalankan("-m", "app.main", "--init-only")
    rev5, n5 = keadaan()
    print(f"4. DB lebih baru dari aplikasi: exit={r.returncode} revisi tetap={rev5} data utuh={n5 == sebelum}")
    print("   pesan:", [b for b in r.stderr.splitlines() if "versi aplikasi yang lebih baru" in b][:1])
    assert r.returncode == 1 and rev5 == "revisi_dari_masa_depan" and n5 == sebelum
    print("SEMUA SKENARIO LULUS")
finally:
    eng.dispose()
    with admin.connect() as c:
        c.execute(sa.text("DROP DATABASE IF EXISTS antrian_skenario WITH (FORCE)"))
