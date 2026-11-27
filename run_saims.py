"""Start SAIMS Desktop from source (also the PyInstaller entry point): python run_saims.py"""
import os
import sys
import traceback

# The windowed Windows build has no console, so sys.stdout / sys.stderr are None and any library that writes
# to them (or checks isatty()) would crash. Give them a harmless sink before anything else is imported.
if sys.stdout is None or sys.stderr is None:
    _sink = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stdout or _sink
    sys.stderr = sys.stderr or _sink

# Packaged Windows app: compiled modules in sub-folders of the bundle (e.g. _argon2_cffi_bindings\_ffi.pyd)
# depend on DLLs at the bundle's top level (python3.dll). Windows only searches a module's own folder, the
# program folder and folders registered here, so register the bundle folder before anything is imported.
if getattr(sys, "frozen", False) and sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    _bundle = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.add_dll_directory(_bundle)
    os.environ["PATH"] = _bundle + os.pathsep + os.environ.get("PATH", "")


def _crash_log() -> None:
    """Keep the traceback of a crash in <data folder>/crash.log: the windowed app has nowhere else to show it."""
    try:
        from saims.paths import data_dir
        text = traceback.format_exc()
        error = sys.exc_info()[1]
        if sys.platform == "win32" and "DLL load failed" in str(error):
            try:
                from saims.windiag import report
                text += "\n" + report(str(error))
            except Exception:  # noqa: BLE001
                text += "\n(DLL diagnostics failed: " + traceback.format_exc() + ")"
        (data_dir() / "crash.log").write_text(text, encoding="utf-8")
    except Exception:  # noqa: BLE001 - never hide the original error
        pass


if __name__ == "__main__":
    try:
        from saims.desktop.main import main
        code = main()
    except SystemExit:
        raise
    except BaseException:
        _crash_log()
        if getattr(sys, "frozen", False):
            os._exit(1)  # the windowed app has no console to show the error; exit at once
        raise
    sys.exit(code)
