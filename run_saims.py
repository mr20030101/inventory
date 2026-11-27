"""Start SAIMS Desktop from source (also the PyInstaller entry point): python run_saims.py"""
import os
import sys

# The windowed Windows build has no console, so sys.stdout / sys.stderr are None and any library that writes
# to them (or checks isatty()) would crash. Give them a harmless sink before anything else is imported.
if sys.stdout is None or sys.stderr is None:
    _sink = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stdout or _sink
    sys.stderr = sys.stderr or _sink

from saims.desktop.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
