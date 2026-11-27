"""Start SAIMS Desktop from source (also the PyInstaller entry point): python run_saims.py"""
import sys

from saims.desktop.main import main

if __name__ == "__main__":
    sys.exit(main())
