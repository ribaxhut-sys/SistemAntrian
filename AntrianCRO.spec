# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller untuk AntrianCRO.exe.

Dibangun sebagai satu FOLDER (onedir), bukan satu berkas (onefile). Mode
onefile membongkar seluruh isi PySide6 ke folder temporary setiap kali
aplikasi dibuka — beberapa detik penundaan di depan loket yang sedang
melayani, setiap hari. Foldernya cukup disalin apa adanya.

Yang wajib ikut dibundel dan tidak terdeteksi otomatis:

* alembic.ini dan alembic/   Aplikasi menjalankan migration sendiri saat
                             start. Tanpa keduanya, .exe tidak dapat
                             membuat maupun menaikkan skema database.
* tzdata                     Windows tidak menyediakan database timezone
                             IANA, sedangkan seluruh waktu memakai
                             Asia/Jakarta.
"""

from PyInstaller.utils.hooks import collect_data_files

datas = [
    ("alembic.ini", "."),
    ("alembic", "alembic"),
]
# Berkas zona waktu ikut sebagai data, bukan sekadar hidden import: isinya
# tabel biner, bukan modul Python.
datas += collect_data_files("tzdata")

hiddenimports = [
    "tzdata",
    # Dimuat Alembic lewat nama saat runtime, sehingga tidak terlihat oleh
    # analisis import statis PyInstaller.
    "alembic.ddl.sqlite",
    "sqlalchemy.dialects.sqlite",
    # WAJIB. alembic/env.py dan berkas migration dimuat dari file .py saat
    # runtime, bukan diimpor sebagai modul, sehingga PyInstaller tidak pernah
    # menganalisis isinya. Seluruh yang mereka butuhkan harus disebut di sini
    # atau .exe gagal bermigrasi dengan ModuleNotFoundError.
    "logging.config",
    "logging.handlers",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
]

a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Modul besar yang tidak dipakai sama sekali. Membuangnya memangkas
    # ukuran distribusi secara berarti.
    excludes=[
        "tkinter",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AntrianCRO",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # console=False: aplikasi berjendela, tidak boleh memunculkan jendela
    # hitam di belakang layar antrian yang menghadap publik.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AntrianCRO",
)
