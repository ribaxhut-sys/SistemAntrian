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

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("alembic.ini", "."),
    ("alembic", "alembic"),
]
# Berkas zona waktu ikut sebagai data, bukan sekadar hidden import: isinya
# tabel biner, bukan modul Python.
datas += collect_data_files("tzdata")

hiddenimports = [
    "tzdata",
    # Driver database dipilih saat runtime menurut isi ANTRIAN_DB_URL,
    # sehingga tidak satu pun terlihat oleh analisis import statis.
    "psycopg",
    "psycopg_binary",
    "sqlalchemy.dialects.postgresql",
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
# `--kios-api` loads the API at runtime, so normal import analysis cannot
# discover its modules. FastAPI's request stack is also assembled dynamically.
hiddenimports += ["app.kiosk_api"]
hiddenimports += collect_submodules("fastapi")
hiddenimports += collect_submodules("starlette")
hiddenimports += collect_submodules("uvicorn")

a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["app/runtime_hook_qt.py"],
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

# Qt6Core.dll mengimpor `icuuc.dll` milik Windows (System32, nama fungsi tanpa
# sufiks versi). PyInstaller dapat menemukan icuuc.dll lain lebih dulu dan
# membundelnya — mis. ICU 78 yang namanya bersufiks `_78`. Windows lalu
# memuat salinan itu dan setiap `import PySide6.QtWidgets` gagal dengan
# "The specified procedure could not be found". ICU harus selalu dari sistem.
a.binaries = [
    b for b in a.binaries
    if not os.path.basename(b[0]).lower().startswith(("icuuc", "icuin", "icudt"))
]

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
