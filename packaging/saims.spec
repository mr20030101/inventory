# PyInstaller spec for SAIMS Desktop (includes the server for the built-in demo mode).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent

# Windows: extensions built for Python's stable ABI ("abi3": argon2-cffi-bindings, cryptography) load
# python3.dll, which PyInstaller does not always collect. Without it the app fails on start with
# "DLL load failed while importing _ffi".
extra_binaries = []
if sys.platform == "win32":
    python3_dll = Path(sys.base_prefix) / "python3.dll"
    if not python3_dll.exists():
        raise SystemExit(f"python3.dll not found in {sys.base_prefix}")
    extra_binaries.append((str(python3_dll), "."))

a = Analysis(
    [str(root / "run_saims.py")],
    pathex=[str(root)],
    binaries=extra_binaries,
    datas=[
        (str(root / "saims" / "assets"), "saims/assets"),
        (str(root / "saims" / "backend" / "migrations"), "saims/backend/migrations"),
    ],
    hiddenimports=collect_submodules("uvicorn") + [
        "sqlalchemy.dialects.sqlite", "argon2", "_cffi_backend", "PySide6.QtSvg", "PySide6.QtPrintSupport",
        "saims.backend.seed",
    ],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtPdf", "pytest", "uvloop", "httptools", "watchfiles", "websockets"],
    noarchive=False,
)

# Drop Qt pieces this widgets app never loads (Quick/QML/PDF arrive via unused plugins).
_UNUSED = ("Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6VirtualKeyboard", "qtvirtualkeyboard", "qpdf", "Qt6WebEngine")


def _keep(entry):
    dest = entry[0].replace("\\", "/")
    if any(name in dest for name in _UNUSED):
        return False
    if "/translations/" in dest and not Path(dest).name.startswith("qtbase_"):
        return False
    return True


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)
# disable_windowed_traceback: on an unexpected crash, exit instead of showing a dialog nobody can click
# (it blocked the Windows build server for hours).
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SAIMS", console=False,
          disable_windowed_traceback=True,
          icon=str(root / "packaging" / "saims.ico") if sys.platform == "win32" else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SAIMS")
