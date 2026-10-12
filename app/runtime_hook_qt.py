"""Pastikan modul PySide6 memakai DLL Qt dari bundel aplikasi sendiri."""

from __future__ import annotations

import os
import sys
from pathlib import Path


if sys.platform == "win32" and getattr(sys, "frozen", False):
    folder_qt = Path(sys._MEIPASS) / "PySide6"
    if folder_qt.is_dir():
        # PATH membantu DLL turunan Qt; add_dll_directory membuat pemilihan
        # Qt6Core/Qt6Widgets deterministik pada Python Windows modern.
        os.add_dll_directory(str(folder_qt))
        os.environ["PATH"] = str(folder_qt) + os.pathsep + os.environ.get("PATH", "")
