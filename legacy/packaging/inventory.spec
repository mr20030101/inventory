# PyInstaller spec, used by build.sh / build.bat. Builds a one-folder app.
import sys
from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    datas=[(str(root / "inventory_app" / "assets"), "inventory_app/assets")],
    hiddenimports=["PySide6.QtSvg"],
    excludes=[
        "tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
        "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
        "PySide6.QtDataVisualization", "PySide6.QtPdf",
    ],
    noarchive=False,
)
# Drop Qt pieces this widgets app never loads (Quick/QML/PDF come in via unused plugins).
_UNUSED = ("Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6VirtualKeyboard", "qtvirtualkeyboard", "qpdf")


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
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InventoryManager",
    console=False,
    icon=str(root / "packaging" / "icon.ico") if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="InventoryManager")
