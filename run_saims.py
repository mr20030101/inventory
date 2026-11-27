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


def _crash_log() -> None:
    """Keep the traceback of a crash in <data folder>/crash.log: the windowed app has nowhere else to show it."""
    try:
        from saims.paths import data_dir
        (data_dir() / "crash.log").write_text(traceback.format_exc(), encoding="utf-8")
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
        raise
    sys.exit(code)
