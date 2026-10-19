"""
Tandatangani installer Windows untuk dibagikan server ke PC loket.

Dijalankan pengembang di komputernya sendiri, SETELAH build-installer.ps1:

    .\\.venv\\Scripts\\python.exe alat\\tandatangani_pembaruan.py ^
        dist\\Pembaruan-AntrianCRO.exe --kunci "D:\\sistemantrian kunci\\kunci-reset.pem"

Menulis `Pembaruan-AntrianCRO.version` dan `Pembaruan-AntrianCRO.sig` di
sebelah installer, serta `Pembaruan-AntrianCRO.catatan.txt` bila `--catatan`
diberikan (teks "apa yang baru" untuk petugas). Semuanya disalin bersama ke
folder `pembaruan` di komputer server. Kata sandi kunci ditanya lewat papan ketik dan tidak
pernah ditulis ke mana pun.

Berkas ini tidak memuat rahasia dan tidak ikut installer; kunci rahasia
tetap di folder pengembang di luar repository (docs/keamanan-sesi.md).
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import sys
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AKAR))

from app import __version__  # noqa: E402
from app.services.pembaruan_windows import (  # noqa: E402
    NAMA_CATATAN,
    NAMA_TANDA,
    NAMA_VERSI,
    InfoPembaruan,
    bagian_versi,
    bersihkan_catatan,
    pesan_tanda_tangan,
    tanda_sah,
)


def _sha256(berkas: Path) -> str:
    ringkasan = hashlib.sha256()
    with berkas.open("rb") as isi:
        for blok in iter(lambda: isi.read(1024 * 1024), b""):
            ringkasan.update(blok)
    return ringkasan.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("installer", type=Path, help="Pembaruan-AntrianCRO.exe hasil build")
    parser.add_argument("--kunci", type=Path, required=True, help="kunci-reset.pem")
    parser.add_argument(
        "--versi", default=__version__, help=f"versi installer (bawaan {__version__})"
    )
    parser.add_argument(
        "--catatan", type=Path, help="berkas teks catatan rilis (opsional)"
    )
    args = parser.parse_args(argv)

    from cryptography.hazmat.primitives import serialization

    bagian_versi(args.versi)
    installer: Path = args.installer
    ukuran = installer.stat().st_size
    sha256 = _sha256(installer)
    kata_sandi = getpass.getpass("Kata sandi kunci: ")
    kunci = serialization.load_pem_private_key(
        args.kunci.read_bytes(), kata_sandi.encode("utf-8")
    )
    catatan = ""
    if args.catatan is not None:
        catatan = bersihkan_catatan(args.catatan.read_text(encoding="utf-8-sig"))
    tanda = base64.b64encode(
        kunci.sign(pesan_tanda_tangan(args.versi, ukuran, sha256, catatan))
    )
    info = InfoPembaruan(
        args.versi, installer, ukuran, sha256, tanda.decode("ascii"), catatan
    )
    if not tanda_sah(info):
        print(
            "Tanda tangan TIDAK cocok dengan kunci publik di app/core/kunci_publik.py; "
            "kunci yang dipakai salah. Tidak ada berkas yang ditulis.",
            file=sys.stderr,
        )
        return 1

    folder = installer.parent
    (folder / NAMA_VERSI).write_text(args.versi + "\n", encoding="utf-8")
    (folder / NAMA_TANDA).write_text(info.tanda + "\n", encoding="utf-8")
    print(f"Versi {args.versi}, {ukuran} byte, SHA-256 {sha256}")
    print(f"Ditulis: {folder / NAMA_VERSI}")
    print(f"Ditulis: {folder / NAMA_TANDA}")
    if args.catatan is not None:
        (folder / NAMA_CATATAN).write_text(catatan + "\n", encoding="utf-8")
        print(f"Ditulis: {folder / NAMA_CATATAN}")
    print(
        "Salin installer, .version, .sig (dan catatan bila ada) ke folder "
        "'pembaruan' di komputer server."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
